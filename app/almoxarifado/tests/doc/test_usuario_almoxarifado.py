"""Roteiro navegado das tarefas do módulo ``almoxarifado`` — a fonte de
``almoxarifado/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

O ciclo é encadeado: o empenho nasce no teste 3 e a entrada de compra do teste 4 recebe
dele; a requisição nasce no teste 6 e é atendida no 7; a transferência do teste 8 é
atendida pelo campus de destino no próprio teste. Rodar uma fatia isolada não é suportado.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import escolher_autocomplete
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

UNIDADE = '/admin/almoxarifado/unidademedida/'
MATERIAL = '/admin/almoxarifado/materialconsumo/'
PLANO_CONTAS = '/admin/almoxarifado/planocontasalmox/'
ELEMENTO = '/admin/almoxarifado/categoriamaterialconsumo/'
EMPENHOS = '/almoxarifado/empenhos/'
ENTRADA_BUSCA = '/almoxarifado/entrada_busca/'
ENTRADA_DOACAO = '/almoxarifado/entrada_doacao/'
REQUISICAO = '/almoxarifado/form_requisicao_usuario_pedido/'
REQUISICOES_PENDENTES = '/almoxarifado/requisicoes_pendentes/'
INTERCAMPI = '/almoxarifado/form_requisicao_uo_pedido/'
CONFIGURACAO_ESTOQUE = '/almoxarifado/configuracao_estoque/'
SITUACAO_ESTOQUE = '/almoxarifado/situacao_estoque/'
BALANCETE_DETALHADO = '/almoxarifado/balancete_ed_detalhado/'
MATERIAIS_TRANSFERIDOS = '/almoxarifado/materiais_transferidos/'
SALDO_ED = '/almoxarifado/saldo_ed/'
SAIDAS_POR_SETOR = '/almoxarifado/relatorio/consumo_setor/'


def _escolher_jquery(page, seletor: str, texto: str, opcao: str | None = None):
    """Escolhe numa lista dos autocompletes jQuery antigos do módulo (``.ac_results``).

    O plugin (``almoxarifado/static/almoxarifado/js/jquery.autocomplete.js``) escuta
    ``keydown``; o ``fill()`` do Playwright não dispara evento de tecla e a lista nunca abre —
    por isso ``press_sequentially``.
    """
    campo = page.locator(seletor)
    campo.click()
    campo.press_sequentially(texto, delay=30)
    alvo = page.locator('.ac_results li').filter(has_text=opcao or texto).first
    expect(alvo).to_be_visible()
    alvo.click()


def _ultimo_empenho_da_doc():
    """O empenho criado pelo teste 3 (fora o do seed, que não tem item com saldo)."""
    from almoxarifado.models import Empenho

    empenho = Empenho.objects.filter(numero__startswith='2019NE').exclude(numero='20193012RE').order_by('-id').first()
    assert empenho is not None, 'empenho ausente: rode test_registrar_empenho antes'
    return empenho


# ---------------------------------------------------------------------------------------------
# Tarefa 1 — Cadastrar uma unidade de medida e um material de consumo
# ---------------------------------------------------------------------------------------------


def test_cadastrar_material_de_consumo(logado_almox, capturar):
    """Tarefa 1 — o almoxarifado prepara a base do catálogo: unidade de medida e material."""
    from almoxarifado.models import MaterialConsumo, UnidadeMedida

    page = logado_almox('CoordDeAlmoxSiste')
    UnidadeMedida.objects.filter(nome='Pacote').delete()

    tela = Tela(page).ir(UNIDADE)
    tela.ver_texto('Adicionar Unidade de Medida')
    capturar(page, 'unidade-medida-listagem')
    tela.clicar_botao('Adicionar Unidade de Medida')
    tela.esperar()
    page.fill('input[name=nome]', 'Pacote')
    capturar(page, 'unidade-medida-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Cadastro realizado com sucesso')
    assert UnidadeMedida.objects.filter(nome='Pacote').exists(), 'a unidade de medida não persistiu'

    MaterialConsumo.objects.filter(nome='Papel A4').delete()
    tela = tela.ir(MATERIAL)
    tela.ver_texto('Adicionar Material de Consumo')
    capturar(page, 'material-listagem')
    tela.clicar_botao('Adicionar Material de Consumo')
    tela.esperar()
    escolher_autocomplete(page, 'categoria', 'Categoria Material Consumo')
    escolher_autocomplete(page, 'unidade', 'Pacote')
    page.fill('textarea[name=nome], input[name=nome]', 'Papel A4')
    capturar(page, 'material-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Cadastro realizado com sucesso')
    assert MaterialConsumo.objects.filter(nome='Papel A4').exists(), 'o material não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 2 — Cadastrar o plano de contas e os elementos de despesa
# ---------------------------------------------------------------------------------------------


def test_cadastrar_plano_de_contas_e_elemento_de_despesa(logado_almox, capturar):
    """Tarefa 2 — a contabilidade mantém o plano de contas e os elementos de despesa."""
    from almoxarifado.models import CategoriaMaterialConsumo, PlanoContasAlmox

    page = logado_almox('ContadorAdministra')
    CategoriaMaterialConsumo.objects.filter(codigo='99').delete()
    PlanoContasAlmox.objects.filter(codigo='99').delete()

    tela = Tela(page).ir(PLANO_CONTAS)
    tela.ver_texto('Adicionar Plano de Contas')
    capturar(page, 'plano-contas-listagem')
    tela.clicar_botao('Adicionar Plano de Contas')
    tela.esperar()
    page.fill('input[name=codigo]', '99')
    page.fill('textarea[name=descricao], input[name=descricao]', 'MATERIAIS DE ESCRITÓRIO')
    capturar(page, 'plano-contas-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Cadastro realizado com sucesso')
    assert PlanoContasAlmox.objects.filter(codigo='99').exists(), 'o plano de contas não persistiu'

    tela = tela.ir(f'{ELEMENTO}add/')
    tela.esperar()
    page.fill('input[name=codigo]', '99')
    page.fill('input[name=nome]', 'MATERIAIS DE ESCRITÓRIO')
    escolher_autocomplete(page, 'plano_contas', 'MATERIAIS DE ESCRITÓRIO')
    capturar(page, 'elemento-despesa-formulario')
    page.click('input[name=_save]')
    tela.sucesso('Cadastro realizado com sucesso')
    assert CategoriaMaterialConsumo.objects.filter(codigo='99').exists(), 'o elemento de despesa não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 3 — Registrar um empenho (e empenhar um item)
# ---------------------------------------------------------------------------------------------


def test_registrar_empenho(logado_almox, capturar, doc_seed):
    """Tarefa 3 — o empenho é a porta de entrada do material; o item define o que se compra."""
    from almoxarifado.models import Empenho, EmpenhoConsumo

    page = logado_almox('CoordDeAlmoxSiste')
    tela = Tela(page).ir(EMPENHOS)
    tela.ver_titulo('Empenhos')
    capturar(page, 'empenho-listagem')

    tela.clicar_botao('Adicionar Empenho')
    tela.ver_titulo('Adicionar Empenho')
    numero = f'2019NE{uuid4().int % 10**6:06d}'
    page.fill('input[name=numero]', numero)
    escolher_autocomplete(page, 'uo', 'A0')
    escolher_autocomplete(page, 'processo', doc_seed['processo'].assunto)
    escolher_autocomplete(page, 'tipo_material', 'Consumo')
    escolher_autocomplete(page, 'pessoa_fisica', 'CoordDeAlmoxSiste')
    capturar(page, 'empenho-formulario')
    page.click('input[name=_save]')

    tela.ver_titulo(f'Empenho {numero}')
    page.get_by_text('Empenhar novo item').first.click()
    page.wait_for_load_state()
    escolher_autocomplete(page, 'material', 'Material de Consumo')
    page.fill('input[name=qtd_empenhada]', '2')
    page.fill('input[name=valor]', '200')
    capturar(page, 'empenho-item')
    page.click('input[name=empenhoconsumo_form]')
    tela.sucesso('Item de Empenho cadastrada com sucesso.')

    empenho = Empenho.objects.get(numero=numero)
    assert EmpenhoConsumo.objects.filter(empenho=empenho, material__nome='Material de Consumo').exists(), 'o item não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 4 — Efetuar a entrada de compra
# ---------------------------------------------------------------------------------------------


def test_efetuar_entrada_de_compra(logado_almox, capturar):
    """Tarefa 4 — receber o que foi comprado: a nota fiscal encontra o empenho no estoque."""
    from almoxarifado.models import Entrada

    page = logado_almox('CoordDeAlmoxSiste')
    empenho = _ultimo_empenho_da_doc()

    tela = Tela(page).ir(ENTRADA_BUSCA)
    tela.ver_titulo('Busca de Entradas')
    capturar(page, 'entrada-busca')
    page.get_by_role('link', name='Efetuar Entrada de Compra').click()

    tela.ver_titulo('Efetuar Entrada de Compra')
    _escolher_jquery(page, '#empenho', empenho.numero)
    expect(page.locator('#empenho_itens table')).to_be_visible()
    page.check('input[name=empenho_itens]')
    # O auto-preenchimento do plugin usa o decimal pt-BR do atributo (ex.: "2,00000"), que o
    # `input[type=number]` rejeita e deixa vazio: a quantidade é digitada à mão.
    page.locator('input[name=qtds]').first.fill('2')
    page.fill('input[name=numero_nota]', '123')
    page.fill('input[name=data_nota]', '2019-01-10')
    capturar(page, 'entrada-compra-formulario')
    page.click('input[value=Efetuar]')

    tela.sucesso('Entrada realizada com sucesso.')
    capturar(page, 'entrada-detalhe')
    assert Entrada.objects.filter(tipo_entrada__nome='compra').exists(), 'a entrada de compra não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 5 — Efetuar a entrada de doação
# ---------------------------------------------------------------------------------------------


def test_efetuar_entrada_de_doacao(logado_almox, capturar, doc_seed):
    """Tarefa 5 — doação não tem empenho: o processo e o doador substituem a nota de compra."""
    from almoxarifado.models import Entrada

    page = logado_almox('CoordDeAlmoxSiste')
    tela = Tela(page).ir(ENTRADA_DOACAO)
    tela.ver_titulo('Efetuar Entrada de Doação')
    page.fill('input[name=data]', '2019-01-15T00:00')
    page.select_option('select[name=tipo_material]', label='Consumo')
    escolher_autocomplete(page, 'vinculo_fornecedor', doc_seed['doador'].nome)
    escolher_autocomplete(page, 'processo', doc_seed['processo'].assunto)
    page.fill('input[name=numero_nota_fiscal]', 'DOACAO-123')
    page.fill('input[name=data_nota_fiscal]', '2019-01-14')
    capturar(page, 'entrada-doacao-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Entrada realizada com sucesso.')

    # Os itens da doação entram pela tela da entrada, num popup.
    tela.clicar_botao('Adicionar Item')
    popup = tela.popup()
    escolher_autocomplete(page, 'material', 'Material de Consumo', escopo=popup.raiz)
    popup.preencher_formulario([('Qtd', 'texto', '5'), ('Valor', 'texto', '10,00')])
    capturar(page, 'entrada-doacao-item')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Item adicionado com sucesso.')
    assert Entrada.objects.filter(numero_nota_fiscal='DOACAO-123').exists(), 'a doação não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 6 — Registrar uma requisição de saída de material
# ---------------------------------------------------------------------------------------------


def test_registrar_requisicao_de_material(logado_almox, capturar, doc_seed, almoxarifado_a0):
    """Tarefa 6 — o almoxarifado registra o pedido do servidor (a tela é de operador)."""
    from almoxarifado.models import RequisicaoAlmoxUser

    page = logado_almox('CoordDeAlmoxSiste')
    tela = Tela(page).ir(REQUISICAO)
    tela.ver_titulo('Requisição de Saída de Material para Consumo')

    _escolher_jquery(page, '#solicitante', 'Joana', opcao=doc_seed['solicitante'].pessoa_fisica.nome)
    _escolher_jquery(page, '#material_1', 'Material de Consumo')
    page.fill('#qtd_1', '4')
    capturar(page, 'requisicao-formulario')
    page.click('input[value=Efetuar]')

    tela.sucesso('Requisição efetuada com sucesso.')
    assert RequisicaoAlmoxUser.objects.filter(vinculo_solicitante__pessoa__nome='Joana Souza').exists(), 'a requisição não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 7 — Atender as requisições pendentes
# ---------------------------------------------------------------------------------------------


def test_atender_requisicao(logado_almox, capturar, almoxarifado_a0):
    """Tarefa 7 — responder a fila dá baixa no estoque; atendimento parcial é o caso comum."""
    from almoxarifado.models import MaterialEstoque, RequisicaoAlmoxUser

    page = logado_almox('CoordDeAlmoxSiste')
    requisicao = RequisicaoAlmoxUser.objects.filter(avaliada=False, vinculo_solicitante__pessoa__nome='Joana Souza').latest('id')
    item = requisicao.item_set.first()
    uo, _, material = almoxarifado_a0
    antes = MaterialEstoque.objects.get(material=material, uo=uo).quantidade

    tela = Tela(page).ir(REQUISICOES_PENDENTES)
    tela.ver_titulo('Requisições Pendentes')
    capturar(page, 'requisicoes-pendentes')
    page.locator(f'a[href="/almoxarifado/requisicao_detalhe/user/{requisicao.pk}/"]').click()

    tela.ver_titulo(f'Requisição #{requisicao.pk}')
    capturar(page, 'requisicao-atendimento')
    page.check(f'input[name=idRequisicoesMaterial][value="{item.pk}"]')
    page.fill(f'#qtd{item.pk}', '2')
    page.get_by_role('button', name='Responder').click()

    tela.sucesso('Saída de Material Realizada')
    depois = MaterialEstoque.objects.get(material=material, uo=uo).quantidade
    assert depois == antes - 2, f'o estoque deveria cair 2 (atendido), foi de {antes} para {depois}'


# ---------------------------------------------------------------------------------------------
# Tarefa 8 — Transferir material entre campi
# ---------------------------------------------------------------------------------------------


def test_transferir_material_intercampi(logado_almox, capturar, doc_seed, logado):
    """Tarefa 8 — a requisição intercampi é pedida ao almoxarifado de outro campus."""
    from almoxarifado.models import RequisicaoAlmoxUO

    page = logado_almox('CoordDeAlmoxSiste')
    tela = Tela(page).ir(INTERCAMPI)
    tela.ver_titulo('Requisição de Transferência de Material de Consumo Intercampi')
    page.select_option('select[name=uo_id]', label='B0')
    _escolher_jquery(page, '#material_1', 'Material de Consumo')
    page.fill('#qtd_1', '3')
    capturar(page, 'transferencia-formulario')
    page.click('input[value=Efetuar]')
    tela.sucesso('Requisição efetuada com sucesso.')
    requisicao = RequisicaoAlmoxUO.objects.latest('id')
    assert requisicao.item_set.filter(material__nome='Material de Consumo').exists(), 'a transferência não persistiu'

    # O campus de destino vê o pedido na aba "Saída para Outros Campi" e o atende.
    page_b0 = logado(doc_seed['coord_b0'].matricula)
    tela = Tela(page_b0).ir(REQUISICOES_PENDENTES)
    tela.clicar_aba('Saída para Outros Campi')
    capturar(page_b0, 'transferencia-pendente')
    page_b0.locator(f'a[href="/almoxarifado/requisicao_detalhe/uo/{requisicao.pk}/"]').click()

    tela = Tela(page_b0).esperar()
    tela.ver_titulo(f'Requisição #{requisicao.pk}')
    capturar(page_b0, 'transferencia-atendimento')
    item = requisicao.item_set.first()
    page_b0.check(f'input[name=idRequisicoesMaterial][value="{item.pk}"]')
    page_b0.fill(f'#qtd{item.pk}', '3')
    page_b0.get_by_role('button', name='Responder').click()
    tela.sucesso('Saída de Material Realizada')


# ---------------------------------------------------------------------------------------------
# Tarefa 9 — Controlar o estoque crítico
# ---------------------------------------------------------------------------------------------


def test_controlar_estoque_critico(logado_almox, capturar):
    """Tarefa 9 — declarar o material controlado e acompanhar a situação do estoque do campus."""
    from almoxarifado.models import ConfiguracaoEstoque

    page = logado_almox('CoordDeAlmoxSiste')
    ConfiguracaoEstoque.objects.filter(material__nome='Material de Consumo').delete()

    # O menu abre a situação do estoque; a configuração do material controlado sai do botão.
    tela = Tela(page).ir(SITUACAO_ESTOQUE)
    tela.ver_titulo('Situação do Estoque')
    tela.clicar_botao('Adicionar Material Controlado')
    popup = tela.popup()
    escolher_autocomplete(page, 'material', 'Material de Consumo', escopo=popup.raiz)
    popup.preencher_formulario([('Tempo de Aquisição', 'texto', '1'), ('Intervalo de Aquisição', 'texto', '2')])
    capturar(page, 'configuracao-estoque')
    assert ConfiguracaoEstoque.objects.filter(material__nome='Material de Consumo').count() == 0, 'a configuração sob controle devia começar vazia'
    popup.clicar_botao('Enviar')
    # O save re-renderiza a própria tela dentro do iframe (não fecha o popup): o desfecho é a
    # linha nova no corpo da tabela "Materiais Sob Controle" (o cabeçalho já tem o texto).
    expect(popup.raiz.locator('table tbody tr', has_text='Material de Consumo')).to_have_count(1)
    assert ConfiguracaoEstoque.objects.filter(material__nome='Material de Consumo').exists(), 'a configuração não persistiu'

    # A lista dos materiais sob controle fica na tela de configuração.
    tela = Tela(page).ir(CONFIGURACAO_ESTOQUE)
    tela.ver_titulo('Controle de Estoque de Materiais')
    capturar(page, 'materiais-sob-controle')

    tela = tela.ir(SITUACAO_ESTOQUE)
    tela.ver_titulo('Situação do Estoque')
    capturar(page, 'estoque-critico')


# ---------------------------------------------------------------------------------------------
# Tarefa 10 — Consultar os relatórios
# ---------------------------------------------------------------------------------------------


def test_consultar_relatorios(logado_almox, capturar):
    """Tarefa 10 — os balancetes, o saldo, os materiais transferidos e as saídas por setor."""
    from datetime import date

    from almoxarifado.models import CategoriaMaterialConsumo

    page = logado_almox('CoordDeAlmoxSiste')
    hoje = date.today().isoformat()
    elemento = CategoriaMaterialConsumo.objects.get(nome='Categoria Material Consumo')

    tela = Tela(page).ir(BALANCETE_DETALHADO)
    tela.ver_titulo('Balancete Elemento de Despesa Detalhado')
    page.select_option('select[name=elemento_de_despesa]', value=str(elemento.pk))
    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', hoje)
    capturar(page, 'relatorio-balancete')
    page.click('input[name=balanceteeddetalhado_form]')
    expect(page.get_by_role('heading', name=re.compile('Gerar Relatório de Balancete de Elemento de Despesa Detalhado'))).to_be_visible()
    capturar(page, 'relatorio-processamento')

    tela = Tela(page).ir(MATERIAIS_TRANSFERIDOS)
    tela.ver_titulo('Materiais Transferidos')
    escolher_autocomplete(page, 'vinculo_solicitante', 'CoordDeAlmoxSiste')
    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', hoje)
    capturar(page, 'relatorio-materiais-transferidos')
    page.click('input[name=notasfornecimento_form]')
    tela.esperar()

    tela = tela.ir(SALDO_ED)
    tela.ver_titulo('Relatório Saldo Atual por Elemento de Despesa')
    # O `change` do select dispara o POST do relatório (o `search-and-filters` do SUAP
    # auto-submete): esperar a navegação antes de capturar, ou o `evaluate` do `capturar`
    # cai com o contexto destruído no meio dela.
    with page.expect_navigation():
        page.select_option('select[name=campus]', label='A0')
    tela.esperar()
    capturar(page, 'relatorio-saldo-ed')

    tela = tela.ir(SAIDAS_POR_SETOR)
    tela.ver_titulo('Saída por Setor')
    capturar(page, 'relatorio-saidas-por-setor')
