from django.urls import path

from plan_estrategico import views

urlpatterns = (
    # PDI -------------------------------------------------------------------------------------------------------------
    path('pdi/<int:pdi_pk>/ver/', views.pdi_ver, name='pdi_ver'),
    path('pdi/', views.pdi_ver, name='pdi'),
    # Unidade Gestora
    path('pdi/<int:pdi_pk>/unidadegestora/add/', views.pdi_unidadegestora_add_change, name='pdi_unidadegestora_add'),
    path('pdi/<int:pdi_pk>/unidadegestora/<int:ug_pk>/', views.pdi_unidadegestora_add_change, name='pdi_unidadegestora_change'),
    # Associar Perspectiva
    path('pdi/<int:pdi_pk>/perspectiva/', views.pdi_perspectivas_associar, name='pdi_perspectivas_associar'),
    # Objetivo estratégico
    path('pdi/<int:pdi_pk>/<int:perspectiva_pk>/objetivoestrategico/', views.pdi_objetivo_associar, name='pdi_objetivo_associar'),
    # Projeto estratégico
    path('pdi/<int:pdi_pk>/projetoestrategico/', views.pdi_projeto_add_change, name='pdi_projetoestrategico_add'),
    path('pdi/<int:pdi_pk>/projetoestrategico/<int:projeto_pk>/', views.pdi_projeto_add_change, name='pdi_projetoestrategico_change'),
    path('pdi/<int:pdi_pk>/macroprocesso/', views.pdi_macroprocesso_add_change, name='pdi_macroprocesso_add'),
    path('pdi/<int:pdi_pk>/macroprocesso/<int:projeto_pk>/', views.pdi_macroprocesso_add_change, name='pdi_macroprocesso_change'),
    path('pdi/<int:pdi_pk>/plano_interno/', views.plano_interno_add_change, name='plano_interno_add'),
    path('pdi/<int:pdi_pk>/plano_interno/<int:plano_interno_pk>/', views.plano_interno_add_change, name='plano_interno_change'),
    path('remover_planointerno/<int:planointerno_pk>/', views.remover_planointerno, name='plano_interno_remover'),
    path('remover_projeto/<int:projeto_id>/', views.remover_projeto, name='pdi_projetoestrategico_remover'),
    path('remover_etapa/<int:etapa_id>/', views.remover_etapa, name='projeto_etapa_remover'),
    path('remover_processo/<int:processo_id>/', views.remover_processo, name='macroprocesso_processo_remover'),
    # Etapa do Projeto
    path('pdi/<int:pdi_pk>/detalharprojetoestrategico/<int:projeto_pk>/', views.pdi_projeto_etapas, name='pdi_projeto_etapas'),
    path('pdi/<int:pdi_pk>/detalharmacroprocesso/<int:macroprocesso_pk>/', views.pdi_macroprocesso_processo, name='pdi_macroprocesso_processo'),
    path('projetoestrategico/<int:projeto_pk>/etapaprojeto/', views.pdi_projeto_etapa_add_change, name='pdi_projeto_etapa_add_change'),
    path('pdi/<int:projeto_pk>/etapaprojeto/<int:etapa_pk>/', views.pdi_projeto_etapa_add_change, name='pdi_projeto_etapa_add_change'),
    path(
        'pdi/macroprocesso/<int:macroprocesso_pk>/processo/<int:processo_pk>/',
        views.pdi_macroprocesso_processo_add_change,
        name='pdi_macroprocesso_processo_add_change',
    ),
    path(
        'pdi/macroprocesso/<int:macroprocesso_pk>/processo/',
        views.pdi_macroprocesso_processo_add_change,
        name='pdi_macroprocesso_processo_add_change',
    ),
    # Indicadores
    path('pdi/<int:pdi_pk>/<int:objetivo_pk>/indicador/', views.pdi_indicador_associar, name='pdi_indicador_associar'),
    path('pdi/objetivo/<int:objetivo_pk>/indicador/add/', views.indicador_add_change, name='indicador_add_change'),
    path('pdi/objetivo/<int:objetivo_pk>/indicador/<int:indicador_pk>/', views.indicador_add_change, name='indicador_add_change'),
    path('pdi/metaindicador/<int:indicador_pk>/<int:ano_base>/meta/', views.pdi_ver_meta_indicador, name='pdi_ver_meta_indicador'),
    # Farol de Desempenho
    path('pdi/<int:pdi_pk>/indicador/<int:indicador_pk>/metas/atualizar/', views.pdi_meta_atualizar, name='pdi_meta_atualizar'),
    path('variavel/<int:variavelcampus_pk>/atualizar/', views.informar_valor_variavel, name='informar_valor_variavel'),
    path('variavel/<int:variavel_pk>/visualizar/', views.visualizar_variavel, name='visualizar_variavel'),
    path('variavel_ideal/<int:variavelcampus_pk>/atualizar/', views.informar_valor_variavel_ideal, name='informar_valor_variavel_ideal'),
    path('objetivo/<int:objetivo_pk>/indicador/relevancia/atualizar/', views.indicador_relevancia_atualizar, name='indicador_relevancia_atualizar'),
    path('pdi/<int:pdi_pk>/farol/', views.pdi_farol_nivel_1, name='pdi_farol_nivel_1'),
    path('pdi/<int:pdi_pk>/farol2/<int:objetivo_pk>/<int:ano_base>/<int:uo>/', views.pdi_farol_nivel_2, name='pdi_farol_nivel_2'),
    path('pdi/<int:pdi_pk>/farol2/<int:objetivo_pk>/<int:ano_base>/', views.pdi_farol_nivel_2, name='pdi_farol_nivel_2'),
    path('ver_valores_trimestrais/<int:variavel_pk>/', views.ver_valores_trimestrais, name='ver_valores_trimestrais'),
    # Farol Consolidado
    path('pdi/<int:pdi_pk>/farol_consolidado/', views.pdi_farol_nivel_1_consolidado, name='pdi_farol_nivel_1_consolidado'),
    path(
        'pdi/<int:pdi_pk>/farol2_consolidado/<int:objetivo_pk>/<int:ano_base>/<int:uo>/',
        views.pdi_farol_nivel_2_consolidado,
        name='pdi_farol_nivel_2_consolidado',
    ),
    path(
        'pdi/<int:pdi_pk>/farol2_consolidado/<int:objetivo_pk>/<int:ano_base>/',
        views.pdi_farol_nivel_2_consolidado,
        name='pdi_farol_nivel_2_consolidado',
    ),
    path('ver_detalhamento/<int:objetivo_pk>/<int:indicador_pk>/', views.ver_detalhamento, name='ver_detalhamento'),
    path('ver_grafico_indicadores/<int:indicador_pk>/<int:ano_base>/', views.ver_grafico_indicadores, name='ver_grafico_indicadores'),
    path('ver_grafico_indicadores/<int:indicador_pk>/<int:ano_base>/<int:uo>/', views.ver_grafico_indicadores, name='ver_grafico_indicadores'),
    path('ver_faixas_valores_indicador/<int:indicador_pk>/<int:ano_base>/', views.ver_faixas_valores_indicador, name='ver_faixas_valores_indicador'),
    path(
        'ver_faixas_valores_indicador/<int:indicador_pk>/<int:ano_base>/<int:uo>/',
        views.ver_faixas_valores_indicador,
        name='ver_faixas_valores_indicador',
    ),
    # Plano de Atividades
    path('ver_plano_atividade/<int:plano_atividade_pk>/', views.ver_plano_atividade, name='ver_plano_atividade'),
    path('dados_orcamentarios/', views.dados_orcamentarios, name='dados_orcamentarios'),
    path(
        'planoatividade/detalharprojetoestrategico/<int:projeto_pk>/', views.plano_atividade_detalhar_projeto, name='plano_atividade_detalhar_projeto'
    ),
    path(
        'planoatividade/<int:projeto_plano_atividade_pk>/etapas/',
        views.plano_atividade_projeto_etapa_associar,
        name='plano_atividade_projeto_etapa_associar',
    ),
    path(
        'planoatividade/etapa/<int:etapa_projeto_plano_atividade_pk>/delete/', views.remover_etapaplanoatividade, name='remover_etapaplanoatividade'
    ),
    path(
        'planoatividade/<int:projeto_plano_atividade_pk>/origemrecurso/',
        views.plano_atividade_origem_recurso_projeto_associar,
        name='plano_atividade_origem_recurso_projeto_associar',
    ),
    path(
        'planoatividade/<int:projeto_plano_atividade_pk>/origemrecursoetapa/<int:etapa_projeto_plano_atividade_pk>/',
        views.plano_atividade_origem_recurso_etapa_projeto_associar,
        name='plano_atividade_origem_recurso_etapa_projeto_associar',
    ),
    path(
        'planoatividade/origemrecursoprojeto/<int:plano_atividade_pk>/<int:origemrecursoprojeto_id>/',
        views.informar_valor_origemrecurso_projeto,
        name='informar_valor_origemrecurso_projeto',
    ),
    path(
        'projeto/<int:projeto_plano_atividade_pk>/etapa/<int:etapa_projeto_plano_atividade_pk>/',
        views.definir_etapa_especial,
        name='definir_etapa_especial',
    ),
    path('etapa/<int:etapa_projeto_plano_atividade_pk>/', views.cancelar_etapa_especial, name='cancelar_etapa_especial'),
    path(
        'projeto/<int:projeto_plano_atividade_pk>/etapa/<int:etapa_projeto_plano_atividade_pk>/unidade_gestora/',
        views.plano_atividade_unidade_gestora_etapa_associar,
        name='unidade_gestora_etapa_associar',
    ),
    path('planoatividade/<int:plano_atividade_pk>/projetos/', views.plano_atividade_projeto_associar, name='plano_atividade_projeto_associar'),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/add/',
        views.planoatividade_origemrecurso_add_change,
        name='planoatividade_origemrecurso_add',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/<int:origem_pk>/',
        views.planoatividade_origemrecurso_add_change,
        name='planoatividade_origemrecurso_change',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/<int:origem_pk>/delete/',
        views.planoatividade_origemrecurso_delete,
        name='planoatividade_origemrecurso_delete',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/naturezadespesa/add/',
        views.planoatividade_naturezadespesa_add_change,
        name='planoatividade_naturezadespesa_add',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/planointerno/add/',
        views.planoatividade_planointerno_add_change,
        name='planoatividade_planointerno_add',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/naturezadespesa/<int:natureza_despesa_pk>/delete/',
        views.planoatividade_naturezadespesa_delete,
        name='planoatividade_naturezadespesa_delete',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/<int:origem_pk>/',
        views.planoatividade_origemrecurso_add_change,
        name='planoatividade_origemrecurso_change',
    ),
    path(
        'etapa/<int:etapa_projeto_plano_atividade_pk>/atividade/<int:atividade_pk>/', views.atividade_etapa_add_change, name='atividade_etapa_change'
    ),
    path('etapa/<int:etapa_projeto_plano_atividade_pk>/atividade/add/', views.atividade_etapa_add_change, name='atividade_etapa_add'),
    path('etapa/atividade/<int:atividade_pk>/delete/', views.remover_atividade, name='atividade_etapa_delete'),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/<int:origem_pk>/',
        views.planoatividade_origemrecurso_add_change,
        name='planoatividade_origemrecurso_change',
    ),
    path(
        'planoatividade/<int:plano_atividade_pk>/origemrecurso/<int:origem_pk>/delete/',
        views.planoatividade_origemrecurso_delete,
        name='planoatividade_origemrecurso_delete',
    ),
    path('planoatividade/ver_atividades_etapa/etapa/<int:etapa_pk>/', views.ver_atividades_etapa, name='ver_atividades_etapa'),
    path(
        'planoatividade/detalhar_atividades_unidade/<int:etapa_pk>/<int:origemrecurso_pk>/<int:unidade_pk>/',
        views.detalhar_atividades_unidade,
        name='detalhar_atividades_unidade',
    ),
    path('planoatividade/remover_rateio_atividades/<int:etapa_pk>/', views.remover_rateio_unidades, name='remover_rateio_unidades'),
    path(
        'planoatividade/remover_rateio_atividades/<int:etapa_pk>/<int:origemrecurso_pk>/',
        views.remover_rateio_atividades,
        name='remover_rateio_atividades',
    ),
    path(
        'gerenciar_compartilhamento_poder_de_gestor_ua/',
        views.gerenciar_compartilhamento_poder_de_gestor_ua,
        name='gerenciar_compartilhamento_poder_de_gestor_ua',
    ),
    path('adicionar_valores_origem_etapas/<int:origemrecurso_id>/', views.adicionar_valores_origem_etapas, name='adicionar_valores_origem_etapas'),
    path('ver_rateio_atividades/<int:plano_atividade_pk>/<int:etapa_id>/', views.ver_rateio_atividades, name='ver_rateio_atividades'),
    path('ratear_valores_unidades/<int:etapa_id>/<int:origemrecurso_id>/', views.ratear_valores_unidades, name='ratear_valores_unidades'),
    path('ratear_valores_atividades/<int:etapa_id>/<int:origemrecurso_id>/', views.ratear_valores_atividades, name='ratear_valores_atividades'),
    path('ver_rateio_reserva_tecnica/<int:etapa_id>/', views.ver_rateio_reserva_tecnica, name='ver_rateio_reserva_tecnica'),
    path('ver_extrato_reserva_tecnica/<int:plano_atividade_pk>/', views.ver_extrato_reserva_tecnica, name='ver_extrato_reserva_tecnica'),
    path('ver_extrato_projeto/<int:projeto_pk>/', views.ver_extrato_projeto, name='ver_extrato_projeto'),
    path('ver_resumo_plano/<int:plano_atividade_pk>/', views.ver_resumo_plano, name='ver_resumo_plano'),
    path('ver_extrato_unidade/<int:plano_atividade_pk>/', views.ver_extrato_unidade, name='ver_extrato_unidade'),
    path('relatorio_indicadores_pdi/<int:pdi_pk>/', views.relatorio_indicadores_pdi, name='indicadores_pdi'),
    path('relatorio_linhadotempo/', views.relatorio_linhadotempo, name='relatorio_linhadotempo'),
    path('relatorio_indicadores_pdi/', views.relatorio_indicadores_pdi, name='relatorio_pdi'),
    path('relatorio_rede/', views.relatorio_rede, name='relatorio_rede'),
    path('relatorio_ranking/', views.relatorio_ranking, name='relatorio_ranking'),
    path('plano_concluido/<int:plano_atividade_pk>/', views.plano_concluido, name='plano_concluido'),
    path(
        'requisitar_realocacao_concedente/<int:plano_atividade_pk>/', views.requisitar_realocacao_concedente, name='requisitar_realocacao_concedente'
    ),
    path(
        'requisitar_realocacao_recebedora/<int:plano_atividade_pk>/', views.requisitar_realocacao_recebedora, name='requisitar_realocacao_recebedora'
    ),
    path('requisitar_realocacao_ambas/<int:plano_atividade_pk>/', views.requisitar_realocacao_ambas, name='requisitar_realocacao_ambas'),
    path('detalhar_requisicao_realocacao/<int:id_requisicao>/', views.detalhar_requisicao_realocacao),
    path('indeferir_requisicaorealocacao/<int:requisicao_id>/', views.indeferir_requisicaorealocacao),
    path('deferir_requisicaorealocacao/<int:requisicao_id>/', views.deferir_requisicaorealocacao),
    path('cancelar_requisicaorealocacao/<int:requisicao_id>/', views.cancelar_requisicaorealocacao),
    path('detalhar_atividade/<int:atividade_id>/', views.detalhar_atividade, name='detalhar_atividade'),
    path(
        'detalhar_realocacao/<int:planoatividade_id>/<int:atividade_id>/', views.detalhar_atividade_realocacao, name='detalhar_atividade_realocacao'
    ),
    path(
        'relatorio_distribuicao_recursos_projetos/<int:plano_atividade_pk>/',
        views.relatorio_distribuicao_recursos_projetos,
        name='relatorio_distribuicao_recursos_projetos',
    ),
    path(
        'relatorio_distribuicao_recursos_ua/<int:plano_atividade_pk>/',
        views.relatorio_distribuicao_recursos_ua,
        name='relatorio_distribuicao_recursos_ua',
    ),
    path('relatorio_detalhar_recursos_ua/<int:origem_pk>/', views.relatorio_detalhar_recursos_ua, name='relatorio_detalhar_recursos_ua'),
    path('realocacoes/<int:plano_atividade_pk>/', views.realocacoes, name='realocacoes'),
    path('movimentacoes_credito/<int:plano_atividade_pk>/', views.movimentacoes_credito, name='movimentacoes_credito'),
    path('requisitar_movimentacaocredito/<int:plano_atividade_pk>/', views.requisitar_movimentacaocredito, name='requisitar_movimentacaocredito'),
    path('requisitar_estornocredito/<int:plano_atividade_pk>/', views.requisitar_estornocredito, name='requisitar_estornocredito'),
    path('requisitar_ajusteinterno/<int:plano_atividade_pk>/', views.requisitar_ajusteinterno, name='requisitar_ajusteinterno'),
    path('detalhar_movimentacao_credito/<int:id_movimentacao>/', views.detalhar_movimentacao_credito),
    path('indeferir_movimentacaocredito/<int:movimentacao_id>/', views.indeferir_movimentacaocredito),
    path('aprovar_movimentacaocredito/<int:movimentacao_id>/', views.aprovar_movimentacaocredito),
    path('atestar_ciencia_movimentacaocredito/<int:movimentacao_id>/', views.atestar_ciencia_movimentacaocredito),
    path('cancelar_movimentacaocredito/<int:movimentacao_id>/', views.cancelar_movimentacaocredito),
    path('adicionar_notacredito/<int:movimentacao_id>/', views.adicionar_notacredito, name='adicionar_notacredito'),
    path('adicionar_notadotacao/<int:movimentacao_id>/', views.adicionar_notadotacao, name='adicionar_notadotacao'),
    path('dotacaoprovisoria/<int:plano_atividade_pk>/', views.requisitar_dotacaoprovisoria, name='dotacaoprovisoria'),
    path('dotacaoempenho/<int:plano_atividade_pk>/', views.requisitar_dotacaoempenho, name='dotacaoempenho'),
    path('detalhar_requisicaodespesa/<int:requisicao_despesa_id>/', views.detalhar_requisicaodespesa),
    path('adicionar_naturezadespesa/<int:requisicao_despesa_id>/', views.adicionar_naturezadespesa),
    path('editar_naturezadespesa/<int:notaempenho_id>/', views.editar_naturezadespesa),
    path('editar_valornaturezadespesa/<int:notaempenho_id>/', views.editar_valornaturezadespesa),
    path('encaminhar_emissao_cdo/<int:requisicao_despesa_id>/', views.encaminhar_emissao_cdo),
    path('cancelar_requisicaodespesa/<int:requisicao_despesa_id>/', views.cancelar_requisicaodespesa),
    path('emitir_cdo_provisoria/<int:requisicaodespesa_id>/', views.emitir_cdo_provisorio),
    path('emitir_cdo_empenho/<int:requisicaodespesa_id>/', views.emitir_cdo_empenho),
    path('autorizar_despesa_provisoria/<int:requisicaodespesa_id>/', views.autorizar_despesa_provisorio),
    path('autorizar_despesa/<int:requisicaodespesa_id>/', views.autorizar_despesa_empenho),
    path('anuir_despesa/<int:requisicaodespesa_id>/', views.anuir_despesa),
    path('encaminhar_validacao_siafi/<int:requisicao_despesa_id>/', views.encaminhar_validacao_siafi),
    path('gerar_despesa_definitiva/<int:requisicaodespesa_id>/', views.gerar_despesa_definitiva),
    path('adicionar_notaempenho/<int:notaempenho_id>/', views.adicionar_notaempenho, name='adicionar_notaempenho'),
    path('remover_notaempenho/<int:notaempenho_id>/', views.remover_notaempenho),
    path('remover_notacredito/<int:notacredito_id>/', views.remover_notacredito),
    path('remover_notadotacao/<int:notadotacao_id>/', views.remover_notadotacao),
    path('cancelar_notas_requisicao/', views.cancelar_notas_requisicao),
    path('ajustar_requisicoes_despesa/', views.ajustar_requisicoes_despesa),
    path('editar_valorempenho/<int:notaempenho_id>/', views.editar_valorempenho),
    path(
        'adicionar_atividade_orcamentaria/<int:plano_atividade_pk>/', views.adicionar_atividade_orcamentaria, name='adicionar_atividade_orcamentaria'
    ),
    path('reforcoempenho/<int:plano_atividade_pk>/', views.requisitar_reforcoempenho, name='reforcoempenho'),
    path('adicionar_ro/<int:notaempenho_id>/', views.adicionar_ro, name='adicionar_ro'),
    path('reforcar_empenho/<int:notaempenho_id>/', views.reforcar_empenho, name='reforcar_empenho'),
    path('anulacaoempenho/<int:plano_atividade_pk>/', views.requisitar_anulacaoempenho, name='anulacaoempenho'),
    path('detalhar_movimentacoes/<int:plano_interno_id>/<int:ug_id>/', views.detalhar_movimentacoes, name='detalhar_movimentacoes'),
    path('detalhar_notas_requisicao/<int:plano_interno_id>/<int:ug_id>/', views.detalhar_notas_requisicao, name='detalhar_notas_requisicao'),
    path(
        'listar_requisicoes_despesa/<int:planoatividade_id>/<int:atividade_id>/', views.listar_requisicoes_despesa, name='listar_requisicoes_despesa'
    ),
    path('empenhos_sem_requisicao/<int:plano_atividade_pk>/', views.empenhos_sem_requisicao, name='empenhos_sem_requisicao'),
    # Filtros - Selected Autocompletes
    path('filtrar_origem_por_projeto/<int:projeto_id>/', views.filtrar_origem_por_projeto),
    path('filtrar_plano_interno_por_origem/<int:origem_recurso_id>/', views.filtrar_plano_interno_por_origem),
    path(
        'filtrar_origem_por_projeto_recebedor/<int:projeto_id_recebedor>/',
        views.filtrar_origem_por_projeto_recebedor,
        name='filtrar_origem_por_projeto_recebedor',
    ),
    path(
        'filtrar_plano_interno_por_origem_recebedor/<int:origem_recurso_id_recebedor>/',
        views.filtrar_plano_interno_por_origem_recebedor,
        name='filtrar_plano_interno_por_origem_recebedor',
    ),
    path('filtrar_processo_por_projeto/<int:projeto_id>/', views.filtrar_processo_por_projeto),
    path('filtrar_origem_por_processo/<int:processo_id>/', views.filtrar_origem_por_processo),
    path('filtrar_plano_interno_por_origem_recurso_etapa/<int:origem_recurso_id>/', views.filtrar_plano_interno_por_origem_recurso_etapa),
)
