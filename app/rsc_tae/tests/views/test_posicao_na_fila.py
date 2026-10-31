"""Testes da posição do processo na fila da etapa (``ProcessoRSCTae.posicao_na_fila``).

A posição só existe nas etapas em que o processo depende de OUTRA pessoa. Onde a ação é do
próprio servidor (preenchimento/correção) não há fila, e depois de finalizado não há mais espera.

A ordem é a de ``expressao_data_entrada_situacao_atual`` — a mesma da listagem do admin e de
Minhas Avaliações. Como as transições gravam ``data_transicao`` com ``auto_now_add``, os testes
que precisam controlar o instante gravam a data por ``queryset.update()``.
"""

from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from rsc_tae.admin.processo import ProcessoRSCTaeAdmin
from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import HistoricoSituacaoProcessoRSCTae, Nivel, ProcessoRSCTae


@pytest.mark.django_db(databases='__all__')
class TestPosicaoNaFila:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)

    def _processo(self, servidor, situacao=SituacaoProcesso.AGUARDANDO_CRSC, entrou_ha_dias=0):
        """Cria um processo já na situação desejada, com a entrada nela datada no passado."""
        processo = ProcessoRSCTae.objects.create(
            vinculo=servidor.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=situacao,
        )
        historico = HistoricoSituacaoProcessoRSCTae.objects.create(
            processo=processo,
            situacao_anterior=SituacaoProcesso.EM_ANALISE,
            situacao_nova=situacao,
        )
        quando = timezone.now() - timedelta(days=entrou_ha_dias)
        HistoricoSituacaoProcessoRSCTae.objects.filter(pk=historico.pk).update(data_transicao=quando)
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_cadastro=quando)
        processo.refresh_from_db()
        return processo

    # ------------------------------------------------------------------ ordem

    def test_quem_entrou_antes_na_etapa_vem_primeiro(self):
        antigo = self._processo(self.servidor_a, entrou_ha_dias=30)
        meio = self._processo(self.servidor_b, entrou_ha_dias=10)
        novo = self._processo(self.servidor_c, entrou_ha_dias=1)

        assert antigo.posicao_na_fila()['posicao'] == 1
        assert meio.posicao_na_fila()['posicao'] == 2
        assert novo.posicao_na_fila()['posicao'] == 3

    def test_total_conta_todos_os_processos_da_etapa(self):
        self._processo(self.servidor_a, entrou_ha_dias=30)
        meio = self._processo(self.servidor_b, entrou_ha_dias=10)
        self._processo(self.servidor_c, entrou_ha_dias=1)

        assert meio.posicao_na_fila()['total'] == 3

    def test_fila_e_por_etapa_e_nao_global(self):
        """Processo em outra situação não entra na conta — cada etapa tem a sua fila."""
        self._processo(self.servidor_a, situacao=SituacaoProcesso.EM_ANALISE, entrou_ha_dias=50)
        sozinho = self._processo(self.servidor_b, situacao=SituacaoProcesso.AGUARDANDO_CRSC, entrou_ha_dias=1)

        assert sozinho.posicao_na_fila() == {'posicao': 1, 'total': 1}

    def test_quem_voltou_para_a_etapa_vai_para_o_fim(self):
        """O caso que distingue "entrada na etapa" de "data de cadastro".

        Um processo antigo que voltou de correção reentra na fila agora — não recupera o lugar que
        tinha pela idade do cadastro. Sem esta asserção, ordenar por ``data_cadastro`` passaria
        despercebido, porque nos demais cenários as duas datas coincidem.
        """
        veterano = self._processo(self.servidor_a, entrou_ha_dias=1)
        ProcessoRSCTae.objects.filter(pk=veterano.pk).update(data_cadastro=timezone.now() - timedelta(days=100))
        veterano.refresh_from_db()

        recente = self._processo(self.servidor_b, entrou_ha_dias=30)
        ProcessoRSCTae.objects.filter(pk=recente.pk).update(data_cadastro=timezone.now() - timedelta(days=10))
        recente.refresh_from_db()

        # Pelo cadastro, o veterano viria primeiro (100 dias contra 10). Pela entrada na etapa,
        # que é o critério correto, ele é o último (1 dia contra 30).
        assert recente.posicao_na_fila()['posicao'] == 1
        assert veterano.posicao_na_fila()['posicao'] == 2

    def test_ordem_bate_com_a_da_listagem_do_admin(self):
        """A posição não pode contradizer a ordem em que a comissão vê os processos."""
        self._processo(self.servidor_a, entrou_ha_dias=30)
        self._processo(self.servidor_b, entrou_ha_dias=10)
        self._processo(self.servidor_c, entrou_ha_dias=1)

        listagem = list(
            ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.AGUARDANDO_CRSC)
            .annotate(entrada=ProcessoRSCTae.expressao_data_entrada_situacao_atual())
            .order_by('entrada', 'data_cadastro')
        )
        posicoes = [processo.posicao_na_fila()['posicao'] for processo in listagem]
        assert posicoes == [1, 2, 3]

    def test_desempata_pela_data_de_cadastro(self):
        """Duas entradas no mesmo instante não podem produzir duas vezes a mesma posição."""
        primeiro = self._processo(self.servidor_a, entrou_ha_dias=5)
        segundo = self._processo(self.servidor_b, entrou_ha_dias=5)
        # Mesmo instante de entrada; o cadastro do segundo é posterior.
        entrada = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=primeiro).values_list('data_transicao', flat=True).first()
        HistoricoSituacaoProcessoRSCTae.objects.filter(processo=segundo).update(data_transicao=entrada)
        ProcessoRSCTae.objects.filter(pk=segundo.pk).update(data_cadastro=entrada + timedelta(minutes=1))
        segundo.refresh_from_db()

        assert {primeiro.posicao_na_fila()['posicao'], segundo.posicao_na_fila()['posicao']} == {1, 2}

    # ------------------------------------------------- etapas sem fila

    @pytest.mark.parametrize(
        'situacao',
        [SituacaoProcesso.AGUARDANDO_PREENCHIMENTO, SituacaoProcesso.AGUARDANDO_CORRECAO],
    )
    def test_sem_fila_quando_a_acao_e_do_proprio_servidor(self, situacao):
        processo = self._processo(self.servidor_a, situacao=situacao)

        assert processo.posicao_na_fila() is None

    @pytest.mark.parametrize('situacao', [SituacaoProcesso.DEFERIDO, SituacaoProcesso.INDEFERIDO])
    def test_processo_finalizado_nao_tem_posicao(self, situacao):
        """Depois de finalizado não há mais espera — e foi exatamente o que se pediu."""
        processo = self._processo(self.servidor_a, situacao=situacao)

        assert processo.posicao_na_fila() is None

    @pytest.mark.parametrize(
        'situacao',
        [
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            SituacaoProcesso.EM_ANALISE,
            SituacaoProcesso.AGUARDANDO_CRSC,
        ],
    )
    def test_ha_fila_nas_etapas_que_dependem_de_terceiro(self, situacao):
        processo = self._processo(self.servidor_a, situacao=situacao)

        assert processo.posicao_na_fila() == {'posicao': 1, 'total': 1}

    def test_aceita_uma_situacao_solta_alem_de_lista(self):
        """O parâmetro é plural, mas passar a constante sozinha é o engano natural de quem chama."""
        processo = self._processo(self.servidor_a, situacao=SituacaoProcesso.AGUARDANDO_CRSC)

        mapa = ProcessoRSCTae.mapa_de_posicoes(SituacaoProcesso.AGUARDANDO_CRSC)

        assert mapa[processo.pk] == {'posicao': 1, 'total': 1}

    def test_processo_sem_historico_de_transicao_nao_quebra(self):
        """Processos anteriores ao histórico caem para data_cadastro na expressão de ordenação."""
        processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

        assert processo.posicao_na_fila() == {'posicao': 1, 'total': 1}


