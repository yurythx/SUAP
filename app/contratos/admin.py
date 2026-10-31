from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.models import Arquivo, Vinculo
from contratos.forms import ContratoForm, FiscalForm, TermoAditivoForm
from contratos.models import (
    Aditivo,
    BaseLegal,
    Contrato,
    DocumentoTextoContrato,
    Fiscal,
    MaoDeObra,
    MotivoConclusaoContrato,
    PreConfiguracaoAgenda,
    PublicacaoContrato,
    SubtipoContrato,
    TipoAnexo,
    TipoContrato,
    TipoDocumentoComprobatorio,
    TipoFiscal,
    TipoLicitacao,
    TipoOcorrencia,
    TipoPublicacao,
    TipoVerbaSalarial,
)
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.tags import icon
from documento_eletronico.models import DocumentoTexto
from edu.models import Configuracao
from suap import nomenclatura


class FiscalInline(admin.TabularInline):
    exclude = ('data_exclusao',)

    form = FiscalForm
    model = Fiscal
    extra = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_delete = False


class PublicacaoInline(admin.TabularInline):
    can_delete = False
    exclude = ('arquivo',)
    model = PublicacaoContrato
    extra = 1


class FiscalFilter(admin.SimpleListFilter):
    title = 'Fiscal'
    parameter_name = 'fiscal'

    SOMENTE_EU = 'somente_eu'
    FISCALIZADOS_POR_SERVIDORES_DO_MEU_SETOR = 'meus_setores'

    OPCOES = ((SOMENTE_EU, 'Somente eu'),)

    def lookups(self, request, model_admin):
        if request.user.eh_servidor and request.user.get_relacionamento().setores_que_eh_chefe_hoje.exists():
            return (*FiscalFilter.OPCOES, (FiscalFilter.FISCALIZADOS_POR_SERVIDORES_DO_MEU_SETOR, 'Fiscalizados por servidores do meu setor'))
        return FiscalFilter.OPCOES

    def queryset(self, request, queryset):
        if self.value() == FiscalFilter.SOMENTE_EU:
            if request.user.eh_servidor:
                return queryset.filter(fiscais__servidor=request.user.get_relacionamento(), fiscais__inativo=False).distinct()
            else:
                return Contrato.objects.none()
        elif self.value() == FiscalFilter.FISCALIZADOS_POR_SERVIDORES_DO_MEU_SETOR:
            setores = request.user.get_relacionamento().setores_que_eh_chefe_hoje
            return queryset.filter(fiscais__servidor__setor__in=setores, fiscais__inativo=False).distinct()
        return queryset


