from django.urls import path

from avaliacao_integrada import views

urlpatterns = [
    path('indicador/<int:pk>/', views.indicador),
    path('replicar_indicador/<int:pk>/', views.replicar_indicador),
    path('avaliacao/<int:pk>/', views.avaliacao, name='avaliacao'),
    path('avaliacao/<int:avaliacao_id>/setores_sem_areas_de_vinculacao', views.setores_sem_areas_de_vinculacao),
    path('lista_emails_comissao/<int:comissao_id>/', views.lista_emails_comissao),
    path('obter_membros_por_setor/<int:setor_id>/', views.obter_membros_por_setor),
    path('questionario/<int:pk>/', views.questionario, name='questionario'),
    path('avaliacao_externa/<str:token>', views.avaliacao_externa, name='avaliacao_externa'),
    path('avaliacao_externa/<str:token>/<int:segmento_id>/', views.questionario_avaliacao_externa, name='avaliacao_externa_responder_via_link'),
    path('remover_respostas_avaliacao/<str:token>/', views.remover_respostas_avaliacao),
    # Relatórios
    path('relatorio/<int:pk>/<int:pk_avaliacao>/', views.exibir_relatorio_indicador),
    path('relatorio/', views.relatorio),
    path('relatorio_xlsx/', views.relatorio_xlsx),
    path('escalalikert/<int:pk>/', views.escalalikert),
    path('respondente_externo_check/', views.respondente_externo_check),
    path('avaliacao/<int:pk>/enviar-email/', views.avaliacao_enviar_email, name='avaliacao_enviar_email'),
    path(
        'avaliacao/<int:pk>/quadro-resumo/<str:bloco>/',
        views.avaliacao_quadro_resumo_bloco,
        name='avaliacao_quadro_resumo_bloco',
    ),
    path(
        'avaliacao/<int:pk>/quadro-resumo-xlsx',
        views.quadro_resumo_xlsx,
        name='avaliacao_quadro_resumo_xlsx',
    ),
]
