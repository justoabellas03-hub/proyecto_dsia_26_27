"""Tests de las features, con series pequeñas calculadas a mano."""

import math

import pandas as pd
import pytest

from pipeline_dsia.features import (
    FEATURES, OBJETIVO, RETRASO_MERCADOS_DIAS, construir_features, filas_entrenables, mercados_con_retraso,
    valor_desplazado,
)


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
