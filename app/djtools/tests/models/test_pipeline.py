import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from django.conf import settings

from djtools.pipeline import LibSassCompiler


@pytest.fixture
def compiler():
    storage = MagicMock()
    storage.location = '/tmp'
    return LibSassCompiler(verbose=False, storage=storage)


@pytest.fixture
def fontes(tmp_path: Path) -> tuple[Path, Path]:
    """Tema que importa uma parcial de outro diretório, como os ``main.scss`` de ``djtools/themes``."""
    (tmp_path / 'default').mkdir()
    (tmp_path / 'default' / 'variables.scss').write_text('$cor: red;', encoding='utf-8')
    (tmp_path / 'tema').mkdir()
    entrada = tmp_path / 'tema' / 'main.scss'
    entrada.write_text('@import "../default/variables.scss";\n.cls { color: $cor; }', encoding='utf-8')
    return entrada, tmp_path / 'tema' / 'main.css'


class TestLibSassCompiler:
    def test_output_extension(self, compiler):
        assert compiler.output_extension == 'css'

    def test_match_file_sass(self, compiler):
        assert compiler.match_file('style.sass') is True

    def test_match_file_scss(self, compiler):
        assert compiler.match_file('style.scss') is True

    def test_match_file_other(self, compiler):
        assert compiler.match_file('style.css') is False
        assert compiler.match_file('script.js') is False
        assert compiler.match_file('file.txt') is False

    def test_compile_file_debug_mode(self, compiler, fontes):
        entrada, saida = fontes
        with patch.object(settings, 'DEBUG', True):
            compiler.compile_file(str(entrada), str(saida), outdated=True)
        assert saida.read_text(encoding='utf-8') == '.cls {\n  color: red; }\n'

    def test_compile_file_production_mode(self, compiler, fontes):
        entrada, saida = fontes
        with patch.object(settings, 'DEBUG', False):
            compiler.compile_file(str(entrada), str(saida), outdated=True)
        assert saida.read_text(encoding='utf-8').strip() == '.cls{color:red}'
        assert not list(saida.parent.glob('.*.tmp'))

    def test_compile_file_em_dia_nao_reescreve(self, compiler, fontes):
        entrada, saida = fontes
        saida.write_text('antigo', encoding='utf-8')
        os.utime(saida, (entrada.stat().st_mtime + 10,) * 2)
        compiler.compile_file(str(entrada), str(saida))
        assert saida.read_text(encoding='utf-8') == 'antigo'

    def test_compile_file_force_reescreve(self, compiler, fontes):
        entrada, saida = fontes
        saida.write_text('antigo', encoding='utf-8')
        os.utime(saida, (entrada.stat().st_mtime + 10,) * 2)
        with patch.object(settings, 'DEBUG', False):
            compiler.compile_file(str(entrada), str(saida), force=True)
        assert saida.read_text(encoding='utf-8').strip() == '.cls{color:red}'

    def test_compile_file_parcial_nova_recompila(self, compiler, fontes):
        entrada, saida = fontes
        saida.write_text('antigo', encoding='utf-8')
        parcial = entrada.parent.parent / 'default' / 'variables.scss'
        os.utime(saida, (parcial.stat().st_mtime - 10,) * 2)
        os.utime(entrada, (parcial.stat().st_mtime - 20,) * 2)
        with patch.object(settings, 'DEBUG', False):
            compiler.compile_file(str(entrada), str(saida))
        assert saida.read_text(encoding='utf-8').strip() == '.cls{color:red}'

    def test_match_file_none(self, compiler):
        assert compiler.match_file('') is False