@pytest.mark.django_db(databases='__all__')
class TestColunaNoAdmin:
    """A coluna existe na aba do servidor e nas três etapas com fila.

    Nas abas mistas (Todos) e nas sem fila (Finalizados, preenchimento, correção) ela não aparece:
    não haveria posição a mostrar, só uma coluna de traços.
    """

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        from django.contrib.admin.sites import site

        self.admin = ProcessoRSCTaeAdmin(ProcessoRSCTae, site)
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)

    def _request(self, **params):
        request = RequestFactory().get('/admin/rsc_tae/processorsctae/', params)
        request.user = self.servidor_a.get_vinculo().user
        return request

    @pytest.mark.parametrize(
        'aba',
        ['tab_meus_processos', 'tab_aguardando_validacao', 'tab_processos_em_analise', 'tab_aguardando_crsc'],
    )
    def test_coluna_aparece_na_aba_do_servidor_e_nas_etapas_com_fila(self, aba):
        assert 'get_posicao_fila' in self.admin.get_list_display(self._request(tab=aba))

    def test_coluna_aparece_sem_tab_na_url(self):
        """Sem ``?tab=`` o filtro cai na primeira aba, que é justamente "Meus processos"."""
        assert 'get_posicao_fila' in self.admin.get_list_display(self._request())

    @pytest.mark.parametrize('aba', ['tab_todos', 'tab_processos_finalizados', 'tab_aguardando_preenchimento', 'tab_aguardando_correcao'])
    def test_coluna_nao_aparece_onde_nao_ha_fila(self, aba):
        """Abas que misturam etapas ou listam processos sem fila renderizariam só traços."""
        assert 'get_posicao_fila' not in self.admin.get_list_display(self._request(tab=aba))

    def test_toda_etapa_com_fila_tem_aba_correspondente(self):
        """Trava: incluir uma situação em COM_FILA_DE_ESPERA sem exibi-la em aba nenhuma é meio caminho."""
        situacoes_das_abas = {
            'tab_aguardando_validacao': SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            'tab_processos_em_analise': SituacaoProcesso.EM_ANALISE,
            'tab_aguardando_crsc': SituacaoProcesso.AGUARDANDO_CRSC,
        }
        cobertas = {situacoes_das_abas[aba] for aba in self.admin.SITUACAO_DA_ABA if aba in situacoes_das_abas}
        # Os legados não têm aba própria; aparecem em "Meus processos" e em "Todos".
        legados = {SituacaoProcesso.AGUARDANDO_AVALIADOR, SituacaoProcesso.AGUARDANDO_ACEITE_AVALIADOR}

        assert set(SituacaoProcesso.COM_FILA_DE_ESPERA) - legados == cobertas

    def test_coluna_vem_antes_do_prazo(self):
        colunas = self.admin.get_list_display(self._request(tab='tab_meus_processos'))

        assert colunas.index('get_posicao_fila') < colunas.index('get_prazo')

    def test_aba_de_etapa_calcula_so_a_fila_daquela_etapa(self):
        """Sem o recorte, abrir uma aba materializaria as filas de todas as etapas do sistema."""
        na_crsc = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel, situacao=SituacaoProcesso.AGUARDANDO_CRSC
        )
        em_analise = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_b.get_vinculo(), nivel_requisitado=self.nivel, situacao=SituacaoProcesso.EM_ANALISE
        )
        self.admin._request = self._request(tab='tab_aguardando_crsc')

        mapa = self.admin._mapa_de_posicoes()

        assert na_crsc.pk in mapa
        assert em_analise.pk not in mapa

    def test_aba_meus_processos_cobre_todas_as_etapas(self):
        """Ali os processos do servidor podem estar em etapas diferentes."""
        na_crsc = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel, situacao=SituacaoProcesso.AGUARDANDO_CRSC
        )
        em_analise = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel, situacao=SituacaoProcesso.EM_ANALISE
        )
        self.admin._request = self._request(tab='tab_meus_processos')

        mapa = self.admin._mapa_de_posicoes()

        assert na_crsc.pk in mapa
        assert em_analise.pk in mapa

    def test_celula_mostra_posicao_e_total(self):
        processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

        assert '1º de 1' in self.admin.get_posicao_fila(processo)

    def test_celula_avisa_que_a_ordem_nao_e_garantia(self):
        """O texto do title é o que impede o servidor de ler a posição como senha de atendimento."""
        processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

        assert 'não uma garantia' in self.admin.get_posicao_fila(processo)

    def test_celula_vazia_para_processo_finalizado(self):
        processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.DEFERIDO,
        )

        assert self.admin.get_posicao_fila(processo) == '—'


