"""Smoke das factories e das regras de papel/permissão do app auditoria.

Garante que cada factory produz objeto válido e que a cadeia de chefia montada
via factory faz as funções de ``papeis.py`` responderem como esperado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group

from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.models.posicionamento import TipoPosicionamento
from auditoria.papeis import eh_auditor, eh_auditor_chefe, tenho_poder_de_chefe
from auditoria.tests import factories as f
from rh.tests.factories import ServidorFactory, SetorFactory, SetorSiapeFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('sync_permissions')]


class TestCadeiaDeChefia:
    def test_funcao_chefia_e_marcada_como_chefia(self):
        funcao = f.FuncaoChefiaFactory()
        assert funcao.pk is not None
        assert funcao.eh_funcao_chefia is True

    def test_chefia_torna_servidor_chefe_do_setor(self):
        setor = SetorFactory()
        gestor = ServidorFactory(setor=setor)

        f.ServidorFuncaoChefiaFactory(servidor=gestor, setor=SetorSiapeFactory(), setor_suap=setor)

        assert gestor.eh_chefe_do_setor_hoje(setor) is True
        assert tenho_poder_de_chefe(gestor.get_user(), setor) is True

    def test_quem_nao_tem_funcao_nao_e_chefe(self):
        # Lotado no setor, com a chefia ocupada por outro e a hierarquia acima dele: ser do
        # setor não basta, é a função que dá o poder de chefe.
        setor = SetorFactory(superior=SetorFactory())
        f.ServidorFuncaoChefiaFactory(servidor=ServidorFactory(setor=setor), setor=SetorSiapeFactory(), setor_suap=setor)
        estranho = ServidorFactory(setor=setor)

        assert tenho_poder_de_chefe(estranho.get_user(), setor) is False


class TestPapeisAuditor:
    def test_servidor_sem_grupo_nao_e_auditor(self):
        user = ServidorFactory().get_user()
        assert eh_auditor(user) is False

    def test_entrar_no_grupo_auditor(self):
        user = ServidorFactory().get_user()
        user.groups.add(Group.objects.get(name='Auditor'))
        assert eh_auditor(user) is True
        assert eh_auditor_chefe(user) is False

    def test_auditor_chefe_exige_os_dois_grupos(self):
        user = ServidorFactory().get_user()
        user.groups.add(Group.objects.get(name='Auditor'))
        user.groups.add(Group.objects.get(name='Auditor Sistêmico'))
        assert eh_auditor_chefe(user) is True


class TestFactoriesDominio:
    def test_recomendacao_e_monitoramento(self, cenario_atendimento):
        c = cenario_atendimento
        assert c.recomendacao.pk is not None
        assert c.recomendacao.numero >= 1
        assert c.recomendacao.monitor == c.auditor_vinculo
        assert c.setor in c.recomendacao.unidades.all()
        assert c.monitoramento.status == MonitoramentoStatus.REGISTRADO
        assert c.monitoramento.unidade == c.setor

    def test_referencia_atendimento(self, cenario_atendimento):
        c = cenario_atendimento
        assert c.motivacao.tipo_posicionamento == TipoPosicionamento.ATENDIMENTO

    def test_manifestacao_e_posicionamento(self, cenario_atendimento):
        c = cenario_atendimento
        solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=c.monitoramento, setor=c.setor)
        manifestacao = f.ManifestacaoFactory(
            monitoramento=c.monitoramento,
            solicitacao_providencia=solicitacao,
            incluido_por=c.gestor_user,
        )
        assert manifestacao.pk is not None

        posicionamento = f.PosicionamentoFactory(manifestacao=manifestacao, incluido_por=c.auditor_user)
        assert posicionamento.pk is not None
        assert posicionamento.tipo == TipoPosicionamento.ATENDIMENTO
