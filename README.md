# Predicción de precios de carburantes en España

Trabajo de la asignatura **Desarrollo de Soluciones de IA (DSIA) 2026-2027** (Proyectos I y II; base
del Trabajo Final).

Cada día el pipeline descarga el precio de los carburantes de todas las gasolineras de España,
el precio del petróleo Brent y el cambio euro/dólar. Con ese histórico, un modelo de
**scikit-learn** predice cuánto variará mañana el precio de cada carburante en cada estación, y un
modelo de **Hugging Face** redacta la previsión en lenguaje natural.

```text
Ministerio + FRED + BCE ─► ingesta ─► contrato de datos ─► historico/
                                                              │
                              ┌───────────────────────────────┘
                              ▼
                          features ─► entrenar (sklearn) ─► models/modelo.joblib
                              │                                   │
                              └────────────► predecir ◄───────────┘
                                                │
                                                ▼
                        data/predicciones.csv ─► explicación (Hugging Face o mock)
```

| Documento | Contenido |
| --- | --- |
| [`docs/DEFENSA.md`](docs/DEFENSA.md) | Explicación detallada de cada decisión (modelo, hiperparámetros, validación) |
| [`models/INFORME_MODELO.md`](models/INFORME_MODELO.md) | Métricas del último entrenamiento (se genera al entrenar) |
| [`AI_USAGE.md`](AI_USAGE.md) | Uso de IA: en el pipeline y como ayuda al desarrollo |

## Dominio, datos y motivación

**Problema.** El precio de los carburantes cambia cada día y de forma distinta en cada estación.
Saber si mañana subirá o bajará en una estación concreta ayuda a decidir cuándo repostar.

**Por qué este dominio.** Los datos son públicos, oficiales, se actualizan a diario y cubren todas
las estaciones del país, lo que permite montar un pipeline real de ingesta, entrenamiento y
predicción diaria.

