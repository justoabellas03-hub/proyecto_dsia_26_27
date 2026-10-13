import pandas as pd

from pipeline_dsia.contracts import CAMPOS_PRECIO


# --- Funciones base ----------------------------------------------------------

def media_carburante(df: pd.DataFrame, carburante: str, agrupar_por: str | None = None):
    """Precio medio de un carburante.

    Args:
        df: Estaciones.
        carburante: Columna de precio (p. ej. "gasoleo_a").
        agrupar_por: Columna por la que agrupar (p. ej. "id_provincia").

    Returns:
        - Sin agrupar: un número, la media de todas las estaciones.
        - Agrupando: una Serie con la media del grupo de cada estación,
          alineada fila a fila con df.
    Las estaciones que no venden el carburante (NaN) no cuentan.
    """
    if agrupar_por is None:
        return df[carburante].mean()
    return df.groupby(agrupar_por)[carburante].transform("mean")


def media_gasolinera(df: pd.DataFrame, columnas: list[str]) -> pd.Series:
    """Media de varias columnas en cada fila (una por gasolinera).

    Ignora los NaN: una gasolinera que no vende un carburante se promedia
    solo con los que sí vende.
    """
    return df[columnas].mean(axis=1)


# --- Métricas ----------------------------------------------------------------

def precio_medio_por_provincia(df: pd.DataFrame) -> pd.DataFrame:
    """Precio medio de cada carburante por provincia y media de todos ellos.

    Devuelve una fila por provincia, una columna por carburante y la columna
    "media_carburantes" (media de las medias de cada carburante).
    """
    tabla = df[["id_provincia", "provincia"]].copy()
    for carburante in CAMPOS_PRECIO:
        tabla[carburante] = media_carburante(df, carburante, "id_provincia")

    tabla = tabla.drop_duplicates("id_provincia")
    tabla["media_carburantes"] = media_gasolinera(tabla, list(CAMPOS_PRECIO))
    return tabla.sort_values("id_provincia").round(3).reset_index(drop=True)


def comparar_con_provincia(df: pd.DataFrame) -> pd.DataFrame:
    """Compara los precios de cada estación con la media de su provincia.

    Añade a una copia del DataFrame:
      - media_prov_<carburante>: precio medio de ese carburante en la
        provincia de la estación (€/l).
      - dif_<carburante>: precio de la estación menos la media de ese
        carburante en su provincia (€/l). Negativo = más barata que la media.
      - dif_media: media de las diferencias anteriores. Indica si la
        estación es, en conjunto, más cara o más barata que su provincia.
    """
    resultado = df.copy()
    columnas_nuevas, columnas_dif = [], []
    for carburante in CAMPOS_PRECIO:
        media = f"media_prov_{carburante}"
        dif = f"dif_{carburante}"
        resultado[media] = media_carburante(df, carburante, "id_provincia")
        resultado[dif] = resultado[carburante] - resultado[media]
        columnas_nuevas += [media, dif]
        columnas_dif.append(dif)

    resultado["dif_media"] = media_gasolinera(resultado, columnas_dif)
    columnas_nuevas.append("dif_media")
    resultado[columnas_nuevas] = resultado[columnas_nuevas].round(3)
    return resultado


def mas_baratas(df: pd.DataFrame, n: int, solo_publicas: bool = True) -> pd.DataFrame:
    """Las n gasolineras más baratas de España teniendo en cuenta todos sus carburantes.

    Para cada estación se calcula "dif_nacional": la media de las diferencias
    entre cada uno de sus precios y la media nacional de ese carburante (€/l).
    Así se comparan estaciones que venden carburantes distintos de forma justa.

    Args:
        df: Estaciones válidas.
        n: Número de gasolineras a devolver.
        solo_publicas: Si es True, excluye las estaciones de venta restringida.

    Raises:
        ValueError: Si n no es positivo.
    """
    if n <= 0:
        raise ValueError("n debe ser mayor que 0")

    estaciones = df.copy()
    columnas_dif = []
    for carburante in CAMPOS_PRECIO:
        columna = f"dif_{carburante}"
        estaciones[columna] = estaciones[carburante] - media_carburante(df, carburante)
        columnas_dif.append(columna)
    estaciones["dif_nacional"] = media_gasolinera(estaciones, columnas_dif)

    if solo_publicas:
        estaciones = estaciones[estaciones["tipo_venta"] == "P"]

    columnas = ["rotulo", "direccion", "municipio", "provincia", *CAMPOS_PRECIO, "dif_nacional"]
    return estaciones.nsmallest(n, "dif_nacional")[columnas].round(3).reset_index(drop=True)


def precio_medio_por_marca(df: pd.DataFrame, min_estaciones: int = 20) -> pd.DataFrame:
    """Precio medio de cada carburante por marca (rótulo).

    Incluye "dif_media": cuánto más cara (+) o más barata (-) es de media la
    marca respecto a la media de la provincia de cada una de sus estaciones.
    Permite comparar marcas de forma justa, sin que influya qué carburantes
    venden ni en qué provincias están. Se ordena por ella, de más barata a más cara.

    Solo incluye marcas con al menos min_estaciones gasolineras.
    """
    marcas = comparar_con_provincia(df).dropna(subset=["rotulo"])
    marcas["rotulo"] = marcas["rotulo"].str.upper().str.strip()

    tabla = marcas[["rotulo"]].copy()
    for carburante in CAMPOS_PRECIO:
        tabla[carburante] = media_carburante(marcas, carburante, "rotulo")
    tabla["dif_media"] = media_carburante(marcas, "dif_media", "rotulo")
    tabla["num_estaciones"] = marcas.groupby("rotulo")["rotulo"].transform("size")

    tabla = tabla.drop_duplicates("rotulo")
    tabla = tabla[tabla["num_estaciones"] >= min_estaciones]
    return tabla.sort_values("dif_media").round(3).reset_index(drop=True)



def diferencia_gasolina_gasoleo(df: pd.DataFrame) -> pd.DataFrame:
    """Añade a cada gasolinera la diferencia entre gasolina 95 y gasóleo A.

    Añade a una copia del DataFrame la columna "dif_gasolina_gasoleo"
    (€/l): positiva si la gasolina es más cara que el gasóleo. Es NaN en las
    estaciones que no venden alguno de los dos.
    """
    resultado = df.copy()
    resultado["dif_gasolina_gasoleo"] = (resultado["gasolina_95"] - resultado["gasoleo_a"]).round(3)
    return resultado


def media_diferencia_gasolina_gasoleo(df: pd.DataFrame) -> float:
    """Diferencia media entre gasolina 95 y gasóleo A en España (€/l).

    Solo cuentan las estaciones que venden los dos carburantes.
    """
    con_diferencia = diferencia_gasolina_gasoleo(df)
    return round(float(media_carburante(con_diferencia, "dif_gasolina_gasoleo")), 3)
