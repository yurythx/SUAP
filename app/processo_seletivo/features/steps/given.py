from behave import given

from comum.models import Ano


@given('os dados básicos do processo seletivo')
def step_dados_basicos_aval_int(context):
    Ano.objects.get_or_create(ano=2020)
