"""Tarefa 5 — o avaliador indicado avalia o projeto (a avaliação só aparece para quem foi
indicado na tarefa 4). Executada por um Avaliador de Projetos de Ensino.
"""

from __future__ import annotations

import sys
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .fabricas import (
    criar_comissao,
    criar_criterio,
    criar_edital,
    criar_oferta,
    criar_projeto,
    criar_recurso,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AVALIACAO = '/projetos_ensino/avaliacao/'


def test_avaliar_projeto(logado_doc, capturar):
    """Tarefa 5 — avaliar um projeto pré-selecionado, a partir da indicação (tarefa 4)."""
    from projetos_ensino.models import Avaliacao, AvaliadorIndicado

    siape_a, siape_b = '158005', '158006'
    suf = uuid4().hex[:8]
    edital = criar_edital(
        f'E2E Edital Qua Doc {suf}',
        inicio_inscricoes=-50,
        fim_inscricoes=-35,
        inicio_pre_selecao=-15,
        inicio_selecao=-3,
        fim_selecao=7,
        divulgacao_selecao=30,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    criterio = criar_criterio(edital)
    criar_comissao(edital, [siape_a, siape_b])
    projeto = criar_projeto(f'E2E Projeto Qua Doc {suf}', edital, pre_aprovado=True)
    # Indicação pelo ORM (mesmo efeito da tarefa 4), com as datas do edital em período de
    # avaliação — sem ela o avaliador não vê o projeto nem a tela de avaliar (`avaliacao()`
    # filtra por `AvaliadorIndicado`).
    from comum.models import Vinculo

    for matricula in (siape_a, siape_b):
        _salvar_indicacao(projeto, Vinculo.objects.get(user__username=matricula))

    tela = Tela(logado_doc('avaliador_a')).ir(AVALIACAO)
    tela.ver_titulo('Editais em Avaliação')
    capturar(tela.pagina, 'avaliacao-editais')
    anotar_tela('avaliacao-editais', tela)
    tela.linha(edital.titulo).clicar_link('CZN')

    tela.ver_titulo('Seleção de Projetos')
    anotar_tela('avaliacao-projetos', tela)
    capturar(tela.pagina, 'avaliacao-projetos')
    tela.linha(projeto.titulo).ver_botao('Avaliar')
    tela.linha(projeto.titulo).clicar_botao('Avaliar')

    tela.ver_titulo('Avaliação de Projeto')
    anotar_tela('avaliacao-form', tela)
    # O formulário de avaliação é gerado dinamicamente por critério (`AvaliacaoFormFactory`);
    # o parecer é um campo rotulado "Parecer:" e cada critério um <select> com as notas.
    tela.preencher('Parecer', 'textarea', 'Parecer favorável do avaliador A')
    from playwright.sync_api import expect

    select = tela.pagina.locator(f'//select[contains(@name, "{criterio.pk}")]').first
    expect(select).to_be_visible()
    select.select_option(index=0)
    capturar(tela.pagina, 'avaliacao-formulario')
    tela.clicar_botao('Enviar')

    tela.sucesso('Projeto avaliado com sucesso.')
    assert Avaliacao.objects.filter(projeto=projeto, vinculo__user__username=siape_a).exists(), 'a UI disse que avaliou, mas não persistiu'


def _salvar_indicacao(projeto, vinculo) -> None:
    from projetos_ensino.models import AvaliadorIndicado

    AvaliadorIndicado.objects.create(projeto=projeto, vinculo=vinculo)
