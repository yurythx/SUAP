from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest import mock
from unittest.mock import MagicMock

import pytest
import requests

from comum.models import Configuracao
from edu.diploma_digital.rap import ERRO_CONECTIVIDADE, AssinadorDigital

_DATA_PADRAO = date(2024, 6, 1)
_VALOR_PADRAO = object()


@pytest.fixture
def contexto_assinador() -> dict[str, Any]:
    return {
        'assinador': AssinadorDigital(debug=False),
        'data_emissao': date(2024, 6, 15),
        'data_expedicao': date(2024, 7, 1),
    }


def _criar_aluno_mock(
    *,
    qacademico: bool = False,
    data_conclusao: date | None = None,
    data_colacao: date | None | object = _VALOR_PADRAO,
) -> MagicMock:
    data_colacao_efetiva: date | None = _DATA_PADRAO if data_colacao is _VALOR_PADRAO else data_colacao  # type: ignore[assignment]
    aluno = MagicMock()
    aluno.matricula = '2023001'
    aluno.is_qacademico.return_value = qacademico
    aluno.dt_conclusao_curso = data_conclusao
    aluno.data_matricula = date(2023, 1, 15)
    aluno.forma_ingresso.get_classificacao_diploma_digital_display.return_value = 'Vestibular'
    aluno.atividadecomplementar_set.filter.return_value = []
    aluno.get_estagios_historico.return_value = []
    aluno.get_data_colacao_grau.return_value = data_colacao_efetiva

    if not qacademico:
        aluno.matriz.estrutura.is_lancamento_conceito.return_value = False
        aluno.get_convocacoes_enade_diploma.return_value = []
        if data_colacao_efetiva is not None:
            participacao = MagicMock()
            participacao.colacao_grau.data_colacao = data_colacao_efetiva
            aluno.get_participacao_colacao_grau.return_value = participacao
        else:
            aluno.get_participacao_colacao_grau.return_value = None

    return aluno


def _criar_historico(
    *,
    data_colacao: date | None | object = _VALOR_PADRAO,
    ch_total: str = '3000',
    ch_total_cumprida: str = '2800',
) -> dict[str, Any]:
    data_colacao_efetiva: date | None = _DATA_PADRAO if data_colacao is _VALOR_PADRAO else data_colacao  # type: ignore[assignment]
    return {
        'grupos_componentes': {},
        'ch_total': ch_total,
        'ch_total_cumprida': ch_total_cumprida,
        'data_colacao_grau': data_colacao_efetiva,
        'convocacoes': [],
    }


def _criar_matricula_periodo(
    *, situacao: str = 'OutraSituacao', descricao: str = 'Reprovado por falta', ano: int = 2023, periodo: int = 1
) -> MagicMock:
    matricula_periodo = MagicMock()
    matricula_periodo.situacao.get_situacao_diploma_digital.return_value = situacao
    matricula_periodo.situacao.descricao = descricao
    matricula_periodo.ano_letivo.ano = ano
    matricula_periodo.periodo_letivo = periodo
    return matricula_periodo


def _obter_situacao_discente(aluno: MagicMock, historico: dict[str, Any], contexto_assinador: dict[str, Any]) -> Any:
    aluno.get_historico_legado.return_value = historico
    aluno.get_historico.return_value = historico

    _, dados = contexto_assinador['assinador'].get_dados_historico_escolar(
        aluno,
        contexto_assinador['data_emissao'],
        contexto_assinador['data_expedicao'],
    )
    return dados['SituacaoAtualDiscente']['Situacao']


