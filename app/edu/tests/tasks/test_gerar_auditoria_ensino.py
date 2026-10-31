from __future__ import annotations

import datetime
import io
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest
from dateutil.relativedelta import relativedelta

from edu.auditoria_ensino import (
    ANO_CORTE_PRONATEC_SISTEC,
    RE_NOME_INVALIDO,
    AuditoriaEnsinoService,
    _aluno_esta_retido,
    _carregar_alunos_por_codigo_sistec,
    _comparar_dados_rf,
    _curso_tem_codigo_sistec,
    _desconsiderar_minicursos_menor_20h,
    _determinar_valor_comparacao,
    _finalizar_auditoria,
    _gerar_aluno_sem_sistec,
    _gerar_alunos_retidos,
    _gerar_cidade_alunos,
    _gerar_matricula_modalidade,
    _gerar_nome_aluno,
    _gerar_nome_pais,
    _gerar_sistec,
    _iterar_linhas_planilha_sistec,
    _localizar_aluno_sistec,
    _obter_codigos_sistec_minicursos_menor_20h,
    _obter_codigos_sistec_nivel,
    _obter_qs_alunos_rf,
    _obter_qs_alunos_sistec,
    _obter_qs_alunos_situacao_matricula,
    _parse_cpf,
    _parse_data_inicio,
    _processar_alunos_ausentes_sistec,
    _processar_linha_sistec,
    _selecionar_candidato_aluno,
    iterate_task,
)
from edu.models import Aluno, AuditoriaEnsino, CursoCampus, Diretoria, Modalidade, SituacaoMatricula
from edu.tasks import gerar_auditoria_ensino
from rh.models import PessoaFisica, UnidadeOrganizacional


class TestParseHelpers:
    def test_parse_cpf(self):
        assert _parse_cpf('123.456.789-01') == '123.456.789-01'
        assert _parse_cpf('12345678901') == '123.456.789-01'
        assert _parse_cpf('123') == '000.000.001-23'
        assert _parse_cpf('') == ''
        assert _parse_cpf(None) == ''

    def test_parse_data_inicio(self):
        assert _parse_data_inicio('15/02/2026') == datetime.date(2026, 2, 15)
        assert _parse_data_inicio('15/02/2026 08:30:00') == datetime.date(2026, 2, 15)
        assert _parse_data_inicio('2026-02-15') == datetime.date(2026, 2, 15)
        assert _parse_data_inicio('2026-02-15 10:00:00') == datetime.date(2026, 2, 15)

    def test_curso_tem_codigo_sistec(self):
        assert _curso_tem_codigo_sistec('100', 100) is True
        assert _curso_tem_codigo_sistec('100;200;300', 200) is True
        assert _curso_tem_codigo_sistec('100;200;300', 100) is True
        assert _curso_tem_codigo_sistec('100;200;300', 300) is True
        assert _curso_tem_codigo_sistec('100;200;300', 400) is False
        assert _curso_tem_codigo_sistec(None, 100) is False
        assert _curso_tem_codigo_sistec('', 100) is False

    def test_iterate_task(self):
        items = [1, 2, 3]
        assert list(iterate_task(None, items)) == [1, 2, 3]

        task = MagicMock()
        task.iterate.side_effect = lambda it: (x * 2 for x in it)
        assert list(iterate_task(task, items)) == [2, 4, 6]


class TestComparacaoSistec:
    def test_determinar_valor_comparacao_status_padrao(self):
        aluno = MagicMock()
        aluno.situacao_id = SituacaoMatricula.CONCLUIDO
        assert _determinar_valor_comparacao(aluno) == ['CONCLUÍDA']

        aluno.situacao_id = SituacaoMatricula.CANCELADO
        assert _determinar_valor_comparacao(aluno) == ['ABANDONO', 'DESLIGADO']

        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        assert _determinar_valor_comparacao(aluno) == ['EM_CURSO']

        aluno.situacao_id = SituacaoMatricula.CONCLUDENTE
        assert _determinar_valor_comparacao(aluno) == ['INTEGRALIZADA']

        aluno.situacao_id = SituacaoMatricula.TRANSFERIDO_EXTERNO
        assert _determinar_valor_comparacao(aluno) == ['TRANSF_EXT']

    def test_selecionar_candidato_unico(self):
        aluno = MagicMock()
        assert _selecionar_candidato_aluno([aluno], datetime.date(2026, 1, 1)) == aluno

    def test_selecionar_candidato_por_ciclo(self):
        a1 = MagicMock(data_inicio_ciclo=datetime.date(2026, 1, 10))
        a2 = MagicMock(data_inicio_ciclo=datetime.date(2025, 1, 10))
        res = _selecionar_candidato_aluno([a1, a2], datetime.date(2026, 1, 1))
        assert res == a1

    def test_selecionar_candidato_por_ano_letivo(self):
        a1 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2026))
        a2 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2025))
        res = _selecionar_candidato_aluno([a1, a2], datetime.date(2026, 6, 1))
        assert res == a1

    def test_selecionar_candidato_nao_encontrado(self):
        a1 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2024))
        a2 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2025))
        with pytest.raises(Aluno.DoesNotExist):
            _selecionar_candidato_aluno([a1, a2], datetime.date(2026, 1, 1))

    def test_selecionar_candidato_duplicado(self):
        a1 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2026))
        a2 = MagicMock(data_inicio_ciclo=None, ano_letivo=MagicMock(ano=2026))
        with pytest.raises(Aluno.MultipleObjectsReturned):
            _selecionar_candidato_aluno([a1, a2], datetime.date(2026, 1, 1))


