import json

from bs4 import BeautifulSoup

from documento_eletronico.comparacao import gerar_comparacao_documentos, preparar_html_documento


def _mudancas(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, 'html.parser')
    return json.loads(soup.find(id='document-changes-data').string)


class TestComparacaoDocumentos:
    def test_marca_texto_alterado(self):
        comparacao = gerar_comparacao_documentos('<p>Texto original</p>', '<p>Texto atualizado</p>')
        soup = BeautifulSoup(comparacao, 'html.parser')

        assert soup.find('del').get_text(strip=True) == 'Texto original'
        assert soup.find('ins').get_text(strip=True) == 'Texto atualizado'
        assert _mudancas(comparacao) == [{'tipo': 'alteracao', 'antes': 'Texto original', 'depois': 'Texto atualizado'}]

    def test_resume_imagem_sem_reproduzi_la(self):
        comparacao = gerar_comparacao_documentos(
            '<p><img src="imagem-antiga.png" alt="Brasão antigo"></p>',
            '<p><img src="imagem-nova.png" alt="Brasão novo"></p>',
        )

        assert _mudancas(comparacao) == [{'tipo': 'alteracao_imagem', 'texto': 'Imagem alterada.'}]
        assert '<img' not in json.dumps(_mudancas(comparacao))

    def test_torna_imagem_responsiva(self):
        conteudo = preparar_html_documento('<p><img src="imagem.png" width="1200"></p>')
        imagem = BeautifulSoup(conteudo, 'html.parser').find('img')

        assert 'img-fluid' in imagem['class']
