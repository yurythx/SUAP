from unittest.mock import Mock

import ldap
import pytest

from ldap_backend.models import LdapConf


def test_sync_ou_sincroniza_pai_ausente_e_repete_movimento(monkeypatch: pytest.MonkeyPatch) -> None:
    ldap_conf = LdapConf()
    setor_superior = Mock()
    setor = Mock(superior=setor_superior)
    dn_atual = 'OU=COSEFIN-RE,OU=PROAD-RE,OU=RE,OU=IFRN,DC=ifrn,DC=local'
    novo_dn = 'OU=COSEFIN-RE,OU=DCF-RE,OU=PROAD-RE,OU=RE,OU=IFRN,DC=ifrn,DC=local'
    monkeypatch.setattr(
        ldap_conf,
        'get_ou_by_admin_description',
        Mock(return_value=[{'dn': dn_atual, 'description': [b'Coordenacao de Contabilidade e Financas']}]),
    )
    monkeypatch.setattr(ldap_conf, 'move_object', Mock(side_effect=ldap.NO_SUCH_OBJECT))
    monkeypatch.setattr(ldap_conf, 'sync_ou_setor', Mock())
    monkeypatch.setattr(ldap_conf, 'sync_ou', Mock())

    LdapConf.sync_ou(
        ldap_conf,
        novo_dn,
        'Coordenacao de Contabilidade e Financas',
        '123',
        setor,
        test_mode=False,
        force=True,
    )

    ldap_conf.sync_ou_setor.assert_called_once_with(setor_superior, test_mode=False, force=True)
    ldap_conf.sync_ou.assert_called_once_with(
        novo_dn,
        'Coordenacao de Contabilidade e Financas',
        '123',
        setor,
        test_mode=False,
        force=True,
    )
