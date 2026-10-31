import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_lista_publica_exibe_boletins_gerados(client, criar_documento, criar_boletim_programado):
    criar_documento()
    boletim_programado = criar_boletim_programado()

    resposta = client.get(reverse('boletim_servico:boletins_publicos'))

    assert resposta.status_code == 200
    assert 'Boletins de Serviço do Período' in resposta.content.decode()
    assert boletim_programado.boletimdiario_set.count() == 1
