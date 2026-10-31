from django.urls import path

from remanejamento import views

urlpatterns = [
    path('edital/<int:edital_id>/gerenciar/', views.gerenciar_edital, name='gerenciar_edital'),
    path('edital/<int:edital_id>/processar/', views.processar_resultado, name='processar_resultado'),
    path('edital/<int:edital_id>/publicar_resultado_parcial/', views.publicar_resultado_parcial, name='publicar_resultado_parcial'),
    path('edital/<int:edital_id>/publicar_resultado_final/', views.publicar_resultado_final, name='publicar_resultado_final'),
    path(
        'edital/<int:edital_id>/publicar_homologacao_resultado_final/',
        views.publicar_homologacao_resultado_final,
        name='publicar_homologacao_resultado_final',
    ),
    path('edital/<int:edital_id>/vagaedital_id/<int:vagaedital_id>/cadastrar_vagas/', views.cadastrar_vagas_edital, name='cadastrar_vagas_edital'),
    path('edital/<int:edital_id>/vagaedital_id/<int:vagaedital_id>/excluir_vagas/', views.excluir_vagas_edital, name='excluir_vagas_edital'),
    path(
        'edital/vagaedital_id/<int:vagaedital_id>/cadastrar_areas_correlatas/',
        views.cadastrar_areas_correlatas_edital,
        name='cadastrar_areas_correlatas_edital',
    ),
    path(
        'edital/vagaedital_id/<int:vagaedital_id>/cadastrar_cargos_correlatos/',
        views.cadastrar_cargos_correlatos_edital,
        name='cadastrar_cargos_correlatos_edital',
    ),
    path(
        'edital/vagaedital_id/<int:vagaedital_id>/cadastrar_disciplinas_correlatas_edital/',
        views.cadastrar_disciplinas_correlatas_edital,
        name='cadastrar_disciplinas_correlatas_edital',
    ),
    path(
        'edital/<int:edital_id>/atualizar_afastamentos/',
        views.atualizar_afastamentos,
        name='atualizar_afastamentos',
    ),
    path('edital/<int:edital_id>/configurar_cargos/', views.configurar_cargos_vagas_edital, name='configurar_cargos_edital'),
    path('edital/<int:edital_id>/configurar_disciplinas/', views.configurar_disciplinas_edital, name='configurar_disciplinas_edital'),
    path(
        'edital/<int:edital_id>/<str:tipo_doc>vincular_documento_resultado/', views.vincular_documento_resultado, name='vincular_documento_resultado'
    ),
    path('visualizar_recurso_edital/<int:recurso_pk>/', views.visualizar_recurso_edital),
    path('recurso_edital/<int:edital_pk>/', views.recurso_edital),
    path('inscrever/<int:edital_pk>/', views.inscrever),
    path('inscricao/<int:inscricao_pk>/', views.inscricao),
    path('inscricao/<int:inscricao_pk>/editar/', views.editar_inscricao_coordenador),
    path('inscricao/<int:inscricao_pk>/desistir/', views.inscricao_desistir),
    path('inscricao/<int:inscricao_pk>/inabilitar/', views.inabililitar_inscricao),
    path('inscricao/<int:inscricao_pk>/reabilitar/', views.reabilitar_inscricao),
    path('inscricao/<int:inscricao_pk>/imprimir/', views.inscricao_imprimir),
    path('inscricao/<int:inscricao_pk>/excluir_recurso/', views.inscricao_excluir_recurso),
    path('inscricao/<int:inscricao_pk>/validar_afastamentos/', views.validar_afastamentos, name='validar_afastamentos'),
    path('inscricao/<int:inscricao_pk>/avaliar_anexo_inscricao/', views.avaliar_anexo_inscricao, name='avaliar_anexo_inscricao'),
    path('inscricoes_csv/<int:edital_pk>/', views.inscricoes_csv),
    path('adicionar_disciplinas/<int:edital_pk>/', views.adicionar_disciplinas),
    path('adicionar_disciplina_itens/<int:edital_pk>/', views.adicionar_disciplina_itens),
    path(
        'adicionar_inscricao_contemplada_extraordinaria/<int:edital_pk>/',
        views.adicionar_inscricao_contemplada_extraordinaria,
        name='adicionar_inscricao_contemplada_extraordinaria',
    ),
]
