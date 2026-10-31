"""Testes das funções de leitura de arquivos de colunas fixas (``comum.importador``).

É o parsing que o motor da importação SIAPE (``rh/importacao_siape``, acionado pelo command
``importar_siape``) usa para ler cada par ``.REF``/``.TXT`` — daí a categoria ``tasks/``. O
fluxo antigo do ``Importador`` (``run``, ``identificar_layout``, descompactação e limpeza de
pastas) foi removido na #17415, e o ``Importador`` base e o ``txt_to_dict`` na #17414.
"""

import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from comum.importador import formatar_ref, get_itens

# Layout sintético mínimo, para os testes de parsing que não precisam do arquivo real.
REF_MINIMA = ['CODIGO                                  N 0002\n', 'NOME                                    A 0004\n']


def _apagar(caminho: str) -> None:
    """Apaga recursivamente uma pasta do storage, tolerando o que já não existe."""
    if not default_storage.exists(caminho):
        return
    pastas, arquivos = default_storage.listdir(caminho)
    for nome in arquivos:
        default_storage.delete(f'{caminho}/{nome}')
    for nome in pastas:
        _apagar(f'{caminho}/{nome}')
    default_storage.delete(caminho)


@pytest.fixture
def pasta():
    """Pasta de trabalho exclusiva deste teste, no ``MEDIA_ROOT`` (que é real e compartilhado).

    Infraestrutura, não dado de teste: o ``MEDIA_ROOT`` é o mesmo para todos os workers do
    xdist e para execuções simultâneas.
    """
    raiz = f'comum/importador_teste_{uuid.uuid4().hex[:8]}'
    yield raiz
    _apagar(raiz)


# --- funções puras de parsing ------------------------------------------------


def test_formatar_ref_calcula_as_posicoes_dos_campos() -> None:
    campos = formatar_ref(REF_MINIMA)

    assert [c['descricao'] for c in campos] == ['CODIGO', 'NOME']
    assert (campos[0]['inicio'], campos[0]['fim']) == (0, 2)
    assert (campos[1]['inicio'], campos[1]['fim']) == (2, 6)


def test_formatar_ref_soma_as_partes_de_um_tamanho_decimal() -> None:
    # Campo monetário "12,2" ocupa 14 posições no arquivo (parte inteira + casas decimais)
    campos = formatar_ref(['VALOR                                   N 12,2\n'])

    assert campos[0]['tamanho'] == '12,2'
    assert campos[0]['tamanho_int'] == 14
    assert campos[0]['fim'] == 14


# --- get_itens ---------------------------------------------------------------


def test_get_itens_le_o_par_ref_txt(pasta) -> None:
    default_storage.save(f'{pasta}/mini.REF', ContentFile(''.join(REF_MINIMA).encode()))
    default_storage.save(f'{pasta}/mini.TXT', ContentFile(b'00BETA\n01ALFA\n'))

    itens = get_itens(f'{pasta}/mini.REF', f'{pasta}/mini.TXT')

    # O campo zerado sai como '00', não None: as funções `importar_*` do SIAPE tratam os zeros
    # campo a campo (flags '0' têm significado, `int('000')`, `.lstrip('0')`) — #17414.
    assert itens == [{'CODIGO': '00', 'NOME': 'BETA'}, {'CODIGO': '01', 'NOME': 'ALFA'}]


def test_get_itens_ordena_pelo_campo_pedido(pasta) -> None:
    default_storage.save(f'{pasta}/mini.REF', ContentFile(''.join(REF_MINIMA).encode()))
    default_storage.save(f'{pasta}/mini.TXT', ContentFile(b'02BETA\n01ALFA\n'))

    itens = get_itens(f'{pasta}/mini.REF', f'{pasta}/mini.TXT', order_by='CODIGO')

    assert [i['CODIGO'] for i in itens] == ['01', '02']


def test_get_itens_sem_arquivo_devolve_lista_vazia(pasta) -> None:
    assert get_itens(f'{pasta}/nao-existe.REF', f'{pasta}/nao-existe.TXT') == []
