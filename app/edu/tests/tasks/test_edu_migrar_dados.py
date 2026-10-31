from __future__ import annotations

import io
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from edu.migracao import ResultadoMigracao


class TestEduMigrarDadosCommand:
    """Testes unitários para o management command edu_migrar_dados."""

    def test_arquivo_inexistente_lanca_command_error(self):
        with pytest.raises(CommandError, match='Arquivo CSV para a etapa "matrizes" não foi encontrado'):
            call_command('edu_migrar_dados', 'matrizes', '/caminho/inexistente/matrizes.csv')

    def test_etapa_all_sem_diretorio_lanca_command_error(self):
        with pytest.raises(CommandError, match='A opção --diretorio é obrigatória'):
            call_command('edu_migrar_dados', 'all')

    @patch('edu.migracao.ImportadorMatrizes')
    def test_executar_etapa_individual_com_sucesso(self, mock_importador_cls):
        mock_inst = MagicMock()
        mock_inst.run.return_value = ResultadoMigracao(
            sucesso=True, total_processados=1, total_validos=1, mensagem='1 registros validados com sucesso.'
        )
        mock_importador_cls.return_value = mock_inst

        with tempfile.NamedTemporaryFile(suffix='.csv') as arq_tmp:
            out = io.StringIO()
            call_command('edu_migrar_dados', 'matrizes', arq_tmp.name, '--apenas-validar', stdout=out)

            mock_importador_cls.assert_called_once()
            args, kwargs = mock_importador_cls.call_args
            assert args[0] == arq_tmp.name
            assert kwargs['apenas_validar'] is True
            assert 'Operação de migração concluída com sucesso!' in out.getvalue()

    @patch('edu.migracao.ImportadorMatrizes')
    def test_executar_etapa_com_erro_de_validacao_lanca_command_error(self, mock_importador_cls):
        mock_inst = MagicMock()
        mock_inst.run.return_value = ResultadoMigracao(
            sucesso=False,
            total_processados=1,
            total_validos=0,
            erros=['Erro de validação'],
            mensagem='Erros de validação encontrados.',
        )
        mock_importador_cls.return_value = mock_inst

        with (
            tempfile.NamedTemporaryFile(suffix='.csv') as arq_tmp,
            pytest.raises(CommandError, match='Ocorreram erros na migração: Etapa matrizes'),
        ):
            call_command('edu_migrar_dados', 'matrizes', arq_tmp.name)

    @patch('edu.management.commands.edu_migrar_dados.Command._executar_etapa')
    def test_executar_todas_as_etapas_via_diretorio(self, mock_executar_etapa):
        mock_executar_etapa.return_value = ResultadoMigracao(sucesso=True, total_processados=1, total_validos=1, mensagem='Sucesso')

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Cria os 8 arquivos vazios no diretório temporário
            arquivos = [
                'matrizes.csv',
                'componentes.csv',
                'cursos.csv',
                'alunos.csv',
                'historicos.csv',
                'procedimentos.csv',
                'equivalencias.csv',
                'inicializar_periodo.csv',
            ]
            for arq in arquivos:
                with open(f'{tmp_dir}/{arq}', 'w') as f:
                    f.write('coluna1;coluna2\n')

            out = io.StringIO()
            call_command('edu_migrar_dados', 'all', '--diretorio', tmp_dir, stdout=out)

            assert mock_executar_etapa.call_count == 8
            assert 'Operação de migração concluída com sucesso!' in out.getvalue()

    def test_render_migracao_cabecalho_card_com_comando(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            'includes/migracao_cabecalho_card.html',
            {
                'comando_etapa': 'matrizes',
                'total_colunas': 28,
                'cabecalho_csv': 'col1;col2',
            },
        )
        assert 'python manage.py edu_migrar_dados matrizes /caminho/do/arquivo.csv' in html
        assert 'Cabeçalho requerido (28 colunas)' in html
        assert 'data-clipboard="col1;col2"' in html

    def test_render_migracao_passos_com_steps(self):
        from django.template.loader import render_to_string

        html = render_to_string('includes/migracao_passos.html', {'passo_atual': 3})
        assert '<ul class="steps steps-migracao">' in html
        assert '1. Matrizes' in html
        assert '3. Cursos' in html
        assert '8. Inicializar período' in html
        assert 'step-info active">3. Cursos</span>' in html
        assert 'step-info">1. Matrizes</span>' in html

    def test_render_migracao_orientacao_csv(self):
        from django.template.loader import render_to_string

        html = render_to_string('includes/migracao_orientacao_csv.html')
        assert 'Orientações para geração do arquivo CSV' in html
        assert 'Separador de colunas' in html
        assert 'UTF-8' in html
