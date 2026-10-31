from django.urls import path

from gestao import views

urlpatterns = [
    path('comparar_variavel/<str:sigla>/', views.comparar_variavel),
    path('definir_periodo_referencia/', views.definir_periodo_referencia),
    path('definir_periodo_referencia_global/', views.definir_periodo_referencia_global),
    path('detalhar_variavel/<str:sigla>/<str:uo_ativa>/', views.detalhar_variavel),
    path('exibir_indicadores/', views.exibir_indicadores),
    path('exibir_indicadores/<str:orgao_regulamentador>/', views.exibir_indicadores),
    path('exibir_variaveis/<str:tipo>/', views.exibir_variaveis),
    path('exibir_variaveis/<str:tipo>/<str:vinculo_aluno_convenio>/', views.exibir_variaveis),
    path('periodo_referencia/', views.periodo_referencia),
    path('ajax/recuperar_valor/', views.recuperar_valor),
]
