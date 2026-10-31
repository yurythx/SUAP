from django.urls import reverse

from djtools.assincrono import task
from licenca_capacitacao.models import ProcessamentoEdital


@task(name='Calcular Processamento da Licença Capacitação')
def calcular_processamento(processamento_id, user, task=None):
    processamento = ProcessamentoEdital.objects.get(pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])
    task.start_progress(100)
    task.update_progress(5)
    ProcessamentoEdital.processar_resultado(user, processamento, task)
    return task.finalize('Cálculos realizados com sucesso.', url)
