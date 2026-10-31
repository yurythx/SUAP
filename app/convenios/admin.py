from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseRedirect
from django.utils.safestring import mark_safe

from comum.models import Arquivo, Configuracao
from comum.utils import get_sigla_reitoria, get_uo
from convenios.forms import ConvenioForm, ParceriaInternacionalForm, ProfissionalLiberalForm
from convenios.models import (
    AnexoConvenio,
    ConselhoProfissional,
    Convenio,
    ParceriaInternacional,
    ProfissionalLiberal,
    SituacaoConvenio,
    TipoAnexo,
    TipoConvenio,
)
from djtools.contrib.admin import ModelAdminPlus
from djtools.contrib.admin.filters import DateRangeListFilter
from djtools.templatetags.filters import format_, in_group
from djtools.templatetags.filters.utils import status
from djtools.templatetags.tags import icon
from rh.models import PessoaExterna, UnidadeOrganizacional


class CampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        campus = UnidadeOrganizacional.objects.suap().all()
        if in_group(request.user, ['Operador de Convênios']):
            sigla_reitoria = get_sigla_reitoria()
            if UnidadeOrganizacional.objects.suap().filter(sigla=sigla_reitoria).exists():
                reitoria = UnidadeOrganizacional.objects.suap().get(sigla=sigla_reitoria)
                campus = UnidadeOrganizacional.objects.suap().filter(id__in=[get_uo(request.user).id, reitoria.id])
            else:
                campus = UnidadeOrganizacional.objects.suap().filter(id=get_uo(request.user).id)
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(uo=self.value())


