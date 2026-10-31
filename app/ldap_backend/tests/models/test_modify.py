from unittest.mock import Mock

import ldap
import pytest

from comum.tests.factories import UserFactory
from comum.models import User
from ldap_backend.models import LdapConf


EMAIL = 'fulano@academico.ifrn.edu.br'


def constraint_violation(atributo: str = 'userPrincipalName') -> ldap.CONSTRAINT_VIOLATION:
    return ldap.CONSTRAINT_VIOLATION({'info': f'CONSTRAINT_ATT_TYPE ({atributo})'})


@pytest.fixture
def ldap_conf(monkeypatch: pytest.MonkeyPatch) -> tuple[LdapConf, Mock]:
    conf = LdapConf()
    conexao = Mock()
    monkeypatch.setattr(conf, 'get_user', Mock(return_value={'dn': 'CN=atual'}))
    monkeypatch.setattr(conf, 'bind', Mock(return_value=conexao))
    monkeypatch.setattr(conf, 'get_usernames_from_principalname', Mock(return_value=['outro']))
    monkeypatch.setattr(conf, '_atualizar_user_principal_name', Mock())
    return conf, conexao


@pytest.mark.parametrize('user_principal_name', [EMAIL, [EMAIL]])
def test_modify_atualiza_dono_do_upn_e_repete_alteracao(ldap_conf: tuple[LdapConf, Mock], user_principal_name: str | list[str]) -> None:
    conf, conexao = ldap_conf
    conexao.modify_s.side_effect = [constraint_violation(), None]

    assert conf.modify('atual', {'userPrincipalName': user_principal_name}) == 1

    conf.get_usernames_from_principalname.assert_called_once_with(EMAIL)
    conf._atualizar_user_principal_name.assert_called_once_with('outro', EMAIL)
    assert conexao.modify_s.call_count == 2


@pytest.mark.parametrize(
    ('attrs', 'atributo_erro'),
    [({'displayName': 'Nome'}, 'userPrincipalName'), ({'userPrincipalName': EMAIL}, 'displayName')],
)
def test_modify_preserva_constraint_nao_relacionada_ao_upn(ldap_conf: tuple[LdapConf, Mock], attrs: dict[str, str], atributo_erro: str) -> None:
    conf, conexao = ldap_conf
    error = constraint_violation(atributo_erro)
    conexao.modify_s.side_effect = error

    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as raised:
        conf.modify('atual', attrs)

    assert raised.value is error
    conf._atualizar_user_principal_name.assert_not_called()


def test_modify_preserva_constraint_se_atualizacao_do_dono_falhar(ldap_conf: tuple[LdapConf, Mock]) -> None:
    conf, conexao = ldap_conf
    error = constraint_violation()
    conexao.modify_s.side_effect = error
    conf._atualizar_user_principal_name.side_effect = Exception('Usuário não encontrado no SUAP')

    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as raised:
        conf.modify('atual', {'userPrincipalName': EMAIL})

    assert raised.value is error


