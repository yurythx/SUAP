from ninja import Router

from djtools.ninja.router import get
from processo_eletronico.models import (
    Processo,
)

from ..schemas.processo import (
    ProcessoSchema,
)

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/processos/',
    response=list[ProcessoSchema],
    auth=False,
    summary='Processos',
    description=(
        'Retorna número do processo, interessado, assunto, data de cadastro, campus de origem, situação e trâmites. '
        'O número é o de protocolo físico, gerado logo após o cadastro: um processo recém-criado pode sair com número nulo.'
    ),
)
def processos(
    request,
):
    return Processo.objects.filter(nivel_acesso=Processo.NIVEL_ACESSO_PUBLICO)