class TestProcessamentoLinhaSistec:
    def _criar_auditoria(self):
        auditoria = AuditoriaEnsino()
        auditoria.id = 1
        auditoria.data_inicio_auditoria = datetime.date(2026, 1, 1)
        auditoria.data_fim_auditoria = datetime.date(2026, 12, 31)
        return auditoria

    def test_linha_fora_do_intervalo_retorna_none(self):
        auditoria = self._criar_auditoria()
        data = {
            'NU_CPF': '12345678901',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2025.1',
            'NO_ALUNO': 'Fulano',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '01/01/2025',
        }
        res = _processar_linha_sistec(data, auditoria, {}, MagicMock(), [], [])
        assert res is None

    def test_aluno_convergente(self):
        auditoria = self._criar_auditoria()
        data = {
            'NU_CPF': '12345678901',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2026.1',
            'NO_ALUNO': 'Fulano de Tal',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '15/02/2026',
        }

        aluno = MagicMock()
        aluno.id = 1
        aluno.matricula = '2026001'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Técnico em Informática'
        aluno.codigo_sistec = None

        alunos_por_cpf = {'123.456.789-01': [aluno]}
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg = _processar_linha_sistec(data, auditoria, alunos_por_cpf, MagicMock(), alunos_atualizar, ids_nao_ausentes)

        assert reg is not None
        assert reg.divergente is False
        assert 'CONVERGENTE' in reg.registro
        assert '2026001' in reg.registro
        assert aluno.codigo_sistec == '999'
        assert aluno in alunos_atualizar
        assert 1 in ids_nao_ausentes

    def test_aluno_divergente(self):
        auditoria = self._criar_auditoria()
        data = {
            'NU_CPF': '12345678901',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'CONCLUÍDA',
            'NO_CICLO_MATRICULA': '2026.1',
            'NO_ALUNO': 'Fulano de Tal',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '15/02/2026',
        }

        aluno = MagicMock()
        aluno.id = 2
        aluno.matricula = '2026002'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Técnico em Informática'
        aluno.codigo_sistec = '999'

        alunos_por_cpf = {'123.456.789-01': [aluno]}
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg = _processar_linha_sistec(data, auditoria, alunos_por_cpf, MagicMock(), alunos_atualizar, ids_nao_ausentes)

        assert reg is not None
        assert reg.divergente is True
        assert 'DIVERGENTE' in reg.registro

    def test_aluno_nao_encontrado(self):
        auditoria = self._criar_auditoria()
        data = {
            'NU_CPF': '99999999999',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2026.1',
            'NO_ALUNO': 'Não Existe',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '15/02/2026',
        }
        reg = _processar_linha_sistec(data, auditoria, {}, MagicMock(), [], [])
        assert reg is not None
        assert reg.divergente is True
        assert 'NÃO ENCONTRADO' in reg.registro


class TestComparacaoReceitaFederal:
    def test_dados_convergentes(self):
        aluno = MagicMock()
        aluno.pessoa_fisica.nome_registro = 'João da Silva'
        aluno.pessoa_fisica.nascimento_data = datetime.date(2000, 5, 20)
        aluno.nome_mae = 'Maria da Silva'

        dados_rf = {'Nome': 'JOAO DA SILVA', 'DataNascimento': '20000520', 'NomeMae': 'MARIA DA SILVA'}

        divergente, *_ = _comparar_dados_rf(aluno, dados_rf)
        assert divergente is False

    def test_dados_divergentes_nome(self):
        aluno = MagicMock()
        aluno.pessoa_fisica.nome_registro = 'João da Silva'
        aluno.pessoa_fisica.nascimento_data = datetime.date(2000, 5, 20)
        aluno.nome_mae = 'Maria da Silva'

        dados_rf = {'Nome': 'JOAO SOUZA', 'DataNascimento': '20000520', 'NomeMae': 'MARIA DA SILVA'}

        divergente, nome_suap, nome_rf, *_ = _comparar_dados_rf(aluno, dados_rf)
        assert divergente is True
        assert nome_suap == 'João da Silva'
        assert nome_rf == 'JOAO SOUZA'

    def test_dados_divergentes_nascimento(self):
        aluno = MagicMock()
        aluno.pessoa_fisica.nome_registro = 'João da Silva'
        aluno.pessoa_fisica.nascimento_data = datetime.date(2000, 5, 20)
        aluno.nome_mae = 'Maria da Silva'

        dados_rf = {'Nome': 'JOAO DA SILVA', 'DataNascimento': '20000521', 'NomeMae': 'MARIA DA SILVA'}

        divergente, _, _, nasc_suap, nasc_rf, *_ = _comparar_dados_rf(aluno, dados_rf)
        assert divergente is True
        assert nasc_suap == '20/05/2000'
        assert nasc_rf == '21/05/2000'


class TestRegexNomes:
    def test_nomes_validos(self):
        assert not bool(RE_NOME_INVALIDO.search('João Carlos da Silva'))
        assert not bool(RE_NOME_INVALIDO.search("O'Connor"))
        assert not bool(RE_NOME_INVALIDO.search('Ana-Maria Saint-Clair'))
        assert not bool(RE_NOME_INVALIDO.search('Álvaro Müller Núñez'))

    def test_nomes_invalidos(self):
        assert bool(RE_NOME_INVALIDO.search('João Silva 123'))
        assert bool(RE_NOME_INVALIDO.search('Carlos (Bebê)'))
        assert bool(RE_NOME_INVALIDO.search('Maria@Silva'))
        assert bool(RE_NOME_INVALIDO.search('José.Santos'))


class TestFinalizacaoAuditoria:
    @patch('edu.auditoria_ensino.send_notification')
    def test_finalizar_outras_auditorias_com_divergencias(self, mock_notify):
        auditoria = MagicMock()
        auditoria.tipo_auditoria = AuditoriaEnsino.TIPO_RECEITA_FEDERAL
        auditoria.registroauditoriaensino_set.filter.return_value.exists.return_value = True
        auditoria.is_auditoria_administrador.return_value = True
        auditoria.get_tipo_auditoria_display.return_value = 'Receita Federal'
        auditoria.get_absolute_url.return_value = '/edu/auditoria/1/'

        task = MagicMock()

        with patch('edu.auditoria_ensino.UsuarioGrupo.objects.filter') as mock_ug:
            mock_user = MagicMock()
            mock_ug.return_value.select_related.return_value.distinct.return_value = [MagicMock(user=mock_user)]
            _finalizar_auditoria(auditoria, task)

        assert auditoria.geracao_finalizada is True
        auditoria.save.assert_called_once()
        mock_notify.assert_called_once()
        task.finalize.assert_called_once_with('Auditoria gerada com sucesso.', '/edu/auditoria/1/')

    @patch('edu.auditoria_ensino.send_notification')
    def test_finalizar_sistec_com_divergencias_nao_envia_notificacao(self, mock_notify):
        auditoria = MagicMock()
        auditoria.tipo_auditoria = AuditoriaEnsino.TIPO_SISTEC
        auditoria.registroauditoriaensino_set.filter.return_value.exists.return_value = True
        auditoria.get_absolute_url.return_value = '/edu/auditoria/1/'

        task = MagicMock()
        _finalizar_auditoria(auditoria, task)

        assert auditoria.geracao_finalizada is True
        auditoria.save.assert_called_once()
        mock_notify.assert_not_called()
        task.finalize.assert_called_once_with('Auditoria gerada com sucesso.', '/edu/auditoria/1/')

    @patch('edu.auditoria_ensino._enviar_notificacao_divergencia')
    def test_service_notificar_campus(self, mock_enviar):
        auditoria = MagicMock()
        AuditoriaEnsinoService.notificar_campus(auditoria)
        mock_enviar.assert_called_once_with(auditoria)

    @patch('edu.auditoria_ensino.send_notification')
    def test_finalizar_sem_divergencias(self, mock_notify):
        auditoria = MagicMock()
        auditoria.registroauditoriaensino_set.filter.return_value.exists.return_value = False
        auditoria.get_absolute_url.return_value = '/edu/auditoria/2/'

        _finalizar_auditoria(auditoria, task=None)

        assert auditoria.geracao_finalizada is True
        assert auditoria.data_ciencia_atendente is not None
        assert auditoria.data_resolucao_auditoria is not None
        mock_notify.assert_not_called()


