"""Tests del cliente de IA. Nunca usan la red: mock o un cliente falso inyectado."""

import os
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from pipeline_dsia.config import Configuracion, cargar_env, leer_configuracion
from pipeline_dsia.exceptions import IAError
from pipeline_dsia.ia import (
    ClienteHF, ClienteMock, Explicacion, ResumenCarburante, ResumenPrediccion, crear_cliente,
    explicar_con_respaldo, resumen_a_texto,
)


@pytest.fixture
def resumen() -> ResumenPrediccion:
    return ResumenPrediccion(
        fecha_prediccion=date(2026, 11, 13), var_brent_7=4.2,
        carburantes=[
            ResumenCarburante(carburante="gasoleo_a", precio_medio_hoy=1.459, variacion_media_cts=0.8, pct_suben=60, pct_bajan=10),
            ResumenCarburante(carburante="gasolina_95", precio_medio_hoy=1.599, variacion_media_cts=-0.3, pct_suben=5, pct_bajan=40),
        ],
    )


class ChatFalso:
    """Imita a InferenceClient.chat_completion."""

    def __init__(self, texto="Mañana el gasóleo subirá ligeramente.", error=None):
        self.texto, self.error, self.llamadas = texto, error, []

    def chat_completion(self, mensajes, **kwargs):
        self.llamadas.append((mensajes, kwargs))
        if self.error:
            raise self.error
        mensaje = SimpleNamespace(content=self.texto)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensaje)])


# --- Contratos -------------------------------------------------------------------

def test_contrato_rechaza_porcentajes_imposibles():
    with pytest.raises(PydanticValidationError):
        ResumenCarburante(carburante="gasoleo_a", precio_medio_hoy=1.4, variacion_media_cts=0, pct_suben=120, pct_bajan=0)


def test_contrato_rechaza_explicacion_vacia():
    with pytest.raises(PydanticValidationError):
        Explicacion(texto="", proveedor="mock", modelo="plantilla")


def test_resumen_a_texto_incluye_las_cifras(resumen):
    texto = resumen_a_texto(resumen)
    assert "13/11/2026" in texto and "+4.2 %" in texto
    assert "gasóleo A" in texto and "+0.80 céntimos" in texto


# --- Mock ------------------------------------------------------------------------

def test_mock_devuelve_un_contrato_valido_y_determinista(resumen):
    explicacion = ClienteMock().explicar(resumen)
    assert isinstance(explicacion, Explicacion)
    assert explicacion.proveedor == "mock"
    assert "subirá unos 0.80 céntimos" in explicacion.texto
    assert "bajará unos 0.30 céntimos" in explicacion.texto
    assert explicacion == ClienteMock().explicar(resumen)


def test_mock_precio_estable(resumen):
    resumen.carburantes[0].variacion_media_cts = 0.01
    assert "se mantendrá estable" in ClienteMock().explicar(resumen).texto


# --- Hugging Face (con cliente falso) ----------------------------------------------

def test_cliente_hf_envia_el_resumen_y_devuelve_el_contrato(resumen):
    falso = ChatFalso()
    explicacion = ClienteHF("hf_test", "owner/modelo", cliente=falso).explicar(resumen)

    assert explicacion == Explicacion(texto="Mañana el gasóleo subirá ligeramente.", proveedor="hf", modelo="owner/modelo")
    mensajes, opciones = falso.llamadas[0]
    assert opciones["model"] == "owner/modelo"
    assert mensajes[0]["role"] == "system"
    assert "1.459" in mensajes[1]["content"]                # las cifras de sklearn van en el mensaje


@pytest.mark.parametrize("falso", [ChatFalso(error=TimeoutError("lento")), ChatFalso(texto="   ")])
def test_cliente_hf_convierte_los_fallos_en_iaerror(resumen, falso):
    with pytest.raises(IAError):
        ClienteHF("hf_test", "owner/modelo", cliente=falso).explicar(resumen)


def test_respaldo_al_mock_si_falla_hugging_face(resumen):
    cliente = ClienteHF("hf_test", "owner/modelo", cliente=ChatFalso(error=ConnectionError("sin red")))
    explicacion = explicar_con_respaldo(cliente, resumen)
    assert explicacion.proveedor == "mock"                  # el pipeline no se cae


# --- Selección del cliente y configuración --------------------------------------------

@pytest.mark.parametrize("proveedor, token", [("mock", None), ("hf", None), ("otro", "hf_x")])
def test_crear_cliente_usa_el_mock_por_defecto(proveedor, token):
    config = Configuracion(ai_provider=proveedor, hf_token=token, hf_model="owner/modelo")
    assert isinstance(crear_cliente(config), ClienteMock)


def test_leer_configuracion_por_defecto(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for variable in ("AI_PROVIDER", "HF_TOKEN", "HF_MODEL"):
        monkeypatch.delenv(variable, raising=False)
    config = leer_configuracion()
    assert config.ai_provider == "mock" and config.hf_token is None


def test_cargar_env_no_pisa_el_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("HF_MODEL", raising=False)
    fichero = tmp_path / ".env"
    fichero.write_text("# comentario\nAI_PROVIDER=hf\nHF_MODEL='owner/otro'\nlinea sin igual\n", encoding="utf-8")
    cargar_env(fichero)
    assert os.environ["AI_PROVIDER"] == "mock"              # manda el entorno
    assert os.environ["HF_MODEL"] == "owner/otro"
    monkeypatch.delenv("HF_MODEL")


@pytest.mark.hf_real
def test_hugging_face_real(resumen):
    """Llamada real a la Inference API. Solo se ejecuta si hay HF_TOKEN: pytest -m hf_real"""
    config = leer_configuracion()
    if not config.hf_token:
        pytest.skip("sin HF_TOKEN")
    explicacion = ClienteHF(config.hf_token, config.hf_model).explicar(resumen)
    assert explicacion.proveedor == "hf" and len(explicacion.texto) > 20
