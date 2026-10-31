from django.urls import path

from protocolo import views

urlpatterns = [
    path('caixa_entrada_saida/', views.caixa_entrada_saida),
    path('caixa_tramitacao_externa/', views.caixa_tramitacao_externa),
    path('capa_processo/<int:processo_id>/', views.processo_capa),
    path('capa_processo_a3/<int:processo_id>/', views.processo_capa_a3),
    path('processo/<int:processo_id>/', views.processo),
    path('processo_editar_encaminhamento/<int:tramite_id>/', views.processo_editar_encaminhamento),
    path('processo_encaminhar/<int:tramite_id>/<str:tipo_encaminhamento_descricao>/', views.processo_encaminhar),
    path('processo_encaminhar_primeiro_tramite/<int:processo_id>/<str:tipo_encaminhamento_descricao>/', views.processo_encaminhar_primeiro_tramite),
    path('processo_finalizar/<int:processo_id>/', views.processo_finalizar),
    path('processo_imprimir_etiqueta/<int:processo_id>/', views.processo_imprimir_etiqueta),
    path('processo_informar_recebimento_externo/<int:tramite_id>/', views.processo_informar_recebimento_externo),
    path('processo_receber/<int:tramite_id>/', views.processo_receber),
    path('processo_remover_encaminhamento/<int:tramite_id>/', views.processo_remover_encaminhamento),
    path('processo_remover_finalizacao/<int:processo_id>/', views.processo_remover_finalizacao),
    path('processo_retornar_para_ambito_interno/<int:tramite_id>/', views.processo_retornar_para_ambito_interno),
    path('consulta_publica/', views.consulta_publica),
    path('visualizar_processo_consulta_publica/<int:processo_id>/', views.visualizar_processo_consulta_publica),
]
