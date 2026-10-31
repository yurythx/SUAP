from django.urls import path

from sica import views

urlpatterns = [
    path('editar_aluno/<int:pk>/', views.editar_aluno),
    path('matriz/<int:pk>/<int:ano_inicio>/<int:ano_fim>/', views.matriz),
    path('matriz/<int:pk>/', views.matriz),
    path('historico/<int:pk>/', views.historico),
    path('invalidar_registros_emissao/<int:pk>/', views.invalidar_registros_emissao),
    path('atualizar_componente_curricular/<int:pk>/', views.atualizar_componente_curricular),
    path('historico_sica_pdf/<int:pk>/', views.historico_sica_pdf),
    path('declaracao_sica_pdf/<int:pk>/', views.declaracao_sica_pdf),
    path('atualizar_registro/<int:pk>/', views.atualizar_registro),
    path('atualizar_registro/<int:pk>/<int:registro_pk>/', views.atualizar_registro),
]
