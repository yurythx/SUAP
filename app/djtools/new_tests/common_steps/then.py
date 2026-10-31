import datetime
import tempfile

from behave import then

from djtools.new_tests.base_test import XPathConstructor
from djtools.new_tests.common_steps.when import ARQUIVOS_TEMPORARIOS
from djtools.new_tests.utils import abrir_debugger, click, force_fill, force_fill_file, force_view_msg, gerar_highlight_screenshot, scroll_to


@then('vejo o indicador "{nome_indicador}" com o valor "{valor_indicador}"')
def step_ver_indicador_com_valor(context, nome_indicador, valor_indicador):
    step_ver_indicador(context, nome_indicador)

    my_xpath = context.xpath.reset()
    my_xpath.find_stat_value(name=nome_indicador, value=valor_indicador)
    assert my_xpath.get()

    scroll_to(context, my_xpath.xpath)
    gerar_highlight_screenshot(my_xpath)


@then('vejo o indicador "{nome_indicador}"')
def step_ver_indicador(context, nome_indicador):
    my_xpath = context.xpath.reset()
    my_xpath.find_stat(name=nome_indicador)
    assert my_xpath.get()

    scroll_to(context, my_xpath.xpath)
    gerar_highlight_screenshot(my_xpath)


@then('vejo a página "{nome_pagina}"')
def step_ver_pagina(context, nome_pagina):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_element(element='h2', text=nome_pagina)
    assert my_xpath.get()
    gerar_highlight_screenshot(my_xpath)
    context.xpath.reset()


