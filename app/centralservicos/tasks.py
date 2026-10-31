from sentry_sdk import capture_exception

from centralservicos.models import Servico
from djtools.assincrono import task
from djtools.models import Task


@task('Atualizar estatísticas de um serviço da central de serviços')
def atualizar_estatisticas(servico: Servico, task: Task | None = None) -> None:
    # Quem pediu quer recalcular: marca como pendente mesmo que não estivesse.
    servico.anular_estatisticas()
    try:
        recalculado = Servico.recalcular_estatisticas_pendentes(servico.pk)
    except Exception as error:
        capture_exception(error)
        task.finalize(f'As estatísticas do serviço "{servico}" não foram atualizadas: {error!s}', error=True)
        return
    if recalculado:
        task.finalize(
            f'As estatísticas do serviço "{servico}" foram atualizadas com sucesso.', url=f'/centralservicos/estatisticas_servico/{servico.pk}/'
        )
    else:
        task.finalize(f'As estatísticas do serviço "{servico}" já estão sendo atualizadas por outra execução. Tente novamente em instantes.')
