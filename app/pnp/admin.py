from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import path

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import render
from pnp import tasks
from pnp.forms import (
    ImportarAreaTematicaPNPForm,
    ImportarEixoPNPForm,
    ImportarEstruturaPNPForm,
    ImportarMatriculaPNPForm,
    ImportarServidorPNPForm,
)
from pnp.models import AreaTematicaPNP, EixoPNP, EstruturaPNP, MatriculaPNP, ServidorPNP


class ImportacaoParquetAdmin(ModelAdminPlus):
    """Base dos admins da PNP, com a ação de importação de um arquivo Parquet.

    As subclasses declaram o formulário em ``importacao_form``, a task em ``importacao_task``
    e o título da tela em ``importacao_title``.
    """

    importacao_form = None
    importacao_task = None
    importacao_title = 'Importar'

    list_display_icons = True
    export_to_xls = True
    show_count_on_tabs = True

    def get_urls(self):
        my_urls = [path('importar/', self.url_wrap(self.importar), name=f'pnp_{self.model._meta.model_name}_importar')]
        return my_urls + super().get_urls()

    def get_list_filter(self, request):
        # as abas de get_tabs só são renderizadas se o CustomTabListFilter estiver no list_filter
        list_filter = super().get_list_filter(request)
        if not self.get_tabs(request) or CustomTabListFilter in list_filter:
            return list_filter
        return (CustomTabListFilter, *list_filter)

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if self.has_add_permission(request):
            items.append({'url': 'importar/', 'label': self.importacao_title, 'css_class': 'success'})
        return items

    def get_argumento_da_task(self, form):
        """Devolve o que a task recebe: as linhas lidas ou, nas bases grandes, o caminho do arquivo."""
        return form.linhas

    def importar(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        title = h1 = self.importacao_title
        form = self.importacao_form(request.POST or None, request.FILES or None)
        if form.is_valid():
            return self.importacao_task(self.get_argumento_da_task(form))
        return render('djtools/templates/default.html', {'title': title, 'h1': h1, 'form': form}, request)


class EstruturaPNPAdmin(ImportacaoParquetAdmin):
    importacao_form = ImportarEstruturaPNPForm
    importacao_task = staticmethod(tasks.importar_estruturas)
    importacao_title = 'Importar Estruturas'

    list_display = ('codigo', 'nome', 'uo')
    search_fields = ('codigo', 'nome', 'uo__nome', 'uo__sigla')

    def get_tabs(self, request):
        return ['tab_sem_unidade', 'tab_com_unidade']

    def tab_sem_unidade(self, request, queryset):
        return queryset.filter(uo__isnull=True)

    tab_sem_unidade.short_description = 'Sem unidade organizacional'

    def tab_com_unidade(self, request, queryset):
        return queryset.filter(uo__isnull=False)

    tab_com_unidade.short_description = 'Com unidade organizacional'


admin.site.register(EstruturaPNP, EstruturaPNPAdmin)


class AreaTematicaPNPAdmin(ImportacaoParquetAdmin):
    importacao_form = ImportarAreaTematicaPNPForm
    importacao_task = staticmethod(tasks.importar_areas_tematicas)
    importacao_title = 'Importar Áreas Temáticas'

    list_display = ('codigo', 'nome', 'area')
    search_fields = ('codigo', 'nome', 'area__codigo', 'area__descricao')

    def get_tabs(self, request):
        return ['tab_sem_area', 'tab_com_area']

    def tab_sem_area(self, request, queryset):
        return queryset.filter(area__isnull=True)

    tab_sem_area.short_description = 'Sem área do conhecimento'

    def tab_com_area(self, request, queryset):
        return queryset.filter(area__isnull=False)

    tab_com_area.short_description = 'Com área do conhecimento'


admin.site.register(AreaTematicaPNP, AreaTematicaPNPAdmin)


class EixoPNPAdmin(ImportacaoParquetAdmin):
    importacao_form = ImportarEixoPNPForm
    importacao_task = staticmethod(tasks.importar_eixos)
    importacao_title = 'Importar Eixos'

    list_display = ('codigo', 'nome', 'eixo_tecnologico')
    search_fields = ('codigo', 'nome', 'eixo_tecnologico__descricao')

    def get_tabs(self, request):
        return ['tab_sem_eixo_tecnologico', 'tab_com_eixo_tecnologico']

    def tab_sem_eixo_tecnologico(self, request, queryset):
        return queryset.filter(eixo_tecnologico__isnull=True)

    tab_sem_eixo_tecnologico.short_description = 'Sem eixo tecnológico'

    def tab_com_eixo_tecnologico(self, request, queryset):
        return queryset.filter(eixo_tecnologico__isnull=False)

    tab_com_eixo_tecnologico.short_description = 'Com eixo tecnológico'


admin.site.register(EixoPNP, EixoPNPAdmin)


class ServidorPNPAdmin(ImportacaoParquetAdmin):
    importacao_form = ImportarServidorPNPForm
    importacao_task = staticmethod(tasks.importar_servidores)
    importacao_title = 'Importar Servidores'

    list_display = ('matricula', 'nome', 'unidade', 'servidor', 'estrutura')
    list_filter = ('unidade',)
    search_fields = ('matricula', 'nome', 'cpf', 'unidade', 'servidor__matricula')

    def get_queryset(self, request, *args, **kwargs):
        return super().get_queryset(request, *args, **kwargs).select_related('servidor__pessoa_fisica', 'estrutura')

    def get_tabs(self, request):
        return ['tab_sem_servidor', 'tab_com_servidor', 'tab_sem_estrutura']

    def tab_sem_servidor(self, request, queryset):
        return queryset.filter(servidor__isnull=True)

    tab_sem_servidor.short_description = 'Sem servidor'

    def tab_com_servidor(self, request, queryset):
        return queryset.filter(servidor__isnull=False)

    tab_com_servidor.short_description = 'Com servidor'

    def tab_sem_estrutura(self, request, queryset):
        return queryset.filter(estrutura__isnull=True)

    tab_sem_estrutura.short_description = 'Sem estrutura'


admin.site.register(ServidorPNP, ServidorPNPAdmin)


class MatriculaPNPAdmin(ImportacaoParquetAdmin):
    importacao_form = ImportarMatriculaPNPForm
    importacao_task = staticmethod(tasks.importar_matriculas)
    importacao_title = 'Importar Matrículas'

    list_display = ('matricula', 'nome', 'curso', 'unidade', 'aluno')
    list_filter = ('unidade',)
    search_fields = ('matricula', 'nome', 'cpf', 'curso', 'aluno__matricula')

    def get_argumento_da_task(self, form):
        return form.caminho

    def get_queryset(self, request, *args, **kwargs):
        return super().get_queryset(request, *args, **kwargs).select_related('aluno__pessoa_fisica', 'estrutura')

    def get_tabs(self, request):
        return ['tab_sem_aluno', 'tab_com_aluno']

    def tab_sem_aluno(self, request, queryset):
        return queryset.filter(aluno__isnull=True)

    tab_sem_aluno.short_description = 'Sem aluno'

    def tab_com_aluno(self, request, queryset):
        return queryset.filter(aluno__isnull=False)

    tab_com_aluno.short_description = 'Com aluno'


admin.site.register(MatriculaPNP, MatriculaPNPAdmin)
