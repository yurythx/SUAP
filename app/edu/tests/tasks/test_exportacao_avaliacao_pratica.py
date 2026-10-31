import csv
from types import SimpleNamespace

import pytest

from edu.tasks import (
    download_professores_orientadores_avaliacao_pratica,
    download_professores_supervisores_avaliacao_pratica,
)

# task_mock e patch_task_model vêm de edu/tests/tasks/conftest.py


@pytest.fixture
def csv_path(tmp_path):
    return str(tmp_path / 'avaliacao_pratica.csv')


def _ler_csv(caminho):
    with open(caminho) as arquivo:
        return list(csv.reader(arquivo, delimiter=';'))


class _QuerySetFake:
    def __init__(self, itens):
        self._itens = itens

    def count(self):
        return len(self._itens)

    def __iter__(self):
        return iter(self._itens)


def _queryset_fake(itens):
    return _QuerySetFake(itens)


def _convocacao_orientador(*, cpf, periodo, mes=6, nome='Aluno'):
    pessoa_fisica = SimpleNamespace(cpf=cpf)
    pessoa = SimpleNamespace(pessoafisica=pessoa_fisica)
    vinculo = SimpleNamespace(pessoa=pessoa)
    professor = SimpleNamespace(vinculo=vinculo)
    estagio = SimpleNamespace(professor_orientador=professor)
    periodo_convocacao = SimpleNamespace(data_fim=SimpleNamespace(month=mes))
    aluno = SimpleNamespace(pessoa_fisica=SimpleNamespace(nome=nome))
    return SimpleNamespace(
        percentual_ch_cumprida=80.0,
        estagio_docente=estagio,
        periodo_convocacao_regencia=periodo_convocacao,
        aluno=aluno,
        periodo_letivo=periodo,
    )


def _convocacao_supervisor(*, cpf, periodo, codigo_inep, mes=6, nome='Aluno'):
    local = SimpleNamespace(codigo_inep=codigo_inep)
    estagio = SimpleNamespace(cpf_professor_colaborador=cpf, local=local)
    periodo_convocacao = SimpleNamespace(data_fim=SimpleNamespace(month=mes))
    aluno = SimpleNamespace(pessoa_fisica=SimpleNamespace(nome=nome))
    return SimpleNamespace(
        percentual_ch_cumprida=80.0,
        estagio_docente=estagio,
        periodo_convocacao_regencia=periodo_convocacao,
        aluno=aluno,
        periodo_letivo=periodo,
    )


def _executar_exportacao_orientador(caminho_csv, convocacoes, task):
    download_professores_orientadores_avaliacao_pratica(caminho_csv, _queryset_fake(convocacoes), '1', '2', '3', task=task)
    return _ler_csv(caminho_csv)


def _executar_exportacao_supervisor(caminho_csv, convocacoes, task):
    download_professores_supervisores_avaliacao_pratica(caminho_csv, _queryset_fake(convocacoes), '1', '2', '3', task=task)
    return _ler_csv(caminho_csv)


@pytest.mark.usefixtures('patch_task_model')
class TestExportacaoProfessoresOrientadoresAvaliacaoPratica:
    def test_exporta_uma_linha_por_orientador_em_mesmo_periodo(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_orientador(cpf='12345678901', periodo=1, mes=3, nome='Aluno A'),
            _convocacao_orientador(cpf='98765432101', periodo=1, mes=3, nome='Aluno B'),
        ]
        linhas = _executar_exportacao_orientador(csv_path, convocacoes, task_mock)

        assert len(linhas) == 3
        assert linhas[1][5] == '12345678901'
        assert linhas[2][5] == '98765432101'

    def test_nao_duplica_orientador_quando_chave_igual(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_orientador(cpf='12345678901', periodo=1, mes=3, nome='Aluno A'),
            _convocacao_orientador(cpf='12345678901', periodo=1, mes=3, nome='Aluno B'),
        ]
        linhas = _executar_exportacao_orientador(csv_path, convocacoes, task_mock)

        assert len(linhas) == 2
        assert linhas[1][5] == '12345678901'

    def test_mantem_duas_linhas_quando_muda_periodo(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_orientador(cpf='12345678901', periodo=1, mes=3, nome='Aluno A'),
            _convocacao_orientador(cpf='12345678901', periodo=2, mes=9, nome='Aluno A'),
        ]
        linhas = _executar_exportacao_orientador(csv_path, convocacoes, task_mock)

        assert len(linhas) == 3
        assert linhas[1][1] == '1'
        assert linhas[2][1] == '2'


@pytest.mark.usefixtures('patch_task_model')
class TestExportacaoProfessoresSupervisoresAvaliacaoPratica:
    def test_exporta_uma_linha_por_supervisor_quando_chaves_diferentes(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_supervisor(cpf='12345678901', periodo=1, mes=3, codigo_inep='11111111', nome='Aluno A'),
            _convocacao_supervisor(cpf='98765432101', periodo=1, mes=3, codigo_inep='22222222', nome='Aluno B'),
        ]
        linhas = _executar_exportacao_supervisor(csv_path, convocacoes, task_mock)

        assert len(linhas) == 3
        assert linhas[1][5] == '12345678901'
        assert linhas[2][5] == '98765432101'

    def test_nao_duplica_supervisor_quando_chave_igual(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_supervisor(cpf='12345678901', periodo=1, mes=3, codigo_inep='11111111', nome='Aluno A'),
            _convocacao_supervisor(cpf='12345678901', periodo=1, mes=3, codigo_inep='11111111', nome='Aluno B'),
        ]
        linhas = _executar_exportacao_supervisor(csv_path, convocacoes, task_mock)

        assert len(linhas) == 2
        assert linhas[1][5] == '12345678901'

    def test_mantem_duas_linhas_quando_supervisor_mesmo_em_escolas_diferentes(self, csv_path, task_mock):
        convocacoes = [
            _convocacao_supervisor(cpf='12345678901', periodo=1, mes=3, codigo_inep='11111111', nome='Aluno A'),
            _convocacao_supervisor(cpf='12345678901', periodo=1, mes=3, codigo_inep='22222222', nome='Aluno A'),
        ]
        linhas = _executar_exportacao_supervisor(csv_path, convocacoes, task_mock)

        assert len(linhas) == 3
