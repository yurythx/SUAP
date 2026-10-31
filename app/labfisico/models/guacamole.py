from django.conf import settings
from django.urls import reverse

from comum.models import UnidadeOrganizacional
from djtools.db import models
from labfisico.managers import GuacamoleConnectionGroupManager
from labfisico.perms import pode_gerenciar_laboratorio_guacamole, pode_gerenciar_solicitacao_labfisico
from labfisico.services import (
    GuacamoleService,
    make_guacamole_connection_group_payload,
    make_guacamole_connection_payload,
    make_guacamole_org_connection_group_payload,
)

if 'ldap_backend' in settings.INSTALLED_APPS:
    from ldap_backend.models import LdapGroup


def make_ldap_group(name, base_dn):
    group = LdapGroup.objects.filter(sAMAccountName=name).first()
    if group is None:
        defaults = {'name': name, 'sAMAccountName': name, 'cn': name}
        group = LdapGroup(**defaults)
        group.base_dn = base_dn
        group.save()
        return group, True
    return group, False


class GuacamoleServer(models.ModelPlus):
    name = models.CharFieldPlus(verbose_name='Nome', unique=True, max_length=100)
    uri = models.CharFieldPlus(verbose_name='URI', help_text='Ex.: "banos.ifrn.local:8800".', blank=False, null=False, max_length=255)
    username = models.CharFieldPlus(verbose_name='Username', blank=False, null=False, max_length=50)
    password = models.CharFieldPlus(verbose_name='Password', blank=False, null=False, max_length=50)
    priority = models.IntegerFieldPlus(verbose_name='Prioridade', default=1000)
    active = models.BooleanField(verbose_name='Serviço ativo', default=True)

    class Meta:
        verbose_name = 'Configuração do Servidor Guacamole'
        verbose_name_plural = 'Configurações dos Servidores Guacamole'

    def __str__(self):
        return self.name

    @property
    def api(self):
        return GuacamoleService(hostname=self.uri, username=self.username, password=self.password)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(active=True).order_by('priority').first()

    @classmethod
    def get_active_endpoint(cls):
        server = cls.get_active()
        if server:
            return server.api
        raise Exception('Não existem servidores guacamole ativos configurados.')


class GuacamoleConnectionGroup(models.ModelPlus):
    #
    name = models.CharFieldPlus(verbose_name='Nome', max_length=90, help_text='O nome final será: Sigla-Campus>_<LABxx>_GUACAMOLE_XXX')
    description = models.CharFieldPlus(max_length=200, verbose_name='Descrição')
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=False, blank=False)
    connection_group_name = models.CharFieldPlus(max_length=128, unique=True, verbose_name='Grupo de Conexão')
    ldap_group_name = models.CharFieldPlus(max_length=128, unique=True, verbose_name='Grupo do LDAP')
    #
    connection_group_id = models.IntegerFieldPlus(verbose_name='Identificador', null=True)
    max_connections = models.IntegerFieldPlus(default=10, verbose_name='Número Máximo de Conexões')
    max_connections_per_user = models.IntegerFieldPlus(default=1, verbose_name='Número de Conexões por Usuário')
    enable_session_affinity = models.BooleanField(default=True, verbose_name='Afinidade de Sessão')

    #
    objects = GuacamoleConnectionGroupManager()

    class Meta:
        verbose_name = 'Laboratório Remoto'
        verbose_name_plural = 'Laboratórios Remotos'
        unique_together = (('name', 'campus'),)

    def __str__(self):
        return self.name

    @property
    def org_connection_group(self):
        return self.campus.sigla

    def pode_solicitar(self, user):
        autorizado = False
        if not user.is_anonymous:
            autorizado = pode_gerenciar_solicitacao_labfisico(user, self)
            if not autorizado and user.has_perm('labfisico.add_solicitacaolabfisico'):
                autorizado = GuacamoleConnectionGroup.objects.my_guacamole_connection_groups(user).filter(id=self.id).exists()
        return autorizado

    def location(self):
        api = self.guacamole_api()
        connection = api.connection_group_by_name(self.org_connection_group)
        return connection or 'ROOT'

    def as_payload(self, location=None):
        payload = make_guacamole_connection_group_payload(
            self.connection_group_name, self.max_connections, self.max_connections_per_user, self.enable_session_affinity, location
        )
        return payload

    def get_absolute_url(self):
        return reverse('labfisico:guacamole_connection_group_detail', kwargs={'pk': self.pk})

    def guacamole_api(self) -> GuacamoleService:
        return GuacamoleServer.get_active_endpoint()

    def connections(self):
        return self.guacamoleconnection_set.all()

    def connections_count(self):
        return self.guacamoleconnection_set.count()

    def ldap_group(self):
        if 'ldap_backend.router.SuapRouter' not in settings.DATABASE_ROUTERS:
            return None
        return LdapGroup.objects.filter(cn=self.ldap_group_name).first()

    def is_sync_ldap(self):
        return self.ldap_group() is not None

    def __bind_to_master(self, group):
        # Colocando como filho do grupo de acesso geral.
        # G_RE_GUACAMOLE
        master = LdapGroup.objects.filter(sAMAccountName='G_RE_GUACAMOLE').first()
        master.add_member(group)
        master.save()

    def sync_ldap(self):
        try:
            parent_name = f'G_{self.campus.sigla}_GUACAMOLE_LABS'
            base_dn = 'OU=GUACAMOLE,OU=COINRE,OU=DIGTI,OU=RE,OU=IFRN,DC=ifrn,DC=local'
            parent_group, created = make_ldap_group(parent_name, base_dn)
            if created:
                self.__bind_to_master(parent_group)
            #
            group, _ = make_ldap_group(self.ldap_group_name, base_dn)
            parent_group.add_member(group)
            return group
        except Exception as e:
            raise Exception(f'Erro na comunicação com o ldap. Verificar a conexão!: {e}')

    def remove_ldap_group(self):
        LdapGroup.objects.filter(sAMAccountName=self.ldap_group_name).delete()

    def kill_sessions(self, api=None):
        api = api or self.guacamole_api()
        api.kill_active_session_by_group(self.connection_group_id)

    def sync_guacamole_org_group(self):
        connection = self.location()
        if not connection:
            api = self.guacamole_api()
            payload = make_guacamole_org_connection_group_payload(self.org_connection_group)
            connection = api.add_connection_group(payload)
        #
        return connection

    def sync_guacamole(self):
        try:
            location = self.sync_guacamole_org_group()
            payload = self.as_payload(location=location)
            api = self.guacamole_api()
            self.connection_group_id = api.sync_connection_group(self.connection_group_id, payload)
            api.add_group(self.connection_group_name)
        except Exception as e:
            self.remove_ldap_group()
            raise e

    def guacamole_cleanup(self):
        if self.connections_count():
            self.disable_guacamole_connections()
        #
        api = self.guacamole_api()
        api.remove_group(self.connection_group_name)
        api.remove_connection_group(self.connection_group_id)

    def enable_guacamole_connections(self, user_group=None):
        user_group = user_group or self.connection_group_name
        api = self.guacamole_api()
        # 1 - Permissão na Organization Folder
        org_connection_group = self.location()
        api.assign_connection_groups_to_group(user_group=user_group, connection_group=org_connection_group)
        #  2- Permissão para o grupo de conexão
        api.assign_connection_groups_to_group(user_group=user_group, connection_group=self.connection_group_id)

    #
    def disable_guacamole_connections(self, user_group=None):
        user_group = user_group or self.connection_group_name
        api = self.guacamole_api()
        self.kill_sessions(api)
        #
        org_connection_group = self.location()
        api.revoke_connection_groups_from_group(user_group=user_group, connection_group=org_connection_group)
        #
        api.revoke_connection_groups_from_group(user_group=user_group, connection_group=self.connection_group_id)

    #

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.connection_group_name = f'G_LAB_{self.name}'
            self.ldap_group_name = f'G_{self.campus.sigla}_LAB_{self.name}'
        #
        self.sync_ldap()
        self.sync_guacamole()
        try:
            super().save(*args, **kwargs)
        except Exception as e:
            self.remove_ldap_group()
            self.guacamole_cleanup()
            raise e

    #
    def delete(self, *args, **kwargs):
        self.remove_ldap_group()
        self.guacamole_cleanup()
        super().delete(*args, **kwargs)

    def can_change(self, user):
        return pode_gerenciar_laboratorio_guacamole(user, self)

    def can_delete(self, user):
        return pode_gerenciar_laboratorio_guacamole(user, self)


