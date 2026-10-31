"""Cota de deliberações por categoria da comissão (regra interna do IFRN).

Cada categoria de membro (CONSUP, DIGPE, CIS-PCCTAE...) pode gastar no máximo ``limite``
deliberações em cada escopo de votação — um escopo por anexo divergente e um escopo para a
deliberação final do processo. Os contadores são independentes: a categoria que esgotou a cota
num item continua podendo votar na deliberação final.

Sem essa trava, um terceiro membro da mesma categoria votava e a correção era apagar deliberação
na mão (o que os commands ``reverter_deliberacao_*`` faziam).

O limite vem da tela Configurações > Rsc_tae (``comum.Configuracao``, chave
``limite_deliberacoes_por_categoria``); em branco, vale o padrão de 2.
"""

import io
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import call_command
from django.forms import modelform_factory
from django.test import RequestFactory
from django.urls import reverse

from comum.models import Configuracao
from rsc_tae.enums import MotivoIndeferimento, SituacaoProcesso
from rsc_tae.admin.comissao import MembroComissaoRSCTaeInline
from rsc_tae.forms import ConfiguracaoForm
from rsc_tae.models import (
    CategoriaMembroComissaoRSCTae,
    ComissaoRSCTae,
    ConfiguracaoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    GrupoSaberCompetencia,
    MembroComissaoRSCTae,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    VotoDeliberacaoFinalRSCTae,
)
from rsc_tae.views.layout import index_membro_crsc
from rsc_tae.views._helpers import (
    CHAVE_LIMITE_POR_CATEGORIA,
    LIMITE_POR_CATEGORIA_PADRAO,
    limite_deliberacoes_por_categoria,
    status_cota_categoria,
)


def _configurar_limite(valor):
    """Grava o limite na configuração do SUAP e limpa o cache de ``Configuracao`` (TTL de 10s)."""
    Configuracao.objects.update_or_create(
        app='rsc_tae',
        chave=CHAVE_LIMITE_POR_CATEGORIA,
        defaults={'valor': valor, 'descricao': 'Limite por categoria (teste)'},
    )
    Configuracao.clear_cache()


