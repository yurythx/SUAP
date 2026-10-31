"""Smoke de rota das famílias do edu que o behave nunca cobriu.

Minicurso, NAPNE, ENEM, censo, auditoria, material de aula, atividade complementar, pasta de
créditos especiais: telas que existem em ``edu/urls.py`` e cujo objeto nenhum passo da cadeia
01→14 cria. Quem os cria é ``edu/tests/e2e/seed_rotas.py``, uma fábrica por família, e é da
existência daquelas linhas que estas rotas dependem — sem elas a rota só pode dar 404, e 404
não distingue "tela quebrada" de "não havia o que abrir".

Mesma forma dos ``test_15``→``test_19``: um teste por grupo, rota como literal com marcador,
papel derivado do decorador da view cruzado com ``edu/permissions.yaml``.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ATIVIDADES_COMPLEMENTARES_ADMIN_ACADEMICO = (
    '/edu/adicionar_item_configuracao_ce/{configuracao_creditos_especiais}/',
    '/edu/adicionar_item_configuracao_ce/{configuracao_creditos_especiais}/{item_configuracao_creditos_especiais}/',
    '/edu/atividadeaprofundamento/{atividade_aprofundamento}/',
    '/edu/atividadeaprofundamento_delete/{atividade_aprofundamento}/',
    '/edu/atividadecomplementar/{atividade_complementar}/',
    '/edu/atividadecomplementar_delete/{atividade_complementar}/',
    '/edu/atividadecurricularextensaoextra/editar/{atividade_curricular_extensao_extra}/',
    '/edu/atividadepraticaprofissional/{atividade_pratica_profissional}/concluir/',
    '/edu/atividadepraticaprofissional/{atividade_pratica_profissional}/editar/',
    '/edu/atividadepraticaprofissional/{atividade_pratica_profissional}/lancar_nota/',
    '/edu/solicitar_atividade_complementar/{aluno}/',
)
AUDITORIA_ADMIN_ACADEMICO = (
    '/edu/auditoria_ensino/{auditoria_ensino}/',
    '/edu/editar_atendente_auditoria/{auditoria_ensino}/',
    '/edu/ignorar_registro_auditoria/{registro_auditoria_ensino}/',
    '/edu/informar_fonte_dados_auditoria/{auditoria_ensino}/',
    '/edu/informar_situacao_registro_auditoria/{registro_auditoria_ensino}/',
    '/edu/resolver_auditoria/{auditoria_ensino}/',
)
CENSOS_ADMIN_ACADEMICO = (
    '/edu/abertura_extemporanea/{abertura_extemporanea}/',
    '/edu/adicionar_questaoeducacenso/{questao_educacenso}/',
    '/edu/adicionar_questaoeducacenso/{questao_educacenso}/{questao_educacenso}/',
    '/edu/editar_execucaoplano/{execucao_plano_laboratorio}/',
    '/edu/editar_resposta_questionarioeducacenso/{resposta_educacenso}/',
    '/edu/iniciar_abertura_extemporanea/{abertura_extemporanea}/',
    '/edu/justificativacensup/{justificativa_censup}/',
    '/edu/laboratorio/{laboratorio}/',
    '/edu/registroeducacenso/{registro_educacenso}/',
    '/edu/responder_questaoeducacenso/{questao_educacenso}/',
    '/edu/responder_questionarioeducacenso/{registro_educacenso}/',
    '/edu/responder_questionarioeducacenso_campus/{registro_educacenso}/{sigla_campus}/',
    '/edu/respostajustificativacensup/{resposta_justificativa_censup}/',
    '/edu/solicitar_alteracao_resposta/{resposta_justificativa_censup}/',
)
DIARIOS_ADMIN_ACADEMICO = (
    '/edu/abonofaltas/{abono_faltas}/',
    '/edu/avaliar_abono_faltas/{abono_faltas}/',
    '/edu/diario/{material_diario}/{material_diario}/',
    '/edu/editar_observacaodiario/{observacao_diario}/',
    '/edu/equivalenciacomponente/{equivalencia_componente}/',
    '/edu/equivalenciacomponente/{equivalencia_componente}/adicionar_avaliador/',
    '/edu/registrar_ocorrencia_diario/{ocorrencia_diario}/{ocorrencia_diario}/',
    '/edu/responder_topico_discussao/{topico_discussao}/',
)
DIARIOS_ESPECIAIS_ADMIN_ACADEMICO = ('/edu/configuracaocreditosespeciais/{configuracao_creditos_especiais}/',)
ENEM_ADMIN_ACADEMICO = (
    '/edu/atender_com_ressalva_solicitacao_certificado_enem/{solicitacao_certificado_enem}/',
    '/edu/cancelar_registroemissaocertificadoenem/{registro_emissao_certificado_enem}/',
    '/edu/comprovante_solicitacao_certificado_enem/{codigo_solicitacao_enem}/',
    '/edu/configuracao_certificacao_enem/{configuracao_certificado_enem}/',
    '/edu/editar_dados_pessoais_solicitacao_enem/{codigo_solicitacao_enem}/',
    '/edu/editar_registro_inep/{registro_aluno_inep}/',
    '/edu/escolher_reitor_diretor_geral/{registro_emissao_certificado_enem}/',
    '/edu/gerar_certificado_enem/{codigo_certificado_enem}/',
    '/edu/imprimir_certificado_enem_antes_2014_pdf/{registro_emissao_certificado_enem}/',
    '/edu/imprimir_certificado_enem_pdf/{registro_emissao_certificado_enem}/',
    '/edu/registroemissaocertificadoenem/{registro_emissao_certificado_enem}/',
    '/edu/registroemissaocertificadoenem_pdf/{registro_emissao_certificado_enem}/',
    '/edu/rejeitar_solicitacao_certificado_enem/{solicitacao_certificado_enem}/',
    '/edu/replicar_solicitacao_certificado_enem/{solicitacao_certificado_enem}/',
    '/edu/solicitacao_certificado_enem/{solicitacao_certificado_enem}/',
)
MINI_CURSOS_ADMIN_ACADEMICO = (
    '/edu/adicionar_participante_turma_minicurso/{turma_minicurso}/',
    '/edu/clonar_minicurso/{minicurso}/',
    '/edu/criar_turma_minicurso/{minicurso}/',
    '/edu/editar_monitor_minicurso/{turma_minicurso}/',
    '/edu/editar_monitor_minicurso/{turma_minicurso}/{monitor_minicurso}/',
    '/edu/editar_participante_turma_minicurso/{participante_turma_minicurso}/',
    '/edu/editar_professor_minicurso/{turma_minicurso}/',
    '/edu/editar_professor_minicurso/{turma_minicurso}/{professor_minicurso}/',
    '/edu/importar_participantes_turma_minicurso/{turma_minicurso}/',
    '/edu/turma_minicurso/{turma_minicurso}/',
    '/edu/vincular_participantes_sem_turma_minicurso/{turma_minicurso}/',
)
NAPNE_ADMIN_ACADEMICO = ('/edu/napne/acolhimento/{acolhimento}/visualizar/',)
PDFS_ADMIN_ACADEMICO = (
    '/edu/comprovante_pedido_matricula/{pedido_matricula}/',
    '/edu/imprimir_pedido_diario_pdf/{configuracao_pedido_matricula}/{configuracao_pedido_matricula}/',
    '/edu/imprimir_pedidos_alunos_pdf/{configuracao_pedido_matricula}/',
    '/edu/imprimir_pedidos_diarios_pdf/{configuracao_pedido_matricula}/',
)
PROCEDIMENTOS_ADMIN_ACADEMICO = (
    '/edu/add_curso_configuracao_pedido_matricula/{configuracao_pedido_matricula}/',
    '/edu/configuracao_pedido_matricula/{configuracao_pedido_matricula}/',
    '/edu/meu_pedido_matricula/{pedido_matricula}/',
    '/edu/replicar_configuracao_pedido_matricula/{configuracao_pedido_matricula}/',
    '/edu/visualizar_alunos_configuracao_pedido_matricula/{configuracao_pedido_matricula}/{curso_campus}/',
    '/edu/visualizar_alunos_pedido_diario/{configuracao_pedido_matricula}/{diario}/',
)
NAPNE_COORDENADOR_NAPNE = (
    '/edu/napne/acolhimento/{acolhimento}/anexo/adicionar/',
    '/edu/napne/acolhimento/{acolhimento}/anexo/remover/{acolhimento_anexo}/',
    '/edu/napne/acolhimento/{acolhimento}/apoioespecializado/adicionar/',
    '/edu/napne/acolhimento/{acolhimento}/atualizar_nees/',
    '/edu/napne/acolhimento/{acolhimento}/editar/',
    '/edu/napne/acompanhamento/{acolhimento}/adicionar/',
    '/edu/napne/acompanhamento/{acolhimento}/adicionar/{profissional_apoio_especializado}/',
    '/edu/napne/entrevista/{acolhimento}/adicionar/',
)
AUDITORIA_PROFESSOR = ('/edu/log_acesso_material_aula/{material_aula}/{material_aula}/',)
MINI_CURSOS_PROFESSOR = ('/edu/ver_alunos_turma_minicurso/{turma_minicurso}/',)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', ATIVIDADES_COMPLEMENTARES_ADMIN_ACADEMICO, id='atividades_complementares-admin_academico'),
        pytest.param('admin_academico', AUDITORIA_ADMIN_ACADEMICO, id='auditoria-admin_academico'),
        pytest.param('admin_academico', CENSOS_ADMIN_ACADEMICO, id='censos-admin_academico'),
        pytest.param('admin_academico', DIARIOS_ADMIN_ACADEMICO, id='diarios-admin_academico'),
        pytest.param('admin_academico', DIARIOS_ESPECIAIS_ADMIN_ACADEMICO, id='diarios_especiais-admin_academico'),
        pytest.param('admin_academico', ENEM_ADMIN_ACADEMICO, id='enem-admin_academico'),
        pytest.param('admin_academico', MINI_CURSOS_ADMIN_ACADEMICO, id='mini_cursos-admin_academico'),
        pytest.param('admin_academico', NAPNE_ADMIN_ACADEMICO, id='napne-admin_academico'),
        pytest.param('admin_academico', PDFS_ADMIN_ACADEMICO, id='pdfs-admin_academico'),
        pytest.param('admin_academico', PROCEDIMENTOS_ADMIN_ACADEMICO, id='procedimentos-admin_academico'),
        pytest.param('coordenador_napne', NAPNE_COORDENADOR_NAPNE, id='napne-coordenador_napne'),
        pytest.param('professor', AUDITORIA_PROFESSOR, id='auditoria-professor'),
        pytest.param('professor', MINI_CURSOS_PROFESSOR, id='mini_cursos-professor'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)
