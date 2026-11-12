"""Construcción de las variables (features) y del objetivo del modelo.

Unidad de predicción: una fila por estación × carburante × día.

Objetivo (lo que se predice):
    variacion_manana = precio de mañana − precio de hoy   (€/l)

Se predice la VARIACIÓN y no el precio porque el precio de mañana es casi igual
al de hoy: un modelo que predijera el precio parecería muy bueno (R² ≈ 1) sin haber
aprendido nada. Con la variación, el modelo solo tiene mérito si mejora a la
predicción trivial "mañana igual que hoy" (variación = 0).

Regla de oro: cada feature del día D usa solo información disponible el día D.
"""

import pandas as pd

OBJETIVO = "variacion_manana"

# Días hacia atrás con los que se compara el precio de la estación
RETARDOS_PRECIO = (1, 3, 7)
# Días hacia atrás con los que se compara el Brent
RETARDOS_BRENT = (3, 7, 14)
# FRED publica el Brent con retraso (entre 2 y 9 días). Para no usar en el
# entrenamiento un dato que el día de la predicción aún no existe, el día D
# se usa el valor de mercado del día D − 10.
RETRASO_MERCADOS_DIAS = 10
# Una variación de más de 25 céntimos en un día no es real: es un error al cargar el
# precio (p. ej. 1,589 → 0,589). Esas filas no se usan para entrenar ni para evaluar.
MAX_VARIACION_DIARIA = 0.25

FEATURES_CATEGORICAS = ["carburante", "id_provincia", "tipo_venta"]
FEATURES_NUMERICAS = [
    "precio",                                                   # precio de hoy
    *[f"dif_precio_{k}" for k in RETARDOS_PRECIO],              # cuánto ha cambiado en 1, 3 y 7 días
    "dif_provincia",                                            # precio − media de su provincia hoy
    "var_provincia_1",                                          # cuánto cambió ayer→hoy la media de su provincia
    "var_nacional_1",                                           # cuánto cambió ayer→hoy ese carburante en toda España
    "brent_eur",                                                # barril en euros (con retraso)
    *[f"var_brent_{k}" for k in RETARDOS_BRENT],                # variación % del Brent en 3, 7 y 14 días
    "dia_semana",                                               # 0 = lunes ... 6 = domingo
    "latitud", "longitud",
]
FEATURES = FEATURES_CATEGORICAS + FEATURES_NUMERICAS

CLAVE_SERIE = ["id", "carburante"]   # cada estación × carburante es una serie temporal


def valor_desplazado(df: pd.DataFrame, columna: str, dias: int) -> pd.Series:
    """Valor de `columna` de la misma estación y carburante `dias` días antes.

    Con dias negativo devuelve el valor de días DESPUÉS (solo se usa para el objetivo).
    Si ese día exacto no está en el histórico (hueco en los datos), devuelve NaN:
    nunca se usa por error el dato de otro día.

    Requiere el DataFrame ordenado por id, carburante y fecha.
    """
    grupos = df.groupby(CLAVE_SERIE, sort=False)
    valor = grupos[columna].shift(dias)
    fecha = grupos["fecha"].shift(dias)
    dia_correcto = (df["fecha"] - fecha) == pd.Timedelta(days=dias)
    return valor.where(dia_correcto)


def mercados_con_retraso(mercados: pd.DataFrame, retraso: int = RETRASO_MERCADOS_DIAS) -> pd.DataFrame:
    """Prepara las features de mercado tal y como se conocían cada día.

    La fila del día D contiene el Brent en euros del día D − retraso y sus
    variaciones porcentuales respecto a 3, 7 y 14 días antes.
    Requiere una fila por día del calendario (lo garantiza combinar_mercados).
    """
    m = mercados[["fecha", "brent_eur"]].sort_values("fecha").reset_index(drop=True)
    for k in RETARDOS_BRENT:
        m[f"var_brent_{k}"] = (m["brent_eur"] / m["brent_eur"].shift(k) - 1) * 100
    m["fecha"] = m["fecha"] + pd.Timedelta(days=retraso)
    return m


def construir_features(largo: pd.DataFrame, mercados: pd.DataFrame) -> pd.DataFrame:
    """Añade las features y el objetivo al histórico en formato largo.

    Args:
        largo: Salida de historico.a_formato_largo (fecha, id, carburante, precio...).
        mercados: Salida de historico.cargar_mercados (fecha, brent_eur...).

    Returns:
        Copia de `largo` con las columnas FEATURES y OBJETIVO. El objetivo es NaN
        en el último día de cada serie (todavía no se conoce el precio de mañana):
        esas filas son justo las que se usan para predecir.
    """
    df = largo.sort_values([*CLAVE_SERIE, "fecha"]).reset_index(drop=True)

    # --- Historia del propio precio ---
    for k in RETARDOS_PRECIO:
        df[f"dif_precio_{k}"] = df["precio"] - valor_desplazado(df, "precio", k)

    # --- Contexto: su provincia (las estaciones cercanas se copian los precios) ---
    df["media_provincia"] = df.groupby(["fecha", "id_provincia", "carburante"])["precio"].transform("mean")
    df["dif_provincia"] = df["precio"] - df["media_provincia"]
    df["var_provincia_1"] = df["media_provincia"] - valor_desplazado(df, "media_provincia", 1)

    # --- Contexto: tendencia del día en toda España (señal más reciente que el Brent, que llega con retraso) ---
    df["var_nacional_1"] = df.groupby(["fecha", "carburante"])["dif_precio_1"].transform("mean")

    # --- Mercado: Brent en euros, con retraso de publicación ---
    df = df.merge(mercados_con_retraso(mercados), on="fecha", how="left")

    # --- Calendario ---
    df["dia_semana"] = df["fecha"].dt.dayofweek

    # --- Objetivo: precio de mañana − precio de hoy ---
    df[OBJETIVO] = valor_desplazado(df, "precio", -1) - df["precio"]

    return df.drop(columns=["media_provincia"])


def filas_entrenables(datos: pd.DataFrame) -> pd.DataFrame:
    """Filas con las que se puede entrenar y evaluar.

    Se descartan:
      - Las filas sin objetivo (último día de cada serie: no se conoce mañana).
      - Los primeros días del histórico, en los que ninguna estación tiene todavía
        una semana de historia y las features de retardo están vacías.
      - Las variaciones imposibles (más de MAX_VARIACION_DIARIA): errores de carga.
    """
    primer_dia_completo = datos["fecha"].min() + pd.Timedelta(days=max(RETARDOS_PRECIO))
    filas = datos[(datos["fecha"] >= primer_dia_completo) & (datos[OBJETIVO].abs() <= MAX_VARIACION_DIARIA)]
    return filas.reset_index(drop=True)
