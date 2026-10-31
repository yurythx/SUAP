import itertools
import logging
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import ldap
import ldap.modlist as modlist
import ldapdb
import ldapdb.models.fields as ldapFields
from ldap.filter import escape_filter_chars

#
from django.conf import settings
from sentry_sdk import capture_exception

from comum.exceptions import LoginException, UserMustResetPassword
from comum.models import Configuracao, User
from comum.utils import remote_logout_user
from djtools.db import models
from djtools.utils import send_mail, send_notification

#
from rh.models import Setor, UnidadeOrganizacional

from .manager import LdapUserManager

#
from .utils import ad_to_datetime, datetime_to_ad, get_obj_attrs, get_senha_inicial, get_setor_dn, print_

#
USER_ACCOUNT_CONTROL_ACTIVE = '512'
USER_ACCOUNT_CONTROL_INACTIVE = '514'

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)

logger = logging.getLogger(__name__)


def _relacionamento(obj: Any) -> Any:
    """Servidor/Aluno/Prestador do ``obj``; quando ``obj`` é um username, busca o relacionamento do usuário."""
    if not isinstance(obj, str):
        return obj
    try:
        user = User.objects.get(username__iexact=obj)
        user.reset_vinculo()
        user.reset_profile()
        return user.get_relacionamento()
    except User.DoesNotExist:
        raise Exception(f'Nenhum usuário com username {obj}')


def _encerrar_pedido_de_troca_de_senha(obj: Any, pwd_last_set: str) -> None:
    """Se o usuário alterou a senha no LDAP depois que o SUAP solicitou a troca, remove a solicitação no SUAP."""
    user = obj.get_user()
    if not user or not user.forcar_troca_senha:
        return
    data = user.data_solicitacao_forcar_troca_senha or datetime.today()
    data_hora = datetime(data.year, data.month, data.day)
    data_solicitacao_forcar_troca_senha = datetime_to_ad(data_hora)
    if pwd_last_set and data_solicitacao_forcar_troca_senha < int(pwd_last_set):
        User.objects.filter(pk=user.pk).update(data_solicitacao_forcar_troca_senha=None, forcar_troca_senha=False)


def _atributos_em_bytes(obj_attrs: dict) -> dict[str, bytes | list[bytes]]:
    """Valores texto (e listas de texto) codificados em UTF-8, como o ``addModlist`` exige; os demais ficam de fora."""
    dict_bin = {}
    for key, value in list(obj_attrs.items()):
        if isinstance(value, str):
            dict_bin[key] = value.encode('utf8')
        if isinstance(value, list):
            dict_bin[key] = [item.encode('utf8') for item in value]
    return dict_bin


def props(obj):
    return {key: value for key, value in obj.__dict__.items() if not callable(value) and not key.startswith('_')}


