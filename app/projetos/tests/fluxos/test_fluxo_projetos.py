"""Testes de fluxo dos projetos de Extensão.

Cada teste cobre uma transição de estado do projeto, a partir do estágio
montado pelas fixtures (`conftest.py`). A antiga matriz de visibilidade de
botões (detalhe de UI) foi substituída pela verificação direta do estado de
domínio (período do edital, situação, datas).
"""

import datetime

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from projetos.models import Projeto, RegistroConclusaoProjeto
from projetos.tests.conftest import (
    _login,
    set_periodo_execucao,
    set_periodo_inscricao,
    set_periodo_pre_selecao,
)


@pytest.mark.django_db(databases='__all__')
class TestFluxoProjetos:
    def test_enviar_projeto_conclui_planejamento(self, client, usuarios, edital, projeto):
        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos/concluir_planejamento/{projeto.pk}/', follow=True)

        assert 'Projeto enviado com sucesso' in resposta.content.decode()
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento.date() == datetime.date.today()

    def test_projeto_incompleto_nao_pode_ser_enviado(self, client, usuarios, edital):
        """Sem plano, metas e beneficiários, o envio é barrado com mensagens de erro."""
        from projetos.tests.conftest import _adicionar_projeto

        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)
        projeto = _adicionar_projeto(client, edital)

        conteudo = client.get(f'/projetos/concluir_planejamento/{projeto.pk}/', follow=True).content.decode()

        assert 'Cadastre o Plano de Aplicação antes de enviar o Projeto.' in conteudo
        assert 'Cadastre as Metas/Atividades antes de enviar o Projeto.' in conteudo
        assert 'Cadastre a Caracterização dos Beneficiários antes de enviar o Projeto.' in conteudo
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento is None

    def test_pre_selecionar_projeto(self, client, usuarios, projeto_enviado):
        projeto = projeto_enviado
        _login(client, usuarios.pre_avaliador)
        set_periodo_pre_selecao(projeto.edital)

        resposta = client.get(
            f'/projetos/pre_selecionar/{projeto.pk}/',
            HTTP_REFERER=f'/projetos/projetos_nao_avaliados/{projeto.edital.id}/',
        )

        assert resposta.status_code == 302
        projeto.refresh_from_db()
        assert projeto.pre_aprovado is True
        assert projeto.data_pre_avaliacao is not None

    def test_pre_selecionado_visivel_no_periodo_correto(self, client, usuarios, projeto_pre_selecionado):
        projeto = projeto_pre_selecionado
        set_periodo_pre_selecao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos/projeto/{projeto.pk}/')

        assert Projeto.PERIODO_PRE_SELECAO in resposta.content.decode()
        assert projeto.get_periodo() == Projeto.PERIODO_PRE_SELECAO

    def test_projeto_aprovado_entra_em_execucao(self, client, usuarios, projeto_aprovado):
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos/projeto/{projeto.pk}/')

        assert projeto.get_periodo() == Projeto.PERIODO_EXECUCAO
        assert Projeto.STATUS_EM_EXECUCAO in resposta.content.decode()

    def test_registrar_conclusao_projeto(self, client, usuarios, projeto_aprovado):
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.post(
            f'/projetos/registro_conclusao/{projeto.pk}/',
            {
                'projeto': projeto.pk,
                'resultados_alcancados': 'Resultados Alcançados',
                'disseminacao_resultados': 'Disseminação dos Resultados',
                'obs': 'Observação da conclusão',
            },
        )

        assert_no_validation_errors(resposta)
        assert RegistroConclusaoProjeto.objects.filter(projeto=projeto).exists()

    # --- Permissões por perfil ---------------------------------------------

    def test_coordenador_acessa_formulario_de_projeto_no_periodo(self, client, usuarios, edital):
        """No período de inscrição, o coordenador acessa o formulário de novo projeto."""
        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos/adicionar_projeto/{edital.id}/')

        assert resposta.status_code == 200
        assert 'Adicionar Projeto' in resposta.content.decode()

    def test_pre_avaliacao_disponivel_apenas_no_periodo(self, client, usuarios, edital):
        _login(client, usuarios.pre_avaliador)
        url = '/projetos/pre_avaliacao/'

        set_periodo_inscricao(edital)
        assert 'Nenhum edital disponível no momento' in client.get(url).content.decode()

        set_periodo_pre_selecao(edital)
        assert edital.titulo in client.get(url).content.decode()
