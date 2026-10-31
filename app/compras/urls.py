from django.urls import path

from compras import views

urlpatterns = [
    path('processo_compra/<int:pk>/', views.processo_compra),
    path('processo_compra/<int:pk>/validar/', views.processo_compra_validar),
    path('processo_compra_relatorio_ug/<int:pk>/', views.processo_compra_relatorio_ug),
    path('processo_compra_relatorio_campus/<int:pk>/', views.processo_compra_relatorio_campus),
    path('processo_compra_relatorio_geral/<int:pk>/', views.processo_compra_relatorio_geral),
    path('relatorio_processo_compra_campus/<int:pk>/', views.relatorio_processo_compra_campus),
    path('processo_compra_relatorio_cotacao/<int:pk>/', views.processo_compra_relatorio_cotacao),
    path('processo_compra_campus/<int:pk>/', views.processo_compra_campus),
    path('processo_compra_campus/<int:pk>/validar/', views.processo_compra_campus_validar),
    path('processo_compra_editar/<int:pk>/', views.processo_compra_editar),
    path('preencher_materiais_ausentes_campus/<int:pk>/', views.preencher_materiais_ausentes_campus),
    path('detalhar_anexos/<int:pk>/', views.detalhar_anexos),
    path('calendarios_referencia/', views.calendarios_referencia),
    path('adicionar_fase/<int:pk>/', views.adicionar_fase),
    path('solicitar_participacao/<int:pk>/', views.solicitar_participacao),
    path('calendarios_processos_compras/', views.calendarios_processos_compras),
    path('compra/<int:pk>/cronograma/', views.cronograma_compra, name='cronograma_compra'),
    path('compra/<int:pk>/atualizar_etapa_atual/', views.atualizar_etapa_atual, name='atualizar_etapa_atual'),
    path('compra/<int:pk>/registrar_conclusao/', views.registrar_conclusao_processo_compra, name='registrar_conclusao_processo_compra'),
    path('compra/<int:pk>/retornar_cronograma/', views.retornar_cronograma_processo_compra, name='retornar_cronograma_processo_compra'),
    path('compra/gerenciar_execucao_etapa/<int:pk_etapacompra>/', views.gerenciar_execucao_etapa, name='gerenciar_execucao_etapa'),
    path('compra/gerenciar_comentarios_etapa/<int:pk_etapacompra>/', views.gerenciar_comentarios_etapa, name='gerenciar_comentarios_etapa'),
    path('compra/adicionar_comentario_etapa/<int:pk_etapacompra>/', views.adicionar_comentario_etapa, name='adicionar_comentario_etapa'),
    path('compra/excluir_comentario_etapa/<int:pk_comentario>/', views.excluir_comentario_etapa, name='excluir_comentario_etapa'),
    path('compra/desconsiderar_comentario_etapa/<int:pk_comentario>/', views.desconsiderar_comentario_etapa, name='desconsiderar_comentario_etapa'),
    path('get_campi_vinculados_json/', views.get_campi_vinculados_json, name='get_campi_vinculados_json'),
]
