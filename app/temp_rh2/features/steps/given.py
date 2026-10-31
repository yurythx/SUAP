from behave import given
from django.apps.registry import apps

from rh.models import PessoaFisica

Ano = apps.get_model('comum', 'Ano')


@given('os dados básicos para competição desportiva')
def step_dados_basicos_competicao(context):
    Ano.objects.get_or_create(ano='2020')


@given('os dados de sexo do servidor está populado')
def step_dados_de_sexo_do_servidor_esta_populado(context):
    p = PessoaFisica.objects.get(servidor_set__matricula=337003)
    p.sexo = 'M'
    p.save()
