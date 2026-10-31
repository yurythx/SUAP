"""Inclusão de inscrição contemplada extraordinária (``adicionar_inscricao_contemplada_extraordinaria``).

A origem é o campus de lotação, como no processamento do resultado. O edital lista os campi pelas
UOs SUAP (ex.: ``SGA``), mas a lotação do servidor aponta para a UO SIAPE equivalente, cuja sigla em produção pode ser outra (``CSGA``, ``CCNAT``, ``CCAL``, ``CNC``).
"""

import datetime

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from remanejamento.conftest import _servidor_do_fluxo
from remanejamento.models import Inscricao, InscricaoContemplada
from remanejamento.tests.factories import EditalFactory
from rh.models import Setor
from rh.tests.factories import SetorFactory, SetorSiapeFactory, UnidadeOrganizacionalFactory

URL = '/remanejamento/adicionar_inscricao_contemplada_extraordinaria/{}/'


def _campus_com_uo_siape(sigla_suap: str, sigla_siape: str) -> tuple[Setor, Setor]:
    setor_suap = SetorFactory(sigla=sigla_suap)
    setor_siape = SetorSiapeFactory(sigla=sigla_siape)
    UnidadeOrganizacionalFactory(setor=setor_siape, sigla=sigla_siape, equivalente=setor_suap.uo, tipo=None)
    return setor_suap, Setor.objects.get(pk=setor_siape.pk)


def _inscricao_confirmada(edital, servidor) -> Inscricao:
    return Inscricao.objects.create(
        edital=edital,
        servidor=servidor,
        inicio_exercicio=servidor.data_inicio_exercicio_no_cargo,
        concurso_ingresso_eh_ifrn=True,
        classificacao_concurso=1,
        dou_numero=servidor.matricula,
        dou_data=datetime.date(2000, 2, 1),
        dou_pagina='1',
        dou_sessao='1',
        jornada_trabalho=servidor.jornada_trabalho,
        confirmada=True,
    )


def _cenario_permuta(servidor_coordenador):
    """Edital SGA/ZN com resultado já processado (a tela só abre quando existe alguma contemplada) e a
    inscrição de um servidor lotado na UO SIAPE ``CSGA`` e em exercício em ZN."""
    sga, csga = _campus_com_uo_siape('SGA', 'CSGA')
    zn, zn_siape = _campus_com_uo_siape('ZN', 'ZN')
    edital = EditalFactory()
    edital.campus.add(sga.uo, zn.uo)
    edital.coordenadores.add(servidor_coordenador.get_user())

    ja_contemplado = _servidor_do_fluxo(setor=SetorFactory(superior=zn), setor_lotacao=zn_siape, setor_exercicio=zn_siape)
    InscricaoContemplada.cadastrar(_inscricao_confirmada(edital, ja_contemplado), zn.uo, sga.uo, InscricaoContemplada.CONTEMPLADO, None)

    servidor = _servidor_do_fluxo(setor=SetorFactory(superior=sga), setor_lotacao=csga, setor_exercicio=zn_siape)
    return edital, _inscricao_confirmada(edital, servidor), sga.uo, zn.uo


def _incluir(coordenador, edital, inscricao, campus_origem, campus_destino):
    return coordenador.post(
        URL.format(edital.pk),
        {
            'inscricao': inscricao.pk,
            'campus_origem': campus_origem.pk,
            'campus_destino': campus_destino.pk,
            'justificativa': 'Permuta entre servidores.',
        },
    )


@pytest.mark.django_db
def test_campus_de_lotacao_siape_com_sigla_diferente_da_suap_e_aceito(coordenador, servidor_coordenador):
    edital, inscricao, sga, zn = _cenario_permuta(servidor_coordenador)

    resposta = _incluir(coordenador, edital, inscricao, campus_origem=sga, campus_destino=zn)

    assert_no_validation_errors(resposta)
    assert resposta.status_code == 302
    contemplada = InscricaoContemplada.objects.get(inscricao=inscricao)
    assert (contemplada.campus_origem_sigla_ajustado, contemplada.campus_destino_sigla_ajustado) == ('SGA', 'ZN')


@pytest.mark.django_db
def test_origem_diferente_da_lotacao_e_recusada_indicando_o_campus_correto(coordenador, servidor_coordenador):
    edital, inscricao, sga, zn = _cenario_permuta(servidor_coordenador)

    resposta = _incluir(coordenador, edital, inscricao, campus_origem=zn, campus_destino=sga)

    assert 'O campus de origem deve ser o campus de lotação do servidor: selecione SGA.' in resposta.content.decode()
    assert not InscricaoContemplada.objects.filter(inscricao=inscricao).exists()
