from django.contrib import admin
from django.db.models import Q
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, TabularInlinePlus
from djtools.templatetags.filters import status
from djtools.utils import httprr
from edu.models import Diretoria
from pafc.forms import (
    MembroComissaoPAFCForm,
    MembroComissaoPAFCFormset,
    PAFCForm,
    RevisorTecnicoPAFCForm,
    RevisorTecnicoPAFCFormset,
    ValidadorPAFCForm,
    ValidadorPAFCFormset,
    PoloEadPAFCInlineFormset,
    PoloEadPAFCForm,
    TutorMediadorEadPAFCFormset,
    TutorMediadorEadPAFCForm,
    MapeamentoVersaoPAFCModalidadesForm,
)
from pafc.models import (
    PAFC,
    DocumentoHibrido,
    MembroComissaoPAFC,
    ModeloPAFC,
    RevisorTecnicoPAFC,
    ValidadorPAFC,
    SolicitacaoTramitacaoAdReferendumPAFC,
    PoloEadPAFC,
    TutorMediadorEadPAFC,
    MapeamentoVersaoPAFCModalidades,
)
from pafc.utils import eh_diretor_academico


class ModeloPAFCAdmin(ModelAdminPlus):
    list_display = ('descricao', 'tipo_oferta', 'get_versao_modelo', 'ativo')
    ordering = (
        '-ativo',
        'descricao',
    )
    list_filter = ('tipo_oferta', 'versao_modelo', 'ativo')
    search_fields = ('descricao',)
    list_display_icons = True

    fieldsets = (('Dados gerais', {'fields': (('descricao'), ('tipo_oferta', 'versao_modelo'), 'ativo')}),)

    def get_versao_modelo(self, obj):
        return obj.get_versao_modelo_display()

    get_versao_modelo.short_description = 'Versão do modelo'
    get_versao_modelo.admin_order_field = 'versao_modelo'

    def has_delete_permission(self, request, obj=None):
        return obj and super().has_delete_permission(request, obj) and not obj.pafc_set.exists()

    def tab_sem_secoes(self, request, queryset):
        return queryset.filter(secao__isnull=True)

    tab_sem_secoes.short_description = 'Sem Seções'

    def tab_sem_conteudo(self, request, queryset):
        return queryset.filter(secao__conteudo__isnull=True)

    tab_sem_conteudo.short_description = 'Sem Conteúdo de Seção'

    def get_tabs(self, request):
        return ['tab_sem_secoes', 'tab_sem_conteudo']


admin.site.register(ModeloPAFC, ModeloPAFCAdmin)


class MapeamentoVersaoPAFCModalidadesAdmin(ModelAdminPlus):
    list_display = ('versao_modelo', 'get_modalidades_de_ensino')
    list_filter = ('versao_modelo', 'modalidades_de_ensino')
    search_fields = ('modalidades_de_ensino__descricao',)
    list_display_icons = True
    form = MapeamentoVersaoPAFCModalidadesForm

    def get_modalidades_de_ensino(self, obj):
        modalidades = list(obj.modalidades_de_ensino.values_list('descricao', flat=True))
        prefixo, sufixo = ('<ul><li>', '</li></ul>') if len(modalidades) > 1 else ('', '')
        return mark_safe(f'{prefixo}{"</li><li>".join(modalidades)}{sufixo}')

    get_modalidades_de_ensino.short_description = 'Modalidades de ensino'


admin.site.register(MapeamentoVersaoPAFCModalidades, MapeamentoVersaoPAFCModalidadesAdmin)


def _usuario_pode_elaborar_pafc(pafc, user):
    return pafc.pode_ser_elaborado() and pafc.tem_permissao_edicao(user)


def _get_inlines_especificados_na_requisicao(request):
    if not request.GET:
        return []
    parametros_dos_inlines = ['comissao', 'revisao_tecnica', 'validacao', 'polos', 'tutores']
    return [parametro for parametro in parametros_dos_inlines if request.GET.get(parametro) == '1']


class MembroComissaoPAFCInline(TabularInlinePlus):
    model = MembroComissaoPAFC
    formset = MembroComissaoPAFCFormset
    form = MembroComissaoPAFCForm
    extra = 1

    def has_add_permission(self, request, obj):
        return self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj:
            inlines_especificados_na_requisicao = _get_inlines_especificados_na_requisicao(request)
            return (
                obj.pode_ter_comissao_editada()
                and obj.pode_alterar_elaboradores(request.user)
                and ('comissao' in inlines_especificados_na_requisicao or not inlines_especificados_na_requisicao)
            )
        return True

    def has_delete_permission(self, request, obj=None):
        return obj is None or self.has_add_permission(request, obj)


