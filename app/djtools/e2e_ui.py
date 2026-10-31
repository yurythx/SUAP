"""Localizadores da interface do SUAP para os e2e de pytest.

Porta para o pytest os localizadores que o behave já tinha em
``djtools/new_tests/base_test.py`` (``XPathConstructor``) e
``djtools/new_tests/common_steps/when.py``. Os dois mundos exercitam a MESMA
interface com o MESMO Playwright; a única diferença é como o teste é escrito. Sem esta
camada, cada teste e2e voltaria a descobrir na mão seletores que o behave já resolveu —
rótulo → campo, botão por texto, aba, quadro, linha da tabela, popup do fancybox.

O desenho é o do behave, de propósito: um XPath montado por texto visível, com um
**escopo** (o ``contexto`` de lá) que prefixa os XPaths seguintes para limitar a busca a um
quadro, a uma linha ou ao corpo de um popup. Assim um cenário ``.feature`` vira quase uma
transcrição literal::

    Quando acesso o menu "Ensino::Cadastros Gerais::Núcleos"      →  tela.ir('/edu/nucleos/')
    E clico no botão "Adicionar Núcleo"                           →  tela.clicar_botao('Adicionar Núcleo')
    E preencho o formulário com os dados | Descrição | texto | X | →  tela.preencher('Descrição', 'texto', 'X')
    E clico no botão "Salvar"                                     →  tela.clicar_botao('Salvar')
    Então vejo mensagem de sucesso "Cadastro realizado..."        →  tela.sucesso('Cadastro realizado...')

O que NÃO é portado: o menu por título (``acesso o menu``), porque depende de o menu estar
renderizado e os testes de pytest vão direto na URL; e os screenshots de documentação
(``@do_document``), que são a razão de a suíte behave continuar existindo.
"""

from __future__ import annotations

import datetime
import os
from collections.abc import Callable

from django.conf import settings
from playwright.sync_api import APIResponse, Error, Locator, Page, expect

# Arquivos de upload reusados dos testes do behave (mesmos de
# `common_steps/when.py:ARQUIVOS_TEMPORARIOS`).
ARQUIVOS = {
    'pdf': 'djtools/new_tests/files/arquivo.pdf',
    'docx': 'djtools/new_tests/files/arquivo.docx',
    'png': 'djtools/new_tests/files/arquivo.png',
    'jpg': 'djtools/new_tests/files/arquivo.jpg',
}

ICONES = {'exibição': 'icon-view', 'edição': 'icon-edit', 'remoção': 'icon-delete', 'configuração': 'icon-cog'}

# Tetos de espera da camada, ambos acima do default do Playwright (5s no `expect`, 30s na
# navegação). O default não cabe a tela do SUAP quando a run é paralela: MEDIDO em
# 05/08/2026 na rodada de doc, o mesmo teste que leva 6,4s com dois workers leva 13,7s com
# quatro. Os workers disputam CPU com o Chromium, o `live_server` e o Postgres, e com
# `DEBUG=True` cada página busca os estáticos NÃO empacotados um a um (ver
# `suap/settings_test.py`, e o guard de `e2e_fixtures.e2e_seed` que EXIGE o pipeline
# desligado) — o pior caso é o primeiro load de um contexto novo, de cache vazio.
#
# O job `gerar-doc` baixou depois para `pytest -m doc -n 1 --dist loadgroup`, então a rodada
# de doc do CI hoje NÃO é paralela; os tetos ficam porque o `e2e-modulo` continua rodando
# vários jobs na mesma caixa, porque a rodada local usa `-n` à vontade e porque subir o `-n`
# do `gerar-doc` é um caractere. Teto folgado não custa nada quando nada estoura.
#
# Tetos que ESTOURARAM de verdade e motivaram os números: no job `gerar-doc` do CI, dois
# `goto` nos 30s (`eventos::test_inscricao_publica_e_confirmacao` e `erros::test_triar_erros`
# — os dois em contexto recém-criado); na verificação local, o desfecho do popup nos 30s
# (`erros::test_triar_erros`). Daí `TEMPO_NAVEGACAO` valer para TUDO que espera uma tela
# inteira chegar, não só o `goto`: `salvar_no_popup` recarrega a página de trás e custa o
# mesmo.
#
# 15s já era o número de fato da camada (`esperar`, `sucesso`, `erro`); `set_options` só o
# torna o padrão de TODA asserção, inclusive as escritas direto nos testes.
#
# O que estes tetos NÃO resolvem: sob contenção a página continua se mexendo depois de
# pronta, e daí saem falhas que não são de tempo — clique em opção do select2 interceptado
# por outro elemento, `label` de custom-checkbox que fica `hidden` por 15s. São raras e
# somem com o módulo rodando sozinho (`eventos/tests/doc`: 10/10 em 86s).
TEMPO_ESPERA = 15000
TEMPO_NAVEGACAO = 60000

# Teto de uma transição de CSS (o `.fade` do bootstrap é 0,15 s). Curto porque quem espera
# por ela nunca está esperando a rede — ver `Tela._esperar_transicao_da_aba`.
TEMPO_TRANSICAO = 2000

expect.set_options(timeout=TEMPO_ESPERA)

# Alternativas de XPath que valem só para UM dos tipos que compartilham o caminho de `texto`.
#
# `senha`: `PasswordInput` é remapeado GLOBALMENTE para `djtools/templates/widgets/password.html`
# (`djtools/forms/widgets/patch_templates.py`), que embrulha o campo num `div.password-container`
# ao lado do botão "Exibir a senha". O input deixa de ser irmão do rótulo, então o caminho de
# `texto` não o alcança — e isso vale para TODO campo de senha do SUAP, não para uma tela só.
#
# As duas alternativas são ancoradas no rótulo (a primeira pela estrutura, a segunda pelo par
# `for`/`id`), nunca por `ancestor::*`: num formulário com dois campos de senha — o caso normal,
# "Senha" e "Confirmação de senha" — um caminho amplo casaria os dois e o `.first` preencheria o
# mesmo campo duas vezes, deixando a confirmação vazia.
#
# Dicionário, e não um `if` dentro de `_xpath_campo`: a função já está no teto de complexidade
# ciclomática 10 do projeto, e `dict.get` não é ponto de decisão.
_EXTRA_POR_TIPO = {
    'senha': (
        '|//label[normalize-space(text())="{rotulo}"]/following-sibling::div[contains(@class, "password-container")]/input'
        '|//input[@id = //label[normalize-space(text())="{rotulo}"]/@for]'
    )
}

# Grafias que aparecem na coluna `Tipo` das `.feature` e não são chave de `_PREENCHEDORES`.
# A normalização de caixa (`Texto`, `TextArea`) é feita em `Tela.preencher`; aqui ficam só as
# que diferem por acento ou sinônimo, e que `lower()` sozinho não resolve.
_ALIAS_TIPO = {'numero': 'número', 'text area': 'textarea', 'datahora': 'data e hora', 'data/hora': 'data e hora', 'datetime': 'data e hora'}


def arquivo_de_teste(nome: str) -> str:
    """Caminho absoluto de um arquivo de upload por extensão (``'arquivo.pdf'`` → pdf)."""
    extensao = nome.rsplit('.', 1)[-1].lower()
    return os.path.join(settings.BASE_DIR, ARQUIVOS.get(extensao, ARQUIVOS['pdf']))


def _rotulo(campo: str) -> str:
    """Rótulo como o SUAP renderiza: com dois-pontos, salvo quando já tem pontuação."""
    return campo if campo[-1] in ':?.!' else f'{campo}:'


