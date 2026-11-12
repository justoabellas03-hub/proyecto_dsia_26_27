"""Tests de la descarga: reintentos y métodos de conexión alternativos (sin red)."""

import subprocess
from types import SimpleNamespace

import pytest
import requests

import pipeline_dsia.loader as loader
from pipeline_dsia.exceptions import DataLoadError

JSON_OK = b'{"ListaEESSPrecio": [{"IDEESS": "1"}]}'


@pytest.fixture(autouse=True)
def sin_esperas_ni_memoria(monkeypatch):
    """Sin pausas entre intentos y sin método preferido heredado de otro test."""
    monkeypatch.setattr(loader.time, "sleep", lambda s: None)
    monkeypatch.setattr(loader, "_preferido", None)


def metodo_falso(contenido=JSON_OK, fallos=0, error=requests.ConnectionError("caída")):
    """Método de conexión que falla `fallos` veces y después devuelve `contenido`."""
    llamadas = []

    def metodo(url, timeout, cabeceras):
        llamadas.append((url, cabeceras))
        if len(llamadas) <= fallos:
            raise error
        return contenido

    metodo.llamadas = llamadas
    return metodo


def test_reintenta_y_acaba_funcionando(monkeypatch):
    metodo = metodo_falso(fallos=2)
    monkeypatch.setattr(loader, "METODOS", [metodo])
    df = loader.cargar_datos("http://x")
    assert len(metodo.llamadas) == 3
    assert df.loc[0, "IDEESS"] == "1"
    assert metodo.llamadas[0][1]["Accept"] == "application/json"


def test_se_rinde_tras_los_reintentos(monkeypatch):
    metodo = metodo_falso(fallos=99, error=requests.Timeout("lento"))
    monkeypatch.setattr(loader, "METODOS", [metodo])
    with pytest.raises(DataLoadError):
        loader.cargar_datos("http://x", reintentos=2)
    assert len(metodo.llamadas) == 2


def test_si_falla_la_conexion_segura_prueba_el_siguiente_metodo(monkeypatch):
    bloqueado = metodo_falso(fallos=99, error=requests.exceptions.SSLError("EOF occurred in violation of protocol"))
    alternativo = metodo_falso()
    monkeypatch.setattr(loader, "METODOS", [bloqueado, alternativo])

    assert loader.descargar("http://x").content == JSON_OK
    assert len(bloqueado.llamadas) == 1 and len(alternativo.llamadas) == 1

    # La siguiente descarga empieza directamente por el método que funcionó
    loader.descargar("http://y")
    assert len(bloqueado.llamadas) == 1 and len(alternativo.llamadas) == 2


def test_json_con_formato_inesperado(monkeypatch):
    monkeypatch.setattr(loader, "METODOS", [metodo_falso(contenido=b'{"otra": []}')])
    with pytest.raises(DataLoadError):
        loader.cargar_datos("http://x")


def test_respuesta_que_no_es_json(monkeypatch):
    monkeypatch.setattr(loader, "METODOS", [metodo_falso(contenido=b"<html>Service Unavailable</html>")])
    with pytest.raises(DataLoadError):
        loader.cargar_datos("http://x")


def test_respuesta_texto_quita_la_marca_bom():
    assert loader.Respuesta("﻿hola".encode("utf-8")).text == "hola"


def test_con_curl_devuelve_la_salida(monkeypatch):
    ordenes = []

    def run(orden, **kwargs):
        ordenes.append(orden)
        return SimpleNamespace(returncode=0, stdout=JSON_OK, stderr=b"")

    monkeypatch.setattr(loader, "ruta_curl", lambda: "curl")
    monkeypatch.setattr(loader.subprocess, "run", run)
    assert loader.con_curl("http://x", 30, {"Accept": "application/json"}) == JSON_OK
    assert ordenes[0][-1] == "http://x"
    assert "Accept: application/json" in ordenes[0]
    assert "--insecure" not in ordenes[0] and "-k" not in ordenes[0]      # nunca sin verificar el certificado


def test_con_curl_error(monkeypatch):
    monkeypatch.setattr(loader, "ruta_curl", lambda: "curl")
    monkeypatch.setattr(loader.subprocess, "run",
                        lambda orden, **kw: SimpleNamespace(returncode=35, stdout=b"", stderr=b"SSL connect error"))
    with pytest.raises(OSError, match="35"):
        loader.con_curl("http://x", 30, {})


def test_curl_no_instalado_cuenta_como_fallo_del_metodo(monkeypatch):
    def sin_curl():
        raise FileNotFoundError("curl no está instalado")

    monkeypatch.setattr(loader, "ruta_curl", sin_curl)
    monkeypatch.setattr(loader, "METODOS", [loader.con_curl, metodo_falso()])
    assert loader.descargar("http://x").content == JSON_OK


def test_adaptador_tls_compatible_no_desactiva_la_verificacion():
    adaptador = loader.AdaptadorTLSCompatible()
    contexto = adaptador.poolmanager.connection_pool_kw["ssl_context"]
    assert contexto.verify_mode == loader.ssl.CERT_REQUIRED
    assert contexto.maximum_version == loader.ssl.TLSVersion.TLSv1_2