class LdapConf(models.ModelPlus):
    SOLUCAO_ACTIVE_DIRECTORY = 'active_directory'
    SOLUCAO_OPEN_LDAP = 'open_ldap'
    SOLUCAO_CHOICES = ((SOLUCAO_ACTIVE_DIRECTORY, 'Active Directory'), (SOLUCAO_OPEN_LDAP, 'OpenLDAP'))

    solucao = models.CharField('Solução de autenticação', max_length=20, choices=SOLUCAO_CHOICES)
    uri = models.CharFieldPlus('URI', help_text='Ex.: "ldap://ldap.ifrn.local:389".', unique=True)
    uri_change_password = models.CharFieldPlus('URI troca de senha', help_text='Ex.: "ldaps://ldap.ifrn.local".', default='', unique=True)
    who = models.CharFieldPlus('Usuário (DN)', help_text='Ex.: "cn=admin,dc=ifrn,dc=edu,dc=br".', width=600)
    cred = models.CharFieldPlus('Senha', null=True, blank=True)
    base = models.CharFieldPlus('Base DN', help_text='Ex.: "OU=IFRN,DC=ifrn,DC=local".', width=600)
    filterstr_prefix = models.CharFieldPlus('Filtro de autenticação', default='sAMAccountName=', help_text='Ex.: "sAMAccountName=", "uid=".')
    domain = models.CharFieldPlus('Domínio', help_text='Ex.: "ifrn.local".')
    email_admin = models.EmailField(default='digti@ifrn.edu.br', help_text='Email da coordenação de TI')
    priority = models.IntegerField('Prioridade', default=1000)
    active = models.BooleanField('Serviço ativo', default=True)
    resolve_referral = models.BooleanField('LDAP should resolve referrals', default=True)
    use_extension_attributes = models.BooleanField('Utilizar extensionAttributes do AD?', default=True)

    class Meta:
        permissions = (
            ('change_ldap_user_password_subtree', 'Pode modificar a senha de usuários da sub-árvore'),
            ('change_ldap_user_password_all', 'Pode modificar a senha de todos os usuários'),
            ('change_ldap_user_password_aluno', 'Pode modificar a senha de alunos'),
            ('sync_ldap_user', 'Pode sincronizar usuários'),
            ('view_ldap_user', 'Pode ver usuários'),
            ('pode_acessar_google_classroom', 'Pode acessar o Google Classrooom'),
        )
        verbose_name = 'Configuração do Serviço de Diretório'
        verbose_name_plural = 'Configurações dos Serviços de Diretório'

    def __str__(self):
        return self.uri

    @property
    def filterstr(self):
        return [x.replace('=', '') for x in self.filterstr_prefix.split(',')]

    @classmethod
    def peek(cls):
        try:
            return cls.objects.filter(active=True).order_by('priority').first()
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_active_settings(cls):
        obj = cls.peek()
        return props(obj or LdapConf())

    @classmethod
    def get_active(cls):
        for obj in cls.objects.filter(active=True).order_by('priority'):
            if obj.has_connectivity():
                return obj

    def has_connectivity(self):
        try:
            self.bind()
            return True
        except LoginException:
            return False
        except ValueError:
            return False

    def get_latency(self):
        """
        Measures latency (in milliseconds) to an LDAP server using python-ldap.
        :return: Latency in milliseconds or error message
        """
        try:
            start = time.time()
            conn = ldap.initialize(self.uri, bytes_mode=False)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
            conn.simple_bind_s(self.who, self.cred)
            conn.search_s(self.base, ldap.SCOPE_BASE, attrlist=['dn'])
            conn.unbind_s()
            end = time.time()
            latency_ms = (end - start) * 1000
            return round(latency_ms, 2)
        except (ldap.LDAPError, Exception) as e:
            capture_exception(e)
            return -1

    def bind(self, who=None, password=None, unbind=False):
        if who is None and password is None:
            who, password = self.who, self.cred
        ldap_obj = ldap.initialize(self.uri, bytes_mode=False)
        ldap_obj.set_option(ldap.OPT_NETWORK_TIMEOUT, 60.0)
        ldap_obj.set_option(ldap.OPT_TIMEOUT, 60.0)
        if not self.resolve_referral:
            ldap_obj.set_option(ldap.OPT_REFERRALS, 0)

        retries = int(Configuracao.get_valor_por_chave('ldap_backend', 'tentativas_maximas_bind') or 1)
        last_exception = Exception('Erro ao conectar no LDAP')
        for attempts in range(1, retries + 1):
            try:
                ldap_obj.simple_bind_s(who, password)
                if unbind:
                    ldap_obj.unbind_s()
                return ldap_obj
            except ldap.INVALID_CREDENTIALS as e:
                """
                    773 é o codigo que informa que o usuário precisa alterar a senha no próximo login
                    Por algum motivo essa informação não vem de forma estruturada na exception
                """
                if 'data 773' in str(e):
                    raise UserMustResetPassword('Altere a senha do usuário antes de tentar efetuar a autenticação.')
                raise ValueError(f'Credenciais invalidas para {who}')
            except ldap.LDAPError as e:
                last_exception = e
                if attempts < retries:
                    time.sleep(2 * attempts)
        capture_exception(last_exception)
        raise LoginException(str(last_exception))

    def check_password(self, username, password):
        try:
            if self.solucao == self.SOLUCAO_ACTIVE_DIRECTORY:
                who = username + '@' + self.domain
            else:
                who = self.filterstr_prefix + username + ',' + self.base
            self.bind(who, password, unbind=True)
            return True
        except (LoginException, UserMustResetPassword) as e:
            raise e
        except ValueError:
            return False

    @property
    def default_search_fields(self):
        default_search_fields = ['sAMAccountName', 'givenName', 'sn', 'mail']
        for filter in self.filterstr:
            if filter not in default_search_fields:
                default_search_fields.append(filter)
        return default_search_fields

    def mount_filter_by_query(self, q, search_fields=None):
        search_fields = search_fields or self.default_search_fields
        filterstr = '(|'
        for f in search_fields:
            filterstr += f'({f}=*{q}*)'
        filterstr += ')'

        return filterstr

    def mount_filterstr(self, username):
        default_search_fields = ['sAMAccountName', *self.filterstr]
        filterstr = '(|'
        for f in default_search_fields:
            filterstr += f'({f}={username})'
        filterstr += ')'
        return filterstr

    def get_usernames_from_attributes(self, attributes: Sequence[str], value: str) -> list[str]:
        """Busca usernames (``cn``) cujo ``value`` case com qualquer um dos ``attributes``.

        Exemplo: get_usernames_from_attributes(['sAMAccountName', 'mail'], 'johndoe')
        """
        valor = escape_filter_chars(value)
        filterstr = '(|{})'.format(''.join(f'({attribute}={valor})' for attribute in attributes))
        return list(itertools.chain(*[[cn.decode() for cn in row['cn']] for row in self.search_objects(filterstr=filterstr, attrlist=['cn'])]))

    def get_usernames_from_attribute(self, attribute: str, value: str) -> list[str]:
        """
        Busca usernames a partir de um atributo e seu valor.
        Exemplo: get_usernames_from_attribute('sAMAccountName', 'johndoe')
        """
        return self.get_usernames_from_attributes([attribute], value)

    def get_usernames_from_principalname(self, principal_name):
        return self.get_usernames_from_attribute('userPrincipalName', principal_name)

    def get_usernames_from_mail(self, principal_name):
        return self.get_usernames_from_attribute('mail', principal_name)

    def get_usernames_from_email_academico(self, email_academico):
        return self.get_usernames_from_attribute('extensionAttribute4', email_academico)

    def get_usernames_from_email_google_classroom(self, email_google_classroom):
        return self.get_usernames_from_attribute('extensionAttribute5', email_google_classroom)

    def get_user(self, username, attrs=None, base=None):
        """recupera dados do usuário ``username``"""
        if not self.has_write_permission():
            return {}
        base = base or self.base
        ldap_obj = self.bind()
        filterstr = self.mount_filterstr(username)
        retries = int(Configuracao.get_valor_por_chave('ldap_backend', 'tentativas_maximas_busca') or 1)
        last_exception = Exception('Erro ao buscar no LDAP')
        for attempts in range(1, retries + 1):
            try:
                result = ldap_obj.search_ext_s(
                    base=base,
                    scope=ldap.SCOPE_SUBTREE,
                    filterstr=filterstr,
                    attrlist=attrs,
                    attrsonly=0,
                    serverctrls=None,
                    clientctrls=None,
                    timeout=-1,
                    sizelimit=0,
                )
                if result:
                    dn, attrs = result[0]
                    if isinstance(attrs, list):
                        return {}
                    attrs['dn'] = dn
                    return attrs
                else:
                    return {}
            except Exception as e:
                last_exception = e
                if attempts < retries:
                    time.sleep(2 * attempts)

        capture_exception(last_exception)
        raise LoginException(str(last_exception))

    def get_users_by_ou(self, ou_dn, attrlist=None):
        """Recupera os usuários de uma OU específica."""
        base = ou_dn
        filterstr = '(objectClass=person)'
        try:
            return self.search_objects(base=base, filterstr=filterstr, attrlist=attrlist)
        except Exception as e:
            capture_exception(e)
            raise LoginException(str(e))

    def search_objects(
        self, q=None, filterstr=None, attrlist=None, base=None, search_fields=None, use_paged_results=True, scope=ldap.SCOPE_SUBTREE, sizelimit=500
    ):
        """
        Busca objetos genéricos. Usado para buscar usuários e OUs
        """
        base = base or self.base
        filterstr = filterstr or self.mount_filter_by_query(q, search_fields)

        ldap_obj = self.bind()
        retries = int(Configuracao.get_valor_por_chave('ldap_backend', 'tentativas_maximas_busca') or 1)
        last_exception = Exception('Erro ao buscar no LDAP')
        for attempts in range(1, retries + 1):
            try:
                if not use_paged_results:
                    result = ldap_obj.search_ext_s(
                        base=base,
                        filterstr=filterstr,
                        attrlist=attrlist,
                        scope=scope,
                        attrsonly=0,
                        serverctrls=None,
                        clientctrls=None,
                        timeout=-1,
                        sizelimit=sizelimit,
                    )
                    results = []
                    for r in result:
                        dn, attrs = r
                        if dn:
                            attrs['dn'] = dn
                            results.append(attrs)
                    return results
                else:
                    # Busca paginada
                    from ldap.controls import SimplePagedResultsControl

                    page_size = sizelimit
                    results = []
                    page_control = SimplePagedResultsControl(True, size=page_size, cookie='')
                    while True:
                        serverctrls = [page_control]
                        msgid = ldap_obj.search_ext(base=base, filterstr=filterstr, attrlist=attrlist, scope=scope, serverctrls=serverctrls)
                        _rtype, result, _rmsgid, serverctrls = ldap_obj.result3(msgid)
                        for r in result:
                            dn, attrs = r
                            if dn:
                                attrs['dn'] = dn
                                results.append(attrs)
                        # Verifica cookie para próxima página
                        paged_ctrls = [c for c in serverctrls if c.controlType == SimplePagedResultsControl.controlType]
                        if paged_ctrls:
                            cookie = paged_ctrls[0].cookie
                            if cookie:
                                page_control.cookie = cookie
                                continue
                        break
                    return results
            except Exception as e:
                last_exception = e
                if attempts < retries:
                    time.sleep(2 * attempts)

        capture_exception(last_exception)
        raise LoginException(str(last_exception))

    def modify(self, dn_or_username: str, attrs: dict[str, Any], mod_list: dict[str, str] | None = None) -> int:
        """
        Faz a operação modify.

        attrs: {'field1': 'value1', 'field2': 'value2'}
        mod_list: {'field1', 'add', 'field2': 'delete'}, o default é o 'replace'.
        """
        MODS = {'add': ldap.MOD_ADD, 'replace': ldap.MOD_REPLACE, 'delete': ldap.MOD_DELETE}
        # Se dn_or_username tiver os caracteres ',' e '=', assume-se que é o dn
        if ',' in dn_or_username and '=' in dn_or_username:
            dn = dn_or_username
        else:  # assume-se que foi passado um username
            dn = self.get_user(dn_or_username, attrs=['dn']).get('dn')
            if not dn:
                return 0

        mod_list = mod_list or {}
        mod_attrs = []
        for key, value in list(attrs.items()):
            if value == '':
                raise ValueError(f'Error on modify "{dn}": "{key}" is empty string (should be None?)')
            if isinstance(value, list):
                value = [val.encode('utf-8') for val in value]
            if isinstance(value, str):
                value = [value.encode('utf-8')]
            mod = MODS[mod_list.get(key, 'replace')]
            mod_attrs.append((mod, key, value))
        try:
            self.bind().modify_s(dn, mod_attrs)
        except ldap.CONSTRAINT_VIOLATION as error:
            self._resolver_conflito_user_principal_name(dn_or_username, attrs, error)
            self.bind().modify_s(dn, mod_attrs)
        return 1

    def _resolver_conflito_user_principal_name(self, dn_or_username: str, attrs: dict[str, Any], error: ldap.CONSTRAINT_VIOLATION) -> None:
        user_principal_name = attrs.get('userPrincipalName')
        # O AD identifica o atributo conflitante no campo `info` da exceção.
        if not user_principal_name or 'userPrincipalName' not in str(error):
            raise error
        if isinstance(user_principal_name, list):
            user_principal_name = user_principal_name[0]
        outro_username = next(
            (username for username in self.get_usernames_from_principalname(user_principal_name) if username.lower() != dn_or_username.lower()), None
        )
        if not outro_username:
            raise error
        try:
            self._atualizar_user_principal_name(outro_username, user_principal_name)
        except Exception as exc:
            # Chamadores silenciados (``sync_ldap_user``) só enviam ao Sentry: a causa e os dois usernames dizem o porquê.
            error.add_note(f'userPrincipalName {user_principal_name} de "{dn_or_username}" em uso por "{outro_username}", que não foi liberado.')
            raise error from exc

    def _atualizar_user_principal_name(self, username: str, user_principal_name_em_uso: str) -> None:
        user = User.objects.get(username__iexact=username)
        user.reset_vinculo()
        user.reset_profile()
        obj_attrs = get_obj_attrs(model_obj=user.get_relacionamento(), ldap_conf=self, com_foto=False)
        novo_user_principal_name = obj_attrs.get('userPrincipalName') if obj_attrs else None
        if isinstance(novo_user_principal_name, list):
            novo_user_principal_name = novo_user_principal_name[0]
        if not novo_user_principal_name or novo_user_principal_name.lower() == user_principal_name_em_uso.lower():
            raise ValueError(f'Não foi possível liberar o userPrincipalName {user_principal_name_em_uso}.')
        self.modify(username, {'userPrincipalName': novo_user_principal_name})

    def move_object(self, dn, newdn, newrdn=None):
        newrdn = newrdn or newdn.split(',')[0]
        newsuperior = ','.join(newdn.split(',')[1:])
        ldap_obj = self.bind()
        ldap_obj.rename_s(dn=dn, newsuperior=newsuperior, newrdn=newrdn)

    def sync_all_ous(self, test_mode=True):
        """Sincroniza todos os setores do SUAP no LDAP.
        Nota: como a criação é recursiva, deve-se criar os nós mais profundos da árvore primeiro.
        """
        for s in Setor.get_setores_por_profundidade(raiz_por_ultimo=False):
            self.sync_ou_setor(s, test_mode=test_mode)
        if 'edu' in settings.INSTALLED_APPS:
            self.sync_ou_alunos(test_mode=test_mode)
        self.sync_ous_especiais(test_mode=test_mode)

    def create_alunos_group(self, setor, test_mode=True):
        campus_identificacao = setor.sigla.split('/')[-1]
        aluno_dn = f'OU=Alunos,{get_setor_dn(setor, self.domain)}'
        dn = f'CN=G_{campus_identificacao}_ALUNOS,{aluno_dn}'
        self.create_group(dn, test_mode=test_mode)

    def sync_ou_alunos(self, test_mode=True):
        for uo in UnidadeOrganizacional.objects.campi():
            setor = uo.setor
            newdn = f'OU=Alunos,{get_setor_dn(setor, self.domain)}'
            description = setor.nome
            admin_description = f'alunos-{setor.id}'
            self.sync_ou(newdn, description, admin_description, setor, test_mode=test_mode)
            self.create_alunos_group(setor, test_mode=test_mode)

    def _sync_special_ou(self, ou_name, description, admin_description, test_mode=True):
        """
        Método auxiliar para sincronizar OUs especiais no LDAP.
        """
        setor = Setor.raiz_suap()
        newdn = f'OU={ou_name},{get_setor_dn(setor, self.domain)}'
        print_(f'Sincronizando OU de {description.lower()}: {newdn}', test_mode)
        if not test_mode:
            self.sync_ou(newdn, description, admin_description, setor, test_mode=test_mode)

    def sync_ous_especiais(self, test_mode=True):
        self._sync_special_ou('Servidores Sem Setor', 'Servidores sem setor definido', 'servidores-sem-setor', test_mode=test_mode)
        self._sync_special_ou('Usuários Externos', 'Usuários Externos', 'usuarios-externos', test_mode=test_mode)
        self._sync_special_ou('Servidores Aposentados', 'Servidores aposentados', 'servidores-aposentados', test_mode=test_mode)
        self._sync_special_ou('Servidores Inativos', 'Servidores com situação inativa', 'servidores-inativos', test_mode=test_mode)
        self._sync_special_ou('Infra', 'Serviços de infraestrutura', 'infra', test_mode=test_mode)

    def sync_ou_setor(self, setor, test_mode=True, force=False):
        """
        Mapeamento SUAP X LDAP:
            Setor.id -> OU.adminDescription
            Setor.nome -> OU.description
        """
        description = setor.nome
        admin_description = str(setor.id)
        newdn = get_setor_dn(setor, self.domain)
        if setor.setores_servidor.exists() or setor.setores_prestadorservico.exists() or force:
            self.sync_ou(newdn, description, admin_description, setor, test_mode=test_mode, force=force)
        else:
            print_(f'"{newdn}" não possui servidores ou prestadores, não sincronizando.', test_mode)

    def get_emails_ad(self, username):
        attrs = ['mail', 'extensionAttribute4', 'extensionAttribute5']
        ldap_user = self.get_user(username, attrs=attrs)
        emails = []
        if ldap_user:
            if 'mail' in ldap_user:
                emails.append(ldap_user['mail'][0].decode())
            if 'extensionAttribute4' in ldap_user:
                emails.append(ldap_user['extensionAttribute4'][0].decode())
            if 'extensionAttribute5' in ldap_user:
                emails.append(ldap_user['extensionAttribute5'][0].decode())
        return list(set(emails))

    def sync_ou(self, newdn: str, description: str, admin_description: str, setor: Setor, test_mode: bool = True, force: bool = False) -> None:
        ldap_ou = self.get_ou_by_admin_description(admin_description)
        if ldap_ou:  # Atualizar OU existente no LDAP
            alterado = False
            dn = ldap_ou[0]['dn']
            if ldap_ou[0]['description'][0].decode() != description:
                alterado = True
                print_(f'Atualizando descrição da OU "{dn}" para "{description}"', test_mode)
                if not test_mode:
                    self.modify(dn, {'description': description})
            if dn != newdn:
                alterado = True
                self._move_ou(dn, newdn, description, admin_description, setor, test_mode, force)
            if not alterado and test_mode:
                print_(f'Nenhuma alteração necessária em "{newdn}"', test_mode)

        else:  # Criar OU no LDAP
            attrs = {
                'objectclass': [b'top', b'organizationalUnit'],
                'adminDescription': [admin_description.encode()],
                'description': [description.encode()],
            }
            ldif = modlist.addModlist(attrs)
            print_(f'Criando OU "{newdn}"', test_mode)
            if not test_mode:
                try:
                    self.bind().add_ext_s(newdn, ldif)
                except ldap.ALREADY_EXISTS:
                    print_(f'OU "{newdn}" já existe, atualizando apenas a descrição.', test_mode)
                    self.modify(newdn, {'description': description, 'adminDescription': admin_description})

    def _move_ou(self, dn: str, newdn: str, description: str, admin_description: str, setor: Setor, test_mode: bool, force: bool) -> None:
        print_(f'Movendo OU de "{dn}" para "{newdn}"', test_mode)
        if test_mode:
            return
        try:
            self.move_object(dn=dn, newdn=newdn)
        except ldap.NO_SUCH_OBJECT:
            if not setor.superior:
                raise
            self.sync_ou_setor(setor.superior, test_mode=test_mode, force=force)
            self.sync_ou(newdn, description, admin_description, setor, test_mode=test_mode, force=force)
        except ldap.OTHER as e:
            if setor.superior:
                self.sync_ou_setor(setor.superior, test_mode=test_mode, force=force)
            else:
                raise e
        except ldap.ALREADY_EXISTS:
            print_(
                f'OU "{dn}" não pode ser movida para "{newdn}" pois a OU de destino já existe, atualizando apenas a descrição da OU de destino.',
                test_mode,
            )
            self.modify(newdn, {'description': description, 'adminDescription': admin_description})

    def _get_emails_notificacao_inativacao(self, obj: Any) -> tuple[list[str], list[str]]:
        emails = [
            obj.email_pessoal,
            obj.get_vinculo().user.email if obj.get_vinculo().user else None,
            obj.email_notificacao,
            obj.email_academico,
            obj.email_google_classroom,
        ]
        emails_ad = self.get_emails_ad(obj.matricula)
        return list(set(filter(None, emails + emails_ad))), emails_ad

    def _get_descricao_vinculo_inativacao(self, obj: Any) -> tuple[str, str, str]:
        tipo_vinculo = obj.__class__._meta.verbose_name
        descricao_vinculo = ''
        matricula = f' com matrícula <b>{obj.matricula}</b>'
        if tipo_vinculo == 'Aluno':
            return 'Aluno(a)', matricula, f', do curso: <b>{obj.curso_campus}</b>'
        if tipo_vinculo == 'Usuário Externo':
            ocupacao = obj.ocupacoes_ativas().first() if obj.ocupacoes_ativas() else None
            if ocupacao:
                setor = ocupacao.prestador.setor
                setor_html = f'- {setor.get_caminho_as_html()}' if setor else ''
                descricao_vinculo = f', ocupação: <b>{ocupacao.ocupacao} {setor_html}</b>'
            descricao_vinculo = descricao_vinculo or ' (Avaliador externo de RSC, Avaliador externo de projetos de extensão, ou outros)'
            return 'Prestador(a) de Serviço', '', descricao_vinculo
        if tipo_vinculo == 'Servidor':
            setor = f'- <b>{obj.setor.get_caminho_as_html()}</b>' if obj.setor else ''
            cargo = f', com cargo: <b>{obj.cargo_emprego.nome}</b>' if obj.cargo_emprego else ''
            return 'Servidor(a)', matricula, f'{cargo} {setor}'
        return tipo_vinculo, matricula, descricao_vinculo

    def _get_dados_contas_email(self, emails_instituicao: list[str]) -> tuple[str, str]:
        if not emails_instituicao:
            return '', ''
        if len(emails_instituicao) == 1:
            contas_email = 'e sua conta de e-mail institucional serão inativadas'
            lista_emails = (
                f'<li>A conta de e-mail <b>{emails_instituicao[0]}</b> será inativada e, em até 90 dias, <b>excluída permanentemente.</b></li>'
            )
            return contas_email, lista_emails
        contas = ', '.join(f'<b>{email}</b>' for email in emails_instituicao)
        return (
            'e suas contas de e-mail institucionais serão inativadas',
            f'<li>As contas de e-mail {contas} serão inativadas e, em até 90 dias, <b>excluídas permanentemente.</b></li>',
        )

    def _get_orientacao_acesso_inativado(self, obj: Any, tipo_vinculo: str) -> str:
        if obj.pessoa_fisica.eh_estrangeiro:
            return '<li>Seu acesso aos serviços institucionais será encerrado. O acesso ao SUAP continuará disponível com sua matrícula e senha do SUAP.</li>'
        if tipo_vinculo != 'Servidor(a)':
            return '<li>Seu acesso ao Suap via senha será encerrado. A partir de então, o acesso será possível <b>apenas para consulta, por meio do Gov.br;</b></li>'
        return '<li>Seu acesso ao Suap será encerrado;</li>'

    def notificar_usuario_inativacao(
        self,
        obj: Any,
        dia_da_desativacao: int | datetime,
        dias_para_inativar: int | None = None,
        tempo_maximo_inativacao_email: int | None = None,
    ) -> None:
        dias_para_inativar = dias_para_inativar or Configuracao.get_valor_por_chave('ldap_backend', 'dias_para_inativar_conta') or 30
        tempo_maximo_inativacao_email = (
            tempo_maximo_inativacao_email or Configuracao.get_valor_por_chave('ldap_backend', 'tempo_maximo_inativacao_email') or 90
        )
        emails, emails_ad = self._get_emails_notificacao_inativacao(obj)
        # Sem domínio configurado, nenhum e-mail é institucional; pedaço vazio ('a;') casaria qualquer e-mail.
        dominios = [d.strip() for d in Configuracao.get_valor_por_chave_str('comum', 'dominios_institucionais').split(';') if d.strip()]
        emails_instituicao = [email for email in emails_ad if any(dominio in email for dominio in dominios)]
        contas_email, lista_emails = self._get_dados_contas_email(emails_instituicao)
        tipo_vinculo, matricula, descricao_vinculo = self._get_descricao_vinculo_inativacao(obj)
        # Sem sigla configurada, texto neutro em vez de "conta no None" (#17464).
        sigla_instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao_sigla')
        instituicao = f'o {sigla_instituicao}' if sigla_instituicao else 'a instituição'
        conta_suap = f'SUAP do {sigla_instituicao}' if sigla_instituicao else 'SUAP'
        resolucao = Configuracao.get_valor_por_chave('ldap_backend', 'resolucao') or 'Resolução 26/2023 - CONSUP/IFRN, de 19 de abril de 2023'
        resolucao_url = Configuracao.get_valor_por_chave('ldap_backend', 'resolucao_url') or (
            'https://suap.ifrn.edu.br/documento_eletronico/conteudo_documento/5d029371-65a2-4d7a-99cb-6eb8405588a9/'
        )
        email_ti = Configuracao.get_valor_por_chave('ldap_backend', 'email_ti') or self.email_admin
        sigla_ti = Configuracao.get_valor_por_chave('ldap_backend', 'sigla_ti') or 'DIGTI'
        eh_estrangeiro = obj.pessoa_fisica.eh_estrangeiro
        descricao_conta = 'sua conta institucional' if eh_estrangeiro else f'sua conta no {conta_suap}'
        descricao_inativacao = contas_email if emails_instituicao else 'será inativada'
        orientacao_acesso = self._get_orientacao_acesso_inativado(obj, tipo_vinculo)
        recomendacao = (
            'Cadastre ou atualize sua senha do SUAP e mantenha seu e-mail secundário atualizado.'
            if eh_estrangeiro
            else 'Recomendamos que utilize este período para salvar documentos, e-mails ou arquivos pessoais que deseje manter. Após a exclusão, não será possível recuperar os dados.'
        )
        titulo = f'[SUAP] Informações relevantes sobre a sua conta no {sigla_instituicao or "SUAP"}'
        mensagem = f"""
        <p>Olá <b>{obj.pessoa_fisica.nome},</b></p>
        <p>Estamos entrando em contato para informar que, em razão do <b>encerramento do seu vínculo com {instituicao}</b> como <b>{tipo_vinculo}</b>{matricula}{descricao_vinculo}, {descricao_conta} {descricao_inativacao} em <b>{dias_para_inativar} dias</b>.</p>
        <p>Após esse prazo:</p>
        <ul>{orientacao_acesso}{lista_emails}</ul>
        <p><b>O que você deve fazer agora?</b> {recomendacao}</p>
        <p>Este procedimento segue a <a href="{resolucao_url}">{resolucao}</a>, que regulamenta o uso do serviço de correio eletrônico institucional.</p>
        <p>Em caso de dúvidas, ficamos à disposição nos canais oficiais da <a href="mailto:{email_ti}">{sigla_ti}</a>.</p>
        <hr>
        <p>Este e-mail é automático. Favor não respondê-lo.</p>
        """
        dia_exclusao = ad_to_datetime(dia_da_desativacao) if isinstance(dia_da_desativacao, int) else dia_da_desativacao
        if settings.DEBUG:
            logger.info(titulo)
            logger.info(mensagem)
            return
        send_mail(titulo, mensagem, self.email_admin, emails)
        send_notification(
            titulo,
            mensagem,
            settings.DEFAULT_FROM_EMAIL,
            [obj.get_vinculo()],
            categoria=f'[SUAP] Sua conta de {tipo_vinculo} será expirada.',
            data_permite_excluir=dia_exclusao,
        )

    def sync_user_emails(self, obj, emails):
        """
        Sincroniza os emails do usuário no LDAP.

        obj: instância de Servidor, Aluno ou Prestador
        emails: dicionário de emails a serem sincronizados
        """
        ATTRS_TO_GET = ['dn', 'sAMAccountName', 'userAccountControl', 'memberOf', 'mail', 'accountExpires', 'pwdLastSet', 'lastLogon']
        ATTRS_TO_GET.extend(self.filterstr)
        ATTRS_TO_GET = list(set(ATTRS_TO_GET))
        ldap_user = self.get_user(obj.username, attrs=ATTRS_TO_GET)
        if not ldap_user:
            print_(f'Usuário {obj.username} não encontrado no LDAP para sincronização de emails.')
            return

        obj_attrs = {}
        if emails:
            email_institucional = emails.get('email_institucional', '')
            email_academico = emails.get('email_academico', '')
            email_google_classroom = emails.get('email_google_classroom', '')
            if email_institucional:
                obj_attrs['mail'] = email_institucional  # email institucional
            if email_academico:
                obj_attrs['extensionAttribute4'] = email_academico  # email acadêmico
            if email_google_classroom:
                obj_attrs['extensionAttribute5'] = email_google_classroom  # email google classroom

        if not obj_attrs:
            print_(f'Nenhum email para sincronizar para o usuário {obj.username}.')
            return

        self.modify(obj.username, obj_attrs)

    def sync_user(self, obj: Any, com_foto: bool = True) -> None:
        """
        Cria ou atualiza o `obj` no LDAP.

        obj: instância de Servidor, Aluno ou Prestador; também pode ser uma
            string representando o username (evitar essa opção, que é mais lenta)
        com_foto: sincroniza também a foto do servidor (``thumbnailPhoto``). O login passa ``False``: a leitura
            da foto no storage não deve segurar o request (#17597); a sincronia agendada leva a foto.
        """
        ATTRS_TO_GET = ['dn', 'sAMAccountName', 'userAccountControl', 'memberOf', 'mail', 'accountExpires', 'pwdLastSet', 'lastLogon']
        obj = _relacionamento(obj)
        ATTRS_TO_GET.extend(self.filterstr)
        ATTRS_TO_GET = list(set(ATTRS_TO_GET))
        ldap_user = self.get_user(obj.username, attrs=ATTRS_TO_GET)
        self._atualizar_email_institucional(obj, ldap_user)

        obj_attrs = get_obj_attrs(model_obj=obj, ldap_conf=self, com_foto=com_foto)
        if not obj_attrs:
            print_(f'Impossível gerar DN para objeto: {obj}')
            return

        new_dn = obj_attrs.pop('dn')
        setor = obj_attrs.pop('setor')
        member_of = obj_attrs.pop('memberOf', [])
        thumbnail_photo = obj_attrs.pop('thumbnailPhoto')
        senha = get_senha_inicial(obj)

        if ldap_user and ldap_user['dn'] != new_dn:  # Usuário deve ser movido?
            self._mover_usuario(ldap_user['dn'], new_dn, setor)

        if not obj_attrs.pop('active'):  # o usuário deve ser inativo no LDAP
            self._inativar_usuario(obj, ldap_user, obj_attrs)
            return

        if ldap_user:  # Usuário existe, vamos atualizá-lo
            self._atualizar_usuario_ativo(obj, ldap_user, obj_attrs, new_dn, senha)
        else:  # Usuário não existe, vamos criá-lo
            ldap_user = self._criar_usuario(obj, obj_attrs, new_dn, setor, senha, ATTRS_TO_GET)
        self._adicionar_aos_grupos(ldap_user, member_of, new_dn)

        # tratando o ``thumbnailPhoto`` do usuário; estranhamente a escrita
        # do atributo só funciona ser atualizado isoladamente.
        if thumbnail_photo:
            self.modify(obj.username, {'thumbnailPhoto': thumbnail_photo})

    def _atualizar_email_institucional(self, obj: Any, ldap_user: dict | None) -> None:
        #####################################################################################
        # Se no LDAP o user tem `mail`, deixar o valor do `mail` em Servidor.email_institucional`
        # e `Aluno.email_academico`.
        # if ldap_user and ldap_user['sAMAccountName'][0]:
        # Testando se todas as chaves listadas no filtro de autenticação estão presentes.
        #####################################################################################
        if obj.__class__.__name__.lower() != 'servidor' or not ldap_user or not all(k in ldap_user for k in self.filterstr):
            return
        ldap_mail = ldap_user.get('mail', [b''])[0].decode()
        if ldap_mail:
            obj.__class__.objects.filter(id=obj.id).update(email_institucional=ldap_mail)
            obj.email_institucional = ldap_mail

    def _mover_usuario(self, dn_atual: str, new_dn: str, setor: Setor | None) -> None:
        if setor:
            self.sync_ou_setor(setor, test_mode=False, force=True)
        self.move_object(dn_atual, new_dn)

    def _atualizar_usuario_ativo(self, obj: Any, ldap_user: dict, obj_attrs: dict, new_dn: str, senha: str) -> None:
        pwd_last_set = ldap_user.get('pwdLastSet', [b'0'])[0].decode()
        last_logon = ldap_user.get('lastLogon', [b'0'])[0].decode()

        # Usuário nunca logou nem definiu a senha? (verificado antes do bloco pwdLastSet != '0')
        if pwd_last_set == '0' and last_logon == '0':
            self.change_password(new_dn, senha)

        # Só vai fazer qualquer sincronização de alteração caso pwdLastSet não esteja setado igual a 0
        if pwd_last_set == '0':
            return
        # Caso futuramente se queira sincronizar o `objectClass` nas
        # edições, cada item deve ser tratado individualmente para apenas
        # adicionar o que é necessário, pois o ldap.MOD_REPLACE pode causar
        # inconsistências com outros sistemas (ex: Microsoft Lync)
        obj_attrs.pop('cn', None)  # `cn` não é atualizável

        # `userPrincipalName` aka UPN não é atualizável (erro CONSTRAINT_ATT_TYPE)
        obj_attrs.pop('userPrincipalName', None)

        if ldap_user['userAccountControl'][0].decode() == USER_ACCOUNT_CONTROL_INACTIVE:  # Usuário deve ser ativado?
            self.change_password(new_dn, senha)
            self.activate_user(obj.username)

        _encerrar_pedido_de_troca_de_senha(obj, pwd_last_set)

        # Verifica se a conta do usuário está com data de expiração e caso esteja retira a data da expiração
        if ldap_user.get('accountExpires', [None])[0] not in [None, b'0', b'9223372036854775807']:
            obj_attrs['accountExpires'] = ['0']
        # sincroniza os atributos e já ativa também
        self.modify(obj.username, obj_attrs)

    def _criar_usuario(self, obj: Any, obj_attrs: dict, new_dn: str, setor: Setor | None, senha: str, attrs_to_get: list[str]) -> dict | None:
        obj_attrs.pop('mail', None)  # `mail` de um novo usuário é sempre None (e dá erro no addModlist)
        # Não se pode criar objeto com algum atributo sendo `None`
        for k, v in list(obj_attrs.items()):
            if not v:
                del obj_attrs[k]
        obj_attrs['userAccountControl'] = USER_ACCOUNT_CONTROL_INACTIVE
        try:
            modattrs = modlist.addModlist(_atributos_em_bytes(obj_attrs))
            if setor:
                self.sync_ou_setor(setor, test_mode=False, force=True)
            self.bind().add_s(new_dn, modattrs)
        except ldap.NO_SUCH_OBJECT:
            raise ValueError(f'OU inexistente no LDAP: {new_dn.split(",", 1)[1]}')
        self.change_password(new_dn, senha)
        self.activate_user(obj.username)
        return self.get_user(obj.username, attrs=attrs_to_get)

    def _adicionar_aos_grupos(self, ldap_user: dict | None, member_of: list[str], new_dn: str) -> None:
        # tratando o ``memberOf`` do usuário
        existing_groups = set(ldap_user.get('memberOf', []) if ldap_user else [])
        target_groups = set(member_of)
        groups_to_add = list(target_groups - existing_groups)
        for group_dn in groups_to_add:
            try:
                self.modify(group_dn, {'member': new_dn}, mod_list={'member': 'add'})
            except ldap.ALREADY_EXISTS:
                pass
            except ldap.NO_SUCH_OBJECT:
                self.create_group(group_dn, test_mode=False)
                self.modify(group_dn, {'member': new_dn}, mod_list={'member': 'add'})

    def _inativar_usuario(self, obj: Any, ldap_user: dict | None, obj_attrs: dict) -> None:
        if not ldap_user:
            return
        obj_attrs.pop('objectClass', None)
        obj_attrs.pop('cn', None)
        obj_attrs.pop('accountExpires', None)
        # daqui_a_15_dias = datetime_to_ad(datetime.now() + timedelta(15))
        hoje = datetime.now()
        dias_para_inativar = int(Configuracao.get_valor_por_chave('ldap_backend', 'dias_para_inativar') or '30')
        tempo_maximo_inativacao_email = int(Configuracao.get_valor_por_chave('ldap_backend', 'tempo_maximo_inativacao_email') or '90')
        dia_da_desativacao = datetime_to_ad(datetime.now() + timedelta(dias_para_inativar))
        # Verifica se o usuário ainda está ativo
        if ldap_user['userAccountControl'][0].decode() != USER_ACCOUNT_CONTROL_INACTIVE:
            self._programar_inativacao(obj, ldap_user, obj_attrs, hoje, dia_da_desativacao, tempo_maximo_inativacao_email)
        self.modify(obj.username, obj_attrs)

    def _programar_inativacao(
        self, obj: Any, ldap_user: dict, obj_attrs: dict, hoje: datetime, dia_da_desativacao: int, tempo_maximo_inativacao_email: int
    ) -> None:
        """Usuário ainda ativo no AD que deve ser inativado: define a expiração da conta ou, se já definida, avisa/inativa no prazo."""
        # Em estando ativo o usuario no AD verifica se ja foi setado o tempo de expiração
        account_expires_value = ldap_user['accountExpires'][0].decode()
        if not int(account_expires_value) or account_expires_value == '9223372036854775807':
            obj_attrs['accountExpires'] = str(dia_da_desativacao)
            obj_attrs['userAccountControl'] = USER_ACCOUNT_CONTROL_ACTIVE  # Mantém usuário ativo
            self.notificar_usuario_inativacao(obj, dia_da_desativacao)
            # Quando adicionar o atributo accountsExpires ele vai deslogar o usuário para que ele possa
            # logar novamente e adicionar o accountExpires na sessão
            remote_logout_user(obj.username)
            return

        obj_attrs['userAccountControl'] = USER_ACCOUNT_CONTROL_ACTIVE
        data_da_desativacao = ad_to_datetime(int(account_expires_value))
        if data_da_desativacao - timedelta(15) <= hoje <= data_da_desativacao:
            tempo_maximo_inativacao_email = (data_da_desativacao + timedelta(days=tempo_maximo_inativacao_email) - hoje).days
            dias_para_inativar = (data_da_desativacao - datetime.now()).days
            self.notificar_usuario_inativacao(obj, data_da_desativacao, dias_para_inativar, tempo_maximo_inativacao_email)
            print_(f'Usuario será inativado em {dias_para_inativar} dias: {obj}')
        elif hoje > data_da_desativacao:
            obj_attrs['userAccountControl'] = USER_ACCOUNT_CONTROL_INACTIVE
            obj_attrs['accountExpires'] = ['0']
            self.notificar_usuario_inativacao(obj, data_da_desativacao)
            # Quando adicionar o atributo accountsExpires ele vai deslogar o usuário para que ele possa
            # logar novamente e adicionar o accountExpires na sessão
            remote_logout_user(obj.username)

    def limpar_emails_academico_e_google(self, obj):
        """
        Inativa o `obj` no LDAP.

        obj: instância de Aluno; também pode ser uma
            string representando o username (evitar essa opção, que é mais lenta)
        """
        ATTRS_TO_GET = ['dn', 'sAMAccountName', 'userAccountControl', 'memberOf', 'mail', 'accountExpires', 'pwdLastSet', 'lastLogon']

        if isinstance(obj, str):
            try:
                obj = User.objects.get(username=obj).get_relacionamento()
            except User.DoesNotExist:
                raise Exception(f'Nenhum usuário com username {obj}')

        ATTRS_TO_GET.extend(self.filterstr)
        ATTRS_TO_GET = list(set(ATTRS_TO_GET))
        obj_attrs = {}
        # Retirei a inativação do AD
        # obj_attrs['userAccountControl'] = '514'
        # Email Academico
        obj_attrs['extensionAttribute4'] = None
        # Email Classroom
        obj_attrs['extensionAttribute5'] = None
        # UserPrincipalName deve voltar a ser a matricula do usuário
        obj_attrs['userPrincipalName'] = f'{obj.username}@{self.domain}'
        ldap_user = self.get_user(obj.username, attrs=ATTRS_TO_GET)
        if not ldap_user:
            return False
        self.modify(obj.username, obj_attrs)
        return True

    def makepassword(self, pw):
        return [f'"{pw}"'.encode('utf-16-le')]

    def change_password(self, dn_or_username, password):
        if ',' in dn_or_username:
            dn = dn_or_username
        else:
            dn = self.get_user(dn_or_username, attrs=['dn']).get('dn', '')

        if not dn:
            return False

        passwd = self.makepassword(password)
        uri = self.uri_change_password
        if not uri:
            host = str(self.uri.split('//')[1].split(':')[0])
            uri = f'ldaps://{host}:636'
        try:
            conn = ldap.initialize(uri)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 60.0)
            conn.set_option(ldap.OPT_TIMEOUT, 60.0)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            conn.simple_bind_s(self.who, self.cred)
            conn.modify_s(dn, [(ldap.MOD_REPLACE, 'unicodePwd', passwd)])
            return True
        except Exception as e:
            if settings.DEBUG:
                raise e
            return False

    def force_user_reset_password(self, username):
        self.modify(username, {'pwdLastSet': '0'})

    def force_user_not_reset_password(self, username):
        self.modify(username, {'pwdLastSet': '-1'})

    def activate_user(self, username):
        self.modify(username, {'userAccountControl': USER_ACCOUNT_CONTROL_ACTIVE})

    def get_ou_by_admin_description(self, description, base=None):
        """``description`` é `setor.pk`"""
        try:
            query = '(&(objectClass=organizationalUnit)(adminDescription={0}))'
            filterstr = query.format(str(description))
            attrlist = ['dn', 'ou', 'name', 'description', 'adminDescription']
            return self.search_objects(base=base, filterstr=filterstr, attrlist=attrlist)
        except ldap.NO_SUCH_OBJECT:
            return None

    def get_group_by_dn(self, dn):
        try:
            query = f'(&(objectClass=group)(distinguishedName={dn}))'
            attrlist = ['dn', 'cn', 'name', 'sAMAccountName']
            return self.search_objects(filterstr=query, attrlist=attrlist)
        except ldap.NO_SUCH_OBJECT:
            return None

    def create_group(self, dn: str, test_mode: bool = True) -> None:
        cn = dn.split(',', maxsplit=1)[0].split('=', maxsplit=1)[1]
        ldap_group = self.get_group_by_dn(dn)
        if ldap_group:
            print_(f'Grupo "{dn}" já existe no LDAP', test_mode)
            return
        attrs = {
            'objectclass': [b'top', b'group'],
            'cn': [cn.encode()],
            'name': [cn.encode()],
            'sAMAccountName': [cn.encode()],
        }
        ldif = modlist.addModlist(attrs)
        print_(f'Criando grupo "{dn}"', test_mode)
        if not test_mode:
            try:
                self.bind().add_ext_s(dn, ldif)
            except ldap.ALREADY_EXISTS:
                if self.get_group_by_dn(dn):
                    print_(f'Grupo "{dn}" já existe no LDAP', test_mode)
                    return

                groups = self.search_objects(
                    filterstr=f'(&(objectClass=group)(sAMAccountName={escape_filter_chars(cn)}))',
                    attrlist=['dn'],
                )
                if len(groups) != 1:
                    raise
                old_dn = groups[0]['dn']
                print_(f'Movendo grupo "{old_dn}" para "{dn}"', test_mode)
                self.move_object(old_dn, dn)

    def has_write_permission(self):
        return bool(self.cred)

    def search_users_by_account_expires(self, min_expires=0, max_expires=None, use_paged_results=True):
        """
        Busca especializada de usuários no LDAP pelo atributo accountExpires.
        Permite busca flexível por accountExpires:
        - min_expires: valor mínimo (exclusivo)
        - max_expires: valor máximo (inclusivo)
        :param min_expires: valor mínimo de accountExpires (exclusivo)
        :param max_expires: valor máximo de accountExpires (inclusivo)
        :param use_paged_results: Se True, usa resultados paginados
        :return: Lista de usuários encontrados
        """
        username_field = self.filterstr_prefix.replace('=', '')
        search_fields = [username_field]
        # Monta filtro LDAP para faixa de valores
        # LDAP não suporta operadores > e < nativamente, mas AD aceita filtros extensivos com 'accountExpires>=valor' e 'accountExpires<=valor'
        filter_parts = ['(userAccountControl=512)', f'(accountExpires>={min_expires + 1})']
        if max_expires is not None:
            filter_parts.append(f'(accountExpires<={max_expires})')
        # Ignora 9223372036854775807
        filter_parts.append('(!(accountExpires=9223372036854775807))')
        filterstr = f'(&{"".join(filter_parts)}(objectClass=user))'
        return self.search_objects(filterstr=filterstr, attrlist=search_fields, use_paged_results=use_paged_results, sizelimit=500)

    def extend_user_expiration_date(self, username, expiration_date):
        """
        Estende a expiração da conta do usuário no LDAP.
        :param username: Nome de usuário (sAMAccountName)
        :param expiration_date: Nova data de expiração
        :return: True se a operação for bem-sucedida, False caso contrário
        """
        user = self.get_user(username, attrs=['dn', 'accountExpires'])
        if not user or 'dn' not in user:
            capture_exception(Exception(f'Usuário {username} não encontrado no LDAP.'))
            return False

        modificacoes = {}

        # Força troca de senha
        modificacoes['pwdLastSet'] = ['0']

        # Define a data de expiração
        data_expiracao_ldap = datetime_to_ad(expiration_date)
        modificacoes['accountExpires'] = [int(data_expiracao_ldap)]

        # Reativa usuário
        modificacoes['userAccountControl'] = [USER_ACCOUNT_CONTROL_ACTIVE]

        self.modify(username, modificacoes)
        return True


