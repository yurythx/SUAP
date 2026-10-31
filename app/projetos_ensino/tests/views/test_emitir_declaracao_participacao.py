"""Emissão da declaração de participação (documento com CPF/RG do participante)."""

import pytest
from django.contrib.messages import get_messages

from projetos_ensino.models import Participacao
from projetos_ensino.tests.conftest import _login, set_periodo_execucao
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db(databases='__all__')
def test_so_quem_a_tela_oferece_emite_a_declaracao(client, usuarios, projeto_aprovado):
    """Servidor sem relação com o projeto não emite a declaração de outro participante (#17554)."""
    projeto = projeto_aprovado
    set_periodo_execucao(projeto.edital)
    participacao = Participacao.objects.filter(projeto=projeto, vinculo_pessoa__isnull=False).first()
    url = f'/projetos_ensino/emitir_declaracao_participacao_pdf/{participacao.pk}/'

    _login(client, ServidorFactory())
    resposta = client.get(url)
    assert resposta.status_code == 302
    assert resposta['Location'] == '/'
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == ['Você não tem permissão para ver isso.']

    _login(client, usuarios.coordenador)
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert 'Declaramos para os devidos fins' in resposta.content.decode()
