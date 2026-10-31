"""Testes de fluxo da Pesquisa de Egressos.

Cobrem o ciclo do ponto de vista dos dois atores: o gerente de extensão monta e
publica a pesquisa; o egresso é notificado e a responde. Cada teste parte do
estado montado pelas fixtures (`conftest.py`) e exercita um endpoint real.
"""

import datetime

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from edu.models import Aluno
from egressos.models import Categoria, Opcao, Pergunta, Pesquisa, Resposta


@pytest.mark.django_db(databases='__all__')
class TestFluxoEgressos:
    # --- Gerente: montagem e publicação ------------------------------------

    def test_cadastrar_pesquisa(self, gerente, curso_campus, ano_atual):
        """O gerente cadastra uma pesquisa pelo admin, direcionada a uma modalidade."""
        dados = {
            'titulo': 'Pesquisa de Acompanhamento',
            'descricao': 'Descrição da pesquisa',
            'conclusao': [ano_atual.pk],
            'modalidade': curso_campus.modalidade.pk,
        }

        resposta = gerente.post('/admin/egressos/pesquisa/add/', dados, follow=True)

        assert_no_validation_errors(resposta)
        assert Pesquisa.objects.filter(titulo='Pesquisa de Acompanhamento').exists()

    def test_montar_questionario(self, gerente, pesquisa_basica):
        """Sobre uma pesquisa, o gerente cria categoria, pergunta e opção de resposta."""
        resposta = gerente.post(f'/egressos/cadastrar_categoria/{pesquisa_basica.pk}/', {'titulo': 'Categoria 1', 'ordem': 1}, follow=True)
        assert_no_validation_errors(resposta)
        categoria = Categoria.objects.get(pesquisa=pesquisa_basica)

        dados_pergunta = {
            'conteudo': 'Como você avalia seu curso?',
            'categoria': categoria.pk,
            'tipo': Pergunta.OBJETIVA_RESPOSTA_UNICA,
            'preenchimento_obrigatorio': True,
        }
        resposta = gerente.post(f'/egressos/cadastrar_pergunta/{pesquisa_basica.pk}/', dados_pergunta, follow=True)
        assert_no_validation_errors(resposta)
        pergunta = Pergunta.objects.get(categoria=categoria)

        resposta = gerente.post(f'/egressos/cadastrar_opcao/{pergunta.pk}/', {'conteudo': 'Ótimo', 'direcionamento_categoria': []}, follow=True)
        assert_no_validation_errors(resposta)
        assert Opcao.objects.filter(pergunta=pergunta, conteudo='Ótimo').exists()

    def test_publicar_pesquisa_notifica_egresso(self, gerente, pesquisa, egresso, suap_client):
        """Ao publicar, o egresso-alvo passa a ver o convite nos seus avisos."""
        hoje = datetime.date.today()
        # até amanhã: com fim = hoje, um teste que atravessa a meia-noite publica no dia D e lê os avisos em D+1, já vencida
        resposta = gerente.post(
            f'/egressos/publicar_pesquisa/{pesquisa.pk}/',
            {'inicio': hoje.strftime('%d/%m/%Y'), 'fim': (hoje + datetime.timedelta(days=1)).strftime('%d/%m/%Y')},
            follow=True,
        )

        assert_no_validation_errors(resposta)
        pesquisa.refresh_from_db()
        assert pesquisa.publicada

        client = suap_client
        client.login(username=egresso.get_user().username, password='123')
        avisos = client.get('/comum/index/meus_avisos/').content.decode()
        assert 'Responda Pesquisa de Acompanhamento de Ex-Aluno' in avisos

    def test_clonar_pesquisa(self, gerente, pesquisa):
        """Clonar gera uma nova pesquisa a partir da existente."""
        resposta = gerente.post(
            f'/egressos/clonar_pesquisa/{pesquisa.pk}/',
            {'titulo': 'Pesquisa Clone', 'descricao': 'Clone da Pesquisa Teste'},
            follow=True,
        )

        assert_no_validation_errors(resposta)
        assert Pesquisa.objects.filter(titulo='Pesquisa Clone').exists()

    # --- Egresso: resposta -------------------------------------------------

    def test_egresso_atualiza_cadastro(self, egresso, pesquisa_publicada, suap_client):
        """O egresso atualiza seus dados cadastrais antes de responder."""
        client = suap_client
        client.login(username=egresso.get_user().username, password='123')

        resposta = client.post(
            f'/egressos/responder_pesquisa_egressos/atualizacao_cadastral/{pesquisa_publicada.pk}/',
            _dados_atualizacao_cadastral(),
            follow=True,
        )

        assert_no_validation_errors(resposta)
        assert 'Atualização cadastral realizada com sucesso.' in resposta.content.decode()

    def test_egresso_responde_questionario(self, egresso, pesquisa_publicada, suap_client):
        """Respondendo o bloco de perguntas, a resposta do egresso é registrada."""
        client = suap_client
        client.login(username=egresso.get_user().username, password='123')
        client.post(
            f'/egressos/responder_pesquisa_egressos/atualizacao_cadastral/{pesquisa_publicada.pk}/',
            _dados_atualizacao_cadastral(),
        )

        categoria = pesquisa_publicada.categoria_set.first()
        pergunta = categoria.pergunta_set.first()
        opcao = pergunta.opcao_set.first()
        resposta = client.post(
            f'/egressos/responder_pesquisa_egressos/bloco/{pesquisa_publicada.pk}/{categoria.pk}/',
            {f'pergunta_{pergunta.pk}': opcao.pk},
            follow=True,
        )

        assert_no_validation_errors(resposta)
        assert Resposta.objects.filter(aluno=egresso, pergunta=pergunta).exists()


def _dados_atualizacao_cadastral():
    return {
        'estado_civil': 'Solteiro',
        'numero_dependentes': '0',
        'email_pessoal': 'meuemail@provedor.com',
        'logradouro': 'Rua dos Passaros',
        'numero': '1',
        'complemento': '',
        'cep': '59001-001',
        'bairro': 'Lagoa Nova',
        'tipo_zona_residencial': Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES[0][0],
        'telefone_principal': '84 99911-1111',
        'telefone_secundario': '84 99922-2222',
        'facebook': '',
        'instagram': '',
        'twitter': '',
        'linkedin': '',
        'skype': '',
        'logradouro_profissional': '',
        'numero_profissional': '',
        'complemento_profissional': '',
        'cep_profissional': '',
        'bairro_profissional': '',
        'tipo_zona_residencial_profissional': '',
    }
