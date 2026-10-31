# imports ----------------------------------------------------------------------
from django.contrib import admin
from django.utils import dateformat
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus, TabularInlinePlus
from djtools.templatetags.filters import in_group
from djtools.utils import mask_money
from planejamento.forms import (
    AcaoExtraTetoForm,
    AcaoForm,
    AcaoPropostaForm,
    AtividadeForm,
    ConfiguracaoPlanejamentoForm,
    DimensaoForm,
    MetaForm,
    MetaUnidadeAcaoPropostaForm,
    MetaUnidadeForm,
    NaturezaDespesaForm,
    ObjetivoEstrategicoForm,
    OrigemRecursoForm,
    OrigemRecursoUAForm,
    UnidadeAdministrativaForm,
    UnidadeMedidaForm,
)
from planejamento.models import (
    Acao,
    AcaoExtraTeto,
    AcaoProposta,
    Atividade,
    AtividadeExecucao,
    Configuracao,
    Dimensao,
    Meta,
    MetaUnidade,
    MetaUnidadeAcaoProposta,
    NaturezaDespesa,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    UnidadeAdministrativa,
    UnidadeMedida,
)
from planejamento.utils import get_setor_unidade_administrativa

# -------------------------------------------------------------------------------


# -------------------------------------------------------------------------------
class ConfiguracaoAdmin(ModelAdminPlus):
    form = ConfiguracaoPlanejamentoForm

    list_display = ('ano_base', 'vigencia', 'periodo_cad_metas', 'periodo_cad_acoes')
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'ano_base',
                    ('data_geral_inicial', 'data_geral_final'),
                    ('data_metas_inicial', 'data_metas_final'),
                    ('data_acoes_inicial', 'data_acoes_final'),
                    ('data_validacao_inicial', 'data_validacao_final'),
                    ('data_planilhas_inicial', 'data_planilhas_final'),
                )
            },
        ),
    )

    def vigencia(self, obj):
        return mark_safe('De {} à {}'.format(dateformat.format(obj.data_geral_inicial, 'j F Y'), dateformat.format(obj.data_geral_final, 'j F Y')))

    vigencia.short_description = 'Período de vigência'

    def periodo_cad_metas(self, obj):
        return mark_safe('De {} à {}'.format(dateformat.format(obj.data_metas_inicial, 'j F Y'), dateformat.format(obj.data_metas_final, 'j F Y')))

    periodo_cad_metas.short_description = 'Período para cadastro de metas'

    def periodo_cad_acoes(self, obj):
        return mark_safe('De {} à {}'.format(dateformat.format(obj.data_acoes_inicial, 'j F Y'), dateformat.format(obj.data_acoes_final, 'j F Y')))

    periodo_cad_acoes.short_description = 'Período para cadastro de ações'


admin.site.register(Configuracao, ConfiguracaoAdmin)

# -------------------------------------------------------------------------------


class DimensaoAdmin(ModelAdminPlus):
    form = DimensaoForm

    search_fields = ('descricao', 'setor_sistemico__nome')
    list_display = ('codigo', 'descricao', 'sigla', 'setor_sistemico_nome')

    def setor_sistemico_nome(self, obj):
        return mark_safe(obj.setor_sistemico.nome)

    setor_sistemico_nome.short_description = 'Setor Sistemico'


admin.site.register(Dimensao, DimensaoAdmin)


def restringir_origemrecurso(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user))


