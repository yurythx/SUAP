"""Testes de fluxo dos projetos de Pesquisa.

Cada teste cobre uma transição de estado do projeto, partindo do estágio
montado pelas fixtures (`conftest.py`) e disparando a ação real do usuário.
A antiga matriz de visibilidade de botões (detalhe de UI) foi substituída pela
verificação direta do estado de domínio (período do edital, situação, datas).
"""

import datetime

import pytest
from django.contrib.auth.models import Group
from django.db.models.sql.query import FieldError

from comum.pytest_fixtures import assert_no_validation_errors, verificar_perfil_status
from djtools.utils import get_datetime_now
from pesquisa.models import Edital, Participacao, Projeto, RecursoProjeto, RegistroConclusaoProjeto
from pesquisa.tests.conftest import (
    GRUPO_AVALIADOR,
    GRUPO_COORDENADOR_PROJETO,
    GRUPO_GERENTE_SISTEMICO,
    GRUPO_PRE_AVALIADOR,
    _login,
    set_periodo_execucao,
    set_periodo_inscricao,
    set_periodo_pre_selecao,
)
from pesquisa.tests.factories import ProjetoCanceladoFactory, RecursoProjetoFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory


def _coordenador_pesquisa_outro_campus(usuarios) -> Servidor:
    servidor = ServidorFactory(setor=usuarios.outro_campus.setor)
    servidor.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))
    return servidor


def _assessor_pesquisa_outro_campus(usuarios) -> Servidor:
    servidor = ServidorFactory(setor=usuarios.outro_campus.setor)
    servidor.get_user().groups.add(Group.objects.get(name='Assessor de Pesquisa'))
    return servidor


