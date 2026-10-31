"""Matriz de permissão por **status HTTP**, medida no browser e não deduzida do YAML.

O módulo é governado por ``permissions.yaml`` e por dois métodos de domínio que olham o vínculo com
o chamado (``Chamado.pode_visualizar`` e ``Chamado.get_permissoes``). A regressão típica é uma
permissão a mais: um papel que passa a ver o chamado de outro, ou a tela de indicadores que abre
para quem não tem ``pode_ver_indicadores``.

Duas fronteiras de tipos diferentes aparecem aqui: a **permissão de grupo** (403 pela ausência da
permissão no decorator) e o **vínculo com o registro** (403 porque o usuário não é interessado nem
atendente do chamado). As duas dão o mesmo status, mas o motivo é outro — e é isso que os casos
nomeados dizem.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, criar_chamado, criar_contexto, nome_e2e, usuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def permissao(centralservicos_seed) -> SimpleNamespace:
    """Um chamado do ``supervisor`` (o servidor não é parte dele) e o contexto para as rotas."""
    contexto = criar_contexto(artigo_privado=True)
    chamado_de_outro = criar_chamado(contexto, interessado=usuario(PAPEIS['supervisor']))
    return SimpleNamespace(
        chamado_de_outro=chamado_de_outro.pk,
        artigo=contexto.artigo_privado.pk,
        servico=contexto.servico.pk,
    )


@pytest.fixture
def servicos_que_barram_a_abertura(centralservicos_seed) -> SimpleNamespace:
    """Os serviços em cada estado que ``_validar_abertura_de_chamado`` (views.py:410) recusa.

    São os três primeiros ``if`` da função: interno, inativo e fora do público do usuário. O quarto
    (``get_uo`` nulo) não é representável no e2e — o middleware ``usuario_sem_setor`` desloga o
    servidor cujo setor SUAP está sem campus antes de a view rodar — e é coberto por teste unitário
    em ``centralservicos/tests/test_chamados.py``.
    """
    from centralservicos.models import Servico
    from comum.models import Publico

    interno = criar_contexto()
    Servico.objects.filter(pk=interno.servico.pk).update(interno=True)

    inativo = criar_contexto()
    Servico.objects.filter(pk=inativo.servico.pk).update(ativo=False)

    restrito = criar_contexto()
    publico = Publico.objects.create(nome=nome_e2e('Público Alunos'), modelo_base=Publico.BASE_ALUNO)
    restrito.servico.publico_direcionado.add(publico)

    return SimpleNamespace(interno=interno.servico.pk, inativo=inativo.servico.pk, restrito=restrito.servico.pk)


# (rota, papel, status, motivo). O motivo fica na mensagem de falha: quando a matriz quebra, o
# relatório diz **qual** fronteira caiu.
#
# O lado "sem permissão" é sempre o ``servidor`` (ou um papel com permissão diferente da rota): o
# ``gestor`` e o ``supervisor`` NÃO servem para isso nesta suíte, porque o signal
# ``_sincronizar_grupo_atendente`` (``models.py:736``) concede o grupo ``Atendente da Central de
# Serviços`` a quem entra como atendente/responsável de um ``GrupoAtendimento`` — e os testes de
# cadastro fazem exatamente isso, na mesma sessão e sem flush. Afirmar 403 para o gestor aqui
# passaria numa execução isolada do arquivo e falharia na suíte inteira: dependência de ordem que o
# `parametrize` não pode ter.
CASOS = [
    ('/centralservicos/dashboard/', 'servidor', 403, 'Servidor não tem `change_chamado`'),
    ('/centralservicos/dashboard/', 'atendente', 200, 'O atendente tem `change_chamado`'),
    ('/centralservicos/listar_chamados_suporte/', 'servidor', 403, 'Servidor não tem `list_chamados_suporte`'),
    ('/centralservicos/listar_chamados_suporte/', 'atendente', 200, 'O atendente tem `list_chamados_suporte`'),
    ('/centralservicos/indicadores/', 'servidor', 403, 'Servidor não tem `pode_ver_indicadores`'),
    ('/centralservicos/indicadores/', 'atendente', 200, 'O atendente tem `pode_ver_indicadores`'),
    ('/centralservicos/chamado/{chamado_de_outro}/', 'servidor', 403, 'Servidor não é parte do chamado nem tem `change_chamado`'),
    ('/centralservicos/chamado/{chamado_de_outro}/', 'supervisor', 200, 'O supervisor é o interessado do chamado'),
    ('/centralservicos/chamado/{chamado_de_outro}/', 'atendente', 200, 'O atendente tem `change_chamado` e é do grupo do chamado'),
    ('/centralservicos/suspender_chamado/{chamado_de_outro}/', 'servidor', 403, 'Servidor não tem `suspend_chamado`'),
    ('/centralservicos/suspender_chamado/{chamado_de_outro}/', 'gestor', 403, 'Gestor não tem `suspend_chamado`'),
    ('/centralservicos/resolver_chamado/{chamado_de_outro}/', 'servidor', 403, 'Servidor não tem `solve_chamado`'),
    ('/centralservicos/baseconhecimento/aprovar/{artigo}/', 'servidor', 403, 'Servidor não tem `review_baseconhecimento`'),
    ('/centralservicos/baseconhecimento/aprovar/{artigo}/', 'supervisor', 302, 'O supervisor tem `review_baseconhecimento`'),
    ('/centralservicos/estatisticas_servico/{servico}/', 'servidor', 403, 'Servidor não está no escopo de serviços de nenhuma área'),
    ('/centralservicos/estatisticas_servico/{servico}/', 'gestor', 200, 'O gestor é o gestor da área do serviço'),
    ('/admin/comum/areaatuacao/', 'servidor', 403, 'Servidor não tem permissão de Área de Atuação'),
    ('/admin/comum/areaatuacao/', 'admin', 200, 'O administrador da central tem `comum.add_areaatuacao`'),
    ('/admin/centralservicos/baseconhecimento/', 'servidor', 403, 'Servidor não tem permissão de Base de Conhecimento'),
    ('/admin/centralservicos/baseconhecimento/', 'gestor', 200, 'O gestor tem `add_baseconhecimento`'),
    ('/admin/centralservicos/tarefa/', 'supervisor', 403, 'Supervisor não mantém o cadastro de tarefas'),
    ('/admin/centralservicos/tarefa/', 'gestor', 200, 'O gestor mantém o cadastro de tarefas'),
]


@pytest.mark.parametrize(('rota', 'papel', 'status_esperado', 'motivo'), CASOS, ids=[f'{caso[1]}-{caso[0]}' for caso in CASOS])
def test_permissao_por_status_http(logado_central, permissao, rota, papel, status_esperado, motivo):
    """Cada papel recebe o status da sua permissão — ``403`` quando a fronteira está de pé."""
    tela = Tela(logado_central(papel))
    resposta = tela.buscar(rota.format(**vars(permissao)))
    assert resposta.status == status_esperado, f'{rota} como {papel} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'


# Serviço em cada estado que barra a abertura, com o contraste de quem passa: o caso do serviço
# interno é o único em que o papel muda o desfecho (o atendente tem `change_chamado` e grupo na
# área). As negativas de serviço inativo e restrito valem para todo mundo.
CASOS_DE_ABERTURA = [
    ('interno', 'servidor', 403, 'Serviço interno exige `change_chamado` e grupo de atendimento da área'),
    ('interno', 'atendente', 200, 'O atendente tem a permissão e o grupo da área'),
    ('inativo', 'servidor', 403, 'Serviço inativo não abre para ninguém'),
    ('restrito', 'servidor', 403, 'Serviço restrito a um público do qual o servidor não faz parte'),
]


@pytest.mark.parametrize(
    ('qual', 'papel', 'status_esperado', 'motivo'),
    CASOS_DE_ABERTURA,
    ids=[f'{caso[1]}-{caso[0]}' for caso in CASOS_DE_ABERTURA],
)
def test_abertura_barrada_pelo_estado_do_servico(logado_central, servicos_que_barram_a_abertura, qual, papel, status_esperado, motivo):
    """As negativas de ``_validar_abertura_de_chamado`` são o que separa catálogo de permissão."""
    rota = f'/centralservicos/abrir_chamado/{getattr(servicos_que_barram_a_abertura, qual)}/'
    tela = Tela(logado_central(papel))
    resposta = tela.buscar(rota)
    assert resposta.status == status_esperado, (
        f'abertura de serviço {qual} como {papel} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'
    )
