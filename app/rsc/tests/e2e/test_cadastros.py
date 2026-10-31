"""Cadastros da CPPD (unidades, tipos de RSC e diretrizes, que eram as três ``.feature`` do behave) e as listagens de admin do menu.

O gate ``--rotas`` não enxerga ``/admin/``: as listagens provam que cada tela do menu abre para o papel que a
libera e mostra um objeto do seed ou criado no próprio teste, não só o rótulo da página.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _unidade(nome: str) -> tuple[str, list[tuple[str, ...]], dict[str, Any]]:
    return '/admin/rsc/unidade/add/', [('Nome', 'texto', nome), ('Sigla', 'texto', 'E2E')], {'nome': nome}


def _tipo_rsc(nome: str) -> tuple[str, list[tuple[str, ...]], dict[str, Any]]:
    return '/admin/rsc/tiporsc/add/', [('Nome', 'texto', nome), ('Categoria', 'texto', 'docente')], {'nome': nome}


def _diretriz(nome: str) -> tuple[str, list[tuple[str, ...]], dict[str, Any]]:
    campos = [
        ('Tipo rsc', 'autocomplete', 'RSC-II'),
        ('Nome', 'texto', nome),
        ('Descricao', 'textarea', 'Diretriz cadastrada no e2e.'),
        ('Valor do peso', 'texto', '2'),
        ('Teto', 'texto', '10'),
    ]
    return '/admin/rsc/diretriz/add/', campos, {'nome': nome, 'tipo_rsc__nome': 'RSC-II', 'peso': 2}


@pytest.mark.parametrize('cadastro', [_unidade, _tipo_rsc, _diretriz], ids=['unidade', 'tipo_rsc', 'diretriz'])
def test_cppd_cadastra(logado_rsc: Callable[[str], Page], rsc_seed: dict, cadastro: Callable[[str], tuple]) -> None:
    from django.apps import apps

    nome = f'E2E {uuid4().hex[:8]}'
    url, campos, filtro = cadastro(nome)
    modelo = apps.get_model('rsc', url.split('/')[3])
    tela = Tela(logado_rsc('membro')).ir(url)
    tela.preencher_formulario(campos)
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert modelo.objects.filter(**filtro).exists(), 'a UI disse que salvou, mas não persistiu'


# (papel, listagem, texto de um objeto do seed que a listagem tem de mostrar)
LISTAGENS = [
    ('membro', '/admin/rsc/criterio/', 'Critério E2E RSC-II'),
    ('membro', '/admin/rsc/diretriz/', 'Diretriz E2E RSC-II'),
    ('membro', '/admin/rsc/tiporsc/', 'RSC-III'),
    ('membro', '/admin/rsc/unidade/', '>UN<'),
    ('membro', '/admin/rsc/parametropagamento/', '100,0'),
    ('membro', '/admin/rsc/configuracaorsc/', 'CONFIG_RSC'),
]


@pytest.mark.parametrize(('papel', 'url', 'texto'), LISTAGENS, ids=[linha[1].split('/')[3] for linha in LISTAGENS])
def test_listagem_admin(logado_rsc: Callable[[str], Page], rsc_seed: dict, papel: str, url: str, texto: str) -> None:
    resposta = Tela(logado_rsc(papel)).buscar(url)
    assert resposta.status == 200, f'{url}: HTTP {resposta.status}'
    assert texto in resposta.text(), f'{url}: {texto!r} ausente'


def test_listagens_de_processos(
    logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]
) -> None:
    """Meus Processos (docente), Processos pendentes e Avaliadores nos Processos (CPPD) mostram o processo novo."""
    from rsc.models import ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD)
    banca(processo)
    for papel, url, texto in (
        ('docente', '/admin/rsc/processorsc/?tab=tab_meus_processos', f'/rsc/abrir_processo_rsc/{processo.pk}/'),
        ('membro', '/admin/rsc/processorsc/?tab=tab_processos_pendentes', f'href="/rsc/validar_processorsc/{processo.pk}"'),
        ('membro', f'/admin/rsc/processoavaliador/?processo__id__exact={processo.pk}', rsc_seed['avaliador'].nome),
    ):
        resposta = Tela(logado_rsc(papel)).buscar(url)
        assert resposta.status == 200, f'{url}: HTTP {resposta.status}'
        assert texto in resposta.text(), f'{url}: {texto!r} ausente'
