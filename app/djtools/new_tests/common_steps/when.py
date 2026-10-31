import datetime
import os
import sys
import tempfile

from behave import when
from django.conf import settings
from freezegun import freeze_time

from djtools.new_tests.utils import (
    abrir_debugger,
    click,
    click_button,
    force_click_checkbox,
    force_fill,
    force_fill_file,
    gerar_highlight_screenshot,
    gerar_screenshot,
    go_url,
    is_anonymous_screen,
    is_menu_visible,
    scroll_to,
    toggle_menu,
    wait_for_ajax,
)

# Funções que mudan o contexto -----------------------------------------------------------------------------------------

ARQUIVOS_TEMPORARIOS = {
    'pdf': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/arquivo.pdf'),
    'xml': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/0176911404054198.xml'),
    'xlsx': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/qualis.xlsx'),
    'xls': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/qualis.xlsx'),
    'png': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/arquivo.png'),
    'docx': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/arquivo.docx'),
    'doc': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/arquivo.docx'),
    'jpg': os.path.join(settings.BASE_DIR, 'djtools/new_tests/files/arquivo.jpg'),
}


@when('olho para a página')
def step_impl(context):
    scroll_to(context, None)
    context.xpath.reset()
    context.xpath.contexto = ''


@when('olho para o quadro "{nome_quadro}"')
def step_olhar_quadro(context, nome_quadro):
    quadro_path = context.xpath.reset()
    quadro_path.find_box(nome_quadro)
    assert quadro_path.get()

    gerar_highlight_screenshot(quadro_path)

    context.xpath.contexto = quadro_path.xpath


@when('olho para os filtros')
def step_olhar_filtros(context):
    quadro_path = context.xpath.reset()
    quadro_path.find_filters()
    assert quadro_path.get()

    gerar_highlight_screenshot(quadro_path)

    context.xpath.contexto = quadro_path.xpath


@when('olho para a listagem')
def step_olhar_listagem(context):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_table(id_name='result_list')
    assert my_xpath.get()

    gerar_highlight_screenshot(my_xpath)

    context.xpath.contexto = my_xpath.xpath


@when('olho para a tabela')
def step_olhar_tabela(context):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_table()
    assert my_xpath.get()

    gerar_highlight_screenshot(my_xpath)

    context.xpath.contexto = my_xpath.xpath


@when('olho para a tabela "{id_tabela}"')
def step_olhar_tabela_id(context, id_tabela):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_table(id_name=id_tabela)
    assert my_xpath.get()

    gerar_highlight_screenshot(my_xpath)

    context.xpath.contexto = my_xpath.xpath


@when('olho a linha "{texto}"')
def step_olhar_linha(context, texto):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_tr(text=texto)
    assert my_xpath.get()

    gerar_highlight_screenshot(my_xpath)

    context.xpath.contexto = my_xpath.xpath


@when('olho para o popup')
def step_olhar_popup(context):
    context.popup.append(context.page)
    context.page = context.page.frame_locator("//iframe[@class='fancybox-iframe']").locator('//body')
    context.page.wait_for()
    context.xpath.page = context.page


@when('olho para a aba "{nome_tab}"')
def step_olhar_aba(context, nome_tab):
    my_xpath = context.xpath
    my_xpath.find_tab_content(name=nome_tab)
    context.main_page.wait_for_selector('ul.nav-tabs', state='visible')
    assert my_xpath.get()

    gerar_highlight_screenshot(my_xpath)

    context.xpath.contexto = my_xpath.xpath


@when('fecho o popup')
def step_fecho_popup(context):
    context.page = context.popup.pop()
    context.xpath.page = context.page
    context.page.evaluate('jQuery.fancybox.close();')
    context.xpath.reset()
    context.xpath.contexto = ''


@when('o popup é fechado')
def step_popup_fechado(context):
    context.page = context.popup.pop()
    context.xpath.page = context.page


# Funções que modificam a lib ------------------------------------------------------------------------------------------


