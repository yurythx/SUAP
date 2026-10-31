from django.conf import settings
from requests import exceptions, packages
from sentry_sdk import capture_exception

from comum.models import Configuracao
from djtools.utils import requests


class API_PEN_Exception(Exception):
    pass


def create_password_context(password):
    # Subclass OpenSSL.SSL.Context to use a password callback that gives your password
    class PasswordContext(packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context):
        def __init__(self, method):
            super().__init__(method)

            def passwd_cb(maxlen, prompt_twice, userdata):
                return password.encode() if len(password) < maxlen else b''

            self.set_passwd_cb(passwd_cb)

    return PasswordContext


def get_config_api():
    url_ws = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='urlProducaoWS_pen')
    password = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='senhaWS_pen')
    cert = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='pathCertificadoPublico_pen')
    cert_priv = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='pathCertificadoPrivado_pen')
    certs = (cert, cert_priv)
    if url_ws and certs:
        if password:
            packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(password)
        try:
            resposta = requests.get(
                url=url_ws.split('/interoperabilidade')[0],
                verify=True,
                cert=certs,
                timeout=settings.REQUESTS_TIMEOUT,
            )
            if resposta.status_code == 200:
                return {'password': str(password), 'certs': certs}
        except exceptions.RequestException:
            return {}
        except Exception as e:
            capture_exception(e)
    return {}


def request_test_api(url):
    configuracao = get_config_api()
    try:
        if configuracao:
            packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(configuracao.get('password'))
            resposta = requests.get(
                url=url.split('/interoperabilidade')[0],
                verify=True,
                cert=configuracao.get('certs'),
                timeout=settings.REQUESTS_TIMEOUT,
            )
            if resposta.status_code:
                return {'status_code': resposta.status_code, 'mensagem': resposta.content}
        return {'mensagem': 'Erro na Configuração do TramitaGov, entre em contato com os administradores do sistema.'}
    except exceptions.RequestException:
        return {
            'mensagem': 'Ocorreu um erro na conexão com serviço do TramitaGov. Tente novamente mais tarde e caso o problema persista reporte um erro no SUAP.'
        }
    except Exception as e:
        capture_exception(e)
        raise e


def request_get(url, params=None):
    if params is None:
        params = {}
    configuracao = get_config_api()
    if configuracao:
        packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(configuracao.get('password'))
        try:
            resposta = requests.get(
                url=url,
                verify=True,
                cert=configuracao.get('certs'),
                params=params,
                timeout=settings.REQUESTS_TIMEOUT,
            )
            if resposta.content:
                return {'status_code': resposta.status_code, 'content': resposta.content, 'data': resposta.json()}
            elif resposta.status_code:
                return {'status_code': resposta.status_code}
        except Exception:
            return {'status_code': 500}
    return {}


def request_post(url, json_data):
    configuracao = get_config_api()
    if configuracao:
        packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(configuracao.get('password'))
        req = requests.post(
            url=url,
            verify=True,
            cert=configuracao.get('certs'),
            json=json_data,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if req.content:
            return {'status_code': req.status_code, 'content': req.content}
        elif req.status_code:
            return {'status_code': req.status_code}
    return {}


def request_put(url, json_data):
    configuracao = get_config_api()
    if configuracao:
        packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(configuracao.get('password'))
        params = {'hashDoComponenteDigital': json_data['hashDoComponenteDigital'], 'protocolo': json_data['protocolo']}
        resposta = requests.put(
            url=url,
            verify=True,
            cert=configuracao.get('certs'),
            params=params,
            files={'conteudo': json_data['conteudo']},
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if resposta.content:
            return {'status_code': resposta.status_code, 'content': resposta.content}
        elif resposta.status_code:
            return {'status_code': resposta.status_code}
    return {}


def request_delete(url, params=None):
    if params is None:
        params = {}
    configuracao = get_config_api()
    if configuracao:
        packages.urllib3.contrib.pyopenssl.OpenSSL.SSL.Context = create_password_context(configuracao.get('password'))
        resposta = requests.delete(
            url=url,
            verify=True,
            cert=configuracao.get('certs'),
            params=params,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if resposta.content:
            return {'status_code': resposta.status_code, 'content': resposta.content, 'data': resposta.json()}
        elif resposta.status_code:
            return {'status_code': resposta.status_code}
    return {}