| Fuente | Qué aporta | Origen | Condiciones de uso |
| --- | --- | --- | --- |
| [Precio de carburantes en las gasolineras españolas](https://datos.gob.es/es/catalogo/e05068001-precio-de-carburantes-en-las-gasolineras-espanolas) | Precio de cada carburante en cada estación | Ministerio, servicio REST ([ayuda](https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/help)) | Datos abiertos del sector público; ver las condiciones de reutilización en la ficha del catálogo |
| [Brent, serie DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU) | Precio del barril en dólares | U.S. Energy Information Administration, vía FRED | Citar la fuente (EIA / FRED) |
| [EUR/USD, serie EXR.D.USD.EUR.SP00.A](https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A) | Dólares por euro | Banco Central Europeo | Reutilización libre citando la fuente (BCE) |

Los datos se descargan con el propio pipeline. El histórico (`historico/`) sí se guarda en el
repositorio, porque el servicio del Ministerio solo devuelve los precios del día.

## Instalación

```bash
git clone https://github.com/justoabellas03-hub/proyecto_dsia_26_27.git
cd proyecto_dsia_26_27
uv sync
```

## Uso

El flujo completo son tres comandos, en este orden:

```bash
uv run python -m pipeline_dsia.ingesta --desde 2026-08-01   # 1. (solo la primera vez) rellenar el histórico
uv run python -m pipeline_dsia.ingesta                      # 1. datos de hoy
uv run python -m pipeline_dsia.entrenar                     # 2. entrenar el modelo sklearn
uv run python -m pipeline_dsia.predecir                     # 3. predecir mañana + explicación
uv run python -m pipeline_dsia.consultar --provincia sevilla --carburante gasoleo_a   # 4. consultar
```

| Comando | Qué hace | Genera |
| --- | --- | --- |
| `pipeline_dsia.ingesta` | Descarga precios, Brent y EUR/USD y los valida | `historico/` |
| `pipeline_dsia.entrenar` | Busca hiperparámetros, evalúa y guarda el modelo | `models/modelo.joblib`, `models/metricas.json`, `models/INFORME_MODELO.md` |
| `pipeline_dsia.predecir` | Aplica el modelo al último día y explica el resultado | `data/predicciones.csv`, `data/informe_prediccion.md` |
| `pipeline_dsia.consultar` | Muestra el precio previsto por estación, municipio, provincia, marca o carburante | (por pantalla) |
| `pipeline_dsia` | Métricas descriptivas del día (Proyecto I) | `data/gasolineras_metricas.csv` |

Todos aceptan `--help`. Los logs se escriben por pantalla y en `logs/`.

### Consultar la predicción

```bash
uv run python -m pipeline_dsia.consultar --provincia madrid                           # todos los carburantes
uv run python -m pipeline_dsia.consultar --municipio getafe --carburante gasolina_95  # + las 5 más baratas
uv run python -m pipeline_dsia.consultar --estacion 4354                              # una estación (columna id)
uv run python -m pipeline_dsia.consultar --rotulo repsol --provincia valencia --top 10
```

Los filtros se combinan y no distinguen tildes ni mayúsculas. Lee `data/predicciones.csv`, así
que antes hay que ejecutar `predecir`. Códigos de salida: `0` correcto · `1` ninguna estación
coincide · `2` no hay predicciones.

### Configuración

Copia `.env.example` como `.env` (no se sube a Git):

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `AI_PROVIDER` | `mock` | `mock` (sin red) o `hf` (Hugging Face) |
| `HF_TOKEN` | — | Token de Hugging Face, solo si `AI_PROVIDER=hf` |
| `HF_MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | Modelo del Hub para `chat_completion` |

### Métricas descriptivas (Proyecto I)

```bash
uv run python -m pipeline_dsia                                 # ejecución con valores por defecto
uv run python -m pipeline_dsia --top 5 --min-estaciones 30     # cambiar los rankings
uv run python -m pipeline_dsia --salida otra_ruta.csv          # guardar el CSV en otra ruta
```

| Opción | Por defecto | Descripción |
| --- | --- | --- |
| `--top N` | 10 | Número de gasolineras en el ranking de más baratas |
| `--min-estaciones N` | 20 | Mínimo de gasolineras para que una marca aparezca en el ranking de marcas |
| `--salida RUTA_CSV` | `data/gasolineras_metricas.csv` | CSV donde se guardan las gasolineras válidas con sus métricas |

**Códigos de salida:** `0` correcto · `1` ninguna estación supera la validación · `2` error al descargar los datos.

## Ingesta diaria e histórico

Para entrenar un modelo que prediga el precio del día siguiente hace falta un histórico. El
endpoint del Ministerio solo devuelve los precios **actuales**, así que cada día se guarda una foto
de todas las estaciones válidas, junto con dos series de mercado que influyen en el precio:

| Fuente | Qué es | URL | Clave |
| --- | --- | --- | --- |
| Ministerio (actual) | Precios de hoy de todas las estaciones | `.../EstacionesTerrestres/` | No |
| Ministerio (histórico) | Precios de un día pasado (`dd-mm-aaaa`) | `.../EstacionesTerrestresHist/{fecha}` | No |
| [FRED – DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU) | Brent, USD/barril, días hábiles. CSV con toda la serie | `fredgraph.csv?id=DCOILBRENTEU` | No |
| [BCE – EXR](https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A) | EUR/USD de referencia, diario | `data-api.ecb.europa.eu/.../D.USD.EUR.SP00.A` | No |

```bash
uv run python -m pipeline_dsia.ingesta                       # precios de hoy + mercados
uv run python -m pipeline_dsia.ingesta --desde 2026-06-01    # backfill de los días que falten
uv run python -m pipeline_dsia.ingesta --sin-mercados        # solo precios
```

```text
historico/
├── precios/AAAA-MM-DD.csv.gz   # estaciones válidas de cada día (mismo contrato que el pipeline)
└── mercados.csv                # fecha, brent_usd, eurusd, brent_eur (todos los días del calendario)
```

- **Automatización.** `.github/workflows/pipeline_diario.yml` la ejecuta cada día y hace commit de
  `historico/`. Desde la pestaña *Actions → Pipeline diario → Run workflow* se puede lanzar a mano,
  también con una fecha para el backfill.
- **Idempotente.** Un fichero por día: repetir un día lo sobrescribe y el backfill se salta los
  días que ya existen. Si un día del backfill falla, se registra y se sigue con el resto.
- **Robustez.** Cada descarga se reintenta 3 veces con espera creciente. Los logs van por pantalla y
  a `logs/ingesta.log`.
- **Mercados sin información del futuro.** Brent y EUR/USD no publican en fin de semana ni
  festivos: se rellenan **hacia delante** con el último valor conocido, nunca hacia atrás.
  `brent_eur = brent_usd / eurusd` es el coste del barril para un operador español.

## Modelo scikit-learn

Resumen; el detalle y la justificación de cada decisión están en [`docs/DEFENSA.md`](docs/DEFENSA.md).

- **Qué predice.** La variación del precio al día siguiente (`precio de mañana − precio de hoy`,
  en €/l) de cada estación y carburante. Se predice la variación y no el precio para poder
  compararse con la predicción trivial "mañana igual que hoy" (persistencia).
- **Variables.** Historia del propio precio (cambio en 1, 3 y 7 días), posición respecto a la
  media de su provincia, variación del Brent en euros (3, 7 y 14 días), día de la semana,
  coordenadas, carburante, provincia y tipo de venta.
- **Modelo.** `HistGradientBoostingRegressor` dentro de un `Pipeline` con `ColumnTransformer`.
- **Hiperparámetros.** `GridSearchCV` sobre `learning_rate`, `max_iter` y `max_leaf_nodes`
  (8 combinaciones) con validación cruzada temporal por días.
- **Evaluación.** Los últimos días son el test (nunca partición aleatoria). Se comparan
  persistencia, Ridge y gradient boosting con MAE, RMSE y acierto de dirección.
- **Sin fuga de información.** El Brent se usa con 10 días de retraso (FRED lo publica tarde),
  los mercados se rellenan solo hacia delante y los huecos de días no se cruzan.
- **Persistencia.** `models/modelo.joblib` (joblib) + `models/metricas.json`.
- **Métricas.** En [`models/INFORME_MODELO.md`](models/INFORME_MODELO.md), que se regenera en
  cada entrenamiento.
- **Reentrenar.** `uv run python -m pipeline_dsia.entrenar` (con `--sin-busqueda` reutiliza los
  hiperparámetros anteriores). En GitHub Actions se reentrena cada lunes.

## Hugging Face (borde de IA)

| | |
| --- | --- |
| **Tarea Inference** | `chat_completion` |
| **Modelo del Hub** | `meta-llama/Llama-3.1-8B-Instruct` (variable `HF_MODEL`) |
| **Para qué** | Redactar en lenguaje natural la previsión calculada por scikit-learn (post-proceso) |
| **Cliente** | `src/pipeline_dsia/ia.py`: contratos pydantic, `ClienteMock` y `ClienteHF` con la misma interfaz |
| **En tests y CI** | Siempre **mock** (sin red ni token). `pytest -m hf_real` prueba el proveedor real |

El modelo de lenguaje no calcula nada: recibe un resumen con las cifras y lo redacta. Si la API
falla, el pipeline sigue con el mock.

## Automatización

`.github/workflows/pipeline_diario.yml` ejecuta cada día ingesta → (los lunes, entrenar) →
predecir, guarda `historico/` y `models/` en el repositorio y publica la predicción como
artefacto de la ejecución. `.github/workflows/cli.yml` ejecuta los tests en cada push.

## Qué se ampliará en el Proyecto III

- **API** (FastAPI): `/predict` sobre `predecir_manana()` y los filtros de `consultar.py`, y `/analyze` sobre `ClienteIA.explicar()`.
- **Monitorización**: comparar cada día la predicción de ayer con el precio real y vigilar el error.
- **Despliegue** de la API y reentrenamiento cuando el error supere un umbral.
- Nuevas variables: marca (clasificada), régimen fiscal y festivos.

## Estructura

```text
src/pipeline_dsia/
├── __main__.py     # línea de comandos: orquesta todo el pipeline
├── loader.py       # descarga con reintentos → DataFrame
├── constants.py    # URL de la API, columnas numéricas y rangos válidos
├── contracts.py    # contrato de datos (pydantic) de una estación
├── validator.py    # normalización de números y validación con el contrato
├── metrics.py      # métricas
├── mercados.py     # Brent (FRED) y EUR/USD (BCE)
├── historico.py    # almacén histórico: un fichero por día
├── ingesta.py      # CLI de la ingesta diaria y del backfill
├── features.py     # variables y objetivo del modelo
├── modelo.py       # modelo sklearn: definición, validación temporal, búsqueda, métricas, joblib
├── entrenar.py     # CLI de entrenamiento
├── predecir.py     # CLI de inferencia + explicación
├── consultar.py    # CLI de consulta de las predicciones
├── ia.py           # cliente de IA: contratos, mock y Hugging Face
├── config.py       # variables de entorno (.env)
├── registro.py     # configuración de los logs
└── exceptions.py   # excepciones de dominio
test/
├── conftest.py     # estaciones y respuesta de la API inventadas
├── test_metrics.py
├── test_cli.py
├── test_loader.py
├── test_mercados.py
├── test_historico.py
├── test_ingesta.py
├── test_features.py
├── test_modelo.py          # incluye guardar → cargar → predecir
├── test_ia.py              # mock y cliente HF simulado
├── test_consultar.py
└── test_pipeline_modelo.py # integración: histórico → entrenar → predecir
models/                     # modelo entrenado, métricas e informe
historico/                  # datos diarios (los genera la ingesta)
docs/DEFENSA.md             # explicación detallada de las decisiones
```

## Validación de los datos

Cada estación pasa por el contrato `Estacion` (pydantic). Una estación se descarta si:

| Regla | Detalle |
| --- | --- |
| Identificadores | `IDEESS`, municipio, provincia y comunidad deben ser códigos numéricos con el formato esperado |
| Tipo de venta | Solo `P` (venta al público) o `R` (venta restringida a socios) |
| Código postal | 5 dígitos, si existe |
| Coordenadas | Dentro de España, incluidas Canarias (latitud 27–44,5; longitud −18,5–4,5) |
| Precios | Entre 0,5 y 3,5 €/l, si existen. Un precio vacío significa que la estación no vende ese carburante y **no** es un error |
| Al menos un carburante | La estación debe vender al menos uno de los 4 carburantes analizados |
| Duplicados | Si un `IDEESS` aparece dos veces, se queda la primera estación |

Carburantes analizados: **gasolina 95 E5, gasolina 98 E5, gasóleo A y gasóleo premium**. Quedan
fuera el AdBlue (es un aditivo, no un carburante), el gasóleo B (es agrícola y tiene otra
fiscalidad) y los gases, que se venden por kilo y no se pueden comparar con los demás.

## Métricas

| Métrica | Función | Qué responde |
| --- | --- | --- |
| Precio medio por provincia | `precio_medio_por_provincia` | Precio medio de cada carburante en cada provincia y la media de todos ellos |
| Comparación con la provincia | `comparar_con_provincia` | Añade a cada estación el precio medio de su provincia (`media_prov_<carburante>`) y cuánto más cara o más barata es, por carburante (`dif_<carburante>`) y en conjunto (`dif_media`) |
| Gasolineras más baratas | `mas_baratas` | Las N gasolineras más baratas de España teniendo en cuenta todos sus carburantes |
| Precio por marca | `precio_medio_por_marca` | Qué marcas son más baratas o más caras que la media de su zona |
| Gasolina frente a gasóleo | `diferencia_gasolina_gasoleo` y `media_diferencia_gasolina_gasoleo` | Diferencia entre gasolina 95 y gasóleo A en cada estación y su media en España |

Todas las métricas se apoyan en dos funciones base: `media_carburante` (media de un carburante,
en toda España o por grupo) y `media_gasolinera` (media de varias columnas en cada estación).

## Resultados (métricas descriptivas)

Cada ejecución guarda un CSV (por defecto `data/gasolineras_metricas.csv`, se sobrescribe en
cada ejecución) con una fila por gasolinera válida y estas columnas:

| Columnas | Contenido |
| --- | --- |
| `id`, `rotulo`, `tipo_venta`, `direccion`, `codigo_postal`, `municipio`, `provincia`, `id_municipio`, `id_provincia`, `id_ccaa`, `latitud`, `longitud` | Datos de la estación |
| `gasolina_95`, `gasolina_98`, `gasoleo_a`, `gasoleo_premium` | Precios (€/l). Vacío si no vende ese carburante |
| `media_prov_<carburante>` | Precio medio de ese carburante en la provincia de la estación |
| `dif_<carburante>` | Precio de la estación menos la media de su provincia (negativo = más barata) |
| `dif_media` | Media de las diferencias anteriores: si la estación es, en conjunto, más cara o más barata que su provincia |
| `dif_gasolina_gasoleo` | Gasolina 95 menos gasóleo A en esa estación |

El fichero se guarda en UTF-8 con BOM, para que Excel muestre bien las tildes.

## Decisiones de diseño

- **Comparaciones justas entre estaciones y marcas.** No se compara la media de los precios de cada
  estación, porque saldría barata una estación que solo vende gasóleo A (el carburante más barato)
  y cara la que vende gasolina 98. En su lugar, cada precio se compara con la media **del mismo
  carburante** y después se promedian esas diferencias (`dif_media`, `dif_nacional`).
- **Las marcas se comparan con la media de su provincia.** Así una marca con muchas estaciones en
  provincias baratas no sale barata solo por dónde está.
- **Venta restringida.** Las estaciones de venta restringida solo venden a socios, así que se
  excluyen del ranking de más baratas: no le sirven a un conductor cualquiera.
- **Mínimo de estaciones por marca.** Evita que una marca con una o dos gasolineras salga primera
  por casualidad.
- **Agrupación por códigos.** Se agrupa por `id_provincia` y no por el nombre, que puede venir
  escrito de formas distintas. Los rótulos de las marcas se pasan a mayúsculas y sin espacios.
- **Limpieza de formato fuera del contrato.** La API usa coma decimal (`"1,379"`).
  `normalizar_numeros` la cambia por punto antes del contrato, y el contrato se ocupa del tipo y
  de los rangos. El contrato convierte las cadenas vacías en `None`.
- **Alias en el contrato.** Los nombres de la API (`"C.P."`, `"Longitud (WGS84)"`) no son nombres
  válidos en Python. Los alias permiten usar nombres limpios (`codigo_postal`, `longitud`) en todo
  el código.

## Limitaciones

- **Canarias, Ceuta y Melilla** tienen otra fiscalidad sobre los carburantes y precios más bajos,
  así que dominan las comparaciones con la media nacional (`mas_baratas`).
- **Las medias por provincia** de carburantes poco vendidos (gasolina 98, gasóleo premium) se basan
  en pocas estaciones en algunas provincias y son menos fiables.
- **Se usa la media**, sensible a precios extremos. Cambiarla por la mediana solo requiere modificar
  `media_carburante`.

## Tests

```bash
uv run pytest                                          # todos los tests (sin conexión a internet)
uv run pytest --cov=pipeline_dsia --cov-report=term-missing
uv run pytest -m integration                           # solo integración: histórico → entrenar → predecir
uv run pytest -m hf_real                               # llamada real a Hugging Face (necesita HF_TOKEN)
```

Ningún test necesita conexión a internet (salvo `hf_real`, que se salta si no hay token):

- Las métricas se prueban con 5 estaciones inventadas, con resultados calculados a mano.
- Las descargas se simulan (`monkeypatch`).
- El modelo se prueba con un histórico sintético (`crear_historico_sintetico` en `conftest.py`),
  incluida la carga del modelo guardado y la inferencia.
- El cliente de IA se prueba con el mock y con un cliente de Hugging Face simulado.
