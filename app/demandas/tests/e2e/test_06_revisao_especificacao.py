"""Fluxo da revisão de especificação: alterar a consolidação depois de aprovada.

Depois de aprovada, a consolidação só muda por revisão: o analista revisa uma especificação,
pede a remoção de outra, acrescenta uma nova e então pede a validação das alterações — e o
demandante aprova ou rejeita cada uma. O produto só oferece essas telas com a demanda em
desenvolvimento ou homologação, e o pedido de validação bloqueia novas revisões. Este arquivo
usa a segunda demanda da suíte (criada em ``test_05``) e a leva a "Em desenvolvimento".
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from demandas.tests.e2e.apoio import esperar_editor_rico
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda, RevisaoEspecificacao

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VISUALIZAR = '/demandas/visualizar/{}/'
REVISAR = '/demandas/especificacao/{}/revisar/'
VISUALIZAR_ESPECIFICACAO = '/demandas/especificacao/{}/visualizar/'
SOLICITAR_REMOCAO = '/demandas/especificacao/{}/solicitar_remocao/'
ADICIONAR_REVISAO = '/demandas/revisaoespecificacao/{}/adicionar/'
EDITAR_REVISAO = '/demandas/revisaoespecificacao/{}/editar/'
APROVAR_REVISAO = '/demandas/revisaoespecificacao/{}/aprovar/'
REPROVAR_REVISAO = '/demandas/revisaoespecificacao/{}/reprovar/'
SOLICITAR_VALIDACAO = '/demandas/dod/{}/solicitar_aprovacao_modificacoes/'
VALIDAR_MODIFICACOES = '/demandas/dod/{}/validar_modificacoes/'


def demanda_em_desenvolvimento() -> Demanda:
    """A segunda demanda da suíte, levada a "Em desenvolvimento" pelo domínio.

    O estado é precondição da revisão de especificação (o produto só a oferece em
    desenvolvimento ou homologação); o caminho pela tela é o que ``test_01`` a ``test_03``
    percorrem na primeira demanda.
    """
    from comum.models import User
    from demandas.models import Demanda, DoD, Situacao

    demanda = Demanda.objects.get(titulo='Demanda 2')
    if demanda.situacao == Situacao.ESTADO_EM_ANALISE:
        analista = User.objects.get(username='105002')
        demanda.alterar_situacao(analista, Situacao.ESTADO_APROVADO)
        demanda.alterar_situacao(analista, Situacao.ESTADO_EM_DESENVOLVIMENTO)
    # A consolidação precisa estar "feita" (descrição + especificações com atividades) para o
    # produto oferecer a validação das modificações ao demandante.
    dod = DoD.objects.get(demanda=demanda)
    if not dod.descricao:
        dod.descricao = 'Consolidação da Demanda 2'
        dod.save(update_fields=['descricao'])
    demanda.refresh_from_db()
    return demanda


def test_analista_revisa_a_consolidacao(logado_demandas: Callable[[str], Page]) -> None:
    """O analista revisa, remove, acrescenta especificações e pede a validação."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import DoD, Especificacao, RevisaoEspecificacao, Situacao

    demanda = demanda_em_desenvolvimento()
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO, 'a cadeia exige a demanda em desenvolvimento'
    dod = DoD.objects.get(demanda=demanda)
    especificacao = Especificacao.objects.get(dod=dod, nome='Especificação 1')
    # Cada especificação só oferece uma das duas revisões: assim que existe uma revisão para
    # ela, o produto troca "Revisar"/"Remover" por "Editar"/"Remover revisão". Por isso a
    # remoção é pedida para uma segunda especificação.
    removivel = Especificacao.objects.get_or_create(dod=dod, nome='Especificação 2', defaults={'atividades': 'Atividade 2', 'ordem': 2})[0]

    # Revisar: cria a revisão da especificação (o produto recusa revisão idêntica à original).
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    quadro = tela.quadro('Especificação 1')
    expect(quadro.botao('Revisar')).to_have_attribute('href', REVISAR.format(especificacao.pk))
    quadro.clicar_botao('Revisar')
    tela.ver_titulo('Revisar especificação')
    esperar_editor_rico(tela, 'id_atividades')
    tela.preencher_formulario([('Nome', 'Texto', 'Especificação 1 revisada'), ('Atividade(s)', 'Texto rico', 'Atividade revisada')])
    tela.clicar_botao('Salvar').sucesso('Especificação revisada com sucesso.')
    revisao = RevisaoEspecificacao.objects.get(dod=dod, nome='Especificação 1 revisada')
    assert revisao.especificacao == especificacao, 'a revisão precisa apontar para a especificação de origem'

    # A "Versão atual" é o popup que mostra o texto aprovado da especificação.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    # O título do quadro continua sendo o da especificação: ele só muda quando a revisão é aprovada.
    expect(tela.quadro('Especificação 1').botao('Versão atual')).to_have_attribute('href', VISUALIZAR_ESPECIFICACAO.format(especificacao.pk))
    tela.quadro('Especificação 1').clicar_botao('Versão atual')
    tela.popup().ver_texto('Atividade')

    # Pedir a remoção cria uma revisão de remoção — que só apaga a especificação se aprovada.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    expect(tela.quadro('Especificação 2').botao('Remover')).to_have_attribute('href', SOLICITAR_REMOCAO.format(removivel.pk))
    tela.quadro('Especificação 2').clicar_botao('Remover')
    tela.sucesso('Remoção da especificação solicitada com sucesso.')
    assert RevisaoEspecificacao.objects.filter(dod=dod, remocao_solicitada=True).exists(), (
        'a UI disse que solicitou, mas a revisão de remoção não foi criada'
    )
    assert Especificacao.objects.filter(pk=removivel.pk).exists(), 'a remoção só acontece depois da aprovação'

    # Acrescentar uma especificação nova e depois editá-la.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    expect(tela.aba('Consolidação').botao('Adicionar especificação')).to_have_attribute('href', ADICIONAR_REVISAO.format(dod.pk))
    tela.aba('Consolidação').clicar_botao('Adicionar especificação')
    tela.ver_titulo('Adicionar especificação')
    esperar_editor_rico(tela, 'id_atividades')
    tela.preencher_formulario([('Nome', 'Texto', 'Especificação nova'), ('Atividade(s)', 'Texto rico', 'Atividade nova')])
    tela.clicar_botao('Salvar').sucesso('Especificação adicionada com sucesso.')
    nova = RevisaoEspecificacao.objects.get(dod=dod, nome='Especificação nova')
    assert nova.especificacao is None, 'a revisão de uma especificação nova não aponta para nenhuma existente'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    expect(tela.quadro('Nova especificação: Especificação nova').botao('Editar')).to_have_attribute('href', EDITAR_REVISAO.format(nova.pk))
    tela.quadro('Nova especificação: Especificação nova').clicar_botao('Editar')
    tela.ver_titulo('Editar revisão da especificação')
    tela.preencher('Nome', 'Texto', 'Especificação nova revisada')
    tela.clicar_botao('Salvar').sucesso('Especificação adicionada com sucesso.')
    nova.refresh_from_db()
    assert nova.nome == 'Especificação nova revisada', 'a UI disse que editou, mas o nome da revisão não mudou'

    # O pedido de validação bloqueia novas revisões até o demandante decidir.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Consolidação')
    expect(tela.aba('Consolidação').botao('Solicitar validação das alterações')).to_have_attribute('href', SOLICITAR_VALIDACAO.format(dod.pk))
    tela.aba('Consolidação').clicar_botao('Solicitar validação das alterações')
    tela.sucesso('Foi solicitada validação das alterações na consolidação.')
    dod.refresh_from_db()
    assert dod.validacao_revisao_solicitada, 'a UI disse que solicitou, mas a consolidação não ficou pendente de validação'
    assert RevisaoEspecificacao.objects.filter(dod=dod).count() == 3, 'as três revisões precisam estar pendentes'