@when('a data do sistema for "{data}"')
def step_data_sistema(context, data):
    try:
        context.browser_context.time_freezer.stop()
    except Exception:
        pass
    dia, mes, ano = data.split('/')
    time_freezer = freeze_time(f'{ano}-{mes}-{dia}', tick=True)
    context.browser_context.time_freezer = time_freezer
    time_freezer.start()


@when('retorna a data do sistema')
def step_retorna_data_sistema(context):
    try:
        context.browser_context.time_freezer.stop()
    except Exception:
        pass


@when('realizo o login com o usuário "{usuario}" e senha "{senha}"')
def step_do_login(context, usuario, senha):
    my_xpath = context.xpath.reset()

    # 1. Verifica se já está logado ou não
    if not is_anonymous_screen(my_xpath):
        if not is_menu_visible(my_xpath):
            toggle_menu(my_xpath)
        my_xpath.find_user()
        user_span = my_xpath.get()
        # O atributo 'title' geralmente tem o vínculo, ex: 'Vínculo: 907008'
        if f'Vínculo: {usuario}' in user_span.get_attribute('title'):
            # Já está logado com o usuário correto
            return
        else:
            # Está logado com outro usuário, faz logout
            go_url(context, '/comum/logout/')
            context.page.reload()

    # 2. Preenche o formulário de login
    inputs = [{'nome': 'Usuário:', 'valor': usuario, 'tipo': 'texto'}, {'nome': 'Senha:', 'valor': senha, 'tipo': 'senha'}]

    for i in inputs:
        my_xpath.reset()
        my_xpath.find_form_input(i['nome'], i['tipo'])
        force_fill(my_xpath, i['valor'])

    my_xpath.reset()
    my_xpath.find_submit_button('Acessar')
    click(my_xpath)

    # 3. Aguarda o login e valida
    if not is_menu_visible(my_xpath):
        toggle_menu(my_xpath)
    my_xpath.find_user()
    user_span = my_xpath.get()
    assert f'Vínculo: {usuario}' in user_span.get_attribute('title')
    if is_menu_visible(my_xpath):
        toggle_menu(my_xpath)

    # 4. Armazena credenciais para reuso (--reuse-successful-scenarios)
    context._last_login = {'usuario': usuario, 'senha': senha}


@when('acesso o menu "{item_menu}"')
def step_acessar_menu(context, item_menu, from_search=False):
    """
    Acessa o menu interno do SUAP ou o menu anônimo.

    Args:
        context: Objeto de contexto do Behave.
        item_menu (str): Caminho do menu a ser acessado.
        from_search (bool): Indica se o menu será acessado via busca.
    """
    if item_menu == 'Sair':
        go_url(context, '/comum/logout/')
        return

    my_xpath = context.xpath.reset()

    if is_menu_visible(my_xpath):
        toggle_menu(my_xpath)

    if settings.BEHAVE_AUTO_DOC:
        if not is_menu_visible(my_xpath):
            toggle_menu(my_xpath)
        my_xpath.reset()
        my_xpath.find_menu_input()
        force_fill(my_xpath, item_menu)
        gerar_highlight_screenshot(my_xpath)
        if is_menu_visible(my_xpath):
            toggle_menu(my_xpath)

    items = item_menu.split('::')
    my_xpath.find_item_menu(items)

    # Timeout maior que o padrão: este `assert` espera presença, e 2s é apertado num runner
    # de CI com três jobs concorrendo — era o segundo fator do flake (o primeiro é o clique
    # que não esperava a navegação, corrigido em `utils.click_button`).
    assert my_xpath.is_in_dom(timeout=15000), f'Item de menu "{item_menu}" não encontrado na página atual.'
    endereco = my_xpath.get_all()[0].get_attribute('href')
    go_url(context, endereco)

    my_xpath.reset()