@pytest.mark.usefixtures('patch_task_model')
class TestServiceDispatcher:
    @patch.object(AuditoriaEnsinoService, 'processar')
    def test_gerar_auditoria_ensino_task_entrypoint(self, mock_processar, task_mock):
        auditoria = MagicMock()
        gerar_auditoria_ensino(auditoria)
        mock_processar.assert_called_once_with(auditoria, task=task_mock)

    @patch('edu.auditoria_ensino._finalizar_auditoria')
    def test_dispatcher_chama_handler_correspondente(self, mock_finalizar):
        auditoria = MagicMock()
        auditoria.tipo_auditoria = AuditoriaEnsino.TIPO_NOME_ALUNO
        task = MagicMock()

        mock_nome_aluno = MagicMock()
        with patch.dict('edu.auditoria_ensino.HANDLERS', {AuditoriaEnsino.TIPO_NOME_ALUNO: mock_nome_aluno}):
            AuditoriaEnsinoService.processar(auditoria, task)
            mock_nome_aluno.assert_called_once_with(auditoria, task)
            mock_finalizar.assert_called_once_with(auditoria, task)

    @patch('edu.auditoria_ensino._finalizar_auditoria')
    def test_dispatcher_receita_federal_sem_operador_nao_finaliza(self, mock_finalizar):
        auditoria = MagicMock()
        auditoria.tipo_auditoria = AuditoriaEnsino.TIPO_RECEITA_FEDERAL

        with patch('edu.auditoria_ensino._gerar_receita_federal', return_value=False):
            AuditoriaEnsinoService.processar(auditoria)
            mock_finalizar.assert_not_called()


