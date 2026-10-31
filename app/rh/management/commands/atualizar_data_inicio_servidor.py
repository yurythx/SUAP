from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from rh.models import Servidor

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Atualizar as datas de início de exercício de alguns servidores'

    matriculas_a_atualizar = ['1082207']  # chamado 50117 (Dalia Maria Bezerra Maia)

    def handle(self, *args, **options):
        for servidor in Servidor.objects.all():
            if servidor.matricula in self.matriculas_a_atualizar:
                print(('Atualizando...', servidor))

                Servidor.objects.filter(id=servidor.id).update(
                    data_inicio_servico_publico=servidor.calcula_inicio_no_servico_publico,
                    data_inicio_exercicio_na_instituicao=servidor.calcula_inicio_exercicio_na_instituicao,
                    data_posse_na_instituicao=servidor.calcula_posse_na_instituicao,
                    data_posse_no_cargo=servidor.calcula_posse_no_cargo,
                    data_inicio_exercicio_no_cargo=servidor.calcula_inicio_exercicio_no_cargo,
                    data_fim_servico_na_instituicao=servidor.calcula_fim_servico_na_instituicao,
                )
