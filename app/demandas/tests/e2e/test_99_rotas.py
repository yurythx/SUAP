"""Smoke de rota do Demandas (modo 2: a unidade é a tela).

Abre em lote as telas de leitura e de formulário — as que renderizam sem mudar estado — com
`Tela.buscar` (GET sem renderizar). As ações, os downloads e as telas que dependem da API do
GitLab ficam em `ROTAS_DISPENSADAS`, no conftest, com o motivo.

Os alvos (demanda da cadeia, sugestão e atualização) são resolvidos do que `test_01` a
`test_07` criaram. As telas restritas a outros papéis (áreas de atuação, prioridades da área,
gerenciamento de demandantes) ficam fora do smoke: cada uma é coberta com o papel certo. A falha lista **todas** as rotas quebradas de
uma vez, e as telas com defeito de produto conhecido ficam fora por nome: `demandas_listagem`
(renderiza o template default, sem conteúdo, porque a view procura `demandas_listagem.html` e
o arquivo é `listagem_demandas.html`) e `especificacao_tecnica` (guarda invertida, só abre em
demanda terminal) — as duas estão cobertas por teste próprio.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Sem parâmetro: listagens, relatórios e painéis que renderizam tela.
ROTAS_SEM_PARAMETRO = [
    '/demandas/demandas/',
    '/demandas/indicadores/',
    '/demandas/glossario/',
    '/demandas/atualizacoes/',
    '/demandas/acompanhamento_demandas/',
    '/demandas/relatorio_atividades_reprimidas/',
    '/demandas/painel_forca_trabalho/',
    '/demandas/ajax/get_tags_area/',
]

# Com parâmetro: detalhe e formulários sobre os objetos da cadeia.
ROTAS_COM_ALVO = [
    '/demandas/visualizar/{demanda}/',
    '/demandas/visualizar/{demanda}/exportar_markdown/',
    '/demandas/sugestao_melhoria/{sugestao}/',
    '/demandas/atualizacao/{atualizacao}/',
]


def _alvos() -> dict[str, int]:
    """Resolve os alvos da cadeia ou explica a dependência sequencial."""
    from demandas.models import AreaAtuacaoDemanda, Atualizacao, Demanda, SugestaoMelhoria, Tag

    demanda = Demanda.objects.filter(titulo='Demanda 1').first()
    sugestao = SugestaoMelhoria.objects.filter(titulo='Melhoria Tag Especial').first()
    atualizacao = Atualizacao.objects.filter(descricao='Atualização E2E').first()
    area = AreaAtuacaoDemanda.objects.filter(area__nome='Tecnologia da Informação').first()
    tag = Tag.objects.filter(nome='Tag Especial').first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    assert sugestao is not None, 'sugestão ausente: a cadeia é sequencial'
    assert atualizacao is not None, 'atualização ausente: o seed não criou a atualização do sistema'
    assert area is not None, 'a área de atuação precisa existir no seed'
    assert tag is not None, 'o módulo precisa existir no seed'
    return {
        'demanda': demanda.pk,
        'sugestao': sugestao.pk,
        'atualizacao': atualizacao.pk,
        'area': area.pk,
        'tag': tag.pk,
    }


def _abrir(tela: Tela, rotas: list[str], alvos: dict[str, int]) -> list[str]:
    """Percorre as rotas e devolve a lista de falhas, sem parar na primeira."""
    falhas = []
    for rota in rotas:
        url = rota.format_map(alvos)
        try:
            resposta = tela.buscar(url)
        except Exception as erro:
            falhas.append(f'{url} -> {type(erro).__name__}: {str(erro).splitlines()[0]}')
            continue
        if resposta.status == 200:
            continue
        if resposta.status in (301, 302):
            destino = resposta.headers.get('location', '')
            if 'login' in destino:
                falhas.append(f'{url} -> redirect para o login ({destino})')
            continue
        falhas.append(f'{url} -> HTTP {resposta.status}')
    return falhas


def test_rotas_abrem(logado_demandas: Callable[[str], Page]) -> None:
    """O analista abre, em lote, as telas de leitura e de formulário do módulo."""
    alvos = _alvos()
    tela = Tela(logado_demandas('analista'))
    falhas = _abrir(tela, ROTAS_SEM_PARAMETRO, alvos) + _abrir(tela, ROTAS_COM_ALVO, alvos)
    total = len(ROTAS_SEM_PARAMETRO) + len(ROTAS_COM_ALVO)
    assert not falhas, f'{len(falhas)} de {total} rotas não abriram:\n  ' + '\n  '.join(falhas)
