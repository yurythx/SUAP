from django.urls import path

from . import views

app_name = 'auditoria'

urlpatterns = [
    # Relatorio
    path('relatorio/<int:relatorio_id>/', views.visualizar_relatorio, name='visualizar_relatorio'),
    path('relatorio/documentos/listar/<int:relatorio_id>/', views.listar_relatorios_anexar, name='listar_relatorios_anexar'),
    path('relatorio/documento/anexar/<int:relatorio_id>/<int:documento_id>', views.anexar_documento_relatorio, name='anexar_documento_relatorio'),
    path('relatorio/documento/upload/<int:relatorio_id>/', views.upload_documento_ao_relatorio, name='upload_documento_ao_relatorio'),
    path('relatorio/documento/remover/<int:relatorio_documento_id>/', views.remover_documento_relatorio, name='remover_documento_relatorio'),
    path('relatorio/documento/editar/<int:relatorio_documento_id>/', views.editar_relatorio_documento, name='editar_relatorio_documento'),
    # Recomendação
    path('recomendacao/<int:recomendacao_id>/', views.visualizar_recomendacao, name='visualizar_recomendacao'),
    path('recomendacao/revisar/<int:recomendacao_id>/', views.revisar_recomendacao, name='revisar_recomendacao'),
    path('recomedacao/monitorar/<int:recomendacao_id>/', views.monitorar_recomendacao, name='monitorar_recomendacao'),
    path('recomedacao/reiniciar_monitoramento/<int:recomendacao_id>/', views.reiniciar_monitoramento, name='reiniciar_monitoramento'),
    path('recomedacao/cancelar/<int:recomendacao_id>/', views.cancelar_recomendacao, name='cancelar_recomendacao'),
    path('recomedacao/consolidar/<int:recomendacao_id>/', views.consolidar_recomendacao, name='consolidar_recomendacao'),
    path(
        'recomendacao/comentario/adicionar/<int:recomendacao_id>/', views.adicionar_comentario_recomendacao, name='adicionar_comentario_recomendacao'
    ),
    path('recomendacao/documentos/listar/<int:recomendacao_id>/', views.listar_documentos_anexar, name='listar_documentos_anexar'),
    path(
        'recomendacao/documento/anexar/<int:recomendacao_id>/<int:documento_id>',
        views.anexar_documento_recomendacao,
        name='anexar_documento_recomendacao',
    ),
    path('recomendacao/documento/upload/<int:recomendacao_id>/', views.upload_documento_recomendacao, name='upload_documento_recomendacao'),
    path(
        'recomendacao/documento/remover/<int:recomendacao_documento_id>/', views.remover_documento_recomendacao, name='remover_documento_recomendacao'
    ),
    # Monitoramentos
    path('monitoramentos/', views.monitoramentos, name='meus_monitoramentos'),
    path('monitoramento/<int:monitoramento_id>/', views.visualizar_monitoramento, name='visualizar_monitoramento'),
    path('monitoramento/cancelar/<int:monitoramento_id>/', views.cancelar_monitoramento, name='cancelar_monitoramento'),
    path('monitoramento/finalizar/<int:monitoramento_id>/', views.finalizar_monitoramento, name='finalizar_monitoramento'),
    path(
        'monitoramento/manifestacao/prorrogar/<int:monitoramento_id>/',
        views.solicitar_prorrogacao_manifestacao,
        name='solicitar_prorrogacao_manifestacao',
    ),
    path(
        'monitoramento/manifestacao/adicionar/<int:monitoramento_id>/',
        views.adicionar_manifestacao_monitoramento,
        name='adicionar_manifestacao_monitoramento',
    ),
    path('monitoramento/manifestacao/entregar/<int:manifestacao_id>/', views.entregar_manifestacao, name='entregar_manifestacao'),
    path('monitoramento/manifestacao/receber/<int:manifestacao_id>/', views.receber_manifestacao, name='receber_manifestacao'),
    path('monitoramento/manifestacao/responder/<int:manifestacao_id>/', views.adicionar_posicionamento, name='adicionar_posicionamento'),
    path('monitoramento/solicitacao/<int:monitoramento_id>/', views.enviar_solicitacao_providencia, name='enviar_solicitacao_providencia'),
    path('monitoramento/relatorios/monitoramentos_por_unidade/', views.monitoramentos_por_unidade, name='monitoramentos_por_unidade'),
    path(
        'monitoramento/designar_servidor/<int:monitoramento_id>',
        views.designar_servidor_para_monitoramento,
        name='designar_servidor_para_monitoramento',
    ),
    path('monitoramento/revogar_indicacao/<int:indicacao_id>', views.revogar_indicacao_monitoramento, name='revogar_indicacao_monitoramento'),
    path(
        'monitoramento/concluir_indicacao_monitoramento/<int:indicacao_id>',
        views.concluir_indicacao_monitoramento,
        name='concluir_indicacao_monitoramento',
    ),
    # Manifestacoes
    path('manifestacao/<int:manifestacao_id>/', views.visualizar_manifestacao, name='visualizar_manifestacao'),
    path('manifestacao/editar/<int:manifestacao_id>/', views.editar_manifestacao, name='editar_manifestacao'),
    path('manifestacao/remover/<int:manifestacao_id>/', views.remover_manifestacao, name='remover_manifestacao'),
    path('manifestacao/reclassificar/<int:manifestacao_id>/', views.reclassificar_manifestacao, name='reclassificar_manifestacao'),
    path('manifestacao/documentos/listar/<int:manifestacao_id>/', views.listar_manifestacoes_anexar, name='listar_manifestacoes_anexar'),
    path(
        'manifestacao/documento/anexar/<int:manifestacao_id>/<int:documento_id>',
        views.anexar_documento_manifestacao,
        name='anexar_documento_manifestacao',
    ),
    path('manifestacao/documento/upload/<int:manifestacao_id>/', views.upload_documento_manifestacao, name='upload_documento_manifestacao'),
    path(
        'manifestacao/documento/remover/<int:manifestacao_documento_id>/', views.remover_documento_manifestacao, name='remover_documento_manifestacao'
    ),
    path('manifestacao/manifestacoes_a_enviar/', views.manifestacoes_a_enviar, name='manifestacoes_a_enviar'),
    path('manifestacao/manifestacoes_pendentes/', views.manifestacoes_pendentes, name='manifestacoes_pendentes'),
    # Posicionamentos
    path('monitoramento/posicionamento/<int:posicionamento_id>/', views.visualizar_posicionamento, name='visualizar_posicionamento'),
    path('monitoramento/posicionamento/editar/<int:posicionamento_id>/', views.editar_posicionamento, name='editar_posicionamento'),
    path('monitoramento/posicionamento/remover/<int:posicionamento_id>/', views.remover_posicionamento, name='remover_posicionamento'),
    path('monitoramento/posicionamento/publicar/<int:posicionamento_id>/', views.publicar_posicionamento, name='publicar_posicionamento'),
    path(
        'monitoramento/posicionamento/revisao/solicitar/<int:posicionamento_id>/',
        views.solicitar_revisao_posicionamento,
        name='solicitar_revisao_posicionamento',
    ),
    path(
        'monitoramento/posicionamento/revisao/adicionar/<int:posicionamento_id>/',
        views.adicionar_revisao_posicionamento,
        name='adicionar_revisao_posicionamento',
    ),
    path('monitoramento/posicionamento/revisao/editar/<int:revisao_id>/', views.editar_revisao_posicionamento, name='editar_revisao_posicionamento'),
    path(
        'monitoramento/posicionamento/revisao/remover/<int:revisao_id>/', views.remover_revisao_posicionamento, name='remover_revisao_posicionamento'
    ),
    path('monitoramento/posicionamento/revisao/enviar/<int:revisao_id>/', views.enviar_revisao_posicionamento, name='enviar_revisao_posicionamento'),
    path('monitoramento/em_monitoramento/<int:relatorio_id>', views.monitoramentos_em_monitoramento, name='monitoramentos_em_monitoramento'),
    path('monitoramento/concluidos/<int:relatorio_id>/', views.monitoramentos_concluidos, name='monitoramentos_concluidos'),
    path('monitoramento/finalizados/<int:relatorio_id>/', views.monitoramentos_finalizados, name='monitoramentos_finalizados'),
    path('monitoramento/cancelados/<int:relatorio_id>/', views.monitoramentos_cancelados, name='monitoramentos_cancelados'),
    path('monitoramento/expirados/<int:relatorio_id>/', views.monitoramentos_expirados, name='monitoramentos_expirados'),
    path('monitoramento/expirando/<int:relatorio_id>/', views.monitoramentos_expirando, name='monitoramentos_expirando'),
    # Solicitações
    path('solicitacao/<int:solicitacao_id>/', views.visualizar_solicitacao_providencia, name='visualizar_solicitacao_providencia'),
    path('solicitacao/cancelar/<int:solicitacao_id>/', views.cancelar_solicitacao_providencia, name='cancelar_solicitacao_providencia'),
    path('solicitacao/remover/<int:solicitacao_id>/', views.remover_solicitacao_providencia, name='remover_solicitacao_providencia'),
    # Comentarios
    path('comentario/desconsiderar/<int:comentario_id>/', views.desconsiderar_comentario, name='desconsiderar_comentario'),
    path('comentario/remover/<int:comentario_id>/', views.excluir_comentario, name='excluir_comentario'),
    # Benefícios
    path('beneficio/<int:beneficio_id>/', views.visualizar_beneficio, name='visualizar_beneficio'),
    path('beneficio/<int:beneficio_id>/parcelas/', views.beneficio_adicionar_parcela, name='beneficio_adicionar_parcela'),
    path('beneficio/parcelas/<int:parcela_id>/editar/', views.beneficio_editar_parcela, name='beneficio_editar_parcela'),
    path('beneficio/parcelas/<int:parcela_id>/remover/', views.beneficio_remover_parcela, name='beneficio_remover_parcela'),
    path('beneficio/documento/upload/<int:beneficio_id>/', views.upload_documento_beneficio, name='upload_documento_beneficio'),
    path('beneficio/monitorar/<int:beneficio_id>/', views.monitorar_beneficio, name='monitorar_beneficio'),
    path('beneficio/concluir/<int:beneficio_id>/', views.concluir_beneficio, name='concluir_beneficio'),
    path('beneficio/reiniciar/<int:beneficio_id>/', views.reiniciar_monitoramento_beneficio, name='reiniciar_monitoramento_beneficio'),
    path('beneficio/cancelar/<int:beneficio_id>/', views.cancelar_beneficio, name='cancelar_beneficio'),
    path('beneficio/finalizar/<int:beneficio_id>/', views.finalizar_beneficio, name='finalizar_beneficio'),
    path('beneficio/documentos/listar/<int:beneficio_id>/', views.listar_beneficio_anexar, name='listar_beneficio_anexar'),
    path('beneficio/documento/anexar/<int:beneficio_id>/<int:documento_id>/', views.anexar_documento_beneficio, name='anexar_documento_beneficio'),
    path(
        'beneficio/adicionar/monitoramento/<int:monitoramento_id>/',
        views.vincular_beneficio_ao_monitoramento,
        name='vincular_beneficio_ao_monitoramento',
    ),
    path('beneficios/documento/remover/<int:beneficio_documento_id>/', views.remover_documento_beneficio, name='remover_documento_beneficio'),
    path('beneficios/relatorios/financeiros/', views.relatorio_beneficios_financeiros_view, name='relatorio_beneficios_financeiros'),
    path('beneficios/relatorios/qualitativos/', views.relatorio_beneficios_qualitativos_view, name='relatorio_beneficios_qualitativos'),
    # Relatorios
    path('relatorios/raint/', views.relatorios_raint, name='relatorios_raint'),
    path('relatorios/estoque/recomendacoes/', views.estoque_recomendacoes, name='estoque_recomendacoes'),
    path('relatorios/estoque/monitoramentos/', views.estoque_monitoramentos, name='estoque_monitoramentos'),
    path('relatorios/paint/relatorio_carga_horaria', views.relatorio_carga_horaria, name='relatorio_carga_horaria'),
    # PAINT
    path('paint/<int:paint_id>', views.visualizar_paint, name='visualizar_paint'),
    path('paint/carregar_ch_auditores/<int:paint_id>', views.carregar_ch_auditores, name='carregar_ch_auditores'),
    path('paint/planejamento/anual/<int:planejamento_id>', views.planejamento_anual_auditor, name='planejamento_anual_auditor'),
    path('paint/planejamento/anual/<int:planejamento_id>/sincronizar', views.sincronizar_planejamento, name='sincronizar_planejamento'),
    path('paint/planejamento/anual/<int:planejamento_id>/enviar-para-homologacao', views.enviar_para_homologacao, name='enviar_para_homologacao'),
    path('paint/planejamento/anual/<int:planejamento_id>/analisar', views.analisar_planejamento, name='analisar_planejamento'),
    path('paint/planejamento/anual/<int:planejamento_id>/deferir', views.deferir_planejamento, name='deferir_planejamento'),
    path('paint/planejamento/anual/<int:planejamento_id>/indeferir', views.indeferir_planejamento, name='indeferir_planejamento'),
    path('paint/planejamento/anual/<int:planejamento_id>/retornar-para-rascunho', views.retornar_para_rascunho, name='retornar_para_rascunho'),
    # Afastamentos
    path('paint/afastamento/<int:afastamento_id>/adicionar', views.cadastrar_afastamento, name='cadastrar_afastamento'),
    path('paint/afastamento/<int:afastamento_id>/editar', views.editar_afastamento, name='editar_afastamento'),
    path('paint/afastamento/<int:afastamento_id>/remover', views.remover_afastamento, name='remover_afastamento'),
    path('paint/afastamento/<int:afastamento_id>/avaliar', views.avaliar_afastamento, name='avaliar_afastamento'),
    # Painel de indicadores
    path('indicadores/monitoramento/painel/', views.dashboard_monitoramento_view, name='dashboard_monitoramento'),
    path('indicadores/beneficio/painel/', views.dashboard_beneficio_view, name='dashboard_beneficios'),
]
