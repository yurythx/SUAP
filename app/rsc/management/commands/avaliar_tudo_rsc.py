from djtools.management.commands import BaseCommandPlus
from rsc.models import Avaliacao


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('processo_id', type=int, help='ID do processo')
        parser.add_argument('avaliador_id', type=int, help='ID do avaliador')

    def handle(self, *args, **options):
        processo_id = options['processo_id']
        avaliador_id = options['avaliador_id']

        # selecionado a avaliação
        avaliacao = Avaliacao.objects.filter(processo__id=processo_id, avaliador__id=avaliador_id)
        if avaliacao.exists():
            avaliacao = avaliacao[0]
            print(f'Avaliação selecionada: {avaliacao}')
            for item in avaliacao.avaliacaoitem_set.all():
                item.data_referencia = item.arquivo.data_referencia
                item.qtd_itens_validado = item.arquivo.qtd_itens
                item.save()
