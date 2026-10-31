"""Tarefa 4 — indicação de avaliadores para os projetos pré-selecionados, pelo Gerente
Sistêmico (a coordenadora do edital indica, dentre a comissão de avaliação, quem avaliará
cada projeto). Importante: a indicação é o passo que dá ao avaliador o acesso à tela de
avaliação da tarefa 5.
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

INDICAR_AVALIADOR = '/projetos_ensino/editais_para_avaliacao/'


def test_indicar_avaliadores(logado_doc, capturar):
    """Tarefa 4 — indicar os avaliadores de um projeto pré-selecionado."""
    from projetos_ensino.models import AvaliadorIndicado, Projeto

    siape_a, siape_b = '158005', '158006'
    suf = uuid4().hex[:8]
    edital = criar_edital(
        f'E2E Edital Aval Doc {suf}',
        inicio_inscricoes=-40,
        fim_inscricoes=-25,
        inicio_pre_selecao=-5,
        inicio_selecao=5,
        fim_selecao=15,
        divulgacao_selecao=30,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    criar_criterio(edital)
    criar_comissao(edital, [siape_a, siape_b])
    projeto = criar_projeto(f'E2E Projeto Aval Doc {suf}', edital, pre_aprovado=True, aprovado=False)

    tela = Tela(logado_doc('gerente')).ir(INDICAR_AVALIADOR)
    tela.ver_titulo('Editais em Avaliação')
    capturar(tela.pagina, 'indicar-avaliador-editais')
    tela.linha(edital.titulo).clicar_icone('exibição')

    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {edital.titulo}')
    anotar_tela('indicar-avaliador-projetos', tela)
    capturar(tela.pagina, 'indicar-avaliador-projetos')
    tela.linha(projeto.titulo).ver_botao('Selecionar avaliadores')
    tela.linha(projeto.titulo).clicar_botao('Selecionar avaliadores')

    popup = tela.popup()
    popup.ver_botao('Enviar')
    anotar_tela('indicar-avaliador-popup', popup)
    capturar(tela.pagina, 'indicar-avaliador-popup')
    popup.selecionar_item('Avaliador Proj Doc A')
    popup.selecionar_item('Avaliador Proj Doc B')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Avaliadores cadastrados com sucesso.')
    indicacoes = AvaliadorIndicado.objects.filter(projeto=projeto)
    assert indicacoes.count() == 2, 'a UI disse que indicou 2 avaliadores, mas não persistiu'
    # Os avaliadores indicados ganham o grupo 'Avaliador de Projetos de Ensino', que um já
    # não tem no seed (o usuário 158005 já nasce com ele) — a rede por usuário é o que valida
    # a indicação, não o grupo.
    assert {i.vinculo.user.username for i in indicacoes} == {siape_a, siape_b}
