# ruff: noqa: F403,F405
from edu.tests._suap_edu_legacy_pos import PosGraduacaoBaseWorkflowTestCase
from edu.tests.test_suap_edu_legacy_base import *


class QAcademicoImportWorkflowTestCase(PosGraduacaoBaseWorkflowTestCase):
    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        PosGraduacaoBaseWorkflowTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['FormaIngresso'] = self.retornar(FormaIngresso, chaves={'descricao': 'Integração Q-Acadêmico'})
        self.initial_data['NaturezaParticipacao'] = self.retornar(NaturezaParticipacao, chaves={'descricao': 'Presencial'})
        self.initial_data['EstruturaCurso'] = self.retornar(EstruturaCurso, chaves={'descricao': 'PÓS-GRADUAÇAO (SERIADO)'})

    def importar_dados(self):
        call_command('edu_importar_dados', verbosity=0)
        assert self.retornar(CursoCampus, chaves={'descricao': 'Curso Importado'}).descricao == 'Curso Importado'
        assert self.retornar(Aluno, chaves={'matricula': '270636252864'}).matricula == '270636252864'

    def ativar_curso_importado(self):
        curso = self.retornar(CursoCampus)
        # acessando a página de cadastro de curso
        url = f'/admin/edu/cursocampus/{curso.pk}/change/'
        response = self.client.get(url)
        assert f'Editar {curso}' in response.content.decode()
        assert response.status_code == 200
        turno = self.retornar(Turno, chaves={'descricao': 'Matutino'})
        estrutura = self.retornar(EstruturaCurso)
        diretoria = self.retornar(Diretoria)
        area = self.retornar(AreaCurso)
        eixo = self.retornar(EixoTecnologico)
        area_capes = self.retornar(AreaCapes)
        data = {
            'descricao': 'Curso Importado',
            'descricao_historico': 'Curso Importado',
            'ano_letivo': self.ano_2013.pk,
            'periodo_letivo': '1',
            'data_inicio': '17/06/2013',
            'data_fim': '',
            'ativo': 'on',
            'codigo': '1234',
            'turno': turno.pk,
            'modalidade': Modalidade.MESTRADO,
            'area': area.pk,
            'eixo': eixo.pk,
            'area_capes': area_capes.pk,
            'estrutura': estrutura.pk,
            'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
            'diretoria': diretoria.pk,
            'emite_diploma': True,
            'titulo_certificado_masculino': 'Certificado',
            'titulo_certificado_feminino': 'Certificada',
            'quantidade_vagas': '10',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        return self.retornar(CursoCampus)

    def integralizar_aluno(self):
        matriz = self.retornar(Matriz)
        # acessando a página de integralização dos alunos do Q-Acadêmico
        url = f'/edu/integralizar_alunos/{matriz.id}/'
        response = self.client.get(url)
        assert 'Migração de Alunos Ativos do Q-Acadêmico' in response.content.decode()
        assert response.status_code == 200
        arquivo = open('edu/fixtures/test_integralizacao.xlsx', 'r+b')
        data = {'ano_letivo': self.ano_2013.pk, 'periodo_letivo': '2', 'arquivo': arquivo}
        response = self.client.post(url, data)
        arquivo.close()
        self.assert_no_validation_errors(response)
        assert self.retornar(Aluno).matriz == matriz

    def atualizar_dados_aluno_integralizado(self):
        aluno = self.retornar(Aluno)
        cidade = Cidade.objects.get(codigo=2401403)
        convenio = self.retornar(Convenio)
        url = f'/admin/edu/aluno/{aluno.pk}/change/'
        response = self.client.get(url)
        assert 'Editar ' in response.content.decode()
        assert response.status_code == 200
        count = Aluno.objects.all().count()

        data = {
            'nome': aluno.pessoa_fisica.nome,
            'nome_mae': 'Maria da Silva',
            'cpf': aluno.pessoa_fisica.cpf,
            'data_nascimento': '27/08/1984',
            'estado_civil': 'Solteiro',
            'sexo': aluno.pessoa_fisica.sexo,
            'genero': aluno.pessoa_fisica.genero or '',
            'nacionalidade': 'Brasileira',
            'naturalidade': cidade.pk,
            'turno': aluno.turno.pk,
            'logradouro': 'Av. Pedro e Silva',
            'numero': '908',
            'bairro': 'Centro',
            'cidade': cidade.pk,
            'cota_sistec': 9,
            'cota_mec': 0,
            'forma_ingresso': self.retornar(FormaIngresso).pk,
            'raca': self.raca.pk,
            'tipo_instituicao_origem': Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES[0][0],
            'tipo_zona_residencial': Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES[0][0],
            'possui_convenio': True,
            'convenio': convenio.pk,
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert Aluno.objects.all().count() == count

    def realizar_equivalencia_componente_qacademico(self):
        componente = self.retornar(Componente, chaves={'sigla': 'POS.0001'})
        equivalencia_componente_qacademico = self.retornar(EquivalenciaComponenteQAcademico)

        # acessando o histórico antes da equivalencia
        aluno = self.retornar(Aluno)
        url_historico = f'/edu/emitir_historico_parcial_pdf/{aluno.id}/?html=1'
        response = self.client.get(url_historico)
        assert equivalencia_componente_qacademico.sigla in response.content.decode()
        assert response.status_code == 200

        # acessando a página de equivalencia do componente importado do Q-Acadêmico
        url = f'/admin/edu/equivalenciacomponenteqacademico/{equivalencia_componente_qacademico.id}/change/'
        response = self.client.get(url, follow=True)
        assert f'Editar {equivalencia_componente_qacademico.sigla}' in response.content.decode()
        assert response.status_code == 200
        data = {
            'q_academico': equivalencia_componente_qacademico.q_academico,
            'sigla': equivalencia_componente_qacademico.sigla,
            'descricao': equivalencia_componente_qacademico.descricao,
            'carga_horaria': equivalencia_componente_qacademico.carga_horaria,
            'componente': componente.id,
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        # acessando o histórico depois da equivalencia
        response = self.client.get(url_historico)
        assert equivalencia_componente_qacademico.sigla not in response.content.decode()
        assert response.status_code == 200

    def test_fluxo_importacao_qacademico_completo(self):
        with freeze_time('2013-01-01'):
            # VINCULAÇÃO DOS USUÁRIOS
            self.vincular_usuario_a_diretoria('Secretário Acadêmico')
            self.vincular_usuario_a_diretoria('Coordenador de Registros Acadêmicos')

            # IMPORTANDO E ATIVANDO O CURSO
            self.acessar_como_administrador()
            self.importar_dados()
            self.ativar_curso_importado()
            self.vincular_matriz_curso()
            self.cadastrar_convenio('PRONATEC')

            # ACESSANDO A PÁGINA DO ALUNO APÓS A IPORTAÇÃO
            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos(com_boletim=False, com_historico=False, com_atividades_complementares=True)

            # PRIMEIRO PERÍODO DO CURSO (INTEGRALIZAÇÃO DO ALUNO)
            self.acessar_como_administrador()
            self.integralizar_aluno()
            self.atualizar_dados_aluno_integralizado()
            self.realizar_equivalencia_componente_qacademico()

            # ACESSANDO A PÁGINA DO ALUNO APÓS A MIGRAÇÃO
            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos(ja_selecionou_email=True, com_boletim=False)

            # SEGUNDO PERÍODO DO CURSO (GERAÇÃO DE TURMAS E DIÁRIOS)
            self.acessar_como_secretario()
            self.cadastrar_calendario_academico(self.ano_2013, 2, CalendarioAcademico.TIPO_SEMESTRAL)
            self.gerar_turmas_diarios(self.ano_2013, 2, 2)
            self.cadastrar_professor_nao_servidor()
            self.transferir_posse_etapa()
            self.configurar_diario()

            self.acessar_como_professor()
            self.visualizar_locais_horario_aulas_professor()

            # MATRÍCULA DA TURMA DO SEGUNDO PERÍODO
            self.acessar_como_secretario()
            self.efetuar_matricula_turma()
            self.emitir_relatorio_alunos()
            self.imprimir_comprovante_matricula()

            self.efetuar_matricula_em_diario()

            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos()
            self.visualizar_botao_email_academico()
            self.atualizar_endereco()
            self.definir_email_institucional()
            self.visualizar_locais_horario_aulas_aluno()

        with freeze_time('2013-01-02'):
            # LANÇAMENTO DAS NOTAS
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor()
            self.lancar_notas_professor()

            self.acessar_como_aluno()
            self.acompanhar_aulas()

            self.acessar_como_professor()
            self.cadastrar_material_didatico()
            self.vincular_material_didatico()

            self.acessar_como_aluno()
            self.visualizar_materiais_didaticos()

            # JUSTIFICATIVA DE FALTAS

            self.acessar_como_secretario()
            self.abonar_falta()

            self.acessar_como_professor()
            self.imprimir_diario()

            self.acessar_como_aluno()
            self.visualizar_boletim_individual()

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
            # self.excluir_projeto_final()

            # ENTREGA DA ETAPA
            self.acessar_como_professor()
            self.entregar_etapa()

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
