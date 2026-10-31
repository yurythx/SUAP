from django.urls import path

from encceja import views

urlpatterns = [
    path('solicitacao/<int:pk>/', views.solicitacao),
    path('importar_resultado/', views.importar_resultado),
    path('quantitativo/', views.quantitativo),
    path('cancelar_solicitacao/<int:pk>/', views.cancelar_solicitacao),
    path('descancelar_solicitacao/<int:pk>/', views.descancelar_solicitacao),
    path('atualizar_configuracao_solicitacao_encceja/<int:pk>/', views.atualizar_configuracao_solicitacao_encceja),
]
