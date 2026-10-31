from django.urls import path

from boletim_servico import views

app_name = 'boletim_servico'

urlpatterns = [
    path('publico/', views.boletins_publicos, name='boletins_publicos'),
    path('gerar_boletim_servico/<int:boletim_programado_pk>/', views.gerar_boletim_servico, name='gerar_boletim_servico'),
    path('reprocessar_boletim/<int:boletim_pk>/', views.reprocessar_boletim, name='reprocessar_boletim'),
    path('remover_boletim_periodo/<int:boletim_pk>/', views.remover_boletim_periodo, name='remover_boletim_periodo'),
]
