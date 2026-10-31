"""Diários com nota pendente após o fechamento do período (``Diario.objects.pendentes()``, #17801).

Caracteriza o resultado do filtro usado no painel da diretoria e na aba "Notas Pendentes" do admin:
um diário é pendente quando o período já fechou e tem matrícula cursando (ou em prova final) com
uma nota exigida pela quantidade de avaliações do componente ainda vazia, ou com prova final pendente.
Cada diário do cenário isola um caso. O grafo é montado por ``bulk_create`` (sem os ``save`` com
efeitos colaterais de ``Diario`` e ``MatriculaDiario``).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

from comum.models import User
from comum.tests.factories import AnoFactory
from djtools.middleware import threadlocals
from rh.tests.factories import ServidorFactory

from edu.models import ComponenteCurricular, CursoCampus, Diario, MatriculaDiario, Turma
from edu.tests.factories import AlunoFactory, MatriculaPeriodoFactory
from edu.tests.views.test_declaracao_docencia import _base, _calendario, _diarios

pytestmark = pytest.mark.django_db

CURSANDO, PROVA_FINAL = MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL
APROVADO, REPROVADO = MatriculaDiario.SITUACAO_APROVADO, MatriculaDiario.SITUACAO_REPROVADO
NOTAS = {'nota_1': 80, 'nota_2': 80, 'nota_3': 80, 'nota_4': 80}

# nome: (pendente?, qtd_avaliacoes, período aberto?, [(situação, notas vazias, prova_final_pendente), ...])
CASOS: dict[str, tuple[bool, int | None, bool, list[tuple[int, tuple[str, ...], bool]]]] = {
    'n1_vazia_1_avaliacao': (True, 1, False, [(CURSANDO, ('nota_1',), False)]),
    'n2_vazia_1_avaliacao': (False, 1, False, [(CURSANDO, ('nota_2', 'nota_3', 'nota_4'), False)]),
    'n1_vazia_0_avaliacoes': (False, 0, False, [(CURSANDO, ('nota_1', 'nota_2', 'nota_3', 'nota_4'), False)]),
    'n2_vazia_2_avaliacoes': (True, 2, False, [(CURSANDO, ('nota_2',), False)]),
    'n3_vazia_2_avaliacoes': (False, 2, False, [(CURSANDO, ('nota_3', 'nota_4'), False)]),
    'n3_vazia_3_avaliacoes': (False, 3, False, [(CURSANDO, ('nota_3',), False)]),
    'n3_vazia_4_avaliacoes': (True, 4, False, [(CURSANDO, ('nota_3',), False)]),
    'n4_vazia_4_avaliacoes': (True, 4, False, [(PROVA_FINAL, ('nota_4',), False)]),
    'prova_final_pendente': (True, 2, False, [(PROVA_FINAL, (), True)]),
    'sem_pendencia': (False, 4, False, [(CURSANDO, (), False), (PROVA_FINAL, (), False)]),
    'situacao_fora_da_lista': (False, 2, False, [(APROVADO, ('nota_1', 'nota_2'), False), (REPROVADO, (), True)]),
    'duas_matriculas_pendentes': (True, 2, False, [(CURSANDO, ('nota_1',), False), (PROVA_FINAL, (), True), (APROVADO, ('nota_1',), False)]),
    # Sem componente (qtd_avaliacoes=None): só a prova final pendente conta.
    'sem_componente_prova_final': (True, None, False, [(PROVA_FINAL, ('nota_1', 'nota_2'), True)]),
    'sem_componente_nota_vazia': (False, None, False, [(CURSANDO, ('nota_1', 'nota_2'), False)]),
    'periodo_aberto': (False, 2, True, [(CURSANDO, ('nota_1', 'nota_2'), False), (PROVA_FINAL, (), True)]),
}


@pytest.fixture
def cenario() -> SimpleNamespace:
    """Um diário por caso de ``CASOS``; o do período aberto fecha em 2099."""
    # Semente própria: não colide com os códigos/siglas de ``montar_cenario`` (``_seq`` começa em 0).
    b = _base(17801)
    diarios = dict(zip(CASOS, _diarios(b, 17801, len(CASOS)), strict=True))
    cal_aberto = _calendario(b, AnoFactory(ano=2099), anual=False)
    alunos = [MatriculaPeriodoFactory(aluno=AlunoFactory()) for _ in range(3)]
    matriculas = []
    for nome, (_, qtd_avaliacoes, aberto, linhas) in CASOS.items():
        diario = diarios[nome]
        if qtd_avaliacoes is None:
            Diario.objects.filter(pk=diario.pk).update(componente_curricular=None)
        else:
            ComponenteCurricular.objects.filter(pk=diario.componente_curricular_id).update(qtd_avaliacoes=qtd_avaliacoes)
        if aberto:
            Diario.objects.filter(pk=diario.pk).update(calendario_academico=cal_aberto)
        for aluno, (situacao, vazias, prova_final_pendente) in zip(alunos, linhas, strict=False):
            notas = {campo: None if campo in vazias else valor for campo, valor in NOTAS.items()}
            matriculas.append(
                MatriculaDiario(matricula_periodo=aluno, diario=diario, situacao=situacao, prova_final_pendente=prova_final_pendente, **notas)
            )
    MatriculaDiario.objects.bulk_create(matriculas)
    pendentes = {diarios[nome].pk for nome, (pendente, *_) in CASOS.items() if pendente}
    return SimpleNamespace(diarios=diarios, pendentes=pendentes)


def test_pendentes_traz_cada_diario_com_nota_pendente_uma_vez(cenario: SimpleNamespace) -> None:
    qs = Diario.objects.pendentes()

    assert set(qs.values_list('pk', flat=True)) == cenario.pendentes
    assert qs.count() == len(cenario.pendentes)


def test_pendentes_respeita_o_filtro_de_quem_chama(cenario: SimpleNamespace) -> None:
    """Formas do painel da diretoria (filtro depois) e da aba do admin (filtro antes)."""
    alguns = {cenario.diarios[nome].pk for nome in ('n1_vazia_1_avaliacao', 'prova_final_pendente', 'sem_pendencia', 'periodo_aberto')}
    esperado = alguns & cenario.pendentes

    assert Diario.objects.pendentes().filter(id__in=alguns).count() == len(esperado)
    assert set(Diario.objects.filter(pk__in=alguns).pendentes().values_list('pk', flat=True)) == esperado


def test_turmas_pendentes_sao_as_dos_diarios_pendentes(cenario: SimpleNamespace, sync_permissions) -> None:
    """``Turma.objects.pendentes()`` passa por ``Diario.locals``: superusuário vê todas as diretorias."""
    user = ServidorFactory().get_user()
    User.objects.filter(pk=user.pk).update(is_superuser=True)
    user.is_superuser = True
    threadlocals.context.user = user
    turmas = {d.turma_id for d in cenario.diarios.values() if d.pk in cenario.pendentes}

    assert set(Turma.objects.pendentes().values_list('pk', flat=True)) == turmas


def test_pendentes_usa_a_data_de_fechamento_do_periodo(cenario: SimpleNamespace) -> None:
    Diario.objects.filter(pk=cenario.diarios['periodo_aberto'].pk).update(
        calendario_academico=cenario.diarios['n1_vazia_1_avaliacao'].calendario_academico
    )
    hoje = datetime.date.today()
    assert cenario.diarios['n1_vazia_1_avaliacao'].calendario_academico.data_fechamento_periodo < hoje

    assert set(Diario.objects.pendentes().values_list('pk', flat=True)) == cenario.pendentes | {cenario.diarios['periodo_aberto'].pk}


@pytest.fixture
def outra_diretoria(cenario: SimpleNamespace) -> SimpleNamespace:
    """Diretoria B (#17815): a turma ``t0`` tem dois diários pendentes e um sem pendência; ``t3`` só um sem pendência."""
    b = _base(17815)
    d0, d1, d2, d3 = _diarios(b, 17815, 4)
    Diario.objects.filter(pk__in=[d1.pk, d2.pk]).update(turma=d0.turma_id)
    aluno = MatriculaPeriodoFactory(aluno=AlunoFactory())
    MatriculaDiario.objects.bulk_create(
        MatriculaDiario(matricula_periodo=aluno, diario=d, situacao=CURSANDO, **{**NOTAS, 'nota_1': None if pendente else 80})
        for d, pendente in ((d0, True), (d1, True), (d2, False), (d3, False))
    )
    turmas_a = {d.turma_id for d in cenario.diarios.values() if d.pk in cenario.pendentes}
    return SimpleNamespace(base=b, t0=d0.turma_id, turmas_a=turmas_a, base_a=Diario.objects.get(pk=cenario.diarios['n1_vazia_1_avaliacao'].pk))


def test_turmas_pendentes_respeitam_a_diretoria_do_usuario(outra_diretoria: SimpleNamespace, sync_permissions) -> None:
    """Usuário lotado na diretoria A não vê a turma pendente da B, nem pelo manager local da aba do admin."""
    setor_a = outra_diretoria.base_a.turma.curso_campus.diretoria.setor
    threadlocals.context.user = ServidorFactory(setor=setor_a).get_user()

    assert set(Turma.objects.pendentes().values_list('pk', flat=True)) == outra_diretoria.turmas_a
    assert set(Turma.locals.pendentes().values_list('pk', flat=True)) == outra_diretoria.turmas_a


def test_painel_do_coordenador_conta_so_turmas_dos_diarios_visiveis(outra_diretoria: SimpleNamespace, sync_permissions) -> None:
    """Forma do painel (``Turma.objects.filter(curso_campus_id=...).pendentes().count()``): turma com dois diários pendentes conta uma vez."""
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Curso'))
    curso_b = outra_diretoria.base.curso_anual
    CursoCampus.objects.filter(pk=curso_b.pk).update(coordenador=user.get_vinculo())
    threadlocals.context.user = user

    assert list(Turma.objects.filter(curso_campus_id=curso_b.pk).pendentes().values_list('pk', flat=True)) == [outra_diretoria.t0]
    assert Turma.objects.filter(curso_campus_id=curso_b.pk).pendentes().count() == 1
    # O curso da diretoria A tem turmas pendentes, mas o coordenador de B não vê os diários delas.
    assert Turma.objects.filter(curso_campus_id=outra_diretoria.base_a.turma.curso_campus_id).pendentes().count() == 0
