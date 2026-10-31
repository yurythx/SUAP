from django.conf import settings

from djtools.assincrono import task
from djtools.models import Task
from djtools.utils import send_notification


@task('Notificar participantes do PGD')
def notificar_pgd_task(vinculo: object, assunto: str, texto: str, task: Task | None = None) -> None:
    assunto = f'[SUAP] PGD - {assunto}'
    mensagem = f'<p>{texto}</p>'
    send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo])
    # A Task pode chegar como None quando o registro já foi removido/expirou antes
    # do worker desserializá-la (ver retentativas em djtools/assincrono). Nesse caso
    # a notificação já foi enviada acima; apenas não há o que finalizar.
    if task is not None:
        task.finalize('Notificações PGD enviadas com sucesso.')
