from django.urls import path

from plan_v2 import views

urlpatterns = (
    # PDI -------------------------------------------------------------------------------------------------------------
    path('pdi/<int:pdi_pk>/ver/', views.pdi_view, name='pdi_view'),
    # Unidade Administrativa
    path('pdi/<int:pdi_pk>/unidadeadministrativa/add/', views.pdi_unidadeadministrativa_add_change, name='pdi_unidadeadministrativa_add'),
    path('pdi/<int:pdi_pk>/unidadeadministrativa/<int:ua_pk>/', views.pdi_unidadeadministrativa_add_change, name='pdi_unidadeadministrativa_change'),
    path(
        'pdi/<int:pdi_pk>/unidadeadministrativa/<int:ua_pk>/delete/', views.pdi_unidadeadministrativa_delete, name='pdi_unidadeadministrativa_delete'
    ),
    # Macroprocesso
    path('pdi/<int:pdi_pk>/macroprocesso/', views.pdi_macroprocessos_associar, name='pdi_macroprocessos_associar'),
    # Objetivo estratégico
    path('pdi/<int:pdi_pk>/objetivoestrategico/', views.pdi_objetivo_add_change, name='pdi_objetivoestrategico_add'),
    path('pdi/<int:pdi_pk>/objetivoestrategico/<int:objetivo_pk>/', views.pdi_objetivo_add_change, name='pdi_objetivoestrategico_change'),
    # Meta
    path('pdi/<int:pdi_pk>/objetivoestrategico/<int:objetivo_pk>/meta/add/', views.pdi_meta_add_change, name='pdi_meta_add'),
    path('pdi/<int:pdi_pk>/objetivoestrategico/<int:objetivo_pk>/meta/<int:meta_pk>/', views.pdi_meta_add_change, name='pdi_meta_change'),
    # Indicadores
    path('pdi/<int:pdi_pk>/meta/<int:meta_pk>/indicadores/', views.pdi_meta_indicadores, name='pdi_meta_indicadores'),
    path('pdi/<int:pdi_pk>/meta/<int:meta_pk>/indicador/add/', views.pdi_meta_indicador_add_change, name='pdi_meta_indicador_add'),
    path('pdi/<int:pdi_pk>/meta/<int:meta_pk>/indicador/<int:indicador_pk>/', views.pdi_meta_indicador_add_change, name='pdi_meta_indicador_change'),
    # Ações do Plano de Ação
    path('pdi/<int:pdi_pk>/acoes_planoacao/', views.planoacao_acao_associar, name='planoacao_acao_associar'),
    # Ações
    path('pdi/<int:pdi_pk>/acoes/', views.pdi_acao_associar, name='pdi_acao_associar'),
    # Solicitações
    path('pdi/<int:pdi_pk>/solicitacao/parecer/<int:solicitacao_pk>/', views.pdi_solicitacao_parecer, name='pdi_solicitacao_parecer'),
    # Plano de Ação - Sistêmico ----------------------------------------------------------------------------------------
    path('planoacaosistemico/<int:plano_acao_pk>/ver/', views.planoacao_sistemico_view, name='planoacao_sistemico_view'),
    # Objetivo estratégicos
    path('planoacaosistemico/<int:plano_acao_pk>/objetivos/importar/', views.pas_importar_objetivos, name='pas_importar_objetivos'),
    # Origem de recurso
    path('planoacaosistemico/<int:plano_acao_pk>/origemrecurso/add/', views.pas_origemrecurso_add_change, name='pas_origemrecurso_add'),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/origemrecurso/<int:origem_pk>/', views.pas_origemrecurso_add_change, name='pas_origemrecurso_change'
    ),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/origemrecurso/<int:origem_pk>/delete/',
        views.pas_origemrecurso_delete,
        name='pas_origemrecurso_delete',
    ),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/origemrecurso/<int:origem_recurso_pk>/ua/',
        views.pas_alterar_origem_recurso_ua,
        name='pas_alterar_origem_recurso_ua',
    ),
    # Natureza de despesa
    path(
        'planoacaosistemico/<int:plano_acao_pk>/naturezadespesa/vincular/',
        views.pas_natureza_despesa_add_delete,
        name='pas_natureza_despesa_vincular',
    ),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/naturezadespesa/<int:natureza_despesa_pk>/desvincular/',
        views.pas_natureza_despesa_add_delete,
        name='pas_natureza_despesa_desvincular',
    ),
    # Indicadores
    path('planoacaosistemico/<int:plano_acao_pk>/indicadores/<int:meta_pk>/', views.pas_indicadores_detalhar, name='pas_indicadores_detalhar'),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/indicador/<int:indicador_pa_pk>/change/',
        views.pas_indicadores_alterar,
        name='pas_indicadores_alterar',
    ),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/indicador/<int:indicador_pa_pk>/ua/',
        views.pas_indicadores_ua__alterar,
        name='pas_indicadores_ua__alterar',
    ),
    # Ações
    path(
        'planoacaosistemico/<int:plano_acao_pk>/acoes/<int:meta_pk>/',
        views.pas_indicadores_acao_vincular_desvincular,
        name='pas_indicadores_acao_vincular',
    ),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/acoes/<int:meta_pk>/acao/<int:acao_pk>/',
        views.pas_indicadores_acao_vincular_desvincular,
        name='pas_indicadores_acao_desvincular',
    ),
    # Validação
    path('planoacaosistemico/<int:plano_acao_pk>/validacao/<int:unidade_pk>/', views.pas_unidade_validacao, name='pas_unidade_validacao'),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/validacao/<int:unidade_pk>/acao/<int:acao_pk>/<str:tipo>/',
        views.pas_acao_validacao,
        name='pas_acao_validacao',
    ),
    path('planoacaosistemico/atividade/validar/', views.pas_atividade_validar, name='pas_atividade_validar'),
    # Relatórios
    path('planoacaosistemico/<int:plano_acao_pk>/disponibilidade/', views.pas_disponibilidade_financeira, name='pas_disponibilidade_financeira'),
    path(
        'planoacaosistemico/<int:plano_acao_pk>/disponibilidade/geral/',
        views.pas_disponibilidade_geral_financeira,
        name='pas_disponibilidade_geral_financeira',
    ),
    path('planoacaosistemico/relatorio/plano/', views.pas_relatorio_plano_acao, name='pas_relatorio_plano_acao'),
    # Plano de Ação - Unid. Administrativa -----------------------------------------------------------------------------
    path('planoacaounidade/<int:plano_acao_pk>/ver/', views.planoacao_unidade_view, name='planoacao_unidade_view'),
    # Ações
    path('planoacaounidade/<int:plano_acao_pk>/meta/<int:meta_pk>/acao/add/', views.paua_acao_add_change, name='paua_acao_add'),
    path('planoacaounidade/<int:plano_acao_pk>/meta/<int:meta_pk>/acao/<int:acao_pa_pk>/', views.paua_acao_add_change, name='paua_acao_change'),
    path('planoacaounidade/<int:plano_acao_pk>/meta/<int:meta_pk>/acao/<int:acao_pa_pk>/delete/', views.paua_acao_delete, name='paua_acao_delete'),
    # Atividades
    path('planoacaounidade/<int:plano_acao_pk>/acao/<int:acao_pa_pk>/atividades/', views.paua_acao_atividades, name='paua_acao_atividades'),
    path('planoacaounidade/<int:plano_acao_pk>/acao/<int:acao_pa_pk>/atividade/add/', views.paua_atividade_add_change, name='paua_atividade_add'),
    path(
        'planoacaounidade/<int:plano_acao_pk>/acao/<int:acao_pa_pk>/atividade/<int:atividade_pk>/',
        views.paua_atividade_add_change,
        name='paua_atividade_change',
    ),
    path(
        'planoacaounidade/<int:plano_acao_pk>/acao/<int:acao_pa_pk>/atividade/<int:atividade_pk>/delete/',
        views.paua_atividade_delete,
        name='paua_atividade_delete',
    ),
    # Relatórios
    path('planoacaounidade/<int:plano_acao_pk>/financeiro/', views.paua_disponibilidade_financeira, name='paua_disponibilidade_financeira'),
    path('planoacaounidade/<int:plano_acao_pk>/relatorio/plano/', views.paua_relatorio_plano_acao, name='paua_relatorio_plano_acao'),
    # Geral ------------------------------------------------------------------------------------------------------------
    # Solicitação de Cadastro de Ações
    path('geral/<int:plano_acao_pk>/solicitacao/acao/add/', views.geral_acao_solicitacao_add_change, name='geral_acao_solicitacao_add'),
    path(
        'geral/<int:plano_acao_pk>/solicitacao/acao/<int:solicitacao_pk>/',
        views.geral_acao_solicitacao_add_change,
        name='geral_acao_solicitacao_change',
    ),
    path(
        'geral/<int:plano_acao_pk>/solicitacao/acao/<int:solicitacao_pk>/delete/',
        views.geral_acao_solicitacao_delete,
        name='geral_acao_solicitacao_delete',
    ),
    # Relatorio
    path('relatorio/planoacao/<int:plano_acao_pk>/detalhamento/', views.relatorio_detalhamento, name='relatorio_detalhamento'),
    path('relatorio/planoacao/<int:plano_acao_pk>/origemrecurso/', views.relatorio_origemrecurso, name='relatorio_origemrecurso'),
    path('relatorio/planoacao/<int:plano_acao_pk>/naturezadespesa/', views.relatorio_naturezadespesa, name='relatorio_naturezadespesa'),
)