class LdapUser(ldapdb.models.Model):
    default_search_fields = ['uid', 'sAMAccountName', 'givenName', 'sn', 'mail']
    base_dn = 'OU=IFRN,DC=ifrn,DC=local'
    object_classes = ['person', 'organizationalPerson', 'user']
    rdn_fields = ['uid']
    #
    uid = ldapFields.CharField(db_column='uSNCreated', verbose_name='User ID', help_text='uid')
    sAMAccountName = ldapFields.CharField(db_column='sAMAccountName', verbose_name='Account Name', unique=True)
    givenName = ldapFields.CharField(db_column='givenName', verbose_name='First Name', blank=True, null=True)
    sn = ldapFields.CharField(db_column='sn', verbose_name='Surname', help_text='Surname', blank=False)
    mail = ldapFields.CharField(db_column='mail', help_text='E-mail', verbose_name='E-mail', blank=True, null=True)

    cn = ldapFields.CharField(db_column='cn', verbose_name='Common Name', help_text='Common Name', blank=False)
    name = ldapFields.CharField(db_column='displayName', help_text='Display Name', verbose_name='Display Name', blank=True, null=True)
    distinguishedName = ldapFields.CharField(db_column='distinguishedName', verbose_name='Distinguished Name', unique=True)
    #
    member_of = ldapFields.ListField(db_column='memberOf', editable=False, null=True)
    objects = LdapUserManager()

    class Meta:
        verbose_name = 'LDAP User'
        verbose_name_plural = 'LDAP Users'

    def distinguished_name(self):
        return self.distinguishedName

    def membership(self):
        # memberOf fill fields in people entries only if a change/write happens in its definitions
        try:
            membership = LdapGroup.objects.filter(member__contains=self.dn)
            if membership:
                # return os.linesep.join([m.dn for m in membership])
                return [i.cn for i in membership]
        except ldap.FILTER_ERROR:
            return []

    def __str__(self):
        return self.sAMAccountName


