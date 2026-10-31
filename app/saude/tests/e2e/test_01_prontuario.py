"""Fluxo: busca e abertura dos prontuários de aluno e servidor (feature 0001).

A busca é a porta de entrada de todo atendimento do Saúde. Estes testes verificam os dois
tipos de vínculo usados pela feature e confirmam, depois da tela, que cada prontuário foi
materializado para a cadeia clínica de ``test_02_atendimento.py``.
"""

import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRONTUARIOS = '/saude/prontuarios/'
PRONTUARIO = '/saude/prontuario/{}/'


def _buscar(tela: Tela, termo: str, tipo_vinculo: str, nome: str) -> Tela:
    """Busca um vínculo e afirma que o cartão correto chegou à tela."""
    tela.ir(PRONTUARIOS)
    tela.preencher_formulario(
        [
            ('Buscar por Nome, Matrícula ou CPF', 'Texto', termo),
            ('Vínculo', 'Lista', tipo_vinculo),
        ]
    )
    tela.clicar_botao('Buscar').esperar()
    return tela.cartao(nome).ver_texto(termo)


def test_busca_e_abre_prontuario_do_aluno(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador localiza o aluno pela matrícula e abre seu prontuário."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    cartao = _buscar(tela, aluno.matricula, 'Aluno', 'Aluno Saúde')
    cartao.clicar_botao('Prontuário')
    expect(tela.pagina).to_have_url(re.compile(rf'{PRONTUARIO.format(vinculo.id)}$'))
    tela.esperar().ver_titulo('Prontuário')

    assert Prontuario.objects.filter(vinculo=vinculo).exists(), 'a UI abriu o prontuário, mas ele não persistiu'


def test_busca_e_abre_prontuario_do_servidor(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador localiza o próprio vínculo de servidor e abre o prontuário."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from rh.models import Servidor
    from saude.models import Prontuario

    servidor = Servidor.objects.get(matricula='111001')
    vinculo = servidor.get_vinculo()
    assert vinculo is not None, 'o servidor sintético não possui vínculo'
    cartao = _buscar(tela, servidor.matricula, 'Servidor', 'CoordSaudeSistemico')
    cartao.clicar_botao('Prontuário')
    expect(tela.pagina).to_have_url(re.compile(rf'{PRONTUARIO.format(vinculo.id)}$'))
    tela.esperar().ver_titulo('Prontuário')

    assert Prontuario.objects.filter(vinculo=vinculo).exists(), 'a UI abriu o prontuário, mas ele não persistiu'
