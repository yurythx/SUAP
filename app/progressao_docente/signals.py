import logging

import sentry_sdk
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from progressao_docente.models import DocenteAProgredir, ProgressaoDocente

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=ProgressaoDocente)
def after_progressao_docente_delete(sender: type[ProgressaoDocente], instance: ProgressaoDocente, **kwargs) -> None:
    if instance and instance.relatorio_a_progredir:

        def atualizar_relatorio():
            try:
                relatorio = DocenteAProgredir.objects.get(pk=instance.relatorio_a_progredir.pk)
                # Outra progressão segue ligada ao relatório: reabri-lo devolvia o botão de criar e gerava cópia (#17738)
                if relatorio.progressaodocente_set.exists():
                    return
                relatorio.progressao_criada = False
                relatorio.progressao_finalizada = False
                relatorio.save()
            except Exception as e:
                logger.warning(f'Erro ao atualizar relatorio após exclusão de ProgressaoDocente ID {instance.id}: {e}')
                sentry_sdk.capture_exception(e)

        transaction.on_commit(atualizar_relatorio)


@receiver(post_save, sender=ProgressaoDocente)
def after_save_progressao_docente(sender, instance, **kwargs):
    if instance and instance.relatorio_a_progredir:

        def atualizar_relatorio():
            try:
                relatorio = DocenteAProgredir.objects.get(pk=instance.relatorio_a_progredir.pk)

                if instance.data_inicio_periodo and instance.data_fim_periodo:
                    relatorio.data_inicio_contagem = instance.data_inicio_periodo
                    relatorio.data_fim_contagem = instance.data_fim_periodo
                    relatorio.nivel_atual = instance.nivel_atual
                    relatorio.proximo_nivel = instance.proximo_nivel
                    relatorio.save()
                else:
                    logger.warning(f'Relatório não atualizado: campos obrigatórios ausentes para ProgressaoDocente ID {instance.id}')

            except Exception as e:
                logger.warning(f'Erro ao atualizar relatorio após salvar ProgressaoDocente ID {instance.id}: {e}')
                sentry_sdk.capture_exception(e)

        transaction.on_commit(atualizar_relatorio)
