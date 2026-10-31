"""Fluxo: negociação e análise da consolidação (features 001 e 002 do behave).

O analista leva a demanda para "Em negociação", monta a consolidação (a descrição do DoD e as
especificações) e a encaminha para "Em análise" — que o produto recusa enquanto a consolidação
não estiver completa. O demandante então reprova (volta para negociação) e depois aprova, o que
leva a demanda para "Aprovada". A cadeia é sequencial: o teste depende da demanda de ``test_01``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from demandas.tests.e2e.apoio import esperar_editor_rico
from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VISUALIZAR = '/demandas/visualizar/{}/'
ALTERAR_SITUACAO = '/demandas/alterar_situacao/{}/{}/'
ESPECIFICACAO_ADD = '/demandas/especificacao/{}/{}/add/'
ESPECIFICACAO_CHANGE = '/demandas/especificacao/{}/{}/{}/change/'
ESPECIFICACAO_DELETE = '/demandas/especificacao/{}/{}/{}/delete/'
DOD_ALTERAR = '/demandas/dod/{}/{}/'
DOD_APROVAR = '/demandas/dod/{}/{}/aprovar/'
DOD_REPROVAR = '/demandas/dod/{}/{}/reprovar/'

COMENTARIO = 'Comentário da Situação'
PREVISAO = '01/02/2019'


def demanda_da_cadeia() -> Demanda:
    """A demanda aberta por ``test_01`` — âncora dos demais arquivos da cadeia."""
    from demandas.models import Demanda

    demanda = Demanda.objects.filter(titulo='Demanda 1').first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    return demanda


def confirmar_com_senha(tela: Tela) -> None:
    """Preenche o `ConfirmarComSenhaForm`: a senha do usuário e o aceite da operação.

    A senha é o `PasswordField` do djtools (`PasswordInput`), cujo rótulo não é irmão do input
    — por isso o alvo é o próprio campo pelo nome.
    """
    tela.loc('//input[@name="senha"]').fill(SENHA_E2E)
    tela.preencher('Confirma a operação', 'Checkbox', 'marcar')


def alterar_etapa(tela: Tela, demanda: Demanda, etapa: str) -> None:
    """Abre o menu "Alterar etapa" e clica na etapa pedida, conferindo a rota do produto."""
    tela.ir(VISUALIZAR.format(demanda.pk))
    tela.clicar_botao('Alterar etapa')
    expect(tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(demanda.pk, etapa)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(demanda.pk, etapa)}"]').click()
    tela.esperar()


def test_analista_negocia_e_monta_a_consolidacao(logado_demandas: Callable[[str], Page]) -> None:
    """O analista negocia, monta a consolidação e a encaminha para análise."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import DoD, Especificacao, Situacao

    demanda = demanda_da_cadeia()
    alterar_etapa(tela, demanda, 'Negociar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_SITUACAO.format(demanda.pk, "Negociar")}$'))
    tela.preencher('Comentário', 'TextArea', COMENTARIO)
    tela.preencher('Analistas', 'Autocomplete Multiplo', '105002')
    tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_NEGOCIACAO, 'a UI disse que alterou a etapa, mas a demanda não mudou'

    # A consolidação começa pela especificação; sem a descrição do DoD ela fica incompleta.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    tela.aba('Consolidação').clicar_botao('Adicionar especificação')
    dod = DoD.objects.get(demanda=demanda)
    expect(tela.pagina).to_have_url(re.compile(rf'{ESPECIFICACAO_ADD.format(demanda.pk, dod.pk)}$'))
    esperar_editor_rico(tela, 'id_atividades')
    tela.preencher_formulario([('Nome', 'Texto', 'Especificação 1'), ('Atividade(s)', 'Texto rico', 'Esta é uma atividade')])
    tela.clicar_botao('Salvar').sucesso('A especificação foi adicionada.')
    especificacao = Especificacao.objects.get(dod=dod, nome='Especificação 1')
    assert especificacao.atividades, 'a UI disse que adicionou, mas as atividades da especificação não persistiram'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    quadro = tela.quadro('Especificação 1')
    expect(quadro.botao('Editar')).to_have_attribute('href', ESPECIFICACAO_CHANGE.format(demanda.pk, dod.pk, especificacao.pk))
    quadro.clicar_botao('Editar')
    esperar_editor_rico(tela, 'id_atividades')
    tela.preencher_formulario([('Nome', 'Texto', 'Especificação 1 revisada'), ('Atividade(s)', 'Texto rico', 'Atividade revisada')])
    tela.clicar_botao('Salvar').sucesso('A especificação foi atualizada.')
    especificacao.refresh_from_db()
    assert especificacao.nome == 'Especificação 1 revisada', 'a UI disse que alterou, mas o nome da especificação não mudou'

    # A remoção é o ícone do próprio quadro da especificação (ação por GET).
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    tela.aba('Consolidação').clicar_botao('Adicionar especificação')
    esperar_editor_rico(tela, 'id_atividades')
    tela.preencher_formulario([('Nome', 'Texto', 'Especificação 2'), ('Atividade(s)', 'Texto rico', 'Atividade 2')])
    tela.clicar_botao('Salvar').sucesso('A especificação foi adicionada.')
    descartavel = Especificacao.objects.get(dod=dod, nome='Especificação 2')
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    tela.quadro('Especificação 2').clicar_botao('Remover')
    tela.sucesso('A especificação foi removida com sucesso.')
    assert not Especificacao.objects.filter(pk=descartavel.pk).exists(), 'a UI disse que removeu, mas a especificação permanece'

    # Com a especificação mas sem a descrição, o produto recusa o encaminhamento para análise
    # já na escolha da etapa (a view redireciona com o erro, sem chegar ao formulário).
    alterar_etapa(tela, demanda, 'Analisar')
    tela.erro('Não é possível alterar uma demanda para Em Análise caso ela não tenha Consolidação')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_NEGOCIACAO, 'a demanda não podia ter saído de Em negociação'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    expect(tela.aba('Consolidação').botao('Editar')).to_have_attribute('href', DOD_ALTERAR.format(demanda.pk, dod.pk))
    tela.aba('Consolidação').clicar_botao('Editar')
    tela.preencher_formulario([('Descrição', 'Texto', 'Consolidação da Demanda 1'), ('Novos Grupos de Usuários', 'TextArea', 'Grupos Envolvidos')])
    tela.clicar_botao('Salvar').sucesso('A demanda foi atualizada.')
    dod.refresh_from_db()
    assert dod.descricao == 'Consolidação da Demanda 1', 'a UI disse que atualizou, mas a descrição da consolidação não persistiu'
    assert dod.feito, 'a consolidação precisa ficar completa (descrição + especificação com atividades)'

    # Com a consolidação completa, o encaminhamento para análise passa a ser aceito.
    alterar_etapa(tela, demanda, 'Analisar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_SITUACAO.format(demanda.pk, "Analisar")}$'))
    tela.preencher_formulario([('Comentário', 'TextArea', COMENTARIO), ('Previsão', 'Data', PREVISAO)])
    tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_ANALISE, 'a UI disse que alterou a etapa, mas a demanda não mudou'
    assert demanda.get_dod().especificacao_set.filter(nome='Especificação 1 revisada').exists(), 'a especificação precisa continuar na consolidação'


