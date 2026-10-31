from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rh.deduplicacao.entrada import Politica

from edu.tasks import (
    importar_alunos_csv_v2,
    importar_componentes_csv,
    importar_cursos_csv,
    importar_equivalencia_csv,
    importar_historico_aluno_csv,
    importar_matrizes_csv,
    importar_procedimento_matricula_csv,
    inicializar_periodo_letivo,
)


@pytest.mark.usefixtures('patch_task_model')
class TestMigracaoTarefasBase:
    """Testes para o fluxo base de importação e validação de CSV."""

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_matrizes')
    @patch('edu.migracao.Matriz.objects.create')
    def test_importar_matrizes_csv_sucesso(self, mock_matriz_create, mock_validar, mock_commit, mock_savepoint, task_mock):
        csv_data = 'Matriz.sigla;Matriz.descricao\nM1;Matriz 1\n'
        mock_validar.return_value = ({'sigla': 'M1', 'descricao': 'Matriz 1'}, [])

        func = getattr(importar_matrizes_csv, '__wrapped__', importar_matrizes_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_validar.assert_called_once()
        mock_matriz_create.assert_called_once_with(sigla='M1', descricao='Matriz 1')
        task_mock.update_progress.assert_called_once_with(3)
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_matrizes')
    @patch('edu.migracao.Matriz.objects.update_or_create')
    def test_importar_matrizes_csv_com_id_atualiza(self, mock_matriz_update_or_create, mock_validar, mock_commit, mock_savepoint, task_mock):
        csv_data = 'Matriz.sigla;Matriz.descricao\nM1;Matriz 1\n'
        mock_validar.return_value = ({'id': 123, 'sigla': 'M1', 'descricao': 'Matriz 1'}, [])

        func = getattr(importar_matrizes_csv, '__wrapped__', importar_matrizes_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_matriz_update_or_create.assert_called_once_with(id=123, defaults={'sigla': 'M1', 'descricao': 'Matriz 1'})

    @patch('edu.migracao.validar_matrizes')
    @patch('edu.migracao.Matriz.objects.create')
    def test_importar_matrizes_apenas_validar(self, mock_matriz_create, mock_validar, task_mock):
        csv_data = 'Matriz.sigla;Matriz.descricao\nM1;Matriz 1\n'
        mock_validar.return_value = ({'sigla': 'M1', 'descricao': 'Matriz 1'}, [])

        func = getattr(importar_matrizes_csv, '__wrapped__', importar_matrizes_csv)
        func(csv_data, apenas_validar=True, ignorar_obrigatorios=False, task=task_mock)

        mock_validar.assert_called_once()
        mock_matriz_create.assert_not_called()
        task_mock.finalize.assert_called_once_with('1 registros validados com sucesso.', '..')

    @patch('edu.migracao.validar_matrizes')
    def test_importar_matrizes_com_erros_validacao(self, mock_validar, task_mock):
        csv_data = 'Matriz.sigla;Matriz.descricao\nM1;Matriz 1\n'
        mock_validar.return_value = (None, ['Campo obrigatório ausente'])

        func = getattr(importar_matrizes_csv, '__wrapped__', importar_matrizes_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        task_mock.finalize.assert_called_once()
        args, kwargs = task_mock.finalize.call_args
        assert 'Erros de validação foram encontrados' in args[0]
        assert kwargs.get('error') is True
        assert 'file_path' in kwargs

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_componentes')
    @patch('edu.migracao.Diretoria.objects.get')
    @patch('edu.migracao.Componente.objects.update_or_create')
    @patch('edu.migracao.ComponenteCurricular.objects.update_or_create')
    def test_importar_componentes_csv_sucesso(
        self,
        mock_cc_update_or_create,
        mock_comp_update_or_create,
        mock_diretoria_get,
        mock_validar,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Componente.sigla_legado;Componente.descricao\nC1;Componente 1\n'
        registro = {
            'componente_descricao': 'Desc 1',
            'componente_sigla_legado': 'C1',
            'componente_ativo': True,
            'componente_ch_qtd_creditos': 4,
            'componente_abreviatura': 'D1',
            'componente_tipo_id': 1,
            'componente_ch_hora_relogio': 60,
            'componente_ch_hora_aula': 72,
            'componente_nivel_ensino_id': 2,
            'componente_observacao': '',
            'componentecurricular_qtd_avaliacoes': 4,
            'componentecurricular_ch_semanal_1s': 2,
            'componentecurricular_ch_semanal_2s': 2,
            'componentecurricular_optativo': False,
            'componentecurricular_periodo': 1,
            'componentecurricular_tipo_id': 1,
            'componentecurricular_ch_presencial': 60,
            'componentecurricular_ch_pratica': 0,
            'componentecurricular_ch_extensao': 0,
            'componentecurricular_ch_pcc': 0,
            'componentecurricular_avaliacao_por_conceito': False,
            'componentecurricular_segundo_semestre': False,
            'componentecurricular_pode_fechar_pendencia': False,
            'componentecurricular_nucleo_id': None,
            'matriz_id': 10,
            'componentecurricular_co_requisitos': [],
            'componentecurricular_pre_requisitos': [],
        }
        mock_validar.return_value = (registro, [])
        mock_comp = MagicMock()
        mock_comp_update_or_create.return_value = (mock_comp, True)
        mock_cc = MagicMock()
        mock_cc_update_or_create.return_value = (mock_cc, True)

        func = getattr(importar_componentes_csv, '__wrapped__', importar_componentes_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_validar.assert_called_once()
        mock_comp_update_or_create.assert_called_once()
        mock_cc_update_or_create.assert_called_once()
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_cursos')
    @patch('edu.migracao.CursoCampus.objects.get')
    def test_importar_cursos_csv_existente(self, mock_curso_get, mock_validar, mock_commit, mock_savepoint, task_mock):
        csv_data = 'CursoCampus.codigo;CursoCampus.descricao\nCUR1;Curso 1\n'
        registro = {'codigo': 'CUR1', 'descricao': 'Curso 1', 'matrizes': [1, 2]}
        mock_validar.return_value = (registro, [])
        curso_existente = MagicMock()
        mock_curso_get.return_value = curso_existente

        func = getattr(importar_cursos_csv, '__wrapped__', importar_cursos_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_curso_get.assert_called_once_with(codigo='CUR1')
        curso_existente.save.assert_called_once()
        curso_existente.matrizes.clear.assert_called_once()
        assert curso_existente.matrizes.add.call_count == 2
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_alunos')
    @patch('edu.migracao.Aluno.objects.filter')
    @patch('edu.migracao.PessoaFisica.objects.obter_ou_criar')
    @patch('edu.migracao.Aluno.objects.create')
    def test_importar_alunos_csv_novo_com_deficiencias(
        self,
        mock_aluno_create,
        mock_pf_create,
        mock_aluno_filter,
        mock_validar,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Aluno.matricula;PessoaFisica.nome\n2026101;Fulano\n'
        registro = {
            'matricula': '2026101',
            'data_matricula': '2026-02-01',
            'email_qacademico': 'fulano@exemplo.com',
            'PessoaFisica': {'nome': 'Fulano', 'cpf': '11122233344'},
            'deficiencias': [101, 102],
            'outras_nees': [201],
        }
        mock_validar.return_value = (registro, [])
        mock_aluno_filter.return_value.first.return_value = None
        mock_pf = MagicMock(id=99)
        mock_pf_create.return_value = (mock_pf, True)
        mock_aluno = MagicMock(id=55)
        mock_aluno_create.return_value = mock_aluno
        mock_aluno.get_vinculo.return_value = MagicMock()

        func = getattr(importar_alunos_csv_v2, '__wrapped__', importar_alunos_csv_v2)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        # aluno novo reusa a pessoa do documento em vez de criar outra (deduplicação de pessoas)
        mock_pf_create.assert_called_once_with({'nome': 'Fulano', 'cpf': '11122233344', 'passaporte': None, 'pais_origem': None}, Politica.CAUTELOSA)
        mock_aluno.deficiencias.set.assert_called_once_with([101, 102])
        mock_aluno.outras_nees.set.assert_called_once_with([201])
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_historico_aluno')
    @patch('edu.migracao.Aluno.objects.get')
    @patch('edu.migracao.Aluno.objects.filter')
    @patch('edu.migracao.MatriculaPeriodo.objects.update_or_create')
    @patch('edu.migracao.RegistroHistorico.objects.update_or_create')
    def test_importar_historico_aluno_csv_sucesso(
        self,
        mock_rh_update_or_create,
        mock_mp_update_or_create,
        mock_aluno_filter,
        mock_aluno_get,
        mock_validar,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Aluno.id;MatriculaPeriodo.ano_letivo\n1;2026\n'
        registro = {
            'aluno_id': 1,
            'MatriculaPeriodo': {'ano_letivo_id': 2026, 'periodo_letivo': 1, 'situacao_id': 1},
            'RegistroHistorico': {'identificador_externo': '999', 'media_final': 85},
        }
        mock_validar.return_value = (registro, [])
        mock_aluno_get.return_value = MagicMock(id=1)
        mock_mp_update_or_create.return_value = (MagicMock(), True)

        func = getattr(importar_historico_aluno_csv, '__wrapped__', importar_historico_aluno_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_aluno_get.assert_called_once_with(pk=1)
        mock_mp_update_or_create.assert_called_once()
        mock_rh_update_or_create.assert_called_once()
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.transaction.savepoint_rollback')
    @patch('edu.migracao.validar_procedimento_matricula')
    @patch('edu.migracao.Aluno.objects.get')
    @patch('edu.migracao.MatriculaPeriodo.objects.update_or_create')
    @patch('edu.migracao.ProcedimentoMatricula.objects.update_or_create')
    def test_importar_procedimento_matricula_csv_sucesso(
        self,
        mock_pm_update_or_create,
        mock_mp_update_or_create,
        mock_aluno_get,
        mock_validar,
        mock_rollback,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Aluno.id;ProcedimentoMatricula.tipo\n1;Trancamento\n'
        registro = {
            'aluno_id': 1,
            'ProcedimentoMatricula': {'tipo': 'Trancamento Voluntário', 'identificador_externo': '555'},
            'MatriculaPeriodo': {'ano_letivo_id': 2026, 'periodo_letivo': 1},
        }
        mock_validar.return_value = (registro, [])
        mock_aluno_get.return_value = MagicMock(id=1)
        mock_mp_update_or_create.return_value = (MagicMock(), True)

        func = getattr(importar_procedimento_matricula_csv, '__wrapped__', importar_procedimento_matricula_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_aluno_get.assert_called_once_with(pk=1)
        mock_mp_update_or_create.assert_called_once()
        mock_pm_update_or_create.assert_called_once()
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_equivalencia')
    @patch('edu.migracao.Aluno.objects.get')
    @patch('edu.migracao.MatriculaPeriodo.objects.get_or_create')
    @patch('edu.migracao.AproveitamentoComponente.objects.get_or_create')
    def test_importar_equivalencia_csv_sucesso(
        self,
        mock_aproveitamento_get_or_create,
        mock_mp_get_or_create,
        mock_aluno_get,
        mock_validar,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Aluno.id;componente_curricular_id\n1;50\n'
        registro = {
            'aluno_id': 1,
            'componente_currricular_id': 50,
            'MatriculaPeriodo': {'ano_letivo_id': 2026, 'periodo_letivo': 1},
            'registros_historico': [MagicMock()],
        }
        mock_validar.return_value = (registro, [])
        mock_aluno_get.return_value = MagicMock(id=1)
        mock_mp_get_or_create.return_value = (MagicMock(), True)
        mock_aproveitamento = MagicMock()
        mock_aproveitamento_get_or_create.return_value = (mock_aproveitamento, True)

        func = getattr(importar_equivalencia_csv, '__wrapped__', importar_equivalencia_csv)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_aluno_get.assert_called_once_with(pk=1)
        mock_mp_get_or_create.assert_called_once()
        mock_aproveitamento_get_or_create.assert_called_once()
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_commit')
    @patch('edu.migracao.validar_matricula')
    @patch('edu.migracao.Aluno.objects.get')
    @patch('edu.migracao.RegistroHistorico.objects.filter')
    def test_inicializar_periodo_letivo_sucesso(
        self,
        mock_rh_filter,
        mock_aluno_get,
        mock_validar,
        mock_commit,
        mock_savepoint,
        task_mock,
    ):
        csv_data = 'Aluno.id\n1\n'
        mock_validar.return_value = ({'aluno_id': 1}, [])
        mock_aluno = MagicMock(id=1, situacao_id=1)
        mock_aluno_get.return_value = mock_aluno
        mock_rh_filter.return_value = []

        func = getattr(inicializar_periodo_letivo, '__wrapped__', inicializar_periodo_letivo)
        func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_aluno_get.assert_called_once_with(pk=1)
        mock_aluno.recalcular_periodo_matriz_periodos_letivos.assert_called_once()
        mock_aluno.atualizar_periodo_referencia.assert_called_once()
        task_mock.finalize.assert_called_once_with('1 registros criados/atualizados com sucesso.', '..')

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_rollback')
    @patch('edu.migracao.validar_historico_aluno')
    @patch('edu.migracao.Aluno.objects.get')
    def test_importar_historico_aluno_csv_erro_executa_rollback_unico(
        self,
        mock_aluno_get,
        mock_validar,
        mock_rollback,
        mock_savepoint,
        task_mock,
    ):
        mock_savepoint.return_value = 'sp_hist'
        mock_validar.return_value = ({'aluno_id': 1}, [])
        mock_aluno_get.side_effect = RuntimeError('Falha de banco ao buscar aluno')

        csv_data = 'Aluno.id;MatriculaPeriodo.ano_letivo\n1;2026\n'
        func = getattr(importar_historico_aluno_csv, '__wrapped__', importar_historico_aluno_csv)

        with pytest.raises(RuntimeError, match='Falha de banco ao buscar aluno'):
            func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_rollback.assert_called_once_with('sp_hist')
        task_mock.add_log.assert_called_once()
        assert 'Erro na linha' in task_mock.add_log.call_args[0][0]

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_rollback')
    @patch('edu.migracao.validar_procedimento_matricula')
    @patch('edu.migracao.Aluno.objects.get')
    def test_importar_procedimento_matricula_csv_erro_executa_rollback_unico(
        self,
        mock_aluno_get,
        mock_validar,
        mock_rollback,
        mock_savepoint,
        task_mock,
    ):
        mock_savepoint.return_value = 'sp_proc'
        mock_validar.return_value = ({'aluno_id': 1}, [])
        mock_aluno_get.side_effect = RuntimeError('Falha de banco ao buscar aluno')

        csv_data = 'Aluno.id;ProcedimentoMatricula.tipo\n1;Trancamento\n'
        func = getattr(importar_procedimento_matricula_csv, '__wrapped__', importar_procedimento_matricula_csv)

        with pytest.raises(RuntimeError, match='Falha de banco ao buscar aluno'):
            func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_rollback.assert_called_once_with('sp_proc')
        task_mock.add_log.assert_called_once()
        assert 'Erro na linha' in task_mock.add_log.call_args[0][0]

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_rollback')
    @patch('edu.migracao.validar_equivalencia')
    @patch('edu.migracao.Aluno.objects.get')
    def test_importar_equivalencia_csv_erro_executa_rollback_unico(
        self,
        mock_aluno_get,
        mock_validar,
        mock_rollback,
        mock_savepoint,
        task_mock,
    ):
        mock_savepoint.return_value = 'sp_equiv'
        mock_validar.return_value = ({'aluno_id': 1}, [])
        mock_aluno_get.side_effect = RuntimeError('Falha de banco ao buscar aluno')

        csv_data = 'Aluno.id;componente_curricular_id\n1;50\n'
        func = getattr(importar_equivalencia_csv, '__wrapped__', importar_equivalencia_csv)

        with pytest.raises(RuntimeError, match='Falha de banco ao buscar aluno'):
            func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_rollback.assert_called_once_with('sp_equiv')
        task_mock.add_log.assert_called_once()
        assert 'Erro na linha' in task_mock.add_log.call_args[0][0]

    @patch('edu.migracao.transaction.savepoint')
    @patch('edu.migracao.transaction.savepoint_rollback')
    @patch('edu.migracao.validar_matricula')
    @patch('edu.migracao.Aluno.objects.get')
    def test_inicializar_periodo_letivo_erro_executa_rollback_unico(
        self,
        mock_aluno_get,
        mock_validar,
        mock_rollback,
        mock_savepoint,
        task_mock,
    ):
        mock_savepoint.return_value = 'sp_ini'
        mock_validar.return_value = ({'aluno_id': 1}, [])
        mock_aluno_get.side_effect = RuntimeError('Falha de banco ao buscar aluno')

        csv_data = 'Aluno.id\n1\n'
        func = getattr(inicializar_periodo_letivo, '__wrapped__', inicializar_periodo_letivo)

        with pytest.raises(RuntimeError, match='Falha de banco ao buscar aluno'):
            func(csv_data, apenas_validar=False, ignorar_obrigatorios=False, task=task_mock)

        mock_rollback.assert_called_once_with('sp_ini')
        task_mock.add_log.assert_called_once()
        assert 'Erro na linha' in task_mock.add_log.call_args[0][0]

    def test_console_progress_handler_update_progress(self):
        from edu.migracao import ConsoleProgressHandler

        handler = ConsoleProgressHandler()
        handler.set_total(10)
        assert handler.corrente == 0
        handler.update_progress(10)
        assert handler.corrente == 10

    def test_validar_naturalidade_com_ignorar_obrigatorios(self):
        from edu.validators import validar_naturalidade

        erros = []
        # Com ignorar_obrigatorios=False e valor vazio, gera erro
        res = validar_naturalidade('', 'Aluno.naturalidade', obrigatorio=True, erros=erros, ignorar_obrigatorios=False)
        assert res is None
        assert len(erros) == 1
        assert 'é obrigatório e não pode estar vazio' in erros[0]

        # Com ignorar_obrigatorios=True e valor vazio, NÃO gera erro
        erros_ignorado = []
        res = validar_naturalidade('', 'Aluno.naturalidade', obrigatorio=True, erros=erros_ignorado, ignorar_obrigatorios=True)
        assert res is None
        assert len(erros_ignorado) == 0

    @patch('edu.validators.validar_naturalidade')
    @patch('edu.validators.validar_modelo')
    @patch('edu.validators.validar_string')
    @patch('edu.validators.validar_data')
    @patch('edu.validators.validar_inteiro')
    @patch('edu.validators.validar_booleano')
    def test_validar_alunos_extrai_deficiencias_e_outras_nees(
        self,
        mock_bool,
        mock_int,
        mock_data,
        mock_str,
        mock_mod,
        mock_nat,
    ):
        from edu.validators import validar_alunos

        def _mock_validar_modelo(valor, modelo, nome_campo, **kwargs):
            erros_lista = kwargs.get('erros')
            val_str = str(valor).strip()
            if val_str == 'invalid':
                if erros_lista is not None:
                    erros_lista.append(f'O campo {nome_campo} requer um valor válido para id. "{valor}" foi informado.')
                return None
            try:
                return int(val_str)
            except ValueError:
                return 1

        mock_mod.side_effect = _mock_validar_modelo

        linha = {
            'Aluno.matricula': '20261001',
            'Aluno.deficiencias': ' 1, 2, invalid, 3 ',
            'Aluno.outras_nees': '4, 5',
        }
        registro, erros = validar_alunos(linha, ignorar_obrigatorios=True)
        assert len(erros) == 1
        assert 'Aluno.deficiencias' in erros[0]
        assert 'invalid' in erros[0]
        assert registro['deficiencias'] == [1, 2, 3]
        assert registro['outras_nees'] == [4, 5]

    def test_validar_lista_modelos_vazio_ou_nulo(self):
        from edu.models import Deficiencia
        from edu.validators import validar_lista_modelos

        erros = []
        assert validar_lista_modelos('', Deficiencia, 'Aluno.deficiencias', erros=erros) == []
        assert validar_lista_modelos(None, Deficiencia, 'Aluno.deficiencias', erros=erros) == []
        assert validar_lista_modelos('   ', Deficiencia, 'Aluno.deficiencias', erros=erros) == []
        assert len(erros) == 0

    @patch('edu.validators.validar_modelo')
    def test_validar_lista_modelos_ignora_espacos_e_virgulas_vazias(self, mock_validar_modelo):
        from edu.models import Deficiencia
        from edu.validators import validar_lista_modelos

        mock_validar_modelo.side_effect = lambda valor, *args, **kwargs: int(str(valor).strip())
        erros = []
        resultado = validar_lista_modelos(' 1, , 2, ', Deficiencia, 'Aluno.deficiencias', erros=erros)
        assert resultado == [1, 2]
        assert len(erros) == 0
        assert mock_validar_modelo.call_count == 2

    @patch('edu.validators.validar_modelo')
    def test_validar_lista_modelos_reporta_erros_de_tokens_invalidos(self, mock_validar_modelo):
        from edu.models import Deficiencia
        from edu.validators import validar_lista_modelos

        def _mock_validar(valor, modelo, nome_campo, **kwargs):
            erros_lista = kwargs.get('erros')
            val_str = str(valor).strip()
            if val_str == '99999':
                if erros_lista is not None:
                    erros_lista.append(f'O campo {nome_campo} com id "{valor}" não foi encontrado.')
                return None
            if val_str == 'abc':
                if erros_lista is not None:
                    erros_lista.append(f'O campo {nome_campo} requer um valor válido para id. "{valor}" foi informado.')
                return None
            return int(val_str)

        mock_validar_modelo.side_effect = _mock_validar
        erros = []
        resultado = validar_lista_modelos('1, 99999, abc, 2', Deficiencia, 'Aluno.deficiencias', erros=erros)
        assert resultado == [1, 2]
        assert len(erros) == 2
        assert 'com id "99999" não foi encontrado' in erros[0]
        assert 'requer um valor válido para id. "abc"' in erros[1]
