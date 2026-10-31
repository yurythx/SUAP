from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import path
from django.db.models import Q
from django.utils.html import escape
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_, in_group, status
from rh.admin import EstrangeiroListFilter
from edu.forms import AlunoForm
from edu.models import Aluno, Modalidade, SituacaoMatricula, SolicitacaoAutorizacaoUsoImagem


class ModalidadeListFilter(admin.SimpleListFilter):
    title = 'Modalidades de ensino'
    parameter_name = 'curso_campus__modalidade_id__in'

    def __init__(self, request, params, model, model_admin):
        self.allow_multiple_choices = type(self) in model_admin.list_filter_multiple_choices
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        result = []
        for data in Modalidade.objects.all():
            result.append((data.id, data.descricao))
        return result

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(curso_campus__modalidade_id__in=value)

    def value(self):
        value = self.used_parameters.get(self.parameter_name)
        if value is None:
            value = []
        elif isinstance(value, str):
            value = value.split(',')
        return value

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            yield {
                'selected': str(lookup) in self.value(),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }


class AlunoEstrangeiroListFilter(EstrangeiroListFilter):
    # a nacionalidade do aluno está na matrícula: na pessoa física ela quase nunca está preenchida
    filtro = Q(nacionalidade='Estrangeira')


class AlunoAdmin(ModelAdminPlus):
    list_display = ('get_foto', 'get_info_principal', 'get_situacao', 'ano_letivo', 'periodo_letivo', 'get_pasta')
    list_filter = (
        CustomTabListFilter,
        'ano_letivo',
        'periodo_letivo',
        'situacao',
        'curso_campus__diretoria__setor__uo',
        'curso_campus',
        ModalidadeListFilter,
        'polo',
        AlunoEstrangeiroListFilter,
    )
    list_filter_multiple_choices = (ModalidadeListFilter,)
    list_filter_autocomplete_form_filters = {'curso_campus': [('curso_campus__diretoria__setor__uo', 'diretoria__setor__uo')]}
    list_display_icons = True
    export_to_xls = True
    list_per_page = 15
    ordering = ('-id',)
    form = AlunoForm
    fieldsets = AlunoForm.fieldsets

    search_fields = ('pessoa_fisica__nome_registro', 'pessoa_fisica__search_fields_optimized', 'registroemissaodiploma__pasta', 'numero_pasta')

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request, Aluno.locals)
            .exclude(participanteturmaminicurso__turma__gerar_matricula=False)
            .select_related('ano_letivo', 'pessoa_fisica', 'situacao', 'curso_campus__diretoria__setor__uo')
        )

    def get_foto(self, obj):
        return mark_safe(
            f'<div class="photo-circle"><img class="img-inside-container" src="{obj.get_foto_75x100_url()}" alt="{obj.pessoa_fisica.nome_registro}"></div>'
        )

    get_foto.short_description = 'Foto'

    def tab_suap(self, request, queryset):
        return queryset.filter(codigo_academico__isnull=True, matriz__id__isnull=False)

    tab_suap.short_description = 'Matriculados no Suap'

    def tab_q_academico(self, request, queryset):
        return queryset.filter(codigo_academico__isnull=False, matriz__id__isnull=True)

    tab_q_academico.short_description = lambda: (
        f'Matriculados no {Configuracao.get_valor_por_chave("edu", "academico_nome_sistema") or "Q-Acadêmico"}'
    )

    def tab_integralizados(self, request, queryset):
        return queryset.filter(codigo_academico__isnull=False, matriz__id__isnull=False)

    tab_integralizados.short_description = 'Migrados'

    def tab_vaga_migrada(self, request, queryset):
        return queryset.filter(
            situacao_id__in=(
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            ),
            candidato_vaga__vaga__isnull=True,
        ).exclude(candidato_vaga_id__isnull=True)

    tab_vaga_migrada.short_description = 'Cancelados com vaga migrada'

    def get_tabs(self, request):
        tabs = ['tab_suap', 'tab_q_academico', 'tab_integralizados']
        if 'processo_seletivo' in settings.INSTALLED_APPS and (
            request.user.has_perm('comum.is_administrador_academico') or request.user.has_perm('comum.is_operador_de_censo')
        ):
            tabs.append('tab_vaga_migrada')
        return tabs

    def correntes(self, request):
        url = '/admin/edu/aluno/'
        if not in_group(request.user, 'Administrador Acadêmico') and (request.user.eh_servidor or request.user.eh_prestador):
            sigla_reitoria = get_sigla_reitoria()
            if request.user.get_relacionamento().setor and request.user.get_relacionamento().setor.uo.sigla != sigla_reitoria:
                url = f'{url}?curso_campus__diretoria__setor__uo__id__exact={request.user.get_relacionamento().setor.uo_id}'
        return HttpResponseRedirect(url)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Nome', 'Matrícula', 'Curso', 'Campus', 'Polo', 'Situação', 'E-mail Acadêmico', 'E-mail Pessoal', 'Ano/Periodo Letivo']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.get_nome_social_composto(),
                obj.matricula,
                obj.curso_campus,
                obj.curso_campus.diretoria.setor.uo,
                format(obj.polo),
                obj.situacao,
                format(obj.email_academico),
                obj.email_pessoal,
                f'{obj.ano_letivo.ano}.{obj.periodo_letivo:d}',
            ]
            rows.append(row)
        return rows

    def get_info_principal(self, obj):
        out = f"""
                <dl>
                    <dt class="hidden">Nome:</dt><dd><h3 class="py-0">{obj.pessoa_fisica.nome_registro}</h3></dd>"""
        if obj.pessoa_fisica.nome_social:
            out += f'<dt>Nome social:</dt><dd>{obj.pessoa_fisica.nome_social}</dd>'
        if in_group(self.request.user, 'Administrador Acadêmico, Secretário Acadêmico'):
            # o documento identificador: CPF, ou o passaporte com o país (ARG-AB123456) do estrangeiro
            out += f'<dt>Documento:</dt><dd>{escape(obj.pessoa_fisica.documento_identificador or "-")}</dd>'
        out += f"""<dt>Matrícula:</dt><dd>{obj.matricula}</dd>
                    <dt>Curso:</dt><dd>{obj.curso_campus}</dd>"""
        if self.request.user.has_perm('comum.is_operador_de_censo'):
            out += f'<dt>Dados SISTEC:</dt><dd>{format_(obj.codigo_sistec)} | {format_(obj.data_inicio_ciclo)} | {format_(obj.data_prevista_termino_ciclo)}</dd>'
        out += """
                </dl>
            """
        return mark_safe(out)

    get_info_principal.short_description = 'Dados principais'
    get_info_principal.admin_order_field = 'pessoa_fisica__nome'

    def get_situacao(self, obj):
        return status(obj.situacao)

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'situacao'

    def get_pasta(self, obj):
        return obj.numero_pasta or '-'

    get_pasta.short_description = 'Nº Pasta'

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('.')


