"""Modelo scikit-learn: definición, validación temporal, búsqueda de hiperparámetros,
evaluación y persistencia.

Modelo elegido: HistGradientBoostingRegressor (árboles de decisión con boosting).
  - Capta relaciones no lineales (p. ej. "si el Brent sube Y la estación está por
    debajo de su provincia, sube más") sin tener que programarlas a mano.
  - Acepta valores vacíos (NaN) y variables categóricas directamente.
  - Entrena rápido con millones de filas (agrupa los valores en histogramas).

Se compara siempre con dos referencias:
  - Persistencia: "mañana igual que hoy" (variación = 0). Es la referencia a batir.
  - Ridge: regresión lineal regularizada, el modelo más sencillo razonable.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from pipeline_dsia.exceptions import ModelError
from pipeline_dsia.features import FEATURES, FEATURES_CATEGORICAS, FEATURES_NUMERICAS, OBJETIVO

log = logging.getLogger(__name__)

CARPETA_MODELOS = Path("models")
SEMILLA = 42

# Hiperparámetros que se prueban (2 × 2 × 2 = 8 combinaciones)
REJILLA = {
    "modelo__learning_rate": [0.05, 0.1],     # cuánto corrige cada árbol: bajo = más lento pero más estable
    "modelo__max_leaf_nodes": [15, 31],       # complejidad de cada árbol (número de hojas)
    "modelo__max_iter": [100, 300],           # número de árboles
}
# Hiperparámetros fijos
MIN_MUESTRAS_HOJA = 50      # cada hoja necesita 50 filas: evita reglas basadas en casos aislados
REGULARIZACION_L2 = 1.0     # penaliza predicciones extremas


# --- Definición de los modelos -----------------------------------------------------

def crear_modelo(**hiperparametros) -> Pipeline:
    """Pipeline: codificar categóricas → gradient boosting.

    Las categóricas (carburante, provincia, tipo de venta) se pasan a números
    enteros con OrdinalEncoder y se le indica al modelo que son categorías (no
    cantidades). Una categoría nunca vista en el entrenamiento se trata como "desconocida".
    """
    preproceso = ColumnTransformer([
        ("categoricas", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan),
         FEATURES_CATEGORICAS),
        ("numericas", "passthrough", FEATURES_NUMERICAS),
    ])
    modelo = HistGradientBoostingRegressor(
        loss="squared_error",
        categorical_features=list(range(len(FEATURES_CATEGORICAS))),   # las primeras columnas tras el preproceso
        min_samples_leaf=MIN_MUESTRAS_HOJA,
        l2_regularization=REGULARIZACION_L2,
        early_stopping=False,
        random_state=SEMILLA,
        **hiperparametros,
    )
    return Pipeline([("preproceso", preproceso), ("modelo", modelo)])


def crear_modelo_lineal() -> Pipeline:
    """Referencia lineal: one-hot + imputación + escalado → Ridge."""
    numericas = Pipeline([("imputar", SimpleImputer(strategy="median")), ("escalar", StandardScaler())])
    preproceso = ColumnTransformer([
        ("categoricas", OneHotEncoder(handle_unknown="ignore"), FEATURES_CATEGORICAS),
        ("numericas", numericas, FEATURES_NUMERICAS),
    ])
    return Pipeline([("preproceso", preproceso), ("modelo", Ridge(alpha=1.0))])


# --- Validación temporal ------------------------------------------------------------

def separar_train_test(df: pd.DataFrame, fraccion_test: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Los últimos días son el test; todos los anteriores, el entrenamiento.

    Nunca se mezclan al azar: el modelo se evalúa siempre con días posteriores
    a los que ha visto, igual que se usará en la realidad.
    """
    fechas = np.sort(df["fecha"].unique())
    n_test = max(1, int(round(len(fechas) * fraccion_test)))
    if len(fechas) - n_test < 1:
        raise ModelError("No hay días suficientes para separar entrenamiento y test")
    corte = fechas[-n_test]
    return df[df["fecha"] < corte], df[df["fecha"] >= corte]


def particiones_temporales(fechas: pd.Series, n_particiones: int = 3) -> list[tuple[np.ndarray, np.ndarray]]:
    """Validación cruzada temporal con ventana creciente, cortando por DÍAS.

    Con 4 bloques de días (n_particiones = 3):
        partición 1: entrena con bloque 1       → valida con bloque 2
        partición 2: entrena con bloques 1-2    → valida con bloque 3
        partición 3: entrena con bloques 1-3    → valida con bloque 4

    No se usa TimeSeriesSplit de sklearn porque corta por número de fila y aquí
    hay miles de filas con la misma fecha: un mismo día quedaría partido entre
    entrenamiento y validación.

    Returns:
        Lista de (índices de entrenamiento, índices de validación) como posiciones.
    """
    dias = np.sort(fechas.unique())
    if len(dias) < n_particiones + 1:
        raise ModelError(f"Hacen falta al menos {n_particiones + 1} días para la validación cruzada; hay {len(dias)}")
    bloques = np.array_split(dias, n_particiones + 1)
    valores = fechas.to_numpy()
    particiones = []
    for i in range(1, n_particiones + 1):
        entrenamiento = np.flatnonzero(valores < bloques[i][0])
        validacion = np.flatnonzero(np.isin(valores, bloques[i]))
        particiones.append((entrenamiento, validacion))
    return particiones


