"""Tests del modelo sklearn: validación temporal, entrenamiento, guardado, carga e inferencia."""

import numpy as np
import pandas as pd
import pytest

from pipeline_dsia.exceptions import ModelError
from pipeline_dsia.features import FEATURES, OBJETIVO, construir_features, filas_entrenables
from pipeline_dsia.historico import a_formato_largo, cargar_historico, cargar_mercados
from pipeline_dsia.modelo import (
    buscar_hiperparametros, calcular_metricas, cargar_metadatos, cargar_modelo, crear_modelo,
    evaluar_modelos, guardar_modelo, particiones_temporales, separar_train_test,
)

REJILLA_PEQUENA = {"modelo__max_iter": [10, 20], "modelo__learning_rate": [0.1]}
HIPER_RAPIDOS = {"max_iter": 20}


@pytest.fixture(scope="module")
def datos(historico_sintetico) -> pd.DataFrame:
    largo = a_formato_largo(cargar_historico(historico_sintetico))
    return filas_entrenables(construir_features(largo, cargar_mercados(historico_sintetico)))


# --- Validación temporal -----------------------------------------------------------

def test_separar_train_test_por_fecha(datos):
    train, test = separar_train_test(datos, 0.2)
    assert train["fecha"].max() < test["fecha"].min()       # el test es siempre posterior
    assert len(train) + len(test) == len(datos)
    assert test["fecha"].nunique() == round(datos["fecha"].nunique() * 0.2)


def test_separar_train_test_sin_dias_suficientes(datos):
    un_dia = datos[datos["fecha"] == datos["fecha"].min()]
    with pytest.raises(ModelError):
        separar_train_test(un_dia)


def test_particiones_temporales_no_mezclan_dias():
    fechas = pd.Series(pd.to_datetime(["2026-11-01"] * 3 + ["2026-11-02"] * 3 + ["2026-11-03"] * 3 + ["2026-11-04"] * 3))
    particiones = particiones_temporales(fechas, n_particiones=3)

    assert len(particiones) == 3
    for entrenamiento, validacion in particiones:
        assert fechas[entrenamiento].max() < fechas[validacion].min()      # se valida con días posteriores
        assert set(fechas[entrenamiento]).isdisjoint(set(fechas[validacion]))
    assert [len(e) for e, _ in particiones] == [3, 6, 9]                   # ventana creciente


def test_particiones_temporales_pocos_dias():
    with pytest.raises(ModelError):
        particiones_temporales(pd.Series(pd.to_datetime(["2026-11-01", "2026-11-02"])), n_particiones=3)


# --- Métricas ------------------------------------------------------------------------

def test_calcular_metricas():
    real = pd.Series([0.0, 0.02, -0.01, 0.0])
    metricas = calcular_metricas(real, np.array([0.0, 0.01, 0.01, 0.0]))
    assert metricas["mae_cts"] == pytest.approx(0.75)       # (0 + 1 + 2 + 0) / 4 céntimos
    assert metricas["rmse_cts"] == pytest.approx(1.118, abs=1e-3)
    assert metricas["acierto_direccion"] == 50.0            # de 2 cambios acierta el signo de 1


def test_la_persistencia_no_acierta_ninguna_direccion():
    metricas = calcular_metricas(pd.Series([0.02, -0.01]), np.zeros(2))
    assert metricas["acierto_direccion"] == 0.0


# --- Entrenamiento ---------------------------------------------------------------------

def test_buscar_hiperparametros(datos):
    train, _ = separar_train_test(datos)
    mejores, tabla = buscar_hiperparametros(train, rejilla=REJILLA_PEQUENA, fraccion_estaciones=0.5)
    assert set(mejores) == {"max_iter", "learning_rate"}
    assert len(tabla) == 2
    assert tabla["rmse_validacion_cts"].is_monotonic_increasing             # ordenada de mejor a peor


def test_evaluar_modelos_devuelve_las_tres_referencias(datos):
    train, test = separar_train_test(datos)
    _, metricas = evaluar_modelos(train, test, HIPER_RAPIDOS)
    assert set(metricas) == {"persistencia", "ridge", "gradient_boosting"}
    for valores in metricas.values():
        assert valores["mae_cts"] >= 0 and valores["rmse_cts"] >= 0


def test_el_modelo_aprende_la_senal_de_los_datos_sinteticos(datos):
    # En los datos inventados el precio sigue al Brent: el modelo debe mejorar a "mañana igual que hoy"
    train, test = separar_train_test(datos)
    _, metricas = evaluar_modelos(train, test, {"max_iter": 100})
    assert metricas["gradient_boosting"]["rmse_cts"] < metricas["persistencia"]["rmse_cts"]


# --- Guardado, carga e inferencia --------------------------------------------------------

def test_guardar_cargar_y_predecir(datos, tmp_path):
    modelo = crear_modelo(**HIPER_RAPIDOS).fit(datos[FEATURES], datos[OBJETIVO])
    guardar_modelo(modelo, {"hiperparametros": HIPER_RAPIDOS}, tmp_path)

    cargado = cargar_modelo(tmp_path)
    muestra = datos[FEATURES].head(50)
    predicciones = cargado.predict(muestra)

    assert predicciones.shape == (50,)
    assert np.isfinite(predicciones).all()
    assert predicciones == pytest.approx(modelo.predict(muestra))           # mismo modelo tras recargar
    assert np.abs(predicciones).max() < 0.5                                 # variaciones plausibles (€/l)

    metadatos = cargar_metadatos(tmp_path)
    assert metadatos["hiperparametros"] == HIPER_RAPIDOS
    assert metadatos["features"] == FEATURES


def test_inferencia_con_huecos_y_categorias_nuevas(datos):
    modelo = crear_modelo(**HIPER_RAPIDOS).fit(datos[FEATURES], datos[OBJETIVO])
    fila = datos[FEATURES].head(1).copy()
    fila["id_provincia"] = "99"                             # provincia que no estaba en el entrenamiento
    fila["dif_precio_7"] = np.nan                           # estación sin una semana de historia
    fila["brent_eur"] = np.nan
    assert np.isfinite(modelo.predict(fila)).all()


def test_cargar_modelo_que_no_existe(tmp_path):
    with pytest.raises(ModelError):
        cargar_modelo(tmp_path)


def test_cargar_modelo_corrupto(tmp_path):
    (tmp_path / "modelo.joblib").write_bytes(b"esto no es un modelo")
    with pytest.raises(ModelError):
        cargar_modelo(tmp_path)
