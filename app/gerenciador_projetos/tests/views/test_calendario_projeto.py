"""Calendário de um projeto: as tarefas entram como links, com o título escapado."""

from __future__ import annotations

from datetime import date

from django.urls import reverse

from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory


class TestCalendarioProjeto:
    def test_titulo_da_tarefa_com_html_nao_vira_codigo(self, client):
        gerente = ServidorFactory().get_user()
        projeto = ProjetoFactory(criado_por=gerente)
        projeto.gerentes.add(gerente)
        hoje = date.today()
        TarefaFactory(projeto=projeto, criado_por=gerente, titulo='<img src=x onerror=alert(1)>', data_conclusao_estimada=hoje)
        client.force_login(gerente)

        html = client.post(
            reverse('calendario', args=[projeto.pk]),
            {'data_inicio': hoje.replace(day=1).strftime('%d/%m/%Y'), 'data_fim': hoje.strftime('%d/%m/%Y')},
        ).content.decode()

        assert '&lt;img src=x onerror=alert(1)&gt;' in html
        assert '<img src=x onerror' not in html
