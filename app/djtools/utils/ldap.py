from django.conf import settings

from .python import silenciar


@silenciar(return_on_error=False)
def is_ldap_enabled():
    """
    Verifica se o backend LDAP está ativo.
    """
    from comum.models import Configuracao

    utiliza_autenticacao_ldap = Configuracao.get_valor_por_chave('ldap_backend', 'utilizar_autenticacao_via_ldap')
    return 'ldap_backend' in settings.INSTALLED_APPS and utiliza_autenticacao_ldap and settings.SUAP_ENVIRONMENT != 'dev'


@silenciar()
def get_ldap_conf():
    """
    Obtém a configuração ativa do LDAP.
    """
    if is_ldap_enabled():
        from ldap_backend.models import LdapConf

        return LdapConf.get_active()


@silenciar(return_on_error=False)
def is_ldap_write_enabled():
    """
    Verifica se a configuração LDAP permite escrita.
    """
    ldap_conf = get_ldap_conf()
    return ldap_conf and ldap_conf.has_write_permission()


@silenciar()
def sync_ldap_user(matricula):
    """
    Sincroniza um usuário com o LDAP, se o backend LDAP estiver ativo.
    """
    conf = get_ldap_conf()
    if conf and conf.has_write_permission():
        conf.sync_user(matricula)


@silenciar()
def sync_ldap_user_emails(user, emails):
    """
    Sincroniza os emails de um usuário com o LDAP, se o backend LDAP estiver ativo.
    """
    conf = get_ldap_conf()
    if conf and conf.has_write_permission():
        conf.sync_user_emails(user, emails)


@silenciar()
def sync_ldap_setor(setor):
    """
    Sincroniza um setor com o LDAP, se o backend LDAP estiver ativo.
    """
    conf = get_ldap_conf()
    if conf and conf.has_write_permission():
        conf.sync_ou_setor(setor, test_mode=False, force=True)
