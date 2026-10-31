from datetime import datetime, timedelta

from django.conf import settings

from compras.models import EtapaCompra, EtapasProcessoCompra
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification

"""
python manage.py compras_notificar_alteracao_de_etapa
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        try:
            """Obtém etapas que estão iniciando e finalizando"""
            etapas_compras_data_fim_em_5_dias = EtapaCompra.objects.filter(data_fim=datetime.today() + timedelta(days=5))

            """Notificação de fim de etapa de processo de compra -  5 dias antes"""
            qtd_compras_fim_etapa_notificadas = 0
            for etapa_compra in etapas_compras_data_fim_em_5_dias:
                titulo = '[SUAP]  Etapa de processo de compra próxima do fim'
                texto = []
                texto.append('<h1>Compras -  Etapa de processo de compra próxima do fim</h1>')
                texto.append(
                    f'<h2>Etapa {EtapasProcessoCompra.get_display(etapa_compra.etapa)} a finalizar para processo de compra {etapa_compra.compra.processo.numero_protocolo_fisico}</h2>'
                )
                texto.append(
                    f'<p>A compra de objeto: {etapa_compra.compra.objeto} instruída no  <a href="{etapa_compra.compra.processo.get_absolute_url()}">{etapa_compra.compra.processo}</a>  está com a etapa de {EtapasProcessoCompra.get_display(etapa_compra.etapa)} a finalizar em 5 dias: {etapa_compra.data_fim.strftime("%d/%m/%Y")}.</p>'
                )
                texto.append('<h3>Dados gerais</h3>')
                texto.append('<dl>')
                texto.append(
                    f'<dt>Processo:</dt><dd><a href="{etapa_compra.compra.processo.get_absolute_url()}">{etapa_compra.compra.processo}</a></dd>'
                )
                texto.append(f'<dt>Tipo de Calendário:</dt><dd>{etapa_compra.compra.tipo_calendario}</dd>')
                texto.append(f'<dt>Núcleo responsável:</dt><dd>{etapa_compra.compra.nucleo_responsavel}</dd>')
                texto.append(f'<dt>Campus responsável:</dt><dd>{etapa_compra.compra.campus_responsavel}</dd>')
                texto.append('</dl>')
                texto.append(
                    f'<p class="more-info">Para mais informações, acesse: <a href="{etapa_compra.compra.get_absolute_url()}">{etapa_compra.compra}</a></p>'
                )
                vinculos_a_notificar = []
                if etapa_compra.compra.nucleo_responsavel.responsavel_vinculo:
                    vinculos_a_notificar.append(etapa_compra.compra.nucleo_responsavel.responsavel_vinculo)
                if etapa_compra.compra.nucleo_responsavel:
                    vinculos_a_notificar.append(etapa_compra.compra.nucleo_responsavel.get_vinculos_componentes())
                if etapa_compra.compra.processo:
                    vinculos_a_notificar.append(etapa_compra.compra.processo.interessados.all())
                if vinculos_a_notificar:
                    for vinculo in vinculos_a_notificar:
                        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos=vinculo, objeto=etapa_compra.compra)

            self.stdout.write(self.style.SUCCESS(f'Notificou {qtd_compras_fim_etapa_notificadas} datas de início de etapa. '))
        except Exception as e:
            if settings.DEBUG:
                raise e
            self.stdout.write(self.style.ERROR(f'Erro na execução, detalhes: {e}'))