@pytest.mark.django_db(databases='__all__')
class TestFluxoPesquisa:
    # --- Transições do ciclo de vida ---------------------------------------

    def test_enviar_projeto_conclui_planejamento(self, client, usuarios, edital, projeto):
        """Com a equipe, metas e plano preenchidos, o coordenador envia o projeto."""
        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/pesquisa/concluir_planejamento/{projeto.pk}/', follow=True)

        assert 'Projeto enviado com sucesso' in resposta.content.decode()
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento.date() == datetime.date.today()

    def test_projeto_incompleto_nao_pode_ser_enviado(self, client, usuarios, edital):
        """Sem plano de aplicação e metas, o envio é barrado com mensagem de erro."""
        from pesquisa.tests.conftest import _adicionar_projeto

        set_periodo_inscricao(edital)
        _login(client, usuarios.coordenador)
        projeto = _adicionar_projeto(client, edital)

        resposta = client.get(f'/pesquisa/concluir_planejamento/{projeto.pk}/', follow=True)

        conteudo = resposta.content.decode()
        assert 'Cadastre o Plano de Aplicação antes de enviar o Projeto.' in conteudo
        assert 'Cadastre as Metas/Atividades antes de enviar o Projeto.' in conteudo
        projeto.refresh_from_db()
        assert projeto.data_conclusao_planejamento is None

    def test_pre_selecionar_projeto(self, client, usuarios, projeto_enviado):
        """No período de pré-seleção, o pré-avaliador pré-aprova o projeto enviado."""
        projeto = projeto_enviado
        _login(client, usuarios.pre_avaliador)
        set_periodo_pre_selecao(projeto.edital)

        resposta = client.post(f'/pesquisa/pre_selecionar/{projeto.pk}/', {'obs_reprovacao': 'ok'})

        assert_no_validation_errors(resposta)
        projeto.refresh_from_db()
        assert projeto.pre_aprovado is True
        assert projeto.data_pre_avaliacao is not None

    def test_pre_selecao_segue_papel_campus_e_estado(self, client, usuarios, projeto_enviado):
        """Pré-seleção exige o pré-avaliador com o recorte de campus e o estado em que a lista oferece o botão (#17570)."""
        projeto = projeto_enviado
        set_periodo_pre_selecao(projeto.edital)
        justificativa = {'obs_reprovacao': 'justificativa'}

        _login(client, _coordenador_pesquisa_outro_campus(usuarios))
        assert client.post(f'/pesquisa/pre_selecionar/{projeto.pk}/', justificativa).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).data_pre_avaliacao is None

        # O Assessor de Pesquisa pré-avalia projeto de qualquer campus, e a lista lhe oferece o botão.
        _login(client, _assessor_pesquisa_outro_campus(usuarios))
        assert f'/pesquisa/pre_selecionar/{projeto.pk}/' in client.get(f'/pesquisa/projetos_nao_avaliados/{projeto.edital.pk}/').content.decode()
        assert client.post(f'/pesquisa/pre_aprovar/{projeto.pk}/', justificativa).status_code == 302
        assert Projeto.objects.get(pk=projeto.pk).pre_aprovado is True

        # pre_aprovar em projeto já pré-aprovado não inverte o estado; pre_rejeitar não repete.
        _login(client, usuarios.pre_avaliador)
        assert client.post(f'/pesquisa/pre_aprovar/{projeto.pk}/', justificativa).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).pre_aprovado is True
        assert client.post(f'/pesquisa/pre_rejeitar/{projeto.pk}/', justificativa).status_code == 302
        assert Projeto.objects.get(pk=projeto.pk).pre_aprovado is False
        assert client.post(f'/pesquisa/pre_rejeitar/{projeto.pk}/', justificativa).status_code == 403

        # Em edital de seleção geral, a lista é negada ao Coordenador de Pesquisa; a ação também.
        Edital.objects.filter(pk=projeto.edital.pk).update(forma_selecao=Edital.GERAL)
        assert client.post(f'/pesquisa/pre_aprovar/{projeto.pk}/', justificativa).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).pre_aprovado is False

    def test_projeto_e_impressoes_so_do_proprio_campus(self, client, usuarios, projeto_enviado):
        """Coordenador de Pesquisa de outro campus não abre, não imprime nem exporta o projeto (#17571)."""
        projeto = projeto_enviado
        urls = [
            f'/pesquisa/projeto/{projeto.pk}/',
            f'/pesquisa/imprimir_projeto/{projeto.pk}/?html=1',
            f'/pesquisa/relatorio_projeto/{projeto.pk}/?html=1',
            f'/pesquisa/gerar_lista_frequencia/{projeto.pk}/',
            f'/pesquisa/exportar_atividades_projeto_xls/{projeto.pk}/',
        ]

        _login(client, _coordenador_pesquisa_outro_campus(usuarios))
        assert [client.get(url).status_code for url in urls] == [403] * len(urls)

        _login(client, usuarios.pre_avaliador)
        assert client.get(urls[0]).status_code == 200
        assert client.get(urls[1]).status_code == 200

        # O Assessor de Pesquisa imprime projeto de qualquer campus, como na lista de pré-seleção (#17570).
        _login(client, _assessor_pesquisa_outro_campus(usuarios))
        assert client.get(urls[1]).status_code == 200
        assert client.get(urls[2]).status_code == 200

    def test_pre_selecionado_visivel_no_periodo_correto(self, client, usuarios, projeto_pre_selecionado):
        """Projeto pré-selecionado aparece como tal na visão do coordenador."""
        projeto = projeto_pre_selecionado
        set_periodo_pre_selecao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/pesquisa/projeto/{projeto.pk}/')

        assert Projeto.PERIODO_PRE_SELECAO in resposta.content.decode()
        assert projeto.get_periodo() == Projeto.PERIODO_PRE_SELECAO

    def test_projeto_aprovado_entra_em_execucao(self, client, usuarios, projeto_aprovado):
        """Após avaliação e distribuição de bolsas, na divulgação o projeto fica em execução."""
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.get(f'/pesquisa/projeto/{projeto.pk}/')

        assert projeto.get_periodo() == Projeto.PERIODO_EXECUCAO
        assert Projeto.STATUS_EM_EXECUCAO in resposta.content.decode()

    def test_devolucao_so_por_quem_pode_devolver(self, client, usuarios, projeto_enviado):
        """O formulário de devolução só aparece para quem pode devolver; o POST forjado por outro é recusado (#17515)."""
        projeto = projeto_enviado
        url = f'/pesquisa/gerenciar_historico_projeto/{projeto.pk}/'

        _login(client, usuarios.avaliador)
        assert client.post(url, {'parecer_devolucao': 'Forjado'}).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is not None

        # Coordenador de Pesquisa é papel de campus: o de outro campus não devolve (#17557).
        _login(client, _coordenador_pesquisa_outro_campus(usuarios))
        assert client.post(url, {'parecer_devolucao': 'Forjado'}).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is not None

        # O Assessor de Pesquisa pré-seleciona, mas não devolve (#17570).
        _login(client, _assessor_pesquisa_outro_campus(usuarios))
        assert client.post(url, {'parecer_devolucao': 'Forjado'}).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is not None

        _login(client, usuarios.pre_avaliador)
        assert client.post(url, {'parecer_devolucao': 'Ajustar o plano de trabalho'}).status_code == 302
        assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is None

    def test_avaliacao_de_cancelamento_so_do_proprio_campus(self, client, usuarios, projeto_enviado):
        """A avaliação do pedido de cancelamento segue o recorte de campus da lista "Cancelamentos" (#17520)."""
        url = f'/pesquisa/avaliar_cancelamento_projeto/{ProjetoCanceladoFactory(projeto=projeto_enviado).pk}/'

        _login(client, _coordenador_pesquisa_outro_campus(usuarios))
        assert client.get(url).status_code == 403

        _login(client, usuarios.pre_avaliador)
        assert client.get(url).status_code == 200

    def test_documentos_de_participacao_so_do_proprio_campus(self, client, usuarios, projeto_aprovado):
        """Coordenador de Pesquisa de outro campus não emite plano de trabalho nem declaração de membro (#17557)."""
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        participacao = Participacao.objects.filter(projeto=projeto).exclude(vinculo_pessoa=None).first()
        url_plano = f'/pesquisa/plano_trabalho_participante/{projeto.pk}/{participacao.pk}/'
        url_declaracao = f'/pesquisa/emitir_declaracao_participacao_pdf/{participacao.pk}/'

        # O Assessor de Pesquisa só pré-seleciona e imprime: não emite documento de membro (#17570).
        for de_outro_campus in (_coordenador_pesquisa_outro_campus(usuarios), _assessor_pesquisa_outro_campus(usuarios)):
            _login(client, de_outro_campus)
            assert client.get(url_plano).status_code == 403
            resposta = client.get(url_declaracao, follow=True)
            assert 'Você não tem permissão para ver isso.' in resposta.content.decode()

        _login(client, usuarios.pre_avaliador)
        assert client.get(url_plano).status_code == 200

    def test_recurso_de_pre_selecao_segue_recorte_da_lista(self, client, usuarios, projeto_enviado):
        """Detalhe e avaliação do recurso repetem o recorte de campus de "Solicitações de Recurso" (#17563); o Auditor lê de qualquer campus (#17562)."""
        recurso = RecursoProjetoFactory(projeto=projeto_enviado)
        url_detalhe = f'/pesquisa/recurso_projeto/{recurso.pk}/'
        url_avaliar = f'/pesquisa/avaliar_recurso_projeto/{recurso.pk}/'

        _login(client, _coordenador_pesquisa_outro_campus(usuarios))
        assert client.get(url_detalhe).status_code == 403
        assert client.post(url_avaliar, {'parecer': 'Forjado', 'parecer_favoravel': 'on'}).status_code == 403
        assert RecursoProjeto.objects.get(pk=recurso.pk).data_avaliacao is None

        auditor = ServidorFactory(setor=usuarios.outro_campus.setor)
        auditor.get_user().groups.add(Group.objects.get(name='Auditor'))
        _login(client, auditor)
        assert client.get(url_detalhe).status_code == 200

        _login(client, usuarios.pre_avaliador)
        assert client.get(url_detalhe).status_code == 200
        client.post(url_avaliar, {'parecer': 'De acordo', 'parecer_favoravel': 'on'})
        assert RecursoProjeto.objects.get(pk=recurso.pk).data_avaliacao is not None

    def test_recurso_validado_nao_aceita_nova_avaliacao(self, client, usuarios, projeto_enviado):
        """Depois da validação a lista mostra "-" no lugar de "Editar Avaliação"; a rota também recusa (#17563)."""
        recurso = RecursoProjetoFactory(projeto=projeto_enviado, data_avaliacao=get_datetime_now(), data_validacao=get_datetime_now())

        _login(client, usuarios.pre_avaliador)
        assert client.post(f'/pesquisa/avaliar_recurso_projeto/{recurso.pk}/', {'parecer': 'Mudei de ideia'}).status_code == 403
        assert RecursoProjeto.objects.get(pk=recurso.pk).parecer is None

    def test_indicacao_de_avaliadores_so_no_proprio_campus(self, client, usuarios, projeto_enviado):
        """A indicação de avaliadores de um projeto segue o recorte da lista "Selecionar avaliadores" (#17550)."""
        from django.contrib.auth.models import Group

        from pesquisa.tests.conftest import GRUPO_PRE_AVALIADOR
        from rh.tests.factories import ServidorFactory

        url = f'/pesquisa/selecionar_avaliadores_do_projeto/{projeto_enviado.pk}/?url=/'
        de_outro_campus = ServidorFactory()
        de_outro_campus.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

        _login(client, de_outro_campus)
        assert client.get(url).status_code == 403

        _login(client, usuarios.pre_avaliador)
        assert client.get(url).status_code == 200

    def test_anuencia_da_chefia_so_com_opcao_valida(self, client, usuarios, edital, projeto):
        """Opção fora de 1/2 dá 404 sem gravar nada; a válida registra a anuência (#17551)."""
        set_periodo_inscricao(edital)
        Projeto.objects.filter(pk=projeto.pk).update(responsavel_anuencia=usuarios.avaliador)
        _login(client, usuarios.avaliador)

        assert client.get(f'/pesquisa/registrar_anuencia/{projeto.pk}/3/').status_code == 404
        assert Projeto.objects.get(pk=projeto.pk).anuencia_registrada_em is None

        assert client.get(f'/pesquisa/registrar_anuencia/{projeto.pk}/1/').status_code == 302
        assert Projeto.objects.get(pk=projeto.pk).anuencia is True

    def test_responsavel_pela_anuencia_so_diretor_ou_coordenador_do_campus(self, client, usuarios, edital, projeto):
        """Só o Diretor e o Coordenador de Pesquisa do campus trocam o responsável pela anuência, e só em edital que a exige (#17578)."""
        set_periodo_inscricao(edital)
        Projeto.objects.filter(pk=projeto.pk).update(anuencia=True, anuencia_registrada_em=get_datetime_now())
        url = f'/pesquisa/alterar_chefia_imediata/{projeto.pk}/'
        dados = {'responsavel_anuencia': usuarios.avaliador.pk}

        # Edital que não exige anuência: nem o Coordenador de Pesquisa do campus troca.
        _login(client, usuarios.pre_avaliador)
        assert client.post(url, dados).status_code == 403
        assert Projeto.objects.get(pk=projeto.pk).anuencia is True

        Edital.objects.filter(pk=edital.pk).update(exige_anuencia=True)
        for intruso in (_coordenador_pesquisa_outro_campus(usuarios), _assessor_pesquisa_outro_campus(usuarios)):
            _login(client, intruso)
            assert client.post(url, dados).status_code == 403
            assert Projeto.objects.get(pk=projeto.pk).anuencia is True

        # O Pré-Avaliador Sistêmico abre o projeto, mas não recebe o botão.
        pre_avaliador_sistemico = ServidorFactory(setor=usuarios.coordenador.setor)
        pre_avaliador_sistemico.get_user().groups.add(Group.objects.get(name='Pré-Avaliador Sistêmico de Projetos de Pesquisa'))
        _login(client, pre_avaliador_sistemico)
        resposta = client.get(f'/pesquisa/projeto/{projeto.pk}/')
        assert resposta.status_code == 200
        assert url not in resposta.content.decode()

        _login(client, usuarios.pre_avaliador)
        assert url in client.get(f'/pesquisa/projeto/{projeto.pk}/').content.decode()
        assert client.post(url, dados).status_code == 302
        projeto.refresh_from_db()
        assert projeto.responsavel_anuencia == usuarios.avaliador
        assert projeto.anuencia is None

    def test_registrar_conclusao_projeto(self, client, usuarios, projeto_aprovado):
        """Em execução, o coordenador registra a conclusão do projeto."""
        projeto = projeto_aprovado
        set_periodo_execucao(projeto.edital)
        _login(client, usuarios.coordenador)

        resposta = client.post(
            f'/pesquisa/registro_conclusao/{projeto.pk}/',
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

    def test_pode_visualizar_edital(self, client, usuarios, edital):
        _login(client, usuarios.coordenador)
        verificar_perfil_status(client, client.user, f'/pesquisa/edital/{edital.id}/', perfis_corretos=[GRUPO_GERENTE_SISTEMICO])

    def test_pode_cadastrar_projeto(self, client, usuarios, edital):
        """Coordenador, gerente, pré-avaliador e avaliador podem abrir o formulário de projeto."""
        _login(client, usuarios.coordenador)
        verificar_perfil_status(
            client,
            client.user,
            f'/pesquisa/adicionar_projeto/{edital.id}/',
            verificar_sem_perfil=False,
            perfis_corretos=[GRUPO_COORDENADOR_PROJETO, GRUPO_GERENTE_SISTEMICO, GRUPO_PRE_AVALIADOR, GRUPO_AVALIADOR],
        )

    # --- Disponibilidade por período ---------------------------------------

    def test_pre_avaliacao_disponivel_apenas_no_periodo(self, client, usuarios, edital):
        """A tela de pré-avaliação só lista o edital durante a pré-seleção."""
        _login(client, usuarios.pre_avaliador)
        url = '/pesquisa/pre_avaliacao/pesquisa/'

        set_periodo_inscricao(edital)
        assert 'Nenhum edital disponível no momento' in client.get(url).content.decode()

        set_periodo_pre_selecao(edital)
        assert edital.titulo in client.get(url).content.decode()


@pytest.mark.django_db(databases='__all__')
class TestGerarBolsaAE:
    def test_filtro_antigo_levanta_fielderror(self, usuarios):
        with pytest.raises(FieldError):
            Participacao.objects.filter(vinculo_pessoa__alunos__isnull=False).exists()

    def test_filtro_novo_nao_levanta_erro(self, usuarios):
        Participacao.objects.filter(vinculo_pessoa__tipo_relacionamento__model='aluno').exists()

    def test_gerar_bolsa_ae_com_edital_sem_participacoes(self, usuarios):
        edital = Edital.objects.create(
            titulo='Edital Teste',
            descricao='Descrição teste',
            tipo_edital=Edital.PESQUISA,
            inicio_inscricoes=datetime.datetime.now(),
            fim_inscricoes=datetime.datetime.now() + datetime.timedelta(days=30),
        )
        Participacao.gerar_bolsa_ae(editais=[edital.id])  # não deve levantar FieldError


@pytest.mark.django_db(databases='__all__')
class TestRelatorioDadosCartaoPesquisador:
    def test_data_inicio_exercicio_none_retorna_string_vazia(self):
        servidor = Servidor(data_inicio_exercicio_no_cargo=None)
        resultado = servidor.data_inicio_exercicio_no_cargo.strftime('%d/%m/%Y').split('/', 1)[1] if servidor.data_inicio_exercicio_no_cargo else ''
        assert resultado == ''

    def test_data_inicio_exercicio_com_valor_retorna_mes_ano(self):
        servidor = Servidor(data_inicio_exercicio_no_cargo=datetime.date(2010, 1, 1))
        resultado = servidor.data_inicio_exercicio_no_cargo.strftime('%d/%m/%Y').split('/', 1)[1] if servidor.data_inicio_exercicio_no_cargo else ''
        assert resultado == '01/2010'
