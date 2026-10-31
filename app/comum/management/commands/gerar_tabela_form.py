import importlib

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='+', type=str)

    def handle(self, *args, **options):
        modulo = args[0]
        form_class = args[1]

        forms = importlib.import_module(f'{modulo}.forms')
        FormClass = getattr(forms, form_class)
        gerar_tabela_form(FormClass)


def get_tipo(tipo):
    # 'select', 'checkbox', 'textarea', 'autocomplete', 'radio'
    tipos = {
        'DecimalFieldPlus': 'Texto',
        'IntegerFieldPlus': 'Texto',
        'ModelChoiceField': 'Lista',
        'ModelChoiceFieldPlus': 'Lista',
        'ModelMultipleChoiceField': 'AutoComplete',
        'CharField': 'Texto',
        'CharFieldPlus': 'Texto',
        'DateTimeFieldPlus': 'Data',
        'BooleanField': 'Checkbox',
        'ChoiceFieldPlus': 'Lista',
    }
    return tipos[tipo]


def gerar_tabela_form(form_class):
    form = form_class()
    fields = form.fields
    tabela = [['Campo', 'Tipo', 'Obrigatório', 'Valor']]
    for field in fields:
        campo = fields[field].label
        tipo = get_tipo(fields[field].__class__.__name__)
        obrigatorio = fields[field].required and 'Sim' or 'Não'
        valor = ''
        tabela.append([campo, tipo, obrigatorio, valor])

    tamanho = [0, 0, 0, 0]
    for campo, tipo, obrigatorio, valor in tabela:
        if len(campo) > tamanho[0]:
            tamanho[0] = len(campo)

        if len(tipo) > tamanho[1]:
            tamanho[1] = len(tipo)

        if len(obrigatorio) > tamanho[2]:
            tamanho[2] = len(obrigatorio)

        if len(valor) > tamanho[3]:
            tamanho[3] = len(obrigatorio)

    template = f'  | {{:{tamanho[0]}}} | {{:{tamanho[1]}}} | {{:{tamanho[2]}}} | {{:{tamanho[3]}}} |'
    print('Então vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preenchidos com')
    for campo, tipo, obrigatorio, valor in tabela:
        print(template.format(campo, tipo, obrigatorio, valor))
