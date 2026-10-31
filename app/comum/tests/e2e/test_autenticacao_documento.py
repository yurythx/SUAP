"""Fluxo: autenticação pública de documento emitido pelo SUAP — do código verificador ao PDF.

Todo documento que o SUAP emite (declaração, certificado, carteira funcional, diploma) sai com um
rodapé que diz *tipo, data de emissão e código verificador*, e com um QR code apontando para a
tela pública de autenticação. Quem recebe o papel confere a emissão ali, **sem conta no SUAP**, e
baixa o original em PDF pelo link que a própria tela oferece. Este arquivo percorre esse caminho
inteiro: autenticar → link → baixar.

A regressão que ele pega é a que invalida documento já entregue: a tela de autenticação deixa de
encontrar o registro (mudou a janela de data, o ``startswith`` do código, a lista de tipos), ou o
link de download passa a exigir sessão. Nos dois casos o documento impresso, que continua
circulando, vira impossível de conferir — e ninguém percebe de dentro do sistema.

Cobre também ``/comum/documentos_emitidos_suap/``, o índice em que o próprio usuário reúne os
documentos que pode emitir. Essa tela é um *fan-out* por sinal (``djtools.documentos.signal``):
nove aplicações respondem a ele, e um erro em qualquer uma derruba o índice inteiro.
"""

from __future__ import annotations

from datetime import date

import pytest

from djtools.e2e_ui import Tela

from .conftest import ASSINANTE

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
AUTENTICAR = '/comum/autenticar_documento/'
BAIXAR = '/comum/baixar_documento/{pk}/{codigo}/'
DOCUMENTOS_EMITIDOS = '/comum/documentos_emitidos_suap/'


def test_autenticacao_publica_localiza_o_documento_e_baixa_o_pdf(pagina_anonima, registro_emissao_documento):
    """Autentica pelo trio do rodapé, confere o assinante e baixa o PDF pelo link da própria tela.

    Um teste só para as duas rotas porque a segunda **é** o desfecho da primeira: o endereço de
    download não é adivinhado pelo teste, é o ``href`` que a tela de autenticação publica. Afirmar
    o ``href`` antes de buscá-lo é o que faz o teste medir o contrato (a tela aponta para o
    registro certo) e não uma coincidência de URL montada por fora.

    O download é feito com ``buscar`` (a requisição da própria sessão do navegador, sem renderizar)
    porque a resposta é ``application/pdf``: um ``goto`` num PDF não produz DOM e não haveria o que
    afirmar além de "não explodiu".

    Roda anônimo de propósito — é a promessa impressa no QR code de todo documento do SUAP.
    """
    registro = registro_emissao_documento
    url_do_pdf = BAIXAR.format(pk=registro.pk, codigo=registro.codigo_verificador)

    tela = Tela(pagina_anonima).ir(AUTENTICAR)
    tela.preencher_formulario(
        [
            ('Tipo de Documento', 'lista', registro.tipo),
            ('Data da Emissão', 'data', registro.data_emissao.strftime('%d/%m/%Y')),
            ('Código Verificador', 'texto', registro.codigo_verificador),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto('Documento autenticado com sucesso.')
    # O registro aponta para um PDF assinado, então a tela tem de identificar quem assinou:
    # é o ramo que chama `comum.signer.verify` sobre o arquivo guardado.
    tela.ver_texto(ASSINANTE)

    link = tela.loc(f'//a[@href="{url_do_pdf}"]').first
    assert link.count(), f'a tela autenticou o documento mas não ofereceu o download em {url_do_pdf}'

    pdf = tela.buscar(url_do_pdf)
    assert pdf.status == 200, f'o download do documento autenticado respondeu HTTP {pdf.status}'
    assert pdf.headers['content-type'] == 'application/pdf', f'o download veio como {pdf.headers["content-type"]!r}'
    assert pdf.body().startswith(b'%PDF'), 'o download não é um PDF'


def test_autenticacao_de_codigo_inexistente_nao_autentica(pagina_anonima, registro_emissao_documento):
    """Código que não existe tem de dizer isso — e nunca autenticar por engano.

    O contraexemplo importa porque a busca é por ``codigo_verificador__startswith`` dentro de uma
    janela de data: é um filtro frouxo por construção, e o que impede um código inventado de casar
    com um documento real é só ele. O registro da fixture existe para a lista de tipos ter opção —
    e para o teste provar que a tela rejeitou mesmo tendo onde procurar.
    """
    tela = Tela(pagina_anonima).ir(AUTENTICAR)
    tela.preencher_formulario(
        [
            ('Tipo de Documento', 'lista', registro_emissao_documento.tipo),
            ('Data da Emissão', 'data', date.today().strftime('%d/%m/%Y')),
            ('Código Verificador', 'texto', 'ZZZZZZZZZZ'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto('Documento não autenticado.')


def test_indice_de_documentos_emitidos(logado_comum):
    """O índice pessoal de documentos abre e responde ao *fan-out* das nove aplicações.

    A asserção é o estado vazio ("Não há documentos"), e é o que há para afirmar: as fontes do
    índice são de outros módulos (processo eletrônico, documento eletrônico, ensino, pesquisa), e
    montá-las aqui inverteria a dependência entre os apps. O que o teste protege é o *fan-out* em
    si — ``documentos.signal.send`` percorre todos os receptores registrados, e uma exceção em
    qualquer um deles derruba a tela para todo mundo, inclusive para quem tem documentos.
    """
    tela = Tela(logado_comum('solicitante')).ir(DOCUMENTOS_EMITIDOS)

    tela.ver_titulo('Meus Documentos SUAP')
    tela.ver_texto('Não há documentos.')
