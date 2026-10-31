from django.contrib import admin
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin.options import ModelAdminPlus
from terminais.models import Artefato, Deployment, Dispositivo, Release, UpdateStatus, UpdateStatusChoices


@admin.register(Dispositivo)
class DispositivoAdmin(ModelAdminPlus):
    list_display = ('dispositivo_id', 'maquina__descricao', 'get_versao', 'status', 'get_last_seen')
    list_filter = ('status',)
    list_display_icons = True

    readonly_fields = ('status', 'last_seen', 'created_at')

    fieldsets = (
        (
            '',
            {'fields': ('maquina',)},
        ),
        (
            'Dados do dispositivo',
            {
                'fields': (
                    'dispositivo_id',
                    'current_version',
                )
            },
        ),
        (
            'Sincronização',
            {
                'fields': (
                    'status',
                    'last_seen',
                    'created_at',
                )
            },
        ),
    )

    @admin.display(description='Dispositivo')
    def get_dispositivo(self, obj):
        return obj.dispositivo_id

    @admin.display(description='Versão')
    def get_versao(self, obj):
        return obj.current_version

    @admin.display(description='Última atualização')
    def get_last_seen(self, obj):
        return obj.last_seen


class ArtefatoInline(admin.StackedInline):
    model = Artefato
    extra = 1


@admin.register(Release)
class ReleaseAdmin(ModelAdminPlus):
    list_display = ('versao', 'get_artefatos', 'created_at')
    list_display_icons = True

    inlines = [ArtefatoInline]

    @admin.display(description='Artefatos')
    def get_artefatos(self, obj):
        artefatos = obj.artefatos.all()

        ret_str = ['<ul>']

        for artefato in artefatos:
            ret_str.append(f'<li>{artefato.componente}</li>')

        ret_str.append('</ul>')

        return mark_safe(''.join(ret_str))


@admin.register(Deployment)
class DeploymentAdmin(ModelAdminPlus):
    list_display = ('release', 'rollout_percentage', 'started_at', 'get_statistica', 'status', 'get_opcoes')
    list_filter = (
        'release',
        'status',
    )
    list_display_icons = True

    fieldsets = (
        (
            '',
            {'fields': ('release',)},
        ),
        (
            'Configuração',
            {
                'fields': (
                    'rollout_percentage',
                    'started_at',
                )
            },
        ),
    )

    @admin.display(description='Estatística')
    def get_statistica(self, obj):
        wait_status = [
            UpdateStatusChoices.PENDING,
            UpdateStatusChoices.DOWNLOADING,
            UpdateStatusChoices.INSTALLING,
        ]

        result = UpdateStatus.objects.filter(deploy=obj).aggregate(
            total=Count('id'),
            success=Count('id', filter=Q(status=UpdateStatusChoices.SUCCESS)),
            failed=Count('id', filter=Q(status=UpdateStatusChoices.FAILED)),
            wait=Count('id', filter=Q(status__in=wait_status)),
        )

        ret_str = f"""
        <dl class="definition-list">
            <dt>Total</dt><dd>{result['total']}</dd>
            <dt>Atualizados</dt><dd>{result['success']}</dd>
            <dt>Aguardando</dt><dd>{result['wait']}</dd>
            <dt>Falhas</dt><dd>{result['failed']}</dd>
        </dl>"""

        return mark_safe(ret_str)

    @admin.display(description='Opções')
    def get_opcoes(self, obj):
        ret_str = f"""
        <ul class="action-bar">
            <li><a class="btn" href="/admin/terminais/deployment/processar/{obj.id}/">Selecionar Dispositivos</a></li>
        </ul>"""
        return mark_safe(ret_str)

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('processar/<int:deployment_id>/', self.url_wrap(self.selecionar_dispositivos), name='terminais_deployment_dispositivos'),
        ]

        return my_urls + urls

    def selecionar_dispositivos(self, request, deployment_id):
        deployment = self.get_object(request, deployment_id)

        if deployment:
            deployment.selecione_dispositivos()
            self.message_user(request, 'Dispositivos selecionados para atualização.')
        else:
            self.message_user(request, 'Deployment não encontrado.', level='error')

        return redirect('/admin/terminais/deployment/')
