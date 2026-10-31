"""Substrato dos e2e do frota (modo 2): relógio congelado em 25/11/2018 e os cinco papéis.

A unidade de cobertura é a **tela (rota)** — o gate é `paridade_e2e.py frota --rotas` em zero
descobertas. As `.feature` do behave serviram de fonte dos campos, papéis e datas, não de
contrato: não há `@pytest.mark.cenario`, e a rastreabilidade de cada arquivo é a sua docstring.
(Removidas do módulo no modo 2 — o histórico do git as guarda.)

O domínio vive em novembro de 2018: o agendamento da feature fixa `25/11/2018` e a saída/chegada
da viagem em `03`/`04/12/2018`. Congelar a sessão é o que faz a fila de "Viagens Agendadas"
enxergar o agendamento recém-deferido como futuro.

Rodar (invocação separada da suíte unitária)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest frota/tests/e2e --reuse-db
"""

from __future__ import annotations

from pathlib import Path

import pytest
from freezegun import freeze_time

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import Relogio, aquecer_urlconf

DATA_BASE = '25/11/2018'

# Apelido -> matrícula. Os nomes são os papéis da tabela da feature 001, não os próprios.
PAPEIS = {
    'coord_sistemico': '107001',
    'coord_frota': '107002',
    'agendador': '107003',
    'passageiro': '107004',
    'motorista': '107005',
}

_MODULO = Path(__file__).resolve().parents[2]
_RELOGIO = Relogio()


@pytest.fixture(scope='session')
def relogio():
    aquecer_urlconf()
    _RELOGIO.congelar(DATA_BASE)
    yield _RELOGIO
    _RELOGIO.descongelar()


def pytest_runtest_setup(item):
    _RELOGIO.retomar()


def pytest_runtest_teardown(item, nextitem):
    if nextitem is None or not nextitem.path.is_relative_to(_MODULO):
        _RELOGIO.suspender()


@pytest.fixture(autouse=True)
def data_do_modulo(request, relogio):
    relogio.congelar(getattr(request.module, 'DATA', DATA_BASE))
    yield
    relogio.descongelar()


@pytest.fixture(scope='session')
def frota_seed(e2e_seed, relogio):
    """Cadastros básicos (estacionamento, grupo/status de viatura, patrimônio) e os 5 papéis."""
    from frota.tests.e2e import seed

    seed.montar()
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def papeis(frota_seed):
    from comum.models import User

    return {m: User.objects.filter(username=m).first() for m in PAPEIS.values()}


@pytest.fixture
def logado_frota(new_context, login_ui, papeis):
    """``(papel) -> Page`` autenticada, com login real a cada teste (o relógio é de sessão)."""

    def _logado(papel: str):
        matricula = PAPEIS.get(papel, papel)
        assert matricula in papeis, f'papel desconhecido: {papel!r}'
        contexto = new_context()
        page = contexto.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        return login_ui(page, matricula)

    return _logado


# --- rotas dispensadas (gate `paridade_e2e.py frota --rotas`) --------------------------------
#
# Toda rota de `frota/urls.py` que não é aberta pelo smoke (`test_04_rotas.py`) está aqui, com o
# motivo. O gate lê este dicionário como literal (AST).
ROTAS_DISPENSADAS = {
    '/frota/editar_agendamento_deferido/<int:agendamento_id>/': 'edita um agendamento **deferido**; o smoke roda depois da cadeia, quando o agendamento já virou viagem finalizada e o guard recusa.',
    # Geração de arquivo / relatório em PDF ou planilha, sem asserção além do content-type.
    '/frota/pdf_requisicao/<int:viagem_id>/': 'gera o PDF da requisição de viagem; sem asserção além do content-type.',
    '/frota/baixar_notas_fiscais_servicos/': 'baixa as notas fiscais (download); sem tela.',
    # Ações que mudam estado por GET (o fluxo as exercita pelos botões, na janela certa).
    '/frota/autorizar_agendamento/<int:agendamento_id>/<str:opcao>/': 'autoriza/nega por GET; o fluxo de avaliação a exercita pelo botão.',
    '/frota/saida_viagem/<int:resp_agendamento_id>/': 'registra a saída (POST do formulário); o fluxo a exercita pelo botão.',
    '/frota/chegada_viagem/<int:viagem_id>/': 'registra a chegada; o fluxo a exercita pelo botão.',
    '/frota/validar_saida/<int:viagem_id>/': 'valida a saída por GET; abre só na tela de viagem.',
    '/frota/validar_chegada/<int:viagem_id>/': 'valida a chegada por GET; abre só na tela de viagem.',
    '/frota/validar_ordem_abastecimento/<int:ordem_id>/': 'valida a ordem de abastecimento por GET; abre só na tela de viagem.',
    '/frota/avaliar_edicao/<int:edicao_id>/<int:opcao>/': 'avalia edição de agendamento deferido por GET; abre só na tela de solicitações.',
    '/frota/manutencaoviatura/<int:servico_id>/': 'detalhe da manutenção; é a página de destino do admin de manutenção.',
    # Exercitada pelo fluxo (test_02), mas o gate só lê literal: a navegação usa f-string com o pk.
    '/frota/avaliar_agendamento_viagem/<int:agendamento_id>/': 'é a tela de avaliação, exercitada por `test_02`; o smoke roda depois e o agendamento já foi deferido.',
    # Formulário de objeto que a cadeia não cria (a multa só existe depois de uma viagem multada).
    '/frota/editar_multa/<int:multa_id>/': 'edição de multa cadastrada; a cadeia não cria multa, e o cadastro (em tela) é coberto pelo smoke.',
    # Relatórios em PDF/planilha: sem asserção possível além do content-type.
    '/frota/relatorio_viaturas/': 'gera relatório (PDF/planilha); sem tela para asserir além do content-type.',
    '/frota/relatorio_solicitacoes_por_pessoa/': 'gera relatório (PDF/planilha); sem tela.',
    '/frota/relatorio_deslocamento_por_viatura/': 'gera relatório (PDF/planilha); sem tela.',
    '/frota/relatorio_consumo_por_maquina/': 'gera relatório (PDF/planilha); sem tela.',
    '/frota/relatorio_viagens_por_motorista/': 'gera relatório (PDF/planilha); sem tela.',
}
