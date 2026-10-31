"""Tarefa 2 (etapas 5-7) — a coordenadora planeja o orçamento (memória de cálculo e
desembolso) e envia o projeto.

Continua o projeto criado pela tela no ``test_02a`` (o id vem de ``estado.CAMPOS``).
"""

from __future__ import annotations

import sys
from datetime import date

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from . import estado
from .fabricas import criar_edital, criar_oferta, criar_recurso

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_planejar_orcamento_e_enviar(logado_doc, capturar):
    """Tarefa 2, etapas 5 a 7 — memória de cálculo, desembolso e envio do projeto."""
    from projetos_ensino.models import Desembolso, ItemMemoriaCalculo, Projeto

    projeto_id = estado.pega('projeto_id', 'test_submeter_projeto_partes_1_a_4')
    projeto = Projeto.objects.get(pk=projeto_id)
    recurso = projeto.edital.recurso_set.first()
    assert recurso, 'o edital do projeto precisa de fonte de recurso'
    rol_memoria = f'{recurso.despesa.codigo} - {recurso.despesa.nome} / {recurso.origem}'

    tela = Tela(logado_doc('coordenador_projeto')).ir(f'/projetos_ensino/projeto/{projeto_id}/')

    # Etapa 5 — memória de cálculo (Plano de Aplicação)
    tela.clicar_aba('Plano de Aplicação')
    capturar(tela.pagina, 'projeto-plano-vazio')
    tela.ver_botao('Adicionar Memória de Cálculo')
    tela.clicar_botao('Adicionar Memória de Cálculo')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('memoria-calculo-popup', popup)
    popup.preencher_formulario(
        [
            ('Recurso', 'lista', rol_memoria),
            ('Descrição', 'textarea', 'Pagamento de bolsas dos alunos'),
            ('Unidade de Medida', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '10.000,00'),
        ]
    )
    capturar(tela.pagina, 'projeto-memoria-calculo')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Item adicionado com sucesso.')
    item = ItemMemoriaCalculo.objects.filter(projeto=projeto).first()
    assert item is not None, 'a UI disse que salvou a memória de cálculo, mas não persistiu'

    # Etapa 6 — desembolso (Plano de Desembolso)
    tela.clicar_aba('Plano de Desembolso')
    tela.ver_botao('Adicionar Item')
    tela.clicar_botao('Adicionar Item')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('desembolso-popup', popup)
    rol_desembolso = f'{recurso.despesa.codigo} - {recurso.despesa.nome} / {recurso.origem} - Pagamento de bolsas dos alunos'
    popup.preencher_formulario(
        [
            ('Mémoria de Cálculo', 'lista', rol_desembolso),
            ('Ano', 'autocomplete', str(date.today().year)),
            ('Mês', 'lista', '1'),
            ('Valor (R$)', 'texto', '10.000,00'),
        ]
    )
    capturar(tela.pagina, 'projeto-desembolso')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Desembolso adicionado com sucesso.')
    assert Desembolso.objects.filter(projeto=projeto).exists(), 'a UI disse que salvou o desembolso, mas não persistiu'

    # Etapa 7 — enviar o projeto
    tela.ver_botao('Enviar Projeto')
    tela.clicar_botao('Enviar Projeto')
    tela.sucesso('Projeto enviado com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_conclusao_planejamento is not None, 'a UI disse que enviou, mas não persistiu'
    anotar_tela('projeto-enviado', tela)
    capturar(tela.pagina, 'projeto-enviado')