@pytest.mark.django_db(databases='__all__')
class TestLimiteConfigurado:
    """Leitura do limite: a configuração manda; em branco ou inválida, vale o padrão."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _limpar(self):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_LIMITE_POR_CATEGORIA).delete()
        Configuracao.clear_cache()

    def test_sem_configuracao_cadastrada_vale_o_padrao(self):
        assert limite_deliberacoes_por_categoria() == LIMITE_POR_CATEGORIA_PADRAO == 2

    def test_configuracao_em_branco_vale_o_padrao(self):
        _configurar_limite('')

        assert limite_deliberacoes_por_categoria() == 2

    def test_configuracao_preenchida_substitui_o_padrao(self):
        _configurar_limite('3')

        assert limite_deliberacoes_por_categoria() == 3

    def test_configuracao_nao_numerica_vale_o_padrao(self):
        _configurar_limite('dois')

        assert limite_deliberacoes_por_categoria() == 2

    def test_configuracao_zerada_vale_o_padrao(self):
        """Zero impediria qualquer deliberação — a trava não pode parar a comissão inteira."""
        _configurar_limite('0')

        assert limite_deliberacoes_por_categoria() == 2


@pytest.mark.django_db(databases='__all__')
class TestCotaPorCategoria:
    """A cota olha a categoria de quem já votou, não a quantidade total de votos."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_LIMITE_POR_CATEGORIA).delete()
        Configuracao.clear_cache()

        comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)
        self.consup = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP')
        self.digpe = CategoriaMembroComissaoRSCTae.objects.create(nome='DIGPE')

        # Três membros do CONSUP (b, c, d) e um da DIGPE (a) — a cota padrão é 2 por categoria.
        self.membro_b = self._membro(comissao, self.servidor_b, self.consup)
        self.membro_c = self._membro(comissao, self.servidor_c, self.consup)
        self.membro_d = self._membro(comissao, self.servidor_d, self.consup)
        self.membro_a = self._membro(comissao, self.servidor_a, self.digpe)

        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.anexo = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='x.pdf')

    def _membro(self, comissao, servidor, categoria, presidente=False):
        return MembroComissaoRSCTae.objects.create(
            comissao=comissao,
            vinculo=servidor.get_vinculo(),
            categoria=categoria,
            presidente=presidente,
        )

    def _votar_item(self, servidor, pontuacao=Decimal('1.00'), desempate=False):
        return DeliberacaoItemCRSCRSCTae.objects.create(
            processo=self.processo,
            anexo=self.anexo,
            decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR,
            pontuacao_crsc=pontuacao,
            deliberado_por_vinculo=servidor.get_vinculo(),
            desempate=desempate,
        )

    def _votos_item(self):
        return list(DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo, anexo=self.anexo))

    def _cota(self, servidor, votos=None):
        return status_cota_categoria(self._votos_item() if votos is None else votos, servidor.get_vinculo())

    # ------------------------------------------------------------------ #

    def test_sem_votos_a_cota_esta_aberta(self):
        cota = self._cota(self.servidor_b)

        assert cota['bloqueado'] is False
        assert cota['usados'] == 0
        assert cota['limite'] == 2

    def test_um_voto_da_categoria_nao_bloqueia_o_segundo_membro(self):
        self._votar_item(self.servidor_b)

        assert self._cota(self.servidor_c)['bloqueado'] is False

    def test_dois_votos_da_categoria_bloqueiam_o_terceiro_membro(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        cota = self._cota(self.servidor_d)

        assert cota['bloqueado'] is True
        assert cota['usados'] == 2
        assert cota['categoria'] == self.consup

    def test_bloqueio_informa_quem_usou_a_cota(self):
        """O membro precisa saber que a cota é da categoria dele, e quem a gastou."""
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        cota = self._cota(self.servidor_d)

        assert 'CONSUP' in cota['motivo']
        esperados = sorted(str(s.pessoa_fisica.nome) for s in (self.servidor_b, self.servidor_c))
        assert sorted(cota['nomes_que_usaram']) == esperados

    def test_membro_de_outra_categoria_nao_e_bloqueado(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        cota = self._cota(self.servidor_a)

        assert cota['bloqueado'] is False
        assert cota['usados'] == 0
        assert cota['categoria'] == self.digpe

    def test_proprio_voto_nao_consome_a_cota_do_autor(self):
        """Quem já votou continua podendo revisar o próprio voto enquanto o item não fecha."""
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        assert self._cota(self.servidor_b)['bloqueado'] is False
        assert self._cota(self.servidor_c)['bloqueado'] is False

    def test_voto_de_desempate_nao_consome_a_cota(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_d, desempate=True)

        cota = self._cota(self.servidor_c)

        assert cota['bloqueado'] is False
        assert cota['usados'] == 1

    def test_membro_sem_categoria_nao_delibera(self):
        self.membro_d.categoria = None
        self.membro_d.save()

        cota = self._cota(self.servidor_d)

        assert cota['bloqueado'] is True
        assert cota['categoria'] is None
        assert 'categoria' in cota['motivo'].lower()

    def test_quem_nao_e_membro_da_comissao_ativa_nao_delibera(self):
        self.membro_d.delete()

        assert self._cota(self.servidor_d)['bloqueado'] is True

    def test_limite_configurado_libera_o_terceiro_membro(self):
        _configurar_limite('3')
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        cota = self._cota(self.servidor_d)

        assert cota['bloqueado'] is False
        assert cota['limite'] == 3

    def test_cota_do_item_nao_bloqueia_a_deliberacao_final(self):
        """Escopos independentes: o terceiro membro barrado no item segue podendo votar a final."""
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        votos_finais = list(VotoDeliberacaoFinalRSCTae.objects.filter(processo=self.processo))

        assert self._cota(self.servidor_d)['bloqueado'] is True
        assert self._cota(self.servidor_d, votos=votos_finais)['bloqueado'] is False

    def test_cota_da_deliberacao_final_tem_contador_proprio(self):
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=self.servidor_b.get_vinculo(),
            resultado=SituacaoProcesso.DEFERIDO,
            pontuacao_final=Decimal('1.00'),
        )
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=self.servidor_c.get_vinculo(),
            resultado=SituacaoProcesso.DEFERIDO,
            pontuacao_final=Decimal('1.00'),
        )
        votos_finais = list(VotoDeliberacaoFinalRSCTae.objects.filter(processo=self.processo))

        assert self._cota(self.servidor_d, votos=votos_finais)['bloqueado'] is True
        assert self._cota(self.servidor_a, votos=votos_finais)['bloqueado'] is False


