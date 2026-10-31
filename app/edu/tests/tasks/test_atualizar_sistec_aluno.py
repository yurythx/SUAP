from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from edu.forms.censos import AtualizarSistecAlunoForm
from edu.models import SituacaoMatricula
from edu.tasks import (
    _aplicar_codigo_sistec_mes,
    _atualizar_aluno_por_curso_ciclo,
    _atualizar_aluno_por_matricula,
    _atualizar_data_prevista_termino_aluno,
    _buscar_candidatos_atualizar_sistec,
    _carregar_codigos_sistec_cursos,
    _curso_tem_codigo_sistec,
    _extrair_identificadores_planilha,
    _parse_data_planilha_sistec,
    _precarregar_alunos_sistec,
    _processar_linha_atualizacao_sistec,
    _tentar_meses_vizinhos_ou_curso,
    atualizar_sistec_aluno,
)


class TestFormAtualizarSistecAluno:
    def test_campo_atualizar_data_fim_presente_no_form(self):
        form = AtualizarSistecAlunoForm()
        assert 'atualizar_data_fim' in form.fields
        assert form.fields['atualizar_data_fim'].required is False

    def test_campos_checkbox_labels_e_help_text(self):
        form = AtualizarSistecAlunoForm()
        assert form.fields['sobrescrever'].label == 'Sobrescrever código SISTEC'
        assert form.fields['sobrescrever'].help_text != ''
        assert form.fields['atualizar'].label == 'Sobrescrever data de início do ciclo'
        assert form.fields['atualizar'].help_text != ''
        assert form.fields['atualizar_data_fim'].label == 'Sobrescrever data prevista de término do ciclo'
        assert form.fields['atualizar_data_fim'].help_text != ''

    def test_cabecalho_com_matricula_valido(self):
        csv_content = b'MATRICULA;CO_MATRICULA\n2023101;123456\n'
        uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')
        form = AtualizarSistecAlunoForm(data={}, files={'planilha': uploaded})
        form.cleaned_data = {'planilha': uploaded}
        assert form.clean_planilha() == uploaded

    def test_cabecalho_com_cpf_valido(self):
        csv_content = b'CO_MATRICULA;CO_CURSO;DT_DATA_INICIO;NU_CPF\n123456;100;01/02/2026;123.456.789-01\n'
        uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')
        form = AtualizarSistecAlunoForm(data={}, files={'planilha': uploaded})
        form.cleaned_data = {'planilha': uploaded}
        assert form.clean_planilha() == uploaded

    def test_cabecalho_sem_cpf_com_nome_e_nascimento_valido(self):
        csv_content = b'CO_MATRICULA;CO_CURSO;DT_DATA_INICIO;NO_ALUNO;DT_DATA_NASCIMENTO\n123456;100;01/02/2026;Fulano;15/05/2000\n'
        uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')
        form = AtualizarSistecAlunoForm(data={}, files={'planilha': uploaded})
        form.cleaned_data = {'planilha': uploaded}
        assert form.clean_planilha() == uploaded

    def test_cabecalho_planilha_sistec_sem_cpf_completa_valido(self):
        colunas = [
            'CO_ALUNO',
            'NO_ALUNO',
            'NO_MAE_ALUNO',
            'SG_SEXO',
            'DT_DATA_NASCIMENTO',
            'DS_EMAIL',
            'CO_PESSOA_FISICA_ALUNO',
            'DS_SENHA',
            'CO_MATRICULA',
            'CO_CICLO_MATRICULA',
            'CO_CURSO',
            'NU_CARGA_HORARIA',
            'DT_DATA_INICIO',
            'DT_FIM_PREVISTO',
            'CO_PERIODO_CADASTRO',
            'NO_CICLO_MATRICULA',
            'CO_TIPO_OFERTA_CURSO',
            'CO_TIPO_INSTITUICAO',
            'CO_PORTFOLIO',
            'NU_VAGAS_OFERTADAS',
            'NU_TOTAL_INSCRITOS',
            'NO_STATUS_MATRICULA',
            'CO_UNIDADE_ENSINO',
            'MES_DE_OCORRENCIA',
        ]
        csv_content = f'{";".join(colunas)}\n'.encode('iso-8859-1')
        uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')
        form = AtualizarSistecAlunoForm(data={}, files={'planilha': uploaded})
        form.cleaned_data = {'planilha': uploaded}
        assert form.clean_planilha() == uploaded

    def test_cabecalho_invalido_dispara_validation_error(self):
        csv_content = b'CO_ALUNO;NO_ALUNO\n1;Fulano\n'
        uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')
        form = AtualizarSistecAlunoForm(data={}, files={'planilha': uploaded})
        form.cleaned_data = {'planilha': uploaded}
        with pytest.raises(ValidationError):
            form.clean_planilha()


