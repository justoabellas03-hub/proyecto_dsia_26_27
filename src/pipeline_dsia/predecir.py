"""Inferencia: predice el precio de mañana de cada estación y carburante.

Uso:
    python -m pipeline_dsia.predecir                  # usa historico/ y models/
    python -m pipeline_dsia.predecir --salida data/   # carpeta de resultados
    python -m pipeline_dsia.predecir --help

Pasos:
    1. Cargar los últimos días del histórico y construir las features.
    2. Cargar el modelo sklearn (models/modelo.joblib) y predecir la variación.
    3. Guardar data/predicciones.csv (una fila por estación × carburante).
    4. Resumir la predicción y pedir la explicación al cliente de IA
       (Hugging Face o mock) → data/informe_prediccion.md.

Códigos de salida: 0 correcto · 2 no hay histórico · 3 no hay modelo entrenado.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from pipeline_dsia.config import leer_configuracion
from pipeline_dsia.exceptions import DataLoadError, ModelError
from pipeline_dsia.features import FEATURES, RETARDOS_PRECIO, construir_features
from pipeline_dsia.historico import CARPETA_HISTORICO, a_formato_largo, cargar_historico, cargar_mercados
from pipeline_dsia.ia import (
    ClienteIA, Explicacion, ResumenCarburante, ResumenPrediccion, crear_cliente, explicar_con_respaldo,
)
from pipeline_dsia.modelo import CARPETA_MODELOS, cargar_modelo
from pipeline_dsia.registro import configurar_logs

log = logging.getLogger("pipeline_dsia.predecir")

# Para las features del último día basta con los días del retardo más largo (+ margen)
DIAS_NECESARIOS = max(RETARDOS_PRECIO) + 3

# Una estación cuenta como "sube" o "baja" solo si la variación prevista llega a medio céntimo.
# El modelo predice una media: sin umbral, una previsión de −0,1 céntimos contaría como bajada.
UMBRAL_CAMBIO = 0.005   # €/l

COLUMNAS_SALIDA = [
    "fecha_prediccion", "id", "rotulo", "municipio", "provincia", "carburante",
    "precio_hoy", "variacion_prevista", "precio_previsto",
]


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline_dsia.predecir",
        description="Predice el precio de mañana de cada estación con el modelo entrenado.",
    )
    parser.add_argument("--carpeta", type=Path, default=CARPETA_HISTORICO, help="carpeta del histórico")
    parser.add_argument("--modelos", type=Path, default=CARPETA_MODELOS, help="carpeta del modelo")
    parser.add_argument("--salida", type=Path, default=Path("data"), help="carpeta de resultados (por defecto data/)")
    return parser


def predecir_manana(modelo, datos: pd.DataFrame) -> pd.DataFrame:
    """Aplica el modelo a las filas del último día del histórico.

    Args:
        modelo: Pipeline de sklearn ya entrenado.
        datos: Salida de construir_features.

    Returns:
        Una fila por estación × carburante con el precio de hoy, la variación
        prevista y el precio previsto para mañana (€/l, redondeado a milésimas
        como los precios reales).
    """
    ultimo_dia = datos["fecha"].max()
    hoy = datos[datos["fecha"] == ultimo_dia].copy()
    hoy["variacion_prevista"] = modelo.predict(hoy[FEATURES]).round(3)
    hoy["fecha_prediccion"] = ultimo_dia + pd.Timedelta(days=1)
    hoy = hoy.rename(columns={"precio": "precio_hoy"})
    hoy["precio_previsto"] = (hoy["precio_hoy"] + hoy["variacion_prevista"]).round(3)
    return hoy[COLUMNAS_SALIDA + ["var_brent_7"]].reset_index(drop=True)


def resumir(predicciones: pd.DataFrame) -> ResumenPrediccion:
    """Predicciones de todas las estaciones → resumen nacional por carburante."""
    carburantes = []
    for carburante, grupo in predicciones.groupby("carburante"):
        carburantes.append(ResumenCarburante(
            carburante=carburante,
            precio_medio_hoy=round(float(grupo["precio_hoy"].mean()), 3),
            variacion_media_cts=round(float(grupo["variacion_prevista"].mean()) * 100, 2),
            pct_suben=round(float((grupo["variacion_prevista"] >= UMBRAL_CAMBIO).mean()) * 100, 1),
            pct_bajan=round(float((grupo["variacion_prevista"] <= -UMBRAL_CAMBIO).mean()) * 100, 1),
        ))
    brent = predicciones["var_brent_7"].dropna()
    return ResumenPrediccion(
        fecha_prediccion=predicciones["fecha_prediccion"].iloc[0].date(),
        var_brent_7=round(float(brent.iloc[0]), 2) if len(brent) else None,
        carburantes=carburantes,
    )


def escribir_informe(ruta: Path, resumen: ResumenPrediccion, explicacion: Explicacion) -> None:
    lineas = [
        f"# Previsión de precios para el {resumen.fecha_prediccion:%d/%m/%Y}",
        "",
        explicacion.texto,
        "",
        "| Carburante | Precio medio hoy (€/l) | Variación media prevista (cts) | % suben ≥ 0,5 cts | % bajan ≥ 0,5 cts |",
        "| --- | --- | --- | --- | --- |",
    ]
    lineas += [f"| {c.carburante} | {c.precio_medio_hoy:.3f} | {c.variacion_media_cts:+.2f} | {c.pct_suben:.1f} | {c.pct_bajan:.1f} |"
               for c in resumen.carburantes]
    lineas += ["", f"_Cifras: modelo scikit-learn. Texto: proveedor `{explicacion.proveedor}`, modelo `{explicacion.modelo}`._", ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


def main(argv=None, cliente: ClienteIA | None = None) -> int:
    args = crear_parser().parse_args(argv)
    configurar_logs("predecir")

    # 1. Datos recientes y features
    try:
        largo = a_formato_largo(cargar_historico(args.carpeta, ultimos_dias=DIAS_NECESARIOS))
        datos = construir_features(largo, cargar_mercados(args.carpeta))
    except DataLoadError as exc:
        log.error("No se pudo cargar el histórico: %s", exc)
        return 2

    # 2. Modelo e inferencia
    try:
        modelo = cargar_modelo(args.modelos)
    except ModelError as exc:
        log.error("%s", exc)
        return 3
    predicciones = predecir_manana(modelo, datos)
    log.info("Predicciones para el %s: %d (estación × carburante)",
             predicciones["fecha_prediccion"].iloc[0].date(), len(predicciones))

    # 3. Guardar las predicciones
    args.salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = args.salida / "predicciones.csv"
    predicciones[COLUMNAS_SALIDA].to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    log.info("Guardado %s", ruta_csv)

    # 4. Explicación en lenguaje natural (Hugging Face o mock)
    resumen = resumir(predicciones)
    cliente = cliente or crear_cliente(leer_configuracion())
    explicacion = explicar_con_respaldo(cliente, resumen)
    log.info("Explicación generada con '%s' (%s)", explicacion.proveedor, explicacion.modelo)
    ruta_informe = args.salida / "informe_prediccion.md"
    escribir_informe(ruta_informe, resumen, explicacion)
    log.info("Guardado %s", ruta_informe)
    print("\n" + explicacion.texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