# -------------------------------------------------------------------------------
class OrigemRecursoAdmin(ModelAdminPlus):
    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        return items

    list_display = ('show_nome', 'show_valor_capital', 'show_valor_custeio', 'valor', 'show_dimensao', 'acao_ano', 'visivel_campus')
    list_filter = ('configuracao__ano_base',)
    search_fields = ('nome',)
    form = OrigemRecursoForm
    get_queryset = restringir_origemrecurso

    def add_view(self, request):
        result = super().add_view(request)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/origemrecurso/'
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/origemrecurso/'
        return result

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/planejamento/origemrecurso/'
        return result

    def show_nome(self, obj):
        return mark_safe(f'<a href="/planejamento/origemrecurso/{obj.id}/" title="Visualizar Origem Recurso">{obj.nome}</a>')

    show_nome.short_description = 'Nome'

    def show_valor_capital(self, obj):
        if obj.valor_capital:
            return mark_safe(mask_money(obj.valor_capital))
        else:
            return '-'

    show_valor_capital.short_description = 'Valor Capital'

    def show_valor_custeio(self, obj):
        if obj.valor_custeio:
            return mark_safe(mask_money(obj.valor_custeio))
        else:
            return '-'

    show_valor_custeio.short_description = 'Valor Custeio'

    def valor(self, obj):
        # If necessário para exibir orçamento de anos anteriores.
        if obj.valor_capital or obj.valor_custeio:
            orcamento = obj.valor_capital + obj.valor_custeio
            return mark_safe(mask_money(orcamento))
        elif obj.valor_disponivel:
            return mark_safe(mask_money(obj.valor_disponivel))
        else:
            return '-'

    valor.short_description = 'Orçamento'

    def show_dimensao(self, obj):
        if obj.dimensao:
            return mark_safe(obj.dimensao)
        else:
            return '-'

    show_dimensao.short_description = 'Dimensão'


admin.site.register(OrigemRecurso, OrigemRecursoAdmin)

# -------------------------------------------------------------------------------


class UnidadeMedidaAdmin(ModelAdminPlus):
    form = UnidadeMedidaForm

    search_fields = ('nome',)
    list_display = ('nome',)


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)


class NaturezaDespesaAdmin(ModelAdminPlus):
    form = NaturezaDespesaForm
    search_fields = ('naturezadespesa__codigo', 'naturezadespesa__nome')
    list_display = ('naturezadespesa', 'get_naturezadespresa_tipo')

    def get_naturezadespresa_tipo(self, obj):
        if obj.naturezadespesa.tipo:
            return mark_safe(obj.naturezadespesa.tipo)
        else:
            return '-'

    get_naturezadespresa_tipo.short_description = 'Tipo'


admin.site.register(NaturezaDespesa, NaturezaDespesaAdmin)

# -------------------------------------------------------------------------------


class UnidadeAdministrativaAdmin(ModelAdminPlus):
    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        return items

    form = UnidadeAdministrativaForm
    search_fields = ('setor_equivalente__nome', 'tipo')

    list_filter = ('configuracao__ano_base',)
    list_display = ('setor_equivalente_nome', 'tipo', 'show_orcamento')
    ordering = ('setor_equivalente',)

    fieldsets = ((None, {'fields': ('configuracao', 'setor_equivalente', 'tipo', 'orcamento')}),)

    def add_view(self, request):
        result = super().add_view(request)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/unidadeadministrativa/'
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/unidadeadministrativa/'
        return result

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/planejamento/unidadeadministrativa/'
        return result

    def cod_simec(self, obj):
        if obj.codigo_simec:
            return mark_safe(f'{obj.codigo_simec}.{obj.codigo_simec_digito}')
        else:
            return '-'

    cod_simec.short_description = 'Cód. SIMEC'
    cod_simec.attrs = {'width': '80px'}

    def setor_equivalente_nome(self, obj):
        return mark_safe(obj.setor_equivalente.nome)

    setor_equivalente_nome.short_description = 'Nome'

    def show_orcamento(self, obj):
        if obj.orcamento:
            return mark_safe(mask_money(obj.orcamento))
        else:
            return '-'

    show_orcamento.short_description = 'Orçamento Próprio'


admin.site.register(UnidadeAdministrativa, UnidadeAdministrativaAdmin)

# -------------------------------------------------------------------------------


