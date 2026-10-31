"""Testes de fluxo dos projetos de Ensino.

Cada teste cobre uma transição de estado do projeto, a partir do estágio
montado pelas fixtures (`conftest.py`). A antiga matriz de visibilidade de
botões (detalhe de UI) foi substituída pela verificação direta do estado de
domínio (período do edital, situação, datas).
"""

import datetime

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from projetos_ensino.models import Projeto, RegistroConclusaoProjeto
from projetos_ensino.tests.conftest import (
    _login,
    set_periodo_execucao,
    set_periodo_inscricao,
    set_periodo_pre_selecao,
    set_periodo_selecao,
)


@pytest.mark.django_db(databases='__all__')
class TestFluxoProjetosEnsino:
    def test_enviar_projeto_conclui_planejamento(self, client, usuarios, edital, projeto):
        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos_ensino/concluir_planejamento/{projeto.pk}/', follow=True)

        assert 'Projeto enviado com sucesso' in resposta.content.decode()
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento.date() == datetime.date.today()

    def test_projeto_incompleto_nao_pode_ser_enviado(self, client, usuarios, edital):
        """Sem plano, metas e beneficiários, o envio é barrado com mensagens de erro."""
        from projetos_ensino.tests.conftest import _adicionar_projeto

        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)
        projeto = _adicionar_projeto(client, edital)

        conteudo = client.get(f'/projetos_ensino/concluir_planejamento/{projeto.pk}/', follow=True).content.decode()

        assert 'Cadastre o Plano de Aplicação antes de enviar o Projeto.' in conteudo
        assert 'Cadastre as Metas/Atividades antes de enviar o Projeto.' in conteudo
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento is None

    def test_pre_selecionar_projeto(self, client, usuarios, projeto_enviado):
        projeto = projeto_enviado
        _login(client, usuarios.pre_avaliador)
        set_periodo_pre_selecao(projeto.edital)

        resposta = client.get(
            f'/projetos_ensino/pre_selecionar/{projeto.pk}/',
            HTTP_REFERER=f'/projetos_ensino/projetos_nao_avaliados/{projeto.edital.id}/',
        )

        assert resposta.status_code == 302
        projeto.refresh_from_db()
        assert projeto.pre_aprovado is True
        assert projeto.data_pre_avaliacao is not None

    def test_pre_selecionado_visivel_no_periodo_correto(self, client, usuarios, projeto_pre_selecionado):
        projeto = projeto_pre_selecionado
        set_periodo_pre_selecao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos_ensino/projeto/{projeto.pk}/')

        assert Projeto.PERIODO_PRE_SELECAO in resposta.content.decode()
        assert projeto.get_periodo() == Projeto.PERIODO_PRE_SELECAO

    def test_projeto_aprovado_entra_em_execucao(self, client, usuarios, projeto_aprovado):
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos_ensino/projeto/{projeto.pk}/')

        assert projeto.get_periodo() == Projeto.PERIODO_EXECUCAO
        assert Projeto.STATUS_EM_EXECUCAO in resposta.content.decode()

    def test_devolucao_so_por_quem_pode_devolver(self, client, usuarios, projeto_enviado):
        """O formulário de devolução só aparece para quem pode devolver; o POST forjado por outro é recusado (#17515)."""
        projeto = projeto_enviado
        url = f'/projetos_ensino/gerenciar_historico_projeto/{projeto.pk}/'

        _login(client, usuarios.avaliador)
        assert client.post(url, {'parecer_devolucao': 'Forjado'}).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is not None

        _login(client, usuarios.pre_avaliador)
        assert client.post(url, {'parecer_devolucao': 'Ajustar o plano de trabalho'}).status_code == 302
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is None

    def test_relatorio_do_projeto_so_para_quem_ve_o_projeto(self, client, usuarios, projeto_enviado):
        """O relatório expõe contatos da equipe: professor de fora do projeto recebe 403 (#17516)."""
        from django.contrib.auth.models import Group

        from projetos_ensino.tests.conftest import GRUPO_COORDENADOR_PROJETO
        from rh.tests.factories import ServidorFactory

        url = f'/projetos_ensino/relatorio_projeto/{projeto_enviado.pk}/?html=1'
        estranho = ServidorFactory()
        estranho.get_user().groups.add(Group.objects.get(name=GRUPO_COORDENADOR_PROJETO))

        _login(client, estranho)
        assert client.get(url).status_code == 403

        _login(client, usuarios.coordenador)
        assert client.get(url).status_code == 200

    def test_avaliacao_de_cancelamento_so_do_proprio_campus(self, client, usuarios, projeto_enviado):
        """A avaliação do pedido de cancelamento segue o recorte de campus da lista "Cancelamentos" (#17520)."""
        from django.contrib.auth.models import Group

        from projetos_ensino.tests.conftest import GRUPO_PRE_AVALIADOR
        from projetos_ensino.tests.factories import ProjetoCanceladoFactory
        from rh.tests.factories import ServidorFactory

        url = f'/projetos_ensino/avaliar_cancelamento_projeto/{ProjetoCanceladoFactory(projeto=projeto_enviado).pk}/'
        de_outro_campus = ServidorFactory()
        de_outro_campus.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

        _login(client, de_outro_campus)
        assert client.get(url).status_code == 403

        _login(client, usuarios.pre_avaliador)
        assert client.get(url).status_code == 200

    def test_indicacao_de_avaliadores_so_no_proprio_campus(self, client, usuarios, projeto_enviado):
        """A indicação de avaliadores de um projeto segue o recorte da lista "Selecionar avaliadores" (#17550)."""
        from django.contrib.auth.models import Group

        from projetos_ensino.tests.conftest import GRUPO_PRE_AVALIADOR
        from rh.tests.factories import ServidorFactory

        url = f'/projetos_ensino/selecionar_avaliadores_do_projeto/{projeto_enviado.pk}/'
        de_outro_campus = ServidorFactory()
        de_outro_campus.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

        _login(client, de_outro_campus)
        assert client.get(url).status_code == 403

        _login(client, usuarios.pre_avaliador)
        assert client.get(url).status_code == 200

    def test_so_o_avaliador_indicado_avalia_o_projeto(self, client, usuarios, projeto_pre_selecionado):
        """Ter o grupo de avaliador não basta: sem indicação para o projeto, a avaliação dá 403 (#17547)."""
        from projetos_ensino.tests.factories import AvaliadorIndicadoFactory

        projeto = projeto_pre_selecionado
        set_periodo_selecao(projeto.edital)
        url = f'/projetos_ensino/avaliar/{projeto.pk}/'

        _login(client, usuarios.avaliador)
        assert client.get(url).status_code == 403

        AvaliadorIndicadoFactory(projeto=projeto, vinculo=usuarios.avaliador.get_vinculo())
        assert client.get(url).status_code == 200

    def test_registrar_conclusao_projeto(self, client, usuarios, projeto_aprovado):
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.post(
            f'/projetos_ensino/registro_conclusao/{projeto.pk}/',
            {
                'projeto': projeto.pk,
                'resultados_alcancados': 'Resultados Alcançados',
                'disseminacao_resultados': 'Disseminação dos Resultados',
                'obs': 'Observação da conclusão',
            },
        )

        assert_no_validation_errors(resposta)
        assert RegistroConclusaoProjeto.objects.filter(projeto=projeto).exists()

    def test_coordenador_acessa_formulario_de_projeto_no_periodo(self, client, usuarios, edital):
        """No período de inscrição, o coordenador acessa o formulário de novo projeto."""
        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/projetos_ensino/adicionar_projeto/{edital.id}/')

        assert resposta.status_code == 200
        assert 'Adicionar projeto' in resposta.content.decode()
