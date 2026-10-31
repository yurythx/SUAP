from django.contrib import admin
from django.contrib.admin.filters import SimpleListFilter
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_, in_group
from edu.models.diretorias import Diretoria
from etep.forms import AcompanhamentoForm, SolicitacaoAcompanhamentoForm
from etep.models import (
    Acompanhamento,
    Atividade,
    Categoria,
    Documento,
    Encaminhamento,
    RegistroAcompanhamento,
    SolicitacaoAcompanhamento,
    TipoAtividade,
    TipoDocumento,
)


class AcompanhamentoAdmin(ModelAdminPlus):
    list_display = ('get_foto', 'get_aluno', 'get_situacao', 'get_categorias', 'get_encaminhamentos', 'get_interessados')
    list_filter = (
        CustomTabListFilter,
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus__diretoria',
        'acompanhamentocategoria__categoria',
        'acompanhamentoencaminhamento__encaminhamento',
    )
    list_display_icons = True
    search_fields = ('id', 'aluno__pessoa_fisica__nome', 'aluno__matricula')
    ordering = ('-data',)
    form = AcompanhamentoForm
    list_per_page = 25
    show_count_on_tabs = True

    def get_queryset(self, request, manager=None, **kwargs):
        return (
            super()
            .get_queryset(request, Acompanhamento.locals)
            .select_related(
                'aluno__curso_campus__diretoria__setor',
                'aluno__curso_campus__diretoria__setor__uo',
                'aluno',
                'aluno__curso_campus',
                'aluno__curso_campus__diretoria',
                'aluno__pessoa_fisica',
            )
        )

    def get_list_filter(self, request):
        filters = super().get_list_filter(request)
        if request.user.groups.filter(name__in=['etep Administrador', 'Membro ETEP']).exists():
            filters = (*filters, 'interessado__vinculo')
        return filters

    def get_foto(self, obj):
        img_src = obj.aluno.get_foto_75x100_url()
        return mark_safe(f'<img class="img-inside-container" src="{img_src}"/>')

    get_foto.short_description = 'Foto'

    def get_aluno(self, obj):
        return mark_safe(f'<a href="{obj.aluno.get_absolute_url()}?tab=acompanhamento_etep">{obj.aluno}</a>')

    get_aluno.short_description = 'Aluno'
    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'

    def get_situacao(self, obj):
        situacao = obj.get_situacao()
        if situacao == RegistroAcompanhamento.EM_ACOMPANHAMENTO:
            status = 'alert'
        elif situacao == RegistroAcompanhamento.ACOMPANHAMENTO_FINALIZADO:
            status = 'success'
        else:
            status = 'error'
        return mark_safe(f'<span class="status status-{status}">{obj.get_situacao_display()}</span>')

    get_situacao.short_description = 'Situação'

    def get_interessados(self, obj):
        vinculos = obj.get_interessados()
        lista = ''
        if not vinculos:
            return '-'
        for vinculo in vinculos:
            lista += f'<li>{format_(vinculo.pessoa)}</li>'
        return mark_safe(f'<ul>{lista}</ul>')

    get_interessados.short_description = 'Interessados'

    def get_categorias(self, obj):
        categorias = obj.acompanhamentocategoria_set.all().values_list('categoria__nome', flat=True)
        if not categorias:
            return None
        return mark_safe('<ul><li>{}</li></ul>'.format('</li><li>'.join(categorias)))

    get_categorias.short_description = 'Categorias'

    def get_encaminhamentos(self, obj):
        encaminhamentos = list(obj.acompanhamentoencaminhamento_set.all().values_list('encaminhamento__nome', flat=True))
        if not encaminhamentos:
            return None
        return mark_safe('<ul><li>{}</li></ul>'.format('</li><li>'.join(encaminhamentos)))

    get_encaminhamentos.short_description = 'Encaminhamentos'

    def get_tabs(self, request):
        return ['tab_acompanhamento_prioritario', 'tab_em_acompanhamento', 'tab_acompanhamento_finalizado', 'tab_acompanhamento_nao_finalizado']

    def tab_acompanhamento_nao_finalizado(self, request, queryset):
        return queryset.nao_finalizados()

    tab_acompanhamento_nao_finalizado.short_description = 'Não Finalizados'

    def tab_acompanhamento_prioritario(self, request, queryset):
        return queryset.prioritarios()

    tab_acompanhamento_prioritario.short_description = 'Prioritários'

    def tab_em_acompanhamento(self, request, queryset):
        return queryset.em_acompanhamento()

    tab_em_acompanhamento.short_description = 'Em Acompanhamento'

    def tab_acompanhamento_finalizado(self, request, queryset):
        return queryset.finalizados()

    tab_acompanhamento_finalizado.short_description = 'Finalizados'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        url = '/admin/etep/acompanhamento/'
        if not in_group(request.user, 'etep Administrador') and request.user.get_vinculo().setor:
            diretoria = Diretoria.locals.filter(setor__uo=request.user.get_vinculo().setor.uo).first()
            if diretoria:
                url = f'{url}?aluno__curso_campus__diretoria__id__exact={diretoria.pk}&tab=tab_acompanhamento_nao_finalizado'
        return HttpResponseRedirect(url)


