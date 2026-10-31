# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *


class FicWorkflowTestCase(EduTestCase):
    CENARIOS = frozenset({'fic'})

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        EduTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['FormaIngresso'] = self.retornar(FormaIngresso, chaves={'descricao': 'Matrícula Direta'})
        self.initial_data['NivelEnsino'] = NivelEnsino.objects.get(pk=NivelEnsino.FUNDAMENTAL)
        self.initial_data['TipoComponente'] = self.retornar(TipoComponente, chaves={'descricao': 'FIC'})
        self.initial_data['Componente'] = self.retornar(Componente, chaves={'sigla': 'FIC.0001'})
        self.initial_data['Matriz'] = self.retornar(Matriz, chaves={'descricao': 'FIC em Agricultor Familiar [PRONATEC]'})
        self.initial_data['CursoCampus'] = self.retornar(CursoCampus, chaves={'descricao': 'FIC+ Agricultor Familiar [PRONATEC]'})
        self.initial_data['MatrizCurso'] = self.retornar(MatrizCurso, chaves={'matriz__descricao': 'FIC em Agricultor Familiar [PRONATEC]'})
        self.initial_data['Professor'] = self.retornar(Professor)

    def efetuar_matricula_turma(self):
        aluno = self.retornar(Aluno)
        numero_matriculas_diario_antes = MatriculaDiario.objects.count()
        url = f'/edu/efetuar_matricula_turma/{aluno.pk}/'
        response = self.client.get(url)
        assert 'Matrícula em Turma' in response.content.decode()
        assert response.status_code == 200
        turma = self.retornar(Turma)
        data = {'turma': turma.pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        numero_matriculas_diario_depois = MatriculaDiario.objects.count()
        assert numero_matriculas_diario_depois == numero_matriculas_diario_antes + turma.diario_set.count()

    def test_fluxo_fic_completo(self):
        with freeze_time('2013-01-01'):
            # VINCULAÇÃO DOS USUÁRIOS
            self.vincular_usuario_a_diretoria('Secretário Acadêmico')

            # EAD
            self.acessar_como_secretario()
            # self.acessar_polo()
            # self.cadastrar_atividade_polo()

            # GERAÇÃO DE TURMAS E DIARIOS
            self.cadastrar_calendario_academico(params={'descricao': 'Calendário 1'})
            self.gerar_turmas_diarios()
            self.cadastrar_professor_nao_servidor()
            self.transferir_posse_etapa()
            self.configurar_diario()
            self.acessar_como_professor()
            self.visualizar_locais_horario_aulas_professor()

            # MATRÍCULA INSTITUCIONAL
            self.acessar_como_secretario()
            self.acessar_painel_controle()
            self.efetuar_matricula_institucional()
            self.cancelar_matricula()
            self.efetuar_matricula_institucional()
            self.efetuar_matricula_turma()
            self.emitir_relatorio_alunos()
            self.emitir_relatorio_professores()
            self.emitir_relatorio_diarios()
            self.emitir_relatorio_ead()
            self.imprimir_comprovante_matricula()
            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos()
            self.atualizar_endereco()
            self.visualizar_locais_horario_aulas_aluno()

        with freeze_time('2013-01-02'):
            # LANÇAMENTO DAS NOTAS
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor()
        self.acessar_como_aluno()
        self.acompanhar_aulas()
        self.acessar_como_professor()
        self.cadastrar_material_didatico()
        self.vincular_material_didatico()
        self.acessar_como_aluno()
        self.visualizar_materiais_didaticos()
        self.acessar_como_professor()
        self.lancar_notas_professor(50)
        self.lancar_notas_professor(80, 5)
        self.lancar_notas_professor(None, 5)
        self.lancar_notas_professor(None)
        self.lancar_notas_professor(20)
        self.lancar_notas_professor(None)
        self.lancar_notas_professor(80)
        self.imprimir_diario()
        self.acessar_como_aluno()
        self.visualizar_boletim_individual()

        # ENTREGA E RELANÇAMENTO DE ETAPA
        self.acessar_como_professor()
        self.entregar_etapa()
        self.solicitar_relancamento_etapa()
        self.acessar_como_secretario()
        self.indeferir_solicitacao_relancamento_etapa()
        self.acessar_como_professor()
        self.solicitar_relancamento_etapa()
        self.acessar_como_secretario()
        self.alterar_aulas_faltas_notas()
        self.deferir_solicitacao_relancamento_etapa()
        self.emitir_relatorio_faltas(codigo_turma=self.retornar(Turma).codigo)
        self.emitir_relatorio_faltas(codigo_turma=self.retornar(Turma).codigo, contendo=self.retornar(Aluno).pessoa_fisica.nome)

        # ACESSANDO PAINEL DE CONTROLE
        # A diretoria é cadastrada no setor do `servidor_b` (ver `cadastrar_diretoria`), e o
        # painel rotula a pendência com a sigla dele — antes fixa em 'B1', do `suap_data`.
        self.acessar_painel_controle(conteudo=f'Pendências da {self.servidor_b.setor.sigla}')
        self.relatorio_periodos_abertos(ano='2013', contem=True, contendo=self.retornar(Aluno).pessoa_fisica.nome)

        # FECHAMENTO DO PERÍODO COM PENDÊNCIA E SEM FORÇAMENTO
        self.transferir_posse_etapa_registro_escolar()
        self.lancar_notas_secretario('')
        self.fechar_periodo(False, SituacaoMatricula.MATRICULADO, SituacaoMatriculaPeriodo.MATRICULADO, MatriculaDiario.SITUACAO_CURSANDO)

        # FECHAMENTO DO PERÍODO COM PENDÊNCIA E COM FORÇAMENTO
        self.acessar_como_administrador()
        # self.abrir_periodo()
        self.acessar_como_secretario()
        self.lancar_notas_secretario('')
        self.fechar_periodo(True, SituacaoMatricula.NAO_CONCLUIDO, SituacaoMatriculaPeriodo.REPROVADO, MatriculaDiario.SITUACAO_REPROVADO)

        # FECHAMENTO DO PERÍODO SEM PENDÊNCIA E SEM FORÇAMENTO
        self.acessar_como_administrador()
        self.abrir_periodo()
        self.acessar_como_secretario()
        self.lancar_notas_secretario(80)
        self.fechar_periodo(False, SituacaoMatricula.CONCLUIDO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)
        self.relatorio_periodos_abertos(ano='2013', contem=False, contendo=self.retornar(Aluno).pessoa_fisica.nome)

        # CONFIGURAÇÃO DO LIVRO DE REGISTRO DE DIPLOMA
        self.acessar_como_administrador()
        self.configurar_livro()
        self.cadastrar_processo()

        # self.fechar_periodo(False, SituacaoMatricula.CONCLUIDO, SituacaoMatriculaPeriodo.APROVADO, MatriculaDiario.SITUACAO_APROVADO)

        # EMISSÃO DO CERTIFICADO
        self.emitir_diploma_lote()
        self.acessar_como_secretario()
        self.imprimir_registro_emissao_diploma()
        self.visualizar_historico(True)

        # ENVIO DE MENSAGEM
        self.acessar_como_secretario()
        self.enviar_mensagem()
        self.acessar_como_aluno()
        self.caixa_entrada_aluno()

        # ESTATÍSTICA
        self.acessar_como_administrador()
        self.relatorio_estatisticas()

        self.acessar_como_aluno()
        self.visualizar_dados_pessoais_e_academicos(ja_selecionou_email=True)

    def acessar_painel_controle(self, conteudo=None):
        url = '/edu/painel_controle/'
        response = self.client.get(url)
        # self.to_html(response)
        assert 'Painel de Controle' in response.content.decode()

        if conteudo:
            assert conteudo in response.content.decode()
