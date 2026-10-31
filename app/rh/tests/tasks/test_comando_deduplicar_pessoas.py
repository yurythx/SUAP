import os
import stat
from io import StringIO
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa', 'pessoas_com_relacionamento')


def test_planejar_relatorio_aplicar(settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = str(tmp_path / 'media')  # o basetemp do pytest fica dentro do MEDIA_ROOT padrão do repo
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')
    saida = StringIO()

    call_command('deduplicar_pessoas', 'planejar', stdout=saida)
    csv = tmp_path / 'plano.csv'
    csv.write_text('conteudo antigo', encoding='utf-8')
    csv.chmod(0o644)
    call_command('deduplicar_pessoas', 'relatorio', '--csv', str(csv), stdout=saida)
    assert 'mesclada (pendente): 1' in saida.getvalue()
    assert stat.S_IMODE(os.stat(csv).st_mode) == 0o600
    call_command('deduplicar_pessoas', 'aplicar', stdout=saida)
    antes = len(saida.getvalue())
    call_command('deduplicar_pessoas', 'relatorio', stdout=saida)
    assert 'mesclada (aplicada): 1' in saida.getvalue()[antes:]

    assert 'mesclada: 1' in saida.getvalue()
    assert (tmp_path / 'plano.csv').read_text().startswith('id,pf_id,sobrevivente_id,documento,acao')
    assert 'mescladas: 1' in saida.getvalue()


def test_relatorio_recusa_csv_dentro_do_media(settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)

    with pytest.raises(CommandError):
        call_command('deduplicar_pessoas', 'relatorio', '--csv', str(tmp_path / 'plano.csv'))


@pytest.mark.parametrize('lote', ['0', '-5', 'x'])
def test_aplicar_recusa_lote_invalido(lote: str) -> None:
    with pytest.raises(CommandError):
        call_command('deduplicar_pessoas', 'aplicar', '--lote', lote)


def test_comando_roda_sem_historico_mesmo_com_ele_ligado(
    settings, caplog: pytest.LogCaptureFixture, django_capture_on_commit_callbacks: Callable[..., AbstractContextManager]
) -> None:
    PessoaFisicaFactory(cpf='529.982.247-25', nome_mae=''), PessoaFisicaFactory(cpf='529.982.247-25', nome_mae='Joana')
    settings.USE_HISTORY = True

    with caplog.at_level(logging.INFO, logger='history'), django_capture_on_commit_callbacks(execute=True):
        call_command('deduplicar_pessoas', 'planejar', stdout=StringIO())
        call_command('deduplicar_pessoas', 'aplicar', stdout=StringIO())

    assert [r for r in caplog.records if r.name == 'history'] == []
    assert PessoaFisica.objects.filter(cpf='529.982.247-25').count() == 1
    assert settings.USE_HISTORY  # o comando desliga só durante a execução


def _relatorio() -> list[str]:
    """As linhas da trava, na ordem (o BaseCommandPlus imprime as de início e fim do comando em volta)."""
    saida = StringIO()
    call_command('deduplicar_pessoas', 'relatorio', stdout=saida)
    return [linha for linha in saida.getvalue().splitlines() if linha.startswith('trava da 4.0.0')]


def test_relatorio_mostra_os_contadores_da_trava_da_4_0_0() -> None:
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')

    com_duplicata = _relatorio()
    call_command('deduplicar_pessoas', 'planejar', stdout=StringIO())
    call_command('deduplicar_pessoas', 'aplicar', stdout=StringIO())
    call_command('deduplicar_pessoas', 'planejar', stdout=StringIO())  # o portão do runbook: planejar + relatorio
    limpa = _relatorio()

    assert 'trava da 4.0.0 — cpf_repetido: 1' in com_duplicata
    assert com_duplicata[-1] == 'trava da 4.0.0: bloqueada'
    assert 'trava da 4.0.0 — cpf_repetido: 0' in limpa
    assert limpa[-1] == 'trava da 4.0.0: liberada'