def adicionar_ao_filteredselect(pagina: Page, campo_id: str, *opcoes: str) -> None:
    """Escolhe opções num ``FilteredSelectMultiple`` do admin endereçando pelo ``id``.

    Para os formulários em que o rótulo fica fora do ``div.selector`` e o
    ``_PREENCHEDORES['filteredselectmultiple']`` da ``Tela`` não acha o campo pelo label.
    ``campo_id`` é o da caixa "Disponíveis" (``id_<campo>_from``) e as opções são escolhidas
    pelo texto visível.

    O que o request envia é a caixa "Escolhido(S)" (``_to``): ao montar o quadro, o
    ``SelectFilter2`` renomeia o ``name`` do ``_from`` para ``<campo>_old``, então **selecionar
    à esquerda não basta** — é preciso clicar em "Escolher selecionado(s)" (``_add``), ou o
    formulário grava vazio e o teste falha depois, em "campo obrigatório". Quando o quadro não
    é montado (catálogo ``jsi18n`` ausente em página fora do admin sem ``collectstatic``), o
    ``_from`` fica com o ``name`` cru e a seleção já vale — daí o botão ser opcional.

    O clique é o normal, sem ``force``: o ``_add`` nasce ``disabled`` e só é liberado pelo
    ``change`` que a seleção dispara, e um ``force`` em botão ``disabled`` é um no-op silencioso
    (o ``move_selection`` do Django sai no ``hasAttribute('disabled')``) que só apareceria
    adiante, na asserção da mensagem de sucesso.
    """
    select = pagina.locator(f'//select[@id="{campo_id}"]').first
    expect(select).to_be_visible()
    select.select_option(label=list(opcoes))
    adicionar = pagina.locator(f'//button[@id="{campo_id.removesuffix("_from")}_add"]')
    if adicionar.count():
        adicionar.first.click()


def marcar_documento(pagina: Page) -> None:
    """Carimba o documento e remove feedback antigo antes de uma ação em popup."""
    pagina.evaluate(
        '() => { window.__e2e_documento = true; document.querySelectorAll("p#feedback_message").forEach((elemento) => elemento.remove()) }'
    )


def esperar_desfecho_do_popup(pagina: Page, timeout: int = TEMPO_NAVEGACAO) -> None:
    """Espera o popup terminar: documento substituído **ou** banner de feedback presente.

    ``djtools/static/djtools/fancybox/custom.js:1-9`` define os dois desfechos possíveis —
    ``close_fancybox`` recarrega a página de trás, ``close_fancybox_noreload`` injeta a
    mensagem por JS sem recarregar. Esperar só pelo primeiro penduraria os testes do segundo,
    então a condição aceita qualquer um dos dois, sem ``sleep`` arbitrário.

    Sem esta espera, a asserção seguinte começa a contar o próprio timeout ainda no documento
    ANTIGO — que nunca vai ter o banner. Causa medida da instabilidade de #16990.
    """
    pagina.wait_for_function(
        '() => window.__e2e_documento === undefined || !!document.querySelector("p#feedback_message")',
        timeout=timeout,
    )


def _textos(alvo: Locator) -> list[str]:
    """Lê texto para **diagnóstico**, sem nunca levantar.

    Todo coletor de evidência desta camada roda dentro de um ``except``, ou seja, quando o
    teste já falhou — e a página em navegação é justamente o estado que produz a falha. Uma
    leitura one-shot (``all_inner_texts``) nesse instante levanta
    ``Error: Execution context was destroyed, most likely because of a navigation``, que
    **substitui** a ``AssertionError`` original: o relatório perde a mensagem que dizia o que
    de fato não aconteceu e mostra um erro interno do Playwright no lugar.

    Medido em 31/07/2026 (#16990): as falhas de `edu/tests/e2e/test_01_diretoria.py` chegavam
    ao relatório como esse erro interno, escondendo a asserção real.
    """
    try:
        return [texto.strip() for texto in alvo.all_inner_texts() if texto.strip()]
    except Exception as erro:
        return [f'<indisponível: {type(erro).__name__}>']


def _textos_avaliados(alvo, script: str) -> list[str]:
    """Lê um ``evaluate_all`` para **diagnóstico**, sem nunca levantar.

    Mesmo contrato de ``_textos``: quem chama está dentro de um ``except``, e a página em
    navegação é justamente o estado que produziu a falha. Uma leitura one-shot aí levanta
    ``Execution context was destroyed`` e **substitui** a ``AssertionError`` original (#16990).
    """
    try:
        return alvo.evaluate_all(script)
    except Exception as erro:
        return [f'<indisponível: {type(erro).__name__}>']


