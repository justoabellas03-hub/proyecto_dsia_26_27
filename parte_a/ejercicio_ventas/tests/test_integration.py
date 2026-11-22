"""Tests de integración: el pipeline completo con el CSV real del curso."""

import json
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from ejercicio_ventas.cli import main
from ejercicio_ventas.loader import cargar_ventas, guardar_resultados
from ejercicio_ventas.metrics import resumen_calidad
from ejercicio_ventas.validator import validar_ventas

from conftest import CSV_CURSO

pytestmark = pytest.mark.integration


def test_modulos_encadenados_con_el_csv_del_curso(tmp_path):
    df = cargar_ventas(CSV_CURSO)
    df_validos, df_errores = validar_ventas(df)
    calidad = resumen_calidad(df, df_validos, df_errores)
    ruta_csv, ruta_json = guardar_resultados(df_validos, calidad, tmp_path)

    assert (len(df_validos), len(df_errores)) == (140, 10)
    assert calidad["importe_total"] == pytest.approx(96598.17)
    assert len(pd.read_csv(ruta_csv)) == 140
    assert json.loads(ruta_json.read_text(encoding="utf-8")) == calidad


def test_cli_con_rutas_por_defecto(tmp_path, monkeypatch, capsys):
    # Copiamos el CSV del curso a una carpeta temporal para no tocar data/ del proyecto
    (tmp_path / "data").mkdir()
    shutil.copy(CSV_CURSO, tmp_path / "data" / "ventas.csv")
    monkeypatch.chdir(tmp_path)

    assert main([]) == 0

    assert "Ventas válidas: 140 · inválidas: 10" in capsys.readouterr().out
    calidad = json.loads((tmp_path / "data" / "calidad_datos.json").read_text(encoding="utf-8"))
    assert calidad["filas_validas"] == 140


def test_python_m_ejercicio_ventas(tmp_path):
    """Lanza el paquete como lo haría un usuario: python -m ejercicio_ventas."""
    resultado = subprocess.run(
        [sys.executable, "-m", "ejercicio_ventas", "--entrada", str(CSV_CURSO), "--salida", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert (tmp_path / "ventas_limpias.csv").exists()
