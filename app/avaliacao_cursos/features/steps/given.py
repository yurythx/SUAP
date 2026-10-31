from behave import given

from comum.models import Ano


@given('os dados basicos cadastrados da avaliacao de cursos')
def step_atual_pagina(context):
    Ano.objects.get_or_create(ano=2020)
