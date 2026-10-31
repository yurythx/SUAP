from django.urls import path

from . import processa_pendencias, views

urlpatterns = [
    path('processar_pendencias_recebimento/', processa_pendencias.processar_pendencias_recebimento, name='processar_pendencias_recebimento'),
    path('consulta_estrutura/<int:repositorio_id>/', views.consulta_estrutura),
    path('processar_pendencias/', views.processar_pendencias, name='processar_pendencias'),
    path('importar_hipoteses_legais_pen/', views.importar_hipoteses_legais_pen, name='importar_hipoteses_legais_pen'),
    path('definir_hipotese_padrao_pen/', views.definir_hipotese_padrao_pen, name='definir_hipotese_padrao_pen'),
]
