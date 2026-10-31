"""Fluxo: solicitações de documento funcional — acompanhar, atender e rejeitar.

O servidor pede a via de um documento (carteira funcional, crachá) e a Gestão de Pessoas despacha:
atende ou rejeita com motivo. As três telas deste arquivo são o lado de quem despacha — a de
acompanhamento, que reúne o histórico da solicitação, e as duas que mudam o estado dela.

A regressão que o arquivo pega é a do **estado**: atender e rejeitar são transições de mão única
(``pode_atender_solicitacao``/``pode_rejeitar_solicitacao`` só valem enquanto a situação for
"Não Atendida"). A mensagem de sucesso só sai quando o registro muda, e a transição recusada
responde erro (#17393); a asserção no ORM confirma o desfecho que a tela anunciou.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
VER_SOLICITACAO = '/comum/ver_solicitacao_documento/{pk}/'
MARCAR_ATENDIDA = '/comum/marcar_solicitacao_atendida/{pk}/'
REJEITAR = '/comum/rejeitar_solicitacao/{pk}/'


def test_acompanhar_e_atender_solicitacao(logado_comum, solicitacao_documento):
    """Abre a solicitação, confere o histórico e a atende pelo botão da própria tela.

    As duas rotas num teste só porque a segunda é a ação que a primeira publica: o endereço de
    atendimento não é montado pelo teste, é o ``href`` do botão. Afirmá-lo antes de clicar é o que
    liga a ação à solicitação certa — clicar num botão achado pelo rótulo provaria só que existe
    um botão com aquele texto.

    O histórico não é decoração: cada transição grava um ``DocumentoControleHistorico``, e é essa
    trilha que a Gestão de Pessoas usa para justificar o despacho meses depois.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle

    _, solicitacao = solicitacao_documento
    url_atender = MARCAR_ATENDIDA.format(pk=solicitacao.pk)

    tela = Tela(logado_comum('gestor_pessoal')).ir(VER_SOLICITACAO.format(pk=solicitacao.pk))
    tela.ver_texto('Histórico da Solicitação')
    tela.ver_texto(solicitacao.justificativa)
    tela.ver_texto('Não Atendida')

    botao = tela.loc(f'//a[@href="{url_atender}"]').first
    assert botao.count(), f'a tela não ofereceu o atendimento em {url_atender} para quem tem `comum.change_documentocontrole`'
    botao.click()

    tela.sucesso('Solicitação atendida com sucesso.')
    assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.ATENDIDA, (
        'a UI disse que atendeu, mas a situação da solicitação não mudou'
    )


def test_rejeitar_solicitacao_com_motivo(logado_comum, solicitacao_documento):
    """Rejeita a solicitação registrando o motivo, que fica no histórico.

    Entra pela tela de acompanhamento antes de abrir a rejeição porque a view responde
    ``httprr('..')``, cujo destino sai do *breadcrumb* da sessão
    (``djtools/utils/breadcrumbs.py``) — e porque é esse o caminho real: ninguém rejeita sem antes
    ler o pedido.

    O motivo é afirmado no ``DocumentoControleHistorico``, e não só na situação: uma rejeição sem
    motivo gravado é indistinguível de uma rejeição por engano quando o servidor reclamar.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle, DocumentoControleHistorico

    _, solicitacao = solicitacao_documento
    motivo = 'Documento anterior ainda dentro da validade.'

    tela = Tela(logado_comum('gestor_pessoal')).ir(VER_SOLICITACAO.format(pk=solicitacao.pk))
    tela.ir(REJEITAR.format(pk=solicitacao.pk))
    tela.preencher('Motivo', 'textarea', motivo)
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação rejeitada com sucesso.')
    assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.REJEITADA, (
        'a UI disse que rejeitou, mas a situação da solicitação não mudou'
    )
    assert DocumentoControleHistorico.objects.filter(solicitacao=solicitacao, motivo=motivo).exists(), (
        'a rejeição não registrou o motivo no histórico da solicitação'
    )


def test_rejeitar_solicitacao_ja_atendida_e_recusado(logado_comum, solicitacao_documento):
    """Solicitação atendida não pode mais ser rejeitada: a tela diz ERRO e o registro fica intacto.

    Antes do #17393 a view checava só a permissão, o model recusava em silêncio e a tela
    anunciava "rejeitada com sucesso".
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle

    _, solicitacao = solicitacao_documento

    tela = Tela(logado_comum('gestor_pessoal')).ir(VER_SOLICITACAO.format(pk=solicitacao.pk))
    tela.clicar_botao('Marcar Solicitação como Atendida')
    tela.sucesso('Solicitação atendida com sucesso.')

    tela.ir(REJEITAR.format(pk=solicitacao.pk))
    tela.erro('Somente solicitações não atendidas podem ser rejeitadas.')
    assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.ATENDIDA, (
        'a solicitação atendida foi rejeitada'
    )


def test_transicoes_da_solicitacao_fechadas_a_quem_nao_despacha(logado_comum, solicitacao_documento):
    """Quem não tem ``comum.change_documentocontrole`` não atende nem rejeita — medido por HTTP.

    A tela de acompanhamento é aberta a qualquer pessoa logada de propósito (o próprio solicitante
    acompanha o pedido dele), e é justamente por isso que as duas rotas de transição precisam de
    guarda própria: elas mudam estado a partir de um simples GET com o ``pk`` na URL.
    """
    _, solicitacao = solicitacao_documento

    tela = Tela(logado_comum('solicitante'))

    assert tela.buscar(VER_SOLICITACAO.format(pk=solicitacao.pk)).status == 200, 'o solicitante deixou de conseguir acompanhar o próprio pedido'
    assert tela.buscar(MARCAR_ATENDIDA.format(pk=solicitacao.pk)).status == 403, 'o atendimento da solicitação ficou aberto a quem não despacha'
    assert tela.buscar(REJEITAR.format(pk=solicitacao.pk)).status == 403, 'a rejeição da solicitação ficou aberta a quem não despacha'
