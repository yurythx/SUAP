from django.contrib import admin
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import in_group
from djtools.utils import httprr
from processo_seletivo.forms import ConfiguracaoMigracaoVagaForm, EditalAdesaoCampusForm, EditalForm, InscricaoFiscalAdminForm
from processo_seletivo.models import (
    Candidato,
    ConfiguracaoMigracaoVaga,
    Edital,
    EditalAdesao,
    EditalAdesaoCampus,
    InscricaoFiscal,
    Lista,
    TipoEditalAdesao,
    WebService,
)
from rh.models import UnidadeOrganizacional


def eh_sistemico(user):
    return user.is_superuser or user.has_group_cached('Diretor Geral') or user.has_group_cached('Coordenador de Editais de Adesão Sistêmico')


def eh_campus(user):
    return user.has_group_cached('Coordenador de Editais de Adesão')


class CampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'campus'

    def lookups(self, request, model_admin):
        campus = UnidadeOrganizacional.objects.suap().all()
        if not eh_sistemico:
            campus = UnidadeOrganizacional.objects.suap().filter(id=get_uo(request.user).id)
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(campus=self.value())


class InscricaoCampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'edital__campus'

    def lookups(self, request, model_admin):
        campus = UnidadeOrganizacional.objects.suap().all()
        if not eh_sistemico:
            campus = UnidadeOrganizacional.objects.suap().filter(id=get_uo(request.user).id)
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__campus=self.value())


class ListaAdmin(ModelAdminPlus):
    list_display = ('edital', 'codigo', 'descricao', 'forma_ingresso')
    search_fields = ('codigo', 'descricao', 'forma_ingresso')
    list_display_icons = True
    export_to_xls = True

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)


admin.site.register(Lista, ListaAdmin)


class EditalAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao', 'ano', 'semestre', 'remanescentes', 'get_quantidade_vagas', 'get_quantidade_candidatos', 'get_opcoes')
    search_fields = ('descricao',)
    list_filter = ('ano', 'semestre', 'ofertavagacurso__curso_campus__diretoria__setor__uo')
    form = EditalForm
    fieldsets = EditalForm.fieldsets
    list_display_icons = True
    export_to_xls = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request)
        if request.user.has_perm('processo_seletivo.add_edital'):
            items.append({'url': '/processo_seletivo/importar_edital/', 'label': 'Importar Edital'})
        return items

    def get_quantidade_vagas(self, obj):
        return obj.get_quantidade_vagas_ofertadas()

    get_quantidade_vagas.short_description = 'Vagas Ofertadas'

    def get_quantidade_candidatos(self, obj):
        return obj.get_quantidade_candidatos()

    get_quantidade_candidatos.short_description = 'Candidatos Habilitados'

    def get_opcoes(self, obj):
        uo_usuario = None

        if not in_group(self.request.user, 'Administrador Acadêmico'):
            uo_usuario = get_uo(self.request.user)

        if obj.pode_ausentar(self.request.user, uo_usuario):
            return mark_safe(f'<a href="/processo_seletivo/edital/{obj.pk}/ausentar_candidatos/" class="btn">Ausentar Candidatos</a>')

    get_opcoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_group_cached('Coordenador de Polo EAD', ignore_groups_if_superuser=False):
            from edu.models import CoordenadorPolo

            polos = CoordenadorPolo.objects.filter(vinculo=request.user.get_vinculo()).values_list('polo__descricao', flat=True)
            pks = Candidato.objects.filter(edital__matricula_no_polo=True, campus_polo__in=polos).values_list('edital', flat=True).distinct()
            return qs.filter(pk__in=pks)
        else:
            return qs


admin.site.register(Edital, EditalAdmin)


class CandidatoAdmin(ModelAdminPlus):
    list_display = ('inscricao', 'cpf', 'nome', 'get_lista_candidato')
    search_fields = ('cpf', 'nome', 'inscricao')
    list_filter = ('edital__ofertavagacurso__curso_campus__diretoria__setor__uo', 'edital__ano', 'edital__semestre')
    list_display_icons = True
    export_to_xls = True

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)


admin.site.register(Candidato, CandidatoAdmin)


class WebServiceAdmin(ModelAdminPlus):
    list_display = ('descricao', 'url_editais', 'url_edital', 'url_candidato', 'url_caracterizacoes')
    list_display_icons = True
    search_fields = ('descricao',)
    list_per_page = 15
    export_to_xls = True
    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'is_zipped')}),
        ('Dados do WebService', {'fields': ('url_editais', 'url_edital', 'url_candidato', 'url_caracterizacoes')}),
        ('Segurança', {'fields': ('token',)}),
    )

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/admin/processo_seletivo/webservice/add/', 'label': 'Adicionar WebService'})
        return items