class RevisorTecnicoPAFCInline(TabularInlinePlus):
    model = RevisorTecnicoPAFC
    formset = RevisorTecnicoPAFCFormset
    form = RevisorTecnicoPAFCForm
    extra = 1

    def has_add_permission(self, request, obj):
        return obj is not None and self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return 'revisao_tecnica' in _get_inlines_especificados_na_requisicao(request) and (
            obj is None or obj.pode_alterar_revisores_tecnicos(request.user)
        )

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        return 'revisao_tecnica' in _get_inlines_especificados_na_requisicao(request)


class ValidadorPAFCInline(TabularInlinePlus):
    model = ValidadorPAFC
    formset = ValidadorPAFCFormset
    form = ValidadorPAFCForm
    extra = 1

    def has_add_permission(self, request, obj):
        return obj is not None and self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return 'validacao' in _get_inlines_especificados_na_requisicao(request) and (obj is None or obj.pode_alterar_validadores(request.user))

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        return 'validacao' in _get_inlines_especificados_na_requisicao(request)


class PoloEaDPAFCInline(TabularInlinePlus):
    model = PoloEadPAFC
    formset = PoloEadPAFCInlineFormset
    form = PoloEadPAFCForm
    extra = 1

    def has_add_permission(self, request, pafc):
        return pafc is not None and self.has_change_permission(request, pafc)

    def has_change_permission(self, request, pafc=None):
        return 'polos' in _get_inlines_especificados_na_requisicao(request) and (
            pafc is None or pafc.requer_cadastro_de_polos() and _usuario_pode_elaborar_pafc(pafc, request.user)
        )

    def has_delete_permission(self, request, pafc=None):
        return self.has_change_permission(request, pafc)

    def has_view_permission(self, request, pafc=None):
        return 'polos' in _get_inlines_especificados_na_requisicao(request)


class TutorMediadorEaDPAFCInline(TabularInlinePlus):
    model = TutorMediadorEadPAFC
    formset = TutorMediadorEadPAFCFormset
    form = TutorMediadorEadPAFCForm
    extra = 1

    def has_add_permission(self, request, pafc):
        return pafc is not None and self.has_change_permission(request, pafc)

    def has_change_permission(self, request, pafc=None):
        return 'tutores' in _get_inlines_especificados_na_requisicao(request) and (
            pafc is None or pafc.requer_cadastro_de_tutores() and _usuario_pode_elaborar_pafc(pafc, request.user)
        )

    def has_delete_permission(self, request, pafc=None):
        return self.has_change_permission(request, pafc)

    def has_view_permission(self, request, pafc=None):
        return 'tutores' in _get_inlines_especificados_na_requisicao(request)


class VinculacaoFilter(admin.SimpleListFilter):
    title = 'Vinculados a mim'
    parameter_name = 'vinculo'

    MEUS_COMO_PROREITOR = 'proreitor'
    MEUS_COMO_DA = 'diac'
    MEUS_COMO_ELABORADOR = 'elaborador'
    MEUS_COMO_REVISOR = 'revisor'
    MEUS_COMO_VALIDADOR = 'validador'
    MEUS_COMO_INTEGR_CAMARA = 'integr_camara'

    OPCOES = (
        (MEUS_COMO_PROREITOR, 'Como pró-reitor'),
        (MEUS_COMO_DA, 'Como diretor acadêmico'),
        (MEUS_COMO_ELABORADOR, 'Como elaborador'),
        (MEUS_COMO_REVISOR, 'Como revisor técnico'),
        (MEUS_COMO_VALIDADOR, 'Como validador'),
        (MEUS_COMO_INTEGR_CAMARA, 'Como integrante da Câmara'),
    )

    def lookups(self, request, model_admin):
        return VinculacaoFilter.OPCOES

    def queryset(self, request, queryset):
        vinculo_usuario = request.user.get_vinculo()
        diretoria_como_da = Diretoria.objects.filter(Q(diretor_academico=vinculo_usuario) | Q(diretor_academico_exercicio=vinculo_usuario)).first()

        switcher = {
            VinculacaoFilter.MEUS_COMO_PROREITOR: queryset.filter(proreitoria__setor_id=vinculo_usuario.setor_id),
            VinculacaoFilter.MEUS_COMO_DA: queryset.filter(setor=diretoria_como_da.setor if diretoria_como_da else None),
            VinculacaoFilter.MEUS_COMO_ELABORADOR: queryset.filter(membrocomissaopafc__servidor=vinculo_usuario.relacionamento),
            VinculacaoFilter.MEUS_COMO_REVISOR: queryset.filter(revisortecnicopafc__servidor=vinculo_usuario.relacionamento),
            VinculacaoFilter.MEUS_COMO_VALIDADOR: queryset.filter(validadorpafc__servidor=vinculo_usuario.relacionamento),
            VinculacaoFilter.MEUS_COMO_INTEGR_CAMARA: queryset.filter(
                Q(camara__coordenador__matricula=request.user.username) | Q(camara__secretario__matricula=request.user.username)
            ),
        }

        if self.value():
            return switcher.get(self.value(), queryset.none()).distinct()
        return queryset


