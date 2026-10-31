from django.urls import path

from catalogo_provedor_servico import views

urlpatterns = [
    # API do Provedor
    # path('servicos/', views.servicos_ativos),
    # path('servicos/<int:id_servico_portal_govbr>/', views.servicos_ativos),
    # path('servicos/cpf/<str:cpf>/', views.servicos_disponiveis),
    # path('servicos/cpf/<str:cpf>/avaliacao_disponibilidade/', views.servicos_avaliacao_disponibilidade),
    # path('servicos/<int:id_servico_portal_govbr>/cpf/<str:cpf>/receber_solicitacao/', views.receber_solicitacao),
    # path('servicos/cpf/<str:cpf>/obter_arquivo/<str:hash_sha512_link_id>/', views.obter_arquivo),
    # TODO: Criar uma url "/servicos/autocomplete/{nome_entidade}/{texto_busca}", assim concentramos tudo num só endopoint.
    # path('servicos/autocompletar/', views.servicos_autocompletar),
    # path('servicos/cpf/<str:cpf>/acompanhamentos/', views.acompanhamentos_por_cidadao),
    # path('servicos/cpf/<str:cpf>/pendentes_avaliar/', views.solicitacoes_pendentes_de_avaliacao),
    # URLs Internas do Provedor.
    path('avaliar_solicitacao/<int:id>/', views.avaliar_solicitacao, name='avaliar_solicitacao'),
    path('executar_solicitacao/<int:id>/', views.executar_solicitacao),
    path('indeferir_solicitacao/<int:id>/', views.indeferir_solicitacao),
    path('enviar_notificacao_correcao_dados_govbr/<int:id>/', views.enviar_notificacao_correcao_dados_govbr),
    path('reenviar_notificacao_govbr/<int:id>/', views.reenviar_notificacao_govbr),
    path('retornar_para_analise_solicitacao/<int:id>/', views.retornar_para_analise_solicitacao),
    path('assumir_atendimento/<int:id>/', views.assumir_atendimento, name='assumir_atendimento'),
    path('atribuir_atendimento/<int:id>/', views.atribuir_atendimento, name='atribuir_atendimento'),
    path('dashboard/', views.dashboard, name='catalogo_dashboard'),
    path('testar_disponibilidade/', views.testar_disponibilidade, name='testar_disponibilidade'),
    # Voltada só para ambiente de desenvolvimento (DEBUG=True)
    path('apagar_atendimento/', views.apagar_atendimento, name='apagar_atendimento'),
    # Gerenciamento da equipe do serviço
    path('servico/<int:servico_id>/equipe/', views.gerenciar_equipe, name='gerenciar_equipe_servico_catalogo'),
    path('servico/<int:servico_id>/equipe/<int:uo_id>/adicionar/', views.adicionar_usuario_equipe, name='adicionar_usuario_equipe_servico_catalogo'),
    path(
        'servico/<int:servico_id>/equipe/<int:vinculo_id>/<int:uo_id>/remover/',
        views.remover_usuario_equipe,
        name='remover_usuario_equipe_servico_catalogo',
    ),
    path(
        'servico/<int:servico_id>/gerentelocalequipe/',
        views.gerenciar_gerente_equipe_local_servico_catalogo,
        name='gerenciar_gerente_equipe_servico_catalogo',
    ),
    path(
        'servico/<int:servico_id>/gerentelocalequipe/<int:uo_id>/adicionar/',
        views.adicionar_usuario_gerente_equipe_local,
        name='adicionar_usuario_gerente_equipe_local_servico_catalogo',
    ),
    path(
        'servico/<int:servico_id>/gerentelocalequipe/<int:vinculo_id>/<int:uo_id>/remover/',
        views.remover_usuario_gerente_equipe_local,
        name='remover_usuario_gerente_equipe_local_servico_catalogo',
    ),
]