class OrigemRecursoUAAdmin(ModelAdminPlus):
    list_display = ('origem_recurso', 'unidade', 'show_valor_capital', 'show_valor_custeio')
    list_filter = ('origem_recurso__configuracao__ano_base',)
    form = OrigemRecursoUAForm

    def add_view(self, request):
        result = super().add_view(request)
        if request.POST.get('origem_recurso'):
            result['Location'] = '/planejamento/origemrecurso/{}/'.format(request.POST['origem_recurso'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if request.POST.get('origem_recurso'):
            result['Location'] = '/planejamento/origemrecurso/{}/'.format(request.POST['origem_recurso'])
        return result

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        if request.POST.get('origem_recurso'):
            result['Location'] = '/planejamento/origemrecurso/{}/'.format(request.POST['origem_recurso'])
        return result

    def show_valor_custeio(self, obj):
        if obj.valor_custeio:
            return mark_safe(mask_money(obj.valor_custeio))
        else:
            return '-'

    show_valor_custeio.short_description = 'Valor Custeio'

    def show_valor_capital(self, obj):
        if obj.valor_capital:
            return mark_safe(mask_money(obj.valor_capital))
        else:
            return '-'

    show_valor_capital.short_description = 'Valor Capital'


admin.site.register(OrigemRecursoUA, OrigemRecursoUAAdmin)
# -------------------------------------------------------------------------------


def restringir_objetivos(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user))


# -------------------------------------------------------------------------------
class ObjetivoEstrategicoAdmin(ModelAdminPlus):
    get_queryset = restringir_objetivos
    form = ObjetivoEstrategicoForm
    search_fields = ('descricao', 'macro_projeto_institucional')
    list_filter = ('configuracao__ano_base',)
    list_display = ('codigo_completo', 'macro_projeto_institucional', 'descricao', 'remover_icone')

    fieldsets = ((None, {'fields': ('configuracao', 'dimensao', 'macro_projeto_institucional', 'descricao', 'codigo')}),)

    def add_view(self, request):
        result = super().add_view(request)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/objetivoestrategico/'
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/objetivoestrategico/'
        return result

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/planejamento/objetivoestrategico/'
        return result

    def codigo_completo(self, obj):
        return mark_safe(
            f'<a href="/planejamento/objetivoestrategico/{obj.id}/" title="Visualizar Macro Projeto Institucional">{obj.get_codigo_completo()}</a>'
        )

    codigo_completo.short_description = 'Código'

    def remover_icone(self, obj):
        if obj.configuracao.periodo_sistemico() is True:
            return mark_safe(
                f'<a href="/admin/planejamento/objetivoestrategico/{obj.id}/delete" class="btn danger" title="Remover Macro Projeto Institucional">Remover</a>'
            )
        else:
            return '-'

    remover_icone.short_description = 'Remover'


admin.site.register(ObjetivoEstrategico, ObjetivoEstrategicoAdmin)

# -------------------------------------------------------------------------------


def restringir_metas(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request).order_by('-codigo', '-titulo')
    else:
        return (
            admin.ModelAdmin.get_queryset(self, request)
            .filter(objetivo_estrategico__dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user))
            .order_by('-codigo', '-titulo')
        )


