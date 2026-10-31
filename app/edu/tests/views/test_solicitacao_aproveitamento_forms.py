"""Validação de duplicidade nos formulários de solicitação de aproveitamento de estudo."""

from __future__ import annotations

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from comum.tests.factories import AnoFactory
from edu.forms.procedimentos import (
    SolicitacaoAproveitamentoEstudoExternoFom,
    SolicitacaoAproveitamentoEstudoInternoFom,
)
from edu.models import (
    Aluno,
    ComponenteCurricular,
    Diario,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    SolicitacaoAproveitamentoEstudoExterno,
    SolicitacaoAproveitamentoEstudoInterno,
)
from edu.tests.factories import (
    AlunoFactory,
    ComponenteCurricularFactory,
    DiarioFactory,
    MatriculaDiarioFactory,
    MatriculaPeriodoFactory,
    MatrizFactory,
    RequerimentoAproveitamentoEstudoFactory,
    SolicitacaoAproveitamentoEstudoExternoFactory,
    SolicitacaoAproveitamentoEstudoInternoFactory,
)

pytestmark = pytest.mark.django_db

MENSAGEM_DUPLICIDADE = 'Já existe uma solicitação de aproveitamento para a disciplina informada.'
PDF_BYTES = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF'


def _pdf(nome: str = 'ementa.pdf') -> SimpleUploadedFile:
    return SimpleUploadedFile(nome, PDF_BYTES, content_type='application/pdf')


def _criar_diario_aprovado_para_cpf(aluno: Aluno) -> Diario:
    ano = AnoFactory(ano=datetime.date.today().year)
    outro_vinculo = AlunoFactory(pessoa_fisica=aluno.pessoa_fisica)
    mp_anterior = MatriculaPeriodoFactory(aluno=outro_vinculo, ano_letivo=ano)
    diario = DiarioFactory(turma__ano_letivo=ano, ano_letivo=ano)
    MatriculaDiarioFactory(matricula_periodo=mp_anterior, diario=diario)
    return diario


def _submeter_form_interno(
    requerimento: RequerimentoAproveitamentoEstudo,
    componente_curricular: ComponenteCurricular,
    diario: Diario,
    instance: SolicitacaoAproveitamentoEstudoInterno | None = None,
) -> SolicitacaoAproveitamentoEstudoInternoFom:
    return SolicitacaoAproveitamentoEstudoInternoFom(
        data={
            'componente_curricular': componente_curricular.pk,
            'diario_1': diario.pk,
        },
        files={
            'ementa': _pdf('ementa.pdf'),
            'ementa_1': _pdf('ementa_1.pdf'),
        },
        requerimento=requerimento,
        instance=instance,
    )


def _submeter_form_externo(
    requerimento: RequerimentoAproveitamentoEstudo,
    componente_curricular: ComponenteCurricular,
    instance: SolicitacaoAproveitamentoEstudoExterno | None = None,
) -> SolicitacaoAproveitamentoEstudoExternoFom:
    ano = AnoFactory(ano=datetime.date.today().year)
    return SolicitacaoAproveitamentoEstudoExternoFom(
        data={
            'componente_curricular': componente_curricular.pk,
            'ano_letivo_1': ano.pk,
            'periodo_letivo_1': 1,
            'nome_1': 'Disciplina Cursada na Origem',
            'nota_1': 85,
            'frequencia_1': 90,
        },
        files={
            'ementa': _pdf('ementa.pdf'),
            'ementa_1': _pdf('ementa_1.pdf'),
        },
        requerimento=requerimento,
        instance=instance,
    )


