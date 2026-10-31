from django.urls import path


from . import views
from rh.importacao_siape import views as views_importacao_siape

urlpatterns = [
    path('', views.index),
    path('servidores_sem_setor_suap/', views.servidores_sem_setor_suap),
    path('servidores_sem_cargo/', views.servidores_sem_cargo),
    path('editar_informacoes_digitais_fracas/<int:pessoa_fisica_id>/', views.editar_informacoes_digitais_fracas),
    # exibição de dados dos servidores
    path('servidor/<int:servidor_matricula>/', views.servidor, name='servidor'),
    path('servidor/editar_informacoes_pessoais/', views.editar_informacoes_pessoais_servidor),
    # pessoa jurídica
    path('pessoajuridica/<int:pessoajuridica_id>/', views.pessoajuridica),
    # Importar Pessoa Jurídica.
    path('importar_pj/', views.importar_pj),
    path('unificar_pessoas/', views.unificar_pessoas),
    # exibição dos relatórios
    path('tela_relatorio/', views.tela_relatorio),
    path('tela_recursos_humanos/', views.tela_recursos_humanos),
    path('tela_servidores_com_funcao/', views.tela_servidores_com_funcao),
    path('servidor/buscar/', views.servidor_buscar),
    path('servidores_capacitacao_setor/', views.servidores_para_capacitacao_por_setor),
    # Arquivos PDF
    path('cracha_pessoa/<int:pessoa_id>/', views.cracha_pessoa),
    path('cracha_setor/<int:setor_id>/', views.cracha_setor),
    path('carteira_funcional/', views.carteira_funcional),
    path('carteira_funcional/<int:servidor_id>/', views.carteira_funcional),
    path('carteira_funcional_setor/<int:setor_id>/<str:abrangencia>/', views.carteira_funcional_setor),
    # imprimir carteria funcional
    path('imprimir_carteira_funcional_pdf/', views.imprimir_carteira_funcional_pdf),
    path('aniversariantes/', views.aniversariantes),
    path('enderecos/', views.enderecos),
    path('enderecos_fora_do_estado/', views.enderecos_fora_do_estado),
    # Tela antiga aposentada: redireciona para a importação SIAPE
    path('upload_arquivos_extrator/', views.upload_arquivos_extrator),
    # Importação SIAPE
    path('importacao_siape/', views_importacao_siape.importacao_siape_lista),
    path('importacao_siape/<int:importacao_id>/', views_importacao_siape.importacao_siape_detalhe),
    path('importacao_siape/<int:importacao_id>/interromper/', views_importacao_siape.importacao_siape_interromper),
    path('importacao_siape/<int:importacao_id>/progresso.json', views_importacao_siape.importacao_siape_progresso),
    path(
        'importacao_siape/<int:importacao_id>/arquivo/<int:arquivo_id>/ocorrencias/',
        views_importacao_siape.importacao_siape_ocorrencias,
    ),
    # Relatórios Gestão
    path('quadro_referencia/', views.quadro_referencia),
    path('afastamentos_servidores/', views.afastamentos_servidores),
    path('relatorio_afastamentos_saude/', views.relatorio_afastamentos_saude),
    path('setor_jornada_historico/<int:setor_pk>/', views.setor_jornada_historico),
    path('setor_jornada_historico_remover/<int:jornada_historico_pk>/', views.setor_jornada_historico_remover),
    path('setor_jornada_historico_pendencias/', views.setor_jornada_historico_pendencias),
    # Avaliador
    path('atualizar_dados_avaliador/', views.atualizar_dados_avaliador),
    path('avaliador/<int:avaliador_id>/', views.visualizar_avaliador),
    # SCDP
    path('tela_pcdp/<int:pcdp_pk>/', views.tela_pcdp, name='tela_pcdp'),
    path('viagens_consolidadas/', views.viagens_consolidadas),
    path('viagens_consolidadas_detalhamento/<int:ano>/<int:mes>/<str:siorg>/', views.viagens_consolidadas_detalhamento),
    path('diarias_passagens/importar_do_arquivo/', views.scdp_importar_do_arquivo),
    # Área de Vinculação
    path('definir_areas_vinculacao/', views.definir_areas_vinculacao),
    path('areas_vinculacao_setor/', views.areas_vinculacao_setor),
    # services
    # path('api/emitir_carteira_funcional_digital/<int:matricula>/', services.emitir_carteira_funcional_digital),
    # redução de carga horária
    path('abrir_processo_afastamento_parcial/<int:processo_id>/', views.abrir_processo_afastamento_parcial),
    path('afastamento_pacial_upload/', views.afastamento_pacial_upload, name='afastamento_pacial_upload'),
    path('visualizar_documentacao_pdf/<str:arquivo_id>/', views.visualizar_documentacao_pdf),
    path('excluir_documentacao_pdf/<str:arquivo_id>/', views.excluir_documentacao_pdf),
    path(
        'alterar_situacao_afastamento_parcial_rh/<int:processo_id>/<str:situacao>/',
        views.alterar_situacao_afastamento_parcial_rh,
        name='afastamento_parcial_situacao_alterar_rh',
    ),
    path('excluir_processo_afastamento_parcial/<int:processo_id>/', views.excluir_processo_afastamento_parcial),
    path('adicionar_horario_afastamento_parcial/<int:processo_id>/', views.adicionar_horario_afastamento_parcial),
    path('remover_horario_afastamento/<int:horario_id>/', views.remover_horario_afastamento),
    path('editar_horario_afastamento/<int:horario_id>/', views.editar_horario_afastamento),
    # path('editar_processo/<int:processo_id>/', views.editar_processo),
    # ação de saúde
    path('adicionar_horario/<str:acaosaude_id>/', views.adicionar_horario),
    path('agendar_horario/<str:horario_id>/', views.agendar_horario),
    path('acao_saude/<str:acao_id>/', views.acao_saude),
    path('cancelar_agendamento/<str:horarioagendado_id>/', views.cancelar_agendamento),
    path('remover_horario/<str:horario_id>/', views.remover_horario),
    # webservice siape
    # path('sincronizar_ws_siape/', views.sincronizar_ws_siape),
    # path('test_importador_ws/<str:cpf>/', views.test_importador_ws),
    path('importar_servidor/<str:cpf>/<str:apenas_servidores_em_exercicio>/', views.importar_servidor),
    path('importar_servidor/', views.importar_servidor),
    path('atualizar_meus_dados_servidor/', views.atualizar_meus_dados_servidor),
    # relatorio docentes por disciplina
    path('disciplina_ingresso_docentes/', views.disciplina_ingresso_docentes),
    # Organogramas
    path('organograma/', views.organograma),
    path('organograma/data/', views.organograma_data, name='organograma_data'),
    path('setor_detalhes/<int:setor_pk>/', views.setor_detalhes, name='setor_detalhes'),
    path(
        'editar_servidor_cargo_emprego_area/<int:servidor_pk>/', views.editar_servidor_cargo_emprego_area, name='editar_servidor_cargo_emprego_area'
    ),
    path('servidores_por_area/', views.servidores_por_area, name='servidores_por_area'),
    path('arquivo_unico/<str:hash_sha512_link_id>/', views.arquivo_unico, name='arquivo_unico'),
    path('setor/<int:pk>/', views.setor),
    path('editar_bases_legais_setor/<int:pk>/', views.editar_bases_legais_setor),
    # solicitacao alteracao de foto
    path('validaralteracaofoto/<int:solicitacao_id>/', views.validaralteracaofoto),
    path('rejeitaralteracaofoto/<int:solicitacao_id>/', views.rejeitaralteracaofoto),
    path('detalhe_solicitacao_alteracao_foto/<int:solicitacao_id>/', views.detalhe_solicitacao_alteracao_foto),
    path('indicadores_publicos/', views.indicadores_publicos),
    # Informações Complementares de Pessoa
    path('pessoa_info_complementar/<int:vinculo_id>/', views.pessoa_info_complementar, name='pessoa_info_complementar'),
    path('importar_dados_completares_pessoa/<int:vinculo_id>/', views.importar_dados_completares_pessoa, name='importar_dados_completares_pessoa'),
    # alertas rh
    path('alertagestaopessoa/<int:id>/ver/', views.ver_alerta_rh),
    # Importação de Pessoa Juridica - RFB
    path('importar_pessoajuridica/', views.importar_pessoajuridica_api_rfb, name='importar_pessoajuridica'),
    # equivalência a nível de setores
    path('equivalencia_setor/<int:id>/', views.equivalencia_setor, name='equivalencia_setor'),
]
