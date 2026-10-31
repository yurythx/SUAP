from datetime import datetime, timedelta

from tqdm import tqdm

from djtools.management.commands import BaseCommandPlus
from eventos.models import Evento


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        agora = datetime.now()
        data_limite_finalizacao = agora - timedelta(15)
        eventos_a_serem_finalizados = Evento.objects.filter(
            finalizado=False, submetido=True, deferido=True, ativo=True, data_fim__lte=data_limite_finalizacao
        )
        for evento in tqdm(eventos_a_serem_finalizados):
            evento.finalizar_automaticamente()

        eventos_encerrados = Evento.objects.filter(
            gera_certificado=True,
            cancelado=False,
            submetido=True,
            deferido=True,
            data_fim__lte=agora.date(),
        ).distinct()

        for evento in tqdm(eventos_encerrados, leave=False):
            evento.emitir_certificados_automaticamente()
