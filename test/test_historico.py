"""Tests del almacén histórico (en una carpeta temporal)."""

from datetime import date

import pandas as pd
import pytest

from pipeline_dsia.exceptions import DataLoadError
from pipeline_dsia.historico import (
    a_formato_largo, cargar_historico, cargar_mercados, dias_guardados, guardar_dia,
    guardar_mercados, preparar_estaciones,
)


def test_preparar_estaciones(respuesta_api):
    validas, invalidas = preparar_estaciones(respuesta_api)
    assert len(validas) == 2
    assert invalidas == 1                                   # no vende ningún carburante
    assert validas.loc[0, "gasoleo_a"] == pytest.approx(1.459)


def test_preparar_estaciones_faltan_columnas(respuesta_api):
    with pytest.raises(DataLoadError):
        preparar_estaciones(respuesta_api.drop(columns=["Precio Gasoleo A"]))


def test_guardar_y_cargar_varios_dias(respuesta_api, tmp_path):
    validas, _ = preparar_estaciones(respuesta_api)
    guardar_dia(validas, date(2026, 11, 11), tmp_path)
    guardar_dia(validas, date(2026, 11, 12), tmp_path)

    assert dias_guardados(tmp_path) == {date(2026, 11, 11), date(2026, 11, 12)}
    historico = cargar_historico(tmp_path)
    assert len(historico) == 4
    assert historico["id_provincia"].iloc[0] == "28"       # los códigos siguen siendo texto
    assert historico["fecha"].dt.day.tolist() == [11, 11, 12, 12]


def test_guardar_el_mismo_dia_no_duplica(respuesta_api, tmp_path):
    validas, _ = preparar_estaciones(respuesta_api)
    guardar_dia(validas, date(2026, 11, 12), tmp_path)
    guardar_dia(validas, date(2026, 11, 12), tmp_path)
    assert len(cargar_historico(tmp_path)) == 2


def test_cargar_historico_vacio(tmp_path):
    with pytest.raises(DataLoadError):
        cargar_historico(tmp_path)


def test_formato_largo_quita_carburantes_que_no_vende(respuesta_api, tmp_path):
    validas, _ = preparar_estaciones(respuesta_api)
    guardar_dia(validas, date(2026, 11, 12), tmp_path)
    largo = a_formato_largo(cargar_historico(tmp_path))

    assert set(largo["carburante"]) == {"gasolina_95", "gasoleo_a"}
    assert len(largo) == 4                                  # 2 estaciones × 2 carburantes


def test_guardar_y_cargar_mercados(tmp_path):
    mercados = pd.DataFrame({"fecha": pd.to_datetime(["2026-11-11", "2026-11-12"]),
                             "brent_usd": [80.0, 81.0], "eurusd": [1.1, 1.1], "brent_eur": [72.7, 73.6]})
    guardar_mercados(mercados, tmp_path)
    assert cargar_mercados(tmp_path).equals(mercados)


def test_cargar_mercados_sin_fichero(tmp_path):
    with pytest.raises(DataLoadError):
        cargar_mercados(tmp_path)
