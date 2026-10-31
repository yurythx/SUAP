import tqdm
from djtools.management.commands import BaseCommandPlus
from erros.models import Erro


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        lote_erros = []
        lote_tamanho = 1000

        self.stdout.write('\nAtualizando o atributo "modulo_afetado" de todos os Erros\n')
        for erro in tqdm.tqdm(Erro.objects.all()):
            erro.set_modulo_afetado()
            lote_erros.append(erro)

            if len(lote_erros) == lote_tamanho:
                Erro.objects.bulk_update(lote_erros, ['modulo_afetado'])
                lote_erros.clear()

        if lote_erros:
            Erro.objects.bulk_update(lote_erros, ['modulo_afetado'])
            lote_erros.clear()
