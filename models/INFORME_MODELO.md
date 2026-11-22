# Informe del modelo

Generado automáticamente por `python -m pipeline_dsia.entrenar` el 2026-11-12 19:14.

## Datos

- Entrenamiento: 2026-06-08 → 2026-10-11 (4,228,603 filas)
- Test: 2026-10-12 → 2026-11-11 (1,036,363 filas)
- Una fila = estación × carburante × día. Objetivo: variación del precio al día siguiente (€/l).

## Hiperparámetros elegidos

- `learning_rate` = 0.05
- `max_iter` = 100
- `max_leaf_nodes` = 15

### Búsqueda (validación cruzada temporal, RMSE medio en céntimos)

| learning_rate | max_iter | max_leaf_nodes | rmse_validacion_cts |
| --- | --- | --- | --- |
| 0.05 | 100 | 15 | 2.5866 |
| 0.05 | 300 | 15 | 2.6456 |
| 0.1 | 100 | 15 | 2.6541 |
| 0.05 | 100 | 31 | 2.6682 |
| 0.1 | 300 | 15 | 2.6744 |
| 0.1 | 100 | 31 | 2.6864 |
| 0.05 | 300 | 31 | 2.696 |
| 0.1 | 300 | 31 | 2.7033 |

## Métricas en test (céntimos de €/l)

| modelo | mae_cts | rmse_cts | acierto_direccion |
| --- | --- | --- | --- |
| persistencia | 0.5419 | 1.3244 | 0.0 |
| ridge | 1.0826 | 1.453 | 71.4 |
| gradient_boosting | 0.8611 | 1.4389 | 74.3 |

El modelo **no mejora** a la persistencia en RMSE (-8.6 %).

- `mae_cts`: error medio absoluto. `rmse_cts`: castiga más los errores grandes.
- `acierto_direccion`: % de aciertos de subida/bajada cuando el precio cambió.
- En MAE la persistencia es muy difícil de batir: la mayoría de los días el precio no cambia, así que predecir 0 acierta de pleno casi siempre. El modelo se entrena para reducir el error cuadrático, es decir, para fallar menos los días en que el precio sí se mueve.

## Importancia de las variables

Aumento del RMSE (céntimos) al desordenar cada variable en el test:

| variable | aumento_rmse_cts |
| --- | --- |
| precio | 0.1623 |
| var_brent_14 | 0.0765 |
| var_nacional_1 | 0.0533 |
| dia_semana | 0.038 |
| dif_precio_7 | 0.0205 |
| carburante | 0.0083 |
| var_brent_7 | 0.0038 |
| dif_provincia | 0.0038 |
| dif_precio_3 | 0.0023 |
| id_provincia | 0.0014 |
| latitud | 0.0005 |
| tipo_venta | 0.0 |
| longitud | 0.0 |
| brent_eur | -0.0004 |
| dif_precio_1 | -0.0104 |
| var_provincia_1 | -0.0224 |
| var_brent_3 | -0.0257 |