class LdapGroup(ldapdb.models.Model):
    """
    Class for representing an LDAP group entry.
    """

    # LDAP meta-data
    base_dn = 'OU=IFRN,DC=ifrn,DC=local'
    object_classes = ['top', 'group']
    rdn_fields = ['cn']

    cn = ldapFields.CharField(db_column='cn', max_length=200, unique=True, verbose_name='Common Name')
    name = ldapFields.CharField(db_column='name', help_text='Name', verbose_name='Name', blank=True, null=True)
    sAMAccountName = ldapFields.CharField(db_column='sAMAccountName', verbose_name='Account Name', unique=True)
    member = ldapFields.ListField(db_column='member', verbose_name='Group Members', default=[], editable=True, null=True)

    class Meta:
        verbose_name = 'LDAP Grupo'
        verbose_name_plural = 'LDAP Grupos'

    def __str__(self):
        return self.cn

    def add_member(self, member_obj):
        member_obj_dn = member_obj.dn
        if member_obj_dn not in self.member:
            self.member.append(member_obj.dn)
            self.save()
            return True
        return False

    def remove_member(self, member_obj):
        member_obj_dn = member_obj.dn
        if member_obj_dn in self.member:
            self.member.remove(member_obj_dn)
            self.save()
            return True
        return False

    def is_member(self, member_obj):
        member_obj_dn = member_obj.dn
        return member_obj_dn in self.member

    def remove_all(self):
        self.member = []
        self.save()
