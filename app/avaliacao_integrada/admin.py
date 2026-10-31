from django.contrib import admin
from django.utils.safestring import mark_safe

from avaliacao_integrada.forms import AvaliacaoForm, ComissaoCPAForm, EixoForm, EscalaLikertForm, IndicadorForm
from avaliacao_integrada.models import (
    Avaliacao,
    ComissaoCPA,
    Dimensao,
    Eixo,
    EscalaLikert,
    Indicador,
    Iterador,
    Macroprocesso,
    NivelEscalaLikert,
    OpcaoResposta,
    Resposta,
    Segmento,
    TipoAvaliacao,
    Variavel,
)
from djtools.contrib.admin import ModelAdminPlus, TabularInlinePlus
from djtools.utils import httprr


class EixoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('ordem', 'descricao')
    list_display_icons = True
    export_to_xls = True
    form = EixoForm


admin.site.register(Eixo, EixoAdmin)


class DimensaoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_filter = ('eixo',)
    list_display = ('ordem', 'descricao', 'eixo')
    list_display_icons = True
    export_to_xls = True


admin.site.register(Dimensao, DimensaoAdmin)


class MacroprocessoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_filter = ('dimensao', 'dimensao__eixo')
    list_display = ('ordem', 'descricao', 'dimensao', 'eixo')
    fields = ('dimensao', 'descricao', 'texto_ajuda')
    list_display_icons = True
    export_to_xls = True

    def eixo(self, obj):
        return obj.dimensao.eixo


admin.site.register(Macroprocesso, MacroprocessoAdmin)


class TipoAvaliacaoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('descricao',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(TipoAvaliacao, TipoAvaliacaoAdmin)


class SegmentoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('id', 'descricao', 'tipo')
    export_to_xls = True


admin.site.register(Segmento, SegmentoAdmin)


class VariavelInline(admin.TabularInline):
    model = Variavel
    extra = 1


class OpcaoRespostaInline(admin.TabularInline):
    model = OpcaoResposta
    extra = 1


class IteradorInline(admin.TabularInline):
    model = Iterador
    extra = 0


class SegmentoSaveMixin:
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        #  Gerencie o ManyToMany 'segmentos' após salvar o objeto

        # Combinar segmentos internos e externos
        segmentos_alunos = form.cleaned_data.get('segmentos_alunos', [])
        segmentos_servidores = form.cleaned_data.get('segmentos_servidores', [])
        segmentos_sociedade_civil = form.cleaned_data.get('segmentos_sociedade_civil', [])

        # Criar a lista completa de segmentos
        segmentos_combined = list(segmentos_alunos) + list(segmentos_servidores) + list(segmentos_sociedade_civil)
        if segmentos_combined:
            # Atribuir os segmentos combinados ao campo segmento do modelo
            obj.segmentos.set(segmentos_combined)


class IndicadorAdmin(SegmentoSaveMixin, ModelAdminPlus):
    list_display = ('ordem', 'macroprocesso', 'nome', 'aspecto', 'tipo_resposta', 'escala', 'get_anos_referencia', 'get_acoes')
    list_filter = (
        'anos_referencia',
        'macroprocesso',
        'macroprocesso__dimensao__eixo',
        'tipo_resposta',
        'escala',
        'em_uso',
        'segmentos',
        'areas_vinculacao',
        'modalidades',
    )
    search_fields = ('nome', 'aspecto')
    list_display_icons = True
    export_to_xls = True
    form = IndicadorForm
    fieldsets = IndicadorForm.fieldsets
    inlines = [VariavelInline, OpcaoRespostaInline, IteradorInline]

    def get_anos_referencia(self, obj):
        lista = ['<ul>']
        for ano in obj.anos_referencia.all():
            lista.append('<li> ')
            lista.append(str(ano))
            lista.append('</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_anos_referencia.short_description = 'Anos de Referência'

    def get_acoes(self, obj):
        return mark_safe(f'<a href="/avaliacao_integrada/replicar_indicador/{obj.pk}/" class="btn">Replicar Indicador</a>')

    get_acoes.short_description = 'Opções'

    def response_change(self, request, obj):
        return httprr('..', 'Indicador editado com sucesso.')


admin.site.register(Indicador, IndicadorAdmin)


class AvaliacaoAdmin(SegmentoSaveMixin, ModelAdminPlus):
    list_display = ('nome', 'descricao', 'ano', 'data_inicio', 'data_termino')
    list_filter = ('tipos', 'areas_vinculacao', 'segmentos', 'modalidades', 'ano__ano')
    search_fields = ('nome', 'descricao')
    form = AvaliacaoForm
    fieldsets = AvaliacaoForm.fieldsets
    list_display_icons = True
    export_to_xls = True
    ordering = ['-id']

    def response_change(self, request, obj):
        return httprr('..', 'Avaliação editada com sucesso.')


admin.site.register(Avaliacao, AvaliacaoAdmin)


class RespostaAdmin(ModelAdminPlus):
    list_filter = (
        'indicador__macroprocesso__dimensao__eixo',
        'indicador__macroprocesso__dimensao',
        'indicador__macroprocesso',
        'respondente__segmento',
        'respondente__avaliacao',
        'indicador',
    )
    list_display = ('indicador', 'valor')
    list_display_icons = True


admin.site.register(Resposta, RespostaAdmin)


class ComissaoCPAAdmin(ModelAdminPlus):
    list_display = ('ativo', 'tipo', 'nome', 'setor', 'data_portaria', 'documento_portaria', 'get_membros', 'get_lista_emails')
    list_display_icons = True
    list_filter = ('uo', 'tipo', 'ativo')
    ordering = ('nome',)
    form = ComissaoCPAForm

    def get_membros(self, obj):
        return mark_safe(obj.get_membros())

    get_membros.short_description = 'Membros'

    def get_lista_emails(self, obj):
        return mark_safe(
            f"""<ul class="action-bar"><li><a class="btn primary popup" href="/avaliacao_integrada/lista_emails_comissao/{obj.id}/">Lista de Emails dos Membros</a></li></ul>"""
        )

    get_lista_emails.short_description = 'Lista de Emails dos Membros'


admin.site.register(ComissaoCPA, ComissaoCPAAdmin)


class NivelEscalaLikertInline(TabularInlinePlus):
    model = NivelEscalaLikert
    fields = ('nivel', 'descricao', 'emoji', 'tipo_criterio')
    extra = 1


class EscalaLikertAdmin(ModelAdminPlus):
    form = EscalaLikertForm
    inlines = [NivelEscalaLikertInline]

    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    list_display_icons = True

    # def has_change_permission(self, request, obj=None):
    #     if obj and not obj.em_uso():
    #         return super().has_change_permission(request, obj)
    #     return False
    #
    # def show_list_display_icons(self, obj):
    #     out = []
    #     out.append(icon("view", obj.get_absolute_url()))
    #     if not obj.em_uso():
    #         out.append(icon("edit", f"/admin/avaliacao_integrada/escalalikert/{obj.id}/"))
    #     return mark_safe(''.join(out))
    # show_list_display_icons.short_description = '#'


admin.site.register(EscalaLikert, EscalaLikertAdmin)
