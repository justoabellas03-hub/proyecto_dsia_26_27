import json
from pathlib import Path

import pandas as pd


def cargar_ventas(ruta: Path) -> pd.DataFrame:
    """Lee el CSV de ventas.

    Raises:
        FileNotFoundError: Si el fichero no existe.
    """
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el fichero de ventas: {ruta}")
    return pd.read_csv(ruta)


def Validar_ventas(df_raw) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa las ventas en válidas y erróneas.

    Una venta es válida si unidades y precio_unitario son números mayores que 0.
    A las válidas se les añade la columna importe = unidades * precio_unitario.
    """
    unidades = pd.to_numeric(df_raw["unidades"], errors="coerce")
    precio = pd.to_numeric(df_raw["precio_unitario"], errors="coerce")

    error_unidades = (unidades <= 0) | (unidades.isna())
    error_precio = precio.isna() | (precio <= 0)

    df_errores = df_raw[error_precio | error_unidades].copy()

    validos = ~(error_unidades | error_precio)
    df_validos = df_raw[validos].copy()

    df_validos["unidades"] = unidades[validos].astype(int)
    df_validos["precio_unitario"] = precio[validos]

    df_validos["importe"] = df_validos["unidades"] * df_validos["precio_unitario"]

    return (df_validos, df_errores)


def importe_por_region(df_validos: pd.DataFrame) -> pd.Series:
    """Importe total de cada región, de mayor a menor."""
    return df_validos.groupby("region")["importe"].sum().sort_values(ascending=False)


def top_productos(df_validos: pd.DataFrame, n: int = 3) -> pd.Series:
    """Los n productos con más importe."""
    return df_validos.groupby("producto")["importe"].sum().sort_values(ascending=False).head(n)


def clientes_habituales(df_validos: pd.DataFrame) -> pd.Series:
    """Clientes con más de una compra y su número de compras."""
    compras_por_cliente = df_validos["cliente_id"].value_counts()
    return compras_por_cliente[compras_por_cliente > 1]


def resumen_calidad(df: pd.DataFrame, df_validos: pd.DataFrame, df_errores: pd.DataFrame) -> dict:
    """Resumen de la calidad de los datos."""
    return {
        "filas_totales": len(df),
        "filas_validas": len(df_validos),
        "filas_invalidas": len(df_errores),
        "importe_total": round(float(df_validos["importe"].sum()), 2),
    }


def exportar(df_validos: pd.DataFrame, calidad: dict, carpeta: Path) -> None:
    """Guarda las ventas válidas (CSV) y el resumen de calidad (JSON) en carpeta."""
    carpeta.mkdir(parents=True, exist_ok=True)
    df_validos.to_csv(carpeta / "ventas_limpias.csv", index=False)
    (carpeta / "calidad_datos.json").write_text(
        json.dumps(calidad, indent=2, ensure_ascii=False), encoding="utf-8"
    )
