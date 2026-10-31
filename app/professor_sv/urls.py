from django.urls import path

from professor_sv import views

urlpatterns = [
    path('configuracao/', views.configuracao, name='configuracao'),
    path('configuracao/<str:cadastrar>/', views.configuracao, name='configuracao_cadastrar'),
    path('seleciona_campus/', views.seleciona_campus, name='seleciona_campus'),
    path('seleciona_categoria/', views.seleciona_categoria, name='seleciona_categoria'),
    path('cadastrar_vaga/<str:categoria_id>/', views.cadastrar_vaga, name='cadastrar_vaga'),
    path('gerenciar_vaga/<int:vaga_id>/', views.gerenciar_vaga, name='gerenciar_vaga'),
    path('emprestar_vaga/<int:vaga_id>/', views.emprestar_vaga, name='emprestar_vaga'),
    path('desfazer_emprestimo_vaga/<int:vaga_id>/', views.desfazer_emprestimo_vaga, name='desfazer_emprestimo_vaga'),
    path('devolver_emprestimo_vaga/<int:vaga_id>/', views.devolver_emprestimo_vaga, name='devolver_emprestimo_vaga'),
    path('ativar_vaga/<int:vaga_id>/', views.ativar_vaga, name='ativar_vaga'),
    path('desativar_vaga/<int:vaga_id>/', views.desativar_vaga, name='desativar_vaga'),
    path('remover_vaga/<int:vaga_id>/', views.remover_vaga, name='remover_vaga'),
    path('aprovar_solicitacao_emprestimo/', views.aprovar_solicitacao_emprestimo, name='aprovar_solicitacao_emprestimo'),
    path('cancelar_solicitacao_emprestimo/<int:sol_emp_id>/', views.cancelar_solicitacao_emprestimo, name='cancelar_solicitacao_emprestimo'),
    path('seleciona_vaga_para_contrato/', views.seleciona_vaga_para_contrato, name='seleciona_vaga_para_contrato'),
    path('cadastrar_contrato/<int:vaga_id>/', views.cadastrar_contrato, name='cadastrar_contrato'),
    path('gerenciar_contrato/<int:contrato_id>/', views.gerenciar_contrato, name='gerenciar_contrato'),
    path('editar_contrato/<int:contrato_id>/', views.editar_contrato, name='editar_contrato'),
    path('cadastrar_publicacao_contrato/<int:contrato_id>/', views.cadastrar_publicacao_contrato, name='cadastrar_publicacao_contrato'),
    path('remover_publicacao_contrato/<int:contrato_publicacao_id>/', views.remover_publicacao_contrato, name='remover_publicacao_contrato'),
    path('cadastrar_aditivo_contrato/<int:contrato_id>/', views.cadastrar_aditivo_contrato, name='cadastrar_aditivo_contrato'),
    path('remover_aditivo_contrato/<int:contrato_aditivo_id>/', views.remover_aditivo_contrato, name='remover_aditivo_contrato'),
    path('cadastrar_aditivo_tempo_contrato/<int:contrato_id>/', views.cadastrar_aditivo_tempo_contrato, name='cadastrar_aditivo_tempo_contrato'),
    path(
        'remover_aditivo_tempo_contrato/<int:contrato_aditivo_tempo_id>/', views.remover_aditivo_tempo_contrato, name='remover_aditivo_tempo_contrato'
    ),
    path('finalizar_contrato/<int:contrato_id>/', views.finalizar_contrato, name='finalizar_contrato'),
    path('remover_finalizacao_contrato/<int:contrato_id>/', views.remover_finalizacao_contrato, name='remover_finalizacao_contrato'),
    path('cancelar_contrato/<int:contrato_id>/', views.cancelar_contrato, name='cancelar_contrato'),
    path('quadro_vagas/', views.quadro_vagas, name='quadro_vagas'),
    path('quadro_limites/', views.quadro_limites, name='quadro_limites'),
]
