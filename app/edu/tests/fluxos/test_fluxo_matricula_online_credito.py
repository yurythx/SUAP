# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *
from edu.tests._suap_edu_legacy_matricula_online import MatriculaOnlineBaseWorkflowTestCase


class MatriculaOnlineCreditoWorkflowTestCase(MatriculaOnlineBaseWorkflowTestCase):
    QTD_ABAIXO_MINIMA = 1
    QTD_MINIMA_DISCIPLINAS = 2
    QTD_MAXIMA_DISCIPLINAS = 3
    CHOQUE_HORARIO = 4

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        MatriculaOnlineBaseWorkflowTestCase._auto_setup.__wrapped__(self, atores_edu)
        self.initial_data['CursoCampus'] = self.retornar(CursoCampus, chaves={'descricao': 'Mestrado Crédito'})
        self.initial_data['MatrizCurso'] = self.retornar(
            MatrizCurso, chaves={'matriz__descricao': 'Mestrado', 'curso_campus__descricao': 'Mestrado Crédito'}
        )

    def salvar_pedido_matricula(self, descricao_componentes=None, validacao=None):
        if descricao_componentes is None:
            descricao_componentes = []
        aluno = self.retornar(Aluno)
        estrutura = aluno.matriz.estrutura
        data = {}

        if validacao:
            # alterando estrutura para validações
            if validacao == self.QTD_ABAIXO_MINIMA:
                estrutura.qtd_minima_disciplinas = 4
            elif validacao == self.QTD_MINIMA_DISCIPLINAS:
                estrutura.qtd_minima_disciplinas = 2
                descricao_componentes.remove('A1')
            elif validacao == self.QTD_MAXIMA_DISCIPLINAS:
                estrutura.numero_disciplinas_superior_periodo = 1
            elif validacao == self.CHOQUE_HORARIO:
                # forcando choque de horário
                self.definindo_horario_diario(dias_semana=[6], descricao_componente='B1')
                self.definindo_horario_diario(dias_semana=[6], descricao_componente='B2')
            estrutura.save()

        # diários selecionados
        for descricao_componente in descricao_componentes:
            diario = Diario.objects.filter(componente_curricular__componente__descricao=descricao_componente).order_by('-id')[0]
            chave_diario = f'diarios_{diario.componente_curricular.componente.pk}'
            data.update({chave_diario: diario.pk})

        # salvar pedido de matrícula
        count = PedidoMatricula.objects.all().count()
        url = f'/edu/pedido_matricula_credito/{aluno.pk}/'
        response = self.client.post(url, data)

        if validacao:
            if validacao == self.QTD_ABAIXO_MINIMA:
                assert (
                    'O seu curso requer que você se matricule em todas as disciplinas obrigatórias e optativas exibidas.' in response.content.decode()
                )
                assert response.status_code == 200
            elif validacao == self.QTD_MINIMA_DISCIPLINAS:
                assert (
                    f'Escolha, no mínimo, {estrutura.qtd_minima_disciplinas} disciplina(s) obrigatória(s) e/ou optativa(s) para cursar no próximo período letivo.'
                    in response.content.decode()
                )
                assert response.status_code == 200
            elif validacao == self.QTD_MAXIMA_DISCIPLINAS:
                assert 'Não é permitido se matricular em mais de ' in response.content.decode()
                assert response.status_code == 200
            elif validacao == self.CHOQUE_HORARIO:
                assert 'Seu pedido não pôde ser salvo, pois há conflitos de horários entre as seguintes disciplinas' in response.content.decode()
                assert response.status_code == 200
                HorarioAulaDiario.objects.filter(dia_semana=6).delete()

            estrutura.qtd_minima_disciplinas = 1
            estrutura.numero_disciplinas_superior_periodo = 1
            estrutura.save()
        else:
            self.assert_no_validation_errors(response)
            assert PedidoMatricula.objects.all().count() == count + 1

    def test_fluxo_matricula_online_credito_completo(self):
        # alterando codigo do curso para utilização do edital já existente
        CursoCampus.objects.filter(codigo='0989').update(codigo='1010', codigo_academico=None)
        CursoCampus.objects.filter(codigo='8888').update(codigo='0989', codigo_academico='0989')

        with freeze_time('2013-01-01'):
            # MATRICULA ONLINE CRÉDITO
            self.fluxo_inicial(EstruturaCurso.TIPO_AVALIACAO_CREDITO)

            # CONFIGURAÇÃO DE PEDIDO DE MATRíCULA

            # testando acesso a matricula online sem existir um período de matrícula
            self.acessar_matricula_online('Não existe um período de renovação de matrícula ativa para o seu curso.', contem=True)

            # cadastrando configuracao
            self.cadastrar_configuracao_pedido_matricula()

            # acessando a matricula online
            self.acessar_matricula_online()

            # TODO
            # eletivas

            # Validando exibição de diários mediante a definição de horários
            self.validando_diarios_com_horarios()

            # validando pre e correquisitos
            self.validando_pre_correquisitos()

            # validando inexistência de diários
            self.validando_inexistencia_diarios()

            # validando matrícula vínculo
            self.validando_exibicao_matricula_vinculo()

            # validando quantidade de diários abaixo da qtd mínima de disciplinas da estrutura
            # self.salvar_pedido_matricula(['A1'], validacao=self.QTD_ABAIXO_MINIMA) TODO

            self.acessar_como_aluno()

            # validando escolha da qtd mínima de disciplinas, quantidade de diários acima da qtd mínima de disciplinas da estrutura
            self.salvar_pedido_matricula(['A1', 'B1'], validacao=self.QTD_MINIMA_DISCIPLINAS)

            # validando escolha da qtd máxima de disciplinas
            self.salvar_pedido_matricula(['A1', 'B1', 'B2', 'OP1'], validacao=self.QTD_MAXIMA_DISCIPLINAS)

            self.acessar_como_secretario()

            # validando choque de horário
            self.salvar_pedido_matricula(['B1', 'B2'], validacao=self.CHOQUE_HORARIO)

            self.acessar_como_aluno()

            # validando exibição dos Horários das Disciplinas Solicitadas
            self.acessar_matricula_online('Horários das Disciplinas Solicitadas', contem=False)

            # salvando o pedido de matrícula
            self.salvar_pedido_matricula(['A1', 'B2'])

            # validando exibição dos Horários das Disciplinas Solicitadas
            self.acessar_matricula_online('Horários das Disciplinas Solicitadas', contem=True)

            # validando se o link do comprovante está disponível
            self.acessar_matricula_online('Imprimir Comprovante', contem=True)

            # comprovante de pedido de matrícula
            self.comprovante_pedido_matricula(disciplinas=['A1', 'B2'])

            self.acessar_como_secretario()

            # acessando a configuracao e verificando disponibilidade de processar
            self.acessar_configuracao_pedido_matricula(pode_processar=False)

        with freeze_time('2013-01-02'):
            self.acessar_configuracao_pedido_matricula(pode_processar=True)

            # TODO
            # matrículas vínculos
            # segunda chamada

            # processando
            self.processar_pedidos_matricula()

            # acessando pedidos de matrícula
            self.acessar_como_administrador()
            self.acessar_pedidos_matricula(conteudo='A1')

            self.acessar_como_aluno()
            self.visualizar_dados_pessoais_e_academicos(ja_selecionou_email=True, com_boletim=False, com_procedimento_academico=True)
