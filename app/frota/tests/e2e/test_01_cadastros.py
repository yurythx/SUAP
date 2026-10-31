"""Fluxo: cadastros de apoio do frota — viatura e motorista temporário (modo 2).

Sem viatura não há o que agendar, e sem motorista temporário a avaliação do agendamento não
tem quem indicar. São dois cadastros de `ModelAdminPlus`, cada um com um grupo diferente, e é
deles que a cadeia agendamento → avaliação → saída → chegada depende.
"""

import pytest

from djtools.e2e_ui import Tela
from frota.tests.e2e.seed import PATRIMONIO

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VIATURAS = '/admin/frota/viatura/'
RELATORIO_MOTORISTAS = '/frota/relatorio_motoristas_temporarios/'


def test_cadastro_de_viatura(logado_frota):
    """O Coordenador de Frota cadastra uma viatura com os campos que a tela exige.

    `Patrimônio` é o autocomplete que o seed alimenta (número ``PATRIMONIO``, via `almoxarifado` →
    `patrimonio`). O resto (marca/modelo/cor/combustível) vem dos cadastros do app
    `estacionamento` que o replay do seed cria — é por isso que a viatura é o primeiro elo.
    """
    from frota.models import Viatura

    tela = Tela(logado_frota('coord_frota')).ir(VIATURAS)
    tela.ver_botao('Adicionar Viatura').clicar_botao('Adicionar Viatura')
    tela.preencher_formulario(
        [
            ('Patrimônio', 'Autocomplete', str(PATRIMONIO)),
            ('Grupo', 'Lista', 'Carro de Passeio'),
            ('Modelo', 'Autocomplete', 'Ranger'),
            ('Cor', 'Autocomplete', 'Branca'),
            ('Ano', 'Texto', '2012'),
            ('Placa', 'Texto', 'MXY-0001'),
            ('Lotação', 'Texto', '5'),
            ('Odômetro', 'Texto', '10000'),
            ('Chassi', 'Texto', '11111111111111111'),
            ('Renavam', 'Texto', '999999999'),
            ('Potência', 'Texto', '140'),
            ('Cilindrada', 'Texto', '1400'),
            ('Combustíveis', 'checkbox multiplo', 'Gasolina'),
            ('Tanque', 'Texto', '50'),
            ('Rendimento Estimado', 'Texto', '10'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    viatura = Viatura.objects.filter(patrimonio__numero=PATRIMONIO).order_by('-id').first()
    assert viatura is not None, 'a UI disse que salvou, mas a viatura não persistiu'


def test_cadastro_de_motorista_temporario(logado_frota):
    """O Coordenador de Frota cadastra o motorista temporário.

    A `Pessoa` é o servidor 107005 (Motorista Frota), que o seed cria no grupo `Servidor` —
    é ele que a avaliação do agendamento oferece em "Motoristas Disponíveis".
    """
    from frota.models import MotoristaTemporario

    tela = Tela(logado_frota('coord_frota')).ir(RELATORIO_MOTORISTAS)
    tela.ver_botao('Adicionar Motorista').clicar_botao('Adicionar Motorista')
    tela.preencher_formulario(
        [
            ('Pessoa', 'Autocomplete', '107005'),
            ('Portaria', 'Texto', '1234'),
            ('Ano da Portaria', 'Texto', '2018'),
            ('Data Inicial', 'Data', '01/01/2018'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert MotoristaTemporario.objects.filter(vinculo_pessoa__user__username='107005').exists(), (
        'a UI disse que salvou, mas o motorista temporário não persistiu'
    )

    tela.ir(RELATORIO_MOTORISTAS)
    tela.filtros().preencher_formulario(
        [
            ('Campus', 'Lista', 'CZN'),
            ('Categoria', 'Lista', 'Servidor'),
            ('Disponibilidade', 'Lista', 'Todos'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.linha('Motorista Frota')
