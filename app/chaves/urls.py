from django.urls import path

from chaves import views

urlpatterns = [
    path('get_tabela_chaves/', views.get_tabela_chaves),
    path('get_tabela_permissoes/', views.get_tabela_permissoes),
    path('movimentacao_chave/', views.movimentacao_chave),
    path('gerenciamento_pessoas/', views.gerenciamento_pessoas),
    path('chaves_pessoa/<int:vinculo_id>/', views.chaves_pessoa),
    path('adicionar_chave/<int:vinculo_id>/', views.adicionar_chave),
    path('copiar_usuarios/', views.copiar_usuarios),
    path('copiar_usuarios_chave/<int:chave_origem_id>/<int:chave_destino_id>/', views.copiar_usuarios_chave),
    path('associar_setor_a_chave/', views.associar_setor_a_chave),
    path('chaves_emprestadas/', views.chaves_emprestadas),
]
