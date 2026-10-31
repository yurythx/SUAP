from django.contrib import admin

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import AulaCampoForm, ConfiguracaoSeguroForm
from edu.models import AulaCampo, ConfiguracaoSeguro


class ConfiguracaoSeguroAdmin(ModelAdminPlus):
    list_display = ('seguradora', 'data_inicio_contrato', 'data_fim_contrato', 'valor_contrato', 'valor_repasse_pessoa')
    search_fields = ('seguradora__nome',)
    ordering = ('id',)
    list_display_icons = True
    form = ConfiguracaoSeguroForm

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('seguradora',),
                    ('data_inicio_contrato', 'data_fim_contrato'),
                    ('valor_contrato',),
                    ('valor_repasse_pessoa',),
                    'fiscais',
                    'ativa',
                )
            },
        ),
        ('Dados para Envio da Planilha', {'fields': ('email_disparo_planilha',)}),
    )


admin.site.register(ConfiguracaoSeguro, ConfiguracaoSeguroAdmin)


class AulaCampoAdmin(ModelAdminPlus):
    list_filter = (CustomTabListFilter, 'uo', 'configuracao_seguro', 'situacao')
    list_display = (
        'id',
        'uo',
        'descricao',
        'finalidade',
        'data_partida',
        'data_chegada',
        'roteiro',
        'situacao',
        'get_qtd_servidores_participantes',
        'get_qtd_alunos_participantes',
    )
    search_fields = ('descricao', 'roteiro')
    ordering = ('data_partida',)
    list_display_icons = True
    form = AulaCampoForm
    date_hierarchy = 'data_partida'

    def get_tabs(self, request):
        return ['tab_com_alunos', 'tab_sem_alunos']

    def tab_sem_alunos(self, request, queryset):
        return queryset.filter(alunos__isnull=True)

    tab_sem_alunos.short_description = 'Sem Alunos Participantes'

    def tab_com_alunos(self, request, queryset):
        return queryset.exclude(alunos__isnull=True)

    tab_com_alunos.short_description = 'Com Alunos Participantes'

    def get_qtd_servidores_participantes(self, obj):
        return obj.responsaveis.count()

    get_qtd_servidores_participantes.short_description = 'Qtd. de Servidores Participantes'

    def get_qtd_alunos_participantes(self, obj):
        return obj.alunos.count()

    get_qtd_alunos_participantes.short_description = 'Qtd. de Alunos Participantes'

    fieldsets = (
        (
            'Dados gerais',
            {'fields': (('configuracao_seguro',), ('uo',), ('descricao',), ('finalidade',), ('roteiro',), ('data_partida', 'data_chegada'))},
        ),
        ('Participantes', {'fields': ('responsaveis', 'arquivo')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request, AulaCampo.locals)


admin.site.register(AulaCampo, AulaCampoAdmin)
