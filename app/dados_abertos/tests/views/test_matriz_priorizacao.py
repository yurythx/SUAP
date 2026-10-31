"""Testes da tela de Matriz de Priorização."""

import datetime

import pytest
from django.urls import reverse

from dados_abertos.models import PlanoDadosAbertos
from dados_abertos.tests.views.conftest import logar
from rh.tests.factories import ServidorFactory


def _criar_pda(titulo: str, ano: int) -> PlanoDadosAbertos:
    return PlanoDadosAbertos.objects.create(
        titulo=titulo,
        vigencia_inicio=datetime.date(ano, 1, 1),
        vigencia_fim=datetime.date(ano, 12, 31),
    )


def test_servidor_fora_do_grupo_de_trabalho_nao_acessa_a_matriz(client, db, sync_permissions):
    """Ser servidor (ou staff) não basta: a matriz exige a permissão sobre as avaliações."""
    _criar_pda('PDA 2026-2027', 2026)
    logar(client, ServidorFactory())

    assert client.get(reverse('dados_abertos:matriz_priorizacao')).status_code == 403


def test_abre_a_matriz_do_pda_selecionado(cliente_membro_gt):
    """A matriz deve operar sobre o PDA indicado na URL, não sobre o primeiro do banco."""
    _criar_pda('PDA 2024-2025', 2024)
    pda_desejado = _criar_pda('PDA 2026-2027', 2026)

    resposta = cliente_membro_gt.get(reverse('dados_abertos:matriz_priorizacao'), {'pda': pda_desejado.pk})

    assert resposta.status_code == 200
    assert resposta.context['pda'] == pda_desejado


def test_mantem_o_pda_selecionado_ao_salvar(cliente_membro_gt):
    """Após salvar, a matriz volta para o mesmo PDA — e não para o padrão."""
    _criar_pda('PDA 2024-2025', 2024)
    pda_desejado = _criar_pda('PDA 2026-2027', 2026)

    resposta = cliente_membro_gt.post(reverse('dados_abertos:matriz_priorizacao'), {'pda': pda_desejado.pk, 'acao': 'salvar'})

    assert resposta.status_code == 302
    assert resposta.url.endswith(f'?pda={pda_desejado.pk}')


def test_usa_o_pda_de_vigencia_mais_recente_por_padrao(cliente_membro_gt):
    """Sem escolha explícita, a matriz abre no PDA vigente mais recente."""
    _criar_pda('PDA 2024-2025', 2024)
    mais_recente = _criar_pda('PDA 2026-2027', 2026)

    resposta = cliente_membro_gt.get(reverse('dados_abertos:matriz_priorizacao'))

    assert resposta.status_code == 200
    assert resposta.context['pda'] == mais_recente
