# Guía de defensa del Proyecto II

Documento para preparar la exposición: qué hace cada pieza, **por qué** se decidió así y qué
responder a las preguntas más probables. Los números concretos del modelo no están aquí porque
cambian en cada entrenamiento: están en [`models/INFORME_MODELO.md`](../models/INFORME_MODELO.md),
que se genera solo al entrenar.

## 1. El proyecto en un minuto

> Cada mañana el pipeline descarga el precio de todos los carburantes de todas las gasolineras de
> España, el precio del petróleo Brent y el cambio euro/dólar. Con ese histórico, un modelo de
> scikit-learn predice cuánto variará mañana el precio de cada carburante en cada estación. Un
> modelo de lenguaje de Hugging Face redacta la previsión en un párrafo. Todo se ejecuta solo en
> GitHub Actions.

Las dos piezas que pide el enunciado:

| Pieza | En este proyecto | Fichero |
| --- | --- | --- |
| Modelo scikit-learn entrenado por mí | Regresión: variación del precio al día siguiente | `modelo.py`, `entrenar.py`, `predecir.py` |
| Modelo del Hub de Hugging Face vía API | Tarea `chat_completion`: redactar la previsión | `ia.py` |

## 2. Flujo completo

```text
        Ministerio (precios)      FRED (Brent)      BCE (EUR/USD)
                 │                     │                 │
                 └──────────┬──────────┴─────────────────┘
                            ▼
   ingesta.py   →  contrato pydantic  →  historico/ (un fichero por día)
                            ▼
   features.py  →  una fila por estación × carburante × día, con sus variables
                            ▼
   entrenar.py  →  búsqueda de hiperparámetros → evaluación → models/modelo.joblib
                            ▼                                 models/INFORME_MODELO.md
   predecir.py  →  data/predicciones.csv  (precio previsto para mañana)
                            ▼
   ia.py        →  data/informe_prediccion.md  (explicación: Hugging Face o mock)
```

Tres comandos, en este orden: `ingesta` → `entrenar` → `predecir`.

## 3. Los datos

| Fuente | Qué aporta | Detalle importante |
| --- | --- | --- |
| Ministerio, servicio REST | Precio de cada carburante en cada estación | Solo da el precio **de hoy**: por eso hay que guardarlo cada día. Tiene un endpoint histórico por fecha para rellenar el pasado (backfill) |
| FRED, serie `DCOILBRENTEU` | Precio del barril de Brent en dólares | Solo días hábiles y **se publica con retraso** (entre 2 y 9 días) |
| BCE, serie `EXR.D.USD.EUR.SP00.A` | Dólares por euro | El Brent cotiza en dólares pero aquí se paga en euros |

- **`brent_eur = brent_usd / eurusd`**: lo que le cuesta el barril a un operador español. Si el
  Brent no se mueve pero el euro se deprecia, el carburante sube igual.
- **Fines de semana y festivos**: los mercados no publican, pero las gasolineras sí cambian
  precios. Se repite el último valor conocido (relleno hacia delante). Nunca hacia atrás, porque
  eso sería usar un dato del futuro.
- **Formato largo**: el histórico se transforma a una fila por estación × carburante × día. Así un
  solo modelo sirve para los cuatro carburantes y para todas las estaciones (el carburante es una
  variable más), en vez de entrenar miles de modelos pequeños.

## 4. Qué se predice exactamente

```text
objetivo = precio de mañana − precio de hoy      (€/litro)
```

**Por qué la variación y no el precio.** El precio de mañana es casi igual al de hoy. Si predijera
el precio, cualquier modelo sacaría un R² de 0,99 simplemente copiando el precio de hoy, y
parecería excelente sin haber aprendido nada. Prediciendo la variación, el modelo solo tiene
mérito si mejora a la predicción trivial **"mañana igual que hoy"** (persistencia), que es
exactamente la referencia con la que se compara.

El precio previsto se obtiene al final: `precio_previsto = precio_hoy + variación_prevista`.

## 5. Las variables (features)

Están todas en `features.py`. La idea general: el precio de una estación mañana depende de
(a) su propia inercia, (b) lo que hacen las estaciones de su zona y (c) el coste del petróleo.

