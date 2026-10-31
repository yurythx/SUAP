from django.contrib import admin
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon
from pdp_ifrn.forms import RespostaForm
from pdp_ifrn.models import (
    PDP,
    AreaTematica,
    CompetenciaAssociada,
    EnfoqueDesenvolvimento,
    EspecificacaoTipoAprendizagem,
    HistoricoStatusResposta,
    Necessidade,
    PublicoAlvo,
    Resposta,
    TipoAprendizagem,
)


class StatusFilter(admin.SimpleListFilter):
    title = 'Situação'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        status = HistoricoStatusResposta.STATUS_RESPOSTA
        return [(d[0], d[1]) for d in status]

    def queryset(self, request, queryset):
        if self.value():
            qs = [x.id for x in queryset if x.get_ultimo_status == self.value()]
            return queryset.filter(id__in=qs)
        return queryset


class PDPAdmin(ModelAdminPlus):
    list_display_icons = True
    list_filter = ('ano',)
    list_display = ('ano', 'descricao', 'data_inicial', 'data_final', 'preenchimento_habilitado')


class EnfoqueDesenvolvimentoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


class AreaTematicaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


class ObjetoTematicoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)
    # IFMA/Tássio
    list_filter = ['descricao']
    # IFMA/Tássio FIM


class CompetenciaAssociadaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'ativa')


class PublicoAlvoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


class TipoAprendizagemAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'nome',
        'descricao',
    )


class EspecificacaoTipoAprendizagemAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'descricao',
        'tipo_aprendizagem',
    )


class RespostaAdmin(ModelAdminPlus):
    form = RespostaForm
    list_display = ('opcoes', 'pdp', 'servidor', 'campus', 'setor_servidor', 'funcao_servidor', 'data_cadastro', 'get_status')
    list_filter = (
        StatusFilter,
        'pdp',
        'campus',
        'area_tematica',
        'publico_alvo',
        'tipo_aprendizagem',
        'especificacao_tipo_aprendizagem',
        'necessidade',
    )
    search_fields = (
        'servidor__pessoa_fisica__nome',
        'servidor__matricula',
    )
    date_hierarchy = 'data_cadastro'
    list_per_page = 20
    export_to_xls = True

    fieldsets = (
        ('Dados gerais', {'fields': ('pdp',)}),
        (
            'Ação de Desenvolvimento',
            {
                'fields': (
                    'enfoque_desenvolvimento',
                    'enfoque_outros',
                    'area_tematica',
                    'necessidade',
                    'justificativa_necessidade',
                    'competencia_associada',
                    'acao_transversal',
                    'publico_alvo',
                    'setor_beneficiado',
                    'qtd_pessoas_beneficiadas',
                    'tipo_aprendizagem',
                    'especificacao_tipo_aprendizagem',
                    'modalidade',
                    'titulo_necessidade',
                    'ano_termino_acao',
                )
            },
        ),
        ('Custos desta Ação', {'fields': ('onus_inscricao', 'valor_onus_inscricao')}),
        # ('Centro de Formação de Servidores - CFS', {
        #    'fields': ('atendida_pelo_cfs',)
        # }),
    )

    def get_status(self, obj):
        return obj.status_formatado

    get_status.short_description = 'Situação'

    def opcoes(self, obj):
        texto = icon('view', obj.get_absolute_url())
        if obj.pode_editar():
            texto = texto + icon('edit', f'/admin/pdp_ifrn/resposta/{obj.pk:d}/change/')
            texto = texto + icon('delete', f'/admin/pdp_ifrn/resposta/{obj.pk:d}/delete/')
        texto = texto + '</ul>'
        return mark_safe(texto)

    opcoes.short_description = 'Opções'

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar()
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar()
        return super().has_delete_permission(request, obj)

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser or request.user.has_group_cached('Coordenador de PDP Sistêmico'):
            return qs
        if request.user.has_group_cached('Coordenador de PDP'):
            return qs.filter(campus=get_uo(request.user))
        return qs.filter(servidor=request.user.get_relacionamento())

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'PDP',
            'Situação',
            'Data da Resposta',
            'Servidor',
            'Campus',
            'Setor do Servidor',
            'Função do Servidor',
            'Qual a área que melhor identifica a temática relacionada a essa necessidade de desenvolvimento? (Macros)',
            'A ação de desenvolvimento para essa necessidade está relacionada a qual área temática dos Sistemas Estruturadores do Poder Executivo Federal?',
            'Que necessidade de desenvolvimento o Campus/Reitoria possui?',
            'Que resultado essa ação de desenvolvimento trará?',
            'Essa necessidade está associada a quais competências?',
            'Descreva quais são as outras necessidades de desenvolvimento não especificadas',
            f'Essa necessidade de desenvolvimento é transversal, ou seja, comum a múltiplas unidades do {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}?',
            'Qual o público-alvo da ação de desenvolvimento para essa necessidade?',
            f'Qual unidade funcional do {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")} será beneficiada pela ação de desenvolvimento para essa necessidade?',
            'Quantos servidores serão beneficiados pela ação de desenvolvimento para essa necessidade?',
            'A ação de desenvolvimento para essa necessidade deve preferencialmente ser ofertada em qual tipo de aprendizagem?',
            'De acordo com a resposta anterior, qual opção melhor caracteriza o subtipo de aprendizagem?',
            'Modalidade',
            'Título previsto da ação de desenvolvimento',
            'Em caso de já possuir uma opção em consideração, qual o término previsto da ação de desenvolvimento para essa necessidade?',
            'A ação de desenvolvimento pode ser ofertada de modo gratuito? Sim ou não',
            'Se não gratuita, qual o custo total previsto da ação de desenvolvimento para essa necessidade? (R$)',
            # 'A ação de desenvolvimento para essa necessidade pode ser ofertada pelo Centro de Formação de Servidores?',
        ]

        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.pdp,
                obj.status_descricao,
                obj.data_cadastro,
                obj.servidor,
                obj.campus,
                obj.servidor.setor,
                obj.servidor.get_funcao(),
                obj.enfoque_desenvolvimento,
                obj.enfoque_outros,
                obj.area_tematica,
                obj.necessidade,
                obj.justificativa_necessidade,
                ', '.join(obj.competencia_associada.values_list('descricao', flat=True)),
                obj.get_acao_transversal_display(),
                obj.publico_alvo,
                # obj.setor_beneficiado,
                obj.setores_beneficiados_str(),
                obj.qtd_pessoas_beneficiadas,
                obj.tipo_aprendizagem,
                obj.especificacao_tipo_aprendizagem,
                obj.get_modalidade_display(),
                obj.titulo_necessidade,
                obj.ano_termino_acao,
                obj.get_onus_inscricao_display(),
                obj.valor_onus_inscricao,
                # obj.get_atendida_pelo_cfs_display()
            ]
            rows.append(row)
        return rows


admin.site.register(PDP, PDPAdmin)
admin.site.register(Resposta, RespostaAdmin)
admin.site.register(EnfoqueDesenvolvimento, EnfoqueDesenvolvimentoAdmin)
admin.site.register(AreaTematica, AreaTematicaAdmin)
admin.site.register(Necessidade, ObjetoTematicoAdmin)
admin.site.register(CompetenciaAssociada, CompetenciaAssociadaAdmin)
admin.site.register(PublicoAlvo, PublicoAlvoAdmin)
admin.site.register(TipoAprendizagem, TipoAprendizagemAdmin)
admin.site.register(EspecificacaoTipoAprendizagem, EspecificacaoTipoAprendizagemAdmin)
