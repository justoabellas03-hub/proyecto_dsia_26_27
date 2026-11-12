"""Tests de la ingesta (sin conexión: se simulan las descargas)."""

from datetime import date, timedelta

import pandas as pd
import pytest

import pipeline_dsia.ingesta as ingesta
from pipeline_dsia.exceptions import DataLoadError
from pipeline_dsia.historico import cargar_mercados, dias_guardados


@pytest.fixture(autouse=True)
def en_carpeta_temporal(monkeypatch, tmp_path):
    """Los logs se escriben en tmp_path/logs, no en el proyecto."""
    monkeypatch.chdir(tmp_path)


def mercados_falsos():
    return pd.DataFrame({"fecha": pd.to_datetime(["2026-11-12"]),
                         "brent_usd": [80.0], "eurusd": [1.1], "brent_eur": [72.727]})


def test_url_dia_formato_del_ministerio():
    assert ingesta.url_dia(date(2026, 3, 7)).endswith("EstacionesTerrestresHist/07-03-2026")


def test_ingesta_de_hoy(monkeypatch, tmp_path, respuesta_api):
    monkeypatch.setattr(ingesta, "cargar_datos", lambda url: respuesta_api)
    monkeypatch.setattr(ingesta, "descargar_mercados", mercados_falsos)

    assert ingesta.main(["--carpeta", str(tmp_path / "h")]) == 0
    assert dias_guardados(tmp_path / "h") == {date.today()}
    assert len(cargar_mercados(tmp_path / "h")) == 1
    assert (tmp_path / "logs" / "ingesta.log").exists()


def test_backfill_salta_los_dias_ya_guardados(monkeypatch, tmp_path, respuesta_api):
    urls = []
    monkeypatch.setattr(ingesta, "cargar_datos", lambda url: urls.append(url) or respuesta_api)
    monkeypatch.setattr(ingesta, "PAUSA_BACKFILL", 0)
    carpeta = tmp_path / "h"

    ok, fallidos = ingesta.backfill(date(2026, 11, 1), date(2026, 11, 3), carpeta, pausa=0)
    assert (ok, fallidos) == (3, 0)

    ok, _ = ingesta.backfill(date(2026, 11, 1), date(2026, 11, 4), carpeta, pausa=0)
    assert ok == 1                                          # solo faltaba el día 4
    assert len(urls) == 4


def test_backfill_sigue_aunque_falle_un_dia(monkeypatch, tmp_path, respuesta_api):
    def carga(url):
        if url.endswith("02-11-2026"):
            raise DataLoadError("caída del servicio")
        return respuesta_api

    monkeypatch.setattr(ingesta, "cargar_datos", carga)
    ok, fallidos = ingesta.backfill(date(2026, 11, 1), date(2026, 11, 3), tmp_path, pausa=0)
    assert (ok, fallidos) == (2, 1)
    assert date(2026, 11, 2) not in dias_guardados(tmp_path)


def test_desde_no_puede_ser_hoy():
    assert ingesta.main(["--desde", date.today().isoformat(), "--sin-mercados"]) == 2


def test_error_de_carga_devuelve_2(monkeypatch):
    def falla(url):
        raise DataLoadError("sin conexión")

    monkeypatch.setattr(ingesta, "cargar_datos", falla)
    assert ingesta.main(["--sin-mercados"]) == 2


def test_error_en_mercados_devuelve_2(monkeypatch, tmp_path, respuesta_api):
    def falla():
        raise DataLoadError("FRED caído")

    monkeypatch.setattr(ingesta, "cargar_datos", lambda url: respuesta_api)
    monkeypatch.setattr(ingesta, "descargar_mercados", falla)
    assert ingesta.main(["--carpeta", str(tmp_path / "h")]) == 2


def test_fecha_no_valida():
    with pytest.raises(SystemExit):
        ingesta.crear_parser().parse_args(["--desde", "12/11/2026"])


def test_backfill_se_detiene_si_el_servicio_no_responde(monkeypatch, tmp_path):
    urls = []

    def falla(url):
        urls.append(url)
        raise DataLoadError("conexión cortada")

    monkeypatch.setattr(ingesta, "cargar_datos", falla)
    ok, fallidos = ingesta.backfill(date(2026, 8, 1), date(2026, 11, 11), tmp_path, pausa=0)
    assert (ok, fallidos) == (0, 3)                         # no insiste con los 103 días
    assert len(urls) == 3