class TestDesconsiderarMinicursosMenor20h:
    def test_helper_desconsiderar_minicursos_menor_20h_estrutura_query(self):
        qs = _desconsiderar_minicursos_menor_20h(Aluno.objects.all())
        query_sql = str(qs.query)
        assert '"ch_total" < 20' in query_sql

    def test_helper_com_mock_qs(self):
        mock_qs = MagicMock()
        _desconsiderar_minicursos_menor_20h(mock_qs)
        mock_qs.exclude.assert_called_once_with(
            curso_campus__ch_total__lt=CursoCampus.CARGA_HORARIA_BASE_MINICURSO, curso_campus__modalidade_id=Modalidade.FIC_MENOS
        )

    def test_obter_qs_alunos_sistec_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None
        auditoria.data_inicio_auditoria = '2026-01-01'
        auditoria.data_fim_auditoria = None

        qs = _obter_qs_alunos_sistec(auditoria)
        assert '"ch_total" < 20' in str(qs.query)

    def test_obter_qs_alunos_situacao_matricula_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        qs = _obter_qs_alunos_situacao_matricula(auditoria)
        assert '"ch_total" < 20' in str(qs.query)

    def test_obter_qs_alunos_rf_desconsidera_minicursos_menor_20h(self):
        auditoria = MagicMock()
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        qs = _obter_qs_alunos_rf(auditoria)
        assert '"ch_total" < 20' in str(qs.query)

    def test_gerar_matricula_modalidade_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.nivel_ensino_id = None

        captured = []
        with patch('edu.auditoria_ensino.iterate_task', side_effect=lambda task, qs: captured.append(qs) or iter([])):
            _gerar_matricula_modalidade(auditoria, None)

        assert len(captured) == 1
        assert '"ch_total" < 20' in str(captured[0].query)

    def test_gerar_nome_aluno_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        captured = []
        with patch('edu.auditoria_ensino.iterate_task', side_effect=lambda task, qs: captured.append(qs) or iter([])):
            _gerar_nome_aluno(auditoria, None)

        assert len(captured) == 1
        assert '"ch_total" < 20' in str(captured[0].query)

    def test_gerar_nome_pais_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        captured = []
        with patch('edu.auditoria_ensino.iterate_task', side_effect=lambda task, qs: captured.append(qs) or iter([])):
            _gerar_nome_pais(auditoria, None)

        assert len(captured) == 1
        assert '"ch_total" < 20' in str(captured[0].query)

    def test_gerar_cidade_alunos_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1

        captured = []
        with patch('edu.auditoria_ensino.iterate_task', side_effect=lambda task, qs: captured.append(qs) or iter([])):
            _gerar_cidade_alunos(auditoria, None)

        assert len(captured) == 1
        assert '"ch_total" < 20' in str(captured[0].query)

    def test_gerar_aluno_sem_sistec_desconsidera_minicursos_menor_20h(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        captured = []
        with patch('edu.auditoria_ensino.iterate_task', side_effect=lambda task, qs: captured.append(qs) or iter([])):
            _gerar_aluno_sem_sistec(auditoria, None)

        assert len(captured) == 1
        assert '"ch_total" < 20' in str(captured[0].query)

    def test_obter_codigos_sistec_minicursos_menor_20h_parsing(self):
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.values_list.return_value = ['10; 20', '30', 'invalid', '40;']
        with patch.object(CursoCampus.objects, 'filter', return_value=mock_qs):
            codigos = _obter_codigos_sistec_minicursos_menor_20h(UnidadeOrganizacional(id=1))
            assert codigos == {10, 20, 30, 40}

    def test_obter_codigos_sistec_nivel_parsing(self):
        assert _obter_codigos_sistec_nivel(None) is None

        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.values_list.return_value = ['10', '20;30']
        with patch.object(CursoCampus.objects, 'filter', return_value=mock_qs):
            codigos = _obter_codigos_sistec_nivel(1)
            assert codigos == {10, 20, 30}
            mock_qs.exclude.assert_called_once_with(codigo_sistec='')

    def test_iterar_linhas_planilha_sistec_ignora_minicurso_menor_20h(self):
        auditoria = MagicMock()
        rsheet = [
            {'CO_CURSO': '10', 'NU_CPF': '11111111111'},
            {'CO_CURSO': '20', 'NU_CPF': '22222222222'},
        ]
        codigos_desconsiderados = {10}
        with patch('edu.auditoria_ensino._processar_linha_sistec') as mock_processar:
            mock_reg = MagicMock()
            mock_processar.return_value = mock_reg
            registros, alunos_sistec_set, _atualizar, _ausentes = _iterar_linhas_planilha_sistec(
                rsheet,
                auditoria,
                codigos_nivel=None,
                codigo_unidade='UO1',
                alunos_por_cpf={},
                qs_final_alunos=MagicMock(),
                task=None,
                codigos_desconsiderados=codigos_desconsiderados,
            )
            assert mock_processar.call_count == 1
            assert mock_processar.call_args[0][0]['CO_CURSO'] == '20'
            assert len(registros) == 1
            assert ('111.111.111-11', '10', 'UO1') not in alunos_sistec_set
            assert ('222.222.222-22', '20', 'UO1') in alunos_sistec_set


class TestFiltroPronatecSistec:
    def test_constante_ano_corte_pronatec_sistec(self):
        assert ANO_CORTE_PRONATEC_SISTEC == 2025

    def test_obter_qs_alunos_sistec_exclui_pronatec_antes_de_2025(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None
        auditoria.data_inicio_auditoria = '2026-01-01'
        auditoria.data_fim_auditoria = None

        qs = _obter_qs_alunos_sistec(auditoria)
        query_sql = str(qs.query)
        # Cláusula de exclusão conjunta do PRONATEC (tipo 4) com ano letivo < 2025
        assert '"comum_ano"."ano" < 2025' in query_sql
        assert f'"edu_diretoria"."tipo" = {Diretoria.TIPO_PRONATEC}' in query_sql

    def test_outras_auditorias_nao_excluem_pronatec_por_ano(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None

        qs_sit = _obter_qs_alunos_situacao_matricula(auditoria)
        assert '"comum_ano"."ano" < 2025' not in str(qs_sit.query)

        qs_rf = _obter_qs_alunos_rf(auditoria)
        assert '"comum_ano"."ano" < 2025' not in str(qs_rf.query)


class TestFluxoSemCpfSistec:
    def test_obter_qs_alunos_sistec_apenas_sem_cpf(self):
        campus = UnidadeOrganizacional(id=1)
        auditoria = MagicMock()
        auditoria.campus = campus
        auditoria.campus_id = 1
        auditoria.nivel_ensino_id = None
        auditoria.data_inicio_auditoria = '2026-01-01'
        auditoria.data_fim_auditoria = None

        qs_com = _obter_qs_alunos_sistec(auditoria, apenas_sem_cpf=False)
        query_com_sql = str(qs_com.query)
        assert 'NOT (("pessoa_fisica"."cpf" IS NULL' in query_com_sql

        qs_sem = _obter_qs_alunos_sistec(auditoria, apenas_sem_cpf=True)
        query_sem_sql = str(qs_sem.query)
        assert '"pessoa_fisica"."cpf" IS NULL' in query_sem_sql
        assert 'NOT (("pessoa_fisica"."cpf" IS NULL' not in query_sem_sql

    def test_localizar_aluno_sem_cpf_formato_iso(self):
        data = {
            'NO_ALUNO': 'Fulano Sem Cpf',
            'DT_DATA_NASCIMENTO': '2005-08-15 00:00:00',
        }
        aluno = MagicMock()
        aluno.curso_campus.codigo_sistec = '10'

        qs_final_alunos = MagicMock()
        qs_filter = qs_final_alunos.filter.return_value.select_related.return_value
        qs_filter.__iter__.return_value = [aluno]

        aluno_enc, _candidatos, erro = _localizar_aluno_sistec(
            data,
            cpf_aluno='',
            codigo_sistec_curso=10,
            data_inicio=datetime.date(2026, 1, 1),
            alunos_por_cpf={},
            qs_final_alunos=qs_final_alunos,
        )

        assert erro is None
        assert aluno_enc == aluno
        qs_final_alunos.filter.assert_called_once_with(
            pessoa_fisica__nome__iexact='Fulano Sem Cpf',
            pessoa_fisica__nascimento_data=datetime.date(2005, 8, 15),
        )

    def test_localizar_aluno_sem_cpf_formato_brasileiro(self):
        data = {
            'NO_ALUNO': 'Ciclana Sem Cpf',
            'DT_DATA_NASCIMENTO': '20/12/2006',
        }
        aluno = MagicMock()
        aluno.curso_campus.codigo_sistec = '20'

        qs_final_alunos = MagicMock()
        qs_filter = qs_final_alunos.filter.return_value.select_related.return_value
        qs_filter.__iter__.return_value = [aluno]

        aluno_enc, _candidatos, erro = _localizar_aluno_sistec(
            data,
            cpf_aluno='',
            codigo_sistec_curso=20,
            data_inicio=datetime.date(2026, 1, 1),
            alunos_por_cpf={},
            qs_final_alunos=qs_final_alunos,
        )

        assert erro is None
        assert aluno_enc == aluno
        qs_final_alunos.filter.assert_called_once_with(
            pessoa_fisica__nome__iexact='Ciclana Sem Cpf',
            pessoa_fisica__nascimento_data=datetime.date(2006, 12, 20),
        )

    def test_processar_linha_sistec_apenas_sem_cpf_ignora_linha_com_cpf(self):
        auditoria = AuditoriaEnsino()
        auditoria.id = 1
        auditoria.data_inicio_auditoria = datetime.date(2026, 1, 1)
        auditoria.data_fim_auditoria = datetime.date(2026, 12, 31)

        data = {
            'NU_CPF': '12345678901',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2026.1',
            'NO_ALUNO': 'Aluno Com Cpf',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '15/02/2026',
        }
        reg = _processar_linha_sistec(
            data,
            auditoria,
            alunos_por_cpf={},
            qs_final_alunos=MagicMock(),
            alunos_atualizar_sistec=[],
            ids_nao_ausentes=[],
            apenas_sem_cpf=True,
        )
        assert reg is None

    def test_processar_linha_sistec_sem_cpf_convergente(self):
        auditoria = AuditoriaEnsino()
        auditoria.id = 1
        auditoria.data_inicio_auditoria = datetime.date(2026, 1, 1)
        auditoria.data_fim_auditoria = datetime.date(2026, 12, 31)

        data = {
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2026.1',
            'NO_ALUNO': 'Fulano Sem Cpf',
            'CO_MATRICULA': '999',
            'DT_DATA_INICIO': '15/02/2026',
            'DT_DATA_NASCIMENTO': '10/05/2005',
        }

        aluno = MagicMock()
        aluno.id = 10
        aluno.matricula = '2026010'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Curso Técnico'
        aluno.codigo_sistec = None

        qs_final_alunos = MagicMock()
        qs_filter = qs_final_alunos.filter.return_value.select_related.return_value
        qs_filter.__iter__.return_value = [aluno]

        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg = _processar_linha_sistec(
            data,
            auditoria,
            alunos_por_cpf={},
            qs_final_alunos=qs_final_alunos,
            alunos_atualizar_sistec=alunos_atualizar,
            ids_nao_ausentes=ids_nao_ausentes,
            apenas_sem_cpf=True,
        )

        assert reg is not None
        assert reg.divergente is False
        assert 'CONVERGENTE' in reg.registro
        assert '2026010;;Fulano Sem Cpf;' in reg.registro
        assert 10 in ids_nao_ausentes
        assert aluno in alunos_atualizar

    def test_iterar_linhas_planilha_sistec_sem_cpf_ignora_linhas_com_cpf(self):
        auditoria = MagicMock()
        rsheet = [
            {'CO_CURSO': '10', 'NU_CPF': '11111111111', 'NO_ALUNO': 'Com CPF'},
            {'CO_CURSO': '20', 'NO_ALUNO': 'Sem CPF', 'DT_DATA_NASCIMENTO': '01/01/2005'},
        ]
        with patch('edu.auditoria_ensino._processar_linha_sistec') as mock_processar:
            mock_processar.return_value = MagicMock()
            registros, alunos_sistec_set, _atualizar, _ausentes = _iterar_linhas_planilha_sistec(
                rsheet,
                auditoria,
                codigos_nivel=None,
                codigo_unidade='UO1',
                alunos_por_cpf={},
                qs_final_alunos=MagicMock(),
                task=None,
                apenas_sem_cpf=True,
            )
            assert mock_processar.call_count == 1
            assert mock_processar.call_args[0][0]['NO_ALUNO'] == 'Sem CPF'
            assert len(registros) == 1
            assert ('SEM CPF', datetime.date(2005, 1, 1), '20', 'UO1') in alunos_sistec_set

    def test_processar_alunos_ausentes_sistec_sem_cpf(self):
        auditoria = AuditoriaEnsino()
        auditoria.id = 1
        auditoria.data_inicio_auditoria = datetime.date(2026, 1, 1)
        auditoria.data_fim_auditoria = None

        aluno = MagicMock()
        aluno.id = 5
        aluno.matricula = '2026005'
        aluno.pessoa_fisica.cpf = None
        aluno.pessoa_fisica.nome = 'Aluno Ausente Sem Cpf'
        aluno.pessoa_fisica.nascimento_data = datetime.date(2005, 3, 10)
        aluno.situacao = 'Matriculado'
        aluno.curso_campus.descricao = 'Curso Teste'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.diretoria.setor.uo.codigo_sistec = 'UO1'

        qs_final_alunos = MagicMock()
        qs_final_alunos.exclude.return_value.select_related.return_value.distinct.return_value = [aluno]

        with patch('edu.auditoria_ensino._aluno_ausente_valido', return_value=True):
            regs = _processar_alunos_ausentes_sistec(
                auditoria,
                qs_final_alunos,
                ids_nao_ausentes=[],
                alunos_sistec_set=set(),
                task=None,
                apenas_sem_cpf=True,
            )
            assert len(regs) == 1
            assert regs[0].divergente is True
            assert regs[0].registro == '2026005;;Aluno Ausente Sem Cpf;-;Matriculado;AUSENTE;Curso Teste;-'

    def test_gerar_sistec_detecta_cabecalho_com_cpf(self):
        auditoria = AuditoriaEnsino()
        auditoria.campus = UnidadeOrganizacional(id=1, codigo_sistec='UO1')
        auditoria.nivel_ensino_id = None
        csv_content = 'CO_ALUNO_IDENTIFICADO;NU_CPF;CO_CURSO;NO_ALUNO\n1;111.111.111-11;10;Fulano\n'
        auditoria.fonte_dados = MagicMock()
        auditoria.fonte_dados.open.return_value = io.BytesIO(csv_content.encode('iso-8859-1'))

        with (
            patch('edu.auditoria_ensino._obter_qs_alunos_sistec') as mock_obter_qs,
            patch('edu.auditoria_ensino._obter_codigos_sistec_minicursos_menor_20h', return_value=set()),
            patch('edu.auditoria_ensino._obter_codigos_sistec_nivel', return_value=None),
            patch('edu.auditoria_ensino._iterar_linhas_planilha_sistec', return_value=([], set(), [], [])),
            patch('edu.auditoria_ensino._processar_alunos_ausentes_sistec', return_value=[]),
            patch('edu.auditoria_ensino._inicializar_task_sistec'),
            patch('edu.auditoria_ensino._carregar_alunos_por_cpf', return_value={}),
        ):
            _gerar_sistec(auditoria, None)
            mock_obter_qs.assert_called_once_with(auditoria, apenas_sem_cpf=False)

    def test_gerar_sistec_detecta_cabecalho_sem_cpf(self):
        auditoria = AuditoriaEnsino()
        auditoria.campus = UnidadeOrganizacional(id=1, codigo_sistec='UO1')
        auditoria.nivel_ensino_id = None
        csv_content = 'CO_CURSO;NO_ALUNO;DT_DATA_NASCIMENTO\n10;Fulano;2005-01-01\n'
        auditoria.fonte_dados = MagicMock()
        auditoria.fonte_dados.open.return_value = io.BytesIO(csv_content.encode('iso-8859-1'))

        with (
            patch('edu.auditoria_ensino._obter_qs_alunos_sistec') as mock_obter_qs,
            patch('edu.auditoria_ensino._obter_codigos_sistec_minicursos_menor_20h', return_value=set()),
            patch('edu.auditoria_ensino._obter_codigos_sistec_nivel', return_value=None),
            patch('edu.auditoria_ensino._iterar_linhas_planilha_sistec', return_value=([], set(), [], [])),
            patch('edu.auditoria_ensino._processar_alunos_ausentes_sistec', return_value=[]),
            patch('edu.auditoria_ensino._inicializar_task_sistec'),
            patch('edu.auditoria_ensino._carregar_alunos_por_cpf') as mock_carregar_cpfs,
        ):
            _gerar_sistec(auditoria, None)
            mock_obter_qs.assert_called_once_with(auditoria, apenas_sem_cpf=True)
            mock_carregar_cpfs.assert_not_called()


class TestBuscaPorCodigoSistec:
    def _criar_auditoria(self):
        auditoria = AuditoriaEnsino()
        auditoria.id = 1
        auditoria.data_inicio_auditoria = datetime.date(2023, 1, 1)
        auditoria.data_fim_auditoria = None
        return auditoria

    def test_carregar_alunos_por_codigo_sistec(self):
        a1 = MagicMock(codigo_sistec='100')
        a2 = MagicMock(codigo_sistec='200')
        a3 = MagicMock(codigo_sistec=None)

        qs = MagicMock()
        qs_filter = qs.filter.return_value.select_related.return_value.distinct.return_value
        qs_filter.__iter__.return_value = [a1, a2, a3]

        res = _carregar_alunos_por_codigo_sistec(qs, {'100', '200'})
        assert '100' in res
        assert '200' in res
        assert None not in res
        assert res['100'] == [a1]

    def test_localizar_aluno_por_codigo_sistec_direto(self):
        aluno = MagicMock()
        aluno.curso_campus.codigo_sistec = '10'
        aluno.codigo_sistec = '999'

        data = {
            'CO_MATRICULA': '999',
            'CO_CURSO': '10',
            'DT_DATA_INICIO': '28/08/2023',
        }
        alunos_por_cod = {'999': [aluno]}

        aluno_enc, _candidatos, erro = _localizar_aluno_sistec(
            data,
            cpf_aluno='142.552.144-41',
            codigo_sistec_curso=10,
            data_inicio=datetime.date(2023, 8, 28),
            alunos_por_cpf={},
            qs_final_alunos=MagicMock(),
            alunos_por_cod_sistec=alunos_por_cod,
        )
        assert erro is None
        assert aluno_enc == aluno

    def test_localizar_aluno_sem_cpf_por_codigo_sistec(self):
        aluno = MagicMock()
        aluno.curso_campus.codigo_sistec = '10'
        aluno.codigo_sistec = '888'

        data = {
            'CO_MATRICULA': '888',
            'CO_CURSO': '10',
            'NO_ALUNO': 'Aluno Sem Cpf',
            'DT_DATA_INICIO': '28/08/2023',
        }
        alunos_por_cod = {'888': [aluno]}
        qs_final_alunos = MagicMock()

        aluno_enc, _candidatos, erro = _localizar_aluno_sistec(
            data,
            cpf_aluno='',
            codigo_sistec_curso=10,
            data_inicio=datetime.date(2023, 8, 28),
            alunos_por_cpf={},
            qs_final_alunos=qs_final_alunos,
            alunos_por_cod_sistec=alunos_por_cod,
        )
        assert erro is None
        assert aluno_enc == aluno
        qs_final_alunos.filter.assert_not_called()

    def test_fallback_quando_codigo_sistec_vazio_popula_codigo(self):
        auditoria = self._criar_auditoria()
        aluno = MagicMock()
        aluno.id = 1
        aluno.matricula = '20232010590001'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Licenciatura'
        aluno.codigo_sistec = None

        data = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }
        alunos_por_cpf = {'142.552.144-41': [aluno]}
        alunos_por_cod: dict[str, list[Aluno]] = defaultdict(list)
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg = _processar_linha_sistec(
            data,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )
        assert reg is not None
        assert reg.divergente is False
        assert 'CONVERGENTE' in reg.registro
        assert aluno.codigo_sistec == '104651977'
        assert aluno in alunos_atualizar
        assert aluno in alunos_por_cod['104651977']

    def test_duas_linhas_mesmo_cpf_codigos_sistec_distintos_apenas_um_convergente(self):
        auditoria = self._criar_auditoria()
        aluno = MagicMock()
        aluno.id = 1
        aluno.matricula = '20232010590001'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Licenciatura'
        aluno.codigo_sistec = None

        data1 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }
        data2 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '113772967',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }

        alunos_por_cpf = {'142.552.144-41': [aluno]}
        alunos_por_cod: dict[str, list[Aluno]] = defaultdict(list)
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg1 = _processar_linha_sistec(
            data1,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )
        reg2 = _processar_linha_sistec(
            data2,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )

        assert reg1 is not None
        assert reg1.divergente is False
        assert 'CONVERGENTE' in reg1.registro

        assert reg2 is not None
        assert reg2.divergente is True
        assert 'NÃO ENCONTRADO' in reg2.registro

    def test_aluno_com_codigo_sistec_segunda_linha_apenas_um_convergente(self):
        auditoria = self._criar_auditoria()
        aluno = MagicMock()
        aluno.id = 1
        aluno.matricula = '20232010590001'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Licenciatura'
        aluno.codigo_sistec = '113772967'

        data1 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }
        data2 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '113772967',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }

        alunos_por_cpf = {'142.552.144-41': [aluno]}
        alunos_por_cod: dict[str, list[Aluno]] = {'113772967': [aluno]}
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        reg1 = _processar_linha_sistec(
            data1,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )
        reg2 = _processar_linha_sistec(
            data2,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )

        assert reg1 is not None
        assert reg1.divergente is True
        assert 'NÃO ENCONTRADO' in reg1.registro

        assert reg2 is not None
        assert reg2.divergente is False
        assert 'CONVERGENTE' in reg2.registro

    def test_aluno_com_codigo_sistec_carregado_apenas_em_alunos_por_cpf(self):
        auditoria = self._criar_auditoria()
        aluno = MagicMock()
        aluno.id = 1
        aluno.matricula = '20232010590001'
        aluno.situacao_id = SituacaoMatricula.MATRICULADO
        aluno.situacao.descricao = 'Matriculado'
        aluno.curso_campus.codigo_sistec = '10'
        aluno.curso_campus.descricao = 'Licenciatura'
        aluno.codigo_sistec = '104651977'

        outro_aluno = MagicMock()
        outro_aluno.id = 2
        outro_aluno.codigo_sistec = '9999999'

        alunos_por_cpf = {'142.552.144-41': [aluno]}
        # alunos_por_cod nao possui Jeremias inicialmente, apenas outro aluno
        alunos_por_cod: dict[str, list[Aluno]] = {'9999999': [outro_aluno]}
        alunos_atualizar: list[Aluno] = []
        ids_nao_ausentes: list[int] = []

        data1 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '104651977',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }
        data2 = {
            'NU_CPF': '142.552.144-41',
            'NO_ALUNO': 'Jeremias Cleyton',
            'CO_MATRICULA': '113772967',
            'CO_CURSO': '10',
            'NO_STATUS_MATRICULA': 'EM_CURSO',
            'NO_CICLO_MATRICULA': '2023.2',
            'DT_DATA_INICIO': '28/08/2023',
        }

        reg1 = _processar_linha_sistec(
            data1,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )
        reg2 = _processar_linha_sistec(
            data2,
            auditoria,
            alunos_por_cpf,
            MagicMock(),
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod,
        )

        assert reg1 is not None
        assert reg1.divergente is False
        assert 'CONVERGENTE' in reg1.registro
        assert '20232010590001' in reg1.registro
        assert aluno in alunos_por_cod.get('104651977', [])

        assert reg2 is not None
        assert reg2.divergente is True
        assert 'NÃO ENCONTRADO' in reg2.registro

    def test_indexar_alunos_cpf_em_cod_sistec(self):
        from edu.auditoria_ensino import _indexar_alunos_cpf_em_cod_sistec

        aluno = MagicMock()
        aluno.codigo_sistec = ' 104651977 '
        alunos_por_cpf = {'142.552.144-41': [aluno]}
        alunos_por_cod: dict[str, list[Aluno]] = defaultdict(list)

        _indexar_alunos_cpf_em_cod_sistec(alunos_por_cpf, alunos_por_cod)
        assert '104651977' in alunos_por_cod
        assert aluno in alunos_por_cod['104651977']


