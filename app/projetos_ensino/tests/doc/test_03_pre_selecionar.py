"""Tarefa 3 — a coordenadora de projetos de ensino pré-seleciona os projetos enviados
(pré-avaliação). Continua o projeto submetido nas tarefas 1-2 (via ``estado``).
"""

from __future__ import annotations

import sys
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .fabricas import criar_edital, criar_oferta, criar_projeto as criar_projeto_doc, criar_recurso

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRE_AVALIACAO = '/projetos_ensino/pre_avaliacao/'


def test_pre_selecionar_projeto(logado_doc, capturar):
    """Tarefa 3 — pré-selecionar um projeto enviado, pelo Coordenador de Projetos de Ensino."""
    from projetos_ensino.models import Projeto

    # Cria o próprio edital em pré-seleção e o projeto enviado — autossuficiente, sem depender
    # da ordem de execução do test_02b (o edital da submissão tem datas de pré-seleção futuras).
    suf = uuid4().hex[:8]
    edital = criar_edital(
        f'E2E Edital PreSel Doc {suf}',
        inicio_inscricoes=-40,
        fim_inscricoes=-25,
        inicio_pre_selecao=-5,
        inicio_selecao=10,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    projeto = criar_projeto_doc(f'E2E Projeto PreSel Doc {suf}', edital)
    projeto_id = projeto.pk

    tela = Tela(logado_doc('coordenador')).ir(PRE_AVALIACAO)
    tela.ver_titulo('Editais')
    capturar(tela.pagina, 'preselecao-editais')
    anotar_tela('pre-selecao-editais', tela)
    tela.linha(projeto.edital.titulo).clicar_icone('exibição')

    tela.ver_titulo(f'Pré-Seleção de Projetos - {projeto.edital.titulo}')
    anotar_tela('pre-selecao-projetos', tela)
    capturar(tela.pagina, 'preselecao-projetos')
    tela.linha(projeto.titulo).ver_botao('Pré-selecionar')
    tela.linha(projeto.titulo).clicar_botao('Pré-selecionar')

    tela.sucesso('Projeto pré-avaliado com sucesso.')
    projeto_bd = Projeto.objects.get(pk=projeto_id)
    assert projeto_bd.pre_aprovado, 'a UI disse que pré-selecionou, mas não persistiu'
    assert projeto_bd.vinculo_monitor is not None, 'pré-seleção não definiu o monitor do projeto'
