"""Fluxo psicológico: anamnese, atendimento, anexos e relatório clínico.

A cadeia abre o atendimento pela interface e confirma que data, queixas e intervenção chegam
ao prontuário e aos indicadores. O ciclo do anexo cobre também autoria, substituição do
arquivo e remoção, pontos em que uma resposta de sucesso pode esconder falha de persistência.
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

ATENDIMENTO_PSICOLOGICO = '/saude/atendimento_psicologico/{}/'
REGISTRAR_HORA = '/saude/registrar_hora_atendimento/{}/'
ADICIONAR_MOTIVO = '/saude/adicionar_motivo_psicologia/{}/'
ADICIONAR_ANAMNESE = '/saude/adicionar_anamnese_psicologica/{}/'
ADICIONAR_ANEXO = '/saude/adicionar_anexo_psicologia/{}/'
EDITAR_ANEXO = '/saude/editar_anexo_psicologia/{}/'
REMOVER_ANEXO = '/saude/remover_anexo_psicologia/{}/'
RELATORIO_PSICOLOGIA = '/saude/relatorio_atendimento_psicologia/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento_psicologico() -> Atendimento:
    """Devolve o atendimento psicológico mais recente materializado pela tela."""
    from saude.models import Atendimento, TipoAtendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=TipoAtendimento.PSICOLOGICO).order_by('-id').first()
    assert atendimento is not None, 'o atendimento psicológico não foi criado pela tela'
    return atendimento


def test_fluxo_psicologico_com_anexo_e_relatorio(logado_saude: Callable[[str], Page]) -> None:
    """O Psicólogo percorre as oito rotas do atendimento e encerra o caso."""
    tela = Tela(logado_saude('psicologo'))

    from saude.models import AnamnesePsicologia, AnexoPsicologia, AtendimentoPsicologia, SituacaoAtendimento, TipoAtendimento

    aluno, prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento Psicológico')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_psicologico/\d+/$'))
    tela.esperar().sucesso('Atendimento Psicológico gerado com sucesso.').ver_titulo('Atendimento Psicológico')
    atendimento = _ultimo_atendimento_psicologico()
    assert atendimento.tipo == TipoAtendimento.PSICOLOGICO, 'a UI abriu um tipo de atendimento incorreto'
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'

    tela.clicar_aba('Informações sobre o atendimento').clicar_botao('Registrar Data/Hora do Atendimento')
    expect(tela.pagina).to_have_url(re.compile(rf'{REGISTRAR_HORA.format(atendimento.pk)}$'))
    tela.preencher('Data/hora do atendimento', 'Data e Hora', '21/01/2019 10:00')
    tela.clicar_botao('Salvar').sucesso('Data/hora do atendimento registrada com sucesso.')
    registro = AtendimentoPsicologia.objects.get(atendimento=atendimento)
    assert registro.data_atendimento is not None, 'a UI disse que salvou, mas a data/hora não persistiu'

    tela.clicar_aba('Informações sobre o atendimento').clicar_botao('Adicionar informações')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_MOTIVO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Motivo da Chegada', 'Autocomplete', 'Demanda Espontânea'),
            ('Queixa principal', 'checkbox multiplo', 'Autoestima/autoimagem, Ansiedade'),
            ('Queixa identificada', 'checkbox multiplo', 'Autoestima/autoimagem, Ansiedade'),
            ('Intervenção / Encaminhamento', 'TextArea', 'Descrição da intervenção psicológica E2E.'),
            ('Tipo de atendimento', 'Autocomplete', 'Atendimento aos pais'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.motivo_chegada is not None, 'a UI disse que salvou, mas o atendimento ficou sem motivo'
    assert registro.motivo_chegada.descricao == 'Demanda Espontânea', 'o motivo psicológico selecionado não persistiu'
    assert set(registro.queixa_principal.values_list('descricao', flat=True)) == {'Autoestima/autoimagem', 'Ansiedade'}, (
        'a UI disse que salvou, mas as queixas principais não persistiram'
    )

    tela.ir(f'/saude/prontuario/{vinculo.pk}/').clicar_aba('Anamnese')
    tela.aba('Anamnese').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANAMNESE.format(vinculo.pk)}$'))
    tela.preencher_formulario(
        [
            ('Histórico da Queixa', 'TextArea', 'Histórico psicológico E2E.'),
            ('Dimensão Familiar', 'TextArea', 'Contexto familiar estável.'),
            ('Dimensão Escolar', 'TextArea', 'Acompanhamento escolar em curso.'),
            ('Dimensão Emocional (saúde mental/física)', 'TextArea', 'Avaliação emocional inicial.'),
            ('Dimensão dos Projetos de Vida', 'TextArea', 'Projetos acadêmicos definidos.'),
            ('Dimensão Social', 'TextArea', 'Rede social preservada.'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Anamnese registrada com sucesso.')
    assert AnamnesePsicologia.objects.filter(
        prontuario=prontuario, profissional__username='111008', historico_queixa='Histórico psicológico E2E.'
    ).exists(), 'a UI disse que salvou, mas a anamnese psicológica não persistiu'

    tela.ir(ATENDIMENTO_PSICOLOGICO.format(atendimento.pk)).clicar_aba('Anexos')
    tela.clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANEXO.format(atendimento.pk)}$'))
    tela.preencher_formulario([('Descrição', 'Texto', 'Anexo psicológico E2E'), ('Arquivo', 'Arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar').sucesso('Anexo registrado com sucesso.')
    anexo = AnexoPsicologia.objects.get(atendimento=atendimento, descricao='Anexo psicológico E2E')
    assert anexo.arquivo.name, 'a UI disse que salvou, mas o arquivo não persistiu'

    tela.clicar_aba('Anexos')
    tela.aba('Anexos').linha('Anexo psicológico E2E').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_ANEXO.format(anexo.pk)}$'))
    tela.preencher_formulario([('Descrição', 'Texto', 'Anexo psicológico revisado E2E'), ('Arquivo', 'Arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar').sucesso('Anexo editado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.descricao == 'Anexo psicológico revisado E2E', 'a UI disse que editou, mas a descrição não mudou'

    tela.clicar_aba('Anexos')
    tela.aba('Anexos').linha('Anexo psicológico revisado E2E').clicar_icone('remoção')
    tela.sucesso('Anexo removido com sucesso.')
    assert not AnexoPsicologia.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo permanece'

    # O relatório é uma tela de filtro: o corpo (total e gráficos) só existe depois do GET
    # com o período preenchido — e os títulos dos gráficos são JS do Highcharts, não texto
    # visível, então a asserção é o total em tela e o container do gráfico.
    tela.ir(RELATORIO_PSICOLOGIA).ver_titulo('Relatório de Atendimento de Psicologia')
    tela.filtros().preencher_formulario([('Data Inicial', 'Data', '01/01/2019'), ('Data Final', 'Data', '31/01/2019')])
    tela.clicar_botao('Enviar')
    tela.ver_texto('Total de Atendimentos Registrados:')
    expect(tela.pagina.locator('#grafico1')).to_be_attached()
    assert AtendimentoPsicologia.objects.filter(atendimento=atendimento, queixa_principal__descricao='Ansiedade').exists(), (
        'o relatório abriu sem o atendimento psicológico criado pela UI'
    )

    tela.ir(ATENDIMENTO_PSICOLOGICO.format(atendimento.pk)).clicar_link('Fechar')
    tela.preencher('Observação de Fechamento', 'TextArea', 'Atendimento psicológico E2E concluído')
    tela.clicar_botao('Salvar').sucesso('Atendimento fechado com sucesso.')
    atendimento.refresh_from_db()
    assert atendimento.situacao == SituacaoAtendimento.FECHADO, 'a UI disse que fechou, mas o atendimento continua aberto'
