from django.urls import path

from documento_eletronico import views

from .views import (
    conteudo_documento,
    verificar_integridade,
    visualizar_documento,
    visualizar_documento_digitalizado,
)

urlpatterns = [
    path('dashboard/', views.dashboard),
    path('assinar_documento/<int:documento_id>/', views.AssinarDocumentoSenhaWizard.as_view(), name='assinar_documento_com_senha'),
    path('assinar_documento_lote/', views.AssinarDocumentoLoteFormView.as_view(), name='assinar_documento_lote'),
    path('autenticar_documento/', views.autenticar_documento, name='autenticar_documento'),
    path('verificar_documento_externo/', views.verificar_documento_externo, name='verificar_documento_externo'),
    path('clonar_documento/<int:documento_id>/', views.clonar_documento),
    path(
        'criar_documento_relacionado/<int:documento_id>/',
        views.criar_documento_relacionado,
        name='criar_documento_relacionado',
    ),
    path('clonar_modelo_documento/<int:modelo_documento_id>/', views.clonar_modelo_documento),
    path('clonar_tipo_documento/<int:tipo_documento_id>/', views.clonar_tipo_documento),
    #
    path('concluir_documento/<int:documento_id>/', views.concluir_documento, name='concluir_documento'),
    path('cancelar_documento/<int:documento_id>/', views.cancelar_documento, name='cancelar_documento'),
    path('editar_documento/<int:documento_id>/', views.editar_documento, name='editar_documento'),
    path('editar_documento/<int:documento_id>/<str:remontar_partes_documento>/', views.editar_documento, name='editar_documento'),
    path('conteudo_documento/<int:documento_id>/', conteudo_documento, name='conteudo_documento'),
    path('conteudo_documento/<uuid:documento_id>/', conteudo_documento, name='conteudo_documento'),
    path('editar_modelo_documento/<int:modelo_documento_id>/', views.editar_modelo_documento, name='editar_modelo_documento'),
    path(
        'gerenciar_compartilhamento_documento/<int:documento_id>/',
        views.gerenciar_compartilhamento_documento,
        name='gerenciar_compartilhamento_documento',
    ),
    path('gerenciar_compartilhamento_setor/', views.gerenciar_compartilhamento_setor, name='gerenciar_compartilhamento_setor'),
    path('gerenciar_favoritos/<int:documento_id>/<str:operacao>/', views.gerenciar_favoritos, name='gerenciar_favoritos'),
    path('imprimir_documento_pdf/<int:documento_id>/<str:orientacao>/', views.imprimir_documento_pdf, name='imprimir_previa_pdf'),
    path('exportar_pdfa/<int:documento_id>/<str:orientacao>/', views.exportar_pdfa, name='exportar_pdfa'),
    path('meus_documentos/', views.meus_documentos, name='meus_documentos'),
    path('modelos_tipo_documento/<int:tipo_documento_id>/', views.modelos_tipo_documento),
    path('nivel_acesso_padrao_classificacoes_modelo_documento/<int:modelo_documento_id>/', views.nivel_acesso_padrao_classificacoes_modelo_documento),
    path('get_hipoteses_legais_by_documento_nivel_acesso/<int:documento_nivel_acesso_id>/', views.get_hipoteses_legais_by_documento_nivel_acesso),
    path('excluir_documento_texto/<int:documento_id>/', views.excluir_documento_texto, name='excluir_documento_texto'),
    path(
        'gerar_sugestao_identificador_documento_texto/<int:tipo_documento_id>/<int:setor_dono_id>/',
        views.gerar_sugestao_identificador_documento_texto,
        name='gerar_sugestao_identificador_documento_texto',
    ),
    path('retornar_para_rascunho/<int:documento_id>/', views.retornar_para_rascunho, name='retornar_para_rascunho'),
    path('solicitar_assinatura/<int:documento_id>/', views.solicitar_assinatura, name='solicitar_assinatura'),
    path('solicitar_assinatura_com_anexacao/<int:documento_id>/', views.solicitar_assinatura_com_anexacao, name='solicitar_assinatura_com_anexacao'),
    path('rejeitar_assinatura/<int:documento_id>/', views.rejeitar_assinatura, name='rejeitar_assinatura'),
    path('verificar_integridade/<int:documento_id>/', verificar_integridade, name='verificar_integridade'),
    path('visualizar_documento/<int:documento_id>/', visualizar_documento, name='visualizar_documento'),
    path('visualizar_documento_digitalizado/<int:documento_id>/', visualizar_documento_digitalizado, name='visualizar_documento_digitalizado'),
    path('visualizar_documento_digitalizado/<uuid:documento_id>/', visualizar_documento_digitalizado, name='visualizar_documento_digitalizado'),
    path('visualizar_variaveis/', views.visualizar_variaveis, name='visualizar_variaveis'),
    path('solicitar_revisao/<int:documento_id>/', views.solicitar_revisao, name='solicitar_revisao'),
    path('revisar_documento/<int:documento_id>/', views.revisar_documento, name='revisar_documento'),
    path('cancelar_revisao/<int:documento_id>/', views.cancelar_revisao, name='cancelar_revisao'),
    path('rejeitar_revisao/<int:documento_id>/', views.rejeitar_revisao, name='rejeitar_revisao'),
    path('finalizar_documento/<int:documento_id>/', views.finalizar_documento, name='finalizar_documento'),
    path('vincular_documentos/<int:documento_texto_base_id>/', views.vincular_documentos, name='vincular_documentos'),
    path(
        'remover_vinculo_documento_texto/<int:vinculo_documento_texto_id>/<int:documento_id>/',
        views.remover_vinculo_documento_texto,
        name='remover_vinculo_documento_texto',
    ),
    path(
        'remover_solicitacao_assinatura/<int:solicitacao_assinatura_id>/', views.remover_solicitacao_assinatura, name='remover_solicitacao_assinatura'
    ),
    path(
        'solicitar_compartilhamento_documento_digitalizado/<int:processo_id>/<int:documento_id>/',
        views.solicitar_compartilhamento_documento_digitalizado,
        name='solicitar_compartilhamento_documento_digitalizado',
    ),
    path(
        'avaliar_solicitacao_compartilhamento_documento_digitalizado/<int:processo_id>/<int:solicitacao_id>/',
        views.avaliar_solicitacao_compartilhamento_documento_digitalizado,
        name='avaliar_solicitacao_compartilhamento_documento_digitalizado',
    ),
    path(
        'documento_texto_editar_interessados/<int:documento_id>/',
        views.documento_texto_editar_interessados,
        name='documento_texto_editar_interessados',
    ),
    path(
        'documento_texto_reprocessar_interessados/<int:documento_id>/',
        views.documento_texto_reprocessar_interessados,
        name='documento_texto_reprocessar_interessados',
    ),
    path(
        'assinar_via_senha_documento_pessoal/<int:documento_id>/',
        views.assinar_via_senha_documento_pessoal,
        name='assinar_via_senha_documento_pessoal',
    ),
    path(
        'visualizar_documento_digitalizado_pessoal/<int:documento_id>/',
        views.visualizar_documento_digitalizado_pessoal,
        name='visualizar_documento_digitalizado_pessoal',
    ),
    path('listar_documentos_anexar/<int:documento_id>/', views.listar_documentos_anexar, name='listar_documentos_anexar'),
    path(
        'anexar_documento_a_documentotexto/<int:documentotexto_id>/<int:documento_id>/',
        views.anexar_documento_a_documentotexto,
        name='anexar_documento_a_documentotexto',
    ),
    path('desanexar_documento/<int:documentotexto_id>/<int:documento_id>/', views.desanexar_documento, name='desanexar_documento'),
    path(
        'visualizar_documento_digitalizado_anexo_simples/<int:documento_id>/',
        views.visualizar_documento_digitalizado_anexo_simples,
        name='visualizar_documento_digitalizado_anexo_simples',
    ),
    path(
        'editar_documento_digitalizado_anexo_simples/<int:documento_id>/',
        views.editar_documento_digitalizado_anexo_simples,
        name='editar_documento_digitalizado_anexo_simples',
    ),
    path(
        'alterar_nivel_acesso_documento_digitalizado_anexo_simples/<int:documento_id>/',
        views.alterar_nivel_acesso_documento_digitalizado_anexo_simples,
        name='alterar_nivel_acesso_documento_digitalizado_anexo_simples',
    ),
    path(
        'alterar_nivel_acesso_documento_texto_anexo/<int:documento_id>/',
        views.alterar_nivel_acesso_documento_texto_anexo,
        name='alterar_nivel_acesso_documento_texto_anexo',
    ),
    path(
        'alterar_nivel_acesso_documento_texto/<int:documento_texto_id>/',
        views.alterar_nivel_acesso_documento_texto,
        name='alterar_nivel_acesso_documento_texto',
    ),
    path(
        'alterar_nivel_acesso_documento_digitalizado/<int:documento_digitalizado_id>/',
        views.alterar_nivel_acesso_documento_digitalizado,
        name='alterar_nivel_acesso_documento_digitalizado',
    ),
    path('assinar_documento_com_gov_br/<int:documento_id>/', views.assinar_documento_com_gov_br, name='assinar_documento_com_gov_br'),
    path('enviar_codigo_verificacao_govbr', views.enviar_codigo_verificacao_govbr, name='enviar_codigo_verificacao_govbr'),
    path('enviar_codigo_verificacao_email', views.enviar_codigo_verificacao_email, name='enviar_codigo_verificacao_email'),
    path('consulta_publica/', views.consulta_publica, name='consulta_publica'),
    path('editar_tags_anonimizacao/<int:documento_id>/', views.editar_tags_anonimizacao, name='editar_tags_anonimizacao'),
]
