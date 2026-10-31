"""Testes de fluxo da view de estatística de alunos.

Cobrem `edu/views/relatorios.py::estatistica`: renderização, filtros, coerência
gráfico vs. tabela e a exportação XLS (cuja task externa é mockada). Reaproveitam o
cenário acadêmico de `EduTestCase`.

Os testes ficam concentrados em poucos métodos de propósito porque o cenário
(`carga_inicial`) é remontado a cada método — agrupar as verificações de leitura
num só fluxo evita pagar esse custo várias vezes.
"""

from unittest.mock import patch

from django.http import HttpResponse

from edu.tests.test_suap_edu_legacy_base import EduTestCase


class EstatisticaViewTestCase(EduTestCase):
    def _query_padrao(self):
        return {
            'tab': 'listagem',
            'situacao_matricula_periodo': 'SITUACAO_MATRICULADO',
            'periodicidade': 'por_ano_letivo',
            'apartir_do_ano': self.ano_2013.pk,
        }

    def test_renderiza_filtra_e_compoe_grafico(self):
        """Abre a página, aplica filtros e confere a coerência gráfico vs. tabela."""
        # Abre sem parâmetros.
        resp = self.client.get('/edu/estatistica/')
        assert resp.status_code == 200
        conteudo = resp.content.decode()
        assert 'Estatísticas' in conteudo or 'Quantitativo de Alunos' in conteudo

        # Com filtros: monta o gráfico de pizza e a tabela; o somatório das séries
        # do gráfico deve bater com o total geral da tabela.
        resp = self.client.get('/edu/estatistica/', self._query_padrao())
        assert resp.status_code == 200
        assert 'id_grafico_x' in resp.content.decode()
        tabela = resp.context['tabela']
        series = resp.context.get('series') or []
        total_tabela = tabela.registros[-1][len(tabela.colunas) - 1]
        assert sum(valor for _, valor in series) == total_tabela

        # Com termo de busca livre, a página continua íntegra.
        resp = self.client.get('/edu/estatistica/', self._query_padrao() | {'q': 'a'})
        assert resp.status_code == 200
        assert 'id_grafico_x' in resp.content.decode()

    @patch('edu.views.relatorios.tasks.exportar_listagem_alunos_xls', return_value=HttpResponse('OK'))
    def test_exporta_listagem_xls_delega_para_task(self, mock_export):
        """Com `xls=1` na aba de listagem, a exportação é delegada à task (mockada)."""
        params = self._query_padrao() | {'xls': 1, 'tab': 'listagem'}

        resp = self.client.get('/edu/estatistica/', params)

        assert resp.status_code == 200
        assert resp.content == b'OK'
        assert mock_export.called
