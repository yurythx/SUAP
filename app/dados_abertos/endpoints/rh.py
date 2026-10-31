from ninja import Router

from djtools.ninja.router import get
from rh.models import Servidor, Setor

from ..schemas.servidor import ServidorSchema
from ..schemas.setor import SetorSchema

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/servidores/',
    response=list[ServidorSchema],
    ignore_paginate=True,
    auth=False,
    summary='Servidores',
    description='Retorna matrícula, nome, cargo/emprego e campus (informações iniciais).',
)
def servidores(request):
    return Servidor.objects.ativos().select_related('pessoa_fisica', 'cargo_emprego', 'setor__uo').order_by('matricula')


@get(
    router,
    '/setores/',
    response=list[SetorSchema],
    ignore_paginate=True,
    auth=False,
    summary='Setores',
    description='Retorna informações relevantes de setores (sigla, nome, campus e hierarquia).',
)
def setores(request):
    return Setor.objects.suap_ativos().select_related('uo', 'superior').order_by('uo__sigla', 'sigla', 'nome')
