"""Pipeline de gasolineras: carga → selección de columnas → normalización → contrato → métricas.

Uso:
    python -m pipeline_dsia
    python -m pipeline_dsia --top 5 --min-estaciones 30
    python -m pipeline_dsia --salida otra_carpeta/mis_resultados.csv
    python -m pipeline_dsia --help
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline_dsia.constants import URL_API
from pipeline_dsia.exceptions import DataLoadError, ValidationError
from pipeline_dsia.loader import cargar_datos
from pipeline_dsia.metrics import (
    comparar_con_provincia,
    diferencia_gasolina_gasoleo,
    mas_baratas,
    media_diferencia_gasolina_gasoleo,
    precio_medio_por_marca,
    precio_medio_por_provincia,
)
from pipeline_dsia.validator import normalizar_numeros, validar_estaciones

# Columnas del DataFrame general que usamos en el proyecto
COLUMNAS = [
    "IDEESS", "Rótulo", "Tipo Venta",
    "Dirección", "C.P.", "Municipio", "Provincia",
    "IDMunicipio", "IDProvincia", "IDCCAA",
    "Latitud", "Longitud (WGS84)",
    "Precio Gasolina 95 E5", "Precio Gasolina 98 E5",
    "Precio Gasoleo A", "Precio Gasoleo Premium",
]

# CSV donde se guardan las gasolineras válidas con sus métricas
SALIDA_POR_DEFECTO = "data/gasolineras_metricas.csv"

# Mostrar todas las columnas al imprimir DataFrames
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


def entero_positivo(valor: str) -> int:
    """Tipo para argparse: acepta solo enteros mayores que 0."""
    try:
        numero = int(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un número entero")
    if numero <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")
    return numero


def crear_parser() -> argparse.ArgumentParser:
    """Define las opciones de la línea de comandos."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia",
        description="Descarga los precios de carburantes de las gasolineras de España, "
        "los valida y calcula métricas.",
    )
    parser.add_argument(
        "--top", type=entero_positivo, default=10,
        help="número de gasolineras en el ranking de más baratas (por defecto 10)",
    )
    parser.add_argument(
        "--min-estaciones", type=entero_positivo, default=20,
        help="mínimo de gasolineras para que una marca aparezca en el ranking de marcas (por defecto 20)",
    )
    parser.add_argument(
        "--salida", metavar="RUTA_CSV", default=SALIDA_POR_DEFECTO,
        help=f"CSV donde se guardan las gasolineras válidas con sus métricas (por defecto {SALIDA_POR_DEFECTO})",
    )
    return parser


def main(argv=None):
    args = crear_parser().parse_args(argv)

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

    print(f"\n=== Las {args.top} gasolineras más baratas de España ===")
    print(mas_baratas(df_validas, args.top))

    print(f"\n=== Precio medio por marca (marcas con {args.min_estaciones}+ estaciones) ===")
    print(precio_medio_por_marca(df_validas, args.min_estaciones))

    diferencia = media_diferencia_gasolina_gasoleo(df_validas)
    print(f"\nLa gasolina 95 cuesta de media {diferencia} €/l más que el gasóleo A")

    # 7. Guardar las gasolineras válidas con sus métricas
    ruta = Path(args.salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df_metricas.to_csv(ruta, index=False, encoding="utf-8-sig")
    print(f"\nResultados guardados en {ruta} ({len(df_metricas)} gasolineras)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
