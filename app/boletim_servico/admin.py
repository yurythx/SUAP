from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

from boletim_servico import models
from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus, TabularInlinePlus
from documento_eletronico.models import Documento

from .forms import BoletimProgramadoForm, ConfiguracaoSetorBoletimForm


class ConfiguracaoSetorInline(TabularInlinePlus):
    model = models.ConfiguracaoSetorBoletim
    form = ConfiguracaoSetorBoletimForm
    min_num = 1
    extra = 0


class TemBoletimSimpleFilter(admin.SimpleListFilter):
    title = 'Tem boletim ?'
    parameter_name = 'tem_boletim'

    def lookups(self, request, model_admin):
        return (('Sim', 'Sim'), ('Não', 'Não'))

    def queryset(self, request, queryset):
        if self.value() in ['Sim', 'Não']:
            return queryset.filter(boletimperiodo__isnull=self.value() == 'Não').distinct()


@admin.register(models.BoletimProgramado)
class BoletimProgramadoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('titulo', 'campus', 'link', 'get_quantidade_boletins', 'acoes')
    list_filter = ['tipo_documento', TemBoletimSimpleFilter]
    inlines = [ConfiguracaoSetorInline]
    form = BoletimProgramadoForm

    def get_changeform_initial_data(self, request):
        return {'criado_por': request.user, 'nivel_acesso': [Documento.NIVEL_ACESSO_PUBLICO]}

    @mark_safe
    def link(self, obj):
        if obj.programado:
            url = reverse('admin:boletim_servico_boletimdiario_changelist') + f'?boletim_programado={obj.pk}'
        else:
            url = reverse('admin:boletim_servico_boletimperiodo_changelist') + f'?boletim_programado={obj.pk}'

        return f'<a href="{url}" class="btn default">Visualizar Boletins</a>'

    def acoes(self, obj):
        return mark_safe(f'<a href="/boletim_servico/gerar_boletim_servico/{obj.pk}/" class="btn">Gerar Boletim</a>')

    acoes.short_description = 'Ações'

    def get_quantidade_boletins(self, obj):
        return obj.boletimperiodo_set.all().count()

    get_quantidade_boletins.short_description = 'Quantidade de boletins'

    def save_model(self, request, obj, form, change):
        uo = get_uo(request.user)
        obj.campus = uo
        if not obj.pk:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        user = request.user
        if user.groups.filter(name='Gerente de Boletins de Serviço') and not user.groups.filter(name='Gerente Sistêmico de Boletins de Serviço'):
            uo = get_uo(user)
            queryset = queryset.filter(campus=uo)
        return queryset


@admin.register(models.BoletimDiario)
class BoletimDiarioAdmin(ModelAdminPlus):
    list_display = ('titulo', 'situacao', 'data_criacao')
    list_filter = ('boletim_programado', 'situacao')
    date_hierarchy = 'data'
    ordering = ['-data']
    list_display_links = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return not obj

    def get_list_filter(self, request):
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            return []
        return super().get_list_filter(request)

    def get_list_display(self, request):
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            return ('titulo', 'data_criacao')
        return super().get_list_display(request)

    @mark_safe
    def titulo(self, obj):
        if obj.possui_link:
            return f'<a href="{obj.arquivo.url}">{obj}</a>'
        return f'{obj}'

    titulo.short_description = 'Título'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            qs = qs.filter(situacao=models.BoletimDiario.Situacao.FINALIZADO)
        return qs


@admin.register(models.BoletimPeriodo)
class BoletimPeriodoAdmin(ModelAdminPlus):
    list_display = ('titulo', 'situacao', 'data_criacao', 'acoes')
    list_filter = ('boletim_programado', 'situacao')
    date_hierarchy = 'data_inicio'
    ordering = ['-data_inicio']
    list_display_links = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return not obj

    def get_list_filter(self, request):
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            return []
        return super().get_list_filter(request)

    def get_list_display(self, request):
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            return ('titulo', 'data_criacao')
        return super().get_list_display(request)

    @mark_safe
    def titulo(self, obj):
        if obj.possui_link:
            return f'<a href="{obj.arquivo.url}">{obj}</a>'
        return f'{obj}'

    titulo.short_description = 'Título'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if not request.user.has_perm('boletim_servico.add_boletimprogramado'):
            qs = qs.filter(situacao=models.BoletimPeriodo.Situacao.FINALIZADO)
        return qs

    def acoes(self, obj):
        opcoes = '<ul class="action-bar">'

        usuario = self.request.user

        if obj.situacao not in [3, 4]:
            opcoes += f'<li><a href="/boletim_servico/reprocessar_boletim/{obj.id}/" class="btn primary">Reprocessar Boletim</a></li>'

        if usuario.has_perm('boletim_servico.delete_boletimperiodo'):
            opcoes += f'<li><a href="/boletim_servico/remover_boletim_periodo/{obj.id}/" class="btn danger">Excluir</a></li>'

        opcoes += '</ul>'
        return mark_safe(opcoes)

    acoes.short_description = 'Ações'
