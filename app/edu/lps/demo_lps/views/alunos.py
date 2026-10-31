from django.shortcuts import get_object_or_404

from djtools.utils import (
    normalizar_nome_proprio,
    rtr,
)
from edu.models import Aluno


@rtr()
def aluno(request, matricula):
    obj = get_object_or_404(Aluno, matricula=matricula)
    title = f'{normalizar_nome_proprio(obj.get_nome())} ({obj.matricula!s}) LPS'

    is_responsavel = True
    return locals()
