# ruff: noqa: T100
import logging
import os
import sys
import time

from django.conf import settings

# Get an instance of a logger
logger = logging.getLogger('behave')


def get_js_scroll_to(element):
    if element:
        result = f'$(document.evaluate(\'{element}\', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.scrollIntoView({{block: "nearest"}}))'
    else:
        result = 'window.scrollTo(0,0);'
    return result


def get_js_snippet_off():
    return '$(".highlight_behave").remove();'


def get_js_snippet_on(element):
    if element:
        return f"highlight_behave($(document.evaluate('{element}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue));"
    return 'console.log("elemento vazio")'


def scroll_to(context, elemento):
    page = context.page
    page.evaluate(get_js_scroll_to(elemento))


def eh_para_documentar(context):
    if settings.BEHAVE_AUTO_DOC:
        for tag in context.tags:
            if 'do_document' in tag:
                return True
    return False


def _console_location_url(msg):
    try:
        location = getattr(msg, 'location', None) or {}
        return (location.get('url') or '').lower()
    except Exception:
        return ''


def _should_ignore_console_error(msg):
    msg_text = msg.text or ''
    msg_text_lower = msg_text.lower()
    _console_location_url(msg)

    # Filtra erros relacionados a recursos que falharam ao carregar, mas ignora erros de outros tipos ou mensagens que não contenham 'failed to load resource'
    if 'failed to load resource' in msg_text_lower:
        if '404' in msg_text_lower or '500' in msg_text_lower:
            return True
    # Violação de Permissions-Policy do navegador (ex.: compute-pressure): ruído do Chrome, sem impacto na aplicação
    if 'permissions policy violation' in msg_text_lower:
        return True
    # Storage Access API negada ao iframe do reCAPTCHA (cookie de terceiro): ruído do Chrome. Derruba
    # qualquer cenário que passe por tela com ReCaptchaField, sempre no step de navegação.
    if 'requeststorageaccess' in msg_text_lower:
        return True
    # Fallback de WebGL/GPU do Chromium headless sem adaptador de vídeo disponível no runner de CI:
    # ruído de ambiente, sem relação com a aplicação.
    return 'no available adapters' in msg_text_lower


def _console_message_type(msg):
    try:
        msg_type = getattr(msg, 'type', '')
        return msg_type() if callable(msg_type) else msg_type
    except Exception:
        return ''


def console_handler(msg):
    msg_type = _console_message_type(msg)
    if msg_type != 'info':
        if _should_ignore_console_error(msg):
            msg_text = msg.text or ''
            logger.warning('Console error ignored: %s, type: %s', msg_text, msg_type)
            return
        raise Exception(f'Console {msg_type}: {msg.text}')
    sys.stdout.write(f'\n\n\nConsole {msg_type}: {msg.text}\n\n\n')
    sys.stdout.flush()


def page_error_handler(exception):
    raise Exception(f'Uncaught exception: {exception}')


def habilitar_inspecao_js(context):
    context.page.on('console', console_handler)
    context.page.on('pageerror', page_error_handler)


def desabilitar_inspecao_js(context):
    context.page.remove_listener('console', console_handler)
    context.page.remove_listener('pageerror', page_error_handler)


def gerar_highlight_screenshot(xpath_constructor):
    from djtools.new_tests.environment_base import add_documentation_step

    if eh_para_documentar(xpath_constructor.behave_context):
        elemento = xpath_constructor.xpath
        context = xpath_constructor.behave_context
        locator = xpath_constructor.get_first_visible()
        locator.evaluate(get_js_snippet_on(elemento))
        screenshot_name = f'{settings.BEHAVE_AUTO_DOC_PATH}/{context.application_text}/screenshot_{time.time()}.png'
        context.main_page.screenshot(path=screenshot_name, full_page=True)
        locator.evaluate(get_js_snippet_off())
        add_documentation_step(context=context, image_name=screenshot_name)


