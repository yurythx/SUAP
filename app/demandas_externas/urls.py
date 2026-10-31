from django.urls import path

from demandas_externas import views

urlpatterns = [
    path('periodos_demanda/', views.periodos_demanda),
    path('cadastrar_demanda/<int:periodo_id>/', views.cadastrar_demanda),
    path('demanda/<int:demanda_id>/', views.demanda),
    path('aceitar_demanda/<int:demanda_id>/', views.aceitar_demanda),
    path('nao_aceitar_demanda/<int:demanda_id>/', views.nao_aceitar_demanda),
    path('atribuir_demanda/<int:demanda_id>/', views.atribuir_demanda),
    path('indicar_campus_atendimento/<int:demanda_id>/', views.indicar_campus_atendimento),
    path('retornar_demanda/<int:demanda_id>/', views.retornar_demanda),
    path('adicionar_membro/<int:demanda_id>/', views.adicionar_membro),
    path('registrar_atendimento/<int:demanda_id>/', views.registrar_atendimento),
    path('ver_periodo/<int:periodo_id>/', views.ver_periodo),
    path('atribuir_prioridade/<int:demanda_id>/', views.atribuir_prioridade),
]