def test_historico_usa_dict_outra_situacao_quando_situacao_nao_padrao(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock()
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo(
        situacao='OutraSituacao',
        descricao='Reprovado por falta',
    )

    situacao = _obter_situacao_discente(aluno, _criar_historico(), contexto_assinador)

    assert situacao == {'OutraSituacao': 'Reprovado por falta'}


def test_historico_usa_string_simples_quando_situacao_padrao(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock()
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo(
        situacao='MatriculadoEmDisciplina',
        descricao='Matriculado',
    )

    situacao = _obter_situacao_discente(aluno, _criar_historico(), contexto_assinador)

    assert situacao == 'MatriculadoEmDisciplina'


def test_historico_do_formado_informa_datas_obrigatorias(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock(data_conclusao=date(2024, 5, 20), data_colacao=date(2024, 6, 1))
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo()

    situacao = _obter_situacao_discente(aluno, _criar_historico(data_colacao=date(2024, 6, 1)), contexto_assinador)

    assert isinstance(situacao, dict)
    assert 'Formado' in situacao
    assert situacao['Formado']['DataConclusaoCurso'] == '2024-05-20'
    assert situacao['Formado']['DataColacaoGrau'] == '2024-06-01'
    assert situacao['Formado']['DataExpedicaoDiploma'] == contexto_assinador['data_expedicao'].isoformat()


def test_historico_do_formado_sem_colacao_grau_registra_erro(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock(data_conclusao=date(2024, 5, 20), data_colacao=None)
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo()
    historico = _criar_historico(data_colacao=None)
    aluno.get_historico.return_value = historico

    erros, dados = contexto_assinador['assinador'].get_dados_historico_escolar(
        aluno,
        contexto_assinador['data_emissao'],
        contexto_assinador['data_expedicao'],
    )

    assert 'Data de colação de grau não foi informada.' in erros
    situacao = dados['SituacaoAtualDiscente']['Situacao']
    assert situacao['Formado']['DataColacaoGrau'] is None


def test_historico_do_aluno_nao_formado_sem_colacao_nao_gera_erro_de_colacao(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock(data_conclusao=None, data_colacao=None)
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo(
        situacao='MatriculadoEmDisciplina',
        descricao='Matriculado',
    )
    historico = _criar_historico(data_colacao=None)
    aluno.get_historico.return_value = historico

    erros, _ = contexto_assinador['assinador'].get_dados_historico_escolar(
        aluno,
        contexto_assinador['data_emissao'],
        contexto_assinador['data_expedicao'],
    )

    assert 'Data de colação de grau não foi informada.' not in erros


def test_historico_aluno_qacademico_formado_sem_colacao_registra_erro(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock(qacademico=True, data_conclusao=date(2024, 5, 20), data_colacao=None)
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo()
    historico = _criar_historico(data_colacao=None)
    aluno.get_historico_legado.return_value = historico

    erros, dados = contexto_assinador['assinador'].get_dados_historico_escolar(
        aluno,
        contexto_assinador['data_emissao'],
        contexto_assinador['data_expedicao'],
    )

    assert 'Data de colação de grau não foi informada.' in erros
    situacao = dados['SituacaoAtualDiscente']['Situacao']
    assert situacao['Formado']['DataColacaoGrau'] is None


def test_historico_do_intercambio_internacional_retorna_objeto_vazio(contexto_assinador: dict[str, Any]) -> None:
    aluno = _criar_aluno_mock()
    aluno.get_ultima_matricula_periodo.return_value = _criar_matricula_periodo(
        situacao='IntercambioInternacional',
        descricao='Intercambio',
    )

    situacao = _obter_situacao_discente(aluno, _criar_historico(), contexto_assinador)

    assert situacao == {'IntercambioInternacional': {}}


def _resposta_500(*args: Any, **kwargs: Any) -> requests.Response:
    resposta = requests.Response()
    resposta.status_code = 500
    resposta._content = b'{}'
    return resposta


def _sem_rede(*args: Any, **kwargs: Any) -> requests.Response:
    raise requests.exceptions.ConnectionError('RAP fora do ar')


@pytest.mark.django_db
@pytest.mark.parametrize('falha', [_sem_rede, _resposta_500], ids=['sem_rede', 'http_500'])
def test_consultar_documento_devolve_erro_de_conectividade_quando_o_rap_falha(falha) -> None:
    """#17448: o ``except ConnectionError`` embutido não pegava a falha de rede do ``requests``."""
    Configuracao.objects.update_or_create(app='edu', chave='rap_api_url', defaults={'valor': 'https://rap.exemplo'})
    Configuracao.clear_cache()
    documento = SimpleNamespace(id_rap=1, status_rap=None)

    try:
        with mock.patch('requests.Session.send', side_effect=falha) as send:
            codigo = AssinadorDigital(debug=False).consultar_documento(documento)
    finally:
        Configuracao.clear_cache()

    assert send.called
    assert codigo == ERRO_CONECTIVIDADE


def test_envio_da_documentacao_nao_deixa_o_pdfa_no_disco(tmp_path) -> None:
    """#17602: o PDF/A gerado para cada documento da pasta documental ficava no disco a cada sincronização."""
    pdfa = tmp_path / 'documento_pdfa.pdf'

    def to_pdfa() -> str:
        pdfa.write_bytes(b'%PDF-1.4 PDF/A')
        return str(pdfa)

    aluno_arquivo = MagicMock(id=1)
    aluno_arquivo.to_pdfa.side_effect = to_pdfa
    assinatura = MagicMock()
    assinatura.registro_emissao_diploma.aluno.is_qacademico.return_value = False
    assinatura.registro_emissao_diploma.aluno.get_documentos_obrigatorios.return_value = [aluno_arquivo]
    assinador = AssinadorDigital(debug=False)

    with (
        mock.patch('edu.diploma_digital.rap.UnidadeOrganizacional'),
        mock.patch('edu.diploma_digital.rap.Credenciamento'),
        mock.patch('edu.diploma_digital.rap.get_sigla_reitoria', return_value='RE'),
        mock.patch.multiple(
            assinador,
            get_autorizacao=mock.DEFAULT,
            get_reconhecimento=mock.DEFAULT,
            get_tramitacao_emec=mock.DEFAULT,
            get_renovacao_reconhecimento=mock.DEFAULT,
        ),
        mock.patch.object(assinador, 'get_dados_historico_escolar', return_value=(['Histórico incompleto'], {})),
        mock.patch.object(assinador, 'registrar_erro_cadastro') as registrar_erro_cadastro,
    ):
        assinador.enviar_documentacao_academica(assinatura)

    aluno_arquivo.to_pdfa.assert_called_once()
    assert not pdfa.exists()
    assert 'Histórico incompleto' in registrar_erro_cadastro.call_args.kwargs['detalhe']
