"""Línea de comandos del pipeline de precios de carburantes.

Uso:
    python -m pipeline_dsia                             # todo el flujo: ingesta → entrenar → predecir → métricas
    python -m pipeline_dsia todo --reentrenar           # lo mismo, reentrenando aunque no sea lunes
    python -m pipeline_dsia metricas                    # Proyecto I: API → contrato → métricas del día → CSV
    python -m pipeline_dsia metricas --top 5 --min-estaciones 30
    python -m pipeline_dsia ingesta                     # precios de hoy + Brent + EUR/USD → historico/
    python -m pipeline_dsia ingesta --desde 2026-06-01  # backfill: rellena los días que falten
    python -m pipeline_dsia entrenar                    # modelo sklearn → models/
    python -m pipeline_dsia predecir                    # precio de mañana + explicación → data/
    python -m pipeline_dsia consultar --provincia sevilla --carburante gasoleo_a
    python -m pipeline_dsia <comando> --help            # opciones de cada comando

Este módulo solo lee los argumentos y llama a la función de cada paso; la lógica
está en los demás módulos (historico, modelo, predecir...). Así, en el Proyecto III
la API podrá llamar a las mismas funciones sin pasar por la línea de comandos.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from pipeline_dsia.config import COLUMNAS, URL_API, DataLoadError, ValidationError
from pipeline_dsia.historico import CARPETA_HISTORICO, ejecutar_ingesta
from pipeline_dsia.loader import cargar_datos
from pipeline_dsia.metrics import (
    comparar_con_provincia,
    diferencia_gasolina_gasoleo,
    mas_baratas,
    media_diferencia_gasolina_gasoleo,
    precio_medio_por_marca,
    precio_medio_por_provincia,
)
from pipeline_dsia.modelo import CARPETA_MODELOS, ejecutar_entrenamiento
from pipeline_dsia.predecir import PREDICCIONES_POR_DEFECTO, ejecutar_consulta, ejecutar_prediccion
from pipeline_dsia.validator import CAMPOS_PRECIO, normalizar_numeros, validar_estaciones

# CSV donde se guardan las gasolineras válidas con sus métricas
SALIDA_POR_DEFECTO = "data/gasolineras_metricas.csv"

# Mostrar todas las columnas al imprimir DataFrames
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


# --- Métricas del día (Proyecto I) -------------------------------------------------------

def ejecutar_metricas(top: int = 10, min_estaciones: int = 20, salida: str = SALIDA_POR_DEFECTO) -> int:
    """API → selección de columnas → normalización → contrato → métricas → CSV.

    Códigos de salida: 0 correcto · 1 ninguna estación válida · 2 error al descargar.
    """
    # 1. Cargar los datos de la API
    try:
        df = cargar_datos(URL_API)
    except DataLoadError as exc:
        print(f"Error al cargar los datos: {exc}")
        return 2
    print(f"Datos consultados el {datetime.now():%d/%m/%Y a las %H:%M}")
    print(f"Estaciones cargadas: {len(df)}")

    # 2. Nuevo DataFrame solo con las columnas que nos interesan
    df_util = df[COLUMNAS].copy()

    # 3. Coma decimal → punto
    df_normalizado = normalizar_numeros(df_util)

    # 4. Contrato de datos → DataFrame de estaciones válidas
    try:
        df_validas, num_invalidas = validar_estaciones(df_normalizado)
    except ValidationError as exc:
        print(f"Validación fallida: {exc}")
        return 1
    print(f"Válidas: {len(df_validas)} · Inválidas: {num_invalidas}")

    # 5. Copia del DataFrame con las columnas nuevas de cada estación
    df_metricas = comparar_con_provincia(df_validas)           # media_prov_<carburante>, dif_<carburante>, dif_media
    df_metricas = diferencia_gasolina_gasoleo(df_metricas)     # dif_gasolina_gasoleo

    # 6. Métricas por pantalla
    print("\n=== Estaciones con las columnas nuevas ===")
    print(df_metricas.head())

    print("\n=== Precio medio por provincia (€/l) ===")
    print(precio_medio_por_provincia(df_validas))

    print(f"\n=== Las {top} gasolineras más baratas de España ===")
    print(mas_baratas(df_validas, top))

    print(f"\n=== Precio medio por marca (marcas con {min_estaciones}+ estaciones) ===")
    print(precio_medio_por_marca(df_validas, min_estaciones))

    diferencia = media_diferencia_gasolina_gasoleo(df_validas)
    print(f"\nLa gasolina 95 cuesta de media {diferencia} €/l más que el gasóleo A")

    # 7. Guardar las gasolineras válidas con sus métricas
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df_metricas.to_csv(ruta, index=False, encoding="utf-8-sig")
    print(f"\nResultados guardados en {ruta} ({len(df_metricas)} gasolineras)")
    return 0


# --- Flujo completo ------------------------------------------------------------------------

def toca_reentrenar(reentrenar: bool = False, hoy: date | None = None) -> bool:
    """Se reentrena si se pide, los lunes o si todavía no hay modelo guardado."""
    hoy = hoy or date.today()
    return reentrenar or hoy.weekday() == 0 or not (CARPETA_MODELOS / "modelo.joblib").exists()


def ejecutar_todo(reentrenar: bool = False) -> int:
    """Ingesta → (los lunes) entrenar → predecir → métricas, con las opciones por defecto.

    Si un paso falla, se sigue con el siguiente: sin ingesta se predice con el último
    histórico y, si el entrenamiento falla, con el último modelo guardado.
    Devuelve 0 si todo ha ido bien o el código del primer paso que ha fallado.
    """
    codigos = {"ingesta": ejecutar_ingesta()}
    if toca_reentrenar(reentrenar):
        codigos["entrenar"] = ejecutar_entrenamiento()
    else:
        print("Hoy no toca reentrenar (se hace los lunes; usa --reentrenar para forzarlo)")
    codigos["predecir"] = ejecutar_prediccion()
    codigos["metricas"] = ejecutar_metricas()

    print("\n=== Resumen ===")
    for paso, codigo in codigos.items():
        print(f"{paso:9s} {'correcto' if codigo == 0 else f'falló (código {codigo})'}")
    return next((codigo for codigo in codigos.values() if codigo), 0)


# --- Tipos para argparse ---------------------------------------------------------------

def entero_positivo(valor: str) -> int:
    """Acepta solo enteros mayores que 0."""
    try:
        numero = int(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un número entero")
    if numero <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")
    return numero


def fraccion(valor: str) -> float:
    """Acepta un número en (0, 1]."""
    try:
        numero = float(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un número")
    if not 0 < numero <= 1:
        raise argparse.ArgumentTypeError("debe estar entre 0 (excluido) y 1")
    return numero


def fecha_iso(valor: str) -> date:
    """Acepta una fecha AAAA-MM-DD."""
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es una fecha AAAA-MM-DD")


# --- Línea de comandos -------------------------------------------------------------------

def crear_parser() -> argparse.ArgumentParser:
    """Un comando por paso del pipeline, cada uno con sus opciones."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia",
        description="Pipeline de precios de carburantes en España: métricas, histórico, modelo y predicción.",
    )
    comandos = parser.add_subparsers(dest="comando", metavar="comando")

    todo = comandos.add_parser(
        "todo", help="todo el flujo: ingesta → entrenar (los lunes) → predecir → métricas (por defecto)",
        description="Ejecuta todo el pipeline con las opciones por defecto. Es lo que se lanza sin comando.",
    )
    todo.add_argument("--reentrenar", action="store_true", help="reentrenar el modelo aunque no sea lunes")

    metricas = comandos.add_parser(
        "metricas", help="métricas descriptivas de hoy (Proyecto I)",
        description="Descarga los precios de hoy, los valida y calcula métricas.",
    )
    metricas.add_argument("--top", type=entero_positivo, default=10,
                          help="número de gasolineras en el ranking de más baratas (por defecto 10)")
    metricas.add_argument("--min-estaciones", type=entero_positivo, default=20,
                          help="mínimo de gasolineras para que una marca aparezca en el ranking de marcas (por defecto 20)")
    metricas.add_argument("--salida", metavar="RUTA_CSV", default=SALIDA_POR_DEFECTO,
                          help=f"CSV con las gasolineras válidas y sus métricas (por defecto {SALIDA_POR_DEFECTO})")

    ingesta = comandos.add_parser(
        "ingesta", help="guarda los precios del día y los mercados en el histórico",
        description="Guarda los precios del día y los datos de mercado en el histórico.",
    )
    ingesta.add_argument("--desde", type=fecha_iso, metavar="AAAA-MM-DD",
                         help="backfill: descarga del histórico del Ministerio los días que falten desde esta fecha hasta ayer")
    ingesta.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO,
                         help=f"carpeta del histórico (por defecto {CARPETA_HISTORICO})")
    ingesta.add_argument("--sin-mercados", action="store_true", help="no descargar Brent ni EUR/USD")

    entrenar = comandos.add_parser(
        "entrenar", help="entrena el modelo sklearn con el histórico",
        description="Entrena el modelo que predice la variación del precio de cada estación al día siguiente.",
    )
    entrenar.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO, help="carpeta del histórico")
    entrenar.add_argument("--modelos", type=Path, default=CARPETA_MODELOS, help="carpeta donde se guarda el modelo")
    entrenar.add_argument("--fraccion-test", type=fraccion, default=0.2,
                          help="parte final de los días reservada para el test (por defecto 0.2)")
    entrenar.add_argument("--muestra-busqueda", type=fraccion, default=0.2,
                          help="fracción de estaciones usada en la búsqueda de hiperparámetros (por defecto 0.2)")
    entrenar.add_argument("--sin-busqueda", action="store_true",
                          help="no buscar: usar los hiperparámetros del último entrenamiento (o los de por defecto)")

    predecir = comandos.add_parser(
        "predecir", help="predice el precio de mañana y lo explica con IA",
        description="Predice el precio de mañana de cada estación con el modelo entrenado.",
    )
    predecir.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO, help="carpeta del histórico")
    predecir.add_argument("--modelos", type=Path, default=CARPETA_MODELOS, help="carpeta del modelo")
    predecir.add_argument("--salida", type=Path, default=Path("data"), help="carpeta de resultados (por defecto data/)")

    consultar = comandos.add_parser(
        "consultar", help="consulta el precio previsto para mañana",
        description="Consulta el precio previsto para mañana. Los filtros se pueden combinar.",
    )
    consultar.add_argument("--provincia", help="nombre de la provincia o parte de él (sin importar tildes ni mayúsculas)")
    consultar.add_argument("--municipio", help="nombre del municipio o parte de él")
    consultar.add_argument("--rotulo", help="marca de la estación o parte de ella (p. ej. repsol)")
    consultar.add_argument("--estacion", metavar="ID", help="identificador de la estación (columna id)")
    consultar.add_argument("--carburante", choices=CAMPOS_PRECIO, help="un solo carburante (por defecto, todos)")
    consultar.add_argument("--top", type=int, default=5,
                           help="número de estaciones más baratas que se listan (por defecto 5; 0 para no listar)")
    consultar.add_argument("--predicciones", type=Path, default=PREDICCIONES_POR_DEFECTO,
                           help=f"fichero de predicciones (por defecto {PREDICCIONES_POR_DEFECTO})")
    return parser


def main(argv=None) -> int:
    args = crear_parser().parse_args(argv)
    if args.comando in (None, "todo"):
        return ejecutar_todo(getattr(args, "reentrenar", False))
    if args.comando == "metricas":
        return ejecutar_metricas(args.top, args.min_estaciones, args.salida)
    if args.comando == "ingesta":
        return ejecutar_ingesta(args.desde, args.carpeta, args.sin_mercados)
    if args.comando == "entrenar":
        return ejecutar_entrenamiento(args.carpeta, args.modelos, args.fraccion_test,
                                      args.muestra_busqueda, args.sin_busqueda)
    if args.comando == "predecir":
        return ejecutar_prediccion(args.carpeta, args.modelos, args.salida)
    return ejecutar_consulta(args.provincia, args.municipio, args.rotulo, args.estacion,
                             args.carburante, args.top, args.predicciones)


if __name__ == "__main__":
    sys.exit(main())
