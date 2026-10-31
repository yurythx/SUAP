"""Login com sincronia LDAP: a foto do servidor fica fora do request (#17597).

O ``authenticate`` sincroniza o usuário no AD a cada login. Ler a foto do storage nesse momento derrubava o worker quando o S3
ficava lento; agora o login sincroniza sem a foto e a sincronia agendada (``sync_user`` padrão) continua levando-a.
Só o servidor LDAP é simulado: os métodos de ``LdapConf`` que falam com ele.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from comum.models import Vinculo
from comum.utils import get_sigla_reitoria
from ldap_backend.ldap_backend import LdapBackend
from ldap_backend.models import LdapConf
from ldap_backend.utils import _storage_da_foto
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

FOTO = b'\xff\xd8 jpeg 75x100'


@pytest.fixture
def servidor_com_foto(sync_permissions, settings, tmp_path: Path):
    settings.MEDIA_ROOT = str(tmp_path)
    _storage_da_foto.cache_clear()
    # O DN do servidor parte da raiz SUAP (setor da reitoria).
    servidor = ServidorFactory(setor=SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria'))
    (tmp_path / 'fotos' / '75x100').mkdir(parents=True)
    (tmp_path / 'fotos' / '75x100' / f'{servidor.matricula}.jpg').write_bytes(FOTO)
    Vinculo.objects.filter(pk=servidor.get_vinculo().pk).update(foto=f'fotos/{servidor.matricula}.jpg')
    yield type(servidor).objects.get(pk=servidor.pk)
    _storage_da_foto.cache_clear()


@pytest.fixture
def ldap_conf(monkeypatch: pytest.MonkeyPatch) -> LdapConf:
    conf = LdapConf(filterstr_prefix='employeeNumber=', domain='ifrn.local')
    usuario_no_ad = {
        'dn': 'CN=outro',
        'userAccountControl': [b'512'],
        'pwdLastSet': [b'132000000000000000'],
        'lastLogon': [b'132000000000000000'],
        'whenCreated': [b'20200101000000.0Z'],
        'accountExpires': [b'0'],
        'memberOf': [],
    }
    for metodo, simulado in {
        'has_write_permission': Mock(return_value=True),
        'check_password': Mock(return_value=True),
        'get_user': Mock(return_value=usuario_no_ad),
        'move_object': Mock(),
        'sync_ou_setor': Mock(),
        'modify': Mock(),
    }.items():
        monkeypatch.setattr(conf, metodo, simulado)
    monkeypatch.setattr('ldap_backend.ldap_backend.get_ldap_conf', Mock(return_value=conf))
    return conf


def _fotos_escritas(conf: LdapConf) -> list[bytes]:
    return [attrs['thumbnailPhoto'] for _, attrs, *_ in (c.args for c in conf.modify.call_args_list) if 'thumbnailPhoto' in attrs]


def test_login_sincroniza_sem_ler_a_foto(servidor_com_foto, ldap_conf: LdapConf) -> None:
    user = LdapBackend().authenticate(SimpleNamespace(session={}), username=servidor_com_foto.matricula, password='senha')

    assert user == servidor_com_foto.get_user()
    assert ldap_conf.modify.called  # a sincronia do login aconteceu
    assert _fotos_escritas(ldap_conf) == []


def test_sincronia_agendada_continua_levando_a_foto(servidor_com_foto, ldap_conf: LdapConf) -> None:
    ldap_conf.sync_user(servidor_com_foto)

    assert _fotos_escritas(ldap_conf) == [FOTO]
