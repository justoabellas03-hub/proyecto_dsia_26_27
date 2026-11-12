"""Datos de prueba compartidos por los tests."""

import pandas as pd
import pytest

NAN = float("nan")


@pytest.fixture
def estaciones() -> pd.DataFrame:
    """Cinco estaciones válidas inventadas, con resultados fáciles de calcular a mano.

    | id | provincia | venta | rótulo   | g95  | g98  | gasóleo A |
    |----|-----------|-------|----------|------|------|-----------|
    | 1  | MADRID    | P     | Repsol   | 1.60 | 1.80 | 1.45      |
    | 2  | MADRID    | P     | REPSOL   | 1.50 | -    | 1.40      |
    | 3  | MADRID    | R     | Coop     | -    | -    | 1.20      |
    | 4  | ALBACETE  | P     | Plenoil  | 1.40 | -    | 1.30      |
    | 5  | ALBACETE  | P     | Plenoil  | 1.44 | -    | 1.34      |

    Nadie vende gasóleo premium.
    """
    return pd.DataFrame({
        "id": ["1", "2", "3", "4", "5"],
        "rotulo": ["Repsol", "REPSOL ", "Coop", "Plenoil", "Plenoil"],
        "tipo_venta": ["P", "P", "R", "P", "P"],
        "direccion": ["Calle A", "Calle B", "Calle C", "Calle D", "Calle E"],
        "municipio": ["Madrid", "Getafe", "Madrid", "Albacete", "Hellín"],
        "provincia": ["MADRID", "MADRID", "MADRID", "ALBACETE", "ALBACETE"],
        "id_provincia": ["28", "28", "28", "02", "02"],
        "gasolina_95": [1.60, 1.50, NAN, 1.40, 1.44],
        "gasolina_98": [1.80, NAN, NAN, NAN, NAN],
        "gasoleo_a": [1.45, 1.40, 1.20, 1.30, 1.34],
        "gasoleo_premium": [NAN, NAN, NAN, NAN, NAN],
    })


@pytest.fixture
def respuesta_api() -> pd.DataFrame:
    """Respuesta cruda de la API (texto y coma decimal): dos estaciones válidas y una inválida."""
    base = {
        "IDEESS": "1", "Rótulo": "REPSOL", "Tipo Venta": "P", "Dirección": "Calle A",
        "C.P.": "28001", "Municipio": "Madrid", "Provincia": "MADRID",
        "IDMunicipio": "4354", "IDProvincia": "28", "IDCCAA": "13",
        "Latitud": "40,416775", "Longitud (WGS84)": "-3,703790",
        "Precio Gasolina 95 E5": "1,599", "Precio Gasolina 98 E5": "",
        "Precio Gasoleo A": "1,459", "Precio Gasoleo Premium": "",
    }
    otra = {**base, "IDEESS": "2", "Rótulo": "PLENOIL", "Precio Gasoleo A": "1,399"}
    invalida = {**base, "IDEESS": "3", "Precio Gasolina 95 E5": "", "Precio Gasoleo A": ""}
    return pd.DataFrame([base, otra, invalida])


def crear_historico_sintetico(carpeta, n_estaciones: int = 30, n_dias: int = 45, semilla: int = 0):
    """Escribe en `carpeta` un histórico inventado pero realista, para probar el modelo sin red.

    Los precios siguen al Brent en euros de 12 días antes y solo se actualizan
    algunos días (como en la realidad: la mayoría de días el precio no cambia).
    """
    import numpy as np

    from pipeline_dsia.historico import guardar_dia, guardar_mercados

    rng = np.random.default_rng(semilla)
    fechas = pd.date_range(end="2026-11-10", periods=n_dias, freq="D")
    calendario = pd.date_range(fechas[0] - pd.Timedelta(days=40), fechas[-1], freq="D")
    brent_eur = np.empty(len(calendario))                 # oscila alrededor de 70 €/barril
    brent_eur[0] = 70.0
    for i in range(1, len(calendario)):
        brent_eur[i] = 70 + 0.9 * (brent_eur[i - 1] - 70) + rng.normal(0, 1.5)
    mercados = pd.DataFrame({"fecha": calendario, "brent_usd": brent_eur * 1.1, "eurusd": 1.1,
                             "brent_eur": brent_eur.round(3)})
    guardar_mercados(mercados, carpeta)
    brent = mercados.set_index("fecha")["brent_eur"]

    margen = rng.normal(0, 0.03, n_estaciones)            # cada estación es algo más cara o más barata
    precio = np.full(n_estaciones, np.nan)
    for fecha in fechas:
        objetivo = 0.75 + 0.01 * brent[fecha - pd.Timedelta(days=12)] + margen
        actualiza = np.isnan(precio) | (rng.random(n_estaciones) < 0.35)
        precio = np.where(actualiza, objetivo, precio).round(3)
        dia = pd.DataFrame({
            "id": [str(i) for i in range(1, n_estaciones + 1)],
            "rotulo": "MARCA", "tipo_venta": "P", "municipio": "Municipio", "provincia": "PROVINCIA",
            "id_municipio": "1", "id_provincia": ["28" if i % 2 else "08" for i in range(n_estaciones)],
            "id_ccaa": "13", "latitud": 40.0 + margen, "longitud": -3.0 + margen,
            "gasolina_95": precio + 0.10, "gasolina_98": NAN, "gasoleo_a": precio, "gasoleo_premium": NAN,
        })
        guardar_dia(dia, fecha.date(), carpeta)
    return carpeta


@pytest.fixture(scope="session")
def historico_sintetico(tmp_path_factory):
    """Carpeta con 45 días de histórico inventado (se crea una sola vez para todos los tests)."""
    return crear_historico_sintetico(tmp_path_factory.mktemp("historico"))
