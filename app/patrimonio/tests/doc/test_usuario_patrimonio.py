"""Roteiro navegado das tarefas do módulo ``patrimonio`` — a fonte de
``patrimonio/docs/usuario.md``.

O módulo não tem inventário de tarefas colhido (``docs/agents/inventario-tarefas.yaml`` não
tem ``patrimonio``) nem ``features/``: as tarefas abaixo foram **propostas** a partir do
``menu.yaml``, das telas e dos testes existentes, e validadas navegando o sistema — o
relatório do MR diz isso ao revisor.

Um teste por tarefa da doc. As asserções são a mensagem de sucesso e/ou a persistência, e
existem para a rodada falhar alto quando a tela mudou de forma. O ciclo é encadeado onde o
fluxo é: a requisição de transferência do teste 3 é avaliada e deferida no 4.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import re
from datetime import date
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import escolher_autocomplete
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

BUSCA = '/patrimonio/inventario_busca/'
CARGA = '/patrimonio/carga/'
REQUISITAR_TRANSFERENCIA = '/patrimonio/requisitar_transferencia/'
BAIXA_ADMIN = '/admin/patrimonio/baixa/add/'
CAUTELA_ADMIN = '/admin/patrimonio/cautela/add/'
CONFERENCIA_ADMIN = '/admin/patrimonio/conferenciasala/add/'


def _bem(papel: str, doc_seed):
    """O tombamento ativo reservado a uma tarefa da doc."""
    return doc_seed['ativos'][papel]


def _escolher_inventario(page, numero: int):
    """Escolhe, no autocomplete múltiplo de inventários, o item do tombo ``numero``.

    O ``escolher_autocomplete`` casa por ``has_text``, e o número do tombo aparece dentro da
    descrição de todos os itens (``... Latitude 3420``): sem ancorar no início do rótulo
    (``4 - Notebook...``), a escolha cai no primeiro item da lista — foi um flake real da
    rodada completa.
    """
    campo = page.locator('select[name="inventarios"] + span.select2').first
    campo.click()
    busca = page.locator('span.select2-search--dropdown input')
    if busca.count():
        busca.first.fill(str(numero))
    else:
        page.keyboard.type(str(numero))
    expect(page.locator('.select2-results__option.loading-results')).to_have_count(0)
    opcao = page.locator('.select2-results__option').filter(has_text=re.compile(rf'^{numero} - ')).first
    expect(opcao).to_be_visible()
    opcao.click()


# ---------------------------------------------------------------------------------------------
# Tarefa 1 — Consultar e atualizar um bem do inventário
# ---------------------------------------------------------------------------------------------


def test_consultar_e_atualizar_um_bem(logado, capturar, doc_seed):
    """Tarefa 1 — achar o tombamento pela busca, abrir a ficha, ver o histórico e editar."""
    from patrimonio.models import Inventario

    page = logado('159001')
    inventario = _bem('consulta', doc_seed)

    tela = Tela(page).ir(BUSCA)
    page.fill('input[name=numero]', str(inventario.numero))
    capturar(page, 'inventario-busca')
    page.click('input[type=submit]')

    tela.linha(str(inventario.numero)).clicar_link(str(inventario.numero))
    tela = Tela(page).esperar()
    tela.ver_texto(str(inventario.numero))
    capturar(page, 'inventario-ficha')

    tela.clicar_botao('Editar')
    nova_descricao = f'Notebook Dell Latitude 3420 (revisado {uuid4().hex[:4]})'
    page.fill('textarea[name=descricao]', nova_descricao)
    capturar(page, 'inventario-editar')
    tela.clicar_botao('Salvar')
    tela.sucesso('Inventário salvo com sucesso.')
    assert Inventario.objects.get(pk=inventario.pk).descricao == nova_descricao, 'a edição não persistiu'

    tela = tela.ir(f'/patrimonio/historico_movimentacao_inventario/{inventario.numero}/')
    tela.esperar()
    capturar(page, 'inventario-historico')


# ---------------------------------------------------------------------------------------------
# Tarefa 2 — Dar carga nos bens pendentes
# ---------------------------------------------------------------------------------------------


def test_dar_carga_nos_inventarios_pendentes(logado, capturar, doc_seed):
    """Tarefa 2 — a requisição de carga entrega os tombamentos pendentes a um servidor."""
    from patrimonio.models import Requisicao

    page = logado('159001')
    tela = Tela(page).ir(CARGA)
    tela.ver_texto('Criar Requisição de Carga de Inventários Pendentes')
    capturar(page, 'carga-pendentes')

    for inventario in doc_seed['pendentes']:
        page.check(f'input[name=inventarios][value="{inventario.pk}"]')
    escolher_autocomplete(page, 'servidor_destino', 'Sofia')
    page.select_option('select[name=estado_conservacao]', label='Bom')
    escolher_autocomplete(page, 'sala', 'Laboratório')
    page.fill('textarea[name=descricao]', 'Carga inicial do laboratório de informática')
    capturar(page, 'carga-formulario')
    tela.clicar_botao('Criar requisição de carga para os inventários selecionados')

    tela.sucesso('Requisição criada com sucesso.')
    assert Requisicao.objects.filter(descricao='Carga inicial do laboratório de informática').exists(), 'a requisição de carga não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 3 — Requisitar a transferência de um bem
# ---------------------------------------------------------------------------------------------


def test_requisitar_transferencia(logado, capturar, doc_seed):
    """Tarefa 3 — o servidor pede a transferência de um bem da própria carga."""
    from patrimonio.models import Requisicao, RequisicaoItem

    page = logado('159003')
    inventario = _bem('transferencia', doc_seed)

    tela = Tela(page).ir(REQUISITAR_TRANSFERENCIA)
    tela.ver_texto('Requisitar Transferência')
    escolher_autocomplete(page, 'servidor_destino', 'Diego Destino')
    page.check('input[name=tipo_transferencia][value="inventarios"]')
    _escolher_inventario(page, inventario.numero)
    page.fill('textarea[name=descricao]', 'Transferência do notebook para o campus de destino')
    capturar(page, 'transferencia-formulario')
    tela.clicar_botao('Enviar')

    tela.sucesso('Requisição de transferência de patrimônio efetuada com sucesso.')
    requisicao = Requisicao.objects.latest('id')
    assert RequisicaoItem.objects.filter(requisicao=requisicao, inventario=inventario).exists(), 'o item da transferência não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 4 — Avaliar e deferir a transferência
# ---------------------------------------------------------------------------------------------


def test_avaliar_e_deferir_transferencia(logado, capturar, doc_seed):
    """Tarefa 4 — o servidor de destino aprova os itens, defere a requisição e informa as PAs."""
    from patrimonio.models import Requisicao, RequisicaoItem

    requisicao = Requisicao.objects.filter(status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO).latest('id')
    item = RequisicaoItem.objects.get(requisicao=requisicao)

    page = logado('159004')
    tela = Tela(page).ir(f'/patrimonio/requisicao/{requisicao.pk}/')
    tela.ver_texto(f'Requisição de Transferência #{requisicao.pk}')
    capturar(page, 'requisicao-detalhe')

    page.check(f'input[name=itens][value="{item.pk}"]')
    tela.clicar_botao('Aprovar apenas selecionados')
    tela.sucesso('Inventários avaliados com sucesso')
    item.refresh_from_db()
    assert item.situacao == RequisicaoItem.APROVADO, 'o item não foi aprovado'

    tela.clicar_botao('Deferir')
    tela = Tela(page).esperar()
    capturar(page, 'requisicao-deferir')
    tela.clicar_botao('Salvar')
    tela.esperar()
    requisicao.refresh_from_db()
    assert requisicao.status == Requisicao.STATUS_DEFERIDA, 'a requisição não foi deferida'
    inventario = item.inventario
    inventario.refresh_from_db()
    assert inventario.responsavel_vinculo_id == doc_seed['servidores']['coord_destino'].get_vinculo().pk, 'o bem não foi para a carga do destino'
    tela = Tela(page).ir(f'/patrimonio/requisicao/{requisicao.pk}/')
    capturar(page, 'requisicao-deferida')


# ---------------------------------------------------------------------------------------------
# Tarefa 5 — Efetuar a baixa de um bem
# ---------------------------------------------------------------------------------------------


def test_efetuar_baixa(logado, capturar, doc_seed):
    """Tarefa 5 — a portaria de baixa registra o bem que sai do patrimônio."""
    from patrimonio.models import Baixa, Inventario, InventarioStatus

    page = logado('159001')
    inventario = _bem('baixa', doc_seed)

    tela = Tela(page).ir(BAIXA_ADMIN)
    tela.ver_texto('Adicionar Baixa')
    page.fill('input[name=data]', f'{date.today().isoformat()}T12:00')
    escolher_autocomplete(page, 'tipo', 'doacao')
    page.fill('input[name=numero]', f'{uuid4().int % 10**5:05d}/2026')
    page.fill('input[name=observacao]', 'Bem inservível, doado conforme portaria')
    escolher_autocomplete(page, 'uo', 'A0')
    capturar(page, 'baixa-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Baixa adicionada com sucesso')
    baixa = Baixa.objects.latest('id')

    tela = tela.ir(f'/patrimonio/baixa/{baixa.pk}/')
    tela.ver_texto(f'Baixa {baixa.numero}')
    tela.clicar_botao('Baixar Novo Inventário')
    page.check('input[name=tipo_baixa][value="inventario"]')
    escolher_autocomplete(page, 'inventario', str(inventario.numero))
    capturar(page, 'baixa-tela')
    tela.clicar_botao('Enviar')
    tela.sucesso('Baixa efetuada com sucesso.')
    assert Inventario.objects.get(pk=inventario.pk).status == InventarioStatus.BAIXADO(), 'o bem não foi baixado'


# ---------------------------------------------------------------------------------------------
# Tarefa 6 — Emitir uma cautela
# ---------------------------------------------------------------------------------------------


def test_emitir_cautela(logado, capturar, doc_seed):
    """Tarefa 6 — a cautela entrega bens sob responsabilidade de alguém por um período."""
    from patrimonio.models import Cautela, CautelaInventario

    page = logado('159002')
    inventario = _bem('cautela', doc_seed)

    tela = Tela(page).ir(CAUTELA_ADMIN)
    tela.ver_texto('Adicionar Cautela')
    escolher_autocomplete(page, 'responsavel', 'Sofia Servidora')
    page.fill('input[name=data_inicio]', '2026-09-01')
    page.fill('input[name=data_fim]', '2026-12-31')
    page.fill('textarea[name=descricao]', 'Cautela do notebook para trabalho remoto')
    capturar(page, 'cautela-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Cautela adicionada com sucesso')
    cautela = Cautela.objects.latest('id')

    tela = tela.ir(f'/patrimonio/cautela/{cautela.pk}/')
    tela.ver_texto(f'Cautela #{cautela.pk}')
    tela.clicar_botao('Adicionar Novo Item')
    escolher_autocomplete(page, 'inventario', str(inventario.numero))
    capturar(page, 'cautela-detalhe')
    tela.clicar_botao('Salvar')
    tela.sucesso('Item da Cautela cadastrado com sucesso.')
    assert CautelaInventario.objects.filter(cautela=cautela, inventario=inventario).exists(), 'o item da cautela não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 7 — Conferir uma sala
# ---------------------------------------------------------------------------------------------


def test_conferir_sala(logado, capturar, doc_seed):
    """Tarefa 7 — a conferência de sala lista os bens que o coletor ainda não leu."""
    from patrimonio.models import ConferenciaSala

    page = logado('159001')

    tela = Tela(page).ir(CONFERENCIA_ADMIN)
    tela.ver_texto('Adicionar Conferência de Sala')
    escolher_autocomplete(page, 'sala', 'Laboratório de Informática')
    escolher_autocomplete(page, 'responsavel', 'Sofia Servidora')
    capturar(page, 'conferencia-formulario')
    page.click('input[name=_save]')
    tela = Tela(page).esperar()
    conferencia = ConferenciaSala.objects.latest('id')
    assert conferencia.sala == doc_seed['sala'], 'a conferência não persistiu'

    tela = tela.ir(f'/patrimonio/conferenciasala/{conferencia.pk}/')
    tela.esperar()
    capturar(page, 'conferencia-sala')

    tela = tela.ir(f'/patrimonio/autorizar_coletor/{conferencia.pk}/')
    tela.ver_texto('QRCode para Leitura')
    capturar(page, 'conferencia-coletor')


# ---------------------------------------------------------------------------------------------
# Tarefa 8 — Reavaliar e ajustar o valor de um bem
# ---------------------------------------------------------------------------------------------


def test_reavaliar_e_ajustar_valor(logado, capturar, doc_seed):
    """Tarefa 8 — a coordenação corrige o valor do bem (reavaliação e valor recuperável)."""
    from patrimonio.models import Inventario

    page = logado('159001')
    inventario = _bem('consulta', doc_seed)
    valor_antes = Inventario.objects.get(pk=inventario.pk).valor

    tela = Tela(page).ir(f'/patrimonio/inventario_reavaliar/{inventario.pk}/')
    tela.ver_texto('Reavaliar Inventário')
    page.fill('input[name=valor]', '500,00')
    page.fill('textarea[name=motivo]', 'Reavaliação anual do bem')
    capturar(page, 'reavaliar-formulario')
    tela.clicar_botao('Enviar')
    tela.sucesso('Inventário reavaliado com sucesso.')
    assert Inventario.objects.get(pk=inventario.pk).valor == valor_antes + 500, 'a reavaliação não persistiu'

    tela = tela.ir(f'/patrimonio/inventario_ajustar_valor/{inventario.pk}/')
    tela.ver_texto('Ajustar Valor Recuperável Inventário')
    page.fill('input[name=valor]', '100,00')
    page.fill('textarea[name=motivo]', 'Ajuste do valor recuperável')
    capturar(page, 'ajustar-valor-formulario')
    tela.clicar_botao('Enviar')
    tela.sucesso('Ajuste do valor recuperável realizado com sucesso.')


# ---------------------------------------------------------------------------------------------
# Tarefa 9 — Consultar os relatórios
# ---------------------------------------------------------------------------------------------


def test_consultar_relatorios(logado, capturar, doc_seed):
    """Tarefa 9 — depreciação, totalizações, cargas por servidor e termos."""
    page = logado('159001')

    tela = Tela(page).ir('/patrimonio/inventario_depreciacao/')
    tela.esperar()
    capturar(page, 'relatorio-depreciacao')

    tela = tela.ir('/patrimonio/total_ed_periodo/')
    tela.ver_texto('Totalização por Elemento de Despesa por Período de Entrada')
    capturar(page, 'relatorio-totalizacao-ed')

    tela = tela.ir('/patrimonio/servidores_com_carga/')
    tela.esperar()
    capturar(page, 'relatorio-servidores-carga')

    tela = tela.ir('/patrimonio/relatorios/inventarios_nao_conferidos/')
    tela.esperar()
    capturar(page, 'relatorio-nao-conferidos')

    tela = tela.ir('/patrimonio/termos/')
    tela.esperar()
    capturar(page, 'relatorio-termos')
