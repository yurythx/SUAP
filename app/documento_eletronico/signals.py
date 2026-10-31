from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_fsm.signals import post_transition

from .status import SolicitacaoStatus

SolicitacaoRevisao = apps.get_model(app_label='documento_eletronico', model_name='SolicitacaoRevisao')
SolicitacaoAssinatura = apps.get_model(app_label='documento_eletronico', model_name='SolicitacaoAssinatura')


@receiver(post_save, sender=SolicitacaoRevisao, dispatch_uid='update_revisao_status')
def update_revisao_status(sender, instance, created, **kwargs):
    if created:
        instance.documento.colocar_em_revisao()
    elif instance.documento.estah_em_revisao:
        instance.documento.finalizar_revisao()
    instance.documento.save()


@receiver(post_save, sender=SolicitacaoAssinatura, dispatch_uid='update_assinatura_status')
def update_assinatura_status(sender, instance, created, **kwargs):
    if created:
        if not instance.documento.estah_aguardando_assinatura:
            instance.documento.solicitar_assinatura()
            instance.documento.save()


def on_solicitacao_assinatura_transition(sender, instance, name, source, target, **kwargs):
    outras_solicitacoes = (
        SolicitacaoAssinatura.objects.exclude(id=instance.id).filter(documento=instance.documento, status=SolicitacaoStatus.STATUS_ESPERANDO).exists()
    )
    if not outras_solicitacoes:
        if not instance.documento.estah_cancelado:
            if instance.documento.possui_assinatura():
                instance.documento.marcar_como_assinado()
            else:
                instance.documento.cancelar_assinatura()
        instance.documento.save()


post_transition.connect(on_solicitacao_assinatura_transition, sender=SolicitacaoAssinatura)
