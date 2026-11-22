"""Tests de metrics: agregaciones y resumen de calidad."""

import pytest

from ejercicio_ventas.metrics import clientes_habituales, importe_por_region, resumen_calidad, top_productos
from ejercicio_ventas.validator import validar_ventas


def test_importe_por_region(ventas_validas):
    resultado = importe_por_region(ventas_validas)
    # Norte: 20 + 100 = 120 · Sur: 60 + 40 = 100
    assert resultado.index.tolist() == ["Norte", "Sur"]
    assert resultado.tolist() == [120.0, 100.0]


def test_top_productos(ventas_validas):
    resultado = top_productos(ventas_validas, 2)
    # C: 100 · A: 20 + 40 = 60 · B: 60 → empate A/B, pero solo pedimos 2
    assert len(resultado) == 2
    assert resultado.index[0] == "C"
    assert resultado.iloc[0] == 100.0


def test_top_productos_n_mayor_que_productos(ventas_validas):
    assert len(top_productos(ventas_validas, 10)) == 3


@pytest.mark.parametrize("n", [0, -1])
def test_top_productos_n_invalido(ventas_validas, n):
    with pytest.raises(ValueError):
        top_productos(ventas_validas, n)


def test_clientes_habituales(ventas_validas):
    # C002 compra 2 veces (filas 3 y 5); C001 y C003 solo 1 vez entre las válidas
    assert clientes_habituales(ventas_validas).to_dict() == {"C002": 2}


def test_resumen_calidad(ventas_mini):
    df_validos, df_errores = validar_ventas(ventas_mini)
    assert resumen_calidad(ventas_mini, df_validos, df_errores) == {
        "filas_totales": 6,
        "filas_validas": 4,
        "filas_invalidas": 2,
        "importe_total": 220.0,
    }
