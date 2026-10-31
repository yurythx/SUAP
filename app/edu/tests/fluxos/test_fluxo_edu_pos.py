# ruff: noqa: F403,F405
from edu.tests._suap_edu_legacy_pos import PosGraduacaoBaseWorkflowTestCase
from edu.tests.test_suap_edu_legacy_base import *


class PosGraduacaoWorkflowTestCase(PosGraduacaoBaseWorkflowTestCase):
    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        PosGraduacaoBaseWorkflowTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['MatrizCurso'] = self.retornar(
            MatrizCurso, chaves={'matriz__descricao': 'Mestrado em Agricultor Familiar', 'curso_campus__descricao': 'Mestrado em Agricultor Familiar'}
        )
        self.initial_data['CursoCampus'] = self.retornar(CursoCampus, chaves={'descricao': 'Mestrado em Agricultor Familiar'})
        self.initial_data['FormaIngresso'] = self.retornar(FormaIngresso, chaves={'descricao': 'Processo Seletivo'})

    def evasao_em_lote(self):
        aluno = self.retornar(Aluno)
        situacao_inicial = aluno.situacao.id
        # acessando a evasao em lote
        ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
        url = f'/edu/evasao_em_lote/?ano_letivo={ultima_matricula_periodo.ano_letivo.pk:d}&periodo_letivo={ultima_matricula_periodo.periodo_letivo:d}&uo=&curso_campus=&curso_campus='
        response = self.client.get(url, follow=True)
        # evadindo o aluno
        assert 'Em Aberto' in response.content.decode()
        assert response.status_code == 200

        url = f'/edu/evadir_aluno/{aluno.id}/'
        data = {'alunos_selecionados': [aluno.id]}
        response = self.client.post(url, data, follow=True)
        assert 'Aluno evadido com sucesso.' in response.content.decode()
        aluno = self.recarregar(aluno)
        assert aluno.situacao.id == SituacaoMatricula.EVASAO

        # desfazendo a evasao
        url = f'/edu/aluno/{aluno.matricula}/?tab=procedimentos'
        response = self.client.get(url, follow=True)
        assert 'Desfazer procedimento' in response.content.decode()
        assert response.status_code == 200
        procedimento = ProcedimentoMatricula.objects.get(matricula_periodo__in=aluno.matriculaperiodo_set.all())
        url = f'/edu/aluno/{aluno.matricula}/?tab=procedimentos&procedimento_id={procedimento.pk:d}'
        response = self.client.get(url, follow=True)
        assert 'Procedimento desfeito com sucesso!' in response.content.decode()
        assert response.status_code == 200
        aluno = self.recarregar(aluno)
        assert aluno.situacao.id == situacao_inicial

    def test_fluxo_pos_graduacao_completo(self):
        with freeze_time('2013-01-01'):
            # VINCULAÇÃO DOS USUÁRIOS
            self.vincular_usuario_a_diretoria('Secretário Acadêmico')
            self.vincular_usuario_a_diretoria('Coordenador de Registros Acadêmicos')

            # GERAÇÃO DE TURMAS E DIARIOS
            self.acessar_como_secretario()
            self.cadastrar_calendario_academico(tipo=CalendarioAcademico.TIPO_SEMESTRAL)
            self.gerar_turmas_diarios()
            self.cadastrar_professor_nao_servidor()
            self.transferir_posse_etapa()
            self.configurar_diario()

            self.acessar_como_professor()
            self.visualizar_locais_horario_aulas_professor()

            # IMPORTAÇÃO DO EDITAL
            self.acessar_como_administrador()
            self.importar_edital()
            self.definir_formas_ingresso()

            # MATRÍCULA INSTITUCIONAL POR PROCESSO SELETIVO
            self.acessar_como_secretario()
            self.identificar_canditado()
            self.efetuar_matricula_institucional()
            self.cancelar_matricula()
            self.identificar_canditado()
            self.efetuar_matricula_institucional()
            self.efetuar_matricula_turma()
            self.emitir_relatorio_alunos()
            self.imprimir_comprovante_matricula()

        with freeze_time('2013-01-02'):
            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos()
            self.visualizar_botao_email_academico()
            self.atualizar_endereco()
            self.definir_email_institucional()
            self.visualizar_locais_horario_aulas_aluno()

            # LANÇAMENTO DAS NOTAS
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor()
            self.imprimir_diario()

            self.acessar_como_aluno()
            self.acompanhar_aulas()

            self.acessar_como_professor()
            self.cadastrar_material_didatico()
            self.vincular_material_didatico()

            self.acessar_como_aluno()
            self.visualizar_materiais_didaticos()

            self.acessar_como_aluno()
            self.visualizar_boletim_individual()

            # ENTREGA DE ETAPA
            self.acessar_como_professor()
            self.lancar_notas_professor()
            self.alterar_configuracao_avaliacao()
            self.entregar_etapa()

            self.acessar_como_secretario()
            self.fechar_periodo(False, SituacaoMatricula.MATRICULADO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)

            # CADASTRO DE CONFIGURAÇÃO DE ATIVIDADES COMPLEMENTARES
            self.acessar_como_administrador()
            self.cadastrar_configuracao_atividade_complementar()
            self.visualizar_configuracao_atividade_complementar()
            self.cadastrar_item_configuracao_atividade_complementar()
            self.excluir_item_configuracao_atividade_complementar()
            self.cadastrar_item_configuracao_atividade_complementar()
            self.vincular_matriz_configuracao_atividade_complementar()

            # CADASTRO DE ATIVIDADES COMPLEMENTARES
            self.acessar_como_aluno()
            self.cadastrar_atividade_complementar(is_aluno=True)

            self.acessar_como_secretario()
            self.avaliar_atividade_complementar()
            self.excluir_atividade_complementar()
            self.cadastrar_atividade_complementar(False)
            self.visualizar_atividade_complementar(False)
            self.excluir_atividade_complementar()
            self.cadastrar_atividade_complementar()
            self.visualizar_atividade_complementar()

        with freeze_time('2013-02-01'):
            # SEGUNDO PERÍODO DO CURSO (GERAÇÃO DE TURMAS E DIÁRIOS)
            self.acessar_como_secretario()
            self.cadastrar_calendario_academico(self.ano_2013, 2, CalendarioAcademico.TIPO_SEMESTRAL)
            self.gerar_turmas_diarios(self.ano_2013, 2, 2, qtd_turmas=1)
            self.configurar_diario()

            self.gerar_turmas_diarios(self.ano_2013, 2, 2, qtd_turmas=2)
            self.configurar_diario()

            self.acessar_como_professor()
            self.visualizar_locais_horario_aulas_professor()

            # TESTANDO A EVASÃO EM LOTE
            self.acessar_como_secretario()
            self.evasao_em_lote()

            # MATRÍCULA DA TURMA DO SEGUNDO PERÍODO
            self.acessar_como_secretario()

            self.efetuar_matricula_turma()
            self.efetuar_tansferencia_turma()
            self.excluir_turma()

            self.emitir_relatorio_alunos()
            self.imprimir_comprovante_matricula()

        with freeze_time('2013-02-02'):
            # LANÇAMENTO DAS NOTAS
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor()
            self.lancar_notas_professor()

            self.acessar_como_aluno()
            self.acompanhar_aulas()

            # ENTREGA DA ETAPA
            self.acessar_como_professor()
            self.entregar_etapa()

            self.acessar_como_secretario()
            self.fechar_periodo(False, SituacaoMatricula.MATRICULADO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)

        with freeze_time('2014-01-01'):
            # TERCEIRO PERÍODO DO CURSO (GERAÇÃO DE TURMAS E DIÁRIO COM  DISCIPLINA DE TCC)
            self.acessar_como_secretario()
            self.cadastrar_calendario_academico(self.ano_2014, 1, CalendarioAcademico.TIPO_SEMESTRAL)
            self.gerar_turmas_diarios(self.ano_2014, 1, 3)
            self.configurar_diario()

            self.acessar_como_professor()
            self.visualizar_locais_horario_aulas_professor()

            # MATRÍCULA DA TURMA DO TERCEIRO PERÍODO
            self.acessar_como_secretario()
            self.efetuar_matricula_turma()

        with freeze_time('2014-01-02'):
            # CADASTRO DOS ENCONTROS COM O ALUNO
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor(self.ano_2014)
            self.lancar_notas_professor()

            # LANÇAMENTO DA NOTA DO PROJETO FINAL
            self.acessar_como_secretario()
            self.cadastrar_projeto_final()
            self.emitir_declaracao_participacao_projeto_final()
            # self.excluir_projeto_final()

            # ENTREGA DA ETAPA
            self.acessar_como_professor()
            self.entregar_etapa()

            # FECHANDO O TERCEIRO E ÚLTIMO PERÍODO
            self.acessar_como_secretario()
            # lançar dispensa ENADE

            self.fechar_periodo(False, SituacaoMatricula.CONCLUIDO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)

            # PROCEDIMENTOS DE MATRÍCULA
            self.cadastrar_processo()
            self.acessar_como_administrador()
            self.abrir_periodo()
            self.acessar_como_secretario()
            self.procedimento_matricula(SituacaoMatricula.CANCELAMENTO_COMPULSORIO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.CANCELADO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.EVASAO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.JUBILADO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.INTERCAMBIO)
            self.desfazer_ultimo_procedimento_matricula()
            self.procedimento_matricula(SituacaoMatricula.TRANCADO)
            self.desfazer_ultimo_procedimento_matricula()

            self.procedimento_matricula(SituacaoMatricula.CANCELADO)
            self.pc_reintegracao(self.ano_2014, '2')
            self.desfazer_ultimo_procedimento_matricula()
            self.desfazer_ultimo_procedimento_matricula()

            # FECHANDO O TERCEIRO E ÚLTIMO PERÍODO
            self.acessar_como_secretario()
            self.fechar_periodo(False, SituacaoMatricula.CONCLUIDO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)

            # CONFIGURAÇÃO DO LIVRO DE REGISTRO DE DIPLOMA
            self.acessar_como_administrador()
            self.configurar_livro()
            self.cadastrar_processo()

            # EMISSÃO DO DIPLOMA
            self.acessar_como_secretario()
            self.emitir_diploma()
            self.imprimir_registro_emissao_diploma()
            self.visualizar_historico(True)

            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos(ja_selecionou_email=True, com_atividades_complementares=True)
