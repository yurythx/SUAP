from django.urls import path

from gerenciador_projetos import views

urlpatterns = [
    path('projeto/<int:projeto_id>/', views.projeto, name='projeto'),
    path('projeto/<int:projeto_id>/dashboard/', views.dashboard, name='dashboard'),
    path('projeto/<int:projeto_id>/gantt/', views.gantt, name='gantt'),
    path('projeto/<int:projeto_id>/calendario/', views.calendario, name='calendario'),
    path('projeto/<int:projeto_id>/tarefa/adicionar/', views.gerenciar_tarefa, name='adicionar_tarefa'),
    path('projeto/<int:projeto_id>/tarefa/adicionar/api/', views.gerenciar_tarefa_api, name='adicionar_tarefa_api'),
    path('projeto/<int:projeto_id>/tarefa/<int:tarefa_id>/', views.gerenciar_tarefa, name='alterar_tarefa'),
    path('projeto/<int:projeto_id>/clonar/', views.clonar_projeto, name='clonar_projeto'),
    path('projeto/<int:projeto_id>/listaprojeto/', views.adicionar_ou_vincular_lista_projeto, name='adicionar_ou_vincular_lista_projeto'),
    path('adicionar_tag/<int:projeto_id>/', views.adicionar_tag, name='adicionar_tag'),
    path('editar_tag/<int:tag_id>/', views.editar_tag, name='editar_tag'),
    path('listaprojeto/<int:lista_projeto_id>/', views.atualizar_posicao_lista_projeto, name='atualizar_posicao_lista_projeto'),
    path('tarefa/<int:tarefa_id>/', views.tarefa, name='tarefa'),
    path('tarefa/<int:tarefa_id>/excluir/', views.excluir_tarefa, name='excluir_tarefa'),
    path('tarefa/<int:tarefa_id>/checklist/', views.gerenciar_checklist, name='gerenciar_checklist'),
    path('tarefa/<int:tarefa_id>/clonar/', views.clonar_tarefa, name='clonar_tarefa'),
    path('tarefa/<int:tarefa_id>/historicoevolucao/adicionar/', views.gerenciar_historicoevolucao, name='gerenciar_historicoevolucao'),
    path('tarefa/<int:tarefa_id>/comentario/adicionar/', views.adicionar_comentario_rapido_tarefa, name='adicionar_comentario_rapido_tarefa'),
    path('tarefa/<int:tarefa_id>/anexo/adicionar/', views.adicionar_anexo, name='adicionar_anexo'),
    path('tarefa/<int:tarefa_id>/links/adicionar/', views.gerenciar_link_tarefa, name='adicionar_link_tarefa'),
    path('tarefa/<int:tarefa_id>/links/<int:link_id>/', views.gerenciar_link_tarefa, name='editar_link_tarefa'),
    path('links/<int:link_id>/excluir/', views.excluir_link_tarefa, name='excluir_link_tarefa'),
    path('tarefa/<int:tarefa_id>/mudarlista/<int:lista_id>/<int:posicao>/', views.mudarlista, name='mudarlista'),
    path('tarefa/<int:tarefa_id>/recorrencia/', views.recorrencia_tarefa, name='recorrencia_tarefa'),
    path('tarefa/<int:tarefa_id>/reabrir/', views.reabrir_tarefa, name='reabrir_tarefa'),
    path('tarefa/<int:tarefa_id>/vincular_a_campus/', views.atribuir_tarefa_a_campus, name='atribuir_tarefa_a_campus'),
    path('tarefa/<int:tarefa_id>/adicionar_observador/', views.adicionar_observador, name='adicionar_observador'),
    path('tarefa/<int:tarefa_id>/remover_observador/', views.remover_observador, name='remover_observador'),
    path('tarefa/<int:tarefa_id>/atribuicoes/', views.alterar_atribuidos_tarefa, name='alterar_atribuidos_tarefa'),
    path('tarefa/<int:tarefa_id>/alterar_situacao/<int:situacao>/', views.alterar_situacao_tarefa, name='alterar_situacao_tarefa'),
    path('tarefa/<int:tarefa_id>/alterar_progresso/<int:percentual>/', views.alterar_progresso_tarefa, name='alterar_progresso_tarefa'),
    path('atribuir_a_mim/<int:tarefa_id>/', views.atribuir_a_mim, name='atribuir_a_mim'),
    path('recorrenciatarefa/<int:recorrenciatarefa_id>/remover/', views.remover_recorrencia_tarefa, name='remover_recorrencia_tarefa'),
    path('projetos/comparar/', views.comparar_projetos, name='comparar_projetos'),
    path('projetos/comparar/graficos/', views.comparar_projetos_graficos, name='comparar_projetos_graficos'),
    path('projetos/comparar/gantt/', views.comparar_projetos_gantt, name='comparar_projetos_gantt'),
    path('projetos/comparar/calendario/', views.comparar_projetos_calendario, name='comparar_projetos_calendario'),
    path('minhastarefas/', views.minhas_tarefas, name='minhas_tarefas'),
    path('status_projeto/<int:projeto_id>/', views.status_projeto, name='status_projeto'),
    path('evolucao_tarefas_projeto/<int:projeto_id>/', views.evolucao_tarefas_projeto, name='evolucao_tarefas_projeto'),
]


"""
    modelo/add/             # Incluir
    modelo/{{id}}/          # Alterar
    modelo/{{id}}/delete/   # Excluir
    modelo/{{id}}/view/     # Visualizar
"""