class TipoConveniadoFilter(admin.SimpleListFilter):
    title = 'Tipo de Conveniada'
    parameter_name = 'conveniada'

    def lookups(self, request, model_admin):
        opcoes = (('Profissionais Liberais', 'Profissionais Liberais'), ('Pessoas Jurídicas', 'Pessoas Jurídicas'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'Profissionais Liberais':
                return queryset.filter(vinculos_conveniadas__in=ProfissionalLiberal.objects.values_list('vinculo_pessoa', flat=True))
            elif self.value() == 'Pessoas Jurídicas':
                return queryset.filter(vinculos_conveniadas__pessoa__pessoajuridica__isnull=False).distinct()


class ConvenioAdmin(ModelAdminPlus):
    form = ConvenioForm
    list_display = ['get_acoes', 'numero', 'uo', 'get_conveniadas_as_string', 'tipo', 'objeto', 'data_inicio', 'get_data_vencimento', 'get_situacao']
    ordering = ('-data_fim',)
    search_fields = (
        'numero',
        'vinculos_conveniadas__pessoa__pessoajuridica__nome_fantasia',
        'vinculos_conveniadas__pessoa__pessoajuridica__cnpj',
        'vinculos_conveniadas__pessoa__pessoafisica__cpf',
        'vinculos_conveniadas__pessoa__nome',
        'objeto',
    )
    list_filter = ['situacao', 'tipo', 'uo', ('data_inicio', DateRangeListFilter)]
    export_to_xls = True
    list_display_icons = False
    fieldsets = (
        (
            'Dados do Convênio',
            {
                'fields': (
                    'numero',
                    'tipo',
                    'situacao',
                    'vinculos_conveniadas',
                    'conveniadas_descricao',
                    'uo',
                    'interveniente',
                    'data_inicio',
                    'data_fim',
                    'objeto',
                    'continuado',
                    'financeiro',
                )
            },
        ),
        (
            'Anexo',
            {
                'fields': (
                    'tipo_anexo',
                    'descricao_anexo',
                    'arquivo_anexo',
                )
            },
        ),
    )

    def get_list_display(self, request):
        list_display = list(self.list_display)
        if (
            request.user
            and request.user.has_perm('convenios.view_convenio')
            and not in_group(request.user, 'Operador de Convênios Sistêmico, Operador de Convênios')
        ):
            list_display.remove('get_acoes')
        return list_display

    def get_list_display_links(self, request, list_display):
        if (
            request.user
            and request.user.has_perm('convenios.view_convenio')
            and not in_group(request.user, 'Operador de Convênios Sistêmico, Operador de Convênios')
        ):
            return None
        return super().get_list_display_links(request, list_display)

    def get_acoes(self, obj):
        return mark_safe(''.join([icon('view', f'/convenios/convenio/{obj.id}/'), icon('edit', f'/admin/convenios/convenio/{obj.id}/change/')]))

    get_acoes.short_description = 'Ações'
    get_acoes.allow_tags = 'Ações'

    def get_conveniadas_as_string(self, obj):
        return obj.get_conveniadas_as_string()

    get_conveniadas_as_string.short_description = 'Conveniadas'

    def get_data_vencimento(self, obj):
        return obj.get_data_vencimento().strftime('%d/%m/%y')

    get_data_vencimento.short_description = 'Data de Vencimento'

    def get_situacao(self, obj):
        situacao = obj.get_situacao()
        retorno = '-'
        if situacao.pk == SituacaoConvenio.VIGENTE:
            retorno = f'<span class="status status-success">{situacao.descricao}</span>'
        elif situacao.pk == SituacaoConvenio.VENCENDO:
            retorno = f'<span class="status status-alert">{situacao.descricao}</span>'
        elif situacao.pk == SituacaoConvenio.VENCIDO:
            retorno = f'<span class="status status-error">{situacao.descricao}</span>'
        elif situacao.pk == SituacaoConvenio.RESCINDIDO:
            retorno = f'<span class="status status-success">{situacao.descricao}</span>'
        return mark_safe(retorno)

    get_situacao.short_description = 'Situação'

    def response_change(self, request, obj):
        self.message_user(request, 'Convênio atualizado com sucesso.')
        return HttpResponseRedirect(f'/convenios/convenio/{obj.pk}/')

    def response_add(self, request, obj):
        self.message_user(request, 'Convênio cadastrado com sucesso.')
        return HttpResponseRedirect(f'/convenios/convenio/{obj.pk}/')

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if in_group(request.user, ['Operador de Convênios']):
            sigla_reitoria = get_sigla_reitoria()
            if UnidadeOrganizacional.objects.suap().filter(sigla=sigla_reitoria).exists():
                reitoria = UnidadeOrganizacional.objects.suap().get(sigla=sigla_reitoria)
                return qs.filter(uo__in=[get_uo(request.user), reitoria.id])
            else:
                return qs.filter(uo=get_uo(request.user))
        return qs

    def get_form(self, request, obj=None, **kwargs):
        FormClass = super().get_form(request, obj=obj, **kwargs)
        if in_group(request.user, ['Operador de Convênios']):
            uo = get_uo(request.user)
            if uo:
                qs_uo = UnidadeOrganizacional.objects.suap().filter(id=uo.id)
            else:
                qs_uo = UnidadeOrganizacional.objects.none()
        else:
            qs_uo = UnidadeOrganizacional.objects.suap().all()
        FormClass.base_fields['uo'].queryset = qs_uo
        return FormClass

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Número', 'Campus', 'Conveniadas', 'Tipo', 'Data de Início', 'Data de Vencimento', 'Situação', 'Possui Anexo Cadastrado']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            tem_anexo = 'Não'
            if AnexoConvenio.objects.filter(convenio=obj).exists():
                tem_anexo = 'Sim'
            empresas = []
            for empresa in obj.vinculos_conveniadas.all():
                texto = f'{empresa.pessoa}'
                empresas.append(texto)
            conveniadas = ', '.join(empresas)
            row = [idx + 1, obj.numero, obj.uo, conveniadas, obj.tipo, format_(obj.data_inicio), format_(obj.data_fim), obj.situacao, tem_anexo]
            rows.append(row)
        return rows

    def save_model(self, request, obj, form, change):
        obj.save()
        if form.cleaned_data.get('arquivo_anexo'):
            arquivo_up = form.cleaned_data.get('arquivo_anexo')
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            anexo = AnexoConvenio()
            anexo.tipo = TipoAnexo.objects.get(id=form.cleaned_data.get('tipo_anexo').id)
            anexo.descricao = form.cleaned_data.get('descricao_anexo')
            anexo.arquivo = arquivo
            anexo.convenio = obj
            anexo.save()
            arquivo.store(request.user, content)


admin.site.register(Convenio, ConvenioAdmin)


class ProfissionalLiberalAdmin(ModelAdminPlus):
    form = ProfissionalLiberalForm
    list_display = ['vinculo_pessoa', 'numero_registro', 'conselho', 'telefone', 'email']
    search_fields = ('vinculo_pessoa__pessoa__nome', 'vinculo_pessoa__pessoa__pessoafisica__cpf')
    list_display_icons = False
    fieldsets = (
        ('Dados Pessoais', {'fields': ('nome', 'cpf', 'sexo', 'nascimento_data', ('numero_registro', 'conselho'), 'telefone', 'email')}),
        ('Endereço', {'fields': ('cep', 'logradouro', 'numero', 'complemento', 'bairro', 'municipio')}),
    )

    def save_model(self, request, obj, form, change):
        if PessoaExterna.objects.filter(cpf=form.cleaned_data.get('cpf')).exists():
            pessoaexterna = PessoaExterna.objects.filter(cpf=form.cleaned_data.get('cpf')).order_by('-id')[0]
        else:
            pessoaexterna = PessoaExterna()
            pessoaexterna.cpf = form.cleaned_data.get('cpf')
        pessoaexterna.nome = form.cleaned_data.get('nome')
        pessoaexterna.sexo = form.cleaned_data.get('sexo')
        pessoaexterna.nascimento_data = form.cleaned_data.get('nascimento_data')
        pessoaexterna.save()
        obj.vinculo_pessoa = pessoaexterna.get_vinculo()
        return super().save_model(request, obj, form, change)


admin.site.register(ProfissionalLiberal, ProfissionalLiberalAdmin)


class ConselhoProfissionalAdmin(ModelAdminPlus):
    list_display = ['nome', 'sigla', 'ativo']
    search_fields = ('nome', 'sigla')

    list_display_icons = False


admin.site.register(ConselhoProfissional, ConselhoProfissionalAdmin)


class TipoConvenioAdmin(ModelAdminPlus):
    pass


class TipoAnexoAdmin(ModelAdminPlus):
    pass


class SituacaoConvenioAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoConvenio, TipoConvenioAdmin)
admin.site.register(TipoAnexo, TipoAnexoAdmin)
admin.site.register(SituacaoConvenio, SituacaoConvenioAdmin)


class ParceriaInternacionalAdmin(ModelAdminPlus):
    form = ParceriaInternacionalForm
    list_display = ['numero', 'uo', 'conveniadas_descricao', 'objeto', 'data_inicio', 'get_data_vencimento', 'get_situacao']
    ordering = ('-data_fim',)
    search_fields = ('numero', 'conveniadas_descricao', 'objeto')
    list_filter = ['situacao', 'tipo', 'uo', TipoConveniadoFilter, ('data_inicio', DateRangeListFilter)]
    export_to_xls = True
    list_display_icons = True
    fieldsets = (
        (
            'Dados do Convênio',
            {
                'fields': (
                    'numero',
                    'situacao',
                    'conveniadas_descricao',
                    'uo',
                    'interveniente',
                    'data_inicio',
                    'data_fim',
                    'objeto',
                    'continuado',
                    'financeiro',
                )
            },
        ),
        (
            'Anexo',
            {
                'fields': (
                    'tipo_anexo',
                    'descricao_anexo',
                    'arquivo_anexo',
                )
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        tipo_internacionalizacao = Configuracao.get_valor_por_chave('convenios', 'tipo_parceria_relacoes_internacionais')
        return tipo_internacionalizacao and super().has_add_permission(request)

    def get_data_vencimento(self, obj):
        return obj.get_data_vencimento().strftime('%d/%m/%y')

    get_data_vencimento.short_description = 'Data de Vencimento'

    def get_situacao(self, obj):
        situacao = obj.get_situacao()
        retorno = status(situacao.descricao)
        return mark_safe(retorno)

    get_situacao.short_description = 'Situação'

    def get_queryset(self, request: HttpRequest, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        tipo_internacionalizacao = Configuracao.get_valor_por_chave('convenios', 'tipo_parceria_relacoes_internacionais')
        if not tipo_internacionalizacao:
            raise PermissionDenied(
                'Você está tentando acessar uma funcionalidade que requer um convênio internacional, mas não há nenhum cadastrado no sistema. Entre em contato com o administrador do sistema para solicitar o cadastro do convênio internacional necessário.'
            )
        return qs.filter(tipo_id=int(tipo_internacionalizacao))

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Número', 'Campus', 'Conveniadas', 'Tipo', 'Data de Início', 'Data de Vencimento', 'Situação', 'Possui Anexo Cadastrado']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            tem_anexo = 'Não'
            if AnexoConvenio.objects.filter(convenio=obj).exists():
                tem_anexo = 'Sim'
            empresas = []
            for empresa in obj.vinculos_conveniadas.all():
                texto = f'{empresa.pessoa}'
                empresas.append(texto)
            conveniadas = ', '.join(empresas)
            row = [idx + 1, obj.numero, obj.uo, conveniadas, obj.tipo, format_(obj.data_inicio), format_(obj.data_fim), obj.situacao, tem_anexo]
            rows.append(row)
        return rows

    def save_model(self, request, obj, form, change):
        obj.save()
        if form.cleaned_data.get('arquivo_anexo'):
            arquivo_up = form.cleaned_data.get('arquivo_anexo')
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            anexo = AnexoConvenio()
            anexo.tipo = TipoAnexo.objects.get(id=form.cleaned_data.get('tipo_anexo').id)
            anexo.descricao = form.cleaned_data.get('descricao_anexo')
            anexo.arquivo = arquivo
            anexo.convenio = obj
            anexo.save()
            arquivo.store(request.user, content)


admin.site.register(ParceriaInternacional, ParceriaInternacionalAdmin)
