import datetime

from djtools.management.commands import BaseCommandPlus
from projetos.models import AvaliadorIndicado


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for avaliador in AvaliadorIndicado.objects.filter(prazo_para_aceite__isnull=False, rejeitado=False):
            prazo_aceite_vencido = not avaliador.aceito_em and avaliador.prazo_para_aceite and datetime.datetime.now() > avaliador.prazo_para_aceite
            prazo_avaliacao_vencido = (
                avaliador.aceito_em and avaliador.prazo_para_avaliacao and datetime.datetime.now() > avaliador.prazo_para_avaliacao
            )

            if not avaliador.ja_avaliou() and (prazo_aceite_vencido or prazo_avaliacao_vencido):
                avaliador.rejeitado = True
                avaliador.rejeitado_em = datetime.datetime.now()
                avaliador.rejeitado_automaticamente = True
                avaliador.save()