class TestParseDataPlanilhaSistec:
    def test_parse_data_barra(self):
        assert _parse_data_planilha_sistec('28/08/2023 00:00') == datetime.date(2023, 8, 28)
        assert _parse_data_planilha_sistec('28/08/2023') == datetime.date(2023, 8, 28)

    def test_parse_data_hifen(self):
        assert _parse_data_planilha_sistec('2023-08-28 00:00') == datetime.date(2023, 8, 28)
        assert _parse_data_planilha_sistec('2023-08-28') == datetime.date(2023, 8, 28)

    def test_parse_data_invalida(self):
        assert _parse_data_planilha_sistec('') is None
        assert _parse_data_planilha_sistec(None) is None
        assert _parse_data_planilha_sistec('data-invalida') is None


class TestCursoHelpers:
    def test_curso_tem_codigo_sistec(self):
        assert _curso_tem_codigo_sistec('100;200;300', 200) is True
        assert _curso_tem_codigo_sistec('100', 100) is True
        assert _curso_tem_codigo_sistec('100;200', 300) is False
        assert _curso_tem_codigo_sistec(None, 100) is False
        assert _curso_tem_codigo_sistec('', 100) is False

    @patch('edu.tasks.CursoCampus.objects')
    def test_carregar_codigos_sistec_cursos(self, mock_objects):
        mock_objects.exclude.return_value.exclude.return_value.values_list.return_value = [
            '100;200',
            '300',
            'invalid',
        ]
        codigos = _carregar_codigos_sistec_cursos()
        assert codigos == {100, 200, 300}


class TestPrecarregamentoAlunos:
    def test_extrair_identificadores_planilha(self):
        rows = [
            {'MATRICULA': '2023101', 'CO_MATRICULA': '1'},
            {'NU_CPF': '123.456.789-01', 'CO_MATRICULA': '2'},
            {'NO_ALUNO': 'Jeremias', 'DT_DATA_NASCIMENTO': '18/12/2001', 'CO_MATRICULA': '3'},
        ]
        mats, cpfs, datas_nasc, pares = _extrair_identificadores_planilha(rows)
        assert '2023101' in mats
        assert '123.456.789-01' in cpfs
        assert datetime.date(2001, 12, 18) in datas_nasc
        assert ('jeremias', datetime.date(2001, 12, 18)) in pares

    @patch('edu.tasks.Aluno.objects.filter')
    def test_precarregar_alunos_sistec(self, mock_filter):
        aluno_mat = MagicMock(matricula='2023101')
        aluno_cpf = MagicMock(pessoa_fisica=MagicMock(cpf='123.456.789-01', nome='Fulano'))
        aluno_nome = MagicMock(pessoa_fisica=MagicMock(cpf=None, nome='Jeremias', nascimento_data=datetime.date(2001, 12, 18)))

        mock_qs_mat = MagicMock()
        mock_qs_mat.__iter__.return_value = [aluno_mat]
        mock_qs_cpf = MagicMock()
        mock_qs_cpf.__iter__.return_value = [aluno_cpf]
        mock_qs_nome = MagicMock()
        mock_qs_nome.__iter__.return_value = [aluno_nome]

        mock_filter.side_effect = [
            MagicMock(select_related=MagicMock(return_value=mock_qs_mat)),
            MagicMock(select_related=MagicMock(return_value=mock_qs_cpf)),
            MagicMock(select_related=MagicMock(return_value=mock_qs_nome)),
        ]

        rows = [
            {'MATRICULA': '2023101'},
            {'NU_CPF': '123.456.789-01'},
            {'NO_ALUNO': 'Jeremias', 'DT_DATA_NASCIMENTO': '18/12/2001'},
        ]
        p_mat, p_cpf, p_nome = _precarregar_alunos_sistec(rows)

        assert p_mat['2023101'] == aluno_mat
        assert aluno_cpf in p_cpf['123.456.789-01']
        assert aluno_nome in p_nome[('jeremias', datetime.date(2001, 12, 18))]