admin.site.register(WebService, WebServiceAdmin)


class TipoEditalAdesaoAdmin(ModelAdminPlus):
    ordering = ['nome']


class EditalAdesaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'tipo', 'get_numero_edital', 'data_inicio_adesao', 'data_limite_adesao')
    list_filter = ('nome', 'tipo', 'data_inicio_adesao', 'data_limite_adesao')
    readonly_fields = ('criado_em', 'atualizado_em')
    ordering = ['nome', 'numero_edital', 'ano_edital']
    fieldsets = (
        (None, {'fields': ('nome', 'tipo', ('numero_edital', 'ano_edital'), 'data_inicio_adesao', 'data_limite_adesao')}),
        ('Outras Informações', {'fields': ('criado_em', 'atualizado_em'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.criado_por_id:
            obj.criado_por = request.user
        obj.save()

    def get_numero_edital(self, obj):
        return mark_safe(f'{obj.numero_edital}/{obj.ano_edital}')

    get_numero_edital.short_description = 'Número do Edital'


class EditalAdesaoCampusAdmin(ModelAdminPlus):
    list_display = ('nome', 'edital_regulador', 'campus', 'get_numero_edital', 'data_inicio_inscricoes', 'data_encerramento_inscricoes')

    list_filter = ('nome', 'edital_regulador', CampusFilter, 'data_inicio_inscricoes', 'data_encerramento_inscricoes')

    search_fields = ('nome', 'edital_regulador__nome', 'campus__nome', 'data_inicio_inscricoes', 'data_encerramento_inscricoes')

    ordering = ['nome']
    readonly_fields = ('criado_em', 'atualizado_em')
    form = EditalAdesaoCampusForm

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'nome',
                    'edital_regulador',
                    ('numero_edital', 'ano_edital'),
                    'campus',
                    'data_inicio_inscricoes',
                    'data_encerramento_inscricoes',
                    'idade_minima',
                    'data_aplicacao_prova',
                )
            },
        ),
        ('Outras Informações', {'fields': ('criado_em', 'atualizado_em'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.responsavel_id:
            obj.responsavel = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if eh_sistemico(request.user):
            return qs
        else:
            return qs.filter(campus=get_uo(request.user))

    def get_numero_edital(self, obj):
        return mark_safe(f'{obj.numero_edital}/{obj.ano_edital}')

    get_numero_edital.short_description = 'Número do Edital'


class InscricaoFiscalAdmin(ModelAdminPlus):
    list_display = ('id', 'edital', 'get_campus', 'tipo', 'fiscal', 'matricula', 'telefones', 'pis_pasep', 'get_idade')
    list_filter = ('edital', 'tipo', InscricaoCampusFilter)
    search_fields = ['fiscal__pessoa__nome']
    ordering = ['-id', 'fiscal__pessoa__nome']
    list_display_icons = True
    export_to_xls = False
    filters_ajax = False

    form = InscricaoFiscalAdminForm

    def get_campus(self, obj):
        return mark_safe(obj.edital.campus)

    get_campus.short_description = 'Campus'

    def get_idade(self, obj):
        return mark_safe(obj.idade_no_dia_prova())

    get_idade.short_description = 'Idade no Dia da Prova'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        url = f'/processo_seletivo/inscricao_em_edital_xls/?{request.GET.urlencode()}'
        items.append({'url': url, 'label': 'Exportar para XLS'})
        return items

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if eh_sistemico(request.user):
            return qs
        elif in_group(request.user, 'Coordenador de Editais de Adesão'):
            return qs.filter(edital__campus=get_uo(request.user))
        else:
            return qs.filter(fiscal=request.user.get_vinculo())


admin.site.register(InscricaoFiscal, InscricaoFiscalAdmin)
admin.site.register(TipoEditalAdesao, TipoEditalAdesaoAdmin)
admin.site.register(EditalAdesao, EditalAdesaoAdmin)
admin.site.register(EditalAdesaoCampus, EditalAdesaoCampusAdmin)


class ConfiguracaoMigracaoVagaAdmin(ModelAdminPlus):
    form = ConfiguracaoMigracaoVagaForm
    fieldsets = ConfiguracaoMigracaoVagaForm.fieldsets
    list_display_icons = True
    search_fields = ('descricao',)
    list_filter = ('ativo',)
    list_display = ('descricao', 'ativo')

    def response_add(self, request, obj, post_url_continue=None):
        return self.response_change(request, obj)

    def response_change(self, request, obj):
        return httprr(f'/processo_seletivo/configuracaomigracaovaga/{obj.pk}/', 'Informe as precedências de matrícula e migração de vagas.')


admin.site.register(ConfiguracaoMigracaoVaga, ConfiguracaoMigracaoVagaAdmin)
