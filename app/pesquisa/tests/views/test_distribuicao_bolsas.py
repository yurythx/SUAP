"""Escopo da distribuição de bolsas: campus do Coordenador de Pesquisa e ids de participação do POST (#17556).

O Coordenador de Pesquisa é papel de campus: só o Diretor de Pesquisa vê os campi todos. E as
telas que concedem bolsa só podem gravar nas participações que exibem — os projetos do
edital/campus em distribuição —, não em qualquer id que chegue no POST.
"""

import pytest

from pesquisa.models import Participacao, Projeto
from pesquisa.tests.conftest import _login
from rh.models import UnidadeOrganizacional


def _bolsista_aluno(projeto: Projeto) -> Participacao:
    return Participacao.objects.get(projeto=projeto, vinculo='Bolsista', vinculo_pessoa__tipo_relacionamento__model='aluno')


def _participacao_de_outro_projeto(projeto: Projeto) -> Participacao:
    """Bolsista sem bolsa num projeto fora da distribuição (não pré-aprovado), cópia do projeto dado.

    ``bulk_create`` e não ``save()``: o ``Projeto.save`` cria o coordenador a partir do usuário
    da thread e lê atributos que só o form preenche — aqui só interessa uma linha fora do conjunto.
    """
    outro = Projeto.objects.get(pk=projeto.pk)
    outro.pk = None
    outro.titulo = 'Projeto fora da distribuição'
    outro.pre_aprovado = False
    Projeto.objects.bulk_create([outro])
    alheia = _bolsista_aluno(projeto)
    alheia.pk = None
    alheia.projeto = outro
    alheia.bolsa_concedida = False
    Participacao.objects.bulk_create([alheia])
    return alheia


@pytest.mark.django_db(databases='__all__')
class TestDistribuicaoBolsas:
    def test_coordenador_de_pesquisa_so_aprova_lista_de_espera_do_proprio_campus(self, client, usuarios, edital, projeto_pre_selecionado):
        campus = usuarios.coordenador.setor.uo
        outro_campus: UnidadeOrganizacional = usuarios.outro_campus
        _login(client, usuarios.pre_avaliador)

        assert client.get(f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{campus.pk}/').status_code == 200
        assert client.get(f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{outro_campus.pk}/').status_code == 403
        assert client.post(f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{outro_campus.pk}/', {'situacao': []}).status_code == 403

        lista = client.get(f'/pesquisa/projetos_lista_espera/{edital.pk}/').content.decode()
        assert f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{campus.pk}/' in lista
        assert f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{outro_campus.pk}/' not in lista

    def test_aprovar_lista_de_espera_ignora_participacao_fora_da_lista(self, client, usuarios, edital, projeto_pre_selecionado):
        projeto = projeto_pre_selecionado
        campus = usuarios.coordenador.setor.uo
        alheia = _participacao_de_outro_projeto(projeto)
        bolsista = _bolsista_aluno(projeto)
        _login(client, usuarios.gerente)

        resposta = client.post(
            f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{campus.pk}/',
            {'situacao': [projeto.pk], 'participacoes_ic': [bolsista.pk, alheia.pk]},
        )

        assert resposta.status_code == 302
        projeto.refresh_from_db()
        assert projeto.aprovado
        assert Participacao.objects.get(pk=bolsista.pk).bolsa_concedida
        assert not Participacao.objects.get(pk=alheia.pk).bolsa_concedida

    def test_aprovar_lista_de_espera_vazia_nao_quebra(self, client, usuarios, edital, projeto_aprovado):
        """Lista de espera vazia: a tela não oferece "Salvar" e o POST cai na mensagem, não em 500 (#17572)."""
        url = f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{usuarios.coordenador.setor.uo.pk}/'
        _login(client, usuarios.gerente)

        tela = client.get(url)
        assert tela.status_code == 200
        assert 'value="Salvar"' not in tela.content.decode()

        # O navegador sempre manda o token; sem nenhum campo o request.POST seria vazio e cairia no GET.
        resposta = client.post(url, {'csrfmiddlewaretoken': 'token'}, follow=True)
        assert resposta.redirect_chain == [(url, 302)]
        assert 'Nenhum projeto foi selecionado para aprovação.' in resposta.content.decode()

    def test_aprovar_lista_de_espera_de_campus_sem_oferta_de_bolsa(self, client, usuarios, edital, projeto_pre_selecionado):
        """Campus sem ``BolsaDisponivel`` com projeto pré-aprovado: a tela abre com saldo zero (#17572)."""
        campus = usuarios.coordenador.setor.uo
        edital.bolsadisponivel_set.filter(uo=campus).delete()
        _login(client, usuarios.gerente)

        assert client.get(f'/pesquisa/aprovar_projetos_com_bolsa/{edital.pk}/{campus.pk}/').status_code == 200

    def test_gerenciar_bolsas_ignora_participacao_fora_do_edital(self, client, usuarios, edital, projeto_pre_selecionado):
        projeto = projeto_pre_selecionado
        campus = usuarios.coordenador.setor.uo
        alheia = _participacao_de_outro_projeto(projeto)
        bolsista = _bolsista_aluno(projeto)
        _login(client, usuarios.gerente)

        resposta = client.post(
            f'/pesquisa/gerenciar_bolsas/{edital.pk}/{campus.pk}/',
            {'situacao': [projeto.pk], 'participacoes_ic': [bolsista.pk, alheia.pk]},
        )

        assert resposta.status_code == 302
        assert Participacao.objects.get(pk=bolsista.pk).bolsa_concedida
        assert not Participacao.objects.get(pk=alheia.pk).bolsa_concedida
