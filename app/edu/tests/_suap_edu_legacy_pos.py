# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *


class PosGraduacaoBaseWorkflowTestCase(EduTestCase):
    CENARIOS = frozenset({'pos'})

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        EduTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['TipoComponente'] = self.retornar(TipoComponente, chaves={'descricao': 'POS'})
        self.initial_data['NivelEnsino'] = NivelEnsino.objects.get(pk=NivelEnsino.POS_GRADUACAO)
        self.initial_data['TipoAtividadeComplementar'] = self.retornar(TipoAtividadeComplementar, chaves={'descricao': 'Palestra'})
        self.initial_data['LinhaPesquisa'] = self.retornar(LinhaPesquisa, chaves={'descricao': 'Educação'})
        self.initial_data['Matriz'] = self.retornar(Matriz, chaves={'descricao': 'Mestrado em Agricultor Familiar'})
        self.initial_data['Professor'] = self.retornar(Professor)

    def cadastrar_configuracao_atividade_complementar(self, descricao='Padrão'):
        return self.cadastrar(ConfiguracaoAtividadeComplementar, {'descricao': descricao, 'ch_maxima_extensao': 0})

    def efetuar_tansferencia_turma(self):
        turma_origem, turma_destino = self.retornar(Turma, 2)
        matricula_periodo = MatriculaPeriodo.objects.filter(turma=turma_origem)[0]
        # 1º passo do wizard: carregar a página.
        url = f'/edu/transferir_turma/{turma_origem.pk}/{matricula_periodo.pk}/'
        self.client.get(url)

        # 2º passo do wizard: preencher a turma destino.
        data = {'turma_destino': turma_destino.pk}
        self.client.post(url, data)

        data.update({'confirmacao': 'on'})
        self.client.post(url, data)

        matricula_diario = MatriculaDiario.objects.filter(diario__turma=turma_origem)[0]
        assert matricula_diario.situacao == MatriculaDiario.SITUACAO_TRANSFERIDO

    def excluir_turma(self):
        turma = self.retornar(Turma)
        turma.delete()

    def efetuar_matricula_turma(self):
        turma = self.retornar(Turma)
        numero_matriculas_diario_antes = MatriculaDiario.objects.count()
        url = f'/edu/turma/{turma.pk}/?tab=dados_alunos'
        response = self.client.get(url)
        assert 'Adicionar alunos' in response.content.decode()
        assert response.status_code == 200
        url = f'/edu/adicionar_aluno_turma/{turma.pk}/'
        response = self.client.get(url)
        assert 'Adicionar Aluno à Turma' in response.content.decode()
        assert response.status_code == 200
        data = {'matriculas_periodo': [turma.get_alunos_apto_matricula()[0].pk]}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        numero_matriculas_diario_depois = MatriculaDiario.objects.count()
        assert numero_matriculas_diario_depois == numero_matriculas_diario_antes + turma.diario_set.count()

    def efetuar_matricula_em_diario(self):
        aluno = self.retornar(Aluno)
        url = f'/edu/listar_diarios_matricula_aluno/{aluno.get_ultima_matricula_periodo().pk}/'
        response = self.client.get(url)
        assert 'Matricular em Diário' in response.content.decode()
        assert response.status_code == 200
        diretoria = self.retornar(Diretoria)
        data = {'diretoria': diretoria.pk}
        diario = self.retornar(Diario)
        url = f'/edu/matricular_aluno_diario/{aluno.get_ultima_matricula_periodo().pk}/{diario.pk}/'
        response = self.client.get(url, data)
        self.assert_no_validation_errors(response)

    def visualizar_configuracao_atividade_complementar(self):
        configuracao_atividade_complementar = self.retornar(ConfiguracaoAtividadeComplementar)
        url = f'/edu/configuracaoatividadecomplementar/{configuracao_atividade_complementar.pk}/'
        response = self.client.get(url)
        assert 'Configuração da AACC' in response.content.decode()
        assert response.status_code == 200

    def cadastrar_item_configuracao_atividade_complementar(self):
        antes = ItemConfiguracaoAtividadeComplementar.objects.count()
        configuracao_atividade_complementar = self.retornar(ConfiguracaoAtividadeComplementar)
        url = f'/edu/adicionar_item_configuracao_aacc/{configuracao_atividade_complementar.pk}/'
        response = self.client.get(url)
        assert 'Adicionar Atividade Acadêmica' in response.content.decode()
        assert response.status_code == 200
        data = {
            'tipo': self.retornar(TipoAtividadeComplementar).pk,
            'pontuacao_max_periodo': 20,
            'pontuacao_max_curso': 40,
            'fator_conversao': 1.00,
            'percentual_considerar': 100,
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        depois = ItemConfiguracaoAtividadeComplementar.objects.count()
        assert 'Atividade acadêmica cadastrada com sucesso.' in response.content.decode()
        assert response.status_code == 200
        assert depois == antes + 1

    def excluir_item_configuracao_atividade_complementar(self):
        antes = ItemConfiguracaoAtividadeComplementar.objects.count()
        configuracao_atividade_complementar = self.retornar(ConfiguracaoAtividadeComplementar)
        item = ItemConfiguracaoAtividadeComplementar.objects.filter(configuracao=configuracao_atividade_complementar)[0]
        url = f'/comum/excluir/edu/itemconfiguracaoatividadecomplementar/{item.pk}/'
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200
        depois = ItemConfiguracaoAtividadeComplementar.objects.count()
        assert depois == antes - 1

    def vincular_matriz_configuracao_atividade_complementar(self):
        matriz = self.retornar(Aluno).matriz
        matriz.ch_atividades_complementares = 8
        matriz.save()
        configuracao_atividade_complementar = self.retornar(ConfiguracaoAtividadeComplementar)
        antes = configuracao_atividade_complementar.matriz_set.count()
        url = f'/edu/vincular_configuracao_atividade_complementar/{configuracao_atividade_complementar.pk}/'
        response = self.client.get(url)
        assert 'Vincular Matriz' in response.content.decode()
        assert response.status_code == 200
        data = {'matrizes': [matriz.pk]}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Matrizes vinculadas com sucesso.' in response.content.decode()
        assert response.status_code == 200

        url2 = f'/edu/configuracaoatividadecomplementar/{configuracao_atividade_complementar.pk}/?desvincular_matriz={self.retornar(Matriz).pk}'
        response = self.client.get(url2, follow=True)
        assert 'Matriz desvinculada com sucesso.' in response.content.decode()

        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Matrizes vinculadas com sucesso.' in response.content.decode()
        assert response.status_code == 200
        depois = configuracao_atividade_complementar.matriz_set.count()
        assert depois == antes + 1

    def cadastrar_atividade_complementar(self, curricular=True, is_aluno=False):
        antes = AtividadeComplementar.objects.count()
        aluno = self.retornar(Aluno)
        matricula_periodo = aluno.matriculaperiodo_set.all()[0]
        ano_letivo = matricula_periodo.ano_letivo
        periodo_letivo = matricula_periodo.periodo_letivo
        url = f'{aluno.get_absolute_url()}?tab=acc'
        response = self.client.get(url)
        if is_aluno:
            assert 'Informar atividade complementar' in response.content.decode()
            assert response.status_code == 200
            url = '/edu/solicitar_atividade_complementar/'
            response = self.client.get(url)
            assert 'Adicionar solicitação de atividade complementar' in response.content.decode()
            assert response.status_code == 200
        else:
            assert 'Adicionar atividade complementar' in response.content.decode()
            assert response.status_code == 200
            url = f'/edu/cadastrar_atividade_complementar/{aluno.pk}/'
            response = self.client.get(url)
            assert 'Adicionar atividade complementar' in response.content.decode()
            assert response.status_code == 200

        if curricular:
            tipo = TipoAtividadeComplementar.objects.filter(itemconfiguracaoatividadecomplementar__isnull=False)[0]
            data = {
                'vinculacao': AtividadeComplementarForm.VINCULADO_CURSO,
                'aluno': aluno.pk,
                'descricao': 'Participação no congresso',
                'tipo': tipo.pk,
                'ano_letivo': ano_letivo.pk,
                'periodo_letivo': periodo_letivo,
                'data_atividade': '01/07/2014',
                'data_conclusao_atividade': '01/07/2014',
                'carga_horaria': 8,
                'informacoes_complementares': 'Atuou como auxiliar técnico',
                'documento': '',
                'deferida': 'on',
            }
        else:
            tipo = TipoAtividadeComplementar.objects.filter(itemconfiguracaoatividadecomplementar__isnull=True)[0]
            data = {
                'vinculacao': AtividadeComplementarForm.NAO_VINCULADO_CURSO,
                'aluno': aluno.pk,
                'descricao': 'Palestra em congresso',
                'tipo': tipo.pk,
                'ano_letivo': ano_letivo.pk,
                'periodo_letivo': periodo_letivo,
                'data_atividade': '05/08/2014',
                'data_conclusao_atividade': '10/08/2014',
                'carga_horaria': 12,
                'informacoes_complementares': 'Atuou como palestrante',
                'documento': '',
                'deferida': 'on',
            }

        if is_aluno:
            documento = open('edu/fixtures/test_projeto_final.pdf', 'r+b')
            data['documento'] = documento

        response = self.client.post(url, data, follow=True)

        if is_aluno:
            documento.close()
        self.assert_no_validation_errors(response)
        assert '' in response.content.decode()
        assert response.status_code == 200
        depois = AtividadeComplementar.objects.count()
        assert depois == antes + 1

    def excluir_atividade_complementar(self):
        antes = AtividadeComplementar.objects.count()
        atividade_complementar = self.retornar(AtividadeComplementar)
        url = f'/edu/atividadecomplementar_delete/{atividade_complementar.pk}/'
        data = {'senha': '123', 'motivo': 'teste'}
        response = self.client.post(url, data, follow=True)
        assert 'Atividade complementar removida com sucesso' in response.content.decode()
        assert response.status_code == 200
        depois = AtividadeComplementar.objects.count()
        assert depois == antes - 1

    def visualizar_atividade_complementar(self, curricular=True):
        atividade_complementar = self.retornar(AtividadeComplementar)
        url = f'/edu/atividadecomplementar/{atividade_complementar.pk}/'
        response = self.client.get(url)
        if not curricular:
            assert 'Não' in response.content.decode()
            assert response.status_code == 200
        else:
            assert 'Sim' in response.content.decode()
            assert response.status_code == 200

    def avaliar_atividade_complementar(self):
        atividade_complementar = self.retornar(AtividadeComplementar)

        url = f'/edu/atividadecomplementar/{atividade_complementar.pk}/'
        response = self.client.get(url)
        assert 'Aguardando avaliação' in response.content.decode()
        assert response.status_code == 200

        url = f'/edu/atividadecomplementar/{atividade_complementar.pk}/?deferir=1'
        response = self.client.get(url, follow=True)
        assert 'Deferimento realizado com sucesso' in response.content.decode()

        url = f'/edu/atividadecomplementar/{atividade_complementar.pk}/?desfazer=1'
        response = self.client.get(url)
        data = {
            'motivo': 'desfazer deferimento',
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Avaliação da atividade complementar desfeita com sucesso' in response.content.decode()

        url = f'/edu/atividadecomplementar/{atividade_complementar.pk}/?indeferir=1'
        response = self.client.get(url)
        data = {
            'razao_indeferimento': 'indeferir',
            'senha': '123',
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Indeferimento realizado com sucesso' in response.content.decode()

    def cadastrar_projeto_final(self):
        # cadastrando o projeto final
        aluno = self.retornar(Aluno)
        url = f'/edu/adicionar_projeto_final/{aluno.id}/'
        response = self.client.get(url)
        assert 'Adicionar' in response.content.decode()
        assert response.status_code == 200

        projetos_finais_antes = ProjetoFinal.objects.all().count()
        professor = self.retornar(Professor)

        # carregando dados para cadastro de um projeto final
        data = {
            'aluno': aluno.pk,
            'ano_letivo': self.ano_2014.pk,
            'periodo_letivo': '1',
            'titulo': 'Titulo do projeto final.',
            'resumo': 'Resumo do projeto final.',
            'tipo': 'Relatório de Projeto',
            'orientador': professor.vinculo.pk,
            'data_defesa': '01/08/2014',
            'local_defesa': self.retornar(Sala).pk,
            'presidente': professor.pk,
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'TCC / Relatório adicionado com sucesso' in response.content.decode()
        projetos_finais_depois = ProjetoFinal.objects.all().count()
        assert projetos_finais_depois == projetos_finais_antes + 1

        # Verificando link de lançar resultado
        projeto_final = self.retornar(ProjetoFinal)
        url = f'/edu/lancar_resultado_projeto_final/{projeto_final.pk}/'
        response = self.client.get(url)
        assert 'Lançar Resultado' in response.content.decode()
        assert response.status_code == 200

        # realizando o lançamento do resultado
        documento = open('edu/fixtures/test_projeto_final.pdf', 'r+b')
        data = {
            'resultado_data': '01/08/2014',
            'nota': '85',
            'situacao': ProjetoFinal.SITUACAO_APROVADO,
            'tipo_documento': '1',
            'documento_url': 'http://www.google.com',
            'ata': documento,
        }
        response = self.client.post(url, data, follow=True)
        documento.close()
        self.assert_no_validation_errors(response)
        assert 'Resultado registrado com sucesso.' in response.content.decode()

    def emitir_declaracao_participacao_projeto_final(self):
        projeto_final = self.retornar(ProjetoFinal)
        url = f'/edu/declaracao_participacao_projeto_final_pdf/{projeto_final.pk}'

        response = self.client.get(f'{url}/orientador/?html=1')
        assert response.status_code == 200
        conteudo = response.content.decode()
        _, participacao, _ = projeto_final.get_titulo_participante('orientador')
        assert participacao in conteudo
        assert projeto_final.titulo in conteudo

        response = self.client.get(f'{url}/coorientador/', follow=True)
        assert 'Escolha um participante válido.' in response.content.decode()
        response = self.client.get(f'{url}/coorientador/?coorientador=0', follow=True)
        assert 'Coorientador não encontrado para este projeto.' in response.content.decode()

    def excluir_projeto_final(self):
        url = f'/comum/excluir/edu/projetofinal/{1}/'
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200

        # Verificando se a nota no diario foi setada para Nulo
        matricula_diario = self.retornar(MatriculaDiario)
        assert matricula_diario.nota_1 is None

        # apagando o diário referente ao projeto final
        matricula_diario.diario.delete()

    def importar_edital(self):
        # Configurando arquivos de editais
        WebService.objects.get_or_create(
            descricao='WebService1',
            url_editais='file://edu/fixtures/editais.xml',
            url_edital='file://edu/fixtures/edital10.xml',
            url_candidato='file://edu/fixtures/candidato.xml',
        )

        # Importando edital
        count_edital = Edital.objects.count()
        webservice = self.retornar(WebService)
        count_lista = Lista.objects.count()
        count_candidato = Candidato.objects.count()
        count_candidato_vaga = CandidatoVaga.objects.count()
        url = '/processo_seletivo/importar_edital/?test=1'
        data = {'ano': self.ano_2013.pk, 'semestre': 1, 'webservice': webservice.pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        data.update(edital=10)
        response = self.client.post(url, data, follow=True)

        self.assert_no_validation_errors(response)
        assert Edital.objects.count() == count_edital + 1
        assert Lista.objects.count() == count_lista + 2
        assert Candidato.objects.count() == count_candidato + 1
        assert CandidatoVaga.objects.count() == count_candidato_vaga + 1

        # Acessando os editais
        url = '/admin/processo_seletivo/edital/'
        response = self.client.get(url)
        assert 'Mostrando 1' in response.content.decode()

        # Acessando o edital
        edital = self.retornar(Edital)

        url = f'/processo_seletivo/edital/{edital.pk}/'
        response = self.client.get(url)
        assert 'Edital 002/2014' in response.content.decode()

        # Acessando o candidato
        candidato = self.retornar(Candidato)
        url = f'/processo_seletivo/edital/{edital.pk}/?tab=candidatos'
        response = self.client.get(url)
        assert candidato.nome in response.content.decode()

    def definir_formas_ingresso(self):
        edital = Edital.objects.latest('id')
        for lista in edital.lista_set.all():
            forma_ingresso = self.retornar(FormaIngresso)
            url = f'/processo_seletivo/definir_forma_ingresso/{lista.id}/'
            data = {'forma_ingresso': forma_ingresso.pk}
            response = self.client.post(url, data, follow=True)
            assert 'Forma de ingresso definida com sucesso' in response.content.decode()
            assert response.status_code == 200

    def realizar_convocacao(self):
        oferta_vaga_curso = self.retornar(OfertaVagaCurso)
        count1 = CandidatoVaga.objects.filter(convocacao__isnull=True).count()
        url = '/processo_seletivo/edital/{}/?nova_chamada={}'.format(Edital.objects.latest('id').id, oferta_vaga_curso.pk)
        response = self.client.post(url, {}, follow=True)
        self.assert_no_validation_errors(response)
        count2 = CandidatoVaga.objects.filter(convocacao__isnull=True).count()
        assert count1 != count2

    def identificar_canditado(self):
        # Primeiro Passo do Wizard
        url = '/edu/identificar_candidato/'
        data = {'ano': self.ano_2013.pk, 'semestre': 1}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        # Segundo Passo do Wizard
        data.update(edital=10)
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)

        # Terceiro Passo do Wizard
        data.update(cpf='047.704.024-14')
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)

        # Quarto Passo do Wizard
        data.update(candidato_vaga=CandidatoVaga.objects.filter(candidato__cpf='047.704.024-14')[0])
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)

    def vincular_prerequisito(self, inserir, receptor, pre_requisito):
        for descricao in ('PÓS-GRADUAÇAO SERIADO', 'PÓS-GRADUAÇAO CRÉDITO'):
            componente_curricular_receptor = ComponenteCurricular.objects.get(componente__descricao=receptor, matriz__estrutura__descricao=descricao)
            componente_curricular_prerequisito = ComponenteCurricular.objects.get(
                componente__descricao=pre_requisito, matriz__estrutura__descricao=descricao
            )

            if inserir:
                componente_curricular_receptor.pre_requisitos.add(componente_curricular_prerequisito)
            else:
                componente_curricular_receptor.pre_requisitos.remove(componente_curricular_prerequisito)

    def vincular_correquisito(self, inserir, receptor, correquisito):
        for descricao in ('PÓS-GRADUAÇAO SERIADO', 'PÓS-GRADUAÇAO CRÉDITO'):
            componente_curricular_receptor = ComponenteCurricular.objects.get(componente__descricao=receptor, matriz__estrutura__descricao=descricao)
            componente_curricular_correquisito = ComponenteCurricular.objects.get(
                componente__descricao=correquisito, matriz__estrutura__descricao=descricao
            )

            if inserir:
                componente_curricular_receptor.co_requisitos.add(componente_curricular_correquisito)
            else:
                componente_curricular_receptor.co_requisitos.remove(componente_curricular_correquisito)


PosGraduacaoTestCase = PosGraduacaoBaseWorkflowTestCase
