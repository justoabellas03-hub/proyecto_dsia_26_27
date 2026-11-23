"""Tests del almacén histórico y de la ingesta (carpetas temporales, descargas simuladas)."""

from datetime import date

import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
import pipeline_dsia.historico as historico
from pipeline_dsia.config import DataLoadError
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


# ======================================================================================
# Ingesta diaria y backfill
# ======================================================================================

@pytest.fixture(autouse=True)
def en_carpeta_temporal(monkeypatch, tmp_path):
    """Los logs se escriben en tmp_path/logs, no en el proyecto."""
    monkeypatch.chdir(tmp_path)


def mercados_falsos():
    return pd.DataFrame({"fecha": pd.to_datetime(["2026-11-12"]),
                         "brent_usd": [80.0], "eurusd": [1.1], "brent_eur": [72.727]})


def test_url_dia_formato_del_ministerio():
    assert historico.url_dia(date(2026, 3, 7)).endswith("EstacionesTerrestresHist/07-03-2026")


def test_ingesta_de_hoy(monkeypatch, tmp_path, respuesta_api):
    monkeypatch.setattr(historico, "cargar_datos", lambda url: respuesta_api)
    monkeypatch.setattr(historico, "descargar_mercados", mercados_falsos)

    assert cli.main(["ingesta", "--carpeta", str(tmp_path / "h")]) == 0
    assert dias_guardados(tmp_path / "h") == {date.today()}
    assert len(cargar_mercados(tmp_path / "h")) == 1
    assert (tmp_path / "logs" / "ingesta.log").exists()


def test_backfill_salta_los_dias_ya_guardados(monkeypatch, tmp_path, respuesta_api):
    urls = []
    monkeypatch.setattr(historico, "cargar_datos", lambda url: urls.append(url) or respuesta_api)
    monkeypatch.setattr(historico, "PAUSA_BACKFILL", 0)
    carpeta = tmp_path / "h"

    ok, fallidos = historico.backfill(date(2026, 11, 1), date(2026, 11, 3), carpeta, pausa=0)
    assert (ok, fallidos) == (3, 0)

    ok, _ = historico.backfill(date(2026, 11, 1), date(2026, 11, 4), carpeta, pausa=0)
    assert ok == 1                                          # solo faltaba el día 4
    assert len(urls) == 4


def test_backfill_sigue_aunque_falle_un_dia(monkeypatch, tmp_path, respuesta_api):
    def carga(url):
        if url.endswith("02-11-2026"):
            raise DataLoadError("caída del servicio")
        return respuesta_api

    monkeypatch.setattr(historico, "cargar_datos", carga)
    ok, fallidos = historico.backfill(date(2026, 11, 1), date(2026, 11, 3), tmp_path, pausa=0)
    assert (ok, fallidos) == (2, 1)
    assert date(2026, 11, 2) not in dias_guardados(tmp_path)


def test_desde_no_puede_ser_hoy():
    assert cli.main(["ingesta", "--desde", date.today().isoformat(), "--sin-mercados"]) == 2


def test_error_de_carga_devuelve_2(monkeypatch):
    def falla(url):
        raise DataLoadError("sin conexión")

    monkeypatch.setattr(historico, "cargar_datos", falla)
    assert cli.main(["ingesta", "--sin-mercados"]) == 2


def test_error_en_mercados_devuelve_2(monkeypatch, tmp_path, respuesta_api):
    def falla():
        raise DataLoadError("FRED caído")

    monkeypatch.setattr(historico, "cargar_datos", lambda url: respuesta_api)
    monkeypatch.setattr(historico, "descargar_mercados", falla)
    assert cli.main(["ingesta", "--carpeta", str(tmp_path / "h")]) == 2


def test_backfill_se_detiene_si_el_servicio_no_responde(monkeypatch, tmp_path):
    urls = []

    def falla(url):
        urls.append(url)
        raise DataLoadError("conexión cortada")

    monkeypatch.setattr(historico, "cargar_datos", falla)
    ok, fallidos = historico.backfill(date(2026, 8, 1), date(2026, 11, 11), tmp_path, pausa=0)
    assert (ok, fallidos) == (0, 3)                         # no insiste con los 103 días
    assert len(urls) == 3
