"""Datos de prueba compartidos por los tests."""

from pathlib import Path

import pandas as pd
import pytest

CSV_CURSO = Path(__file__).resolve().parents[1] / "data" / "ventas.csv"


@pytest.fixture
def ventas_mini() -> pd.DataFrame:
    """Seis ventas inventadas, tal y como las lee pandas del CSV.

    | fila | región | producto | unidades | precio | cliente | ¿válida?            |
    |------|--------|----------|----------|--------|---------|---------------------|
    | 0    | Norte  | A        | 2        | 10.0   | C001    | sí → importe 20     |
    | 1    | Sur    | B        | (vacío)  | 20.0   | C002    | no: unidades vacías |
    | 2    | Norte  | A        | 5        | -1.0   | C001    | no: precio negativo |
    | 3    | Sur    | B        | 3        | 20.0   | C002    | sí → importe 60     |
    | 4    | Norte  | C        | 1        | 100.0  | C003    | sí → importe 100    |
    | 5    | Sur    | A        | 4        | 10.0   | C002    | sí → importe 40     |
    """
    return pd.DataFrame({
        "fecha": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-02-10", "2026-02-11", "2026-03-01"],
        "region": ["Norte", "Sur", "Norte", "Sur", "Norte", "Sur"],
        "producto": ["A", "B", "A", "B", "C", "A"],
        "unidades": ["2", None, "5", "3", "1", "4"],
        "precio_unitario": [10.0, 20.0, -1.0, 20.0, 100.0, 10.0],
        "cliente_id": ["C001", "C002", "C001", "C002", "C003", "C002"],
    })


@pytest.fixture
def ventas_validas(ventas_mini) -> pd.DataFrame:
    """Las cuatro ventas válidas de ventas_mini, ya validadas."""
    from ejercicio_ventas.funciones import Validar_ventas

    df_validos, _ = Validar_ventas(ventas_mini)
    return df_validos