| Variable | Qué es | Por qué ayuda |
| --- | --- | --- |
| `precio` | Precio de hoy | Nivel de partida |
| `dif_precio_1`, `_3`, `_7` | Cuánto ha cambiado el precio en 1, 3 y 7 días | Inercia: una estación que acaba de subir no suele volver a subir al día siguiente; una que lleva una semana quieta está "pendiente" de actualizar |
| `dif_provincia` | Precio − media de su provincia para ese carburante | Si está muy por encima de sus vecinas tenderá a bajar, y al revés. Reutiliza la idea de `comparar_con_provincia` de la primera parte |
| `var_provincia_1` | Cuánto cambió la media de la provincia de ayer a hoy | Las estaciones se siguen unas a otras: si la zona ha subido hoy, las rezagadas subirán mañana |
| `var_nacional_1` | Cuánto cambió de ayer a hoy la media nacional de ese carburante | Tendencia general del día. Es la señal de mercado más reciente, porque el Brent llega con retraso |
| `brent_eur` | Barril en euros (con retraso de 10 días) | Nivel del coste de la materia prima |
| `var_brent_3`, `_7`, `_14` | Variación % del Brent en 3, 7 y 14 días | El crudo tarda días en trasladarse al surtidor; por eso se miran varias ventanas |
| `dia_semana` | 0 = lunes … 6 = domingo | Muchas estaciones actualizan precios en días concretos |
| `latitud`, `longitud` | Coordenadas | Efectos geográficos más finos que la provincia (costa, frontera, islas) |
| `carburante` (categórica) | Gasolina 95, 98, gasóleo A o premium | Cada carburante reacciona distinto |
| `id_provincia` (categórica) | Código de provincia | Fiscalidad y competencia distintas (Canarias, Ceuta, Melilla) |
| `tipo_venta` (categórica) | Público o restringido | Las cooperativas actualizan precios de otra forma |

**Variables macroeconómicas descartadas (IPC, inflación anual, PIB).** Son mensuales o
trimestrales, iguales para todas las estaciones y se publican con retraso, así que no pueden
explicar variaciones de un día para otro. La inflación sí importa para comparar precios de años
distintos (2 € de hoy no son 2 € de hace diez años), pero aquí no se comparan niveles de precio
entre años: se predice la variación de hoy a mañana con un histórico de semanas o meses, periodo
en el que la inflación es prácticamente una constante. Además, los carburantes forman parte del
IPC: es una consecuencia del precio, no una causa.

**Lo que NO se usa como variable:** el identificador de la estación (el modelo memorizaría
estaciones en lugar de aprender reglas generales) ni el rótulo (cientos de marcas distintas, la
mayoría con muy pocas estaciones; es una mejora posible para el Proyecto III).

## 6. Fuga de información (data leakage): cómo se evita

Es la pregunta más probable. Una fuga es usar, al entrenar, información que el día de la
predicción todavía no existe; el modelo parece muy bueno y luego falla en la realidad. Hay cuatro
protecciones:

1. **Retraso de los datos de mercado.** FRED publica el Brent con hasta 9 días de retraso (el CSV
   descargado el 12-11-2026 llegaba solo hasta el 03-11). Si al entrenar usara el Brent del mismo
   día, estaría usando un dato que en producción no tengo. Por eso el día D se usa siempre el
   valor de D − 10 (`RETRASO_MERCADOS_DIAS`), igual al entrenar que al predecir.
2. **Relleno solo hacia delante** en fines de semana y festivos (`combinar_mercados`).
3. **Separación por fechas, nunca al azar.** El test son los últimos días; el entrenamiento, los
   anteriores. Con una partición aleatoria, el modelo vería el martes y el jueves para "predecir"
   el miércoles.
4. **Huecos en el histórico.** Si falta un día (caída del servicio), `valor_desplazado` devuelve
   vacío en lugar de usar por error el dato de otro día. Hay un test específico.

Además, los primeros 7 días del histórico se descartan para entrenar (`filas_entrenables`): en
ellos ninguna estación tiene todavía una semana de historia.

**Limpieza del objetivo.** Las variaciones de más de 25 céntimos en un día se descartan
(`MAX_VARIACION_DIARIA`): en los datos reales aparecen saltos de hasta 1 €/l que son errores al
cargar el precio (p. ej. 1,589 → 0,589) y distorsionarían tanto el entrenamiento como el RMSE.

## 7. El modelo

**`HistGradientBoostingRegressor`** de scikit-learn, dentro de un `Pipeline`:

```text
ColumnTransformer
 ├─ categóricas → OrdinalEncoder (texto → número entero; categoría nueva → "desconocida")
 └─ numéricas   → tal cual
        ▼
HistGradientBoostingRegressor
```

**Qué es el gradient boosting, en pocas palabras.** Se entrena un árbol de decisión pequeño; se
mira en qué se equivoca; se entrena otro árbol que corrige esos errores; y así cientos de veces.
La predicción final es la suma de todos los árboles. "Hist" significa que antes agrupa cada
variable en 255 tramos (un histograma), lo que lo hace muy rápido con millones de filas.

**Por qué este modelo:**

- **Relaciones no lineales e interacciones** sin programarlas: "si el Brent sube *y* la estación
  está por debajo de su provincia, sube más". Un modelo lineal no puede aprender ese "y".
- **Acepta valores vacíos**: una estación nueva no tiene `dif_precio_7`; no hay que inventarse
  un valor.
- **Acepta categóricas** directamente (se le indica cuáles son con `categorical_features`).
- **No necesita escalar** las variables (los árboles solo comparan "mayor o menor que").
- **Rápido** con el tamaño de estos datos (unas 30.000 filas por día).

**Por qué va dentro de un `Pipeline`:** el preproceso y el modelo se guardan juntos en un único
fichero. Al predecir se aplica exactamente la misma transformación que al entrenar, sin riesgo
de olvidar un paso.

**Alternativas consideradas:**

| Alternativa | Por qué no es el modelo principal |
| --- | --- |
| Regresión lineal (Ridge) | No capta interacciones. **Sí se entrena**, como referencia intermedia |
| Random Forest | Mucho más lento y pesado en memoria con millones de filas |
| Un modelo por estación (ARIMA…) | 11.000 modelos con muy pocos datos cada uno; no aprovecha lo que las estaciones tienen en común |
| Redes neuronales | Fuera del alcance del enunciado (pide scikit-learn) y sin ventaja clara con datos tabulares |

## 8. Hiperparámetros

Son los "ajustes" del modelo que no se aprenden de los datos, sino que hay que elegir.

**Los que se buscan** (`REJILLA` en `modelo.py`, 2 × 2 × 2 = 8 combinaciones):

| Hiperparámetro | Valores | Qué controla |
| --- | --- | --- |
| `learning_rate` | 0,05 · 0,1 | Cuánto corrige cada árbol nuevo. Bajo = aprende despacio pero más estable; necesita más árboles |
| `max_iter` | 100 · 300 | Número de árboles. Pocos = se queda corto; demasiados = empieza a memorizar el ruido |
| `max_leaf_nodes` | 15 · 31 | Hojas de cada árbol = su complejidad. 31 es el valor por defecto de sklearn; 15 es un árbol más simple |

`learning_rate` y `max_iter` se buscan juntos porque se compensan: con paso pequeño hacen falta
más árboles.

**Los que se dejan fijos**, con su motivo:

| Hiperparámetro | Valor | Motivo |
| --- | --- | --- |
| `loss` | `squared_error` | Ver apartado 9: es lo que permite mejorar a la persistencia |
| `min_samples_leaf` | 50 | Cada hoja necesita al menos 50 filas: evita reglas basadas en cuatro casos raros. Con millones de filas, 50 es conservador |
| `l2_regularization` | 1,0 | Penaliza predicciones extremas. La variación real es de céntimos; no quiero que prediga saltos enormes |
| `early_stopping` | `False` | La parada temprana de sklearn separa la validación **al azar**, lo que en datos temporales es una fuga. El número de árboles se elige con la validación temporal |
| `random_state` | 42 | Reproducibilidad: mismo dato → mismo modelo |

**Cómo se elige la mejor combinación:** `GridSearchCV` prueba las 8 y se queda con la de menor
RMSE medio en **validación cruzada temporal** (`particiones_temporales`):

```text
días de entrenamiento divididos en 4 bloques:   [ 1 ][ 2 ][ 3 ][ 4 ]
  partición 1:  entrena con 1        → valida con 2
  partición 2:  entrena con 1-2      → valida con 3
  partición 3:  entrena con 1-2-3    → valida con 4
```

Siempre se valida con días posteriores a los de entrenamiento.

**Por qué una función propia y no `TimeSeriesSplit` de sklearn:** `TimeSeriesSplit` corta por
número de fila. Aquí hay unas 30.000 filas con la misma fecha, así que partiría un mismo día
entre entrenamiento y validación. La función propia corta por días completos.