class TestAtualizarDataPrevistaTerminoAluno:
    def test_atualizar_com_data_fim_informada(self):
        aluno = MagicMock(id=1, data_prevista_termino_ciclo=datetime.date(2025, 1, 1))
        modificados = {}
        data_fim = datetime.date(2027, 8, 31)
        _atualizar_data_prevista_termino_aluno(aluno, data_fim, True, modificados)
        assert aluno.data_prevista_termino_ciclo == data_fim
        assert modificados[1] == aluno

    def test_atualizar_sem_data_fim_calcula(self):
        aluno = MagicMock(id=1, data_prevista_termino_ciclo=datetime.date(2025, 1, 1))
        aluno.calcular_data_prevista_termino_ciclo.return_value = datetime.date(2026, 12, 31)
        modificados = {}
        _atualizar_data_prevista_termino_aluno(aluno, None, True, modificados)
        assert aluno.data_prevista_termino_ciclo == datetime.date(2026, 12, 31)
        assert modificados[1] == aluno

    def test_nao_atualizar_se_ja_definida_e_flag_false(self):
        data_existente = datetime.date(2025, 1, 1)
        aluno = MagicMock(id=1, data_prevista_termino_ciclo=data_existente)
        modificados = {}
        _atualizar_data_prevista_termino_aluno(aluno, datetime.date(2027, 8, 31), False, modificados)
        assert aluno.data_prevista_termino_ciclo == data_existente
        assert modificados == {}

    def test_preenche_se_nula_quando_flag_false(self):
        aluno = MagicMock(id=1, data_prevista_termino_ciclo=None)
        data_fim = datetime.date(2027, 8, 31)
        modificados = {}
        _atualizar_data_prevista_termino_aluno(aluno, data_fim, False, modificados)
        assert aluno.data_prevista_termino_ciclo == data_fim
        assert modificados[1] == aluno


class TestAtualizarAlunoPorMatricula:
    def test_aluno_nao_encontrado(self):
        data = {}
        _atualizar_aluno_por_matricula('2023101', 999, datetime.date(2023, 8, 28), False, False, data, {}, {})
        assert data['RESULTADO'] == 'ALUNO NÃO ENCONTRADO'
        assert data['MATRICULA'] == '2023101'
        assert data['DT_FIM_SUAP'] == ''

    def test_aluno_sem_codigo_previo_informa_codigo(self):
        aluno = MagicMock(id=1, codigo_sistec=None, data_inicio_ciclo=datetime.date(2023, 8, 28), data_prevista_termino_ciclo=None)
        data = {}
        modificados = {}
        _atualizar_aluno_por_matricula('2023101', 999, datetime.date(2023, 8, 28), False, False, data, {'2023101': aluno}, modificados)
        assert data['RESULTADO'] == 'INFORMADO'
        assert aluno.codigo_sistec == '999'
        assert modificados[1] == aluno

    def test_aluno_com_codigo_previo_sem_sobrescrever(self):
        aluno = MagicMock(
            id=1,
            codigo_sistec='888',
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            data_prevista_termino_ciclo=datetime.date(2027, 8, 31),
        )
        data = {}
        modificados = {}
        _atualizar_aluno_por_matricula('2023101', 999, datetime.date(2023, 8, 28), False, False, data, {'2023101': aluno}, modificados)
        assert data['RESULTADO'] == 'LOCALIZADO'
        assert aluno.codigo_sistec == '888'
        assert modificados == {}

    def test_aluno_com_codigo_previo_com_sobrescrever(self):
        aluno = MagicMock(
            id=1,
            codigo_sistec='888',
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            data_prevista_termino_ciclo=datetime.date(2027, 8, 31),
        )
        data = {}
        modificados = {}
        _atualizar_aluno_por_matricula('2023101', 999, datetime.date(2023, 8, 28), False, True, data, {'2023101': aluno}, modificados)
        assert data['RESULTADO'] == 'ATUALIZADO'
        assert aluno.codigo_sistec == '999'
        assert modificados[1] == aluno

    def test_aluno_atualizar_data_fim_true_com_data_planilha(self):
        aluno = MagicMock(
            id=1,
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            data_prevista_termino_ciclo=datetime.date(2025, 1, 1),
        )
        data = {}
        modificados = {}
        data_fim = datetime.date(2027, 8, 31)
        _atualizar_aluno_por_matricula(
            '2023101',
            999,
            datetime.date(2023, 8, 28),
            False,
            False,
            data,
            {'2023101': aluno},
            modificados,
            data_fim=data_fim,
            atualizar_data_fim=True,
        )
        assert aluno.data_prevista_termino_ciclo == data_fim
        assert data['DT_FIM_SUAP'] == '31/08/2027 00:00'
        assert modificados[1] == aluno


