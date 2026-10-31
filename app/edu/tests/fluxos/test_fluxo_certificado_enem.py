# ruff: noqa: F403,F405
from edu.tests.test_suap_edu_legacy_base import *


class CertificadoEnemWorkflowTestCase(EduTestCase):
    # Fluxo não usa nenhum curso da carga_inicial (só Modalidade/livro/processo próprios).
    CENARIOS = frozenset()

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        EduTestCase._auto_setup.__wrapped__(self, atores_edu)

        self.servidor_a.get_user().groups.add(Group.objects.get(name='Administrador Acadêmico'))

        self.ano_2013 = Ano.objects.get_or_create(ano=2013)[0]
        self.ano_2014 = Ano.objects.get_or_create(ano=2014)[0]

        # Criando o municipio
        Municipio.objects.get_or_create(identificacao='NATAL-RN')

        uo = self.setor_re_suap.uo
        # Criando o livro
        data = {
            'descricao': ConfiguracaoLivro.NOME_LIVRO_ENEM,
            'uo': uo,
            'numero_livro': 1,
            'folhas_por_livro': 1,
            'numero_folha': 1,
            'numero_registro': 1,
        }
        configuracao_livro = ConfiguracaoLivro.objects.get_or_create(**data)[0]
        configuracao_livro.modalidades.add(self.retornar(Modalidade))

        # Criando o processo para a solicitação do certificado via Processo
        self.processo_a = Processo(
            vinculo_cadastro=self.servidor_b.get_vinculo(), assunto='Assunto Qualquer', tipo=1, setor_origem=self.servidor_b.setor
        )
        self.processo_a.save()

    def test_fluxo_certificado_enem_completo(self):
        self.acessar_como_administrador()

        # Cadastrando a configuração de certificação
        url = '/admin/edu/configuracaocertificadoenem/add/'
        response = self.client.get(url)
        arquivo = open('edu/fixtures/test_certificacao_enem.xlsx', 'r+b')
        data = {
            'ano': self.ano_2014.pk,
            'data_primeira_prova': '08/11/2014',
            'pontuacao_necessaria_areas_conhecimento': '450',
            'pontuacao_necessaria_redacao': '500',
            'responsaveis_vinculos': self.servidor_b.get_vinculo().pk,
            'planilha_inep': arquivo,
            'uo_planilha': self.setor_a0_suap.uo.id,
            'numero_portaria': 'Portaria XYZ',
        }
        response = self.client.post(url, data)
        arquivo.close()
        self.assert_no_validation_errors(response)
        configuracao_certificacao = self.retornar(ConfiguracaoCertificadoENEM)
        assert configuracao_certificacao.registroalunoinep_set.count() == 1

        # Acessando as configurações para Certificação ENEM
        url = '/admin/edu/configuracaocertificadoenem/'
        response = self.client.get(url)
        assert configuracao_certificacao.numero_portaria in response.content.decode()

        # Acessando a configuração
        url = f'/edu/configuracao_certificacao_enem/{configuracao_certificacao.id}/'
        response = self.client.get(url)
        assert self.servidor_b.pessoa_fisica.nome in response.content.decode()

        # Solicitando um Certificado - Candidato
        self.logout()
        url = '/edu/solicitar_certificado_enem/'
        response = self.client.get(url)
        assert 'Solicitar Certificado ENEM' in response.content.decode()

        arquivo_frente = open('edu/static/edu/img/logo_if.jpg', 'r+b')
        arquivo_verso = open('edu/static/edu/img/brazao_republica.jpg', 'r+b')
        data = {
            'configuracao_certificado_enem': configuracao_certificacao.pk,
            'tipo_certificado': 2,
            'nome': 'Fulano da Silva',
            'cpf': '243.887.408-29',
            'email': 'a@a.com',
            'confirmacao_email': 'a@a.com',
            'telefone': '(84) 3232-3232',
            'documento_identidade_frente': arquivo_frente,
            'documento_identidade_verso': arquivo_verso,
        }
        response = self.client.post(url, data)
        arquivo_frente.close()
        arquivo_verso.close()
        self.assert_no_validation_errors(response)
        assert SolicitacaoCertificadoENEM.objects.count() == 1
        solicitacao_certificado = self.retornar(SolicitacaoCertificadoENEM)

        # Atendendo a Solicitação
        self.acessar_como_administrador()
        url = f'/edu/atender_solicitacao_certificado_enem/{solicitacao_certificado.pk}/'
        response = self.client.get(url, follow=True)
        assert 'Registro de emissão de Certificado ENEM cadastrado com sucesso.' in response.content.decode()
        assert RegistroEmissaoCertificadoENEM.objects.count() == 1
        registro_emissao = self.retornar(RegistroEmissaoCertificadoENEM)

        # Acessando as solicitações de certificação
        url = '/admin/edu/solicitacaocertificadoenem/'
        response = self.client.get(url)
        assert 'Mostrando 1' in response.content.decode()

        # Acessando a solicitação de certificação
        url = f'/edu/solicitacao_certificado_enem/{solicitacao_certificado.id}/'
        response = self.client.get(url)
        assert solicitacao_certificado.nome in response.content.decode()

        # Acessando os registros de emissão de certificado
        url = '/admin/edu/registroemissaocertificadoenem/'
        response = self.client.get(url)
        assert 'Mostrando 1' in response.content.decode()

        # Acessando a solicitação de certificação
        url = f'/edu/registroemissaocertificadoenem/{registro_emissao.id}/'
        response = self.client.get(url)
        assert solicitacao_certificado.nome in response.content.decode()

        # Solicitando um Certificado - Administrador
        url = '/admin/edu/solicitacaocertificadoenem/add/'
        response = self.client.get(url)

        data = {
            'configuracao_certificado_enem': configuracao_certificacao.pk,
            'uo': self.setor_a0_suap.uo_id,
            'tipo_certificado': 2,
            'processo': self.processo_a.pk,
            'nome': 'Beltrano da Silva',
            'nome_mae': 'Beltrana da Silva',
            'numero_rg': '1234567',
            'cpf': '478.699.793-50',
            'data_nascimento': '01/01/1989',
            'email': 'b@b.com',
            'telefone': '(84) 3232-3232',
            'numero_inscricao': '0987654321',
            'nota_ch': '400.10',
            'nota_cn': '500.40',
            'nota_lc': '600.30',
            'nota_mt': '300.60',
            'nota_redacao': '700.90',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert SolicitacaoCertificadoENEM.objects.count() == 2
        solicitacao_certificado = self.retornar(SolicitacaoCertificadoENEM)

        # Rejeitando a Solicitação
        url = f'/edu/rejeitar_solicitacao_certificado_enem/{solicitacao_certificado.pk}/'
        response = self.client.get(url, follow=True)
        data = {'razao_indeferimento': 'Justiticativa de teste.'}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Solicitação rejeitada com sucesso.' in response.content.decode()
