import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.test import Client

from djtools.modulos_ocultos import edu_desativado, menu_visivel

print('edu_desativado', edu_desativado())
itens = [
    {'titulo': 'Ensino', 'url': '/edu/'},
    {'titulo': 'Pesquisa', 'url': '/pesquisa/'},
    {'titulo': 'Gestão de Pessoas', 'url': '/rh/'},
    {'titulo': 'Administração', 'url': '/compras/'},
]
visiveis = [item['titulo'] for item in menu_visivel(itens)]
print('menu', ','.join(visiveis))

cliente = Client()
for caminho in ('/accounts/login/', '/edu/', '/pesquisa/', '/ae/', '/admin/edu/aluno/', '/rh/', '/compras/'):
    resposta = cliente.get(caminho)
    print(caminho, resposta.status_code)
