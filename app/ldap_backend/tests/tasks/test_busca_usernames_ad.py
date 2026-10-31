import pytest

from comum.models import User
from ldap_backend.models import LdapConf
from ldap_backend.tasks import ATRIBUTOS_BUSCA_AD, buscar_usuarios, expirar_no_ad


@pytest.fixture
def ldap_conf(monkeypatch):
    """LdapConf que registra a busca no AD em `buscas` em vez de executá-la."""
    conf = LdapConf()
    conf.buscas = []

    def search_objects(**kwargs):
        conf.buscas.append(kwargs)
        return [{'cn': [b'1234567']}, {'cn': [b'7654321']}]

    monkeypatch.setattr(conf, 'search_objects', search_objects)
    return conf


def test_busca_um_unico_filtro_com_todos_os_atributos(ldap_conf):
    usernames = ldap_conf.get_usernames_from_attributes(ATRIBUTOS_BUSCA_AD, 'fulano@ifrn.edu.br')

    assert usernames == ['1234567', '7654321']
    assert ldap_conf.buscas[0]['attrlist'] == ['cn']
    assert ldap_conf.buscas[0]['filterstr'] == (
        '(|(sAMAccountName=fulano@ifrn.edu.br)'
        '(mail=fulano@ifrn.edu.br)'
        '(extensionAttribute8=fulano@ifrn.edu.br)'
        '(extensionAttribute9=fulano@ifrn.edu.br)'
        '(extensionAttribute4=fulano@ifrn.edu.br)'
        '(extensionAttribute5=fulano@ifrn.edu.br))'
    )


def test_valor_vazado_e_escapado(ldap_conf):
    ldap_conf.get_usernames_from_attributes(['mail'], 'fulano*)(objectClass=*')

    assert ldap_conf.buscas[0]['filterstr'] == r'(|(mail=fulano\2a\29\28objectClass=\2a))'


def test_atributo_unico_delega_para_a_busca_com_lista(ldap_conf):
    ldap_conf.get_usernames_from_attribute('sAMAccountName', '1234567')

    assert ldap_conf.buscas[0]['filterstr'] == '(|(sAMAccountName=1234567))'


@pytest.mark.django_db
def test_email_sem_usuario_no_suap_e_resolvido_pelo_ad(ldap_conf):
    user = User.objects.create_user('1234567', email='')

    users, somente_ad = buscar_usuarios('fulano@ifrn.edu.br', ldap_conf)

    assert list(users) == [user]
    assert somente_ad == ['7654321'], 'a matrícula sem usuário no SUAP tem que voltar à parte'
    assert ldap_conf.buscas, 'o AD deveria ter sido consultado'


@pytest.mark.django_db
def test_email_com_usuario_no_suap_nao_consulta_o_ad(ldap_conf):
    user = User.objects.create_user('7654321', email='fulano@ifrn.edu.br')

    users, somente_ad = buscar_usuarios('7654321', ldap_conf)

    assert list(users) == [user]
    assert somente_ad == []
    assert not ldap_conf.buscas


@pytest.mark.django_db
def test_sem_ldap_configurado_nao_quebra():
    users, somente_ad = buscar_usuarios('fulano@ifrn.edu.br', None)

    assert list(users) == []
    assert somente_ad == []


@pytest.mark.django_db
def test_conta_so_do_ad_tem_a_senha_expirada_e_entra_no_relatorio(ldap_conf):
    expiradas = []
    ldap_conf.force_user_reset_password = expiradas.append
    usuarios_expirados = []

    linhas = expirar_no_ad('fulano@ifrn.edu.br', ['1234567', '7654321'], ldap_conf, usuarios_expirados)

    assert expiradas == ['1234567', '7654321']
    assert usuarios_expirados == ['1234567', '7654321']
    assert linhas.count('<tr>') == 2
    assert 'fulano@ifrn.edu.br' in linhas
    assert '1234567 (somente no AD)' in linhas


@pytest.mark.django_db
def test_conta_do_ad_ja_expirada_nao_repete_no_relatorio(ldap_conf):
    ldap_conf.force_user_reset_password = lambda username: None

    linhas = expirar_no_ad('fulano@ifrn.edu.br', ['1234567'], ldap_conf, ['1234567'])

    assert linhas == ''
