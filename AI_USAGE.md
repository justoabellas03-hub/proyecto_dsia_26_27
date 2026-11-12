# Uso de IA en el proyecto

Este documento recoge dos cosas distintas: la IA que **forma parte del producto** (el modelo de
Hugging Face que usa el pipeline) y la IA usada **como ayuda para desarrollar** el código.

## 1. IA dentro del pipeline

| | |
| --- | --- |
| **Proveedor** | Hugging Face (Inference API, librería `huggingface_hub`, clase `InferenceClient`) |
| **Tarea** | `chat_completion` (generación de texto con un LLM) |
| **Modelo del Hub** | `meta-llama/Llama-3.1-8B-Instruct` (configurable con la variable `HF_MODEL`) |
| **Para qué** | Redactar en lenguaje natural la previsión que calcula el modelo scikit-learn |
| **Dónde** | `src/pipeline_dsia/ia.py` (cliente) y paso 4 de `src/pipeline_dsia/predecir.py` |
| **Credenciales** | `HF_TOKEN` en `.env` (local) o como secreto de GitHub Actions. Nunca en Git |

**Qué hace y qué no hace el LLM.** Las cifras las calcula siempre scikit-learn. El LLM recibe un
resumen ya calculado (precio medio, variación media prevista, % de estaciones que suben o bajan,
variación del Brent) y solo lo redacta. Las instrucciones le prohíben inventar datos o causas, y
el informe final incluye la tabla con las cifras originales para poder contrastar el texto.

**Modo mock.** `AI_PROVIDER=mock` (valor por defecto) usa `ClienteMock`, que genera el texto con
una plantilla fija: sin red, sin token y con resultado reproducible. **Los tests y la CI usan
siempre el mock.** Además, si Hugging Face falla (red, token, modelo no disponible), el pipeline
no se detiene: registra el error y usa el mock como respaldo.

**Test con el proveedor real.** `uv run pytest -m hf_real` hace una llamada real; se salta solo si
no hay `HF_TOKEN`.

## 2. IA como ayuda al desarrollo

| | |
| --- | --- |
| **Herramienta** | Claude (Anthropic), en modo asistente de programación |
| **Fechas** | Noviembre de 2026 |

**Qué generó la IA (y acepté tras revisarlo):**

- Módulos de la segunda parte: `mercados.py`, `historico.py`, `ingesta.py`, `features.py`,
  `modelo.py`, `entrenar.py`, `predecir.py`, `ia.py`, `config.py`, `registro.py`.
- Los tests de esos módulos y el generador de datos sintéticos de `test/conftest.py`.
- El workflow de GitHub Actions `pipeline_diario.yml`.
- Borradores de la documentación (README, `docs/DEFENSA.md` y este fichero).

**Qué decidí yo:**

- El dominio y los datos (precios de carburantes del Ministerio), el contrato de datos y las
  métricas de la primera parte.
- La idea de la segunda parte: añadir variables de mercado (Brent, EUR/USD) y predecir el precio
  del día siguiente con ingesta diaria programada.
- <!-- COMPLETAR: decisiones que hayas cambiado o ajustado tú al revisar el código -->

**Qué revisé y cómo lo comprobé:**

- Ejecuté los tests (`uv run pytest`) y el pipeline completo con datos reales
  (ingesta → entrenar → predecir).
- Revisé `models/INFORME_MODELO.md` para comprobar que las métricas tienen sentido frente a la
  persistencia.
- <!-- COMPLETAR: cualquier error que encontraras y cómo lo corregiste -->

**Qué no acepté o modifiqué:**

- <!-- COMPLETAR: si cambiaste algo de lo que propuso la IA, anótalo aquí. Si no, borra este apartado -->
