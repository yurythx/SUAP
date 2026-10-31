from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import EquivalenciaComponenteForm, EquivalenciaComponenteMatrizFormset
from edu.models import AvaliadorEquivalenciaComponente, EquivalenciaComponente, EquivalenciaComponenteMatriz


class EquivalenciaComponenteMatrizInline(admin.TabularInline):
    formset = EquivalenciaComponenteMatrizFormset
    model = EquivalenciaComponenteMatriz
    extra = 1
    exclude = 'chave_unica_1', 'chave_unica_2'


class AvaliadorEquivalenciaComponenteInline(admin.TabularInline):
    model = AvaliadorEquivalenciaComponente
    exclude = 'aprovada', 'data_avaliacao', 'observacao'
    extra = 1


class EquivalenciaComponenteAdmin(ModelAdminPlus):
    form = EquivalenciaComponenteForm
    fieldsets = EquivalenciaComponenteForm.fieldsets
    list_display = 'get_componentes', 'get_equivalencia', 'ativa', 'aprovada', 'automatica', 'get_matrizes', 'get_avaliadores'
    list_filter = (
        CustomTabListFilter,
        'componentes',
        'equivalentes',
        'ativa',
        'simples',
        'aprovada',
        'equivalenciacomponentematriz__matriz_origem',
        'equivalenciacomponentematriz__matriz_destino',
    )
    ordering = ('id',)
    search_fields = EquivalenciaComponente.SEARCH_FIELDS
    list_display_icons = True
    export_to_xls = True
    list_per_page = 25
    inlines = EquivalenciaComponenteMatrizInline, AvaliadorEquivalenciaComponenteInline
    actions = 'avaliar', 'cancelar_aprovacao', 'automatizar', 'inativar', 'inativar_equivalencias', 'excluir_equivalencias', 'reativar'

    def get_componentes(self, obj):
        html = ['<ul>']
        for componente in obj.componentes.all():
            html.append(f'<li>{componente}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_componentes.short_description = 'Componentes A'

    def get_equivalencia(self, obj):
        html = ['<ul>']
        for componente in obj.equivalentes.all():
            html.append(f'<li>{componente}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_equivalencia.short_description = 'Componentes B'

    def get_matrizes(self, obj):
        html = ['<ul>']
        for item in obj.equivalenciacomponentematriz_set.all():
            html.append(
                f'<li>{item.matriz_origem} <span class="true" style="font-weight:bold;font-size:2rem">&harr;</span> {item.matriz_destino}</li>'
            )
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_matrizes.short_description = 'Matrizes'

    def get_avaliadores(self, obj):
        html = ['<ul>']
        for item in obj.avaliadorequivalenciacomponente_set.all():
            if item.aprovada is None:
                cor = ''
            else:
                cor = 'true' if item.aprovada else 'false'
            obs = f'<br><i>{obj}</i>' if item.observacao else ''
            html.append(f'<li class="{cor}">{item.vinculo}{obs}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_avaliadores.short_description = 'Avaliadores'

    def has_change_permission(self, request, obj=None):
        if obj and obj.avaliadorequivalenciacomponente_set.filter(aprovada__isnull=False).exists():
            return False
        return super().has_change_permission(request, obj=obj)

    def get_tabs(self, request):
        return ['tab_aguardando_avaliacao', 'tab_aguardando_minha_avaliacao', 'tab_aprovadas', 'tab_reprovadas', 'tab_inativas']

    def tab_aguardando_avaliacao(self, request, queryset):
        pks = AvaliadorEquivalenciaComponente.objects.filter(aprovada__isnull=True).values_list('equivalencia_componente', flat=True)
        return queryset.filter(pk__in=pks)

    tab_aguardando_avaliacao.short_description = 'Aguardando Aprovação'

    def tab_aguardando_minha_avaliacao(self, request, queryset):
        pks = AvaliadorEquivalenciaComponente.objects.filter(vinculo=request.user.get_vinculo(), aprovada__isnull=True).values_list(
            'equivalencia_componente', flat=True
        )
        return queryset.filter(pk__in=pks)

    tab_aguardando_minha_avaliacao.short_description = 'Aguardando Minha Avaliação'

    def tab_aprovadas(self, request, queryset):
        pks1 = AvaliadorEquivalenciaComponente.objects.filter(aprovada__isnull=True).values_list('equivalencia_componente', flat=True)
        pks2 = AvaliadorEquivalenciaComponente.objects.filter(aprovada=False).values_list('equivalencia_componente', flat=True)
        return queryset.filter(avaliadorequivalenciacomponente__isnull=False).filter(ativa=True).exclude(pk__in=pks1).exclude(pk__in=pks2).distinct()

    tab_aprovadas.short_description = 'Ativas e Aprovadas'

    def tab_reprovadas(self, request, queryset):
        pks = AvaliadorEquivalenciaComponente.objects.filter(aprovada=False).values_list('equivalencia_componente', flat=True)
        return queryset.filter(pk__in=pks)

    tab_reprovadas.short_description = 'Reprovadas'

    def tab_inativas(self, request, queryset):
        return queryset.filter(ativa=False)

    tab_inativas.short_description = 'Inativas'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') is None or request.GET.get('tab') != 'tab_aguardando_minha_avaliacao':
            actions.pop('avaliar', None)
        if not request.user.is_superuser and not request.user.has_group_cached('Administrador Acadêmico'):
            actions.pop('cancelar_aprovacao', None)
            actions.pop('automatizar', None)
            actions.pop('inativar', None)
            actions.pop('inativar_equivalencias', None)
            actions.pop('excluir_equivalencias', None)
            actions.pop('reativar', None)
        return actions

    def avaliar(self, request, queryset):
        qs = queryset.filter(avaliadorequivalenciacomponente__vinculo=request.user.get_vinculo())
        qs = queryset.filter(avaliadorequivalenciacomponente__aprovada__isnull=True) | queryset.filter(
            avaliadorequivalenciacomponente__aprovada=False
        )
        ids = [str(x) for x in qs.values_list('id', flat=True)]
        if ids:
            url = '/edu/avaliar_equivalencia_componente/{}/'.format('_'.join(set(ids)))
            return HttpResponseRedirect(url)

    def cancelar_aprovacao(self, request, queryset):
        total = queryset.count()
        qtd = 0
        qs = queryset.filter(aproveitamentocomponente__isnull=True)
        for equivalencia in qs:
            if equivalencia.avaliadorequivalenciacomponente_set.filter(data_avaliacao__isnull=False).update(
                data_avaliacao=None, aprovada=None, observacao=None
            ):
                qtd += 1
        queryset.update(aprovada=False, automatica=False)
        messages.success(request, f'Ação realizada com sucesso. Total de {qtd} de {total} registro(s) afetado(s).')

    cancelar_aprovacao.short_description = 'Cancelar Aprovação'

    def automatizar(self, request, queryset):
        for obj in queryset.filter(ativa=True, aprovada=True):
            obj.identificar_registros_equivalencia(gerar=True)
            obj.automatica = True
            obj.save()
        messages.success(request, 'Ação realizada com sucesso.')

    automatizar.short_description = 'Criar registros de equivalências e automatizar'

    def excluir_equivalencias(self, request, queryset):
        total = queryset.count()
        qtd = 0
        # equivalências que ainda não foram usadas
        for obj in queryset.filter(aproveitamentocomponente__isnull=True):
            obj.delete()
            qtd += 1
        # equivalências que já foram usadas
        for obj in queryset.filter(aproveitamentocomponente__isnull=False):
            # excluindo registros dos alunos ativos
            obj.excluir_registros()
            if obj.pode_ser_excluida():
                obj.delete()
            else:
                # caso a equivalência não tenha sido usada por algum aluno inativo
                obj.ativa = False
            qtd += 1
        messages.success(request, f'Ação realizada com sucesso. Total de {qtd} de {total} registro(s) afetado(s).')

    excluir_equivalencias.short_description = 'Desfazer registros de equivalências e excluir.'

    def inativar_equivalencias(self, request, queryset):
        # equivalências que já foram usadas
        for obj in queryset.filter(aproveitamentocomponente__isnull=False):
            # excluindo registros dos alunos ativos
            obj.excluir_registros()
        queryset.update(ativa=False, automatica=False)
        messages.success(request, 'Ação realizada com sucesso.')

    inativar_equivalencias.short_description = 'Desfazer registros de equivalências e inativar.'

    def reativar(self, request, queryset):
        queryset.update(ativa=True, automatica=False)
        messages.success(request, 'Ação realizada com sucesso.')

    reativar.short_description = 'Reativar'

    def inativar(self, request, queryset):
        queryset.update(ativa=False, automatica=False)
        messages.success(request, 'Ação realizada com sucesso.')

    inativar.short_description = 'Inativar'

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.save()


admin.site.register(EquivalenciaComponente, EquivalenciaComponenteAdmin)
