"""Tests de cli: argumentos y gestión de errores."""

from pathlib import Path

from ejercicio_ventas.cli import ENTRADA_POR_DEFECTO, SALIDA_POR_DEFECTO, crear_parser, main


def test_argumentos_por_defecto():
    args = crear_parser().parse_args([])
    assert args.entrada == ENTRADA_POR_DEFECTO
    assert args.salida == SALIDA_POR_DEFECTO
    assert args.top == 3


def test_argumentos_personalizados():
    args = crear_parser().parse_args(["--entrada", "x.csv", "--salida", "out", "--top", "5"])
    assert (args.entrada, args.salida, args.top) == (Path("x.csv"), Path("out"), 5)


def test_main_ok_con_rutas_propias(tmp_path, csv_mini, capsys):
    salida = tmp_path / "resultados"
    assert main(["--entrada", str(csv_mini), "--salida", str(salida), "--top", "2"]) == 0

    texto = capsys.readouterr().out
    assert "Ventas válidas: 4 · inválidas: 2" in texto
    assert "Top 2 productos" in texto
    assert (salida / "ventas_limpias.csv").exists()


def test_main_fichero_inexistente_devuelve_1(tmp_path, capsys):
    assert main(["--entrada", str(tmp_path / "no.csv"), "--salida", str(tmp_path)]) == 1
    assert "Error: No existe el fichero" in capsys.readouterr().err
    assert not (tmp_path / "ventas_limpias.csv").exists()


def test_main_csv_sin_columnas_devuelve_1(tmp_path, capsys):
    malo = tmp_path / "malo.csv"
    malo.write_text("a,b\n1,2\n", encoding="utf-8")
    assert main(["--entrada", str(malo), "--salida", str(tmp_path)]) == 1
    assert "Faltan columnas" in capsys.readouterr().err


def test_main_top_invalido_devuelve_1(csv_mini, tmp_path):
    assert main(["--entrada", str(csv_mini), "--salida", str(tmp_path), "--top", "0"]) == 1
