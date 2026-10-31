"""Roteiro navegado das tarefas do ``gerenciador_projetos`` — a fonte de ``docs/usuario.md``.

Um teste por tarefa (ou etapa) da doc; dentro do teste, os passos que a doc descreve,
executados de verdade. As asserções existem para a rodada falhar alto quando a tela mudou de
forma: doc que descreve um passo que não existe mais é pior que doc velha.

O módulo não tem ``features/`` — as tarefas foram **propostas** (menu + admin + views), não
colhidas do inventário de tarefas. A cadeia é deliberada: o projeto nasce pela UI no teste 1
e os demais o reencontram por ``projeto_da_rodada`` (âncora no gerente da suíte). O banco é
compartilhado entre os módulos da rodada e não há flush entre testes, então cada busca por
nome é qualificada por ``projeto`` ou pelo gerente — os nomes, que aparecem nas capturas,
ficam livres de sufixo de unicidade.

A ordem de EXECUÇÃO difere da ordem da doc num ponto, de propósito: o projeto só é posto
"Em andamento" (tarefa 1, etapa 2 da doc) depois que as tarefas nascem. É o que permite
executar — e não só ler no código — o aviso que o SUAP dá a cada tarefa criada enquanto o
projeto está Aberto, que é a razão de a etapa 2 existir.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import TEMPO_NAVEGACAO, Tela
from gerenciador_projetos.tests.doc.conftest import AREA_ATUACAO, PAPEIS, TIPO_ATIVIDADE

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DESTINO = Path(settings.BASE_DIR) / 'gerenciador_projetos' / 'docs' / 'usuario'

LISTAGEM = '/admin/gerenciador_projetos/projeto/'
MINHAS_TAREFAS = '/gerenciador_projetos/minhastarefas/'
# Quadros sintéticos de Minhas tarefas, gravados a fio em `templates/minhas_tarefas.html`
# (`data-lista-id`). Não são listas: no Dashboard o mesmo `0` é *Tarefas sem lista*.
QUADRO_ANDAMENTO = 0
QUADRO_CONCLUIDAS = 1

# Nomes que a cadeia cria pela UI e reencontra depois. Aparecem nas capturas, então são
# nomes de trabalho plausíveis e SEM sufixo de unicidade: a unicidade vem da âncora da
# fixture `projeto_da_rodada` (o gerente) e do filtro por `projeto` nas buscas por nome.
N_PROJETO = 'Modernização do Laboratório de Informática'
N_LISTA_1 = 'A Fazer'
N_LISTA_2 = 'Em Execução'
N_LISTA_3 = 'Concluído'
N_TAG = 'Urgente'
N_TAREFA_1 = 'Elaborar cronograma'
N_TAREFA_2 = 'Coletar requisitos'
N_SUBTAREFA = 'Entrevistar as coordenações'

AVISO_PROJETO_ABERTO = 'Este projeto ainda está com situação Aberto, favor editar o projeto e corrigir a situação.'


# -- auxiliares --------------------------------------------------------------------------


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, abas, botões e rótulos para a redação da doc (não é asserção).

    Arquivo, e não só stderr: quando a rodada fica VERDE o pytest engole o stderr capturado,
    e é justamente a rodada verde que produz a doc. Fica ao lado das capturas, no diretório
    que o ``.gitignore`` já exclui.
    """
    tela.esperar()
    cabecalhos = tela.raiz.get_by_role('heading').all_inner_texts()
    abas = tela.raiz.locator('//*[contains(@class, "nav-link") and ancestor::*[contains(@class, "nav-tabs")]]').all_inner_texts()
    despejo = (
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  abas: {[a.strip() for a in abas if a.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}\n'
    )
    DESTINO.mkdir(parents=True, exist_ok=True)
    with (DESTINO / 'anotacoes.txt').open('a', encoding='utf-8') as arquivo:
        arquivo.write(despejo)
    sys.stderr.write(despejo)


def _ir_dashboard(tela: Tela, projeto) -> Tela:
    """Navega ao Dashboard driblando o reload do ``sessionStorage``.

    ``dashboard.html:6-11`` recarrega a página uma vez quando o sinal de "dados antigos"
    está no storage (a cada duas visitas). O reload pega o teste no meio do clique no popup;
    limpar a chave depois de carregar anula o sinal para a próxima visita. O ``ir`` vem
    antes do ``evaluate`` de propósito: numa página recém-aberta (``about:blank``) a leitura
    do ``sessionStorage`` lança ``SecurityError``.
    """
    tela.ir(f'/gerenciador_projetos/projeto/{projeto.pk}/dashboard/')
    try:
        tela.pagina.evaluate("sessionStorage.removeItem('dashboard_gerenciador_projetos')")
    except Exception:
        pass
    return tela


def _coluna(tela: Tela, lista_id: int) -> Locator:
    """O quadro (coluna) de uma lista no Dashboard; ``0`` é o de *Tarefas sem lista*."""
    return tela.pagina.locator(f'.board-container[data-lista-id="{lista_id}"]').first


def _clicar_adicionar_tarefa_da_coluna(tela: Tela, lista_id: int) -> Tela:
    """Clique no ``+`` do quadro da lista no Dashboard — o passo que a doc descreve."""
    alvo = _coluna(tela, lista_id).locator('.title-container a.popup').first
    expect(alvo).to_be_visible()
    alvo.click()
    return tela


def _arrastar_percentual(popup: Tela, percentual: int) -> None:
    """Leva o slider *Percentual executado* ao valor (o ``Tela`` não tem tipo para ``input type=range``)."""
    slider = popup.raiz.locator('#id_percentual_executado')
    slider.fill(str(percentual))
    expect(popup.raiz.locator('#id_percentual_executado + output')).to_have_text(f'{percentual}%')


def _limpar_banners(tela: Tela) -> None:
    """Remove os banners de feedback do documento atual.

    O banner de uma ação anterior satisfaz o desfecho do popup seguinte
    (``esperar_desfecho_do_popup`` aceita ``p#feedback_message`` já presente) antes de o
    POST terminar — o ``salvar_no_popup`` volta na hora e a asserção seguinte lê o banco
    antes do commit. Medido em 06/08/2026 na segunda evolução da tarefa 4.
    """
    tela.pagina.locator('p#feedback_message').evaluate_all('els => els.forEach(e => e.remove())')


def _esperar_tarefa_salva_no_popup(tela: Tela) -> Locator:
    """O ``Salvar`` do popup de tarefa redireciona o IFRAME para a página da tarefa.

    Diferente do desfecho que ``salvar_no_popup`` espera (fechar o fancybox e recarregar a
    página de trás): ``gerenciar_tarefa`` responde com ``httprr(tarefa.get_absolute_url(),
    ...)``, então o iframe navega para a tarefa com o banner — sem fechar o popup. A espera é
    no frame, não na página. Devolve os banners do frame, para quem precisa afirmar o aviso de
    projeto Aberto que vem junto (``messages.html`` dá o mesmo ``id`` a cada mensagem — filtrar
    pelo texto não depende da ordem de renderização).
    """
    banners = tela.pagina.frame_locator('iframe.fancybox-iframe').locator('p#feedback_message')
    try:
        expect(banners.filter(has_text='Operação realizada com sucesso')).to_be_visible(timeout=TEMPO_NAVEGACAO)
    except AssertionError as falha:
        frame = tela.pagina.frame_locator('iframe.fancybox-iframe')
        try:
            url = frame.locator('body').evaluate('() => window.location.href')
            erros = frame.locator('p.errornote, ul.errorlist li').all_inner_texts()
        except Exception:
            url, erros = '<iframe indisponível>', []
        raise AssertionError(f'popup não mostrou a tarefa salva. iframe url: {url} | erros: {erros}') from falha
    return banners


def _menu(tela: Tela, titulo: str) -> Locator:
    """Abre o menu suspenso da barra de ações cujo botão tem ``title=titulo`` e devolve o ``<ul>``.

    O submenu está no DOM o tempo todo, escondido por CSS até o clique no botão pai
    (``comum/static/comum/js/main.js``, ``init_action_bar``) — é o gesto do usuário.
    """
    item = tela.pagina.locator(f'xpath=//ul[contains(@class, "action-bar")]/li[contains(@class, "has-child")][a[@title="{titulo}"]]').first
    item.locator('xpath=./a').click()
    submenu = item.locator('xpath=./ul')
    expect(submenu).to_be_visible()
    return submenu


def _abrir_visualizacao(tela: Tela, rotulo: str) -> Tela:
    """Escolhe ``rotulo`` no submenu **Visualização** (o botão do olho) da página do projeto."""
    item = tela.pagina.locator(
        'xpath=//ul[contains(@class, "action-bar")]/li[contains(@class, "has-child")][a[contains(normalize-space(.), "Visualização")]]'
    ).first
    item.locator('xpath=./a').click()
    opcao = item.locator('xpath=./ul//a', has_text=rotulo).first
    expect(opcao).to_be_visible()
    opcao.click()
    return tela.esperar()


def _opcoes_de_visualizacao(tela: Tela) -> list[str]:
    """Os itens do submenu **Visualização** que o perfil logado recebe (estão no DOM, ocultos)."""
    item = tela.pagina.locator(
        'xpath=//ul[contains(@class, "action-bar")]/li[contains(@class, "has-child")][a[contains(normalize-space(.), "Visualização")]]'
    ).first
    return [texto.strip() for texto in item.locator('xpath=./ul//a').all_text_contents()]


def _arrastar_cartao(tela: Tela, tarefa_id: int, lista_id: int) -> dict:
    """Arrasta o cartão da tarefa para o fim do quadro ``lista_id`` com o mouse, como o usuário.

    O Dashboard usa o ``sortable`` do jQuery UI, que só reage a uma sequência real de
    ``mousedown`` → movimentos → ``mouseup`` (``drag_to`` do Playwright salta direto). O ponto
    de pegada é o rodapé do cartão, longe do link do título e da barra de ações.

    A janela é ampliada durante o gesto: os quadros ficam lado a lado sem quebra de linha, e na
    janela padrão do Playwright (1280x720) o terceiro já nasce fora da tela — o mouse não chega
    lá e o gesto vira seleção de texto. A ``capturar`` volta a janela ao tamanho da doc.

    Devolve o JSON com que o servidor respondeu ao ``mudarlista`` — é por ele que se sabe se a
    mudança foi gravada, porque a tela mostra o cartão no quadro novo em qualquer caso.
    """
    pagina = tela.pagina
    pagina.set_viewport_size({'width': 1920, 'height': 1200})
    pagina.evaluate('window.scrollTo(0, 0)')
    cartao = pagina.locator(f'.beautiful-board-item[data-tarefa-id="{tarefa_id}"]').first
    expect(cartao).to_be_visible()
    origem = cartao.bounding_box()
    destino = _coluna(tela, lista_id).bounding_box()
    assert origem, 'cartão sem caixa na tela'
    assert destino, 'quadro sem caixa na tela'
    x, y = origem['x'] + 15, origem['y'] + origem['height'] - 12
    with pagina.expect_response(lambda resposta: '/mudarlista/' in resposta.url) as resposta:
        pagina.mouse.move(x, y)
        pagina.mouse.down()
        pagina.mouse.move(x + 10, y + 10, steps=5)
        pagina.mouse.move(destino['x'] + destino['width'] / 2, destino['y'] + destino['height'] - 15, steps=25)
        pagina.mouse.up()
    tela.esperar()
    expect(_coluna(tela, lista_id).locator(f'.beautiful-board-item[data-tarefa-id="{tarefa_id}"]')).to_be_visible()
    return resposta.value.json()


def _resultados_do_autocomplete(tela: Tela, rotulo: str, busca: str) -> list[str]:
    """Digita ``busca`` no autocomplete múltiplo de ``rotulo`` e devolve as opções oferecidas, sem escolher.

    Serve para afirmar quem o campo NÃO oferece. Fecha o dropdown e limpa a busca na saída.
    """
    campo = tela.raiz.locator(
        f'xpath=//label[normalize-space(text())="{rotulo}:"]/ancestor::div[contains(@class, "form-row")][1]//input[contains(@class, "select2-search__field")]'
    ).first
    campo.click()
    campo.fill(busca)
    opcoes = tela.raiz.locator('li.select2-results__option')
    expect(opcoes.first).to_be_visible()
    expect(tela.raiz.locator('li.select2-results__option.loading-results')).to_have_count(0)
    textos = [texto.strip() for texto in opcoes.all_inner_texts()]
    campo.fill('')
    campo.press('Escape')
    return textos


def _topo(tela: Tela) -> None:
    """Rola a página ao topo antes da captura de formulário com editor rico.

    A barra do editor (TinyMCE) é *sticky*: com a página rolada até o último campo
    preenchido, a captura de página inteira a mostra flutuando sobre outro campo.
    """
    tela.pagina.evaluate('window.scrollTo(0, 0)')
    tela.esperar()


def _tarefa(projeto, titulo: str, **filtros):
    from gerenciador_projetos.models import Tarefa

    return Tarefa.objects.filter(projeto=projeto, titulo=titulo, **filtros).order_by('-pk').first()


def _listas(projeto) -> dict[str, int]:
    from gerenciador_projetos.models import ListaProjeto

    return {lp.lista.nome: lp.lista_id for lp in ListaProjeto.objects.filter(projeto=projeto)}


# -- tarefa 1: criar o projeto -------------------------------------------------------------


def test_criar_projeto(logado_doc, capturar):
    """Tarefa 1, etapa 1 — o gerente cadastra o projeto e monta a equipe pelo admin.

    Também executa a afirmação da doc de que entrar na equipe concede o grupo do módulo:
    membro e interessado nascem sem ele no seed.
    """
    from django.contrib.auth.models import Group

    from gerenciador_projetos.enums import SituacaoProjeto
    from gerenciador_projetos.models import Projeto

    hoje = date.today()

    tela = Tela(logado_doc('gerente')).ir(LISTAGEM)
    tela.ver_titulo('Projetos')
    tela.ver_item_de_menu('Gerenciador de Projetos::Projetos')
    capturar(tela.pagina, 'projeto-listagem')

    tela.clicar_botao('Adicionar Projeto')
    tela.ver_titulo('Adicionar Projeto')
    _anotar('form-projeto', tela)
    capturar(tela.pagina, 'projeto-formulario')

    tela.preencher_formulario(
        [
            ('Áreas de Atuação', 'checkbox multiplo', AREA_ATUACAO),
            ('Título', 'texto', N_PROJETO),
            ('Descrição', 'texto rico', 'Projeto de demonstração da documentação de usuário.'),
            ('Data Estimada de Conclusão', 'data', (hoje + timedelta(days=60)).strftime('%d/%m/%Y')),
            ('Campus', 'lista', 'CZN'),
            ('Gerentes', 'autocomplete multiplo', 'Gerente Projeto Doc'),
            ('Membros', 'autocomplete multiplo', 'Membro Projeto Doc'),
            ('Interessados', 'autocomplete multiplo', 'Interessado Projeto Doc'),
            ('Visibilidade', 'radio', 'Privado'),
        ]
    )
    tela.clicar_botao('Salvar')

    # `ProjetoAdmin.response_add` redireciona para a página do projeto SEM mensagem — a doc
    # afirma a navegação, não o banner.
    tela.ver_titulo(f'Projeto: {N_PROJETO}')
    _anotar('projeto-criado', tela)
    capturar(tela.pagina, 'projeto-criado')

    projeto = Projeto.objects.filter(titulo=N_PROJETO, gerentes__username=PAPEIS['gerente']).order_by('-pk').first()
    assert projeto is not None, 'a UI disse que salvou, mas não persistiu'
    assert projeto.situacao == SituacaoProjeto.ABERTO, 'o projeto não nasceu Aberto'
    assert projeto.uo.sigla == 'CZN'
    assert projeto.areas.filter(nome=AREA_ATUACAO).exists(), 'área de atuação não foi gravada'
    assert set(projeto.membros.values_list('username', flat=True)) == {PAPEIS['membro']}
    assert set(projeto.interessados.values_list('username', flat=True)) == {PAPEIS['interessado']}
    assert projeto.visibilidade == 'Privado'
    for papel, grupo in (('membro', 'Membro de Projeto'), ('interessado', 'Interessado do Projeto')):
        assert Group.objects.get(name=grupo).user_set.filter(username=PAPEIS[papel]).exists(), f'entrar na equipe não deu ao {papel} o grupo {grupo}'


def test_tabelas_de_apoio(logado_doc):
    """ "Antes de começar" — onde ficam as duas tabelas de apoio e quem as alcança.

    Sem captura: a doc só afirma o caminho e o acesso, e são essas afirmações que este teste
    executa — o gerente abre o cadastro de Tipos de Atividades e leva 403 em Áreas de Atuação.
    """
    tela = Tela(logado_doc('gerente')).ir('/admin/gerenciador_projetos/tipoatividade/')
    tela.ver_item_de_menu('Gerenciador de Projetos::Cadastros::Tipos de Atividades')
    tela.ver_item_de_menu('Gerenciador de Projetos::Cadastros::Listas')
    tela.clicar_botao('Adicionar Tipo de Atividade')
    tela.ver_titulo('Adicionar Tipo de Atividade')

    resposta = tela.buscar('/admin/comum/areaatuacao/')
    assert resposta.status == 403, f'gerente de projeto alcançou Áreas de Atuação (status {resposta.status})'


# -- tarefa 2: listas e tags ---------------------------------------------------------------


def test_organizar_projeto_em_listas_e_tags(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 2 — o gerente organiza o projeto: cria listas e a primeira tag."""
    from gerenciador_projetos.models import ListaProjeto, Tag

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'

    tela = Tela(logado_doc('gerente')).ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    tela.ver_titulo(f'Projeto: {N_PROJETO}')
    tela.clicar_aba('Listas')
    capturar(tela.pagina, 'projeto-listas')

    for posicao, nome_lista in enumerate((N_LISTA_1, N_LISTA_2, N_LISTA_3), start=1):
        tela.clicar_botao('Adicionar Lista')
        popup = tela.popup()
        popup.ver_botao('Enviar')
        if posicao == 1:
            _anotar('popup-lista', popup)
            capturar(tela.pagina, 'lista-popup')
        popup.preencher_formulario(
            [
                ('Ação', 'radio', 'Adicionar'),
                ('Nome', 'texto', nome_lista),
                ('Posição', 'número', str(posicao)),
            ]
        )
        popup.salvar_no_popup('Enviar')
        tela.sucesso('Operação realizada com sucesso.')
        _limpar_banners(tela)
        tela.clicar_aba('Listas')
        assert ListaProjeto.objects.filter(projeto=projeto, lista__nome=nome_lista, posicao=posicao).exists()

    tela.clicar_aba('Tags')
    tela.clicar_botao('Adicionar Tag')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    _anotar('popup-tag', popup)
    capturar(tela.pagina, 'tag-popup')
    popup.preencher_formulario([('Nome', 'texto', N_TAG), ('Cor', 'lista', 'Vermelho')])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Tag adicionada com sucesso.')
    assert Tag.objects.filter(projeto=projeto, nome=N_TAG).exists()


# -- tarefa 3: tarefas e subtarefas --------------------------------------------------------


def test_criar_tarefas(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 3, etapa 1 — o membro cria tarefas: pelo ``+`` do Dashboard e pela página do projeto.

    O ``+`` de cada quadro abre o formulário já vinculado à lista (``?lista=<id>``); o botão
    *Adicionar Tarefa* da página do projeto abre o mesmo formulário em página inteira, com o
    campo *Lista* para escolher. Com o projeto ainda Aberto, as duas criações trazem o aviso
    que motiva a etapa 2 da tarefa 1 — afirmado aqui.
    """
    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    hoje = date.today()
    listas = _listas(projeto)
    assert {N_LISTA_1, N_LISTA_2, N_LISTA_3} <= set(listas), 'o teste 2 não criou as listas'

    tela = _ir_dashboard(Tela(logado_doc('membro')), projeto)
    tela.ver_titulo(f'Dashboard: {N_PROJETO}')

    _clicar_adicionar_tarefa_da_coluna(tela, listas[N_LISTA_1])
    popup = tela.popup()
    popup.ver_botao('Salvar')
    _anotar('form-tarefa', popup)
    capturar(tela.pagina, 'tarefa-formulario')
    # "Atribuído a" só oferece membros e gerentes do projeto — o interessado não aparece.
    oferecidos = _resultados_do_autocomplete(popup, 'Atribuído a', 'Projeto Doc')
    assert any('Membro' in texto for texto in oferecidos), f'o membro não é oferecido em Atribuído a: {oferecidos}'
    assert not any('Interessado' in texto for texto in oferecidos), f'Atribuído a oferece o interessado: {oferecidos}'
    # Em projeto Privado, "Observadores" só oferece os membros — nem o gerente nem o interessado.
    oferecidos = _resultados_do_autocomplete(popup, 'Observadores', 'Projeto Doc')
    assert any('Membro' in texto for texto in oferecidos), f'o membro não é oferecido em Observadores: {oferecidos}'
    assert not any('Interessado' in texto or 'Gerente' in texto for texto in oferecidos), (
        f'Observadores de projeto privado oferece quem não é membro: {oferecidos}'
    )
    popup.preencher_formulario(
        [
            ('Tipo de Atividade', 'autocomplete', TIPO_ATIVIDADE),
            ('Título', 'texto', N_TAREFA_1),
            ('Descrição', 'texto rico', 'Definir as etapas e os prazos do projeto.'),
            ('Situação', 'radio', 'Aberta'),
            ('Prioridade', 'radio', 'Alta'),
            ('Atribuído a', 'autocomplete multiplo', 'Membro Projeto Doc'),
            ('Data de Início', 'data', hoje.strftime('%d/%m/%Y')),
            ('Data de Conclusão Estimada', 'data', (hoje + timedelta(days=5)).strftime('%d/%m/%Y')),
            ('Tags', 'autocomplete multiplo', N_TAG),
        ]
    )
    popup.clicar_botao('Salvar')
    banners = _esperar_tarefa_salva_no_popup(tela)
    expect(banners.filter(has_text=AVISO_PROJETO_ABERTO)).to_be_visible()

    tarefa1 = _tarefa(projeto, N_TAREFA_1)
    assert tarefa1 is not None, 'a UI disse que salvou, mas não persistiu'
    assert tarefa1.lista_id == listas[N_LISTA_1], 'a tarefa não caiu na lista do quadro'
    assert tarefa1.atribuido_a.filter(username=PAPEIS['membro']).exists()
    assert tarefa1.tags.filter(nome=N_TAG).exists()

    tela.ir(f'/gerenciador_projetos/tarefa/{tarefa1.pk}/')
    tela.ver_titulo(f'Tarefa: {N_TAREFA_1}')
    _anotar('tarefa-criada', tela)
    capturar(tela.pagina, 'tarefa-criada')

    # Segunda porta: o botão da aba Tarefas da página do projeto, em página inteira. Antes,
    # o que o membro NÃO vê ali (a doc reserva listas, tags e edição do projeto ao gerente).
    tela.ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    expect(tela.pagina.locator('a.btn[href^="/admin/gerenciador_projetos/projeto/"]')).to_have_count(0)
    botoes = tela.botoes_na_tela()
    for ausente in ('Clonar projeto', 'Adicionar Lista', 'Adicionar Tag'):
        assert ausente not in botoes, f'o membro vê {ausente!r} na página do projeto'
    # O mesmo seletor que afirma a AUSÊNCIA do `+ Tarefa` para o interessado acha o botão aqui.
    expect(tela.pagina.locator(f'a.btn[href="/gerenciador_projetos/projeto/{projeto.pk}/tarefa/adicionar/"]')).to_have_count(1)
    tela.clicar_botao('Adicionar Tarefa')
    tela.ver_titulo(N_PROJETO)
    _anotar('form-tarefa-pagina', tela)
    tela.preencher_formulario(
        [
            ('Tipo de Atividade', 'autocomplete', TIPO_ATIVIDADE),
            ('Título', 'texto', N_TAREFA_2),
            ('Descrição', 'texto rico', 'Levantar os requisitos com as áreas envolvidas.'),
            ('Lista', 'autocomplete', N_LISTA_2),
            ('Atribuído a', 'autocomplete multiplo', 'Membro Projeto Doc'),
            ('Data de Início', 'data', hoje.strftime('%d/%m/%Y')),
            ('Data de Conclusão Estimada', 'data', (hoje + timedelta(days=15)).strftime('%d/%m/%Y')),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    tela.ver_texto(AVISO_PROJETO_ABERTO)
    tela.ver_titulo(f'Tarefa: {N_TAREFA_2}')
    tarefa2 = _tarefa(projeto, N_TAREFA_2)
    assert tarefa2 is not None, 'a tarefa da página do projeto não foi gravada'
    assert tarefa2.lista_id == listas[N_LISTA_2], 'a tarefa da página do projeto não caiu na lista escolhida'


def test_colocar_projeto_em_andamento(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 1, etapa 2 — o gerente edita o projeto e muda a Situação para *Em andamento*."""
    from gerenciador_projetos.enums import SituacaoProjeto

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'

    tela = Tela(logado_doc('gerente')).ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    tela.clicar_botao('Editar')
    _anotar('form-projeto-edicao', tela)
    tela.preencher('Situação', 'radio', 'Em andamento')
    _topo(tela)
    capturar(tela.pagina, 'projeto-edicao')
    tela.clicar_botao('Salvar')

    tela.ver_titulo(f'Projeto: {N_PROJETO}')
    projeto.refresh_from_db()
    assert projeto.situacao == SituacaoProjeto.EM_ANDAMENTO, 'a situação do projeto não foi gravada'


def test_criar_subtarefa(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 3, etapa 2 — a subtarefa nasce da aba *Subtarefas* da tarefa-pai."""
    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    tarefa2 = _tarefa(projeto, N_TAREFA_2)
    assert tarefa2 is not None, 'o teste de criação de tarefas não criou a tarefa 2'
    hoje = date.today()

    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/tarefa/{tarefa2.pk}/')
    tela.clicar_aba('Subtarefas')
    tela.clicar_botao('Adicionar subtarefa')
    tela.ver_titulo(N_PROJETO)
    # A Tarefa Pai chega preenchida (e travada) pelo link e NÃO é tocada abaixo; a asserção do
    # banco no fim (subtarefa ligada à tarefa 2) prova que o valor mostrado é o que vai gravado.
    # Renderizada como texto somente leitura com o título, mais o id num campo oculto.
    expect(tela.pagina.locator('input[name="tarefa_pai_"][readonly]')).to_have_value(N_TAREFA_2)
    expect(tela.pagina.locator('input#id_tarefa_pai')).to_have_value(str(tarefa2.pk))
    _anotar('form-subtarefa', tela)
    tela.preencher_formulario(
        [
            ('Tipo de Atividade', 'autocomplete', TIPO_ATIVIDADE),
            ('Título', 'texto', N_SUBTAREFA),
            ('Descrição', 'texto rico', 'Ouvir cada coordenação sobre o uso do laboratório.'),
            ('Atribuído a', 'autocomplete multiplo', 'Membro Projeto Doc'),
            ('Data de Início', 'data', hoje.strftime('%d/%m/%Y')),
            ('Data de Conclusão Estimada', 'data', (hoje + timedelta(days=7)).strftime('%d/%m/%Y')),
        ]
    )
    _topo(tela)
    capturar(tela.pagina, 'subtarefa-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    tela.ver_titulo(f'Tarefa: {N_SUBTAREFA}')
    tela.ver_texto(f'Esta tarefa é filha da tarefa #{tarefa2.pk}')

    subtarefa = _tarefa(projeto, N_SUBTAREFA)
    assert subtarefa is not None, 'a subtarefa não foi gravada'
    assert subtarefa.tarefa_pai_id == tarefa2.pk, 'a subtarefa não ficou ligada à tarefa-pai'

    tela.ir(f'/gerenciador_projetos/tarefa/{tarefa2.pk}/')
    tela.clicar_aba('Subtarefas')
    tela.ver_texto(N_SUBTAREFA)
    capturar(tela.pagina, 'tarefa-subtarefas')


# -- tarefa 4: registrar o andamento e concluir -------------------------------------------


def test_registrar_andamento_e_concluir_tarefa(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 4 — checklist, comentário, evolução com percentual e conclusão da tarefa."""
    from gerenciador_projetos.enums import SituacaoTarefa
    from gerenciador_projetos.models import HistoricoEvolucao, ItemChecklist

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    tarefa = _tarefa(projeto, N_TAREFA_1)
    assert tarefa is not None, 'o teste de criação de tarefas não criou a tarefa 1'
    hoje = date.today()

    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/tarefa/{tarefa.pk}/')
    tela.ver_titulo(f'Tarefa: {N_TAREFA_1}')

    # Checklist: o widget é jQuery puro (`tarefa.html`) — a camada `Tela` não porta esse formulário.
    tela.pagina.locator('#novoItemDescricao').fill('Revisar as etapas com a equipe')
    tela.pagina.locator('#novoItemDescricao').press('Enter')
    tela.esperar()
    item = ItemChecklist.objects.filter(tarefa=tarefa, descricao='Revisar as etapas com a equipe').first()
    assert item is not None, 'o item do checklist não foi criado'
    tela.pagina.locator(f'#checklist li[data-id="{item.pk}"] input').check()
    tela.esperar()
    assert ItemChecklist.objects.get(pk=item.pk).concluido, 'marcar o item não persistiu'
    capturar(tela.pagina, 'tarefa-checklist')

    # Comentário rápido: só texto, sem popup.
    tela.preencher('Novo comentário', 'textarea', 'Rascunho do cronograma enviado à equipe.')
    tela.clicar_botao('Comentar')
    tela.sucesso('Comentário adicionado com sucesso.')
    assert HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='Rascunho do cronograma enviado à equipe.').exists()

    # Link: aba Links > Adicionar link.
    tela.clicar_aba('Links')
    tela.clicar_botao('Adicionar link')
    popup = tela.popup()
    _anotar('popup-link', popup)
    popup.preencher_formulario([('Título', 'texto', 'Planilha do cronograma'), ('URL', 'texto', 'https://exemplo.org/cronograma')])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Link salvo com sucesso.')
    assert tarefa.links.filter(titulo='Planilha do cronograma').exists(), 'o link não foi gravado'
    _limpar_banners(tela)
    tela.clicar_aba('Evolução')

    # Evolução 1: comentário + percentual.
    tela.clicar_botao('Registrar evolução')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    _anotar('popup-evolucao', popup)
    capturar(tela.pagina, 'tarefa-evolucao')
    popup.preencher_formulario([('Comentário', 'textarea', 'Cronograma validado com a equipe.')])
    _arrastar_percentual(popup, 50)
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Evolução registrada com sucesso.')
    tarefa.refresh_from_db()
    assert tarefa.percentual_executado == 50, 'o percentual da evolução não foi gravado'
    # O banner da evolução 1 satisfaria o desfecho do popup seguinte antes do POST terminar.
    _limpar_banners(tela)

    # Evolução 2: percentual final + data de conclusão — é assim que a tarefa é encerrada.
    tela.clicar_botao('Registrar evolução')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Comentário', 'textarea', 'Tarefa concluída.'),
            ('Data de Conclusão', 'data', hoje.strftime('%d/%m/%Y')),
        ]
    )
    _arrastar_percentual(popup, 100)
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Evolução registrada com sucesso.')

    tarefa.refresh_from_db()
    assert tarefa.data_conclusao == hoje, 'a data de conclusão não foi gravada'
    assert tarefa.situacao == SituacaoTarefa.CONCLUIDA, 'a tarefa não foi marcada como concluída'
    assert tarefa.percentual_executado == 100
    assert HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='Tarefa concluída.').exists()

    tela.ir(f'/gerenciador_projetos/tarefa/{tarefa.pk}/')
    tela.ver_titulo(f'Tarefa: {N_TAREFA_1}')
    botoes = tela.botoes_na_tela()
    for ausente in ('Registrar evolução', 'Situação', 'Progresso', 'Comentar'):
        assert ausente not in botoes, f'tarefa concluída ainda oferece {ausente!r}'
    capturar(tela.pagina, 'tarefa-concluida')


# -- tarefa 5: situação, progresso e atribuições pelos botões ------------------------------


def test_ajustar_situacao_progresso_e_atribuicoes(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 5 — os botões *Situação*, *Progresso*, *Ações > Alterar atribuições* e *Observar*."""
    from gerenciador_projetos.enums import SituacaoTarefa

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    tarefa = _tarefa(projeto, N_TAREFA_2)
    assert tarefa is not None, 'o teste de criação de tarefas não criou a tarefa 2'

    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/tarefa/{tarefa.pk}/')
    tela.ver_titulo(f'Tarefa: {N_TAREFA_2}')

    _menu(tela, 'Alterar situação').locator('a', has_text='Em andamento').click()
    popup = tela.popup()
    popup.ver_botao('Alterar para Em andamento')
    _anotar('popup-situacao', popup)
    capturar(tela.pagina, 'tarefa-situacao')
    popup.salvar_no_popup('Alterar para Em andamento')
    tela.sucesso('Situação da tarefa alterada com sucesso.')
    tarefa.refresh_from_db()
    assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO, 'a situação da tarefa não foi gravada'

    _menu(tela, 'Alterar progresso').locator('button', has_text='25%').click()
    tela.sucesso('Progresso atualizado com sucesso.')
    tarefa.refresh_from_db()
    assert tarefa.percentual_executado == 25, 'o progresso da tarefa não foi gravado'

    _menu(tela, 'Ações').locator('a', has_text='Alterar atribuições').click()
    popup = tela.popup()
    _anotar('popup-atribuicoes', popup)
    popup.preencher('Atribuído a', 'autocomplete multiplo', 'Gerente Projeto Doc')
    capturar(tela.pagina, 'tarefa-atribuicoes')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atribuições atualizadas com sucesso.')
    assert set(tarefa.atribuido_a.values_list('username', flat=True)) == {PAPEIS['membro'], PAPEIS['gerente']}

    tela.clicar_botao('Observar')
    tela.sucesso('Você foi adicionado como observador desta tarefa.')
    assert tarefa.observadores.filter(username=PAPEIS['membro']).exists()

    tela.ir(f'/gerenciador_projetos/tarefa/{tarefa.pk}/')
    tela.ver_texto('Observadores')
    capturar(tela.pagina, 'tarefa-acoes')


def test_concluir_pela_evolucao_e_reabrir(logado_doc, projeto_da_rodada):
    """Tarefa 4 — *Registrar evolução* com 100% conclui a tarefa, e *Ações > Reabrir tarefa* a devolve.

    Executado na subtarefa para não mexer nas duas tarefas que as visões capturam. Sem
    captura: as telas são as mesmas da tarefa 5.
    """
    from gerenciador_projetos.enums import SituacaoTarefa

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    subtarefa = _tarefa(projeto, N_SUBTAREFA)
    assert subtarefa is not None, 'o teste de subtarefa não criou a subtarefa'

    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/tarefa/{subtarefa.pk}/')
    tela.clicar_aba('Evolução')
    tela.clicar_botao('Registrar evolução')
    popup = tela.popup()
    popup.preencher_formulario([('Comentário', 'textarea', 'Subtarefa entregue.')])
    _arrastar_percentual(popup, 100)
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Evolução registrada com sucesso.')
    _limpar_banners(tela)
    subtarefa.refresh_from_db()
    assert subtarefa.situacao == SituacaoTarefa.CONCLUIDA, 'evolução com 100% não concluiu a tarefa'

    _menu(tela, 'Ações').locator('a', has_text='Reabrir tarefa').click()
    popup = tela.popup()
    popup.ver_texto('A tarefa volta à situação Aberta')
    popup.salvar_no_popup('Reabrir tarefa')
    tela.sucesso('A tarefa foi reaberta.')
    subtarefa.refresh_from_db()
    assert subtarefa.situacao == SituacaoTarefa.ABERTA, 'reabrir não devolveu a tarefa à situação Aberta'
    assert subtarefa.data_conclusao is None, 'reabrir não limpou a data de conclusão'


# -- tarefa 6: Dashboard ---------------------------------------------------------------


def test_usar_dashboard(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 6 — mover cartões entre os quadros, filtrar e usar o menu do cartão.

    Executa os dois desfechos do arrasto, porque a doc afirma os dois: soltar o cartão abaixo
    de outro grava a mudança; soltar num quadro vazio NÃO grava — ``mudarlista`` responde
    ``{'erro': True}`` para a primeira posição de um quadro (``views.py``: ``if posicao < 2``),
    embora a tela mostre o cartão no quadro novo. Se essa asserção passar a falhar, o
    comportamento mudou: atualize o aviso da tarefa 6 na doc. O contorno que a doc ensina
    (campo *Lista* no Editar da tarefa) também é executado.
    """
    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    listas = _listas(projeto)
    tarefa1, tarefa2, subtarefa = _tarefa(projeto, N_TAREFA_1), _tarefa(projeto, N_TAREFA_2), _tarefa(projeto, N_SUBTAREFA)
    assert subtarefa.lista_id is None, 'a subtarefa deveria começar sem lista'
    assert tarefa2.lista_id == listas[N_LISTA_2], f'a tarefa 2 deveria começar em {N_LISTA_2}'

    # Pela porta que a doc descreve: o botão Visualização da página do projeto.
    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    _abrir_visualizacao(tela, 'Dashboard')
    tela.ver_titulo(f'Dashboard: {N_PROJETO}')
    tela.pagina.evaluate("sessionStorage.removeItem('dashboard_gerenciador_projetos')")
    tela.ver_texto('Tarefas sem lista')
    _anotar('dashboard', tela)

    # Abaixo de um cartão existente: grava.
    resposta = _arrastar_cartao(tela, subtarefa.pk, listas[N_LISTA_2])
    subtarefa.refresh_from_db()
    assert resposta == {'ok': True}, f'arrasto abaixo de outro cartão recusado: {resposta}'
    assert subtarefa.lista_id == listas[N_LISTA_2], 'arrasto abaixo de outro cartão não gravou'

    # Num quadro vazio: a tela mostra o cartão lá, mas nada é gravado e ele volta ao recarregar.
    # Com a tarefa 2 (em andamento): a tarefa 1 já está concluída e não se edita mais.
    resposta = _arrastar_cartao(tela, tarefa2.pk, listas[N_LISTA_3])
    tarefa2.refresh_from_db()
    assert resposta == {'erro': True}, f'o arrasto para quadro vazio passou a ser aceito ({resposta}) — atualize o aviso da tarefa 6 na doc'
    assert tarefa2.lista_id == listas[N_LISTA_2], 'o arrasto para quadro vazio passou a ser gravado — atualize o aviso da tarefa 6 na doc'
    tela = _ir_dashboard(tela, projeto)
    expect(_coluna(tela, listas[N_LISTA_2]).locator(f'.beautiful-board-item[data-tarefa-id="{tarefa2.pk}"]')).to_be_visible()

    # O contorno: Editar a tarefa e escolher a lista no campo Lista.
    tela.ir(f'/gerenciador_projetos/tarefa/{tarefa2.pk}/')
    tela.clicar_botao('Editar')
    tela.preencher('Lista', 'autocomplete', N_LISTA_3)
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    tarefa2.refresh_from_db()
    assert tarefa2.lista_id == listas[N_LISTA_3], 'mudar a lista pelo Editar não gravou'

    # Filtro: só as tarefas em andamento.
    tela = _ir_dashboard(tela, projeto)
    tela.preencher('Situação', 'lista', 'Em andamento')
    tela.clicar_botao('Enviar')
    tela.esperar()
    expect(tela.pagina.locator(f'.beautiful-board-item[data-tarefa-id="{tarefa2.pk}"]')).to_be_visible()
    expect(tela.pagina.locator(f'.beautiful-board-item[data-tarefa-id="{tarefa1.pk}"]')).to_have_count(0)

    # Menu do cartão: Alterar > Progresso > 50% leva à página da tarefa.
    tela = _ir_dashboard(tela, projeto)
    cartao = tela.pagina.locator(f'.beautiful-board-item[data-tarefa-id="{tarefa2.pk}"]').first
    cartao.locator('xpath=.//li[contains(@class, "has-child")][a[@title="Alterar"]]/a').click()
    cartao.locator('button', has_text='Progresso > 50%').click()
    tela.sucesso('Progresso atualizado com sucesso.')
    tela.ver_titulo(f'Tarefa: {N_TAREFA_2}')
    tarefa2.refresh_from_db()
    assert tarefa2.percentual_executado == 50, 'o progresso pelo menu do cartão não foi gravado'

    tela = _ir_dashboard(tela, projeto)
    cartao = tela.pagina.locator(f'.beautiful-board-item[data-tarefa-id="{tarefa2.pk}"]').first
    cartao.locator('xpath=.//li[contains(@class, "has-child")][a[@title="Alterar"]]/a').click()
    expect(cartao.locator('a', has_text='Situação > Em análise')).to_be_visible()
    capturar(tela.pagina, 'dashboard-board')


# -- tarefa 7: acompanhar o andamento --------------------------------------------------


def test_acompanhar_projeto_como_interessado(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 7, visão padrão — o interessado acompanha o projeto sem botões de ação."""
    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'

    tela = Tela(logado_doc('interessado')).ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    tela.ver_titulo(f'Projeto: {N_PROJETO}')
    _anotar('projeto-interessado', tela)
    # `+ Tarefa` por endereço: o rótulo vem com quebra de linha ("Adicionar\nTarefa") e uma
    # comparação por texto passaria mesmo com o botão na tela.
    expect(tela.pagina.locator(f'a.btn[href="/gerenciador_projetos/projeto/{projeto.pk}/tarefa/adicionar/"]')).to_have_count(0)
    botoes = tela.botoes_na_tela()
    for ausente in ('Editar', 'Clonar projeto', 'Adicionar Lista', 'Adicionar Tag'):
        assert ausente not in botoes, f'interessado vê o botão {ausente!r}'
    opcoes = _opcoes_de_visualizacao(tela)
    assert opcoes == ['Padrão', 'Gantt', 'Calendário', 'Evolução das tarefas'], f'submenu Visualização do interessado: {opcoes}'
    capturar(tela.pagina, 'projeto-interessado')


def _consultar_visualizacao(tela: Tela, projeto, rotulo: str, titulo: str) -> Tela:
    """Abre uma visão pelo submenu **Visualização** da página do projeto, como o usuário."""
    tela.ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    _abrir_visualizacao(tela, rotulo)
    tela.ver_titulo(titulo)
    _anotar(rotulo, tela)
    return tela


# Quatro testes e não um ``parametrize``: o pytest reordena as instâncias parametrizadas (o
# ``browser_name`` do pytest-playwright é um parâmetro de sessão) e as mandava para depois
# dos testes de campi e de clonagem — medido em 07/10/2026, as capturas das visões saíam com
# as cópias por campus. A cadeia depende da ordem do arquivo.


def test_visao_gantt(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 7 — o gráfico de Gantt, como o interessado o vê."""
    tela = _consultar_visualizacao(Tela(logado_doc('interessado')), projeto_da_rodada, 'Gantt', f'Gantt: {N_PROJETO}')
    expect(tela.pagina.locator('.plotly-graph-div').first).to_be_visible()
    capturar(tela.pagina, 'gantt')


def test_visao_calendario(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 7 — o calendário; submeter o filtro é o passo que a doc descreve, então é executado."""
    tela = _consultar_visualizacao(Tela(logado_doc('interessado')), projeto_da_rodada, 'Calendário', f'Calendário: {N_PROJETO}')
    tela.ver_texto('Apenas tarefas com data de conclusão estimada aparecerão no calendário.')
    # A tarefa 2 vence em hoje + 15 dias, que cai no mês seguinte a partir da metade do mês: o
    # período padrão (mês corrente) não a mostraria.
    tela.preencher('Data de Término', 'data', (date.today() + timedelta(days=30)).strftime('%d/%m/%Y'))
    tela.clicar_botao('Enviar')
    tela.esperar()
    tela.ver_texto(N_TAREFA_2)
    capturar(tela.pagina, 'calendario')


def test_visao_tarefas_por_situacao(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 7 — tarefas por situação. No submenu só para quem edita tarefas, por isso o membro."""
    tela = _consultar_visualizacao(Tela(logado_doc('membro')), projeto_da_rodada, 'Tarefas por situação', f'Tarefas por situação: {N_PROJETO}')
    opcoes = _opcoes_de_visualizacao(tela)
    assert opcoes == ['Padrão', 'Dashboard', 'Tarefas por situação', 'Gantt', 'Calendário', 'Evolução das tarefas'], (
        f'submenu Visualização do membro: {opcoes}'
    )
    colunas = [texto.strip() for texto in tela.pagina.locator('.board-container > h3.title').all_inner_texts()]
    assert colunas == ['Aberta', 'Em andamento', 'Concluída'], f'colunas inesperadas: {colunas}'
    tela.clicar_botao(N_TAG)
    expect(tela.pagina.locator('.board-container:visible')).to_have_count(1)
    tela.clicar_botao('Todas as tags')
    capturar(tela.pagina, 'situacao-tarefas')


def test_visao_evolucao_das_tarefas(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 7 — o histórico de evolução de todas as tarefas do projeto."""
    tela = _consultar_visualizacao(Tela(logado_doc('interessado')), projeto_da_rodada, 'Evolução das tarefas', f'Evolução das tarefas: {N_PROJETO}')
    tela.ver_texto('Cronograma validado com a equipe.')
    capturar(tela.pagina, 'evolucao-tarefas')


# -- tarefa 8: minhas tarefas ------------------------------------------------------------


def test_minhas_tarefas(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 8 — o membro vê as tarefas que lhe foram atribuídas e filtra por projeto."""
    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'

    tela = Tela(logado_doc('membro')).ir(MINHAS_TAREFAS)
    tela.ver_titulo('Minhas tarefas')
    tela.ver_item_de_menu('Gerenciador de Projetos::Minhas tarefas')
    _anotar('minhas-tarefas', tela)

    andamento = tela.pagina.locator(f'.board-container[data-lista-id="{QUADRO_ANDAMENTO}"]')
    concluidas = tela.pagina.locator(f'.board-container[data-lista-id="{QUADRO_CONCLUIDAS}"]')
    for titulo in (N_TAREFA_2, N_SUBTAREFA):
        expect(andamento.get_by_role('link', name=titulo).first).to_be_visible()
    expect(concluidas.get_by_role('link', name=N_TAREFA_1).first).to_be_visible()

    # O filtro. Afirma-se só o que vale para qualquer projeto homônimo: em banco reusado há um
    # "Modernização…" por rodada, e o autocomplete não os distingue (no CI o banco é novo).
    tela.preencher('Projetos', 'autocomplete', N_PROJETO)
    tela.clicar_botao('Enviar')
    tela.esperar()
    # O interessado tem o item no menu (que pede `view_tarefa`), mas a tela pede `change_tarefa`
    # e o recusa. A doc avisa; se isto mudar, atualize o "Quem pode" da tarefa 8.
    interessado = Tela(logado_doc('interessado')).ir('/')
    interessado.ver_item_de_menu('Gerenciador de Projetos::Minhas tarefas')
    status = interessado.buscar(MINHAS_TAREFAS).status
    assert status == 403, f'Minhas tarefas respondeu {status} ao interessado — atualize o "Quem pode" da tarefa 8'
    projetos_nos_cartoes = set(tela.pagina.locator('.board-container .status-info-container').all_inner_texts())
    assert projetos_nos_cartoes == {f'Projeto: {N_PROJETO}'}, f'o filtro deixou cartões de outros projetos: {projetos_nos_cartoes}'
    capturar(tela.pagina, 'minhas-tarefas')


# -- tarefas opcionais: campi e clonagem -----------------------------------------------


def test_distribuir_tarefa_entre_campi(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 9 — *Ações > Atribuir a campus*: a tarefa fica com o 1º campus e ganha cópia para os demais.

    Por último entre os que mexem nas tarefas: a cópia nasce sem lista e mudaria as capturas
    do Dashboard e das visões.
    """
    from gerenciador_projetos.models import Tarefa

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'
    tarefa = _tarefa(projeto, N_TAREFA_2)
    antes = Tarefa.objects.filter(projeto=projeto, titulo=N_TAREFA_2).count()

    tela = Tela(logado_doc('membro')).ir(f'/gerenciador_projetos/tarefa/{tarefa.pk}/')
    _menu(tela, 'Ações').locator('a', has_text='Atribuir a campus').click()
    tela.ver_titulo('Atribuir tarefa a campus')
    _anotar('form-campus', tela)
    tela.preencher('Campi', 'filteredselectmultiple', 'CEN, CZN')
    tela.preencher('Manter atendentes', 'checkbox', 'sim')
    capturar(tela.pagina, 'tarefa-campus')
    tela.clicar_botao('Enviar')
    tela.sucesso('Vínculo realizado com sucesso.')
    tela.ver_titulo(f'Projeto: {N_PROJETO}')

    copias = Tarefa.objects.filter(projeto=projeto, titulo=N_TAREFA_2)
    assert copias.count() == antes + 1, 'a distribuição entre dois campi não criou a cópia'
    assert set(copias.values_list('uo__sigla', flat=True)) == {'CEN', 'CZN'}, 'as duas tarefas não ficaram uma em cada campus'
    copia = copias.exclude(pk=tarefa.pk).get()
    assert copia.atribuido_a.filter(username=PAPEIS['membro']).exists(), '"Manter atendentes" não levou o atribuído para a cópia'
    assert copia.lista_id is None, 'a cópia por campus deveria nascer sem lista'
    assert copia.gerenciador_tarefa_pai_set.filter(titulo=N_SUBTAREFA).exists(), 'a cópia por campus não levou a subtarefa'
    tela.ver_texto(f'{copia.uo.sigla} - {N_TAREFA_2}')
    capturar(tela.pagina, 'tarefa-campus-resultado')


def test_clonar_projeto(logado_doc, projeto_da_rodada, capturar):
    """Tarefa 10 — *Clonar projeto*: confirmado numa página, cria a cópia com só quem clonou na equipe.

    Também afirma o que a cópia NÃO leva (listas, tags, responsáveis das tarefas), porque a doc
    o diz — é o que o usuário precisa refazer.

    Último da cadeia: o clone tem o mesmo gerente, e a âncora ``projeto_da_rodada`` o exclui
    pelo prefixo ``Cópia de`` do título.
    """
    from gerenciador_projetos.enums import SituacaoProjeto
    from gerenciador_projetos.models import Projeto

    projeto = projeto_da_rodada
    assert projeto is not None, 'o teste 1 não criou o projeto'

    tela = Tela(logado_doc('gerente')).ir(f'/gerenciador_projetos/projeto/{projeto.pk}/')
    tela.clicar_botao('Clonar projeto')
    tela.ver_texto('Será criada uma cópia do projeto')
    tela.clicar_botao('Clonar projeto')
    tela.sucesso('Operação realizada com sucesso.')
    tela.ver_titulo(f'Projeto: Cópia de {N_PROJETO}')
    _anotar('projeto-clonado', tela)
    capturar(tela.pagina, 'projeto-clonado')

    clone = Projeto.objects.filter(titulo=f'Cópia de {N_PROJETO}', gerentes__username=PAPEIS['gerente']).order_by('-pk').first()
    assert clone is not None, 'o clone não foi gravado'
    assert clone.pk != projeto.pk, 'a âncora achou o próprio projeto, não o clone'
    assert clone.situacao == SituacaoProjeto.ABERTO, 'o clone não nasceu Aberto'
    assert set(clone.gerentes.values_list('username', flat=True)) == {PAPEIS['gerente']}
    assert not clone.membros.exists(), 'o clone copiou os membros'
    assert not clone.interessados.exists(), 'o clone copiou os interessados'
    assert clone.areas.filter(nome=AREA_ATUACAO).exists(), 'o clone não levou a área de atuação'
    # Listas e tags NÃO vão para a cópia, embora `Projeto.clonar` tente copiá-las: os querysets
    # `listaprojeto_set`/`tag_set` são avaliados depois de o objeto trocar de pk, e voltam vazios.
    # A doc afirma o que a tela entrega; se estas duas passarem a falhar, o clone foi corrigido —
    # atualize a tarefa 10 da doc.
    assert not _listas(clone), 'o clone passou a levar as listas — atualize a tarefa 10 da doc'
    assert not clone.tag_set.exists(), 'o clone passou a levar as tags — atualize a tarefa 10 da doc'
    assert clone.tarefa_set.filter(titulo=N_TAREFA_1).exists(), 'o clone não levou as tarefas'
    assert clone.tarefa_set.filter(titulo=N_SUBTAREFA, tarefa_pai__isnull=False).exists(), 'o clone não levou as subtarefas'
    assert not clone.tarefa_set.filter(atribuido_a__isnull=False).exists(), 'as tarefas do clone vieram com responsáveis'
    assert not clone.tarefa_set.filter(tags__isnull=False).exists(), 'as tarefas do clone vieram com tags — atualize a tarefa 10 da doc'
