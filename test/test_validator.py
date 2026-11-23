"""Tests del validador: normalización de números y contrato de las estaciones."""

import pandas as pd
import pytest

from pipeline_dsia.config import CAMPOS_PRECIOS, COORDENADAS, ValidationError
from pipeline_dsia.validator import CAMPOS_PRECIO, normalizar_numeros, validar_estaciones

def validar(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Lo mismo que hace el pipeline: primero normalizar, luego validar."""
    return validar_estaciones(normalizar_numeros(df))


# --- normalizar_numeros --------------------------------------------------------------

def test_normalizar_cambia_coma_por_punto(respuesta_api):
    resultado = normalizar_numeros(respuesta_api)
    assert resultado.loc[0, "Latitud"] == "40.416775"
    assert resultado.loc[0, "Longitud (WGS84)"] == "-3.703790"
    assert resultado.loc[0, "Precio Gasolina 95 E5"] == "1.599"


def test_normalizar_solo_toca_precios_y_coordenadas(respuesta_api):
    resultado = normalizar_numeros(respuesta_api)
    otras = [c for c in respuesta_api.columns if c not in (*CAMPOS_PRECIOS, *COORDENADAS)]
    pd.testing.assert_frame_equal(resultado[otras], respuesta_api[otras])


def test_normalizar_no_modifica_la_entrada(respuesta_api):
    antes = respuesta_api.copy()
    normalizar_numeros(respuesta_api)
    pd.testing.assert_frame_equal(respuesta_api, antes)


def test_normalizar_deja_vacios_como_vacios(respuesta_api):
    assert normalizar_numeros(respuesta_api).loc[0, "Precio Gasolina 98 E5"] == ""


# --- validar_estaciones: caso normal -----------------------------------------------------

def test_validar_separa_validas_e_invalidas(respuesta_api):
    df_validas, num_invalidas = validar(respuesta_api)
    # La estación 3 no vende ningún carburante analizado
    assert df_validas["id"].tolist() == ["1", "2"]
    assert num_invalidas == 1


def test_validar_renombra_y_convierte_tipos(respuesta_api):
    df_validas, _ = validar(respuesta_api)
    for columna in ["id", "rotulo", "tipo_venta", "provincia", "latitud", "longitud", *CAMPOS_PRECIO]:
        assert columna in df_validas.columns
    assert df_validas.loc[0, "latitud"] == pytest.approx(40.416775)
    assert df_validas.loc[0, "gasolina_95"] == pytest.approx(1.599)
    for campo in CAMPOS_PRECIO:
        assert df_validas[campo].dtype == "float64"


def test_precio_vacio_pasa_a_nan(respuesta_api):
    df_validas, _ = validar(respuesta_api)
    assert df_validas["gasolina_98"].isna().all()
    assert df_validas["gasoleo_premium"].isna().all()


def test_quita_espacios_y_vacios_a_none(respuesta_api):
    df = respuesta_api.copy()
    df.loc[0, "Rótulo"] = "  REPSOL  "
    df.loc[0, "Dirección"] = "   "
    df_validas, _ = validar(df)
    assert df_validas.loc[0, "rotulo"] == "REPSOL"
    assert pd.isna(df_validas.loc[0, "direccion"])     # "" → None → NaN en el DataFrame


def test_columnas_extra_se_ignoran(respuesta_api):
    df_validas, _ = validar(respuesta_api.assign(Horario="L-D: 24H"))
    assert "Horario" not in df_validas.columns
    assert len(df_validas) == 2


# --- validar_estaciones: reglas del contrato ---------------------------------------------

@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("IDEESS", "abc"),                    # el id debe ser numérico
        ("C.P.", "2800"),                     # código postal de 5 cifras
        ("Tipo Venta", "X"),                  # solo P (pública) o R (restringida)
        ("IDProvincia", "2"),                 # provincia con 2 cifras
        ("Municipio", ""),                    # obligatorio
        ("Latitud", "50,0"),                  # fuera de España
        ("Longitud (WGS84)", "10,0"),
        ("Precio Gasolina 95 E5", "0,10"),    # precio imposible por abajo
        ("Precio Gasoleo A", "9,99"),         # precio imposible por arriba
        ("Precio Gasoleo A", "gratis"),       # no es un número
    ],
)
def test_estacion_que_incumple_el_contrato(respuesta_api, columna, valor):
    df = respuesta_api.iloc[[0]].copy()      # solo la estación 1, que es válida
    otra = respuesta_api.iloc[[1]].copy()    # la 2 sigue siendo válida para que no falle todo
    df[columna] = valor
    df_validas, num_invalidas = validar(pd.concat([df, otra], ignore_index=True))
    assert df_validas["id"].tolist() == ["2"]
    assert num_invalidas == 1


def test_ids_repetidos_cuentan_como_invalidos(respuesta_api):
    df = pd.concat([respuesta_api.iloc[[0, 1]], respuesta_api.iloc[[0]]], ignore_index=True)
    df_validas, num_invalidas = validar(df)
    assert df_validas["id"].tolist() == ["1", "2"]      # se queda la primera aparición
    assert num_invalidas == 1


def test_ninguna_valida_lanza_error(respuesta_api):
    with pytest.raises(ValidationError, match="Ninguna estación"):
        validar(respuesta_api.iloc[[2]])