@pytest.mark.django_db(databases='__all__')
class TestTravaNasTelasDeDeliberacao:
    """A trava valendo no POST — o caminho que um terceiro membro percorre de verdade.

    Cenário: CONSUP com três membros (b, c e d, este presidente) e o avaliado (a) fora da comissão.
    """

    databases = '__all__'
    SENHA = 'senha-de-teste-123'

    @pytest.fixture(autouse=True)
    def _setup(self, atores, client):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_LIMITE_POR_CATEGORIA).delete()
        Configuracao.clear_cache()
        self.client = client

        # Quórum alto o bastante para o item não fechar com dois votos — o que barra o terceiro
        # membro precisa ser a cota da categoria, não o quórum já atingido.
        ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=4)

        comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)
        self.consup = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP')
        for servidor, presidente in ((self.servidor_b, False), (self.servidor_c, False), (self.servidor_d, True)):
            MembroComissaoRSCTae.objects.create(
                comissao=comissao,
                vinculo=servidor.get_vinculo(),
                categoria=self.consup,
                presidente=presidente,
            )

        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        self.item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.anexo = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=self.item, arquivo='x.pdf')

    def _logar(self, servidor):
        user = servidor.get_user()
        user.set_password(self.SENHA)
        user.save()
        self.client.force_login(user)

    def _votar_item(self, servidor, decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, pontuacao=Decimal('1.00')):
        return DeliberacaoItemCRSCRSCTae.objects.create(
            processo=self.processo,
            anexo=self.anexo,
            decisao=decisao,
            pontuacao_crsc=pontuacao,
            deliberado_por_vinculo=servidor.get_vinculo(),
        )

    def _postar_voto_item(self, servidor):
        self._logar(servidor)
        return self.client.post(
            reverse('rsc_tae:deliberar_item_crsc', kwargs={'processo_id': self.processo.pk, 'anexo_id': self.anexo.pk}),
            {'decisao': '2', 'pontuacao_crsc': '1,00', 'justificativa': 'Documentação suficiente.'},
        )

    def _votar_final(self, servidor):
        return VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=servidor.get_vinculo(),
            resultado=SituacaoProcesso.INDEFERIDO,
            pontuacao_final=Decimal('0'),
            motivos_indeferimento=[MotivoIndeferimento.PONTUACAO_MINIMA],
        )

    def _postar_voto_final(self, servidor):
        self._logar(servidor)
        return self.client.post(
            reverse('rsc_tae:deliberar_crsc', kwargs={'processo_id': self.processo.pk}),
            {
                'resultado': str(SituacaoProcesso.INDEFERIDO),
                'motivos_indeferimento': [str(MotivoIndeferimento.PONTUACAO_MINIMA)],
                'justificativa': 'Pontuação insuficiente após a avaliação.',
                'confirmacao': 'on',
                'senha': self.SENHA,
            },
        )

    def _votos_item_de(self, servidor):
        return DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo, anexo=self.anexo, deliberado_por_vinculo=servidor.get_vinculo())

    def _votos_finais_de(self, servidor):
        return VotoDeliberacaoFinalRSCTae.objects.filter(processo=self.processo, deliberado_por_vinculo=servidor.get_vinculo())

    # ------------------------------------------------------------------ #
    # Escopo do item com divergência
    # ------------------------------------------------------------------ #

    def test_segundo_membro_da_categoria_registra_o_voto_no_item(self):
        """Controle: com a cota aberta o POST grava — o bloqueio dos outros testes é a cota, não o form."""
        self._votar_item(self.servidor_b)

        self._postar_voto_item(self.servidor_c)

        assert self._votos_item_de(self.servidor_c).exists()

    def test_terceiro_membro_da_categoria_nao_registra_o_voto_no_item(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        self._postar_voto_item(self.servidor_d)

        assert not self._votos_item_de(self.servidor_d).exists()

    def test_tela_do_item_explica_o_bloqueio_ao_terceiro_membro(self):
        """Sem a explicação na tela, o membro só descobre o bloqueio ao tentar salvar."""
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)
        self._logar(self.servidor_d)

        resposta = self.client.get(reverse('rsc_tae:deliberar_item_crsc', kwargs={'processo_id': self.processo.pk, 'anexo_id': self.anexo.pk}))
        html = resposta.content.decode()

        assert 'CONSUP' in html
        assert 'já utilizou as 2 deliberações' in html

    def test_tela_da_deliberacao_final_explica_o_bloqueio(self):
        self._votar_final(self.servidor_b)
        self._votar_final(self.servidor_c)
        self._logar(self.servidor_d)

        resposta = self.client.get(reverse('rsc_tae:deliberar_crsc', kwargs={'processo_id': self.processo.pk}))

        assert 'já utilizou as 2 deliberações' in resposta.content.decode()

    def test_presidente_desempata_mesmo_com_a_cota_da_categoria_cheia(self):
        """Empate com a cota cheia: sem a isenção do desempate, o item ficaria sem saída."""
        ConfiguracaoRSCTae.objects.update(quantidade_deliberacoes_item=2)
        self._votar_item(self.servidor_b, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))
        self._votar_item(self.servidor_c, DeliberacaoItemCRSCRSCTae.DECISAO_INDEFERIR, None)

        self._postar_voto_item(self.servidor_d)

        assert self._votos_item_de(self.servidor_d).filter(desempate=True).exists()

    # ------------------------------------------------------------------ #
    # Escopo da deliberação final
    # ------------------------------------------------------------------ #

    def test_segundo_membro_da_categoria_registra_o_voto_final(self):
        """Controle do escopo final: com a cota aberta o voto é gravado."""
        self._votar_final(self.servidor_b)

        self._postar_voto_final(self.servidor_c)

        assert self._votos_finais_de(self.servidor_c).exists()

    def test_terceiro_membro_da_categoria_nao_registra_o_voto_final(self):
        self._votar_final(self.servidor_b)
        self._votar_final(self.servidor_c)

        self._postar_voto_final(self.servidor_d)

        assert not self._votos_finais_de(self.servidor_d).exists()

    # ------------------------------------------------------------------ #
    # Voto concorrente entre a tela e a gravação
    # ------------------------------------------------------------------ #

    def _voto_concorrente(self, votar):
        """Grava ``votar()`` quando a view confere a cota ao montar a tela, antes de a gravação travar o processo.

        Reproduz o membro que salva entre a checagem da tela e a escrita deste voto.
        """
        chamadas = []

        def conferir_cota_com_concorrente(votos, vinculo, limite=None):
            if not chamadas:
                chamadas.append(votar())
            return status_cota_categoria(votos, vinculo, limite)

        return mock.patch('rsc_tae.views.processo.status_cota_categoria', side_effect=conferir_cota_com_concorrente)

    def test_item_fechado_por_voto_concorrente_nao_recebe_mais_um_voto(self):
        """O item fecha entre a tela e a gravação: um voto a mais mudaria a moda já consolidada.

        Limite 3 para a cota não ser o que barra — aqui quem barra é o estado do item.
        """
        _configurar_limite('3')
        ConfiguracaoRSCTae.objects.update(quantidade_deliberacoes_item=2)
        self._votar_item(self.servidor_b)

        with self._voto_concorrente(lambda: self._votar_item(self.servidor_c)):
            self._postar_voto_item(self.servidor_d)

        assert not self._votos_item_de(self.servidor_d).exists()

    def test_deliberacao_final_fechada_por_voto_concorrente_nao_recebe_mais_um_voto(self):
        """Mesma corrida no escopo final: o voto a mais entraria na maioria já consolidada."""
        _configurar_limite('3')
        ConfiguracaoRSCTae.objects.update(quantidade_deliberacoes_item=2)
        self._votar_final(self.servidor_b)

        with self._voto_concorrente(lambda: self._votar_final(self.servidor_c)):
            self._postar_voto_final(self.servidor_d)

        assert not self._votos_finais_de(self.servidor_d).exists()


