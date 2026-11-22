"""Entrada/salida del pipeline: leer el CSV de ventas y guardar los resultados."""

import json
from pathlib import Path

import pandas as pd

NOMBRE_CSV_LIMPIO = "ventas_limpias.csv"
NOMBRE_JSON_CALIDAD = "calidad_datos.json"


def cargar_ventas(ruta: Path | str) -> pd.DataFrame:
    """Lee el CSV de ventas tal cual (sin limpiar).

    Raises:
        FileNotFoundError: Si el fichero no existe.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el fichero de ventas: {ruta}")
    return pd.read_csv(ruta)


def guardar_resultados(df_validos: pd.DataFrame, calidad: dict, carpeta: Path | str) -> tuple[Path, Path]:
    """Guarda las ventas válidas (CSV) y el resumen de calidad (JSON) en `carpeta`.

    Crea la carpeta si no existe. Devuelve las rutas de los dos ficheros escritos.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)

    ruta_csv = carpeta / NOMBRE_CSV_LIMPIO
    ruta_json = carpeta / NOMBRE_JSON_CALIDAD

    df_validos.to_csv(ruta_csv, index=False)
    ruta_json.write_text(json.dumps(calidad, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta_csv, ruta_json
