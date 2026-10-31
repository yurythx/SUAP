from django.urls import path

from egressos import views

urlpatterns = [
    path('pesquisa/<int:pk>/', views.pesquisa),
    path('cadastrar_categoria/<int:pk>/', views.cadastrar_categoria),
    path('cadastrar_categoria/<int:pk>/<int:categoria_pk>/', views.cadastrar_categoria),
    path('cadastrar_pergunta/<int:pk>/', views.cadastrar_pergunta),
    path('cadastrar_pergunta/<int:pk>/<int:pergunta_pk>/', views.cadastrar_pergunta),
    path('cadastrar_opcao/<int:pk>/', views.cadastrar_opcao),
    path('cadastrar_opcao/<int:pk>/<int:opcao_pk>/', views.cadastrar_opcao),
    path('copiar_opcoes/<int:pk>/', views.copiar_opcoes),
    path('responder_pesquisa_egressos/atualizacao_cadastral/<int:pk>/', views.atualizacao_cadastral),
    path('responder_pesquisa_egressos/bloco/<int:pk>/<int:pk_categoria>/', views.responder_bloco),
    path('publicar_pesquisa/<int:pk>/', views.publicar_pesquisa),
    path('gerar_planilha_alunos_alvo/<int:pk>/', views.gerar_planilha_alunos_alvo),
    path('pesquisas_respondidas/', views.pesquisas_respondidas),
    path('reenviar_convites_alunos_nao_respondentes/<int:pk>/', views.reenviar_convites_alunos_nao_respondentes),
    path('clonar_pesquisa/<int:pk>/', views.clonar_pesquisa),
    path('ver_respostas_pesquisa/<int:pk>/', views.ver_respostas_pesquisa),
    path('exportar_respostas/<int:pk>/', views.exportar_respostas),
]
