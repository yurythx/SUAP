"""Ida e volta do id da pessoa no terminal de chaves legado (``suap-terminais``).

O terminal guarda a tabela de permissões (``/chaves/get_tabela_permissoes/``) e devolve os
empréstimos (``importar_emprestimos``, XML-RPC) com o id da sua tabela ``pessoa``, que vem do dump
do ``comum``: ``-vinculo.id``, uma linha por vínculo. O ``REMOTE_ADDR`` é explícito e fora do
``127.0.0.1`` (ver ``comum/tests/views/test_webservice.py``).
"""

from __future__ import annotations

import io
import xmlrpc.client
import zipfile

import pytest
from django.test import Client

from chaves.models import Movimentacao
from chaves.tests.factories import ChaveFactory
from comum.tests.factories import PrestadorServicoFactory
from ponto.tests.factories import MaquinaFactory
from rh.models import Servidor

pytestmark = pytest.mark.django_db

IP_TERMINAL = '10.99.0.43'


def test_permissao_e_emprestimo_usam_o_id_do_vinculo(client: Client, operador: Servidor) -> None:
    MaquinaFactory(ip=IP_TERMINAL, cliente_chaves=True)
    vinculo = PrestadorServicoFactory().get_vinculo()
    vinculo_operador = operador.get_vinculo()
    chave = ChaveFactory()
    chave.vinculos.add(vinculo)

    resposta = client.get('/chaves/get_tabela_permissoes/', REMOTE_ADDR=IP_TERMINAL)
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as dump:
        permissoes = [linha.split('\t')[1:] for linha in dump.read('tabela_terminal.copy').decode().splitlines()]

    registro = f'1\t{chave.id}\t{-vinculo_operador.id}\t{-vinculo.id}\t2026-10-19 10:00:00\tnull\tnull\tnull\tnull\tnull'
    envelope = xmlrpc.client.dumps((registro,), methodname='importar_emprestimos')
    retorno = client.post('/webservice/', data=envelope, content_type='text/xml', REMOTE_ADDR=IP_TERMINAL)

    assert [str(chave.id), str(-vinculo.id)] in permissoes
    assert xmlrpc.client.loads(retorno.content)[0][0]['ok'] is True
    movimentacao = Movimentacao.objects.get(chave=chave)
    assert (movimentacao.operador_emprestimo_id, movimentacao.vinculo_emprestimo_id) == (vinculo_operador.id, vinculo.id)
