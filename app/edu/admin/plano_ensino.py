from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, TabularInlinePlus
from djtools.templatetags.filters import in_group
from edu.forms import PlanoEnsinoForm
from edu.models import PlanoEnsino, ReferenciaBibliograficaBasica, ReferenciaBibliograficaComplementar


class ReferenciaBibliograficaBasicaInline(TabularInlinePlus):
    model = ReferenciaBibliograficaBasica
    extra = 1


class ReferenciaBibliograficaComplementarInline(TabularInlinePlus):
    model = ReferenciaBibliograficaComplementar
    extra = 1


class PlanoEnsinoAdmin(ModelAdminPlus):
    list_display = 'diario', 'coordenador_curso', 'data_submissao', 'data_homologacao', 'get_acoes'
    list_display_icons = True
    list_filter = CustomTabListFilter, 'diario__ano_letivo', 'diario__periodo_letivo', 'diario', 'diario__turma'
    list_per_page = 15
    inlines = ReferenciaBibliograficaBasicaInline, ReferenciaBibliograficaComplementarInline
    form = PlanoEnsinoForm
    actions = ('submeter', 'aprovar', 'homologar', 'cancelar_submissao', 'cancelar_homologacao', 'devolver_professor', 'devolver_coordenador')
    show_count_on_tabs = True

    def has_change_permission(self, request, obj=None):
        return obj and not obj.data_homologacao and super().has_change_permission(request, obj=obj)

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            ids = []
            ids.extend(qs.filter(diario__professordiario__professor__vinculo=request.user.get_vinculo()).values_list('id', flat=True))
            ids.extend(qs.filter(coordenador_curso=request.user.get_vinculo()).values_list('id', flat=True))
            if in_group(request.user, 'Diretor Acadêmico'):
                ids.extend(
                    qs.filter(diario__turma__curso_campus__diretoria__setor__uo=request.user.get_vinculo().setor.uo).values_list('id', flat=True)
                )
            return qs.filter(id__in=ids)
        return qs

    def get_actions(self, request):
        actions = super().get_actions(request)
        active = {}
        if request.GET.get('tab'):
            if request.GET.get('tab') == 'tab_aguardando_minha_subissao' and in_group(request.user, 'Professor'):
                active['submeter'] = actions['submeter']
            elif request.GET.get('tab') == 'tab_aguardando_aprovacao' and in_group(request.user, 'Professor'):
                active['cancelar_submissao'] = actions['cancelar_submissao']
            elif request.GET.get('tab') == 'tab_aguardando_minha_aprovacao' and in_group(request.user, 'Coordenador de Curso'):
                active['aprovar'] = actions['aprovar']
                active['devolver_professor'] = actions['devolver_professor']
            elif request.GET.get('tab') == 'tab_aguardando_homologacao' and in_group(request.user, 'Diretor Acadêmico'):
                active['homologar'] = actions['homologar']
                active['devolver_coordenador'] = actions['devolver_coordenador']
            elif request.GET.get('tab') == 'tab_homologados' and in_group(request.user, 'Diretor Acadêmico'):
                active['cancelar_homologacao'] = actions['cancelar_homologacao']
        return active

    def submeter(self, request, queryset):
        queryset.update(data_submissao=datetime.today())
        messages.success(request, 'Submissão realizada com sucesso.')

    submeter.short_description = 'Submeter'

    def cancelar_submissao(self, request, queryset):
        queryset.update(data_submissao=None)
        messages.success(request, 'Ação realizada com sucesso.')

    cancelar_submissao.short_description = 'Cancelar Submissão'

    def aprovar(self, request, queryset):
        queryset.update(data_aprovacao=datetime.today())
        messages.success(request, 'Aprovação realizada com sucesso.')

    aprovar.short_description = 'Aprovar'

    def homologar(self, request, queryset):
        queryset.update(data_homologacao=datetime.today())
        messages.success(request, 'Homologação realizada com sucesso.')

    homologar.short_description = 'Homologar'

    def cancelar_homologacao(self, request, queryset):
        queryset.update(data_homologacao=None)
        messages.success(request, 'Ação realizada com sucesso.')

    cancelar_homologacao.short_description = 'Cancelar Homologação'

    def devolver_professor(self, request, queryset):
        pks = [str(pk) for pk in queryset.values_list('pk', flat=True)]
        url = '/edu/devolver_plano_ensino/professor/{}/'.format('_'.join(pks))
        return HttpResponseRedirect(url)

    devolver_professor.short_description = 'Devolver'

    def devolver_coordenador(self, request, queryset):
        pks = [str(pk) for pk in queryset.values_list('pk', flat=True)]
        url = '/edu/devolver_plano_ensino/coordenador/{}/'.format('_'.join(pks))
        return HttpResponseRedirect(url)

    devolver_coordenador.short_description = 'Devolver'

    def get_tabs(self, request):
        tabs = []
        if in_group(request.user, 'Professor'):
            tabs.append('tab_aguardando_minha_subissao')
            tabs.append('tab_aguardando_aprovacao')
        if in_group(request.user, 'Coordenador de Curso'):
            tabs.append('tab_aguardando_minha_aprovacao')
        tabs.append('tab_aguardando_homologacao')
        tabs.append('tab_homologados')
        return tabs

    def tab_aguardando_minha_subissao(self, request, queryset):
        return queryset.filter(data_submissao__isnull=True, diario__professordiario__professor__vinculo=request.user.get_vinculo())

    tab_aguardando_minha_subissao.short_description = 'Meus planos Aguardando Submissão'

    def tab_aguardando_minha_aprovacao(self, request, queryset):
        return queryset.filter(data_submissao__isnull=False, data_aprovacao__isnull=True, coordenador_curso=request.user.get_vinculo())

    tab_aguardando_minha_aprovacao.short_description = 'Aguardando Minha Aprovação'

    def tab_aguardando_aprovacao(self, request, queryset):
        return queryset.filter(data_submissao__isnull=False, data_aprovacao__isnull=True).filter(
            diario__professordiario__professor__vinculo=request.user.get_vinculo()
        )

    tab_aguardando_aprovacao.short_description = 'Meus planos Aguardando Aprovação'

    def tab_aguardando_homologacao(self, request, queryset):
        return queryset.filter(data_aprovacao__isnull=False, data_homologacao__isnull=True)

    tab_aguardando_homologacao.short_description = 'Aguardando Homologação'

    def tab_homologados(self, request, queryset):
        return queryset.filter(data_homologacao__isnull=False)

    tab_homologados.short_description = 'Homologados'

    def get_acoes(self, obj):
        if (
            in_group(self.request.user, 'Diretor Acadêmico')
            and PlanoEnsino.objects.filter(
                pk=obj.pk, diario__turma__curso_campus__diretoria__setor__uo=self.request.user.get_vinculo().setor.uo
            ).exists()
        ):
            return mark_safe(f"<a class='btn popup' href='/edu/alterar_coordenador_plano_ensino/{obj.pk}/'>Alterar Coordenador</a>")
        return ''

    get_acoes.short_description = 'Ações'


admin.site.register(PlanoEnsino, PlanoEnsinoAdmin)
