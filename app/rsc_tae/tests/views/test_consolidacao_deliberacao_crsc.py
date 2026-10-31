"""Consolidação da deliberação final da CRSC: uma só, por mais vezes que se tente gravá-la.

As checagens que antecedem a consolidação (``pode_deliberar_crsc``, o estado da votação) rodam
ao montar a tela, antes do POST. Entre elas e a gravação cabem dois cliques do mesmo membro ou
dois membros fechando o quórum ao mesmo tempo — e a segunda gravação violava o ``OneToOne`` de
``DeliberacaoCRSCRSCTae.processo``, derrubando a requisição com ``IntegrityError`` em produção.
"""

from decimal import Decimal

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from djtools.middleware import threadlocals
from rsc_tae.enums import MotivoIndeferimento, SituacaoProcesso
from rsc_tae.models import (
    DeliberacaoCRSCRSCTae,
    HistoricoSituacaoProcessoRSCTae,
    Nivel,
    ProcessoRSCTae,
    VotoDeliberacaoFinalRSCTae,
)
from rsc_tae.views.processo import _consolidar_deliberacao_final


def _requisicao():
    """Requisição mínima para o consolidador: ele lê o IP/user-agent e responde com ``httprr``."""
    request = RequestFactory().post('/rsc_tae/processo/deliberar_crsc/')
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db(databases='__all__')
class TestConsolidacaoConcorrente:
    ATORES = ('servidor_a', 'servidor_b')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        self.vinculo = self.servidor_b.get_vinculo()
        self.votos = [
            VotoDeliberacaoFinalRSCTae.objects.create(
                processo=self.processo,
                deliberado_por_vinculo=self.vinculo,
                resultado=SituacaoProcesso.INDEFERIDO,
                pontuacao_final=Decimal('0'),
                motivos_indeferimento=[MotivoIndeferimento.PONTUACAO_MINIMA],
                justificativa='Pontuação insuficiente após a avaliação.',
            )
        ]
        threadlocals.context.request = _requisicao()

    def _consolidar(self):
        """Uma requisição de consolidação, com o processo em memória como a segunda o veria."""
        return _consolidar_deliberacao_final(
            threadlocals.context.request,
            self.processo,
            SituacaoProcesso.INDEFERIDO,
            Decimal('0'),
            self.vinculo,
            self.votos,
        )

    def test_segunda_consolidacao_nao_duplica_a_deliberacao(self):
        self._consolidar()

        self._consolidar()

        assert DeliberacaoCRSCRSCTae.objects.filter(processo=self.processo).count() == 1

    def test_segunda_consolidacao_nao_repete_a_transicao_do_processo(self):
        """O histórico é a prova de que a segunda requisição parou antes dos efeitos colaterais."""
        self._consolidar()

        self._consolidar()

        assert HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo, situacao_nova=SituacaoProcesso.INDEFERIDO).count() == 1
