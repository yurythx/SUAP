from django.urls import path

from etep import views

urlpatterns = [
    path('acompanhamento/<int:acompanhamento_pk>/', views.acompanhamento),
    path('adicionar_registro/<int:acompanhamento_pk>/', views.adicionar_registro),
    path('alterar_registro/<int:registro_pk>/', views.alterar_registro),
    path('alterar_situacao_acompanhamento/<int:acompanhamento_pk>/', views.alterar_situacao_acompanhamento),
    path('alterar_interessados/<int:acompanhamento_pk>/', views.alterar_interessados),
    path('inativar_interessado/<int:interessado_pk>/', views.inativar_interessado),
    path('reativar_interessado/<int:interessado_pk>/', views.reativar_interessado),
    path('excluir_registro/<int:registro_pk>/', views.excluir_registro),
    path('registros_ciencia_pendente/', views.registros_ciencia_pendente),
    path('notificar_acompanhamento/<int:registro_pk>/', views.notificar_acompanhamento),
    path('desvincular_acompanhamento/<int:registro_pk>/', views.desvincular_acompanhamento),
    path('dar_ciencia_acompanhamento/<int:registro_acompanhamento_interessado_pk>/', views.dar_ciencia_acompanhamento),
    path('adicionar_encaminhamentos/<int:acompanhamento_pk>/', views.adicionar_encaminhamentos),
    path('solicitacao_acompanhamento/<int:solicitacao_pk>/', views.solicitacao_acompanhamento),
    path('rejeitar_solicitacao/<int:solicitacao_pk>/', views.rejeitar_solicitacao),
    path('atividade/<int:atividade_pk>/', views.atividade),
    path('adicionar_documento/<int:atividade_pk>/', views.adicionar_documento),
    path('alterar_documento/<int:documento_pk>/', views.alterar_documento),
    path('relatorio_acompanhamento/', views.relatorio_acompanhamento),
]
