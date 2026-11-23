"""Tests de la consulta de predicciones (la predicción completa está en test_integration.py)."""

import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
import pipeline_dsia.predecir as predecir

@pytest.fixture
def predicciones() -> pd.DataFrame:
    return pd.DataFrame({
        "fecha_prediccion": "2026-11-13",
        "id": ["1", "1", "2", "3", "4"],
        "rotulo": ["REPSOL", "REPSOL", "Plenoil", None, "CEPSA"],
        "municipio": ["Córdoba", "Córdoba", "Lucena", "Coruña (A)", "Getafe"],
        "provincia": ["CÓRDOBA", "CÓRDOBA", "CÓRDOBA", "CORUÑA (A)", "MADRID"],
        "carburante": ["gasoleo_a", "gasolina_95", "gasoleo_a", "gasoleo_a", "gasoleo_a"],
        "precio_hoy": [1.500, 1.600, 1.400, 1.450, 1.480],
        "variacion_prevista": [-0.010, -0.005, 0.000, 0.002, -0.004],
        "precio_previsto": [1.490, 1.595, 1.400, 1.452, 1.476],
    })


@pytest.fixture
def fichero(predicciones, tmp_path):
    ruta = tmp_path / "predicciones.csv"
    predicciones.to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta


def test_normalizar_quita_tildes_y_mayusculas():
    assert predecir.normalizar(" córdoba ") == "CORDOBA"
    assert predecir.normalizar("Coruña (A)") == "CORUNA (A)"


def test_filtrar_por_provincia_sin_tildes(predicciones):
    filas = predecir.filtrar(predicciones, provincia="cordoba")
    assert filas["id"].tolist() == ["1", "1", "2"]


def test_filtrar_por_parte_del_nombre(predicciones):
    assert predecir.filtrar(predicciones, provincia="coruña")["id"].tolist() == ["3"]


def test_filtros_combinados(predicciones):
    filas = predecir.filtrar(predicciones, provincia="córdoba", carburante="gasoleo_a", rotulo="repsol")
    assert filas["id"].tolist() == ["1"]


def test_filtrar_por_estacion_es_exacto(predicciones):
    assert len(predecir.filtrar(predicciones, estacion="1")) == 2          # no incluye la 10, 11...
    assert predecir.filtrar(predicciones, estacion="99").empty


def test_rotulo_vacio_no_rompe_el_filtro(predicciones):
    assert predecir.filtrar(predicciones, rotulo="cepsa")["id"].tolist() == ["4"]


def test_resumen_por_carburante(predicciones):
    resumen = predecir.resumen_por_carburante(predecir.filtrar(predicciones, provincia="cordoba"))
    gasoleo = resumen.set_index("carburante").loc["gasoleo_a"]
    assert gasoleo["estaciones"] == 2
    assert gasoleo["precio_medio_hoy"] == pytest.approx(1.45)
    assert gasoleo["precio_medio_previsto"] == pytest.approx(1.445)
    assert gasoleo["variacion_cts"] == pytest.approx(-0.5)


def test_mas_baratas_previstas(predicciones):
    filas = predecir.filtrar(predicciones, carburante="gasoleo_a")
    assert predecir.mas_baratas_previstas(filas, 2)["id"].tolist() == ["2", "3"]


def test_cli_provincia_y_carburante(fichero, capsys):
    codigo = cli.main(["consultar", "--provincia", "cordoba", "--carburante", "gasoleo_a", "--predicciones", str(fichero)])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "2026-11-13" in salida and "2 estaciones" in salida
    assert "1.445" in salida and "Plenoil" in salida


def test_cli_estacion(fichero, capsys):
    assert cli.main(["consultar", "--estacion", "1", "--predicciones", str(fichero)]) == 0
    salida = capsys.readouterr().out
    assert "gasolina_95" in salida and "1.595" in salida


def test_cli_sin_coincidencias(fichero, capsys):
    assert cli.main(["consultar", "--provincia", "atlantida", "--predicciones", str(fichero)]) == 1


def test_cli_sin_fichero_de_predicciones(tmp_path, capsys):
    assert cli.main(["consultar", "--predicciones", str(tmp_path / "no_existe.csv")]) == 2
    assert "predecir" in capsys.readouterr().out


def test_cli_carburante_no_valido(fichero):
    with pytest.raises(SystemExit):
        cli.main(["consultar", "--carburante", "queroseno", "--predicciones", str(fichero)])
