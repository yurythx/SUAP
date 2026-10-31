"""Autocomplete de subobjetivos dos ODS da ONU (``/comum/get_subojetivos_ods_onu/``).

Quem consome é o par encadeado objetivo → subobjetivos dos formulários de projeto (``pesquisa`` e
``projetos``, ``projetoform.js``). Sem ``ids`` válidos a resposta é lista vazia, não "todos": é
autocomplete, e o próprio JS esvazia o campo quando nenhum objetivo está escolhido. Antes, sem
``ids`` o ``''.split(',')`` virava ``['']`` e o filtro estourava 500 (#17395).
"""

from __future__ import annotations

import pytest
from django.test import Client

from comum.tests.factories import SubobjetivoDesenvolvimentoSustentavelFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

ROTA = '/comum/get_subojetivos_ods_onu/'
# Servidor, não ``UserFactory``: usuário sem vínculo é redirecionado para ``/`` antes da view.


@pytest.mark.parametrize('query', [{}, {'ids': ''}, {'ids': ',,abc'}], ids=['ausente', 'vazio', 'lixo'])
def test_sem_ids_validos_devolve_lista_vazia(client: Client, sync_permissions, query: dict[str, str]) -> None:
    """Sem objetivo escolhido não há o que oferecer: 200 e ``results`` vazio."""
    SubobjetivoDesenvolvimentoSustentavelFactory()
    client.force_login(ServidorFactory().get_user())

    resposta = client.get(ROTA, query)

    assert resposta.status_code == 200, f'o autocomplete respondeu HTTP {resposta.status_code}'
    assert resposta.json() == {'results': []}


def test_filtra_pelo_objetivo_escolhido(client: Client, sync_permissions) -> None:
    """Só volta o subobjetivo do objetivo pedido; o do outro objetivo é o contraexemplo."""
    escolhido = SubobjetivoDesenvolvimentoSustentavelFactory()
    ignorado = SubobjetivoDesenvolvimentoSustentavelFactory()
    client.force_login(ServidorFactory().get_user())

    resposta = client.get(ROTA, {'ids': f'{escolhido.objetivo_id},,abc'})

    assert resposta.status_code == 200
    devolvidos = [item['id'] for item in resposta.json()['results']]
    assert devolvidos == [escolhido.pk], f'esperava só o subobjetivo do objetivo escolhido (sem {ignorado.pk}): {devolvidos}'
