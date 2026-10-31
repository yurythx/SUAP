from decimal import Decimal

from django.apps import apps
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from comum.models import Vinculo
from contratos.models import BaseLegal, Contrato, SubtipoContrato, TipoContrato, TipoFiscal, TipoLicitacao, TipoPublicacao

Permission = apps.get_model('auth', 'permission')
User = apps.get_model('comum', 'user')
PessoaJuridica = apps.get_model('rh', 'pessoajuridica')
Processo = apps.get_model('protocolo', 'processo')


class ContratosTestCase:
    def setUp(self):
        self.servidor_a.get_user().groups.add(Group.objects.get(name='Operador de Contrato'))
        self.servidor_a.get_user().groups.add(Group.objects.get(name='Coordenador de Contrato Sistêmico'))
        self.client.login(username=self.servidor_a.get_user().username, password='123')
        self.processo = Processo.objects.create(
            vinculo_cadastro=self.servidor_a.get_vinculo(), assunto='Assunto Qualquer', tipo=1, setor_origem=self.servidor_a.setor
        )
        with open('contratos/static/contratos/Manual_Contrato_FISCAL.pdf', 'r+b') as f:
            self.pdf_content = f.read()
        self.subtipo = self._cadastrar_subtipo()
        self.base_legal = self._cadastrar_base_legal()
        self.contrato = self._cadastrar_contrato()

    def get_uploaded_file_pdf(self):
        return SimpleUploadedFile('teste.pdf', self.pdf_content, content_type='application/pdf')

    def _cadastrar_subtipo(self):
        url = '/admin/contratos/subtipocontrato/add/'
        response = self.client.get(url)
        assert response.status_code == 200
        data = {'tipo': TipoContrato.objects.get(pk=1).pk, 'descricao': 'Subtipo 1'}
        response = self.client.post(url, data)
        assert SubtipoContrato.objects.count() == 1
        return SubtipoContrato.objects.first()

    def _cadastrar_base_legal(self):
        url = '/admin/contratos/baselegal/add/'
        response = self.client.get(url)
        assert response.status_code == 200
        data = {'titulo': 'Nova base legal 123'}
        response = self.client.post(url, data)
        assert BaseLegal.objects.count() == 1
        return BaseLegal.objects.first()

    def _cadastrar_contrato(self):
        url = '/admin/contratos/contrato/add/'
        response = self.client.get(url)
        assert response.status_code == 200
        data = {
            'tipo': TipoContrato.objects.get(pk=1).pk,
            'subtipo': self.subtipo.pk,
            'numero': '99999/9999',
            'valor': '12.000,00',
            'data_inicio': '01/01/2012',
            'data_fim': '31/12/2012',
            'objeto': 'Contrato para prestacao de servico de limpeza',
            'continuidade': 'CONTINUO',
            'processo': self.processo.pk,
            'campus_gerenciador': self.campus_a_suap.pk,
            'campi': self.campus_a_suap.pk,
            'vinculo_contratado': Vinculo.objects.filter(tipo_relacionamento__model='pessoajuridica').first().pk,
            'qtd_parcelas': 12,
            'tipo_licitacao': TipoLicitacao.objects.get(pk=1).pk,
            'pregao': '00001/2020 (168345)',
            'concluido': False,
            'motivo_conclusao': '',
            'cancelado': False,
            'motivo_cancelamento': '',
            'dh_cancelamento': '01/01/2012',
            'dh_cancelamento_time': '00:00',
            'arquivo_contrato': self.get_uploaded_file_pdf(),
            'mao_obra_exclusiva': True,
            'natureza': 'RECEITA',
            'base_legal': self.base_legal.pk,
        }
        response = self.client.post(url, data)
        assert Contrato.objects.count() == 1
        return Contrato.objects.first()

    def test_cadastrar_subtipo_contrato(self):
        """Cria um SubtipoContrato via admin e verifica persistencia."""
        assert self.subtipo.pk is not None
        assert self.subtipo.descricao == 'Subtipo 1'

    def test_cadastrar_base_legal(self):
        """Cria uma BaseLegal via admin e verifica persistencia."""
        assert self.base_legal.pk is not None
        assert self.base_legal.titulo == 'Nova base legal 123'

    def test_cadastrar_contrato(self):
        """Cria um Contrato via admin com todos os campos obrigatorios."""
        assert self.contrato.pk is not None
        assert self.contrato.numero == '99999/9999'

    def test_adicionar_publicacao(self):
        """Adiciona publicacao a um contrato via view."""
        url = f'/contratos/adicionar_publicacao/{self.contrato.pk}/'
        data = {
            'tipo': TipoPublicacao.objects.get(pk=1).pk,
            'numero': '2012.1-0',
            'data': '01/01/2012',
            'descricao': 'Publicação inicial',
            'arquivo': self.get_uploaded_file_pdf(),
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert self.contrato.get_publicacoes_contrato().count() == 1

    def test_adicionar_fiscal(self):
        """Adiciona fiscal a um contrato via view."""
        url = f'/contratos/adicionar_fiscal/{self.contrato.pk}/'
        data = {
            'tipo': TipoFiscal.objects.get(pk=1).pk,
            'data_nomeacao': '01/01/2012',
            'data_vigencia': '31/12/2012',
            'numero_portaria': '99999/99',
            'fiscais-0-servidor': self.servidor_a.pk,
            'fiscais-0-campus': self.campus_a_suap.pk,
            'fiscais-TOTAL_FORMS': '1',
            'fiscais-INITIAL_FORMS': '0',
            'fiscais-MIN_NUM_FORMS': '0',
            'fiscais-MAX_NUM_FORMS': '1000',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert self.contrato.fiscais.count() == 1

    def test_adicionar_aditivo(self):
        """Adiciona termo aditivo a um contrato via view."""
        url = f'/contratos/adicionar_aditivo/{self.contrato.pk}/'
        data = {
            'numero': '99999/9999',
            'valor': '1.000,00',
            'data_inicio': '01/01/2013',
            'data_fim': '01/02/2013',
            'de_prazo': 'on',
            'de_valor': 'on',
            'arquivo_aditivo': self.get_uploaded_file_pdf(),
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert self.contrato.aditivos.count() == 1

    def test_registrar_ocorrencia(self):
        """Registra ocorrencia em um contrato via view."""
        url = f'/contratos/registrar_ocorrencia/{self.contrato.pk}/'
        data = {'descricao': 'Isso é um teste', 'prazo_resolucao': '01/02/2013'}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert self.contrato.ocorrencias.count() == 1

    def test_gerar_parcelas_com_cronograma(self):
        """Define cronograma e gera parcelas para um contrato."""
        url = f'/contratos/definir_cronograma/{self.contrato.pk}/'
        data = {'numero': '99999/9999', 'nl': '9999'}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        url = f'/contratos/gerar_parcelas/{self.contrato.pk}/'
        parcelas_data = {'form-TOTAL_FORMS': self.contrato.qtd_parcelas, 'form-INITIAL_FORMS': 1}
        meses = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
        valor_parcela = str(self.contrato.valor / Decimal(12)).replace('.', ',')
        for i in range(self.contrato.qtd_parcelas):
            parcelas_data[f'form-{i:d}-data_prevista_inicio'] = f'01/{meses[i]}/2012'
            parcelas_data[f'form-{i:d}-data_prevista_fim'] = f'01/{meses[i]}/2012'
            parcelas_data[f'form-{i:d}-valor_previsto'] = valor_parcela
        response = self.client.post(url, parcelas_data)
        self.assert_no_validation_errors(response)
        assert self.contrato.get_cronograma().parcelas.count() == self.contrato.qtd_parcelas

    def test_efetuar_medicao_sem_perfil_de_fiscal_retorna_form_com_erro(self):
        """Tenta medir parcela sem perfil de fiscal - espera que o form retorne com erros."""
        self.test_gerar_parcelas_com_cronograma()
        valor_parcela = str(self.contrato.valor / Decimal(12)).replace('.', ',')
        url = f'/contratos/efetuar_medicao/{self.contrato.pk}/1/'
        data = {
            'data_inicio': '01/01/2012',
            'data_fim': '01/02/2012',
            'numero_documento': '9999',
            'valor_executado': valor_parcela,
            'ocorrencia': 'Descrição da ocorrência',
            'arquivo_medicao': self.get_uploaded_file_pdf(),
            'processo': self.processo.pk,
        }
        response = self.client.post(url, data)
        assert 'input name="valor_executado" ' not in response.content.decode('utf-8')
