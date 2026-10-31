import random
import re
import string

from bs4 import BeautifulSoup

from comum.models import Configuracao
from djtools.utils import requests


def id_generator(size=6, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def clear_cpf(cpf):
    return re.sub(r'\D', '', str(cpf))


def gerar_chave_rucks(identificador):
    # 05156.abcd (5 primeiros dígitos do CPF/RG/CNPJ + ponto + 4 caracteres aleatórios)
    key_part1 = clear_cpf(identificador)[:5]
    key_part2 = id_generator(4)
    return f'{key_part1}.{key_part2}'


def get_chave_wifi(identificador):
    solucao_wifi = Configuracao.get_valor_por_chave('integracao_wifi', 'solucao_wifi')
    if solucao_wifi == 'ruckus':
        return gerar_chave_rucks(identificador)
    return 'ERRO AO GERAR CHAVE'


def get_chaves_wifi_ruckus(lista_descricao_acesso, email, validade=1, url_wifi='', limite_compartilhamento_wifi=1):
    tokens = []
    # browser

    # User-Agent (this is cheating, ok?)
    session = requests.Session()
    headers = {'User-agent': 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1'}

    ###################################
    # Abrir tela via mechanize do Ruckus
    ###################################
    url_wifi = url_wifi or Configuracao.get_valor_por_chave('integracao_wifi', 'url_wifi')

    data = {
        'username': Configuracao.get_valor_por_chave('integracao_wifi', 'usuario_wifi'),
        'password': Configuracao.get_valor_por_chave('integracao_wifi', 'senha_wifi'),
        'email': '',
        'user': '',
        'ssid': '',
        'ok': 'Log In',
    }
    try:
        session.get(url_wifi, headers=headers, verify=False)
        response = session.post(url_wifi, headers=headers, data=data, verify=False)
    except Exception:
        return [(lista_descricao_acesso[0], 'ERRO AO GERAR CHAVE. SERVIÇO INDISPONÍVEL.')]
    url_principal = response.url
    for descricao_acesso in lista_descricao_acesso:
        try:
            response = session.get(url_principal)
            html = response.content.decode('utf-8')
            soup = BeautifulSoup(html)
            key = soup.find(id='key').attrs['value']
            data = {
                'fullname': descricao_acesso,
                'duration': str(validade),
                'email': email or '',
                'limitnumber': str(limite_compartilhamento_wifi) or '1',
                'gentype': 'single',
                'duration-unit': 'day_Days',
                'guest-wlan': 'wIFRN-Visitantes',
                'countrycode': '+1',
                'phonenumber': '4081234567',
                'key': key,
                'remarks': '',
                'number': '5',
                'createToNum': '',
                'batchpass': '',
                'reauth': 'off',
                'reauth-time': '',
                'reauth-unit': 'min',
            }
            response = session.post(url_principal, data=data, headers=headers, verify=False)
            data = {'task': 'user-guesspass', 'next': 'Next >'}
            tokens.append((descricao_acesso, key))
            response = session.post(response.url, data=data, headers=headers, verify=False)
        except Exception:
            tokens.append((descricao_acesso, 'ERRO AO GERAR CHAVE'))

    return tokens
