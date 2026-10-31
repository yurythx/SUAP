"""Guardas de contagem de queries da listagem admin de processos (``?opcao=1``).

Trancam as duas otimizações contra regressão de N+1:

1. ``acesso_ao_processo_em_funcao_cargo`` (via ``pode_ver_informacoes_basicas``)
   depende só do ``user``, não do processo: os grupos são memoizados no user,
   então N linhas => 1 query, não 2 por linha.
2. O ``Prefetch('interessados', queryset=Vinculo...select_related('pessoa'))`` do
   ``ProcessoAdmin.get_queryset`` deve tornar o acesso por linha (usado em
   ``get_interessados``) gratuito — sem ``.count()``/``.select_related`` que furam
   o cache do prefetch.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Prefetch

from comum.models import Vinculo
from processo_eletronico.models import Processo, TipoProcesso
from processo_eletronico.utils import auditoria_deve_ter_acesso_ao_processo, procuradoria_deve_ter_acesso_ao_processo


@pytest.mark.django_db
def test_acesso_em_funcao_cargo_memoiza_grupos_do_user(django_assert_num_queries):
    """Fix #1: a checagem de cargo consome os grupos do user uma vez por request, não por linha."""
    user = get_user_model().objects.create(username='u-query-count')
    user.groups.add(Group.objects.get_or_create(name='Auditor')[0])

    # 20 linhas simuladas (2 checagens cada) => 1 única query de grupos.
    with django_assert_num_queries(1):
        for _ in range(20):
            assert auditoria_deve_ter_acesso_ao_processo(user, processo=None) is True
            assert procuradoria_deve_ter_acesso_ao_processo(user, processo=None) is False


class TestListagemPrefetchInteressados:
    """Fix #2: o prefetch da listagem torna o acesso a interessados/pessoa O(1) em linhas."""

    def _criar_processos(self, tipo, interessados, quantidade):
        # save() gera o numero_protocolo via SIORG do setor de criação (setado em _setup).
        gerador = self.interessados[0].user
        for _ in range(quantidade):
            processo = Processo.objects.create(
                tipo_processo=tipo,
                nivel_acesso=Processo.NIVEL_ACESSO_PUBLICO,
                setor_criacao=self.setor,
                usuario_gerador=gerador,
                modificado_por=gerador,
            )
            processo.interessados.add(*interessados)

    def _qs_listagem(self):
        # Espelha ProcessoAdmin.get_queryset (parte relevante ao get_interessados).
        return Processo.objects.filter(tipo_processo=self.tipo).prefetch_related(
            Prefetch('interessados', queryset=Vinculo.objects.select_related('pessoa'))
        )

    def _consumir(self, django_assert_num_queries):
        qs = list(self._qs_listagem())  # avalia base + prefetch aqui
        # Reproduz o acesso de get_interessados: lista + pessoa, sem query extra por linha.
        with django_assert_num_queries(0):
            for processo in qs:
                interessados = list(processo.interessados.all())
                _ = len(interessados)
                _ = [interessado.pessoa for interessado in interessados[:3]]

    @pytest.fixture(autouse=True)
    def _setup(self, setor_com_siorg, dois_servidores):
        self.setor = setor_com_siorg
        self.tipo = TipoProcesso.objects.create(nome='Tipo QC', nivel_acesso_default=Processo.NIVEL_ACESSO_PUBLICO)
        self.interessados = [dois_servidores.a.get_vinculo(), dois_servidores.b.get_vinculo()]

    def test_acesso_interessados_e_pessoa_nao_gera_query_por_linha(self, django_assert_num_queries):
        """Com o prefetch correto, iterar interessados + pessoa custa 0 query adicional."""
        self._criar_processos(self.tipo, self.interessados, quantidade=4)
        self._consumir(django_assert_num_queries)
