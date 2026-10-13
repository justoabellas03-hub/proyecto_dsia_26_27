import pandas as pd
from pydantic import ValidationError as PydanticValidationError
 
from pipeline_dsia.constants import COORDENADAS, PRECIOS
from pipeline_dsia.contracts import Estacion
from pipeline_dsia.exceptions import ValidationError
 
 
def normalizar_numeros(df: pd.DataFrame) -> pd.DataFrame:
    #Devuelve una copia del df corrigiendo los valores numéricos cambiando el valor con una coma por el valor con un 
    resultado = df.copy()
    for col in (*PRECIOS, *COORDENADAS):
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
            estacion_valida=Estacion(fila)
            validas.append(fila)
        except PydanticValidationError:
            num_invalidas += 1
 
    if not validas:
        raise ValidationError("Ninguna estación supera el contrato")
 
    # Lista de objetos Estacion → lista de diccionarios → DataFrame
    df_validas = pd.DataFrame([estacion.model_dump() for estacion in validas])
 
    # Regla de conjunto (el contrato valida fila a fila y no puede verla)
    duplicadas = df_validas["id"].duplicated(keep="first")
    num_invalidas += int(duplicadas.sum())
    df_validas = df_validas[~duplicadas].reset_index(drop=True)
 
    return df_validas, num_invalidas
 