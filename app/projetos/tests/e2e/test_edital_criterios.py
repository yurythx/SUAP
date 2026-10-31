"""Fluxo: critérios do edital — de avaliação da qualificação (com nota) e de pré-seleção.

Os critérios de avaliação são o que o avaliador pontua e o que desempata a classificação
(``ordem_desempate``); os de pré-seleção orientam a pré-avaliação do campus. Pega a regressão do
ciclo de cada um pelas abas do edital (popups de adicionar/editar, remoção por GET) e das duas
regras do critério de avaliação: a ordem de desempate é única no edital
(``CriterioAvaliacaoForm.clean``) e critério já pontuado numa avaliação não pode ser removido
(``CriterioAvaliacao.pode_ser_removido``) — apagá-lo levaria junto as notas dadas.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = '/projetos/edital/{}/'
ABA_AVALIACAO = 'Critérios de Avaliação da Qualificação do Projeto'
ADICIONAR_CRITERIO_AVALIACAO = '/projetos/adicionar_criterio_avaliacao/{}/'
EDITAR_CRITERIO_AVALIACAO = '/projetos/editar_criterio_avaliacao/{}/'
REMOVER_CRITERIO_AVALIACAO = '/projetos/remover_criterio_avaliacao/{}/'
ADICIONAR_CRITERIO_PRE_SELECAO = '/projetos/adicionar_criterio_pre_selecao/{}/'
EDITAR_CRITERIO_PRE_SELECAO = '/projetos/editar_criterio_pre_selecao/{}/'
REMOVER_CRITERIO_PRE_SELECAO = '/projetos/remover_criterio_pre_selecao/{}/'


def test_criterio_de_avaliacao_ciclo_completo(logado_projetos, edital_novo):
    """Adicionar (popup) → editar (popup) → remover, pelo coordenador de extensão do campus do edital."""
    from projetos.models import CriterioAvaliacao

    edital = edital_novo()
    descricao = f'Relevância social {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_extensao')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_AVALIACAO)
    clicar_em(tela, ADICIONAR_CRITERIO_AVALIACAO.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_CRITERIO_AVALIACAO.format(edital.pk))
    popup.preencher_formulario([('Descrição', 'textarea', descricao), ('Pontuação Máxima', 'texto', '10,00'), ('Ordem para Desempate', 'texto', '1')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Critério de avaliação adicionado com sucesso.')
    criterio = CriterioAvaliacao.objects.filter(edital=edital, descricao=descricao).first()
    assert criterio is not None, 'a UI disse que salvou, mas não persistiu'
    assert (criterio.pontuacao_maxima, criterio.ordem_desempate) == (Decimal('10'), 1), 'pontuação ou ordem gravadas erradas'

    tela.clicar_aba(ABA_AVALIACAO)
    clicar_em(tela, EDITAR_CRITERIO_AVALIACAO.format(criterio.pk))
    popup = popup_em(tela, EDITAR_CRITERIO_AVALIACAO.format(criterio.pk)).preencher('Pontuação Máxima', 'texto', '20,00')
    tela = popup.salvar_no_popup('Salvar').sucesso('Critério de avaliação editado com sucesso.')
    criterio.refresh_from_db()
    assert criterio.pontuacao_maxima == Decimal('20'), 'a UI disse que editou, mas a pontuação não mudou'

    tela.clicar_aba(ABA_AVALIACAO)
    clicar_em(tela, REMOVER_CRITERIO_AVALIACAO.format(criterio.pk))
    tela.esperar().sucesso('Critério de avaliação removido com sucesso.')
    assert not CriterioAvaliacao.objects.filter(pk=criterio.pk).exists(), 'a UI disse que removeu, mas o critério continua'


def test_ordem_de_desempate_e_unica_no_edital(logado_projetos, edital_novo):
    from projetos.models import CriterioAvaliacao
    from projetos.tests.factories import CriterioAvaliacaoFactory

    edital = edital_novo()
    CriterioAvaliacaoFactory(edital=edital, ordem_desempate=1)
    descricao = f'Critério repetido {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(ADICIONAR_CRITERIO_AVALIACAO.format(edital.pk))

    tela.preencher_formulario([('Descrição', 'textarea', descricao), ('Pontuação Máxima', 'texto', '5,00'), ('Ordem para Desempate', 'texto', '1')])
    tela.clicar_botao('Salvar')
    tela.erro('Já existe um critério de avaliação com esta ordem de desempate.')
    assert not CriterioAvaliacao.objects.filter(edital=edital, descricao=descricao).exists(), 'o formulário recusou, mas o critério foi gravado'


def test_criterio_ja_pontuado_nao_pode_ser_removido(logado_projetos, edital_novo, projetos_seed):
    from projetos.models import CriterioAvaliacao
    from projetos.tests.e2e.conftest import vinculo
    from projetos.tests.factories import AvaliacaoFactory, CriterioAvaliacaoFactory, ItemAvaliacaoFactory, ProjetoFactory

    edital = edital_novo()
    criterio = CriterioAvaliacaoFactory(edital=edital)
    avaliacao = AvaliacaoFactory(projeto=ProjetoFactory(edital=edital, uo=projetos_seed.uo), vinculo=vinculo('avaliador'))
    ItemAvaliacaoFactory(avaliacao=avaliacao, criterio_avaliacao=criterio)
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_AVALIACAO)
    clicar_em(tela, REMOVER_CRITERIO_AVALIACAO.format(criterio.pk))
    tela.erro('Critério de avaliação não pode ser removido, pois existem avaliações feitas para esse critério.')
    assert CriterioAvaliacao.objects.filter(pk=criterio.pk).exists(), 'a UI recusou, mas o critério foi removido'


def test_criterio_de_pre_selecao_ciclo_completo(logado_projetos, edital_novo):
    """Adicionar (popup) → editar (popup) → remover, pelo gerente."""
    from projetos.models import CriterioPreSelecao

    edital = edital_novo()
    descricao = f'Aderência ao campus {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba('Critérios para Pré-seleção')
    clicar_em(tela, ADICIONAR_CRITERIO_PRE_SELECAO.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_CRITERIO_PRE_SELECAO.format(edital.pk))
    popup.preencher_formulario([('Descrição', 'texto', descricao), ('Texto de ajuda', 'textarea', 'Considere o arranjo produtivo local')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Critério adicionado com sucesso.')
    criterio = CriterioPreSelecao.objects.filter(edital=edital, descricao=descricao).first()
    assert criterio is not None, 'a UI disse que salvou, mas não persistiu'

    tela.clicar_aba('Critérios para Pré-seleção')
    clicar_em(tela, EDITAR_CRITERIO_PRE_SELECAO.format(criterio.pk))
    popup = popup_em(tela, EDITAR_CRITERIO_PRE_SELECAO.format(criterio.pk)).preencher('Texto de ajuda', 'textarea', 'Texto revisado')
    tela = popup.salvar_no_popup('Salvar').sucesso('Critério editado com sucesso.')
    criterio.refresh_from_db()
    assert criterio.texto_ajuda == 'Texto revisado', 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba('Critérios para Pré-seleção')
    clicar_em(tela, REMOVER_CRITERIO_PRE_SELECAO.format(criterio.pk))
    tela.esperar().sucesso('Critério removido com sucesso.')
    assert not CriterioPreSelecao.objects.filter(pk=criterio.pk).exists(), 'a UI disse que removeu, mas o critério continua'
