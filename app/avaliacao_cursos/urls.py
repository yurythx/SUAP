from django.urls import path

from avaliacao_cursos import views

urlpatterns = [
    path('questionario/<int:pk>/', views.questionario),
    path('questionario/<int:pk>/visualizar_respondentes/', views.visualizar_respondentes),
    path('adicionar_grupo_pergunta/<int:questionario_pk>/', views.adicionar_grupo_pergunta),
    path('adicionar_grupo_pergunta/<int:questionario_pk>/<int:grupo_pergunta_pk>/', views.adicionar_grupo_pergunta),
    path('adicionar_pergunta/<int:grupo_pergunta_pk>/', views.adicionar_pergunta),
    path('adicionar_pergunta/<int:grupo_pergunta_pk>/<int:pergunta_pk>/', views.adicionar_pergunta),
    path('adicionar_opcao_resposta/<int:pergunta_pk>/', views.adicionar_opcao_resposta),
    path('adicionar_opcao_resposta/<int:pergunta_pk>/<int:opcao_resposta_pk>/', views.adicionar_opcao_resposta),
    path('responder/<int:pk>/', views.responder),
    path('reabrir/<int:pk>/', views.reabrir),
    path('resultado/', views.resultado),
    path('avaliacao/<int:pk>/', views.avaliacao),
    path('avaliacao/<int:pk>/xls/', views.xls_avaliacao),
    path('avaliacao/<int:pk>/<int:pk_grupo>/xls/', views.xls_avaliacao),
    path('estatistica_avaliacao/<int:pk>/', views.estatistica_avaliacao),
    path('estatistica_avaliacao_componentes/<int:pk>/', views.estatistica_avaliacao_componentes),
    path('adicionar_questionario/<int:pk>/', views.adicionar_questionario),
    path('adicionar_questionario/<int:pk>/<int:questionario_pk>/', views.adicionar_questionario),
    path('estatistica_resposta/<int:pk>/', views.estatistica_resposta),
    path('estatistica_grupo_resposta/<int:pk>/', views.estatistica_grupo_resposta),
    path('resultado_avaliacao_matriz/<int:pk>/<int:matriz_pk>/', views.resultado_avaliacao_matriz),
    path('estatistica_resposta_componente/<int:pk>/<int:matriz_pk>/<int:componente_pk>/<int:segmento_pk>/', views.estatistica_resposta_componente),
    path(
        'estatistica_resposta_componente_curricular/<int:pk>/<int:componente_curricular_pk>/<int:segmento_pk>/',
        views.estatistica_resposta_componente_curricular,
    ),
    path('respostas_subjetivas_xls/<int:pk>/', views.respostas_subjetivas_xls),
    path('respostas_subjetivas_componentes_xls/<int:pk>/', views.respostas_subjetivas_componentes_xls),
    path('respostas_subjetivas_componentes_xls/<int:pk>/<int:matriz_id>/', views.respostas_subjetivas_componentes_xls),
    path(
        'justificar_avaliacao_componente_ajax/<int:respondente>/<int:campo>/<int:componente_curricular>/', views.justificar_avaliacao_componente_ajax
    ),
]
