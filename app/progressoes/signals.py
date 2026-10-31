from django.db.models.signals import post_delete
from django.dispatch import receiver

from progressoes.models import ServidorAProgredir, ProcessoProgressao


@receiver(post_delete, sender=ProcessoProgressao)
def after_processo_progressao_delete(sender, instance, **kwargs):
    # mantendo a flag do relatório atualizada com a situação do processo de progressão
    if instance and instance.registro_a_progredir:
        try:
            relatorio = ServidorAProgredir.objects.get(pk=instance.registro_a_progredir.pk)
            relatorio.processo_criado = False
            relatorio.save()
        except Exception:
            pass
