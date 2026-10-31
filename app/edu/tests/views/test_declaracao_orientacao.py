"""Declarações de orientação do professor (TCC e estágios e afins) em PDF.

Quem emite é quem emite a declaração de vínculo docente (``Professor.pode_emitir_declaracao_docencia``, #17733):
o papel local só alcança o campus do professor. Em teste o ``@documento`` devolve o HTML sem passar pelo
wkhtmltopdf. As orientações são criadas por ``bulk_create`` para pular as notificações do ``save``.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

import pytest

from comum.models import User, Vinculo
from edu.models import Professor, ProjetoFinal
from edu.tests.factories import AlunoFactory, MatriculaPeriodoFactory
from edu.tests.views.test_declaracao_docencia import SECRETARIO, _no_campus_do, _professor, _servidor_com
from estagios.models import AtividadeProfissionalEfetiva


@pytest.fixture
def cliente(db, sync_permissions, suap_client):
    return suap_client


def _orientou_tcc(professor: Professor) -> str:
    ProjetoFinal.objects.bulk_create(
        [ProjetoFinal(matricula_periodo=MatriculaPeriodoFactory(), titulo='TCC', resumo='Resumo', tipo='Monografia', orientador=professor)]
    )
    return f'/edu/emitir_declaracao_de_orientacao_tcc_pdf/{professor.pk}/'


def _orientou_atividade_profissional(professor: Professor) -> str:
    AtividadeProfissionalEfetiva.objects.bulk_create(
        [
            AtividadeProfissionalEfetiva(
                aluno=AlunoFactory(),
                orientador=professor,
                inicio=datetime.date(2025, 3, 1),
                data_prevista_encerramento=datetime.date(2025, 12, 1),
                ch_semanal=20,
                documentacao_comprobatoria='documentacao.pdf',
                plano_atividades='plano.pdf',
            )
        ]
    )
    return f'/edu/emitir_declaracao_de_orientacao_pdf/{professor.pk}/atividadesprofissionaisefetivas/0/'


DECLARACOES = {'TCC': _orientou_tcc, 'estágio': _orientou_atividade_profissional}
ORIENTACOES = {'TCC': 'projetos_finais', 'estágio': 'atividades_profissionais_efetivas'}
USUARIOS: dict[str, Callable[[Professor], User]] = {
    'próprio professor': lambda professor: professor.vinculo.user,
    'secretário acadêmico do campus': lambda professor: _servidor_com(SECRETARIO, setor=_no_campus_do(professor)),
    'secretário acadêmico de outro campus': lambda professor: _servidor_com(SECRETARIO),
}
PODEM = {'próprio professor', 'secretário acadêmico do campus'}


@pytest.mark.parametrize('declaracao', DECLARACOES)
@pytest.mark.parametrize('papel', USUARIOS)
def test_quem_pode_emitir_a_declaracao_de_orientacao(cliente, declaracao: str, papel: str):
    professor = _professor()
    caminho = DECLARACOES[declaracao](professor)
    cliente.force_login(USUARIOS[papel](professor))

    resposta = cliente.get(caminho)

    assert resposta.status_code == (200 if papel in PODEM else 403)
    if papel in PODEM:
        assert resposta.context[ORIENTACOES[declaracao]].exists()


@pytest.mark.parametrize('declaracao', DECLARACOES)
def test_professor_sem_setor_emite_a_declaracao_de_orientacao(cliente, declaracao: str):
    professor = _professor()
    caminho = DECLARACOES[declaracao](professor)
    Vinculo.objects.filter(pk=professor.vinculo.pk).update(setor=None)  # prestador sem setor: o middleware o deixa passar
    usuario = User.objects.get(pk=professor.vinculo.user_id)
    usuario.reset_vinculo()  # User.VINCULOS é cache de classe, ainda com o setor
    cliente.force_login(usuario)

    resposta = cliente.get(caminho)

    assert resposta.status_code == 200
    assert resposta.context['uo'] is None


ABAS = {'TCC': 'projetofinal', 'estágio': 'estagios'}


@pytest.mark.parametrize('declaracao', DECLARACOES)
@pytest.mark.parametrize('papel', ['secretário acadêmico do campus', 'secretário acadêmico de outro campus'])
def test_botao_de_emitir_so_aparece_para_quem_pode(cliente, declaracao: str, papel: str):
    professor = _professor()
    caminho = DECLARACOES[declaracao](professor)
    cliente.force_login(USUARIOS[papel](professor))

    resposta = cliente.get(f'/edu/professor/{professor.pk}/?tab={ABAS[declaracao]}')

    assert resposta.status_code == 200
    ve_botao = caminho in resposta.content.decode()
    assert ve_botao is (papel in PODEM)
