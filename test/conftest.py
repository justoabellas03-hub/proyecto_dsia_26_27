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
