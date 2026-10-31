import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from pesquisa.models import Edital, Projeto, ProjetoCancelado, RegistroConclusaoProjeto


@pytest.fixture
def dados_pesquisa(servidor_a, campus_a) -> SimpleNamespace:
    campus = campus_a

    # Mock get_user para evitar AttributeError em Projeto.save
    with patch('djtools.middleware.threadlocals.get_user', return_value=servidor_a.get_user()):
        edital = Edital.objects.create(
            titulo='Edital Teste',
            descricao='Descrição',
            tipo_edital=Edital.PESQUISA,
            inicio_inscricoes=timezone.now(),
            fim_inscricoes=timezone.now() + datetime.timedelta(days=30),
            inicio_pre_selecao=timezone.now() + datetime.timedelta(days=31),
            fim_pre_selecao=timezone.now() + datetime.timedelta(days=40),
            inicio_selecao=timezone.now() + datetime.timedelta(days=41),
            fim_selecao=timezone.now() + datetime.timedelta(days=50),
            divulgacao_selecao=timezone.now() + datetime.timedelta(days=51),
        )

        dados_comuns = {
            'edital': edital,
            'uo': campus,
            'inicio_execucao': datetime.date.today(),
            'fim_execucao': datetime.date.today() + datetime.timedelta(days=365),
            'vinculo_coordenador': servidor_a.get_vinculo(),
        }

        def criar_projeto(**kwargs) -> Projeto:
            p = Projeto(**kwargs)
            p.bolsa_coordenador = False
            p.save()
            return p

        d = SimpleNamespace(servidor_a=servidor_a, edital=edital)
        d.projeto_ativo = criar_projeto(**dados_comuns, titulo='Projeto Ativo', pre_aprovado=True, aprovado=True, inativado=False)

        d.projeto_concluido = criar_projeto(**dados_comuns, titulo='Projeto Concluido', pre_aprovado=True, aprovado=True, inativado=False)
        RegistroConclusaoProjeto.objects.create(
            projeto=d.projeto_concluido,
            resultados_alcancados='Resultados',
            disseminacao_resultados='Disseminação',
            dt_avaliacao=datetime.date.today(),
        )

        d.projeto_cancelado = criar_projeto(**dados_comuns, titulo='Projeto Cancelado', pre_aprovado=True, aprovado=True, inativado=False)
        ProjetoCancelado.objects.create(projeto=d.projeto_cancelado, data_solicitacao=timezone.now(), cancelado=True)

        d.projeto_inativo = criar_projeto(**dados_comuns, titulo='Projeto Inativo', pre_aprovado=True, aprovado=True, inativado=True)

        d.projeto_nao_aprovado = criar_projeto(**dados_comuns, titulo='Projeto Nao Aprovado', pre_aprovado=True, aprovado=False, inativado=False)

    return d


class TestPesquisa:
    def test_projetos(self, api_client, dados_pesquisa):
        response = api_client.get('/api/pesquisa/projetos/', user=dados_pesquisa.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']

        project_ids = [p['id'] for p in items]

        assert dados_pesquisa.projeto_ativo.id in project_ids, 'Projeto ativo deveria estar na resposta'
        assert dados_pesquisa.projeto_concluido.id in project_ids, 'Projeto concluído deveria estar na resposta'
        assert dados_pesquisa.projeto_cancelado.id not in project_ids, 'Projeto cancelado NÃO deveria estar na resposta'
        assert dados_pesquisa.projeto_inativo.id not in project_ids, 'Projeto inativo NÃO deveria estar na resposta'
        assert dados_pesquisa.projeto_nao_aprovado.id not in project_ids, 'Projeto não aprovado NÃO deveria estar na resposta'

        for p in items:
            if p['id'] == dados_pesquisa.projeto_concluido.id:
                assert p['situacao'] == 'Concluído'
            elif p['id'] == dados_pesquisa.projeto_ativo.id:
                assert p['situacao'] == 'Em execução'