@when('clico no botão "{nome_botao}"')
def step_clicar_botao(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button(nome_botao)
    click_button(my_xpath)


@when('baixo um arquivo clicando no botão "{nome_botao}"')
def step_baixar_arquivo(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button(nome_botao)
    click_button(my_xpath, download=True)


@when('olho e clico no botão "{nome_botao}"')
def step_mover_e_clicar_botao(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button(nome_botao)
    click_button(my_xpath)


@when('clico no botão de ação "{nome_botao}"')
def step_clicar_botao_acao(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button_action(nome_botao)
    click_button(my_xpath)


@when('clico no botão de submit "{nome_botao}"')
def step_clicar_botao_submit(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_submit_button(nome_botao)
    click_button(my_xpath)


@when('clico no link "{nome_link}"')
def step_clicar_link(context, nome_link):
    my_xpath = context.xpath.reset()
    my_xpath.find_link(nome_link)
    click_button(my_xpath)


@when('clico no link h4 "{nome_link}"')
def step_clicar_h4_link(context, nome_link):
    my_xpath = context.xpath.reset()
    my_xpath.find_link_h4(nome_link)
    click_button(my_xpath)


@when('clico no quadro "{nome_quadro}"')
def step_clicar_box(context, nome_quadro):
    my_xpath = context.xpath.reset()
    my_xpath.find_box(nome_quadro)
    click_button(my_xpath)


@when('clico no indicador "{nome_indicador}"')
def step_clicar_indicador(context, nome_indicador):
    my_xpath = context.xpath.reset()
    my_xpath.find_stat(nome_indicador)
    click_button(my_xpath)


@when('clico no ícone de {nome_link}')
def step_clicar_icone(context, nome_link):
    my_xpath = context.xpath.reset()
    icon = None
    if nome_link == 'edição':
        icon = 'icon-edit'
    elif nome_link == 'exibição':
        icon = 'icon-view'
    elif nome_link == 'remoção':
        icon = 'icon-delete'
    elif nome_link == 'configuração':
        icon = 'icon-cog'
    my_xpath.find_html_element(element='a', class_name=icon)
    click_button(my_xpath)


@when('clico na aba "{nome_tab}"')
def step_clicar_aba(context, nome_tab):
    my_xpath = context.xpath.reset()
    my_xpath.find_tab(name=nome_tab)
    context.main_page.wait_for_selector('ul.nav-tabs', state='visible')
    click_button(my_xpath)


@when('removo o item "{item}" no autocomplete "{autocomplete}"')
def step_clicar_item_autocomplete(context, item, autocomplete):
    my_xpath = context.xpath.reset()
    my_xpath.find_item_autocomplete(autocomplete=autocomplete, item=item)
    click(my_xpath)


@when('preencho as linhas do quadro "{obj}" com os dados')
def step_preencher_linha(context, obj):
    my_xpath = context.xpath.reset()
    my_xpath.find_box(obj)
    context.xpath.contexto = my_xpath.xpath

    for linha in range(len(context.table.rows)):
        row = context.table.rows[linha]
        for i in range(len(row)):
            valor = row[i]
            coluna, tipo = context.table.headings[i].lower().split(':')
            from unicodedata import combining, normalize

            nfkd = normalize('NFKD', coluna)
            coluna = ''.join([c for c in nfkd if not combining(c)])
            row_xpath = context.xpath.reset()
            if tipo == 'lista':
                row_xpath.find_form_inline_select(linha, coluna)
                row_xpath.get().select_option(label=valor)
            elif tipo == 'texto':
                row_xpath.find_form_inline_input(linha, coluna)
                force_fill(row_xpath, valor)
            elif tipo == 'checkbox':
                row_xpath.find_form_inline_checkbox(linha, coluna)
                force_click_checkbox(row_xpath, valor)
            # TODO: se não achar linha clicar no link adicionar outro
    step_impl(context)


@when('preencho o formulário com os dados')
def step_preencher_formulario(context):
    def fill_autocomplete(context, valor, log_data):
        """
        Preenche um campo de autocomplete e seleciona o valor desejado.

        Args:
            context: Objeto de contexto do Behave.
            valor (str): Valor a ser preenchido no campo de autocomplete.
            log_data (str): Dados de log para depuração.
        """
        # Clique no campo de autocomplete para ativá-lo
        click(my_xpath)

        # Localiza o campo de entrada do autocomplete
        xpath_input = context.xpath.reset()
        xpath_input.xpath = '//span[contains(@class, "select2-search--dropdown")]/input'
        force_fill(xpath_input, valor)

        # Aguarda até que os resultados do autocomplete sejam exibidos
        xpath_results = context.xpath.reset()
        xpath_results.xpath = f'//li[contains(@class,"select2-results__option") and (contains(text(), "{row["Valor"]}") or descendant::*[contains(text(), "{row["Valor"]}")])]'

        log_data += f' -> {xpath_results.xpath}'

        click(xpath_results)

    def fill_autocomplete_multiplo(context, valor, log_data):
        click(my_xpath)

        xpath_input = context.xpath
        xpath_input.xpath = f'{my_xpath.xpath}//span//ul//li//input'
        force_fill(xpath_input, valor)

        xpath_local = context.xpath.reset()
        xpath_local.xpath = (
            '//li[contains(@class,"select2-results__option") and (contains(text(), "{0}") or descendant::*[contains(text(), "{0}")])]'.format(
                row['Valor']
            )
        )

        log_data += f' -> {xpath_local.xpath}'

        click(xpath_local)

    my_xpath = context.xpath.reset()
    my_xpath.xpath = '//main//form'
    wait_for_ajax(context, timeout=10)
    gerar_highlight_screenshot(my_xpath)
    my_xpath.reset()
    for row in context.table:
        # Tem que zerar o xpath para garantir que o campo do formulário vai ser encontrado
        my_xpath = context.xpath.reset()
        campo = row['Campo']
        tipo = row['Tipo'].lower()
        valor = row['Valor']
        if tipo not in ('texto rico', 'checkbox multiplo', 'radio', 'checkbox popup'):
            log_data = my_xpath.xpath
            my_xpath.find_form_input(campo, tipo)

        if tipo in ('texto', 'textarea', 'senha', 'número', 'numero', 'number'):
            force_fill(my_xpath, valor)

        elif tipo in ('checkbox multiplo', 'radio'):
            for valor_unico in valor.split(','):
                my_xpath.reset()
                my_xpath.find_form_input(campo, tipo, valor_unico.strip())
                click(my_xpath)

        elif tipo == 'checkbox popup':
            my_xpath.xpath = f'//input[contains(@class, "popup_multiple_choice_field") and ancestor::div[preceding-sibling::label[contains(normalize-space(text()), "{campo}")]]]'
            item = my_xpath.get()
            item.click()
            for valor_unico in valor.split(','):
                my_xpath.reset()
                my_xpath.xpath = f'//input[contains(@title, "{valor_unico}")]'
                click(my_xpath)
            my_xpath.reset()
            my_xpath.xpath = '//button[contains(text(), "Confirmar")]'
            click(my_xpath)

        elif tipo == 'data':
            data_id = my_xpath.get().get_attribute('id')
            data_type = my_xpath.get().get_attribute('type')
            if data_type == 'date':
                valor = datetime.datetime.strptime(valor, '%d/%m/%Y').strftime('%Y-%m-%d')
                context.page.evaluate(f'$("#{data_id}").val("{valor}");')
            elif data_type == 'datetime-local':
                if len(valor) == 10:
                    valor = f'{valor} 00:00:00'
                valor = datetime.datetime.strptime(valor, '%d/%m/%Y %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')
                context.page.evaluate(f'$("#{data_id}").val("{valor}");')

        elif tipo == 'hora':
            data_id = my_xpath.get().get_attribute('id')
            if len(valor) == 5:
                valor = f'{valor}:00'
            context.page.evaluate(f'$("#{data_id}").val("{valor}");')

        elif tipo == 'lista':
            my_xpath.get().select_option(label=valor)
            wait_for_ajax(context, timeout=10)

        elif tipo == 'checkbox':
            force_click_checkbox(my_xpath, valor)

        elif tipo == 'autocomplete':
            fill_autocomplete(context, valor, log_data)

        elif tipo == 'filteredselectmultiple':
            my_xpath.reset()
            valores = [v.strip() for v in valor.split(',')]
            my_xpath.find_form_input(campo, tipo)
            select = my_xpath.get()
            select.select_option(valores)
            my_xpath.reset()
            my_xpath.find_form_filteredselectmultiple_add(campo)
            click(my_xpath, force=True)
            my_xpath.reset()

        elif tipo == 'autocomplete multiplo':
            for valor_unico in valor.split(','):
                my_xpath.reset()
                my_xpath.find_form_input(campo, tipo)
                fill_autocomplete_multiplo(context, valor_unico.strip(), log_data)

        elif tipo == 'arquivo':
            if '.' in valor:
                suffix = valor.split('.')[-1].lower()
            else:
                suffix = 'pdf'
            if suffix in ARQUIVOS_TEMPORARIOS:
                nome_arquivo = ARQUIVOS_TEMPORARIOS[suffix]
            else:
                with tempfile.NamedTemporaryFile(suffix='.' + suffix, dir=context.artifact_path, delete=False) as nome_arquivo:
                    nome_arquivo.write(b'Teste de upload de arquivo.\n')
                    nome_arquivo.write(f'Criado em {datetime.datetime.now()}\n'.encode())
                    nome_arquivo.write(b'Arquivo temporario para testes automatizados.\n')
                    nome_arquivo.flush()
                    ARQUIVOS_TEMPORARIOS[suffix] = nome_arquivo.name
            force_fill_file(my_xpath, campo, nome_arquivo, False)

        elif tipo == 'arquivo real':
            force_fill_file(my_xpath, campo, valor, True)

        elif tipo == 'texto rico':
            frame = f'//label[contains(normalize-space(.),"{campo}")]/following-sibling::div//iframe'
            body = context.page.frame_locator(frame).locator('//body')
            body.fill(valor)
            assert body.all()[0].all_inner_texts()[0].lower() == valor.lower()
        elif tipo == 'busca':
            click(my_xpath)
    context.xpath.reset()


@when('preencho o formulário inline "{nome_formulario}" com os dados')
def step_preencher_formulario_inline(context, nome_formulario):
    """
    Preenche campos de um inline Django Admin, incluindo autocomplete/select2.
    Compatível com TabularInline e StackedInline.
    """
    my_xpath = context.xpath.reset()

    def fill_inline_autocomplete(campo_xpath, valor):
        select2_container_xpath = f"{campo_xpath}//span[contains(@class, 'select2-selection')]"
        my_xpath = context.xpath.reset()
        my_xpath.xpath = select2_container_xpath

        click(my_xpath)

        xpath_input = context.xpath.reset()
        xpath_input.xpath = '//span[contains(@class, "select2-search--dropdown")]/input'
        force_fill(xpath_input, valor)

        xpath_results = context.xpath.reset()
        xpath_results.xpath = (
            f'//li[contains(@class,"select2-results__option") and (contains(text(), "{valor}") or descendant::*[contains(text(), "{valor}")])]'
        )
        click(xpath_results)

    for row in context.table:
        campo = row['Campo']
        tipo = row['Tipo'].lower()
        valor = row['Valor']
        idx_inline = int(row.get('Inline', 1))  # padrão: 1º inline
        # Detecta se é TabularInline (tem <tr class="form-row ...">)
        tabular_tr_xpath = f"(//fieldset[.//h2[contains(normalize-space(), '{nome_formulario}')]]//tr[contains(@class, 'form-row') and not(contains(@class, 'empty-form'))])[{idx_inline}]"
        my_xpath.xpath = tabular_tr_xpath
        is_tabular = my_xpath.is_in_dom()

        if is_tabular:
            # 1. Encontra todos os <th> do cabeçalho
            ths_xpath = f"//fieldset[.//h2[contains(normalize-space(), '{nome_formulario}')]]//th"
            my_xpath.xpath = ths_xpath
            ths = my_xpath.get_all()
            col_index = None
            for idx, th in enumerate(ths, 1):  # 1-based
                if campo.strip() in th.all_inner_texts():
                    col_index = idx
                    break
            assert col_index, f"Não encontrou o cabeçalho '{campo}'"
            td_xpath = f'{tabular_tr_xpath}/td[{col_index}]'
            campo_xpath = td_xpath
        else:
            # StackedInline (com <div class="form-row field-...">)
            inlines_xpath = "//div[contains(@class, 'inline-related') and not(contains(@class, 'empty-form'))]"
            inline_xpath = f'({inlines_xpath})[{idx_inline}]'
            campo_xpath = f"{inline_xpath}//div[contains(@class, 'form-row') and contains(@class, 'field-{campo.lower().replace(' ', '_')}')]"

        # --- Preenchimento dos campos ---
        if tipo == 'autocomplete':
            fill_inline_autocomplete(campo_xpath, valor)
            continue

        if tipo in ('texto', 'senha', 'textarea', 'data', 'hora', 'número', 'numero', 'number'):
            input_xpath = f'{campo_xpath}//input | {campo_xpath}//textarea'
            my_xpath = context.xpath.reset()
            my_xpath.xpath = input_xpath

            force_fill(my_xpath, valor)
            continue

        if tipo == 'lista':
            select_xpath = f'{campo_xpath}//select'
            my_xpath = context.xpath.reset()
            my_xpath.xpath = select_xpath
            my_xpath.get().select_option(valor)
            continue

        if tipo == 'checkbox':
            checkbox_xpath = f"{campo_xpath}//input[@type='checkbox']"
            my_xpath = context.xpath.reset()
            my_xpath.xpath = checkbox_xpath

            force_click_checkbox(my_xpath, valor)
            continue

        # Fallback
        input_xpath = f'{campo_xpath}//input | {campo_xpath}//textarea | {campo_xpath}//select'
        my_xpath = context.xpath.reset()
        my_xpath.xpath = input_xpath

        force_fill(my_xpath, valor)


@when('acesso a página "{url}"')
def step_acessar_pagina(context, url):
    page = context.page
    my_xpath = context.xpath.reset()
    if is_menu_visible(my_xpath):
        toggle_menu(my_xpath)
    current_url = page.url.rstrip('/')
    # Monta a URL absoluta esperada
    base_url = context.config.server_url.rstrip('/')
    if not url.startswith('/'):
        url = '/' + url
    expected_url = base_url + url
    if current_url == expected_url.rstrip('/'):
        return
    go_url(context, url)
    gerar_screenshot(context)


@when('aguardo o conteúdo ajax carregar')
def step_aguardo_conteudo_ajax_carregar(context):
    wait_for_ajax(context, timeout=15)


@when('atualizo a página')
def step_atualizar_pagina(context):
    context.page.reload()


@when('gero um screenshot - "{marcador}"')
def step_gerar_screenshot(context, marcador):
    sys.stdout.write(f'{marcador}: {context.page.screenshot()}')


@when('gero um erro')
def step_gerar_erro(_):
    assert True is False


@when('seleciono o item "{obj}" da lista')
def step_selecionar_checkbox(context, obj):
    my_xpath = context.xpath.reset()
    my_xpath.find_checkbox(obj)
    click(my_xpath)


@when('clico no checkbox')
def step_clico_checkbox(context):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_element(element='input')
    click(my_xpath)


@when('clico no link "{nome_link}" na listagem das áreas')
def step_clicar_link_lista_area_servicos(context, nome_link):
    my_xpath = context.xpath.reset()
    my_xpath.find_link_h4(nome_link)
    assert my_xpath.get()
    gerar_highlight_screenshot(my_xpath)
    click(my_xpath)
    context.xpath.contexto = ''


@when('abro o debugger')
def step_abro_debugger(context):
    abrir_debugger(context)


@when('seleciono o custom checkbox "{nome_do_checkbox}"')
def step_selecionar_custom_checkbox(context, nome_do_checkbox):
    my_xpath = context.xpath.reset()
    my_xpath.find_custom_checkbox(nome_do_checkbox)
    assert my_xpath.get()
    gerar_highlight_screenshot(my_xpath)
    click(my_xpath)
