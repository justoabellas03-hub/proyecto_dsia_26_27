"""Tests de integración: histórico → entrenar → predecir → explicación (todo sin red)."""

import json

import numpy as np
import pandas as pd
import pytest

import pipeline_dsia.entrenar as entrenar
import pipeline_dsia.predecir as predecir
from pipeline_dsia.ia import ClienteMock

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
    original = entrenar.buscar_hiperparametros
    entrenar.buscar_hiperparametros = lambda train, **kw: original(train, rejilla=rejilla, **kw)
    try:
        codigo = entrenar.main(["--carpeta", str(historico_sintetico), "--modelos", str(carpeta)])
    finally:
        entrenar.buscar_hiperparametros = original
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
    assert entrenar.main(["--carpeta", str(historico_sintetico), "--modelos", str(tmp_path / "m"), "--sin-busqueda"]) == 0
    metadatos = json.loads((tmp_path / "m" / "metricas.json").read_text(encoding="utf-8"))
    assert metadatos["hiperparametros"] == {"max_iter": 15}


def test_predecir_de_extremo_a_extremo(historico_sintetico, modelos, tmp_path, capsys):
    salida = tmp_path / "resultados"
    codigo = predecir.main(["--carpeta", str(historico_sintetico), "--modelos", str(modelos), "--salida", str(salida)])
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

    assert predecir.main(["--carpeta", str(historico_sintetico), "--modelos", str(modelos),
                          "--salida", str(tmp_path)], cliente=Espia()) == 0
    assert {c.carburante for c in Espia.resumen.carburantes} == {"gasoleo_a", "gasolina_95"}
    assert Espia.resumen.var_brent_7 is not None


def test_predecir_sin_modelo_devuelve_3(historico_sintetico, tmp_path):
    assert predecir.main(["--carpeta", str(historico_sintetico), "--modelos", str(tmp_path / "vacio")]) == 3


def test_predecir_sin_historico_devuelve_2(tmp_path):
    assert predecir.main(["--carpeta", str(tmp_path / "nada")]) == 2


def test_entrenar_sin_historico_devuelve_2(tmp_path):
    assert entrenar.main(["--carpeta", str(tmp_path / "nada")]) == 2


def test_entrenar_con_pocos_dias_devuelve_1(tmp_path):
    from conftest import crear_historico_sintetico
    crear_historico_sintetico(tmp_path / "corto", n_estaciones=5, n_dias=12)
    assert entrenar.main(["--carpeta", str(tmp_path / "corto"), "--modelos", str(tmp_path / "m")]) == 1
