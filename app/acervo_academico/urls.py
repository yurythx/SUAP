from django.urls import path

from acervo_academico import views

urlpatterns = [
    path('rotina/<int:pk>', views.visualizar_rotina, name='acervo_visualizar_rotina'),
    path('rotina/<int:pk>/processar', views.processar_rotina, name='acervo_processar_rotina'),
    path('rotina/<int:pk>/limpar_logs', views.limpar_logs_rotina, name='acervo_limpar_logs_rotina'),
    path('item_rotina/<int:pk>', views.visualizar_item_rotina, name='acervo_visualizar_item_rotina'),
    path('item_rotina/<int:pk>/processar', views.processar_item, name='acervo_processar_item_rotina'),
]
