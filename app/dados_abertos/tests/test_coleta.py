"""Testes da coleta: download com paginação e leitura tabular do conteúdo."""

import json

import pytest

from dados_abertos.enums import FormatoRecurso
from dados_abertos.services import coleta


class RespostaFake:
    """Resposta HTTP mínima no formato que ``coleta.baixar`` consome."""

    def __init__(self, conteudo: bytes, content_type: str = 'application/json'):
        self.content = conteudo
        self.headers = {'Content-Type': content_type}

    def raise_for_status(self) -> None:
        return None


def _servidor(paginas: dict[str, bytes], monkeypatch: pytest.MonkeyPatch, content_type: str = 'application/json') -> list[str]:
    """Instala um ``requests.get`` falso servindo ``paginas`` e devolve a lista de URLs acessadas."""
    acessos: list[str] = []

    def get_fake(url, **kwargs):
        acessos.append(url)
        return RespostaFake(paginas[url], content_type)

    monkeypatch.setattr('dados_abertos.services.coleta.requests.get', get_fake)
    return acessos


def test_segue_a_paginacao_e_concatena_os_registros(monkeypatch: pytest.MonkeyPatch) -> None:
    """O envelope de paginação do djtools é percorrido até o fim e some do arquivo final.

    Sem isso o recurso publicado no CKAN teria só a primeira página, embrulhada em
    ``{"results": ..., "count": ...}`` — que é o que o cidadão baixaria.
    """
    acessos = _servidor(
        {
            'https://suap.br/api/contrato/contratos/?ano=2026': json.dumps(
                {'results': [{'id': 1}, {'id': 2}], 'count': 3, 'next': 'https://suap.br/api/contrato/contratos/?ano=2026&page=2', 'previous': None}
            ).encode(),
            'https://suap.br/api/contrato/contratos/?ano=2026&page=2': json.dumps(
                {'results': [{'id': 3}], 'count': 3, 'next': None, 'previous': None}
            ).encode(),
        },
        monkeypatch,
    )

    coletado = coleta.baixar('https://suap.br/api/contrato/contratos/?ano=2026')

    assert len(acessos) == 2
    assert coletado.paginas == 2
    assert json.loads(coletado.conteudo) == [{'id': 1}, {'id': 2}, {'id': 3}]


def test_preserva_o_conteudo_quando_nao_ha_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL externa que não usa o envelope do djtools é gravada byte a byte, sem interpretação."""
    csv = b'matricula;nome\n123;Fulano\n'
    _servidor({'https://exemplo.br/servidores.csv': csv}, monkeypatch, content_type='text/csv')

    coletado = coleta.baixar('https://exemplo.br/servidores.csv')

    assert coletado.conteudo == csv
    assert coletado.paginas == 1


def test_interrompe_a_paginacao_em_ciclo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Um ``next`` que aponta para a própria página não pode prender a rotina em laço infinito."""
    url = 'https://suap.br/api/ensino/cursos/'
    _servidor({url: json.dumps({'results': [{'id': 1}], 'count': 1, 'next': url, 'previous': None}).encode()}, monkeypatch)

    coletado = coleta.baixar(url)

    assert json.loads(coletado.conteudo) == [{'id': 1}]


def test_le_as_colunas_de_um_csv_com_ponto_e_virgula() -> None:
    """O delimitador brasileiro (``;``) é reconhecido sem configuração."""
    tabular = coleta.ler_tabular('matricula;nome;campus\n123;Fulano;NAT\n', FormatoRecurso.CSV)

    assert tabular.colunas == ['matricula', 'nome', 'campus']
    assert tabular.linhas == [['123', 'Fulano', 'NAT']]


def test_le_as_colunas_de_um_json_de_objetos() -> None:
    """As chaves do primeiro registro definem as colunas do recurso JSON."""
    tabular = coleta.ler_tabular(json.dumps([{'numero': 1, 'objeto': 'Obra'}]), FormatoRecurso.JSON)

    assert tabular.colunas == ['numero', 'objeto']
    assert tabular.linhas == [['1', 'Obra']]


def test_json_invalido_vira_erro_e_nao_excecao() -> None:
    """A leitura nunca lança: quem chama decide o que fazer com o erro."""
    tabular = coleta.ler_tabular('{isso não é json', FormatoRecurso.JSON)

    assert tabular.erro
    assert tabular.colunas == []


def test_json_de_objeto_unico_vira_um_registro() -> None:
    """Um objeto plano é um registro, não a ausência de registros.

    É a forma do ``/ensino/estatistica/alunos_geral/``, cujo endpoint declara
    ``response=EstatisticaAlunoGeralSchema`` em vez de ``list[...]``: sem isto a prévia do LAI
    mostra "Sem registros." para um recurso que tem dados.
    """
    payload = json.dumps({'quantidade_total_alunos': 48231, 'quantidade_total_matriculas_trancadas': 1975})
    tabular = coleta.ler_tabular(payload, FormatoRecurso.JSON)

    assert tabular.erro is None
    assert tabular.colunas == ['quantidade_total_alunos', 'quantidade_total_matriculas_trancadas']
    assert tabular.linhas == [['48231', '1975']]


def test_json_de_objeto_vazio_segue_sem_registros() -> None:
    """Objeto sem chave alguma não vira linha em branco."""
    tabular = coleta.ler_tabular('{}', FormatoRecurso.JSON)

    assert tabular.erro
    assert tabular.linhas == []


def test_teto_de_paginacao_falha_alto_em_vez_de_truncar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Estourar o teto não pode virar arquivo publicado como se estivesse completo.

    O módulo já declara, em ``_coletar_recursos``, que publicar um dataset pela metade é pior do
    que adiar a atualização: cortar em silêncio contradizia isso.
    """
    monkeypatch.setattr(coleta, 'MAX_PAGINAS', 3)
    monkeypatch.setattr(
        coleta.requests,
        'get',
        lambda url, **kwargs: RespostaFake(json.dumps({'results': [{'n': url[-1]}], 'next': f'{url}x'}).encode()),
    )

    with pytest.raises(coleta.ColetaTruncada):
        coleta.baixar('https://suap.br/api/contrato/contratos/?ano=2026')
