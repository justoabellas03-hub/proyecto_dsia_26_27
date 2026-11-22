"""Tests de las funciones del pipeline de ventas."""

import json

import pandas as pd
import pytest

from ejercicio_ventas.funciones import (
    Validar_ventas,
    cargar_ventas,
    clientes_habituales,
    exportar,
    importe_por_region,
    resumen_calidad,
    top_productos,
)

from conftest import CSV_CURSO


# --- Carga -------------------------------------------------------------------

def test_cargar_ventas_fichero_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_ventas(tmp_path / "no_existe.csv")


def test_cargar_ventas_lee_el_csv(tmp_path, ventas_mini):
    ruta = tmp_path / "ventas.csv"
    ventas_mini.to_csv(ruta, index=False)
    assert cargar_ventas(ruta).shape == (6, 6)


# --- Validación ----------------------------------------------------------------

def test_validar_cuenta_validas_e_invalidas(ventas_mini):
    df_validos, df_errores = Validar_ventas(ventas_mini)
    assert len(df_validos) == 4
    assert len(df_errores) == 2
    assert df_errores.index.tolist() == [1, 2]


def test_validar_tipos_e_importe(ventas_validas):
    assert ventas_validas["unidades"].dtype == "int64"
    assert ventas_validas["importe"].tolist() == [20.0, 60.0, 100.0, 40.0]


def test_validar_no_modifica_la_entrada(ventas_mini):
    antes = ventas_mini.copy()
    Validar_ventas(ventas_mini)
    pd.testing.assert_frame_equal(ventas_mini, antes)


@pytest.mark.parametrize(
    ("unidades", "precio", "es_valida"),
    [
        ("3", 10.0, True),
        ("0", 10.0, False),
        ("-2", 10.0, False),
        ("na", 10.0, False),
        ("3", 0.0, False),
        ("3", -1.0, False),
        ("3", 1.0, True),
    ],
)
def test_validar_reglas(unidades, precio, es_valida):
    df = pd.DataFrame({
        "fecha": ["2026-01-01"], "region": ["Norte"], "producto": ["A"],
        "unidades": [unidades], "precio_unitario": [precio], "cliente_id": ["C001"],
    })
    df_validos, _ = Validar_ventas(df)
    assert (len(df_validos) == 1) is es_valida


# --- Agregaciones ----------------------------------------------------------------

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


def test_clientes_habituales(ventas_validas):
    resultado = clientes_habituales(ventas_validas)
    # C002 compra 2 veces (filas 3 y 5); C001 y C003 solo 1 vez entre las válidas
    assert resultado.to_dict() == {"C002": 2}


# --- Calidad y exportación ---------------------------------------------------------

def test_resumen_calidad(ventas_mini):
    df_validos, df_errores = Validar_ventas(ventas_mini)
    assert resumen_calidad(ventas_mini, df_validos, df_errores) == {
        "filas_totales": 6,
        "filas_validas": 4,
        "filas_invalidas": 2,
        "importe_total": 220.0,
    }


def test_exportar_crea_los_ficheros(tmp_path, ventas_validas):
    carpeta = tmp_path / "salida"
    calidad = {"filas_totales": 6, "filas_validas": 4, "filas_invalidas": 2, "importe_total": 220.0}

    exportar(ventas_validas, calidad, carpeta)

    assert len(pd.read_csv(carpeta / "ventas_limpias.csv")) == 4
    assert json.loads((carpeta / "calidad_datos.json").read_text(encoding="utf-8")) == calidad


# --- Con el CSV real del curso -------------------------------------------------------

def test_csv_del_curso_140_validas_10_invalidas():
    df = cargar_ventas(CSV_CURSO)
    df_validos, df_errores = Validar_ventas(df)
    assert (len(df_validos), len(df_errores)) == (140, 10)
    assert resumen_calidad(df, df_validos, df_errores)["importe_total"] == pytest.approx(96598.17)
