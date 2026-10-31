from django.urls import path

from portaria import views

urlpatterns = [
    path('registro_acesso_campus/', views.registro_acesso_campus),
    path('listar_pessoas/', views.listar_pessoas),
    path('registrar_acesso_pessoa/<int:vinculo_id>/', views.registrar_acesso_pessoa),
    path('registrar_acesso_pessoa_externa/<int:visitante_id>/', views.registrar_acesso_pessoa_externa),
    path('cadastrar_pessoa_externa/', views.cadastrar_pessoa_externa),
    path('alterar_pessoa_externa/<int:visitante_id>/', views.alterar_pessoa_externa),
    path('visualizar_pessoa_externa/<int:visitante_id>/', views.visualizar_pessoa_externa),
    path('cadastrar_baixa_em_acesso/', views.cadastrar_baixa_em_acesso),
    path('registrar_chave_wifi/', views.registrar_chave_wifi),
    path('listar_historico_acesso_geral/', views.listar_historico_acesso_geral),
    path('deferir_solicitacaoentrada/<int:solicitacaoentrada_id>/', views.deferir_solicitacaoentrada),
    path('indeferir_solicitacaoentrada/<int:solicitacaoentrada_id>/', views.indeferir_solicitacaoentrada),
    path('cancelar_solicitacaoentrada/<int:solicitacaoentrada_id>/', views.cancelar_solicitacaoentrada),
    path('solicitacao_entrada/<int:solicitacaoentrada_id>/', views.solicitacao_entrada),
]
