"""Fluxo: leitura de um arquivo posicional do SIAFI a partir do seu layout.

O SIAFI entrega dois arquivos: o *ref*, que descreve o layout (uma linha por campo, com a
descrição nos 40 primeiros caracteres, o tipo no 41º e o tamanho no resto), e o arquivo de
dados, posicional, sem separador nenhum. A tela casa os dois: fatia cada linha de dados pelas
posições do layout e devolve os registros já nomeados, filtrados pelo texto buscado.

O fluxo tem dois passos porque a paginação é servida da sessão: o resultado é calculado no
POST e relido no GET da página seguinte — quem mexer nisso sem o segundo passo quebra a
navegação sem quebrar teste nenhum.

Divisão com o e2e (``comum/tests/e2e/test_ferramentas_apoio.py``): lá o envio passa pelo
navegador e afirma a tabela na tela; aqui se afirmam o filtro, a paginação pela sessão e o
token CSRF do formulário.
"""

from __future__ import annotations

import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from rh.tests.factories import ServidorFactory, SetorFactory

VER_ARQUIVO_SIAFI = '/comum/ver_arquivo_siafi/'


def _campo_do_layout(descricao: str, tipo: str, tamanho: str) -> bytes:
    """Monta uma linha do arquivo *ref*: 40 posições de descrição, 1 de tipo, o resto tamanho."""
    return f'{descricao:<40}{tipo}{tamanho}'.encode('latin-1')


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_extrai_os_itens_do_arquivo_posicional_e_pagina_pela_sessao(client) -> None:
    servidor = ServidorFactory(setor=SetorFactory(sigla='SI0'))
    client.force_login(servidor.get_user())

    layout = b'\n'.join(
        [
            _campo_do_layout('UNIDADE GESTORA', 'N', '6'),
            _campo_do_layout('CREDOR', 'A', '10'),
        ]
    )
    # Posicional: 6 posições de unidade gestora + 10 de credor, sem separador.
    dados = '153080SIMÕES LTD\n153081PAPELARIA '.encode('latin-1')

    resposta = client.post(
        VER_ARQUIVO_SIAFI,
        {
            'arquivo_1': SimpleUploadedFile('ref.txt', layout, content_type='text/plain'),
            'arquivo_2': SimpleUploadedFile('siafi.txt', dados, content_type='text/plain'),
            'campo_busca': 'SIMÕES',
        },
    )

    assert resposta.status_code == 200
    itens = resposta.context['itens']
    assert len(itens) == 1, 'o filtro por texto deveria ter deixado passar só a linha do credor buscado'
    (item,) = itens
    assert item['UNIDADE GESTORA'] == '153080'
    assert item['CREDOR'] == 'SIMÕES LTD'
    assert resposta.context['arquivo'] == 'siafi.txt'

    # O segundo passo relê o resultado da sessão, sem reenviar os arquivos.
    resposta = client.get(VER_ARQUIVO_SIAFI, {'page': '1'})

    assert resposta.status_code == 200
    assert [i['CREDOR'] for i in resposta.context['itens']] == ['SIMÕES LTD'], 'a paginação perdeu o resultado guardado na sessão'


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_busca_vazia_devolve_o_arquivo_inteiro(client) -> None:
    """Sem texto de busca a tela lista tudo — é como se confere o arquivo recebido."""
    servidor = ServidorFactory(setor=SetorFactory(sigla='SI1'))
    client.force_login(servidor.get_user())

    layout = _campo_do_layout('UNIDADE GESTORA', 'N', '6')
    dados = b'153080\n153081\n153082'

    resposta = client.post(
        VER_ARQUIVO_SIAFI,
        {
            'arquivo_1': SimpleUploadedFile('ref.txt', layout, content_type='text/plain'),
            'arquivo_2': SimpleUploadedFile('siafi.txt', dados, content_type='text/plain'),
            'campo_busca': '',
        },
    )

    assert resposta.status_code == 200
    assert [item['UNIDADE GESTORA'] for item in resposta.context['itens']] == ['153080', '153081', '153082']


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_formulario_envia_o_token_csrf() -> None:
    """O navegador só processa o envio se o formulário carregar o token (#17394).

    Sem ``{% csrf_token %}`` no ``<form>`` do template, todo envio real respondia 403. O cliente
    de teste padrão não impõe CSRF; aqui ele impõe, e o token é tirado **do formulário da tela**
    — o cookie ou outro form da página passariam sem a correção.
    """
    client = Client(enforce_csrf_checks=True)
    servidor = ServidorFactory(setor=SetorFactory(sigla='SI2'))
    client.force_login(servidor.get_user())

    pagina = client.get(VER_ARQUIVO_SIAFI).content.decode()
    formulario = pagina.split(f'action="{VER_ARQUIVO_SIAFI}"', 1)[1].split('</form>', 1)[0]
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', formulario)
    assert token, 'o formulário do leitor SIAFI não carrega o token CSRF'

    resposta = client.post(
        VER_ARQUIVO_SIAFI,
        {
            'csrfmiddlewaretoken': token.group(1),
            'arquivo_1': SimpleUploadedFile('ref.txt', _campo_do_layout('UNIDADE GESTORA', 'N', '6'), content_type='text/plain'),
            'arquivo_2': SimpleUploadedFile('siafi.txt', b'153080', content_type='text/plain'),
            'campo_busca': '',
        },
    )

    assert resposta.status_code == 200
    assert [item['UNIDADE GESTORA'] for item in resposta.context['itens']] == ['153080']
