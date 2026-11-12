"""Cliente de IA: explica en lenguaje natural la predicción del modelo sklearn.

Reparto de papeles:
    - sklearn calcula los números (cuánto variará cada precio).
    - El modelo de Hugging Face (tarea chat_completion) solo los REDACTA: recibe
      un resumen ya calculado y escribe un párrafo para el usuario. No predice nada.

Diseño:
    - Contratos tipados (pydantic) de entrada (ResumenPrediccion) y salida (Explicacion).
    - Dos clientes con la misma interfaz (ClienteIA): ClienteMock y ClienteHF.
    - En tests y CI se usa siempre el mock: sin red, sin token y con resultado fijo.
    - Si Hugging Face falla, el pipeline no se cae: se usa el mock como respaldo.
"""

import logging
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from pipeline_dsia.config import Configuracion
from pipeline_dsia.exceptions import IAError

log = logging.getLogger(__name__)

NOMBRES = {
    "gasolina_95": "gasolina 95", "gasolina_98": "gasolina 98",
    "gasoleo_a": "gasóleo A", "gasoleo_premium": "gasóleo premium",
}

INSTRUCCIONES = (
    "Eres un analista de precios de carburantes en España. Redacta en español un párrafo "
    "breve (máximo 120 palabras) y claro para conductores que explique la previsión de mañana. "
    "Usa ÚNICAMENTE las cifras que se te dan: no inventes datos, causas ni noticias. "
    "Recuerda al final que es una estimación de un modelo estadístico."
)


# --- Contratos ---------------------------------------------------------------------

class ResumenCarburante(BaseModel):
    carburante: str
    precio_medio_hoy: float = Field(gt=0)             # €/l
    variacion_media_cts: float                        # céntimos; positivo = sube
    pct_suben: float = Field(ge=0, le=100)            # % de estaciones con subida prevista ≥ 0,5 céntimos
    pct_bajan: float = Field(ge=0, le=100)            # % de estaciones con bajada prevista ≥ 0,5 céntimos


class ResumenPrediccion(BaseModel):
    fecha_prediccion: date
    var_brent_7: float | None = None                  # variación % del Brent en 7 días (dato con ~10 días de retraso)
    carburantes: list[ResumenCarburante] = Field(min_length=1)


class Explicacion(BaseModel):
    texto: str = Field(min_length=1)
    proveedor: Literal["mock", "hf"]
    modelo: str


class ClienteIA(Protocol):
    def explicar(self, resumen: ResumenPrediccion) -> Explicacion: ...


# --- Texto común --------------------------------------------------------------------

def resumen_a_texto(resumen: ResumenPrediccion) -> str:
    """Los números del resumen en frases cortas (es lo que se le envía al modelo de chat)."""
    lineas = [f"Previsión para el {resumen.fecha_prediccion:%d/%m/%Y}."]
    if resumen.var_brent_7 is not None:
        lineas.append(f"Brent en euros, variación en 7 días según el último dato disponible "
                      f"(se publica con unos 10 días de retraso): {resumen.var_brent_7:+.1f} %.")
    for c in resumen.carburantes:
        lineas.append(
            f"{NOMBRES.get(c.carburante, c.carburante)}: precio medio hoy {c.precio_medio_hoy:.3f} €/l, "
            f"variación media prevista {c.variacion_media_cts:+.2f} céntimos, "
            f"{c.pct_suben:.0f} % de estaciones con subida prevista de al menos medio céntimo "
            f"y {c.pct_bajan:.0f} % con bajada de al menos medio céntimo."
        )
    return "\n".join(lineas)


# --- Cliente mock ---------------------------------------------------------------------

class ClienteMock:
    """Explicación con una plantilla fija: mismo resumen → mismo texto. Sin red."""

    def explicar(self, resumen: ResumenPrediccion) -> Explicacion:
        frases = []
        for c in resumen.carburantes:
            if abs(c.variacion_media_cts) < 0.05:
                tendencia = "se mantendrá estable"
            else:
                tendencia = f"{'subirá' if c.variacion_media_cts > 0 else 'bajará'} unos {abs(c.variacion_media_cts):.2f} céntimos de media"
            frases.append(f"la {NOMBRES.get(c.carburante, c.carburante)} {tendencia}"
                          if c.carburante.startswith("gasolina")
                          else f"el {NOMBRES.get(c.carburante, c.carburante)} {tendencia}")
        texto = f"Para el {resumen.fecha_prediccion:%d/%m/%Y} el modelo prevé que " + "; ".join(frases) + "."
        if resumen.var_brent_7 is not None:
            texto += (f" El último dato disponible del Brent en euros (llega con unos 10 días de retraso) "
                      f"muestra una variación del {resumen.var_brent_7:+.1f} % en 7 días.")
        texto += " Es una estimación de un modelo estadístico."
        return Explicacion(texto=texto, proveedor="mock", modelo="plantilla")


# --- Cliente Hugging Face ---------------------------------------------------------------

class ClienteHF:
    """Tarea chat_completion de la Inference API de Hugging Face.

    Args:
        token: HF_TOKEN.
        modelo: Id del modelo en el Hub (owner/name).
        cliente: Objeto con el método chat_completion. Por defecto se crea un
            InferenceClient; en los tests se inyecta uno falso para no usar la red.
    """

    def __init__(self, token: str, modelo: str, cliente=None, timeout: float = 30.0):
        self.modelo = modelo
        if cliente is None:
            try:
                from huggingface_hub import InferenceClient
            except ImportError as exc:
                raise IAError("Falta la librería huggingface_hub (uv sync)") from exc
            cliente = InferenceClient(api_key=token, timeout=timeout)
        self.cliente = cliente

    def explicar(self, resumen: ResumenPrediccion) -> Explicacion:
        mensajes = [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": resumen_a_texto(resumen)},
        ]
        try:
            respuesta = self.cliente.chat_completion(mensajes, model=self.modelo, max_tokens=300, temperature=0.2)
            texto = (respuesta.choices[0].message.content or "").strip()
        except Exception as exc:   # red, token no válido, modelo no disponible, respuesta rara...
            raise IAError(f"Fallo en Hugging Face ({self.modelo}): {exc}") from exc
        if not texto:
            raise IAError(f"Hugging Face ({self.modelo}) devolvió una respuesta vacía")
        return Explicacion(texto=texto, proveedor="hf", modelo=self.modelo)


# --- Selección del cliente y respaldo ------------------------------------------------------

def crear_cliente(config: Configuracion) -> ClienteIA:
    """mock por defecto; hf solo si AI_PROVIDER=hf y hay token."""
    if config.ai_provider == "hf":
        if not config.hf_token:
            log.warning("AI_PROVIDER=hf pero falta HF_TOKEN: se usa el mock")
            return ClienteMock()
        try:
            return ClienteHF(config.hf_token, config.hf_model)
        except IAError as exc:
            log.warning("%s: se usa el mock", exc)
            return ClienteMock()
    if config.ai_provider != "mock":
        log.warning("AI_PROVIDER='%s' no reconocido: se usa el mock", config.ai_provider)
    return ClienteMock()


def explicar_con_respaldo(cliente: ClienteIA, resumen: ResumenPrediccion) -> Explicacion:
    """Si el proveedor real falla, se registra el error y se responde con el mock."""
    try:
        return cliente.explicar(resumen)
    except IAError as exc:
        log.error("%s. Se usa el mock como respaldo", exc)
        return ClienteMock().explicar(resumen)