**Por qué la búsqueda usa el 20 % de las estaciones** (`--muestra-busqueda`): son 8 combinaciones
× 3 particiones = 24 entrenamientos. Con una muestra aleatoria de estaciones (conservando todas
sus fechas) tarda una fracción y el orden entre combinaciones apenas cambia. El modelo final sí
se entrena con todas.

**Por qué una rejilla pequeña:** es deliberado. 8 combinaciones se pueden explicar una a una y
entrenar en minutos en GitHub Actions. La tabla completa de la búsqueda queda en el informe.

## 9. Evaluación

1. **Separación temporal**: el último 20 % de los días es el test. Los hiperparámetros se buscan
   solo con el 80 % anterior; el test no se toca hasta el final.
2. **Tres modelos** sobre el mismo test:
   - **Persistencia** (variación = 0): la referencia a batir.
   - **Ridge**: ¿basta con un modelo lineal?
   - **Gradient boosting**: el modelo elegido.
3. **Métricas**, en céntimos de euro por litro:

| Métrica | Qué mide | Cómo leerla |
| --- | --- | --- |
| `mae_cts` | Error medio en valor absoluto | "De media me equivoco X céntimos" |
| `rmse_cts` | Igual, pero castiga más los errores grandes | Es la que se optimiza |
| `acierto_direccion` | De los días en que el precio cambió, % en que acerté si subía o bajaba | La persistencia saca 0 por definición |

**Punto clave para la defensa — MAE frente a RMSE.** La mayoría de los días el precio de una
estación **no cambia**. Por eso predecir "0" acierta de pleno casi siempre y la persistencia
tiene un MAE bajísimo, muy difícil de mejorar. Pero cuando el precio sí cambia, la persistencia
falla siempre. El modelo se entrena con error cuadrático (`squared_error`), que da más peso a esos
días: reparte pequeñas correcciones para fallar menos cuando hay movimiento. Por eso es normal y
esperable que el modelo **mejore en RMSE y en acierto de dirección** aunque en MAE quede parecido
o algo peor que la persistencia. El informe lo dice explícitamente.

**Si con los datos reales el modelo no mejora a la persistencia**, la respuesta honesta es:
"predecir precios a un día es un problema difícil porque el precio casi nunca cambia; por eso
comparo siempre con la persistencia en vez de enseñar un R² engañoso. Con más meses de histórico
y precios mayoristas se podría mejorar". Un resultado negativo bien medido es defendible; un
resultado inflado por una fuga, no.

4. **Importancia de las variables** (por permutación): se desordena una variable en el test y se
   mide cuánto empeora el RMSE. Si no empeora, el modelo no la usa. Sirve para explicar *qué ha
   aprendido* el modelo.
5. **Modelo final**: tras evaluar, se reentrena con **todos** los datos (entrenamiento + test) con
   los hiperparámetros elegidos, porque los días más recientes son los más útiles para predecir
   mañana. Las métricas publicadas son las del test, medidas antes de ese reentrenamiento.

**Qué significa la predicción de una estación.** El modelo predice la variación *media esperada*.
Si una estación tiene un 40 % de probabilidad de bajar 2 céntimos y un 60 % de no moverse, la
predicción será −0,8 céntimos, un valor que en la realidad no ocurrirá. Por eso:

- En el resumen, una estación solo cuenta como "sube" o "baja" si la variación prevista llega a
  medio céntimo (`UMBRAL_CAMBIO` en `predecir.py`). Sin ese umbral, una previsión de −0,1 céntimos
  contaría como bajada y saldría que "bajan el 99 % de las estaciones".
- El modelo acierta bien la **dirección** pero se queda corto en la **magnitud** cuando el mercado
  se mueve con fuerza, sobre todo si en el histórico de entrenamiento no ha visto un movimiento
  parecido. Es una limitación conocida y la razón principal para acumular más histórico.

## 10. Persistencia e inferencia

- `models/modelo.joblib`: el `Pipeline` completo (preproceso + modelo), guardado con joblib.
- `models/metricas.json`: fecha, versión de sklearn, variables, hiperparámetros, fechas de train
  y test y métricas. Permite saber con qué se entrenó el modelo que está en uso.
