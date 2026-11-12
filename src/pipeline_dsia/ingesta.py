"""Ingesta diaria: precios de las gasolineras + Brent + EUR/USD → historico/.

Uso:
    python -m pipeline_dsia.ingesta                       # precios de hoy + mercados
    python -m pipeline_dsia.ingesta --desde 2026-06-01    # backfill: rellena los días que falten
    python -m pipeline_dsia.ingesta --sin-mercados        # solo precios
    python -m pipeline_dsia.ingesta --help

Códigos de salida: 0 correcto · 1 ninguna estación válida · 2 error al descargar.
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from pipeline_dsia.constants import URL_API, URL_API_HIST
from pipeline_dsia.exceptions import DataLoadError, ValidationError
from pipeline_dsia.historico import (
    CARPETA_HISTORICO, dias_guardados, guardar_dia, guardar_mercados, preparar_estaciones,
)
from pipeline_dsia.loader import cargar_datos
from pipeline_dsia.mercados import descargar_mercados
from pipeline_dsia.registro import configurar_logs

log = logging.getLogger("pipeline_dsia")

PAUSA_BACKFILL = 2.0   # segundos entre días, para no saturar el servicio del Ministerio
MAX_FALLOS_SEGUIDOS = 3 # días seguidos fallidos a partir de los cuales el backfill se detiene


def fecha_iso(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es una fecha AAAA-MM-DD")


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia.ingesta",
        description="Guarda los precios del día y los datos de mercado en el histórico.",
    )
    parser.add_argument("--desde", type=fecha_iso, metavar="AAAA-MM-DD",
                        help="backfill: descarga del histórico del Ministerio los días que falten desde esta fecha hasta ayer")
    parser.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO,
                        help=f"carpeta del histórico (por defecto {CARPETA_HISTORICO})")
    parser.add_argument("--sin-mercados", action="store_true", help="no descargar Brent ni EUR/USD")
    return parser


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


def main(argv=None) -> int:
    args = crear_parser().parse_args(argv)
    configurar_logs("ingesta")
    hoy = date.today()

    # 1. Precios de las gasolineras
    if args.desde:
        if args.desde >= hoy:
            log.error("--desde debe ser anterior a hoy")
            return 2
        ok, fallidos = backfill(args.desde, hoy - timedelta(days=1), args.carpeta)
        log.info("Backfill terminado: %d días guardados, %d fallidos", ok, fallidos)
        if fallidos and not ok:
            return 2
    else:
        try:
            ingerir_dia(URL_API, hoy, args.carpeta)
        except DataLoadError as exc:
            log.error("Error al cargar los precios: %s", exc)
            return 2
        except ValidationError as exc:
            log.error("Validación fallida: %s", exc)
            return 1

    # 2. Mercados: FRED y BCE devuelven toda la serie, así que se reescribe entera
    if not args.sin_mercados:
        try:
            guardar_mercados(descargar_mercados(), args.carpeta)
        except DataLoadError as exc:
            log.error("Error al descargar los mercados: %s", exc)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
