# Informe del modelo

Generado automáticamente por `python -m pipeline_dsia entrenar` el 2026-11-23 23:30.

## Datos

- Entrenamiento: 2026-06-08 → 2026-10-19 (4,496,615 filas)
- Test: 2026-10-20 → 2026-11-22 (1,138,196 filas)
- Una fila = estación × carburante × día. Objetivo: variación del precio al día siguiente (€/l).

## Hiperparámetros elegidos

- `learning_rate` = 0.05
- `max_iter` = 100
- `max_leaf_nodes` = 15

### Búsqueda (validación cruzada temporal, RMSE medio en céntimos)

| learning_rate | max_iter | max_leaf_nodes | rmse_validacion_cts |
| --- | --- | --- | --- |
| 0.05 | 100 | 15 | 2.4394 |
| 0.1 | 100 | 15 | 2.4685 |
| 0.05 | 100 | 31 | 2.4774 |
| 0.05 | 300 | 15 | 2.5142 |
| 0.1 | 300 | 15 | 2.5241 |
| 0.1 | 100 | 31 | 2.526 |
| 0.1 | 300 | 31 | 2.5417 |
| 0.05 | 300 | 31 | 2.5487 |

## Métricas en test (céntimos de €/l)

| modelo | mae_cts | rmse_cts | acierto_direccion |
| --- | --- | --- | --- |
| persistencia | 0.6569 | 1.5173 | 0.0 |
| ridge | 0.986 | 1.5091 | 73.2 |
| gradient_boosting | 0.8509 | 1.4736 | 81.7 |

El modelo **mejora** a la persistencia un 2.9 % en RMSE.

- `mae_cts`: error medio absoluto. `rmse_cts`: castiga más los errores grandes.
- `acierto_direccion`: % de aciertos de subida/bajada cuando el precio cambió.
- En MAE la persistencia es muy difícil de batir: la mayoría de los días el precio no cambia, así que predecir 0 acierta de pleno casi siempre. El modelo se entrena para reducir el error cuadrático, es decir, para fallar menos los días en que el precio sí se mueve.

## Importancia de las variables

Aumento del RMSE (céntimos) al desordenar cada variable en el test:

| variable | aumento_rmse_cts |
| --- | --- |
| var_nacional_1 | 0.0712 |
| precio | 0.0516 |
| dia_semana | 0.0163 |
| dif_precio_7 | 0.0083 |
| dif_precio_3 | 0.0081 |
| brent_eur | 0.0053 |
| var_brent_14 | 0.0023 |
| latitud | 0.0012 |
| var_provincia_1 | 0.0012 |
| dif_provincia | 0.0006 |
| tipo_venta | 0.0 |
| longitud | 0.0 |
| id_provincia | -0.0003 |
| carburante | -0.0022 |
| dif_precio_1 | -0.0027 |
| var_brent_3 | -0.0075 |
| var_brent_7 | -0.025 |