- `models/INFORME_MODELO.md`: lo mismo, legible, con la tabla de búsqueda y la importancia.
- **Inferencia integrada** (`predecir.py`): carga los últimos 10 días del histórico (no hace falta
  más para las features del último día), construye las features **con la misma función** que el
  entrenamiento (`construir_features`) y aplica el modelo a las filas de hoy.
- **Reentrenamiento**: semanal (los lunes) en GitHub Actions. Predecir es diario. Reentrenar cada
  día no aporta: un día más sobre meses de histórico apenas cambia el modelo.

## 11. Hugging Face

| | |
| --- | --- |
| Tarea | `chat_completion` |
| Modelo | `meta-llama/Llama-3.1-8B-Instruct` (variable `HF_MODEL`) |
| Papel | Post-proceso: redacta la predicción de sklearn para un conductor |

- **sklearn calcula, el LLM redacta.** El LLM recibe un resumen ya calculado y tiene prohibido
  inventar cifras o causas. El informe incluye la tabla original para contrastar.
- **Borde tipado**: la entrada (`ResumenPrediccion`) y la salida (`Explicacion`) son modelos
  pydantic, igual que el contrato de estaciones de la primera parte. El resto del código no sabe
  qué proveedor hay detrás.
- **Misma interfaz, dos clientes** (`ClienteIA`): `ClienteMock` (plantilla fija, sin red) y
  `ClienteHF`. Se elige con `AI_PROVIDER`. Cambiar a OpenAI o Anthropic sería escribir una tercera
  clase con el método `explicar`, sin tocar nada más.
- **Mock obligatorio en tests y CI**: sin token, sin red, resultado reproducible y gratis.
- **Respaldo**: si Hugging Face falla, se registra el error y se usa el mock. La predicción
  numérica nunca depende de que la API esté disponible.

## 12. Tests

`uv run pytest` — todos sin conexión a internet.

| Fichero | Qué comprueba |
| --- | --- |
| `test_features.py` | Objetivo y retardos calculados a mano; huecos de días; que el Brent no usa el futuro |
| `test_modelo.py` | Separación y particiones temporales; métricas; **guardar → cargar → predecir**; categorías nuevas y valores vacíos |
| `test_ia.py` | Contratos; mock determinista; cliente HF con un cliente falso inyectado; respaldo al mock |
| `test_pipeline_modelo.py` | **Integración** (`@pytest.mark.integration`): histórico → entrenar → predecir → informe, y los códigos de salida |
| `test_mercados.py`, `test_historico.py`, `test_ingesta.py`, `test_loader.py` | Ingesta, reintentos e histórico |
| `test_metrics.py`, `test_cli.py` | Primera parte |

- Los tests del modelo usan un **histórico sintético** (`crear_historico_sintetico` en
  `conftest.py`): precios inventados que siguen al Brent con retraso. Como ahí la señal existe por
  construcción, se puede exigir que el modelo mejore a la persistencia.
- `pytest -m hf_real` hace una llamada real a Hugging Face (se salta si no hay token).

## 13. Robustez

- **Reintentos** con espera creciente en cada descarga (el servicio del Ministerio se cae a veces).
- **Métodos de conexión alternativos** (`loader.py`). El servidor del Ministerio cortaba la conexión
  segura cuando la abría Python, aunque desde el navegador funcionaba. Cada descarga prueba, en
  orden: `requests` normal, `requests` con una configuración TLS más compatible y el programa
  `curl` del sistema. Se recuerda el que funciona. Nunca se desactiva la verificación del certificado.
- **El backfill se detiene** tras 3 días seguidos fallidos, en vez de insistir con todos; al
  repetirlo continúa donde se quedó.
- **Excepciones de dominio**: `DataLoadError`, `ValidationError`, `ModelError`, `IAError`.
- **Códigos de salida** distintos por tipo de fallo, para que GitHub Actions marque el error:

| Comando | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| `ingesta` | correcto | ninguna estación válida | error de descarga | — |
| `entrenar` | correcto | datos insuficientes | no hay histórico | — |
| `predecir` | correcto | — | no hay histórico | no hay modelo |

- **Logs** por pantalla y en `logs/<comando>.log`.
- **Configuración** por variables de entorno (`.env` en local, secretos en Actions). `.env` está
  en `.gitignore`; `.env.example` documenta las variables.
- **Ingesta idempotente**: repetir un día no duplica datos; un día fallido del backfill no detiene
  el resto.

## 14. Limitaciones (dichas con honestidad)

