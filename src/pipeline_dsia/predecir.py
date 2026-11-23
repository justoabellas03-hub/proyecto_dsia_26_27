"""Inferencia y consulta de las predicciones.

Secciones:
    1. Predicción (ejecutar_prediccion): precio de mañana de cada estación y carburante,
       con la explicación del cliente de IA.
    2. Consulta (ejecutar_consulta): precio previsto por estación, municipio o provincia.
"""

import logging
import unicodedata
from pathlib import Path

import pandas as pd

from pipeline_dsia.config import DataLoadError, ModelError, configurar_logs, leer_configuracion
from pipeline_dsia.historico import CARPETA_HISTORICO, a_formato_largo, cargar_historico, cargar_mercados
from pipeline_dsia.ia import (
    ClienteIA, Explicacion, ResumenCarburante, ResumenPrediccion, crear_cliente, explicar_con_respaldo,
)
from pipeline_dsia.modelo import CARPETA_MODELOS, FEATURES, RETARDOS_PRECIO, cargar_modelo, construir_features

log = logging.getLogger(__name__)


# ======================================================================================
# 1. Predicción
# ======================================================================================

# Inferencia: predice el precio de mañana de cada estación y carburante.
#
# Uso:
# python -m pipeline_dsia predecir                  # usa historico/ y models/
# python -m pipeline_dsia predecir --salida data/   # carpeta de resultados
# python -m pipeline_dsia predecir --help
#
# Pasos:
# 1. Cargar los últimos días del histórico y construir las features.
# 2. Cargar el modelo sklearn (models/modelo.joblib) y predecir la variación.
# 3. Guardar data/predicciones.csv (una fila por estación × carburante).
# 4. Resumir la predicción y pedir la explicación al cliente de IA
# (Hugging Face o mock) → data/informe_prediccion.md.
#
# Códigos de salida: 0 correcto · 2 no hay histórico · 3 no hay modelo entrenado.

# Para las features del último día basta con los días del retardo más largo (+ margen)
DIAS_NECESARIOS = max(RETARDOS_PRECIO) + 3

# Una estación cuenta como "sube" o "baja" solo si la variación prevista llega a medio céntimo.
# El modelo predice una media: sin umbral, una previsión de −0,1 céntimos contaría como bajada.
UMBRAL_CAMBIO = 0.005   # €/l

COLUMNAS_SALIDA = [
    "fecha_prediccion", "id", "rotulo", "municipio", "provincia", "carburante",
    "precio_hoy", "variacion_prevista", "precio_previsto",
]


def predecir_manana(modelo, datos: pd.DataFrame) -> pd.DataFrame:
    """Aplica el modelo a las filas del último día del histórico.

    Args:
        modelo: Pipeline de sklearn ya entrenado.
        datos: Salida de construir_features.

    Returns:
        Una fila por estación × carburante con el precio de hoy, la variación
        prevista y el precio previsto para mañana (€/l, redondeado a milésimas
        como los precios reales).
    """
    ultimo_dia = datos["fecha"].max()
    hoy = datos[datos["fecha"] == ultimo_dia].copy()
    hoy["variacion_prevista"] = modelo.predict(hoy[FEATURES]).round(3)
    hoy["fecha_prediccion"] = ultimo_dia + pd.Timedelta(days=1)
    hoy = hoy.rename(columns={"precio": "precio_hoy"})
    hoy["precio_previsto"] = (hoy["precio_hoy"] + hoy["variacion_prevista"]).round(3)
    return hoy[COLUMNAS_SALIDA + ["var_brent_7"]].reset_index(drop=True)


def resumir(predicciones: pd.DataFrame) -> ResumenPrediccion:
    """Predicciones de todas las estaciones → resumen nacional por carburante."""
    carburantes = []
    for carburante, grupo in predicciones.groupby("carburante"):
        carburantes.append(ResumenCarburante(
            carburante=carburante,
            precio_medio_hoy=round(float(grupo["precio_hoy"].mean()), 3),
            variacion_media_cts=round(float(grupo["variacion_prevista"].mean()) * 100, 2),
            pct_suben=round(float((grupo["variacion_prevista"] >= UMBRAL_CAMBIO).mean()) * 100, 1),
            pct_bajan=round(float((grupo["variacion_prevista"] <= -UMBRAL_CAMBIO).mean()) * 100, 1),
        ))
    brent = predicciones["var_brent_7"].dropna()
    return ResumenPrediccion(
        fecha_prediccion=predicciones["fecha_prediccion"].iloc[0].date(),
        var_brent_7=round(float(brent.iloc[0]), 2) if len(brent) else None,
        carburantes=carburantes,
    )


