from behave import given

from comum.models import Predio, Sala
from rh.models import Servidor, UnidadeOrganizacional


@given('Salas e Servidores já existentes')
def step_cadastros_feature_001(context):
    campus_a_suap = UnidadeOrganizacional.objects.get(sigla='A0')
    predio = Predio.objects.get_or_create(nome='Prédio A1', uo=campus_a_suap, ativo=True)[0]
    Sala.objects.get_or_create(nome='Sala A1', ativa=True, predio=predio, agendavel=False)
    pessoa_fisica = Servidor.objects.get(matricula='1111111').pessoa_fisica
    pessoa_fisica.tem_digital_fraca = True
    pessoa_fisica.save()
