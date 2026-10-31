from django.db import transaction
from django.db.models import Max, Min
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

from estagios.models import ModuloAprendizagem, Aprendizagem


@receiver(post_save, sender=ModuloAprendizagem)
def moduloaprendizagem_post_save_atualizar_datas_aprendizagem(sender, instance: ModuloAprendizagem, created, **kwargs):
    """
    Signal para garantir que o início e a previsão de fim da aprendizagem reflitam corretamente as datas dos módulos associados a ela.
    """
    id_aprendizagem = instance.aprendizagem_id

    def _atualizar_aprendizagem():
        if id_aprendizagem:
            inicio_primeiro_modulo, fim_ultimo_modulo = (
                ModuloAprendizagem.objects.filter(aprendizagem_id=id_aprendizagem)
                .aggregate(inicio_primeiro_modulo=Min('inicio'), fim_ultimo_modulo=Max('fim'))
                .values()
            )

            Aprendizagem.objects.filter(pk=id_aprendizagem).update(data_inicio=inicio_primeiro_modulo, data_prevista_encerramento=fim_ultimo_modulo)

    transaction.on_commit(_atualizar_aprendizagem)
