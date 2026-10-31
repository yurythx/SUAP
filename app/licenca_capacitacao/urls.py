from django.urls import path

from licenca_capacitacao import views

urlpatterns = [
    path('quadro/', views.quadro, name='quadro'),
    path('visualizar_servidores_por_dia/<str:data>/', views.visualizar_servidores_por_dia, name='visualizar_servidores_por_dia'),
    path('visualizar_edital_gestao/<int:edital_id>/', views.visualizar_edital_gestao, name='visualizar_edital_gestao'),
    path('visualizar_edital_servidor/<int:edital_id>/', views.visualizar_edital_servidor, name='visualizar_edital_servidor'),
    path(
        'excluir_solicitacao_alteracao_dt_inicio_exercicicio_servidor/<int:solicitacao_id>/',
        views.excluir_solicitacao_alteracao_dt_inicio_exercicicio_servidor,
        name='excluir_solicitacao_alteracao_dt_inicio_exercicicio_servidor',
    ),
    path(
        'excluir_solicitacao_alteracao_dados_servidor/<int:solicitacao_id>/',
        views.excluir_solicitacao_alteracao_dados_servidor,
        name='excluir_solicitacao_alteracao_dados_servidor',
    ),
    path('ativar_edital/<int:edital_id>/', views.ativar_edital, name='ativar_edital'),
    path('inativar_edital/<int:edital_id>/', views.inativar_edital, name='inativar_edital'),
    path('calcular_parametros_edital/<int:edital_id>/', views.calcular_parametros_edital, name='calcular_parametros_edital'),
    path(
        'operacao_pedido_licenca_capacitacao/<int:pedido_id>/<str:operacao>/',
        views.operacao_pedido_licenca_capacitacao,
        name='operacao_pedido_licenca_capacitacao',
    ),
    path('visualizar_pedido_servidor/<int:pedido_id>/', views.visualizar_pedido_servidor, name='visualizar_pedido_servidor'),
    path('visualizar_processamento/<int:processamento_id>/', views.visualizar_processamento, name='visualizar_processamento'),
    path('gerar_processamento/<int:edital_id>/<int:tipo>/', views.gerar_processamento, name='gerar_processamento'),
    path('visualizar_pedido_gestao/<int:pedido_id>/', views.visualizar_pedido_gestao, name='visualizar_pedido_gestao'),
    path('regerar_dados_processamento/<int:processamento_id>/', views.regerar_dados_processamento, name='regerar_dados_processamento'),
    path('calcular_processamento/<int:processamento_id>/', views.calcular_processamento, name='calcular_processamento'),
    path('finalizar_processamento/<int:processamento_id>/', views.finalizar_processamento, name='finalizar_processamento'),
    path('desfinalizar_processamento/<int:processamento_id>/', views.desfinalizar_processamento, name='desfinalizar_processamento'),
    path('cancelar_processamento/<int:processamento_id>/', views.cancelar_processamento, name='cancelar_processamento'),
    path('descancelar_processamento/<int:processamento_id>/', views.descancelar_processamento, name='descancelar_processamento'),
    path('definir_processamento_definitivo/<int:processamento_id>/', views.definir_processamento_definitivo, name='definir_processamento_definitivo'),
    path(
        'desfazer_definir_processamento_definitivo/<int:processamento_id>/',
        views.desfazer_definir_processamento_definitivo,
        name='desfazer_definir_processamento_definitivo',
    ),
    path(
        'editar_ordem_classificacao_gestao/<int:dado_processamento_edital_id>/',
        views.editar_ordem_classificacao_gestao,
        name='editar_ordem_classificacao_gestao',
    ),
    path('exportar_submissoes/<int:edital_id>/', views.exportar_submissoes, name='exportar_submissoes'),
    path('imprimir_pedido_servidor/<int:pedido_id>/', views.imprimir_pedido_servidor, name='imprimir_pedido_servidor'),
    path('importar_resultado_final/<int:edital_id>/', views.importar_resultado_final, name='importar_resultado_final'),
    path('solicitar_desistencia/<int:pedido_id>/', views.solicitar_desistencia, name='solicitar_desistencia'),
    path('listar_servidores_aptos_no_edital/<int:edital_id>/', views.listar_servidores_aptos_no_edital, name='listar_servidores_aptos_no_edital'),
    path('cadastrar_servidor_complementar/<int:edital_id>/', views.cadastrar_servidor_complementar, name='cadastrar_servidor_complementar'),
    path(
        'excluir_servidor_complementar/<int:edital_id>/<int:servidor_complementar_id>/',
        views.excluir_servidor_complementar,
        name='excluir_servidor_complementar',
    ),
    path('excluir_processamento/<int:processamento_id>/', views.excluir_processamento, name='excluir_processamento'),
    path('cancelar_pedido_gestao/<int:pedido_id>/', views.cancelar_pedido_gestao, name='cancelar_pedido_gestao'),
    path(
        'listar_inscritos_para_ajuste_dt_exercicio/<int:edital_id>/',
        views.listar_inscritos_para_ajuste_dt_exercicio,
        name='listar_inscritos_para_ajuste_dt_exercicio',
    ),
    path('ajustar_dt_exercicio/<int:edital_id>/<str:matricula>/', views.ajustar_dt_exercicio, name='ajustar_dt_exercicio'),
]