class ContratadaListFilter(admin.SimpleListFilter):
    title = 'Contratada'
    parameter_name = 'vinculo_contratado'

    def lookups(self, request, model_admin):
        campi = request.GET.get('campi__id__exact', None)
        if campi:
            contratadas = Vinculo.objects.filter(
                id__in=Contrato.objects.filter(campi__in=campi).values_list('vinculo_contratado', flat=True).distinct()
            )
        else:
            contratadas = Vinculo.objects.filter(id__in=Contrato.objects.all().values_list('vinculo_contratado', flat=True).distinct())

        return [(c.id, c) for c in contratadas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(vinculo_contratado__id=self.value())
        else:
            return queryset


class ContratoAdmin(ModelAdminPlus):
    change_form_template = 'contratos/templates/admin/contrato/change_form.html'
    list_display = (
        'numero',
        'vinculo_contratado',
        'objeto',
        'campus_gerenciador',
        'get_setores_gerenciadores',
        'get_uos_as_string',
        'get_contratada',
        'data_inicio',
        'get_data_fim_contrato',
        'aditivos',
    )
    list_filter = (
        CustomTabListFilter,
        'campi',
        'campus_gerenciador',
        'setores_gerenciadores',
        ContratadaListFilter,
        'tipo',
        'subtipo',
        'continuidade',
        'natureza',
        'mao_obra_exclusiva',
        'exige_garantia_contratual',
        'base_legal',
        FiscalFilter,
    )
    ordering = ('-data_inicio',)
    search_fields = Contrato.SEARCH_FIELDS
    list_display_icons = True
    form = ContratoForm
    date_hierarchy = 'data_inicio'
    show_count_on_tabs = True
    export_to_xls = True
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'permite_medicao_sem_empenho',
                    'numero',
                    'valor',
                    ('data_inicio', 'data_fim'),
                    'objeto',
                    'processo',
                    'campus_gerenciador',
                    'setores_gerenciadores',
                    'campi',
                    'vinculo_contratado',
                    'qtd_parcelas',
                )
            },
        ),
        ('Classificações', {'fields': (('tipo', 'subtipo'), ('continuidade', 'natureza'), ('mao_obra_exclusiva', 'grau_risco'))}),
        ('Documento do Contrato', {'fields': ('arquivo_contrato', 'documento_digital_contrato')}),
        ('Dados da Licitação', {'fields': (('tipo_licitacao', 'pregao'), 'base_legal', 'estimativa_licitacao')}),
        ('Garantia', {'fields': ('exige_garantia_contratual',)}),
        ('ComprasGov', {'fields': ('id_comprasgov',)}),
    )

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        is_visualizador_sistemico = (
            request.user.is_superuser or request.user.has_group_cached('Auditor') or request.user.has_group_cached('Supervisor de Contratos')
        )
        restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
        if restringir_por_unidade and not is_visualizador_sistemico:
            queryset = queryset.filter(campus_gerenciador=request.user.get_vinculo().setor.uo)
        return queryset

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_gerenciar(request.user)
        return super().has_change_permission(request, obj)

    def get_tabs(self, request):
        return [
            'tab_ativos',
            'tab_proximos_a_vencer',
            'tab_proximos_a_vencer_com_garantias',
            'tab_com_vigencia_expirada',
            'tab_com_ocorrencias_expiradas',
            'tab_concluidos',
            'tab_any_data',
        ]

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Número',
            'Contratada',
            f'{nomenclatura.campus} Gerenciador',
            'Setores Gerenciadores',
            nomenclatura.campi,
            'Percentual Executado',
            'Data de Início',
            'Data de Término',
            'Termos Aditivos',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            porcentagem_dias = f'{obj.get_percentual_dias_executado()}%'
            porcentagem_valor = f'{obj.get_percentual_executado()}%'
            executado = f'Valor Executado: {porcentagem_valor} / Período Executado:{porcentagem_dias}'
            retorno = []
            for aditivo in obj.aditivos.all():
                retorno.append(str(aditivo))
            descricao_aditivos = ', '.join(retorno)
            fim_contrato = ''
            if obj.data_fim and obj.data_vencimento and obj.data_vencimento == obj.data_fim:
                fim_contrato = mark_safe(obj.data_fim.strftime('%d/%m/%Y'))
            elif obj.data_fim:
                fim_contrato = mark_safe(
                    'Prorrogado de {}  <br> para {}'.format(obj.data_fim.strftime('%d/%m/%Y'), obj.get_data_fim().strftime('%d/%m/%Y'))
                )
            campus_gerenciador = obj.campus_gerenciador.sigla if obj.campus_gerenciador_id else ''
            setores_gerenciadores = ', '.join([setor.sigla for setor in obj.setores_gerenciadores.all()])
            row = [
                idx + 1,
                obj.numero,
                obj.vinculo_contratado,
                campus_gerenciador,
                setores_gerenciadores,
                obj.get_uos_as_string(),
                executado,
                obj.data_inicio,
                fim_contrato,
                descricao_aditivos,
            ]
            rows.append(row)
        return rows

    def tab_ativos(self, request, queryset):
        return queryset.ativos()

    tab_ativos.short_description = 'Ativos'

    def tab_concluidos(self, request, queryset):
        return queryset.concluidos()

    tab_concluidos.short_description = 'Concluídos'

    def tab_proximos_a_vencer(self, request, queryset):
        return queryset.proximos_a_vencer()

    tab_proximos_a_vencer.short_description = 'Próximos a Vencer'

    def tab_proximos_a_vencer_com_garantias(self, request, queryset):
        return queryset.proximos_a_vencer_com_garantias()

    tab_proximos_a_vencer_com_garantias.short_description = 'Próximos a Vencer com Garantias'

    def tab_com_vigencia_expirada(self, request, queryset):
        return queryset.com_vigencia_expirada()

    tab_com_vigencia_expirada.short_description = 'Com Vigência Expirada'

    def tab_com_ocorrencias_expiradas(self, request, queryset):
        return queryset.com_ocorrencias_expiradas()

    tab_com_ocorrencias_expiradas.short_description = 'Com Ocorrências Expiradas'

    def get_data_inicio_display(self, obj):
        return mark_safe(obj.data_inicio.strftime('%d/%m/%Y'))

    get_data_inicio_display.short_description = 'Data de Início'
    get_data_inicio_display.admin_order_field = 'data_inicio'

    def get_setores_gerenciadores(self, obj):
        return ', '.join(sigla for sigla in obj.setores_gerenciadores.values_list('sigla', flat=True))

    get_setores_gerenciadores.short_description = 'Setores Gerenciadores'

    def get_contratada(self, obj):
        porcentagem_dias = f'{obj.get_percentual_dias_executado()}%'
        porcentagem_valor = f'{obj.get_percentual_executado()}%'
        return mark_safe(
            f"""
        <dl>
            <dt>Valor executado:</dt>
            <dd><div class="progress" data-progress="{porcentagem_valor}"><p style="width: {porcentagem_valor};">{porcentagem_valor}</p></div></dd>
            <dt>Período executado:</dt>
            <dd><div class="progress" data-progress="{porcentagem_dias}"><p style="width: {porcentagem_dias};">{porcentagem_dias}</p></div></dd>
        </dl>"""
        )

    get_contratada.short_description = 'Percentual Executado'

    def save_model(self, request, obj, form, change):
        if request.POST.get('documento_digital_contrato', None) and obj.pk:
            # Cria/atualiza instancia de DocumentoTextoContrato para vincular o documento
            documento_contrato = (
                DocumentoTextoContrato()
                if not obj.documentos_texto_tipo_contato_relacionados().exists()
                else obj.documentos_texto_tipo_contato_relacionados().first()
            )
            documento_contrato.documento = DocumentoTexto.objects.get(pk=int(request.POST.get('documento_digital_contrato')))
            documento_contrato.contrato = obj
            documento_contrato.save()

        arquivo_up = request.FILES.get('arquivo_contrato')
        if arquivo_up:
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            obj.arquivo = arquivo
            obj.save()
            arquivo.store(request.user, content)
        super().save_model(request, obj, form, change)

    def get_data_fim_contrato(self, obj):
        if not obj.data_fim:
            return mark_safe('Tempo Indeterminado')
        elif obj.data_vencimento == obj.data_fim:
            return mark_safe(obj.data_fim.strftime('%d/%m/%Y'))
        else:
            return mark_safe(
                '<span class="line-through">Prorrogado de {} para:</span> {}'.format(
                    obj.data_fim.strftime('%d/%m/%Y'), obj.data_vencimento.strftime('%d/%m/%Y')
                )
            )

    get_data_fim_contrato.short_description = 'Data de Término'
    get_data_fim_contrato.admin_order_field = 'data_vencimento'

    def get_uos_as_string(self, obj):
        return obj.get_uos_as_string()

    get_uos_as_string.short_description = nomenclatura.campi
    get_uos_as_string.admin_order_field = 'campi'

    def aditivos(self, obj):
        retorno = '<ul>'
        for aditivo in obj.aditivos.all():
            retorno += '<li>' + str(aditivo) + '</li>'
        retorno += '</ul>'
        return mark_safe(retorno)

    aditivos.short_description = 'Termos Aditivos'

    def response_change(self, request, obj):
        self.message_user(request, 'Contrato atualizado com sucesso.')
        redirect_url = reverse('contrato', args=[obj.pk])
        return HttpResponseRedirect(redirect_url)

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if request.user.has_perm('contratos.add_contrato'):
            items.append({'url': '/contratos/importar_novo_contrato_comprasgov/', 'label': 'Importar do ComprasGov', 'css_class': 'primary'})
        return items