class TestSolicitacaoAproveitamentoEstudoInternoFom:
    def test_permite_adicionar_disciplina_quando_outro_aluno_tem_solicitacao_pendente(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)
        outro_aluno = AlunoFactory(matriz=matriz)

        req_outro = RequerimentoAproveitamentoEstudoFactory(aluno=outro_aluno, interno=True, situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
        SolicitacaoAproveitamentoEstudoInternoFactory(requerimento=req_outro, componente_curricular=cc, parecer=None)

        req_aluno = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=True, situacao=None)
        diario = _criar_diario_aprovado_para_cpf(aluno)

        form = _submeter_form_interno(req_aluno, cc, diario)

        assert form.is_valid(), form.errors

    @pytest.mark.parametrize('situacao_req', [None, Requerimento.SITUACAO_EM_ANDAMENTO])
    def test_bloqueia_quando_proprio_aluno_ja_possui_solicitacao_pendente(self, situacao_req: str | None) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)
        diario = _criar_diario_aprovado_para_cpf(aluno)

        req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=True, situacao=situacao_req)
        SolicitacaoAproveitamentoEstudoInternoFactory(requerimento=req, componente_curricular=cc, diario_1=diario, parecer=None)

        form = _submeter_form_interno(req, cc, diario)

        assert not form.is_valid()
        assert MENSAGEM_DUPLICIDADE in form.non_field_errors()

    def test_permite_quando_solicitacao_anterior_do_aluno_esta_em_requerimento_arquivado(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)
        diario = _criar_diario_aprovado_para_cpf(aluno)

        req_arquivado = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=True, situacao=Requerimento.SITUACAO_ARQUIVADO)
        SolicitacaoAproveitamentoEstudoInternoFactory(requerimento=req_arquivado, componente_curricular=cc, diario_1=diario, parecer=None)

        novo_req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=True, situacao=None)
        form = _submeter_form_interno(novo_req, cc, diario)

        assert form.is_valid(), form.errors

    def test_permite_edicao_da_propria_solicitacao(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)
        diario = _criar_diario_aprovado_para_cpf(aluno)

        req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=True, situacao=None)
        solicitacao = SolicitacaoAproveitamentoEstudoInternoFactory(
            requerimento=req,
            componente_curricular=cc,
            diario_1=diario,
            parecer=None,
        )

        form = _submeter_form_interno(req, cc, diario, instance=solicitacao)

        assert form.is_valid(), form.errors


class TestSolicitacaoAproveitamentoEstudoExternoFom:
    def test_permite_adicionar_disciplina_quando_outro_aluno_tem_solicitacao_pendente(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)
        outro_aluno = AlunoFactory(matriz=matriz)

        req_outro = RequerimentoAproveitamentoEstudoFactory(aluno=outro_aluno, interno=False, situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
        SolicitacaoAproveitamentoEstudoExternoFactory(requerimento=req_outro, componente_curricular=cc, parecer=None)

        req_aluno = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=False, situacao=None)
        form = _submeter_form_externo(req_aluno, cc)

        assert form.is_valid(), form.errors

    @pytest.mark.parametrize('situacao_req', [None, Requerimento.SITUACAO_EM_ANDAMENTO])
    def test_bloqueia_quando_proprio_aluno_ja_possui_solicitacao_externa_pendente(self, situacao_req: str | None) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)

        req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=False, situacao=situacao_req)
        SolicitacaoAproveitamentoEstudoExternoFactory(requerimento=req, componente_curricular=cc, parecer=None)

        form = _submeter_form_externo(req, cc)

        assert not form.is_valid()
        assert MENSAGEM_DUPLICIDADE in form.non_field_errors()

    def test_permite_quando_solicitacao_anterior_do_aluno_esta_em_requerimento_arquivado(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)

        req_arquivado = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=False, situacao=Requerimento.SITUACAO_ARQUIVADO)
        SolicitacaoAproveitamentoEstudoExternoFactory(requerimento=req_arquivado, componente_curricular=cc, parecer=None)

        novo_req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=False, situacao=None)
        form = _submeter_form_externo(novo_req, cc)

        assert form.is_valid(), form.errors

    def test_permite_edicao_da_propria_solicitacao(self) -> None:
        matriz = MatrizFactory()
        cc = ComponenteCurricularFactory(matriz=matriz)
        aluno = AlunoFactory(matriz=matriz)

        req = RequerimentoAproveitamentoEstudoFactory(aluno=aluno, interno=False, situacao=None)
        solicitacao = SolicitacaoAproveitamentoEstudoExternoFactory(
            requerimento=req,
            componente_curricular=cc,
            parecer=None,
        )

        form = _submeter_form_externo(req, cc, instance=solicitacao)

        assert form.is_valid(), form.errors
