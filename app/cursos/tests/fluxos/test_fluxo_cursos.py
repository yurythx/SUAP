"""Testes de fluxo do módulo de cursos (GECC).

Exercitam as transições de estado do domínio — o ciclo de vida do Curso e o do
Participante — pelos métodos de domínio (curso.iniciar/finalizar,
participante.deferir/indeferir), sem passar por HTTP/templates. São testes de
fluxo de alto nível: descrevem o que o sistema faz, não como.

Estados (ver cursos/enums.py):
  Curso:        NAO_INICIADO -> INICIADO -> AGUARDANDO_CADASTRO_EM_FOLHA -> ...
  Participante: AGUARDANDO_LIBERACAO -> LIBERADO (deferido) / NAO_LIBERADO (indeferido)

Tudo numa única classe para agrupar o fluxo; as fixtures (`conftest.py`) montam
só o que cada teste usa.
"""

import pytest
from django.core.exceptions import ValidationError

from cursos.enums import SituacaoCurso, SituacaoDetalhamentoAtividadeParticipante, SituacaoParticipante


@pytest.mark.django_db(databases='__all__')
class TestFluxoCursos:
    # --- Ciclo de vida do Participante -------------------------------------

    def test_deferir_participacao_libera_o_participante(self, curso, servidor, aprovador, adicionar_participante):
        participante = adicionar_participante(curso, servidor)

        participante.deferir_participacao(aprovador)

        assert participante.situacao == SituacaoParticipante.LIBERADO
        assert participante.responsavel_liberacao == aprovador
        assert participante.data_liberacao is not None

    def test_deferir_recusa_horas_acima_da_cota_anual(self, curso, servidor, aprovador, adicionar_participante):
        # Cota padrão é 120h/ano; 200h previstas estouram o limite.
        participante = adicionar_participante(curso, servidor, horas_prevista=200.0)

        with pytest.raises(ValidationError):
            participante.deferir_participacao(aprovador)

        assert participante.situacao == SituacaoParticipante.AGUARDANDO_LIBERACAO

    def test_indeferir_participacao_registra_motivo(self, curso, servidor, aprovador, adicionar_participante):
        participante = adicionar_participante(curso, servidor)

        participante.indeferir_participacao('Carga horária do evento não comprovada.')

        assert participante.situacao == SituacaoParticipante.NAO_LIBERADO
        assert participante.motivo_nao_liberacao == 'Carga horária do evento não comprovada.'

    # --- Ciclo de vida do Curso --------------------------------------------

    def test_curso_nasce_nao_iniciado(self, curso):
        assert curso.situacao == SituacaoCurso.NAO_INICIADO

    def test_iniciar_curso_com_participante_deferido(self, curso, servidor, aprovador, adicionar_participante):
        participante = adicionar_participante(curso, servidor)
        participante.deferir_participacao(aprovador)

        curso.iniciar()

        assert curso.situacao == SituacaoCurso.INICIADO
        assert curso.data_inicio is not None

    def test_nao_inicia_curso_sem_participantes(self, curso):
        with pytest.raises(ValidationError):
            curso.iniciar()
        assert curso.situacao == SituacaoCurso.NAO_INICIADO

    def test_nao_inicia_curso_com_participante_aguardando_liberacao(self, curso, servidor, aprovador, adicionar_participante):
        adicionar_participante(curso, servidor)  # fica AGUARDANDO_LIBERACAO

        with pytest.raises(ValidationError):
            curso.iniciar()
        assert curso.situacao == SituacaoCurso.NAO_INICIADO

    def test_nao_inicia_curso_com_participante_indeferido(self, curso, servidor, aprovador, adicionar_participante):
        participante = adicionar_participante(curso, servidor)
        participante.indeferir_participacao('Indeferido.')

        with pytest.raises(ValidationError):
            curso.iniciar()
        assert curso.situacao == SituacaoCurso.NAO_INICIADO

    def test_finaliza_curso_com_horas_e_detalhamento_deferido(self, curso_iniciado):
        participante = curso_iniciado.participante
        participante.horas_trabalhada = 10.0
        participante.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
        participante.save()

        curso_iniciado.curso.finalizar()

        assert curso_iniciado.curso.situacao == SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA

    def test_nao_finaliza_curso_sem_horas_trabalhadas(self, curso_iniciado):
        # participante deferido mas sem horas_trabalhada registradas
        with pytest.raises(ValidationError):
            curso_iniciado.curso.finalizar()
        assert curso_iniciado.curso.situacao == SituacaoCurso.INICIADO

    def test_nao_finaliza_curso_nao_iniciado(self, curso):
        with pytest.raises(ValidationError):
            curso.finalizar()
        assert curso.situacao == SituacaoCurso.NAO_INICIADO
