# Admins gerais --------------------------------------------------------------------------------------------------------

from django.contrib import admin
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from djtools.middleware.threadlocals import get_user
from djtools.templatetags.filters import in_group
from plan_v2.forms import AcaoForm, DimensaoForm, EixoForm, MacroprocessoForm, PDIForm, PlanoAcaoPDIForm, UnidadeMedidaForm
from plan_v2.models import PDI, Acao, Dimensao, Eixo, Macroprocesso, PlanoAcao, UnidadeMedida


class EixoAdmin(ModelAdminPlus):
    list_display = ('nome',)
    list_display_icons = True

    form = EixoForm
    fieldsets = ((None, {'fields': ('nome',)}),)


admin.site.register(Eixo, EixoAdmin)


class DimensaoAdmin(ModelAdminPlus):
    list_display = ('eixo', 'codigo', 'nome', 'setor_sistemico')
    list_display_icons = True
    list_filter = ('eixo',)
    search_fields = ('nome',)

    form = DimensaoForm

    fieldsets = ((None, {'fields': ('eixo', 'codigo', 'nome', 'setor_sistemico')}),)


admin.site.register(Dimensao, DimensaoAdmin)


class MacroprocessoAdmin(ModelAdminPlus):
    list_display = ('nome', 'dimensao')
    list_display_icons = True
    list_filter = ('dimensao',)
    search_fields = ('nome',)

    form = MacroprocessoForm

    fieldsets = ((None, {'fields': ('dimensao', 'nome', 'descricao')}),)


admin.site.register(Macroprocesso, MacroprocessoAdmin)


class AcaoAdmin(ModelAdminPlus):
    list_display = ('detalhamento', 'macroprocesso', 'eh_vinculadora', 'ativa')
    list_display_icons = True
    list_filter = ('macroprocesso', 'eh_vinculadora', 'ativa')
    search_fields = ('detalhamento',)

    form = AcaoForm

    fieldsets = ((None, {'fields': ('macroprocesso', 'detalhamento', 'eh_vinculadora', 'ativa')}),)


admin.site.register(Acao, AcaoAdmin)


class UnidadeMedidaAdmin(ModelAdminPlus):
    list_display = ('nome',)
    list_display_icons = True

    form = UnidadeMedidaForm

    fieldsets = ((None, {'fields': ('nome',)}),)


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)


class PDIAdmin(ModelAdminPlus):
    list_display = ('ano_inicial', 'ano_final', 'get_acoes')
    list_display_icons = True

    form = PDIForm

    fieldsets = ((None, {'fields': ('ano_inicial', 'ano_final')}),)

    def get_acoes(self, obj):
        return mark_safe('<a class="btn" href="{}">Detalhar</a>'.format(reverse_lazy('pdi_view', kwargs={'pdi_pk': obj.pk})))

    get_acoes.short_description = 'Ações'


admin.site.register(PDI, PDIAdmin)


class PlanoAcaoAdmin(ModelAdminPlus):
    list_display = ('pdi', 'ano_base', 'data_geral_inicial', 'data_geral_final', 'get_acoes')
    list_display_icons = True

    form = PlanoAcaoPDIForm

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'pdi',
                    'ano_base',
                    ('data_geral_inicial', 'data_geral_final'),
                    ('data_metas_inicial', 'data_metas_final'),
                    ('data_acoes_inicial', 'data_acoes_final'),
                    ('data_validacao_inicial', 'data_validacao_final'),
                )
            },
        ),
    )

    def get_acoes(self, obj):
        usuario = get_user()

        acoes = []
        acoes.append('<ul class="action-bar">')

        if usuario.has_perm('plan_v2.pode_detalhar_planoacao'):
            if in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional Sistêmico, Auditor'):
                acoes.append(
                    '<li><a class="btn" href="{}">Detalhar Sistêmico</a></li>'.format(
                        reverse_lazy('planoacao_sistemico_view', kwargs={'plano_acao_pk': obj.pk})
                    )
                )
            if in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional, Auditor'):
                acoes.append(
                    '<li><a class="btn" href="{}">Detalhar Unid. Adm.</a></li>'.format(
                        reverse_lazy('planoacao_unidade_view', kwargs={'plano_acao_pk': obj.pk})
                    )
                )

        acoes.append('</ul>')
        return mark_safe(' '.join(acoes))

    get_acoes.short_description = 'Ações'


admin.site.register(PlanoAcao, PlanoAcaoAdmin)
