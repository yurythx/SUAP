"""Regressão do alerta/aba "A atualizar".

Demandas na etapa "Aprovada" que dependem da conclusão de outra demanda
(`eh_dependente`) não devem ser consideradas no alerta nem na aba "A
atualizar" do admin — issue #17176.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import RequestFactory

from comum.tests.factories import UserFactory
from demandas.models import Demanda
from demandas.models.demanda import Situacao
from demandas.tests.factories import DemandaFactory


@pytest.fixture
def demanda_pre_requisito(db):
    return DemandaFactory(titulo='Pré-requisito', situacao=Situacao.ESTADO_EM_DESENVOLVIMENTO)


class TestAAtualizar:
    def test_aprovada_dependente_de_demanda_nao_concluida_nao_aparece(self, demanda_pre_requisito):
        dependente = DemandaFactory(titulo='Dependente', situacao=Situacao.ESTADO_APROVADO, prioridade=1, dependencia=demanda_pre_requisito)
        assert dependente.eh_dependente is True
        assert dependente not in Demanda.objects.a_atualizar()

    def test_aprovada_dependente_de_demanda_concluida_aparece(self, demanda_pre_requisito):
        demanda_pre_requisito.situacao = Situacao.ESTADO_CONCLUIDO
        demanda_pre_requisito.save()
        dependente = DemandaFactory(titulo='Dependente', situacao=Situacao.ESTADO_APROVADO, prioridade=1, dependencia=demanda_pre_requisito)
        assert dependente.eh_dependente is False
        assert dependente in Demanda.objects.a_atualizar()

    def test_aprovada_sem_dependencia_aparece(self, db):
        demanda = DemandaFactory(titulo='Sem dependência', situacao=Situacao.ESTADO_APROVADO, prioridade=1)
        assert demanda in Demanda.objects.a_atualizar()

    def test_regra_vale_apenas_para_aprovada_dependentes_aberta_e_homologada_aparecem(self, demanda_pre_requisito):
        # Decisão (issue #17176): a exclusão por dependência vale só para a etapa "Aprovada",
        # alinhada a eh_dependente/pode_desenvolver, que só bloqueiam o desenvolvimento.
        # Demandas dependentes em "Solicitada"/"Homologada" continuam no alerta.
        for situacao in (Situacao.ESTADO_ABERTO, Situacao.ESTADO_HOMOLOGADA):
            dependente = DemandaFactory(titulo=f'Dependente {situacao}', situacao=situacao, prioridade=1, dependencia=demanda_pre_requisito)
            assert dependente in Demanda.objects.a_atualizar()


class TestIndexAtribuidosAMim:
    """Protege o refactor de `index_atribuidos_a_mim` (demandas/views.py), que passou a
    reutilizar `a_atualizar()` em vez de duplicar o filtro — a duplicação manual era
    justamente onde o bug #17176 vivia."""

    @pytest.fixture
    def analista(self, db):
        user = UserFactory()
        user.groups.add(Group.objects.get_or_create(name='Analista')[0])
        user.get_groups_cached(force=True)
        return user

    def _pendencia_a_atualizar(self, analista):
        from demandas.views import index_atribuidos_a_mim

        request = RequestFactory().get('/')
        request.user = analista
        pendencias = index_atribuidos_a_mim(sender=None, request=request)
        return next((p for p in pendencias if p['subtitulo'] == 'a atualizar'), None)

    def test_dependente_aprovada_nao_concluida_nao_gera_pendencia(self, analista):
        pre = DemandaFactory(titulo='Pré', situacao=Situacao.ESTADO_EM_DESENVOLVIMENTO)
        dependente = DemandaFactory(titulo='Dependente', situacao=Situacao.ESTADO_APROVADO, prioridade=1, dependencia=pre)
        dependente.analistas.add(analista)

        assert self._pendencia_a_atualizar(analista) is None

    def test_dependente_aprovada_concluida_gera_pendencia(self, analista):
        pre = DemandaFactory(titulo='Pré', situacao=Situacao.ESTADO_CONCLUIDO)
        dependente = DemandaFactory(titulo='Dependente', situacao=Situacao.ESTADO_APROVADO, prioridade=1, dependencia=pre)
        dependente.analistas.add(analista)

        pendencia = self._pendencia_a_atualizar(analista)
        assert pendencia is not None
        assert pendencia['qtd'] == 1