# -------------------------------------------------------------------------------
class MetaAdmin(ModelAdminPlus):
    form = MetaForm
    get_queryset = restringir_metas

    list_display = ('codigo_completo', 'titulo', 'periodo_execucao')

    list_filter = ('objetivo_estrategico__configuracao__ano_base',)
    search_fields = ('titulo', 'objetivo_estrategico__descricao')

    fieldsets = ((None, {'fields': ('objetivo_estrategico', 'titulo', 'justificativa', ('data_inicial', 'data_final'), 'codigo')}),)

    def add_view(self, request):
        result = super().add_view(request)
        if 'objetivo_estrategico' in request.POST:
            result['Location'] = '/planejamento/objetivoestrategico/{}/'.format(request.POST['objetivo_estrategico'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        result['Location'] = f'/planejamento/meta/{object_id}/'
        return result

    def codigo_completo(self, obj):
        return mark_safe(f'<a href="/planejamento/meta/{obj.id}/" title="Visualizar Meta">{obj.get_codigo_completo()}</a>')

    codigo_completo.short_description = 'Código'

    def periodo_execucao(self, obj):
        return mark_safe('de {} à {}'.format(dateformat.format(obj.data_inicial, 'F'), dateformat.format(obj.data_final, 'F')))

    periodo_execucao.short_description = 'Período de Execução'


admin.site.register(Meta, MetaAdmin)

# -------------------------------------------------------------------------------


def restringir_metas_unidade(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Coordenador de Planejamento Sistêmico', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(unidade__setor_equivalente=get_setor_unidade_administrativa(request.user))


# -------------------------------------------------------------------------------
class MetaUnidadeAdmin(ModelAdminPlus):
    form = MetaUnidadeForm

    list_display = ('codigo_completo', 'meta', 'unidade_adm', 'unidade_medida', 'get_valor_proposto')
    list_filter = ('meta__objetivo_estrategico__configuracao__ano_base', 'meta__objetivo_estrategico__dimensao')
    search_fields = ('meta__titulo', 'meta__objetivo_estrategico__dimensao__descricao')

    get_queryset = restringir_metas_unidade

    def add_view(self, request):
        result = super().add_view(request)
        if 'meta' in request.POST:
            result['Location'] = '/planejamento/meta/{}/'.format(request.POST['meta'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if 'meta' in request.POST:
            result['Location'] = '/planejamento/meta/{}/'.format(request.POST['meta'])
        return result

    def codigo_completo(self, obj):
        return mark_safe(f'<a href="/planejamento/metaunidade/{obj.pk}/" title="Visulizar Meta">{obj.get_codigo_completo()}</a>')

    codigo_completo.short_description = 'Código'

    def unidade_adm(self, obj):
        return mark_safe(obj.unidade.setor_equivalente.sigla)

    unidade_adm.short_description = 'Unidade Admin.'

    def unidade_medida(self, obj):
        return mark_safe(obj.meta.unidade_medida)

    unidade_medida.short_description = 'Unidade de Medida'

    def get_valor_proposto(self, obj):
        return mask_money(obj.get_valor_proposto())

    get_valor_proposto.short_description = 'Valor Total'


admin.site.register(MetaUnidade, MetaUnidadeAdmin)
# -------------------------------------------------------------------------------


def restringir_acoes_propostas(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(
            meta__objetivo_estrategico__dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user)
        )


# -------------------------------------------------------------------------------
class MetaUnidadeAcaoPropostaInline(TabularInlinePlus):
    form = MetaUnidadeAcaoPropostaForm
    model = MetaUnidadeAcaoProposta
    extra = 1


class AcaoPropostaAdmin(ModelAdminPlus):
    form = AcaoPropostaForm
    get_queryset = restringir_acoes_propostas

    inlines = [MetaUnidadeAcaoPropostaInline]

    list_display = ('codigo_completo', 'titulo')
    list_filter = ('meta__objetivo_estrategico__configuracao__ano_base',)
    search_fields = ('titulo', 'unidade_medida__nome')

    fieldsets = ((None, {'fields': ('meta', 'titulo', ('data_inicial', 'data_final'), 'fonte_financiamento', 'codigo')}),)

    def add_view(self, request):
        result = super().add_view(request)
        if request.POST.get('meta'):
            result['Location'] = '/planejamento/meta/{}/'.format(request.POST['meta'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if request.POST.get('meta'):
            result['Location'] = '/planejamento/meta/{}/'.format(request.POST['meta'])
        return result

    def delete_view(self, request, object_id):
        obj = AcaoProposta.objects.get(id=object_id)
        result = super().delete_view(request, object_id)
        result['Location'] = f'/planejamento/meta/{obj.meta.id}/'
        return result

    def codigo_completo(self, obj):
        return mark_safe(f'<a href="/planejamento/acaoproposta/{obj.id}/" title="Visualizar Ação Proposta">{obj.get_codigo_completo()}</a>')

    codigo_completo.short_description = 'Código'


admin.site.register(AcaoProposta, AcaoPropostaAdmin)

# -------------------------------------------------------------------------------


class MetaUnidadeAcaoPropostaAdmin(ModelAdminPlus):
    form = MetaUnidadeAcaoPropostaForm

    fieldsets = ((None, {'fields': ('acao_proposta', 'meta_unidade', 'quantidade', 'valor_unitario')}),)

    def add_view(self, request):
        result = super().add_view(request)
        if request.POST.get('acao_proposta'):
            result['Location'] = '/planejamento/acaoproposta/{}/'.format(request.POST['acao_proposta'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if 'acao_proposta' in request.POST:
            result['Location'] = '/planejamento/acaoproposta/{}/'.format(request.POST['acao_proposta'])
        return result


admin.site.register(MetaUnidadeAcaoProposta, MetaUnidadeAcaoPropostaAdmin)

# -------------------------------------------------------------------------------


def restringir_acoes(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(
            meta_unidade__unidade__setor_equivalente=get_setor_unidade_administrativa(request.user)
        )


# -------------------------------------------------------------------------------
class AcaoAdmin(ModelAdminPlus):
    form = AcaoForm
    list_display = ('codigo_completo', 'titulo')
    list_filter = ('meta_unidade__meta__objetivo_estrategico__configuracao__ano_base',)
    search_fields = ('titulo',)
    get_queryset = restringir_acoes

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'meta_unidade',
                    'acao_indutora',
                    'titulo',
                    'detalhamento',
                    'setor_responsavel',
                    ('data_inicial', 'data_final'),
                    'fonte_financiamento',
                    'codigo',
                )
            },
        ),
    )

    def add_view(self, request):
        result = super().add_view(request)
        if request.POST.get('meta_unidade'):
            result['Location'] = '/planejamento/metaunidade/{}/'.format(request.POST['meta_unidade'])
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        result['Location'] = f'/planejamento/acao/{object_id}/'
        return result

    def codigo_completo(self, obj):
        return mark_safe(f'<a href="/planejamento/acao/{obj.id}/" title="Visualizar Ação">{obj.get_codigo_completo()}</a>')

    codigo_completo.short_description = 'Código'


admin.site.register(Acao, AcaoAdmin)

# -------------------------------------------------------------------------------


def restringir_acoes_extrateto(self, request):
    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return admin.ModelAdmin.get_queryset(self, request).filter(unidade__setor_equivalente=get_setor_unidade_administrativa(request.user))


# -------------------------------------------------------------------------------
class AcaoExtraTetoAdmin(ModelAdminPlus):
    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        return items

    get_queryset = restringir_acoes_extrateto
    form = AcaoExtraTetoForm

    search_fields = ('titulo',)
    list_filter = ('unidade__configuracao__ano_base',)
    ordering = ('titulo',)

    def icone_editar(self, obj):
        return 'Editar'

    icone_editar.short_description = ''
    icone_editar.attrs = {'width': '18px'}

    def add_view(self, request):
        result = super().add_view(request)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/acaoextrateto/'
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            result['Location'] = '/planejamento/acaoextrateto/'
        return result

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/planejamento/acaoextrateto/'
        return result


admin.site.register(AcaoExtraTeto, AcaoExtraTetoAdmin)

# -------------------------------------------------------------------------------


class AtividadeAdmin(ModelAdminPlus):
    form = AtividadeForm
    list_display = ('icone_editar', 'acao', 'descricao', 'quantidade')
    search_fields = ('descricao',)

    fieldsets = (
        (
            None,
            {'fields': ('acao', 'descricao', 'detalhamento', 'elemento_despesa', 'tipo_recurso', 'unidade_medida', 'quantidade', 'valor_unitario')},
        ),
    )

    def add_view(self, request):
        result = super().add_view(request)
        if request.POST.get('acao'):
            acao = Acao.objects.get(id=request.POST['acao'])
            result['Location'] = f'/planejamento/acao/{acao.id}/'
        return result

    def change_view(self, request, object_id):
        result = super().change_view(request, object_id)
        result['Location'] = f'/planejamento/atividade/{object_id}/'
        return result

    def icone_editar(self, obj):
        return 'Editar'

    icone_editar.short_description = ''
    icone_editar.attrs = {'width': '18px'}


admin.site.register(Atividade, AtividadeAdmin)

# -------------------------------------------------------------------------------


class AtividadeExecucaoAdmin(ModelAdminPlus):
    pass


admin.site.register(AtividadeExecucao, AtividadeExecucaoAdmin)