admin.site.register(Aluno, AlunoAdmin)


class SolicitacaoAutorizacaoUsoImagemAdmin(ModelAdminPlus):
    list_display_icons = True
    search_fields = ('aluno__matricula', 'aluno__pessoa_fisica__search_fields_optimized')
    list_display = ('aluno', 'autorizado', 'data_avaliacao', 'get_responsavel_avaliacao', 'data_revogacao', 'get_responsavel_revogacao')
    list_filter = (
        CustomTabListFilter,
        'aluno__ano_letivo',
        'aluno__periodo_letivo',
        'aluno__situacao',
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus',
    )

    def get_responsavel_avaliacao(self, obj):
        return obj.usuario_avaliacao_id and 'Próprio aluno' or 'Responsável do aluno'

    get_responsavel_avaliacao.short_description = 'Responsável pela Avaliação'

    def get_responsavel_revogacao(self, obj):
        if obj.data_revogacao:
            return obj.usuario_revogacao_id and 'Próprio aluno' or 'Responsável pelo aluno'
        return '-'

    get_responsavel_revogacao.short_description = 'Responsável pela Revogação'

    def tab_autorizadas(self, request, queryset):
        return queryset.filter(autorizado=True, data_revogacao__isnull=True)

    tab_autorizadas.short_description = 'Autorizadas'

    def tab_recusadas(self, request, queryset):
        return queryset.filter(autorizado=False)

    tab_recusadas.short_description = 'Recusadas'

    def tab_revogadas(self, request, queryset):
        return queryset.filter(autorizado=True, data_revogacao__isnull=False)

    tab_revogadas.short_description = 'Revogadas'

    def get_tabs(self, request):
        return ['tab_autorizadas', 'tab_recusadas', 'tab_revogadas']


admin.site.register(SolicitacaoAutorizacaoUsoImagem, SolicitacaoAutorizacaoUsoImagemAdmin)
