import ldap

from .exceptions import LdapGroupDoesNotExist, LdapModificationFailed
from .models import LdapUser


def ldap_check_connection(ldap_connection):
    try:
        ldap_connection.simple_bind_s()
    except ldap.SERVER_DOWN:
        raise Exception('LDAP server is not reachable.')


def ldap_connect(server_uri, bind_dn, bind_password, unbind=False):
    try:
        ldap_obj = ldap.initialize(server_uri, bytes_mode=False)
        ldap_obj.set_option(ldap.OPT_NETWORK_TIMEOUT, 60.0)
        ldap_obj.set_option(ldap.OPT_TIMEOUT, 60.0)
        ldap_obj.simple_bind_s(bind_dn, bind_password)
        if unbind:
            ldap_obj.unbind_s()
        return ldap_obj
    except ldap.INVALID_CREDENTIALS:
        raise ValueError("The credentials aren't valid.")
    except ldap.SERVER_DOWN:
        raise Exception(f'LDAP server {server_uri} is not reachable.')
    except ldap.LDAPError:
        raise ValueError('The LDAP server is down or the SERVER_URI is invalid.')


def ldap_attempt_modification(ldap_connection, mod_type, target_type, target_identifier, group_dn):
    action_word = 'adding' if mod_type == ldap.MOD_ADD else 'removing'
    action_prep = 'to' if mod_type == ldap.MOD_DELETE else 'from'
    message_base = f"Error {action_word} {target_type} '{target_identifier}' {action_prep} group '{group_dn}':"
    try:
        modify_list = [
            (
                mod_type,
                target_type,
                [target_identifier.encode('utf-8')],
            )
        ]
        return ldap_connection.modify_s(group_dn, modify_list)
    except Exception as error_message:
        raise LdapModificationFailed(message_base + str(error_message))


def ldap_search_objects(ldap_connection, base_dn, scope=ldap.SCOPE_SUBTREE, filterstr=None, attrlist=None, page_size=500):
    entry_list = ldap_connection.search_ext_s(base=base_dn, filterstr=filterstr, attrlist=attrlist, scope=scope, timeout=-1, sizelimit=page_size)
    results = []
    for result in entry_list:
        dn, attrs = result
        if dn:
            attrs['dn'] = dn
            results.append(attrs)
    return results


###############################################################################################################
#                                         Group Information Methods                                           #
###############################################################################################################
def ldap_group_members(ldap_connection, group_dn, base_dn, scope=ldap.SCOPE_SUBTREE, page_size=500):
    """Searches for a group and retrieve its members.
    : param group_dn
    : param base_dn
    :param page_size (optional): Many servers have a limit on the number of results that can be returned.
                                 Paged searches circumvent that limit. Adjust the page_size to be below the
                                 server's size limit. (default: 500)
    :type page_size: int
    """
    attr_list = ['displayName', 'sAMAccountName', 'distinguishedName']
    GROUP_MEMBER_SEARCH = {
        'base': base_dn,
        'scope': scope,
        'filterstr': f'(&(objectCategory=user)(memberOf={group_dn}))',
        'attrlist': attr_list,
        'sizelimit': page_size,
    }
    entry_list = ldap_connection.search_ext_s(**GROUP_MEMBER_SEARCH)
    return entry_list


###############################################################################################################
#                                         Group Modification Methods                                          #
###############################################################################################################


def ldap_add_member(ldap_connection, group_dn, user_dn):
    return ldap_attempt_modification(ldap_connection, ldap.MOD_ADD, 'member', user_dn, group_dn)


def ldap_remove_member(ldap_connection, group_dn, user_dn):
    return ldap_attempt_modification(ldap_connection, ldap.MOD_DELETE, 'member', user_dn, group_dn)


###############################################################################################################
#                                         High-level Search Methods                                           #
###############################################################################################################
def ldap_group_by_name(ldap_connection, group_name, base_dn):
    results = ldap_search_objects(ldap_connection, base_dn, filterstr=f'(&(objectClass=group)(name={group_name}))')
    if not results:
        raise LdapGroupDoesNotExist(f'The {group_name} provided does not exist in the Active Directory.')
    #
    return results[0]


def ldap_members_group_by_name(ldap_connection, group_name, base_dn, scope=ldap.SCOPE_SUBTREE, page_size=500):
    ldap_group = ldap_group_by_name(ldap_connection, group_name, base_dn)
    return ldap_group_members(ldap_connection, ldap_group['dn'], base_dn, scope, page_size)


###############################################################################################################
#                                         High-level API                                                      #
###############################################################################################################


def adicionar_membro_ldap_group(ldap_group, sAMAccountName):
    ldap_user = LdapUser.objects.filter(sAMAccountName=sAMAccountName).first()
    if ldap_user:
        return ldap_group.add_member(ldap_user)
    return False


def adicionar_membros_ldap_group(ldap_group, membros):
    for membro in membros:
        adicionar_membro_ldap_group(ldap_group, membro)


def remover_membero_ldap_group(ldap_group, sAMAccountName):
    ldap_user = LdapUser.objects.filter(sAMAccountName=sAMAccountName).first()
    if ldap_user:
        return ldap_group.remover_member(ldap_user)
    return False
