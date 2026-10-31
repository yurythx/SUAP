"""Fluxo: solicitação e avaliação do agendamento de viagem (modo 2).

É a transição de estado central do frota: o Agendador de Frota pede a viagem, e o Coordenador
de Frota a **defere** escolhendo viatura e motoristas. Sem o deferimento não há viagem, e é ele
que as telas de "Registrar Saída"/"Registrar Chegada" leem.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AGENDAMENTOS = '/admin/frota/viagemagendamento/'
AGENDAMENTO_FORM = '/admin/frota/viagemagendamento/add/'


def _agendamento():
    from frota.models import ViagemAgendamento

    ag = ViagemAgendamento.objects.order_by('-id').first()
    assert ag is not None, 'agendamento ausente: a cadeia é sequencial, rode `pytest frota/tests/e2e` inteiro'
    return ag


def test_solicitacao_de_agendamento(logado_frota):
    """O Agendador de Frota solicita a viagem.

    A data da saída (03/12) é **futura** em relação ao relógio da sessão (25/11) — é o que faz o
    agendamento nascer na fila de "Agendamentos Futuros", onde a avaliação o alcança.
    """
    from frota.models import ViagemAgendamento

    tela = Tela(logado_frota('agendador')).ir(AGENDAMENTOS)
    tela.ver_botao('Adicionar Agendamento de Viagem').clicar_botao('Adicionar Agendamento de Viagem')
    tela.preencher_formulario(
        [
            ('Objetivo', 'TextArea', 'objetivo da viagem'),
            ('Itinerário', 'TextArea', 'trajeto a ser percorrido'),
            ('Saída', 'Data', '03/12/2018'),
            ('Chegada', 'Data', '04/12/2018'),
            ('Nome do Responsável', 'Texto', 'Nome do Servidor 1'),
            ('Telefone do Responsável', 'Texto', '(84) 12345-6789'),
            ('Passageiros', 'Autocomplete Multiplo', '107004'),
            ('Local de Saída', 'Texto', 'local de saída da viatura'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    ag = ViagemAgendamento.objects.order_by('-id').first()
    assert ag is not None, 'a UI disse que salvou, mas o agendamento não persistiu'
    assert ag.objetivo == 'objetivo da viagem'


def test_avaliacao_do_agendamento(logado_frota):
    """O Coordenador de Frota defere o agendamento, escolhendo viatura e motoristas.

    A viatura vem do cadastro de `test_01_cadastros.py` (placa `MXY-0001`, modelo Ranger) e o
    motorista é o temporário cadastrado lá — a asserção do ORM cobre exatamente esse vínculo,
    que a mensagem de sucesso não prova.
    """
    from frota.models import ViagemAgendamento

    ag = _agendamento()

    tela = Tela(logado_frota('coord_frota')).ir(AGENDAMENTOS)
    tela.clicar_aba('Agendamentos Futuros')
    tela.linha('Agendador Frota').clicar_botao('Avaliar')
    tela.preencher_formulario(
        [
            ('Situação', 'Lista', 'Deferida'),
            ('Viaturas Disponíveis', 'Lista', 'MXY-0001 Ford Ranger'),
            ('Motoristas Disponíveis', 'FilteredSelectMultiple', 'Motorista Frota (107005) (Servidor)'),
            ('Observações', 'TextArea', 'Observações sobre o agendamento'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Agendamento avaliado com sucesso.')
    ag.refresh_from_db()
    assert ag.status == 'Deferida', f'a UI disse que avaliou, mas o status ficou {ag.status!r}'