@pytest.mark.usefixtures('patch_task_model')
class TestRemoverRegistrosAuditoriaEnsino:
    def test_remover_registros_auditoria_ensino_chama_raw_delete_e_finalize(self, task_mock):
        from edu.tasks import remover_registros_auditoria_ensino

        auditoria = MagicMock()
        auditoria.get_absolute_url.return_value = '/edu/auditoria_ensino/1/'
        mock_qs = MagicMock()
        mock_qs.db = 'default'
        auditoria.registroauditoriaensino_set.all.return_value = mock_qs

        remover_registros_auditoria_ensino(auditoria)

        auditoria.registroauditoriaensino_set.all.assert_called_once()
        mock_qs._raw_delete.assert_called_once_with(using='default')
        task_mock.finalize.assert_called_once_with('Auditoria desfeita com sucesso.', '/edu/auditoria_ensino/1/')

    def test_remover_registros_auditoria_ensino_direto_com_task_none(self):
        from edu.tasks import remover_registros_auditoria_ensino

        auditoria = MagicMock()
        mock_qs = MagicMock()
        mock_qs.db = 'default'
        auditoria.registroauditoriaensino_set.all.return_value = mock_qs

        remover_registros_auditoria_ensino(auditoria, task=None)

        mock_qs._raw_delete.assert_called_once_with(using='default')

    def test_registro_auditoria_ensino_nao_herda_logmodel_e_history_disabled(self):
        from edu.models import LogModel, RegistroAuditoriaEnsino

        assert not issubclass(RegistroAuditoriaEnsino, LogModel)
        assert hasattr(RegistroAuditoriaEnsino, 'History')
        assert getattr(RegistroAuditoriaEnsino.History, 'disabled', False) is True


