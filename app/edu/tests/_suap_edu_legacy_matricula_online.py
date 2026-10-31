# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *
from edu.tests._suap_edu_legacy_pos import PosGraduacaoBaseWorkflowTestCase


class MatriculaOnlineBaseWorkflowTestCase(PosGraduacaoBaseWorkflowTestCase):
    CENARIOS = frozenset({'pos', 'matricula_online'})

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        PosGraduacaoBaseWorkflowTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['FormaIngresso'] = self.retornar(FormaIngresso, chaves={'descricao': 'Processo Seletivo'})
        self.initial_data['Matriz'] = self.retornar(Matriz, chaves={'descricao': 'Mestrado'})

    def lancar_aulas_faltas_professor(self, ano=None, componente='A1'):
        if not ano:
            ano = self.ano_2013

        matricula_diario = MatriculaDiario.objects.get(diario__componente_curricular__componente__descricao=componente)
        professor_diario = ProfessorDiario.objects.get(diario__componente_curricular__componente__descricao=componente)

        # verificando a existência do link de acesso à página de visualização de etapa
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
        response = self.client.get(url)
        assert 'Etapa 1' in response.content.decode()
        assert response.status_code == 200
        # acessando a página de visualização da etapa 1, na aba "Aulas e Conteúdo"
        self.client.get(url)
        # verificando a existência do link de acesso à página de cadastro de aula
        url = f'/edu/adicionar_aula_diario/{matricula_diario.diario.pk}/1/'
        # self.assertContains(response, url)
        # acessando a página de cadastro de aula
        self.client.get(url)
        # registrando uma aula para atingir 80% da carga horária necessária (8 de 10)
        assert matricula_diario.diario.get_horas_aulas_etapa_1() == 0
        data = {
            'professor_diario': professor_diario.pk,
            'etapa': '1',
            'quantidade': '8',
            'tipo': 1,
            'data': f'01/01/{ano.ano}',
            'conteudo': 'Aula 01.',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        matricula_diario = MatriculaDiario.objects.get(diario__componente_curricular__componente__descricao=componente)

        assert not matricula_diario.is_carga_horaria_diario_fechada()
        assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Cursando'
        assert matricula_diario.get_situacao_nota()['rotulo'] == 'Cursando'
        assert matricula_diario.get_situacao_diario()['rotulo'] == 'Cursando'
        assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
        assert not matricula_diario.pode_fechar_periodo_letivo()
        assert matricula_diario.is_cursando()
        assert not matricula_diario.realizou_todas_avaliacoes_regulares()
        assert not matricula_diario.realizou_todas_avaliacoes()
        assert not matricula_diario.is_aprovado_sem_prova_final()
        assert not matricula_diario.realizou_avaliacao_final()
        assert not matricula_diario.is_em_prova_final()
        assert not matricula_diario.is_aprovado_em_prova_final()
        assert not matricula_diario.is_aprovado_por_nota()
        assert matricula_diario.is_aprovado_por_frequencia()
        assert not matricula_diario.is_aprovado()
        assert matricula_diario.get_media_disciplina() is None
        assert matricula_diario.get_media_final_disciplina() is None
        assert matricula_diario.get_numero_faltas_primeira_etapa() == 0
        assert matricula_diario.get_percentual_carga_horaria_frequentada() == 100
        # lançando mais uma aula para atingir o percentual mínimo de 90% necessário para fechar o diário
        data = {
            'professor_diario': professor_diario.pk,
            'etapa': '1',
            'quantidade': '2',
            'tipo': 1,
            'data': f'02/01/{ano.ano}',
            'conteudo': 'Aula 02.',
        }
        self.client.post(url, data)
        # verificando algumas condições acerca da carga horária
        temp = Diario.locals.get(pk=matricula_diario.diario.pk)
        assert temp.get_horas_aulas_etapa_1() == 10
        assert temp.get_percentual_carga_horaria_cumprida() == 100
        matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
        assert matricula_diario.is_carga_horaria_diario_fechada()
        assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
        # voltando para a página de listagem de diários
        url = '/edu/meus_diarios/'
        self.client.get(url)
        # acessando a página de visualização de diário na aba "Chamada"
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/?tab=notas'
        response = self.client.get(url)
        # lançando uma falta
        aula_ = matricula_diario.diario.professordiario_set.all()[0].aula_set.all()[0]
        url_ = f'/edu/registrar_chamada_ajax/{matricula_diario.pk}/{aula_.pk}/1/'
        assert 'O salvamento das notas é realizado' in response.content.decode()
        assert response.status_code == 200
        response_ = self.client.get(url_)
        assert '1' in response_.content.decode()
        assert response_.status_code == 200

    def acessar_matricula_online(self, contendo=None, contem=True):
        aluno = self.retornar(Aluno)
        if aluno.curso_campus.modalidade_id in [Modalidade.SUBSEQUENTE, Modalidade.CONCOMITANTE]:
            return

        if not contendo:
            # Está assim porque nas páginas abaixo o aluno é renderizado com |format que exibe o format_user com o nome usual
            contendo = aluno.pessoa_fisica.nome_usual or aluno.pessoa_fisica.nome

        # acessando a matricula online
        url = ''
        if aluno.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_SERIADO:
            url = f'/edu/pedido_matricula_seriado/{aluno.pk}/'
        elif aluno.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
            url = f'/edu/pedido_matricula_credito/{aluno.pk}/'

        response = self.client.get(url, follow=True)
        if contem:
            assert contendo in response.content.decode()
            assert response.status_code == 200
        else:
            assert contendo not in response.content.decode()
        assert response.status_code == 200

    def cadastrar_configuracao_pedido_matricula(self):
        curso = self.retornar(CursoCampus)
        # acessando o admin de configuração de pedido de matrícula
        url = '/admin/edu/configuracaopedidomatricula/'
        response = self.client.get(url)
        assert 'Renovações de Matrícula' in response.content.decode()
        assert response.status_code == 200
        # cadastrar configuração de pedido matrícula
        url = '/admin/edu/configuracaopedidomatricula/add/'
        response = self.client.get(url)
        assert 'Adicionar Renovação de Matrícula' in response.content.decode()
        assert response.status_code == 200
        count = ConfiguracaoPedidoMatricula.objects.all().count()
        data = {
            'descricao': 'Configuração Seriado 2013.2',
            'ano_letivo': self.ano_2013.pk,
            'periodo_letivo': '2',
            'data_inicio': datetime.date.today().strftime('%d/%m/%Y'),
            'data_fim': datetime.date.today().strftime('%d/%m/%Y'),
            'diretorias': [curso.diretoria.pk],
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert ConfiguracaoPedidoMatricula.objects.all().count() == count + 1

        # acessando a configuração de pedido de matrícula
        configuracao_pedido_matricula = self.retornar(ConfiguracaoPedidoMatricula)
        url = f'/edu/configuracao_pedido_matricula/{configuracao_pedido_matricula.id}/'
        response = self.client.get(url)
        assert configuracao_pedido_matricula.descricao in response.content.decode()
        assert response.status_code == 200

        # adicionado o curso a configuração de pedido de matrícula
        count = configuracao_pedido_matricula.cursos.count()
        url = f'/edu/add_curso_configuracao_pedido_matricula/{configuracao_pedido_matricula.id}/'
        data = {'cursos': [curso.pk]}
        response = self.client.post(url, data)
        configuracao_pedido_matricula = self.recarregar(configuracao_pedido_matricula)
        assert count == configuracao_pedido_matricula.cursos.count() - 1

        return configuracao_pedido_matricula

    def acessar_configuracao_pedido_matricula(self, pode_processar=True):
        configuracao_pedido_matricula = self.retornar(ConfiguracaoPedidoMatricula)
        url = f'/edu/configuracao_pedido_matricula/{configuracao_pedido_matricula.pk}/'
        response = self.client.get(url)
        if pode_processar:
            assert 'Processar Pedidos' in response.content.decode()
            assert response.status_code == 200
        else:
            assert 'Processar Pedidos' not in response.content.decode()
        assert response.status_code == 200

    def processar_pedidos_matricula(self):
        configuracao_pedido_matricula = self.retornar(ConfiguracaoPedidoMatricula)
        url = f'/edu/processar_pedidos_matricula/{configuracao_pedido_matricula.pk}/'
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        # self.assertContains(response, u'100%')

        url = '{}?continue=1'.format(response.request['PATH_INFO'])
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        # self.assertContains(response, u'Pedidos de matrícula processados com sucesso.', status_code=200)

        aluno = self.retornar(Aluno)
        matricula_periodo = aluno.get_ultima_matricula_periodo()
        assert PedidoMatricula.objects.filter(pedidomatriculadiario__deferido=True).count() == matricula_periodo.matriculadiario_set.count()

    def validando_diarios_com_horarios(self):
        # definindo horario do diário A1
        self.definindo_horario_diario(dias_semana=[4], descricao_componente='A1')
        # definindo horario do diário B1
        self.definindo_horario_diario(dias_semana=[4], descricao_componente='B1')
        # verificando informações

        aluno = self.retornar(Aluno)
        cod_turma = f'20132.2.0989.{aluno.matriz_id}.1M'
        self.acessar_matricula_online(cod_turma, contem=True)
        self.acessar_matricula_online(' B1 ', contem=True)
        self.acessar_matricula_online(' B2 ', contem=False)
        self.acessar_matricula_online(' A1 ', contem=True)
        # definindo horario do diário B2
        self.definindo_horario_diario(dias_semana=[3, 5], descricao_componente='B2')
        # verificando informações, após definição do horário de B2
        self.acessar_matricula_online(cod_turma, contem=True)
        self.acessar_matricula_online(' B1 ', contem=True)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)

    def validando_pre_correquisitos(self):
        self.vincular_prerequisito(inserir=True, receptor='B1', pre_requisito='A1')
        self.acessar_matricula_online(' B1 ', contem=False)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)
        self.vincular_correquisito(inserir=True, receptor='B2', correquisito='B1')
        self.acessar_matricula_online(' B1 ', contem=False)
        self.acessar_matricula_online(' B2 ', contem=False)
        self.acessar_matricula_online(' A1 ', contem=True)
        self.vincular_correquisito(inserir=False, receptor='B2', correquisito='B1')
        self.acessar_matricula_online(' B1 ', contem=False)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)
        self.vincular_prerequisito(inserir=False, receptor='B1', pre_requisito='A1')
        self.acessar_matricula_online(' B1 ', contem=True)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)

    def validando_inexistencia_diarios(self):
        self.vincular_correquisito(inserir=True, receptor='B2', correquisito='B1')
        diario_componente_b1 = Diario.objects.filter(componente_curricular__componente__descricao='B1').order_by('-id')[0]
        diario_componente_b1.delete()
        self.acessar_matricula_online(' B1 ', contem=False)
        self.acessar_matricula_online(' B2 ', contem=False)
        self.acessar_matricula_online(' A1 ', contem=True)
        diario_componente_b1.save()
        self.definindo_horario_diario(dias_semana=[4], descricao_componente='B1')
        self.acessar_matricula_online(' B1 ', contem=True)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)

    def validando_exibicao_matricula_vinculo(self):
        self.vincular_prerequisito(inserir=True, receptor='B1', pre_requisito='A1')
        self.vincular_correquisito(inserir=True, receptor='B2', correquisito='B1')
        diario_componente_a1 = Diario.objects.filter(componente_curricular__componente__descricao='A1').order_by('-id')[0]
        diario_componente_a1.delete()
        self.acessar_matricula_online('Para manter o vínculo com a instituição confirme clicando no botão abaixo', contem=True)
        diario_componente_a1.save()
        self.definindo_horario_diario(dias_semana=[4], descricao_componente='A1')
        self.acessar_matricula_online(' B1 ', contem=False)
        self.acessar_matricula_online(' B2 ', contem=False)
        self.acessar_matricula_online(' A1 ', contem=True)
        self.vincular_prerequisito(inserir=False, receptor='B1', pre_requisito='A1')
        self.vincular_correquisito(inserir=False, receptor='B2', correquisito='B1')
        self.acessar_matricula_online(' B1 ', contem=True)
        self.acessar_matricula_online(' B2 ', contem=True)
        self.acessar_matricula_online(' A1 ', contem=True)

    def comprovante_pedido_matricula(self, turma=None, disciplinas=None):
        if disciplinas is None:
            disciplinas = []
        pedido_matricula = self.retornar(PedidoMatricula)
        url = f'/edu/comprovante_pedido_matricula/{pedido_matricula.pk}/?html=1'
        response = self.client.get(url)
        if turma:
            assert turma in response.content.decode()
            assert response.status_code == 200
        for disciplina in disciplinas:
            assert disciplina in response.content.decode()
            assert response.status_code == 200

    def acessar_pedidos_matricula(self, conteudo=None):
        url = '/admin/edu/pedidomatriculadiario/'
        response = self.client.get(url)
        if not conteudo:
            conteudo = 'Pedidos de Matrícula'
        assert conteudo in response.content.decode()
        assert response.status_code == 200

    def fluxo_inicial(self, regime):
        # GERAÇÃO DE TURMAS E DIARIOS
        self.vincular_usuario_a_diretoria('Secretário Acadêmico')
        self.vincular_usuario_a_diretoria('Coordenador de Registros Acadêmicos')
        self.acessar_como_secretario()
        self.cadastrar_calendario_academico(tipo=CalendarioAcademico.TIPO_SEMESTRAL)
        self.gerar_turmas_diarios()
        self.cadastrar_professor_nao_servidor()
        self.transferir_posse_etapa()
        self.configurar_diario(diario=self.retornar(Diario, chaves={'componente_curricular__componente__descricao': 'A1'}))
        self.configurar_diario(diario=self.retornar(Diario, chaves={'componente_curricular__componente__descricao': 'A2'}))

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

        self.acessar_como_aluno()
        self.visualizar_dados_pessoais_e_academicos()
        self.visualizar_botao_email_academico()
        self.atualizar_endereco()
        self.definir_email_institucional()
        self.visualizar_locais_horario_aulas_aluno()

        with freeze_time('2013-01-02'):
            # LANÇAMENTO DAS NOTAS
            self.acessar_como_professor()
            self.lancar_aulas_faltas_professor(componente='A1')
            self.lancar_aulas_faltas_professor(componente='A2')
            self.imprimir_diario()

            self.acessar_como_aluno()
            self.acompanhar_aulas()

            self.acessar_como_aluno()
            self.visualizar_boletim_individual()

            # ENTREGA DE ETAPA
            self.acessar_como_professor()
            self.lancar_notas_professor(nota=20, descricao_componente='A1')
            self.lancar_notas_professor(nota=90, descricao_componente='A2')
            self.entregar_etapa()

            self.acessar_como_secretario()
            if regime == EstruturaCurso.TIPO_AVALIACAO_SERIADO:
                self.fechar_periodo(
                    False,
                    SituacaoMatricula.MATRICULADO,
                    SituacaoMatriculaPeriodo.DEPENDENCIA,
                    MatriculaDiario.SITUACAO_APROVADO,
                    componentes_situacoes={'A1': MatriculaDiario.SITUACAO_REPROVADO, 'A2': MatriculaDiario.SITUACAO_APROVADO},
                )
            elif regime == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                self.fechar_periodo(
                    False,
                    SituacaoMatricula.MATRICULADO,
                    SituacaoMatriculaPeriodo.PERIODO_FECHADO,
                    MatriculaDiario.SITUACAO_APROVADO,
                    componentes_situacoes={'A1': MatriculaDiario.SITUACAO_REPROVADO, 'A2': MatriculaDiario.SITUACAO_APROVADO},
                )

            # GERANDO TURMAS 2013.2
            self.cadastrar_calendario_academico(self.ano_2013, 2, CalendarioAcademico.TIPO_SEMESTRAL)
            self.gerar_turmas_diarios(ano=self.ano_2013, periodo=2, periodo_matriz=1)

            if regime == EstruturaCurso.TIPO_AVALIACAO_SERIADO:
                self.gerar_turmas_diarios(ano=self.ano_2013, periodo=2, periodo_matriz=2)
            elif regime == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                self.gerar_turmas_diarios(ano=self.ano_2013, periodo=2, periodo_matriz=2)
                self.gerar_turmas_diarios(ano=self.ano_2013, periodo=2, optativas=True)


MatriculaOnline = MatriculaOnlineBaseWorkflowTestCase
