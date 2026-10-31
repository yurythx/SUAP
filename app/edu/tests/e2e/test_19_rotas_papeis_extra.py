"""Smoke de rota dos papéis que nenhuma ``.feature`` do behave exercitava.

O ``edu`` tem telas cujo decorador pede um grupo que a cadeia 001→013 nunca criou usuário
para: migração de dados (``comum.is_migrador_edu``), censo (``comum.is_operador_de_censo``),
operações críticas (``edu Administrador``), NAPNE e Pé de Meia. Sob o Administrador Acadêmico
todas devolvem 403 — e 403 num smoke de rota significa "o papel declarado no teste está
errado", nunca "a rota não é navegável". Os servidores estão em
``seed.SERVIDORES_ROTAS`` e os papéis em ``conftest.PAPEIS``.

Cada grupo abaixo é um papel, e o papel sai do decorador da view cruzado com
``edu/permissions.yaml`` — não de quem "parece" poder.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# `@permission_required('comum.is_migrador_edu')` — o grupo "Migrador edu" é o único que a
# concede. São as telas do importador CSV, todas formulário de upload.
MIGRACAO = (
    '/edu/importar_aluno_csv/v2/',
    '/edu/importar_componente_csv/',
    '/edu/importar_curso_csv/',
    '/edu/importar_equivalencia_csv/',
    '/edu/importar_historico_aluno_csv/',
    '/edu/importar_matriz_csv/',
    '/edu/importar_procedimento_matricula_csv/',
    '/edu/inicializar_periodo_letivo/',
)

# `@permission_required('comum.is_operador_de_censo')` — grupo "Operador de Censo".
CENSO = ('/edu/editar_turno/{aluno}/',)

# `@group_required('edu Administrador')` — operações que os outros perfis não podem fazer.
ADMIN_EDU = ('/edu/editar_situacao_matricula/{aluno}/',)

# `edu.add_acolhimento` só existe nos grupos do NAPNE (`edu/permissions.yaml`).
NAPNE = (
    '/edu/napne/acolhimento/adicionar/',
    '/edu/napne/acolhimento/adicionar/{aluno}/',
)

# `edu.view_operacaopedemeia` era órfã (nenhum grupo a concedia) quando este teste foi escrito;
# o servidor 100014 a recebe direta por `seed.PERMISSOES_DIRETAS`. A permissão foi acrescentada
# ao "Administrador Acadêmico" em `edu/permissions.yaml`, onde os outros três models do Pé de
# Meia já estavam — a concessão direta continua aqui só para o teste não depender dessa correção.
PEDEMEIA = (
    '/edu/cadastrar_operacao_pedemeia/',
    '/edu/calcular_frequencia_pedemeia/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('migrador', MIGRACAO, id='migracao'),
        pytest.param('operador_censo', CENSO, id='censo'),
        pytest.param('admin_edu', ADMIN_EDU, id='admin-edu'),
        pytest.param('coordenador_napne', NAPNE, id='napne'),
        pytest.param('operador_pedemeia', PEDEMEIA, id='pedemeia'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)


# `relatar_inconsistencia_pedemeia` resolve o sujeito por `Aluno.locals` +
# `request.user.username` (`edu/views/pedemeia.py:52`): apesar de morar no módulo do Pé de
# Meia, é tela do discente.
def test_relato_de_inconsistencia_do_pedemeia_abre(abrir_rotas):
    abrir_rotas('aluno', ('/edu/relatar_inconsistencia_pedemeia/',), senha='123')
