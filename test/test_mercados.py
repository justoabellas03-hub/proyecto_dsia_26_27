"""Tests de Brent y EUR/USD, sin conexión: se usan CSV escritos a mano."""

import pandas as pd
import pytest

from pipeline_dsia.exceptions import DataLoadError
from pipeline_dsia.mercados import combinar_mercados, leer_brent, leer_eurusd

# Formato real de FRED: los festivos vienen con el valor vacío
CSV_BRENT = """observation_date,DCOILBRENTEU
2026-11-05,80.00
2026-11-06,82.00
2026-11-09,
2026-11-10,84.00
"""

# Formato real del BCE (resumido): muchas columnas, nos interesan TIME_PERIOD y OBS_VALUE
CSV_EURUSD = """KEY,FREQ,CURRENCY,TIME_PERIOD,OBS_VALUE,OBS_STATUS
EXR.D.USD.EUR.SP00.A,D,USD,2026-11-05,1.10,A
EXR.D.USD.EUR.SP00.A,D,USD,2026-11-06,1.12,A
EXR.D.USD.EUR.SP00.A,D,USD,2026-11-09,1.12,A
EXR.D.USD.EUR.SP00.A,D,USD,2026-11-10,1.05,A
"""


def test_leer_brent_quita_festivos():
    brent = leer_brent(CSV_BRENT)
    assert list(brent.columns) == ["fecha", "brent_usd"]
    assert len(brent) == 3                                  # el 09-11 venía vacío
    assert brent["fecha"].dtype.kind == "M"


def test_leer_brent_columnas_inesperadas():
    with pytest.raises(DataLoadError):
        leer_brent("fecha,precio\n2026-11-05,80\n")


def test_leer_eurusd():
    eurusd = leer_eurusd(CSV_EURUSD)
    assert list(eurusd.columns) == ["fecha", "eurusd"]
    assert eurusd["eurusd"].tolist() == pytest.approx([1.10, 1.12, 1.12, 1.05])


def test_leer_eurusd_columnas_inesperadas():
    with pytest.raises(DataLoadError):
        leer_eurusd("a,b\n1,2\n")


def test_combinar_rellena_todos_los_dias_hacia_delante():
    df = combinar_mercados(leer_brent(CSV_BRENT), leer_eurusd(CSV_EURUSD)).set_index("fecha")

    assert len(df) == 6                                     # del 05-11 al 10-11, fin de semana incluido
    # Sábado, domingo y el festivo del Brent usan el último valor conocido (viernes)
    for dia in ["2026-11-07", "2026-11-08", "2026-11-09"]:
        assert df.loc[dia, "brent_usd"] == pytest.approx(82.0)
    assert df.loc["2026-11-05", "brent_eur"] == pytest.approx(80 / 1.10, abs=1e-3)
    assert df.loc["2026-11-10", "brent_eur"] == pytest.approx(84 / 1.05, abs=1e-3)


def test_combinar_no_usa_informacion_del_futuro():
    brent = pd.DataFrame({"fecha": pd.to_datetime(["2026-11-03", "2026-11-05"]), "brent_usd": [70.0, 90.0]})
    eurusd = pd.DataFrame({"fecha": pd.to_datetime(["2026-11-03"]), "eurusd": [1.0]})
    df = combinar_mercados(brent, eurusd).set_index("fecha")
    assert df.loc["2026-11-04", "brent_usd"] == 70.0        # no se adelanta el 90 del día 5