class GuacamoleConnection(models.Model):
    # Connection
    connection_name = models.CharFieldPlus(max_length=128, verbose_name='Nome')
    connection_id = models.IntegerFieldPlus(verbose_name='Identificador', null=True)
    connection_group = models.ForeignKey(GuacamoleConnectionGroup, on_delete=models.CASCADE, null=True, verbose_name='Laboratório Remoto')
    protocol = models.CharFieldPlus(max_length=32, null=False, blank=False, default='rdp', verbose_name='Protocolo')

    attrs = models.JSONField(null=True, blank=True)
    parameters = models.JSONField(null=True, blank=True)
    objects = GuacamoleConnectionGroupManager()

    class Meta:
        unique_together = (('connection_name', 'connection_group'),)
        verbose_name = 'Cliente Guacamole'
        verbose_name_plural = 'Clientes Guacamole'

    def __str__(self) -> str:
        return self.connection_name

    @property
    def hostname(self):
        return self.parameters.get('hostname')

    @property
    def domain(self):
        return self.parameters.get('domain')

    @property
    def uri(self):
        return f'{self.hostname}@{self.domain}'

    @property
    def location(self):
        return self.connection_group.connection_group_id if self.connection_group else 'ROOT'

    def as_payload(self):
        payload = make_guacamole_connection_payload(
            connection_name=self.connection_name,
            location=self.location,
            attrs=self.attrs,
            parameters=self.parameters,
        )
        return payload

    @property
    def campus(self):
        return self.connection_group.campus

    def guacamole_api(self) -> GuacamoleService:
        return GuacamoleServer.get_active_endpoint()

    def kill_sessions(self, api=None):
        api = api or self.guacamole_api()
        api.kill_active_session(self.connection_id)

    #

    def _create_guacamole_connection(self):
        payload = self.as_payload()
        api = self.guacamole_api()
        self.connection_id = api.sync_connection(connection_id=self.connection_id, payload=payload)

    #

    def delete_connection(self):
        api = self.guacamole_api()
        api.remove_connection(self.connection_id)

    def save(self, *args, **kwargs):
        self._create_guacamole_connection()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.delete_connection()
        super().delete(*args, **kwargs)

    def can_change(self, user):
        return pode_gerenciar_laboratorio_guacamole(user, self)

    def can_delete(self, user):
        return pode_gerenciar_laboratorio_guacamole(user, self)


def sincronizar_laboratorio_guacamole(grupo, membros):
    api = GuacamoleServer.get_active_endpoint()
    api.add_group(grupo)
    for membro in membros:
        api.get_or_create_user(membro)
        api.add_member_to_group(grupo, membro)


def remover_laboratorio_guacamole(grupo):
    api = GuacamoleServer.get_active_endpoint()
    api.remove_group(grupo)


def remover_guacamole_user_from(grupo, membro):
    api = GuacamoleServer.get_active_endpoint()
    api.remove_member_from_group(grupo, membro)