class TestNotificarCampusAuditoriaEnsino:
    def test_pode_notificar_campus_sucesso(self):
        user = MagicMock()
        user.has_perm.side_effect = lambda perm: perm == 'comum.is_administrador_academico'

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=True,
            data_resolucao_auditoria=None,
        )
        assert auditoria.pode_notificar_campus(user) is True

    def test_pode_notificar_campus_sem_permissao(self):
        user = MagicMock()
        user.has_perm.return_value = False

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=True,
            data_resolucao_auditoria=None,
        )
        assert auditoria.pode_notificar_campus(user) is False

    def test_pode_notificar_campus_tipo_nao_sistec(self):
        user = MagicMock()
        user.has_perm.return_value = True

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_RECEITA_FEDERAL,
            geracao_finalizada=True,
            data_resolucao_auditoria=None,
        )
        assert auditoria.pode_notificar_campus(user) is False

    def test_pode_notificar_campus_nao_gerada(self):
        user = MagicMock()
        user.has_perm.return_value = True

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=False,
            data_resolucao_auditoria=None,
        )
        assert auditoria.pode_notificar_campus(user) is False

    def test_pode_notificar_campus_ja_resolvida(self):
        user = MagicMock()
        user.has_perm.return_value = True

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=True,
            data_resolucao_auditoria=datetime.date.today(),
        )
        assert auditoria.pode_notificar_campus(user) is False

    @patch('edu.auditoria_ensino.AuditoriaEnsinoService.notificar_campus')
    def test_notificar_campus_com_permissao(self, mock_service_notificar):
        user = MagicMock()
        user.has_perm.side_effect = lambda perm: perm == 'comum.is_administrador_academico'

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=True,
            data_resolucao_auditoria=None,
        )
        auditoria.notificar_campus(user)
        mock_service_notificar.assert_called_once_with(auditoria)

    @patch('edu.auditoria_ensino.AuditoriaEnsinoService.notificar_campus')
    def test_notificar_campus_sem_permissao_nao_chama_service(self, mock_service_notificar):
        user = MagicMock()
        user.has_perm.return_value = False

        auditoria = AuditoriaEnsino(
            tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC,
            geracao_finalizada=True,
            data_resolucao_auditoria=None,
        )
        auditoria.notificar_campus(user)
        mock_service_notificar.assert_not_called()


