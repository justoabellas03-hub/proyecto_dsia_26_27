"""Tests de las métricas, con resultados calculados a mano a partir de conftest.estaciones."""

import math

import pandas as pd
import pytest

from pipeline_dsia.metrics import (
    comparar_con_provincia,
    diferencia_gasolina_gasoleo,
    mas_baratas,
    media_carburante,
    media_diferencia_gasolina_gasoleo,
    media_gasolinera,
    precio_medio_por_marca,
    precio_medio_por_provincia,
)


# --- Funciones base ------------------------------------------------------------

def test_media_carburante_nacional(estaciones):
    # (1.45 + 1.40 + 1.20 + 1.30 + 1.34) / 5
    assert media_carburante(estaciones, "gasoleo_a") == pytest.approx(1.338)


def test_media_carburante_por_provincia_alineada_por_fila(estaciones):
    medias = media_carburante(estaciones, "gasoleo_a", "id_provincia")
    # Madrid: (1.45 + 1.40 + 1.20) / 3 = 1.35 · Albacete: (1.30 + 1.34) / 2 = 1.32
    assert medias.tolist() == pytest.approx([1.35, 1.35, 1.35, 1.32, 1.32])


def test_media_gasolinera_ignora_carburantes_que_no_vende(estaciones):
    medias = media_gasolinera(estaciones, ["gasolina_95", "gasoleo_a"])
    assert medias.iloc[0] == pytest.approx((1.60 + 1.45) / 2)
    assert medias.iloc[2] == pytest.approx(1.20)   # solo vende gasóleo A


# --- Precio medio por provincia --------------------------------------------------

def test_precio_medio_por_provincia(estaciones):
    tabla = precio_medio_por_provincia(estaciones).set_index("provincia")

    assert len(tabla) == 2
    assert tabla.loc["MADRID", "gasolina_95"] == pytest.approx(1.55)
    assert tabla.loc["MADRID", "gasoleo_a"] == pytest.approx(1.35)
    assert tabla.loc["ALBACETE", "gasolina_95"] == pytest.approx(1.42)
    # media de las medias: (1.55 + 1.80 + 1.35) / 3
    assert tabla.loc["MADRID", "media_carburantes"] == pytest.approx(1.567, abs=1e-3)
    assert math.isnan(tabla.loc["MADRID", "gasoleo_premium"])


# --- Comparación con la provincia -----------------------------------------------

def test_comparar_con_provincia(estaciones):
    resultado = comparar_con_provincia(estaciones)

    assert resultado.loc[0, "media_prov_gasoleo_a"] == pytest.approx(1.35)
    assert resultado.loc[3, "media_prov_gasoleo_a"] == pytest.approx(1.32)
    assert resultado.loc[0, "dif_gasoleo_a"] == pytest.approx(0.10)   # 1.45 - 1.35
    assert resultado.loc[0, "dif_gasolina_98"] == pytest.approx(0.0)  # única que vende 98
    assert resultado.loc[0, "dif_media"] == pytest.approx(0.05)       # (0.05 + 0 + 0.10) / 3
    assert resultado.loc[1, "dif_media"] == pytest.approx(0.0)        # (-0.05 + 0.05) / 2
    assert resultado.loc[2, "dif_media"] == pytest.approx(-0.15)


def test_comparar_con_provincia_no_modifica_la_entrada(estaciones):
    columnas_antes = list(estaciones.columns)
    comparar_con_provincia(estaciones)
    assert list(estaciones.columns) == columnas_antes


def test_comparar_con_provincia_no_redondea_coordenadas():
    df = pd.DataFrame({
        "id_provincia": ["28"], "latitud": [40.416775],
        "gasolina_95": [1.5], "gasolina_98": [1.7], "gasoleo_a": [1.4], "gasoleo_premium": [1.5],
    })
    assert comparar_con_provincia(df).loc[0, "latitud"] == 40.416775


# --- Más baratas ----------------------------------------------------------------

def test_mas_baratas_solo_publicas(estaciones):
    ranking = mas_baratas(estaciones, 3)
    # dif_nacional: estación 4 = -0.0615, estación 5 = -0.0215, estación 2 = 0.0385
    assert ranking["direccion"].tolist() == ["Calle D", "Calle E", "Calle B"]
    assert ranking.loc[0, "dif_nacional"] == pytest.approx(-0.0615, abs=1e-3)


def test_mas_baratas_incluyendo_venta_restringida(estaciones):
    ranking = mas_baratas(estaciones, 1, solo_publicas=False)
    assert ranking.loc[0, "direccion"] == "Calle C"   # cooperativa, 1.20 en gasóleo A


def test_mas_baratas_n_mayor_que_estaciones(estaciones):
    assert len(mas_baratas(estaciones, 100)) == 4     # 4 públicas


@pytest.mark.parametrize("n", [0, -3])
def test_mas_baratas_n_no_valido(estaciones, n):
    with pytest.raises(ValueError):
        mas_baratas(estaciones, n)


# --- Precio por marca -----------------------------------------------------------

def test_precio_medio_por_marca_unifica_rotulos(estaciones):
    tabla = precio_medio_por_marca(estaciones, min_estaciones=1)
    # "Repsol" y "REPSOL " cuentan como la misma marca
    assert tabla["rotulo"].tolist() == ["COOP", "PLENOIL", "REPSOL"]
    repsol = tabla.set_index("rotulo").loc["REPSOL"]
    assert repsol["num_estaciones"] == 2
    assert repsol["dif_media"] == pytest.approx(0.025, abs=1e-3)   # (0.05 + 0.0) / 2


def test_precio_medio_por_marca_filtra_por_minimo(estaciones):
    tabla = precio_medio_por_marca(estaciones, min_estaciones=2)
    assert "COOP" not in tabla["rotulo"].tolist()


# --- Gasolina frente a gasóleo -----------------------------------------------------

def test_diferencia_gasolina_gasoleo(estaciones):
    resultado = diferencia_gasolina_gasoleo(estaciones)
    assert resultado.loc[0, "dif_gasolina_gasoleo"] == pytest.approx(0.15)
    assert math.isnan(resultado.loc[2, "dif_gasolina_gasoleo"])   # no vende gasolina 95
    assert "dif_gasolina_gasoleo" not in estaciones.columns         # no toca la entrada


def test_media_diferencia_gasolina_gasoleo(estaciones):
    # (0.15 + 0.10 + 0.10 + 0.10) / 4; la estación 3 no cuenta
    media = media_diferencia_gasolina_gasoleo(estaciones)
    assert isinstance(media, float)
    assert media == pytest.approx(0.1125, abs=1e-3)
