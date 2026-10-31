from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import AvaliacaoProcessoRSCTae, Nivel, ProcessoRSCTae


@pytest.mark.django_db(databases='__all__')
class TestFinalizarAvaliacaoRedirect:
    """Cobre o redirect do "Cancelar"/"já finalizada" (antes apontavam para uma rota 404)."""

    ATORES = ('servidor_a', 'servidor_b')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=Decimal('0.00'))
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel)

        self.avaliador = self.servidor_b.get_user()
        self.avaliador.user_permissions.add(Permission.objects.get(codename='avaliar_processorsctae'))

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=SituacaoProcesso.EM_ANALISE,
            avaliador_atual=self.avaliador.get_vinculo(),
        )

        self.client.login(username=self.avaliador.username, password='123')

    def _url(self):
        return f'/rsc_tae/processo/{self.processo.id}/avaliacao/finalizar/'

    def test_ja_finalizada_redireciona_para_listagem_admin(self):
        """GET com a avaliação já finalizada redireciona para a listagem do admin (não para rota 404)."""
        AvaliacaoProcessoRSCTae.objects.update_or_create(
            processo=self.processo,
            avaliador_vinculo=self.avaliador.get_vinculo(),
            defaults={'substituido': False, 'finalizada': True, 'data_finalizacao': timezone.now()},
        )

        resp = self.client.get(self._url())

        assert resp.status_code == 302
        assert '/admin/rsc_tae/processorsctae/' in resp['Location']
        # Não pode cair na rota relativa quebrada '.../avaliacao/' (que dava 404).
        assert not resp['Location'].rstrip('/').endswith('avaliacao')

    def test_get_renderiza_com_cancelar_para_avaliar(self):
        """A tela de finalização renderiza e o botão Cancelar aponta para a avaliação (não href='..')."""
        resp = self.client.get(self._url())

        assert resp.status_code == 200
        conteudo = resp.content.decode()
        assert f'/rsc_tae/processo/{self.processo.id}/avaliar/' in conteudo
        assert 'href=".."' not in conteudo
