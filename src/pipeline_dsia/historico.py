"""Almacén histórico de precios: un fichero comprimido por día.

historico/
├── precios/
│   ├── 2026-11-11.csv.gz   # estaciones válidas de ese día
│   └── 2026-11-12.csv.gz
└── mercados.csv            # Brent y EUR/USD, todos los días

Un fichero por día hace que la ingesta sea idempotente (repetir un día lo
sobrescribe, no lo duplica) y que el backfill pueda saltarse los días que ya existen.

Ingesta diaria (ejecutar_ingesta): precios de las gasolineras + Brent + EUR/USD → historico/.
"""

import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pipeline_dsia.config import COLUMNAS, URL_API, URL_API_HIST, DataLoadError, ValidationError, configurar_logs
from pipeline_dsia.loader import cargar_datos, descargar_mercados
from pipeline_dsia.validator import CAMPOS_PRECIO, normalizar_numeros, validar_estaciones

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


# ======================================================================================
# Ingesta diaria y backfill
# ======================================================================================

PAUSA_BACKFILL = 2.0   # segundos entre días, para no saturar el servicio del Ministerio
MAX_FALLOS_SEGUIDOS = 3 # días seguidos fallidos a partir de los cuales el backfill se detiene


def url_dia(dia: date) -> str:
    """El endpoint histórico espera la fecha como dd-mm-aaaa."""
    return f"{URL_API_HIST}{dia:%d-%m-%Y}"


def ingerir_dia(url: str, dia: date, carpeta: Path) -> None:
    df_validas, num_invalidas = preparar_estaciones(cargar_datos(url))
    log.info("%s · válidas: %d · inválidas: %d", dia, len(df_validas), num_invalidas)
    guardar_dia(df_validas, dia, carpeta)


def backfill(desde: date, hasta: date, carpeta: Path, pausa: float = PAUSA_BACKFILL) -> tuple[int, int]:
    """Descarga los días de [desde, hasta] que no estén ya guardados.

    Un día que falla no detiene el resto: se registra y se sigue. Pero si fallan
    varios días seguidos, el servicio no responde y no tiene sentido insistir:
    se detiene (al repetir el comando se retoma donde se quedó).
    Devuelve (días guardados, días fallidos).
    """
    ya = dias_guardados(carpeta)
    pendientes = [desde + timedelta(d) for d in range((hasta - desde).days + 1)]
    pendientes = [d for d in pendientes if d not in ya]
    log.info("Backfill %s → %s: %d días pendientes", desde, hasta, len(pendientes))

    ok = fallidos = seguidos = 0
    for dia in pendientes:
        try:
            ingerir_dia(url_dia(dia), dia, carpeta)
            ok += 1
            seguidos = 0
        except (DataLoadError, ValidationError) as exc:
            log.error("%s · fallido: %s", dia, exc)
            fallidos += 1
            seguidos += 1
            if seguidos >= MAX_FALLOS_SEGUIDOS:
                log.error("%d días seguidos fallidos: el servicio no responde. Se detiene el backfill "
                          "(quedan %d días sin intentar)", seguidos, len(pendientes) - ok - fallidos)
                break
        time.sleep(pausa)
    return ok, fallidos


def ejecutar_ingesta(desde: date | None = None, carpeta: Path = CARPETA_HISTORICO,
                     sin_mercados: bool = False) -> int:
    """Precios del día (o backfill desde `desde` hasta ayer) y datos de mercado → histórico.

    Códigos de salida: 0 correcto · 1 ninguna estación válida · 2 error al descargar.
    """
    configurar_logs("ingesta")
    hoy = date.today()

    # 1. Precios de las gasolineras
    if desde:
        if desde >= hoy:
            log.error("--desde debe ser anterior a hoy")
            return 2
        ok, fallidos = backfill(desde, hoy - timedelta(days=1), carpeta)
        log.info("Backfill terminado: %d días guardados, %d fallidos", ok, fallidos)
        if fallidos and not ok:
            return 2
    else:
        try:
            ingerir_dia(URL_API, hoy, carpeta)
        except DataLoadError as exc:
            log.error("Error al cargar los precios: %s", exc)
            return 2
        except ValidationError as exc:
            log.error("Validación fallida: %s", exc)
            return 1

    # 2. Mercados: FRED y BCE devuelven toda la serie, así que se reescribe entera
    if not sin_mercados:
        try:
            guardar_mercados(descargar_mercados(), carpeta)
        except DataLoadError as exc:
            log.error("Error al descargar los mercados: %s", exc)
            return 2

    return 0
