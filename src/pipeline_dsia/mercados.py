"""Datos de mercado que influyen en el precio de los carburantes: Brent y EUR/USD.

Cada fuente tiene dos funciones:
  - leer_*: convierte el texto CSV en un DataFrame limpio (sin red, se puede testear).
  - descargar_*: baja el CSV de internet y llama a leer_*.
"""

import io
import logging

import pandas as pd

from pipeline_dsia.constants import URL_BRENT, URL_EURUSD
from pipeline_dsia.exceptions import DataLoadError
from pipeline_dsia.loader import descargar

log = logging.getLogger(__name__)


# --- Brent (FRED) -----------------------------------------------------------------

def leer_brent(texto_csv: str) -> pd.DataFrame:
    """CSV de FRED → DataFrame con columnas fecha, brent_usd.

    FRED solo publica días hábiles y deja vacío el valor de los festivos;
    esas filas se eliminan (se rellenan después en combinar_mercados).
    """
    df = pd.read_csv(io.StringIO(texto_csv), na_values=["", "."])
    columnas = {"observation_date", "DCOILBRENTEU"}
    if not columnas.issubset(df.columns):
        raise DataLoadError(f"El CSV del Brent no tiene las columnas esperadas {columnas}: {list(df.columns)}")

    df = df.rename(columns={"observation_date": "fecha", "DCOILBRENTEU": "brent_usd"})
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["brent_usd"] = pd.to_numeric(df["brent_usd"], errors="coerce")
    return df.dropna(subset=["brent_usd"]).sort_values("fecha").reset_index(drop=True)


def descargar_brent(url: str = URL_BRENT) -> pd.DataFrame:
    return leer_brent(descargar(url).text)


# --- EUR/USD (BCE) ----------------------------------------------------------------

def leer_eurusd(texto_csv: str) -> pd.DataFrame:
    """CSV del BCE → DataFrame con columnas fecha, eurusd (dólares por 1 euro)."""
    df = pd.read_csv(io.StringIO(texto_csv))
    columnas = {"TIME_PERIOD", "OBS_VALUE"}
    if not columnas.issubset(df.columns):
        raise DataLoadError(f"El CSV del BCE no tiene las columnas esperadas {columnas}: {list(df.columns)}")

    df = df[["TIME_PERIOD", "OBS_VALUE"]].rename(columns={"TIME_PERIOD": "fecha", "OBS_VALUE": "eurusd"})
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["eurusd"] = pd.to_numeric(df["eurusd"], errors="coerce")
    return df.dropna(subset=["eurusd"]).sort_values("fecha").reset_index(drop=True)


def descargar_eurusd(url: str = URL_EURUSD, desde: str | None = None) -> pd.DataFrame:
    """Args:
        desde: Primera fecha 'AAAA-MM-DD' (el BCE tiene datos desde 1999).
    """
    if desde:
        url = f"{url}&startPeriod={desde}"
    return leer_eurusd(descargar(url).text)


# --- Combinación ------------------------------------------------------------------

def combinar_mercados(brent: pd.DataFrame, eurusd: pd.DataFrame) -> pd.DataFrame:
    """Une Brent y EUR/USD en una serie con TODOS los días del calendario.

    Las gasolineras cambian precios también en fin de semana, pero los mercados no
    publican: se rellena hacia delante con el último valor conocido (ffill).
    Nunca se rellena hacia atrás, para no usar información del futuro.

    Añade brent_eur: precio del barril en euros (brent_usd / eurusd), que es lo que
    realmente paga un operador español.
    """
    desde = max(brent["fecha"].min(), eurusd["fecha"].min())
    hasta = max(brent["fecha"].max(), eurusd["fecha"].max())
    calendario = pd.DataFrame({"fecha": pd.date_range(desde, hasta, freq="D")})

    df = calendario.merge(brent, on="fecha", how="left").merge(eurusd, on="fecha", how="left")
    df[["brent_usd", "eurusd"]] = df[["brent_usd", "eurusd"]].ffill()
    df["brent_eur"] = (df["brent_usd"] / df["eurusd"]).round(3)
    return df


def descargar_mercados(desde: str = "2000-01-01") -> pd.DataFrame:
    """Descarga Brent y EUR/USD y los combina. Punto de entrada para la ingesta."""
    brent = descargar_brent()
    eurusd = descargar_eurusd(desde=desde)
    log.info("Brent hasta %s · EUR/USD hasta %s", brent["fecha"].max().date(), eurusd["fecha"].max().date())
    mercados = combinar_mercados(brent[brent["fecha"] >= desde], eurusd)
    return mercados
