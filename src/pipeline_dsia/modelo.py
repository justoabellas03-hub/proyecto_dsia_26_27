"""Modelo de predicción del precio de mañana: features, modelo scikit-learn y entrenamiento.

Secciones:
    1. Features y objetivo.
    2. Modelo: definición, validación temporal, búsqueda de hiperparámetros, evaluación y persistencia.
    3. Entrenamiento completo (ejecutar_entrenamiento) e informe del modelo.
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
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from pipeline_dsia.config import DataLoadError, ModelError, configurar_logs
from pipeline_dsia.historico import CARPETA_HISTORICO, a_formato_largo, cargar_historico, cargar_mercados

log = logging.getLogger(__name__)


# ======================================================================================
# 1. Features y objetivo
# ======================================================================================

# Construcción de las variables (features) y del objetivo del modelo.
#
# Unidad de predicción: una fila por estación × carburante × día.
#
# Objetivo (lo que se predice):
# variacion_manana = precio de mañana − precio de hoy   (€/l)
#
# Se predice la VARIACIÓN y no el precio porque el precio de mañana es casi igual
# al de hoy: un modelo que predijera el precio parecería muy bueno (R² ≈ 1) sin haber
# aprendido nada. Con la variación, el modelo solo tiene mérito si mejora a la
# predicción trivial "mañana igual que hoy" (variación = 0).
#
# Regla de oro: cada feature del día D usa solo información disponible el día D.

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


# ======================================================================================
# 2. Modelo
# ======================================================================================

# Modelo scikit-learn: definición, validación temporal, búsqueda de hiperparámetros,
# evaluación y persistencia.
#
# Modelo elegido: HistGradientBoostingRegressor (árboles de decisión con boosting).
# - Capta relaciones no lineales (p. ej. "si el Brent sube Y la estación está por
# debajo de su provincia, sube más") sin tener que programarlas a mano.
# - Acepta valores vacíos (NaN) y variables categóricas directamente.
# - Entrena rápido con millones de filas (agrupa los valores en histogramas).
#
# Se compara siempre con dos referencias:
# - Persistencia: "mañana igual que hoy" (variación = 0). Es la referencia a batir.
# - Ridge: regresión lineal regularizada, el modelo más sencillo razonable.

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
        raise ModelError(f"No existe {ruta}: ejecuta antes 'python -m pipeline_dsia entrenar'")
    try:
        return joblib.load(ruta)
    except Exception as exc:   # fichero corrupto o de otra versión de sklearn
        raise ModelError(f"No se pudo cargar {ruta}: {exc}") from exc


def cargar_metadatos(carpeta: Path = CARPETA_MODELOS) -> dict:
    ruta = Path(carpeta) / "metricas.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


# ======================================================================================
# 3. Entrenamiento completo
# ======================================================================================

# Entrenamiento reproducible del modelo de predicción del precio del día siguiente.
#
# Uso:
# python -m pipeline_dsia entrenar                          # búsqueda de hiperparámetros + entrenamiento
# python -m pipeline_dsia entrenar --sin-busqueda           # reutiliza los hiperparámetros guardados
# python -m pipeline_dsia entrenar --muestra-busqueda 1.0   # búsqueda con todas las estaciones (lento)
# python -m pipeline_dsia entrenar --help
#
# Pasos:
# 1. Cargar el histórico y construir las features.
# 2. Separar por fecha: los últimos días son el test.
# 3. Buscar hiperparámetros con validación cruzada temporal (solo con train).
# 4. Evaluar en test: persistencia, Ridge y gradient boosting.
# 5. Reentrenar con TODOS los datos y guardar models/modelo.joblib,
# models/metricas.json y models/INFORME_MODELO.md.
#
# Códigos de salida: 0 correcto · 1 datos insuficientes para entrenar · 2 no hay histórico.

MIN_DIAS = 10                 # mínimo de días útiles (con una semana de historia y objetivo conocido)
HIPERPARAMETROS_POR_DEFECTO = {"learning_rate": 0.1, "max_leaf_nodes": 31, "max_iter": 100}
FILAS_IMPORTANCIA = 20_000    # muestra del test con la que se calcula la importancia de las variables


def preparar_datos(carpeta: Path) -> pd.DataFrame:
    """Histórico → filas con features y objetivo conocido."""
    largo = a_formato_largo(cargar_historico(carpeta))
    datos = filas_entrenables(construir_features(largo, cargar_mercados(carpeta)))
    dias = datos["fecha"].nunique() if len(datos) else 0
    if dias < MIN_DIAS:
        raise ModelError(f"Solo hay {dias} días útiles para entrenar; hacen falta al menos {MIN_DIAS} "
                         f"(es decir, unos {MIN_DIAS + 8} días de histórico). "
                         "Rellena el histórico con 'python -m pipeline_dsia ingesta --desde AAAA-MM-DD'")
    return datos


def importancia_variables(modelo, test: pd.DataFrame) -> pd.DataFrame:
    """Importancia por permutación: cuánto empeora el RMSE (en céntimos) al desordenar
    una variable. Si desordenarla no cambia nada, el modelo no la está usando."""
    muestra = test.sample(min(len(test), FILAS_IMPORTANCIA), random_state=SEMILLA)
    resultado = permutation_importance(
        modelo, muestra[FEATURES], muestra[OBJETIVO],
        scoring="neg_root_mean_squared_error", n_repeats=3, random_state=SEMILLA,
    )
    tabla = pd.DataFrame({"variable": FEATURES, "aumento_rmse_cts": resultado.importances_mean * 100})
    return tabla.sort_values("aumento_rmse_cts", ascending=False).round(4).reset_index(drop=True)


def tabla_markdown(df: pd.DataFrame) -> str:
    """DataFrame → tabla en Markdown (sin depender de librerías externas)."""
    lineas = ["| " + " | ".join(str(c) for c in df.columns) + " |", "|" + " --- |" * len(df.columns)]
    lineas += ["| " + " | ".join(str(v) for v in fila) + " |" for fila in df.itertuples(index=False)]
    return "\n".join(lineas)


def escribir_informe_modelo(carpeta: Path, metadatos: dict, busqueda: pd.DataFrame | None, importancia: pd.DataFrame) -> Path:
    """Informe legible del entrenamiento: datos, hiperparámetros, métricas e importancia."""
    metricas = pd.DataFrame(metadatos["metricas_test"]).T.rename_axis("modelo").reset_index()
    gb, base = metadatos["metricas_test"]["gradient_boosting"], metadatos["metricas_test"]["persistencia"]
    mejora = (1 - gb["rmse_cts"] / base["rmse_cts"]) * 100 if base["rmse_cts"] else 0.0
    veredicto = (f"El modelo **mejora** a la persistencia un {mejora:.1f} % en RMSE."
                 if mejora > 0 else
                 f"El modelo **no mejora** a la persistencia en RMSE ({mejora:.1f} %).")

    partes = [
        "# Informe del modelo",
        f"Generado automáticamente por `python -m pipeline_dsia entrenar` el {metadatos['fecha_informe']}.",
        "## Datos",
        f"- Entrenamiento: {metadatos['train_desde']} → {metadatos['train_hasta']} ({metadatos['filas_train']:,} filas)\n"
        f"- Test: {metadatos['test_desde']} → {metadatos['test_hasta']} ({metadatos['filas_test']:,} filas)\n"
        f"- Una fila = estación × carburante × día. Objetivo: variación del precio al día siguiente (€/l).",
        "## Hiperparámetros elegidos",
        "\n".join(f"- `{k}` = {v}" for k, v in metadatos["hiperparametros"].items()),
    ]
    if busqueda is not None:
        partes += ["### Búsqueda (validación cruzada temporal, RMSE medio en céntimos)", tabla_markdown(busqueda)]
    partes += [
        "## Métricas en test (céntimos de €/l)",
        tabla_markdown(metricas),
        veredicto,
        "- `mae_cts`: error medio absoluto. `rmse_cts`: castiga más los errores grandes.\n"
        "- `acierto_direccion`: % de aciertos de subida/bajada cuando el precio cambió.\n"
        "- En MAE la persistencia es muy difícil de batir: la mayoría de los días el precio no cambia, "
        "así que predecir 0 acierta de pleno casi siempre. El modelo se entrena para reducir el error "
        "cuadrático, es decir, para fallar menos los días en que el precio sí se mueve.",
        "## Importancia de las variables",
        "Aumento del RMSE (céntimos) al desordenar cada variable en el test:",
        tabla_markdown(importancia),
    ]
    ruta = Path(carpeta) / "INFORME_MODELO.md"
    ruta.write_text("\n\n".join(partes) + "\n", encoding="utf-8")
    return ruta


def ejecutar_entrenamiento(carpeta: Path = CARPETA_HISTORICO, modelos: Path = CARPETA_MODELOS,
                           fraccion_test: float = 0.2, muestra_busqueda: float = 0.2,
                           sin_busqueda: bool = False) -> int:
    """Entrena, evalúa y guarda el modelo (pasos 1-5 de arriba).

    Códigos de salida: 0 correcto · 1 datos insuficientes para entrenar · 2 no hay histórico.
    """
    configurar_logs("entrenar")

    # 1. Datos
    try:
        datos = preparar_datos(carpeta)
    except DataLoadError as exc:
        log.error("No se pudo cargar el histórico: %s", exc)
        return 2
    except ModelError as exc:
        log.error("%s", exc)
        return 1
    log.info("Datos: %d filas, %d días, %d estaciones", len(datos), datos["fecha"].nunique(), datos["id"].nunique())

    try:
        # 2. Separación temporal
        train, test = separar_train_test(datos, fraccion_test)
        log.info("Train: %d filas (hasta %s) · Test: %d filas (desde %s)",
                 len(train), train["fecha"].max().date(), len(test), test["fecha"].min().date())

        # 3. Hiperparámetros
        tabla_busqueda = None
        if sin_busqueda:
            hiper = cargar_metadatos(modelos).get("hiperparametros", HIPERPARAMETROS_POR_DEFECTO)
            log.info("Sin búsqueda. Hiperparámetros: %s", hiper)
        else:
            log.info("Buscando hiperparámetros (%d combinaciones)...", len(pd.MultiIndex.from_product(REJILLA.values())))
            hiper, tabla_busqueda = buscar_hiperparametros(train, fraccion_estaciones=muestra_busqueda)
            log.info("Mejores hiperparámetros: %s", hiper)

        # 4. Evaluación en test
        modelo, metricas = evaluar_modelos(train, test, hiper)
    except ModelError as exc:
        log.error("%s", exc)
        return 1
    for nombre, valores in metricas.items():
        log.info("Test · %-18s %s", nombre, valores)
    importancia = importancia_variables(modelo, test)

    # 5. Modelo final con todos los datos (los días más recientes son los más útiles)
    modelo_final = crear_modelo(**hiper).fit(datos[FEATURES], datos[OBJETIVO])
    metadatos = {
        "hiperparametros": hiper,
        "metricas_test": metricas,
        "train_desde": str(train["fecha"].min().date()), "train_hasta": str(train["fecha"].max().date()),
        "test_desde": str(test["fecha"].min().date()), "test_hasta": str(test["fecha"].max().date()),
        "filas_train": len(train), "filas_test": len(test),
        "fecha_informe": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}",
    }
    guardar_modelo(modelo_final, metadatos, modelos)
    informe = escribir_informe_modelo(modelos, metadatos, tabla_busqueda, importancia)
    log.info("Informe guardado en %s", informe)
    return 0
