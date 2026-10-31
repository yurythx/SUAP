"""Fluxo do atendimento multidisciplinar (modo 2): a ficha de procedimentos compartilhada.

O atendimento multidisciplinar é a ficha em que médico, odontólogo, nutricionista ou psicólogo
registram os procedimentos do cuidado compartilhado. Aqui o Nutricionista abre o atendimento
pelo prontuário e registra os procedimentos — o mesmo caminho que a tela oferece a qualquer um
dos papéis que gerenciam esse atendimento.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Atendimento, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ATENDIMENTO = '/saude/atendimento_multidisciplinar/{}/'
ADICIONAR_PROCEDIMENTO = '/saude/adicionar_procedimento_multidisciplinar/{}/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento_multidisciplinar() -> Atendimento:
    """O atendimento multidisciplinar mais recente materializado pela tela."""
    from saude.models import Atendimento, TipoAtendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=TipoAtendimento.MULTIDISCIPLINAR).order_by('-id').first()
    assert atendimento is not None, 'o atendimento multidisciplinar não foi criado pela tela'
    return atendimento


def test_fluxo_multidisciplinar(logado_saude: Callable[[str], Page]) -> None:
    """O Nutricionista abre o atendimento multidisciplinar e registra os procedimentos."""
    tela = Tela(logado_saude('nutricionista'))

    from saude.models import AtendimentoMultidisciplinar, SituacaoAtendimento, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento Multidisciplinar')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_multidisciplinar/\d+/$'))
    tela.esperar().sucesso('Atendimento Multidisciplinar gerado com sucesso.').ver_titulo('Atendimento Multidisciplinar')
    atendimento = _ultimo_atendimento_multidisciplinar()
    assert atendimento.tipo == TipoAtendimento.MULTIDISCIPLINAR, 'a UI abriu um tipo de atendimento incorreto'
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'

    tela.clicar_aba('Procedimentos').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_PROCEDIMENTO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [('Procedimentos', 'FilteredSelectMultiple', 'Atendimento Multiprofissional'), ('Observação', 'TextArea', 'Procedimento E2E')]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento multidisciplinar registrado com sucesso.')
    registro = AtendimentoMultidisciplinar.objects.filter(atendimento=atendimento).order_by('-id').first()
    assert registro is not None, 'a UI disse que salvou, mas a ficha multidisciplinar não persistiu'
    assert registro.procedimento.filter(denominacao='Atendimento Multiprofissional').exists(), (
        'a UI disse que salvou, mas o procedimento não persistiu na ficha'
    )
