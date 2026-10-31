# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *


class GraduacaoWorkflowTestCase(EduTestCase):
    CENARIOS = frozenset({'graduacao'})

    def test_fluxo_graduacao_enade_completo(self):
        curso = self.retornar(CursoCampus, chaves={'descricao': 'Ciência da educação'})

        self.acessar_como_secretario()
        self.efetuar_matricula_institucional(cpf='386.111.790-80', curso=curso)

        # CONVOCAÇÃO DO ENADE
        self.acessar_como_regulador_avaliador()
        self.cadastrar_justificativa_dispensa()

        self.cadastrar_convocacao_enade()
        self.editar_criterios_convocacao_enade()
        self.processar_convocados_enade()

        self.acessar_como_operador_enade()
        self.lancar_situacao_enade_aluno()

    def cadastrar_justificativa_dispensa(self):
        count = JustificativaDispensaENADE.objects.count()
        url = '/admin/edu/justificativadispensaenade/add/'
        data = {'descricao': 'Estudante dispensado conforme Art. 6º, § 2 da Portaria Normativa Nº8 de 14 março de 2014.'}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert JustificativaDispensaENADE.objects.count() == count + 1

    def cadastrar_convocacao_enade(self, ano_letivo=None):
        area_curso_formacao_superior = self.retornar(AreaCursoFormacaoSuperior, chaves={'area_detalhada': 'Ciência da educação'})

        count_convocacoesenade = ConvocacaoENADE.objects.count()
        url = '/admin/edu/convocacaoenade/add/'
        data_limite = somar_dias(datetime.date.today(), 2)
        data = {
            'descricao': 'Teste de convocação 1234',
            'tipo_convocacao': '1',
            'ano_letivo': self.ano_2013.pk,
            'situacoes_convocadas': [SituacaoMatricula.MATRICULADO],
            'modalidades_convocadas': [Modalidade.LICENCIATURA],
            'areas_cursos_formacao_superior': [area_curso_formacao_superior.pk],
            'data_inscricao': data_limite.strftime('%d/%m/%Y'),
            'data_inscricao_ingressantes': data_limite.strftime('%d/%m/%Y'),
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert ConvocacaoENADE.objects.count() == count_convocacoesenade + 1

    def editar_criterios_convocacao_enade(self):
        convocacao = self.retornar(ConvocacaoENADE)
        modalidade_convocacao = convocacao.modalidadeconvocacaoenade_set.first()
        url = f'/edu/editar_modalidadeconvocacaoenade/{modalidade_convocacao.pk}/'
        data_limite = somar_dias(datetime.date.today(), 2)
        data_prova = somar_dias(data_limite, 2)
        data = {
            'percentual_minimo_ingressantes': 0,
            'percentual_maximo_ingressantes': 20,
            'percentual_minimo_concluintes': 80,
            'percentual_maximo_concluintes': 100,
            'data_limite_conclusao': data_limite.strftime('%d/%m/%Y'),
            'data_limite_integralizacao_concluinte': data_limite.strftime('%d/%m/%Y'),
            'data_prova': data_prova.strftime('%d/%m/%Y'),
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Operação realizada com sucesso.' in response.content.decode()
        assert response.status_code == 200

    def processar_convocados_enade(self):
        convocacao_enade = self.retornar(ConvocacaoENADE)
        url = f'/edu/atualizar_lista_convocados_enade/{convocacao_enade.pk}/?curso_campus='
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)

    def lancar_situacao_enade_aluno(self):
        convocacao_enade = self.retornar(ConvocacaoENADE)
        registro = convocacao_enade.registroconvocacaoenade_set.first()
        url = f'/edu/lancar_situacao_enade/{registro.pk}/'
        data = {'situacao': RegistroConvocacaoENADE.SITUACAO_PRESENTE}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
