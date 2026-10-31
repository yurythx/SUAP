from django.urls import path

from documento_eletronico.forms import PapelForm

from . import views
from .forms import DocumentoUploadForm

urlpatterns = (
    # Processo
    path('processo/<int:processo_id>/', views.processo, name='processo'),
    path('processo/numero/<str:numero_protocolo>/', views.processo_por_numero, name='processo_por_numero'),
    path('busca_processo/', views.busca_processo, name='busca_processo'),
    path('processo/editar_interessados/<int:processo_id>/', views.processo_editar_interessados, name='processo_editar_interessados'),
    path('processo/registro_acoes_processo/<int:processo_id>/', views.registro_acoes_processo, name='registro_acoes_processo'),
    path('processo/finalizar/<int:processo_id>/', views.processo_finalizar, name='processo_finalizar'),
    path('processo/desfinalizar/<int:processo_id>/', views.processo_desfinalizar, name='processo_desfinalizar'),
    path('processo/acompanhar/<int:processo_id>/', views.processo_acompanhar, name='processo_acompanhar'),
    path('processo/desacompanhar/<int:processo_id>/', views.processo_desacompanhar, name='processo_desacompanhar'),
    path(
        'processo/documento/ver_justificativa_remocao/<int:pk>/',
        views.ver_justificativa_remocao_documento,
        name='ver_justificativa_remocao_documento',
    ),
    path('anexar_processos/<int:processo_anexador_id>/', views.anexar_processos, name='anexar_processos'),
    path('apensar_processos/<int:processo_apensador_id>/', views.apensar_processos, name='apensar_processos'),
    path('processo/visualizar_minuta/<int:minuta_id>/', views.visualizar_minuta, name='visualizar_minuta'),
    path('processo/conteudo_minuta/<int:minuta_id>/', views.conteudo_minuta, name='conteudo_minuta'),
    path('processo/conteudo_minuta/<uuid:minuta_id>/', views.conteudo_minuta, {'acesso_publico': True}, name='conteudo_minuta'),
    path('clonar_minuta_em_documento/<int:minuta_id>/', views.clonar_minuta_em_documento, name='clonar_minuta_em_documento'),
    path('processo/documento_digitalizado_editar/<int:documentoprocesso_id>/', views.editar_informacoes_upload, name='editar_informacoes_upload'),
    path('desapensar_processo/<int:processo_id>/', views.desapensar_processo, name='desapensar_processo'),
    path('desapensar_todos_processos/<int:apensamento_id>/', views.desapensar_todos_processos, name='desapensar_todos_processos'),
    path('imprimir_processo/<int:processo_id>/', views.visualizar_processo, name='imprimir_processo'),
    path('baixar_processo_zip/<int:processo_id>/', views.fazer_download_zip_processo, name='baixar_processo_zip'),
    path('imprimir_processo_celery/<uuid:processo_uuid>/', views.imprimir_processo_celery, name='imprimir_processo_celery'),
    path('baixar_processo_zip_celery/<uuid:processo_uuid>/', views.fazer_download_zip_processo_celery, name='baixar_processo_celery'),
    path(
        'tipo_processo_classificacoes_nivel_acesso_padrao/<int:tipo_processo_id>/',
        views.tipo_processo_classificacoes_nivel_acesso_padrao,
        name='tipo_processo_classificacoes_nivel_acesso_padrao',
    ),
    path('adicionar_comentario/<int:processo_id>/', views.adicionar_comentario, name='adicionar_comentario'),
    path('desconsiderar_comentario/<int:comentario_id>/', views.desconsiderar_comentario, name='desconsiderar_comentario_processo'),
    path('excluir_comentario/<int:comentario_id>/', views.excluir_comentario, name='excluir_comentario_processo'),
    path('listar_processos_relacionado/<int:processo_id>/', views.listar_processos_relacionado, name='listar_processos_relacionado'),
    path(
        'adicionar_processo_relacionado/<int:processo_principal_id>/<int:processo_relacionado_id>/',
        views.adicionar_processo_relacionado,
        name='adicionar_processo_relacionado',
    ),
    path(
        'remover_relacionamento_processos/<int:processo_principal_id>/<int:processo_relacionado_id>/',
        views.remover_relacionamento_processos,
        name='remover_relacionamento_processos',
    ),
    path('alterar_nivel_acesso_processo/<int:processo_id>/', views.alterar_nivel_acesso_processo, name='alterar_nivel_acesso_processo'),
    path(
        'distribuicao_interna_processos_setor/<int:setor_id>/',
        views.distribuicao_interna_processos_setor,
        name='distribuicao_interna_processos_setor',
    ),
    path('dashboard_processos/<int:setor_id>/', views.dashboard_processos_setor, name='dashboard_processos'),
    # ------------------------------------------------------------------------------------------------------------------
    # Tramite
    path('tramite/visualizar/<int:tramite_id>/', views.tramite_visualizar, name='tramite_visualizar'),
    path('tramite/verificar_integridade/<int:tramite_id>/', views.verificar_integridade_tramite, name='verificar_integridade_tramite'),
    path('caixa_processos/', views.caixa_processos, name='caixa_processos'),
    path('selecao_caixa_processos/', views.selecao_caixa_processos, name='selecao_caixa_processos'),
    path('processo/encaminhar_sem_despacho/<int:processo_id>/', views.encaminhar_sem_despacho, name='encaminhar_sem_despacho'),
    path('processo/encaminhar/<int:processo_id>/', views.processo_encaminhar, name='processo_encaminhar'),
    path('processo/encaminhar_lote/<str:ids>/', views.processo_encaminhar_lote, name='processo_encaminhar_lote'),
    path('processo/receber/<int:processo_id>/', views.processo_receber, name='processo_receber'),
    path('processo/receber_lote/<str:ids>/', views.processo_receber_lote, name='processo_receber_lote'),
    path('processo/remover_ultimo_tramite/<int:processo_id>/', views.processo_remover_ultimo_tramite, name='processo_remover_ultimo_tramite'),
    path('adicionar_prioridade/<int:processo_id>/', views.adicionar_prioridade, name='tramite_adicionar_prioridade'),
    path('adicionar_rotulo/<int:tramite_id>/', views.adicionar_rotulo, name='adicionar_rotulo'),
    path('atribuir_processo/<int:tramite_id>/', views.atribuir_processo, name='atribuir_processo'),
    path('atender_processo/<int:tramite_id>/', views.atender_processo, name='atender_processo'),
    path('movimentacao_interna_processo/', views.movimentacao_interna_processo, name='movimentacao_interna_processo'),
    path('tramite/recibo_envio_conectagov/<int:tramite_id>/', views.recibo_envio_conectagov, name='recibo_envio_barramento'),
    path('tramite/recibo_conclusao_conectagov/<int:tramite_id>/', views.recibo_conclusao_conectagov, name='recibo_conclusao_barramento'),
    # Rota morta removida: `envia_processo` não é view — é o helper chamado por
    # `TramiteFormEncaminharViaBarramento.save()` (o fluxo real é `encaminhar_externamente`,
    # acima) e exige `id_repositorio`/`id_estrutura`, que esta URL não passa; qualquer GET
    # caía em `TypeError` (500). O nome `processo_encaminhar_externo` não era usado em template.
    path('processo/encaminhar_externamente/<int:processo_id>/', views.encaminhar_via_barramento, name='encaminhar_externamente'),
    path(
        'processo/reativar_processo_encaminhado_externamente/<int:processo_id>/',
        views.reativar_processo_encaminhado_externamente,
        name='reativar_processo_encaminhado_externamente',
    ),
    # Distribuição de Trâmites
    path('tramitedistribuicao/excluir_tramitedistribuicao/<int:tramite_distribuicao_pk>/', views.remover_distribuicao_tramite),
    # Documento de Texto
    path(
        'documento_texto_processo/verificar_integridade/<int:documentoprocesso_id>/',
        views.verificar_integridade_documento_texto,
        name='verificar_integridade_documento_texto',
    ),
    path(
        'documento_texto_processo/remover_documento/<int:documento_processo_id>/',
        views.remover_documento_texto_processo,
        name='remover_documento_texto_processo',
    ),
    path('adicionar_documento/<int:processo_id>/<int:documento_id>/', views.adicionar_documento_processo, name='adicionar_documento_processo'),
    path('listar_documentos_adicionar/<int:processo_id>/', views.listar_documentos_adicionar, name='listar_documentos_adicionar'),
    # Documento de Digitalizado
    path(
        'documento_digitalizado_processo/verificar_integridade/<int:documentoprocesso_id>/',
        views.verificar_integridade_documento_digitalizado,
        name='verificar_integridade_documento_digitalizado',
    ),
    path(
        'documento_digitalizado_processo/remover_documento/<int:documento_processo_id>/',
        views.remover_documento_digitalizado_processo,
        name='remover_documento_digitalizado_processo',
    ),
    path('documento_upload/<int:processo_id>/', views.DocumentoUploadWizard.as_view([DocumentoUploadForm, PapelForm]), name='documento_upload'),
    # Minuta
    path('adicionar_minuta/<int:documento_id>/processo/<int:processo_id>/', views.adicionar_processo_minuta, name='adicionar_processo_minuta'),
    path('remover_minuta_processo/<int:minuta_processo_id>/', views.remover_minuta_processo, name='remover_minuta_processo'),
    path('imprimir_minuta_pdf/<int:minuta_id>/<str:orientacao>/', views.imprimir_minuta_pdf, name='imprimir_processo_minuta'),
    path('listar_minutas_adicionar/<int:processo_id>/', views.listar_minutas_adicionar, name='listar_minutas_adicionar'),
    path(
        'processo/minuta/ver_justificativa_remocao_minuta/<int:pk>/', views.ver_justificativa_remocao_minuta, name='ver_justificativa_remocao_minuta'
    ),
    # Ciencia
    path('solicitar_ciencia/<int:processo_id>/', views.solicitar_ciencia, name='solicitar_ciencia'),
    path('dar_ciencia/<int:processo_id>/', views.dar_ciencia, name='dar_ciencia'),
    path('cancelar_solicitacao_ciencia/<int:solicitacao_id>/', views.cancelar_solicitacao_ciencia, name='cancelar_solicitacao_ciencia'),
    # Requerimentos
    path('requerimento_pdf/<int:processo_id>/', views.requirimento_pdf, name='requerimento_pdf'),
    # Solicitações
    path('solicitar_despacho/<int:processo_id>/', views.solicitar_despacho, name='solicitar_despacho'),
    path('solicitar_despacho/visualizar/<int:id>/', views.solicitacao_despacho_visualizar, name='solicitacao_despacho_visualizar'),
    path('solicitar_despacho/editar/<int:id>/', views.solicitacao_despacho_editar, name='solicitacao_despacho_editar'),
    path('solicitar_despacho/deferir/<int:id>/', views.solicitacao_despacho_deferir, name='solicitacao_despacho_deferir'),
    path('solicitar_despacho/indeferir/<int:id>/', views.solicitacao_despacho_indeferir, name='solicitacao_despacho_indeferir'),
    path('solicitar_despacho/cancelar/<int:id>/', views.solicitacao_despacho_cancelar, name='solicitacao_despacho_cancelar'),
    path('solicitar_despacho/conteudo/<int:id>/', views.solicitacao_despacho_conteudo, name='solicitar_despacho_conteudo'),
    path('criar_processo_documento/<int:documento_id>/', views.criar_processo_documento, name='criar_processo_documento'),
    path('incluir_documento_processo/<int:documento_id>/', views.incluir_documento_processo, name='incluir_documento_processo'),
    path('cadastrar_requerimento/', views.cadastrar_requerimento, name='cadastrar_requerimento'),
    path('editar_requerimento/<int:requerimento_id>/', views.editar_requerimento, name='editar_requerimento'),
    path('cancelar_requerimento/<int:requerimento_id>/', views.cancelar_requerimento, name='cancelar_requerimento'),
    path('finalizar_requerimento/<int:requerimento_id>/', views.finalizar_requerimento, name='finalizar_requerimento'),
    path(
        'listar_documentos_adicionar_requerimento/<int:requerimento_id>/',
        views.listar_documentos_adicionar_requerimento,
        name='listar_documentos_adicionar_requerimento',
    ),
    path(
        'adicionar_documento_requerimento/<int:requerimento_id>/<int:documento_id>/',
        views.adicionar_documento_requerimento,
        name='adicionar_documento_requerimento',
    ),
    path(
        'documento_texto_processo_requerimento/verificar_integridade/<int:documento_requerimento_id>/',
        views.verificar_integridade_documento_texto_requerimento,
        name='verificar_integridade_documento_texto_requerimento',
    ),
    path(
        'remover_documento_requerimento/<int:documento_requerimento_id>/', views.remover_documento_requerimento, name='remover_documento_requerimento'
    ),
    path(
        'adicionar_documento_upload_requerimento/<int:requerimento_id>/',
        views.adicionar_documento_upload_requerimento,
        name='adicionar_documento_upload_requerimento',
    ),
    path(
        'editar_documento_upload_requerimento/<int:documento_digitalizado_requerimento_id>/',
        views.editar_documento_upload_requerimento,
        name='editar_documento_upload_requerimento',
    ),
    path(
        'visualizar_documento_requerimento_pdf/<int:requerimento_id>/<int:documento_digitalizado_requerimento_id>/',
        views.visualizar_documento_requerimento_pdf,
        name='visualizar_documento_requerimento_pdf',
    ),
    path(
        'remover_documento_upload_requerimento/<int:documento_digitalizado_requerimento_id>/',
        views.remover_documento_upload_requerimento,
        name='remover_documento_upload_requerimento',
    ),
    path('gerenciar_requerimento/<int:requerimento_id>/', views.gerenciar_requerimento, name='gerenciar_requerimento'),
    path('gerenciar_requerimento/<int:requerimento_id>/modo/<str:modo>/', views.gerenciar_requerimento, name='gerenciar_requerimento'),
    # Solicitação de juntada de documento
    path('enviar_pedido_juntada/<int:processo_id>/', views.enviar_solicitacao_juntada, name='enviar_solicitacao_juntada'),
    path('listar_documentos_juntar/<int:solicitacao_id>/', views.listar_documentos_juntar, name='listar_documentos_juntar'),
    path(
        'solicitar_juntada_documento_interno/<int:solicitacao_id>/<int:documento_id>/',
        views.solicitar_juntada_documento_interno,
        name='solicitar_juntada_documento_interno',
    ),
    path(
        'solicitar_juntada_documento_externo/<int:solicitacao_id>/',
        views.solicitar_juntada_documento_externo,
        name='solicitar_juntada_documento_externo',
    ),
    path('concluir_juntada_documento/<int:solicitacao_id>/', views.concluir_juntada_documento, name='concluir_juntada_documento'),
    path('deferir_solicitacao_juntada/<int:solicitacao_id>/', views.deferir_solicitacao_juntada, name='deferir_solicitacao_juntada'),
    path('indeferir_solicitacao_juntada/<int:solicitacao_id>/', views.indeferir_solicitacao_juntada, name='indeferir_solicitacao_juntada'),
    path(
        'avaliar_solicitacao_juntada_documento/<int:solicitacao_id>/',
        views.avaliar_solicitacao_juntada_documento,
        name='avaliar_solicitacao_juntada_documento',
    ),
    path('cancelar_solicitacao_documento/<int:solicitacao_id>/', views.cancelar_solicitacao_documento, name='cancelar_solicitacao_documento'),
    path('remover_documento_juntada/<int:documentojuntada_id>/', views.remover_documento_juntada, name='remover_documento_juntada'),
    path('processo_eletronico_manutencao/', views.processo_eletronico_manutencao, name='processo_eletronico_manutencao'),
    path(
        'processo_eletronico_manutencao_altera_status/',
        views.processo_eletronico_manutencao_altera_status,
        name='processo_eletronico_manutencao_altera_status',
    ),
    path('processo_eletronico_numeros/', views.processo_eletronico_numeros, name='processo_eletronico_numeros'),
    # Consulta pública de processos
    path('consulta_publica/', views.consulta_publica, name='consulta_publica'),
    path('permissoes/', views.permissoes, name='permissoes'),
    path(
        'gerenciar_compartilhamento_processos_poder_de_chefe/',
        views.gerenciar_compartilhamento_processos_poder_de_chefe,
        name='gerenciar_compartilhamento_processos_poder_de_chefe',
    ),
    path('get_hipoteses_legais_by_processo_nivel_acesso/<int:processo_nivel_acesso_id>/', views.get_hipoteses_legais_by_processo_nivel_acesso),
    path('visualizar_capa_processo/<int:processo_id>/', views.visualizar_capa_processo, name='visualizar_capa_processo'),
    path('visualizar_requerimento_processo/<int:processo_id>/', views.visualizar_requerimento_processo, name='visualizar_requerimento_processo'),
    # path('imprimir_processo_visualizacao_publica/<uuid:processo_uuid>/', views.imprimir_processo_visualizacao_publica, name='imprimir_processo_visualizacao_publica'),
    path('permissoes_processos_documentos/<str:username>/', views.permissoes_processos_documentos, name='permissoes_processos_documentos'),
    path('permissoes_processos_documentos/', views.permissoes_processos_documentos, name='permissoes_processos_documentos'),
    path('remover_permissao_processo_documento/', views.remover_permissao_processo_documento, name='remover_permissao_processo_documento'),
    path('configurar_orientacao_nivel_acesso/', views.configurar_orientacao_nivel_acesso, name='configurar_orientacao_nivel_acesso'),
    path(
        'solicita_alteracao_nivel_acesso/documentodigitalizado/<int:documento_id>/',
        views.solicita_alteracao_nivel_acesso_documento_digitalizado,
        name='solicita_alteracao_nivel_acesso_documento_digitalizado',
    ),
    path(
        'solicita_alteracao_nivel_acesso/documentotexto/<int:documento_id>/',
        views.solicita_alteracao_nivel_acesso_documento_texto,
        name='solicita_alteracao_nivel_acesso_documento_texto',
    ),
    path(
        'solicita_alteracao_nivel_acesso/processo/<int:processo_id>/',
        views.solicita_alteracao_nivel_acesso_processo,
        name='solicita_alteracao_nivel_acesso_processo',
    ),
    path(
        'analisar_solicitacao_alteracao_nivel_acesso/<int:solicitacao_id>/',
        views.analisar_solicitacao_alteracao_nivel_acesso,
        name='analisar_solicitacao_alteracao_nivel_acesso',
    ),
    # path('deferir_solicitacao_alteracao_nivel_acesso/<int:solicitacao_id>/',
    #    views.deferir_solicitacao_alteracao_nivel_acesso, name='deferir_solicitacao_alteracao_nivel_acesso'),
    path(
        'indeferir_solicitacao_alteracao_nivel_acesso/<int:solicitacao_id>/',
        views.indeferir_solicitacao_alteracao_nivel_acesso,
        name='indeferir_solicitacao_alteracao_nivel_acesso',
    ),
    path(
        'solicitacoes_alteracao_nivel_acesso_documento/<int:documento_id>/',
        views.solicitacoes_alteracao_nivel_acesso_documento,
        name='solicitacoes_alteracao_nivel_acesso_documento',
    ),
    path(
        'solicitacoes_alteracao_nivel_acesso_processo/<int:processo_id>/',
        views.solicitacoes_alteracao_nivel_acesso_processo,
        name='solicitacoes_alteracao_nivel_acesso_processo',
    ),
    path('visualizar_processo/<int:processo_id>/', views.visualizar_processo, name='visualizar_processo'),
    path('visualizar_processo/<uuid:processo_id>/', views.visualizar_processo, {'acesso_publico': True}, name='visualizar_processo_publica'),
    path('visualizar_capa_processo/<int:processo_id>/', views.visualizar_capa_processo, name='visualizar_capa_processo'),
    path(
        'visualizar_capa_processo/<uuid:processo_id>/',
        views.visualizar_capa_processo,
        {'acesso_publico': True},
        name='visualizar_capa_processo_publica',
    ),
    path('tramite/conteudo/<int:tramite_id>/', views.tramite_conteudo, name='tramite_conteudo'),
    path('tramite/conteudo/<uuid:tramite_id>/', views.tramite_conteudo, {'acesso_publico': True}, name='tramite_conteudo'),
    path('processo_editar_assunto/<int:processo_id>/', views.processo_editar_assunto, name='processo_editar_assunto'),
    path('linha_tempo/<int:processo_id>/', views.linha_tempo, name='linha_tempo'),
    path('rotulos/<int:setor_id>/', views.visualizar_rotulos, name='visualizar_rotulos'),
    path('imprimir_etiqueta/<int:processo_id>/', views.processo_imprimir_etiqueta, name='imprimir_etiqueta'),
)
