from django_celery_beat.models import IntervalSchedule, PeriodicTask


def load_tasks_schedule():
    every_day, _ = IntervalSchedule.objects.get_or_create(every=1, period=IntervalSchedule.DAYS)

    PeriodicTask.objects.update_or_create(
        name='[auditoria] Atualizar Solicitações de Providência da Auditoria Expiradas',
        task='auditoria.tasks.atualizar_solicitacoes_expiradas',
        defaults={'queue': 'beat', 'interval': every_day},
    )
    PeriodicTask.objects.update_or_create(
        name='[auditoria] Verificar Expiração das Recomendações',
        task='auditoria.tasks.verificar_recomendacoes_expiradas',
        defaults={'queue': 'beat', 'interval': every_day},
    )
