"""Pipeline de ventas: carga → validación → agregaciones → exportación.

Uso (desde la carpeta ejercicio_ventas):
    uv run python -m ejercicio_ventas
"""

from pathlib import Path

from ejercicio_ventas.funciones import (
    Validar_ventas,
    cargar_ventas,
    clientes_habituales,
    exportar,
    importe_por_region,
    resumen_calidad,
    top_productos,
)

CARPETA_DATOS = Path("data")
VENTAS_PATH = CARPETA_DATOS / "ventas.csv"


def main():
    # 1. Carga
    df = cargar_ventas(VENTAS_PATH)

    # 2. Validación
    df_validos, df_errores = Validar_ventas(df)
    print(f"Ventas válidas: {len(df_validos)} · inválidas: {len(df_errores)}")

    # 3. Agregaciones
    print("\nImporte por región:")
    print(importe_por_region(df_validos))

    print("\nTop 3 productos por importe:")
    print(top_productos(df_validos, 3))

    habituales = clientes_habituales(df_validos)
    print(f"\nClientes con más de una compra: {len(habituales)} de {df_validos['cliente_id'].nunique()}")
    print(habituales)

    # 4. Exportación
    calidad = resumen_calidad(df, df_validos, df_errores)
    exportar(df_validos, calidad, CARPETA_DATOS)
    print(f"\nCalidad de datos: {calidad}")
    print(f"Guardado en {CARPETA_DATOS / 'ventas_limpias.csv'} y {CARPETA_DATOS / 'calidad_datos.json'}")


if __name__ == "__main__":
    main()
