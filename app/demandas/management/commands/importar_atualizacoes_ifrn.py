from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import Group

from demandas.models import Atualizacao, Tag
from djtools.management.commands import BaseCommandPlus
from djtools.utils import requests


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        count = Atualizacao.objects.count()
        url = f'https://suap.ifrn.edu.br/api/ti/atualizacoes-suap/?limit=&offset={count}'
        response = requests.get(url, timeout=settings.REQUESTS_TIMEOUT)
        data = response.json()
        for atualizacao in data['results']:
            self.stdout.write(str(atualizacao))
            tipo = atualizacao['tipo']
            tags = atualizacao['tags']
            grupos = atualizacao['grupos']
            data = atualizacao['data']
            descricao = atualizacao['descricao']
            pk = atualizacao['id']
            if not Atualizacao.objects.filter(pk=pk).exists():
                obj = Atualizacao()
                obj.pk = pk
                obj.tipo = tipo
                obj.descricao = descricao
                obj.data = datetime.strptime(data, '%Y-%m-%d')
                obj.save()
                for nome in grupos:
                    grupo = Group.objects.get_or_create(name=nome)[0]
                    obj.grupos.add(grupo)
                for nome in tags:
                    tag = Tag.objects.filter(nome=nome).first()
                    if not tag:
                        tag = Tag.objects.create(nome=nome)
                        obj.tags.add(tag)
