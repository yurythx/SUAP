"""Situação do processo derivada da avaliação mais atrasada (issue #16768)."""

import importlib
import pytest
from django.apps.registry import apps

from progressao_docente.tests.factories import AvaliacaoFactory, ProgressaoDocenteFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

migracao = importlib.import_module('progressao_docente.migrations.0045_ressincronizar_situacao_progressao')

pytestmark = pytest.mark.django_db


def _progressao(situacao=ProgressaoDocente.AGUARDANDO_PREENCHIMENTO):
    """Quem é o avaliado não importa em nenhum teste daqui; a factory cria um."""
    return ProgressaoDocenteFactory(situacao=situacao)


def _avaliacao(progressao, situacao):
    return AvaliacaoFactory(progressao=progressao, situacao=situacao)


class TestSituacaoDerivada:
    def test_sem_avaliacoes_nao_deriva(self, sync_permissions):
        progressao = _progressao()
        assert progressao.situacao_derivada_das_avaliacoes() is None

    def test_a_iniciar_nao_deriva(self, sync_permissions):
        """A_INICIAR é pré-fluxo: as avaliações já existem, mas a CPPD ainda não liberou
        o processo (`pode_iniciar` exige esse estado). Derivar aqui iniciaria o processo
        pelas costas de quem decide."""
        progressao = _progressao(ProgressaoDocente.A_INICIAR)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        assert progressao.situacao_derivada_das_avaliacoes() is None

    def test_finalizado_e_terminal(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.FINALIZADO)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        assert progressao.situacao_derivada_das_avaliacoes() is None

    @pytest.mark.parametrize(
        ('situacao_avaliacao', 'esperado'),
        [
            (Avaliacao.AGUARDANDO_PREENCHIMENTO, ProgressaoDocente.AGUARDANDO_PREENCHIMENTO),
            (Avaliacao.EDITACAO_PARA_REAVALIACAO, ProgressaoDocente.REAVALIACAO),
            (Avaliacao.EM_AVALIACAO, ProgressaoDocente.EM_AVALIACAO),
            (Avaliacao.REAVALIACAO, ProgressaoDocente.REAVALIACAO),
            (Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO),
            (Avaliacao.CONCLUIDA, ProgressaoDocente.CIENTE_RESULTADO),
        ],
    )
    def test_avaliacao_unica_mapeia_direto(self, sync_permissions, situacao_avaliacao, esperado):
        progressao = _progressao()
        _avaliacao(progressao, situacao_avaliacao)
        assert progressao.situacao_derivada_das_avaliacoes() == esperado

    def test_caso_da_issue_concluida_mais_aguardando_preenchimento(self, sync_permissions):
        """Processo 1392: uma avaliação concluída e outra aguardando preenchimento.

        A cascata antiga não casava com nenhuma condição e o processo ficava parado em
        "Aguardando Ciência de Resultado" — etapa que ninguém estava cumprindo.
        """
        progressao = _progressao(ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        assert progressao.situacao_derivada_das_avaliacoes() == ProgressaoDocente.AGUARDANDO_PREENCHIMENTO

    def test_a_mais_atrasada_vence_independente_da_ordem_de_criacao(self, sync_permissions):
        progressao = _progressao()
        _avaliacao(progressao, Avaliacao.AGUARDANDO_CIENCIA_RESULTADO)
        _avaliacao(progressao, Avaliacao.EM_AVALIACAO)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        assert progressao.situacao_derivada_das_avaliacoes() == ProgressaoDocente.EM_AVALIACAO

    def test_todas_concluidas_avanca_para_ciente(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        assert progressao.situacao_derivada_das_avaliacoes() == ProgressaoDocente.CIENTE_RESULTADO


class TestSaveAplicaADerivacao:
    def test_salvar_avaliacao_ressincroniza_o_processo(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.AGUARDANDO_PREENCHIMENTO

    def test_processo_finalizado_nao_regride(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.FINALIZADO)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.FINALIZADO


class TestConstantesDaMigracao:
    """A migração repete os valores das situações como literais.

    Ela precisa: `RunPython` recebe modelos históricos, sem as constantes da classe atual.
    O risco de duplicar é justamente este — os dois lados saírem de sincronia em silêncio e
    a migração passar a gravar situações erradas. Estes testes prendem os dois lados.
    """

    def test_valores_das_situacoes_conferem(self):
        assert migracao.AVALIACAO_AGUARDANDO_PREENCHIMENTO == Avaliacao.AGUARDANDO_PREENCHIMENTO
        assert migracao.AVALIACAO_EM_AVALIACAO == Avaliacao.EM_AVALIACAO
        assert migracao.AVALIACAO_REAVALIACAO == Avaliacao.REAVALIACAO
        assert migracao.AVALIACAO_AGUARDANDO_CIENCIA_RESULTADO == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
        assert migracao.AVALIACAO_CONCLUIDA == Avaliacao.CONCLUIDA
        assert migracao.AVALIACAO_EDITACAO_PARA_REAVALIACAO == Avaliacao.EDITACAO_PARA_REAVALIACAO
        assert migracao.PROGRESSAO_A_INICIAR == ProgressaoDocente.A_INICIAR
        assert migracao.PROGRESSAO_AGUARDANDO_PREENCHIMENTO == ProgressaoDocente.AGUARDANDO_PREENCHIMENTO
        assert migracao.PROGRESSAO_EM_AVALIACAO == ProgressaoDocente.EM_AVALIACAO
        assert migracao.PROGRESSAO_REAVALIACAO == ProgressaoDocente.REAVALIACAO
        assert migracao.PROGRESSAO_AGUARDANDO_CIENCIA_RESULTADO == ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO
        assert migracao.PROGRESSAO_CIENTE_RESULTADO == ProgressaoDocente.CIENTE_RESULTADO
        assert migracao.PROGRESSAO_FINALIZADO == ProgressaoDocente.FINALIZADO

    def test_precedencia_e_mapa_iguais_aos_do_modelo(self):
        from progressao_docente.models import ETAPAS_AVALIACAO_DA_MAIS_ATRASADA, SITUACAO_PROCESSO_POR_ETAPA_DA_AVALIACAO

        assert tuple(migracao.ETAPAS_DA_MAIS_ATRASADA) == tuple(ETAPAS_AVALIACAO_DA_MAIS_ATRASADA)
        assert migracao.SITUACAO_POR_ETAPA == SITUACAO_PROCESSO_POR_ETAPA_DA_AVALIACAO

    def test_toda_situacao_de_avaliacao_esta_na_precedencia(self):
        from progressao_docente.models import ETAPAS_AVALIACAO_DA_MAIS_ATRASADA

        assert {valor for valor, _ in Avaliacao.SITUACAO_CHOICES} == set(ETAPAS_AVALIACAO_DA_MAIS_ATRASADA)


class TestMigracaoDeRessincronizacao:
    class _AppsFalso:
        """Entrega os modelos atuais no lugar dos históricos.

        Serve porque `ressincronizar` só usa ORM básico — `exclude`, `filter`, `values_list`,
        `iterator` e `update` —, sem tocar em métodos, propriedades ou managers das classes;
        o que ela lê das constantes está preso por TestConstantesDaMigracao. O pytest do SUAP
        roda com `--no-migrations`, então não há estado histórico disponível para exercitar o
        `apps` real.
        """

        _mapa = {'progressaodocente': ProgressaoDocente, 'avaliacao': Avaliacao}

        def get_model(self, app_label, model_name):
            return self._mapa[model_name.lower()]

    def test_corrige_o_processo_defasado(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.AGUARDANDO_PREENCHIMENTO)
        _avaliacao(progressao, Avaliacao.CONCLUIDA)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        # força o estado defasado sem passar pelo save() da Avaliacao
        ProgressaoDocente.objects.filter(pk=progressao.pk).update(situacao=ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO)

        migracao.ressincronizar(self._AppsFalso(), None)

        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.AGUARDANDO_PREENCHIMENTO

    def test_nao_toca_em_finalizado(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.AGUARDANDO_PREENCHIMENTO)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        ProgressaoDocente.objects.filter(pk=progressao.pk).update(situacao=ProgressaoDocente.FINALIZADO)

        migracao.ressincronizar(self._AppsFalso(), None)

        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.FINALIZADO

    def test_nao_toca_em_a_iniciar(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.A_INICIAR)
        _avaliacao(progressao, Avaliacao.AGUARDANDO_PREENCHIMENTO)
        ProgressaoDocente.objects.filter(pk=progressao.pk).update(situacao=ProgressaoDocente.A_INICIAR)

        migracao.ressincronizar(self._AppsFalso(), None)

        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.A_INICIAR

    def test_nao_toca_em_processo_sem_avaliacoes(self, sync_permissions):
        progressao = _progressao(ProgressaoDocente.A_INICIAR)
        migracao.ressincronizar(self._AppsFalso(), None)
        progressao.refresh_from_db()
        assert progressao.situacao == ProgressaoDocente.A_INICIAR


class TestRotuloDaAssinatura:
    def _avaliacao_simples(self):
        progressao = _progressao()
        return _avaliacao(progressao, Avaliacao.CONCLUIDA)

    def test_sem_assinatura_fica_pendente(self, sync_permissions):
        avaliacao = self._avaliacao_simples()
        assert 'Pendente' in avaliacao._situacao_assinaturas('conteudo', '', '')

    def test_assinatura_invalida_sem_snapshot_e_nao_verificavel(self, sync_permissions):
        """320 assinaturas na base foram feitas antes de o snapshot existir.

        Sem ele não dá para distinguir reordenação de alteração de conteúdo, e "Inválida"
        sugeriria adulteração onde há apenas ausência de dado histórico.
        """
        avaliacao = self._avaliacao_simples()
        html = avaliacao._situacao_assinaturas('conteudo atual', 'assinatura-que-nao-confere', '')
        assert 'Não verificável' in html
        assert 'Inválida' not in html

    def test_assinatura_invalida_com_snapshot_segue_invalida(self, sync_permissions):
        avaliacao = self._avaliacao_simples()
        html = avaliacao._situacao_assinaturas('conteudo atual', 'assinatura-que-nao-confere', 'conteudo assinado')
        assert 'Inválida' in html

    def test_assinatura_valida(self, sync_permissions):
        from progressoes import assinatura as assinatura_utils

        avaliacao = self._avaliacao_simples()
        conteudo = 'conteudo qualquer'
        assinatura = assinatura_utils.gera_assinatura(conteudo, 'chave')
        assert 'Válida' in avaliacao._situacao_assinaturas(conteudo, assinatura, conteudo)

    def test_o_gate_olha_a_assinatura_recebida_e_nao_a_do_avaliador(self, sync_permissions):
        """O método é genérico; antes ele decidia pelo campo `assinatura_avaliador`."""
        avaliacao = self._avaliacao_simples()
        avaliacao.assinatura_avaliador = 'assinatura-do-avaliador'
        assert 'Pendente' in avaliacao._situacao_assinaturas('conteudo', '', '')
