from datetime import datetime

from behave import given

from ponto.models import Frequencia, Maquina
from rh.models import Servidor


@given('dados do ponto')
def step_atual_pagina(context):
    servidor = Servidor.objects.get(matricula='1111111')
    maquina = Maquina.objects.create(ip='127.0.0.1', descricao='Máquina 1', ativo=True, cliente_cadastro_impressao_digital=True, cliente_ponto=True)
    Frequencia.objects.create(vinculo=servidor.get_vinculo(), horario=datetime.now(), acao='E', maquina=maquina)
