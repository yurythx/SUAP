"""Substrato da rodada de geração da doc de usuário do ``patrimonio``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma.

O módulo NÃO tem ``tests/e2e/`` nem `features/` (o behave dele não existe), então o seed é
montado aqui mesmo, com as factories do próprio módulo
(``patrimonio/tests/factories.py``) sobre o ``e2e_seed`` do ``djtools``. As tabelas de
referência (status do tombamento, tipos de movimento, tipos de entrada) vêm do
``_garantir_dados_de_referencia`` do conftest unitário do módulo — mesma carga de produção.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
      TEST_DATABASE_NAME=test_suap_doc_e2e_patrimonio DJANGO_SETTINGS_MODULE=suap.settings_test \\
      .venv/bin/python -m pytest -m doc --create-db patrimonio/tests/doc/
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login

DESTINO = Path(settings.BASE_DIR) / 'patrimonio' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Matrículas na faixa 159xxx, fora das faixas dos módulos irmãos que dividem o banco no CI.
# Diego (destino da transferência) e Rita (as PAs) ficam no campus A0 de propósito: o
# deferimento entre campi é bloqueado a partir do dia `dia_inicio_bloqueio` do mês, e a doc
# precisa de um roteiro que rode em qualquer data.
PAPEIS = {
    'coord_a0': ('159001', 'Carla Patrimônio', ['Coordenador de Patrimônio']),
    'operador_a0': ('159002', 'Otávio Operador', ['Operador de Patrimônio']),
    'servidor_a0': ('159003', 'Sofia Servidora', []),
    'coord_destino': ('159004', 'Diego Destino', ['Coordenador de Patrimônio']),
}


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Campus A0/B0, os papéis da doc, catálogo e os tombamentos de cada tarefa.

    Oito inventários de uma única entrada permanente: **2 pendentes** (tarefa da carga) e
    **5 ativos** sob a carga da Sofia (um para cada tarefa seguinte — consulta,
    transferência, baixa, cautela e conferência —, para uma tarefa não consumir o dado da
    outra), além de um **baixado** para os relatórios. A sala é do campus A0 e recebe os
    bens da conferência e da consulta.
    """
    from comum.models import Configuracao, Vinculo
    from comum.tests.factories import PredioFactory, SalaFactory
    from patrimonio.models import Inventario, InventarioStatus
    from patrimonio.tests.conftest import _garantir_dados_de_referencia
    from patrimonio.tests.factories import (
        BaixaTipoFactory,
        CategoriaMaterialPermanenteFactory,
        EntradaPermanenteFactory,
        PlanoContasFactory,
    )
    from rh.models import UnidadeOrganizacional

    _garantir_dados_de_referencia()
    a0 = campus('A0')
    uo_a0 = UnidadeOrganizacional.objects.suap().get(setor=a0)
    # Com `--reuse-db`, o `servidor_com_login` reencontra o servidor de rodadas anteriores e
    # ignora o setor novo (é get-or-create por matrícula): realinha o vínculo dos papéis da
    # doc ao campus A0, senão uma rodada antiga deixa o Diego no B0 e a transferência vira
    # "entre diferentes campi" — bloqueada a partir do dia 25.
    from rh.models import Servidor

    for matricula, _, _ in PAPEIS.values():
        existente = Servidor.objects.filter(matricula=matricula).first()
        if existente is not None:
            Servidor.objects.filter(pk=existente.pk).update(setor=a0)
            Vinculo.objects.filter(pk=existente.get_vinculo().pk).update(setor=a0)
    # Configuração do módulo que produção cadastra pela tela de Configuração: sem o dia de
    # bloqueio, `ver_periodo_deferimento` estoura no `int(None)` e a requisição vira 500.
    Configuracao.objects.get_or_create(app='patrimonio', chave='dia_inicio_bloqueio', defaults={'valor': '25'})
    servidores = {
        papel: servidor_com_login(matricula, a0, grupos=grupos, staff=True, pessoa_fisica__nome=nome)
        for papel, (matricula, nome, grupos) in PAPEIS.items()
    }

    plano = PlanoContasFactory(codigo='0100', descricao='PLANO DE CONTAS DE BENS MÓVEIS')
    categoria = CategoriaMaterialPermanenteFactory(codigo='0100', nome='EQUIPAMENTOS DE INFORMÁTICA', plano_contas=plano)
    item = EntradaPermanenteFactory(
        categoria=categoria,
        descricao='Notebook Dell Latitude 3420',
        valor=4500,
        qtd=8,
        entrada__uo=uo_a0,
    )
    sala = SalaFactory(nome='Laboratório de Informática', predio=PredioFactory(nome=f'Prédio Doc {uuid4().hex[:6]}', uo=uo_a0))
    BaixaTipoFactory(nome='doacao')

    inventarios = list(item.inventario_set.order_by('numero'))
    papeis_dos_ativos = ['consulta', 'transferencia', 'baixa', 'cautela', 'conferencia']
    ativos = {}
    for papel, inventario in zip(papeis_dos_ativos, inventarios[2:7], strict=True):
        Inventario.objects.filter(pk=inventario.pk).update(
            status=InventarioStatus.ATIVO(),
            responsavel_vinculo=servidores['servidor_a0'].get_vinculo(),
            sala=sala,
            estado_conservacao='bom',
        )
        ativos[papel] = Inventario.objects.get(pk=inventario.pk)
    Inventario.objects.filter(pk=inventarios[7].pk).update(status=InventarioStatus.BAIXADO())

    return {
        'campi': {'a0': a0},
        'servidores': servidores,
        'plano_contas': plano,
        'categoria': categoria,
        'sala': sala,
        'entrada': item.entrada,
        'item': item,
        'pendentes': [Inventario.objects.get(pk=inventario.pk) for inventario in inventarios[:2]],
        'ativos': ativos,
    }
