"""Fluxo: fonte de recursos do edital (feature 001, "Cadastro das Fontes de Recurso do Edital").

O valor de cada recurso é o teto que um projeto aprovado pode gastar naquela despesa (rubrica),
e é dele que o coordenador parte para a memória de cálculo. Pega a regressão do ciclo pela aba
"Fonte de Recursos" (popups de adicionar/editar, remoção por GET) e a gravação da ORIGEM, que o
formulário recebe como escolha de ``OrigemRecursoEdital`` e a view grava como texto — e do JSON
que alimenta o select de recurso do relatório financeiro (``relatoriofinanceiroform.js``).
"""

from decimal import Decimal

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = '/projetos/edital/{}/'
ADICIONAR_RECURSO = '/projetos/adicionar_recurso/{}/'
EDITAR_RECURSO = '/projetos/editar_recurso/{}/'
REMOVER_RECURSO = '/projetos/remover_recurso/{}/'
FILTRAR_RECURSOS = '/projetos/filtrar_recursos_por_edital/'


def test_fonte_de_recursos_ciclo_completo(logado_projetos, edital_novo, catalogo_do_edital):
    """Adicionar (popup) → editar (popup) → remover, pelo gerente."""
    from projetos.models import Recurso

    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba('Fonte de Recursos')
    clicar_em(tela, ADICIONAR_RECURSO.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_RECURSO.format(edital.pk))
    popup.preencher_formulario(
        [
            ('Origem', 'lista', 'PROEX'),
            ('Valor disponível por projeto (R$)', 'texto', '10.000,00'),
            ('Despesa', 'autocomplete', 'Auxílio Financeiro a Estudantes'),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Recurso adicionado com sucesso.')
    recurso = Recurso.objects.filter(edital=edital, despesa__codigo='339018').first()
    assert recurso is not None, 'a UI disse que salvou, mas não persistiu'
    assert (recurso.origem, recurso.valor) == ('PROEX', Decimal('10000')), f'gravou origem={recurso.origem!r} valor={recurso.valor}'

    tela.clicar_aba('Fonte de Recursos')
    clicar_em(tela, EDITAR_RECURSO.format(recurso.pk))
    popup = popup_em(tela, EDITAR_RECURSO.format(recurso.pk)).preencher('Origem', 'lista', 'CAMPUS')
    tela = popup.salvar_no_popup('Salvar').sucesso('Recurso editado com sucesso.')
    recurso.refresh_from_db()
    assert recurso.origem == 'CAMPUS', 'a UI disse que editou, mas a origem não mudou'

    tela.clicar_aba('Fonte de Recursos')
    clicar_em(tela, REMOVER_RECURSO.format(recurso.pk))
    tela.esperar().sucesso('Recurso removido com sucesso.')
    assert not Recurso.objects.filter(pk=recurso.pk).exists(), 'a UI disse que removeu, mas o recurso continua'


def test_recursos_do_edital_em_json(logado_projetos, edital_novo, catalogo_do_edital):
    """O endpoint do select "Recurso" do relatório financeiro: ``[{titulo, id}]`` dos recursos do edital."""
    from financeiro.models import NaturezaDespesa
    from projetos.tests.factories import RecursoFactory

    edital = edital_novo()
    recurso = RecursoFactory(edital=edital, despesa=NaturezaDespesa.objects.get(codigo='339030'))

    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{FILTRAR_RECURSOS}?edital={edital.pk}')
    assert resposta.status == 200
    assert resposta.json() == [{'titulo': str(recurso), 'id': recurso.pk}]


def test_recursos_de_edital_sem_recurso_responde_lista_vazia(logado_projetos, edital_novo):
    edital = edital_novo()
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{FILTRAR_RECURSOS}?edital={edital.pk}')
    assert resposta.status == 200
    assert resposta.json() == []
