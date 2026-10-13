
import json
 
import pandas as pd
import requests
 
from pipeline_dsia.exceptions import DataLoadError
 
 
def cargar_datos(url, clave="ListaEESSPrecio"):
    """Descarga los datos de una API que devuelve JSON y los pasa a DataFrame.
 
    Args:
        url: Dirección de la API.
        clave: Clave del JSON donde está la lista de registros.
    """
    try:
        respuesta = requests.get(url, headers={"Accept": "application/json"}, timeout=60)
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise DataLoadError(f"No se pudo descargar {url}: {exc}") from exc
    datos = json.loads(respuesta.content.decode("utf-8-sig"))
    return pd.DataFrame(datos[clave])#La APIno devuelve solo el df si no un diccionario con varias cosas dentro
 