@pytest.mark.django_db(databases='__all__')
class TestConsultasDaColuna:
    """Custo da coluna: uma consulta por página, e não duas por linha."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        from django.contrib.admin.sites import site

        self.admin = ProcessoRSCTaeAdmin(ProcessoRSCTae, site)
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)

    def _request(self):
        request = RequestFactory().get('/admin/rsc_tae/processorsctae/', {'tab': 'tab_aguardando_crsc'})
        request.user = self.servidor_a.get_vinculo().user
        return request

    def _criar(self, servidor, situacao=SituacaoProcesso.AGUARDANDO_CRSC):
        return ProcessoRSCTae.objects.create(
            vinculo=servidor.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=situacao,
        )

    def test_mapa_de_todas_as_filas_custa_uma_consulta(self, django_assert_num_queries):
        self._criar(self.servidor_a)
        self._criar(self.servidor_b, situacao=SituacaoProcesso.EM_ANALISE)
        self._criar(self.servidor_c, situacao=SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR)

        with django_assert_num_queries(1):
            ProcessoRSCTae.mapa_de_posicoes()

    def test_coluna_nao_cresce_com_o_numero_de_linhas(self, django_assert_num_queries):
        """O motivo de o mapa existir: sem ele, cada linha da listagem pagaria consultas próprias."""
        processos = [self._criar(servidor) for servidor in (self.servidor_a, self.servidor_b, self.servidor_c, self.servidor_d)]
        self.admin._request = self._request()

        with django_assert_num_queries(1):
            for processo in processos:
                self.admin.get_posicao_fila(processo)

    def test_mapa_vazio_nao_consulta_o_banco(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            ProcessoRSCTae.mapa_de_posicoes([SituacaoProcesso.DEFERIDO])

    def test_etapa_sem_fila_nao_consulta_o_banco(self, django_assert_num_queries):
        processo = self._criar(self.servidor_a, situacao=SituacaoProcesso.DEFERIDO)

        with django_assert_num_queries(0):
            processo.posicao_na_fila()

    def test_cache_e_por_requisicao(self):
        """Requisições diferentes não podem compartilhar mapa: o admin é reusado entre elas."""
        processo = self._criar(self.servidor_a)

        self.admin._request = self._request()
        primeiro = self.admin.get_posicao_fila(processo)

        self._criar(self.servidor_b, situacao=SituacaoProcesso.AGUARDANDO_CRSC)
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_cadastro=timezone.now() + timedelta(days=1))

        self.admin._request = self._request()  # nova requisição
        segundo = self.admin.get_posicao_fila(processo)

        assert '1º de 1' in primeiro
        assert '2º de 2' in segundo
