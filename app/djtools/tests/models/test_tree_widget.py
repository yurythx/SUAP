"""Testes do TreeWidget: a árvore inteira deve ser montada com uma única consulta."""

import types

from rh.models import Setor

from djtools.forms.widgets import TreeWidget


class QuerySetFalso(list):
    """Simula o mínimo de QuerySet usado pelo TreeWidget, contando as consultas."""

    model = Setor

    def __init__(self, nos):
        super().__init__(nos)
        self.consultas = 0

    def all(self):
        self.consultas += 1
        return list(self)


def montar_widget(nos):
    queryset = QuerySetFalso(nos)
    widget = TreeWidget()
    widget.choices = types.SimpleNamespace(queryset=queryset)
    return widget, queryset


def test_arvore_renderizada_com_uma_unica_consulta():
    nos = [
        Setor(id=1, sigla='RAIZ', nome='Raiz', superior_id=None),
        Setor(id=2, sigla='A', nome='A', superior_id=1),
        Setor(id=3, sigla='B', nome='B', superior_id=1),
        Setor(id=4, sigla='A1', nome='A1', superior_id=2),
    ]
    widget, queryset = montar_widget(nos)

    html = widget.render('setor')

    assert queryset.consultas == 1
    assert '<ul><li id="1"><a href="#" title="Raiz">RAIZ</a><ul>' in html
    assert '<li id="2"><a href="#" title="A">A</a><ul><li id="4"><a href="#" title="A1">A1</a></li></ul></li>' in html
    assert '<li id="3"><a href="#" title="B">B</a></li>' in html


def test_folha_nao_gera_ul_vazia():
    widget, _ = montar_widget([Setor(id=1, sigla='RAIZ', nome='Raiz', superior_id=None)])

    html = widget.render('setor')

    assert '<ul><li id="1"><a href="#" title="Raiz">RAIZ</a></li></ul>' in html


def test_root_nodes_explicito_usa_o_mapa_de_filhos():
    nos = [
        Setor(id=1, sigla='RAIZ', nome='Raiz', superior_id=None),
        Setor(id=2, sigla='A', nome='A', superior_id=1),
    ]
    widget, queryset = montar_widget(nos)
    widget.root_nodes = [nos[1]]

    html = widget.render('setor')

    assert queryset.consultas == 1
    assert 'id="1"' not in html
    assert '<li id="2"><a href="#" title="A">A</a></li>' in html
