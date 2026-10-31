"""Substrato da rodada de geração da doc de usuário do ``almoxarifado``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

Reusa por inteiro o substrato dos e2e do módulo (``almoxarifado/tests/e2e/conftest.py``):
``almox_seed``, ``servidores_almox`` (os seis papéis por grupo), ``almoxarifado_a0`` (estoque
no campus A0) e ``logado_almox``. Os dois star-imports são obrigatórios e nesta ordem:

1. ``djtools.e2e_fixtures`` traz os nomes **privados** (``_django_db_helper``,
   ``_exige_banco_de_e2e``), que ``import *`` do conftest do e2e não reexportaria — é a
   armadilha documentada em ``djtools/e2e_fixtures.py``;
2. o conftest do e2e traz as fixtures do módulo.

O que a doc precisa e o e2e não tinha fica no ``doc_seed`` de sessão: um solicitante e um
doador com nome legível (no e2e as matrículas são os nomes), o coordenador do campus B0
(destino da transferência intercampi) e estoque no B0 — sem ele o autocomplete de material
da transferência não acha nada.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
      TEST_DATABASE_NAME=test_suap_doc_e2e_almoxarifado DJANGO_SETTINGS_MODULE=suap.settings_test \\
      .venv/bin/python -m pytest -m doc --create-db almoxarifado/tests/doc/
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import servidor_com_login
from almoxarifado.tests.e2e.conftest import *  # noqa: F403
from almoxarifado.tests.e2e.conftest import _arvore

DESTINO = Path(settings.BASE_DIR) / 'almoxarifado' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Matrículas na faixa 140xxx: a 158xxx é do projetos_ensino, que divide o banco no job de doc.
SOLICITANTE = {'matricula': '140001', 'nome': 'Joana Souza'}
COORDENADOR_B0 = {'matricula': '140002', 'nome': 'Homero Bento'}
DOADOR = {'nome': 'Moveis Escolares LTDA', 'cnpj': '11.222.333/0001-81'}


def credito_de_estoque(material, uo, quantidade=50):
    """Crédito de saldo pelo domínio (item de empenho → entrada), como o e2e faz.

    ``EntradaFactory``/``MaterialEstoqueFactory`` criam a linha; quem move o saldo é
    ``EmpenhoConsumo.efetuar_entrada`` — é ele que mantém o invariante de estoque.
    """
    from almoxarifado.tests.factories import (
        EmpenhoConsumoFactory,
        EmpenhoFactory,
        EntradaFactory,
        MaterialEstoqueFactory,
        MovimentoAlmoxEntradaTipoFactory,
        MovimentoAlmoxSaidaTipoFactory,
    )

    MovimentoAlmoxEntradaTipoFactory(nome='entrada')
    MovimentoAlmoxEntradaTipoFactory(nome='requisicao_uo_material')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_user_material')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_uo_material')

    estoque = MaterialEstoqueFactory(material=material, uo=uo)
    if estoque.quantidade < quantidade:
        # Empenho dedicado à doc: o item precisa de saldo pendente para a entrada.
        item = EmpenhoConsumoFactory(empenho=EmpenhoFactory(numero='2020NE000158'), material=material)
        pendente = (item.qtd_empenhada or 0) - (item.qtd_adquirida or 0)
        if pendente < quantidade:
            item.qtd_empenhada = (item.qtd_empenhada or 0) + 5000
            item.save()
        item.efetuar_entrada(EntradaFactory(uo=uo), quantidade)
        estoque.refresh_from_db()
    return estoque


@pytest.fixture(scope='session')
def doc_seed(servidores_almox, almox_seed):
    """Servidores nomeados da doc, processo do empenho, doador e estoque no campus B0.

    Sessão e eager como o ``servidores_almox``: o cache de permissão é por processo, então
    papel criado depois do primeiro login continuaria sem acesso.
    """
    from almoxarifado.models import MaterialConsumo
    from protocolo.models import Processo
    from rh.models import UnidadeOrganizacional
    from rh.tests.factories import PessoaJuridicaFactory

    arvore = _arvore()
    solicitante = servidor_com_login(
        SOLICITANTE['matricula'],
        arvore['A0'],
        grupos=['Servidor'],
        staff=True,
        pessoa_fisica__nome=SOLICITANTE['nome'],
    )
    coord_b0 = servidor_com_login(
        COORDENADOR_B0['matricula'],
        arvore['B0'],
        grupos=['Coordenador de Almoxarifado'],
        staff=True,
        pessoa_fisica__nome=COORDENADOR_B0['nome'],
    )
    doador = PessoaJuridicaFactory(nome=DOADOR['nome'], cnpj=DOADOR['cnpj'])
    processo, _ = Processo.objects.get_or_create(
        assunto='Assunto da Doc do Almoxarifado',
        defaults={'vinculo_cadastro': solicitante.get_vinculo(), 'tipo': 1, 'setor_origem': solicitante.setor},
    )
    material = MaterialConsumo.objects.get(nome='Material de Consumo')
    uo_b0 = UnidadeOrganizacional.objects.suap().get(setor=arvore['B0'])
    credito_de_estoque(material, uo_b0)
    return {
        'solicitante': solicitante,
        'coord_b0': coord_b0,
        'doador': doador,
        'processo': processo,
        'material': material,
        'uo_b0': uo_b0,
    }
