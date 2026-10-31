from django.urls import path

from temp_rh2 import views

urlpatterns = [
    path('competicao_desportiva/inscricao/<int:competicao_pk>/', views.inscricao_competicoes_desportivas),
    path('competicao_desportiva/inscricao/<int:competicao_pk>/<int:inscricao_pk>/', views.inscricao_competicoes_desportivas),
    path('validar/<int:inscricao_pk>/', views.validar_homologar_inscricoes_desportivas),
    path(
        'provas_por_modalidades/<int:competicao_desportiva_pk>/',
        views.escolha_provas_por_modalidades_ajax,
        name='escolha_provas_por_modalidades_ajax',
    ),
    path('relatorio_inscritos_por_modalidade_prova/', views.relatorio_inscritos_por_modalidade_prova),
]
