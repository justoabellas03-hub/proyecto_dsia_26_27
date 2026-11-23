# Uso de IA en el proyecto

Aquí cuento qué parte del proyecto es mía y en qué me ha ayudado la inteligencia artificial.
Son dos cosas distintas: la IA que forma parte del programa (Hugging Face) y la IA que he usado
como ayuda para programarlo (Claude).

## 1. La IA dentro del programa

El programa usa un modelo de lenguaje de Hugging Face para contar con palabras la predicción del
día siguiente. Las cifras las calcula siempre mi modelo de scikit-learn: el modelo de lenguaje
solo redacta un resumen que ya está calculado, y tiene prohibido inventarse datos o causas. En el
informe final van también las cifras originales, para poder comprobar que el texto dice la verdad.

- **Proveedor:** Hugging Face (Inference Providers), con `InferenceClient` de la librería `huggingface_hub`.
- **Tarea:** `chat_completion` (generar texto con un modelo de lenguaje).
- **Modelo:** `meta-llama/Llama-3.1-8B-Instruct` (se puede cambiar con la variable `HF_MODEL`).
- **Dónde está:** `src/pipeline_dsia/ia.py`; se llama desde `predecir.py`.
- **Token:** `HF_TOKEN` en el fichero `.env` (en local) o como secreto en GitHub. Nunca se sube a Git.

Por defecto (`AI_PROVIDER=mock`) se usa un **mock**: escribe el texto con una plantilla, sin red y
siempre igual. Los tests y el CI usan siempre el mock. Si Hugging Face falla (sin red, token mal,
modelo no disponible), el programa no se para: apunta el error en el log y tira del mock.
La llamada real se prueba con `uv run pytest -m hf_real` (si no hay token, ese test se salta).

## 2. Qué es mío y en qué me ha ayudado la IA

Como asistente de programación he usado **Claude** (Anthropic), sobre todo en noviembre de 2026.

### Lo que es cosecha mía

- **La obtención de los datos.** Elegí el tema y las fuentes: los precios de las gasolineras que
  publica el Ministerio y, como variables de mercado, el Brent (FRED) y el cambio euro-dólar (BCE).
- **La validación de los datos.** Las reglas que tiene que cumplir cada estación: precios entre
  0,5 y 3,5 €/l, coordenadas dentro de España (Canarias incluida), código postal de 5 cifras,
  que venda al menos uno de los carburantes que analizo y que no haya estaciones repetidas.
- **Las métricas diarias.** El precio medio por provincia y por marca, la comparación de cada
  estación con la media de su provincia, las gasolineras más baratas de España y la diferencia
  entre gasolina y gasóleo.
- **El método y el modelo.** Predecir cuánto va a cambiar el precio de cada estación al día
  siguiente; compararlo con la persistencia (suponer que el precio no cambia) y con una regresión
  Ridge; y usar un gradient boosting con sus hiperparámetros (`learning_rate`, `max_leaf_nodes` y
  `max_iter`), elegidos con validación cruzada temporal para no usar datos del futuro.

### Lo que tiene mucho de IA

En estas partes la IA me ha ayudado mucho, tanto explicándome cosas que no conocía como
escribiendo buena parte del código:

- **La estrategia del flujo y el pipeline.** Cómo encadenar los pasos (ingesta → histórico →
  entrenar → predecir), cómo repartir el código en módulos (primero eran 19 ficheros y luego
  los dejamos en 10, con un solo comando `python -m pipeline_dsia`) y el comando `todo`, que lo
  ejecuta todo seguido.
- **Hugging Face.** No lo había usado nunca. La IA me explicó cómo funciona la Inference API y
  me ayudó a montar el cliente, el mock y el respaldo para cuando falla.
- **Los logs.** Cómo configurarlos para que salgan por pantalla y queden guardados en `logs/`.
- **La programación de tareas.** El workflow de GitHub Actions y, cuando vimos que desde GitHub
  fallaba la descarga de los datos de mercado, el script para el Programador de tareas de Windows.
- **La actualización de la base de datos.** El histórico con un fichero por día, el backfill
  para rellenar los días que faltan y cómo subir los datos nuevos al repositorio.
- **Otras ayudas.** Los tests (sobre todo los del validador, los de integración y los de la parte A),
  la reorganización de la parte A en módulos, el CI común para las dos partes y los borradores
  del README y de `docs/DEFENSA.md`.

### Cómo lo he revisado

No he dado nada por bueno sin probarlo:

- Paso los tests (`uv run pytest`) y he ejecutado el programa entero con datos reales.
- Miro `models/INFORME_MODELO.md` para comprobar que el modelo tiene sentido comparado con la
  persistencia.
- Me he peleado con problemas reales que no salen en ningún tutorial: la API del Ministerio me
  cortaba la conexión desde Python y a veces solo funcionaba con curl; el primer backfill desde
  agosto falló entero y tuve que ir cargando los datos por tramos; y la descarga del Brent desde
  FRED a veces se queda colgada, que es lo que hacía fallar cada día el workflow de GitHub.