admin.site.register(Acompanhamento, AcompanhamentoAdmin)


class SolicitacaoAcompanhamentoFilter(SimpleListFilter):
    title = 'situação'
    parameter_name = 'situacao'

    def lookups(self, request, model_admin):
        return (('deferida', 'Deferida'), ('indeferida', 'Indeferida'), ('pendente', 'Pendente'))

    def queryset(self, request, queryset):
        if self.value() == 'pendente':
            return queryset.filter(data_avaliacao__isnull=True)
        if self.value() == 'deferida':
            return queryset.filter(atendida=True)
        if self.value() == 'indeferida':
            return queryset.filter(atendida=False, data_avaliacao__isnull=False)


class SolicitacaoAcompanhamentoAdmin(ModelAdminPlus):
    list_display = ('id', 'get_aluno', 'descricao', 'get_categorias', 'get_solicitante', 'data_solicitacao', 'get_avaliador', 'get_acoes')
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'solicitante',
        'avaliador',
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus__diretoria',
        SolicitacaoAcompanhamentoFilter,
    )
    search_fields = (
        'id',
        'solicitante__first_name',
        'solicitante__username',
        'avaliador__first_name',
        'avaliador__username',
        'aluno__pessoa_fisica__nome',
    )
    ordering = ('-data_avaliacao',)
    form = SolicitacaoAcompanhamentoForm
    export_to_xls = True
    show_count_on_tabs = True

    def get_queryset(self, request, manager=None, **kwargs):
        if not manager:
            manager = SolicitacaoAcompanhamento.locals
        return super().get_queryset(request, manager)

    def get_solicitante(self, obj):
        img_src = obj.solicitante.get_vinculo().get_foto_75x100_url()
        return mark_safe(
            f'<div class="person"><div class="photo-circle"><img src="{img_src}" alt="{obj.solicitante}"></div><dl><dt class="visually-hidden">Solicitante</dt><dd>{obj.solicitante}</dd></dl></div>'
        )

    get_solicitante.short_description = 'Solicitante'

    def get_categorias(self, obj):
        categorias = obj.solicitacaoacompanhamentocategoria_set.all().values_list('categoria__nome', flat=True)
        if not categorias:
            return None
        return mark_safe('<ul><li>{}</li></ul>'.format('</li><li>'.join(categorias)))

    get_categorias.short_description = 'Categorias'

    def get_avaliador(self, obj):
        return mark_safe(format_(obj.avaliador))

    get_avaliador.short_description = 'Avaliador'

    def get_aluno(self, obj):
        return mark_safe(f'<a href="{obj.aluno.get_absolute_url()}">{obj.aluno}</a>')

    get_aluno.short_description = 'Aluno'

    def get_action_bar(self, request, **kwargs):
        items = super().get_action_bar(request, True)
        return items

    def get_diretoria(self, obj):
        return mark_safe(obj.get_diretoria())

    get_diretoria.short_description = 'Diretoria'

    def get_acoes(self, obj):
        lista = []
        if obj.data_avaliacao:
            if obj.atendida:
                lista.append('<span class="status status-success">Deferida</span>')
            else:
                lista.append('<span class="status status-error">Indeferida</span>')
        else:
            lista.append('<span class="status status-pendente">Pendente</span>')
        return mark_safe(' '.join(lista))

    get_acoes.short_description = 'Situação'

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_em_acompanhamento', 'tab_finalizados', 'tab_interessados', 'tab_any_data']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes'

    def tab_em_acompanhamento(self, request, queryset):
        return queryset.em_acompanhamento()

    tab_em_acompanhamento.short_description = 'Em Acompanhamento'

    def tab_finalizados(self, request, queryset):
        return queryset.finalizados()

    tab_finalizados.short_description = 'Finalizadas'

    def tab_interessados(self, request, queryset):
        return queryset.interessados()

    tab_interessados.short_description = 'Interessadas'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        url = '/admin/etep/solicitacaoacompanhamento/'
        if not in_group(request.user, 'etep Administrador') and request.user.get_vinculo().setor:
            diretoria = Diretoria.locals.filter(setor__uo=request.user.get_vinculo().setor.uo).first()
            if diretoria:
                url = f'{url}?aluno__curso_campus__diretoria__id__exact={diretoria.pk}'
        return HttpResponseRedirect(url)


