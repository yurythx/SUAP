"""Abas de relatórios de atividades da prática profissional (``/estagios/pratica_profissional/<pk>/?tab=...``).

A assinatura eletrônica de um relatório só é liberada quando o relatório da contraparte (estagiário x
supervisor) do mesmo período existe e não diverge dele (#17829). Enquanto houver divergência, a tela avisa
quem pode editar o relatório ou resolver as divergências (o orientador).
"""

from __future__ import annotations

import datetime

import pytest
from django.test import Client

from estagios.tests.factories import PraticaProfissionalFactory, RelatorioSemestralEstagioFactory

# aba -> (relatório é do supervisor?, aviso exibido no relatório)
ABAS = {
    'relatorios': (False, 'Este relatório possui divergências com o relatório do supervisor.'),
    'avaliacaosupervisor': (True, 'Este relatório possui divergências com o relatório do aluno.'),
}


@pytest.fixture
def cliente(db: None, sync_permissions: None, suap_client: Client) -> Client:
    return suap_client


@pytest.mark.parametrize('aba', ABAS)
def test_orientador_sem_edicao_ve_aviso_de_divergencia(cliente: Client, aba: str) -> None:
    eh_relatorio_do_supervisor, aviso = ABAS[aba]
    estagio = PraticaProfissionalFactory()
    # O único período vigente já tem relatório: o orientador não pode editar o relatório de período antigo
    # (de antes de um aditivo mudar as datas), mas ainda pode resolver as divergências dele.
    RelatorioSemestralEstagioFactory(pratica_profissional=estagio, eh_relatorio_do_supervisor=eh_relatorio_do_supervisor)
    fim_antigo = estagio.data_prevista_fim - datetime.timedelta(days=15)
    relatorio_antigo = RelatorioSemestralEstagioFactory(
        pratica_profissional=estagio, fim=fim_antigo, eh_relatorio_do_supervisor=eh_relatorio_do_supervisor, realizou_outras_atividades=True
    )
    RelatorioSemestralEstagioFactory(pratica_profissional=estagio, fim=fim_antigo, eh_relatorio_do_supervisor=not eh_relatorio_do_supervisor)
    orientador = estagio.orientador.vinculo.user
    assert not relatorio_antigo.pode_editar(orientador)
    cliente.force_login(orientador)

    resposta = cliente.get(f'/estagios/pratica_profissional/{estagio.pk}/?tab={aba}')

    assert resposta.status_code == 200
    assert aviso in resposta.content.decode()
