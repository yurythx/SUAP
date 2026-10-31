"""Fluxo: plano de aplicação (memória de cálculo) e plano de desembolso do projeto (feature 002).

A memória de cálculo detalha o gasto por fonte de recurso do edital; o desembolso distribui cada
item pelos meses do projeto — e o envio exige que a soma dos desembolsos feche com o total de
cada item. O que se pega aqui: o ciclo da memória (popup de adicionar, edição e remoção pela
MESMA rota com ``?edit_id``/``?del_id``), o "Repetir Desembolso até o mês" (um desembolso por
mês no intervalo, gravado pelo laço de ``adicionar_desembolso``) e a remoção em lote, que é um
formulário na aba postando para ``excluir_desembolsos``.

O edital de cada teste é novo (``projeto_novo``) e só ele ganha a fonte de recurso: recurso num
edital do seed mudaria as pendências de envio de todo projeto dele.
"""

import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA_APLICACAO = 'Plano de Aplicação'
ABA_DESEMBOLSO = 'Plano de Desembolso'
MEMORIA_CALCULO = '/projetos/memoria_calculo/{}/'
ADICIONAR_DESEMBOLSO = '/projetos/adicionar_desembolso/{}/'
EDITAR_DESEMBOLSO = '/projetos/editar_desembolso/{}/'
REMOVER_DESEMBOLSO = '/projetos/remover_desembolso/{}/'
EXCLUIR_DESEMBOLSOS = '/projetos/excluir_desembolsos/{}/'

# `str(Recurso)`: "<natureza> / <origem>" — o rótulo da lista "Recurso" da memória de cálculo.
RECURSO = '339018 - Auxílio Financeiro a Estudantes / PROEX'


@pytest.fixture
def projeto_com_recurso(projeto_novo):
    """Projeto em edição cujo edital (novo) tem uma fonte de recurso PROEX na natureza 339018."""
    from financeiro.models import NaturezaDespesa
    from projetos.tests.factories import RecursoFactory

    projeto = projeto_novo()
    RecursoFactory(edital=projeto.edital, despesa=NaturezaDespesa.objects.get(codigo='339018'))
    return projeto


