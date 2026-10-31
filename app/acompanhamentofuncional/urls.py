from django.urls import path

from . import views

urlpatterns = [
    # cessão de servidores (exercício externo)
    path('exibir_processo_cessao/<int:processo_id>/', views.exibir_processo_cessao),
    path('adicionar_frequencia/<int:processo_id>/', views.adicionar_frequencia),
    path('excluir_frequencia/<int:frequencia_id>/', views.excluir_frequencia),
    path('frequencia_exibir_afastamento/<int:frequencia_id>/', views.frequencia_exibir_afastamento),
    path('frequencia_criar_afastamento/<int:frequencia_id>/', views.frequencia_criar_afastamento),
    path('frequencia_excluir_afastamento/<int:frequencia_id>/', views.frequencia_excluir_afastamento),
]