@then('vejo o botão "{nome_botao}"')
def step_ver_botao(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button(nome_botao)
    assert my_xpath.get()


@then('vejo o botão de ação "{nome_botao}"')
def step_ver_botao_acao(context, nome_botao):
    my_xpath = context.xpath.reset()
    my_xpath.find_button_action(nome_botao)
    assert my_xpath.get()


@then('vejo mensagem de {tipo} "{mensagem}"')
def step_ver_mensagem(context, tipo, mensagem):
    my_xpath = context.xpath.reset()
    if tipo.lower() == 'erro':
        tipo_msg = XPathConstructor.MSG_ERROR
    elif tipo.lower() == 'sucesso':
        tipo_msg = XPathConstructor.MSG_SUCESS
    elif tipo.lower() == 'alerta':
        tipo_msg = XPathConstructor.MSG_ALERT

    force_view_msg(my_xpath, tipo_msg, mensagem)
    scroll_to(context, my_xpath.xpath)
    assert my_xpath.get()
    gerar_highlight_screenshot(my_xpath)
    my_xpath.reset()


@then('nao vejo mensagem de {tipo} "{mensagem}"')
def step_nao_ver_mensagem(context, tipo, mensagem):
    my_xpath = context.xpath.reset()
    if tipo.lower() == 'erro':
        type = XPathConstructor.MSG_ERROR
    elif tipo.lower() == 'sucesso':
        type = XPathConstructor.MSG_SUCESS
    elif tipo.lower() == 'alerta':
        type = XPathConstructor.MSG_ALERT

    my_xpath.find_message(type, mensagem)
    # scroll_to(context, my_xpath.xpath)
    msg = my_xpath.is_in_dom()
    assert not msg
    gerar_highlight_screenshot(my_xpath)


@then('vejo os seguintes campos no formulário')
def step_ver_campos_formularios(context):
    for row in context.table:
        campo = row['Campo']
        tipo = row['Tipo'].lower()

        my_xpath = context.xpath.reset()
        my_xpath.find_form_input(campo, tipo)
        assert my_xpath.is_in_dom(), f'Campo "{campo}" do tipo "{tipo}" não encontrado no formulário. XPath: {my_xpath.xpath}'


@then('vejo os seguintes erros no formulário')
def step_ver_erros_formulario(context):
    for row in context.table:
        my_xpath = context.xpath.reset()
        my_xpath.find_input_error(label_name=row['Campo'], error_text=row['Mensagem'])

        assert my_xpath.get(), f'Erro "{row["Mensagem"]}" para o campo "{row["Campo"]}" não encontrado no formulário. XPath: {my_xpath.xpath}'


@then('vejo o texto "{texto}"')
def step_ver_texto(context, texto):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_element(element='*', text=texto)

    assert my_xpath.get()
    gerar_highlight_screenshot(my_xpath)


@then('vejo a aba "{nome_tab}"')
def step_ver_aba(context, nome_tab):
    my_xpath = context.xpath.reset()
    my_xpath.find_tab(name=nome_tab)

    assert my_xpath.get()


@then('vejo o quadro "{nome_box}"')
def step_ver_quadro(context, nome_box):
    my_xpath = context.xpath.reset()
    my_xpath.find_box(box_name=nome_box)
    assert my_xpath.get()


@then('vejo a caixa de informações "{nome_box}" com "{informacao}"')
def step_ver_caixa_informacoes(context, nome_box, informacao):
    my_xpath = context.xpath.reset()
    my_xpath.find_box_info(box_name=nome_box, informacao=informacao)

    assert my_xpath.get()


@then('vejo o item "{item}" no autocomplete "{autocomplete}"')
def step_ver_item_autocomplete(context, item, autocomplete):
    my_xpath = context.xpath.reset()
    my_xpath.find_item_autocomplete(autocomplete=autocomplete, item=item)
    assert my_xpath.get()


@then('vejo o item de menu "{item_menu}"')
def step_ver_item_menu(context, item_menu):
    my_xpath = context.xpath.reset()
    items = item_menu.split('::')
    my_xpath.find_item_menu(items)
    assert my_xpath.is_in_dom()


@then('vejo a linha "{texto}"')
def step_ver_linha(context, texto):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_tr(text=texto)
    assert my_xpath.get()


@then('vejo os seguintes campos no formulário com as obrigatoriedades atendidas')
def step_ver_campos_formularios_obrigatoriedades(context):
    def step_clicar_botao(context, nome_botao):
        my_xpath = context.xpath.reset()
        my_xpath.find_button(nome_botao)

        assert my_xpath.get()

        gerar_highlight_screenshot(my_xpath)
        click(my_xpath)

        context.xpath.contexto = ''

    def step_ver_erros_formulario(context):
        for row in context.table:
            if row['Obrigatório'] == 'Sim':
                my_xpath = context.xpath.reset()
                my_xpath.find_input_error(label_name=row['Campo'], error_text='Este campo é obrigatório')

                assert my_xpath.get()

    step_ver_campos_formularios(context)
    step_ver_botao(context, 'Salvar', '')
    step_clicar_botao(context, 'Salvar')
    step_ver_mensagem(context, 'erro', 'Por favor, corrija os erros abaixo.', '')
    step_ver_erros_formulario(context)


@then('vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com')
def step_ver_campos_formularios_obrigatoriedades_preenchidos(context):
    def step_clicar_botao(context, nome_botao):
        my_xpath = context.xpath.reset()
        my_xpath.find_button(nome_botao)

        assert my_xpath.get()

        gerar_highlight_screenshot(my_xpath)
        click(my_xpath)

        context.xpath.contexto = ''

    def step_ver_erros_formulario(context):
        for row in context.table:
            if row['Obrigatório'] == 'Sim':
                my_xpath = context.xpath.reset()
                my_xpath.find_input_error(label_name=row['Campo'], error_text='Este campo é obrigatório')
                assert my_xpath.get()

    def step_preencher_formulario(context):
        def fill_autocomplete(context, valor, log_data):
            force_fill(my_xpath, valor)

            item_xpath = context.xpath.reset()
            item_xpath.xpath = '//li[ancestor::div[@class="ac_results" and descendant::*[contains(text(), "{}")]]]'.format(row['Valor'])
            log_data += f' -> {item_xpath.xpath}'

            click(item_xpath)

        def fill_autocomplete_multiplo(context, valor, log_data):
            click(my_xpath)

            xpath_input = context.xpath.reset()
            xpath_input.xpath = f'{my_xpath.xpath}//span//ul//li//input'
            force_fill(xpath_input, valor)

            xpath_local = context.xpath.reset()
            xpath_local.xpath = (
                '//li[contains(@class,"select2-results__option") and (contains(text(), "{0}") or descendant::*[contains(text(), "{0}")])]'.format(
                    row['Valor']
                )
            )
            log_data += f' -> {xpath_local}'

            click(xpath_local)

        for row in context.table:
            campo = row['Campo']
            tipo = row['Tipo'].lower()
            valor = row['Valor']
            if not valor:
                continue

            my_xpath = context.xpath.reset()
            if tipo != 'texto rico':
                my_xpath.find_form_input(campo, tipo)
                log_data = my_xpath.xpath

            if tipo == 'texto':
                input_text = my_xpath.get()
                input_text.first.fill(valor)
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
            elif tipo == 'textarea':
                text_area = my_xpath.get()
                text_area.first.fill(valor)
            elif tipo == 'lista':
                my_xpath.get().select_option(label=valor)
            elif tipo == 'arvore':
                my_xpath.find_form_arvore(valor)
                click(my_xpath)
            elif tipo == 'checkbox':
                input_text = my_xpath.get()
                if input_text.first.selected and valor.lower() == 'desmarcar' or not input_text.first.selected and valor.lower() == 'marcar':
                    click(my_xpath)
            elif tipo == 'autocomplete':
                fill_autocomplete(context, valor, log_data)
            elif tipo == 'autocomplete multiplo':
                for valor_unico in valor.split(','):
                    my_xpath.reset()
                    my_xpath.find_form_input(campo, tipo)
                    fill_autocomplete_multiplo(context, valor_unico.strip(), log_data)
            elif tipo == 'filteredselectmultiple':
                for valor_unico in valor.split(','):
                    my_xpath.reset()
                    my_xpath.find_form_input(campo, tipo)
                    my_xpath.find_form_select_option(valor_unico.strip())
                    click(my_xpath)

                my_xpath.reset()
                my_xpath.find_form_filteredselectmultiple_add(campo)
                click(my_xpath)
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
            elif tipo == 'texto rico':
                browser = context.browser
                contador = 5
                while contador > 0:
                    if browser.is_element_present_by_tag('iframe'):
                        break
                    contador -= 1
                    # sleep(1)

                driver = browser.driver

                label = browser.find_by_xpath(f'//label[contains(normalize-space(text()), "{campo}")]')
                frame = driver.locator(f'//iframe[contains(normalize-space(@title), "{label.first["for"]}")]').first

                driver.switch_to.frame(frame)
                body = browser.find_by_tag('body').first
                body.click()
                body.click()
                body._element.send_keys(valor)

                assert body.html.lower() == f'<p>{valor}</p>'.lower()

                driver.switch_to.default_content()
            elif tipo == 'busca':
                click(my_xpath)

    step_ver_campos_formularios(context)
    step_clicar_botao(context, 'Salvar')
    step_ver_mensagem(context, 'erro', 'Por favor, corrija os erros abaixo.')
    step_ver_erros_formulario(context)
    step_preencher_formulario(context)


@then('abro o debugger')
def step_abro_debugger(context):
    abrir_debugger(context)


@then('vejo o status "{status}"')
def step_ver_status(context, status):
    xpath_padrao = f'//span[contains(@class, "active") and contains(text(), "{status}") and ancestor::*[contains(@class, "steps")]]'
    context.xpath.xpath = xpath_padrao
    assert context.xpath.get()


@then('vejo mais de {resultados_esperados} resultados na tabela')
def step_vejo_mais_resultados_na_tabela(context, resultados_esperados):
    my_xpath = context.xpath.reset()
    my_xpath.find_html_tr()
    assert my_xpath.get(int(resultados_esperados) + 1)


@then('vejo o texto {texto}')
def step_vejo_texto(context, texto):
    my_xpath = context.xpath.reset()
    my_xpath.find_div_text(texto)
