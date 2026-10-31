"""Views de despacho da solicitação de documento: atender e rejeitar.

As duas transições são de mão única (só a partir de "Não Atendida"). A mensagem da tela tem de
dizer o que de fato aconteceu: sucesso quando o registro mudou, erro quando a guarda recusou
(#17393).
"""

from __future__ import annotations

import pytest
from django.contrib import messages
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.test import Client

from comum.models import DocumentoControle, DocumentoControleHistorico, DocumentoControleTipo, User
from djtools.choices import SituacaoSolicitacaoDocumento
from rh.tests.factories import ServidorFactory, SetorFactory

MARCAR_ATENDIDA = '/comum/marcar_solicitacao_atendida/{pk}/'
REJEITAR = '/comum/rejeitar_solicitacao/{pk}/'
GRUPO_GESTAO_PESSOAS = 'Coordenador de Gestão de Pessoas'


@pytest.fixture
def gestor(sync_permissions: None) -> User:
    """Usuário da Gestão de Pessoas: a permissão vem do grupo, que é o que o model checa."""
    user = ServidorFactory(setor=SetorFactory()).get_user()
    user.groups.add(Group.objects.get(name=GRUPO_GESTAO_PESSOAS))
    user = User.objects.get(pk=user.pk)
    user.get_groups_cached(force=True)
    return user


def _solicitacao(gestor: User, situacao: str) -> DocumentoControle:
    # bulk_create: `DocumentoControle.save` exige um request no threadlocal para gravar o histórico.
    tipo = DocumentoControleTipo.objects.create(descricao='Carteira funcional')
    return DocumentoControle.objects.bulk_create(
        [
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=gestor.get_vinculo(),
                justificativa='Primeira via.',
                ativo=True,
                status_solicitacao=situacao,
            )
        ]
    )[0]


def _mensagens(resposta) -> list[tuple[int, str]]:
    return [(m.level, str(m)) for m in get_messages(resposta.wsgi_request)]


def _situacao(solicitacao: DocumentoControle) -> str:
    return DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao


@pytest.mark.django_db
class TestDespachoSolicitacaoDocumento:
    def test_atender_nao_atendida(self, client: Client, gestor: User) -> None:
        solicitacao = _solicitacao(gestor, SituacaoSolicitacaoDocumento.NAO_ATENDIDA)
        client.force_login(gestor)

        resposta = client.get(MARCAR_ATENDIDA.format(pk=solicitacao.pk))

        assert _mensagens(resposta) == [(messages.SUCCESS, 'Solicitação atendida com sucesso.')]
        assert _situacao(solicitacao) == SituacaoSolicitacaoDocumento.ATENDIDA

    def test_atender_ja_rejeitada_e_recusado(self, client: Client, gestor: User) -> None:
        solicitacao = _solicitacao(gestor, SituacaoSolicitacaoDocumento.REJEITADA)
        client.force_login(gestor)

        resposta = client.get(MARCAR_ATENDIDA.format(pk=solicitacao.pk))

        assert [nivel for nivel, _ in _mensagens(resposta)] == [messages.ERROR], 'a tela confirmou um atendimento que não aconteceu'
        assert _situacao(solicitacao) == SituacaoSolicitacaoDocumento.REJEITADA

    def test_rejeitar_nao_atendida(self, client: Client, gestor: User) -> None:
        solicitacao = _solicitacao(gestor, SituacaoSolicitacaoDocumento.NAO_ATENDIDA)
        client.force_login(gestor)

        resposta = client.post(REJEITAR.format(pk=solicitacao.pk), {'motivo': 'Documento ainda válido.'})

        assert _mensagens(resposta) == [(messages.SUCCESS, 'Solicitação rejeitada com sucesso.')]
        assert _situacao(solicitacao) == SituacaoSolicitacaoDocumento.REJEITADA
        assert DocumentoControleHistorico.objects.filter(solicitacao=solicitacao, motivo='Documento ainda válido.').exists()

    def test_rejeitar_ja_atendida_e_recusado(self, client: Client, gestor: User) -> None:
        solicitacao = _solicitacao(gestor, SituacaoSolicitacaoDocumento.ATENDIDA)
        client.force_login(gestor)

        resposta = client.post(REJEITAR.format(pk=solicitacao.pk), {'motivo': 'Engano.'})

        assert [nivel for nivel, _ in _mensagens(resposta)] == [messages.ERROR], 'a tela confirmou uma rejeição que não aconteceu'
        assert _situacao(solicitacao) == SituacaoSolicitacaoDocumento.ATENDIDA
        assert not DocumentoControleHistorico.objects.filter(solicitacao=solicitacao).exists()
