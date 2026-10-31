"""Smoke de rota do edu sob o Administrador Acadêmico — a maior parte da superfície.

O Administrador Acadêmico é o papel de maior alcance do módulo: é o grupo que concentra a
permissão exigida pela maior parte das views de ``edu/views/``, e por isso é sob ele que a
maior fatia da superfície é varrida — 217 rotas, agrupadas pelo módulo de view de origem.
As rotas que exigem OUTRO grupo estão em ``test_17`` (com o papel que a view pede) e as do
discente em ``test_18``; abri-las aqui devolveria 403.

Cada rota é um literal com marcador (``{diario}``), resolvido em ``alvos_rotas.py`` a partir
do que o seed da cadeia 01→14 já criou. Um teste por grupo, e não por rota: o login é real a
cada teste, e a falha lista de uma vez todas as rotas do grupo que não abriram.

O que este arquivo pega e um fluxo profundo não pega é a tela que **deixou de abrir** — 500
por queryset quebrado, 404 por rota renomeada, 403 por permissão movida de grupo.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ALUNOS_ADMIN_ACADEMICO = (
    '/edu/alterar_matriz_aluno/{aluno}/',
    '/edu/alterar_matriz_lote/',
    '/edu/aluno/{matricula}/',
    '/edu/atualizar_dados_pessoais/{aluno}/',
    '/edu/atualizar_dados_responsavel/{aluno}/',
    '/edu/atualizar_foto/{aluno}/',
    '/edu/detalhar_matricula_diario_boletim/{aluno}/{matricula_diario}/',
    '/edu/editar_dados_sistec/{aluno}/',
    '/edu/editar_observacao_integralizacao_ensino_medio/{aluno}/',
    '/edu/editar_situacao_matricula_periodo/{matricula_periodo}/',
    '/edu/exportar_alunos_academico/{matricula}/',
    '/edu/fotografar/',
    '/edu/progresso_ch_por_matriculaperiodo/{aluno}/',
    '/edu/solicitacoes_nada_consta/{aluno}/',
    '/edu/solicitar_quitacao_nada_consta/{aluno}/',
    '/edu/visualizar_requisitos_conclusao/{aluno}/{tipo_requisito}/{tipo_ch}/',
    '/edu/visualizar_requisitos_conclusao/{aluno}/{tipo_requisito}/{tipo_ch}/{tipo_extensao}/',
)
ARQUIVOS_ADMIN_ACADEMICO = ('/edu/upload_arquivo_unico/{aluno}/',)
ATIVIDADES_COMPLEMENTARES_ADMIN_ACADEMICO = (
    '/edu/adicionar_horario_atividade_extra/{aluno}/{ano}/{periodo}/',
    '/edu/adicionar_item_configuracao_aacc/{configuracao_atividade_complementar}/',
    '/edu/adicionar_item_configuracao_atpa/{configuracao_atividade_aprofundamento}/',
    '/edu/atividadepraticaprofissional/cadastrar/{aluno}/{modalidade_pratica}/',
    '/edu/cadastrar_atividade_aprofundamento/{aluno}/',
    '/edu/cadastrar_atividade_complementar/{aluno}/',
    '/edu/configuracaoatividadeaprofundamento/{configuracao_atividade_aprofundamento}/',
    '/edu/configuracaoatividadecomplementar/{configuracao_atividade_complementar}/',
    '/edu/replicar_configuracao_aacc/{configuracao_atividade_complementar}/',
    '/edu/replicar_configuracao_atpa/{configuracao_atividade_aprofundamento}/',
    '/edu/vincular_configuracao_atividade_aprofundamento/{configuracao_atividade_aprofundamento}/',
    '/edu/vincular_configuracao_atividade_complementar/{configuracao_atividade_complementar}/',
    '/edu/visualizar_atividades_aprofundamento_cumpridas/{aluno}/',
    '/edu/visualizar_atividades_complementares_cumpridas/{aluno}/',
    '/edu/visualizar_atividades_complementares_pendentes/{aluno}/',
)
AUDITORIA_ADMIN_ACADEMICO = (
    '/edu/log_aluno/{aluno}/',
    '/edu/realizar_auditoria/',
    '/edu/solicitar_auditoria/',
)
CENSOS_ADMIN_ACADEMICO = (
    '/edu/atualizar_codigo_educacenso/',
    '/edu/atualizar_codigo_sistec/',
    '/edu/auditoria_censos/',
    '/edu/clonar_registroeducacenso/',
    '/edu/importar_educacenso_etapa_2/',
    '/edu/preencher_relatorio_alunos_nao_existentes_sistec/',
    '/edu/preencher_relatorio_censup/',
    '/edu/preencher_relatorio_sistec/',
    '/edu/relatorio_censup/',
    '/edu/relatorio_educacenso/',
    '/edu/relatorio_educacenso_alunos_sem_codigo/',
    '/edu/relatorio_educacenso_etapa_2/',
    '/edu/relatorio_isf/',
    '/edu/relatorio_sttu/',
    '/edu/solicitar_abertura_extemporanea/',
    '/edu/solicitar_abertura_extemporanea_administrador/',
)
COMUNICADOR_RESPONSAVEL_ADMIN_ACADEMICO = ('/edu/enviar_mensagem_responsavel/',)
CURSOS_ADMIN_ACADEMICO = (
    '/edu/adicionar_matriz_curso/{curso_campus}/{matriz_curso}/',
    '/edu/analise_curso/{matriz_curso}/{componente_curricular}/{exibir}/',
    '/edu/matriz/{matriz}/vincular_componente/{componente}/',
    '/edu/relatorio_disciplinas_ead/',
    '/edu/replicar_matriz/{matriz}/',
)
DIARIOS_ADMIN_ACADEMICO = (
    '/edu/abonar_faltas_lote/',
    '/edu/adicionar_alunos_diario/{diario}/',
    '/edu/adicionar_aula_diario/{diario}/{etapa}/',
    '/edu/adicionar_aula_diario/{diario}/{etapa}/{aula}/',
    '/edu/adicionar_professor_diario/{diario}/',
    '/edu/adicionar_professor_diario/{diario}/{professor_diario}/',
    '/edu/agendar_avaliacao/{item_configuracao_avaliacao}/',
    '/edu/alterar_data_vinculo_matricula_aluno/{matricula_diario}/',
    '/edu/alterar_nota_diario/{matricula_diario}/{etapa}/',
    '/edu/cadastrar_frequencia_pratica_profisional/{diario}/',
    '/edu/registrar_chamada/{diario}/',
    '/edu/registrar_chamada/{diario}/{etapa}/',
    '/edu/registrar_chamada/{diario}/{etapa}/{matricula_diario}/',
    '/edu/calendario_avaliacao/',
    '/edu/calendario_avaliacao/{diario}/',
    '/edu/configuracao_avaliacao/{configuracao_avaliacao}/',
    '/edu/configurar_ambiente_virtual_diario/{diario}/',
    '/edu/definir_horario_aula_diario/{diario}/',
    '/edu/definir_local_aula_diario/{diario}/',
    '/edu/dividir_diario_individualizado/{diario}/',
    '/edu/exibir_diarios_fechamento/{matricula_periodo}/',
    '/edu/exibir_diarios_fechamento/{matricula_periodo}/{um}/',
    '/edu/exportar_xml_time_tables/',
    '/edu/grafico_etapa/{diario}/{etapa}/',
    '/edu/grafico_mfd/{diario}/',
    '/edu/importar_xml_time_tables/',
    '/edu/listar_diarios_matricula_aluno/{matricula_periodo}/',
    '/edu/suspender_diario/{diario}/',
)
DIPLOMAS_ADMIN_ACADEMICO = (
    '/edu/diplomas_digitais/',
    '/edu/emitir_certificacao_parcial/',
    '/edu/emitir_diploma/',
    '/edu/emitir_diplomas/',
    '/edu/importar_autenticacao_sistec/',
    '/edu/imprimir_registro_diploma_aluno/',
    '/edu/registroemissaodiploma_public/',
)
DIRETORIAS_ADMIN_ACADEMICO = (
    '/edu/adicionar_coordenador/{diretoria}/{usuario_grupo}/',
    '/edu/adicionar_coordenador_registro_academico/{diretoria}/{usuario_grupo}/',
    '/edu/definir_coordenador_estagio_docente/{curso_campus}/',
    '/edu/imprimir_horarios/',
    '/edu/relatorio_horario/',
    '/edu/relatorio_horario_especial/',
)
ENADE_ADMIN_ACADEMICO = (
    '/edu/adicionar_aluno_avulso_enade/{convocacao_enade}/{curso_campus}/',
    '/edu/atualizar_lista_convocados_enade/{convocacao_enade}/',
    '/edu/convocacao_enade/{convocacao_enade}/',
    '/edu/convocados_enade/{convocacao_enade}/{curso_campus}/',
    '/edu/convocados_enade/{convocacao_enade}/{curso_campus}/{periodo}/',
    '/edu/convocados_enade_irregular/{convocacao_enade}/{diretoria}/{zero}/',
    '/edu/dispensar_nao_convocados/{convocacao_enade}/',
    '/edu/dispensar_participacao_enade/{matricula}/',
    '/edu/editar_datas_inscricao_convocacaoenade/{convocacao_enade}/',
    '/edu/editar_justificativa_dispensa/{curso_campus}/',
    '/edu/editar_modalidadeconvocacaoenade/{modalidade_convocacao_enade}/',
    '/edu/enade/download/estudantes_concluintes_avaliacao_teorica/{convocacao_enade}/{curso_campus}/',
    '/edu/enade/download/estudantes_habilitados_avaliacao_pratica/{convocacao_enade}/{curso_campus}/',
    '/edu/enade/download/estudantes_ingressantes_avaliacao_teorica/{convocacao_enade}/{curso_campus}/',
    '/edu/enade/download/professores_orientadores_avaliacao_pratica/{convocacao_enade}/{curso_campus}/',
    '/edu/enade/download/professores_supervisores_avaliacao_pratica/{convocacao_enade}/{curso_campus}/',
    '/edu/imprimir_lista_convocados_enade_pdf/{convocacao_enade}/',
    '/edu/lancar_situacao_enade/{registro_convocacao_enade}/',
    '/edu/possiveis_concluintes_enade/{convocacao_enade}/{curso_campus}/',
    '/edu/possiveis_integralizados_enade/{convocacao_enade}/{curso_campus}/',
)
ENEM_ADMIN_ACADEMICO = (
    '/edu/consultar_andamento_certificado_enem/',
    '/edu/solicitar_certificado_enem/',
)
ESTAGIO_DOCENTE_ADMIN_ACADEMICO = (
    '/edu/associar_escolas/',
    '/edu/emitir_declaracao_de_orientacao_pdf/{professor}/{tipo_estagio}/{ano}/',
)
HISTORICOS_ADMIN_ACADEMICO = (
    '/edu/adicionar_registro_historico/{aluno}/',
    '/edu/adicionar_registro_historico_mobilidade_academica/{aluno}/',
    '/edu/imprimir_boletim_aluno/',
    '/edu/imprimir_boletins_alunos_em_lote/',
    '/edu/imprimir_historico_em_lote/',
)
MATRICULAS_ADMIN_ACADEMICO = (
    '/edu/efetuar_matricula/',
    '/edu/identificar_candidato/',
)
# Os quatro `redirecionar_*` mandam para a listagem correspondente: o 302 é a tela.
LAYOUT_ADMIN_ACADEMICO = (
    '/edu/redirecionar_aluno/',
    '/edu/redirecionar_calendario/',
    '/edu/redirecionar_diario/',
    '/edu/redirecionar_matriz/',
)
MENSAGENS_ADMIN_ACADEMICO = ('/edu/enviar_mensagem/',)
MINI_CURSOS_ADMIN_ACADEMICO = ('/edu/autenticar_certificado_minicurso/',)
NADA_CONSTA_ADMIN_ACADEMICO = ('/edu/declaracao_nada_consta/{aluno}/',)
NAPNE_ADMIN_ACADEMICO = (
    '/edu/napne/acolhimento/listar/',
    '/edu/napne/visualizardemandas/',
)
PDFS_ADMIN_ACADEMICO = (
    '/edu/comprovante_dados_academicos_pdf/{aluno}/',
    '/edu/comprovante_matricula_pdf/{aluno}/',
    '/edu/declaracao_certificacao_parcial_pdf/{aluno}/{um}/',
    '/edu/declaracao_ch_cumprida_pdf/{aluno}/',
    '/edu/declaracaomatricula_pdf/{aluno}/',
    '/edu/declaracaovinculo_pdf/{aluno}/',
    '/edu/diario_pdf/{diario}/{etapa}/',
    '/edu/emitir_boletins_pdf/{diario}/',
    '/edu/relacao_alunos_pdf/{diario}/',
)
PLANO_ENSINO_ADMIN_ACADEMICO = (
    '/edu/alterar_coordenador_plano_ensino/{plano_ensino}/',
    '/edu/plano_ensino_pdf/{plano_ensino}/',
    '/edu/planoensino_public/',
)
POLOS_ADMIN_ACADEMICO = (
    '/edu/atividades_polo_tutor/',
    '/edu/horario_atendimento_polo/',
    '/edu/relatorio_ead/',
    '/edu/transferir_polo_aluno/',
)
PROCEDIMENTOS_ADMIN_ACADEMICO = (
    '/edu/abrir_periodo_letivo/',
    '/edu/acompanhamento_matricula_turma/',
    '/edu/adicionar_aluno_primeira_oferta/{diario}/',
    '/edu/adicionar_medida_disciplinar/{aluno}/',
    '/edu/adicionar_premiacao/{aluno}/',
    '/edu/alunos_conflitos_horarios/',
    '/edu/aproveitar_componente/{aluno}/{componente_curricular}/',
    '/edu/aproveitar_estudo/{aluno}/{componente_curricular}/',
    '/edu/cadastrar_justificativa_falta/',
    '/edu/cadastrar_procedimento_matricula/{aluno}/',
    '/edu/calcular_ira_parcial/{aluno}/',
    '/edu/certificar_conhecimento/{aluno}/{componente_curricular}/',
    '/edu/desfazer_migracao/{aluno}/',
    '/edu/enviar_fotos_lote/',
    '/edu/evasao_em_lote/',
    '/edu/fechar_periodo_letivo/',
    '/edu/importar_alunos/',
    '/edu/indeferir_em_lote/',
    '/edu/integralizar_alunos/{ano}/',
    '/edu/integralizar_fase_escolar/{matricula_periodo}/',
    '/edu/lancar_credito_especial/{aluno}/',
    '/edu/matricular_aluno_avulso_diario/{diario}/',
    '/edu/matricular_aluno_diario/{matricula_periodo}/{diario}/',
    '/edu/matricular_aluno_turma/{aluno}/',
    '/edu/monitoramento_entrega_diarios/',
    '/edu/monitoramento_fechamento_periodo/',
    '/edu/realizar_cancelamento_matricula/{matricula_periodo}/',
    '/edu/realizar_matricula_vinculo/{matricula_periodo}/',
    '/edu/realizar_trancamento_matricula/{matricula_periodo}/',
    '/edu/realizar_transferencia_curso/{matricula_periodo}/{tipo_transferencia}/',
    '/edu/realizar_transferencia_externa/{matricula_periodo}/',
    '/edu/reintegrar_aluno/{matricula_periodo}/',
    '/edu/relatorio_requerimentos/',
    '/edu/requerer_matricula_com_aumento_ch/{aluno}/{diario}',
    '/edu/requerer_quebra_requisito/{aluno}/{diario}',
)
PROFESSORES_ADMIN_ACADEMICO = (
    '/edu/atualizar_foto_professor/{professor}/',
    '/edu/cadastrar_professor_nao_servidor/',
    '/edu/declaracaodocencia_pdf/{professor}/',
    '/edu/declaracaodocencia_pdf/{professor}/{ano}/',
    '/edu/exportar_dados_pnp/',
    '/edu/professor/{professor}/',
    '/edu/professor/{professor}/editar_dados_portal/',
    '/edu/relatorio_professor/',
)
PROJETO_FINAL_ADMIN_ACADEMICO = (
    '/edu/adicionar_projeto_final/{aluno}/',
    '/edu/emitir_declaracao_de_orientacao_tcc_pdf/{professor}/',
    '/edu/emitir_declaracao_de_orientacao_tcc_pdf/{professor}/{ano}/',
    '/edu/visualizar_agenda_defesas/',
)
RELATORIOS_ADMIN_ACADEMICO = (
    '/edu/alunos_dados_incompletos/',
    '/edu/estatistica/',
    '/edu/exportar_dados_aluno_caracterizacao/',
    '/edu/indicadores/',
    '/edu/relatorio/',
    '/edu/relatorio_dados_responsavel_incompletos/',
    '/edu/relatorio_dependentes/',
    '/edu/relatorio_diario/',
    '/edu/relatorio_disciplinas_aluno/{aluno}/{tipo_disciplinas}/',
    '/edu/relatorio_faltas/',
    '/edu/relatorio_migracao/',
    '/edu/relatorio_migracao/{ano}/{curso_campus}/',
)
TURMAS_ADMIN_ACADEMICO = (
    '/edu/adicionar_aluno_turma/{turma}/{um}/',
    '/edu/efetuar_matricula_turma/{aluno}/',
    '/edu/efetuar_matriculas_turma/{turma}/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', ALUNOS_ADMIN_ACADEMICO, id='alunos-admin_academico'),
        pytest.param('admin_academico', ARQUIVOS_ADMIN_ACADEMICO, id='arquivos-admin_academico'),
        pytest.param('admin_academico', ATIVIDADES_COMPLEMENTARES_ADMIN_ACADEMICO, id='atividades_complementares-admin_academico'),
        pytest.param('admin_academico', AUDITORIA_ADMIN_ACADEMICO, id='auditoria-admin_academico'),
        pytest.param('admin_academico', CENSOS_ADMIN_ACADEMICO, id='censos-admin_academico'),
        pytest.param('admin_academico', COMUNICADOR_RESPONSAVEL_ADMIN_ACADEMICO, id='comunicador_responsavel-admin_academico'),
        pytest.param('admin_academico', CURSOS_ADMIN_ACADEMICO, id='cursos-admin_academico'),
        pytest.param('admin_academico', DIARIOS_ADMIN_ACADEMICO, id='diarios-admin_academico'),
        pytest.param('admin_academico', DIPLOMAS_ADMIN_ACADEMICO, id='diplomas-admin_academico'),
        pytest.param('admin_academico', DIRETORIAS_ADMIN_ACADEMICO, id='diretorias-admin_academico'),
        pytest.param('admin_academico', ENADE_ADMIN_ACADEMICO, id='enade-admin_academico'),
        pytest.param('admin_academico', ENEM_ADMIN_ACADEMICO, id='enem-admin_academico'),
        pytest.param('admin_academico', ESTAGIO_DOCENTE_ADMIN_ACADEMICO, id='estagio_docente-admin_academico'),
        pytest.param('admin_academico', HISTORICOS_ADMIN_ACADEMICO, id='historicos-admin_academico'),
        pytest.param('admin_academico', MATRICULAS_ADMIN_ACADEMICO, id='matriculas-admin_academico'),
        pytest.param('admin_academico', LAYOUT_ADMIN_ACADEMICO, id='layout-admin_academico'),
        pytest.param('admin_academico', MENSAGENS_ADMIN_ACADEMICO, id='mensagens-admin_academico'),
        pytest.param('admin_academico', MINI_CURSOS_ADMIN_ACADEMICO, id='mini_cursos-admin_academico'),
        pytest.param('admin_academico', NADA_CONSTA_ADMIN_ACADEMICO, id='nada_consta-admin_academico'),
        pytest.param('admin_academico', NAPNE_ADMIN_ACADEMICO, id='napne-admin_academico'),
        pytest.param('admin_academico', PDFS_ADMIN_ACADEMICO, id='pdfs-admin_academico'),
        pytest.param('admin_academico', PLANO_ENSINO_ADMIN_ACADEMICO, id='plano_ensino-admin_academico'),
        pytest.param('admin_academico', POLOS_ADMIN_ACADEMICO, id='polos-admin_academico'),
        pytest.param('admin_academico', PROCEDIMENTOS_ADMIN_ACADEMICO, id='procedimentos-admin_academico'),
        pytest.param('admin_academico', PROFESSORES_ADMIN_ACADEMICO, id='professores-admin_academico'),
        pytest.param('admin_academico', PROJETO_FINAL_ADMIN_ACADEMICO, id='projeto_final-admin_academico'),
        pytest.param('admin_academico', RELATORIOS_ADMIN_ACADEMICO, id='relatorios-admin_academico'),
        pytest.param('admin_academico', TURMAS_ADMIN_ACADEMICO, id='turmas-admin_academico'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)
