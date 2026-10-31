"""Fluxo: assinatura digital de PDF — assinar com certificado, conferir e validar publicamente.

São as telas do serviço de assinatura do SUAP, e elas formam um ciclo fechado: o servidor assina
um PDF com o certificado que guardou no sistema, e qualquer pessoa — inclusive quem não tem conta
— pode jogar esse PDF na tela pública de validação e ver quem assinou. O ciclo é o teste: assinar
sem conseguir validar depois não é assinar.

A regressão que este arquivo pega é a silenciosa. A assinatura é feita por uma pilha de
criptografia inteira (``comum/signer.py`` → ``endesive`` → ``oscrypto`` → ``cryptography``), e uma
troca de versão em qualquer degrau produz um PDF que o SUAP aceita gravar e que **nenhum leitor
de PDF reconhece como assinado**. Como o defeito não levanta exceção, só um teste que assina e
**reverifica os bytes que saíram** o pega. É o que ``_assinantes_do_pdf`` faz aqui.

Dependência a declarar: ``endesive`` mora no grupo ``prod`` do ``pyproject.toml`` (é ele que
``comum/signer.py`` importa preguiçosamente). O CI o instala — ``uv sync --all-groups``,
``.gitlab-ci.yml`` —, mas um ambiente montado só com o grupo ``dev`` faz estes testes falharem com
``ModuleNotFoundError`` no meio da view, o que aparece como HTTP 500 na tela e não como erro de
ambiente.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from djtools.e2e_ui import Tela

from .conftest import ARQUIVO_PDF, ARQUIVO_PDF_ASSINADO, ASSINANTE, SENHA_DO_CERTIFICADO

if TYPE_CHECKING:
    from playwright.sync_api import Response

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
ASSINAR = '/comum/assinar_documento/'
ASSINAR_ICPEDU = '/comum/assinar_documento_icpedu/'
VERIFICAR = '/comum/verificar_documento/'
VALIDAR = '/comum/validar_assinatura/'


def _assinantes_do_pdf(conteudo: bytes) -> list[str]:
    """Os nomes comuns (CN) das assinaturas de um PDF em memória, pela pilha de produção.

    Usa ``comum.signer.verify`` — o mesmo código que a tela pública de validação chama — em vez de
    procurar ``/ByteRange`` no corpo: o que se quer afirmar é que o PDF **é verificável**, não que
    ele tem um carimbo parecido com assinatura.
    """
    import tempfile

    from comum import signer

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as arquivo:
        arquivo.write(conteudo)
    return [assinatura['cn'] for assinatura in signer.verify(arquivo.name)]


def _e_o_post_da_assinatura(resposta: Response) -> bool:
    """Casa a resposta do POST que assina — e não a do GET que carregou o formulário."""
    return ASSINAR in resposta.url and resposta.request.method == 'POST'


def test_assinar_documento_devolve_pdf_verificavel(logado_comum, certificado_digital):
    """Assina um PDF pela tela e confere que os bytes devolvidos carregam a assinatura.

    **Dois** capturadores, e não um: a view devolve ``PDFResponse(..., anexo=False)``, isto é,
    ``Content-Disposition: inline``, mas o Chromium headless ainda assim trata a navegação como
    download — e, ao fazê-lo, descarta o corpo do lado do protocolo. Medido:
    ``Response.body()`` devolve ``Protocol error (Network.getResponseBody): No resource with given
    identifier found``. Então os cabeçalhos vêm da resposta e os **bytes** vêm do arquivo baixado.

    O par ``pdf-coords``/``pdf-page`` que a view lê do POST vem de dois ``input hidden`` que o
    ``PositionedPdfInput`` renderiza no servidor com ``0:0`` e ``1``
    (``djtools/templates/widgets/positioned_pdf_input.html``). O posicionador visual é opcional —
    ele só reescreve esses campos quando o usuário arrasta o carimbo —, então o teste não depende
    do pdf.js, que vem de CDN.
    """
    tela = Tela(logado_comum('admin')).ir(ASSINAR)
    tela.preencher_formulario(
        [
            ('Arquivo PDF', 'arquivo real', ARQUIVO_PDF),
            ('Certificado', 'lista', str(certificado_digital)),
            ('Senha do Certificado', 'senha', SENHA_DO_CERTIFICADO),
        ]
    )

    with tela.pagina.expect_download() as baixado, tela.pagina.expect_response(_e_o_post_da_assinatura) as captura:
        tela.clicar_botao('Enviar')
    resposta = captura.value

    assert resposta.status == 200, f'a tela de assinatura respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'application/pdf', (
        f'a tela devolveu {resposta.headers["content-type"]!r} em vez do PDF assinado — provavelmente o formulário não validou'
    )

    with open(baixado.value.path(), 'rb') as assinado:
        conteudo = assinado.read()
    assert _assinantes_do_pdf(conteudo) == [ASSINANTE], 'o PDF voltou da tela, mas sem assinatura digital verificável'


def test_verificar_documento_reconhece_o_assinante(logado_comum):
    """A tela interna de conferência: sobe um PDF assinado e diz quem assinou.

    O arquivo é o PDF **assinado** versionado em ``comum/tests/arquivos/assinatura-digital/``
    (tipo ``arquivo real``). Com o PDF genérico de ``djtools/new_tests/files`` a tela responderia
    "Assinatura digital não identificada" — e o teste estaria afirmando o caminho vazio.
    """
    tela = Tela(logado_comum('admin')).ir(VERIFICAR)
    tela.preencher('Arquivo', 'arquivo real', ARQUIVO_PDF_ASSINADO)
    tela.clicar_botao('Enviar')

    tela.sucesso(f'Documento assinado digitalmente por {ASSINANTE}.')


def test_assinar_e_verificar_negados_a_quem_nao_e_dirigente(logado_comum):
    """Matriz de acesso (#17400): as duas telas internas são de Reitor e Diretor Geral, como no menu.

    O ``admin`` dos testes acima é superusuário e passa pelo ``group_required``; o servidor comum
    (``solicitante``, só no grupo ``Servidor``) recebe 403 mesmo digitando a URL. O lado positivo
    com usuário real nos grupos está em ``comum/tests/views/test_assinatura_digital.py``.
    """
    tela = Tela(logado_comum('solicitante'))

    assert tela.buscar(ASSINAR).status == 403, 'a tela de assinatura ficou aberta a quem não é Reitor nem Diretor Geral'
    assert tela.buscar(VERIFICAR).status == 403, 'a tela de verificação ficou aberta a quem não é Reitor nem Diretor Geral'


def test_validacao_publica_de_assinatura(pagina_anonima):
    """Quem recebeu o documento valida a assinatura **sem ter conta no SUAP**.

    Roda em página anônima de propósito: é essa a promessa impressa no carimbo de toda assinatura
    do SUAP (``comum/signer.py`` grava a URL desta tela no QR code). Se a tela passar a exigir
    login, todo documento já assinado fica sem como ser conferido por quem o recebeu.

    O reCAPTCHA do formulário não atrapalha: ``ReCaptchaField.validate``
    (``djtools/forms/fields/captcha.py``) devolve ``True`` sob teste, antes mesmo da checagem de
    obrigatoriedade.
    """
    tela = Tela(pagina_anonima).ir(VALIDAR)
    tela.preencher('Arquivo', 'arquivo real', ARQUIVO_PDF_ASSINADO)
    tela.clicar_botao('Enviar')

    tela.ver_texto('foram detectadas')
    tela.ver_texto(ASSINANTE)
    tela.ver_texto('A assinatura é')


def test_assinatura_icpedu_avisa_quando_o_servico_esta_fora(logado_comum):
    """A guarda da assinatura em nuvem: com a API ICP EDU desligada, a tela avisa em vez de quebrar.

    É o estado normal do SUAP fora de produção — ``comum/fixtures/apis_externas.json`` instala a
    ``APIExterna`` ICPEDU com ``ativo: false`` — e é o caminho que interessa proteger: sem a
    guarda, a tela montaria o formulário e só descobriria a indisponibilidade ao tentar assinar,
    já com o documento do usuário enviado.

    Entra pela tela de assinatura local primeiro porque a view responde ``httprr('..')``, que
    resolve o destino pelo *breadcrumb* da sessão (``djtools/utils/breadcrumbs.py``): sem uma tela
    anterior registrada, o destino seria o próprio caminho e o navegador entraria em laço de
    redirecionamento.
    """
    tela = Tela(logado_comum('admin')).ir(ASSINAR)
    tela.ir(ASSINAR_ICPEDU)

    tela.erro('O serviço de assinatura ICP EDU está temporariamente indisponível')
