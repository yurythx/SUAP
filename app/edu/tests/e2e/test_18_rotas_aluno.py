"""Smoke de rota do edu sob o próprio aluno: o lado discente do módulo.

São as telas que o aluno alcança pelo menu dele — dados acadêmicos, caracterização,
pedido de matrícula, atividades complementares, polo. Servem também de contraprova do
restante da suíte: se uma dessas devolver 403 sob o aluno do seed, a permissão do
discente regrediu.

Cada rota é um literal com marcador (``{diario}``), resolvido em ``alvos_rotas.py`` a partir
do que o seed da cadeia 01→14 já criou. Um teste por grupo, e não por rota: o login é real a
cada teste, e a falha lista de uma vez todas as rotas do grupo que não abriram.

O que este arquivo pega e um fluxo profundo não pega é a tela que **deixou de abrir** — 500
por queryset quebrado, 404 por rota renomeada, 403 por permissão movida de grupo.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ALUNOS_ALUNO = (
    '/edu/acesso_responsavel/',
    '/edu/atualizar_meus_dados_pessoais/{matricula}/',
    '/edu/atualizar_meus_dados_pessoais/{matricula}/{zero}/',
    '/edu/meus_dados_academicos/',
    '/edu/minha_caracterizacao_socioeconomica/',
)
ATIVIDADES_COMPLEMENTARES_ALUNO = (
    '/edu/solicitar_atividade_aprofundamento/',
    '/edu/solicitar_atividade_complementar/',
)
DIARIOS_ALUNO = (
    '/edu/disciplinas/',
    '/edu/disciplina/{diario}/',
    '/edu/horario_professor/{professor}/{diario}/',
    '/edu/boletim_aluno/',
    '/edu/locais_aula_aluno/',
)
POLOS_ALUNO = ('/edu/atividades_polo_aluno/',)
PROCEDIMENTOS_ALUNO = (
    '/edu/componentes_nao_disponiveis/{aluno}/',
    '/edu/pedido_matricula_credito/{aluno}/',
    '/edu/pedido_matricula_seriado/{aluno}/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('aluno', ALUNOS_ALUNO, id='alunos-aluno'),
        pytest.param('aluno', ATIVIDADES_COMPLEMENTARES_ALUNO, id='atividades_complementares-aluno'),
        pytest.param('aluno', DIARIOS_ALUNO, id='diarios-aluno'),
        pytest.param('aluno', POLOS_ALUNO, id='polos-aluno'),
        pytest.param('aluno', PROCEDIMENTOS_ALUNO, id='procedimentos-aluno'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    # `SENHA_ALUNO` do conftest: o aluno do seed não usa a senha dos servidores.
    abrir_rotas(papel, grupo, senha='123')
