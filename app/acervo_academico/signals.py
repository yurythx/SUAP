from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

from acervo_academico import tasks
from acervo_academico.models import RotinaImportacao


@receiver(post_save, sender=RotinaImportacao)
def rotina_importacao_post_save(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: tasks.baixar_metadados_da_rotina_de_importacao(instance))