def test_demandante_reprova_e_aprova_a_consolidacao(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante reprova a consolidação (volta a negociar) e depois aprova a demanda."""
    analista = Tela(logado_demandas('analista'))
    demandante = Tela(logado_demandas('demandante'))

    from demandas.models import DoD, Situacao

    demanda = demanda_da_cadeia()
    dod = DoD.objects.get(demanda=demanda)
    assert demanda.situacao == Situacao.ESTADO_EM_ANALISE, 'a cadeia exige a demanda em análise'

    demandante.ir(VISUALIZAR.format(demanda.pk)).ver_status('Em análise').clicar_aba('Consolidação')
    demandante.ver_texto('Consolidação da Demanda 1')
    expect(demandante.aba('Consolidação').botao('Reprovar')).to_have_attribute('href', DOD_REPROVAR.format(demanda.pk, dod.pk))
    demandante.aba('Consolidação').clicar_botao('Reprovar')
    expect(demandante.pagina).to_have_url(re.compile(rf'{DOD_REPROVAR.format(demanda.pk, dod.pk)}$'))
    confirmar_com_senha(demandante)
    demandante.clicar_botao('Enviar').sucesso('A consolidação da demanda foi reprovada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_NEGOCIACAO, 'a reprovação precisa devolver a demanda para Em negociação'

    # De volta à análise, o demandante aprova — e a demanda fica Aprovada.
    alterar_etapa(analista, demanda, 'Analisar')
    analista.preencher_formulario([('Comentário', 'TextArea', COMENTARIO), ('Previsão', 'Data', PREVISAO)])
    analista.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')

    demandante.ir(VISUALIZAR.format(demanda.pk)).ver_status('Em análise').clicar_aba('Consolidação')
    expect(demandante.aba('Consolidação').botao('Aprovar')).to_have_attribute('href', DOD_APROVAR.format(demanda.pk, dod.pk))
    demandante.aba('Consolidação').clicar_botao('Aprovar')
    expect(demandante.pagina).to_have_url(re.compile(rf'{DOD_APROVAR.format(demanda.pk, dod.pk)}$'))
    confirmar_com_senha(demandante)
    demandante.clicar_botao('Enviar').sucesso('A consolidação da demanda foi aprovada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_APROVADO, 'a UI disse que aprovou, mas a demanda não ficou Aprovada'
    assert demanda.aprovada, 'a demanda aprovada precisa responder `aprovada`'
