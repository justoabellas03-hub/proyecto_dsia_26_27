"""Test del pipeline completo (python -m ejercicio_ventas)."""

import json
import shutil

from ejercicio_ventas.__main__ import main

from conftest import CSV_CURSO


def test_pipeline_completo(tmp_path, monkeypatch, capsys):
    # Copiamos el CSV del curso a una carpeta temporal para no tocar data/ del proyecto
    (tmp_path / "data").mkdir()
    shutil.copy(CSV_CURSO, tmp_path / "data" / "ventas.csv")
    monkeypatch.chdir(tmp_path)

    main()

    salida = capsys.readouterr().out
    assert "Ventas válidas: 140 · inválidas: 10" in salida
    assert (tmp_path / "data" / "ventas_limpias.csv").exists()
    calidad = json.loads((tmp_path / "data" / "calidad_datos.json").read_text(encoding="utf-8"))
    assert calidad["filas_validas"] == 140
