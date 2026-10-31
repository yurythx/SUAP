"""Fluxo do cartão vacinal (modo 2): cadastro, doses, aprazamentos e histórico.

O Enfermeiro registra o cartão vacinal do aluno pelo prontuário — cadastro do cartão, inclusão
de vacina, dose, reforço e aprazamento, com as remoções pelos próprios botões — e o aluno vê o
próprio cartão no autoatendimento. A importação do RN+Vacina fica de fora: é chamada a API
externa do Ministério da Saúde (coberta por teste unitário com mock, em `saude/tests`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRONTUARIO = '/saude/prontuario/{}/'
ADICIONAR_VACINA = '/saude/adicionar_vacina/{}/'
ADICIONAR_CARTAO = '/saude/adicionar_cartao_vacinal/{}/'
REGISTRAR_VACINACAO = '/saude/registrar_vacinacao/{}/'  # popup do cartão vacinal
REGISTRAR_PREVISAO = '/saude/registrar_previsao/{}/'
HISTORICO_CARTAO = '/saude/historico_cartao_vacinal/{}/'
CARTAO_VACINAL = '/saude/cartao_vacinal/'
ADICIONAR_CARTAO_ALUNO = '/saude/adicionar_cartao_vacinal_aluno/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def test_cartao_vacinal_do_aluno(logado_saude: Callable[[str], Page]) -> None:
    """O Enfermeiro monta o cartão vacinal: cartão, vacina, dose, aprazamento e histórico."""
    tela = Tela(logado_saude('enfermeiro'))

    from saude.models import CartaoVacinal, Vacina

    aluno, prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário').clicar_aba('Cartão Vacinal')

    tela.clicar_botao('Adicionar Cartão Vacinal')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CARTAO.format(vinculo.pk)}$'))
    tela.preencher('Cartão Vacinal', 'Arquivo', 'arquivo.pdf')
    tela.clicar_botao('Salvar').sucesso('Cartão vacinal cadastrado com sucesso.')
    prontuario.refresh_from_db()
    assert prontuario.cartao_vacinal, 'a UI disse que salvou, mas o arquivo do cartão vacinal não persistiu'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.clicar_botao('Adicionar Vacina')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_VACINA.format(prontuario.pk)}$'))
    tela.preencher('Vacina', 'Lista', 'Tríplice Viral')
    tela.clicar_botao('Adicionar').sucesso('Vacina adicionada com sucesso.')
    vacina = Vacina.objects.get(nome='Tríplice Viral')
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina).exists(), 'a UI disse que adicionou, mas a vacina não entrou no cartão'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    # "Adicionar Dose" e "Adicionar Reforço" são ações por GET: criam a linha e voltam para o
    # cartão com a mensagem, sem tela intermediária.
    tela.quadro('Tríplice Viral').clicar_botao('Adicionar Dose')
    tela.sucesso('Dose de Vacina adicionada com sucesso.')
    # "Adicionar Vacina" já cria a primeira dose; "Adicionar Dose" cria a segunda. O ciclo de
    # registrar/aprazar/remover é exercitado sobre a primeira (a linha que o box lista antes).
    registro = CartaoVacinal.objects.get(prontuario=prontuario, vacina=vacina, numero_dose=1, eh_reforco=False)

    # O "Registrar Vacinação" da dose é o que grava data e procedência; ele abre em popup
    # (classe `popup` no template), então o formulário é preenchido dentro do iframe.
    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').linha('Registrar Vacinação').clicar_botao('Registrar Vacinação')
    popup = tela.popup()
    popup.preencher_formulario([('Data da Vacinação', 'Data', '21/01/2019'), ('Observação', 'TextArea', 'Vacinação E2E')])
    popup.salvar_no_popup('Registrar Vacinação')
    tela.sucesso('Registro de vacinação adicionado com sucesso.')
    registro.refresh_from_db()
    assert registro.data_vacinacao is not None, 'a UI disse que registrou, mas a data da vacinação não persistiu'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').linha('1ª').clicar_botao('Adicionar Aprazamento')
    expect(tela.pagina).to_have_url(re.compile(rf'{REGISTRAR_PREVISAO.format(registro.pk)}$'))
    tela.preencher('Previsão da Vacinação', 'Data', '21/02/2019')
    tela.clicar_botao('Salvar').sucesso('Aprazamento adicionado com sucesso.')
    registro.refresh_from_db()
    assert registro.data_prevista is not None, 'a UI disse que aprazou, mas a previsão não persistiu'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').linha('1ª').clicar_botao('Remover Aprazamento')
    tela.sucesso('Aprazamento removido com sucesso.')
    registro.refresh_from_db()
    assert registro.data_prevista is None, 'a UI disse que removeu, mas o aprazamento permanece'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').clicar_botao('Adicionar Reforço')
    tela.sucesso('Reforço de Vacina adicionado com sucesso.')
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina, eh_reforco=True).exists(), (
        'a UI disse que adicionou o reforço, mas ele não entrou no cartão'
    )

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    # O histórico abre em popup (classe `popup` no template): o documento é o do iframe.
    tela.clicar_botao('Historico do Cartão Vacinal')
    historico = tela.popup()
    historico.ver_titulo('Histórico do Cartão Vacinal').ver_texto('Aluno Saúde')

    # A remoção da dose é oferecida na linha, e a mensagem do produto é a de "adicionada"
    # (copy-paste na view) — o teste assere o texto real e o efeito no ORM.
    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').linha('1ª').clicar_botao('Remover Dose')
    tela.sucesso('Dose de Vacina adicionada com sucesso.')
    assert not CartaoVacinal.objects.filter(pk=registro.pk).exists(), 'a UI disse que removeu, mas a dose permanece'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Cartão Vacinal')
    tela.quadro('Tríplice Viral').clicar_botao('Remover Vacina')
    tela.sucesso('Vacina removida com sucesso.')
    assert not CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina).exists(), 'a UI disse que removeu, mas a vacina permanece no cartão'


def test_aluno_ve_o_proprio_cartao_vacinal(logado_saude: Callable[[str], Page]) -> None:
    """O próprio aluno abre o autoatendimento do cartão vacinal e anexa o cartão."""
    tela = Tela(logado_saude('aluno'))

    from saude.models import Prontuario

    _aluno, prontuario = _aluno_e_prontuario()
    tela.ir(CARTAO_VACINAL).ver_titulo('Cartão Vacinal')

    if not prontuario.cartao_vacinal:
        tela.clicar_botao('Adicionar Cartão Vacinal')
        expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CARTAO_ALUNO}$'))
        tela.preencher('Cartão Vacinal', 'Arquivo', 'arquivo.pdf')
        tela.clicar_botao('Salvar').sucesso('Cartão vacinal cadastrado com sucesso.')
        prontuario = Prontuario.objects.get(pk=prontuario.pk)
        assert prontuario.cartao_vacinal, 'a UI disse que salvou, mas o cartão do aluno não persistiu'
