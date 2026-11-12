"""Consulta de las predicciones: precio previsto para mañana por estación, municipio o provincia.

Lee data/predicciones.csv, que genera 'python -m pipeline_dsia.predecir'.

Uso:
    python -m pipeline_dsia.consultar --provincia sevilla
    python -m pipeline_dsia.consultar --provincia madrid --carburante gasoleo_a
    python -m pipeline_dsia.consultar --municipio getafe --carburante gasolina_95 --top 10
    python -m pipeline_dsia.consultar --estacion 4354
    python -m pipeline_dsia.consultar --rotulo repsol --provincia valencia
    python -m pipeline_dsia.consultar                       # resumen de toda España
    python -m pipeline_dsia.consultar --help

Códigos de salida: 0 correcto · 1 ninguna estación coincide · 2 no hay predicciones.
"""

import argparse
import sys
import unicodedata
from pathlib import Path

import pandas as pd

from pipeline_dsia.contracts import CAMPOS_PRECIO

PREDICCIONES_POR_DEFECTO = Path("data/predicciones.csv")
COLUMNAS_ESTACION = ["id", "rotulo", "municipio", "provincia", "carburante",
                     "precio_hoy", "variacion_prevista", "precio_previsto"]


def normalizar(texto: str) -> str:
    """Mayúsculas y sin tildes, para que 'córdoba', 'Cordoba' y 'CÓRDOBA' sean lo mismo."""
    sin_tildes = unicodedata.normalize("NFD", str(texto))
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.upper().strip()


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia.consultar",
        description="Consulta el precio previsto para mañana. Los filtros se pueden combinar.",
    )
    parser.add_argument("--provincia", help="nombre de la provincia o parte de él (sin importar tildes ni mayúsculas)")
    parser.add_argument("--municipio", help="nombre del municipio o parte de él")
    parser.add_argument("--rotulo", help="marca de la estación o parte de ella (p. ej. repsol)")
    parser.add_argument("--estacion", metavar="ID", help="identificador de la estación (columna id)")
    parser.add_argument("--carburante", choices=CAMPOS_PRECIO, help="un solo carburante (por defecto, todos)")
    parser.add_argument("--top", type=int, default=5,
                        help="número de estaciones más baratas que se listan (por defecto 5; 0 para no listar)")
    parser.add_argument("--predicciones", type=Path, default=PREDICCIONES_POR_DEFECTO,
                        help=f"fichero de predicciones (por defecto {PREDICCIONES_POR_DEFECTO})")
    return parser


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


def main(argv=None) -> int:
    args = crear_parser().parse_args(argv)

    if not args.predicciones.exists():
        print(f"No existe {args.predicciones}: ejecuta antes 'python -m pipeline_dsia.predecir'")
        return 2
    predicciones = pd.read_csv(args.predicciones, dtype={"id": str})

    filas = filtrar(predicciones, args.provincia, args.municipio, args.rotulo, args.estacion, args.carburante)
    if filas.empty:
        print("Ninguna estación coincide con esos filtros")
        return 1

    print(f"Previsión para el {filas['fecha_prediccion'].iloc[0]} · {filas['id'].nunique()} estaciones\n")

    if args.estacion:
        # Una estación concreta: se muestran sus carburantes tal cual
        print(filas[COLUMNAS_ESTACION].to_string(index=False))
    else:
        print("Precio medio por carburante (€/l):")
        print(resumen_por_carburante(filas).to_string(index=False))
        if args.carburante and args.top > 0:
            print(f"\nLas {min(args.top, len(filas))} estaciones con el precio previsto más bajo:")
            print(mas_baratas_previstas(filas, args.top).to_string(index=False))

    print("\nLa previsión de una estación concreta es una media esperada: la media de una zona es más fiable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
