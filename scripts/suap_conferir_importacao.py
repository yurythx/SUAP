import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.contrib.auth.models import Group

from comum.models import Configuracao
from rh.models import Servidor, Setor

print('setores', Setor.objects.count())
print('servidores', Servidor.objects.filter(ativo=True).count())
print('sigla', Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'))
print('reitoria', Configuracao.get_valor_por_chave('comum', 'reitoria_sigla'))
for nome in ('Servidor', 'Básico', 'Colaborador (Básico sem Assinatura)'):
    grupo = Group.objects.filter(name=nome).first()
    print(nome, grupo.user_set.count() if grupo else 0)
