"""Configuración por variables de entorno (fichero .env en local, secretos en GitHub Actions).

Variables:
    AI_PROVIDER  mock (por defecto) o hf
    HF_TOKEN     token de Hugging Face (solo si AI_PROVIDER=hf). Nunca se sube a Git.
    HF_MODEL     modelo del Hub para chat (owner/name)
"""

import os
from dataclasses import dataclass
from pathlib import Path

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
