"""Configuración común de los logs: por pantalla y en logs/<nombre>.log."""

import logging
import sys
from pathlib import Path


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
