from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from edu.models import MatriculaDiario

from .beat import load_tasks_schedule
from .helpers import support_periodic_tasks
from .models import DesktopPool, SolicitacaoLabVirtual


@receiver(post_delete, sender=MatriculaDiario)
def notify_lab_virtual_on_save(sender, instance, **kargs):
    if instance.id is None:
        solicitacao = SolicitacaoLabVirtual.objects.deferidas().filter(diario=instance.diario).first()
        if solicitacao:
            try:
                aluno = instance.get_aluno()
                solicitacao.adicionar_membro(aluno.matricula)
            except Exception:
                pass
    #


@receiver(post_save, sender=MatriculaDiario)
def notify_lab_virtual_on_delete(sender, instance, **kargs):
    solicitacao = SolicitacaoLabVirtual.objects.deferidas().filter(diario=instance.diario).first()
    if solicitacao:
        try:
            aluno = instance.get_aluno()
            solicitacao.remover_membro(aluno.matricula)
        except Exception:
            pass


@receiver(post_save, sender=DesktopPool)
def setup_vdi_server(sender, instance, created, **kwargs):
    if created and support_periodic_tasks():
        load_tasks_schedule()
