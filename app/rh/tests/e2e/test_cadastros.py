# ruff: noqa: UP032
"""Cadastros básicos RH: criação de instituição e função seguida de histórico real do servidor.

Feature RH serve como referência de campos; cada teste monta nome único e afirma persistência.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import uuid4

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_instituicao_criar_editar(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import Instituicao

    nome = 'Instituição RH ' + uuid4().hex[:10]
    tela.ir('/admin/rh/instituicao/add/')
    tela.preencher_formulario([('Instituição', 'texto', nome), ('Unidade Gestora', 'texto', '222222'), ('UASG', 'texto', '222222')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert Instituicao.objects.filter(nome=nome, unidade_gestora=222222, uasg=222222).exists()
    instituicao = Instituicao.objects.get(nome=nome)
    tela.ir('/admin/rh/instituicao/{}/change/'.format(instituicao.pk))
    tela.preencher('Instituição', 'texto', nome + ' editada')
    tela.clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')
    assert Instituicao.objects.filter(pk=instituicao.pk, nome=nome + ' editada').exists()


def test_funcao_e_historico(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('admin'))
    from rh.models import Funcao, ServidorFuncaoHistorico
    from rh.tests.factories import ServidorFactory

    nome = 'SUB-' + uuid4().hex[:6]
    servidor = ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), pessoa_fisica__nome='Histórico RH ' + nome, setor=rh_seed['setor'])
    tela.ir('/admin/rh/funcao/add/')
    tela.preencher_formulario(
        [('Codigo', 'texto', nome), ('Nome', 'texto', nome), ('Função SUAP', 'checkbox', 'marcar'), ('Função SIAPE', 'checkbox', 'desmarcar')]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert Funcao.objects.filter(codigo=nome, funcao_suap=True, funcao_siape=False).exists()
    tela.ir('/admin/rh/servidorfuncaohistorico/add/')
    tela.preencher_formulario(
        [
            ('Servidor', 'autocomplete', servidor.matricula),
            ('Data Início na Função', 'data', date.today().strftime('%d/%m/%Y')),
            ('Função', 'lista', nome),
            ('Setor SIAPE', 'autocomplete', rh_seed['siape'].sigla),
            ('Setor SUAP', 'autocomplete', rh_seed['setor'].sigla),
            ('Nome Amigável da Função', 'texto', nome),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert ServidorFuncaoHistorico.objects.filter(servidor=servidor, funcao__codigo=nome, nome_amigavel=nome).exists()
