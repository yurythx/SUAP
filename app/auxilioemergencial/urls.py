from django.urls import path

from auxilioemergencial import views

urlpatterns = [
    path('minhas_inscricoes/', views.minhas_inscricoes),
    path('inscricao/<int:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao),
    path('inscricao_composicao/<int:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao_composicao),
    path('inscricao_detalhamento/<str:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao_detalhamento),
    path('inscricao_ausencia_renda/<str:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao_ausencia_renda),
    path('inscricao_caracterizacao/<str:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao_caracterizacao),
    path('inscricao_confirmacao/<str:tipo_auxilio>/<int:inscricao_pk>/', views.inscricao_confirmacao),
    path('parecer_inscricao/<str:tipo_auxilio>/<int:inscricao_pk>/', views.parecer_inscricao),
    path('comprovante_inscricao/<str:tipo_auxilio>/<int:inscricao_pk>/', views.comprovante_inscricao),
    path('atualizar_dados_bancarios/<str:aluno_pk>/', views.atualizar_dados_bancarios),
    path('assinar_termo/<str:tipo_auxilio>/<int:inscricao_pk>/', views.assinar_termo),
    path('inscricao_documento/<int:aluno_pk>/<int:auxilio_pk>/<int:edital_pk>/', views.inscricao_documento),
    path('documentacao_aluno/<int:aluno_pk>/<str:tipo_auxilio>/<int:inscricao_pk>/', views.documentacao_aluno),
    path('folha_pagamento/<str:tipo_auxilio>/', views.folha_pagamento),
    path('encerrar_auxilio/<str:tipo_auxilio>/<int:inscricao_pk>/', views.encerrar_auxilio),
    path('prestacao_contas_dispositivo/<int:inscricao_pk>/', views.prestacao_contas_dispositivo),
    path('prestacao_contas/<int:inscricao_pk>/<str:tipo_auxilio>/', views.prestacao_contas),
    path('editar_documento/<int:documento_pk>/<int:inscricao_pk>/<str:tipo_auxilio>/', views.editar_documento),
    path('listar_prestacoes_conta/', views.listar_prestacoes_conta),
    path('adicionar_pendencia/<int:inscricao_pk>/<str:tipo_auxilio>/', views.adicionar_pendencia),
    path('adicionar_gru/<int:inscricao_pk>/<str:tipo_auxilio>/', views.adicionar_gru),
    path('concluir_prestacao/<int:inscricao_pk>/<str:tipo_auxilio>/', views.concluir_prestacao),
    path('cadastrar_gru/<int:inscricao_pk>/<str:tipo_auxilio>/', views.cadastrar_gru),
    path('editar_prestacao/<int:inscricao_pk>/<str:tipo_auxilio>/', views.editar_prestacao),
    path('editar_comprovante_gru/<int:inscricao_pk>/<str:tipo_auxilio>/', views.editar_comprovante_gru),
    path('assinatura_responsavel/<str:tipo_auxilio>/<int:inscricao_pk>/', views.assinatura_responsavel),
    path('relatorio_rendimento_frequencia/', views.relatorio_rendimento_frequencia),
    path('relatorio_alunos_assistidos/', views.relatorio_alunos_assistidos),
]