class TestViewAuditoriaNotificarCampus:
    @patch('edu.views.auditoria.get_object_or_404')
    @patch('edu.views.auditoria.httprr')
    def test_view_auditoria_notificar_campus_com_sucesso(self, mock_httprr, mock_get_obj):
        from django.http import HttpResponseRedirect
        from edu.views.auditoria import auditoria

        mock_httprr.return_value = HttpResponseRedirect('/edu/auditoria/1/')
        mock_obj = MagicMock()
        mock_obj.get_absolute_url.return_value = '/edu/auditoria/1/'
        mock_obj.pode_notificar_campus.return_value = True
        mock_get_obj.return_value = mock_obj

        request = MagicMock()
        user = MagicMock()
        user.has_perm.return_value = True
        user.is_authenticated = True
        request.user = user

        resp = auditoria(request, 1, 'notificar_campus')

        assert resp.status_code == 302
        mock_obj.pode_notificar_campus.assert_called_once_with(user)
        mock_obj.notificar_campus.assert_called_once_with(user)
        mock_httprr.assert_called_once_with('/edu/auditoria/1/', 'Notificação enviada com sucesso para o campus.')

    @patch('edu.views.auditoria.get_object_or_404')
    @patch('edu.views.auditoria.httprr')
    def test_view_auditoria_notificar_campus_sem_permissao(self, mock_httprr, mock_get_obj):
        from django.http import HttpResponseRedirect
        from edu.views.auditoria import auditoria

        mock_httprr.return_value = HttpResponseRedirect('/edu/auditoria/1/')
        mock_obj = MagicMock()
        mock_obj.get_absolute_url.return_value = '/edu/auditoria/1/'
        mock_obj.pode_notificar_campus.return_value = False
        mock_get_obj.return_value = mock_obj

        request = MagicMock()
        user = MagicMock()
        user.has_perm.return_value = True
        user.is_authenticated = True
        request.user = user

        resp = auditoria(request, 1, 'notificar_campus')

        assert resp.status_code == 302
        mock_obj.pode_notificar_campus.assert_called_once_with(user)
        mock_obj.notificar_campus.assert_not_called()
        mock_httprr.assert_called_once_with('/edu/auditoria/1/', 'Não foi possível notificar_campus esta auditoria.', 'error')


