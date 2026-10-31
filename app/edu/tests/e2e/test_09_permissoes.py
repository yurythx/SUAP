"""Fronteira de acesso do edu: quem entra em quê.

Teste barato e de sinal alto — permissão no edu vem de duas fontes que se misturam
(grupo global e ``UsuarioGrupoSetor`` com escopo de diretoria), então a regressão típica
não é "a tela quebrou", é "a tela abriu para quem não devia". A matriz abaixo foi
**medida** nesta base, não deduzida do ``permissions.yaml``; onde código e menu discordam,
o comentário registra.

Só afirma código HTTP, nunca varre menu: menu é template, permissão é view.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'

# (papel, rota, status esperado)
MATRIZ = [
    # O Administrador Acadêmico é quem monta o catálogo: cursos, matrizes, diretorias.
    ('admin_academico', '/admin/edu/diretoria/add/', 200),
    ('admin_academico', '/admin/edu/cursocampus/add/', 200),
    ('admin_academico', '/edu/gerar_turmas/', 200),
    ('admin_academico', '/edu/efetuar_matricula/', 200),
    # O Secretário Acadêmico executa procedimentos: turma, matrícula, fechamento.
    ('secretario', '/edu/gerar_turmas/', 200),
    ('secretario', '/edu/efetuar_matricula/', 200),
    ('secretario', '/edu/fechar_periodo_letivo/', 200),
    ('secretario', '/edu/abrir_periodo_letivo/', 200),
    ('secretario', '/admin/edu/diretoria/add/', 403),
    # O professor só alcança o próprio diário — nem catálogo, nem procedimento.
    ('professor', '/admin/edu/cursocampus/add/', 403),
    ('professor', '/edu/gerar_turmas/', 403),
    ('professor', '/edu/efetuar_matricula/', 403),
    ('professor', '/edu/fechar_periodo_letivo/', 403),
    ('professor', '/edu/meus_diarios/', 200),
    # Achado a confirmar com o negócio: o professor NÃO tem `edu.view_diario`, então a
    # tela de diário da secretaria lhe é negada mesmo nos diários em que ele leciona. A PK
    # fixa não fragiliza o teste: o `permission_required` roda antes do `get_object_or_404`,
    # então o 403 independe de o diário 1 existir.
    ('professor', '/edu/diario/1/', 403),
    # O Coordenador de Curso acompanha e ainda pode efetuar matrícula direta (200), mas
    # não fecha período. Este 200 é um achado a confirmar com o negócio: a feature 004
    # descreve a matrícula institucional como ação do Secretário Acadêmico.
    ('coordenador_curso', '/edu/efetuar_matricula/', 200),
    ('coordenador_curso', '/edu/fechar_periodo_letivo/', 403),
]


@pytest.mark.parametrize(('papel', 'rota', 'status'), MATRIZ)
def test_fronteira_de_acesso(logado_edu, edu_seed, papel, rota, status):
    page = logado_edu(papel)
    resposta = page.goto(rota)
    assert resposta.status == status, f'{papel} em {rota}: esperado HTTP {status}, veio {resposta.status}'
