from behave import given
from django.apps.registry import apps

Ano = apps.get_model('comum', 'Ano')


@given('os dados básicos para encceja')
def step_dados_basicos_encceja(context):
    Ano.objects.get_or_create(ano='2020')[0]