class TestAuditoriaAlunosRetidos:
    def test_aluno_minicurso_retido_quando_matriculado_e_vencido_mais_de_1_dia(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
        aluno = Aluno(
            curso_campus=curso,
            situacao_id=SituacaoMatricula.MATRICULADO,
            data_prevista_termino_ciclo=limite_fic - datetime.timedelta(days=1),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is True

    def test_aluno_minicurso_nao_retido_quando_termina_hoje(self) -> None:
        hoje = datetime.date(2026, 10, 16)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
        aluno = Aluno(
            curso_campus=curso,
            situacao_id=SituacaoMatricula.MATRICULADO,
            data_prevista_termino_ciclo=hoje,
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is False

    def test_aluno_minicurso_retido_quando_terminou_ontem(self) -> None:
        hoje = datetime.date(2026, 10, 16)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
        aluno = Aluno(
            curso_campus=curso,
            situacao_id=SituacaoMatricula.MATRICULADO,
            data_prevista_termino_ciclo=hoje - datetime.timedelta(days=1),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is True

    def test_aluno_minicurso_nao_retido_quando_data_prevista_futura(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
        aluno = Aluno(
            curso_campus=curso,
            situacao_id=SituacaoMatricula.MATRICULADO,
            data_prevista_termino_ciclo=hoje + datetime.timedelta(days=5),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is False

    def test_aluno_minicurso_nao_retido_quando_nao_matriculado(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
        aluno = Aluno(
            curso_campus=curso,
            situacao_id=SituacaoMatricula.CONCLUIDO,
            data_prevista_termino_ciclo=limite_fic - datetime.timedelta(days=1),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is False

    def test_aluno_regular_retido_quando_vencido_mais_de_1_ano(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.TECNOLOGIA, descricao='TSI')
        aluno = Aluno(
            curso_campus=curso,
            data_prevista_termino_ciclo=limite_demais - datetime.timedelta(days=5),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is True

    def test_aluno_regular_nao_retido_quando_vencido_ha_menos_de_1_ano(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        curso = CursoCampus(modalidade_id=Modalidade.TECNOLOGIA, descricao='TSI')
        aluno = Aluno(
            curso_campus=curso,
            data_prevista_termino_ciclo=limite_demais + datetime.timedelta(days=10),
        )

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is False

    def test_get_header_alunos_retidos(self):
        auditoria = AuditoriaEnsino(tipo_auditoria=AuditoriaEnsino.TIPO_ALUNOS_RETIDOS)
        header = auditoria.get_header()
        assert header == ['MATRÍCULA', 'CPF', 'NOME', 'SITUAÇÃO', 'CURSO', 'DATA PREVISTA TÉRMINO']

    @patch('edu.models.censos.RegistroAuditoriaEnsino.objects.bulk_create')
    @patch('edu.auditoria_ensino.iterate_task')
    def test_gerar_alunos_retidos_cria_registros(self, mock_iterate, mock_bulk):
        auditoria = AuditoriaEnsino(id=1, campus_id=1, nivel_ensino_id=None)

        curso = CursoCampus(modalidade_id=Modalidade.TECNOLOGIA, descricao='TSI')
        aluno_retido = Aluno(
            matricula='20201001',
            curso_campus=curso,
            pessoa_fisica=PessoaFisica(cpf='111.111.111-11', nome='Aluno Retido'),
            situacao=SituacaoMatricula(descricao='Trancado'),
            data_prevista_termino_ciclo=datetime.date(2022, 1, 1),
        )

        aluno_ok = Aluno(
            matricula='20201002',
            curso_campus=curso,
            pessoa_fisica=PessoaFisica(cpf='222.222.222-22', nome='Aluno OK'),
            situacao=SituacaoMatricula(descricao='Matriculado'),
            data_prevista_termino_ciclo=datetime.date(2030, 1, 1),
        )

        mock_iterate.return_value = [aluno_retido, aluno_ok]

        with patch.object(Aluno.objects, 'filter') as mock_filter:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = []
            mock_qs.exclude.return_value.select_related.return_value = mock_qs
            mock_qs.distinct.return_value = mock_qs
            mock_filter.return_value = mock_qs
            with patch('edu.auditoria_ensino._desconsiderar_minicursos_menor_20h', return_value=mock_qs):
                _gerar_alunos_retidos(auditoria, None)

        mock_bulk.assert_called_once()
        registros_criados = mock_bulk.call_args[0][0]
        assert len(registros_criados) == 1
        assert registros_criados[0].divergente is True
        assert registros_criados[0].registro == '20201001;111.111.111-11;Aluno Retido;Trancado;TSI;01/01/2022'

    def test_aluno_sem_data_prevista_considerado_retido(self):
        hoje = datetime.date(2026, 10, 13)
        limite_fic = hoje - datetime.timedelta(days=1)
        limite_demais = hoje - relativedelta(years=1)

        aluno = Aluno(data_prevista_termino_ciclo=None)

        assert _aluno_esta_retido(aluno, limite_fic, limite_demais) is True

    @patch('edu.models.censos.RegistroAuditoriaEnsino.objects.bulk_create')
    @patch('edu.auditoria_ensino.iterate_task')
    def test_gerar_alunos_retidos_sem_data_prevista_gera_registro_com_hifen(self, mock_iterate, mock_bulk):
        auditoria = AuditoriaEnsino(id=1, campus_id=1, nivel_ensino_id=None)

        curso = CursoCampus(modalidade_id=Modalidade.TECNOLOGIA, descricao='TSI')
        aluno_sem_data = Aluno(
            matricula='20201002',
            curso_campus=curso,
            pessoa_fisica=PessoaFisica(cpf='222.222.222-22', nome='Aluno Sem Data'),
            situacao=SituacaoMatricula(descricao='Matriculado'),
            data_prevista_termino_ciclo=None,
        )

        mock_iterate.return_value = [aluno_sem_data]

        with patch.object(Aluno.objects, 'filter') as mock_filter:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = []
            mock_qs.exclude.return_value.select_related.return_value = mock_qs
            mock_qs.distinct.return_value = mock_qs
            mock_filter.return_value = mock_qs
            with patch('edu.auditoria_ensino._desconsiderar_minicursos_menor_20h', return_value=mock_qs):
                _gerar_alunos_retidos(auditoria, None)

        mock_bulk.assert_called_once()
        registros = mock_bulk.call_args[0][0]
        assert len(registros) == 1
        assert registros[0].divergente is True
        assert registros[0].registro == '20201002;222.222.222-22;Aluno Sem Data;Matriculado;TSI;NÃO INFORMADO'
