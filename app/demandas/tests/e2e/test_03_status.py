"""Fluxo: desenvolvimento, entregas, sub-demandas, homologação e conclusão (feature 003).

Depois de aprovada, a demanda entra em desenvolvimento e passa a receber entregas. Registrar uma
entrega leva a demanda para "Em homologação"; a etapa sai dali pela resposta do demandante:
reprovar ou cancelar devolve ao desenvolvimento, e aprovar a entrega que cobre todas as
especificações deixa a demanda "Homologada". As sub-demandas só nascem numa demanda raiz. A
cadeia é sequencial: depende da demanda aprovada de ``test_02``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from demandas.tests.e2e.apoio import marcar_modulo
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VISUALIZAR = '/demandas/visualizar/{}/'
ALTERAR_SITUACAO = '/demandas/alterar_situacao/{}/{}/'
NOVA_ENTREGA = '/demandas/demanda/{}/entrega/nova/'
ENTREGA_APROVAR = '/demandas/entrega/{}/aprovar/'
ENTREGA_REPROVAR = '/demandas/entrega/{}/reprovar/'
ENTREGA_CANCELAR = '/demandas/entrega/{}/cancelar/'
NOVA_SUBDEMANDA = '/demandas/demanda/{}/subdemanda/nova/'
REORDENAR_SUBDEMANDAS = '/demandas/demanda/{}/subdemanda/reordenar/'

COMENTARIO = 'Comentário da Situação'
PREVISAO = '01/02/2019'
CONCLUSAO = '01/01/2019'


def demanda_da_cadeia() -> Demanda:
    """A demanda aberta por ``test_01`` — âncora dos demais arquivos da cadeia."""
    from demandas.models import Demanda

    demanda = Demanda.objects.filter(titulo='Demanda 1').first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    return demanda


def alterar_etapa(tela: Tela, demanda: Demanda, etapa: str, menu: str = 'Alterar etapa') -> None:
    """Abre o menu de ações da demanda e clica na etapa pedida, conferindo a rota do produto.

    O produto distribui as etapas em dois menus: o fluxo normal em "Alterar etapa" e as
    situações de saída (Suspender, Cancelar) em "Outras opções".
    """
    tela.ir(VISUALIZAR.format(demanda.pk))
    tela.clicar_botao(menu)
    expect(tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(demanda.pk, etapa)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(demanda.pk, etapa)}"]').click()
    tela.esperar()


def test_analista_avanca_para_desenvolvimento(logado_demandas: Callable[[str], Page]) -> None:
    """O analista leva a demanda aprovada para "Em desenvolvimento"."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import Situacao

    demanda = demanda_da_cadeia()
    assert demanda.situacao == Situacao.ESTADO_APROVADO, 'a cadeia exige a demanda aprovada'

    alterar_etapa(tela, demanda, 'Desenvolver')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_SITUACAO.format(demanda.pk, "Desenvolver")}$'))
    tela.preencher_formulario([('Comentário', 'TextArea', COMENTARIO), ('Previsão', 'Data', PREVISAO)])
    tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'a UI disse que alterou a etapa, mas a demanda não mudou'


def _nova_entrega(tela: Tela, demanda: Demanda, titulo: str, especificacoes: tuple[str, ...] = (), prazo: str = '01/03/2019') -> object:
    """Registra uma entrega pelo popup da aba Entregas, confere a ida para homologação e devolve o registro."""
    from demandas.models import Entrega, Situacao

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Entregas')
    tela.aba('Entregas').clicar_botao('Nova entrega')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Título da entrega', 'Texto', titulo),
            ('O que está sendo entregue', 'TextArea', 'Correção do relatório E2E'),
            ('Prazo para o demandante responder', 'Data', prazo),
        ]
    )
    for especificacao in especificacoes:
        popup.campo('Especificações entregues', 'checkbox multiplo', especificacao).check()
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Entrega registrada. A demanda está em homologação.')
    entrega = Entrega.objects.filter(demanda=demanda, titulo=titulo).first()
    assert entrega is not None, 'a UI disse que registrou a entrega, mas ela não persistiu'
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_HOMOLOGACAO, 'registrar a entrega precisa levar a demanda para homologação'
    return entrega