def gerar_screenshot(context):
    from djtools.new_tests.environment_base import add_documentation_step

    if eh_para_documentar(context):
        screenshot_name = f'{settings.BEHAVE_AUTO_DOC_PATH}/{context.application_text}/screenshot_{time.time()}.png'
        context.page.screenshot(path=screenshot_name, full_page=True)
        add_documentation_step(context=context, image_name=screenshot_name)


class LoadJS:
    """An expectation for checking the current url.
    url is the expected url, which must not be an exact match
    returns True if the url is different, false otherwise."""

    def __init__(self, browser):
        self.browser = browser

    def __call__(self, driver):
        return self.browser.evaluate_script('document.readyState') == 'complete' and self.browser.evaluate_script('jQuery.active') == 0


def wait_for_ajax(context, timeout=10):
    try:
        context.main_page.wait_for_load_state('domcontentloaded', timeout=timeout * 1000)
    except Exception:
        sys.stdout.write('Timeout waiting for DOMContentLoaded\n')
    try:
        context.main_page.wait_for_load_state('load', timeout=timeout * 1000)
    except Exception:
        sys.stdout.write('Timeout waiting for load\n')
    try:
        context.main_page.wait_for_function(
            """() => {
                    return window.jQuery && jQuery.active === 0 && jQuery(':animated').length === 0;
                }""",
            timeout=timeout * 1000,
        )
    except Exception:
        sys.stdout.write('Timeout waiting for jQuery active\n')


def wait_for_page(context, timeout=10):
    """Espera a página terminar de carregar (sem esperar jQuery/animação).

    Complemento barato de `wait_for_ajax` para usar logo depois de um clique: cobre a
    navegação que o clique dispara, que é o que fazia o step seguinte correr contra o DOM
    antigo. Tolerante por desenho — se o estado não chegar no prazo, o step seguinte ainda
    tem sua própria espera.
    """
    for estado in ('domcontentloaded', 'load'):
        try:
            context.main_page.wait_for_load_state(estado, timeout=timeout * 1000)
        except Exception:
            sys.stdout.write(f'Timeout waiting for {estado} after click\n')


def _goto_with_retry(page: object, url: str, wait_until: str) -> None:
    try:
        page.goto(url, wait_until=wait_until)
    except Exception as e:
        if 'interrupted by another navigation' not in str(e):
            raise
        page.wait_for_load_state('load')
        page.goto(url, wait_until=wait_until)


def go_url(context: object, url: str, wait_until: str = 'load') -> None:
    page = context.page
    my_url = context.config.server_url
    if url[0] != '/':
        my_url += '/' + url[1:]
    else:
        my_url += url
    if url.endswith('correntes/'):
        request = context.browser_context.request
        response = request.get(my_url, max_redirects=5)
        final_url = response.url
        _goto_with_retry(page, final_url, wait_until)
        # expect(context.page).to_have_url(re.compile(r'.*/correntes/.*'))
    elif url == '/comum/logout/':
        try:
            _goto_with_retry(page, my_url, 'commit')
        except Exception:
            pass
        # expect(context.page).to_have_url(re.compile(r'.*/login/.*'))
    else:
        _goto_with_retry(page, my_url, wait_until)
        wait_for_ajax(context)


def click_button(xpath_constructor, download=False):
    context = xpath_constructor.behave_context
    gerar_highlight_screenshot(xpath_constructor)
    wait_for_ajax(context)
    click(xpath_constructor, download=download)
    # Espera DEPOIS do clique, não só antes: o clique que dispara navegação retorna assim que
    # a ação acontece, e sem isto o step SEGUINTE começa a inspecionar o DOM com a página
    # ainda trocando. É por isso que o flake do behave aparece em cenários diferentes a cada
    # execução — cai onde a corrida foi perdida, não onde está a causa.
    #
    # Só os estados de carga, e não o `wait_for_ajax` completo: o que falta aqui é a
    # navegação assentar. A espera por `jQuery.active`/`:animated` já acontece no início do
    # PRÓXIMO clique, e repeti-la aqui custou ~30% no tempo da suíte do edu sem cobrir nada
    # que este trecho não cubra.
    wait_for_page(context)
    xpath_constructor.reset()
    xpath_constructor.contexto = ''
    if context.popup:
        context.page = context.popup.pop()
        context.xpath.page = context.page


