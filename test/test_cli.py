"""Tests de la línea de comandos (sin conexión: se simula la descarga)."""

import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
from pipeline_dsia.exceptions import DataLoadError


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
    args = cli.crear_parser().parse_args([])
    assert args.top == 10
    assert args.min_estaciones == 20
    assert args.salida == "data/gasolineras_metricas.csv"


@pytest.mark.parametrize("argumentos", [["--top", "0"], ["--top", "diez"], ["--min-estaciones", "-1"]])
def test_rechaza_valores_no_validos(argumentos):
    with pytest.raises(SystemExit):
        cli.crear_parser().parse_args(argumentos)


def test_ejecucion_completa(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "cargar_datos", lambda url: respuesta_api())
    salida = tmp_path / "carpeta_nueva" / "resultados.csv"

    codigo = cli.main(["--top", "1", "--min-estaciones", "1", "--salida", str(salida)])

    assert codigo == 0
    texto = capsys.readouterr().out
    assert "Válidas: 2 · Inválidas: 0" in texto
    assert "PLENOIL" in texto

    csv = pd.read_csv(salida, dtype={"id_provincia": str})
    assert len(csv) == 2
    for columna in ["media_prov_gasoleo_a", "dif_gasoleo_a", "dif_media", "dif_gasolina_gasoleo"]:
        assert columna in csv.columns
    assert csv.loc[0, "media_prov_gasoleo_a"] == pytest.approx(1.429)   # (1.459 + 1.399) / 2


def test_crea_el_csv_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "cargar_datos", lambda url: respuesta_api())
    monkeypatch.chdir(tmp_path)

    assert cli.main([]) == 0
    assert (tmp_path / "data" / "gasolineras_metricas.csv").exists()


def test_error_de_carga(monkeypatch, capsys):
    def falla(url):
        raise DataLoadError("sin conexión")

    monkeypatch.setattr(cli, "cargar_datos", falla)
    assert cli.main([]) == 2
    assert "sin conexión" in capsys.readouterr().out