def test_atualizar_user_principal_name_usa_valor_atual_do_suap(ldap_conf: tuple[LdapConf, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
    conf, _ = ldap_conf
    usuario = Mock()
    relacionamento = usuario.get_relacionamento.return_value
    get_obj_attrs = Mock(return_value={'userPrincipalName': 'outro@ifrn.edu.br'})
    monkeypatch.setattr('ldap_backend.models.User.objects.get', Mock(return_value=usuario))
    monkeypatch.setattr('ldap_backend.models.get_obj_attrs', get_obj_attrs)
    monkeypatch.setattr(conf, 'modify', Mock())

    LdapConf._atualizar_user_principal_name(conf, 'outro', EMAIL)

    usuario.reset_vinculo.assert_called_once_with()
    usuario.reset_profile.assert_called_once_with()
    usuario.get_relacionamento.assert_called_once_with()
    get_obj_attrs.assert_called_once_with(model_obj=relacionamento, ldap_conf=conf, com_foto=False)
    conf.modify.assert_called_once_with('outro', {'userPrincipalName': 'outro@ifrn.edu.br'})


def test_atualizar_user_principal_name_impede_recursao_para_o_mesmo_valor(ldap_conf: tuple[LdapConf, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
    conf, _ = ldap_conf
    usuario = Mock()
    monkeypatch.setattr('ldap_backend.models.User.objects.get', Mock(return_value=usuario))
    monkeypatch.setattr('ldap_backend.models.get_obj_attrs', Mock(return_value={'userPrincipalName': EMAIL.upper()}))
    monkeypatch.setattr(conf, 'modify', Mock())

    with pytest.raises(ValueError, match='Não foi possível liberar'):
        LdapConf._atualizar_user_principal_name(conf, 'outro', EMAIL)

    conf.modify.assert_not_called()


def test_modify_rejeita_user_principal_name_vazio(ldap_conf: tuple[LdapConf, Mock]) -> None:
    conf, conexao = ldap_conf

    with pytest.raises(ValueError, match='is empty string'):
        conf.modify('atual', {'userPrincipalName': ''})

    conexao.modify_s.assert_not_called()


def test_sync_user_inativo_atualiza_user_principal_name(ldap_conf: tuple[LdapConf, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
    conf, _ = ldap_conf
    conf.get_user.return_value = {'dn': 'CN=outro', 'userAccountControl': [b'514']}
    monkeypatch.setattr(conf, 'modify', Mock())
    monkeypatch.setattr('ldap_backend.models.Configuracao.get_valor_por_chave', Mock(return_value=None))
    monkeypatch.setattr('ldap_backend.models.get_senha_inicial', Mock(return_value='senha'))
    monkeypatch.setattr(
        'ldap_backend.models.get_obj_attrs',
        Mock(
            return_value={
                'dn': 'CN=outro',
                'setor': None,
                'memberOf': [],
                'thumbnailPhoto': None,
                'active': False,
                'objectClass': ['user'],
                'cn': 'outro',
                'accountExpires': '0',
                'userPrincipalName': EMAIL,
            }
        ),
    )

    LdapConf.sync_user(conf, Mock(username='outro'))

    conf.modify.assert_called_once_with('outro', {'userPrincipalName': EMAIL})


NOTA_UPN_NAO_LIBERADO = f'userPrincipalName {EMAIL} de "atual" em uso por "outro", que não foi liberado.'


@pytest.fixture
def ldap_conf_resolver_real(monkeypatch: pytest.MonkeyPatch) -> tuple[LdapConf, Mock]:
    """Como ``ldap_conf``, mas executando o ``_atualizar_user_principal_name`` de verdade."""
    conf = LdapConf(domain='ifrn.local')
    conexao = Mock()
    monkeypatch.setattr(conf, 'get_user', Mock(return_value={'dn': 'CN=atual'}))
    monkeypatch.setattr(conf, 'bind', Mock(return_value=conexao))
    monkeypatch.setattr(conf, 'get_usernames_from_principalname', Mock(return_value=['outro']))
    return conf, conexao


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('com_user_sem_vinculo', 'causa'),
    [(False, User.DoesNotExist), (True, KeyError)],
    ids=['inexistente_no_suap', 'sem_vinculo_no_suap'],
)
def test_modify_nao_libera_upn_de_conta_sem_upn_no_suap(
    ldap_conf_resolver_real: tuple[LdapConf, Mock], com_user_sem_vinculo: bool, causa: type[Exception]
) -> None:
    conf, conexao = ldap_conf_resolver_real
    if com_user_sem_vinculo:
        UserFactory(username='outro')
    error = constraint_violation()
    conexao.modify_s.side_effect = error

    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as raised:
        conf.modify('atual', {'userPrincipalName': EMAIL})

    assert raised.value is error
    assert isinstance(raised.value.__cause__, causa)
    assert raised.value.__notes__ == [NOTA_UPN_NAO_LIBERADO]
    assert conexao.modify_s.call_count == 1  # o UPN do outro não foi alterado


def test_modify_registra_contexto_quando_nao_libera_o_upn(ldap_conf: tuple[LdapConf, Mock]) -> None:
    conf, conexao = ldap_conf
    error = constraint_violation()
    falha_ao_liberar = ldap.UNWILLING_TO_PERFORM({'info': 'acesso negado'})
    conexao.modify_s.side_effect = error
    conf._atualizar_user_principal_name.side_effect = falha_ao_liberar

    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as raised:
        conf.modify('atual', {'userPrincipalName': EMAIL})

    assert raised.value is error
    assert raised.value.__cause__ is falha_ao_liberar
    assert raised.value.__notes__ == [NOTA_UPN_NAO_LIBERADO]
