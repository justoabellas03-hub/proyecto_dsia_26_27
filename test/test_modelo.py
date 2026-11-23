"""Tests del modelo: features (series pequeñas calculadas a mano) y modelo sklearn
(validación temporal, entrenamiento, guardado, carga e inferencia)."""

import math

import numpy as np
import pandas as pd
import pytest

from pipeline_dsia.config import ModelError
from pipeline_dsia.historico import a_formato_largo, cargar_historico, cargar_mercados
from pipeline_dsia.modelo import (
    FEATURES, OBJETIVO, RETRASO_MERCADOS_DIAS, buscar_hiperparametros, calcular_metricas, cargar_metadatos,
    cargar_modelo, construir_features, crear_modelo, evaluar_modelos, filas_entrenables, guardar_modelo,
    mercados_con_retraso, particiones_temporales, separar_train_test, valor_desplazado,
)

# ======================================================================================
# 1. Features
# ======================================================================================

def serie(precios: dict[str, float], id_estacion: str = "1", provincia: str = "28") -> pd.DataFrame:
    """Una estación y un carburante: {fecha: precio}."""
    return pd.DataFrame({
        "fecha": pd.to_datetime(list(precios)), "id": id_estacion, "carburante": "gasoleo_a",
        "id_provincia": provincia, "tipo_venta": "P", "latitud": 40.0, "longitud": -3.0,
        "precio": list(precios.values()),
    })


def mercados(desde="2026-10-01", hasta="2026-11-30") -> pd.DataFrame:
    fechas = pd.date_range(desde, hasta, freq="D")
    return pd.DataFrame({"fecha": fechas, "brent_eur": [70.0 + i for i in range(len(fechas))]})


def test_valor_desplazado_respeta_los_huecos():
    # Falta el día 3: el "día anterior" del día 4 no existe
    df = serie({"2026-11-01": 1.40, "2026-11-02": 1.42, "2026-11-04": 1.45})
    ayer = valor_desplazado(df, "precio", 1)
    assert math.isnan(ayer[0])
    assert ayer[1] == pytest.approx(1.40)
    assert math.isnan(ayer[2])                              # no usa por error el dato del día 2


def test_objetivo_es_precio_de_manana_menos_hoy():
    df = serie({"2026-11-01": 1.40, "2026-11-02": 1.42, "2026-11-03": 1.39})
    datos = construir_features(df, mercados())
    assert datos[OBJETIVO].tolist()[:2] == pytest.approx([0.02, -0.03])
    assert math.isnan(datos[OBJETIVO].iloc[2])              # del último día aún no se conoce mañana


def test_diferencias_de_precio():
    df = serie({f"2026-11-0{d}": 1.40 + d / 100 for d in range(1, 9)})   # sube 1 céntimo al día
    datos = construir_features(df, mercados())
    ultima = datos.iloc[-1]
    assert ultima["dif_precio_1"] == pytest.approx(0.01)
    assert ultima["dif_precio_3"] == pytest.approx(0.03)
    assert ultima["dif_precio_7"] == pytest.approx(0.07)
    assert math.isnan(datos.iloc[0]["dif_precio_1"])        # el primer día no tiene ayer


def test_series_de_distintas_estaciones_no_se_mezclan():
    df = pd.concat([serie({"2026-11-01": 1.40, "2026-11-02": 1.41}, "1"),
                    serie({"2026-11-01": 1.90, "2026-11-02": 1.95}, "2")])
    datos = construir_features(df, mercados()).set_index(["id", "fecha"])
    assert datos.loc[("1", "2026-11-01"), OBJETIVO] == pytest.approx(0.01)
    assert datos.loc[("2", "2026-11-01"), OBJETIVO] == pytest.approx(0.05)


def test_contexto_de_la_provincia():
    df = pd.concat([serie({"2026-11-01": 1.40, "2026-11-02": 1.40}, "1"),
                    serie({"2026-11-01": 1.50, "2026-11-02": 1.60}, "2")])
    datos = construir_features(df, mercados()).set_index(["id", "fecha"])
    # Día 2: media de la provincia 1.50 (ayer 1.45)
    assert datos.loc[("1", "2026-11-02"), "dif_provincia"] == pytest.approx(-0.10)
    assert datos.loc[("1", "2026-11-02"), "var_provincia_1"] == pytest.approx(0.05)


def test_mercados_con_retraso_no_usa_el_futuro():
    m = mercados()
    retrasado = mercados_con_retraso(m).set_index("fecha")
    original = m.set_index("fecha")["brent_eur"]
    dia = pd.Timestamp("2026-11-12")
    # El día 12 se usa el Brent de 10 días antes
    assert retrasado.loc[dia, "brent_eur"] == original[dia - pd.Timedelta(days=RETRASO_MERCADOS_DIAS)]
    esperado = (original[dia - pd.Timedelta(days=10)] / original[dia - pd.Timedelta(days=17)] - 1) * 100
    assert retrasado.loc[dia, "var_brent_7"] == pytest.approx(esperado)


def test_construir_features_tiene_todas_las_columnas_y_no_pierde_filas():
    df = serie({"2026-11-01": 1.40, "2026-11-02": 1.42})
    datos = construir_features(df, mercados())
    assert len(datos) == 2
    assert set(FEATURES) <= set(datos.columns)
    assert datos["dia_semana"].tolist() == [6, 0]           # domingo y lunes


def test_sin_datos_de_mercado_las_features_quedan_vacias():
    df = serie({"2026-11-01": 1.40, "2026-11-02": 1.42})
    datos = construir_features(df, mercados("2027-01-01", "2027-01-05"))
    assert datos["brent_eur"].isna().all()                  # el modelo acepta NaN


def test_filas_entrenables_quita_la_primera_semana_y_el_ultimo_dia():
    df = serie({f"2026-11-{d:02d}": 1.40 for d in range(1, 13)})            # del 1 al 12
    filas = filas_entrenables(construir_features(df, mercados()))
    assert filas["fecha"].dt.day.tolist() == [8, 9, 10, 11]                 # desde el día 8; el 12 no tiene mañana


def test_filas_entrenables_descarta_variaciones_imposibles():
    precios = {f"2026-11-{d:02d}": 1.50 for d in range(1, 13)}
    precios["2026-11-10"] = 0.50                            # error de carga: 1,50 → 0,50 → 1,50
    filas = filas_entrenables(construir_features(serie(precios), mercados()))
    assert filas["fecha"].dt.day.tolist() == [8, 11]        # los días 9 y 10 tendrían saltos de 1 €


def test_tendencia_nacional_es_la_media_del_cambio_de_hoy():
    df = pd.concat([serie({"2026-11-01": 1.40, "2026-11-02": 1.42}, "1", "28"),
                    serie({"2026-11-01": 1.50, "2026-11-02": 1.50}, "2", "08")])
    datos = construir_features(df, mercados())
    hoy = datos[datos["fecha"] == "2026-11-02"]
    assert hoy["var_nacional_1"].tolist() == pytest.approx([0.01, 0.01])   # (0.02 + 0) / 2


# ======================================================================================
# 2. Modelo sklearn
# ======================================================================================

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
