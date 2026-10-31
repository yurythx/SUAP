from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from pafc.models import DocumentoHibrido, MatrizPAFC, PAFC, InfraestruturaExternaPAFC


@receiver(post_delete, sender=DocumentoHibrido)
def remover_arquivo_do_storage(sender, instance: DocumentoHibrido, **kwargs):
    if instance.arquivo and instance.arquivo.storage.exists(instance.arquivo.name):
        instance.arquivo.delete(save=False)


@receiver(post_delete, sender=InfraestruturaExternaPAFC)
def remover_comprovante_ao_remover_infraestrutura_externa(sender, instance: InfraestruturaExternaPAFC, **kwargs):
    if instance.comprovante_disponibilidade:
        instance.comprovante_disponibilidade.delete()


@receiver(post_save, sender=MatrizPAFC)
def sincronizar_pomc_apos_adicao_de_matriz(sender, instance: MatrizPAFC, created, **kwargs):
    if created:
        transaction.on_commit(lambda: instance.pafc.sincronizar_planos_disciplina_entre_ppc_e_pomc(None))


@receiver(post_delete, sender=MatrizPAFC)
def sincronizar_pomc_apos_remocao_da_matriz(sender, instance: MatrizPAFC, **kwargs):
    id_pafc = instance.pafc_id

    def _sincronizar():
        pafc = PAFC.objects.filter(pk=id_pafc).first()
        if pafc:
            pafc.sincronizar_planos_disciplina_entre_ppc_e_pomc(None)

    transaction.on_commit(_sincronizar)
