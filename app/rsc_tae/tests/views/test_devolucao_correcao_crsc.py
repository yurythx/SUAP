"""Devolução de um processo RSC-TAE para correção a partir da deliberação da CRSC.

A comissão pode constatar, já na deliberação, um problema que só o servidor resolve
(documento preliminar errado, nível pretendido inadequado). A volta apaga tudo que
foi produzido depois do preenchimento — avaliações e deliberações —, porque essas
peças foram medidas contra um preenchimento que vai mudar. O processo retorna ao
mesmo estado de quem foi devolvido na fase de validação.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from rsc_tae.enums import AreaCorrecao, SituacaoDocumentoPreliminar, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.models import (
    AvaliacaoAnexoRSCTae,
    AvaliacaoProcessoRSCTae,
    ApontamentoCorrecaoRSCTae,
    AvaliacaoDocumentoPreliminarRSCTae,
    ComissaoRSCTae,
    DeliberacaoCRSCRSCTae,
    DeliberacaoItemCRSCRSCTae,
    DocumentoPreliminarRSCTae,
    GrupoSaberCompetencia,
    HistoricoSituacaoProcessoRSCTae,
    MembroComissaoRSCTae,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    SorteioAvaliadorRSCTae,
    VotoDeliberacaoFinalRSCTae,
)
from rsc_tae.views._permissoes import PermissoesProcesso


@pytest.mark.django_db(databases='__all__')
class TestTransicaoDevolucao:
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

    def test_deliberacao_da_crsc_pode_devolver_para_correcao(self):
        self.processo.transicionar(SituacaoProcesso.AGUARDANDO_CORRECAO, motivo='Documento preliminar errado.')

        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_CORRECAO


@pytest.mark.django_db(databases='__all__')
class TestResetFasesPosteriores:
    """O reset apaga o que foi produzido depois do preenchimento e preserva o que é fato consumado."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.processo = _processo_em_deliberacao(self)

    def test_apaga_as_avaliacoes_e_solta_os_avaliadores(self):
        self.processo.anular_fases_posteriores()

        assert not AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=self.processo).exists()
        assert not AvaliacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()
        assert self.processo.avaliadores.count() == 0

    def test_apaga_as_deliberacoes_da_crsc(self):
        self.processo.anular_fases_posteriores()

        assert not DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo).exists()
        assert not VotoDeliberacaoFinalRSCTae.objects.filter(processo=self.processo).exists()

    def test_zera_os_campos_de_finalizacao_da_avaliacao(self):
        self.processo.anular_fases_posteriores()

        processo = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        assert processo.avaliacao_finalizada_por_id is None
        assert processo.data_finalizacao_avaliacao is None
        assert processo.avaliacao_motivo_indeferimento == ''
        assert processo.data_entrada_crsc is None

    def test_preserva_os_sorteios_porque_sao_fato_consumado(self):
        """O sorteio aconteceu; anular a avaliação não desfaz o ato de ter sorteado."""
        self.processo.anular_fases_posteriores()

        assert SorteioAvaliadorRSCTae.objects.filter(processo=self.processo).count() == 3

    def test_apaga_a_deliberacao_consolidada_se_existir(self):
        """Em AGUARDANDO_CRSC ela normalmente não existe (nasce na finalização), mas um processo
        revertido por `reverter_deliberacao_final` pode chegar aqui com resíduo dela."""
        DeliberacaoCRSCRSCTae.objects.create(
            processo=self.processo,
            resultado=SituacaoProcesso.DEFERIDO,
            deliberado_por_vinculo=self.servidor_b.get_vinculo(),
        )

        self.processo.anular_fases_posteriores()

        assert not DeliberacaoCRSCRSCTae.objects.filter(processo=self.processo).exists()

    def test_relata_o_que_removeu(self):
        removidos = self.processo.anular_fases_posteriores()

        assert removidos['avaliacoes_anexo'] == 3
        assert removidos['avaliacoes_processo'] == 3
        assert removidos['deliberacoes_item'] == 3
        assert removidos['votos_finais'] == 1


