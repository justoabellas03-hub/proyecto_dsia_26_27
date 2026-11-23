"""Tests de integración (sin red):

1. Pipeline de métricas del Proyecto I: API simulada → columnas → normalización → contrato → métricas → CSV.
2. Pipeline del modelo: histórico → entrenar → predecir → explicación.
"""

import json

import numpy as np
import pandas as pd
import pytest

import pipeline_dsia.__main__ as cli
import pipeline_dsia.modelo as modelo
import pipeline_dsia.predecir as predecir
from pipeline_dsia.config import COLUMNAS
from pipeline_dsia.ia import ClienteMock
from pipeline_dsia.metrics import comparar_con_provincia, mas_baratas, precio_medio_por_provincia
from pipeline_dsia.validator import normalizar_numeros, validar_estaciones

pytestmark = pytest.mark.integration

# ======================================================================================
# 1. Pipeline de métricas (Proyecto I)
# ======================================================================================

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

    assert cli.main(["metricas", "--top", "1", "--min-estaciones", "1", "--salida", str(salida)]) == 0

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

    assert cli.main(["metricas", "--salida", str(salida)]) == 1
    assert "Validación fallida" in capsys.readouterr().out
    assert not salida.exists()


# ======================================================================================
# 2. Pipeline del modelo: histórico → entrenar → predecir
# ======================================================================================

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch, tmp_path):
    """Logs en una carpeta temporal y sin variables de IA: siempre mock."""
    monkeypatch.chdir(tmp_path)
    for variable in ("AI_PROVIDER", "HF_TOKEN", "HF_MODEL"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(scope="module")
def modelos(historico_sintetico, tmp_path_factory):
    """Entrena una vez con una rejilla pequeña (para que el test sea rápido)."""
    carpeta = tmp_path_factory.mktemp("models")
    rejilla = {"modelo__max_iter": [20, 40]}
    original = modelo.buscar_hiperparametros
    modelo.buscar_hiperparametros = lambda train, **kw: original(train, rejilla=rejilla, **kw)
    try:
        codigo = cli.main(["entrenar", "--carpeta", str(historico_sintetico), "--modelos", str(carpeta)])
    finally:
        modelo.buscar_hiperparametros = original
    assert codigo == 0
    return carpeta


def test_entrenar_genera_modelo_metricas_e_informe(modelos):
    assert (modelos / "modelo.joblib").exists()

    metadatos = json.loads((modelos / "metricas.json").read_text(encoding="utf-8"))
    assert set(metadatos["metricas_test"]) == {"persistencia", "ridge", "gradient_boosting"}
    assert metadatos["train_hasta"] < metadatos["test_desde"]              # sin fuga temporal
    assert metadatos["hiperparametros"]["max_iter"] in (20, 40)

    informe = (modelos / "INFORME_MODELO.md").read_text(encoding="utf-8")
    for apartado in ("Hiperparámetros elegidos", "Métricas en test", "Importancia de las variables"):
        assert apartado in informe


def test_entrenar_sin_busqueda_reutiliza_hiperparametros(historico_sintetico, modelos, tmp_path):
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "metricas.json").write_text(json.dumps({"hiperparametros": {"max_iter": 15}}), encoding="utf-8")
    assert cli.main(["entrenar", "--carpeta", str(historico_sintetico), "--modelos", str(tmp_path / "m"), "--sin-busqueda"]) == 0
    metadatos = json.loads((tmp_path / "m" / "metricas.json").read_text(encoding="utf-8"))
    assert metadatos["hiperparametros"] == {"max_iter": 15}


def test_predecir_de_extremo_a_extremo(historico_sintetico, modelos, tmp_path, capsys):
    salida = tmp_path / "resultados"
    codigo = cli.main(["predecir", "--carpeta", str(historico_sintetico), "--modelos", str(modelos), "--salida", str(salida)])
    assert codigo == 0

    predicciones = pd.read_csv(salida / "predicciones.csv", dtype={"id": str})
    assert len(predicciones) == 60                                         # 30 estaciones × 2 carburantes
    assert (predicciones["fecha_prediccion"] == "2026-11-11").all()        # día siguiente al último del histórico
    assert predicciones["precio_previsto"].between(0.5, 3.5).all()
    diferencia = predicciones["precio_previsto"] - predicciones["precio_hoy"]
    assert np.allclose(diferencia, predicciones["variacion_prevista"], atol=1e-6)

    informe = (salida / "informe_prediccion.md").read_text(encoding="utf-8")
    assert "11/11/2026" in informe and "proveedor `mock`" in informe
    assert "estimación de un modelo estadístico" in capsys.readouterr().out


def test_predecir_acepta_un_cliente_inyectado(historico_sintetico, modelos, tmp_path):
    class Espia(ClienteMock):
        resumen = None

        def explicar(self, resumen):
            Espia.resumen = resumen
            return super().explicar(resumen)

    assert predecir.ejecutar_prediccion(historico_sintetico, modelos, tmp_path, cliente=Espia()) == 0
    assert {c.carburante for c in Espia.resumen.carburantes} == {"gasoleo_a", "gasolina_95"}
    assert Espia.resumen.var_brent_7 is not None


def test_predecir_sin_modelo_devuelve_3(historico_sintetico, tmp_path):
    assert cli.main(["predecir", "--carpeta", str(historico_sintetico), "--modelos", str(tmp_path / "vacio")]) == 3


def test_predecir_sin_historico_devuelve_2(tmp_path):
    assert cli.main(["predecir", "--carpeta", str(tmp_path / "nada")]) == 2


def test_entrenar_sin_historico_devuelve_2(tmp_path):
    assert cli.main(["entrenar", "--carpeta", str(tmp_path / "nada")]) == 2


def test_entrenar_con_pocos_dias_devuelve_1(tmp_path):
    from conftest import crear_historico_sintetico
    crear_historico_sintetico(tmp_path / "corto", n_estaciones=5, n_dias=12)
    assert cli.main(["entrenar", "--carpeta", str(tmp_path / "corto"), "--modelos", str(tmp_path / "m")]) == 1
