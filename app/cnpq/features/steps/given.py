from behave import given
from django.core.management import call_command

from cnpq.models import AreaAvaliacao


@given('os cadastros básicos do cnpq')
def step_cadastros(context):
    AreaAvaliacao.objects.create(nome='MATERIAIS')
    kwargs = {'forcar': True, 'matricula': '300021', 'file': 'cnpq/tests_files/5173495516982528.zip'}
    call_command('cnpq_importar', **kwargs)
