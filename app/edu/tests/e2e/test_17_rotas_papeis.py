"""Smoke de rota do edu sob os demais papéis do seed: professor, secretário, DARE, CRA.

A permissão do SUAP se verifica por status HTTP, e o papel é metade do que o teste afirma:
estas rotas exigem um grupo que o Administrador Acadêmico **não** tem, e abri-las com ele
devolveria 403. Cada grupo declara o papel do seed que a view de fato exige — o papel sai
do decorador (``@permission_required``/``@group_required``) cruzado com
``edu/permissions.yaml``.

Cada rota é um literal com marcador (``{diario}``), resolvido em ``alvos_rotas.py`` a partir
do que o seed da cadeia 01→14 já criou. Um teste por grupo, e não por rota: o login é real a
cada teste, e a falha lista de uma vez todas as rotas do grupo que não abriram.

O que este arquivo pega e um fluxo profundo não pega é a tela que **deixou de abrir** — 500
por queryset quebrado, 404 por rota renomeada, 403 por permissão movida de grupo.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

RELATORIOS_COORDENADOR_CURSO = ('/edu/alunos_sem_turma/{ano}/{periodo}/',)
RELATORIOS_DARE = ('/edu/relatorio_coordenacao_curso/',)
DIPLOMAS_DIRETOR_ACADEMICO = ('/edu/iniciar_sessao_assinatura_eletronica/',)
DIARIOS_PROFESSOR = (
    '/edu/adicionar_materiais_aula/',
    '/edu/materialaula/{material_aula}/',
    '/edu/visualizar_entregas_trabalho/{trabalho}/',
    '/edu/relacao_alunos_emails_pdf/{diario}/',
    '/edu/adicionar_topico_discussao/{diario}/{etapa}/',
    '/edu/entregar_etapa/{diario}/{etapa}/',
    '/edu/entregar_trabalho/{matricula_diario}/',
    '/edu/importar_materiais_aula/',
    '/edu/materiais_diario/{professor_diario}/{etapa}/',
    '/edu/meu_diario/{diario}/{etapa}/',
    '/edu/meu_diario/{diario}/{etapa}/{sem_polo}/',
    '/edu/meus_diarios/',
    '/edu/solicitar_prorrogacao_etapa/{professor_diario}/{etapa}/',
    '/edu/solicitar_relancamento_etapa/{professor_diario}/{etapa}/',
    '/edu/solicitar_trabalho/{diario}/{etapa}/',
    '/edu/solicitar_trabalho/{diario}/{etapa}/{professor_diario}/',
)
PROFESSORES_PROFESSOR = (
    '/edu/locais_aula_professor/',
    '/edu/professor/',
    '/edu/preencher_dados_titulacao/',
)
PROCEDIMENTOS_SECRETARIO = ('/edu/inconsistencias/',)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('coordenador_curso', RELATORIOS_COORDENADOR_CURSO, id='relatorios-coordenador_curso'),
        pytest.param('dare', RELATORIOS_DARE, id='relatorios-dare'),
        pytest.param('diretor_academico', DIPLOMAS_DIRETOR_ACADEMICO, id='diplomas-diretor_academico'),
        pytest.param('professor', DIARIOS_PROFESSOR, id='diarios-professor'),
        pytest.param('professor', PROFESSORES_PROFESSOR, id='professores-professor'),
        pytest.param('secretario', PROCEDIMENTOS_SECRETARIO, id='procedimentos-secretario'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)
