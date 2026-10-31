"""Alteração da equipe do projeto (aba "Equipe" de `projeto.html`)."""

import datetime

import pytest
from django.contrib.auth.models import Group

from projetos_ensino.models import HistoricoEquipe, Participacao
from projetos_ensino.tests.conftest import _login, set_periodo_execucao


def _rotas_da_equipe(projeto):
    aluno = Participacao.objects.filter(projeto=projeto, vinculo_pessoa__tipo_relacionamento__model='aluno').first()
    servidor = Participacao.objects.filter(projeto=projeto, responsavel=False, vinculo_pessoa__tipo_relacionamento__model='servidor').first()
    return [
        f'/projetos_ensino/adicionar_participante_servidor/{projeto.pk}/',
        f'/projetos_ensino/adicionar_participante_aluno/{projeto.pk}/',
        f'/projetos_ensino/editar_participante_servidor/{projeto.pk}/{servidor.pk}/',
        f'/projetos_ensino/editar_participante_aluno/{projeto.pk}/{aluno.pk}/',
        f'/projetos_ensino/alterar_coordenador/{projeto.pk}/',
        f'/projetos_ensino/indicar_orientador/{aluno.pk}/',
        f'/projetos_ensino/remover_participante/{aluno.pk}/',
        f'/projetos_ensino/ativar_participante/{aluno.pk}/',
    ]


@pytest.mark.django_db(databases='__all__')
def test_equipe_so_muda_quando_a_tela_oferece(client, usuarios, projeto_aprovado):
    """Projeto finalizado não tem a equipe alterada nem por URL digitada, nem pelo Gerente Sistêmico (#17558)."""
    projeto = projeto_aprovado
    set_periodo_execucao(projeto.edital)
    rotas = _rotas_da_equipe(projeto)

    # em execução, a tela oferece as oito ações ao coordenador
    _login(client, usuarios.coordenador)
    for rota in rotas:
        assert client.get(rota).status_code != 403, rota

    projeto.data_finalizacao_conclusao = datetime.date.today()
    projeto.save()
    eventos = HistoricoEquipe.objects.filter(projeto=projeto).count()

    for ator in (usuarios.coordenador, usuarios.gerente):
        _login(client, ator)
        for rota in rotas:
            assert client.get(rota).status_code == 403, rota

    assert HistoricoEquipe.objects.filter(projeto=projeto).count() == eventos
    assert not Participacao.objects.filter(projeto=projeto, ativo=False).exists()


@pytest.mark.django_db(databases='__all__')
def test_gerente_de_ensino_sem_grupo_servidor_adiciona_colaborador(client, usuarios, projeto):
    """Gerente com só a permissão de interagir do Ensino (sem o grupo Servidor) abre "Adicionar Colaborador Externo" (#17569)."""
    _login(client, usuarios.gerente)
    # depois do login: o login devolve o grupo Servidor ao servidor
    usuarios.gerente.get_user().groups.remove(Group.objects.get(name='Servidor'))

    assert client.get(f'/projetos_ensino/adicionar_participante_colaborador/{projeto.pk}/').status_code == 200