class PendenciaFilter(admin.SimpleListFilter):
    title = 'Pendência de cadastro'
    parameter_name = 'pendencia'

    SEM_PORTARIA_COMISSAO = 'portaria_comissao'
    SEM_COMISSAO_ELABORACAO = 'comissao_elaboracao'
    SEM_REVISORES_TECNICOS = 'revisores'
    SEM_VALIDADORES = 'validadores'
    SEM_PARECER_PROREITORIA = 'parecer_proreitoria'
    SEM_DATA_REUNIAO_CAMARA = 'reuniao_camara'
    SEM_PARECER_CAMARA = 'parecer_camara'
    SEM_DATA_REUNIAO_CONSEPEX = 'reuniao_consepex'
    SEM_DELIBERACAO_CONSEPEX = 'deliberacao_consepex'
    SEM_DATA_REUNIAO_CONSUP = 'reuniao_consup'
    SEM_RESOLUCAO_CONSUP = 'resolucao_consup'

    OPCOES = (
        (SEM_PORTARIA_COMISSAO, 'Emissão da Portaria da Comissão'),
        (SEM_COMISSAO_ELABORACAO, 'Definição da Comissão de Elaboração'),
        (SEM_REVISORES_TECNICOS, 'Definição dos revisores técnicos'),
        (SEM_VALIDADORES, 'Definição dos validadores'),
        (SEM_DATA_REUNIAO_CAMARA, 'Definição da data de reunião da Câmara'),
        (SEM_DATA_REUNIAO_CONSEPEX, 'Definição da data de reunião do CONSEPEX'),
        (SEM_DATA_REUNIAO_CONSUP, 'Definição da data de reunião do CONSUP'),
        (SEM_PARECER_PROREITORIA, 'Emissão do parecer da Pró-Reitoria'),
        (SEM_PARECER_CAMARA, 'Emissão do parecer da Câmara'),
        (SEM_DELIBERACAO_CONSEPEX, 'Emissão da deliberação do CONSEPEX'),
        (SEM_RESOLUCAO_CONSUP, 'Emissão da resolução do CONSUP'),
    )

    def lookups(self, request, model_admin):
        return PendenciaFilter.OPCOES

    def queryset(self, request, queryset):
        switcher = {
            PendenciaFilter.SEM_PORTARIA_COMISSAO: queryset.filter(portaria_comissao_elaboracao_vigente__isnull=True),
            PendenciaFilter.SEM_COMISSAO_ELABORACAO: queryset.filter(membrocomissaopafc__isnull=True),
            PendenciaFilter.SEM_REVISORES_TECNICOS: queryset.filter(revisortecnicopafc__isnull=True),
            PendenciaFilter.SEM_VALIDADORES: queryset.filter(validadorpafc__isnull=True),
            PendenciaFilter.SEM_DATA_REUNIAO_CAMARA: queryset.filter(decisao_camara__isnull=True, data_convocacao_camara__isnull=True),
            PendenciaFilter.SEM_DATA_REUNIAO_CONSEPEX: queryset.filter(decisao_consepex__isnull=True, data_convocacao_consepex__isnull=True),
            PendenciaFilter.SEM_DATA_REUNIAO_CONSUP: queryset.filter(decisao_consup__isnull=True, data_convocacao_consup__isnull=True),
            PendenciaFilter.SEM_PARECER_PROREITORIA: queryset.filter(situacao=PAFC.EM_ANALISE_PROREITORIA).exclude(
                documentos_emitidos__situacao_pafc=PAFC.EM_ANALISE_PROREITORIA,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            ),
            PendenciaFilter.SEM_PARECER_CAMARA: queryset.filter(situacao=PAFC.AGUARDANDO_APROVACAO_CAMARA).exclude(
                documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CAMARA,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            ),
            PendenciaFilter.SEM_DELIBERACAO_CONSEPEX: queryset.filter(situacao=PAFC.AGUARDANDO_APROVACAO_CONSEPEX).exclude(
                documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            ),
            PendenciaFilter.SEM_RESOLUCAO_CONSUP: queryset.filter(situacao=PAFC.AGUARDANDO_APROVACAO_CONSUP).exclude(
                documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSUP,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            ),
        }

        if self.value():
            return switcher.get(self.value(), queryset.none()).distinct()
        return queryset


