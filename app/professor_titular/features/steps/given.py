from behave import given

from professor_titular.models import CategoriaMemorialDescritivo, Grupo, Indicador, Unidade


@given('os dados básicos para professor titular')
def step_cadastros(context):
    Unidade.objects.get_or_create(nome='mês', sigla='lv')
    CategoriaMemorialDescritivo.get_or_create(nome='pesquisa e atividades', indice='1')
    Grupo.objects.get_or_create(nome='A', percentual=10)

    grupo2 = Grupo.objects.get(nome='A')
    Indicador.objects.get_or_create(grupo=grupo2, nome='atividade', descricao='teste')
