"""Configuración común del paquete: constantes, excepciones, variables de entorno y logs.

Secciones:
    1. Constantes: URL de las fuentes, columnas de la API y rangos válidos.
    2. Excepciones del dominio.
    3. Variables de entorno (fichero .env en local, secretos en GitHub Actions):
         AI_PROVIDER  mock (por defecto) o hf
         HF_TOKEN     token de Hugging Face (solo si AI_PROVIDER=hf). Nunca se sube a Git.
         HF_MODEL     modelo del Hub para chat (owner/name)
    4. Logs: por pantalla y en logs/<nombre>.log.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path


# ======================================================================================
# 1. Constantes
# ======================================================================================

URL_API = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)

# Precios de un día pasado: se añade la fecha en formato dd-mm-aaaa al final
URL_API_HIST = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestresHist/"
)

# --- Fuentes externas (mercados) ---
# Brent (USD/barril), serie DCOILBRENTEU de FRED: CSV con todo el histórico, sin clave
URL_BRENT = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
# Tipo de cambio de referencia del BCE: dólares por 1 euro, diario, sin clave
URL_EURUSD = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata"


# --- Columnas que usamos (nombres tal y como vienen en la API) ---
COLUMNAS = [
    "IDEESS", "Rótulo", "Tipo Venta",
    "Dirección", "C.P.", "Municipio", "Provincia",
    "IDMunicipio", "IDProvincia", "IDCCAA",
    "Latitud", "Longitud (WGS84)",
    "Precio Gasolina 95 E5", "Precio Gasolina 98 E5",
    "Precio Gasoleo A", "Precio Gasoleo Premium",
]
COORDENADAS = ("Latitud", "Longitud (WGS84)")

CAMPOS_PRECIOS = (
    "Precio Gasolina 95 E5",
    "Precio Gasolina 98 E5",
    "Precio Gasoleo A",
    "Precio Gasoleo Premium",
)


# --- Rangos plausibles ---
PRECIO_MIN, PRECIO_MAX = 0.5, 3.5          # Intervalo de precio €/litro de los que considero que es imposible que los combustibles no pertenezca
LATITUD_MIN, LATITUD_MAX = 27.0, 44.5      # Coordenadas que incluye Canarias
LONGITUD_MIN, LONGITUD_MAX = -18.5, 4.5


# ======================================================================================
# 2. Excepciones
# ======================================================================================

class GasolinerasError(Exception):
    """Error base del dominio."""


class DataLoadError(GasolinerasError):
    """No se han podido obtener los datos (red, fichero, formato...)."""


class ValidationError(GasolinerasError):
    """Los datos no superan la validación (p. ej. ninguna estación válida)."""


class ModelError(GasolinerasError):
    """Problema con el modelo: no existe, no se puede cargar o no hay datos para entrenarlo."""


class IAError(GasolinerasError):
    """Ha fallado la llamada al proveedor de IA (Hugging Face)."""


# ======================================================================================
# 3. Variables de entorno
# ======================================================================================

MODELO_HF_POR_DEFECTO = "meta-llama/Llama-3.1-8B-Instruct"


@dataclass(frozen=True)
class Configuracion:
    ai_provider: str
    hf_token: str | None
    hf_model: str


def cargar_env(ruta: Path = Path(".env")) -> None:
    """Lee un fichero .env (líneas CLAVE=valor) y lo pasa a variables de entorno.

    Las variables que ya existen en el entorno tienen prioridad (así en GitHub
    Actions mandan los secretos). Si el fichero no existe, no hace nada.
    """
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def leer_configuracion() -> Configuracion:
    cargar_env()
    return Configuracion(
        ai_provider=os.environ.get("AI_PROVIDER", "mock").strip().lower() or "mock",
        hf_token=os.environ.get("HF_TOKEN", "").strip() or None,
        hf_model=os.environ.get("HF_MODEL", "").strip() or MODELO_HF_POR_DEFECTO,
    )


# ======================================================================================
# 4. Logs
# ======================================================================================

def configurar_logs(nombre: str = "pipeline", carpeta_logs: Path = Path("logs"), nivel: int = logging.INFO) -> None:
    """Todos los módulos del paquete escriben en el logger "pipeline_dsia".

    Args:
        nombre: Nombre del fichero de log (ingesta, entrenar, predecir...).
    """
    carpeta_logs.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    log = logging.getLogger("pipeline_dsia")
    log.setLevel(nivel)
    for handler in log.handlers:
        handler.close()
    log.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(carpeta_logs / f"{nombre}.log", encoding="utf-8")):
        handler.setFormatter(formato)
        log.addHandler(handler)
