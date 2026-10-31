from django.contrib import admin
from django.contrib.auth.models import Group
from django.http.response import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, StackedInlinePlus
from enquete.forms import CategoriaForm, EnqueteForm, PublicoCampiForm
from enquete.models import Categoria, Enquete, PublicoCampi, Resposta


class EnquetePublicoCampiInline(StackedInlinePlus):
    model = PublicoCampi
    form = PublicoCampiForm

    def has_add_permission(self, request, obj):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


class EnqueteCategoriaInline(StackedInlinePlus):
    model = Categoria
    form = CategoriaForm

    def has_add_permission(self, request, obj):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


class EnqueteAdmin(ModelAdminPlus):
    ordering = ('id',)
    search_fields = ('titulo', 'descricao')
    list_filter = (CustomTabListFilter, 'publicada')
    inlines = [EnquetePublicoCampiInline, EnqueteCategoriaInline]
    list_display_icons = True
    form = EnqueteForm
    show_count_on_tabs = True

    fieldsets = (
        ('Dados gerais', {'fields': ('tag', 'titulo', 'descricao', 'texto_orientacao', 'data_inicio', 'data_fim')}),
        ('Administração', {'fields': ('vinculos_responsaveis', 'resultado_publico', 'manter_enquete_inicio')}),
        ('Anexo', {'fields': ('instrucoes', 'descricao_anexo')}),
        ('Público-alvo', {'fields': (('vinculos_relacionados_enquete'),)}),
    )

    def get_publico(self, obj):
        return mark_safe(obj.get_publico_str())

    get_publico.short_description = 'Públicos'

    def get_opcoes(self, obj):
        retorno = '<ul class="action-bar">'

        if obj.respondeu(self.request.user.get_vinculo()):
            retorno += f'<li><a href="{reverse_lazy("ver_respostas", kwargs={"id": obj.id})}" class="btn default">Ver Minhas Respostas</a></li>'

        if obj.pode_responder(self.request.user.get_vinculo()):
            retorno += f'<li><a class="btn success" href="{reverse_lazy("responder_enquete", kwargs={"id": obj.id})}">Responder</a></li>'

        if obj.eh_responsavel(self.request.user):
            if obj.pode_publicar() and not obj.publicada:
                retorno += f'<li><a class="btn success" href="{reverse_lazy("publicar_enquete", kwargs={"id": obj.id})}">Publicar</a></li>'

            retorno += f'<li><a href="{reverse_lazy("ver_publico", kwargs={"enquete_id": obj.id})}" class="btn default">Ver Público</a></li>'
            retorno += f'<li><a href="{reverse_lazy("ver_resultados", kwargs={"id": obj.id})}" class="btn default">Ver Resultados</a></li>'

            if obj.pode_publicar() and obj.publicada:
                retorno += f'<li><a class="btn danger" href="{reverse_lazy("despublicar_enquete", kwargs={"id": obj.id})}">Despublicar</a></li>'

        retorno += '</ul>'
        return mark_safe(retorno)

    get_opcoes.short_description = 'Opções'

    def show_list_display_icons(self, obj):
        if not obj.eh_responsavel(self.request.user):
            return mark_safe('')
        return super().show_list_display_icons(obj)

    show_list_display_icons.short_description = '#'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            id_do_vinculo = request.user.get_vinculo().id
            ids_responsaveis = set(qs.filter(vinculos_responsaveis__id=id_do_vinculo).values_list('id', flat=True))
            ids_respostas = set(Resposta.objects.filter(vinculo_id=id_do_vinculo).values_list('pergunta__enquete__id', flat=True))
            total_ids = set.union(ids_respostas, ids_responsaveis)
            qs = qs.filter(id__in=total_ids)
        qs = qs.prefetch_related('publicocampi_set', 'opcao_set')
        return qs.distinct()

    def get_tabs(self, request):
        enquetes_como_responsavel = Enquete.objects.filter(vinculos_responsaveis=request.user.get_vinculo())
        if enquetes_como_responsavel.exists():
            return ['tab_enquetes_responsavel', 'tab_minhas_enquetes_respondidas', 'tab_any_data']
        return ['tab_minhas_enquetes_respondidas', 'tab_any_data']

    def tab_enquetes_responsavel(self, request, queryset):
        return queryset.filter(vinculos_responsaveis=request.user.get_vinculo()).distinct()

    tab_enquetes_responsavel.short_description = 'Enquetes que sou Responsável'

    def tab_minhas_enquetes_respondidas(self, request, queryset):
        return queryset.filter(pergunta__resposta__vinculo=request.user.get_vinculo()).distinct()

    tab_minhas_enquetes_respondidas.short_description = 'Minhas Enquetes Respondidas'

    def changelist_view(self, request, extra_context=None):
        list_display = ('titulo', 'descricao', 'get_opcoes')
        list_display_responsavel = ('titulo', 'get_publico', 'publicada', 'data_inicio', 'data_fim', 'get_opcoes')

        enquetes_como_responsavel = Enquete.objects.filter(vinculos_responsaveis=request.user.get_vinculo())
        if enquetes_como_responsavel.exists():
            self.list_display = list_display_responsavel
        else:
            self.list_display = list_display

        return super().changelist_view(request, extra_context)

    def response_add(self, request, obj):
        self.message_user(request, 'Enquete cadastrada com sucesso.')
        return HttpResponseRedirect(f'/enquete/enquete/{obj.id:d}/')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        enquete = form.instance
        enquete.set_publico()
        responsaveis = list(form.instance.vinculos_responsaveis.all())
        grupo_criador_enquete = Group.objects.get(name='Criador de Enquete')
        for responsavel in responsaveis:
            responsavel.user.groups.add(grupo_criador_enquete)


admin.site.register(Enquete, EnqueteAdmin)
