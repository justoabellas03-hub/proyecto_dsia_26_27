"""Entrenamiento reproducible del modelo de predicción del precio del día siguiente.

Uso:
    python -m pipeline_dsia.entrenar                          # búsqueda de hiperparámetros + entrenamiento
    python -m pipeline_dsia.entrenar --sin-busqueda           # reutiliza los hiperparámetros guardados
    python -m pipeline_dsia.entrenar --muestra-busqueda 1.0   # búsqueda con todas las estaciones (lento)
    python -m pipeline_dsia.entrenar --help

Pasos:
    1. Cargar el histórico y construir las features.
    2. Separar por fecha: los últimos días son el test.
    3. Buscar hiperparámetros con validación cruzada temporal (solo con train).
    4. Evaluar en test: persistencia, Ridge y gradient boosting.
    5. Reentrenar con TODOS los datos y guardar models/modelo.joblib,
       models/metricas.json y models/INFORME_MODELO.md.

Códigos de salida: 0 correcto · 1 datos insuficientes para entrenar · 2 no hay histórico.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sklearn.inspection import permutation_importance

from pipeline_dsia.exceptions import DataLoadError, ModelError
from pipeline_dsia.features import FEATURES, OBJETIVO, construir_features, filas_entrenables
from pipeline_dsia.historico import CARPETA_HISTORICO, a_formato_largo, cargar_historico, cargar_mercados
from pipeline_dsia.modelo import (
    CARPETA_MODELOS, REJILLA, SEMILLA, buscar_hiperparametros, cargar_metadatos, crear_modelo,
    evaluar_modelos, guardar_modelo, separar_train_test,
)
from pipeline_dsia.registro import configurar_logs

log = logging.getLogger("pipeline_dsia.entrenar")

MIN_DIAS = 10                 # mínimo de días útiles (con una semana de historia y objetivo conocido)
HIPERPARAMETROS_POR_DEFECTO = {"learning_rate": 0.1, "max_leaf_nodes": 31, "max_iter": 100}
FILAS_IMPORTANCIA = 20_000    # muestra del test con la que se calcula la importancia de las variables


def fraccion(valor: str) -> float:
    try:
        numero = float(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valor}' no es un número")
    if not 0 < numero <= 1:
        raise argparse.ArgumentTypeError("debe estar entre 0 (excluido) y 1")
    return numero


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia.entrenar",
        description="Entrena el modelo que predice la variación del precio de cada estación al día siguiente.",
    )
    parser.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO, help="carpeta del histórico")
    parser.add_argument("--modelos", type=Path, default=CARPETA_MODELOS, help="carpeta donde se guarda el modelo")
    parser.add_argument("--fraccion-test", type=fraccion, default=0.2,
                        help="parte final de los días reservada para el test (por defecto 0.2)")
    parser.add_argument("--muestra-busqueda", type=fraccion, default=0.2,
                        help="fracción de estaciones usada en la búsqueda de hiperparámetros (por defecto 0.2)")
    parser.add_argument("--sin-busqueda", action="store_true",
                        help="no buscar: usar los hiperparámetros del último entrenamiento (o los de por defecto)")
    return parser


def preparar_datos(carpeta: Path) -> pd.DataFrame:
    """Histórico → filas con features y objetivo conocido."""
    largo = a_formato_largo(cargar_historico(carpeta))
    datos = filas_entrenables(construir_features(largo, cargar_mercados(carpeta)))
    dias = datos["fecha"].nunique() if len(datos) else 0
    if dias < MIN_DIAS:
        raise ModelError(f"Solo hay {dias} días útiles para entrenar; hacen falta al menos {MIN_DIAS} "
                         f"(es decir, unos {MIN_DIAS + 8} días de histórico). "
                         "Rellena el histórico con 'python -m pipeline_dsia.ingesta --desde AAAA-MM-DD'")
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


def escribir_informe(carpeta: Path, metadatos: dict, busqueda: pd.DataFrame | None, importancia: pd.DataFrame) -> Path:
    """Informe legible del entrenamiento: datos, hiperparámetros, métricas e importancia."""
    metricas = pd.DataFrame(metadatos["metricas_test"]).T.rename_axis("modelo").reset_index()
    gb, base = metadatos["metricas_test"]["gradient_boosting"], metadatos["metricas_test"]["persistencia"]
    mejora = (1 - gb["rmse_cts"] / base["rmse_cts"]) * 100 if base["rmse_cts"] else 0.0
    veredicto = (f"El modelo **mejora** a la persistencia un {mejora:.1f} % en RMSE."
                 if mejora > 0 else
                 f"El modelo **no mejora** a la persistencia en RMSE ({mejora:.1f} %).")

    partes = [
        "# Informe del modelo",
        f"Generado automáticamente por `python -m pipeline_dsia.entrenar` el {metadatos['fecha_informe']}.",
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


def main(argv=None) -> int:
    args = crear_parser().parse_args(argv)
    configurar_logs("entrenar")

    # 1. Datos
    try:
        datos = preparar_datos(args.carpeta)
    except DataLoadError as exc:
        log.error("No se pudo cargar el histórico: %s", exc)
        return 2
    except ModelError as exc:
        log.error("%s", exc)
        return 1
    log.info("Datos: %d filas, %d días, %d estaciones", len(datos), datos["fecha"].nunique(), datos["id"].nunique())

    try:
        # 2. Separación temporal
        train, test = separar_train_test(datos, args.fraccion_test)
        log.info("Train: %d filas (hasta %s) · Test: %d filas (desde %s)",
                 len(train), train["fecha"].max().date(), len(test), test["fecha"].min().date())

        # 3. Hiperparámetros
        tabla_busqueda = None
        if args.sin_busqueda:
            hiper = cargar_metadatos(args.modelos).get("hiperparametros", HIPERPARAMETROS_POR_DEFECTO)
            log.info("Sin búsqueda. Hiperparámetros: %s", hiper)
        else:
            log.info("Buscando hiperparámetros (%d combinaciones)...", len(pd.MultiIndex.from_product(REJILLA.values())))
            hiper, tabla_busqueda = buscar_hiperparametros(train, fraccion_estaciones=args.muestra_busqueda)
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
    guardar_modelo(modelo_final, metadatos, args.modelos)
    informe = escribir_informe(args.modelos, metadatos, tabla_busqueda, importancia)
    log.info("Informe guardado en %s", informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
