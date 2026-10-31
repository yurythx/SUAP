import asyncio

from asgiref.sync import async_to_sync

from comum.models import APIExterna
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        async_to_sync(self.async_handle)(*args, **options)

    async def check_api(self, api):
        """Lógica individual para cada API"""
        # Executa a checagem em uma thread para não bloquear o loop de eventos
        acessivel = await asyncio.to_thread(api.estah_acessivel, verbosity=True)

        if not acessivel:
            api.ativo = False
            await asyncio.to_thread(api.save)
            self.stdout.write(f'API "{api.nome}" desabilitada por estar inacessível.')
        else:
            api.ativo = True
            await asyncio.to_thread(api.save)
            self.stdout.write(f'API "{api.nome}" está acessível.')

    async def async_handle(self, *args, **options):
        # 1. Busca todas as APIs (convertendo o QuerySet para uma lista)
        # Nota: APIExterna.objects.all() em Django moderno suporta a-iterable
        apis = []
        async for api in APIExterna.objects.all():
            apis.append(api)

        # 2. Cria uma lista de tarefas (tasks) para todas as APIs
        tasks = [self.check_api(api) for api in apis]

        # 3. Executa todas concorrentemente e espera o fim de todas
        if tasks:
            await asyncio.gather(*tasks)