def _processo_em_deliberacao(caso):
    """Processo em AGUARDANDO_CRSC com a fase de avaliação inteira produzida.

    Três avaliadores sorteados e finalizados, um anexo avaliado por cada um, votos de item
    da CRSC e um voto final adiantado — o cenário que a devolução precisa desfazer.
    """
    nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
    processo = ProcessoRSCTae.objects.create(
        vinculo=caso.servidor_a.get_vinculo(),
        nivel_requisitado=nivel,
        situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        avaliacao_finalizada_por=caso.servidor_b.get_vinculo(),
        data_finalizacao_avaliacao=timezone.now(),
        avaliacao_motivo_indeferimento='Motivo preliminar.',
        data_entrada_crsc=timezone.now(),
    )

    requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
    grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
    item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
    caso.anexo = RolSaberCompetenciaAnexo.objects.create(processo=processo, rol_saber_competencia=item, arquivo='x.pdf')

    avaliadores = [caso.servidor_b.get_vinculo(), caso.servidor_c.get_vinculo(), caso.servidor_d.get_vinculo()]
    processo.avaliadores.set(avaliadores)
    for vinculo in avaliadores:
        AvaliacaoProcessoRSCTae.objects.create(
            processo=processo,
            avaliador_vinculo=vinculo,
            data_limite_avaliacao=date.today() + timedelta(days=10),
            finalizada=True,
            pontuacao_final=Decimal('1.00'),
            resultado=SituacaoProcesso.DEFERIDO,
            assinatura_hash='a' * 64,
        )
        AvaliacaoAnexoRSCTae.objects.create(anexo=caso.anexo, avaliador_vinculo=vinculo, situacao=2, pontuacao_validada=Decimal('1.00'))
        SorteioAvaliadorRSCTae.objects.create(processo=processo, avaliador_sorteado=vinculo, motivo=SorteioAvaliadorRSCTae.MOTIVO_INICIAL)
        DeliberacaoItemCRSCRSCTae.objects.create(
            processo=processo,
            anexo=caso.anexo,
            decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR,
            pontuacao_crsc=Decimal('1.00'),
            deliberado_por_vinculo=vinculo,
            assinatura_hash='b' * 64,
        )

    VotoDeliberacaoFinalRSCTae.objects.create(
        processo=processo,
        deliberado_por_vinculo=caso.servidor_b.get_vinculo(),
        resultado=SituacaoProcesso.DEFERIDO,
        pontuacao_final=Decimal('1.00'),
        assinatura_hash='c' * 64,
    )
    return processo


