"""Testes de resolução de chefia (`Servidor.get_chefes_no_periodo`).

Cobrem o caso em que o servidor é o **titular** (chefe) do próprio setor: a sua
chefia imediata deve ser resolvida no setor **superior**, e não entre os
**substitutos eventuais** (SUB-CHEFIA) do seu próprio setor.

Cenário (hierarquia montada pelas factories, na fixture `hierarquia`):

    A0  (titular: servidor_b)            <- chefe real do titular de A1
    └── A1  (titular: servidor_a;        <- servidor cuja chefia estamos resolvendo
             substituto: servidor_c)     <- NÃO pode ser o chefe do próprio titular
"""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Configuracao
from rh.models import Funcao, ServidorFuncaoHistorico, ServidorSetorHistorico
from rh.tests.factories import ServidorFactory, SetorFactory


@pytest.fixture
def hierarquia(db, sync_permissions):
    """RAIZ -> A0 -> A1, mais B1 noutro ramo, e um servidor lotado em cada nível.

    Os setores precisam ser encadeados de verdade: a resolução de chefia sobe pelo
    `superior`, e um `SetorFactory()` sem superior viraria a própria raiz de um campus.
    """
    raiz = SetorFactory(sigla='RAIZ')
    a0 = SetorFactory(sigla='A0', superior=raiz)
    a1 = SetorFactory(sigla='A1', superior=a0)
    b1 = SetorFactory(sigla='B1', superior=raiz)
    return SimpleNamespace(
        raiz=raiz,
        a0=a0,
        a1=a1,
        b1=b1,
        servidor_a=ServidorFactory(setor=a1),
        servidor_b=ServidorFactory(setor=a0),
        servidor_c=ServidorFactory(setor=b1),
    )


