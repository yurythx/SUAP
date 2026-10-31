"""Dumps que o terminal de refeitório baixa (``/ae/get_pessoas/`` e ``/ae/get_config_refeicao/``).

São webservices anônimos, autorizados só pelo IP de uma ``ponto.Maquina`` ativa com
``cliente_refeitorio``. O ``get_pessoas`` entrega a tabela de alunos, servidores e prestadores
com as digitais. O que se afirma aqui é a auditoria: todo dump servido deixa um ``MaquinaLog``
de quem baixou (#17450). O ``REMOTE_ADDR`` é explícito e fora do ``127.0.0.1``, que o e2e do
``comum`` cadastra como máquina ativa (ver ``comum/tests/views/test_webservice.py``).
"""

from __future__ import annotations

import io
import xmlrpc.client
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from ae.models import DemandaAluno, DemandaAlunoAtendida
from ae.tests.factories import DemandaAlunoFactory
from edu.tests.factories import AlunoFactory, CursoCampusFactory, DiretoriaFactory
from ponto.models import MaquinaLog
from ponto.tests.factories import MaquinaFactory
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

IP_TERMINAL = '10.99.0.41'
IP_DESCONHECIDO = '10.99.0.202'


@pytest.mark.parametrize(
    ('rota', 'operacao'),
    [('/ae/get_pessoas/', 'ae_get_pessoas'), ('/ae/get_config_refeicao/', 'ae_get_config_refeicao')],
    ids=['pessoas', 'config_refeicao'],
)
def test_dump_do_refeitorio_registra_o_acesso_da_maquina(client: Client, settings: Any, tmp_path: Path, rota: str, operacao: str) -> None:
    settings.TEMP_DIR = str(tmp_path)
    maquina = MaquinaFactory(ip=IP_TERMINAL, cliente_refeitorio=True, uo=SetorFactory().uo)

    resposta = client.get(rota, REMOTE_ADDR=IP_TERMINAL)
    recusa = client.get(rota, REMOTE_ADDR=IP_DESCONHECIDO)

    assert resposta.status_code == 200
    assert resposta['Content-Type'] == 'application/zip'
    assert recusa.status_code == 403
    assert MaquinaLog.objects.filter(maquina=maquina, operacao=operacao).count() == 1


def test_dump_tem_uma_linha_por_matricula_da_mesma_pessoa(client: Client, settings: Any, tmp_path: Path) -> None:
    """Após a deduplicação, duas matrículas ativas no campus são a mesma PF.

    O id é a chave primária da tabela do terminal: repetido, a importação inteira falhava. Com
    ``-vinculo.id`` cada matrícula é uma linha.
    """
    settings.TEMP_DIR = str(tmp_path)
    setor = SetorFactory()
    MaquinaFactory(ip=IP_TERMINAL, cliente_refeitorio=True, uo=setor.uo)
    curso = CursoCampusFactory(diretoria=DiretoriaFactory(setor=setor))
    aluno = AlunoFactory(curso_campus=curso)
    outra_matricula = AlunoFactory(curso_campus=curso, pessoa_fisica=aluno.pessoa_fisica)

    resposta = client.get('/ae/get_pessoas/1.3.1/', REMOTE_ADDR=IP_TERMINAL)

    with zipfile.ZipFile(io.BytesIO(resposta.content)) as dump:
        linhas = [linha.split('\t') for linha in dump.read('tabela_terminal_refeitorio.copy').decode().splitlines()]
    assert {(int(id_), username) for id_, username, *_ in linhas} == {
        (-aluno.get_vinculo().id, aluno.matricula),
        (-outra_matricula.get_vinculo().id, outra_matricula.matricula),
    }


def test_refeicao_exportada_pelo_terminal_fica_no_vinculo_do_operador(client: Client, sync_permissions: None) -> None:
    """O terminal exporta as refeições com o id do operador na sua tabela ``pessoa``: ``-vinculo.id``."""
    MaquinaFactory(ip=IP_TERMINAL, cliente_refeitorio=True, uo=SetorFactory().uo)
    for demanda in (DemandaAluno.CAFE, DemandaAluno.ALMOCO, DemandaAluno.JANTAR):
        DemandaAlunoFactory(id=demanda)
    vinculo_operador = ServidorFactory().get_vinculo()
    aluno = AlunoFactory()

    envelope = xmlrpc.client.dumps((f'{aluno.matricula};2026-10-19 12:00:00', -vinculo_operador.id), methodname='registrar_refeicoes_offline')
    retorno = client.post('/webservice/', data=envelope, content_type='text/xml', REMOTE_ADDR=IP_TERMINAL)

    assert xmlrpc.client.loads(retorno.content)[0][0] == {'ok': True, 'usernames_erro': ''}
    atendimento = DemandaAlunoAtendida.objects.get(aluno=aluno)
    assert (atendimento.demanda_id, atendimento.responsavel_vinculo) == (DemandaAluno.ALMOCO, vinculo_operador)