def click(xpath_constructor, force=False, download=False):
    """
    Força o clique em um elemento localizado pelo XPath e retorna a URL de redirecionamento, se disponível.

    Args:
        xpath_constructor: Instância do XPathConstructor para localizar o elemento.

    Returns:
        str: URL de redirecionamento, se o elemento possuir um atributo 'href'. Caso contrário, retorna None.

    Raises:
        Exception: Se o clique falhar ou o elemento não for encontrado.
    """

    element = xpath_constructor.get()
    redirect_url = element.get_attribute('href')
    page = xpath_constructor.behave_context.main_page
    if download:
        page.pause()
        with page.expect_download() as download_info:
            element.click(force=force)
        download = download_info.value
        path = download.path()
        sys.stdout.write(f'Arquivo baixado temporariamente em: {path}\n')
    else:
        element.click(force=force)
    return redirect_url


def force_click_checkbox(xpath_constructor, action):
    element = xpath_constructor.get()
    if action.lower() == 'desmarcar':
        element.uncheck()
    elif action.lower() == 'marcar':
        element.check()


def force_fill(xpath_constructor, valor):
    xpath_constructor.get().fill(valor)


def force_fill_file(xpath_constructor, campo, valor, real):
    xpath_constructor.find_form_input(campo, 'arquivo', valor)
    if real:
        filename = os.path.join(os.getcwd(), f'djtools/new_tests/files/{valor.lower()}')
    else:
        filename = valor
    xpath_constructor.get().set_input_files(filename)


def force_view_msg(xpath_constructor, type_msg, msg):
    xpath_constructor.find_message(type_msg, msg)
    assert xpath_constructor.get()


def click_until_render(elemento, tentativa=0, maximo_tentativas=10):
    try:
        if tentativa < maximo_tentativas:
            elemento.click()
            return
    except Exception:
        tentativa += 1
        click_until_render(elemento, tentativa)

    elemento.click()


def is_anonymous_screen(xpath_constructor):
    """
    Verifica se a tela atual é uma tela anônima (sem menu lateral).

    Args:
        browser: Instância do navegador.

    Returns:
        bool: True se a tela for anônima, False caso contrário.
    """
    xpath_constructor.xpath = '//body'
    return 'anonima' in xpath_constructor.get().get_attribute('class')


def is_menu_visible(xpath_constructor):
    """
    Verifica se o menu lateral está visível.

    Args:
        browser: Instância do navegador.

    Returns:
        bool: True se o menu estiver visível, False caso contrário.
    """
    xpath_constructor.xpath = '//body'
    classes = xpath_constructor.get().get_attribute('class') or ['anonima']
    return 'hideSidebar' not in classes and 'anonima' not in classes


def toggle_menu(xpath_constructor):
    """
    Alterna a visibilidade do menu lateral clicando no botão de toggle.

    Args:
        browser: Instância do navegador.
    """
    xpath_constructor.xpath = '//button[@id="toggleSidebar"]'
    click(xpath_constructor)
    wait_for_ajax(xpath_constructor.behave_context)
    xpath_constructor.reset()


def log(xpath_constructor):
    logger.debug('\n' + xpath_constructor.xpath)


def log_text(text):
    logger.debug('\n' + text)


def abrir_debugger(context):
    if context.debug:
        browser = context.page
        contexto = context.xpath.contexto
        import ipdb

        ipdb.set_trace()
        sys.stdout.write(f'{browser}, {contexto}\n')
    else:
        sys.stdout.write('Debug desativado. Remova o parâmetro --noinput para reativá-lo\n')
