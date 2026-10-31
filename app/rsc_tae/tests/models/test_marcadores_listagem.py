"""Testes dos marcadores de PCD, exercício externo e 60+ na listagem de processos.

Cobrem as três camadas do recurso: a leitura da política (``codigos_situacao_exercicio_externo``),
a anotação no queryset do admin (``_anotar_marcadores``, incluindo a guarda de content type) e o
gate de visibilidade (``_pode_ver_marcadores``), que mantém o dado sensível fora do SELECT de quem
não pode vê-lo — em especial do avaliador, cuja avaliação é cega.
"""

import datetime

import pytest
from dateutil.relativedelta import relativedelta
from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType

from comum.models import User, Vinculo
from django.contrib.auth.models import Permission
from rh.models import Deficiencia, GrupoDeficiencia, Situacao
from rsc_tae.admin.processo import ExercicioExternoListFilter, Idade60MaisListFilter, PcdListFilter, ProcessoRSCTaeAdmin, _badges_marcadores
from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import ComissaoRSCTae, ConfiguracaoRSCTae, MembroComissaoRSCTae, Nivel, ProcessoRSCTae
from rsc_tae.views._helpers import codigos_situacao_exercicio_externo


class _RequestFalso:
    """Mínimo que o admin consome da request: ``user`` e o cache de gates preso ao objeto."""

    def __init__(self, user, GET=None):
        self.user = user
        self.GET = GET or {}