def escribir_informe_prediccion(ruta: Path, resumen: ResumenPrediccion, explicacion: Explicacion) -> None:
    lineas = [
        f"# Previsión de precios para el {resumen.fecha_prediccion:%d/%m/%Y}",
        "",
        explicacion.texto,
        "",
        "| Carburante | Precio medio hoy (€/l) | Variación media prevista (cts) | % suben ≥ 0,5 cts | % bajan ≥ 0,5 cts |",
        "| --- | --- | --- | --- | --- |",
    ]
    lineas += [f"| {c.carburante} | {c.precio_medio_hoy:.3f} | {c.variacion_media_cts:+.2f} | {c.pct_suben:.1f} | {c.pct_bajan:.1f} |"
               for c in resumen.carburantes]
    lineas += ["", f"_Cifras: modelo scikit-learn. Texto: proveedor `{explicacion.proveedor}`, modelo `{explicacion.modelo}`._", ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


def ejecutar_prediccion(carpeta: Path = CARPETA_HISTORICO, modelos: Path = CARPETA_MODELOS,
                        salida: Path = Path("data"), cliente: ClienteIA | None = None) -> int:
    """Predice mañana, guarda predicciones.csv y el informe con la explicación de la IA.

    Códigos de salida: 0 correcto · 2 no hay histórico · 3 no hay modelo entrenado.
    """
    configurar_logs("predecir")

    # 1. Datos recientes y features
    try:
        largo = a_formato_largo(cargar_historico(carpeta, ultimos_dias=DIAS_NECESARIOS))
        datos = construir_features(largo, cargar_mercados(carpeta))
    except DataLoadError as exc:
        log.error("No se pudo cargar el histórico: %s", exc)
        return 2

    # 2. Modelo e inferencia
    try:
        modelo = cargar_modelo(modelos)
    except ModelError as exc:
        log.error("%s", exc)
        return 3
    predicciones = predecir_manana(modelo, datos)
    log.info("Predicciones para el %s: %d (estación × carburante)",
             predicciones["fecha_prediccion"].iloc[0].date(), len(predicciones))

    # 3. Guardar las predicciones
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = salida / "predicciones.csv"
    predicciones[COLUMNAS_SALIDA].to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    log.info("Guardado %s", ruta_csv)

    # 4. Explicación en lenguaje natural (Hugging Face o mock)
    resumen = resumir(predicciones)
    cliente = cliente or crear_cliente(leer_configuracion())
    explicacion = explicar_con_respaldo(cliente, resumen)
    log.info("Explicación generada con '%s' (%s)", explicacion.proveedor, explicacion.modelo)
    ruta_informe = salida / "informe_prediccion.md"
    escribir_informe_prediccion(ruta_informe, resumen, explicacion)
    log.info("Guardado %s", ruta_informe)
    print("\n" + explicacion.texto)
    return 0


# ======================================================================================
# 2. Consulta de las predicciones
# ======================================================================================

# Consulta de las predicciones: precio previsto para mañana por estación, municipio o provincia.
#
# Lee data/predicciones.csv, que genera 'python -m pipeline_dsia predecir'.
#
# Uso:
# python -m pipeline_dsia consultar --provincia sevilla
# python -m pipeline_dsia consultar --provincia madrid --carburante gasoleo_a
# python -m pipeline_dsia consultar --municipio getafe --carburante gasolina_95 --top 10
# python -m pipeline_dsia consultar --estacion 4354
# python -m pipeline_dsia consultar --rotulo repsol --provincia valencia
# python -m pipeline_dsia consultar                       # resumen de toda España
# python -m pipeline_dsia consultar --help
#
# Códigos de salida: 0 correcto · 1 ninguna estación coincide · 2 no hay predicciones.

PREDICCIONES_POR_DEFECTO = Path("data/predicciones.csv")
COLUMNAS_ESTACION = ["id", "rotulo", "municipio", "provincia", "carburante",
                     "precio_hoy", "variacion_prevista", "precio_previsto"]


def normalizar(texto: str) -> str:
    """Mayúsculas y sin tildes, para que 'córdoba', 'Cordoba' y 'CÓRDOBA' sean lo mismo."""
    sin_tildes = unicodedata.normalize("NFD", str(texto))
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.upper().strip()


def filtrar(predicciones: pd.DataFrame, provincia: str | None = None, municipio: str | None = None,
            rotulo: str | None = None, estacion: str | None = None, carburante: str | None = None) -> pd.DataFrame:
    """Devuelve las filas que cumplen todos los filtros indicados.

    Provincia, municipio y rótulo se buscan como texto contenido ('coruña' encuentra
    'CORUÑA (A)'); la estación y el carburante deben coincidir exactamente.
    """
    filas = predicciones
    for columna, valor in (("provincia", provincia), ("municipio", municipio), ("rotulo", rotulo)):
        if valor:
            contiene = filas[columna].fillna("").map(normalizar).str.contains(normalizar(valor), regex=False)
            filas = filas[contiene]
    if estacion:
        filas = filas[filas["id"] == str(estacion).strip()]
    if carburante:
        filas = filas[filas["carburante"] == carburante]
    return filas


def resumen_por_carburante(filas: pd.DataFrame) -> pd.DataFrame:
    """Precio medio de hoy y previsto para mañana de cada carburante en las estaciones filtradas."""
    resumen = filas.groupby("carburante").agg(
        estaciones=("id", "nunique"),
        precio_medio_hoy=("precio_hoy", "mean"),
        precio_medio_previsto=("precio_previsto", "mean"),
    )
    resumen["variacion_cts"] = (resumen["precio_medio_previsto"] - resumen["precio_medio_hoy"]) * 100
    return resumen.round({"precio_medio_hoy": 3, "precio_medio_previsto": 3, "variacion_cts": 2}).reset_index()


def mas_baratas_previstas(filas: pd.DataFrame, n: int) -> pd.DataFrame:
    """Las n estaciones con menor precio previsto (tiene sentido con un solo carburante)."""
    return filas.nsmallest(n, "precio_previsto")[COLUMNAS_ESTACION].reset_index(drop=True)


def ejecutar_consulta(provincia: str | None = None, municipio: str | None = None, rotulo: str | None = None,
                      estacion: str | None = None, carburante: str | None = None, top: int = 5,
                      fichero: Path = PREDICCIONES_POR_DEFECTO) -> int:
    """Muestra por pantalla la previsión de las estaciones que cumplen los filtros.

    Códigos de salida: 0 correcto · 1 ninguna estación coincide · 2 no hay predicciones.
    """
    fichero = Path(fichero)

    if not fichero.exists():
        print(f"No existe {fichero}: ejecuta antes 'python -m pipeline_dsia predecir'")
        return 2
    predicciones = pd.read_csv(fichero, dtype={"id": str})

    filas = filtrar(predicciones, provincia, municipio, rotulo, estacion, carburante)
    if filas.empty:
        print("Ninguna estación coincide con esos filtros")
        return 1

    print(f"Previsión para el {filas['fecha_prediccion'].iloc[0]} · {filas['id'].nunique()} estaciones\n")

    if estacion:
        # Una estación concreta: se muestran sus carburantes tal cual
        print(filas[COLUMNAS_ESTACION].to_string(index=False))
    else:
        print("Precio medio por carburante (€/l):")
        print(resumen_por_carburante(filas).to_string(index=False))
        if carburante and top > 0:
            print(f"\nLas {min(top, len(filas))} estaciones con el precio previsto más bajo:")
            print(mas_baratas_previstas(filas, top).to_string(index=False))

    print("\nLa previsión de una estación concreta es una media esperada: la media de una zona es más fiable.")
    return 0
