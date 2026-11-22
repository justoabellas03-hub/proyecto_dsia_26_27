"""Métricas sobre las ventas válidas y resumen de calidad de los datos."""

import pandas as pd


def importe_por_region(df_validos: pd.DataFrame) -> pd.Series:
    """Importe total de cada región, de mayor a menor."""
    return df_validos.groupby("region")["importe"].sum().sort_values(ascending=False)


def top_productos(df_validos: pd.DataFrame, n: int = 3) -> pd.Series:
    """Los `n` productos con más importe, de mayor a menor.

    Raises:
        ValueError: Si `n` es menor que 1.
    """
    if n < 1:
        raise ValueError(f"n debe ser al menos 1 (recibido: {n})")
    return df_validos.groupby("producto")["importe"].sum().sort_values(ascending=False).head(n)


def clientes_habituales(df_validos: pd.DataFrame) -> pd.Series:
    """Clientes con más de una compra y su número de compras."""
    compras_por_cliente = df_validos["cliente_id"].value_counts()
    return compras_por_cliente[compras_por_cliente > 1]


def resumen_calidad(df: pd.DataFrame, df_validos: pd.DataFrame, df_errores: pd.DataFrame) -> dict:
    """Resumen de la calidad de los datos: filas totales, válidas, inválidas e importe total."""
    return {
        "filas_totales": len(df),
        "filas_validas": len(df_validos),
        "filas_invalidas": len(df_errores),
        "importe_total": round(float(df_validos["importe"].sum()), 2),
    }