admin.site.register(Contrato, ContratoAdmin)


class BaseLegalAdmin(ModelAdminPlus):
    list_display = ('titulo', 'vigencia', 'prorrogacao', 'get_conformidade_base_legal')
    list_display_links = ()
    ordering = ('titulo',)
    search_fields = ('titulo',)

    def get_conformidade_base_legal(self, obj):
        """truncate in 30chars"""
        return obj.conformidade_base_legal[:30] if obj.conformidade_base_legal else ''


admin.site.register(BaseLegal, BaseLegalAdmin)


class AditivoAdmin(ModelAdminPlus):
    list_display = ('icone_editar', 'numero', 'data_inicio', 'data_fim')
    list_display_links = ()
    ordering = ('data_fim',)
    search_fields = ('numero',)
    form = TermoAditivoForm

    def icone_editar(self, obj):
        return mark_safe(icon('edit', f'/admin/contratos/aditivo/{obj.id}/'))

    icone_editar.short_description = ''


admin.site.register(Aditivo, AditivoAdmin)


class TipoPublicacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoPublicacao, TipoPublicacaoAdmin)


class TipoFiscalAdmin(ModelAdminPlus):
    list_display = (
        'descricao',
        'eh_gestor_contrato',
        'pode_gerenciar_todas_medicoes_contrato',
    )


