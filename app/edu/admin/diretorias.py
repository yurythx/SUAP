from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import CalendarioAcademicoForm, DiretoriaForm
from edu.models import CalendarioAcademico, Diretoria


class DiretoriaAdmin(ModelAdminPlus):
    list_display = ('setor', 'campus', 'tipo')
    search_fields = ('setor__sigla',)
    form = DiretoriaForm
    fieldsets = DiretoriaForm.fieldsets
    list_filter = (CustomTabListFilter, 'setor__uo', 'tipo')
    list_display_icons = True
    export_to_xls = True

    def campus(self, obj):
        return obj.setor.uo and obj.setor.uo.nome.upper() or '-'

    def get_queryset(self, request):
        return super().get_queryset(request, Diretoria.locals)

    def get_tabs(self, request):
        return ['tab_sem_diretores', 'tab_sem_secretarios', 'tab_sem_coordenadores', 'tab_sem_pedagogos']

    def tab_sem_diretores(self, request, queryset):
        return queryset.sem_diretores()

    tab_sem_diretores.short_description = 'Sem Diretores'

    def tab_sem_secretarios(self, request, queryset):
        return queryset.sem_secretarios()

    tab_sem_secretarios.short_description = 'Sem Secretários'

    def tab_sem_coordenadores(self, request, queryset):
        return queryset.sem_coordenadores()

    tab_sem_coordenadores.short_description = 'Sem Coordenadores'

    def tab_sem_pedagogos(self, request, queryset):
        return queryset.sem_pedagogos()

    tab_sem_pedagogos.short_description = 'Sem Pedagogos'


admin.site.register(Diretoria, DiretoriaAdmin)


class CalendarioAcademicoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'tipo', 'uo', 'diretoria', 'ano_letivo', 'periodo_letivo', 'data_inicio', 'data_fim')
    list_filter = ('tipo', 'ano_letivo', 'periodo_letivo', 'uo', 'diretoria', 'eh_calendario_referencia')
    list_display_icons = True
    search_fields = ('descricao', 'id')
    export_to_xls = True
    form = CalendarioAcademicoForm

    fieldsets = (
        ('Dados gerais', {'fields': (('descricao',), ('uo', 'diretoria', 'tipo'), ('ano_letivo', 'periodo_letivo'), 'eh_calendario_referencia')}),
        ('Espaço Pedagógico', {'fields': (('data_inicio_espaco_pedagogico', 'data_fim_espaco_pedagogico'),)}),
        (
            'Período Letivo',
            {
                'fields': (
                    ('data_inicio', 'data_fim'),
                    ('data_inicio_prova_final', 'data_fim_prova_final'),
                    'data_fechamento_periodo',
                )
            },
        ),
        (
            'Trancamento, Certificação e Aproveitamento',
            {
                'fields': (
                    ('data_inicio_trancamento', 'data_fim_trancamento'),
                    ('data_inicio_certificacao', 'data_fim_certificacao'),
                    ('data_inicio_trancamento2', 'data_fim_trancamento2'),
                    ('data_inicio_certificacao2', 'data_fim_certificacao2'),
                )
            },
        ),
        ('Etapas', {'fields': ('qtd_etapas',)}),
        ('Primera Etapa', {'fields': (('data_inicio_etapa_1', 'data_fim_etapa_1'),)}),
        ('Segunda Etapa', {'fields': (('data_inicio_etapa_2', 'data_fim_etapa_2'),)}),
        ('Terceira Etapa', {'fields': (('data_inicio_etapa_3', 'data_fim_etapa_3'),)}),
        ('Quarta Etapa', {'fields': (('data_inicio_etapa_4', 'data_fim_etapa_4'),)}),
    )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        qs = self.get_queryset(request)
        if qs.exists():
            ano = qs.latest('ano_letivo__ano').ano_letivo.id
            url = f'/admin/edu/calendarioacademico/?ano_letivo__id__exact={ano}'
        else:
            url = '/admin/edu/calendarioacademico/'
        return HttpResponseRedirect(url)

    def get_queryset(self, request):
        return self.model.locals.all()


admin.site.register(CalendarioAcademico, CalendarioAcademicoAdmin)
