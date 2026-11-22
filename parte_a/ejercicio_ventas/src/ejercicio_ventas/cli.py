"""Interfaz de línea de comandos: carga → validación → métricas → exportación.

Uso (desde la carpeta ejercicio_ventas):
    uv run python -m ejercicio_ventas
    uv run python -m ejercicio_ventas --entrada data/ventas.csv --salida data --top 5
"""

import argparse
import sys
from pathlib import Path

from ejercicio_ventas.loader import cargar_ventas, guardar_resultados
from ejercicio_ventas.metrics import clientes_habituales, importe_por_region, resumen_calidad, top_productos
from ejercicio_ventas.validator import validar_ventas

ENTRADA_POR_DEFECTO = Path("data") / "ventas.csv"
SALIDA_POR_DEFECTO = Path("data")


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ejercicio_ventas",
        description="Valida un CSV de ventas, calcula métricas y guarda las ventas limpias.",
    )
    parser.add_argument("--entrada", type=Path, default=ENTRADA_POR_DEFECTO,
                        help=f"CSV de ventas de entrada (por defecto: {ENTRADA_POR_DEFECTO})")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO,
                        help=f"carpeta donde guardar los resultados (por defecto: {SALIDA_POR_DEFECTO})")
    parser.add_argument("--top", type=int, default=3,
                        help="número de productos del ranking (por defecto: 3)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el pipeline completo. Devuelve 0 si va bien y 1 si hay un error de datos."""
    args = crear_parser().parse_args(argv)

    try:
        # 1. Carga
        df = cargar_ventas(args.entrada)

        # 2. Validación
        df_validos, df_errores = validar_ventas(df)
        print(f"Ventas válidas: {len(df_validos)} · inválidas: {len(df_errores)}")

        # 3. Métricas
        print("\nImporte por región:")
        print(importe_por_region(df_validos))

        print(f"\nTop {args.top} productos por importe:")
        print(top_productos(df_validos, args.top))

        habituales = clientes_habituales(df_validos)
        print(f"\nClientes con más de una compra: {len(habituales)} de {df_validos['cliente_id'].nunique()}")
        print(habituales)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    # 4. Exportación
    calidad = resumen_calidad(df, df_validos, df_errores)
    ruta_csv, ruta_json = guardar_resultados(df_validos, calidad, args.salida)
    print(f"\nCalidad de datos: {calidad}")
    print(f"Guardado en {ruta_csv} y {ruta_json}")
    return 0