- **Histórico corto.** Con pocos meses no se ven todos los escenarios (subidas fuertes del crudo,
  cambios de impuestos). El modelo mejora a medida que el pipeline acumula días.
- **Cambios fiscales.** Un cambio de IVA o de impuesto especial mueve todos los precios de golpe y
  el modelo no puede anticiparlo. Solución futura: una variable de "régimen fiscal".
- **Retraso del Brent.** Usar el dato de hace 10 días es prudente pero pierde información. Con una
  fuente de precios diaria sin retraso (de pago) se podría reducir.
- **Sin precios mayoristas** de gasolina y gasóleo, que son el predictor más directo y no son
  gratuitos.
- **Horizonte de un día.** Predecir a una semana sería más útil para el conductor y es más difícil.

## 15. Continuidad hacia el Proyecto III

| Ya está (Proyecto II) | Se añadirá (Proyecto III) |
| --- | --- |
| `predecir_manana()` como función independiente | Endpoint `/predict` de una API (FastAPI) |
| `consultar.py`: filtros por estación, municipio, provincia, marca y carburante | Los mismos filtros como parámetros de `/predict` |
| `ClienteIA.explicar()` con contratos pydantic | Endpoint `/analyze` |
| Predicción diaria guardada | **Monitorización**: comparar la predicción de ayer con el precio real de hoy y vigilar si el error crece |
| Reentrenamiento semanal en Actions | Reentrenar cuando el error supere un umbral |
| CLI y workflows | Despliegue |

El núcleo (`features.py`, `modelo.py`, `ia.py`) no depende de la línea de comandos: una API puede
llamar a las mismas funciones sin reescribir nada.

## 16. Preguntas probables y respuesta corta

**¿Por qué no predices directamente el precio?**
Porque el precio de mañana es casi el de hoy y cualquier modelo parecería perfecto. Predigo la
variación para medirme contra "mañana igual que hoy".

**¿Cómo sabes que no hay fuga de información?**
Separación por fechas, validación cruzada por días, Brent retrasado 10 días por su retraso de
publicación, relleno solo hacia delante y control de huecos. Hay tests de cada cosa.

**¿Por qué gradient boosting y no una regresión lineal?**
Porque capta interacciones entre variables y acepta vacíos y categóricas. La lineal también se
entrena y aparece en el informe como comparación.

**¿Qué hiperparámetros has ajustado y cómo?**
Tasa de aprendizaje, número de árboles y hojas por árbol; 8 combinaciones con `GridSearchCV` y
validación temporal de 3 particiones, optimizando RMSE.

**¿Por qué el MAE del modelo no es mejor que el de la persistencia?** (si ocurre)
Porque la mayoría de días el precio no cambia y predecir 0 acierta de pleno. El modelo gana donde
importa: los días en que el precio se mueve (RMSE y acierto de dirección).

**¿Qué pasa si se cae la API de Hugging Face? ¿Y la del Ministerio?**
Hugging Face: se usa el mock y el pipeline termina bien. Ministerio: tres reintentos; si falla,
código de salida 2 y el workflow aparece en rojo; al día siguiente el backfill recupera el hueco.

**¿Por qué el modelo de Hugging Face no hace la predicción?**
Un LLM no es fiable calculando y no se puede evaluar con métricas como un regresor. Cada pieza
hace lo que sabe: sklearn los números, el LLM el texto.

**¿Por qué no usas el id de la estación como variable?**
Para que aprenda reglas generales y funcione con estaciones nuevas, en vez de memorizar.

**¿Cada cuánto se reentrena?**
Cada lunes; la predicción es diaria.

**¿Qué has hecho tú y qué la IA?**
Está en `AI_USAGE.md`.

## 17. Guion de demo (5 minutos)

```bash
uv run pytest                                   # 1. todo pasa, sin red
uv run python -m pipeline_dsia.ingesta          # 2. descarga de hoy → historico/
uv run python -m pipeline_dsia.entrenar         # 3. búsqueda + métricas (enseñar models/INFORME_MODELO.md)
uv run python -m pipeline_dsia.predecir         # 4. predicción + explicación (enseñar data/informe_prediccion.md)
uv run python -m pipeline_dsia.consultar --provincia madrid --carburante gasoleo_a   # 5. consulta concreta
```

Después, enseñar en GitHub la pestaña **Actions** con las ejecuciones diarias y los commits
automáticos de `historico/`.
