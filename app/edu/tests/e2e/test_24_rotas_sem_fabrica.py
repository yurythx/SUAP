"""Rotas que a reauditoria mostrou não precisarem de fábrica nenhuma.

``editar_quantidade_alunos`` e ``editar_taxa_evasao`` entraram depois de duas correções: o
``super()`` do model e a ``matriz`` que a fábrica passou a informar. A hipótese do
``taxa_evasao`` nulo estava errada — o que faltava era a matriz.

Eu vinha orçando fábrica para rota que só precisava de leitura da view. O padrão que se
repete: a view **não** faz ``get_object_or_404`` no parâmetro — ela filtra por ele
(``Log.objects.filter(ref=pk)``), passa-o adiante para um form (``form(..., laboratorio_id=pk)``)
ou o usa como "existe? senão instancia vazio" (``Model.objects.filter(pk=pki).first() or Model()``).
Nesses três casos qualquer valor abre a tela, e o objeto real nunca foi necessário.

Foi o que manteve as quatro rotas ``log_*`` quatro lotes na lista errada. Esta é a varredura
que eu deveria ter feito antes de escrever a primeira fábrica.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# `DataComemorativa.objects.filter(pk=pki).first() or DataComemorativa()` e o mesmo para
# `SabadoLetivo`: o segundo segmento é "edite este, ou adicione um novo", nunca um 404.
CALENDARIO = (
    '/edu/adicionar_data_comemorativa/{calendario_academico}/{um}/',
    '/edu/adicionar_sabado_letivo/{calendario_academico}/{um}/',
    # `int(pk_coordenador) and CoordenadorModalidade.objects.get(...) or None`: zero é o
    # caminho "adicionar", e é o que o botão da tela da diretoria usa.
    '/edu/adicionar_coordenador_modalidade/{diretoria}/{zero}/',
)

# Views que só repassam o pk a um form ou filtram por ele.
SEM_BUSCA = (
    '/edu/adicionar_execucaoplano/{laboratorio}/',
    '/edu/adicionar_observacao/{aluno}/',
    '/edu/adicionar_observacaodiario/{diario}/',
    '/edu/atividadecurricularextensaoextra/adicionar/{aluno_smoke}/',
    '/edu/cadastrar_matricula_periodo/{aluno}/',
    '/edu/avaliacao_documentos/{diretoria}/',
    '/edu/imprimir_historico/{tipo_historico}/',
    # Quinta rota de log encontrada na reauditoria: `Log.objects.filter(ref=pk)`, sem busca.
    '/edu/log_resposta_educacenso/{resposta_educacenso}/',
    # Últimas três da reauditoria: `Aluno.locals.filter(pk).first()` nas duas primeiras,
    # e `identificar_candidato` sequer toca no banco (o form vem do GET).
    '/edu/atualizar_email_secundario/{aluno}/',
    # `editar_orientacao` ficou de fora: `perms.pode_editar_orientadores_pos` recusa o
    # Administrador Acadêmico (403). Descoberta, não dispensada.
    '/edu/identificar_candidato/{origem_candidato}/',
)

# Objetos que o seed já criava desde o lote 2 — eu é que endereçava com o marcador errado.
# `alunos_sem_turma_curso` é do Coordenador de Curso, como a irmã `alunos_sem_turma`
# (já coberta em `test_17`): sob o Administrador Acadêmico devolve 403.
RELATORIO_COORDENADOR = ('/edu/alunos_sem_turma_curso/{ano}/{periodo}/{curso_campus}/',)

# Destravadas por duas coisas: a correção de `edu/models/plano_oferta.py:312` (`super()` sem
# argumentos) e a `matriz` que a fábrica passou a informar — sem ela os dois forms da tela
# liam `instance.matriz.qtd_periodos_letivos` e davam 500.
PLANO_OFERTA = (
    '/edu/editar_quantidade_alunos/{previsao_quantidade_alunos}/',
    '/edu/editar_taxa_evasao/{previsao_quantidade_alunos}/',
)

ATIVIDADES = (
    '/edu/cadastrar_atividade_aprofundamento/{aluno_smoke}/{atividade_aprofundamento}/',
    '/edu/cadastrar_atividade_complementar/{aluno_smoke}/{atividade_complementar}/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', CALENDARIO, id='calendario'),
        pytest.param('admin_academico', SEM_BUSCA, id='sem-busca'),
        pytest.param('admin_academico', ATIVIDADES, id='atividades'),
        pytest.param('coordenador_curso', RELATORIO_COORDENADOR, id='relatorio-coordenador'),
        pytest.param('admin_academico', PLANO_OFERTA, id='plano_oferta'),
    ],
)
def test_rotas_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)


# `salvar_relatorio` repassa `tipo` ao form e `query_string` só ao `processar` (POST); no GET
# nenhum dos dois toca o banco. `variaveis` indexa `IndicadoresForm.INDICADORES[indicador]`
# direto — chave errada é `KeyError`, não 404, e foi o que derrubou a tentativa do lote 1.
RELATORIOS = (
    '/edu/salvar_relatorio/{um}/{query_relatorio}/',
    '/edu/variaveis/{indicador}/{ano}/{uo_sigla}/{modalidades_ids}/{curso_campus}/',
)


def test_rotas_de_relatorio_abrem(abrir_rotas):
    abrir_rotas('admin_academico', RELATORIOS)
