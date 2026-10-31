from behave import then


@then('vejo os seguintes campos no formulário preenchidos com')
def step_ver_campos_formularios_preenchidos(context):
    for row in context.table:
        campo = row['Campo']
        tipo = row['Tipo'].lower()
        valor = row['Valor']

        my_xpath = context.xpath.reset()
        my_xpath.find_form_input(campo, tipo)
        field = my_xpath.get()

        assert field, f'Campo "{campo}" não encontrado no formulário.'
        assert field.first.input_value() == valor, f'Campo "{campo}" esperado: "{valor}", encontrado: "{field.first.input_value()}".'
