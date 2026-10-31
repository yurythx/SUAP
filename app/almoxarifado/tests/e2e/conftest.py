"""Substrato dos e2e do almoxarifado: seed do módulo e servidores com grupo.

O módulo não tem mais ``features/``: o behave dele foi removido ao converter a suíte para o
**modo 2**, em que a unidade de cobertura é a rota — o gate é
``bin/scripts/paridade_e2e.py almoxarifado --rotas`` — e a rastreabilidade de cada arquivo é a sua
docstring de módulo.

O módulo é inteiramente governado por **grupos** (16 deles em ``permissions.yaml``, e o
``menu.yaml`` usa ``groups_required`` na maioria das telas). Daí a fixture ``servidores_almox``, que cria por
factories (#17486) os servidores de ``PAPEIS`` na árvore A0/B0 (campi) → A1/B1/B2.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest almoxarifado/tests/e2e
"""

from __future__ import annotations

import pytest

# Traz as fixtures de browser/banco (`logado`, `live_server`, `e2e_seed`, e os overrides
# de `_django_db_helper`/`django_db_modify_db_settings`). Precisa ser star-import em
# conftest: é a precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login, setor

# (matrícula, grupo, sigla do setor) — subconjunto do step `os usuarios do Almoxarifado`
# que estes fluxos realmente exercitam. A árvore (A0…B2) é a de `_arvore`.
PAPEIS = {
    'CoordDeAlmoxSiste': ('Coordenador de Almoxarifado Sistêmico', 'A0'),
    'OperadDeAlmoxa': ('Operador de Almoxarifado', 'B0'),
    'ContadorAdministra': ('Contador Administrador', 'B2'),
    'GereDoCataDeMate': ('Gerenciador do Catálogo de Materiais', 'A1'),
    'AuditorAlmox': ('Auditor', 'B1'),
    # Só o grupo `Servidor` (que o `save` do servidor já dá): a linha de base do módulo.
    'ServidorSemGrupo': ('Servidor', 'A1'),
}


# Rotas que não viram teste. Cada motivo é uma condição verificável no código.
#
# As remoções e os estornos **mudam estado por GET** (nenhuma tem ``require_POST``): visitá-las no
# smoke apagaria item de empenho, entrada ou requisição do seed, que as outras suítes compartilham.
# O achado está registrado no MR; travar um teste nelas seria endossar o comportamento.
ROTAS_DISPENSADAS = {
    '/almoxarifado/ajax/get_itens_empenho/': (
        'endpoint AJAX consumido por POST da tela de entrada de compra (`almoxarifado/templates/entrada_compra.html:93-108`) '
        'e sem `require_POST`: um GET levanta `MultiValueDictKeyError` (500).'
    ),
    '/almoxarifado/atualizar_movimentacoes/<str:uo_sigla>/<int:material>/': (
        'ação de recálculo chamada por GET; com o estoque que o seed e as factories criam estoura '
        '`strptime() argument 1 must be str, not None` — o recálculo percorre movimentações com data nula. Achado do MR.'
    ),
    '/almoxarifado/atualizar_valor_medio/<str:uo_sigla>/<int:material>/': 'idem `atualizar_movimentacoes`: recálculo por GET, 500 com data nula na movimentação.',
    '/almoxarifado/capa_pagamento_pdf/<int:entrada_id>/': (
        'PDF da capa de pagamento exige `entrada.processo`; a entrada que as fixtures criam não tem processo e a view estoura `AttributeError`.'
    ),
    '/almoxarifado/empenhoconsumo/<int:id_empenhoconsumo>/remover/': (
        '**remove o item de empenho por GET** (`empenhoconsumo_remover` não tem `require_POST`): o smoke apagaria dado do seed.'
    ),
    '/almoxarifado/empenhopermanente/<int:id_empenhopermanente>/remover/': (
        '**remove o item de empenho permanente por GET** (mesma view sem `require_POST`).'
    ),
    '/almoxarifado/entrada/<int:entrada_id>/remover/': '**remove a entrada por GET** (`entrada_remover` sem `require_POST`).',
    '/almoxarifado/entrada_item_estornar/<str:tipo_entrada>/<int:item_id>/': (
        '**estorna o item por GET**: mexe em saldo de estoque (`entrada_item_estornar` sem `require_POST`).'
    ),
    '/almoxarifado/entrada_inventarios_pdf/<int:entrada_id>/': (
        'PDF dos inventários da entrada exige fornecedor (`entrada.vinculo_fornecedor.pessoa`), que a factory de entrada não monta → '
        '`AttributeError`.'
    ),
    '/almoxarifado/entrada_pdf/<int:entrada_id>/': 'idem `entrada_inventarios_pdf`: o PDF da entrada exige fornecedor que as fixtures não criam.',
    '/almoxarifado/requisicao/<str:tipo>/<int:requisicao_id>/remover/': '**remove a requisição por GET** (`requisicao_remover` sem `require_POST`).',
    '/almoxarifado/requisicao_resposta/<str:tipo>/<int:objeto_id>/': (
        'endpoint POST de resposta à requisição (`requisicao_resposta` lê `request.POST` e chama `avaliar`); o fluxo é coberto '
        'por `test_requisicoes.py`.'
    ),
    '/almoxarifado/requisicao_uo_pedido/': (
        'POST-only sem `require_POST`: um GET levanta `MultiValueDictKeyError` (500). O fluxo é coberto por `test_requisicoes.py`.'
    ),
}


