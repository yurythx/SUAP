import urllib.parse

from django.conf import settings

from comum.models import Configuracao
from djtools.utils import requests, to_ascii


def get_dreamspark_url(mail, nome):
    base_url = Configuracao.get_valor_por_chave('microsoft', 'dreamspark_url')
    account = Configuracao.get_valor_por_chave('microsoft', 'dreamspark_account')
    key = Configuracao.get_valor_por_chave('microsoft', 'dreamspark_key')
    url_params = {
        'first_name': to_ascii(nome.split()[0]),
        'last_name': to_ascii(nome.split()[-1]),
        'academic_statuses': 'staff,students,faculty',
        'account': account,
        'key': key,
        'username': mail,
        'email': mail,
    }
    url = f'{base_url}?{urllib.parse.urlencode(url_params)}'
    return requests.get(url, timeout=settings.REQUESTS_TIMEOUT).text
