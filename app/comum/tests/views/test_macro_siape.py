"""Macros SIAPE (``/comum/baixar_macro_siape/`` e ``/comum/baixar_macro_siape_personalizavel/``).

A macro é um template compilado com a UF e o código da instituição da ``Configuracao`` (#17394):

* a de PCA sem documento legal interpolava ``{{codigo_instituicao}}``, chave que a view não
  passa, e saía com ``ps[enter]`` — o operador digitava ``ps`` sem código de instituição;
* sem a UF configurada, ``.lower()`` estourava no ``None`` antes do guard, e a tela dava 500 em
  vez da mensagem pedindo a configuração.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from comum.models import Configuracao
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

MACRO_COMPLETA = '/comum/baixar_macro_siape/'
MACRO_PERSONALIZAVEL = '/comum/baixar_macro_siape_personalizavel/'


@pytest.fixture
def gestor_extracao(client: Client, sync_permissions) -> Client:
    servidor = ServidorFactory()
    servidor.get_user().groups.add(Group.objects.get(name='Gerenciador de Extração SIAPE'))
    client.force_login(servidor.get_user())
    return client


def _configurar(**valores: str) -> None:
    Configuracao.clear_cache()
    for chave, valor in valores.items():
        Configuracao.objects.create(app='comum', chave=chave, valor=valor, descricao=chave)


def test_macro_de_pca_sem_documento_legal_digita_o_codigo_da_instituicao(gestor_extracao: Client) -> None:
    _configurar(instituicao_estado='RN', instituicao_identificador='26435')

    resposta = gestor_extracao.get(MACRO_COMPLETA, {'extracao_sem_posicionamentos_que_estejam_sem_documento_legal': '1'})

    assert resposta.status_code == 200
    assert b'value="ps26435[enter]"' in resposta.content


@pytest.mark.parametrize(
    ('metodo', 'rota', 'dados'),
    [
        ('get', MACRO_COMPLETA, {}),
        ('post', MACRO_PERSONALIZAVEL, {'arquivos_extrator': ['unidadeorganizacional']}),
    ],
    ids=['completa', 'personalizavel'],
)
def test_sem_uf_configurada_pede_a_configuracao_em_vez_de_500(gestor_extracao: Client, metodo: str, rota: str, dados: dict) -> None:
    _configurar(instituicao_identificador='26435')

    resposta = getattr(gestor_extracao, metodo)(rota, dados)

    assert resposta.status_code == 200
    assert 'Defina' in resposta.content.decode()
    assert 'attachment' not in resposta.get('Content-Disposition', '')
