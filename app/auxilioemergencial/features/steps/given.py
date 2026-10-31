from behave import given

# O behave do `ae` foi removido no MR de conversão para o modo 2: o corpo do antigo step
# `os dados basicos cadastrados do ae` hoje vive no seed do e2e do módulo.
from ae.tests.e2e.seed import dados_basicos_ae


@given('os dados básicos do auxílio emergencial')
def step_dados_basicos(context):
    dados_basicos_ae()
