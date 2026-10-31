"""Testes de fluxo do módulo de demandas.

Exercitam a máquina de estados da Demanda pelos métodos/regras de domínio —
alterar_situacao (efeito) e Situacao.eh_estado_possivel (encaminhamentos
permitidos) — sem passar por HTTP/templates. São testes de fluxo de alto nível.

Fluxo (ver demandas/models.py, classe Situacao):
  Solicitada -> Em negociação -> Em análise -> Aprovada -> Em desenvolvimento
            -> Em homologação -> Homologada -> Em implantação -> Concluída
  (Cancelada / Suspensa são alcançáveis da maioria das etapas)

Os colaboradores externos (e-mail, GitLab) são mockados pela fixture autouse
sem_efeitos_externos (ver conftest.py).
"""

import pytest

from demandas.models import HistoricoSituacao, Situacao


# `alterar_situacao` busca o grupo 'Recebedor de Demandas': sem `sync_permissions` o teste só passava
# quando outro teste do mesmo worker xdist já tinha sincronizado os grupos.
@pytest.mark.django_db(databases='__all__')
@pytest.mark.usefixtures('sync_permissions')
class TestFluxoDemanda:
    # --- Efeito das transições ---------------------------------------------

    def test_alterar_situacao_avanca_etapa_e_registra_historico(self, demanda, usuario):
        demanda.alterar_situacao(usuario, Situacao.ESTADO_EM_NEGOCIACAO)

        demanda.refresh_from_db()
        assert demanda.situacao == Situacao.ESTADO_EM_NEGOCIACAO
        assert HistoricoSituacao.objects.filter(demanda=demanda, situacao=Situacao.ESTADO_EM_NEGOCIACAO).exists()

    def test_cancelar_demanda_limpa_a_prioridade(self, demanda, usuario):
        demanda.prioridade = 1
        demanda.save()

        demanda.alterar_situacao(usuario, Situacao.ESTADO_CANCELADO)

        demanda.refresh_from_db()
        assert demanda.situacao == Situacao.ESTADO_CANCELADO
        assert demanda.prioridade is None

    def test_fluxo_completo_da_solicitacao_a_conclusao(self, demanda, usuario):
        etapas = [
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_IMPLANTACAO,
            Situacao.ESTADO_CONCLUIDO,
        ]
        for etapa in etapas:
            demanda.alterar_situacao(usuario, etapa)

        demanda.refresh_from_db()
        assert demanda.situacao == Situacao.ESTADO_CONCLUIDO
        assert demanda.eh_situacao_terminal()

    # --- Regras de encaminhamento (máquina de estados) ----------------------

    def test_encaminhamento_valido_a_partir_de_solicitada(self, demanda):
        assert Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_EM_NEGOCIACAO)

    def test_nao_pula_etapas_de_solicitada_para_concluida(self, demanda):
        assert not Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_CONCLUIDO)

    def test_etapa_terminal_nao_encaminha_para_lugar_nenhum(self, demanda):
        demanda.situacao = Situacao.ESTADO_CANCELADO
        assert not Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_EM_NEGOCIACAO)
