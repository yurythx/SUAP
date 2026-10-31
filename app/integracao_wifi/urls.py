from django.urls import path

from integracao_wifi import views

urlpatterns = [
    path('renovar_autorizacao/<int:pk>/', views.renovar_autorizacao),
    path('revogar_autorizacao/<int:pk>/', views.revogar_autorizacao),
    path('cancelar_autorizacao/<int:pk>/', views.cancelar_autorizacao),
    path('gerar_tokens_wifi/', views.gerar_tokens_wifi),
]
