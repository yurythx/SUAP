import datetime

import tqdm

from centralservicos.models import AtendimentoAtribuicao, Chamado, GrupoAtendimento, HistoricoStatus
from djtools.management.commands import BaseCommandPlus

"""
python manage.py centralservicos_forcar_atribuicao
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for chamado in tqdm.tqdm(Chamado.objects.filter(atendimentoatribuicao__isnull=True)):
            centro_atendimento = chamado.servico.centros_atendimento.first()
            atribuicao = AtendimentoAtribuicao()
            atribuicao.chamado = chamado

            atribuicao.grupo_atendimento = GrupoAtendimento.get_grupo_primeiro_nivel(chamado.campus, centro_atendimento)
            atribuicao.atribuido_em = datetime.datetime.today()
            atribuicao.save()

            historico_status = HistoricoStatus()
            historico_status.chamado = chamado
            historico_status.usuario = chamado.aberto_por
            historico_status.data_hora = chamado.aberto_em
            historico_status.status = chamado.status
            historico_status.save()