admin.site.register(SolicitacaoAcompanhamento, SolicitacaoAcompanhamentoAdmin)


class CategoriaAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    ordering = ('nome', 'descricao')
    search_fields = ('nome', 'descricao')
    list_display_icons = True
    export_to_xls = True


admin.site.register(Categoria, CategoriaAdmin)


class EncaminhamentoAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    ordering = ('nome', 'descricao')
    search_fields = ('nome', 'descricao')
    list_display_icons = True
    export_to_xls = True


admin.site.register(Encaminhamento, EncaminhamentoAdmin)


class TipoAtividadeAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    ordering = ('nome', 'descricao')
    search_fields = ('nome', 'descricao')
    list_display_icons = True
    export_to_xls = True


admin.site.register(TipoAtividade, TipoAtividadeAdmin)


class TipoDocumentoAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    ordering = ('nome', 'descricao')
    search_fields = ('nome', 'descricao')
    list_display_icons = True
    export_to_xls = True


admin.site.register(TipoDocumento, TipoDocumentoAdmin)


class AtividadeAdmin(ModelAdminPlus):
    list_display = ('titulo', 'descricao', 'tipo', 'data_inclusao', 'data_inicio_atividade', 'data_fim_atividade', 'get_visibilidade', 'usuario')
    ordering = ('-id',)
    list_filter = (CustomTabListFilter, 'tipo')
    search_fields = ('titulo', 'descricao')
    date_hierarchy = 'data_inicio_atividade'
    list_display_icons = True
    export_to_xls = True

    def get_tabs(self, request):
        return ['tab_meu_campus', 'tab_compartilhadas']

    def tab_meu_campus(self, request, queryset):
        return queryset.filter(usuario__vinculo__setor__uo=request.user.get_vinculo().setor.uo)

    tab_meu_campus.short_description = 'Meu Campus'

    def tab_compartilhadas(self, request, queryset):
        return queryset.exclude(usuario__vinculo__setor__uo=request.user.get_vinculo().setor.uo)

    tab_compartilhadas.short_description = 'Compartilhadas'

    def get_queryset(self, request, manager=None, **kwargs):
        if not manager:
            manager = Atividade.locals
        return super().get_queryset(request, manager)


admin.site.register(Atividade, AtividadeAdmin)


class DocumentoAdmin(ModelAdminPlus):
    list_display = ('arquivo', 'tipo', 'get_atividade')
    search_fields = ('arquivo',)
    ordering = ('-id',)
    list_filter = (CustomTabListFilter, 'tipo', 'atividade__tipo')
    list_display_icons = True
    export_to_xls = True
    show_count_on_tabs = True

    def get_atividade(self, obj):
        return mark_safe(f'<a href="{obj.atividade.get_absolute_url()}">{obj.atividade}</a>')

    get_atividade.short_description = 'Atividade'
    get_atividade.admin_order_field = 'atividade__pk'

    def get_tabs(self, request):
        return ['tab_meu_campus', 'tab_compartilhadas']

    def tab_meu_campus(self, request, queryset):
        return queryset.filter(atividade__usuario__vinculo__setor__uo=request.user.get_vinculo().setor.uo)

    tab_meu_campus.short_description = 'Meu Campus'

    def tab_compartilhadas(self, request, queryset):
        return queryset.exclude(atividade__usuario__vinculo__setor__uo=request.user.get_vinculo().setor.uo)

    tab_compartilhadas.short_description = 'Compartilhadas'

    def get_queryset(self, request, manager=None, **kwargs):
        if not manager:
            manager = Documento.locals
        return super().get_queryset(request, manager)


admin.site.register(Documento, DocumentoAdmin)
