"""Roteiro navegado das tarefas 6 a 9 da doc: o ciclo do chamado.

A ordem é a do ciclo e a que as permissões exigem: o chamado nasce aberto; o atendente assume
e o coloca Em Atendimento (só nesse estado o solicitante pode comentar, porque
``Chamado.get_permissoes`` só libera comentário em Em Atendimento/Suspenso); o solicitante
acompanha; o atendente resolve com o artigo da Base; e quem abriu fecha e avalia.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .conftest import AREA, ARTIGO, ARTIGO_PUBLICO, PAPEIS, SERVICO, chamado_do_solicitante, popup_em

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ABRIR_CHAMADO = '/centralservicos/listar_area_servico/'
MEUS_CHAMADOS = '/centralservicos/meus_chamados/?tab=ativos'
DASHBOARD = '/centralservicos/dashboard/'

DESCRICAO = 'Impressora da sala dos servidores com problema.'


def test_abrir_chamado(logado_doc, capturar):
    """Tarefa 6 — o solicitante abre um chamado pelo catálogo, depois de ver as soluções prontas."""
    from centralservicos.models import Chamado

    Chamado.objects.filter(servico__nome=SERVICO, aberto_por__username=PAPEIS['solicitante']).delete()

    tela = Tela(logado_doc('solicitante')).ir(ABRIR_CHAMADO)
    tela.ver_titulo('Listar Áreas de serviço')
    capturar(tela.pagina, '06-areas-de-servico')
    tela.clicar_link(AREA)
    tela.ver_titulo(f'Abrir chamado para {AREA}')
    capturar(tela.pagina, '06-servicos-da-area')
    tela.clicar_link(SERVICO)

    # O serviço tem artigo público vinculado, então o SUAP mostra as soluções antes do
    # formulário — a tela existe para evitar a abertura.
    tela.ver_titulo(SERVICO)
    tela.ver_texto(ARTIGO_PUBLICO)
    capturar(tela.pagina, '06-solucoes-antes-de-abrir')
    tela.clicar_link('Não encontrei nenhuma solução')

    tela.ver_titulo(SERVICO)
    anotar_tela('abrir-chamado-form', tela)
    tela.preencher_formulario(
        [
            ('Descrição', 'textarea', DESCRICAO),
            ('Campus', 'lista', 'CZN'),
            ('Centro de Atendimento', 'radio', 'Local'),
            ('Sala/local de atendimento', 'texto', 'Sala dos servidores'),
        ]
    )
    capturar(tela.pagina, '06-formulario-abrir-chamado')
    tela.clicar_botao('Abrir chamado')
    tela.sucesso('Chamado aberto com sucesso.')

    chamado = Chamado.objects.filter(servico__nome=SERVICO, aberto_por__username=PAPEIS['solicitante']).first()
    assert chamado is not None, 'a UI disse que abriu, mas o chamado não existe'
    assert chamado.interessado.username == PAPEIS['solicitante'], 'o interessado deveria ser quem abriu'
    assert chamado.get_atendimento_atribuicao_atual().grupo_atendimento.nome == 'Suporte Local', (
        'o chamado deveria rotear para o grupo de primeiro nível'
    )


def test_atender_chamado(logado_doc, capturar):
    """Tarefa 7 — o atendente encontra o chamado no painel, assume e inicia o atendimento."""
    chamado = chamado_do_solicitante()

    tela = Tela(logado_doc('atendente')).ir(DASHBOARD)
    tela.ver_titulo('Dashboard')
    capturar(tela.pagina, '07-dashboard')
    tela.clicar_link('Não Atribuídos')
    tela.ver_titulo('Chamados')
    capturar(tela.pagina, '07-fila-de-chamados')
    tela.clicar_link(f'INC #{chamado.pk}')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    capturar(tela.pagina, '07-chamado-aberto')

    tela.clicar_botao('Assumir')
    tela.sucesso('Atribuição realizada com sucesso.')
    # `refresh_from_db` não serve aqui: `Chamado.status` é `FSMIntegerField(protected=True)`, e
    # o refresh passa pelo descriptor, que recusa a atribuição direta ("Direct status
    # modification is not allowed"). Relê-se o objeto por uma query nova.
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.get_atendente_do_chamado().username == PAPEIS['atendente'], 'o chamado não ficou com o atendente'

    tela.clicar_botao('Alterar para Em Atendimento')
    tela.sucesso('Alteração de situação realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.estah_em_atendimento(), 'o chamado não foi para Em Atendimento'

    tela.clicar_aba('Notas Internas')
    tela.preencher_textarea('Adicionar Nota interna', 'Equipamento reiniciado; seguindo com o diagnóstico.')
    capturar(tela.pagina, '07-nota-interna')
    tela.clicar_botao('Adicionar Nota interna')
    tela.sucesso('Nota Interna adicionada com sucesso.')


def test_acompanhar_chamado(logado_doc, capturar):
    """Tarefa 8 — o solicitante acompanha o próprio chamado: comenta, anexa e adiciona interessado."""
    chamado = chamado_do_solicitante()

    tela = Tela(logado_doc('solicitante')).ir(MEUS_CHAMADOS)
    tela.ver_titulo('Meus chamados')
    capturar(tela.pagina, '08-meus-chamados')
    tela.clicar_link(f'INC #{chamado.pk}')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.ver_texto('Em atendimento')

    tela.preencher_textarea('Adicionar comentário', 'A impressora voltou a apresentar o mesmo erro hoje.')
    capturar(tela.pagina, '08-comentario')
    tela.clicar_botao('Adicionar Comentário')
    tela.sucesso('Comentário adicionado com sucesso.')

    tela.clicar_aba('Anexos')
    tela.clicar_link('Adicionar Anexo')
    tela.ver_titulo('Adicionar Anexo')
    anotar_tela('anexo-form', tela)
    tela.preencher_formulario([('Descrição', 'texto', 'Foto do painel da impressora'), ('Anexo', 'arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Anexo adicionado com sucesso.')

    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Adicionar outros interessados')
    popup = popup_em(tela, 'adicionar_outros_interessados')
    anotar_tela('outros-interessados-popup', popup)
    popup.preencher('Outros Interessados', 'autocomplete multiplo', PAPEIS['colega'])
    capturar(tela.pagina, '08-outros-interessados')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Adição de outros interessados realizada com sucesso.')

    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.outros_interessados.filter(username=PAPEIS['colega']).exists(), 'o outro interessado não foi vinculado'


def test_resolver_e_concluir_chamado(logado_doc, capturar):
    """Tarefa 9 — o atendente resolve com o artigo e quem abriu fecha e avalia.

    Só o atendente do chamado resolve; só depois de Resolvido o chamado pode ser fechado — e
    quem fecha é quem abriu, na mesma tela em que avalia o atendimento.
    """
    chamado = chamado_do_solicitante()

    tela = Tela(logado_doc('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_aba('Artigos relacionados')
    tela.selecionar_cartao(ARTIGO)
    tela.preencher('Comentário', 'textarea', 'Chamado resolvido com a remoção do papel preso na bandeja.')
    capturar(tela.pagina, '09-resolver-chamado')
    tela.clicar_botao('Alterar para Resolvido')
    tela.sucesso('Alteração de situação realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.estah_resolvido(), 'o chamado não foi resolvido'
    assert chamado.historicostatus_set.filter(bases_conhecimento__titulo=ARTIGO).exists(), 'o artigo usado não ficou no histórico'

    tela = Tela(logado_doc('solicitante')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_link('Fechar Chamado')
    tela.ver_titulo('Fechar Chamado')
    anotar_tela('fechar-chamado-form', tela)
    capturar(tela.pagina, '09-fechar-chamado')
    # O formulário de fechamento é escrito à mão: as notas são radios `#rating-1..5` escondidos
    # pelo `stars.js` (clica-se a estrela, isto é, o `label`), e o botão de confirmação é um
    # `input[type=submit]` sem `value`.
    tela.loc('//label[@for="rating-5"]').first.click()
    tela.preencher('Comentário', 'textarea', 'Atendimento rápido e resolveu o problema.')
    tela.loc('//form[@id="fechareavaliarchamado_form"]//input[@type="submit"]').first.click()
    tela.sucesso('Alteração de situação realizada com sucesso.')
    chamado = type(chamado).objects.get(pk=chamado.pk)
    assert chamado.estah_fechado(), 'o chamado não foi fechado'
    assert chamado.nota_avaliacao == 5, 'a avaliação não foi registrada'
