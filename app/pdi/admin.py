from datetime import date

from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils.html import linebreaks
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import in_group
from pdi.forms import ComissaoPDIForm, EixoForm
from pdi.models import PDI, ComissaoPDI, SecaoPDI, SecaoPDICampus, SecaoPDIInstitucional, SugestaoComunidade, TipoComissaoChoices


class PDIAdmin(ModelAdminPlus):
    list_display = (
        'ano',
        'periodo_inicial',
        'periodo_final',
        'periodo_sugestao_inicial',
        'periodo_sugestao_final',
        'periodo_sugestao_melhoria_inicial',
        'periodo_sugestao_melhoria_final',
    )
    list_display_icons = True


admin.site.register(PDI, PDIAdmin)


class SecaoPDIAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('nome', 'descricao', 'pdi')
    list_filter = ('pdi',)


admin.site.register(SecaoPDI, SecaoPDIAdmin)


class ComissaoPDIAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('nome', 'tipo', 'pdi')
    list_filter = ('pdi',)
    form = ComissaoPDIForm

    def save_related(self, request, form, formsets, change):
        avaliadores_antigos = list(form.instance.vinculos_avaliadores.all())
        super().save_related(request, form, formsets, change)
        avaliadores_atuais = list(form.instance.vinculos_avaliadores.all())

        comissao = form.instance
        for avaliador in avaliadores_antigos:
            comissoes = avaliador.comissaopdi_set.filter(tipo=comissao.tipo)
            if comissao.tipo == TipoComissaoChoices.CENTRAL and in_group(avaliador.user, 'Comissão Central do PDI') and not comissoes.exists():
                avaliador.user.groups.remove(Group.objects.get(name='Comissão Central do PDI'))
            elif comissao.tipo == TipoComissaoChoices.TEMATICA and in_group(avaliador.user, 'Comissão Temática do PDI') and not comissoes.exists():
                avaliador.user.groups.remove(Group.objects.get(name='Comissão Temática do PDI'))
            elif comissao.tipo == TipoComissaoChoices.LOCAL and in_group(avaliador.user, 'Comissão Local do PDI') and not comissoes.exists():
                avaliador.user.groups.remove(Group.objects.get(name='Comissão Local do PDI'))

        for avaliador in avaliadores_atuais:
            if comissao.tipo == TipoComissaoChoices.CENTRAL and not in_group(avaliador.user, 'Comissão Central do PDI'):
                avaliador.user.groups.add(Group.objects.get(name='Comissão Central do PDI'))
            elif comissao.tipo == TipoComissaoChoices.TEMATICA and not in_group(avaliador.user, 'Comissão Temática do PDI'):
                avaliador.user.groups.add(Group.objects.get(name='Comissão Temática do PDI'))
            elif comissao.tipo == TipoComissaoChoices.LOCAL and not in_group(avaliador.user, 'Comissão Local do PDI'):
                avaliador.user.groups.add(Group.objects.get(name='Comissão Local do PDI'))


admin.site.register(ComissaoPDI, ComissaoPDIAdmin)


class SecaoPDIListFilter(admin.SimpleListFilter):
    title = _('Seção do PDI')
    parameter_name = 'secao_pdi'

    def lookups(self, request, model_admin):
        secoes = SecaoPDI.objects.filter(comissaopdi__vinculos_avaliadores=request.user.get_vinculo())
        return secoes.values_list('id', 'nome')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(secao_pdi=self.value())


class SecaoPDICampusAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('secao_pdi', 'campus', 'get_texto', 'anexo')
    search_fields = ('texto',)
    list_filter = ()

    def get_texto(self, obj):
        return mark_safe(f'<pre class="texto">{linebreaks(obj.texto)}</pre>')

    get_texto.short_description = 'Texto'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs

    def changelist_view(self, request, extra_context=None):
        if request.user.has_group_cached('Comissão Temática do PDI'):
            self.list_filter = (SecaoPDIListFilter, 'campus')
        elif request.user.has_group_cached('Comissão Central do PDI'):
            self.list_filter = ('secao_pdi', 'campus')
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(SecaoPDICampus, SecaoPDICampusAdmin)


class SecaoPDIInstitucionalAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('secao_pdi', 'get_anexo_url')
    search_fields = ('texto',)
    list_filter = ('secao_pdi',)

    def get_anexo_url(self, obj):
        if obj.anexo:
            return mark_safe(f'<a href="{obj.anexo.url}">{obj.anexo.name}</a>')
        return '-'

    get_anexo_url.short_description = 'Anexo'


admin.site.register(SecaoPDIInstitucional, SecaoPDIInstitucionalAdmin)


def restringir_contribuicoes(self, request):
    if in_group(request.user, 'Administrador de PDI, Comissão Temática do PDI, Comissão Central do PDI'):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(campus=get_uo(request.user))


class SugestaoComunidadeAdmin(ModelAdminPlus):
    list_display_icons = True

    list_display = (
        'get_usuario_campus',
        'get_campus',
        'secao_pdi',
        'get_texto',
        'get_status',
        'get_total_concordam',
        'get_total_discordam',
        'get_analise',
    )
    search_fields = ('texto',)
    list_filter = ('secao_pdi__pdi', 'secao_pdi', 'campus', 'analisada')
    export_to_xls = True
    export_to_csv = True

    get_queryset = restringir_contribuicoes

    def get_usuario_campus(self, obj):
        if obj.anonima:
            return mark_safe('Anônima')
        return mark_safe(f'{obj.cadastrada_por.get_profile().nome}')

    get_usuario_campus.short_description = 'Usuário'

    def get_total_concordam(self, obj):
        return mark_safe(f'{obj.concordam().count()}')

    get_total_concordam.short_description = 'Total Concordam'

    def get_total_discordam(self, obj):
        return mark_safe(f'{obj.discordam().count()}')

    get_total_discordam.short_description = 'Total Discordam'

    get_usuario_campus.short_description = 'Usuário'

    def get_campus(self, obj):
        return mark_safe(f'{obj.campus}')

    get_campus.short_description = 'Campus'

    def get_texto(self, obj):
        return mark_safe(f'<pre class="texto">{linebreaks(obj.texto)}</pre>')

    get_texto.short_description = 'Texto'

    def get_status(self, obj):
        retorno = '<span class="status status-alert">Em análise</span>'
        if obj.analisada:
            retorno = '<span class="status status-success">Analisada</span>'
        return mark_safe(retorno)

    get_status.short_description = 'Situação'

    def get_analise(self, obj):
        opcao = '-'
        if (
            obj.secao_pdi.pdi
            and obj.secao_pdi.pdi.periodo_inicial <= date.today() <= obj.secao_pdi.pdi.data_final_local
            and self.request.user.has_group_cached('Comissão Local do PDI')
            and obj.analisada is False
            and obj.campus == get_uo(self.request.user)
        ):
            opcao = f'<ul class="action-bar"><li><a href="/pdi/confirmar_analise_sugestao/{obj.id:d}/" class="btn success">Confirmar Análise</a></li></ul>'
        return mark_safe(opcao)

    get_analise.short_description = 'Opções'

    def get_changelist_form(self, request, **kwargs):
        form = EixoForm
        form.request = request
        return form

    def changelist_view(self, request, extra_context=None):
        self.list_editable = ()
        if request.user.has_group_cached('Comissão Local do PDI'):
            self.list_editable = ('secao_pdi',)
        return super().changelist_view(request, extra_context=extra_context)

    def to_csv(self, request, queryset, processo):
        header = ['#', 'Usuário/Campus', 'Seção do PDI', 'Texto']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            if obj.anonima:
                row = [
                    idx + 1,
                    '{}/{}'.format('Anônimo', obj.campus),
                    obj.secao_pdi.nome,
                    obj.texto,
                    obj.concordam().count(),
                    obj.discordam().count(),
                ]
            else:
                row = [idx + 1, f'{obj.cadastrada_por.get_profile().nome}/{obj.campus}', obj.secao_pdi.nome, obj.texto, obj.concordam().count()]
            rows.append(row)
        return rows

    def to_xls(self, request, queryset, processo):
        return self.to_csv(request, queryset, processo)


admin.site.register(SugestaoComunidade, SugestaoComunidadeAdmin)
