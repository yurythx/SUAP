"""Contagens de chamados da página inicial e das listagens (#17814).

As consultas não usam DISTINCT: o chamado não pode aparecer repetido quando o usuário é, ao mesmo tempo,
requisitante e outro interessado, nem quando o filtro casa mais de uma tag. E o ``count()`` não pode carregar a
anotação ``data_ultima_interacao`` (MAX sobre quatro JOINs), que era o custo em produção.
"""

from datetime import datetime

from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
import pytest

from centralservicos.models import Chamado, StatusChamado
from centralservicos.tests.factories import ComunicacaoFactory, TagFactory


class TestContagemDeChamados:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.chamado = centralservicos_context.chamado
        self.solicitante = centralservicos_context.servidor_solicitante.get_user()
        self.atendente = centralservicos_context.servidor_atendente.get_user()
        # O solicitante já é requisitante e interessado; como outro interessado, o JOIN repetiria a linha.
        self.chamado.outros_interessados.add(self.solicitante, self.atendente)

    def test_chamados_do_usuario_sem_repeticao(self):
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.EM_ATENDIMENTO)

        # index_quadros: chamados em atendimento em que o usuário tem algum interesse.
        em_atendimento = Chamado.get_chamados_do_usuario(
            self.solicitante, status=StatusChamado.EM_ATENDIMENTO, tipo_usuario=Chamado.TIPO_USUARIO_ALGUM_INTERESSE
        )
        assert [c.pk for c in em_atendimento] == [self.chamado.pk]
        assert em_atendimento.count() == 1

        # meus_chamados agrega os contadores sobre o mesmo queryset.
        todos = Chamado.get_chamados_do_usuario(self.solicitante)
        assert todos.aggregate(total=Count('pk'))['total'] == 1

        como_outro_interessado = Chamado.get_chamados_do_usuario(self.atendente, tipo_usuario=Chamado.TIPO_USUARIO_OUTROS_INTERESSADOS)
        assert [c.pk for c in como_outro_interessado] == [self.chamado.pk]
        assert Chamado.get_chamados_do_usuario(self.atendente, tipo_usuario=Chamado.TIPO_USUARIO_REQUISITANTE).count() == 0

    def test_chamados_do_suporte_sem_repeticao_e_com_ultima_interacao(self):
        self.chamado.tags.add(TagFactory(), TagFactory())
        ComunicacaoFactory(chamado=self.chamado, remetente=self.solicitante, data_hora=datetime(2026, 1, 1, 8, 0))
        ultima = ComunicacaoFactory(chamado=self.chamado, remetente=self.atendente, data_hora=datetime(2026, 1, 2, 9, 30))

        chamados = Chamado.get_chamados_do_suporte(
            self.atendente,
            tags=list(self.chamado.tags.all()),
            interessado=self.solicitante,
            ordenar_por='data_ultima_interacao',
            tipo_ordenacao='-',
        )
        assert [(c.pk, c.data_ultima_interacao) for c in chamados] == [(self.chamado.pk, ultima.data_hora)]
        assert chamados.count() == 1

    def test_contagem_do_suporte_nao_carrega_a_ultima_interacao(self):
        # index_atribuidos_a_meus_grupos: o chamado recém-aberto está no grupo do atendente, sem atribuição.
        with CaptureQueriesContext(connection) as consultas:
            qtd = Chamado.get_chamados_do_suporte(self.atendente, atribuicoes=Chamado.SEM_ATRIBUICAO).count()

        assert qtd == 1
        sql = consultas.captured_queries[-1]['sql'].upper()
        assert 'MAX(' not in sql
        assert 'GROUP BY' not in sql
        assert 'DISTINCT "CENTRALSERVICOS_CHAMADO"' not in sql
