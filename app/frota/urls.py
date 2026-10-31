from django.urls import path

from frota import relatorio, views

urlpatterns = [
    path('agendamento/<int:agendamento_id>/', views.agendamento),
    path('avaliar_agendamento_viagem/<int:agendamento_id>/', views.avaliar_agendamento_viagem),
    path('viagens_agendadas/', views.viagens_agendadas),
    path('saida_viagem/<int:resp_agendamento_id>/', views.saida_viagem),
    path('viagens_iniciadas/', views.viagens_iniciadas),
    path('chegada_viagem/<int:viagem_id>/', views.chegada_viagem),
    path('viagens/', views.viagens),
    path('viagem/<int:viagem_id>/', views.viagem),
    path('pdf_requisicao/<int:viagem_id>/', views.pdf_requisicao),
    path('viatura/<int:viatura_id>/', views.viatura),
    path('viagem_retroativa/', views.viagem_retroativa),
    path('ordem_abastecimento/<int:viagem_id>/', views.ordem_abastecimento),
    path('estatisticas_viaturas/', views.estatisticas_viaturas),
    path('estatisticas_deslocamento/', views.estatisticas_deslocamento),
    path('viagens_por_viatura/', views.viagens_por_viatura),
    path('estatistica_viagens_por_campus_setor/', views.estatistica_viagens_por_campus_setor),
    path('manutencaoviatura/<int:servico_id>/', views.manutencaoviatura),
    path('ver_calendario_agendamento/', views.ver_calendario_agendamento),
    path('autorizar_agendamento/<int:agendamento_id>/<str:opcao>/', views.autorizar_agendamento),
    path('controle_revisoes_viaturas/', views.controle_revisoes_viaturas),
    path('editar_proxima_revisao_viatura/<int:viatura_id>/', views.editar_proxima_revisao_viatura),
    path('editar_agendamento_deferido/<int:agendamento_id>/', views.editar_agendamento_deferido),
    path('ver_solicitacoes_edicao/<int:agendamento_id>/', views.ver_solicitacoes_edicao),
    path('avaliar_edicao/<int:edicao_id>/<int:opcao>/', views.avaliar_edicao),
    path('cadastrar_multa/<int:viagem_id>/', views.cadastrar_multa),
    path('editar_multa/<int:multa_id>/', views.editar_multa),
    path('visualizar_multas/<int:viagem_id>/', views.visualizar_multas),
    path('validar_saida/<int:viagem_id>/', views.validar_saida),
    path('validar_chegada/<int:viagem_id>/', views.validar_chegada),
    path('validar_ordem_abastecimento/<int:ordem_id>/', views.validar_ordem_abastecimento),
    path('ver_passageiros_viagem/<int:viagem_id>/', views.ver_passageiros_viagem),
    path('ver_ordens_abastecimento_viagem/<int:viagem_id>/', views.ver_ordens_abastecimento_viagem),
    path('baixar_notas_fiscais_servicos/', views.baixar_notas_fiscais_servicos),
]

urlpatterns += [
    path('relatorio_viaturas/', relatorio.relatorio_viaturas),
    path('relatorio_motoristas_temporarios/', relatorio.relatorio_motoristas_temporarios),
    path('relatorio_solicitacoes_por_pessoa/', relatorio.relatorio_solicitacoes_por_pessoa),
    path('relatorio_deslocamento_por_viatura/', relatorio.relatorio_deslocamento_por_viatura),
    path('relatorio_consumo_por_maquina/', relatorio.relatorio_consumo_por_maquina),
    path('relatorio_viagens_por_motorista/', relatorio.relatorio_viagens_por_motorista),
]
