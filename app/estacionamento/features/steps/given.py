from behave import given

from estacionamento.models import VeiculoCor


@given('os dados básicos do estacionamento')
def step_cadastros_feature_001(context):
    VeiculoCor.objects.get_or_create(nome='Branca')
