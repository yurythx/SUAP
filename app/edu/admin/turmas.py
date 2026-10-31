from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import path

from comum.utils import get_sigla_reitoria
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from djtools.utils import httprr
from edu.forms import EditarTurmaMinicursoForm, TurmaForm
from edu.models import Turma, TurmaMinicurso


class TurmaAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao', 'sigla', 'ano_letivo', 'periodo_letivo', 'get_campus', 'get_qtd_diarios', 'get_qtd_alunos', 'polo')
    list_filter = (
        CustomTabListFilter,
        ('ano_letivo'),
        'periodo_letivo',
        'periodo_matriz',
        'turno',
        'curso_campus__diretoria__setor__uo',
        'curso_campus__diretoria',
        'curso_campus',
        'matriz',
        'curso_campus__modalidade',
        'pertence_ao_plano_retomada',
        'convenio',
    )
    list_filter_autocomplete_form_filters = {'curso_campus': [('curso_campus__diretoria__setor__uo', 'diretoria__setor__uo')]}
    list_display_icons = True
    export_to_xls = True
    list_xls_display = (
        'id',
        'codigo',
        'descricao',
        'sigla',
        'ano_letivo',
        'periodo_letivo',
        'get_campus',
        'get_diretoria',
        'get_qtd_diarios',
        'get_qtd_alunos',
        'polo',
        'convenio',
    )
    list_per_page = 15
    search_fields = ('descricao', 'codigo', 'sigla', 'id')
    form = TurmaForm
    show_count_on_tabs = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.gerar_turmas'):
            items.append({'url': '/edu/gerar_turmas/', 'label': 'Gerar Turmas'})
            items.append({'url': '/edu/imprimir_horarios/', 'label': 'Imprimir Horários'})
        if request.user.has_group_cached('Administrador Acadêmico'):
            items.append(
                {
                    'label': 'Ações para o TimeTables',
                    'subitems': [
                        {'url': '/static/edu/timetables/suap_edu.xml', 'label': 'Gerar o Arquivo de configuração do TimeTables'},
                        {'url': '/edu/exportar_xml_time_tables/', 'label': 'Exportar XML para o TimeTables'},
                        {'url': '/edu/importar_xml_time_tables/', 'label': 'Importar XML do TimeTables'},
                    ],
                }
            )
        return items

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        qs = self.get_queryset(request)
        if qs.exists():
            ano = qs.latest('ano_letivo__ano').ano_letivo.id
            url = f'/admin/edu/turma/?ano_letivo__id__exact={ano}'
            if in_group(request.user, 'Diretor Acadêmico') and (request.user.eh_servidor or request.user.eh_prestador):
                sigla_reitoria = get_sigla_reitoria()
                if request.user.get_relacionamento().setor.uo.sigla != sigla_reitoria:
                    url = f'{url}&curso_campus__diretoria__setor__uo__id__exact={request.user.get_vinculo().setor.uo_id}'
        else:
            url = '/admin/edu/turma/'
        return HttpResponseRedirect(url)

    def get_campus(self, obj):
        return obj.curso_campus.diretoria.setor.uo

    get_campus.short_description = 'Campus'

    def get_diretoria(self, obj):
        return obj.curso_campus.diretoria

    get_diretoria.short_description = 'Diretoria'

    def get_qtd_diarios(self, obj):
        return obj.diario_set.order_by('componente_curricular__componente').count()

    get_qtd_diarios.short_description = 'Qtd de Diários'

    def get_qtd_alunos(self, obj):
        return obj.get_alunos_matriculados().count()

    get_qtd_alunos.short_description = 'Qtd de Alunos'

    def get_tabs(self, request):
        return ['tab_em_andamento', 'tab_pendentes']

    def tab_em_andamento(self, request, queryset):
        return queryset.em_andamento()

    tab_em_andamento.short_description = 'Em Andamento'

    def tab_pendentes(self, request, queryset):
        return queryset.pendentes()

    tab_pendentes.short_description = 'Notas Pendentes'

    def get_queryset(self, request):
        if request.user.has_perm('comum.is_operador_de_censo') or request.user.has_perm('comum.is_diretor_academico'):
            manager = Turma.objects
        else:
            manager = Turma.locals
        return super().get_queryset(request, manager).select_related('curso_campus__diretoria__setor__uo')

    def delete_view(self, request, object_id, extra_context=None):
        try:
            turma = Turma.objects.get(pk=object_id)
        except Turma.DoesNotExist:
            msg = 'A turma escolhida não pode ser encontrada.'
            messages.error(request, msg)
            return httprr('/admin/edu/turma/')
        if not request.POST or request.POST and (request.user.has_group_cached('edu Administrador') or turma.pode_ser_excluido()):
            return super().delete_view(request, object_id, extra_context)
        else:
            msg = 'Não é possível realizar a exclusão. Existem diários com alunos para esta turma.'
            messages.error(request, msg)
            return redirect('.')


admin.site.register(Turma, TurmaAdmin)


class TurmaMinicursoAdmin(ModelAdminPlus):
    form = EditarTurmaMinicursoForm

    def get_queryset(self, request):
        return self.model.objects.all()

    def response_add(self, request, obj):
        return httprr(f'/edu/minicurso/{obj.minicurso.pk}/', 'Operação realizada com sucesso.')

    def response_change(self, request, obj):
        return self.response_add(request, obj)

    fieldsets = (
        (
            'Dados gerais',
            {'fields': ('descricao', ('ano_letivo', 'periodo_letivo'), ('data_inicio', 'data_fim'), ('turno', 'gerar_matricula'), 'minicurso')},
        ),
        (
            'Moodle',
            {
                'fields': (
                    ('modelo_padrao', 'integracao_com_moodle'),
                    'url_ambiente_virtual',
                )
            },
        ),
        (
            'Autoinstrução',
            {'fields': (('nota_minima', 'completude_minima'),)},
        ),
        (
            'Autoinscrição',
            {'fields': ('autoinscricional',)},
        ),
        (
            'Público Alvo da Autoinscrição',
            {
                'fields': (
                    ('autoinscricao_alunos', 'autoinscricao_prestadores'),
                    ('autoinscricao_tae', 'autoinscricao_docente'),
                    ('autoinscricao_brasileiros', 'autoinscricao_estrangeiros'),
                )
            },
        ),
        (
            'Restrição dos Alunos para Autoinscrição',
            {'fields': ('autoinscricao_nivel_ensino', 'autoinscricao_modalidades', 'autoinscricao_campi', 'autoinscricao_cursos')},
        ),
    )


admin.site.register(TurmaMinicurso, TurmaMinicursoAdmin)
