# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *
from edu.tests._suap_edu_legacy_matricula_online import MatriculaOnlineBaseWorkflowTestCase


class MatriculaOnlineSeriadoWorkflowTestCase(MatriculaOnlineBaseWorkflowTestCase):
    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        MatriculaOnlineBaseWorkflowTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['CursoCampus'] = self.retornar(CursoCampus, chaves={'descricao': 'Mestrado Seriado'})
        self.initial_data['MatrizCurso'] = self.retornar(
            MatrizCurso, chaves={'matriz__descricao': 'Mestrado', 'curso_campus__descricao': 'Mestrado Seriado'}
        )

    def salvar_pedido_matricula(self, codigo_turma_selecionada=None, descricao_componentes_dependencia_selecionados=None, choque_horario=False):
        if descricao_componentes_dependencia_selecionados is None:
            descricao_componentes_dependencia_selecionados = []
        aluno = self.retornar(Aluno)
        data = {}

        # turma selecionada
        if codigo_turma_selecionada:
            turma = Turma.objects.get(codigo=codigo_turma_selecionada)
            data.update({'turma': turma.pk})

        # diários da dependências selecionadas
        for descricao_componente in descricao_componentes_dependencia_selecionados:
            diario = Diario.objects.filter(componente_curricular__componente__descricao=descricao_componente).order_by('-id')[0]
            chave_diario = f'diarios_{diario.componente_curricular.componente.pk}'
            data.update({chave_diario: diario.pk})

        if choque_horario:
            self.definindo_horario_diario(dias_semana=[6], descricao_componente='B1')
            self.definindo_horario_diario(dias_semana=[6], descricao_componente='B2')

        # salvar pedido de matrícula
        count = PedidoMatricula.objects.all().count()
        url = f'/edu/pedido_matricula_seriado/{aluno.pk}/'
        response = self.client.post(url, data)

        if not codigo_turma_selecionada:
            assert 'Você deve selecionar uma turma.' in response.content.decode()
            assert response.status_code == 200

        if not descricao_componentes_dependencia_selecionados:
            assert 'Escolha uma turma para a disciplina em dependência' in response.content.decode()
            assert response.status_code == 200

        if choque_horario:
            assert 'Seu pedido não pôde ser salvo, pois há conflitos de horários entre as seguintes disciplinas' in response.content.decode()
            assert response.status_code == 200
            HorarioAulaDiario.objects.filter(dia_semana=6).delete()

        if codigo_turma_selecionada and descricao_componentes_dependencia_selecionados and not choque_horario:
            self.assert_no_validation_errors(response)
            assert PedidoMatricula.objects.all().count() == count + 1

    def test_fluxo_matricula_online_seriado_completo(self):
        # alterando codigo do curso para utilização do edital já existente
        CursoCampus.objects.filter(codigo='0989').update(codigo='1010', codigo_academico=None)
        CursoCampus.objects.filter(codigo='9999').update(codigo='0989', codigo_academico='0989')

        with freeze_time('2013-01-01'):
            # MATRICULA ONLINE SERIADO
            self.fluxo_inicial(EstruturaCurso.TIPO_AVALIACAO_SERIADO)

            # CONFIGURAÇÃO DE PEDIDO DE MATRíCULA

            # testando acesso a matricula online sem existir um período de matrícula
            self.acessar_matricula_online('Não existe um período de renovação de matrícula ativa para o seu curso.', contem=True)

            # cadastrando configuracao
            self.cadastrar_configuracao_pedido_matricula()

            # TODO
            # testar cadastro de uma configuração, para um curso, com datas coincidentes
            # testar alteração com pedidos já feitos
            # testar exclusão com não processados
            # testar exclusão com processadas

            # acessando a matricula online
            self.acessar_matricula_online()

            # Validando exibição de diários mediante a definição de horários
            self.validando_diarios_com_horarios()

            # validando pre e correquisitos
            self.validando_pre_correquisitos()

            # validando inexistência de diários
            self.validando_inexistencia_diarios()

            # validando matrícula vínculo
            self.validando_exibicao_matricula_vinculo()

            # validando escolha da turma
            self.salvar_pedido_matricula(descricao_componentes_dependencia_selecionados=['A1'])

            aluno = self.retornar(Aluno)
            cod_turma = f'20132.2.0989.{aluno.matriz_id}.1M'

            # validando escolha dos diários da disciplina em dependência
            self.salvar_pedido_matricula(codigo_turma_selecionada=cod_turma)

            # validando choque de horário
            self.salvar_pedido_matricula(cod_turma, ['A1'], choque_horario=True)

            # validando exibição dos Horários das Disciplinas Solicitadas
            self.acessar_matricula_online('Horários das Disciplinas Solicitadas', contem=False)

            # salvando o pedido de matrícula
            self.salvar_pedido_matricula(cod_turma, ['A1'])

            # validando exibição dos Horários das Disciplinas Solicitadas
            self.acessar_matricula_online('Horários das Disciplinas Solicitadas', contem=True)

            # validando se o link do comprovante está disponível
            self.acessar_matricula_online('Imprimir Comprovante', contem=True)

            # comprovante de pedido de matrícula
            self.comprovante_pedido_matricula(turma=cod_turma, disciplinas=['A1', 'B1', 'B2'])

            # acessando a configuracao e verificando disponibilidade de processar
            self.acessar_configuracao_pedido_matricula(pode_processar=False)

        with freeze_time('2013-01-02'):
            self.acessar_configuracao_pedido_matricula(pode_processar=True)

            # TODO
            # mudança de turma
            # matrículas vínculos
            # dependências
            # segunda chamada

            # processando
            self.processar_pedidos_matricula()

            # acessando pedidos de matrícula
            self.acessar_como_administrador()
            self.acessar_pedidos_matricula(conteudo=cod_turma)

            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos(ja_selecionou_email=True, com_procedimento_academico=True)
