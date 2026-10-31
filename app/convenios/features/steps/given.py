from behave import given
from django.apps.registry import apps

TipoConvenio = apps.get_model('convenios', 'TipoConvenio')
SituacaoConvenio = apps.get_model('convenios', 'SituacaoConvenio')
TipoAnexo = apps.get_model('convenios', 'TipoAnexo')


@given('os dados básicos para convênios')
def step_dados_basicos_convenios(context):
    TipoConvenio.objects.get_or_create(descricao='Acordo de Cooperação')[0]
    TipoConvenio.objects.get_or_create(descricao='Desenvolvimento de RH')[0]
    TipoConvenio.objects.get_or_create(descricao='Aprendizagem')[0]
    TipoConvenio.objects.get_or_create(descricao='Estágio')[0]
    TipoConvenio.objects.get_or_create(descricao='Cooperação Técnica')[0]
    TipoConvenio.objects.get_or_create(descricao='Relações Internacionais')[0]

    TipoAnexo.objects.get_or_create(descricao='Arquivo Digitalizado/Convênio')[0]
    TipoAnexo.objects.get_or_create(descricao='Arquivo Digitalizado/Aditivo')[0]
    TipoAnexo.objects.get_or_create(descricao='Termo de Rescisão')[0]
    TipoAnexo.objects.get_or_create(descricao='Termo de Extinção')[0]

    SituacaoConvenio.objects.get_or_create(id=1, descricao='Vigente')[0]
    SituacaoConvenio.objects.get_or_create(id=4, descricao='Vencido')[0]
    SituacaoConvenio.objects.get_or_create(id=3, descricao='Vencendo')[0]
