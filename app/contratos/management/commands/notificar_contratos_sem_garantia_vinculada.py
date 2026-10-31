from datetime import datetime, timedelta

from comum.models import NotificacaoSistema
from contratos.models import Contrato
from contratos.utils import Notificar
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        Notifica os contratos que possui exigência de garantia contratual e ainda não houver garantias cadastradas,
        o sistema deve enviar notificações periódicas para o Fiscal de Contrato em 15, 30 e 60 dias.
        """
        # Envia notificações
        contratos_que_exigem_garantia_sem_arquivo_cadastrado = Contrato.objects.filter(
            exige_garantia_contratual=True, garantias__isnull=True, concluido=False
        )
        contratos_aditivados_com_garantia_expirada = Contrato.objects.filter(exige_garantia_contratual=True, aditivos__isnull=False).exclude(
            garantias__vigencia__gte=datetime.now()
        )
        contratos_a_notificar = contratos_que_exigem_garantia_sem_arquivo_cadastrado.union(contratos_aditivados_com_garantia_expirada)

        self.stdout.write(f'{contratos_a_notificar.count()} contratos para notificar!')
        for contrato in contratos_a_notificar:
            try:
                # A dt inicio será a data de inicio do contrato ou data de inicio do ultimo aditivo caso exista
                dt_inicio = contrato.data_inicio if not contrato.get_ultimo_termo_aditivo() else contrato.get_ultimo_termo_aditivo().data_inicio
                dt_15_dias_apos_inicio = dt_inicio + timedelta(days=15)
                dt_30_dias_apos_inicio = dt_inicio + timedelta(days=30)
                dt_60_dias_apos_inicio = dt_inicio + timedelta(days=60)
                self.stdout.write(f'{dt_inicio} - {dt_15_dias_apos_inicio} - {dt_30_dias_apos_inicio} - {dt_60_dias_apos_inicio}')
                datas_para_notificacao = [dt_15_dias_apos_inicio, dt_30_dias_apos_inicio, dt_60_dias_apos_inicio]
                foi_notificado = NotificacaoSistema.objects.filter(
                    categoria__assunto=f'Adicione arquivo da garantia - Contrato {contrato.numero}'
                ).exists()
                if (datetime.now().date() in datas_para_notificacao) or ((datetime.now().date() > dt_60_dias_apos_inicio) and not foi_notificado):
                    Notificar.contrato_sem_garantia_vinculada(contrato)
            except Exception:
                continue
