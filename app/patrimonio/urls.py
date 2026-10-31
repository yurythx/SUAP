from django.urls import path

from patrimonio import relatorio, views

urlpatterns = [
    # RELATÓRIOS
    path('total_ed_periodo_pdf/', relatorio.totalizacao_ed_PeriodoPDF),
    path('termos/', relatorio.termos),
    path('relatorio/termos_pdf/', relatorio.termos_pdf),
    path('total_periodo/', relatorio.total_periodo),
    path('total_campus/', relatorio.total_atual_por_campus),
    path('total_campus_html/<str:id_>/', relatorio.total_atual_por_campus_html),
    path('detalhamento_categoria/<int:categoria>/<int:data_final>/', relatorio.total_atual_categoria),
    path('detalhamento_categoria/<int:categoria>/<int:campus>/<str:data_final>/', relatorio.total_atual_categoria),
    path('totalizacao_periodo_pdf/', relatorio.totalizacao_periodo_pdf),
    path('total_ed_acumulado_ateh_periodo/<int:mes>/<int:ano>/', relatorio.total_ed_acumulado_ateh_periodo_html),
    path('total_ed_acumulado_ateh_periodo_pdf/', relatorio.total_ed_acumulado_ateh_periodo_pdf),
    path('relatorioBaixaPDF/<int:baixa_id>/', relatorio.baixa_pdf),
    path('inventario_depreciacao/', relatorio.inventario_depreciacao),
    path('inventario_depreciacao_planocontabil_novo/', relatorio.inventario_depreciacao_planocontabil_novo),
    path('relatorio/termo_cautela_PDF/<int:cautela_id>/', relatorio.termo_cautela_PDF),
    path('relatorio/transferencia/<int:requisicao_id>/', relatorio.termo_transferencia),
]

urlpatterns += [
    # Carga
    path('carga/', views.carga),
    path('inventarios_pendentes/', views.exibir_inventarios_pendentes),
    # NOVA REQUISIÇÃO
    path('requisitar_transferencia/', views.requisitar_transferencia),
    path('cancelar_requisicao/<int:requisicao_id>/', views.cancelar_requisicao),
    path('requisicao/<int:id_requisicao>/', views.requisicao),
    path('deferir_requisicao/<int:requisicao_id>/', views.deferir_requisicao),
    path('indeferir_requisicao/<int:requisicao_id>/', views.indeferir_requisicao),
    path('informar_pa_origem_requisicao/<int:requisicao_id>/', views.informar_pa_origem_requisicao),
    path('informar_pa_destino_requisicao/<int:requisicao_id>/', views.informar_pa_destino_requisicao),
    path('editar_pa_origem_requisicao/<int:requisicao_id>/', views.editar_pa_origem_requisicao),
    path('editar_pa_destino_requisicao/<int:requisicao_id>/', views.editar_pa_destino_requisicao),
    # BAIXA
    path('baixa/<int:baixa_pk>/', views.baixa),
    path('baixa/editar/<int:baixa_pk>/', views.baixa_editar),
    path('baixa/<int:baixa_pk>/remover/', views.baixa_remover),
    path('baixa/<int:baixa_pk>/remover_item/<int:movimentopatrim_pk>/', views.baixa_remover_item),
    # CAUTELA
    path('cautela/adicionar/', views.cautela_adicionar),  # ESTÁ SENDO USADA?
    path('cautela/<int:cautela_pk>/', views.cautela),
    path('tela_cautela_detalhe/<int:cautela_id>/', views.tela_cautela_detalhe),
    # CAUTELA INVENTÁRIO
    path('cautelainventario/<int:id_cautelainventario>/remover/', views.cautelainventario_remover),
    # INVENTARIO
    path('inventario_busca/', views.inventario_busca),
    path('historico_movimentacao_inventario/<int:inventario_numero>/', views.historico_movimentacao_inventario),
    path('inventario_editar/<int:inventario_id>/', views.inventario_editar),
    path('inventario/<int:inventario_numero>/', views.inventario),
    path('inventario_adicionar_rotulo_sala/', views.inventario_adicionar_rotulo_sala),
    path('inventarios_cargas/', views.inventarios_cargas),
    path('adicionar_foto_inventario/<int:inventario_id>/', views.adicionar_foto_inventario),
    path('remover_foto_inventario/<int:inventario_numero>/<int:foto_id>/', views.remover_foto_inventario),
    path('visualizar_foto_inventario/<int:foto_id>/', views.visualizar_foto_inventario),
    path('requisicao_inventario_uso_pessoal/<int:pk>/', views.requisicao_inventario_uso_pessoal),
    path('remover_rotulo/<int:inventario_id>/<int:rotulo_id>/', views.remover_rotulo),
    path('requisicao_inventario_uso_pessoal_listar/', views.requisicao_inventario_uso_pessoal_listar),
    path('listar_inventarios_carga_contabil_inconsistentes/', views.listar_inventarios_carga_contabil_inconsistentes),
    path('corrigir_carga_contabil/<int:inventario_id>/', views.corrigir_carga_contabil),
    path('inventario_reavaliar/<int:inventario_id>/', views.reavaliar_inventario),
    path('inventario_ajustar_valor/<int:inventario_id>/', views.ajustar_valor_inventario),
    path('filtra_inventario_transferencia/', views.filtra_inventario_transferencia),
    path('atualizar_carga_contabil/<int:requisicao_id>/', views.atualizar_carga_contabil),
    # MIGRAÇÃO DE INVENTÁRIOS (assistente de importação por planilha)
    path('migracao/', views.migracao),
    path('migracao/modelo/', views.migracao_modelo),
    # SERVIDORES
    path('servidores_com_carga/', views.servidores_com_carga),
    # RELATÓRIOS
    path('relatorios/inventarios_nao_conferidos/', views.inventarios_nao_conferidos),
    path('total_ed_periodo/', views.totalizacao_ed_periodo),
    path('total_ed_periodo_planocontas/', views.totalizacao_ed_periodo_planocontas),
    # Conferência (Coletor)
    path('autorizar_coletor/<int:conferencia_id>/', views.autorizar_coletor),
    path('imprimir_conferencia/<int:conferencia_id>/', views.imprimir_conferencia),
    path('conferenciasala/<int:conferencia_id>/', views.conferenciasala),
    path('conferenciasala/<int:item_id>/remover/', views.conferenciasala_item_remover),
    path('conferencia_visualizar_qrcode/<int:conferencia_id>/', views.conferencia_visualizar_qrcode),
    path('baixar_app_conferencia', views.baixar_app_conferencia, name='baixar_app_conferencia'),
]
