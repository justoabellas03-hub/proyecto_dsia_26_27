# Informe del modelo

Generado automáticamente por `python -m pipeline_dsia.entrenar` el 2026-11-12 17:43.

## Datos

- Entrenamiento: 2026-10-08 → 2026-11-04 (936,287 filas)
- Test: 2026-11-05 → 2026-11-11 (234,671 filas)
- Una fila = estación × carburante × día. Objetivo: variación del precio al día siguiente (€/l).

## Hiperparámetros elegidos

- `learning_rate` = 0.05
- `max_iter` = 100
- `max_leaf_nodes` = 15

### Búsqueda (validación cruzada temporal, RMSE medio en céntimos)

| learning_rate | max_iter | max_leaf_nodes | rmse_validacion_cts |
| --- | --- | --- | --- |
| 0.05 | 100 | 15 | 1.1641 |
| 0.1 | 100 | 15 | 1.1651 |
| 0.05 | 100 | 31 | 1.1677 |
| 0.05 | 300 | 15 | 1.1682 |
| 0.1 | 300 | 15 | 1.1718 |
| 0.05 | 300 | 31 | 1.1731 |
| 0.1 | 100 | 31 | 1.1733 |
| 0.1 | 300 | 31 | 1.1829 |

## Métricas en test (céntimos de €/l)

| modelo | mae_cts | rmse_cts | acierto_direccion |
| --- | --- | --- | --- |
| persistencia | 0.7836 | 1.8334 | 0.0 |
| ridge | 0.8683 | 1.7232 | 84.6 |
| gradient_boosting | 0.8404 | 1.7478 | 83.0 |

El modelo **mejora** a la persistencia un 4.7 % en RMSE.

- `mae_cts`: error medio absoluto. `rmse_cts`: castiga más los errores grandes.
- `acierto_direccion`: % de aciertos de subida/bajada cuando el precio cambió.
- En MAE la persistencia es muy difícil de batir: la mayoría de los días el precio no cambia, así que predecir 0 acierta de pleno casi siempre. El modelo se entrena para reducir el error cuadrático, es decir, para fallar menos los días en que el precio sí se mueve.

## Importancia de las variables

Aumento del RMSE (céntimos) al desordenar cada variable en el test:

| variable | aumento_rmse_cts |
| --- | --- |
| dif_precio_3 | 0.0321 |
| dia_semana | 0.009 |
| dif_precio_7 | 0.0085 |
| dif_precio_1 | 0.0082 |
| brent_eur | 0.007 |
| carburante | 0.0048 |
| var_provincia_1 | 0.0048 |
| latitud | 0.0039 |
| id_provincia | 0.003 |
| dif_provincia | 0.0019 |
| longitud | 0.0 |
| tipo_venta | 0.0 |
| var_brent_7 | -0.0005 |
| var_brent_14 | -0.0009 |
| precio | -0.001 |
| var_brent_3 | -0.0017 |
