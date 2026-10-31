"""Quadro "Aguardando agendamento de reposição de atividade" da página inicial do professor (#17795).

A contagem do quadro deixou o escopo ``AbonoFaltas.locals`` (custava 17% do banco em produção) e conta
direto sobre ``AbonoFaltas.objects``. A equivalência vem do filtro de ``aguardando_reposicao_atividade``
com ``user``: o aluno do abono tem de estar matriculado no diário da reposição, que é do professor, e
portanto já está no ``locals`` dele. O grafo é montado por ``bulk_create`` (sem os ``save`` com efeitos
colaterais de ``AbonoFaltas`` e ``MatriculaDiario``).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.test import RequestFactory

from djtools.middleware import threadlocals

from edu.admin.procedimentos import AbonoFaltasAdmin
from edu.models import (
    AbonoFaltas,
    ConfiguracaoAvaliacao,
    Diario,
    ItemConfiguracaoAvaliacao,
    MatriculaDiario,
    MotivoAusenciaEscolar,
    SolicitacaoReposicaoAtividade,
)
from edu.tests.factories import AlunoFactory, MatriculaPeriodoFactory
from edu.tests.views.test_declaracao_docencia import montar_cenario
from edu.views.layout import pendencias_requerimento

pytestmark = pytest.mark.django_db

SUBTITULO = 'Aguardando agendamento de reposição de atividade'


def _item(diario: Diario) -> ItemConfiguracaoAvaliacao:
    configuracao = ConfiguracaoAvaliacao.objects.bulk_create([ConfiguracaoAvaliacao(diario=diario, etapa=1)])[0]
    return ItemConfiguracaoAvaliacao.objects.bulk_create([ItemConfiguracaoAvaliacao(configuracao_avaliacao=configuracao, sigla='A1')])[0]


def _abono(
    motivo: MotivoAusenciaEscolar,
    reposicoes: list[ItemConfiguracaoAvaliacao],
    matriculado_em: list[Diario],
    deferida: bool | None = None,
    data_reposicao: datetime.date | None = None,
) -> AbonoFaltas:
    """Abono deferido de um aluno novo, matriculado em ``matriculado_em``, com uma reposição por item."""
    matricula_periodo = MatriculaPeriodoFactory(aluno=AlunoFactory())
    MatriculaDiario.objects.bulk_create([MatriculaDiario(matricula_periodo=matricula_periodo, diario=d) for d in matriculado_em])
    hoje = datetime.date.today()
    abono = AbonoFaltas.objects.bulk_create(
        [AbonoFaltas(aluno=matricula_periodo.aluno, data_inicio=hoje, data_fim=hoje, motivo_ausencia_escolar=motivo, deferido=True)]
    )[0]
    SolicitacaoReposicaoAtividade.objects.bulk_create(
        [
            SolicitacaoReposicaoAtividade(abono_faltas=abono, item_configuracao_avaliacao=item, deferida=deferida, data_reposicao=data_reposicao)
            for item in reposicoes
        ]
    )
    return abono


@pytest.fixture
def cenario(sync_permissions) -> SimpleNamespace:
    """Professor com dois diários (``d1``, ``d2``) e abonos em cada situação do quadro."""
    meu = montar_cenario(n_diarios=2, n_aulas=0, n_extras=0)
    outro = montar_cenario(n_diarios=1, n_aulas=0, n_extras=0)
    d1, d2 = meu.diarios
    d_outro = outro.diarios[0]
    item1, item2, item_outro = _item(d1), _item(d2), _item(d_outro)
    user = meu.servidor.get_user()
    user.groups.add(Group.objects.get(name='Professor'))
    # O escopo ``locals`` lê o usuário do threadlocal, como numa requisição (o ``conftest.py`` raiz o limpa).
    threadlocals.context.user = user
    motivo = MotivoAusenciaEscolar.objects.create(descricao='Atestado médico', ativo=True)
    abonos = SimpleNamespace(
        # Reposições pendentes nos dois diários: o abono conta uma vez só.
        nos_dois_diarios=_abono(motivo, [item1, item2], [d1, d2]),
        reposicao_deferida=_abono(motivo, [item2], [d2], deferida=True),
        outro_professor=_abono(motivo, [item_outro], [d_outro]),
        # Removido do d1 (``MatriculaDiario`` apagada) e ainda no d2: está no ``locals`` do professor,
        # mas a reposição do d1 ficou órfã.
        removido_do_diario=_abono(motivo, [item1], [d2]),
        # Removido do único diário do professor: fora do ``locals``; sem o filtro da matrícula, a contagem
        # sobre ``objects`` o incluiria.
        removido_de_todos=_abono(motivo, [item1], []),
        ja_agendada=_abono(motivo, [item1], [d1], deferida=True, data_reposicao=datetime.date.today()),
        indeferida=_abono(motivo, [item1], [d1], deferida=False),
    )
    return SimpleNamespace(user=user, abonos=abonos, esperados={abonos.nos_dois_diarios.pk, abonos.reposicao_deferida.pk})


def _contagem_do_quadro(user) -> int | None:
    request = RequestFactory().get('/')
    request.user = user
    # Receptor do sinal da página inicial (``djtools.layout.atribuidos_a_mim``), que engole exceções.
    cartoes = pendencias_requerimento(sender=None, request=request)
    return next((c['qtd'] for c in cartoes if c['subtitulo'] == SUBTITULO), None)


def test_quadro_conta_so_reposicoes_pendentes_de_alunos_nos_diarios_do_professor(cenario: SimpleNamespace) -> None:
    sem_locals = AbonoFaltas.locals.aguardando_reposicao_atividade(queryset=AbonoFaltas.objects.all(), user=cenario.user)
    com_locals = AbonoFaltas.locals.aguardando_reposicao_atividade(user=cenario.user)

    assert set(sem_locals.values_list('pk', flat=True)) == cenario.esperados
    assert set(com_locals.values_list('pk', flat=True)) == cenario.esperados
    assert _contagem_do_quadro(cenario.user) == len(cenario.esperados)


def test_aba_do_admin_concorda_com_o_quadro(cenario: SimpleNamespace) -> None:
    request = RequestFactory().get('/')
    request.user = cenario.user
    aba = AbonoFaltasAdmin(AbonoFaltas, None).tab_aguardando_reposicao_minha_atividade(request, AbonoFaltas.locals.all())

    assert set(aba.values_list('pk', flat=True)) == cenario.esperados
