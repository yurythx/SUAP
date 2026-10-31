import uuid

from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from djtools.db import models
from suap import celery_app as app


class Crontab(CrontabSchedule):
    class Meta:
        proxy = True
        verbose_name = 'Crontab'
        verbose_name_plural = 'Crontabs'


class Intervalo(IntervalSchedule):
    class Meta:
        proxy = True
        verbose_name = 'Intervalo'
        verbose_name_plural = 'Intervalos'


class Agendamento(PeriodicTask):
    class Meta:
        proxy = True
        verbose_name = 'Agendamento'
        verbose_name_plural = 'Agendamentos'


class ResultadoExecucao(models.ModelPlus):
    STATUS_PENDING = 'PENDING'
    STATUS_RUNNING = 'RUNNING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_REVOKED = 'REVOKED'
    STATUS_TIMEOUT = 'TIMEOUT'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pendente'),
        (STATUS_RUNNING, 'Executando'),
        (STATUS_SUCCESS, 'Sucesso'),
        (STATUS_FAILED, 'Falha'),
        (STATUS_TIMEOUT, 'Timeout'),
        (STATUS_REVOKED, 'Revogado'),
    )
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    command_name = models.CharFieldPlus(verbose_name='Nome do Comando', max_length=255)
    args = models.TextField(verbose_name='Argumentos', null=True, blank=True)
    kwargs = models.TextField(verbose_name='Argumentos Nomeados', null=True, blank=True)
    datetime_start = models.DateTimeFieldPlus(verbose_name='Data e Hora de Início', auto_now_add=True)
    datetime_end = models.DateTimeFieldPlus(verbose_name='Data e Hora de Fim', null=True, blank=True)
    stdout = models.TextField(verbose_name='Saída Padrão', null=True, blank=True)
    stderr = models.TextField(verbose_name='Saída de Erro', null=True, blank=True)
    status = models.CharField(verbose_name='Status', null=True)
    task_id = models.CharField(verbose_name='ID da Tarefa', max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Resultado de Execução'
        verbose_name_plural = 'Resultados de Execução'

    def __str__(self):
        return f'Comando "{self.command_name}" executado às {self.datetime_start}'

    def get_absolute_url(self) -> str:
        return f'/beat/resultado_execucao/{self.pk}/'

    def get_status_css_class(self) -> str:
        """Classe de situação do Design System correspondente ao status."""
        mapa = {
            self.STATUS_SUCCESS: 'status-success',
            self.STATUS_FAILED: 'status-error',
            self.STATUS_TIMEOUT: 'status-error',
            self.STATUS_RUNNING: 'status-alert',
            self.STATUS_PENDING: 'status-info',
            self.STATUS_REVOKED: 'status-default',
        }
        return mapa.get(self.status, 'status-default')

    def get_stdout_display(self):
        return f'<pre>{self.stdout}</pre>' if self.stdout else 'Nenhuma saída padrão'

    def get_stderr_display(self):
        return f'<pre>{self.stderr}</pre>' if self.stderr else 'Nenhuma saída de erro'

    def get_status_display(self):
        status = dict(self.STATUS_CHOICES)
        return status.get(self.status, 'Desconhecido')

    def revoke(self):
        if self.task_id:
            app.control.revoke(self.task_id, terminate=True)
        self.status = self.STATUS_REVOKED
        self.save()
        return True
