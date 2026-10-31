from django.conf import settings
from django.db import transaction

from comum.models import Municipio
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if 'edu' not in settings.INSTALLED_APPS:
            self.stderr.write('Módulo do edu não está instalado. Finalizando.')
            return

        from edu.models import Cidade

        existentes = set(Municipio.objects.values_list('identificacao', flat=True))
        novos = {}
        for cidade in Cidade.objects.select_related('estado').iterator(chunk_size=2000):
            if not cidade.estado:
                continue
            uf = (cidade.estado.get_sigla() or '').strip()
            nome = (cidade.nome or '').strip()
            identificacao = Municipio.get_identificacao(nome, uf)[:255]
            if identificacao in existentes or identificacao in novos:
                continue
            novos[identificacao] = Municipio(identificacao=identificacao, uf=uf, nome=nome)

        if novos:
            Municipio.objects.bulk_create(list(novos.values()), ignore_conflicts=True, batch_size=2000)
        self.stdout.write(f'Municípios criados: {len(novos)}')
