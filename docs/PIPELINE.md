# Pipeline de la parte B · precios de carburantes

Todos los pasos se lanzan con `python -m pipeline_dsia <comando>`.

```mermaid
flowchart TD
    API["API del Ministerio<br/><small>precios diarios por gasolinera</small>"]:::fuente
    MER_SRC["FRED y BCE<br/><small>Brent y EUR/USD</small>"]:::fuente

    CARGA["Carga y validación<br/><small>loader.py → contrato pydantic (validator.py)</small>"]:::p1
    MER["Mercados<br/><small>loader.py</small>"]:::p2

    METRICAS["Métricas del día<br/><small>metrics.py → data/gasolineras_metricas.csv</small>"]:::p1
    HIST["Histórico<br/><small>historico/ · un fichero por día</small>"]:::p2

    FEAT["Features<br/><small>modelo.py · variables y objetivo</small>"]:::p2
    ENT["Entrenar (los lunes)<br/><small>modelo.py · modelo sklearn → models/modelo.joblib</small>"]:::p2
    PRED["Predecir<br/><small>predecir.py · precio de mañana</small>"]:::p2
    IA["Explicación IA<br/><small>ia.py · Hugging Face o mock</small>"]:::p2
    CONS["Consultar<br/><small>predecir.py</small>"]:::p2

    API --> CARGA
    MER_SRC --> MER
    CARGA --> METRICAS
    CARGA --> HIST
    MER --> HIST
    HIST --> FEAT --> ENT --> PRED
    PRED --> IA
    PRED --> CONS

    classDef fuente fill:#F1EFE8,stroke:#5F5E5A,color:#444441
    classDef p1 fill:#EEEDFE,stroke:#534AB7,color:#3C3489
    classDef p2 fill:#E1F5EE,stroke:#0F6E56,color:#085041
```

Morado: Proyecto I (métricas del día, `python -m pipeline_dsia metricas`).
Verde: Proyecto II (ingesta histórica, modelo, predicción e IA).

## Etapas

| Etapa | Comando · módulo | Entrada | Salida |
|-------|--------|---------|--------|
| Carga | `metricas` · `loader.py` | API del Ministerio (JSON) | DataFrame crudo; reintentos y 3 métodos de conexión |
| Validación | `validator.py` | DataFrame crudo | Estaciones válidas + nº de inválidas (contrato pydantic, duplicados) |
| Métricas | `metricas` · `metrics.py` | Estaciones válidas | Medias por provincia y marca, ranking, CSV de métricas |
| Mercados | `ingesta` · `loader.py` | FRED (Brent) y BCE (EUR/USD) | Brent en €/barril |
| Histórico | `ingesta` · `historico.py` | Estaciones válidas + mercados | `historico/` con un fichero por día |
| Features | `entrenar`, `predecir` · `modelo.py` | Histórico | Variables y objetivo del modelo |
| Entrenar | `entrenar` · `modelo.py` | Features | `models/modelo.joblib`, métricas e informe |
| Predecir | `predecir` · `predecir.py` | Modelo + último día | Predicción de mañana e informe |
| Explicación | `predecir` · `ia.py` | Predicción | Texto explicativo (Hugging Face o mock) |
| Consultar | `consultar` · `predecir.py` | Predicciones | Filtros por provincia, municipio, estación o marca |

## Automatización

- `scripts/pipeline_local.ps1` (Programador de tareas de Windows): cada día ejecuta
  ingesta → entrenar (los lunes) → predecir y sube el histórico y el modelo al repo.
- `.github/workflows/pipeline_diario.yml`: lo mismo en GitHub Actions, lanzado a mano.
- `.github/workflows/ci.yml`: en cada push y pull request ejecuta los tests de las partes A y B.
