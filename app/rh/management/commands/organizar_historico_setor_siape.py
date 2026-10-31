from datetime import timedelta

from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from djtools.utils import date2datetime
from rh.models import Servidor, ServidorSetorLotacaoHistorico

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Organizar Historico de Setores'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument('--reset', action='store_true', help='Reseta data fim dos historico dos setores lotacao do servidor', default=False)

    def handle(self, *args, **options):
        for servidor in Servidor.objects.ativos().filter():
            if servidor.setor_lotacao_data_ocupacao and servidor.setor_exercicio and servidor.setor_lotacao:
                kwargs = {'data_inicio_setor_lotacao': servidor.setor_lotacao_data_ocupacao, 'servidor': servidor}
                historico_setor_lotacao = ServidorSetorLotacaoHistorico.objects.filter(**kwargs)
                kwargs['setor_lotacao'] = servidor.setor_lotacao
                kwargs['setor_exercicio'] = servidor.setor_exercicio
                kwargs['hora_atualizacao_siape'] = date2datetime(servidor.setor_lotacao_data_ocupacao)
                if historico_setor_lotacao.exists():
                    historico_setor_lotacao.update(**kwargs)
                else:
                    ServidorSetorLotacaoHistorico.objects.create(**kwargs)

        servidor_setor_lotacao_historico = ServidorSetorLotacaoHistorico.objects.filter(data_fim_setor_lotacao__isnull=True)
        if options.get('reset'):
            servidor_setor_lotacao_historico = ServidorSetorLotacaoHistorico.objects.all()
            servidor_setor_lotacao_historico.update(data_fim_setor_lotacao=None)

        for id_servidor in servidor_setor_lotacao_historico.values_list('servidor', flat=True).distinct():
            servidor = Servidor.objects.get(id=id_servidor)
            historico_servidor_setor = servidor.servidorsetorlotacaohistorico_set.all().order_by('data_inicio_setor_lotacao')

            data_referencia_lotacao_atual_ou_aposentadoria = servidor.setor_lotacao_data_ocupacao
            historico_anterior = None
            eh_aposentado = False
            eh_excluido = False

            if servidor.eh_aposentado:
                eh_aposentado = True
                data_referencia_lotacao_atual_ou_aposentadoria = servidor.data_aposentadoria
            elif servidor.data_fim_servico_na_instituicao:
                eh_excluido = True
                data_referencia_lotacao_atual_ou_aposentadoria = servidor.data_fim_servico_na_instituicao

            ultimo_elemento = historico_servidor_setor.count()
            contador = 1
            for historico_setor in historico_servidor_setor:
                if contador == 1 and contador == ultimo_elemento:
                    if (eh_aposentado or eh_excluido) and data_referencia_lotacao_atual_ou_aposentadoria:
                        historico_setor.data_fim_setor_lotacao = data_referencia_lotacao_atual_ou_aposentadoria - timedelta(1)
                    else:
                        historico_setor.data_fim_setor_lotacao = None
                    historico_setor.save()
                elif contador == 1:
                    historico_anterior = historico_setor
                elif contador == ultimo_elemento:
                    historico_anterior.data_fim_setor_lotacao = historico_setor.data_inicio_setor_lotacao - timedelta(1)
                    historico_anterior.save()
                    if (eh_aposentado or eh_excluido) and data_referencia_lotacao_atual_ou_aposentadoria:
                        historico_setor.data_fim_setor_lotacao = data_referencia_lotacao_atual_ou_aposentadoria - timedelta(1)
                    else:
                        historico_setor.data_fim_setor_lotacao = None
                    historico_setor.save()
                else:
                    historico_anterior.data_fim_setor_lotacao = historico_setor.data_inicio_setor_lotacao - timedelta(1)
                    historico_anterior.save()
                    historico_anterior = historico_setor
                contador += 1
