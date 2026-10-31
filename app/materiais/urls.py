from django.urls import path

from materiais import views

urlpatterns = [
    path('materialcotacao/<int:pk>/remover/', views.materialcotacao_remover),
    path('materialcotacao/<int:material_id>/', views.adicionar_cotacao),
    path('editar_materialcotacao/<int:material_id>/<int:materialcotacao_id>/', views.editar_cotacao),
    path('visualizar_materialcotacoes/<int:material_id>/', views.visualizar_cotacoes),
    path('detalhar_materialcotacoes/<int:material_id>/<int:materialcotacao_id>/', views.detalhar_cotacoes),
    path('requisicao/<int:pk>/', views.requisicao),
    path('requisicao/<int:pk>/avaliar/', views.requisicao_avaliar),
    path('requisicao_pendente/<int:pk>/remover/', views.requisicao_pendente_remover),
    path('relatorio_cotacao/', views.relatorio_cotacao),
    path('get_categorias/', views.get_categorias),
    path('ativar_cotacao/<int:materialcotacao_id>/', views.ativar_cotacao),
    path('inativar_cotacao/<int:materialcotacao_id>/', views.inativar_cotacao),
    path('visualizar_arquivo_pdf/<int:materialcotacao_id>/', views.visualizar_arquivo_pdf),
]
