"""Substrato dos e2e do Demandas: replay ORM e oito papéis.

A origem do seed é o replay ORM das quatro features que o módulo tinha no behave (as antigas
``demandas/features/``): ``semear_base()`` fornece catálogos e permissões; ``seed.py`` monta a árvore (DIAC/CEN, DIAC/CZN) e
acrescenta os oito servidores da feature (demandante, analista, desenvolvedor, dois servidores
comuns, o coordenador de TI, o recebedor de demandas e o visualizador), a área de atuação com a
tag relacionada e o cadastro de analistas/desenvolvedores. Os papéis são criados de forma eager
antes da primeira request para não depender do cache de permissões.

**Sem relógio congelado**, ao contrário do ``saude``. O behave fixava datas nas tabelas dos
formulários (previsão, conclusão), mas o domínio do Demandas não vive numa data: o que depende
de "hoje" são os atrasos dos relatórios. Congelar aqui tem um efeito colateral medido — o
``HistoricoSituacao`` ordena por ``data_hora`` (``eh_ultimo_historico``), e o congelamento
**reinicia** o relógio a cada teste, então o histórico criado num teste pode ficar com
``data_hora`` menor que o do teste anterior: o último histórico por id deixa de ser o último
por data e a tela de visualização estoura em ``data_historico_posterior.date()``. Com o relógio
real, ``auto_now_add`` é monotônico com o id, como em produção.

Rodar (invocação separada da suíte unitária)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest demandas/tests/e2e --reuse-db
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import pytest
from playwright.sync_api import BrowserContext, Page

from djtools.e2e_fixtures import *  # noqa: F403

if TYPE_CHECKING:
    from comum.models import User

PAPEIS = {
    'demandante': '105001',
    'analista': '105002',
    'desenvolvedor': '105003',
    'servidor': '105004',
    'servidor2': '105005',
    'coordenador_ti': '105006',
    'recebedor': '105007',
    'visualizador': '105008',
}


@pytest.fixture(scope='session')
def demandas_seed(e2e_seed: None) -> None:
    """Monta, sem flush, o replay idempotente do domínio Demandas."""
    from demandas.tests.e2e import seed

    seed.montar()


@pytest.fixture(scope='session')
def papeis(demandas_seed: None) -> dict[str, User]:
    """Resolve todos os atores antes da primeira request para aquecer permissões corretamente."""
    from comum.models import User

    usuarios = {matricula: User.objects.filter(username=matricula).first() for matricula in PAPEIS.values()}
    ausentes = [matricula for matricula, usuario in usuarios.items() if usuario is None]
    assert not ausentes, f'papéis ausentes no seed do Demandas: {ausentes}'
    return {matricula: cast('User', usuario) for matricula, usuario in usuarios.items()}


@pytest.fixture
def logado_demandas(
    new_context: Callable[[], BrowserContext], login_ui: Callable[[Page, str], Page], papeis: dict[str, User]
) -> Callable[[str], Page]:
    """Devolve ``(papel) -> Page`` com login real (o seed não dá flush, então sem ``storage_states``)."""

    def _logado(papel: str) -> Page:
        matricula = PAPEIS.get(papel, papel)
        assert matricula in papeis, f'papel desconhecido: {papel!r}; declare em PAPEIS'
        contexto = new_context()
        pagina = contexto.new_page()
        pagina.on('dialog', lambda dialog: dialog.accept())
        # O tema de desenvolvimento (que só existe com DEBUG=True) atrapalha o clique em duas
        # frentes: a barra `#debug` do rodapé (26 px, `position: fixed`) e os avisos do `dev.css`
        # — que, em `body.debug`, dão `margin-top: 4rem` e um `::after` a toda tabela sem
        # `<caption>`, e esse pseudo-elemento passa a interceptar o clique do botão logo acima
        # (`<table class="table sm"> intercepts pointer events`). Tirar a classe e a barra de
        # cada documento devolve a página ao que o usuário vê em produção, sem mexer no
        # `settings.DEBUG` — que precisa continuar ligado para a página de erro do Django ser
        # legível quando um teste falha.
        pagina.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => {"
            "  document.body.classList.remove('debug');"
            "  document.querySelector('#debug')?.remove();"
            '})'
        )
        return login_ui(pagina, matricula)

    return _logado


# O gate lê este dicionário como literal. Só ficam aqui as rotas que o modo 2 não cobre por
# construção: chamada a API externa, ação que muda estado por GET exercitada por botão ou
# ícone, download/PDF/planilha, impressão/preview e rota órfã (sem ponto de entrada em tela).
ROTAS_DISPENSADAS: dict[str, str] = {
    '/demandas/analistadesenvolvedor/<int:pk>/': 'ciclo de vida da IDE do analista no GitLab (cria/atualiza pipeline, dispara job, lê log): chamada a API externa.',
    '/demandas/ambientehomologacao/<int:pk>/': 'ciclo de vida do container de homologação no GitLab (pipeline, branch, job, log): chamada a API externa.',
    '/demandas/acessar_ambiente_via_demanda/<int:pk>/<int:demanda_pk>/': 'dispara o job que cria o container de homologação no GitLab: chamada a API externa.',
    '/demandas/executar_comando_ambiente_homologacao/<int:pk>/': 'lê o log do job do container de homologação no GitLab: chamada a API externa.',
    '/demandas/criar_issue_gitlab/<int:especificao_id>/': 'cria a issue da especificação no GitLab: chamada a API externa.',
    '/demandas/painel_forca_trabalho_desenvolvedor/<int:desenvolvedor_id>/': 'consulta as issues e milestones do desenvolvedor no GitLab: chamada a API externa.',
    '/demandas/acompanhamento_demandas_pdf/': 'saída em PDF do acompanhamento, sem tela para asserir além do content-type.',
    '/demandas/relatorio/geral/': 'planilha XLSX de demandas por tags, baixada por POST; sem tela para asserir.',
    '/demandas/dod/<int:demanda_id>/<int:dod_id>/fechar/': 'rota órfã: nenhum template ou botão aponta para ela (o fluxo atual é `dod/<pk>/solicitar_aprovacao_modificacoes/`).',
}