def _arvore():
    """``{sigla: Setor}``: campi A0 e B0 (com UO de tipo campus), A1 sob A0, B1 e B2 sob B0."""
    a0, b0 = campus('A0'), campus('B0')
    return {'A0': a0, 'B0': b0, 'A1': setor('A1', a0), 'B1': setor('B1', b0), 'B2': setor('B2', b0)}


@pytest.fixture(scope='session')
def almox_seed(e2e_seed):
    """Seed do módulo: o que o behave carregava por ``almoxarifado/features/test_initial_data``.

    O arquivo veio para ``almoxarifado/tests/e2e/seed.py`` na remoção do behave (era
    behave-free: só ``get_or_create``, sem ``@given``) e é chamado direto daqui.
    Idempotente — o próprio arquivo usa ``get_or_create``.

    O ``PlanoContasAlmox`` que as telas de Elemento de Despesa exigem NÃO precisa ser
    criado: já vem do ``loaddata initial_data`` dos catálogos (``descricao`` é unique, e
    tentar criar estoura ``IntegrityError``).
    """
    from almoxarifado.tests.e2e import seed as seed_almox

    seed_almox.initial_data(verbosity=0)


@pytest.fixture(scope='session')
def servidores_almox(almox_seed) -> dict:
    """Cria TODOS os servidores de ``PAPEIS`` de uma vez, antes de qualquer request.

    Eager de propósito. Criar o vínculo de grupo sob demanda, no meio da sessão, dá
    resultado dependente de ordem: o SUAP resolve permissão com cache por processo, então
    uma tela que já respondeu 403 para o usuário continua 403 mesmo depois de ele entrar no
    grupo. Observado na prática — a mesma URL deu 403 e depois 200 conforme o momento em
    que o grupo foi atribuído. Criando tudo antes do primeiro acesso, não há cache negativo
    para invalidar.
    """
    arvore = _arvore()
    return {
        matricula: servidor_com_login(matricula, arvore[sigla], grupos=[grupo], staff=True, pessoa_fisica__nome=matricula)
        for matricula, (grupo, sigla) in PAPEIS.items()
    }


@pytest.fixture
def almoxarifado_a0(almox_seed):
    """``(uo, setor, material)`` do campus A0, com estoque suficiente para uma saída.

    Credita estoque via o domínio (item de empenho → entrada), que é como o behave fazia,
    porque a tela de entrada depende de encadeamento que ela também não cobria.
    Idempotente: só credita quando o saldo está baixo.
    """
    from almoxarifado.models import MaterialConsumo
    from almoxarifado.tests.factories import (
        EmpenhoConsumoFactory,
        EmpenhoFactory,
        EntradaFactory,
        MaterialEstoqueFactory,
        MovimentoAlmoxEntradaTipoFactory,
        MovimentoAlmoxSaidaTipoFactory,
    )
    from rh.models import UnidadeOrganizacional

    setor_a0 = campus('A0')
    uo = UnidadeOrganizacional.objects.suap().get(setor=setor_a0)
    material = MaterialConsumo.objects.get(nome='Material de Consumo')

    MovimentoAlmoxEntradaTipoFactory(nome='entrada')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_user_material')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_uo_material')

    estoque = MaterialEstoqueFactory(material=material, uo=uo)
    if estoque.quantidade < 10:
        # Empenho DEDICADO a esta fixture, não o `20193012RE` do seed: o `test_entradas`
        # cria um item nele com quantidade pequena, e quem rodasse depois tentaria receber
        # mais do que o pendente ("A quantidade informada (50) é maior que a pendente (9)").
        # Compartilhar recurso mutável entre testes é dependência de ordem.
        item = EmpenhoConsumoFactory(empenho=EmpenhoFactory(numero='2019NE000777'), material=material)

        # A suíte não dá flush, então o saldo empenhado vai sendo consumido a cada run:
        # recompõe antes de receber, em vez de assumir que ainda há folga.
        pendente = (item.qtd_empenhada or 0) - (item.qtd_adquirida or 0)
        if pendente < 50:
            item.qtd_empenhada = (item.qtd_empenhada or 0) + 5000
            item.save()

        # `efetuar_entrada` fica imperativo de propósito: é operação de domínio (move saldo),
        # não criação de linha, e é ela que mantém o invariante de estoque.
        item.efetuar_entrada(EntradaFactory(uo=uo), 50)
        estoque.refresh_from_db()

    return uo, setor_a0, material


@pytest.fixture
def requisicao_pendente(almoxarifado_a0, servidores_almox):
    """Devolve ``(requisicao, item)`` NOVOS a cada teste, pendentes de atendimento.

    Não usa ``get_or_create``: uma requisição atendida deixa de estar pendente, então
    reaproveitá-la entre testes (ou entre runs, já que a suíte não dá flush) faria o teste
    seguinte encontrar a requisição já respondida.
    """
    from almoxarifado.tests.factories import RequisicaoAlmoxUserFactory, RequisicaoAlmoxUserMaterialFactory

    uo, setor_a0, material = almoxarifado_a0
    requisicao = RequisicaoAlmoxUserFactory(
        uo_fornecedora=uo,
        vinculo_solicitante=servidores_almox['CoordDeAlmoxSiste'].get_vinculo(),
        setor_solicitante=setor_a0,
    )
    item = RequisicaoAlmoxUserMaterialFactory(requisicao=requisicao, material=material, qtd=3)
    return requisicao, item


@pytest.fixture
def logado_almox(logado, servidores_almox):
    """``(matricula) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado_almox(matricula: str):
        assert matricula in servidores_almox, f'papel desconhecido: {matricula}; declare em PAPEIS'
        return logado(matricula)

    return _logado_almox