def test_entregas_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """A entrega leva a demanda à homologação; reprovar ou cancelar a devolve ao desenvolvimento."""
    analista = Tela(logado_demandas('analista'))
    demandante = Tela(logado_demandas('demandante'))

    from demandas.models import Entrega, Situacao, StatusEntrega

    demanda = demanda_da_cadeia()
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'a cadeia exige a demanda em desenvolvimento'

    # Quem entregou não valida: o analista não vê Aprovar nem Reprovar.
    reprovada = _nova_entrega(analista, demanda, 'Entrega reprovada E2E')
    analista.ir(VISUALIZAR.format(demanda.pk)).ver_status('Em homologação').clicar_aba('Entregas')
    expect(analista.aba('Entregas').botao('Aprovar')).to_have_count(0)

    # Reprovação: exige o motivo e devolve a demanda ao desenvolvimento.
    demandante.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Entregas')
    expect(demandante.aba('Entregas').botao('Reprovar')).to_have_attribute('href', ENTREGA_REPROVAR.format(reprovada.pk))
    demandante.aba('Entregas').clicar_botao('Reprovar')
    popup = demandante.popup()
    popup.preencher('Motivo da reprovação', 'TextArea', 'Falta o filtro por campus')
    popup.salvar_no_popup('Enviar')
    demandante.sucesso('Entrega reprovada. Demanda retornou para desenvolvimento.')
    reprovada.refresh_from_db()
    demanda.refresh_from_db()
    assert reprovada.status == StatusEntrega.REPROVADA, 'a UI disse que reprovou, mas a entrega não mudou'
    assert reprovada.motivo_rejeicao == 'Falta o filtro por campus', 'o motivo da reprovação não persistiu'
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'a reprovação devolve a demanda ao desenvolvimento'

    # Cancelamento: o analista descarta a entrega antes da resposta do demandante.
    cancelada = _nova_entrega(analista, demanda, 'Entrega cancelada E2E')
    analista.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Entregas')
    expect(analista.aba('Entregas').botao('Cancelar entrega')).to_have_attribute('href', ENTREGA_CANCELAR.format(cancelada.pk))
    analista.aba('Entregas').clicar_botao('Cancelar entrega')
    analista.sucesso('Entrega cancelada. Demanda retornou para desenvolvimento.')
    cancelada.refresh_from_db()
    demanda.refresh_from_db()
    assert cancelada.status == StatusEntrega.CANCELADA, 'a UI disse que cancelou, mas a entrega não mudou'
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'o cancelamento devolve a demanda ao desenvolvimento'
    assert Entrega.objects.filter(demanda=demanda, status=StatusEntrega.ENVIADA).count() == 0, 'nenhuma entrega podia continuar aguardando resposta'


def test_subdemandas_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O analista cria sub-demandas, reordena a prioridade interna e as cancela."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import Demanda, Situacao

    demanda = demanda_da_cadeia()
    criadas = []
    for titulo in ('Sub-demanda A E2E', 'Sub-demanda B E2E'):
        tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Sub-demandas')
        tela.aba('Sub-demandas').clicar_botao('Nova sub-demanda')
        popup = tela.popup()
        popup.preencher_formulario(
            [
                ('Título da sub-demanda', 'Texto', titulo),
                ('Descrição', 'TextArea', f'Descrição da {titulo}'),
                ('Tipo', 'Lista', 'Melhoria'),
            ]
        )
        marcar_modulo(popup, 'Tag Especial')
        popup.salvar_no_popup('Salvar')
        tela.sucesso(f'Sub-demanda "{titulo}" criada com sucesso.')
        criadas.append(Demanda.objects.get(titulo=titulo))
    assert all(sub.parent_id == demanda.pk for sub in criadas), 'as sub-demandas precisam apontar para a demanda pai'
    assert criadas[0].prioridade_interna < criadas[1].prioridade_interna, 'a primeira sub-demanda nasce com prioridade menor'

    # A reordenação é AJAX de arrastar-e-soltar: o endpoint recebe a nova ordem na query.
    resposta = tela.buscar(f'{REORDENAR_SUBDEMANDAS.format(demanda.pk)}?subdemandas={criadas[1].pk},{criadas[0].pk}')
    assert resposta.status == 200, 'o endpoint de reordenação precisa responder 200'
    assert resposta.json().get('ok') is True, f'a reordenação foi recusada: {resposta.text()}'
    criadas[0].refresh_from_db()
    criadas[1].refresh_from_db()
    assert criadas[1].prioridade_interna < criadas[0].prioridade_interna, 'a UI disse que reordenou, mas a prioridade não mudou'

    # O pai só conclui sem sub-demandas ativas: as duas são canceladas pelo analista.
    for sub in criadas:
        alterar_etapa(tela, sub, 'Cancelar', menu='Outras opções')
        tela.preencher('Comentário', 'TextArea', COMENTARIO)
        tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
        sub.refresh_from_db()
        assert sub.situacao == Situacao.ESTADO_CANCELADO, 'a UI disse que cancelou a sub-demanda, mas ela continua ativa'
    demanda.refresh_from_db()
    assert demanda.pode_concluir_pai, 'com as sub-demandas canceladas o pai pode ser concluído'
    assert demanda.percentual_conclusao == 100, 'o progresso do pai conta as sub-demandas encerradas'