def test_memoria_de_calculo_ciclo_completo(logado_projetos, projeto_com_recurso):
    """Adicionar (popup) → editar (``?edit_id``) → remover (``?del_id``), a mesma rota nos três."""
    from projetos.models import ItemMemoriaCalculo

    projeto = projeto_com_recurso
    rota = MEMORIA_CALCULO.format(projeto.pk)
    descricao = f'Bolsas E2E {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_APLICACAO)
    clicar_em(tela, rota)
    popup = popup_em(tela, rota).preencher_formulario(
        [
            ('Recurso', 'lista', RECURSO),
            ('Descrição', 'textarea', descricao),
            ('Unidade de Medida', 'texto', 'Mês'),
            ('Quantidade', 'texto', '2'),
            ('Valor Unitário (R$)', 'texto', '500,00'),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Item adicionado com sucesso.')
    item = ItemMemoriaCalculo.objects.filter(projeto=projeto, descricao=descricao).first()
    assert item is not None, 'a UI disse que salvou, mas o item não persistiu'
    assert (item.qtd, item.valor_unitario, item.despesa.codigo, item.origem) == (2, Decimal('500'), '339018', 'PROEX'), 'item gravado errado'

    tela.clicar_aba(ABA_APLICACAO)
    clicar_em(tela, f'{rota}?edit_id={item.pk}')
    tela.ver_titulo('Memória de Cálculo').preencher('Quantidade', 'texto', '3').clicar_botao('Salvar')
    tela.esperar().sucesso('Item editado com sucesso.')
    item.refresh_from_db()
    assert item.qtd == 3, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_APLICACAO)
    clicar_em(tela, f'{rota}?del_id={item.pk}')  # `.icon-delete`: o `logado` aceita o confirm
    tela.esperar().sucesso('Item removido com sucesso.')
    assert not ItemMemoriaCalculo.objects.filter(pk=item.pk).exists(), 'a UI disse que removeu, mas o item continua'


def test_memoria_de_calculo_com_gasto_avaliado_nao_e_editada_nem_removida(logado_projetos, projeto_com_recurso):
    """#17546: a aba esconde editar/excluir do item com gasto avaliado; a rota também recusa, e o gasto fica."""
    from projetos.models import ItemMemoriaCalculo, RegistroGasto
    from projetos.tests.factories import RegistroGastoFactory

    avaliador = vinculo('coordenador_extensao').relacionamento
    gasto = RegistroGastoFactory(
        desembolso__item__projeto=projeto_com_recurso, avaliador=avaliador, aprovado=True, dt_avaliacao=datetime.date.today()
    )
    item = gasto.item
    rota = MEMORIA_CALCULO.format(projeto_com_recurso.pk)
    tela = Tela(logado_projetos('coordenador_projeto'))

    respostas = {acao: tela.buscar(f'{rota}?{acao}={item.pk}').status for acao in ('edit_id', 'del_id')}

    assert ItemMemoriaCalculo.objects.filter(pk=item.pk).exists(), 'o item com gasto avaliado foi removido'
    assert RegistroGasto.objects.filter(pk=gasto.pk).exists(), 'o gasto avaliado foi apagado na cascata do item'
    assert respostas == {'edit_id': 403, 'del_id': 403}, f'a rota aceitou o item com gasto avaliado: {respostas}'


def test_desembolso_repetido_editado_e_removido(logado_projetos, projeto_com_recurso):
    """ "Repetir até o mês 3" grava três desembolsos (meses 1, 2 e 3); depois um é editado e outro removido."""
    from comum.tests.factories import AnoFactory
    from projetos.models import Desembolso
    from projetos.tests.factories import ItemMemoriaCalculoFactory

    projeto = projeto_com_recurso
    item = ItemMemoriaCalculoFactory(projeto=projeto, qtd=3, valor_unitario=Decimal('1000'))
    ano = AnoFactory(ano=datetime.date.today().year)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_DESEMBOLSO)
    clicar_em(tela, ADICIONAR_DESEMBOLSO.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_DESEMBOLSO.format(projeto.pk)).preencher_formulario(
        [
            ('Mémoria de Cálculo', 'lista', str(item)),
            ('Ano', 'autocomplete', str(ano.ano)),
            ('Mês', 'lista', '1'),
            ('Valor (R$)', 'texto', '1.000,00'),
            ('Repetir Desembolso até o mês', 'texto', '3'),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Desembolso adicionado com sucesso.')
    desembolsos = Desembolso.objects.filter(projeto=projeto, item=item).order_by('mes')
    assert list(desembolsos.values_list('mes', 'valor')) == [(mes, Decimal('1000')) for mes in (1, 2, 3)], 'a repetição não gravou um por mês'
    primeiro, _, terceiro = desembolsos

    tela.clicar_aba(ABA_DESEMBOLSO)
    clicar_em(tela, EDITAR_DESEMBOLSO.format(primeiro.pk))
    popup = popup_em(tela, EDITAR_DESEMBOLSO.format(primeiro.pk)).preencher('Valor (R$)', 'texto', '900,00')
    tela = popup.salvar_no_popup('Salvar').sucesso('Desembolso editado com sucesso.')
    primeiro.refresh_from_db()
    assert primeiro.valor == Decimal('900'), 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_DESEMBOLSO)
    clicar_em(tela, REMOVER_DESEMBOLSO.format(terceiro.pk))
    tela.esperar().sucesso('Desembolso removido com sucesso.')
    assert list(Desembolso.objects.filter(item=item).order_by('mes').values_list('mes', flat=True)) == [1, 2], 'removeu o desembolso errado'


def test_remocao_de_desembolsos_em_lote(logado_projetos, projeto_com_recurso):
    """A ação "Remover" da aba apaga só os desembolsos marcados."""
    from projetos.models import Desembolso
    from projetos.tests.factories import DesembolsoFactory, ItemMemoriaCalculoFactory

    item = ItemMemoriaCalculoFactory(projeto=projeto_com_recurso)
    marcados = [DesembolsoFactory(item=item, mes=mes) for mes in (1, 2)]
    fica = DesembolsoFactory(item=item, mes=3)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto_com_recurso.pk))

    tela.clicar_aba(ABA_DESEMBOLSO)
    formulario = tela.loc(f'//form[@action="{EXCLUIR_DESEMBOLSOS.format(projeto_com_recurso.pk)}"]')
    expect(formulario).to_be_visible()  # o "Aplicar" posta para outra rota
    for desembolso in marcados:
        formulario.locator(f'xpath=.//input[@name="registros" and @value="{desembolso.pk}"]').check()
    tela.clicar_botao('Aplicar')

    tela.esperar().sucesso('Desembolso(s) excluído(s) com sucesso.')
    assert list(Desembolso.objects.filter(item=item).values_list('pk', flat=True)) == [fica.pk], 'a remoção em lote não apagou só os marcados'
