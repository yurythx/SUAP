from django.urls import path

from pit_rit import views

urlpatterns = [
    path('frequencia_docente/', views.frequencia_docente),
    path('configuracaoatividadedocente/<int:pk>/', views.configuracaoatividadedocente),
    path('adicionar_atividade_docente/<int:pk>/<int:tipo>/<int:atividade_pk>/', views.adicionar_atividade_docente),
    path('adicionar_atividade_docente/<int:pk>/<int:tipo>/', views.adicionar_atividade_docente),
    path('deferir_todas_atividade_docente/<int:pk>/<int:tipo>/', views.deferir_todas_atividade_docente),
    path('plano_atividade_docente_pdf/<int:professor_pk>/', views.plano_atividade_docente_pdf),
    path('relatorio_atividade_docente_pdf/<int:professor_pk>/', views.relatorio_atividade_docente_pdf),
    path('relatar_atividade_docente/<int:pk>/', views.relatar_atividade_docente),
    path('planos_individuais_trabalho/', views.planos_individuais_trabalho),
    path('deferir_indeferir_atividade_docente/<int:pk>/', views.deferir_indeferir_atividade_docente),
    path('definir_horario_atividade_docente/<int:pk>/', views.definir_horario_atividade_docente),
    path('relatorio_atividades_docentes_a_deferir/', views.relatorio_atividades_docentes_a_deferir),
    path('relatorio_professores_sem_atividades_docentes/', views.relatorio_professores_sem_atividades_docentes),
    path('relatorio_ch_docente/', views.relatorio_ch_docente),
]
