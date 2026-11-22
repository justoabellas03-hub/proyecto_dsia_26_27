# Ejercicio E1 · Pipeline de calidad de datos de ventas

Parte A del Proyecto I de DSIA (curso 2026-27). El programa lee un CSV de ventas,
separa las filas válidas de las erróneas, calcula métricas de negocio y guarda
las ventas limpias junto con un resumen de calidad.

## Instalación

Hace falta [uv](https://docs.astral.sh/uv/) y Python 3.12 o superior.

```bash
cd parte_a/ejercicio_ventas
uv sync
```

## Uso

```bash
uv run python -m ejercicio_ventas                      # usa data/ventas.csv y escribe en data/
uv run python -m ejercicio_ventas --entrada otro.csv --salida resultados --top 5
uv run ejercicio-ventas --help                         # mismo programa, como comando
```

| Opción      | Por defecto      | Descripción                          |
|-------------|------------------|--------------------------------------|
| `--entrada` | `data/ventas.csv`| CSV de ventas de entrada             |
| `--salida`  | `data`           | Carpeta donde se guardan los ficheros|
| `--top`     | `3`              | Número de productos del ranking      |

Si el fichero no existe, faltan columnas o `--top` no es válido, el programa
muestra el error y termina con código 1.

### Ejemplo de salida (CSV del curso)

```
Ventas válidas: 140 · inválidas: 10
...
Calidad de datos: {'filas_totales': 150, 'filas_validas': 140, 'filas_invalidas': 10, 'importe_total': 96598.17}
```

## Datos

`data/ventas.csv` tiene una fila por venta con estas columnas:

| Columna           | Tipo   | Ejemplo      |
|-------------------|--------|--------------|
| `fecha`           | texto  | `2026-01-09` |
| `region`          | texto  | `Sur`        |
| `producto`        | texto  | `Cable Kit`  |
| `unidades`        | entero | `7`          |
| `precio_unitario` | real   | `12.5`       |
| `cliente_id`      | texto  | `C005`       |

**Regla de validación:** una venta es válida si `unidades` y `precio_unitario`
son números mayores que 0. Las vacías, no numéricas, cero o negativas van a errores.
A las válidas se les añade `importe = unidades × precio_unitario`.

Salidas en la carpeta `--salida`:

- `ventas_limpias.csv`: ventas válidas con la columna `importe`.
- `calidad_datos.json`: filas totales, válidas, inválidas e importe total.

## Estructura

```
ejercicio_ventas/
├── data/                   CSV de entrada y resultados
├── src/ejercicio_ventas/
│   ├── loader.py           leer el CSV y guardar resultados (E/S)
│   ├── validator.py        esquema (columnas obligatorias) y reglas por fila
│   ├── metrics.py          importe por región, top productos, clientes habituales, resumen
│   ├── cli.py              argumentos (argparse) y orquestación del pipeline
│   └── __main__.py         permite `python -m ejercicio_ventas`
└── tests/
    ├── conftest.py         datos de prueba compartidos
    ├── test_loader.py
    ├── test_validator.py
    ├── test_metrics.py
    ├── test_cli.py
    └── test_integration.py pipeline completo con el CSV real
```

Cada módulo tiene una única responsabilidad: `cli` solo encadena
`loader → validator → metrics → loader`, así que cada pieza se puede probar por separado.

## Tests

```bash
uv run pytest                                   # todos
uv run pytest -m "not integration"              # solo unitarios
uv run pytest --cov=ejercicio_ventas --cov-report=term-missing
```

Se ejecutan automáticamente en GitHub Actions con cada push y pull request
(workflow común del repositorio: `.github/workflows/ci.yml`).

## Licencia

MIT. Ver [`LICENSE`](../../LICENSE) en la raíz del repositorio.