admin.site.register(TipoFiscal, TipoFiscalAdmin)


class TipoContratoAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoContrato, TipoContratoAdmin)


class SubtipoContratoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'tipo')
    list_filter = ('tipo',)


admin.site.register(SubtipoContrato, SubtipoContratoAdmin)


class MotivoConclusaoContratoAdmin(ModelAdminPlus):
    pass


admin.site.register(MotivoConclusaoContrato, MotivoConclusaoContratoAdmin)


class FiscalAdmin(ModelAdminPlus):
    pass


admin.site.register(Fiscal, FiscalAdmin)


class TipoLicitacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoLicitacao, TipoLicitacaoAdmin)


class TipoDocumentoComprobatorioMedicaoAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoDocumentoComprobatorio, TipoDocumentoComprobatorioMedicaoAdmin)


class TipoAnexoAdmin(ModelAdminPlus):
    list_display_icons = True


admin.site.register(TipoAnexo, TipoAnexoAdmin)


class PreConfiguracaoAgendaAdmin(ModelAdminPlus):
    list_display = ('icone_editar', 'acao', 'prazo', 'recorrente')
    ordering = ('acao',)
    search_fields = ('acao',)

    def icone_editar(self, obj):
        return mark_safe(icon('edit', f'/admin/contratos/preconfiguracaoagenda/{obj.id}/change/'))

    icone_editar.short_description = ''


admin.site.register(PreConfiguracaoAgenda, PreConfiguracaoAgendaAdmin)


class MaoDeObraAdmin(ModelAdminPlus):
    def has_view_permission(self, request, obj=None, **kwargs):
        has_view_permission = super().has_view_permission(request, obj)
        if obj:
            maodeobra = MaoDeObra.objects.filter(pk=obj.pk).first()
            if maodeobra and maodeobra.contrato.eh_fiscal(request.user.get_relacionamento()):
                return True
        return has_view_permission

    def has_change_permission(self, request, obj=None):
        has_change_permission = super().has_change_permission(request, obj)
        return has_change_permission or request.user.has_perm('contratos.pode_aditivar_contrato')

    def has_delete_permission(self, request, obj=None):
        has_delete_permission = super().has_delete_permission(request, obj)
        return has_delete_permission or request.user.has_perm('contratos.pode_aditivar_contrato')


admin.site.register(MaoDeObra, MaoDeObraAdmin)


class TipoOcorrenciaAdmin(ModelAdminPlus):
    list_display_icons = True


admin.site.register(TipoOcorrencia, TipoOcorrenciaAdmin)


class TipoVerbaSalarialAdmin(ModelAdminPlus):
    list_display_icons = True


admin.site.register(TipoVerbaSalarial, TipoVerbaSalarialAdmin)
