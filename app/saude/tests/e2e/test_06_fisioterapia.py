"""Fluxo do atendimento de fisioterapia (modo 2): anamnese, conduta, retorno, procedimentos e encaminhamento.

O Fisioterapeuta abre o atendimento pelo prontuário e percorre as abas que sustentam o
atendimento. O encaminhamento à avaliação médica é fechado pelo Médico na lista de prontuários —
é o único ponto em que o produto oferece `avaliar_encaminhamento_fisioterapia`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Atendimento, AtendimentoFisioterapia, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ATENDIMENTO = '/saude/atendimento_fisioterapia/{}/'
ADICIONAR_ANAMNESE = '/saude/adicionar_anamnese_fisioterapia/{}/'
ADICIONAR_CONDUTA = '/saude/adicionar_conduta_fisioterapia/{}/'
ADICIONAR_RETORNO = '/saude/adicionar_retorno_fisioterapia/{}/'
ADICIONAR_PROCEDIMENTO = '/saude/adicionar_procedimento_fisioterapia/{}/'
EDITAR_PROCEDIMENTO = '/saude/editar_procedimento_fisioterapia/{}/'
ADICIONAR_ENCAMINHAMENTO = '/saude/adicionar_encaminhamento_fisioterapia/{}/'
EDITAR_ENCAMINHAMENTO = '/saude/editar_encaminhamento_fisioterapia/{}/'
AVALIAR_ENCAMINHAMENTO = '/saude/avaliar_encaminhamento_fisioterapia/{}/'
PRONTUARIOS = '/saude/prontuarios/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento_fisioterapia() -> Atendimento:
    """O atendimento de fisioterapia mais recente materializado pela tela."""
    from saude.models import Atendimento, TipoAtendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=TipoAtendimento.FISIOTERAPIA).order_by('-id').first()
    assert atendimento is not None, 'o atendimento de fisioterapia não foi criado pela tela'
    return atendimento


def _fisio_do_atendimento(atendimento: Atendimento) -> AtendimentoFisioterapia:
    """O registro de atendimento de fisioterapia que as fichas alimentam."""
    from saude.models import AtendimentoFisioterapia

    registro = AtendimentoFisioterapia.objects.filter(atendimento=atendimento).order_by('-id').first()
    assert registro is not None, 'a ficha do atendimento de fisioterapia não foi criada'
    return registro


def test_fluxo_fisioterapia_completo(logado_saude: Callable[[str], Page]) -> None:
    """O Fisioterapeuta preenche as abas do atendimento e o Médico avalia o encaminhamento."""
    tela = Tela(logado_saude('fisioterapeuta'))

    from saude.models import (
        EncaminhamentoFisioterapia,
        ProcedimentoAtendimentoFisioterapia,
        SituacaoAtendimento,
        TipoAtendimento,
    )

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento de Fisioterapia')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_fisioterapia/\d+/$'))
    tela.esperar().sucesso('Atendimento de Fisioterapia gerado com sucesso.').ver_titulo('Atendimento de Fisioterapia')
    atendimento = _ultimo_atendimento_fisioterapia()
    assert atendimento.tipo == TipoAtendimento.FISIOTERAPIA, 'a UI abriu um tipo de atendimento incorreto'
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'

    tela.clicar_aba('Anamnese').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANAMNESE.format(atendimento.pk)}$'))
    tela.preencher('Anamnese', 'TextArea', 'Anamnese fisioterapêutica E2E')
    tela.clicar_botao('Salvar').sucesso('Anamnese registrada com sucesso.')
    registro = _fisio_do_atendimento(atendimento)
    assert registro.anamnese == 'Anamnese fisioterapêutica E2E', 'a UI disse que salvou, mas a anamnese não persistiu'

    tela.clicar_aba('Conduta de Fisioterapia').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CONDUTA.format(atendimento.pk)}$'))
    tela.preencher_formulario([('Conduta de Fisioterapia', 'TextArea', 'Conduta fisioterapêutica E2E'), ('Data do Retorno', 'Data', '28/01/2019')])
    tela.clicar_botao('Salvar').sucesso('Conduta de Fisioterapia registrada com sucesso.')
    registro.refresh_from_db()
    assert registro.conduta == 'Conduta fisioterapêutica E2E', 'a UI disse que salvou, mas a conduta não persistiu'

    tela.clicar_aba('Retorno').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_RETORNO.format(atendimento.pk)}$'))
    tela.preencher('Descrição da Evolução', 'TextArea', 'Evolução fisioterapêutica E2E')
    tela.clicar_botao('Salvar').sucesso('Evolução registrada com sucesso.')
    registro.refresh_from_db()
    assert registro.descricao_evolucao == 'Evolução fisioterapêutica E2E', 'a UI disse que salvou, mas a evolução não persistiu'

    tela.clicar_aba('Procedimentos').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_PROCEDIMENTO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [('Procedimentos', 'Autocomplete Multiplo', 'Fisioterapia Respiratória'), ('Observações', 'TextArea', 'Procedimento E2E')]
    )
    tela.clicar_botao('Salvar').sucesso('Procedimentos cadastrados com sucesso.')
    procedimento = ProcedimentoAtendimentoFisioterapia.objects.get(atendimento=registro, observacoes='Procedimento E2E')

    tela.clicar_aba('Procedimentos')
    tela.aba('Procedimentos').linha('Procedimento E2E').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_PROCEDIMENTO.format(procedimento.pk)}$'))
    tela.preencher('Observações', 'TextArea', 'Procedimento E2E revisado')
    tela.clicar_botao('Salvar').sucesso('Procedimentos editados com sucesso.')
    procedimento.refresh_from_db()
    assert procedimento.observacoes == 'Procedimento E2E revisado', 'a UI disse que editou, mas o procedimento não mudou'

    tela.clicar_aba('Procedimentos')
    tela.aba('Procedimentos').linha('Procedimento E2E revisado').clicar_icone('remoção')
    tela.sucesso('Procedimentos excluídos com sucesso.')
    assert not ProcedimentoAtendimentoFisioterapia.objects.filter(pk=procedimento.pk).exists(), 'a UI disse que excluiu, mas o procedimento permanece'

    tela.clicar_aba('Encaminhamento').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ENCAMINHAMENTO.format(atendimento.pk)}$'))
    tela.preencher('Descrição', 'TextArea', 'Encaminhamento fisioterapêutico E2E')
    tela.clicar_botao('Salvar').sucesso('Encaminhamento cadastrado com sucesso.')
    encaminhamento = EncaminhamentoFisioterapia.objects.get(atendimento=registro)

    tela.clicar_aba('Encaminhamento')
    tela.aba('Encaminhamento').linha('Encaminhamento fisioterapêutico E2E').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_ENCAMINHAMENTO.format(encaminhamento.pk)}$'))
    tela.preencher('Descrição', 'TextArea', 'Encaminhamento fisioterapêutico E2E revisado')
    tela.clicar_botao('Salvar').sucesso('Encaminhamento editado com sucesso.')
    encaminhamento.refresh_from_db()
    assert encaminhamento.descricao == 'Encaminhamento fisioterapêutico E2E revisado', 'a UI disse que editou, mas o encaminhamento não mudou'

    tela.clicar_aba('Encaminhamento')
    tela.aba('Encaminhamento').linha('Encaminhamento fisioterapêutico E2E revisado').clicar_icone('remoção')
    tela.sucesso('Encaminhamento excluído com sucesso.')
    assert not EncaminhamentoFisioterapia.objects.filter(pk=encaminhamento.pk).exists(), 'a UI disse que excluiu, mas o encaminhamento permanece'

    # Reencaminha para o Médico avaliar: o encaminhamento cria a pendência na lista de prontuários.
    tela.clicar_aba('Encaminhamento').clicar_botao('Adicionar')
    tela.preencher('Descrição', 'TextArea', 'Encaminhamento para avaliação médica E2E')
    tela.clicar_botao('Salvar').sucesso('Encaminhamento cadastrado com sucesso.')
    encaminhamento = EncaminhamentoFisioterapia.objects.get(atendimento=registro)
    registro.refresh_from_db()
    assert registro.encaminhado_medico, 'a UI disse que encaminhou, mas o atendimento não ficou pendente para o médico'

    tela_medico = Tela(logado_saude('medico')).ir(PRONTUARIOS)
    tela_medico.clicar_aba('Atendimentos encaminhados da Fisioterapia')
    tela_medico.linha('Aluno Saúde').clicar_botao('Avaliar')
    expect(tela_medico.pagina).to_have_url(re.compile(rf'{AVALIAR_ENCAMINHAMENTO.format(atendimento.pk)}$'))
    tela_medico.preencher('Avaliação Médica', 'TextArea', 'Avaliação médica do encaminhamento E2E')
    tela_medico.clicar_botao('Salvar').sucesso('Encaminhamento de fisioterapia avaliado com sucesso.')
    encaminhamento.refresh_from_db()
    assert encaminhamento.avaliacao_medica == 'Avaliação médica do encaminhamento E2E', 'a UI disse que avaliou, mas a avaliação médica não persistiu'
    assert encaminhamento.avaliado_em is not None, 'a avaliação médica não registrou a data'
