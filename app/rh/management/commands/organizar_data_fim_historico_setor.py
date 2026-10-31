from datetime import timedelta

from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from rh.models import Servidor

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Organizar Data Fim do Historico de Setor'

    def handle(self, *args, **options):
        lista_servidores_afetados = []
        for servidor in Servidor.objects.ativos().all():
            # verfiicando se o servidor tem setores com data fim nulas
            check_historico = servidor.servidorsetorhistorico_set.filter(data_fim_no_setor__isnull=True)
            # se existir mais de um historico de setor com data fim nula, é necessário a correção
            if check_historico.count() > 1:
                s = f'{servidor.pessoa_fisica.nome} ({servidor.matricula})'
                lista_servidores_afetados.append(s)
                data_anterior = None
                for i in check_historico.order_by('-data_inicio_no_setor'):
                    if data_anterior is not None:
                        i.data_fim_no_setor = data_anterior
                        i.save()
                    data_anterior = i.data_inicio_no_setor - timedelta(days=1)

        if lista_servidores_afetados:
            Log.objects.create(
                titulo='Ajustes no histórico de setores',
                texto='Os seguintes servidores tiveram seus históricos de setores ajustados com relação a data fim:'
                + ', '.join(lista_servidores_afetados),
                app='rh',
            )
