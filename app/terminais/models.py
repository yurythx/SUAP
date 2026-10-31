from datetime import datetime

from djtools.db import models
from ponto.models import Maquina


class DispositivoStatus(models.TextChoices):
    ONLINE = 'online', 'Online'
    OFFLINE = 'offline', 'Offline'
    UPDATING = 'updating', 'Updating'


class DeploymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class UpdateStatusChoices(models.TextChoices):
    PENDING = 'pending', 'Pending'
    DOWNLOADING = 'downloading', 'Downloading'
    INSTALLING = 'installing', 'Installing'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'


class ComponentChoices(models.TextChoices):
    BACKEND = 'backend', 'Backend'
    DAEMOM = 'daemon', 'Daemon'
    FRONTEND = 'frontend', 'Frontend'
    OTA_AGENT = 'ota_agent', 'OTA Agent'


class Dispositivo(models.ModelPlus):
    dispositivo_id = models.CharField('Dispositivo', help_text='Id do dispositivo', max_length=255, unique=True)
    maquina = models.ForeignKey('ponto.Maquina', verbose_name='Máquina', on_delete=models.CASCADE, related_name='dispositivos')

    current_version = models.CharField('Versão Atual', max_length=255)

    status = models.CharField(
        max_length=20,
        choices=DispositivoStatus.choices,
    )

    last_seen = models.DateTimeField('Última interação', null=True, blank=True)
    created_at = models.DateTimeField('Criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Dispositivo'
        verbose_name_plural = 'Dispositivos'

    @staticmethod
    def registrar(dispositivo_id, ip_maquina):
        maquina = Maquina.objects.filter(ip=ip_maquina).first()

        if maquina is None:
            raise ValueError(f'Maquina com IP {ip_maquina} não encontrada.')

        dispositivo, created = Dispositivo.objects.get_or_create(
            dispositivo_id=dispositivo_id,
            defaults={
                'maquina': maquina,
                'current_version': 'unknown',
                'status': DispositivoStatus.OFFLINE,
                'last_seen': datetime.now(),
            },
        )

        if not created:
            dispositivo.last_seen = datetime.now()
            dispositivo.save()

        return dispositivo

    def registrar_heartbeat(self, versao, ip, uptime):
        self.last_seen = datetime.now()
        self.current_version = versao
        self.status = DispositivoStatus.ONLINE
        self.save()

        heartbeat = DispositivoHeartbeat.objects.create(dispositivo=self, versao=versao, ip=ip, uptime=uptime)

        return heartbeat


class DispositivoHeartbeat(models.ModelPlus):
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, related_name='heartbeats')
    versao = models.CharField('Versão', max_length=255)
    ip = models.GenericIPAddressField()
    uptime = models.IntegerField(help_text='Uptime em segundos')
    created_at = models.DateTimeField('Criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Dispositivo Heartbeat'
        verbose_name_plural = 'Dispositivo Heartbeats'


class Release(models.ModelPlus):
    versao = models.CharField('Versão', max_length=255, unique=True)
    descricao = models.TextField('Descrição')
    created_at = models.DateTimeField('Criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Release'
        verbose_name_plural = 'Releases'


class Artefato(models.ModelPlus):
    release = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='artefatos')
    componente = models.CharField('Componente', max_length=20, choices=ComponentChoices)
    url = models.URLField(blank=True, null=True)
    checksum = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = 'Artefato'
        verbose_name_plural = 'Artefatos'
        unique_together = [
            ['release', 'componente'],
        ]


class Deployment(models.ModelPlus):
    release = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='deployments')
    rollout_percentage = models.IntegerField('Percentual de Atualização', default=100)
    started_at = models.DateTimeField('Iniciado em')
    status = models.CharField(
        max_length=20,
        choices=DeploymentStatus.choices,
        default=DeploymentStatus.PENDING,
    )

    qtd_esperada = models.IntegerField('Quantidade Esperada', default=0)

    class Meta:
        verbose_name = 'Deployment'
        verbose_name_plural = 'Deployments'

    def save(self, *args, **kwargs):
        if not self.started_at:
            self.started_at = datetime.now()
        super().save(*args, **kwargs)

    @property
    def dispositivos(self):
        return Dispositivo.objects.filter(id__in=self.updatestatus_set.all().values_list('dispositivo_id', flat=True))

    def selecione_dispositivos(self):
        selecionados = UpdateStatus.objects.filter(deploy=self)

        dispositivos_para_atualizar = Dispositivo.objects.exclude(id__in=selecionados.values_list('dispositivo_id', flat=True))

        for dispositivo in dispositivos_para_atualizar:
            UpdateStatus.objects.create(deploy=self, dispositivo=dispositivo, status=UpdateStatusChoices.PENDING)

    def registrar_report_update(self, dispositivo, version, status):
        update_status, created = UpdateStatus.objects.get_or_create(
            deploy=self,
            dispositivo=dispositivo,
            defaults={
                'status': status,
            },
        )

        if not created:
            update_status.status = status
            update_status.save()

        return update_status

    def atualiza_status(self):
        total = UpdateStatus.objects.filter(deploy=self).count()
        success = UpdateStatus.objects.filter(deploy=self, status=UpdateStatusChoices.SUCCESS).count()
        failed = UpdateStatus.objects.filter(deploy=self, status=UpdateStatusChoices.FAILED).count()

        if total == 0:
            self.status = DeploymentStatus.PENDING
        elif success + failed < total:
            self.status = DeploymentStatus.IN_PROGRESS
        elif success + failed == total:
            self.status = DeploymentStatus.COMPLETED if failed == 0 else DeploymentStatus.FAILED

        self.save()


class UpdateStatus(models.ModelPlus):
    deploy = models.ForeignKey(Deployment, on_delete=models.CASCADE)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=UpdateStatusChoices.choices,
    )
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Update Status'
        verbose_name_plural = 'Update Statuses'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.deploy.atualiza_status()