# --- Entrenamiento -------------------------------------------------------------------

def buscar_hiperparametros(train: pd.DataFrame, rejilla: dict = REJILLA, n_particiones: int = 3,
                           fraccion_estaciones: float = 1.0) -> tuple[dict, pd.DataFrame]:
    """Prueba todas las combinaciones de la rejilla con validación cruzada temporal.

    Args:
        fraccion_estaciones: Para ir más rápido, la búsqueda puede hacerse con una
            muestra aleatoria de estaciones (se conservan todas sus fechas).

    Returns:
        (mejores hiperparámetros, tabla con el RMSE medio de cada combinación).
    """
    if fraccion_estaciones < 1.0:
        ids = pd.Series(train["id"].unique())
        muestra = ids.sample(frac=fraccion_estaciones, random_state=SEMILLA)
        train = train[train["id"].isin(muestra)]
    train = train.reset_index(drop=True)

    busqueda = GridSearchCV(
        crear_modelo(), rejilla,
        cv=particiones_temporales(train["fecha"], n_particiones),
        scoring="neg_root_mean_squared_error",
        refit=False,
    )
    busqueda.fit(train[FEATURES], train[OBJETIVO])

    tabla = pd.DataFrame(busqueda.cv_results_["params"])
    tabla.columns = [c.removeprefix("modelo__") for c in tabla.columns]
    tabla["rmse_validacion_cts"] = -busqueda.cv_results_["mean_test_score"] * 100
    tabla = tabla.sort_values("rmse_validacion_cts").round(4).reset_index(drop=True)

    mejores = {k.removeprefix("modelo__"): v for k, v in busqueda.best_params_.items()}
    return mejores, tabla


# --- Evaluación ------------------------------------------------------------------------

def calcular_metricas(real: pd.Series, prediccion: np.ndarray) -> dict:
    """Métricas en céntimos de euro por litro.

    - mae_cts: error medio en valor absoluto.
    - rmse_cts: como el MAE pero castiga más los errores grandes.
    - acierto_direccion: de las veces que el precio SÍ cambió, en qué porcentaje
      se acertó si subía o bajaba. La persistencia siempre saca 0 aquí.
    """
    real = np.asarray(real, dtype=float)
    prediccion = np.asarray(prediccion, dtype=float)
    cambia = real != 0
    acierto = float(np.mean(np.sign(prediccion[cambia]) == np.sign(real[cambia])) * 100) if cambia.any() else float("nan")
    return {
        "mae_cts": round(float(mean_absolute_error(real, prediccion)) * 100, 4),
        "rmse_cts": round(float(root_mean_squared_error(real, prediccion)) * 100, 4),
        "acierto_direccion": round(acierto, 1),
    }


def evaluar_modelos(train: pd.DataFrame, test: pd.DataFrame, hiperparametros: dict) -> tuple[Pipeline, dict]:
    """Entrena con train y evalúa en test la persistencia, Ridge y el gradient boosting.

    Returns:
        (modelo de gradient boosting entrenado con train, métricas de los tres).
    """
    metricas = {"persistencia": calcular_metricas(test[OBJETIVO], np.zeros(len(test)))}

    lineal = crear_modelo_lineal().fit(train[FEATURES], train[OBJETIVO])
    metricas["ridge"] = calcular_metricas(test[OBJETIVO], lineal.predict(test[FEATURES]))

    modelo = crear_modelo(**hiperparametros).fit(train[FEATURES], train[OBJETIVO])
    metricas["gradient_boosting"] = calcular_metricas(test[OBJETIVO], modelo.predict(test[FEATURES]))
    return modelo, metricas


# --- Persistencia ----------------------------------------------------------------------

def guardar_modelo(modelo: Pipeline, metadatos: dict, carpeta: Path = CARPETA_MODELOS) -> Path:
    """Guarda el modelo (joblib) y sus metadatos (JSON legible) uno al lado del otro."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "modelo.joblib"
    joblib.dump(modelo, ruta, compress=3)
    metadatos = {
        "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
        "version_sklearn": sklearn.__version__,
        "features": FEATURES,
        "objetivo": OBJETIVO,
        **metadatos,
    }
    (carpeta / "metricas.json").write_text(json.dumps(metadatos, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Modelo guardado en %s", ruta)
    return ruta


def cargar_modelo(carpeta: Path = CARPETA_MODELOS) -> Pipeline:
    ruta = Path(carpeta) / "modelo.joblib"
    if not ruta.exists():
        raise ModelError(f"No existe {ruta}: ejecuta antes 'python -m pipeline_dsia.entrenar'")
    try:
        return joblib.load(ruta)
    except Exception as exc:   # fichero corrupto o de otra versión de sklearn
        raise ModelError(f"No se pudo cargar {ruta}: {exc}") from exc


def cargar_metadatos(carpeta: Path = CARPETA_MODELOS) -> dict:
    ruta = Path(carpeta) / "metricas.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
