import json

from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def carregar_call_command(name, command, args=None, kwargs=None, interval=None, crontab=None, expire_seconds=None):
    """
    Carrega uma tarefa periódica para o Celery Beat.

    :param name: Nome da tarefa.
    :param command: Comando a ser executado.
    :param every: Intervalo de tempo para executar a tarefa.
    :param period: Unidade de tempo (ex: Intervalo.HOURS).
    :param expire_seconds: Tempo em segundos antes que a tarefa expire.
    """
    from beat.models import Agendamento, Crontab, Intervalo

    schedule = None

    if interval:
        every = interval[0]
        period = interval[1]

        interval, _ = Intervalo.objects.get_or_create(
            every=every,
            period=period,
        )
        schedule = {'interval': interval}

    if crontab:
        minute = crontab.get('minute', '*')
        hour = crontab.get('hour', '*')
        day_of_month = crontab.get('day_of_month', '*')
        month_of_year = crontab.get('month_of_year', '*')
        day_of_week = crontab.get('day_of_week', '*')
        crontab, _ = Crontab.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
        schedule = {'crontab': crontab}

    if not schedule:
        raise ValueError('Você deve fornecer um intervalo ou uma crontab para agendar a tarefa.')

    if not args:
        args = []

    if not kwargs:
        kwargs = {}

    _, created = Agendamento.objects.get_or_create(
        name=name,
        defaults=dict(
            task='beat.tasks.call_command',
            args=json.dumps([command, *args]),
            kwargs=json.dumps(kwargs),
            queue='beat',
            expire_seconds=expire_seconds,
            **schedule,
        ),
    )
    if created:
        logger.info(f"Tarefa '{name}' criada com sucesso para o Celery Beat.")


def carregar_bash_script(name, script_path, args=None, interval=None, crontab=None, expire_seconds=None):
    """
    Carrega uma tarefa periódica para executar um script bash.
    """
    from beat.models import Agendamento, Crontab, Intervalo

    schedule = None

    if interval:
        every = interval[0]
        period = interval[1]

        interval, _ = Intervalo.objects.get_or_create(
            every=every,
            period=period,
        )
        schedule = {'interval': interval}

    if crontab:
        minute = crontab.get('minute', '*')
        hour = crontab.get('hour', '*')
        day_of_month = crontab.get('day_of_month', '*')
        month_of_year = crontab.get('month_of_year', '*')
        day_of_week = crontab.get('day_of_week', '*')
        crontab, _ = Crontab.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
        schedule = {'crontab': crontab}

    if not schedule:
        raise ValueError('Você deve fornecer um intervalo ou uma crontab para agendar a tarefa.')

    if not args:
        args = []

    _, created = Agendamento.objects.get_or_create(
        name=name,
        defaults=dict(
            task='beat.tasks.execute_bash_script',
            args=json.dumps([script_path, *args]),
            queue='beat',
            **schedule,
            expire_seconds=expire_seconds,
        ),
    )
    if created:
        logger.info(f"Tarefa '{name}' criada com sucesso para o Celery Beat.")
