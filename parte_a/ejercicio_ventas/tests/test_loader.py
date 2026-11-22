"""Tests de loader: lectura del CSV y escritura de resultados."""

import json

import pandas as pd
import pytest

from ejercicio_ventas.loader import NOMBRE_CSV_LIMPIO, NOMBRE_JSON_CALIDAD, cargar_ventas, guardar_resultados


def test_cargar_ventas_fichero_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError, match="no_existe.csv"):
        cargar_ventas(tmp_path / "no_existe.csv")


def test_cargar_ventas_lee_el_csv(csv_mini):
    df = cargar_ventas(csv_mini)
    assert df.shape == (6, 6)
    assert list(df.columns) == ["fecha", "region", "producto", "unidades", "precio_unitario", "cliente_id"]


def test_cargar_ventas_acepta_ruta_como_texto(csv_mini):
    assert len(cargar_ventas(str(csv_mini))) == 6


def test_guardar_resultados_crea_los_ficheros(tmp_path, ventas_validas):
    calidad = {"filas_totales": 6, "filas_validas": 4, "filas_invalidas": 2, "importe_total": 220.0}

    ruta_csv, ruta_json = guardar_resultados(ventas_validas, calidad, tmp_path)

    assert ruta_csv == tmp_path / NOMBRE_CSV_LIMPIO
    assert ruta_json == tmp_path / NOMBRE_JSON_CALIDAD
    assert len(pd.read_csv(ruta_csv)) == 4
    assert json.loads(ruta_json.read_text(encoding="utf-8")) == calidad


def test_guardar_resultados_crea_la_carpeta_si_no_existe(tmp_path, ventas_validas):
    carpeta = tmp_path / "a" / "b"
    guardar_resultados(ventas_validas, {}, carpeta)
    assert (carpeta / NOMBRE_CSV_LIMPIO).exists()