class TipoTramitacaoFilter(admin.SimpleListFilter):
    title = 'Tipo de tramitação'
    parameter_name = 'tipo_tramitacao'

    ADEQUACAO = 'adequacao'
    CRIACAO = 'criacao'

    OPCOES = (
        (ADEQUACAO, 'Adequação'),
        (CRIACAO, 'Criação'),
    )

    def lookups(self, request, model_admin):
        return TipoTramitacaoFilter.OPCOES

    def queryset(self, request, queryset):
        if self.value():
            switcher = {
                TipoTramitacaoFilter.ADEQUACAO: queryset.filter(curso_ja_ofertado_campus=True),
                TipoTramitacaoFilter.CRIACAO: queryset.filter(curso_ja_ofertado_campus=False),
            }
            return switcher.get(self.value())
        return queryset


class PAFCAdmin(ModelAdminPlus):
    list_display = ('nome_curso', 'get_tipo_tramitacao', 'modelo', 'ppc', 'get_campus', 'get_situacao')
    ordering = ('-id',)
    list_filter = (
        CustomTabListFilter,
        TipoTramitacaoFilter,
        'situacao',
        'setor__uo',
        'modelo',
        'ppc',
        VinculacaoFilter,
        PendenciaFilter,
    )
    search_fields = ('nome_curso',)
    list_display_icons = True
    inlines = MembroComissaoPAFCInline, RevisorTecnicoPAFCInline, ValidadorPAFCInline, PoloEaDPAFCInline, TutorMediadorEaDPAFCInline
    form = PAFCForm
    fieldsets = (
        ('Dados gerais', {'fields': ('modelo', 'ppc')}),
        (
            'Dados do Curso',
            {
                'fields': (
                    'curso_ja_ofertado_campus',
                    'curso',
                    'ata_reuniao_codiac',
                    'numero_vagas_curso',
                    (
                        'ano_letivo_primeira_oferta',
                        'periodo_letivo_primeira_oferta',
                    ),
                    'previsto_pdi',
                    'justificativa_ausencia_pdi',
                )
            },
        ),
        (
            'Gestão',
            {
                'fields': (
                    ('reitor', 'pro_reitor_ensino'),
                    ('pro_reitor_pesquisa', 'pro_reitor_extensao'),
                    ('diretor_geral', 'diretor_academico'),
                    ('coordenador_pesquisa', 'coordenador_extensao'),
                )
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj=None)
        inlines_especificados_na_requisicao = _get_inlines_especificados_na_requisicao(request)
        if obj is None or obj.pode_editar(request.user) and not inlines_especificados_na_requisicao:
            return fieldsets

        if 'tutores' in inlines_especificados_na_requisicao and _usuario_pode_elaborar_pafc(obj, request.user):
            return (
                (
                    'Previsão de disponibilidade de tutores/mediadores',
                    {
                        'fields': (
                            'qtd_prevista_tutores',
                            'justificativa_indisponibilidade_tutores',
                        )
                    },
                ),
            )

        return ()

    def get_tipo_tramitacao(self, obj):
        return obj.get_tipo_tramitacao()

    get_tipo_tramitacao.short_description = 'Tipo de tramitação'
    get_tipo_tramitacao.admin_order_field = '-curso_ja_ofertado_campus'

    def get_campus(self, obj):
        return obj.setor.uo

    get_campus.short_description = 'Campus'
    get_campus.admin_order_field = 'setor__uo__sigla'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'

    def has_add_permission(self, request):
        return eh_diretor_academico(request.user)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        else:
            inlines_especificados_na_requisicao = _get_inlines_especificados_na_requisicao(request)
            usuario_pode_elaborar_pafc = _usuario_pode_elaborar_pafc(obj, request.user)
            return obj.pode_editar(request.user) or (
                # Usuário pode editar comissão de elaboração
                'comissao' in inlines_especificados_na_requisicao
                and obj.is_elaborador_coordenador(request.user)
                # Usuário pode editar equipe de revisão técnica
                or 'revisao_tecnica' in inlines_especificados_na_requisicao
                and obj.pode_alterar_revisores_tecnicos(request.user)
                # Usuário pode editar equipe de validadores
                or 'validacao' in inlines_especificados_na_requisicao
                and obj.pode_alterar_validadores(request.user)
                # Usuário pode editar lista de tutores
                or 'tutores' in inlines_especificados_na_requisicao
                and usuario_pode_elaborar_pafc
                and obj.requer_cadastro_de_tutores()
                # Usuário pode editar lista de polos
                or 'polos' in inlines_especificados_na_requisicao
                and usuario_pode_elaborar_pafc
                and obj.requer_cadastro_de_polos()
            )

    def has_delete_permission(self, request, obj=None):
        if _get_inlines_especificados_na_requisicao(request):
            # Oculta botão de remoção do PAFC nas telas de edição dos inlines
            return False
        return obj is not None and obj.pode_ser_excluido() and obj.pode_excluir(request.user)

    def response_add(self, request, obj):
        return httprr(f'/pafc/pafc/{obj.pk}/', 'Cadastro realizado com sucesso.')

    def response_change(self, request, obj):
        inlines_especificados_na_requisicao = _get_inlines_especificados_na_requisicao(request)
        eh_edicao_equipe = bool({'comissao', 'revisao_tecnica', 'validacao'}.intersection(inlines_especificados_na_requisicao))
        eh_edicao_infra_ead = bool({'polos', 'tutores'}.intersection(inlines_especificados_na_requisicao))
        tab = 'equipe' if eh_edicao_equipe else 'infraestrutura_ead' if eh_edicao_infra_ead else ''
        return httprr(f'/pafc/pafc/{obj.pk}/{f"?tab={tab}" if tab else ""}', 'Edição realizada com sucesso.')

    def tab_portaria_comissao_elaboracao_emitida(self, request, queryset):
        return queryset.filter(portaria_comissao_elaboracao_vigente__isnull=False)

    tab_portaria_comissao_elaboracao_emitida.short_description = 'Portaria da comissão emitida'

    def tab_comissao_elaboracao_definida(self, request, queryset):
        return queryset.filter(membrocomissaopafc__isnull=False).distinct()

    tab_comissao_elaboracao_definida.short_description = 'Comissão de Elaboração definida'

    def tab_revisores_tecnicos_definidos(self, request, queryset):
        return queryset.filter(revisortecnicopafc__isnull=False).distinct()

    tab_revisores_tecnicos_definidos.short_description = 'Revisores técnicos definidos'

    def tab_validadores_definidos(self, request, queryset):
        return queryset.filter(validadorpafc__isnull=False).distinct()

    tab_validadores_definidos.short_description = 'Validadores definidos'

    def get_tabs(self, request):
        return [
            'tab_portaria_comissao_elaboracao_emitida',
            'tab_comissao_elaboracao_definida',
            'tab_revisores_tecnicos_definidos',
            'tab_validadores_definidos',
        ]


admin.site.register(PAFC, PAFCAdmin)


class SolicitacaoTramitacaoAdReferendumPAFCAdmin(ModelAdminPlus):
    list_display = ('pafc', 'situacao_pafc', 'solicitante', 'data_solicitacao', 'get_situacao')
    list_filter = ('pafc', 'situacao_pafc', 'deferida')
    search_fields = ('pafc__nome_curso', 'justificativa')
    list_display_icons = True

    def get_situacao(self, obj):
        return status(obj.situacao)

    get_situacao.short_description = 'Situação'

    def has_view_permission(self, request, obj=None):
        return SolicitacaoTramitacaoAdReferendumPAFC.usuario_pode_visualizar(request.user, obj)


admin.site.register(SolicitacaoTramitacaoAdReferendumPAFC, SolicitacaoTramitacaoAdReferendumPAFCAdmin)
