from django.urls import path

from pdp_ifrn import views

urlpatterns = [
    path('resposta/<int:resposta_id>/', views.resposta),
    path('gerenciamento_respostas/', views.gerenciamento_respostas),
    path('registrar_historico/<str:resposta_id>/<str:novo_status>/<str:status_selecionado>/', views.registrar_historico),
    path('registrar_historico_selecionadas/<str:novo_status>/<str:status_selecionado>/', views.registrar_historico_selecionadas),
    path('relatorio_geral_pdp/', views.relatorio_geral_pdp),
    # path('consulta/', views.consulta_pdp),
    path('detalhes/<int:resposta_id>)/', views.detalhes_pdp),
]
