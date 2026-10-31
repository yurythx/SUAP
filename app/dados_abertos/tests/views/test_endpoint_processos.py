"""Testes do endpoint público de processos dos dados abertos."""

import pytest

from processo_eletronico.models import Processo
from processo_eletronico.tests.factories import ProcessoFactory
from rh.tests.factories import ServidorFactory, SetorFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_processos_publica_o_numero_de_protocolo_fisico(client):
    # O NUP é gerado no save a partir do código SIORG do setor de criação.
    setor = SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))
    usuario = ServidorFactory(setor=setor).get_user()
    processo = ProcessoFactory(setor_criacao=setor, usuario_gerador=usuario)
    Processo.objects.filter(pk=processo.pk).update(numero_protocolo_fisico='23000.000001/2026-11')
    # Recém-criado: o número físico só é gerado num save posterior, e o processo sai com número nulo
    # em vez de derrubar a listagem inteira na validação da resposta.
    ProcessoFactory(setor_criacao=setor, usuario_gerador=usuario)

    resposta = client.get('/dados_abertos/api/processo/processos/')

    assert resposta.status_code == 200
    assert sorted([p['numero'] for p in resposta.json()['results']], key=str) == ['23000.000001/2026-11', None]
