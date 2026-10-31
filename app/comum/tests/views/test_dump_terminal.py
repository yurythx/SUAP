"""Tabela de pessoas que o terminal legado baixa (``comum.views.obter_query``, via ``get_dump_pessoas``).

A rota em si (zip, cache em disco, ``MaquinaLog``) é coberta pelo e2e em
``comum/tests/e2e/test_webservices_terminal.py``; aqui o alvo é o conteúdo de uma linha: a coluna
``operador_cadastro``, que o terminal usa para liberar a tela de cadastro de digitais.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import connection

from comum.tests.factories import PrestadorServicoFactory
from comum.views import obter_query
from edu.tests.factories import AlunoFactory, CursoCampusFactory, DiretoriaFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def _operador_cadastro_no_dump(servidor: Servidor) -> bool:
    """Monta a tabela do dump para uma matrícula (como a view faz) e lê a coluna ``operador_cadastro``."""
    with connection.cursor() as cursor:
        cursor.execute(obter_query(None, servidor.matricula, servidor.setor.uo_id))
        cursor.execute('SELECT operador_cadastro FROM tabela_terminal_ponto WHERE username = %s', [servidor.matricula])
        ((operador_cadastro,),) = cursor.fetchall()
    return operador_cadastro


@pytest.mark.parametrize(('digital_fraca', 'esperado'), [(False, True), (True, False)], ids=['digital_boa', 'digital_fraca'])
def test_operador_de_cadastro_com_digital_fraca_nao_sai_como_operador(sync_permissions, digital_fraca, esperado):
    """No terminal legado, quem tem digital fraca entra por senha local nunca conferida com o SUAP (#17482)."""
    grupo = Group.objects.create(name='Operador de cadastro de digitais (teste)')
    grupo.permissions.add(Permission.objects.get(codename='pode_cadastrar_digital'))
    servidor = ServidorFactory(pessoa_fisica__tem_digital_fraca=digital_fraca)
    servidor.get_user().groups.add(grupo)

    assert _operador_cadastro_no_dump(servidor) is esperado


def test_pessoa_com_varios_vinculos_tem_uma_linha_por_vinculo(sync_permissions):
    """Após a deduplicação, servidor, prestador e aluno são a mesma PF: cada vínculo é uma linha, com id ``-vinculo.id``.

    O id é a chave primária da tabela do terminal; com o da PF, só uma matrícula sobrevivia e a pessoa
    não batia ponto pelas outras.
    """
    servidor = ServidorFactory(pessoa_fisica__template=b'DIGITAL')  # prestador só sai no dump com digital
    prestador = PrestadorServicoFactory(pessoa_fisica=servidor.pessoa_fisica, setor=servidor.setor)
    aluno = AlunoFactory(pessoa_fisica=servidor.pessoa_fisica, curso_campus=CursoCampusFactory(diretoria=DiretoriaFactory(setor=servidor.setor)))
    prestador.refresh_from_db()

    with connection.cursor() as cursor:
        cursor.execute(obter_query('1.3.1', None, servidor.setor.uo_id))
        cursor.execute(
            'SELECT id, username, pode_bater_ponto FROM tabela_terminal_ponto WHERE username = ANY(%s)',
            [[servidor.matricula, prestador.matricula, aluno.matricula]],
        )
        linhas = set(cursor.fetchall())

    assert linhas == {
        (-servidor.get_vinculo().id, servidor.matricula, True),
        (-prestador.get_vinculo().id, prestador.matricula, True),
        (-aluno.get_vinculo().id, aluno.matricula, False),
    }