@pytest.mark.django_db(databases='__all__')
class TestMarcadoresListagem:
    ATORES = ('admin', 'servidor_a', 'servidor_b', 'servidor_c')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        self.admin = ProcessoRSCTaeAdmin(ProcessoRSCTae, AdminSite())
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)

        self.cedido = Situacao.objects.get_or_create(
            codigo=Situacao.CEDIDO_REQUISITADO, defaults={'nome': 'Cedido/Requisitado', 'nome_siape': 'CEDIDO/REQUISITADO'}
        )[0]

        # servidor_a: PCD e cedido; servidor_b: nenhum marcador — o par mínimo para separar os dois eixos.
        self.processo_a = self._criar_processo(self.servidor_a)
        self.processo_b = self._criar_processo(self.servidor_b)

    def _criar_processo(self, servidor):
        return ProcessoRSCTae.objects.create(
            vinculo=servidor.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
        )

    def _marcar_pcd(self, servidor):
        grupo = GrupoDeficiencia.objects.get_or_create(codigo='1', defaults={'descricao': 'Física'})[0]
        deficiencia = Deficiencia.objects.get_or_create(grupo_deficiencia=grupo, codigo='11', defaults={'descricao': 'Paraplegia'})[0]
        vinculo = servidor.get_vinculo()
        vinculo.deficiencia = deficiencia
        vinculo.save()

    def _colocar_em_exercicio_externo(self, servidor, situacao=None):
        servidor.situacao = situacao or self.cedido
        servidor.save()

    def _marcar_60_mais(self, servidor, idade=61):
        servidor.pessoa_fisica.nascimento_data = datetime.date.today() - relativedelta(years=idade)
        servidor.pessoa_fisica.save()

    def _configurar_situacoes_externas(self, *situacoes):
        config = ConfiguracaoRSCTae.objects.first() or ConfiguracaoRSCTae.objects.create()
        config.situacoes_exercicio_externo.set(situacoes)
        return config

    def _anotado(self, processo):
        return self.admin._anotar_marcadores(ProcessoRSCTae.objects.filter(pk=processo.pk)).get()

    def _tornar_membro_crsc_ativo(self, user):
        comissao = ComissaoRSCTae.objects.get_or_create(nome='Comissão CRSC-TAE (teste)', defaults={'data_inicio': '2020-01-01', 'ativa': True})[0]
        MembroComissaoRSCTae.objects.get_or_create(comissao=comissao, vinculo=user.get_vinculo(), defaults={'ativo': True})

    # --- Política: quais situações contam como exercício externo ---

    def test_codigos_vazios_sem_configuracao(self):
        assert codigos_situacao_exercicio_externo() == []

    def test_codigos_vazios_com_configuracao_sem_situacoes(self):
        self._configurar_situacoes_externas()
        assert codigos_situacao_exercicio_externo() == []

    def test_codigos_retorna_as_situacoes_marcadas(self):
        self._configurar_situacoes_externas(self.cedido)
        assert codigos_situacao_exercicio_externo() == [Situacao.CEDIDO_REQUISITADO]

    def test_codigos_ignora_situacao_sem_codigo_siape(self):
        """``Situacao.codigo`` é nullable: sem esse filtro, o ``None`` viraria ``IN (NULL)`` e nunca casaria."""
        sem_codigo = Situacao.objects.create(codigo=None, nome='Sem código', nome_siape='SEM CODIGO')
        self._configurar_situacoes_externas(self.cedido, sem_codigo)
        assert codigos_situacao_exercicio_externo() == [Situacao.CEDIDO_REQUISITADO]

    def test_codigos_aceita_configuracao_ja_carregada(self):
        """O admin passa a configuração cacheada na request; o resultado tem de ser o mesmo."""
        config = self._configurar_situacoes_externas(self.cedido)
        assert codigos_situacao_exercicio_externo(config) == [Situacao.CEDIDO_REQUISITADO]

    # --- Anotação: PCD ---

    def test_anota_pcd_quando_vinculo_tem_deficiencia(self):
        self._marcar_pcd(self.servidor_a)
        assert self._anotado(self.processo_a)._rsc_pcd is True

    def test_nao_anota_pcd_sem_deficiencia(self):
        assert self._anotado(self.processo_b)._rsc_pcd is False

    # --- Anotação: exercício externo ---

    def test_anota_situacao_externa_quando_configurada(self):
        self._configurar_situacoes_externas(self.cedido)
        self._colocar_em_exercicio_externo(self.servidor_a)
        assert self._anotado(self.processo_a)._rsc_situacao_externa == 'Cedido/Requisitado'

    def test_nao_anota_situacao_externa_quando_nao_configurada(self):
        """Sem política definida, ninguém é sinalizado — mesmo o servidor cedido."""
        self._colocar_em_exercicio_externo(self.servidor_a)
        assert self._anotado(self.processo_a)._rsc_situacao_externa is None

    def test_nao_anota_situacao_externa_de_situacao_fora_da_lista(self):
        self._configurar_situacoes_externas(self.cedido)
        assert self._anotado(self.processo_b)._rsc_situacao_externa is None

    # --- Anotação: 60+ ---

    def test_anota_60_mais_quando_servidor_tem_60_anos_ou_mais(self):
        self._marcar_60_mais(self.servidor_a)
        assert self._anotado(self.processo_a)._rsc_60_mais is True

    def test_nao_anota_60_mais_quando_servidor_tem_menos_de_60_anos(self):
        self._marcar_60_mais(self.servidor_a, idade=59)
        assert self._anotado(self.processo_a)._rsc_60_mais is False

    def test_nao_anota_60_mais_sem_data_de_nascimento_cadastrada(self):
        assert self._anotado(self.processo_b)._rsc_60_mais is False

    def test_anota_60_mais_no_dia_exato_do_aniversario(self):
        """Fronteira do corte: quem completa 60 anos hoje já entra na lista (``<=``, não ``<``)."""
        self._marcar_60_mais(self.servidor_a, idade=60)
        assert self._anotado(self.processo_a)._rsc_60_mais is True

    def test_nao_anota_60_mais_no_dia_anterior_ao_aniversario(self):
        """Do outro lado da fronteira: falta um dia para os 60, ainda fora."""
        vinculo = self.servidor_a.get_vinculo()
        vinculo.pessoa.pessoafisica.nascimento_data = datetime.date.today() - relativedelta(years=60) + datetime.timedelta(days=1)
        vinculo.pessoa.pessoafisica.save()
        assert self._anotado(self.processo_a)._rsc_60_mais is False

    def test_guarda_de_content_type_evita_falso_positivo(self):
        """Um vínculo não-servidor com o mesmo ``id_relacionamento`` de um servidor cedido não é sinalizado."""
        self._configurar_situacoes_externas(self.cedido)
        self._colocar_em_exercicio_externo(self.servidor_a)

        vinculo_impostor = Vinculo.objects.create(
            pessoa=self.servidor_a.get_vinculo().pessoa,
            tipo_relacionamento=ContentType.objects.get_for_model(Nivel),
            id_relacionamento=self.servidor_a.pk,
            secret=0,
        )
        processo_impostor = ProcessoRSCTae.objects.create(
            vinculo=vinculo_impostor, nivel_requisitado=self.nivel, situacao=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO
        )

        assert self._anotado(processo_impostor)._rsc_situacao_externa is None

    # --- Filtros da listagem ---

    def test_filtro_pcd_sim_e_nao(self):
        self._marcar_pcd(self.servidor_a)
        qs = self.admin._anotar_marcadores(ProcessoRSCTae.objects.all())
        request = _RequestFalso(self.servidor_a.get_user())

        filtro_sim = PcdListFilter(request, {'rsc_pcd': ['1']}, ProcessoRSCTae, self.admin)
        filtro_nao = PcdListFilter(request, {'rsc_pcd': ['0']}, ProcessoRSCTae, self.admin)

        assert list(filtro_sim.queryset(request, qs)) == [self.processo_a]
        assert list(filtro_nao.queryset(request, qs)) == [self.processo_b]

    def test_filtro_exercicio_externo_sim_e_nao(self):
        self._configurar_situacoes_externas(self.cedido)
        self._colocar_em_exercicio_externo(self.servidor_a)
        qs = self.admin._anotar_marcadores(ProcessoRSCTae.objects.all())
        request = _RequestFalso(self.servidor_a.get_user())

        filtro_sim = ExercicioExternoListFilter(request, {'rsc_exercicio_externo': ['1']}, ProcessoRSCTae, self.admin)
        filtro_nao = ExercicioExternoListFilter(request, {'rsc_exercicio_externo': ['0']}, ProcessoRSCTae, self.admin)

        assert list(filtro_sim.queryset(request, qs)) == [self.processo_a]
        assert list(filtro_nao.queryset(request, qs)) == [self.processo_b]

    def test_filtro_sem_valor_nao_altera_o_queryset(self):
        qs = self.admin._anotar_marcadores(ProcessoRSCTae.objects.all())
        request = _RequestFalso(self.servidor_a.get_user())
        filtro = PcdListFilter(request, {}, ProcessoRSCTae, self.admin)
        assert list(filtro.queryset(request, qs)) == list(qs)

    def test_filtro_60_mais_sim_e_nao(self):
        self._marcar_60_mais(self.servidor_a)
        qs = self.admin._anotar_marcadores(ProcessoRSCTae.objects.all())
        request = _RequestFalso(self.servidor_a.get_user())

        filtro_sim = Idade60MaisListFilter(request, {'rsc_60_mais': ['1']}, ProcessoRSCTae, self.admin)
        filtro_nao = Idade60MaisListFilter(request, {'rsc_60_mais': ['0']}, ProcessoRSCTae, self.admin)

        assert list(filtro_sim.queryset(request, qs)) == [self.processo_a]
        assert list(filtro_nao.queryset(request, qs)) == [self.processo_b]

    # --- Gate de visibilidade ---

    def test_gate_liberado_para_rh_sistemico(self):
        user = self.servidor_b.get_user()
        user.user_permissions.add(Permission.objects.get(codename='eh_rh_sistemico'))
        # a permissão só vale para uma instância nova: has_perm cacheia no objeto
        user = User.objects.get(pk=user.pk)
        assert self.admin._pode_ver_marcadores(_RequestFalso(user)) is True

    def test_gate_liberado_para_membro_da_crsc(self):
        user = self.servidor_c.get_user()
        self._tornar_membro_crsc_ativo(user)
        assert self.admin._pode_ver_marcadores(_RequestFalso(user)) is True

    def test_gate_fechado_para_servidor_comum(self):
        assert self.admin._pode_ver_marcadores(_RequestFalso(self.servidor_b.get_user())) is False

    def test_filtros_so_aparecem_para_quem_pode_ver(self):
        request_comum = _RequestFalso(self.servidor_b.get_user())
        assert PcdListFilter not in self.admin.get_list_filter(request_comum)
        assert ExercicioExternoListFilter not in self.admin.get_list_filter(request_comum)
        assert Idade60MaisListFilter not in self.admin.get_list_filter(request_comum)

        user_crsc = self.servidor_c.get_user()
        self._tornar_membro_crsc_ativo(user_crsc)
        list_filter_crsc = self.admin.get_list_filter(_RequestFalso(user_crsc))
        assert PcdListFilter in list_filter_crsc
        assert ExercicioExternoListFilter in list_filter_crsc
        assert Idade60MaisListFilter in list_filter_crsc

    # --- Badges ---

    def test_badges_vazios_sem_anotacao(self):
        """Quem não pode ver os marcadores recebe um queryset sem as anotações — e nenhum badge."""
        assert _badges_marcadores(self.processo_a) == ''

    def test_badges_com_pcd_e_exercicio_externo(self):
        self._marcar_pcd(self.servidor_a)
        self._configurar_situacoes_externas(self.cedido)
        self._colocar_em_exercicio_externo(self.servidor_a)

        html = _badges_marcadores(self._anotado(self.processo_a))

        assert 'PCD' in html
        assert 'Exercício externo' in html
        assert 'Cedido/Requisitado' in html

    def test_badges_com_60_mais(self):
        self._marcar_60_mais(self.servidor_a)

        html = _badges_marcadores(self._anotado(self.processo_a))

        assert '60+' in html
