"""Almacén histórico de precios: un fichero comprimido por día.

historico/
├── precios/
│   ├── 2026-11-11.csv.gz   # estaciones válidas de ese día
│   └── 2026-11-12.csv.gz
└── mercados.csv            # Brent y EUR/USD, todos los días

Un fichero por día hace que la ingesta sea idempotente (repetir un día lo
sobrescribe, no lo duplica) y que el backfill pueda saltarse los días que ya existen.
"""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline_dsia.constants import COLUMNAS
from pipeline_dsia.contracts import CAMPOS_PRECIO
from pipeline_dsia.exceptions import DataLoadError
from pipeline_dsia.validator import normalizar_numeros, validar_estaciones

log = logging.getLogger(__name__)

CARPETA_HISTORICO = Path("historico")

# Lo que se guarda de cada estación (la dirección y el C.P. no aportan al modelo)
COLUMNAS_HISTORICO = [
    "fecha", "id", "rotulo", "tipo_venta", "municipio", "provincia",
    "id_municipio", "id_provincia", "id_ccaa", "latitud", "longitud", *CAMPOS_PRECIO,
]


def preparar_estaciones(df_api: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Respuesta cruda de la API → estaciones válidas (mismos pasos que el pipeline)."""
    faltan = [c for c in COLUMNAS if c not in df_api.columns]
    if faltan:
        raise DataLoadError(f"La respuesta de la API no trae las columnas {faltan}")
    return validar_estaciones(normalizar_numeros(df_api[COLUMNAS].copy()))


def ruta_dia(dia: date, carpeta: Path = CARPETA_HISTORICO) -> Path:
    return Path(carpeta) / "precios" / f"{dia:%Y-%m-%d}.csv.gz"


def guardar_dia(df_validas: pd.DataFrame, dia: date, carpeta: Path = CARPETA_HISTORICO) -> Path:
    """Guarda las estaciones válidas de un día. Si el fichero ya existe, lo sobrescribe."""
    df = df_validas.copy()
    df.insert(0, "fecha", pd.Timestamp(dia))
    ruta = ruta_dia(dia, carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNAS_HISTORICO].to_csv(ruta, index=False, compression="gzip")
    log.info("Guardado %s (%d estaciones)", ruta, len(df))
    return ruta


def dias_guardados(carpeta: Path = CARPETA_HISTORICO) -> set[date]:
    """Días que ya están en el histórico."""
    return {date.fromisoformat(p.name.removesuffix(".csv.gz"))
            for p in (Path(carpeta) / "precios").glob("*.csv.gz")}


def cargar_historico(carpeta: Path = CARPETA_HISTORICO, ultimos_dias: int | None = None) -> pd.DataFrame:
    """Une los días guardados en un único DataFrame (formato ancho).

    Args:
        ultimos_dias: Si se indica, solo carga los N ficheros más recientes
            (para predecir no hace falta todo el histórico, solo los últimos días).
    """
    ficheros = sorted((Path(carpeta) / "precios").glob("*.csv.gz"))
    if not ficheros:
        raise DataLoadError(f"No hay datos históricos en {carpeta}")
    if ultimos_dias:
        ficheros = ficheros[-ultimos_dias:]
    tipos = {"id": str, "id_municipio": str, "id_provincia": str, "id_ccaa": str}
    partes = [pd.read_csv(f, dtype=tipos, parse_dates=["fecha"]) for f in ficheros]
    return pd.concat(partes, ignore_index=True)


def a_formato_largo(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por estación × carburante × día, que es la unidad que se predice.

    Las combinaciones sin precio (la estación no vende ese carburante) se eliminan.
    """
    fijas = [c for c in df.columns if c not in CAMPOS_PRECIO]
    largo = df.melt(id_vars=fijas, value_vars=list(CAMPOS_PRECIO), var_name="carburante", value_name="precio")
    largo = largo.dropna(subset=["precio"])
    return largo.sort_values(["id", "carburante", "fecha"]).reset_index(drop=True)


def guardar_mercados(mercados: pd.DataFrame, carpeta: Path = CARPETA_HISTORICO) -> Path:
    """Guarda la serie completa de mercados (FRED y BCE ya dan todo el histórico)."""
    ruta = Path(carpeta) / "mercados.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    mercados.to_csv(ruta, index=False)
    log.info("Guardado %s (hasta %s)", ruta, mercados["fecha"].max().date())
    return ruta


def cargar_mercados(carpeta: Path = CARPETA_HISTORICO) -> pd.DataFrame:
    ruta = Path(carpeta) / "mercados.csv"
    if not ruta.exists():
        raise DataLoadError(f"No existe {ruta}: ejecuta antes la ingesta")
    return pd.read_csv(ruta, parse_dates=["fecha"])
