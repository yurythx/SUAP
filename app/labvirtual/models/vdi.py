from django.urls import reverse

#
from comum.models import UnidadeOrganizacional
from djtools.db import models
from labvirtual.helpers import DictObj
from labvirtual.managers import DesktopPoolManager
from labvirtual.perms import pode_gerenciar_solicitacao_labvirtual
from labvirtual.services import VMWareHorizonService


class VDIServer(models.ModelPlus):
    name = models.CharFieldPlus(verbose_name='Nome', unique=True, max_length=100)
    hostname = models.CharFieldPlus(verbose_name='Hostname', help_text='Ex.: "niteroi".', blank=False, null=False, max_length=255)
    domain = models.CharFieldPlus(verbose_name='Domain', help_text='Ex.: "ifrn.local".', blank=False, null=False, max_length=255)
    username = models.CharFieldPlus(verbose_name='Username', blank=False, null=False, max_length=50)
    password = models.CharFieldPlus(verbose_name='Password', blank=False, null=False, max_length=50)
    priority = models.IntegerFieldPlus(verbose_name='Prioridade', default=1000)
    active = models.BooleanField(verbose_name='Serviço ativo', default=True)

    class Meta:
        verbose_name = 'Configuração do Servidor VDI'
        verbose_name_plural = 'Configurações dos Servidores VDI'

    def __str__(self):
        return self.name

    @property
    def api(self) -> VMWareHorizonService:
        return VMWareHorizonService(hostname=self.hostname, username=self.username, password=self.password, domain=self.domain)

    @classmethod
    def get_active_server(cls):
        return cls.objects.filter(active=True).order_by('priority').first()

    @classmethod
    def get_active_endpoint(cls) -> VMWareHorizonService:
        server = cls.get_active_server()
        if server:
            return server.api
        raise Exception('Não existem servidores guacamole ativos configurados.')


class DesktopPool(models.ModelPlus):
    #
    name = models.CharField(max_length=90, verbose_name='Nome', help_text='Nome do Laboratório')
    description = models.CharField(max_length=200, verbose_name='Descrição')
    location = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True, blank=True)
    #
    desktop_pool_id = models.models.CharField(verbose_name='Identificador', null=False, max_length=200)
    #
    objects = DesktopPoolManager()

    class Meta:
        verbose_name = 'Laboratório Virtual'
        verbose_name_plural = 'Laboratórios Virtuais'

    def __str__(self):
        return self.name

    @property
    def api(self) -> VMWareHorizonService:
        return VDIServer.get_active_endpoint()

    def get_absolute_url(self):
        return reverse('labvirtual:desktop_pool_detail', kwargs={'pk': self.pk})

    def capacidade(self):
        return self.api.number_max_of_machines(self.desktop_pool_id)

    def get_membros_ativos(self):
        ad_users_or_groups = self.api.get_ids_users_or_groups_from_desktop_pool(self.desktop_pool_id)
        membros_ativos = [user_or_group['name'] for user_or_group in ad_users_or_groups]
        return membros_ativos

    def get_machines(self):
        machines = self.api.get_machines_from_desktop_pool(self.desktop_pool_id)
        return [DictObj(machine) for machine in machines]

    def get_desktop_pool_info(self):
        desktop_pool = self.api.get_desktop_pool(desktop_pool_id=self.desktop_pool_id)
        return DictObj(desktop_pool)

    def get_ad_groups(self):
        ad_groups = self.api.get_ad_groups_from_desktop_pool(self.desktop_pool_id)
        return [DictObj(group) for group in ad_groups]

    def pode_solicitar(self, user):
        autorizado = False
        if not user.is_anonymous:
            autorizado = pode_gerenciar_solicitacao_labvirtual(user, self)
            if not autorizado and user.has_perm('labfisico.add_solicitacaolabfisico'):
                autorizado = DesktopPool.objects.my_desktop_pools(user).filter(id=self.id).exists()
        return autorizado