@pytest.mark.django_db(databases='__all__')
class TestCampoDeConfiguracaoDoLimite:
    """O limite é editado em Configurações > Rsc_tae, e não pode inviabilizar o quórum.

    Com quórum de 4 votos e 3 categorias, limite 1 permitiria no máximo 3 votos — o item nunca
    fecharia. A trava não pode criar um impasse pior do que o problema que resolve.
    """

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=4)
        self.comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)

    def _categoria_com_membro(self, nome, servidor):
        categoria = CategoriaMembroComissaoRSCTae.objects.create(nome=nome)
        self._membro(categoria, servidor)
        return categoria

    def _membro(self, categoria, servidor):
        MembroComissaoRSCTae.objects.create(comissao=self.comissao, vinculo=servidor.get_vinculo(), categoria=categoria)

    def _validar(self, valor):
        form = ConfiguracaoForm(data={CHAVE_LIMITE_POR_CATEGORIA: valor})
        form.is_valid()
        return form.errors.get(CHAVE_LIMITE_POR_CATEGORIA, [])

    def test_o_campo_existe_na_configuracao_do_modulo(self):
        """O nome do campo é a chave lida por limite_deliberacoes_por_categoria()."""
        assert CHAVE_LIMITE_POR_CATEGORIA in ConfiguracaoForm().fields

    def test_campo_em_branco_e_valido(self):
        assert self._validar('') == []

    def test_limite_que_viabiliza_o_quorum_e_valido(self):
        self._categoria_com_membro('CONSUP', self.servidor_b)
        self._categoria_com_membro('DIGPE', self.servidor_c)

        assert self._validar('2') == []

    def test_limite_que_inviabiliza_o_quorum_e_recusado(self):
        """O teto é a soma de min(limite, membros): CONSUP com 3 e DIGPE com 1 dão 2 + 1 = 3 votos, abaixo do quórum 4."""
        consup = self._categoria_com_membro('CONSUP', self.servidor_b)
        self._membro(consup, self.servidor_c)
        self._membro(consup, self.servidor_d)
        self._categoria_com_membro('DIGPE', self.servidor_a)

        erros = self._validar('2')

        assert erros
        assert 'quórum' in erros[0]

    def test_limite_zero_e_recusado(self):
        assert self._validar('0')

    def test_sem_comissao_ativa_nao_ha_como_checar_o_quorum(self):
        self.comissao.ativa = False
        self.comissao.save()

        assert self._validar('1') == []


