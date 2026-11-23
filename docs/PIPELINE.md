# Pipeline de la parte B · precios de carburantes

Todos los pasos se lanzan con `python -m pipeline_dsia <comando>`.

```mermaid
flowchart TD
    CLI["__main__.py: una sola línea de comandos<br/><small>metricas · ingesta · entrenar · predecir · consultar</small>"]:::comun

    API["API del Ministerio<br/><small>precios diarios por gasolinera</small>"]:::comun
    MER_SRC["FRED y BCE<br/><small>Brent y EUR/USD</small>"]:::comun

    LOADER["loader.py<br/><small>descargas con reintentos (precios y mercados)</small>"]:::comun
    VAL["validator.py<br/><small>contrato pydantic de cada estación</small>"]:::comun

    METRICAS["metrics.py<br/><small>comando metricas → data/gasolineras_metricas.csv</small>"]:::p1
    HIST["historico.py<br/><small>comando ingesta · un fichero por día</small>"]:::p2
    MODELO["modelo.py<br/><small>comando entrenar · features + sklearn → models/</small>"]:::p2
    PRED["predecir.py<br/><small>comandos predecir y consultar → data/</small>"]:::p2
    IA["ia.py<br/><small>Hugging Face o mock</small>"]:::p2

    CONFIG["config.py: lo usan todos los módulos<br/><small>constantes, excepciones, variables de entorno y logs</small>"]:::comun

    CLI ~~~ API
    CLI ~~~ MER_SRC
    API --> LOADER
    MER_SRC --> LOADER
    LOADER --> VAL
    LOADER -- mercados --> HIST
    VAL --> METRICAS
    VAL --> HIST
    HIST --> MODELO --> PRED --> IA
    IA ~~~ CONFIG

    classDef comun fill:#F1EFE8,stroke:#5F5E5A,color:#444441
    classDef p1 fill:#EEEDFE,stroke:#534AB7,color:#3C3489
    classDef p2 fill:#E1F5EE,stroke:#0F6E56,color:#085041
```

Morado: Proyecto I (métricas del día). Verde: Proyecto II (histórico, modelo, predicción e IA).
Gris: fuentes y módulos comunes. `config.py` (abajo) lo importan todos los módulos.

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
