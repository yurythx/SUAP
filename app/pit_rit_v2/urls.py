from django.urls import path

from pit_rit_v2 import views

urlpatterns = [
    path('cadastrar_plano_individual_trabalho/<int:pk>/<int:ano_letivo>/<int:periodo_letivo>/', views.cadastrar_plano_individual_trabalho),
    path('preencher_relatorio_individual_trabalho/<int:pk>/', views.preencher_relatorio_individual_trabalho),
    path('plano_atividade_docente_pdf/<int:pk>/', views.plano_atividade_docente_pdf),
    path('relatorio_atividade_docente_pdf/<int:pk>/', views.relatorio_atividade_docente_pdf),
    path('enviar_plano/<int:pk>/', views.enviar_plano),
    path('aprovar_plano/<int:pk>/', views.aprovar_plano),
    path('devolver_plano/<int:pk>/', views.devolver_plano),
    path('entregar_relatorio/<int:pk>/', views.entregar_relatorio),
    path('aprovar_relatorio/<int:pk>/', views.aprovar_relatorio),
    path('devolver_relatorio/<int:pk>/', views.devolver_relatorio),
    path('reabrir_relatorio/<int:pk>/', views.reabrir_relatorio),
    path('criar_plano/<int:professor_id>/', views.criar_plano),
]
