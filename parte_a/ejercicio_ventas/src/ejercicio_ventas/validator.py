"""Validación de las ventas: esquema del CSV y reglas de cada fila."""

import pandas as pd

COLUMNAS_OBLIGATORIAS = ("fecha", "region", "producto", "unidades", "precio_unitario", "cliente_id")


def comprobar_columnas(df: pd.DataFrame) -> None:
    """Comprueba que el DataFrame tiene todas las columnas obligatorias.

    Raises:
        ValueError: Si falta alguna columna (se indican cuáles).
    """
    faltan = [col for col in COLUMNAS_OBLIGATORIAS if col not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas obligatorias en las ventas: {', '.join(faltan)}")


def validar_ventas(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa las ventas en válidas y erróneas.

    Una venta es válida si `unidades` y `precio_unitario` son números mayores que 0.
    A las válidas se les convierte `unidades` a entero y se les añade
    `importe = unidades * precio_unitario`. El DataFrame de entrada no se modifica.

    Returns:
        (df_validos, df_errores)

    Raises:
        ValueError: Si faltan columnas obligatorias.
    """
    comprobar_columnas(df_raw)

    unidades = pd.to_numeric(df_raw["unidades"], errors="coerce")
    precio = pd.to_numeric(df_raw["precio_unitario"], errors="coerce")

    error_unidades = unidades.isna() | (unidades <= 0)
    error_precio = precio.isna() | (precio <= 0)
    validos = ~(error_unidades | error_precio)

    df_errores = df_raw[~validos].copy()

    df_validos = df_raw[validos].copy()
    df_validos["unidades"] = unidades[validos].astype(int)
    df_validos["precio_unitario"] = precio[validos]
    df_validos["importe"] = df_validos["unidades"] * df_validos["precio_unitario"]

    return df_validos, df_errores
