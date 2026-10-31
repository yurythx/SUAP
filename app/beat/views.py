from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools.utils import permission_required, rtr

from .models import ResultadoExecucao


@rtr('beat/resultado_execucao.html')
@login_required
@permission_required('beat.view_resultadoexecucao')
def resultado_execucao(request, pk: int):
    title = 'Resultado de execução'
    resultado = get_object_or_404(ResultadoExecucao, pk=pk)
    return locals()
