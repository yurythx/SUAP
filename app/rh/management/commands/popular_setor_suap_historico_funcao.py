from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from rh.models import Funcao, ServidorFuncaoHistorico, Setor

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Popular o setor SUAP no historico de Funções do Servidor a partir do historico de setor SUAP do Servidor.'

    def handle(self, *args, **options):
        contador = 0
        for historico_funcao in ServidorFuncaoHistorico.objects.all().filter(setor__isnull=False).exclude(funcao__codigo=Funcao.CODIGO_ESTAGIARIO):
            if not historico_funcao.setor_suap:
                servidor = historico_funcao.servidor
                setores = servidor.historico_setor_suap(historico_funcao.data_inicio_funcao, historico_funcao.data_fim_funcao)
                servidor.historico_setor_siape(historico_funcao.data_inicio_funcao, historico_funcao.data_fim_funcao)
                setor_suap = None
                if setores.exists():
                    setor_suap = setores.latest('data_inicio_no_setor').setor

                # verifica se no historico de funcao tem o setor siape dele
                if historico_funcao.setor and historico_funcao.setor.uo:
                    if setor_suap and setor_suap.uo == historico_funcao.setor.uo.equivalente:
                        historico_funcao.setor_suap = setor_suap
                        historico_funcao.save()
                        contador = +1

                    elif Setor.objects.suap().filter(sigla=historico_funcao.setor.sigla).exists():
                        historico_funcao.setor_suap = Setor.objects.suap().filter(sigla=historico_funcao.setor.sigla)[0]
                        historico_funcao.save()
                        contador = +1

        Log.objects.create(
            titulo='Popular Setor SUAP no histórico de função',
            texto=f'Foram feitas {contador} atualizações no histórico de funções dos servidores',
            app='rh',
        )
