from django.urls import path

from pit_rit_v3 import views

urlpatterns = [
    path('criar_plano/<int:professor_id>/', views.criar_plano),
    path('planejar_atividade/<int:pit_id>/<int:grupo_id>/<int:pk>/', views.planejar_atividade),
    path('planejar_atividade/<int:pit_id>/<int:grupo_id>/', views.planejar_atividade),
    path('remover_atividade/<int:pit_id>/<int:pk>/', views.remover_atividade),
    path('enviar_plano/<int:pk>/', views.enviar_plano),
    path('aprovar_plano/<int:pk>/', views.aprovar_plano),
    path('devolver_plano/<int:pk>/', views.devolver_plano),
    path('desfazer_envio_plano/<int:pk>/', views.desfazer_envio_plano),
    path('desfazer_envio_relatorio/<int:pk>/', views.desfazer_envio_relatorio),
]
