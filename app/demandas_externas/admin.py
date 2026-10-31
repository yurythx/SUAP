from django.contrib import admin
from django.db.models import Q
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from demandas_externas.forms import PeriodoForm
from demandas_externas.models import Demanda, Periodo, PublicoAlvo, TipoAcao
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.tags import icon


class PeriodoAdmin(ModelAdminPlus):
    form = PeriodoForm
    title = 'Períodos de Recebimento de Demandas'
    list_display = ('icones', 'titulo', 'data_inicio', 'data_termino', 'get_uos')
    ordering = ('data_inicio',)
    search_fields = ('titulo',)
    export_to_xls = True
    list_filter = ('campi',)
    list_per_page = 20
    list_display_icons = False
    list_display_links = None
    show_count_on_tabs = True

    def get_uos(self, obj):
        return ', '.join(obj.campi.all().values_list('sigla', flat=True))

    get_uos.short_description = 'Campi'

    def icones(self, obj):
        return mark_safe(
            ''.join([icon('view', f'/demandas_externas/ver_periodo/{obj.id}/'), icon('edit', f'/admin/demandas_externas/periodo/{obj.id}/change/')])
        )

    icones.short_description = 'Ações'
    icones.allow_tags = 'Ações'


admin.site.register(Periodo, PeriodoAdmin)


class AnoRegistroFilter(admin.SimpleListFilter):
    title = 'Ano de Registro'
    parameter_name = 'ano_registro'

    def lookups(self, request, model_admin):
        anos = []

        for data in Demanda.objects.all().dates('cadastrada_em', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(cadastrada_em__year=self.value())


class AnoConclusaoFilter(admin.SimpleListFilter):
    title = 'Ano de Conclusão'
    parameter_name = 'ano_conclusao'

    def lookups(self, request, model_admin):
        anos = []

        for data in Demanda.objects.all().dates('concluida_em', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(concluida_em__year=self.value())


class DemandaAdmin(ModelAdminPlus):
    title = 'Demandas'
    list_display = (
        'icones',
        'nome',
        'identificador',
        'descricao',
        'qtd_prevista_beneficiados',
        'campus_indicado',
        'campus_atendimento',
        'responsavel',
        'descricao_atendimento',
        'prioridade',
        'cadastrada_em',
        'concluida_em',
    )
    ordering = ('cadastrada_em',)
    search_fields = ('nome', 'identificador')
    export_to_xls = True
    list_filter = (CustomTabListFilter, 'municipio', 'campus_atendimento', 'area_tematica', AnoRegistroFilter, AnoConclusaoFilter, 'tipo_acao')
    list_per_page = 20
    list_display_icons = False
    show_count_on_tabs = True
    list_xls_display = (
        'nome',
        'identificador',
        'descricao',
        'qtd_prevista_beneficiados',
        'campus_indicado',
        'campus_atendimento',
        'responsavel',
        'descricao_atendimento',
        'cadastrada_em',
        'concluida_em',
    )

    def icones(self, obj):
        texto = icon('view', f'/demandas_externas/demanda/{obj.id}/')
        return mark_safe(texto)

    icones.short_description = '-'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('demandas_externas.add_publicoalvo'):
            return qs
        elif request.user.has_perm('demandas_externas.view_publicoalvo'):
            return qs.filter(Q(campus_atendimento=get_uo(request.user)) | Q(campus_atendimento__isnull=True))
        elif request.user.has_perm('demandas_externas.pode_ver_todas_demandas_externas'):
            return qs.exclude(situacao__in=[Demanda.SUBMETIDA, Demanda.NAO_ACEITA])
        else:
            return qs.filter(campus_atendimento=get_uo(request.user)).exclude(situacao__in=[Demanda.SUBMETIDA, Demanda.NAO_ACEITA])

    def get_tabs(self, request):
        return ['tab_submetidas', 'tab_aceitas', 'tab_espera', 'tab_atendimento', 'tab_atendidas', 'tab_nao_atendidas', 'tab_nao_aceitas']

    def tab_submetidas(self, request, queryset):
        return queryset.filter(situacao=Demanda.SUBMETIDA)

    tab_submetidas.short_description = 'Submetidas'

    def tab_aceitas(self, request, queryset):
        return queryset.exclude(situacao__in=[Demanda.NAO_ACEITA, Demanda.SUBMETIDA])

    tab_aceitas.short_description = 'Aceitas'

    def tab_espera(self, request, queryset):
        return queryset.filter(situacao=Demanda.EM_ESPERA)

    tab_espera.short_description = 'Em Espera'

    def tab_atendimento(self, request, queryset):
        return queryset.filter(situacao=Demanda.EM_ATENDIMENTO)

    tab_atendimento.short_description = 'Em Atendimento'

    def tab_atendidas(self, request, queryset):
        return queryset.filter(situacao=Demanda.ATENDIDA)

    tab_atendidas.short_description = 'Atendidas'

    def tab_nao_atendidas(self, request, queryset):
        return queryset.filter(situacao=Demanda.NAO_ATENDIDA)

    tab_nao_atendidas.short_description = 'Não Atendidas'

    def tab_nao_aceitas(self, request, queryset):
        return queryset.filter(situacao=Demanda.NAO_ACEITA)

    tab_nao_aceitas.short_description = 'Não Aceitas'


admin.site.register(Demanda, DemandaAdmin)


class TipoAcaoAdmin(ModelAdminPlus):
    title = 'Tipo de Ação de Extensão'
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    export_to_xls = True
    list_filter = ('ativo',)
    list_per_page = 20
    list_display_icons = False
    show_count_on_tabs = True


admin.site.register(TipoAcao, TipoAcaoAdmin)


class PublicoAlvoAdmin(ModelAdminPlus):
    title = 'Público-Alvo'
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    export_to_xls = True
    list_filter = ('ativo',)
    list_per_page = 20
    list_display_icons = False
    show_count_on_tabs = True


admin.site.register(PublicoAlvo, PublicoAlvoAdmin)
