"""Tests de validator: esquema y reglas de validación de cada venta."""

import pandas as pd
import pytest

from ejercicio_ventas.validator import COLUMNAS_OBLIGATORIAS, comprobar_columnas, validar_ventas


def una_venta(unidades, precio) -> pd.DataFrame:
    return pd.DataFrame({
        "fecha": ["2026-01-01"], "region": ["Norte"], "producto": ["A"],
        "unidades": [unidades], "precio_unitario": [precio], "cliente_id": ["C001"],
    })


# --- Esquema -------------------------------------------------------------------

def test_comprobar_columnas_ok(ventas_mini):
    comprobar_columnas(ventas_mini)  # no lanza


@pytest.mark.parametrize("columna", COLUMNAS_OBLIGATORIAS)
def test_falta_una_columna(ventas_mini, columna):
    with pytest.raises(ValueError, match=columna):
        validar_ventas(ventas_mini.drop(columns=columna))


def test_columnas_extra_no_molestan(ventas_mini):
    df_validos, _ = validar_ventas(ventas_mini.assign(comentario="x"))
    assert len(df_validos) == 4


# --- Reglas ----------------------------------------------------------------------

def test_validar_cuenta_validas_e_invalidas(ventas_mini):
    df_validos, df_errores = validar_ventas(ventas_mini)
    assert len(df_validos) == 4
    assert len(df_errores) == 2
    assert df_errores.index.tolist() == [1, 2]


def test_validar_tipos_e_importe(ventas_validas):
    assert ventas_validas["unidades"].dtype == "int64"
    assert ventas_validas["importe"].tolist() == [20.0, 60.0, 100.0, 40.0]


def test_validar_no_modifica_la_entrada(ventas_mini):
    antes = ventas_mini.copy()
    validar_ventas(ventas_mini)
    pd.testing.assert_frame_equal(ventas_mini, antes)


def test_validar_dataframe_vacio():
    vacio = pd.DataFrame(columns=list(COLUMNAS_OBLIGATORIAS))
    df_validos, df_errores = validar_ventas(vacio)
    assert df_validos.empty and df_errores.empty


@pytest.mark.parametrize(
    ("unidades", "precio", "es_valida"),
    [
        ("3", 10.0, True),
        ("0", 10.0, False),
        ("-2", 10.0, False),
        ("na", 10.0, False),
        (None, 10.0, False),
        ("3", 0.0, False),
        ("3", -1.0, False),
        ("3", "abc", False),
        ("3", 1.0, True),
    ],
)
def test_validar_reglas(unidades, precio, es_valida):
    df_validos, df_errores = validar_ventas(una_venta(unidades, precio))
    assert (len(df_validos) == 1) is es_valida
    assert len(df_validos) + len(df_errores) == 1
