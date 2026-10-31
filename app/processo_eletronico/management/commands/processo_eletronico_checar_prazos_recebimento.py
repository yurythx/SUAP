from datetime import datetime

from comum.models import Configuracao, Vinculo
from djtools.management.commands import BaseCommandPlus
from processo_eletronico.models import PrazoRecebimentoProcesso, Tramite


class Command(BaseCommandPlus):
    def handle(self, *args: object, **options: object) -> None:
        if not Configuracao.get_valor_por_chave('processo_eletronico', 'prazo_recebimento_processo'):
            return
        for obj in PrazoRecebimentoProcesso.objects.filter(tramite__recebido_por__isnull=True, limite__lt=datetime.today()).exclude(decorrido=True):
            self._receber_por_decurso(obj)

    def _receber_por_decurso(self, obj: PrazoRecebimentoProcesso) -> None:
        tramite = obj.tramite
        # Receber um processo apensado recebe também os demais do apensamento: o trâmite pode já ter sido recebido nesta execução.
        tramite.refresh_from_db(fields=['recebido_por', 'data_hora_recebimento'])
        if tramite.recebido_por_id:
            recebido_por = tramite.recebido_por
        else:
            recebido_por = self._get_recebedor(tramite)
            if not recebido_por:
                return
            self.stdout.write(f'Registrando recebimento do processo "{tramite.processo}" por "{recebido_por}"')
            tramite.receber_processo(recebido_por=recebido_por, data_hora_recebimento=datetime.today())
        obj.decorrido = True
        obj.save()
        obj.notificar_decurso(recebido_por)

    @staticmethod
    def _get_recebedor(tramite: Tramite) -> Vinculo | None:
        if tramite.destinatario_vinculo:
            return tramite.destinatario_vinculo
        chefe = tramite.destinatario_setor.obter_chefes_hieraquicamente().first()
        return chefe.vinculo_set.first() if chefe else None