@pytest.mark.django_db(databases='__all__')
class TestAnulacaoEmQualquerCaminho:
    """A anulação é da transição, não da tela: admin e saneamento não podem escapar dela."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.processo = _processo_em_deliberacao(self)

    def _fase_de_avaliacao_de_pe(self):
        return (
            AvaliacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()
            or DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo).exists()
            or VotoDeliberacaoFinalRSCTae.objects.filter(processo=self.processo).exists()
        )

    def test_a_propria_transicao_anula_a_fase_de_avaliacao(self):
        """Quem devolve pelo admin não passa pela view, mas passa por aqui."""
        self.processo.transicionar(SituacaoProcesso.AGUARDANDO_CORRECAO, motivo='Devolução pelo formulário do admin.')

        assert self._fase_de_avaliacao_de_pe() is False

    def test_command_de_saneamento_tambem_anula(self):
        call_command(
            'alterar_situacao_processo',
            self.processo.pk,
            para='aguardando-correcao',
            motivo='Devolução por saneamento.',
            commit=True,
        )

        assert self._fase_de_avaliacao_de_pe() is False

    def test_transicao_para_outro_destino_nao_anula_nada(self):
        """A anulação é específica desta volta — sair para DEFERIDO não pode apagar avaliação."""
        self.processo.transicionar(SituacaoProcesso.DEFERIDO, motivo='Deliberação concluída.')

        assert self._fase_de_avaliacao_de_pe() is True


@pytest.mark.django_db(databases='__all__')
class TestPermissaoDevolucao:
    """Todo membro ativo enxerga a ação; só o presidente a executa."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.processo = _processo_em_deliberacao(self)
        self.comissao = ComissaoRSCTae.objects.create(nome='CRSC 2026', data_inicio=date(2026, 1, 1), ativa=True)
        self.presidente = self._membro(self.servidor_b, presidente=True)
        self.membro = self._membro(self.servidor_c)

    def _membro(self, servidor, presidente=False):
        MembroComissaoRSCTae.objects.create(comissao=self.comissao, vinculo=servidor.get_vinculo(), ativo=True, presidente=presidente)
        return servidor

    def _permissoes(self, servidor, processo=None):
        request = RequestFactory().get('/')
        request.user = servidor.get_user()
        return PermissoesProcesso(request, processo or self.processo)

    def test_membro_da_comissao_ve_a_acao(self):
        assert self._permissoes(self.membro).pode_ver_devolucao_crsc is True

    def test_membro_da_comissao_nao_executa_a_acao(self):
        assert self._permissoes(self.membro).pode_devolver_para_correcao_crsc is False

    def test_presidente_executa_a_acao(self):
        assert self._permissoes(self.presidente).pode_devolver_para_correcao_crsc is True

    def test_quem_nao_e_da_comissao_nao_ve_a_acao(self):
        assert self._permissoes(self.servidor_d).pode_ver_devolucao_crsc is False

    def test_dono_do_processo_nao_ve_a_acao_nem_sendo_presidente(self):
        """O avaliado não age sobre o próprio processo — a regra vale mesmo para o presidente."""
        processo_do_presidente = ProcessoRSCTae.objects.create(
            vinculo=self.presidente.get_vinculo(),
            nivel_requisitado=self.processo.nivel_requisitado,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        perms = self._permissoes(self.presidente, processo_do_presidente)

        assert perms.pode_ver_devolucao_crsc is False
        assert perms.pode_devolver_para_correcao_crsc is False

    def test_fora_da_deliberacao_a_acao_nao_existe(self):
        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(situacao=SituacaoProcesso.EM_ANALISE)
        self.processo.refresh_from_db()

        assert self._permissoes(self.presidente).pode_ver_devolucao_crsc is False


@pytest.mark.django_db(databases='__all__')
class TestViewDevolucao:
    """A devolução pela tela: só o presidente executa, e ela desfaz a fase de avaliação."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.processo = _processo_em_deliberacao(self)
        self.documento = DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            tipo=TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO,
            arquivo='diploma.pdf',
            nome_original='diploma.pdf',
        )
        AvaliacaoDocumentoPreliminarRSCTae.objects.create(documento=self.documento, situacao=SituacaoDocumentoPreliminar.VALIDADO)

        comissao = ComissaoRSCTae.objects.create(nome='CRSC 2026', data_inicio=date(2026, 1, 1), ativa=True)
        MembroComissaoRSCTae.objects.create(comissao=comissao, vinculo=self.servidor_b.get_vinculo(), ativo=True, presidente=True)
        MembroComissaoRSCTae.objects.create(comissao=comissao, vinculo=self.servidor_c.get_vinculo(), ativo=True)
        self.url = f'/rsc_tae/processo/{self.processo.id}/devolver_correcao_crsc/'

    def _post(self, servidor):
        self.client.login(user=servidor.get_user())
        return self.client.post(
            f'{self.url}?_popup=1',
            data={'corrigir_diploma': 'on', 'descricao_diploma': 'Diploma enviado é de outro curso.', 'confirmacao': 'on', 'senha': '123'},
        )

    def test_presidente_devolve_o_processo_para_correcao(self):
        self._post(self.servidor_b)

        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_CORRECAO

    def test_devolucao_apaga_a_fase_de_avaliacao(self):
        self._post(self.servidor_b)

        assert not AvaliacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()
        assert not DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo).exists()

    def test_devolucao_registra_o_apontamento_e_reabre_o_documento(self):
        self._post(self.servidor_b)

        apontamento = ApontamentoCorrecaoRSCTae.objects.get(processo=self.processo)
        assert apontamento.area == AreaCorrecao.DIPLOMA_CERTIFICADO
        assert apontamento.resolvido is False
        self.documento.avaliacao.refresh_from_db()
        assert self.documento.avaliacao.situacao == SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA

    def test_historico_registra_o_que_foi_anulado(self):
        self._post(self.servidor_b)

        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).latest('data_transicao')
        assert registro.situacao_anterior == SituacaoProcesso.AGUARDANDO_CRSC
        assert registro.situacao_nova == SituacaoProcesso.AGUARDANDO_CORRECAO
        assert 'avaliaç' in registro.motivo.lower()

    def test_fecha_a_popup_e_leva_para_a_aba_de_deliberacao(self):
        """A mãe da popup é a tela de deliberação, que o processo acabou de deixar: recarregá-la
        daria 403. A devolução manda a listagem, na aba de onde o processo saiu."""
        resposta = self._post(self.servidor_b)
        conteudo = resposta.content.decode()

        assert 'close_fancybox_and_redirect' in conteudo
        assert '/admin/rsc_tae/processorsctae/?tab=tab_aguardando_crsc' in conteudo

    def test_falha_no_meio_nao_deixa_o_processo_sem_avaliacao(self, monkeypatch):
        """A devolução apaga dados: ou vai inteira, ou não vai. Sem transação única, uma falha
        depois do reset deixaria o processo em deliberação com a avaliação já apagada."""

        def explodir(*_args, **_kwargs):
            raise RuntimeError('falha simulada ao gravar a transição')

        monkeypatch.setattr(ProcessoRSCTae, 'transicionar', explodir)

        with pytest.raises(RuntimeError):
            self._post(self.servidor_b)

        assert AvaliacaoProcessoRSCTae.objects.filter(processo=self.processo).count() == 3
        assert DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo).count() == 3
        assert not ApontamentoCorrecaoRSCTae.objects.filter(processo=self.processo).exists()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_CRSC

    def test_membro_sem_presidencia_nao_devolve(self):
        resposta = self._post(self.servidor_c)

        assert resposta.status_code == 403
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_CRSC

    def test_quem_nao_e_da_comissao_nao_devolve(self):
        resposta = self._post(self.servidor_d)

        assert resposta.status_code == 403

    def test_presidente_abre_o_formulario(self):
        self.client.login(user=self.servidor_b.get_user())
        resposta = self.client.get(f'{self.url}?_popup=1')

        assert resposta.status_code == 200

    def test_botao_diz_devolver_e_nao_solicitar(self):
        """O form é compartilhado com a validação, onde a ação é branda. Aqui ela anula a
        avaliação inteira, e o rótulo herdado ('solicitar correção') subestima isso."""
        self.client.login(user=self.servidor_b.get_user())
        pagina = self.client.get(f'{self.url}?_popup=1').content.decode()

        assert 'Assinar e devolver para correção' in pagina
        assert 'Assinar e solicitar correção' not in pagina


@pytest.mark.django_db(databases='__all__')
class TestAcaoNaTelaDeDeliberacao:
    """A ação aparece para todo membro; só o presidente recebe o link ativo."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.processo = _processo_em_deliberacao(self)
        comissao = ComissaoRSCTae.objects.create(nome='CRSC 2026', data_inicio=date(2026, 1, 1), ativa=True)
        MembroComissaoRSCTae.objects.create(comissao=comissao, vinculo=self.servidor_b.get_vinculo(), ativo=True, presidente=True)
        MembroComissaoRSCTae.objects.create(comissao=comissao, vinculo=self.servidor_c.get_vinculo(), ativo=True)
        self.url = f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/'
        self.link = f'/rsc_tae/processo/{self.processo.id}/devolver_correcao_crsc/'

    def _pagina(self, servidor):
        self.client.login(user=servidor.get_user())
        return self.client.get(self.url).content.decode()

    def test_presidente_recebe_o_link_da_devolucao(self):
        assert self.link in self._pagina(self.servidor_b)

    def test_membro_ve_a_acao_mas_sem_link(self):
        pagina = self._pagina(self.servidor_c)

        assert 'Devolver para correção' in pagina
        assert self.link not in pagina
