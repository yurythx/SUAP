from threading import Thread

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.urls import reverse

from cron import models
from djtools.utils import httprr, rtr


@login_required
@atomic
def atualizar_comandos(request):
    if request.user.is_superuser:
        models.Comando.create_commands_from_django()
        return httprr(request.META.get('HTTP_REFERER', '..'), 'Comandos atualizados com sucesso')
    raise PermissionDenied


@login_required
def executar_comando(request, object_id):
    if request.user.is_superuser:
        comando = get_object_or_404(models.ComandoAgendamento, id=object_id)
        thread = Thread(target=comando.executar, args=(request.user,))
        thread.start()
        return httprr(reverse('admin:cron_logexecucao_changelist'), 'Comando em execução. Acompanhe pelo log de execução.')
    raise PermissionDenied


@login_required
def interromper_comando(request, object_id):
    if request.user.is_superuser:
        log_execucao = get_object_or_404(models.LogExecucao, id=object_id)
        log_execucao.interromper()
        return httprr(reverse('admin:cron_logexecucao_changelist'), 'Comando interrompido. Acompanhe pelo log de execução.')
    raise PermissionDenied


@login_required
@rtr()
def visualizar_execucao(request, object_id):
    if request.user.is_superuser:
        execucao = get_object_or_404(models.LogExecucao, id=object_id)
        return locals()
    raise PermissionDenied
