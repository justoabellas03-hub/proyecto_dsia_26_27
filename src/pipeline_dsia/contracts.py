from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator, Field


from pipeline_dsia.constants import (
    LATITUD_MAX, LATITUD_MIN, LONGITUD_MAX, LONGITUD_MIN, PRECIO_MAX, PRECIO_MIN,
)
CAMPOS_PRECIO=("gasolina_95", "gasolina_98", "gasoleo_a", "gasoleo_premium")

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
        precios = (self.gasolina_95, self.gasolina_98, self.gasoleo_a, self.gasoleo_premium)
        if all(getattr(self, campo) is None for campo in CAMPOS_PRECIO):
            raise ValueError("no vende ninguno de los carburantes analizados")
        return self