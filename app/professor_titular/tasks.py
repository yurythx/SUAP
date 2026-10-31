from django.core.management import call_command

from suap import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def checar_prazos_e_reservas(self):
    """Executa o comando que checa prazos e promove reservas (checar_datas)."""
    call_command('checar_datas')
