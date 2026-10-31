from behave import when

from djtools.new_tests.utils import click


@when('clico no label "{valor_label}" da etapa "{numero_etapa}"')
def step_clico_label(context, valor_label, numero_etapa):
    context.page.evaluate(f"checkAllRadios({numero_etapa}, '{valor_label}')")


@when('seto o status da linha de avaliação para "{status}"')
def step_setar_status(context, status):
    status_value = ''
    if status == 'C.P':
        status_value = 'ERROR'
    my_xpath = context.xpath.reset()
    my_xpath.xpath += f'{context.xpath.contexto}//td//div//input[@value="{status_value}"]'
    click(my_xpath)
