"""Capturas do guia de usuário do frota.

A cadeia é sequencial — viatura → motorista temporário → agendamento → deferimento → saída →
chegada —, como no e2e do módulo: o agendamento precisa da viatura e do motorista que o
deferimento oferece, e a viagem nasce de um agendamento deferido. Os campos, os rótulos e as
mensagens são os mesmos que o e2e exercita; o que muda aqui é o `capturar` por tela e a
unidade, que é a tarefa do usuário, não a rota.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela, adicionar_ao_filteredselect, anotar_tela
from frota.tests.e2e.seed import PATRIMONIO

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VIATURAS = '/admin/frota/viatura/'
MOTORISTAS = '/frota/relatorio_motoristas_temporarios/'
AGENDAMENTOS = '/admin/frota/viagemagendamento/'
VIAGENS_AGENDADAS = '/frota/viagens_agendadas/'
VIAGENS_INICIADAS = '/frota/viagens_iniciadas/'


def _viatura():
    from frota.models import Viatura

    viatura = Viatura.objects.filter(patrimonio__numero=PATRIMONIO).order_by('-id').first()
    assert viatura is not None, 'viatura ausente: a cadeia é sequencial, rode o arquivo inteiro'
    return viatura


def test_cadastros_de_viatura_e_motorista_temporario(logado_frota, capturar):
    """Tarefa 1 e tarefa 2: a viatura que tudo consome e o motorista que a avaliação oferece."""
    from frota.models import MotoristaTemporario

    tela = Tela(logado_frota('coord_frota')).ir(VIATURAS)
    tela.ver_botao('Adicionar Viatura')
    anotar_tela('viaturas-listagem', tela)
    capturar(tela.pagina, 'viaturas-listagem')
    tela.clicar_botao('Adicionar Viatura')
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
    anotar_tela('viatura-formulario', tela)
    capturar(tela.pagina, 'viatura-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    detalhe = tela.ir(f'/frota/viatura/{_viatura().pk}/')
    anotar_tela('viatura-detalhe', detalhe)
    capturar(detalhe.pagina, 'viatura-detalhe')

    tela = Tela(logado_frota('coord_frota')).ir(MOTORISTAS)
    tela.ver_item_de_menu('Administração::Frota::Motoristas Temporários')
    tela.ver_botao('Adicionar Motorista')
    anotar_tela('motoristas-listagem', tela)
    capturar(tela.pagina, 'motoristas-listagem')
    tela.clicar_botao('Adicionar Motorista')
    tela.preencher_formulario(
        [
            ('Pessoa', 'Autocomplete', '107005'),
            ('Portaria', 'Texto', '1234'),
            ('Ano da Portaria', 'Texto', '2018'),
            ('Data Inicial', 'Data', '01/01/2018'),
        ]
    )
    anotar_tela('motorista-formulario', tela)
    capturar(tela.pagina, 'motorista-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert MotoristaTemporario.objects.filter(vinculo_pessoa__user__username='107005').exists()

    tela.ir(MOTORISTAS)
    tela.filtros().preencher_formulario(
        [
            ('Campus', 'Lista', 'CZN'),
            ('Categoria', 'Lista', 'Servidor'),
            ('Disponibilidade', 'Lista', 'Todos'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.linha('Motorista Frota')
    capturar(tela.pagina, 'motoristas-resultado')


def test_agendamento_e_avaliacao_da_viagem(logado_frota, capturar):
    """Tarefa 3 e tarefa 4: o Agendador pede a viagem e o Coordenador a defere."""
    from frota.models import ViagemAgendamento

    tela = Tela(logado_frota('agendador')).ir(AGENDAMENTOS)
    tela.ver_botao('Adicionar Agendamento de Viagem')
    anotar_tela('agendamentos-listagem', tela)
    capturar(tela.pagina, 'agendamentos-listagem')
    tela.clicar_botao('Adicionar Agendamento de Viagem')
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
    anotar_tela('agendamento-formulario', tela)
    capturar(tela.pagina, 'agendamento-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    agendamento = ViagemAgendamento.objects.order_by('-id').first()
    assert agendamento is not None

    tela = Tela(logado_frota('coord_frota')).ir(AGENDAMENTOS)
    tela.clicar_aba('Agendamentos Futuros')
    anotar_tela('agendamentos-futuros', tela)
    capturar(tela.pagina, 'agendamentos-futuros')
    tela.linha('Agendador Frota').clicar_botao('Avaliar')
    tela.preencher_formulario(
        [
            ('Situação', 'Lista', 'Deferida'),
            ('Viaturas Disponíveis', 'Lista', 'MXY-0001 Ford Ranger'),
            ('Observações', 'TextArea', 'Observações sobre o agendamento'),
        ]
    )
    # O rótulo "Motoristas Disponíveis:" fica fora do `div.selector`, então o campo é
    # endereçado pelo `id` da caixa "Disponíveis"; quem envia o valor é a caixa "Escolhido(S)".
    adicionar_ao_filteredselect(tela.pagina, 'id_motoristas_from', 'Motorista Frota (107005) (Servidor)')
    anotar_tela('agendamento-avaliacao', tela)
    capturar(tela.pagina, 'agendamento-avaliacao')
    tela.clicar_botao('Salvar').sucesso('Agendamento avaliado com sucesso.')
    agendamento.refresh_from_db()
    assert agendamento.status == 'Deferida'


def test_saida_e_chegada_da_viagem(logado_frota, capturar):
    """Tarefa 5: com o agendamento deferido, registra-se a saída e, depois, a chegada."""
    from frota.models import Viagem

    tela = Tela(logado_frota('coord_sistemico')).ir(VIAGENS_AGENDADAS)
    tela.ver_item_de_menu('Administração::Frota::Viagens::Registrar Saída')
    tela.ver_botao('Registrar Saída')
    capturar(tela.pagina, 'viagens-agendadas')
    tela.clicar_link('Todas as Viaturas')
    tela.esperar().linha('Agendador Frota').clicar_botao('Registrar Saída')
    tela.preencher_formulario(
        [
            ('Data e Hora', 'Data', '03/12/2018'),
            ('Viatura', 'Lista', 'MXY-0001 Ford Ranger'),
            ('Odômetro', 'Texto', '10000'),
        ]
    )
    anotar_tela('viagem-saida-formulario', tela)
    capturar(tela.pagina, 'viagem-saida-formulario')
    tela.clicar_botao('Salvar').sucesso('Viagem iniciada com sucesso.')
    viagem = Viagem.objects.order_by('-id').first()
    assert viagem is not None
    assert viagem.saida_odometro is not None

    tela = Tela(logado_frota('coord_sistemico')).ir(VIAGENS_INICIADAS)
    capturar(tela.pagina, 'viagens-iniciadas')
    tela.clicar_link('Todas as Viaturas')
    tela.esperar().linha('Agendador Frota').clicar_botao('Registrar Chegada')
    tela.preencher_formulario(
        [
            ('Data e Hora', 'Data', '04/12/2018'),
            ('Odômetro', 'Texto', '10100'),
        ]
    )
    anotar_tela('viagem-chegada-formulario', tela)
    capturar(tela.pagina, 'viagem-chegada-formulario')
    tela.clicar_botao('Salvar').sucesso('Viagem finalizada com sucesso.')
    viagem.refresh_from_db()
    assert viagem.chegada_odometro is not None

    detalhe = tela.ir(f'/frota/viagem/{viagem.pk}/')
    anotar_tela('viagem-detalhe', detalhe)
    capturar(detalhe.pagina, 'viagem-detalhe')


def test_abastecimento_servico_e_viagem_retroativa(logado_frota, capturar, tmp_path):
    """Tarefa 6 a 8: abastecimento, serviço/revisão da viatura e viagem sem agendamento."""
    from frota.models import ManutencaoViatura, ViaturaOrdemAbastecimento

    tela = Tela(logado_frota('coord_frota')).ir('/admin/frota/viaturaordemabastecimento/')
    anotar_tela('abastecimentos-listagem', tela)
    capturar(tela.pagina, 'abastecimentos-listagem')
    tela.ir('/admin/frota/viaturaordemabastecimento/add/')
    tela.preencher_formulario(
        [
            ('Data', 'data e hora', '20/11/2018 10:00'),
            ('Viatura', 'lista', 'MXY-0001 Ford Ranger'),
            ('Combustível', 'lista', 'Gasolina'),
            ('Odômetro', 'número', '10000'),
            ('Quantidade', 'texto', '40,00'),
            ('Valor Total da Nota Fiscal (R$)', 'texto', '200,00'),
            ('Cupom Fiscal', 'texto', '1234'),
        ]
    )
    anotar_tela('abastecimento-formulario', tela)
    capturar(tela.pagina, 'abastecimento-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert ViaturaOrdemAbastecimento.objects.exists()

    # A nota fiscal dos serviços é obrigatória no registro do serviço (é anexo, não texto).
    nota_fiscal = tmp_path / 'nota-fiscal-servicos.pdf'
    nota_fiscal.write_bytes(b'%PDF-1.4\n% nota fiscal dos servicos\n')

    tela = Tela(logado_frota('coord_frota')).ir('/admin/frota/manutencaoviatura/')
    anotar_tela('servicos-listagem', tela)
    capturar(tela.pagina, 'servicos-listagem')
    tela.ir('/admin/frota/manutencaoviatura/add/')
    tela.preencher_formulario(
        [
            ('Data', 'data', '20/11/2018'),
            ('Viatura', 'Autocomplete', 'MXY-0001', 'MXY-0001 Ford Ranger'),
            ('Odômetro', 'número', '10000'),
            ('Tipo de Serviço', 'lista', 'Manutenção Periódica'),
            ('Observação', 'textarea', 'Revisão dos 10.000 km'),
            ('Valor Total da Nota Fiscal de Peças (R$)', 'texto', '0,00'),
            ('Valor Total da Nota Fiscal de Serviços (R$)', 'texto', '0,00'),
            ('Nota Fiscal dos Serviços', 'arquivo', str(nota_fiscal)),
        ]
    )
    anotar_tela('servico-formulario', tela)
    capturar(tela.pagina, 'servico-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert ManutencaoViatura.objects.exists()

    tela = Tela(logado_frota('coord_sistemico')).ir('/frota/viagem_retroativa/')
    tela.preencher_formulario(
        [
            ('Solicitante', 'autocomplete', '107002'),
            ('Saída', 'data e hora', '20/11/2018 08:00'),
            ('Chegada', 'data e hora', '20/11/2018 18:00'),
            ('Objetivo', 'textarea', 'Viagem registrada depois de realizada'),
            ('Itinerário', 'textarea', 'Natal - Currais Novos - Natal'),
            ('Viatura', 'lista', 'MXY-0001 Ford Ranger'),
            ('Quilometragem Inicial', 'número', '10000'),
            ('Local de Saída', 'texto', 'Reitoria'),
            ('Quilometragem Final', 'número', '10300'),
            ('Passageiros', 'autocomplete multiplo', '107004'),
        ]
    )
    anotar_tela('viagem-retroativa-formulario', tela)
    capturar(tela.pagina, 'viagem-retroativa-formulario')
    # O submit deste formulário é "Enviar", e não "Salvar" como no resto do módulo.
    tela.clicar_botao('Enviar')
    tela.sucesso('cadastrada com sucesso.')
    capturar(tela.pagina, 'viagem-retroativa-resultado')