class TestBuscarCandidatosAtualizarSistec:
    def test_busca_por_cpf_sucesso(self):
        aluno = MagicMock()
        alunos_por_cpf = {'123.456.789-01': [aluno]}
        data = {'NU_CPF': '123.456.789-01'}
        candidatos, erro = _buscar_candidatos_atualizar_sistec(data, alunos_por_cpf, {})
        assert candidatos == [aluno]
        assert erro == ''

    def test_busca_por_cpf_nao_encontrado(self):
        data = {'NU_CPF': '123.456.789-01'}
        candidatos, erro = _buscar_candidatos_atualizar_sistec(data, {}, {})
        assert candidatos is None
        assert erro == 'ALUNO COM CPF NÃO ENCONTRADO'

    def test_busca_sem_cpf_por_nome_e_nascimento_sucesso(self):
        aluno = MagicMock()
        chave = ('jeremias cleyton', datetime.date(2001, 12, 18))
        alunos_por_nome_nasc = {chave: [aluno]}
        data = {
            'NU_CPF': '',
            'NO_ALUNO': 'Jeremias Cleyton',
            'DT_DATA_NASCIMENTO': '18/12/2001',
        }
        candidatos, erro = _buscar_candidatos_atualizar_sistec(data, {}, alunos_por_nome_nasc)
        assert candidatos == [aluno]
        assert erro == ''

    def test_busca_sem_cpf_por_nome_e_nascimento_nao_encontrado(self):
        data = {
            'NO_ALUNO': 'Jeremias Cleyton',
            'DT_DATA_NASCIMENTO': '18/12/2001',
        }
        candidatos, erro = _buscar_candidatos_atualizar_sistec(data, {}, {})
        assert candidatos is None
        assert erro == 'ALUNO SEM CPF NÃO ENCONTRADO'

    def test_busca_sem_cpf_e_sem_nome_nascimento_retorna_dados_insuficientes(self):
        data = {'NU_CPF': ''}
        candidatos, erro = _buscar_candidatos_atualizar_sistec(data, {}, {})
        assert candidatos is None
        assert erro == 'DADOS INSUFICIENTES'


