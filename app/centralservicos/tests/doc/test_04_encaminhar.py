"""Roteiro navegado da tarefa 10 da doc: encaminhar o chamado.

O responsável pelo grupo é quem enxerga o menu "Ações" com Atribuir/Escalar/Retornar (o
atendente comum não vê "Atribuir"); o atendente assume, atende e suspende. O chamado deste
teste é criado por ORM de propósito — a doc já mostrou a abertura na tarefa 6, e aqui o
interesse é o que se faz com um chamado que já existe.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from djtools.e2e_ui import Tela, anotar_tela

from .conftest import CENTRO_SISTEMICO, GRUPO_LOCAL, PAPEIS, area, centro_local, popup_em, servico, usuarios_doc

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def chamado_para_encaminhar(doc_seed, usuarios_doc):
    """Chamado aberto por telefone, ainda sem atendente — o estado de partida do encaminhamento."""
    from centralservicos.models import Chamado
    from rh.models import UnidadeOrganizacional

    interessado = usuarios_doc('colega')
    Chamado.objects.filter(servico__nome=servico().nome, interessado=interessado).delete()

    campus = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    chamado = Chamado(
        descricao='Solicitação registrada por telefone: computador não liga.',
        servico=servico(),
        aberto_em=timezone.now(),
        aberto_por=usuarios_doc('atendente'),
        requisitante=interessado,
        interessado=interessado,
        campus=campus,
        meio_abertura=Chamado.MEIO_ABERTURA_TELEFONE,
    )
    chamado.centro_atendimento = centro_local()
    chamado.save()
    return chamado


def test_encaminhar_chamado(logado_doc, capturar, chamado_para_encaminhar, usuarios_doc):
    """Tarefa 10 — atribuir, escalar, retornar, reclassificar, sinalizar com tags e suspender."""
    from centralservicos.models import Tag

    chamado = chamado_para_encaminhar
    Tag.objects.get_or_create(nome='Impressora', area=area())

    tela = Tela(logado_doc('responsavel')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    capturar(tela.pagina, '10-chamado-a-encaminhar')

    # Atribuir a um atendente do grupo.
    tela.clicar_botao('Ações')
    tela.clicar_link('Atribuir')
    popup = popup_em(tela, 'atribuir_chamado')
    anotar_tela('atribuir-popup', popup)
    # O rótulo do campo não tem acento (campo declarado no form, não vem do model) e as opções
    # exibem nome + matrícula — é por esse rótulo que `_preencher_lista` seleciona.
    popup.preencher('Atribuido para', 'lista', str(usuarios_doc('atendente')))
    capturar(tela.pagina, '10-atribuir')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atribuição realizada com sucesso para')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.get_atendente_do_chamado().username == PAPEIS['atendente'], 'a atribuição não ficou com o atendente'

    # Escalar para o grupo de nível superior (Suporte Sistêmico).
    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Escalar')
    tela.ver_titulo('Escalar Atendimento')
    anotar_tela('escalar-form', tela)
    tela.preencher('Texto', 'textarea', 'Caso exige acesso à rede; encaminhando ao nível superior.')
    capturar(tela.pagina, '10-escalar')
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.get_atendimento_atribuicao_atual().grupo_atendimento.nome == 'Suporte Sistêmico', 'não escalou'

    # Retornar ao grupo de origem.
    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Retornar')
    tela.ver_titulo('Retornar Atendimento')
    tela.preencher('Texto', 'textarea', 'O nível superior orientou o procedimento; retornando ao grupo local.')
    capturar(tela.pagina, '10-retornar')
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.get_atendimento_atribuicao_atual().grupo_atendimento.nome == GRUPO_LOCAL, 'não retornou'

    # Reclassificar: muda o serviço/centro e reencaminha o chamado ao grupo do novo centro.
    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Reclassificar')
    tela.ver_titulo(f'Reclassificar Chamado: {chamado.pk}')
    anotar_tela('reclassificar-form', tela)
    tela.preencher('Campus', 'lista', 'CZN')
    tela.preencher('Centro de Atendimento', 'radio', CENTRO_SISTEMICO)
    tela.preencher('Justificativa', 'textarea', 'Atendimento passa a ser sistêmico, não local.')
    capturar(tela.pagina, '10-reclassificar')
    tela.clicar_botao('Salvar')
    tela.sucesso('Reclassificação de chamado realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.get_atendimento_atribuicao_atual().grupo_atendimento.nome == 'Suporte Sistêmico', 'não reclassificou'

    # O atendente reassume no novo grupo, inicia o atendimento e suspende (aguarda terceiros).
    tela = Tela(logado_doc('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Assumir')
    tela.sucesso('Atribuição realizada com sucesso.')
    tela.clicar_botao('Alterar para Em Atendimento')
    tela.sucesso('Alteração de situação realizada com sucesso.')

    # Adicionar tags (a tag é cadastro de apoio do módulo).
    tela.clicar_botao('Ações')
    tela.clicar_link('Adicionar tags')
    popup = popup_em(tela, 'adicionar_tags_ao_chamado')
    anotar_tela('tags-popup', popup)
    popup.preencher('Tags', 'checkbox multiplo', 'Impressora')
    capturar(tela.pagina, '10-adicionar-tags')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Adição de tags realizada com sucesso.')

    tela.clicar_botao('Suspender')
    tela.ver_titulo('Alterar Situação para Suspenso')
    anotar_tela('suspender-form', tela)
    tela.preencher('Comentário', 'textarea', 'Aguardando a chegada da peça de reposição.')
    capturar(tela.pagina, '10-suspender')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.estah_suspenso(), 'o chamado não foi suspenso'
    assert chamado.tags.filter(nome='Impressora').exists(), 'a tag não foi vinculada'
