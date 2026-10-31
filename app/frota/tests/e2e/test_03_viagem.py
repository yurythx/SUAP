"""Fluxo: registro de saída e chegada da viagem (modo 2).

Com o agendamento deferido, o Coordenador de Frota Sistêmico registra a saída da viatura
(gerando a viagem) e, depois, a chegada. É o fecho do ciclo de vida do frota: agendamento →
viagem → viagem finalizada.
"""

import re

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VIAGENS_AGENDADAS = '/frota/viagens_agendadas/'
VIAGENS_INICIADAS = '/frota/viagens_iniciadas/'


def test_registro_da_saida(logado_frota):
    """O Coordenador Sistêmico registra a saída da viatura — nasce a viagem.

    A lista de "Viagens Agendadas" é recortada pela linha do solicitante ("Agendador Frota"), e
    o botão "Registrar Saída" é o que converte o agendamento deferido em viagem.
    """
    from frota.models import Viagem

    tela = Tela(logado_frota('coord_sistemico')).ir(VIAGENS_AGENDADAS)
    tela.clicar_link('Todas as Viaturas')
    expect(tela.pagina).to_have_url(re.compile(r'/frota/viagens_agendadas/\?all=1$'))
    tela.esperar().linha('Agendador Frota').clicar_botao('Registrar Saída')

    tela.preencher_formulario(
        [
            ('Data e Hora', 'Data', '03/12/2018'),
            ('Viatura', 'Lista', 'MXY-0001 Ford Ranger'),
            ('Odômetro', 'Texto', '10000'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Viagem iniciada com sucesso.')
    viagem = Viagem.objects.order_by('-id').first()
    assert viagem is not None, 'a UI disse que iniciou, mas a viagem não persistiu'
    assert viagem.saida_odometro is not None


def test_registro_da_chegada(logado_frota):
    """O Coordenador Sistêmico registra a chegada — a viagem é finalizada."""
    from frota.models import Viagem

    tela = Tela(logado_frota('coord_sistemico')).ir(VIAGENS_INICIADAS)
    tela.clicar_link('Todas as Viaturas')
    expect(tela.pagina).to_have_url(re.compile(r'/frota/viagens_iniciadas/\?all=1$'))
    tela.esperar().linha('Agendador Frota').clicar_botao('Registrar Chegada')

    tela.preencher_formulario(
        [
            ('Data e Hora', 'Data', '04/12/2018'),
            ('Odômetro', 'Texto', '10100'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Viagem finalizada com sucesso.')
    viagem = Viagem.objects.order_by('-id').first()
    assert viagem is not None, 'a UI disse que finalizou, mas a chegada não persistiu'
    assert viagem.chegada_odometro is not None
