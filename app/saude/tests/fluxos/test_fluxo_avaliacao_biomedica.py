"""Testes de fluxo da Avaliação Biomédica (saúde).

Cobrem o ciclo de vida de um atendimento do ponto de vista do profissional de
saúde: abrir o atendimento, preencher as fichas (sinais vitais, antropometria,
acuidade visual, antecedentes, etc.) e fechar. Cada teste parte do estado
montado pelas fixtures (`conftest.py`) e exercita um endpoint real.
"""

import pytest

from comum.pytest_fixtures import assert_no_validation_errors, assert_redirects
from saude.models import (
    AcuidadeVisual,
    AntecedentesFamiliares,
    Antropometria,
    Atendimento,
    DesenvolvimentoPessoal,
    ExameFisico,
    HabitosDeVida,
    InformacaoAdicional,
    PercepcaoSaudeBucal,
    ProcessoSaudeDoenca,
    SinaisVitais,
    SituacaoAtendimento,
)

# Fichas que seguem o mesmo contrato: POST cria um registro e redireciona para a
# aba correspondente da avaliação. (rota, dados, modelo, aba)
FICHAS = [
    (
        'sinaisvitais',
        {'pressao_sistolica': 120, 'pressao_diastolica': 80, 'pulsacao': 45},
        SinaisVitais,
        'aba_sinais_vitais',
    ),
    (
        'antropometria',
        {'estatura': 170, 'peso': 80, 'sentimento_relacao_corpo': 'Muito satisfeito(a)', 'periodo_sem_comida': 'Nunca'},
        Antropometria,
        'aba_antropometria',
    ),
    (
        'acuidadevisual',
        {'usa_lente': False, 'teste_com_lente': False, 'olho_esquerdo': '20/20', 'olho_direito': '20/15'},
        AcuidadeVisual,
        'aba_acuidade_visual',
    ),
    (
        'processosaudedoenca',
        {
            'fez_cirurgia': False,
            'hemorragia': False,
            'alergia_medicamentos': False,
            'usa_medicamentos': False,
            'tem_plano_saude': False,
            'tem_plano_odontologico': False,
            'lesoes_ortopedicas': False,
            'doencas_previas': False,
            'problema_auditivo': False,
            'tem_deficiencia': False,
            'tem_transtorno_neuro': False,
            'gestante': False,
            'tem_doenca_cronica': False,
        },
        ProcessoSaudeDoenca,
        'aba_antecedentes',
    ),
    (
        'habitosdevida',
        {
            'atividade_fisica': False,
            'fuma': False,
            'bebe': False,
            'usa_drogas': False,
            'vida_sexual_ativa': False,
            'frequencia_semanal': 1,
            'duracao_atividade': 1,
            'frequencia_bebida': 1,
        },
        HabitosDeVida,
        'aba_habitosdevida',
    ),
    (
        'desenvolvimentopessoal',
        {'problema_aprendizado': False},
        DesenvolvimentoPessoal,
        'aba_desenvolvimentopessoal',
    ),
    (
        'informacao_adicional',
        {'informacao': 'Texto com a informação adicional.'},
        InformacaoAdicional,
        'aba_informacaoadicional',
    ),
    (
        'examefisico',
        {
            'ectoscopia_alterada': False,
            'acv_alterado': False,
            'ar_alterado': False,
            'abdome_alterado': False,
            'mmi_alterados': False,
            'mms_alterados': False,
            'snl_alterado': False,
            'esm_alterado': False,
            'outras_alteracoes': False,
        },
        ExameFisico,
        'aba_examefisico',
    ),
]


@pytest.mark.django_db(databases='__all__')
class TestFluxoAvaliacaoBiomedica:
    def test_abrir_atendimento_biomedico(self, profissional, prontuario, aluno):
        """Abrir o atendimento de um aluno cria a avaliação e redireciona para ela."""
        resposta = profissional.get(f'/saude/abrir_atendimento/1/{prontuario.id}/0/{aluno.id}/')

        atendimento = Atendimento.objects.latest('id')
        assert_redirects(resposta, f'/saude/avaliacao_biomedica/{atendimento.id}/')
        assert atendimento.prontuario == prontuario

    @pytest.mark.parametrize(('rota', 'dados', 'modelo', 'aba'), FICHAS, ids=[ficha[0] for ficha in FICHAS])
    def test_preencher_ficha(self, profissional, atendimento_aberto, rota, dados, modelo, aba):
        """Cada ficha da avaliação é registrada e leva à aba correspondente."""
        url = f'/saude/adicionar_{rota}/{atendimento_aberto.id}/'

        resposta = profissional.post(url, dados)

        assert_no_validation_errors(resposta)
        assert_redirects(resposta, f'/saude/avaliacao_biomedica/{atendimento_aberto.id}/?tab={aba}')
        assert modelo.objects.filter(atendimento=atendimento_aberto).exists()

    def test_preencher_antecedentes_familiares(self, profissional, atendimento_aberto, doencas):
        doenca_a, doenca_b = doencas
        dados = {
            'tem_agravos_primeiro_grau': True,
            'tem_agravos_segundo_grau': True,
            'agravos_primeiro_grau': doenca_a.id,
            'agravos_segundo_grau': doenca_b.id,
        }

        resposta = profissional.post(f'/saude/adicionar_antecedentesfamiliares/{atendimento_aberto.id}/', dados)

        assert_no_validation_errors(resposta)
        assert AntecedentesFamiliares.objects.filter(atendimento=atendimento_aberto).exists()

    def test_preencher_percepcao_saude_bucal(self, profissional, atendimento_aberto):
        dados = {
            'foi_dentista_anteriormente': False,
            'usa_fio_dental': False,
            'frequencia_escovacao': 'Uma vez',
            'qtd_por_dia_consome_acucar': 'Uma vez',
            'usa_protese': False,
            'usa_aparelho_ortodontico': False,
            'dificuldades': False,
        }

        resposta = profissional.post(f'/saude/adicionar_percepcaosaudebucal/{atendimento_aberto.id}/1/', dados)

        assert_no_validation_errors(resposta)
        assert PercepcaoSaudeBucal.objects.filter(atendimento=atendimento_aberto).exists()

    def test_fechar_atendimento_completo(self, profissional, atendimento_completo):
        """Sem pendências, fechar o atendimento o move para a situação FECHADO."""
        resposta = profissional.post(f'/saude/fechar_atendimento/{atendimento_completo.id}/', {'obs_fechado': 'Observação ao fechar'})

        assert_no_validation_errors(resposta)
        atendimento_completo.refresh_from_db()
        assert atendimento_completo.situacao == SituacaoAtendimento.FECHADO

    def test_nao_fecha_atendimento_com_pendencias(self, profissional, atendimento_aberto):
        """Sem as fichas obrigatórias preenchidas, o atendimento permanece ABERTO."""
        profissional.post(f'/saude/fechar_atendimento/{atendimento_aberto.id}/', {'obs_fechado': 'Tentativa'})

        atendimento_aberto.refresh_from_db()
        assert atendimento_aberto.situacao == SituacaoAtendimento.ABERTO