class TestProcessarLinhaAtualizacaoSistec:
    def test_co_matricula_invalido(self):
        data = {'CO_MATRICULA': 'abc'}
        _processar_linha_atualizacao_sistec(data, False, False, set(), {}, {}, {}, {})
        assert data['RESULTADO'] == 'CO_MATRICULA INVÁLIDO'

    def test_data_inicio_invalida(self):
        data = {'CO_MATRICULA': '123456', 'DT_DATA_INICIO': 'invalida'}
        _processar_linha_atualizacao_sistec(data, False, False, set(), {}, {}, {}, {})
        assert data['RESULTADO'] == 'DATA INÍCIO INVÁLIDA'

    def test_curso_nao_localizado(self):
        data = {
            'CO_MATRICULA': '123456',
            'CO_CURSO': '380090',
            'DT_DATA_INICIO': '28/08/2023',
        }
        _processar_linha_atualizacao_sistec(data, False, False, set(), {}, {}, {}, {})
        assert data['RESULTADO'] == 'CURSO NÃO LOCALIZADO NO SUAP'

    def test_aluno_sem_cpf_processado_com_sucesso(self):
        codigos_cursos = {380090}
        aluno = MagicMock(
            id=10,
            matricula='20232010590001',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            curso_campus=MagicMock(codigo_sistec='380090'),
        )
        chave = ('jeremias cleyton da costa batista', datetime.date(2001, 12, 18))
        alunos_por_nome_nasc = {chave: [aluno]}
        modificados = {}

        data = {
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '380090',
            'DT_DATA_INICIO': '28/08/2023',
            'NO_ALUNO': 'JEREMIAS CLEYTON DA COSTA BATISTA',
            'DT_DATA_NASCIMENTO': '18/12/2001',
        }

        _processar_linha_atualizacao_sistec(
            data,
            False,
            False,
            codigos_cursos,
            {},
            {},
            alunos_por_nome_nasc,
            modificados,
        )

        assert data['RESULTADO'] == 'INFORMADO'
        assert data['MATRICULA'] == '20232010590001'
        assert aluno.codigo_sistec == '104651977'
        assert modificados[10] == aluno

    def test_processar_linha_com_dt_data_fim_previsto(self):
        codigos_cursos = {380090}
        aluno = MagicMock(
            id=10,
            matricula='20232010590001',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            data_prevista_termino_ciclo=datetime.date(2025, 1, 1),
            curso_campus=MagicMock(codigo_sistec='380090'),
        )
        chave = ('jeremias cleyton da costa batista', datetime.date(2001, 12, 18))
        alunos_por_nome_nasc = {chave: [aluno]}
        modificados = {}

        data = {
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '380090',
            'DT_DATA_INICIO': '28/08/2023',
            'DT_DATA_FIM_PREVISTO': '31/08/2027',
            'NO_ALUNO': 'JEREMIAS CLEYTON DA COSTA BATISTA',
            'DT_DATA_NASCIMENTO': '18/12/2001',
        }

        _processar_linha_atualizacao_sistec(
            data,
            False,
            False,
            codigos_cursos,
            {},
            {},
            alunos_por_nome_nasc,
            modificados,
            atualizar_data_fim=True,
        )

        assert data['RESULTADO'] == 'INFORMADO'
        assert aluno.data_prevista_termino_ciclo == datetime.date(2027, 8, 31)
        assert data['DT_FIM_SUAP'] == '31/08/2027 00:00'
        assert modificados[10] == aluno

    def test_multiplas_matriculas_mesmo_curso_cpf_diferentes_anos(self):
        codigos_cursos = {52953}
        cpf_formatado = '110.398.784-40'
        aluno_2023 = MagicMock(
            id=1,
            matricula='20231163000026',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=datetime.date(2027, 12, 31)),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.TRANSFERIDO_EXTERNO,
        )
        aluno_2026 = MagicMock(
            id=2,
            matricula='20261163000021',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2026, 3, 12),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=datetime.date(2030, 12, 31)),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2026),
            situacao_id=SituacaoMatricula.MATRICULADO,
        )
        alunos_por_cpf = {cpf_formatado: [aluno_2023, aluno_2026]}
        modificados = {}
        alunos_atribuidos = set()

        linha_2023 = {
            'CO_MATRICULA': '110996661',
            'CO_CURSO': '52953',
            'DT_DATA_INICIO': '2023-03-01 00:00:00',
            'DT_DATA_FIM_PREVISTO': '2027-12-31 00:00:00',
            'NU_CPF': cpf_formatado,
            'NO_STATUS_MATRICULA': 'TRANSF_EXT',
        }
        _processar_linha_atualizacao_sistec(
            linha_2023,
            False,
            False,
            codigos_cursos,
            {},
            alunos_por_cpf,
            {},
            modificados,
            atualizar_data_fim=True,
            alunos_atribuidos=alunos_atribuidos,
        )
        assert linha_2023['MATRICULA'] == '20231163000026'
        assert linha_2023['RESULTADO'] == 'INFORMADO'
        assert aluno_2023.codigo_sistec == '110996661'
        assert 1 in alunos_atribuidos

        linha_2026 = {
            'CO_MATRICULA': '134787387',
            'CO_CURSO': '52953',
            'DT_DATA_INICIO': '2026-03-12 00:00:00',
            'DT_DATA_FIM_PREVISTO': '2030-12-31 00:00:00',
            'NU_CPF': cpf_formatado,
            'NO_STATUS_MATRICULA': 'EM_CURSO',
        }
        _processar_linha_atualizacao_sistec(
            linha_2026,
            False,
            False,
            codigos_cursos,
            {},
            alunos_por_cpf,
            {},
            modificados,
            atualizar_data_fim=True,
            alunos_atribuidos=alunos_atribuidos,
        )
        assert linha_2026['MATRICULA'] == '20261163000021'
        assert linha_2026['RESULTADO'] == 'INFORMADO'
        assert aluno_2026.codigo_sistec == '134787387'
        assert 2 in alunos_atribuidos

    def test_multiplas_matriculas_mesmo_curso_desempate_por_proximidade_temporal(self):
        codigos_cursos = {52953}
        cpf_formatado = '110.398.784-40'
        aluno_antigo = MagicMock(
            id=1,
            matricula='2020101',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2020, 2, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=None,
            situacao_id=None,
        )
        aluno_recente = MagicMock(
            id=2,
            matricula='2023101',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 2, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=None,
            situacao_id=None,
        )
        alunos_por_cpf = {cpf_formatado: [aluno_antigo, aluno_recente]}
        modificados = {}

        linha = {
            'CO_MATRICULA': '123456',
            'CO_CURSO': '52953',
            'DT_DATA_INICIO': '2023-03-01',
            'NU_CPF': cpf_formatado,
        }
        _processar_linha_atualizacao_sistec(
            linha,
            False,
            False,
            codigos_cursos,
            {},
            alunos_por_cpf,
            {},
            modificados,
        )
        assert linha['MATRICULA'] == '2023101'
        assert aluno_recente.codigo_sistec == '123456'
        assert aluno_antigo.codigo_sistec is None

    def test_multiplas_matriculas_mesmo_curso_desempate_por_status(self):
        codigos_cursos = {52953}
        cpf_formatado = '110.398.784-40'
        aluno_transf = MagicMock(
            id=1,
            matricula='2023101',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.TRANSFERIDO_EXTERNO,
        )
        aluno_ativo = MagicMock(
            id=2,
            matricula='2023102',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.MATRICULADO,
        )
        alunos_por_cpf = {cpf_formatado: [aluno_transf, aluno_ativo]}
        modificados = {}

        linha = {
            'CO_MATRICULA': '789012',
            'CO_CURSO': '52953',
            'DT_DATA_INICIO': '2023-03-01',
            'NU_CPF': cpf_formatado,
            'NO_STATUS_MATRICULA': 'TRANSF_EXT',
        }
        _processar_linha_atualizacao_sistec(
            linha,
            False,
            False,
            codigos_cursos,
            {},
            alunos_por_cpf,
            {},
            modificados,
        )
        assert linha['MATRICULA'] == '2023101'
        assert aluno_transf.codigo_sistec == '789012'
        assert aluno_ativo.codigo_sistec is None

    def test_multiplas_matriculas_mesmo_curso_empate_perfeito_gera_ambiguidade(self):
        codigos_cursos = {52953}
        cpf_formatado = '110.398.784-40'
        aluno_1 = MagicMock(
            id=1,
            matricula='2023101',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.MATRICULADO,
        )
        aluno_2 = MagicMock(
            id=2,
            matricula='2023102',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=None),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.MATRICULADO,
        )
        alunos_por_cpf = {cpf_formatado: [aluno_1, aluno_2]}
        modificados = {}

        linha = {
            'CO_MATRICULA': '789012',
            'CO_CURSO': '52953',
            'DT_DATA_INICIO': '2023-03-01',
            'NU_CPF': cpf_formatado,
            'NO_STATUS_MATRICULA': 'EM_CURSO',
        }
        _processar_linha_atualizacao_sistec(
            linha,
            False,
            False,
            codigos_cursos,
            {},
            alunos_por_cpf,
            {},
            modificados,
        )
        assert linha['RESULTADO'] == 'AMBIGUIDADE: MÚLTIPLAS MATRÍCULAS NO MESMO CURSO'
        assert linha['MATRICULA'] == ''
        assert aluno_1.codigo_sistec is None
        assert aluno_2.codigo_sistec is None
        assert len(modificados) == 0


