from datetime import date

from djtools.management.commands import BaseCommandPlus
from rh.models import JornadaTrabalho, Setor, SetorJornadaHistorico


class Command(BaseCommandPlus):
    help = 'Inicializa os históricos de jornadas de trabalho dos setores'

    def handle(self, *args, **options):
        #
        # limpa o histórico atual
        #
        SetorJornadaHistorico.objects.all().delete()

        #
        # para cada setor, registra dois históricos:
        #     30h semanais até 03/11/2013
        #     40h semanais a partir de 04/11/2013
        #
        jornada_30h = JornadaTrabalho.objects.get(codigo='30')
        jornada_40h = JornadaTrabalho.objects.get(codigo='40')
        for setor in Setor.objects.suap_ativos().all():
            print(setor)

            #
            # 30h
            #
            jornada = SetorJornadaHistorico()
            jornada.setor = setor
            jornada.jornada_trabalho = jornada_30h
            jornada.data_inicio_da_jornada = date(2010, 1, 1)  # reforma administrativa
            jornada.data_fim_da_jornada = date(2013, 11, 3)
            jornada.save()

            #
            # 40h
            #
            jornada = SetorJornadaHistorico()
            jornada.setor = setor
            jornada.jornada_trabalho = jornada_40h
            jornada.data_inicio_da_jornada = date(2013, 11, 4)
            jornada.data_fim_da_jornada = None
            jornada.save()
