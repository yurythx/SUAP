from django.urls import path

from almoxarifado import relatorio, validacao, views

urlpatterns = [
    path('material_historico/<int:material_id>/', views.material_historico),
    # Requisição
    path('form_requisicao_usuario_pedido/', views.form_requisicao_usuario_pedido),
    path('requisicao_usuario_pedido/', views.requisicao_usuario_pedido),
    path('form_requisicao_uo_pedido/', views.form_requisicao_uo_pedido),
    path('requisicao_uo_pedido/', views.requisicao_uo_pedido),
    path('requisicoes_pendentes/', views.requisicoes_pendentes),
    path('requisicao_detalhe/<str:tipo>/<int:objeto_id>/', views.requisicao_detalhe),
    path('materiais_transferidos/', views.materiais_transferidos),
    path('requisicao/<str:tipo>/<int:requisicao_id>/remover/', views.requisicao_remover),
    path('requisicao_resposta/<str:tipo>/<int:objeto_id>/', views.requisicao_resposta),
    path('requisicao_busca/', views.requisicao_busca),
    path('atualizar_valor_medio/<str:uo_sigla>/<int:material>/', views.atualizar_valor_medio),
    path('atualizar_movimentacoes/<str:uo_sigla>/<int:material>/', views.atualizar_movimentacoes),
    # Balancete Elemento de Despesa (deprecate)
    path('balancete_ed/', views.balancete_ed),
    path('balancete_ed_detalhado/', views.balancete_ed_detalhado),
    # Balancete Material
    path('balancete_material/', views.balancete_material),
    # Relatório Saldo ED
    path('saldo_ed/', views.saldo_ed),
    # Situação do Estoque
    path('situacao_estoque/', views.situacao_estoque),
    # Configuração do Estoque
    path('configuracao_estoque/', views.configuracao_estoque),
    # Relatório de Compra
    path('relatorio_compra/', views.relatorio_compra),
    # Empenho
    path('empenhos/', views.empenhos),
    path('empenho/<int:empenho_pk>/', views.empenho),
    path('empenhopermanente/<int:id_empenhopermanente>/remover/', views.empenhopermanente_remover),
    path('empenhoconsumo/<int:id_empenhoconsumo>/remover/', views.empenhoconsumo_remover),
    path('ajax/get_itens_empenho/', views.get_itens_empenho),
    path('ajax/info_solicitante/', views.info_solicitante),
    # Entrada
    path('entrada/<int:entrada_id>/', views.entrada),
    path('entrada/<int:entrada_id>/editar/', views.entrada_editar),
    path('entrada/<int:entrada_id>/remover/', views.entrada_remover),
    path('entrada/<int:entrada_id>/cancelar_itens/', views.entrada_cancelar_itens),
    path('entrada/<int:entrada_id>/adicionar_item/', views.adicionar_item),
    path('entrada_busca/', views.entrada_busca),
    path('entrada_pdf/<int:entrada_id>/', views.entrada_pdf),
    path('entrada_inventarios_pdf/<int:entrada_id>/', views.entrada_inventarios_pdf),
    path('entrada_compra/', views.entrada_compra),
    path('entrada_doacao/', views.entrada_doacao),
    path('entrada_realizar/', views.entrada_realizar),
    path('entrada_item_estornar/<str:tipo_entrada>/<int:item_id>/', views.entrada_item_estornar),
    path('detalhar_elemento_despesa/<int:elemento_despesa_id>/', views.detalhar_elemento_despesa),
    path('capa_pagamento_pdf/<int:entrada_id>/', views.capa_pagamento_pdf),
    path('buscar_servidor/<path:input>/', views.servidor),
    path('buscar_fornecedor/<path:input>/', views.fornecedor),
    path('buscar_empenho/<path:input>/', views.empenho_todos),
    path('buscar_material_consumo_estoque_uo/<int:uo_id>/<path:input>/', views.material_consumo_estoque_uo),
    path('gerar_etiquetas/', views.gerar_etiquetas),
    path('devolver_item/<str:tipo>/<int:uo>/<int:requisicao>/', views.devolver_item),
    path('cancelar_requisicaosaida/<str:tipo>/<int:uo>/<int:requisicao>/', views.cancelar_requisicaosaida),
    path('importar_estoque_csv/', views.importar_estoque_csv, name='importar_estoque_csv'),
]

urlpatterns += [
    path('validar/req_pedido/', validacao.req_pedido),
    path('validar/requisicao_responder/<str:requisicao_tipo>/', validacao.requisicao_responder),
    path('validar/entrada/', validacao.entrada),
    # Validação
    # path('validar/relatorio_balancete_ed_detalhado/', views.relatorio_balancete_ed_detalhado),
    # path('validar/telaRelatorioEstoqueED/', views.relatorio_estoque_ED_detalhado),
]

urlpatterns += [
    # Consumo Setor
    path('relatorio/consumo_setor/', relatorio.consumo_setor),
    # Nota de fornecimento
    path('relatorio/nota_fornecimento_pdf/<str:solicitante_id>/<str:data_inicio>/<str:data_fim>/', relatorio.nota_fornecimento_pdf),
    path('relatorio/nota_fornecimento_pdf/<str:requisicao_tipo>/<int:requisicao_id>/', relatorio.nota_fornecimento_pdf),
    path('relatorio/consumo_setor_html/<str:id_>/', relatorio.consumo_setor_html),
    path('relatorio/consumo_setor_pdf/<str:id_>/', relatorio.consumo_setor_pdf),
    # Balancete ED Detalhado
    # path('relatorio/balancete_ed_detalhado/', views.balancete_ed_detalhado),
    path('relatorio/balancete_ed_detalhado_html/<str:id_>/', relatorio.balancete_ed_detalhado_html),
    path('relatorio/balancete_ed_detalhado_pdf/<str:id_>/', relatorio.balancete_ed_detalhado_pdf),
    # Balancete Material
    # path('relatorio/balancete_material/', views.balancete_material),
    path('relatorio/balancete_material_pdf', relatorio.balancete_material_pdf),
]
