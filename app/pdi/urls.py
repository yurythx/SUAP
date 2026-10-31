from django.urls import path

from pdi import views

urlpatterns = [
    path('contribuicao/', views.contribuicao),
    path('contribuicoes_campi/', views.contribuicoes_campi),
    path('contribuicao/<int:sugestao_id>/', views.contribuicao),
    path('remover_contribuicao/<int:sugestao_id>/', views.remover_contribuicao),
    path('concordar_contribuicao/<int:sugestao_id>/', views.concordar_contribuicao),
    path('discordar_contribuicao/<int:sugestao_id>/', views.discordar_contribuicao),
    path('concordar_contribuicao_consolidacao/<int:sugestao_id>/', views.concordar_contribuicao_consolidacao),
    path('discordar_contribuicao_consolidacao/<int:sugestao_id>/', views.discordar_contribuicao_consolidacao),
    path('membros/', views.membros),
    path('listar_eixos/', views.listar_eixos),
    path('listar_comissoes/', views.listar_comissoes),
    path('listar_contribuicoes/', views.listar_contribuicoes),
    path('redigir_local/', views.redigir_local),
    path('redigir_local/<int:secao_pdi_id>/', views.redigir_local),
    path('redigir_tematica/', views.redigir_tematica),
    path('redigir_tematica/<int:secao_pdi_id>/', views.redigir_tematica),
    path('confirmar_analise_sugestao/<int:sugestao_id>/', views.confirmar_analise_sugestao),
    path('exibir_redacao_tematica/<int:secao_institucional_id>/', views.exibir_redacao_tematica),
    path('contribuicao_consolidacao/', views.contribuicao_consolidacao),
    path('contribuicao_consolidacao/<int:sugestao_id>/', views.contribuicao_consolidacao),
    path('remover_contribuicao_consolidacao/<int:sugestao_id>/', views.remover_contribuicao_consolidacao),
    path('relatorios/', views.relatorios),
]
