"""Smoke de rota da estrutura acadêmica do edu: diretoria, curso, matriz, componente, turma.

Estes são os cadastros que sustentam a cadeia inteira (``test_01``→``test_04`` os exercitam
a fundo, pela interface). O que este arquivo pega é outra classe de regressão: a tela que
**deixou de abrir** — 500 por queryset quebrado, 404 por rota renomeada, 403 por permissão
trocada de grupo. Um fluxo profundo cobre um caminho; o smoke cobre a superfície.

Cada rota é um literal com marcador (``{matriz}``), resolvido em ``alvos_rotas.py`` a partir
do que o seed criou — ver a docstring de lá para o porquê da forma.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Cadastros gerais e estrutura de curso, todos sob o Administrador Acadêmico.
CADASTROS = (
    '/edu/componente/{componente}/',
    '/edu/editar_abreviatura_componente/{componente}/',
    '/edu/tipo_componente/{tipo_componente}/',
    '/edu/horariocampus/{horario_campus}/',
    '/edu/replicar_horariocampus/{horario_campus}/',
    '/edu/estruturacurso/{estrutura_curso}/',
    '/edu/importar_componentes/',
    '/edu/painel_controle/',
    '/edu/videos/',
)

DIRETORIA = (
    '/edu/diretoria/{diretoria}/',
    '/edu/adicionar_coordenador_registro_academico/{diretoria}/',
    '/edu/adicionar_membro_diretoria/{diretoria}/{grupo}/',
    '/edu/vincular_grupo_atendimento_diretoria/{diretoria}/',
    '/edu/calendarioacademico/{calendario_academico}/',
    '/edu/replicar_calendario/{calendario_academico}/',
    '/edu/adicionar_sabado_letivo/{calendario_academico}/',
    '/edu/adicionar_data_comemorativa/{calendario_academico}/',
)

# `edu.add_termovinculacaousuariodiretoria` só existe no grupo Diretor Acadêmico
# (`edu/permissions.yaml`), não no Administrador Acadêmico.
DIRETORIA_DA = (
    '/edu/adicionar_auxiliar_secretaria/{diretoria}/',
    '/edu/adicionar_estagiario_secretaria/{diretoria}/',
)

# `editar_legislacao_matriz` é `@group_required('Diretor de Avaliação e Regulação do Ensino')`
# — o DARE do seed (matrícula 100009).
MATRIZ_DARE = ('/edu/editar_legislacao_matriz/{matriz_curso}/',)

CURSO = (
    '/edu/cursocampus/{curso_campus}/',
    '/edu/cursocampus/{curso_campus}/replicar/',
    '/edu/cursocampus/{curso_campus}/editar_funcionamento/',
    '/edu/cursocampus/{curso_campus}/adicionar_atoregulatorio/',
    '/edu/cursocampus/{curso_campus}/adicionar_tramitacaoprocessoemec/',
    '/edu/definir_coordenador_curso/{curso_campus}/',
    '/edu/editar_diretoria_curso/{curso_campus}/',
    '/edu/inserir_diretoria_curso/{curso_campus}/',
    '/edu/adicionar_matriz_curso/{curso_campus}/',
    '/edu/analise_curso/{matriz_curso}/',
)

MATRIZ = (
    '/edu/matriz/{matriz}/',
    '/edu/matriz/{matriz}/replicar/',
    '/edu/matriz/{matriz}/imprimir/',
    '/edu/matriz/{matriz}/imprimir_ch/',
    '/edu/matriz/{matriz}/grade_curricular/',
    '/edu/matriz/{matriz}/importar_componentes/',
    '/edu/matriz/{matriz}/vincular_componente/',
    '/edu/matriz/{matriz}/adicionar_configuracaocertificacaoparcial/',
    '/edu/definir_requisitos/{componente_curricular}/',
)

TURMA = (
    '/edu/turma/{turma}/',
    '/edu/turma_estatistica/{turma}/',
    '/edu/mapa_turma/{turma}/',
    '/edu/horarios_turma_pdf/{turma}/',
    '/edu/adicionar_aluno_turma/{turma}/',
    '/edu/definir_local_aula_turma/{turma}/',
    '/edu/gerar_turmas/',
    '/edu/gerar_diarios/{turma}/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', CADASTROS, id='cadastros'),
        pytest.param('admin_academico', DIRETORIA, id='diretoria'),
        pytest.param('admin_academico', CURSO, id='curso'),
        pytest.param('admin_academico', MATRIZ, id='matriz'),
        pytest.param('admin_academico', TURMA, id='turma'),
        pytest.param('diretor_academico', DIRETORIA_DA, id='diretoria-diretor-academico'),
        pytest.param('dare', MATRIZ_DARE, id='matriz-dare'),
    ],
)
def test_estrutura_academica_abre(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)


# Regressão: a view lia `user` fora do `if usuario_grupo_id:` e devolvia 500 (UnboundLocalError)
# justamente na rota do botão "Adicionar Coordenador" da tela da diretoria.
def test_adicionar_coordenador_sem_usuario_grupo_abre(abrir_rotas):
    abrir_rotas('admin_academico', ('/edu/adicionar_coordenador/{diretoria}/',))


# Regressão: `ano_selecionado = anos[0]` estourava IndexError quando não há matrícula-período em
# ano anterior ao corrente. Determinístico aqui: relógio em 2019 e toda a cadeia do seed é de 2019.
def test_relatorio_periodos_abertos_abre(abrir_rotas):
    abrir_rotas('admin_academico', ('/edu/relatorio_periodos_abertos/',))