@pytest.mark.django_db(databases='__all__')
class TestGetChefesNoPeriodoTitularSobeNivel:
    def _funcao(self, codigo, nome):
        return Funcao.objects.get_or_create(codigo=codigo, defaults={'nome': nome, 'eh_funcao_chefia': True})[0]

    def _historico_funcao(self, servidor, funcao, setor_suap, inicio):
        return ServidorFuncaoHistorico.objects.create(
            servidor=servidor,
            funcao=funcao,
            setor=setor_suap,
            setor_suap=setor_suap,
            data_inicio_funcao=inicio,
            data_fim_funcao=None,
        )

    def _lotar(self, servidor, setor, inicio):
        return ServidorSetorHistorico.objects.get_or_create(servidor=servidor, data_inicio_no_setor=inicio, defaults={'setor': setor})[0]

    def _config_sigla_substituicao(self, valor='SUB-CHEFIA'):
        Configuracao.objects.get_or_create(
            app='rh', chave='sigla_funcao_substituicao_chefia', defaults={'valor': valor, 'descricao': 'sigla substituição de chefia'}
        )
        Configuracao.clear_cache()

    def test_titular_do_proprio_setor_tem_chefe_resolvido_no_setor_superior(self, hierarquia):
        hoje = datetime.date.today()
        ontem = hoje - datetime.timedelta(days=1)

        a0 = hierarquia.a0  # superior de A1
        a1 = hierarquia.a1
        titular_a1 = hierarquia.servidor_a  # lotado em A1
        substituto_a1 = hierarquia.servidor_c
        titular_a0 = hierarquia.servidor_b

        Configuracao.objects.get_or_create(
            app='rh', chave='sigla_funcao_substituicao_chefia', defaults={'valor': 'SUB-CHEFIA', 'descricao': 'sigla substituição de chefia'}
        )
        Configuracao.clear_cache()

        fg = self._funcao('FG', 'Função Gratificada')
        sub = Funcao.objects.get_or_create(codigo='SUB-CHEFIA', defaults={'nome': 'Substituição de Chefia', 'eh_funcao_chefia': True})[0]

        # lotação do titular em A1
        ServidorSetorHistorico.objects.get_or_create(servidor=titular_a1, data_inicio_no_setor=ontem, defaults={'setor': a1})

        # funções de chefia ativas hoje
        self._historico_funcao(titular_a1, fg, a1, ontem)  # titular de A1
        self._historico_funcao(substituto_a1, sub, a1, ontem)  # SUBSTITUTO de A1
        self._historico_funcao(titular_a0, fg, a0, ontem)  # titular de A0 (chefe real)

        chefes = titular_a1.get_chefes_no_periodo(hoje, hoje).get(hoje)

        # o chefe do titular de A1 deve ser o titular do setor SUPERIOR (A0),
        # e nunca o substituto do próprio setor nem ele mesmo.
        assert titular_a0 in chefes, f'esperado o titular de A0 entre os chefes; veio {[c.matricula for c in chefes]}'
        assert substituto_a1 not in chefes, 'o substituto do próprio setor não pode ser chefe do titular'
        assert titular_a1 not in chefes, 'o servidor não pode ser chefe de si mesmo'

    def test_sobe_multiplos_niveis_quando_setor_intermediario_nao_tem_chefia(self, hierarquia):
        # A1 (titular: servidor_a) -> A0 (sem chefia) -> RAIZ (chefe: servidor_b)
        hoje = datetime.date.today()
        ontem = hoje - datetime.timedelta(days=1)
        a1 = hierarquia.a1
        raiz = hierarquia.raiz
        titular_a1 = hierarquia.servidor_a
        chefe_raiz = hierarquia.servidor_b

        self._config_sigla_substituicao()
        fg = self._funcao('FG', 'Função Gratificada')
        self._lotar(titular_a1, a1, ontem)
        self._historico_funcao(titular_a1, fg, a1, ontem)  # titular de A1
        self._historico_funcao(chefe_raiz, fg, raiz, ontem)  # chefia apenas no topo (RAIZ)

        chefes = titular_a1.get_chefes_no_periodo(hoje, hoje).get(hoje)

        # como A0 (superior imediato) não tem chefia, a resolução sobe até RAIZ.
        assert chefe_raiz in chefes
        assert titular_a1 not in chefes

    def test_titular_sem_superior_nao_retorna_a_si_mesmo(self, hierarquia):
        # titular de RAIZ (setor sem superior) e sem reitor cadastrado -> sem chefe.
        hoje = datetime.date.today()
        ontem = hoje - datetime.timedelta(days=1)
        raiz = hierarquia.raiz
        titular_raiz = hierarquia.servidor_a

        self._config_sigla_substituicao()
        fg = self._funcao('FG', 'Função Gratificada')
        self._lotar(titular_raiz, raiz, ontem)
        self._historico_funcao(titular_raiz, fg, raiz, ontem)  # titular do topo

        chefes = titular_raiz.get_chefes_no_periodo(hoje, hoje).get(hoje)

        # sem setor superior e sem reitor, o fallback não retorna ninguém — e nunca ele mesmo.
        assert titular_raiz not in chefes
        assert chefes == []

    def test_config_de_sigla_ausente_nao_quebra_resolucao(self, hierarquia):
        # Sem a Configuracao da sigla de substituição, get_sigla retorna None e a
        # resolução do titular ainda sobe normalmente para o setor superior.
        hoje = datetime.date.today()
        ontem = hoje - datetime.timedelta(days=1)
        a0 = hierarquia.a0
        a1 = hierarquia.a1
        titular_a1 = hierarquia.servidor_a
        titular_a0 = hierarquia.servidor_b

        Configuracao.clear_cache()  # leitura fresca: sem row -> sigla None
        fg = self._funcao('FG', 'Função Gratificada')
        self._lotar(titular_a1, a1, ontem)
        self._historico_funcao(titular_a1, fg, a1, ontem)
        self._historico_funcao(titular_a0, fg, a0, ontem)

        assert Funcao.get_sigla_substituicao_chefia() is None
        chefes = titular_a1.get_chefes_no_periodo(hoje, hoje).get(hoje)
        assert titular_a0 in chefes
        assert titular_a1 not in chefes

    def test_multiplos_setores_resolve_chefe_de_cada(self, hierarquia):
        # servidor lotado em A1 (onde é titular -> sobe para A0) e em B1 (onde NÃO é
        # titular -> chefe é o titular do próprio B1).
        hoje = datetime.date.today()
        ontem = hoje - datetime.timedelta(days=1)
        a0 = hierarquia.a0
        a1 = hierarquia.a1
        b1 = hierarquia.b1
        servidor = hierarquia.servidor_a
        titular_a0 = hierarquia.servidor_b
        chefe_b1 = hierarquia.servidor_c

        self._config_sigla_substituicao()
        fg = self._funcao('FG', 'Função Gratificada')
        self._lotar(servidor, a1, ontem)
        self._lotar(servidor, b1, ontem - datetime.timedelta(days=1))  # data_inicio distinta (unique_together)
        self._historico_funcao(servidor, fg, a1, ontem)  # titular de A1
        self._historico_funcao(titular_a0, fg, a0, ontem)  # chefe de A0
        self._historico_funcao(chefe_b1, fg, b1, ontem)  # chefe de B1

        chefes = servidor.get_chefes_no_periodo(hoje, hoje).get(hoje)

        assert titular_a0 in chefes  # vindo de A1 (titular) -> sobe para A0
        assert chefe_b1 in chefes  # vindo de B1 (não titular) -> titular de B1
        assert servidor not in chefes
