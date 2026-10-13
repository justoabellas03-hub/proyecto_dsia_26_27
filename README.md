# Pipeline de precios de carburantes en España

Proyecto de la asignatura **Desarrollo de Soluciones de IA (DSIA) 2026-2027**.

Descarga los precios actuales de todas las gasolineras de España desde el servicio oficial del
Ministerio, comprueba la calidad de los datos con un contrato de datos y calcula métricas sobre
precios por provincia, por marca y por estación.

```text
API del Ministerio ──► loader ──► selección de columnas ──► normalización ──► contrato ──► métricas
```

## Origen de los datos


**Conjunto de datos** 
 [Precio de carburantes en las gasolineras españolas](https://datos.gob.es/es/catalogo/e05068001-precio-de-carburantes-en-las-gasolineras-espanolas) (catálogo datos.gob.es) |
**Servicio usado** `https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/` |
**Documentación de la API** [Página de ayuda del servicio REST](https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/help) |
**Actualización** Diaria según el catálogo.
**Fecha de descarga** En cada ejecución


### Por qué no hay datos guardados en el repositorio

El programa descarga los datos de la API en cada ejecución, así que siempre usa los precios más
recientes. Los resultados de cada ejecución se guardan en `data/` (ver [Resultados](#resultados)),
una carpeta que no se sube a GitHub.

## Instalación

```bash
git clone https://github.com/justoabellas03-hub/proyecto_dsia_26_27.git
cd proyecto_dsia_26_27
uv sync
```

## Uso

```bash
uv run python -m pipeline_dsia                                 # ejecución con valores por defecto
uv run python -m pipeline_dsia --top 5 --min-estaciones 30     # cambiar los rankings
uv run python -m pipeline_dsia --salida otra_ruta.csv          # guardar el CSV en otra ruta
uv run python -m pipeline_dsia --help                          # ver todas las opciones
```

| Opción | Por defecto | Descripción |
| --- | --- | --- |
| `--top N` | 10 | Número de gasolineras en el ranking de más baratas |
| `--min-estaciones N` | 20 | Mínimo de gasolineras para que una marca aparezca en el ranking de marcas |
| `--salida RUTA_CSV` | `datos/gasolineras_metricas.csv` | CSV donde se guardan las gasolineras válidas con sus métricas |

**Códigos de salida:** `0` correcto · `1` ninguna estación supera la validación · `2` error al descargar los datos.

## Estructura

```text
src/pipeline_dsia/
├── __main__.py     # línea de comandos: orquesta todo el pipeline
├── loader.py       # descarga de la API → DataFrame
├── constants.py    # URL de la API, columnas numéricas y rangos válidos
├── contracts.py    # contrato de datos (pydantic) de una estación
├── validator.py    # normalización de números y validación con el contrato
├── metrics.py      # métricas
└── exceptions.py   # excepciones de dominio (DataLoadError, ValidationError)
test/
├── conftest.py     # estaciones de prueba inventadas
├── test_metrics.py
└── test_cli.py
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

## Resultados

Cada ejecución guarda un CSV (por defecto `datos/gasolineras_metricas.csv`, se sobrescribe en
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
uv add --dev pytest pytest-cov            # solo la primera vez
uv run pytest                            # ejecutar los tests
uv run pytest --cov=pipeline_dsia

```

Los tests no necesitan conexión a internet. Las métricas se prueban con 5 estaciones inventadas,
cuyos resultados se han calculado a mano, y la línea de comandos se prueba simulando la respuesta
de la API.
