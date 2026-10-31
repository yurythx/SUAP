from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.backends import ModelBackend
from sentry_sdk import capture_exception

from comum.exceptions import LoginException
from comum.models import User
from djtools.utils import get_ldap_conf
from ldap_backend.utils import ad_to_datetime

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ldap_backend.models import LdapConf


def escape_query(query):
    """Escapes certain filter characters from an LDAP query."""
    return query.replace('\\', r'\5C').replace('*', r'\2A').replace('(', r'\28').replace(')', r'\29')


def _senha_confere(ldap_conf: LdapConf, request: HttpRequest | None, username: str, password: str | None) -> bool:
    eh_usuario_autenticado_govbr = request.session.get('autenticou_com_govbr', False) if request else False
    if not User.objects.filter(username__iexact=username).exists():
        return False
    if eh_usuario_autenticado_govbr:
        raise LoginException(
            'Erro ao tentar autenticar utilizando LDAP. Verifique com o administrador do sistema.',
        )
    authorized = ldap_conf.check_password(username, password)
    return bool(password and authorized)


def _sincronizar_usuario(ldap_conf: LdapConf, username: str) -> None:
    if not ldap_conf.has_write_permission():
        return
    try:
        # Sem a foto: lê-la do storage dentro do login derrubava o worker quando o S3 ficava lento (#17597).
        ldap_conf.sync_user(username, com_foto=False)
    except Exception as e:  # usuário não deve ser impedido de logar por falha de sincronização, mas o erro deve ser registrado.
        if settings.DEBUG:
            raise
        capture_exception(e)


def _guardar_expiracao_na_sessao(request: HttpRequest | None, username: str, dn: dict) -> None:
    account_expires = dn.get('accountExpires', [None])[0]
    if account_expires is None or account_expires in [b'0', b'9223372036854775807']:
        return
    account_expires = ad_to_datetime(int(account_expires.decode()))
    try:
        request.session[f'adAccountExpires_{username}'] = account_expires.isoformat()
        request.session.save()
    except Exception:
        pass


def _senha_definida_pelo_usuario(request: HttpRequest | None, username: str, dn: dict) -> bool:
    """Falso se a senha nunca foi definida (``pwdLastSet`` 0) ou se ainda é a da criação da conta (conta vencida)."""
    try:
        pwd_last_set = dn['pwdLastSet'][0].decode()
        when_created = dn['whenCreated'][0].decode()
        if pwd_last_set == '0':
            return False
        datetime_pwd_last_set = ad_to_datetime(int(pwd_last_set))
        datetime_when_created = datetime.datetime.strptime(when_created[:14], '%Y%m%d%H%M%S')
        if (datetime_pwd_last_set - datetime_when_created).total_seconds() < 120:
            messages.error(
                request,
                f'Sua conta "{username}" está vencida. Por favor, clique em "Esqueceu ou deseja alterar sua senha?" ou entre em contato com o suporte de TI do seu campus.',
            )
            return False
    except Exception:
        return False
    return True


class LdapBackend(ModelBackend):
    supports_object_permissions = False
    supports_anonymous_user = False
    supports_inactive_user = False

    def authenticate(self, request: HttpRequest | None, username: str | None = None, password: str | None = None, **kwargs: Any) -> User | None:
        ldap_conf = get_ldap_conf()
        if not ldap_conf or not username:
            return None
        username = str(username).upper()
        if not _senha_confere(ldap_conf, request, username, password):
            return None
        _sincronizar_usuario(ldap_conf, username)

        # Adicionar checagem para ver se o usuario no AD está com a expiração prevista
        # Adicionar checagem para ver se o usuario no AD está desativado = 514
        dn = ldap_conf.get_user(username, attrs=['userAccountControl', 'pwdLastSet', 'whenCreated', 'accountExpires'])
        if dn and dn.get('userAccountControl', [None])[0] == b'514':
            return None
        _guardar_expiracao_na_sessao(request, username, dn)

        if settings.DEBUG:
            return User.objects.filter(username=username).first()
        if not _senha_definida_pelo_usuario(request, username, dn):
            return None
        return User.objects.filter(username=username, vinculo__pessoa__isnull=False).first()

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
