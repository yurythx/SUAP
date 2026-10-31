from django.urls import path

from clipping import views

urlpatterns = [
    path('relatorio_periodo/', views.relatorio_periodo),
    path('importar/', views.importar),
    path('classificar/<int:publicacao_id>/<int:classificacao_id>/', views.classificar),
    path('player/<int:publicacao_id>/', views.player),
    path('', views.index),
]
