"""Tests de integración del pipeline del Proyecto I (sin red):

API (simulada) → selección de columnas → normalización → contrato → métricas → CSV.
"""

import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
from pipeline_dsia.constants import COLUMNAS
from pipeline_dsia.metrics import comparar_con_provincia, mas_baratas, precio_medio_por_provincia
from pipeline_dsia.validator import normalizar_numeros, validar_estaciones

pytestmark = pytest.mark.integration


def estacion(ideess, rotulo, provincia, id_provincia, g95, gasoleo, **extra) -> dict:
    """Una estación con el formato real de la API (todo texto, coma decimal)."""
    return {
        "IDEESS": ideess, "Rótulo": rotulo, "Tipo Venta": "P", "Dirección": "Calle",
        "C.P.": "28001", "Municipio": "Municipio", "Provincia": provincia,
        "IDMunicipio": "1", "IDProvincia": id_provincia, "IDCCAA": "13",
        "Latitud": "40,4", "Longitud (WGS84)": "-3,7",
        "Precio Gasolina 95 E5": g95, "Precio Gasolina 98 E5": "",
        "Precio Gasoleo A": gasoleo, "Precio Gasoleo Premium": "",
        "Horario": "L-D: 24H", "Margen": "D",        # columnas de la API que no usamos
        **extra,
    }


@pytest.fixture
def api_simulada() -> pd.DataFrame:
    """Seis estaciones: tres válidas y tres inválidas, con resultados calculables a mano.

    | IDEESS | provincia | g95   | gasóleo A | ¿válida?                    |
    |--------|-----------|-------|-----------|-----------------------------|
    | 10     | MADRID    | 1,600 | 1,400     | sí                          |
    | 11     | MADRID    | 1,500 | 1,300     | sí                          |
    | 12     | ALBACETE  | 1,450 | 1,330     | sí                          |
    | 13     | ALBACETE  | -     | -         | no: no vende nada           |
    | 10     | MADRID    | 1,600 | 1,400     | no: IDEESS repetido         |
    | 15     | ALBACETE  | 9,999 | 1,300     | no: precio fuera de rango   |
    """
    return pd.DataFrame([
        estacion("10", "REPSOL", "MADRID", "28", "1,600", "1,400"),
        estacion("11", "PLENOIL", "MADRID", "28", "1,500", "1,300"),
        estacion("12", "BP", "ALBACETE", "02", "1,450", "1,330"),
        estacion("13", "CEPSA", "ALBACETE", "02", "", ""),
        estacion("10", "REPSOL", "MADRID", "28", "1,600", "1,400"),
        estacion("15", "GALP", "ALBACETE", "02", "9,999", "1,300"),
    ])


def test_modulos_encadenados(api_simulada):
    df_validas, num_invalidas = validar_estaciones(normalizar_numeros(api_simulada[COLUMNAS]))
    assert df_validas["id"].tolist() == ["10", "11", "12"]
    assert num_invalidas == 3

    comparadas = comparar_con_provincia(df_validas).set_index("id")
    # Madrid: gasóleo A medio (1.400 + 1.300) / 2 = 1.350
    assert comparadas.loc["10", "media_prov_gasoleo_a"] == pytest.approx(1.35)
    assert comparadas.loc["10", "dif_gasoleo_a"] == pytest.approx(0.05)
    assert comparadas.loc["11", "dif_gasoleo_a"] == pytest.approx(-0.05)
    # Albacete solo tiene una estación válida: es su propia media
    assert comparadas.loc["12", "dif_media"] == pytest.approx(0.0)

    provincias = precio_medio_por_provincia(df_validas).set_index("id_provincia")
    assert provincias.loc["28", "gasolina_95"] == pytest.approx(1.55)

    # Medias nacionales: g95 = 1.5167, gasóleo A = 1.3433 → BP es la más barata
    assert mas_baratas(df_validas, 1).loc[0, "rotulo"] == "BP"


def test_cli_de_principio_a_fin(api_simulada, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "cargar_datos", lambda url: api_simulada)
    salida = tmp_path / "resultados" / "gasolineras.csv"

    assert cli.main(["--top", "1", "--min-estaciones", "1", "--salida", str(salida)]) == 0

    texto = capsys.readouterr().out
    assert "Estaciones cargadas: 6" in texto
    assert "Válidas: 3 · Inválidas: 3" in texto
    assert "cuesta de media 0.173 €/l más" in texto        # (0.20 + 0.20 + 0.12) / 3

    csv = pd.read_csv(salida, dtype={"id": str, "id_provincia": str}, encoding="utf-8-sig")
    assert csv["id"].tolist() == ["10", "11", "12"]
    assert "Horario" not in csv.columns
    assert csv.set_index("id").loc["12", "dif_gasolina_gasoleo"] == pytest.approx(0.12)


def test_cli_sin_ninguna_estacion_valida(api_simulada, monkeypatch, tmp_path, capsys):
    solo_invalidas = api_simulada.iloc[[3, 5]]
    monkeypatch.setattr(cli, "cargar_datos", lambda url: solo_invalidas)
    salida = tmp_path / "no_se_crea.csv"

    assert cli.main(["--salida", str(salida)]) == 1
    assert "Validación fallida" in capsys.readouterr().out
    assert not salida.exists()
