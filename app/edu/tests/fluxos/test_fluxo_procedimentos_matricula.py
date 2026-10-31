# ruff: noqa: F403,F405
# pyright: reportAttributeAccessIssue=false
"""Fluxos de alto nível: procedimentos de matrícula — trancamento e transferência.

Reusa a maquinaria da ``EduTestCase`` para matricular um aluno e então exercita os
procedimentos via as views reais (``/edu/realizar_trancamento_matricula/...``,
``/edu/realizar_transferencia_externa/...``), assertando a situação resultante.
DB-backed via ``atores_edu``.
"""

from edu.tests.test_suap_edu_legacy_base import *


class TestFluxoProcedimentosMatricula(EduTestCase):
    CENARIOS = frozenset({'graduacao'})

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        EduTestCase._auto_setup.__wrapped__(self, atores_edu)
        # procedimentos exigem um Processo (form ProcedimentoMatriculaForm.processo)
        self.processo = Processo(
            vinculo_cadastro=self.servidor_b.get_vinculo(),
            assunto='Procedimento acadêmico de teste',
            tipo=1,
            setor_origem=self.servidor_b.setor,
        )
        self.processo.save()

    def _matricular_aluno(self):
        curso = self.retornar(CursoCampus, chaves={'descricao': 'Ciência da educação'})
        self.acessar_como_secretario()
        aluno = self.efetuar_matricula_institucional(curso=curso)
        assert aluno.get_ultima_matricula_periodo().situacao_id == SituacaoMatriculaPeriodo.MATRICULADO
        return aluno

    def test_trancamento_compulsorio_muda_situacao(self):
        aluno = self._matricular_aluno()
        # helper da base: GET form + POST opcoes='2;3;6' + assert aluno.situacao == TRANCADO
        self.procedimento_matricula(SituacaoMatricula.TRANCADO)
        aluno = self.recarregar(aluno)
        assert aluno.situacao_id == SituacaoMatricula.TRANCADO
        # o procedimento de trancamento foi registrado para alguma matrícula-período do aluno
        assert ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=aluno).exists()

    def test_transferencia_externa_muda_situacao(self):
        aluno = self._matricular_aluno()
        matricula_periodo = aluno.get_ultima_matricula_periodo()

        url = f'/edu/realizar_transferencia_externa/{matricula_periodo.pk}/'
        response = self.client.get(url)
        assert response.status_code == 200

        data = {
            'processo': self.retornar(Processo).pk,
            'data': '31/05/2014',
            'opcoes': '11;6;7',  # TRANSFERIDO_EXTERNO / TRANSF_EXTERNA / cancelado
            'motivo': 'Transferência para outra instituição.',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        aluno = self.recarregar(aluno)
        assert aluno.situacao_id == SituacaoMatricula.TRANSFERIDO_EXTERNO
        assert aluno.get_ultima_matricula_periodo().situacao_id == SituacaoMatriculaPeriodo.TRANSF_EXTERNA
