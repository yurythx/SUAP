"""Tarefa 1 — cadastrar e configurar o edital de projetos de ensino.

Navega as cinco telas que a doc agrupa em uma tarefa só: o cadastro do edital no admin, o
plano de oferta por campus, as fontes de recurso, os critérios de avaliação e a comissão de
avaliação. Todas executadas pelo Gerente Sistêmico de Projetos de Ensino (o Coordenador de
Projetos de Ensino também pode, mas o caminho de tela é o mesmo).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM_EDITAL = '/admin/projetos_ensino/edital/'
LISTAGEM_COMISSAO = '/admin/projetos_ensino/comissaoedital/'


def test_cadastrar_e_configurar_edital(logado_doc, capturar):
    """Tarefa 1 — do cadastro do edital à comissão de avaliação, em uma única sessão."""
    from projetos_ensino.models import ComissaoEdital, CriterioAvaliacao, Edital, OfertaProjeto, Recurso

    hoje = date.today()
    nome = f'E2E Edital Doc {uuid4().hex[:8]}'

    tela = Tela(logado_doc('gerente')).ir(LISTAGEM_EDITAL)
    tela.ver_titulo('Editais')
    capturar(tela.pagina, 'edital-listagem')

    # Etapa 1 — cadastrar o edital
    tela.ver_botao('Adicionar Edital')
    tela.clicar_botao('Adicionar Edital')
    tela.ver_titulo('Adicionar Edital')
    anotar_tela('edital-form', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', nome),
            ('Descrição', 'textarea', 'Descrição do edital para seleção de projetos de ensino'),
            ('Tipo do Edital', 'lista', 'Ensino'),
            ('Forma de Seleção', 'lista', 'Campus'),
            ('Edital de Campus', 'checkbox', 'marcar'),
            ('Início das Inscrições', 'texto', f'{(hoje + timedelta(days=30)).isoformat()}T00:00'),
            ('Fim das Inscrições', 'texto', f'{(hoje + timedelta(days=40)).isoformat()}T00:00'),
            ('Início da Pré-Seleção', 'texto', f'{(hoje + timedelta(days=45)).isoformat()}T00:00'),
            ('Início da Seleção', 'texto', f'{(hoje + timedelta(days=50)).isoformat()}T00:00'),
            ('Fim da Seleção', 'texto', f'{(hoje + timedelta(days=55)).isoformat()}T00:00'),
            ('Divulgação da Seleção', 'texto', f'{(hoje + timedelta(days=60)).isoformat()}T00:00'),
            ('Participação de Aluno Obrigatória', 'checkbox', 'marcar'),
            ('Participação de Servidor Obrigatória', 'checkbox', 'marcar'),
            ('Valor Financiado por Projeto', 'texto', '10.000,00'),
        ]
    )
    capturar(tela.pagina, 'edital-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Edital cadastrado com sucesso.')
    edital = Edital.objects.filter(titulo=nome).first()
    assert edital is not None, 'a UI disse que salvou, mas não persistiu'
    tela.ver_titulo(f'{nome} - Edital de Ensino')
    anotar_tela('edital-pagina', tela)
    capturar(tela.pagina, 'edital-pagina')

    # Etapa 2 — plano de oferta por campus
    tela.clicar_aba('Plano de Oferta por Campus')
    tela.ver_botao('Adicionar Oferta')
    tela.clicar_botao('Adicionar Oferta')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('oferta-popup', popup)
    popup.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Pré-Selecionados', 'texto', '5'),
            ('Selecionados', 'texto', '3'),
        ]
    )
    capturar(tela.pagina, 'edital-oferta-popup')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Oferta adicionada com sucesso.')
    assert OfertaProjeto.objects.filter(edital=edital).exists(), 'a UI disse que salvou a oferta, mas não persistiu'

    # Etapa 3 — fontes de recurso
    tela.clicar_aba('Fonte de Recursos')
    tela.ver_botao('Adicionar Recurso')
    tela.clicar_botao('Adicionar Recurso')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('recurso-popup', popup)
    popup.preencher_formulario(
        [
            ('Origem', 'lista', 'CAMPUS'),
            ('Valor disponível por projeto (R$)', 'texto', '10.000,00'),
            ('Despesa', 'autocomplete', 'Auxílio Financeiro a Estudantes'),
        ]
    )
    capturar(tela.pagina, 'edital-recurso-popup')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Recurso adicionado com sucesso.')
    assert Recurso.objects.filter(edital=edital).exists(), 'a UI disse que salvou o recurso, mas não persistiu'

    # Etapa 4 — critérios de avaliação da qualificação
    tela.clicar_aba('Critérios de Avaliação da Qualificação do Projeto')
    tela.ver_botao('Adicionar Critério de Avaliação')
    tela.clicar_botao('Adicionar Critério de Avaliação')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('criterio-popup', popup)
    popup.preencher_formulario(
        [
            ('Descrição', 'textarea', 'Adequação da proposta ao tema do edital'),
            ('Pontuação Máxima', 'texto', '10,00'),
            ('Ordem para Desempate', 'texto', '1'),
        ]
    )
    capturar(tela.pagina, 'edital-criterio-popup')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Critério de avaliação adicionado com sucesso.')
    assert CriterioAvaliacao.objects.filter(edital=edital).exists(), 'a UI disse que salvou o critério, mas não persistiu'

    # Etapa 5 — comissão de avaliação
    tela = Tela(logado_doc('gerente')).ir(LISTAGEM_COMISSAO)
    tela.ver_titulo('Comissões de Avaliação')
    capturar(tela.pagina, 'comissao-listagem')
    tela.ver_botao('Adicionar Comissão de Avaliação')
    tela.clicar_botao('Adicionar Comissão de Avaliação')
    tela.ver_titulo('Adicionar Comissão de Avaliação')
    anotar_tela('comissao-form', tela)
    tela.preencher_formulario(
        [
            ('Filtrar por Edital', 'lista', f'{nome} - Edital de Ensino'),
            ('Membro', 'autocomplete multiplo', 'Avaliador Proj Doc A,Avaliador Proj Doc B'),
        ]
    )
    capturar(tela.pagina, 'comissao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert ComissaoEdital.objects.filter(edital=edital).exists(), 'a UI disse que salvou a comissão, mas não persistiu'
    capturar(tela.pagina, 'comissao-listagem')