def test_demandante_aprova_a_entrega_que_cobre_o_escopo(logado_demandas: Callable[[str], Page]) -> None:
    """Quem entrega tudo de uma vez usa "Homologar": a entrega vem preenchida e, aprovada, deixa a demanda Homologada."""
    analista = Tela(logado_demandas('analista'))
    demandante = Tela(logado_demandas('demandante'))

    from demandas.models import Entrega, Situacao, StatusEntrega

    demanda = demanda_da_cadeia()
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'a cadeia exige a demanda em desenvolvimento'
    assert demanda.get_dod().especificacao_set.exists(), 'a cadeia exige a consolidação com especificações (test_02)'

    # "Homologar" é atalho para o cadastro da entrega, já com tudo o que falta marcado e o prazo sugerido.
    alterar_etapa(analista, demanda, 'Homologar')
    expect(analista.pagina).to_have_url(re.compile(rf'{NOVA_ENTREGA.format(demanda.pk)}\?homologar=1$'))
    analista.clicar_botao('Salvar').sucesso('Entrega registrada. A demanda está em homologação.')
    aprovada = Entrega.objects.get(demanda=demanda, status=StatusEntrega.ENVIADA)
    assert set(aprovada.especificacoes.all()) == set(demanda.get_dod().especificacao_set.all()), 'o atalho entrega todas as especificações'
    demandante.ir(VISUALIZAR.format(demanda.pk)).ver_status('Em homologação').clicar_aba('Entregas')
    expect(demandante.aba('Entregas').botao('Aprovar')).to_have_attribute('href', ENTREGA_APROVAR.format(aprovada.pk))
    demandante.aba('Entregas').clicar_botao('Aprovar')
    demandante.popup().salvar_no_popup('Enviar')
    demandante.sucesso('Entrega aprovada. A demanda está "Homologada".')
    aprovada.refresh_from_db()
    demanda.refresh_from_db()
    assert aprovada.status == StatusEntrega.APROVADA, 'a UI disse que aprovou, mas a entrega não mudou'
    assert demanda.situacao == Situacao.ESTADO_HOMOLOGADA, 'a entrega que cobre o escopo deixa a demanda Homologada'


def test_analista_implanta_e_conclui(logado_demandas: Callable[[str], Page]) -> None:
    """O analista implanta a demanda homologada e a conclui."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import Situacao

    demanda = demanda_da_cadeia()
    assert demanda.situacao == Situacao.ESTADO_HOMOLOGADA, 'a cadeia exige a demanda homologada'

    alterar_etapa(tela, demanda, 'Implantar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_SITUACAO.format(demanda.pk, "Implantar")}$'))
    tela.preencher_formulario([('Comentário', 'TextArea', COMENTARIO), ('Previsão', 'Data', PREVISAO), ('ID Merge-request', 'Número', '25')])
    tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_IMPLANTACAO, 'a UI disse que alterou a etapa, mas a demanda não mudou'
    assert demanda.id_merge_request == 25, 'o ID do merge request não persistiu'

    alterar_etapa(tela, demanda, 'Concluir')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_SITUACAO.format(demanda.pk, "Concluir")}$'))
    tela.preencher_formulario([('Comentário', 'TextArea', COMENTARIO), ('Conclusão', 'Data', CONCLUSAO)])
    tela.clicar_botao('Enviar').sucesso('A etapa da demanda foi alterada.')
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_CONCLUIDO, 'a UI disse que concluiu, mas a demanda não ficou Concluída'
    assert demanda.eh_situacao_terminal(), 'a demanda concluída precisa ser terminal'

    tela.ir(VISUALIZAR.format(demanda.pk)).ver_status('Concluída')
