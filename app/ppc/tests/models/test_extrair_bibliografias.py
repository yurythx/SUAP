import pytest

from ppc.utils import extrair_bibliografias_da_secao

LIVRO_1 = 'SOBRENOME, Nome. Título da obra. 2. ed. Natal: IFRN, 2020.'
LIVRO_2 = 'OUTRO, Autor. Outra obra: subtítulo. São Paulo: Editora, 2018.'


def test_um_paragrafo_por_referencia():
    assert extrair_bibliografias_da_secao(f'<p>{LIVRO_1}</p><p>&nbsp;</p><p>{LIVRO_2}</p>') == [LIVRO_1, LIVRO_2]


@pytest.mark.parametrize(
    'html',
    [
        pytest.param(f'<ol><li>{LIVRO_1}</li><li>{LIVRO_2}</li></ol>', id='ol-li'),
        pytest.param(f'<ul><li><p>{LIVRO_1}</p></li><li><p>{LIVRO_2}</p></li></ul>', id='li-com-p'),
        pytest.param(f'<p><ol><li>{LIVRO_1}</li><li>{LIVRO_2}</li></ol></p>', id='lista-dentro-de-p'),
    ],
)
def test_lista_gera_uma_referencia_por_item(html):
    assert extrair_bibliografias_da_secao(html) == [LIVRO_1, LIVRO_2]


def test_quebras_de_linha_no_paragrafo_separam_referencias():
    assert extrair_bibliografias_da_secao(f'<p>{LIVRO_1}<br>{LIVRO_2}<br /></p>') == [LIVRO_1, LIVRO_2]


@pytest.mark.parametrize('numeracao', ['1. ', '1.', '1) ', '1 - ', '01 \u2013 ', '12. '])
def test_numeracao_digitada_e_removida(numeracao):
    html = f'<p>{numeracao}{LIVRO_1}<br>2. {LIVRO_2}</p>'

    assert extrair_bibliografias_da_secao(html) == [LIVRO_1, LIVRO_2]


def test_numero_que_faz_parte_da_referencia_e_preservado():
    referencias = ['1984. Rio de Janeiro: Companhia das Letras, 2009.', '100 jogos de matemática. Natal: IFRN, 2015.']

    assert extrair_bibliografias_da_secao(''.join(f'<p>{r}</p>' for r in referencias)) == referencias