@pytest.mark.django_db(databases='__all__')
class TestPendenciaDoMembroComCotaCheia:
    """O card "deliberações pendentes" não pode cobrar do membro um voto que a trava vai recusar."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_LIMITE_POR_CATEGORIA).delete()
        Configuracao.clear_cache()

        comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)
        consup = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP')
        for servidor in (self.servidor_b, self.servidor_c, self.servidor_d):
            MembroComissaoRSCTae.objects.create(comissao=comissao, vinculo=servidor.get_vinculo(), categoria=consup)

        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

    def _pendencias(self, servidor):
        request = RequestFactory().get('/')
        request.user = servidor.get_user()
        # O decorator de layout transforma a view em receptor de signal (e silencia exceções
        # devolvendo []) — daí a chamada com sender/request e o teste de controle ao lado.
        return index_membro_crsc(sender=None, request=request)

    def _votar_final(self, servidor):
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=servidor.get_vinculo(),
            resultado=SituacaoProcesso.INDEFERIDO,
            pontuacao_final=Decimal('0'),
            motivos_indeferimento=[MotivoIndeferimento.PONTUACAO_MINIMA],
        )

    def test_membro_com_cota_aberta_ve_a_pendencia(self):
        assert self._pendencias(self.servidor_d)[0]['qtd'] == 1

    def test_membro_com_a_cota_da_categoria_cheia_nao_ve_a_pendencia(self):
        self._votar_final(self.servidor_b)
        self._votar_final(self.servidor_c)

        assert self._pendencias(self.servidor_d) == []

    def test_quem_ja_votou_continua_sem_pendencia(self):
        """Regra que já existia: o próprio voto tira o processo da lista."""
        self._votar_final(self.servidor_b)

        assert self._pendencias(self.servidor_b) == []


@pytest.mark.django_db(databases='__all__')
class TestCategoriaObrigatoriaNoCadastro:
    """Sem categoria a cota não tem balde — o cadastro do membro passa a exigi-la.

    O campo continua aceitando ``NULL`` no banco por causa dos registros legados, que o relatório
    de violações aponta; o que muda é o formulário (inline do admin da comissão).
    """

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)

    def _form(self, **dados):
        FormDoInline = modelform_factory(MembroComissaoRSCTae, fields=MembroComissaoRSCTaeInline.fields)
        base = {'vinculo': self.servidor_b.get_vinculo().pk, 'ativo': True}
        return FormDoInline(data={**base, **dados})

    def test_membro_sem_categoria_e_recusado(self):
        form = self._form()

        assert not form.is_valid()
        assert 'categoria' in form.errors

    def test_membro_com_categoria_e_aceito(self):
        categoria = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP')

        assert self._form(categoria=categoria.pk).is_valid()


@pytest.mark.django_db(databases='__all__')
class TestRelatorioDeViolacoes:
    """``verificar_cota_categoria_crsc``: só lê e aponta o que a trava não alcança retroativamente."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_LIMITE_POR_CATEGORIA).delete()
        Configuracao.clear_cache()

        self.comissao = ComissaoRSCTae.objects.create(nome='Comissão Teste', data_inicio='2026-01-01', ativa=True)
        self.consup = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP')
        for servidor in (self.servidor_b, self.servidor_c, self.servidor_d):
            MembroComissaoRSCTae.objects.create(comissao=self.comissao, vinculo=servidor.get_vinculo(), categoria=self.consup)

        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.anexo = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='x.pdf')

    def _relatorio(self):
        saida = io.StringIO()
        call_command('verificar_cota_categoria_crsc', stdout=saida)
        return saida.getvalue()

    def _votar_item(self, servidor):
        DeliberacaoItemCRSCRSCTae.objects.create(
            processo=self.processo,
            anexo=self.anexo,
            decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR,
            pontuacao_crsc=Decimal('1.00'),
            deliberado_por_vinculo=servidor.get_vinculo(),
        )

    def _votar_final(self, servidor):
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=servidor.get_vinculo(),
            resultado=SituacaoProcesso.INDEFERIDO,
            pontuacao_final=Decimal('0'),
            motivos_indeferimento=[MotivoIndeferimento.PONTUACAO_MINIMA],
        )

    def test_sem_violacao_o_relatorio_diz_que_esta_tudo_certo(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)

        assert 'Nenhuma violação' in self._relatorio()

    def test_aponta_item_com_votos_acima_da_cota(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)
        self._votar_item(self.servidor_d)

        relatorio = self._relatorio()

        assert f'processo {self.processo.pk}' in relatorio
        assert f'anexo {self.anexo.pk}' in relatorio
        assert 'CONSUP' in relatorio
        assert '3 votos' in relatorio

    def test_aponta_deliberacao_final_com_votos_acima_da_cota(self):
        self._votar_final(self.servidor_b)
        self._votar_final(self.servidor_c)
        self._votar_final(self.servidor_d)

        relatorio = self._relatorio()

        assert 'deliberação final' in relatorio
        assert f'processo {self.processo.pk}' in relatorio

    def test_aponta_membro_ativo_sem_categoria(self):
        MembroComissaoRSCTae.objects.filter(vinculo=self.servidor_d.get_vinculo()).update(categoria=None)

        assert 'sem categoria' in self._relatorio()

    def test_relatorio_nao_altera_nem_apaga_voto(self):
        self._votar_item(self.servidor_b)
        self._votar_item(self.servidor_c)
        self._votar_item(self.servidor_d)

        self._relatorio()

        assert DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo, anexo=self.anexo).count() == 3
