from django.core.management import call_command

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', '../fixtures/initial_data_01_classificacao.json', verbosity=verbosity)
        # Os tipos de documento e modelos carregados a seguir foram criados com base em documentos presentes
        # na pasta do GABIN/RE.
        call_command('loaddata', '../fixtures/initial_data_02_tipo_documento.json', verbosity=verbosity)
        call_command('loaddata', '../fixtures/initial_data_03_modelo_documento.json', verbosity=verbosity)
        call_command('loaddata', '../fixtures/initial_data_04_tipo_conferencia.json', verbosity=verbosity)
        call_command('loaddata', '../fixtures/initial_data_05_tipo_vinculo_documento.json', verbosity=verbosity)
        call_command('loaddata', '../fixtures/initial_data_06_hipotese_legal.json', verbosity=verbosity)
        call_command('loaddata', '../fixtures/modelos_documentos_fiscal_contrato.json', verbosity=verbosity)
        call_command('importar_funcao_servidor', verbosity=verbosity)
