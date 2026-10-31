"""Smoke de rota: plano de oferta, atos de curso, auditoria e procedimentos do aluno.

Terceiro bloco de famílias. As quatro rotas de ``log_*`` são de graça e valem a nota: elas
recebem o pk do **objeto referenciado**, não de um ``Log`` (``edu/views/auditoria.py:98,107,164,172``
apenas filtram por ele), então nunca dão 404 e não precisavam de fábrica nenhuma — bastava
ler a view em vez de inferir pelo nome do parâmetro.

Os objetos de ``procedimentos`` são todos do aluno do smoke: medida disciplinar e premiação
aparecem no prontuário, que ``test_08_aluno`` inspeciona no aluno da cadeia.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AUDITORIA = (
    '/edu/log/{log}/',
    '/edu/log_diario/{diario}/',
    '/edu/log_diario_especial/{diario_especial}/',
    '/edu/log_pasta_documental/{aluno}/',
    '/edu/log_situacao_enade/{registro_convocacao_enade}/',
)

# `PrevisaoQuantidadeAlunos` não entra: `edu/models/plano_oferta.py:312` faz
# `super(*args, **kwargs).save(...)` e estoura em qualquer create com kwargs. As rotas
# `editar_quantidade_alunos` e `editar_taxa_evasao` seguem descobertas — é bug, não falta
# de dado. Ver o relatório.
PLANO_OFERTA = (
    '/edu/cenariooferta/{cenario_oferta}/',
    '/edu/adicionar_simulacao_afastamento/{cenario_oferta}/',
    '/edu/adicionar_simulacao_afastamento/{cenario_oferta}/{simulacao_afastamento}/',
    '/edu/adicionar_simulacao_contratacao/{cenario_oferta}/',
    '/edu/adicionar_simulacao_contratacao/{cenario_oferta}/{simulacao_contratacao}/',
    '/edu/simular_carga_horaria_professor/{cenario_oferta}/{um}/',
)

CURSOS = (
    '/edu/atoregulatoriocurso/{ato_regulatorio_curso}/',
    '/edu/atoregulatoriocurso/{ato_regulatorio_curso}/editar/',
    '/edu/cursocampus/{curso_campus}/adicionar_atoregulatorio/{ato_regulatorio_curso}/',
    '/edu/tramitacaoprocessoemec/{tramitacao_processo_emec}/editar/',
    '/edu/configuracaocertificacaoparcial/{configuracao_certificacao_parcial}/editar/',
    '/edu/configuracaocertificacaoparcial/{configuracao_certificacao_parcial}/vincular_modulo/',
    '/edu/configuracaocertificacaoparcial/{configuracao_certificacao_parcial}/vincular_componentecurricular/',
)

PROCEDIMENTOS = (
    '/edu/adicionar_medida_disciplinar/{aluno_smoke}/{medida_disciplinar}/',
    '/edu/adicionar_premiacao/{aluno_smoke}/{premiacao}/',
    '/edu/requerimento/{requerimento}/',
    '/edu/indeferir_requerimento/{requerimento}/',
    '/edu/requerimento_aproveitamento_estudo/{requerimento_aproveitamento_estudo}/',
    '/edu/adicionar_solicitacao_aproveitamento_disciplina/{requerimento_aproveitamento_estudo}/',
    '/edu/lancar_credito_especial/{aluno_smoke}/{credito_especial}/',
    '/edu/visualizar_aproveitamento/{aluno_smoke}/{aproveitamento_estudo}/',
    '/edu/visualizar_certificacao/{aluno_smoke}/{certificacao_conhecimento}/',
    '/edu/visualizar_equivalencia/{aluno_smoke}/{aproveitamento_componente}/',
    # `solicitar_reposicao_atividade` e `avaliar_solicitacao_reposicao_atividade` ficaram de
    # fora: a primeira exige que o logado SEJA o aluno do abono, a segunda devolve 500 sem o
    # avaliador vinculado. Descobertas, não dispensadas.
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', AUDITORIA, id='auditoria'),
        pytest.param('admin_academico', PLANO_OFERTA, id='plano_oferta'),
        pytest.param('admin_academico', CURSOS, id='cursos'),
        pytest.param('admin_academico', PROCEDIMENTOS, id='procedimentos'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)
