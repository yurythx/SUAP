from django.urls import path

from . import views

app_name = 'progressao_docente'

urlpatterns = [
    #
    # processo progressão
    path('finalizar/<int:pk>/', views.finalizar_progressao),
    path('ver/<int:pk>/', views.ver_processo, name='ver_processo'),
    path('iniciar_avaliacao/<int:pk>/', views.iniciar_avaliacao),
    path('formulario/<int:pk>/ver/', views.ver_formulario),
    path('criterio/<int:pk>/ver/', views.ver_criterio),
    path('reabrir_edicao/<int:pk>/', views.reabrir_edicao),
    path('enviar_notificacao/<int:pk>/', views.enviar_notificacao),
    #
    # avaliação
    path('avaliacao/<int:pk>/ver/', views.ver_avaliacao),
    path('avaliacao/<int:pk>/preencher/', views.preencher, name='preencher'),
    path('avaliacao/<int:pk>/concluir_preenchimento/', views.concluir_preenchimento),
    path('avaliacao/<int:pk>/assinar_avaliacao/', views.assinar_avaliacao),
    path('avaliacao/<int:pk>/reavaliar/', views.reavaliar),
    path('avaliacao/<int:pk>/revalidar_assinatura/', views.revalidar_assinatura),
    path('avaliacao/<int:pk>/concluir_reavaliacao/', views.finalizar_reavaliacao),
    path('avaliacao/<int:pk>/ciencia_resultado/', views.ciencia_resultado),
    path('avaliacao/<int:pk>/recalcular_pontuacao/', views.recalcular_pontuacao),
    path('avaliacao/<int:pk>/ciencia_resultado/assinar/', views.assinar_ciencia_resultado),
    # ajax
    path('avaliar_processo/<int:pk>/', views.avaliar_processo, name='avaliar_processo'),
    path('avaliar_item_arquivo/<int:pk_avaliacaoitem>/', views.avaliar_item_arquivo),
    path('salvar_avaliar_item_arquivo/<str:acao>/', views.salvar_avaliar_item_arquivo),
    #
    # auxiliares
    path('reavaliar_observacao/<int:id_avaliacao>/', views.reavaliar_observacao),
    path('preparar_edicao_reavaliacao/<int:id_avaliacao>/', views.preparar_edicao_reavaliacao),
    path('adicionar_pontuacao/<int:pk>/<int:pk_criterio>/', views.adicionar_pontuacao),
    #
    # avaliação item
    path('avaliacaoitem/<int:pk>/delete/', views.apagar_avaliacaoitem),
    path('avaliacaoitem/<int:pk>/editar/', views.editar_avaliacaoitem),
    path('avaliacaoitem/<int:pk>/<int:pk_criterio>/ver_criterio/', views.ver_avaliacao_criterio),
    path('avaliacaoitem/<int:pk_item>/<int:pk_avaliacao>/<str:pontuacao>/save/', views.salvar_item_avaliacao),
    #
    # avaliação discente
    path('detalhar_avaliacao_discente/<int:pk_avaliacao>/', views.detalhar_avaliacao_discente),
    path('avaliacao/<int:pk>/finalizar_avaliacao_discente/', views.finalizar_avaliacao_discente),
    path('ver_avaliacoes_discente/', views.ver_avaliacoes_discente),
    path('nao_reconhece_docente/<int:pk>/', views.nao_reconhece_docente, name='nao_reconhece_docente'),
    #
    # relatórios
    path('executar_importacao/', views.executar_importacao),
    path('docenteaprogredir/<int:id>/', views.docenteaprogredir),
    path('inconsistencias_relatorio/', views.inconsistencias_relatorio),
    path('docentes_sem_data_base/', views.docentes_sem_data_base),
    #
    # Configuração
    path('detalhar_configuracao/<int:pk>/', views.detalhar_configuracao, name='detalhar_configuracao'),
    #
    path('editar_data_base_progressao/<str:matricula>/', views.editar_data_base_progressao, name='editar_data_base_progressao'),
    path('criar_progressao/<int:id>/', views.criar_progressao),
    path('recalcular_pontuacao_avaliacao/<int:id_avaliacao>/', views.recalcular_pontuacao_avaliacao),
    path('aceleracao/<str:acao>/', views.aceleracao),
    path('imprimir_processo/<int:id_processo>/', views.imprimir_processo),
    path('gerar_processo_eletronico/<int:id_processo>/', views.gerar_processo_eletronico),
]