@pytest.mark.usefixtures('patch_task_model')
class TestAtualizarSistecAlunoTask:
    @patch('edu.tasks.transaction.atomic')
    @patch('edu.tasks.Aluno.objects.bulk_update')
    @patch('edu.tasks._precarregar_alunos_sistec')
    @patch('edu.tasks._carregar_codigos_sistec_cursos')
    @patch('edu.tasks.get_temp_storage')
    @patch('edu.tasks.open')
    def test_atualizar_sistec_aluno_completo(self, mock_open, mock_storage, mock_cursos, mock_precarregar, mock_bulk, mock_atomic, task_mock):
        csv_data = (
            'CO_ALUNO;NO_ALUNO;NO_MAE_ALUNO;SG_SEXO;DT_DATA_NASCIMENTO;DS_EMAIL;CO_PESSOA_FISICA_ALUNO;DS_SENHA;'
            'CO_MATRICULA;CO_CICLO_MATRICULA;CO_CURSO;NU_CARGA_HORARIA;DT_DATA_INICIO;DT_DATA_FIM_PREVISTO;'
            'CO_PERIODO_CADASTRO;NO_CICLO_MATRICULA;CO_TIPO_OFERTA_CURSO;CO_TIPO_INSTITUICAO;CO_PORTFOLIO;'
            'NU_VAGAS_OFERTADAS;NU_TOTAL_INSCRITOS;NO_STATUS_MATRICULA;CO_UNIDADE_ENSINO;MES_DE_OCORRENCIA\n'
            '23406208;JEREMIAS CLEYTON DA COSTA BATISTA;ELIANE;M;18/12/2001 00:00;;24784852;;104651977;3030722;'
            '380090;4009;28/08/2023 00:00;31/08/2027 00:00;39475;PORTUGUES/ESPANHOL;;2;591602;7;;EM_CURSO;2959;ago/23\n'
        )

        mock_storage_inst = MagicMock()
        mock_storage_inst.exists.return_value = True
        mock_storage_inst.open.return_value.read.return_value = csv_data.encode('iso-8859-1')
        mock_storage.return_value = mock_storage_inst

        mock_file = MagicMock()
        mock_open.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=mock_file)),
            csv_data.splitlines(),
            MagicMock(__enter__=MagicMock(return_value=mock_file)),
        ]

        mock_cursos.return_value = {380090}
        aluno = MagicMock(
            id=10,
            matricula='20232010590001',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 8, 28),
            curso_campus=MagicMock(codigo_sistec='380090'),
        )
        chave = ('jeremias cleyton da costa batista', datetime.date(2001, 12, 18))
        mock_precarregar.return_value = ({}, {}, {chave: [aluno]})

        func = getattr(atualizar_sistec_aluno, '__wrapped__', atualizar_sistec_aluno)
        func('planilha_teste.csv', False, False, atualizar_data_fim=True, task=task_mock)

        mock_bulk.assert_called_once()
        args, _ = mock_bulk.call_args
        assert args[1] == ['codigo_sistec', 'data_inicio_ciclo', 'data_prevista_termino_ciclo']
        task_mock.finalize.assert_called_once()

    @patch('edu.tasks.transaction.atomic')
    @patch('edu.tasks.Aluno.objects.bulk_update')
    @patch('edu.tasks._precarregar_alunos_sistec')
    @patch('edu.tasks._carregar_codigos_sistec_cursos')
    @patch('edu.tasks.get_temp_storage')
    @patch('edu.tasks.open')
    def test_atualizar_sistec_aluno_caso_mesmo_cpf_multiplas_matriculas(
        self, mock_open, mock_storage, mock_cursos, mock_precarregar, mock_bulk, mock_atomic, task_mock
    ):
        csv_data = (
            'CO_ALUNO;NO_ALUNO;NO_MAE_ALUNO;SG_SEXO;DT_DATA_NASCIMENTO;NU_CPF;DS_EMAIL;CO_PESSOA_FISICA_ALUNO;DS_SENHA;'
            'CO_MATRICULA;CO_CICLO_MATRICULA;CO_CURSO;NU_CARGA_HORARIA;DT_DATA_INICIO;DT_DATA_FIM_PREVISTO;'
            'CO_PERIODO_CADASTRO;NO_CICLO_MATRICULA;CO_TIPO_OFERTA_CURSO;CO_TIPO_INSTITUICAO;CO_PORTFOLIO;'
            'NU_VAGAS_OFERTADAS;NU_TOTAL_INSCRITOS;NO_STATUS_MATRICULA;CO_UNIDADE_ENSINO;MES_DE_OCORRENCIA\n'
            '26308081;SANDRO HENRIQUE;ANA MARIA;M;2003-07-10 00:00:00;110.398.784-40;;22037677;;110996661;2979190;'
            '52953;3815;2023-03-01 00:00:00;2027-12-31 00:00:00;39470;ENG PRODUCAO;;2;575767;40;432;TRANSF_EXT;20419;MAR 2025\n'
            '26308081;SANDRO HENRIQUE;ANA MARIA;M;2003-07-10 00:00:00;110.398.784-40;;22037677;;134787387;3350987;'
            '52953;3745;2026-03-12 00:00:00;2030-12-31 00:00:00;39506;ENG PRODUCAO;;2;575767;40;1045;EM_CURSO;20419;MAR 2026\n'
        )

        mock_storage_inst = MagicMock()
        mock_storage_inst.exists.return_value = True
        mock_storage_inst.open.return_value.read.return_value = csv_data.encode('iso-8859-1')
        mock_storage.return_value = mock_storage_inst

        mock_file = MagicMock()
        mock_open.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=mock_file)),
            csv_data.splitlines(),
            MagicMock(__enter__=MagicMock(return_value=mock_file)),
        ]

        mock_cursos.return_value = {52953}
        aluno_2023 = MagicMock(
            id=1,
            matricula='20231163000026',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2023, 3, 1),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=datetime.date(2027, 12, 31)),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2023),
            situacao_id=SituacaoMatricula.TRANSFERIDO_EXTERNO,
        )
        aluno_2026 = MagicMock(
            id=2,
            matricula='20261163000021',
            codigo_sistec=None,
            data_inicio_ciclo=datetime.date(2026, 3, 12),
            data_prevista_termino_ciclo=None,
            calcular_data_prevista_termino_ciclo=MagicMock(return_value=datetime.date(2030, 12, 31)),
            curso_campus=MagicMock(codigo_sistec='52953'),
            ano_letivo=MagicMock(ano=2026),
            situacao_id=SituacaoMatricula.MATRICULADO,
        )
        mock_precarregar.return_value = ({}, {'110.398.784-40': [aluno_2023, aluno_2026]}, {})

        func = getattr(atualizar_sistec_aluno, '__wrapped__', atualizar_sistec_aluno)
        func('planilha_teste.csv', False, False, atualizar_data_fim=True, task=task_mock)

        mock_bulk.assert_called_once()
        args, _ = mock_bulk.call_args
        atualizados = args[0]
        assert aluno_2023 in atualizados
        assert aluno_2026 in atualizados
        assert aluno_2023.codigo_sistec == '110996661'
        assert aluno_2026.codigo_sistec == '134787387'
        task_mock.finalize.assert_called_once()