class Tela:
    """Uma página (ou um recorte dela) do SUAP, endereçada por texto visível.

    ``escopo`` é um XPath que prefixa todos os outros — é o que permite dizer "dentro do
    quadro X" ou "nesta linha da tabela". ``raiz`` é o que resolve os XPaths: a própria
    ``Page`` ou o ``<body>`` do iframe, quando se está dentro de um popup.
    """

    def __init__(self, pagina: Page, raiz: Page | Locator | None = None, escopo: str = '') -> None:
        self.pagina = pagina
        self.raiz = raiz if raiz is not None else pagina
        self.escopo = escopo

    # -- navegação ----------------------------------------------------------------------

    def ir(self, url: str) -> Tela:
        self.pagina.goto(url, timeout=TEMPO_NAVEGACAO)
        return self.esperar()

    def buscar(self, url: str, timeout: float = TEMPO_NAVEGACAO) -> APIResponse:
        """GET pela sessão do browser, **sem renderizar** — para smoke de rota em lote.

        ``ir`` renderiza (JS, CSS, imagens, jQuery ocioso): um módulo com centenas de rotas
        custaria dezenas de minutos, e o que se afirma num smoke é só "a view respondeu".
        ``pagina.request`` é o ``APIRequestContext`` do **mesmo** ``BrowserContext``, então
        compartilha os cookies: a sessão e as permissões são exatamente as de ``ir``.

        Não segue redirect (``max_redirects=0``) de propósito: sem isso, o 302 que o SUAP dá
        para ``/accounts/login/`` quando a sessão não vale chegaria ao teste como um 200 da
        tela de login, e a rota passaria sem nunca ter sido executada.
        """
        return self.pagina.request.get(url, max_redirects=0, timeout=timeout)

    def postar(self, url: str, dados: dict[str, str] | None = None, timeout: float = TEMPO_NAVEGACAO) -> APIResponse:
        """POST pela sessão do browser, **sem renderizar** — o irmão de ``buscar``.

        Existe para o endpoint que o SUAP só expõe por ``POST`` de AJAX e que nenhum gesto de
        tela alcança sozinho: os três quadros da página inicial (``/comum/index/layout/``,
        ``esconder_quadro`` e ``marcar_quadro_como_lido``) leem ``request.POST['titulo']`` e
        respondem ``PermissionDenied`` a um ``GET`` — um smoke por ``buscar`` afirmaria o 403,
        não a tela.

        **Só serve para view ``@csrf_exempt``**: o ``APIRequestContext`` compartilha os cookies
        do contexto (e portanto a sessão), mas não monta o ``csrfmiddlewaretoken`` que um
        formulário de verdade exige — sem o decorador a resposta volta 403 e o diagnóstico
        aponta para a permissão em vez do token. Para formulário, use a tela.

        ``max_redirects=0`` pelo mesmo motivo de ``buscar``: seguir o redirect faria o 302 para
        ``/accounts/login/`` chegar ao teste como um 200 da tela de login.
        """
        return self.pagina.request.post(url, form=dados or {}, max_redirects=0, timeout=timeout)

    def esperar(self, timeout: int = TEMPO_ESPERA) -> Tela:
        """Espera o jQuery parar — equivalente ao ``wait_for_ajax`` do behave."""
        self.pagina.wait_for_load_state('load', timeout=timeout)
        try:
            self.pagina.wait_for_function('() => !window.jQuery || jQuery.active === 0', timeout=timeout)
        except Exception:
            pass
        return self

    # -- recortes -----------------------------------------------------------------------

    def loc(self, xpath: str) -> Locator:
        return self.raiz.locator(f'{self.escopo}{xpath}')

    def _recorte(self, xpath: str) -> Tela:
        return Tela(self.pagina, self.raiz, xpath)

    def quadro(self, nome: str) -> Tela:
        """O ``olho para o quadro "X"`` do behave: módulo, accordion ou fieldset."""
        modulo = f'//div[contains(@class, "modulo") and div//h3[contains(normalize-space(.), "{nome}")]]'
        accordion = f'//div[contains(@class, "accordion") and h2[contains(normalize-space(.), "{nome}")]]'
        alertas = f'//div[contains(@class, "modulo") and h3[contains(normalize-space(.), "{nome}")]]'
        fieldset = f'//fieldset[contains(@class, "module") and (h2 | legend)[contains(normalize-space(.), "{nome}")]]'
        recorte = self._recorte(f'({modulo}|{accordion}|{alertas}|{fieldset})')
        expect(recorte.loc('').first).to_be_visible()
        return recorte

    def filtros(self) -> Tela:
        return self._recorte(f'{self.escopo}//div[contains(@class, "search-and-filters")]')

    def linha(self, texto: str) -> Tela:
        """A linha da tabela que contém ``texto`` — o ``olho a linha "X"`` do behave."""
        recorte = self._recorte(f'{self.escopo}//tr[descendant-or-self::*[contains(normalize-space(.), "{texto}")]]')
        expect(recorte.loc('').first).to_be_visible()
        return recorte

    def cartao(self, texto: str) -> Tela:
        """O cartão (``div.general-box``) que contém ``texto`` — o ``linha`` das listagens em card.

        O design system trocou tabela por cartão em listagens que os testes já cobriam
        (``selecionar_avaliadores`` de ``projetos`` e de ``pesquisa``, por exemplo): o título
        passou a viver num ``h4`` e as ações numa ``ul.action-bar``, sem nenhum ``tr`` por
        perto — e o cartão AINDA tem tabelas dentro (a lista de avaliadores), então ``linha``
        não só deixa de achar o item como recortaria a tabela errada se achasse.
        """
        recorte = self._recorte(
            f'{self.escopo}//div[(contains(concat(" ", normalize-space(@class), " "), " general-box ") or contains(concat(" ", normalize-space(@class), " "), " card ")) '
            f'and descendant-or-self::*[contains(normalize-space(.), "{texto}")]]'
        )
        expect(recorte.loc('').first).to_be_visible()
        return recorte

    def aba(self, nome: str) -> Tela:
        """O conteúdo da aba visível — usado para asserção, não para clique."""
        return self._recorte(
            f'{self.escopo}//div[contains(@data-title, "{nome}") and contains(@class, "tab-pane") and not(contains(@class, "d-none"))]'
        )

    def popup(self) -> Tela:
        """O popup do SUAP é um iframe do fancybox, não uma janela nova."""
        corpo = self.pagina.frame_locator('iframe.fancybox-iframe').locator('body')
        expect(corpo).to_be_visible()
        return Tela(self.pagina, corpo)

    def popup_ajax(self) -> Tela:
        """O popup de escolha (``popup_choice_field_widget``) é fancybox ``type: 'ajax'``: sem iframe.

        Não dá para decidir entre este e ``popup`` pelo ``count()`` do iframe logo após o
        clique: o iframe ainda não existe, o teste cai no ramo errado e a ``Tela`` fica
        presa à ``div`` que embrulha o iframe — todo popup de iframe passa a ver tela vazia.
        """
        corpo = self.pagina.locator('.fancybox-container .fancybox-slide--current .fancybox-content')
        expect(corpo).to_be_visible()
        return Tela(self.pagina, corpo)

    # -- cliques ------------------------------------------------------------------------

    def _alvos_de_botao(self, nome: str) -> list[str]:
        """Os jeitos de o SUAP renderizar um botão, **em ordem de prioridade**.

        A ordem importa: submit primeiro. Um XPath único com todas as alternativas resolve na
        ordem do DOM, e aí um link cujo texto contém o mesmo nome (num admin, o link do
        ``get_absolute_url`` do objeto) ganha do botão de salvar — o sintoma é o teste sair
        navegando para outra tela em vez de gravar.
        """
        return [
            f'//input[@type="submit" and @value="{nome}"]',
            f'//button[@type="submit" and contains(normalize-space(.), "{nome}")]',
            f'//input[@type="button" and @value="{nome}"]',
            f'//button[contains(normalize-space(.), "{nome}")]',
            # Âncora com o texto EXATO antes da âncora por "contains": numa tela de edição do
            # admin conviveram "Salvar" (submit) e "Salvar em PDF" (link), e o `contains`
            # levava o teste para o PDF em vez de gravar. Fora do menu lateral: com ele aberto,
            # o item "Relatórios::Avaliação de Saúde" do menu do saude ganhava do botão de mesmo nome do
            # prontuário, e o teste ia parar no relatório.
            f'//a[normalize-space(.) = "{nome}" and not(ancestor::nav[@id="mainmenu"])]',
            f'//a[contains(normalize-space(.), "{nome}") and ancestor::ul[contains(@class, "action-bar")]]',
            f'//a[contains(normalize-space(.), "{nome}") and contains(@class, "btn")]',
            f'//a[contains(@title, "{nome}") and contains(@class, "btn")]',
            f'//a[contains(normalize-space(.), "{nome}") and ancestor::ul[contains(@class, "pills")]]',
        ]

    def botao(self, nome: str) -> Locator:
        """O botão visível de maior prioridade; se nenhum for visível, o primeiro candidato."""
        alvos = self._alvos_de_botao(nome)
        for xpath in alvos:
            alvo = self.loc(xpath)
            for indice in range(alvo.count()):
                if alvo.nth(indice).is_visible():
                    return alvo.nth(indice)
        return self.loc('|'.join(alvos)).first

    def clicar_botao(self, nome: str) -> Tela:
        self.esperar()
        alvo = self.botao(nome)
        expect(alvo).to_be_visible()
        alvo.click()
        return self

    def salvar_no_popup(self, nome: str = 'Salvar', timeout: int = TEMPO_NAVEGACAO) -> Tela:
        """Clica no botão que fecha o popup e **espera o desfecho**, devolvendo a página de trás.

        Sem esta espera, o clique retorna com a resposta ainda em voo e a asserção seguinte
        (``sucesso``) começa a contar o próprio timeout ainda no documento ANTIGO — que nunca
        vai ter o banner. Foi a causa medida da instabilidade de #16990: em 3 de 6 falhas o
        banner estava presente, único e visível, só que já **depois** dos 15s do ``expect``.

        Há dois desfechos possíveis, e ``djtools/static/djtools/fancybox/custom.js:1-9`` define
        os dois: ``close_fancybox`` fecha e dá ``window.location.reload()`` na página de trás
        (a mensagem vem do template, com o botão *Fechar*); ``close_fancybox_noreload`` fecha e
        injeta a mensagem por JS, sem recarregar. Esperar só pelo reload penduraria os testes do
        segundo caminho, então a espera aceita **qualquer um dos dois** — documento substituído
        ou banner injetado — numa condição só, sem ``sleep`` arbitrário.
        """
        marcar_documento(self.pagina)
        self.clicar_botao(nome)
        esperar_desfecho_do_popup(self.pagina, timeout)
        return Tela(self.pagina).esperar()

    def clicar_link(self, nome: str) -> Tela:
        alvo = self.loc(f'//a[contains(., "{nome}")]').first
        expect(alvo).to_be_visible()
        alvo.click()
        return self

    def clicar_aba(self, nome: str) -> Tela:
        alvo = self.loc(
            f'//*[contains(@class, "nav-link") and contains(normalize-space(.), "{nome}") and ancestor::*[contains(@class, "nav-tabs")]]'
        ).first
        expect(alvo).to_be_visible()
        alvo.click()
        self._esperar_transicao_da_aba()
        return self

    def _esperar_transicao_da_aba(self, timeout: int = TEMPO_TRANSICAO) -> None:
        """Espera o painel recém-aberto ficar OPACO, não só presente.

        ``djtools/static/djtools/js/tabs.js:244-249`` troca de aba pondo ``active show`` no
        painel, e o ``.fade`` do bootstrap só leva a opacidade a 1 depois da transição. O
        Playwright considera visível um elemento com ``opacity: 0`` — então uma asserção
        passa, mas uma **captura** tirada nesse instante sai transparente: medido na aba CKAN
        de ``dados_abertos`` (``display: block``, altura 674 px, ``opacity: 0``), que virou uma
        tela em branco na doc. Vale para todo módulo que capture aba.

        Falha silenciosa e com teto curto de propósito: painel marcado
        ``data-titled-tab=true`` fica de fora do ``tabs.js`` e pode nunca receber ``show``, e
        esperar por ele não pode custar caro nem derrubar suíte alguma.
        """
        try:
            self.pagina.wait_for_function('() => !document.querySelector(".tab-pane.active:not(.show)")', timeout=timeout)
        except Exception:
            return

    def clicar_icone(self, tipo: str = 'exibição') -> Tela:
        alvo = self.loc(f'//a[contains(@class, "{ICONES[tipo]}")]').first
        expect(alvo).to_be_visible()
        alvo.click()
        return self

    def clicar_acao(self, nome: str) -> Tela:
        """Botão das ações em massa da listagem (``clico no botão de ação``)."""
        submit = f'//button[@type="submit" and @value="{nome}"]'
        acoes = f'//button[contains(normalize-space(.), "{nome}") and ancestor::div[contains(@class, "actions")]]'
        alvo = self.loc(f'{submit}|{acoes}').first
        expect(alvo).to_be_visible()
        alvo.click()
        return self

    def selecionar_item(self, texto: str) -> Tela:
        """Marca o checkbox da linha que contém ``texto`` (``seleciono o item da lista``)."""
        alvo = self.loc(f'//input[ancestor::tr[contains(normalize-space(.), "{texto}")]]').first
        expect(alvo).to_be_visible()
        alvo.check()
        return self

    def selecionar_cartao(self, nome: str) -> Tela:
        """Marca o checkbox de um cartão (``div.general-box``) pelo título em ``h4``.

        É o ``seleciono o custom checkbox "X"`` do behave
        (``djtools/new_tests/base_test.py:398``). Difere de ``selecionar_item`` porque a
        listagem não é uma tabela: o checkbox vive num ``div.custom-checkbox`` irmão
        anterior ao bloco que contém o título. O clique é no ``label`` e não no ``input``,
        como no behave — o input é escondido por CSS e ``check()`` recusaria elemento
        invisível.
        """
        titulo_com_link = f'//h4[descendant::*[normalize-space(text())="{nome}"]]'
        titulo_simples = f'//h4[normalize-space(text())="{nome}"]'
        # O escopo entra em CADA alternativa: num XPath com `|` ele não se distribui, e
        # prefixar só a primeira faria a segunda buscar na página inteira.
        alvos = '|'.join(f'{self.escopo}{titulo}/parent::*/preceding-sibling::*//label' for titulo in (titulo_com_link, titulo_simples))
        alvo = self.raiz.locator(alvos).first
        expect(alvo).to_be_visible()
        alvo.click()
        return self

    # -- formulário ---------------------------------------------------------------------

    def campo(self, nome: str, tipo: str = 'texto', valor: str | None = None) -> Locator:
        """Localiza um campo pelo rótulo.

        ``valor`` só é lido pelos tipos de escolha (``radio`` e ``checkbox multiplo``), em que o
        rótulo sozinho casa o grupo inteiro e é preciso apontar UMA opção — para conferi-la ou
        para desmarcá-la, que é o que ``preencher`` não faz (``_preencher_escolha`` só marca).
        Default ``None`` preserva o comportamento anterior em todos os outros tipos.
        """
        return self.loc(self._xpath_campo(nome, tipo, valor))

    def _xpath_campo(self, nome: str, tipo: str, valor: str | None = None) -> str:
        rotulo = _rotulo(nome)
        if tipo in ('texto', 'senha', 'número'):
            filtro = f'//input[preceding-sibling::label[normalize-space(text())="{rotulo}"]]'
            busca = f'//div[contains(@class, "search-and-filters")]//input[ancestor::div[contains(@class, "filter")]//label[normalize-space(text())="{rotulo}"]]'
            return f'{filtro}|{busca}{_EXTRA_POR_TIPO.get(tipo, "").format(rotulo=rotulo)}'
        if tipo == 'textarea':
            return f'//textarea[ancestor::*/label[normalize-space(text())="{rotulo}"]]'
        if tipo == 'lista':
            return f'//select[ancestor::*/label[normalize-space(text())="{rotulo}"]]'
        if tipo == 'checkbox':
            marca = rotulo[:-1]
            return f'//input[following-sibling::label[contains(normalize-space(.),"{marca}")] or preceding-sibling::label[contains(normalize-space(.), "{marca}")]]'
        if tipo in ('radio', 'checkbox multiplo'):
            escolha = f' and ancestor::*/label[contains(normalize-space(.), "{valor}")]' if valor else ''
            atributo = 'radio' if tipo == 'radio' else 'checkbox'
            return f'//input[ancestor::*/label[contains(normalize-space(.), "{rotulo}")]{escolha} and @type="{atributo}"]'
        if tipo == 'autocomplete':
            return f'//span[ancestor::*/label[normalize-space(text())="{rotulo}"]]'
        if tipo == 'autocomplete multiplo':
            return f'//input[ancestor::*/label[normalize-space(text())="{rotulo}"] and @type="text"]|//span[ancestor::*/label[normalize-space(text())="{rotulo}"]]'
        if tipo in ('arquivo', 'arquivo real'):
            # Três formas de renderizar o mesmo campo, todas observadas no repo: o `div` irmão do
            # rótulo (admin do SUAP), o input como irmão **direto** (o `{% render_form %}` do
            # djtools, `obra.html:542`) e o rótulo apontando para o input pelo `for` (Django
            # padrão). As alternativas anteriores continuam vencendo onde existem — isto só
            # acrescenta.
            return (
                f'//label[contains(normalize-space(.), "{nome}")]/following-sibling::div/input[@type="file"]'
                f'|//label[contains(normalize-space(.), "{nome}")]/following-sibling::input[@type="file"]'
                f'|//input[@type="file"][@id = //label[contains(normalize-space(.), "{nome}")]/@for]'
            )
        if tipo in ('data', 'hora', 'data e hora'):
            return f'//input[preceding-sibling::label[normalize-space(text())="{rotulo}"]]'
        raise AssertionError(f'tipo de campo não suportado: {tipo!r}')

    def preencher(self, nome: str, tipo: str, valor: str, opcao: str | None = None) -> Tela:
        """Preenche um campo pelo rótulo, no dialeto das tabelas do behave.

        O ``tipo`` é normalizado: as ``.feature`` escrevem a coluna capitalizada
        (``Texto`` em 595 lugares, ``TextArea``, ``Autocomplete Multiplo``, ``Numero`` sem
        acento) e as chaves de ``_PREENCHEDORES`` são minúsculas. Sem normalizar, transcrever
        a coluna literalmente — que é exatamente o que um gerador faz — quebra em todas elas.

        ``opcao`` só vale para autocomplete: separa o texto digitado do texto escolhido.

        Quando o campo não é encontrado, a falha lista os rótulos que a tela realmente tem:
        rótulo divergente (acento, maiúscula, dois-pontos) é o erro mais comum ao transcrever
        uma ``.feature``, e descobri-lo de outra forma custa uma execução inteira.
        """
        chave = _ALIAS_TIPO.get(tipo.strip().lower(), tipo.strip().lower())
        preenchedor = self._PREENCHEDORES.get(chave)
        assert preenchedor, f'tipo de campo não suportado: {tipo!r} (conhecidos: {sorted(self._PREENCHEDORES)})'
        try:
            if opcao is not None:
                preenchedor(self, nome, chave, valor, opcao)
            else:
                preenchedor(self, nome, chave, valor)
        except AssertionError as falha:
            raise AssertionError(f'campo {nome!r} ({tipo}) não preenchido. Rótulos na tela: {self.rotulos_na_tela()}') from falha
        return self

    def rotulos_na_tela(self) -> list[str]:
        """Os rótulos do formulário visível — diagnóstico de campo não encontrado."""
        return sorted(set(_textos(self.raiz.locator('//form//label'))))

    def preencher_formulario(self, dados: list[tuple[str, ...]]) -> Tela:
        """A tabela ``preencho o formulário com os dados`` inteira, em ordem.

        Cada linha é ``(nome, tipo, valor)`` ou, para autocomplete cujo texto de busca difere
        do rótulo do resultado, ``(nome, tipo, valor, opcao)``.
        """
        for linha in dados:
            assert len(linha) in (3, 4), f'linha de formulário deve ter 3 ou 4 elementos, veio {linha!r}'
            self.preencher(*linha)
        return self

    def _preencher_texto(self, nome: str, tipo: str, valor: str) -> None:
        alvo = self.campo(nome, tipo).first
        expect(alvo).to_be_visible()
        alvo.fill(valor)

    def _preencher_lista(self, nome: str, tipo: str, valor: str) -> None:
        alvo = self.campo(nome, tipo).first
        try:
            alvo.select_option(label=valor, timeout=TEMPO_ESPERA)
        except Error:
            # Select escondido por layout — campo numa aba recolhida, num fieldset fechado ou
            # atrás de um `d-none`. O behave já resolvia isso com `force_fill`
            # (``common_steps/when.py``), e forçar aqui é o que permite preencher o campo certo
            # em vez de estourar timeout num elemento que existe e é o alvo. Medido no
            # ``AvaliacaoDiagramacaoForm`` da obra do ``pesquisa``.
            alvo.select_option(label=valor, force=True)
        self.esperar()

    def _preencher_checkbox(self, nome: str, tipo: str, valor: str) -> None:
        alvo = self.campo(nome, tipo).first
        alvo.uncheck() if valor.lower() == 'desmarcar' else alvo.check()

    def _preencher_escolha(self, nome: str, tipo: str, valor: str) -> None:
        for item in valor.split(','):
            self.loc(self._xpath_campo(nome, tipo, item.strip())).first.check()

    def _preencher_data(self, nome: str, tipo: str, valor: str) -> None:
        alvo = self.campo(nome, tipo).first
        data = datetime.datetime.strptime(valor, '%d/%m/%Y')
        if alvo.get_attribute('type') == 'datetime-local':
            iso = data.strftime('%Y-%m-%dT%H:%M')
        else:
            iso = data.strftime('%Y-%m-%d')
        alvo.fill(iso)

    def _preencher_data_e_hora(self, nome: str, tipo: str, valor: str) -> None:
        """``input[type=datetime-local]`` — o widget de ``DateTimeFieldPlus``, que ``data`` não preenche.

        ``djtools/forms/fields/datetimeplus.py:180`` casa ``DateTimeFieldPlus`` com
        ``RegionalDateTimeWidget`` (``input[type=datetime-local]``), cujo valor
        aceito é ``aaaa-mm-ddThh:mm[:ss]``. ``_preencher_data`` produz só ``aaaa-mm-dd`` e o
        campo fica vazio — todo formulário de prazo do SUAP (os 12 do edital de Remoção
        Interna, por exemplo) é desta família.

        Aceita ``dd/mm/aaaa`` (hora vira meia-noite), ``dd/mm/aaaa HH:MM`` e
        ``dd/mm/aaaa HH:MM:SS`` — a mesma tolerância que o step do behave já tem
        (``djtools/new_tests/common_steps/when.py:468-472``).

        Os segundos só entram no valor quando são diferentes de zero: o Chromium **normaliza**
        ``...T08:00:00`` para ``...T08:00`` e o ``fill`` do Playwright, que compara o valor
        depois de escrever, rejeita a diferença com ``Error: Malformed value``. Medido ao
        preencher o formulário do edital de Remoção Interna.
        """
        data, _, hora = valor.strip().partition(' ')
        hora = hora or '00:00:00'
        if hora.count(':') == 1:
            hora = f'{hora}:00'
        momento = datetime.datetime.strptime(f'{data} {hora}', '%d/%m/%Y %H:%M:%S')
        iso = momento.strftime('%Y-%m-%dT%H:%M' if momento.second == 0 else '%Y-%m-%dT%H:%M:%S')
        self.campo(nome, tipo).first.fill(iso)

    def _preencher_hora(self, nome: str, tipo: str, valor: str) -> None:
        # Os segundos só entram quando são diferentes de zero, pela mesma normalização do Chromium
        # descrita em `_preencher_data_e_hora`.
        if valor.endswith(':00') and valor.count(':') == 2:
            valor = valor[:-3]
        self.campo(nome, tipo).first.fill(valor)

    def _preencher_arquivo(self, nome: str, tipo: str, valor: str) -> None:
        self.campo(nome, tipo).first.set_input_files(arquivo_de_teste(valor))

    def _preencher_arquivo_real(self, nome: str, tipo: str, valor: str) -> None:
        """Sobe um arquivo ESPECÍFICO, e não o modelo por extensão que ``arquivo`` escolhe.

        ``arquivo`` resolve o valor por extensão em ``ARQUIVOS`` — quatro arquivos genéricos que
        servem para provar que o upload acontece. Não servem quando o **conteúdo** é o que a tela
        processa: a verificação de assinatura digital do ``comum`` precisa de um PDF *assinado*
        (``comum/tests/arquivos/assinatura-digital/arquivo-assinado.pdf``), e com o PDF genérico a
        tela responderia, corretamente, "assinatura não identificada".

        O caminho é relativo ao ``BASE_DIR`` (ou absoluto). A existência é conferida aqui: sem
        isso, o ``set_input_files`` falha com um erro do Playwright sobre o seletor, e o
        diagnóstico manda procurar o campo quando o problema é o caminho.
        """
        caminho = valor if os.path.isabs(valor) else os.path.join(settings.BASE_DIR, valor)
        assert os.path.exists(caminho), f'arquivo de upload inexistente: {caminho}'
        self.campo(nome, tipo).first.set_input_files(caminho)

    def _preencher_autocomplete(self, nome: str, tipo: str, valor: str, opcao: str | None = None) -> None:
        """O select2 do SUAP: abre o widget, digita e clica na opção que casar.

        O dropdown do select2 é anexado ao ``<body>`` do documento em que o widget vive — e
        dentro de um popup esse documento é o do iframe, não o da página. Por isso a busca
        das opções sai de ``raiz`` (sem o escopo, que aponta para o quadro/linha) e não de
        ``pagina``: procurar na página principal não encontra nada e o sintoma é um
        "element(s) not found" na opção, com o widget tendo aberto normalmente.

        ``opcao`` separa **o que se digita** do **que se escolhe**. Sem ele, os dois são o
        mesmo texto — e isso quebra quando o campo é pesquisável por um valor que não aparece
        no rótulo do resultado (o autocomplete de setor exibe o setor superior; o de matriz
        exibe a descrição, não o código). Era essa lacuna que fazia 8 dos 14 arquivos do
        ``edu`` misturarem a ``Tela`` com ``e2e_fixtures.escolher_autocomplete``.
        """
        for item in valor.split(','):
            item = item.strip()
            alvo = item if opcao is None else opcao
            widget = self.loc(self._xpath_campo(nome, tipo)).first
            expect(widget).to_be_visible()
            selecao = widget.locator('.select2-selection').first
            selecao.click() if selecao.count() else widget.click()
            # `count()` logo após o clique é uma corrida: enquanto o select2 não montou a
            # caixa de busca ele dá 0, cai no `keyboard.type`, e as teclas vazam para o campo
            # anterior — que ainda tem o foco. Esperar o dropdown abrir encerra a corrida;
            # mesma causa e mesma correção de `e2e_fixtures.escolher_autocomplete`.
            expect(self.raiz.locator('//span[contains(@class, "select2-container--open")]').first).to_be_visible()
            busca = self.raiz.locator('//span[contains(@class, "select2-search--dropdown")]/input')
            busca.first.fill(item) if busca.count() else self.pagina.keyboard.type(item)
            # Depois de digitar, o select2 mostra "Searching…" (`.loading-results`) enquanto o AJAX
            # corre. Sem esperar, o clique pega a lista de antes da busca: no e2e da comissão da AAI
            # (!19501) a opção "CZN" casou com um setor filho ("CZN → AAI-X"), que foi gravado.
            # Mesma espera de `e2e_fixtures.escolher_autocomplete`.
            expect(self.raiz.locator('.select2-results__option.loading-results')).to_have_count(0)
            seletor = '//li[contains(@class,"select2-results__option")'
            if alvo:
                seletor += f' and (contains(text(), "{alvo}") or descendant::*[contains(text(), "{alvo}")])'
            resultado = self.raiz.locator(f'{seletor}]')
            expect(resultado.first).to_be_visible()
            resultado.first.click()

    def _preencher_filteredselectmultiple(self, nome: str, tipo: str, valor: str) -> None:
        """O select duplo do admin: seleciona à esquerda e clica em "Adicionar".

        Espelha ``djtools/new_tests/common_steps/when.py:490-499``. Selecionar não basta — sem o
        clique no ``selector-add`` o formulário grava vazio, e o teste falha depois, na asserção
        do ORM, longe da causa.

        O caminho comum NÃO usa ``force``. Medido no cadastro de serviços de laboratório do
        PESQUISA: o widget estava inicializado (classes ``filtered`` e caches do ``SelectBox``
        presentes), mas ``click(force=True)`` não disparava o listener nativo criado com
        ``addEventListener``; o clique normal movia a opção como faria o usuário. ``force`` fica
        apenas como fallback para layouts estreitos que encobrem o botão.

        **Não** se verifica aqui que o valor chegou ao ``select`` que o formulário envia. A
        tentativa foi feita e revertida: o ``name`` do ``select`` da esquerda pode ser o mesmo do
        enviado (Django põe o sufixo ``_old`` só num dos lados, e isso varia com o widget), e
        então a "correção" apagava o próprio valor que queria garantir — quebrou o formulário de
        edital do PESQUISA, que estava verde. O que sobra é o gesto do behave, sem inferência
        sobre a estrutura do widget.
        """
        rotulo = _rotulo(nome)
        select = self.loc(f'//select[ancestor::*/label[normalize-space(text())="{rotulo}"]]').first
        expect(select).to_be_visible()
        select.select_option([item.strip() for item in valor.split(',')])
        adicionar = self.loc(f'//button[ancestor::*/label[normalize-space(text())="{rotulo}"] and contains(@class, "selector-add")]').first
        try:
            adicionar.click(timeout=TEMPO_ESPERA)
        except Error:
            # Preserva os formulários em que o layout estreito encobre o botão. O caminho
            # comum continua sendo o clique real, necessário para disparar o listener nativo.
            adicionar.click(force=True)

    def _preencher_texto_rico(self, nome: str, tipo: str, valor: str) -> None:
        """O editor rico vive num ``iframe`` irmão do rótulo; preenche-se o ``body`` de dentro.

        Espelha ``djtools/new_tests/common_steps/when.py:526-530``. O ``frame_locator`` sai de
        ``raiz`` e não de ``pagina`` pelo mesmo motivo do select2: dentro de um popup, o
        documento é o do iframe do popup.

        **A cópia para o ``textarea`` não usa ``window.tinymce``.** A versão anterior escrevia
        ``window.tinymce?.get(textarea.id).getContent()`` e, quando esse ``get`` não resolvia
        (editor ainda não registrado, id divergente), o ``textarea`` ficava vazio **sem falhar**:
        o ``expect`` do ``iframe`` já tinha passado, e o servidor recusava por campo obrigatório
        num campo que o teste havia preenchido. O sintoma era alternância entre execuções com o
        mesmo código — medido na esteira da feature 014 do ``pesquisa``, nos campos
        ``comentario`` e ``obs_conselho_editorial``.

        Agora o HTML vem do **próprio** ``body`` que acabou de ser preenchido (sem intermediário
        que possa estar desligado) e o id do ``textarea`` é derivado do id **deste** ``iframe`` —
        o TinyMCE o monta como ``<id do textarea>_ifr``. O ``expect`` final é o que torna a falha
        alta: campo de texto rico que não sincroniza mais derruba o teste aqui, e não três telas
        depois.
        """
        seletor_iframe = f'//label[contains(normalize-space(.), "{nome}")]/following-sibling::div//iframe'
        quadro = self.raiz.frame_locator(seletor_iframe)
        corpo = quadro.locator('//body')
        expect(corpo).to_be_visible()
        # O TinyMCE inicializa em async e **reescreve** o `body` do iframe quando termina: um
        # `fill` que chega antes disso tem o conteúdo descartado, e o sintoma é o `expect`
        # seguinte falhar com o corpo vazio sem que nada tenha dado errado antes. Por isso o
        # preenchimento é repetido: a primeira tentativa pode cair na janela da inicialização.
        for tentativa in range(3):
            corpo.fill(valor)
            try:
                expect(corpo).to_contain_text(valor, timeout=TEMPO_ESPERA)
                break
            except AssertionError:
                if tentativa == 2:
                    raise

        iframe_id = self.raiz.locator(seletor_iframe).first.get_attribute('id')
        campo_id = iframe_id.removesuffix('_ifr') if iframe_id else None
        if not campo_id:
            rotulo = self.loc(f'//label[contains(normalize-space(.), "{nome}")]').first
            campo_id = rotulo.get_attribute('for')
        assert campo_id, f'campo de texto rico sem id para o rótulo {nome!r}'

        campo = self.loc(f'//textarea[@id="{campo_id}"]').first
        conteudo = corpo.inner_html()
        # A ordem importa e foi medida: o TinyMCE **reescreve o `textarea` a partir do próprio
        # modelo no submit**, então escrever só no `textarea` é descartado e o servidor recusa
        # por campo obrigatório mesmo com o campo preenchido na tela. O que vale é
        # `editor.setContent()`. O `textarea` é escrito também, para o caso de o editor não
        # existir (campo servido sem TinyMCE), e o `get` do editor cobre as três formas de
        # registro — `get(id)` é a canônica, mas o editor pode estar registrado sob outro id ou
        # apenas na lista.
        campo.evaluate(
            """(textarea, html) => {
                const tm = textarea.ownerDocument.defaultView?.tinymce;
                let editor = tm?.get?.(textarea.id);
                if (!editor && tm?.editors?.length) {
                    editor = [...tm.editors].find((e) => e.getElement?.() === textarea) || tm.editors[0];
                }
                if (editor) editor.setContent(html);
                textarea.value = html;
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            conteudo,
        )
        expect(campo).not_to_have_value('')

    def _preencher_checkbox_popup(self, nome: str, tipo: str, valor: str) -> None:
        """O ``popup_multiple_choice_field`` do djtools: campo somente-leitura + fancybox ajax.

        Espelha ``djtools/new_tests/common_steps/when.py:450-460``. Era uma das três lacunas de
        tipo de campo apontadas pelo levantamento (`docs/agents/e2e-vocabulario-tela.md` §3) —
        o behave já a resolvia, e dois módulos a usam.

        O popup é ``type: 'ajax'`` (ver ``djtools/templates/popup_multiple_choice_field_widget.html``),
        ou seja **sem iframe**: as opções e o botão "Confirmar" ficam no MESMO documento do
        campo, dentro de ``#__x__`` (``popup_choice_field.html``).

        Duas armadilhas que este método já paga, as duas medidas com o popup aberto:

        1. **O ``.fancybox-container`` existe ANTES do conteúdo.** Esperar por ele (ou pela
           ``.fancybox-slide--current``) resolve na hora, com a caixa ainda vazia — medido:
           ``container`` visível e ``inputs`` dentro dele contando **zero**. A âncora tem de ser
           o ``.popup-choice-field``, que o próprio template renderiza junto da lista.
        2. **Fechar o popup não é gravar.** O botão "Confirmar" chama ``x()``, que escreve os
           títulos e os pks no input escondido ``#id_<campo>`` (o que o formulário envia) e só
           então remove o ``.fancybox-container``. Sem esperar por esse valor, o teste segue e
           submete o formulário com o campo vazio — com a mensagem de sucesso verde, porque o
           campo é ``required=False``. É a mesma classe de falha da armadilha 15.
        """
        campo = self.loc(
            f'//input[contains(@class, "popup_multiple_choice_field") and ancestor::div[preceding-sibling::label[contains(normalize-space(text()), "{nome}")]]]'
        ).first
        expect(campo).to_be_visible()
        # O id do input escondido é montado do NOME do campo, não do rótulo — e o rótulo é o que
        # o teste conhece. Ler o id do DOM é o que permite esperar pelo valor sem chumbar
        # `id_areas_de_conhecimento` no preenchedor.
        oculto = campo.evaluate('e => e.parentElement.querySelector(\'input[type="hidden"]\')?.id')
        assert oculto, f'campo {nome!r} sem input escondido no container do widget'
        campo.click()

        painel = self.pagina.locator('.fancybox-container .fancybox-slide--current .fancybox-content')
        expect(painel.locator('.popup-choice-field')).to_be_visible()

        for item in valor.split(','):
            # `xpath=.//` e não `.//`: o Playwright decide entre XPath e CSS pelo começo da
            # string — `//` vira XPath, mas `.` é lido como CSS e `.//input[...]` estoura
            # "Unsupported token @title". O `.` sozinho também não basta: um XPath começando em
            # `//` é resolvido na raiz do documento e ignora o pai, o que tornaria o recorte no
            # popup decorativo.
            opcao = painel.locator(f'xpath=.//input[contains(@title, "{item.strip()}")]').first
            expect(opcao).to_be_visible()
            # Idempotente: o widget reabre com o que já estava gravado marcado, e um clique cego
            # **desmarcaria** — o teste passaria a apagar a seleção que queria garantir. Mesmo
            # cuidado do `_preencher_checkbox`, que trata "desmarcar" explicitamente.
            if not opcao.is_checked():
                opcao.click()
            expect(opcao).to_be_checked()

        confirmar = painel.locator('xpath=.//button[contains(text(), "Confirmar")]').first
        expect(confirmar).to_be_visible()
        confirmar.click()

        expect(self.raiz.locator(f'//input[@id="{oculto}"]')).not_to_have_value('')

    def preencher_textarea(self, titulo: str, valor: str) -> Tela:
        """Textarea ancorada por um ``<h4>`` em vez de ``<label>``.

        É o step ``olho para a textarea "X" e preencho com "Y"``
        (``djtools/new_tests/base_test.py:448-449``), que existe porque formulários escritos à
        mão — a linha do tempo do módulo ``erros``, por exemplo — rotulam a caixa de texto com
        um título e não com um ``label``. ``preencher(..., 'textarea')`` exige o ``label`` e
        não acha o campo nesses casos.
        """
        alvo = self.loc(f'//h4[contains(normalize-space(.), "{titulo}")]/parent::*//textarea').first
        expect(alvo).to_be_visible()
        alvo.fill(valor)
        return self

    def preencher_linha(self, indice: int, coluna: str, tipo: str, valor: str) -> Tela:
        """Uma linha de formset inline, endereçada por ``-<indice>-<coluna>`` no ``name``."""
        alvo = self.loc(f'//*[contains(@name, "-{indice}-{coluna}")]').first
        expect(alvo).to_be_visible()
        if tipo == 'lista':
            alvo.select_option(label=valor)
        elif tipo == 'checkbox':
            alvo.check()
        elif tipo == 'data':
            alvo.fill(datetime.datetime.strptime(valor, '%d/%m/%Y').strftime('%Y-%m-%d'))
        else:
            alvo.fill(valor)
        return self

    # -- asserções ----------------------------------------------------------------------

    def sucesso(self, texto: str, timeout: int = TEMPO_ESPERA) -> Tela:
        """A mensagem de feedback do SUAP: ``<p id="feedback_message" class="alert ...">``.

        A tag varia (``success`` no admin, ``info`` no ``httprr`` sem nível), então o que
        identifica sucesso é NÃO ser erro.

        Quando a mensagem não vem, o motivo quase sempre está na tela — validação de campo,
        mensagem de erro do ``httprr``. A falha traz esse texto junto, senão o diagnóstico
        exige rodar o teste de novo com o browser aberto (minutos por tentativa).
        """
        banner = self.pagina.locator('p#feedback_message:not(.alert-error):not(.alert-danger)', has_text=texto)
        try:
            expect(banner.first).to_be_visible(timeout=timeout)
        except AssertionError as falha:
            raise AssertionError(f'mensagem de sucesso "{texto}" não apareceu. {self._estado_dos_banners()} | {self.diagnostico()}') from falha
        return self

    def _estado_dos_banners(self) -> str:
        """Quantos ``#feedback_message`` existem e quais estão visíveis.

        `messages.html` renderiza **um `<p id="feedback_message">` por mensagem** — id duplicado
        quando há mais de uma na fila — e `djtools/static/djtools/fancybox/custom.js:121-131`
        remove e reinjeta outro no ``body`` da página de trás ao fechar o popup. Logo "a
        mensagem não apareceu" pode significar tanto ausência quanto **um banner presente e
        invisível**, ou o `.first` caindo no elemento errado. Sem distinguir os três, a falha
        não diz o que aconteceu (#16990).
        """
        try:
            todos = self.pagina.locator('p#feedback_message')
            estados = [f'{i}:{"visível" if todos.nth(i).is_visible() else "oculto"}' for i in range(todos.count())]
            return f'banners: {len(estados)} [{", ".join(estados)}]'
        except Exception as erro:
            return f'banners: <indisponível: {type(erro).__name__}>'

    def erros_na_tela(self) -> list[str]:
        """Todo texto de erro visível — validação de campo e mensagem do ``httprr``.

        **Instantâneo, sem espera.** Serve para compor mensagem de falha (o ``diagnostico``
        abaixo) ou para afirmar a AUSÊNCIA de erro. Para afirmar que um erro apareceu depois
        de um submit, use ``erro()``: o ``clicar_botao`` devolve com a resposta ainda em voo,
        e esta leitura cai no documento ANTIGO — que não tem erro nenhum e devolve ``[]``.
        Foi a causa medida do flake de ``comum/tests/doc/test_02_autenticacao.py`` no
        ``gerar-doc`` (reproduzido 1 em 23 solto, 100% com 2s de atraso no POST).
        """
        return _textos(self.raiz.locator('p.errornote, ul.errorlist li, p#feedback_message.alert-error'))

    def diagnostico(self) -> str:
        """URL, mensagem de feedback (qualquer que seja) e erros de validação da tela."""
        feedback = _textos(self.pagina.locator('p#feedback_message'))
        return f'URL: {self.pagina.url} | feedback: {feedback} | erros: {self.erros_na_tela()}'

    def erro(self, texto: str, timeout: int = TEMPO_ESPERA) -> Tela:
        alvo = self.pagina.locator('p.errornote, ul.errorlist li, p#feedback_message.alert-error')
        expect(alvo.filter(has_text=texto).first).to_be_visible(timeout=timeout)
        return self

    def ver_texto(self, texto: str) -> Tela:
        alvo = self.loc(f'//*[contains(normalize-space(.), "{texto}")]').first
        try:
            expect(alvo).to_be_visible()
        except AssertionError as falha:
            corpo = ' '.join(_textos(self.raiz.locator('//main')))[:600]
            raise AssertionError(f'texto {texto!r} não visível. URL: {self.pagina.url} | trecho da tela: {corpo!r}') from falha
        return self

    def ver_titulo(self, texto: str) -> Tela:
        """Afirma o ``<h2>`` da tela; na falha, diz o que a página tem no lugar.

        Sem o diagnóstico, "título não visível" é indistinguível de "a view devolveu 500":
        a página de erro do Django não tem heading nenhum, e a mensagem crua manda procurar
        um seletor quebrado quando o problema é a request.
        """
        try:
            expect(self.raiz.get_by_role('heading', name=texto).first).to_be_visible()
        except AssertionError as falha:
            titulos = _textos(self.raiz.get_by_role('heading'))
            raise AssertionError(f'título {texto!r} não visível. Títulos na tela: {titulos} | {self.diagnostico()}') from falha
        return self

    def ver_status(self, status: str) -> Tela:
        """Afirma o passo ATIVO da régua de situação (``ul.steps``) — o ``vejo o status "X"``.

        Espelha ``djtools/new_tests/common_steps/then.py:347-351``. ``ver_texto`` não serve
        aqui: a régua renderiza os quatro rótulos o tempo todo e só a classe ``active``
        distingue o atual, então afirmar o texto passaria com qualquer situação.
        """
        alvo = self.loc(f'//span[contains(@class, "active") and contains(text(), "{status}") and ancestor::*[contains(@class, "steps")]]').first
        try:
            expect(alvo).to_be_visible()
        except AssertionError as falha:
            ativos = _textos(self.raiz.locator('//*[contains(@class, "steps")]//span[contains(@class, "active")]'))
            raise AssertionError(f'status {status!r} não está ativo. Ativos na régua: {ativos} | {self.diagnostico()}') from falha
        return self

    def ver_botao(self, nome: str) -> Tela:
        try:
            expect(self.botao(nome)).to_be_visible()
        except AssertionError as falha:
            raise AssertionError(f'botão {nome!r} não visível. Botões na tela: {self.botoes_na_tela()}') from falha
        return self

    def ver_item_de_menu(self, caminho: str) -> Tela:
        """Afirma que o item de menu existe no **DOM** — o ``vejo o item de menu`` do behave.

        O behave afirma presença (``is_in_dom``, ``base_test.py:217-220``), **não** visibilidade:
        o menu lateral do SUAP é recolhido por padrão, e exigir visível obrigaria a expandi-lo
        a cada asserção — trocando uma asserção de permissão por uma de layout. A força da
        asserção fica a mesma do original.

        Existe porque o levantamento de vocabulário (``docs/agents/e2e-vocabulario-tela.md`` §5)
        é explícito: ``vejo o item de menu`` é o único passo de UI que **não** tem substituto
        por URL — ele afirma o menu em si, então cenários de visibilidade por perfil precisam
        do menu renderizado. Diferente de ``acesso o menu``, que continua fora por decisão do
        porte (o teste vai direto na URL).

        O caminho é o mesmo rótulo do behave, com ``::`` entre os níveis:
        ``'Pesquisa::Editais::Gerenciar Editais'``.
        """
        niveis = caminho.split('::')
        xpath = f'//nav/descendant::a[ancestor::ul[contains(@class, "_main_menu")] and @title="{niveis[0]}"]'
        for nivel in niveis[1:]:
            xpath += f'/following-sibling::ul/child::*/a[@title="{nivel}"]'
        try:
            expect(self.raiz.locator(xpath).first).to_be_attached()
        except AssertionError as falha:
            raise AssertionError(f'item de menu {caminho!r} ausente. Itens no menu: {self.itens_de_menu()}') from falha
        return self

    def itens_de_menu(self) -> list[str]:
        """Todos os ``title`` de item de menu no DOM — diagnóstico de item não encontrado."""
        alvos = self.raiz.locator('//nav//ul[contains(@class, "_main_menu")]//a[@title]')
        return sorted(set(_textos_avaliados(alvos, 'els => els.map(e => e.getAttribute("title")).filter(Boolean)')))

    def botoes_na_tela(self) -> list[str]:
        """Rótulos dos botões e links de ação visíveis — diagnóstico de botão não encontrado."""
        alvos = self.raiz.locator('//input[@type="submit"] | //button | //a[contains(@class, "btn")]')
        rotulos = alvos.evaluate_all('els => els.map(e => (e.value || e.innerText || "").trim()).filter(Boolean)')
        return sorted(set(rotulos))

    _PREENCHEDORES: dict[str, Callable[[Tela, str, str, str], None]] = {
        'texto': _preencher_texto,
        'senha': _preencher_texto,
        'número': _preencher_texto,
        'textarea': _preencher_texto,
        'lista': _preencher_lista,
        'checkbox': _preencher_checkbox,
        'radio': _preencher_escolha,
        'checkbox multiplo': _preencher_escolha,
        'data': _preencher_data,
        'data e hora': _preencher_data_e_hora,
        'hora': _preencher_hora,
        'arquivo': _preencher_arquivo,
        'arquivo real': _preencher_arquivo_real,
        'autocomplete': _preencher_autocomplete,
        'autocomplete multiplo': _preencher_autocomplete,
        'checkbox popup': _preencher_checkbox_popup,
        'filteredselectmultiple': _preencher_filteredselectmultiple,
        'texto rico': _preencher_texto_rico,
    }


def anotar_tela(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela em stderr para a redação da doc de usuário.

    Auxiliar da rodada ``-m doc`` (o ``_anotar`` de cada módulo antes duplicava este bloco
    com variações). Tolerante a navegação em voo (ex.: logo após um clique que redireciona):
    diagnóstico é só leitura, e um ``Execution context was destroyed`` aqui não pode derrubar
    a suíte — os valores ficam como ``<navegação em voo>``.
    """
    import sys

    def _ler(fn):
        try:
            return fn()
        except Exception:
            return ['<navegação em voo>']

    cabecalhos = _ler(lambda: tela.pagina.get_by_role('heading').all_inner_texts())
    botoes = _ler(tela.botoes_na_tela)
    rotulos = _ler(tela.rotulos_na_tela)
    url = _ler(lambda: tela.pagina.url)
    sys.stderr.write(
        f'\n[doc:{titulo}] url={url}'
        f'\n  cabeçalhos: {[str(c).strip() for c in cabecalhos if str(c).strip()]}'
        f'\n  botões: {botoes}'
        f'\n  rótulos: {rotulos}\n'
    )
