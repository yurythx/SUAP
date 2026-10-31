"""Smoke de rota: evento, projeto final, polo EAD, diário especial, diploma, estágio docente.

Segundo bloco de famílias que o behave nunca cobriu. Vale aqui a mesma disciplina do
``test_20``: o objeto vem de uma fábrica de ``edu/tests/e2e/seed_rotas.py``, ancorada no aluno
do smoke (``seed_rotas.CPF_ALUNO_SMOKE``) e num servidor que só existe para isto — nada é
pendurado em objeto de que ``test_01``→``test_14`` dependam.

O model de cada parâmetro foi lido do ``get_object_or_404`` da própria view, não inferido pelo
nome: ``editar_titulo_pesquisa`` recebe um **Aluno** apesar de morar em ``projeto_final.py``
(``edu/views/projeto_final.py:337``), e ``estagio_docente`` recebe ``EstagioDocente.locals``
(``edu/views/estagio_docente.py:48``).
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# `edu.add_evento` não é concedida por NENHUM grupo de `edu/permissions.yaml` — o papel
# `operador_evento` a recebe direta (`seed.PERMISSOES_DIRETAS`). Ver o relatório.
EVENTOS = (
    '/edu/evento/{evento}/',
    '/edu/adicionar_participante_evento/{evento}/{tipo_participante_evento}/',
    '/edu/importar_participantes_evento/{evento}/{tipo_participante_evento}/',
    '/edu/modelo_certificado_evento/{evento}/{tipo_participante_evento}/',
    '/edu/alterar_vinculo_participante_evento/{participante_evento}/',
    '/edu/editar_participante_evento/{participante_evento}/',
)

# Colação de grau é `edu.view_colacaograu`, que o Administrador Acadêmico concentra — não
# `edu.add_evento`, apesar de as duas morarem em `edu/views/eventos.py`.
COLACAO_GRAU = (
    '/edu/colacao_grau/{colacao_grau}/',
    '/edu/adicionar_alunos_colacao_grau/{colacao_grau}/',
    '/edu/deferir_colacao_grau/{colacao_grau}/',
    '/edu/imprimir_lista_colacao_grau_pdf/{colacao_grau}/',
)

PROJETO_FINAL = (
    '/edu/visualizar_projeto_final/{projeto_final}/',
    '/edu/adicionar_projeto_final/{aluno_smoke}/{projeto_final}/',
    '/edu/ata_projeto_final_pdf/{projeto_final}/',
    '/edu/declaracao_participacao_projeto_final/{projeto_final}/',
    '/edu/declaracao_participacao_projeto_final_pdf/{projeto_final}/{participante_declaracao}/',
    '/edu/lancar_resultado_projeto_final/{projeto_final}/',
    '/edu/upload_documento_projeto_final/{projeto_final}/',
    '/edu/ata_eletronica_projeto_final_pdf/{ata_eletronica}/',
    '/edu/visualizar_ata_eletronica/{ata_eletronica}/',
    '/edu/editar_titulo_pesquisa/{aluno_smoke}/',
)

# `InscricaoAlunoEstrangeiro` tem 24 campos obrigatórios, dois deles arquivo (passaporte e
# declaração de vínculo): as 6 rotas que dependem dela seguem descobertas, não dispensadas.
INTERNACIONALIZACAO = (
    '/edu/pre_matricula_internacional/{pre_matricula_internacional}/',
    '/edu/convocacao_prematricula_internacional/{pre_matricula_internacional}/',
    '/edu/processar_prematricula_internacional/{pre_matricula_internacional}/',
)

DIARIOS_ESPECIAIS = (
    '/edu/diarioespecial/{diario_especial}/',
    '/edu/adicionar_aluno_diario_especial/{diario_especial}/',
    '/edu/adicionar_alunos_diario_especial/{diario_especial}/',
    '/edu/adicionar_encontro_diario_especial/{diario_especial}/',
    '/edu/adicionar_professor_diario_especial/{diario_especial}/',
    '/edu/definir_horario_aula_diario_especial/{diario_especial}/',
    '/edu/definir_local_aula_diario_especial/{diario_especial}/',
    '/edu/atualizar_encontro_diario_especial/{encontro}/',
    '/edu/frequencia_diarioespecial/{encontro}/',
)

# `meu_polo` fica de fora: resolve o polo pelo vínculo de quem está logado, e amarrar um
# servidor da cadeia a um polo mudaria o menu dele.
POLOS = (
    '/edu/polo/{polo}/',
    '/edu/adicionar_coordenador_polo/{polo}/',
    '/edu/adicionar_coordenador_polo/{polo}/{coordenador_polo}/',
    '/edu/adicionar_tutor_polo/{polo}/',
    '/edu/adicionar_tutor_polo/{polo}/{tutor_polo}/',
    '/edu/definir_horario_polo/{polo}/',
    '/edu/definir_horario_coordenador_polo/{coordenador_polo}/',
    '/edu/definir_horario_tutor_polo/{tutor_polo}/',
)

# As rotas de status/XML de assinatura ficam de fora: `AssinaturaDigital` exige `Papel`, hmac
# e chave pública de certificado real, e `AssinaturaEletronica` exige o PDF assinado.
DIPLOMAS = (
    '/edu/registroemissaodiploma/{registro_emissao_diploma}/',
    '/edu/cancelar_registroemissaodiploma/{registro_emissao_diploma}/',
    '/edu/consultar_status_assinaturas/{registro_emissao_diploma}/',
    '/edu/emitir_segunda_via_diploma/{registro_emissao_diploma}/',
    '/edu/informar_dados_publicao_dou/{registro_emissao_diploma}/',
)

ESTAGIO_DOCENTE = (
    '/edu/estagio_docente/{estagio_docente}/',
    '/edu/cadastrar_estagio_docente_concomitante/{estagio_docente}/',
    '/edu/encerrar_estagio_docente/{estagio_docente}/',
    '/edu/encerrar_estagio_docente_nao_concluido/{estagio_docente}/',
    '/edu/mudanca_escola_estagio_docente/{estagio_docente}/',
)

# `@group_required('Professor')`: o professor da cadeia (100007) não está em grupo nenhum,
# então quem abre é o servidor que o seed cria já no grupo (`seed.SERVIDORES_ROTAS`).
ESTAGIO_DOCENTE_PROFESSOR = (
    '/edu/cadastrar_visita_estagio_docente/{estagio_docente}/',
    '/edu/cadastrar_visita_estagio_docente/{estagio_docente}/{visita_estagio_docente}/',
    '/edu/enviar_avaliacao_estagio_docente/{estagio_docente}/',
)

# `@group_required('Aluno')`, e o estágio é do aluno do smoke.
ESTAGIO_DOCENTE_ALUNO = ('/edu/enviar_portfolio_estagio_docente/{estagio_docente}/',)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('operador_evento', EVENTOS, id='eventos'),
        pytest.param('admin_academico', COLACAO_GRAU, id='colacao_grau'),
        pytest.param('admin_academico', PROJETO_FINAL, id='projeto_final'),
        pytest.param('secretario', INTERNACIONALIZACAO, id='internacionalizacao'),
        pytest.param('admin_academico', DIARIOS_ESPECIAIS, id='diarios_especiais'),
        pytest.param('admin_academico', POLOS, id='polos'),
        pytest.param('admin_academico', DIPLOMAS, id='diplomas'),
        pytest.param('admin_academico', ESTAGIO_DOCENTE, id='estagio_docente'),
        pytest.param('professor_grupo', ESTAGIO_DOCENTE_PROFESSOR, id='estagio_docente-professor'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)


def test_portfolio_do_estagio_docente_abre(abrir_rotas, alvos):
    abrir_rotas(alvos['matricula_aluno_smoke'], ESTAGIO_DOCENTE_ALUNO, senha='123')
