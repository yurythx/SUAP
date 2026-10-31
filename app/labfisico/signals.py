from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from edu.models import MatriculaDiario

from .beat import load_tasks_schedule
from .helpers import support_periodic_tasks
from .models import GuacamoleServer, SolicitacaoLabFisico


@receiver(post_delete, sender=MatriculaDiario)
def notify_lab_fisico_on_save(sender, instance, **kargs):
    if instance.id is None:
        solicitacao = SolicitacaoLabFisico.objects.deferidas().filter(diario=instance.diario).first()
        if solicitacao:
            try:
                aluno = instance.get_aluno()
                solicitacao.adicionar_membro(aluno.matricula)
            except Exception:
                pass
    #


@receiver(post_save, sender=MatriculaDiario)
def notify_lab_fisico_on_delete(sender, instance, **kargs):
    solicitacao = SolicitacaoLabFisico.objects.deferidas().filter(diario=instance.diario).first()
    if solicitacao:
        try:
            aluno = instance.get_aluno()
            solicitacao.remover_membro(aluno.matricula)
        except Exception:
            pass


@receiver(post_save, sender=GuacamoleServer)
def setup_guacamole_server(sender, instance, created, **kwargs):
    if created and support_periodic_tasks():
        load_tasks_schedule()
