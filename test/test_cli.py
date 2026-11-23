"""Tests de la línea de comandos (sin conexión: se simula la descarga)."""

from datetime import date

import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
from pipeline_dsia.config import DataLoadError

def respuesta_api() -> pd.DataFrame:
    """Dos estaciones con el formato real de la API: texto y coma decimal."""
    base = {
        "IDEESS": "1", "Rótulo": "REPSOL", "Tipo Venta": "P", "Dirección": "Calle A",
        "C.P.": "28001", "Municipio": "Madrid", "Provincia": "MADRID",
        "IDMunicipio": "4354", "IDProvincia": "28", "IDCCAA": "13",
        "Latitud": "40,416775", "Longitud (WGS84)": "-3,703790",
        "Precio Gasolina 95 E5": "1,599", "Precio Gasolina 98 E5": "",
        "Precio Gasoleo A": "1,459", "Precio Gasoleo Premium": "",
        "Horario": "L-D: 24H",
    }
    otra = {**base, "IDEESS": "2", "Rótulo": "PLENOIL", "Precio Gasoleo A": "1,399"}
    return pd.DataFrame([base, otra])


def test_valores_por_defecto():
    args = cli.crear_parser().parse_args(["metricas"])
    assert args.top == 10
    assert args.min_estaciones == 20
    assert args.salida == "data/gasolineras_metricas.csv"


@pytest.mark.parametrize("argumentos", [["metricas", "--top", "0"], ["metricas", "--top", "diez"], ["metricas", "--min-estaciones", "-1"]])
def test_rechaza_valores_no_validos(argumentos):
    with pytest.raises(SystemExit):
        cli.crear_parser().parse_args(argumentos)


def test_crea_el_csv_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "cargar_datos", lambda url: respuesta_api())
    monkeypatch.chdir(tmp_path)

    assert cli.main(["metricas"]) == 0
    assert (tmp_path / "data" / "gasolineras_metricas.csv").exists()


def test_error_de_carga(monkeypatch, capsys):
    def falla(url):
        raise DataLoadError("sin conexión")

    monkeypatch.setattr(cli, "cargar_datos", falla)
    assert cli.main(["metricas"]) == 2
    assert "sin conexión" in capsys.readouterr().out


@pytest.mark.parametrize("argumentos", [
    ["desconocido"],
    ["ingesta", "--desde", "12/11/2026"],                   # fecha con formato no válido
    ["entrenar", "--fraccion-test", "1.5"],
    ["consultar", "--carburante", "queroseno"],
])
def test_comandos_no_validos(argumentos):
    with pytest.raises(SystemExit):
        cli.crear_parser().parse_args(argumentos)


# --- Flujo completo (todo) -------------------------------------------------------------

@pytest.fixture
def pasos(monkeypatch):
    """Sustituye cada paso por uno falso que apunta que se ha llamado y devuelve su código."""
    llamadas, codigos = [], {"ingesta": 0, "entrenar": 0, "predecir": 0, "metricas": 0}

    def falso(paso):
        def funcion(*args, **kwargs):
            llamadas.append(paso)
            return codigos[paso]
        return funcion

    monkeypatch.setattr(cli, "ejecutar_ingesta", falso("ingesta"))
    monkeypatch.setattr(cli, "ejecutar_entrenamiento", falso("entrenar"))
    monkeypatch.setattr(cli, "ejecutar_prediccion", falso("predecir"))
    monkeypatch.setattr(cli, "ejecutar_metricas", falso("metricas"))
    return llamadas, codigos


@pytest.mark.parametrize("argumentos", [[], ["todo"]])
def test_sin_comando_ejecuta_todo_en_orden(pasos, monkeypatch, argumentos):
    llamadas, _ = pasos
    monkeypatch.setattr(cli, "toca_reentrenar", lambda reentrenar=False: True)
    assert cli.main(argumentos) == 0
    assert llamadas == ["ingesta", "entrenar", "predecir", "metricas"]


def test_todo_sin_reentrenar(pasos, monkeypatch, capsys):
    llamadas, _ = pasos
    monkeypatch.setattr(cli, "toca_reentrenar", lambda reentrenar=False: False)
    assert cli.main(["todo"]) == 0
    assert llamadas == ["ingesta", "predecir", "metricas"]
    assert "Hoy no toca reentrenar" in capsys.readouterr().out


def test_todo_sigue_aunque_falle_la_ingesta(pasos, monkeypatch, capsys):
    llamadas, codigos = pasos
    codigos["ingesta"] = 2
    monkeypatch.setattr(cli, "toca_reentrenar", lambda reentrenar=False: False)
    assert cli.main(["todo"]) == 2                      # devuelve el código del paso que falló
    assert llamadas == ["ingesta", "predecir", "metricas"]
    assert "ingesta   falló (código 2)" in capsys.readouterr().out


def test_toca_reentrenar(monkeypatch, tmp_path):
    lunes, martes = date(2026, 11, 23), date(2026, 11, 24)
    monkeypatch.setattr(cli, "CARPETA_MODELOS", tmp_path)          # carpeta sin modelo
    assert cli.toca_reentrenar(hoy=martes) is True                  # no hay modelo
    (tmp_path / "modelo.joblib").write_bytes(b"x")
    assert cli.toca_reentrenar(hoy=martes) is False
    assert cli.toca_reentrenar(hoy=lunes) is True
    assert cli.toca_reentrenar(reentrenar=True, hoy=martes) is True
