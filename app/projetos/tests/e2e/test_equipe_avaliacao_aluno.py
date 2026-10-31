"""Fluxo: a avaliação do aluno da equipe — o coordenador avalia, o aluno registra as considerações.

Com o edital exigindo avaliações dos alunos, a aba "Equipe" oferece "Avaliações do aluno": o
coordenador (ou o orientador) cadastra uma avaliação parcial ou final, com um conceito por
critério ativo e as considerações dele; o aluno abre a própria avaliação e registra as
considerações dele, o que a valida (e a fecha para nova edição). A regressão que se pega é o
item por critério não persistir, ou a validação ficar aberta depois de feita.

As sondas: só o coordenador avalia, só o próprio aluno registra considerações — e as duas telas
de LEITURA, que só abrem para quem acompanha o aluno (``Participacao.pode_ver_avaliacoes``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, membro

if TYPE_CHECKING:
    from projetos.models import AvaliacaoAluno, CriterioAvaliacaoAluno, Participacao


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
AVALIACOES = '/projetos/avaliacoes_aluno/{}/'
ADICIONAR_AVALIACAO = '/projetos/adicionar_avaliacao_aluno/{}/'
VER_AVALIACAO = '/projetos/ver_avaliacao_aluno/{}/'
CONSIDERACOES = '/projetos/registrar_consideracoes_aluno/{}/'


@pytest.fixture
def criterio_de_avaliacao_do_aluno(projetos_seed) -> CriterioAvaliacaoAluno:
    """Critério ativo do formulário de avaliação do aluno (catálogo do gerente, vale para todo edital)."""
    from projetos.tests.factories import CriterioAvaliacaoAlunoFactory

    return CriterioAvaliacaoAlunoFactory(nome='Assiduidade E2E', ativo=True)


@pytest.fixture
def aluno_avaliavel(projeto_em_execucao, criterio_de_avaliacao_do_aluno) -> Participacao:
    """Participação do ``aluno`` num projeto em execução de edital que exige a avaliação dos alunos."""
    from projetos.models import Edital

    projeto = projeto_em_execucao().projeto
    Edital.objects.filter(pk=projeto.edital_id).update(exige_avaliacao_aluno=True)
    return membro(projeto, 'aluno')


def test_coordenador_avalia_e_o_aluno_registra_consideracoes(logado_projetos, aluno_avaliavel, criterio_de_avaliacao_do_aluno):
    """A cadeia: "Avaliações do aluno" → "Adicionar Avaliação" → "Ver Avaliação" (coordenador) → "Registrar Considerações" (aluno)."""
    from projetos.models import AvaliacaoAluno, ItemAvaliacaoAluno

    participacao = aluno_avaliavel
    consideracoes = f'Participou de todas as oficinas {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    clicar_em(tela, AVALIACOES.format(participacao.pk))
    tela.ver_titulo('Avaliações do Aluno - Aluno Extensão E2E').ver_texto('Nenhuma avaliação para este aluno.')
    clicar_em(tela, ADICIONAR_AVALIACAO.format(participacao.pk))
    tela.ver_titulo('Avaliar Aluno Extensão E2E').preencher_formulario(
        [
            ('Tipo de Avaliação', 'lista', 'Parcial'),
            (criterio_de_avaliacao_do_aluno.nome, 'lista', 'Bom'),
            ('Considerações do Avaliador', 'textarea', consideracoes),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Avaliação cadastrada com sucesso.')

    avaliacao = AvaliacaoAluno.objects.filter(participacao=participacao, consideracoes_coordenador=consideracoes).first()
    assert avaliacao is not None, 'a UI disse que cadastrou, mas a avaliação não persistiu'
    assert avaliacao.vinculo_avaliado_por == participacao.projeto.vinculo_coordenador
    assert ItemAvaliacaoAluno.objects.filter(avaliacao=avaliacao, criterio=criterio_de_avaliacao_do_aluno, pontuacao='Bom').exists(), (
        'o conceito do critério não foi gravado'
    )
    tela.ver_titulo('Avaliações do Aluno - Aluno Extensão E2E').linha('Parcial')
    clicar_em(tela, VER_AVALIACAO.format(avaliacao.pk))
    tela.popup().ver_texto(criterio_de_avaliacao_do_aluno.nome).ver_texto(consideracoes)

    aluno = Tela(logado_projetos('aluno')).ir(AVALIACOES.format(participacao.pk))
    clicar_em(aluno, CONSIDERACOES.format(avaliacao.pk))
    aluno.preencher('Considerações do Aluno', 'textarea', 'Concordo com a avaliação.').clicar_botao('Salvar')
    aluno.esperar().sucesso('Avaliação validada com sucesso.')
    avaliacao.refresh_from_db()
    assert (avaliacao.consideracoes_aluno, avaliacao.data_validacao is not None) == ('Concordo com a avaliação.', True), (
        'a UI disse que validou, mas as considerações do aluno não persistiram'
    )
    assert aluno.buscar(CONSIDERACOES.format(avaliacao.pk)).status == 403, 'a avaliação validada continua aberta a novas considerações'


@pytest.fixture
def avaliacao_do_aluno(aluno_avaliavel, criterio_de_avaliacao_do_aluno) -> AvaliacaoAluno:
    from projetos.tests.factories import AvaliacaoAlunoFactory, ItemAvaliacaoAlunoFactory

    avaliacao = AvaliacaoAlunoFactory(participacao=aluno_avaliavel, consideracoes_coordenador='Precisa melhorar a pontualidade.')
    ItemAvaliacaoAlunoFactory(avaliacao=avaliacao, criterio=criterio_de_avaliacao_do_aluno)
    return avaliacao


@pytest.mark.parametrize(
    ('papel', 'rota', 'status'),
    [
        # Só o coordenador (ou o orientador) avalia: `Participacao.pode_fazer_avaliacoes`.
        ('outro_coordenador', ADICIONAR_AVALIACAO, 403),
        ('aluno', ADICIONAR_AVALIACAO, 403),
        # Considerações: `pode_registrar_consideracao_aluno` é do grupo Aluno, e só o avaliado.
        ('coordenador_projeto', CONSIDERACOES, 403),
    ],
)
def test_quem_avalia_e_quem_valida(logado_projetos, avaliacao_do_aluno, papel, rota, status):
    from projetos.models import AvaliacaoAluno

    alvo = avaliacao_do_aluno.participacao_id if rota == ADICIONAR_AVALIACAO else avaliacao_do_aluno.pk
    assert Tela(logado_projetos(papel)).buscar(rota.format(alvo)).status == status
    assert AvaliacaoAluno.objects.filter(participacao=avaliacao_do_aluno.participacao_id).count() == 1


def test_estranho_nao_ve_a_avaliacao_do_aluno(logado_projetos, avaliacao_do_aluno):
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {
        rota: (resposta.status, 'Precisa melhorar a pontualidade.' in resposta.text())
        for rota, resposta in (
            (AVALIACOES, tela.buscar(AVALIACOES.format(avaliacao_do_aluno.participacao_id))),
            (VER_AVALIACAO, tela.buscar(VER_AVALIACAO.format(avaliacao_do_aluno.pk))),
        )
    }
    assert all(status in (302, 403) for status, _ in respostas.values()), f'estranho abriu as avaliações do aluno: {respostas}'
    assert not any(vazou for _, vazou in respostas.values()), f'as considerações do coordenador vazaram: {respostas}'