def test_demandante_valida_as_modificacoes_da_consolidacao(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante aprova uma modificação e rejeita outra pela tela de validação."""
    tela = Tela(logado_demandas('demandante'))

    from demandas.models import DoD, Especificacao, RevisaoEspecificacao

    demanda = demanda_em_desenvolvimento()
    dod = DoD.objects.get(demanda=demanda)
    revisoes = list(RevisaoEspecificacao.objects.filter(dod=dod).order_by('id'))
    assert len(revisoes) == 3, 'a cadeia deste teste exige as três revisões pendentes'
    aprovada, rejeitada = revisoes[0], revisoes[1]

    # Com a validação pendente, o demandante cai direto na tela de validação.
    tela.ir(VISUALIZAR.format(demanda.pk))
    expect(tela.pagina).to_have_url(re.compile(rf'{VALIDAR_MODIFICACOES.format(dod.pk)}$'))
    tela.ver_texto('A consolidação desta demanda foi alterada e necessita da sua validação.')

    expect(tela.loc(f'//a[@href="{APROVAR_REVISAO.format(aprovada.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{APROVAR_REVISAO.format(aprovada.pk)}"]').click()
    tela.sucesso('Modificação aprovada com sucesso.')
    assert not RevisaoEspecificacao.objects.filter(pk=aprovada.pk).exists(), 'a revisão aprovada precisa sair da lista'

    tela.ir(VISUALIZAR.format(demanda.pk))
    expect(tela.loc(f'//a[@href="{REPROVAR_REVISAO.format(rejeitada.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{REPROVAR_REVISAO.format(rejeitada.pk)}"]').click()
    tela.sucesso('Modificação rejeitada com sucesso.')
    assert not RevisaoEspecificacao.objects.filter(pk=rejeitada.pk).exists(), 'a revisão rejeitada precisa sair da lista'

    # A última revisão aprovada aplica a remoção e libera a consolidação.
    ultima = RevisaoEspecificacao.objects.get(dod=dod)
    tela.ir(VISUALIZAR.format(demanda.pk))
    tela.loc(f'//a[@href="{APROVAR_REVISAO.format(ultima.pk)}"]').click()
    tela.sucesso('Modificação aprovada com sucesso.')
    dod.refresh_from_db()
    assert not dod.validacao_revisao_solicitada, 'sem revisões pendentes a consolidação precisa voltar a valer'
    assert Especificacao.objects.filter(dod=dod, nome='Especificação nova revisada').exists(), (
        'a especificação nova aprovada precisa entrar na consolidação'
    )
