"""Validación de las estaciones: contrato de datos (pydantic) y limpieza de la respuesta de la API."""

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from pipeline_dsia.config import (
    CAMPOS_PRECIOS, COORDENADAS, LATITUD_MAX, LATITUD_MIN, LONGITUD_MAX, LONGITUD_MIN, PRECIO_MAX,
    PRECIO_MIN, ValidationError,
)


# ======================================================================================
# Contrato de una estación
# ======================================================================================

CAMPOS_PRECIO = ("gasolina_95", "gasolina_98", "gasoleo_a", "gasoleo_premium")


class Estacion(BaseModel):


    model_config = ConfigDict(extra="ignore", populate_by_name=True) #Crear alias para establecer nombre de las columnas válidos para python

    id: str = Field(alias="IDEESS", pattern=r"^\d+$")
    rotulo: str | None = Field(default=None, alias="Rótulo")
    tipo_venta: Literal["P", "R"] = Field(alias="Tipo Venta")

    direccion: str | None = Field(default=None, alias="Dirección")
    codigo_postal: str | None = Field(default=None, alias="C.P.", pattern=r"^\d{5}$")
    municipio: str = Field(alias="Municipio")
    provincia: str = Field(alias="Provincia")
    id_municipio: str = Field(alias="IDMunicipio", pattern=r"^\d+$")
    id_provincia: str = Field(alias="IDProvincia", pattern=r"^\d{2}$")
    id_ccaa: str = Field(alias="IDCCAA", pattern=r"^\d{2}$")
    latitud: float = Field(alias="Latitud", ge=LATITUD_MIN, le=LATITUD_MAX)
    longitud: float = Field(alias="Longitud (WGS84)", ge=LONGITUD_MIN, le=LONGITUD_MAX)

    gasolina_95: float | None = Field(default=None, alias="Precio Gasolina 95 E5", ge=PRECIO_MIN, le=PRECIO_MAX)
    gasolina_98: float | None = Field(default=None, alias="Precio Gasolina 98 E5", ge=PRECIO_MIN, le=PRECIO_MAX)
    gasoleo_a: float | None = Field(default=None, alias="Precio Gasoleo A", ge=PRECIO_MIN, le=PRECIO_MAX)
    gasoleo_premium: float | None = Field(default=None, alias="Precio Gasoleo Premium", ge=PRECIO_MIN, le=PRECIO_MAX)

    @field_validator("*", mode="before")
    @classmethod
    def vacio_a_none(cls, valor):
        ##Quita espacios y convierte las cadenas vacías en None (en todos los campos)
        if isinstance(valor, str):
            valor = valor.strip()
            if valor == "":
                return None
        return valor

    @model_validator(mode="after")
    def vende_algun_carburante(self):
        """La estación debe vender al menos uno de los carburantes analizados."""
        if all(getattr(self, campo) is None for campo in CAMPOS_PRECIO):
            raise ValueError("no vende ninguno de los carburantes analizados")
        return self


# ======================================================================================
# Validación del DataFrame
# ======================================================================================


def normalizar_numeros(df: pd.DataFrame) -> pd.DataFrame:
    #Devuelve una copia del df corrigiendo los valores numéricos cambiando el valor con una coma por el valor con un
    resultado = df.copy()
    for col in (*CAMPOS_PRECIOS, *COORDENADAS):
        resultado[col] = resultado[col].str.replace(",", ".", regex=False)
    return resultado


def validar_estaciones(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Pasa cada fila por el contrato y se queda con las estaciones válidas.

    Devuelve:
        (df_validas, num_invalidas).
        - df_validas: DataFrame con los nombres del contrato (gasolina_95, latitud...)
          y los tipos ya convertidos.
        - num_invalidas: cuántas estaciones se han descartado (no cumplen el
          contrato o tienen el IDEESS repetido).

    Salta:
        ValidationError: Si no hay ninguna estación válida.
    """
    validas= []
    num_invalidas = 0

    for fila in df.to_dict(orient="records"):
        try:
            estacion_valida=Estacion(**fila)
            validas.append(estacion_valida)
        except PydanticValidationError:
            num_invalidas += 1

    if not validas:
        raise ValidationError("Ninguna estación supera el contrato")

    # Lista de objetos Estacion → lista de diccionarios → DataFrame
    df_validas = pd.DataFrame([estacion.model_dump() for estacion in validas])
    # Si nadie vende un carburante, pandas dejaría la columna como texto (None); la forzamos a número
    df_validas[list(CAMPOS_PRECIO)] = df_validas[list(CAMPOS_PRECIO)].astype(float)

    # Regla de conjunto (el contrato valida fila a fila y no puede verla)
    duplicadas = df_validas["id"].duplicated(keep="first")
    num_invalidas += int(duplicadas.sum())
    df_validas = df_validas[~duplicadas].reset_index(drop=True)

    return df_validas, num_invalidas
