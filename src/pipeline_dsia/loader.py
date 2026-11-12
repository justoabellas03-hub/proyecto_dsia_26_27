"""Descargas con reintentos y varios métodos de conexión.

El servidor del Ministerio a veces corta la conexión segura (TLS) cuando la abre
Python, aunque desde un navegador funcione. Por eso cada descarga prueba, en orden:

    1. requests normal.
    2. requests con una configuración TLS más compatible (TLS 1.2 y más cifrados).
    3. El programa curl del sistema (usa la librería de seguridad de Windows,
       distinta de la de Python).

El método que funciona se recuerda y se usa primero en las descargas siguientes.
En ningún caso se desactiva la verificación del certificado.
"""

import json
import logging
import shutil
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from pipeline_dsia.exceptions import DataLoadError

log = logging.getLogger(__name__)

CABECERAS = {"User-Agent": "Mozilla/5.0 (pipeline-dsia; proyecto docente)"}
# Errores de red de cualquiera de los métodos (requests, curl)
ERRORES_DESCARGA = (requests.RequestException, OSError, subprocess.SubprocessError)


@dataclass
class Respuesta:
    """Contenido descargado, igual para todos los métodos."""
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8-sig", errors="replace")


# --- Métodos de conexión: (url, timeout, cabeceras) → bytes ----------------------------

def con_requests(url: str, timeout: int, cabeceras: dict) -> bytes:
    respuesta = requests.get(url, timeout=timeout, headers=cabeceras)
    respuesta.raise_for_status()
    return respuesta.content


class AdaptadorTLSCompatible(HTTPAdapter):
    """Conexión limitada a TLS 1.2 y con más cifrados permitidos (servidores antiguos)."""

    def init_poolmanager(self, *args, **kwargs):
        contexto = create_urllib3_context(ciphers="DEFAULT:@SECLEVEL=1")
        contexto.maximum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)


def con_requests_tls_compatible(url: str, timeout: int, cabeceras: dict) -> bytes:
    with requests.Session() as sesion:
        sesion.mount("https://", AdaptadorTLSCompatible())
        respuesta = sesion.get(url, timeout=timeout, headers=cabeceras)
        respuesta.raise_for_status()
        return respuesta.content


def ruta_curl() -> str:
    """En Windows se prefiere el curl del sistema, que no usa la misma librería TLS que Python."""
    if sys.platform == "win32":
        de_windows = Path(r"C:\Windows\System32\curl.exe")
        if de_windows.exists():
            return str(de_windows)
    ruta = shutil.which("curl")
    if ruta is None:
        raise FileNotFoundError("curl no está instalado")
    return ruta


def con_curl(url: str, timeout: int, cabeceras: dict) -> bytes:
    orden = [ruta_curl(), "--silent", "--show-error", "--fail", "--location", "--max-time", str(timeout)]
    for clave, valor in cabeceras.items():
        orden += ["--header", f"{clave}: {valor}"]
    resultado = subprocess.run([*orden, url], capture_output=True, timeout=timeout + 15)
    if resultado.returncode != 0:
        raise OSError(f"curl terminó con código {resultado.returncode}: "
                      f"{resultado.stderr.decode(errors='replace').strip()}")
    return resultado.stdout


METODOS = [con_requests, con_requests_tls_compatible, con_curl]
_preferido = None   # último método que funcionó


def _metodos_en_orden() -> list:
    if _preferido in METODOS:
        return [_preferido] + [m for m in METODOS if m is not _preferido]
    return list(METODOS)


def _resumen(exc: Exception) -> str:
    """Mensaje de error corto para el log (los de requests ocupan varias líneas)."""
    texto = str(exc)
    return f"{type(exc).__name__}: {texto[-160:] if len(texto) > 160 else texto}"


# --- Descarga ---------------------------------------------------------------------------

def descargar(url: str, reintentos: int = 3, espera: float = 5.0, timeout: int = 90, headers: dict | None = None) -> Respuesta:
    """Descarga una URL probando los métodos de conexión, con reintentos.

    Espera `espera`, 2·`espera`, 4·`espera`... segundos entre intentos.

    Raises:
        DataLoadError: Si fallan todos los métodos en todos los intentos.
    """
    global _preferido
    cabeceras = {**CABECERAS, **(headers or {})}
    ultimo_error = None

    for intento in range(1, reintentos + 1):
        for metodo in _metodos_en_orden():
            try:
                contenido = metodo(url, timeout, cabeceras)
            except ERRORES_DESCARGA as exc:
                ultimo_error = exc
                log.warning("Intento %d/%d con %s fallido: %s", intento, reintentos, metodo.__name__, _resumen(exc))
                continue
            if metodo is not _preferido:
                log.info("Conexión correcta con el método %s", metodo.__name__)
                _preferido = metodo
            return Respuesta(contenido)
        if intento < reintentos:
            time.sleep(espera * 2 ** (intento - 1))

    raise DataLoadError(f"No se pudo descargar {url}: {_resumen(ultimo_error)}")


def cargar_datos(url, clave="ListaEESSPrecio", reintentos: int = 3):
    """Descarga los datos de una API que devuelve JSON y los pasa a DataFrame.

    Args:
        url: Dirección de la API.
        clave: Clave del JSON donde está la lista de registros.
        reintentos: Intentos antes de rendirse.
    """
    respuesta = descargar(url, reintentos=reintentos, headers={"Accept": "application/json"})
    try:
        datos = json.loads(respuesta.text)
        # La API no devuelve solo la lista, sino un diccionario con varias cosas dentro
        return pd.DataFrame(datos[clave])
    except (ValueError, KeyError, TypeError) as exc:
        raise DataLoadError(f"Respuesta con formato inesperado en {url}: {exc}") from exc
