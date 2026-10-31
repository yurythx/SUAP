"""Fixtures de fluxo da Pesquisa de Egressos.

Montam por ORM o estado mínimo: o gerente de extensão (autor das pesquisas), um
aluno egresso (concluído, alvo das pesquisas da sua modalidade) e uma pesquisa
com questionário. Os testes exercitam os endpoints de cada etapa (montar
questionário, publicar, clonar e responder).
"""

import datetime

import pytest
from django.contrib.auth.models import Group

from comum.models import Ano

# `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest raiz);
# não as importamos aqui para poder usá-las como parâmetro de fixture.
from comum.pytest_fixtures import api_auth_mocks
from edu.models import Aluno, CursoCampus, Diretoria, SituacaoMatricula
from edu.tests.factories import ModalidadeFactory, SituacaoMatriculaFactory
from rh.tests.factories import ServidorFactory, SetorFactory
from egressos.models import Categoria, Opcao, Pergunta, Pesquisa
from rh.models import PessoaFisica

SENHA = '123'


@pytest.fixture
def ano_atual():
    return Ano.objects.get_or_create(ano=datetime.datetime.now().year)[0]


@pytest.fixture
def gerente(suap_client, sync_permissions):
    """Client autenticado como Gerente Sistêmico de Extensão — autor das pesquisas."""
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Gerente Sistêmico de Extensão'))
    user.set_password(SENHA)
    user.save()
    suap_client.login(username=user.username, password=SENHA)
    return suap_client


@pytest.fixture
def curso_campus(db):
    """Curso mínimo (de mestrado) ao qual o egresso está vinculado."""
    diretoria = Diretoria.objects.create(setor=SetorFactory())
    return CursoCampus.objects.create(
        descricao='Mestrado em Educação',
        descricao_historico='Mestrado em Educação',
        codigo='MEST-01',
        # A modalidade é tabela-tipo que vinha do seed do `suap_data`.
        modalidade=ModalidadeFactory(),
        diretoria=diretoria,
    )


@pytest.fixture
def egresso(db, sync_permissions, curso_campus, ano_atual):
    """Aluno concluído neste ano — alvo das pesquisas da sua modalidade.

    Pede `sync_permissions` porque salvar o `User` do aluno dispara o
    `user_post_save` do `comum`, que busca o grupo 'Aluno' pelo nome.
    """
    pessoa = PessoaFisica.objects.get_or_create(
        nome='Carlos Breno Pereira Silva',
        defaults={'cpf': '359.221.769-00'},
    )[0]
    aluno = Aluno.objects.create(
        matricula='20131',
        pessoa_fisica=pessoa,
        ano_letivo=Ano.objects.get_or_create(ano=2013)[0],
        periodo_letivo=1,
        # Também tabela-tipo do seed antigo; o egresso é, por definição, concluído.
        situacao=SituacaoMatriculaFactory(id=SituacaoMatricula.CONCLUIDO, descricao='Concluido'),
        dt_conclusao_curso=datetime.datetime.now(),
        ano_conclusao=ano_atual.ano,
        curso_campus=curso_campus,
    )
    v = aluno.get_vinculo()
    if v:
        v.email_pessoal = 'egresso@email.com'
        v.save(update_fields=['email_pessoal'])
    user = aluno.get_user()
    user.set_password(SENHA)
    user.save()
    return aluno


@pytest.fixture
def pesquisa_basica(curso_campus, ano_atual):
    """Pesquisa sem questionário — ponto de partida para montá-lo pelos endpoints."""
    pesquisa = Pesquisa.objects.create(titulo='Pesquisa Teste', descricao='Descrição da pesquisa', modalidade=curso_campus.modalidade)
    pesquisa.conclusao.add(ano_atual)
    return pesquisa


@pytest.fixture
def pesquisa(curso_campus, ano_atual):
    """Pesquisa com uma categoria, uma pergunta objetiva e uma opção (ainda não publicada)."""
    pesquisa = Pesquisa.objects.create(titulo='Pesquisa Teste', descricao='Descrição da pesquisa', modalidade=curso_campus.modalidade)
    pesquisa.conclusao.add(ano_atual)
    categoria = Categoria.objects.create(titulo='Categoria 1', ordem=1, pesquisa=pesquisa)
    pergunta = Pergunta.objects.create(
        conteudo='Como você avalia seu curso?',
        tipo=Pergunta.OBJETIVA_RESPOSTA_UNICA,
        preenchimento_obrigatorio=True,
        categoria=categoria,
        pesquisa=pesquisa,
    )
    Opcao.objects.create(conteudo='Ótimo', pergunta=pergunta)
    return pesquisa


@pytest.fixture
def pesquisa_publicada(pesquisa, egresso):
    """Pesquisa publicada com os convites enviados (gera o aviso ao egresso)."""
    hoje = datetime.date.today()
    pesquisa.publicada = True
    pesquisa.inicio = hoje
    pesquisa.fim = hoje + datetime.timedelta(days=1)  # até amanhã: o teste que atravessa a meia-noite não acha a pesquisa vencida
    pesquisa.save()
    pesquisa.enviar_convites()
    return pesquisa
