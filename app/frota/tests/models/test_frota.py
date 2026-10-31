"""Testes de fluxo da Frota.

Os testes estão agrupados numa única classe por coesão do fluxo; o cenário é
montado pelas fixtures do `conftest.py`, que constroem só o que cada teste usa.

Cada método cobre uma etapa do ciclo de vida de uma viagem do ponto de vista do
usuário (formulário/endpoint real), e não os métodos internos dos modelos. As
pré-condições de cada etapa vêm de fixtures (ver `conftest.py`), de modo que os
testes são independentes entre si.
"""

import pytest

from comum.pytest_fixtures import assert_no_validation_errors, assert_redirects
from frota.models import MotoristaTemporario, Viagem, ViagemAgendamento, ViagemAgendamentoResposta, Viatura
from frota.tests.conftest import CHEGADA, SAIDA


@pytest.mark.django_db(databases='__all__')
class TestFluxoFrota:
    # --- Cadastros básicos -------------------------------------------------

    def test_cadastrar_viatura(self, cliente, catalogo, patrimonio):
        """O coordenador cadastra uma viatura pelo admin e ela passa a existir."""
        dados = {
            'modelo': catalogo.modelo.pk,
            'cor': catalogo.cor.pk,
            'ano_fabric': '2012',
            'placa_municipio_atual': catalogo.municipio.pk,
            'placa_codigo_atual': 'ABC-1234',
            'placa_municipio_anterior': catalogo.municipio.pk,
            'placa_codigo_anterior': 'ABC-1234',
            'lotacao': '10',
            'odometro': '1000',
            'capacidade_tanque': '150',
            'capacidade_gnv': '',
            'chassi': '11111111111111234',
            'renavam': '00000001234',
            'potencia': '2',
            'cilindrada': '0',
            'obs': 'Nenhuma observação',
            'grupo': catalogo.grupo.pk,
            'patrimonio': patrimonio.pk,
            'status': catalogo.status_ativa.pk,
            'combustiveis': catalogo.combustivel.pk,
            'rendimento_estimado': '9',
            'prazo_revisao': 6,
            'quantidade_km_revisao': 10000,
            'ativo': True,
        }

        resposta = cliente.post('/admin/frota/viatura/add/', dados)

        assert_no_validation_errors(resposta)
        assert Viatura.objects.filter(placa_codigo_atual='ABC-1234').exists()

    def test_cadastrar_motorista_temporario(self, cliente, coordenador):
        """O coordenador habilita um servidor como motorista temporário."""
        vinculo = coordenador.vinculo
        dados = {
            'vinculo_pessoa': vinculo.pk,
            'portaria': '42',
            'ano_portaria': '2015',
            'validade_inicial': '01/02/2012',
            'obs': 'Nenhuma observação cadastrada',
        }

        resposta = cliente.post('/admin/frota/motoristatemporario/add/', dados)

        assert_no_validation_errors(resposta)
        assert MotoristaTemporario.objects.filter(vinculo_pessoa=vinculo, portaria='42').exists()

    def test_solicitar_agendamento_de_viagem(self, cliente, coordenador):
        """O coordenador registra uma solicitação de viagem, que nasce pendente."""
        solicitante = coordenador.vinculo
        dados = {
            'vinculo_solicitante': solicitante.pk,
            'objetivo': 'Apresentação dos módulos do SUAP',
            'intinerario': 'Ida para Caicó por Currais Novos',
            'data_saida': SAIDA.strftime('%d/%m/%Y'),
            'data_saida_time': '08:00:00',
            'data_chegada': CHEGADA.strftime('%d/%m/%Y'),
            'data_chegada_time': '18:00:00',
            'vinculos_passageiros': solicitante.pk,
            'local_saida': 'Saindo do CNAT',
            'nome_responsavel': 'Nome do Responsável',
            'telefone_responsavel': '(84) 12346-7898',
        }

        resposta = cliente.post('/admin/frota/viagemagendamento/add/', dados)

        assert_no_validation_errors(resposta)
        assert ViagemAgendamento.objects.filter(vinculo_solicitante=solicitante, status='Pendente').exists()

    # --- Fluxo da viagem ---------------------------------------------------

    def test_deferir_agendamento(self, cliente, agendamento, viatura, motorista):
        """Ao deferir, o agendamento reserva viatura e motorista e fica DEFERIDA."""
        dados = {
            'agendamento': agendamento.pk,
            'status': 'Deferida',
            'viatura': viatura.pk,
            'motoristas': motorista.pk,
            'local_saida': 'Saindo do CNAT',
            'obs': 'Deferido para teste',
        }

        resposta = cliente.post(f'/frota/avaliar_agendamento_viagem/{agendamento.pk}/', dados)

        assert_no_validation_errors(resposta)
        assert_redirects(resposta, '/admin/frota/viagemagendamento/')
        agendamento.refresh_from_db()
        assert agendamento.status == 'Deferida'
        avaliacao = ViagemAgendamentoResposta.objects.get(agendamento=agendamento)
        assert avaliacao.viatura == viatura
        assert motorista in avaliacao.motoristas.all()

    def test_indeferir_agendamento(self, cliente, agendamento):
        """Ao indeferir, o agendamento fica INDEFERIDA e nenhuma viatura é reservada."""
        dados = {
            'agendamento': agendamento.pk,
            'status': 'Indeferida',
            'obs': 'Sem viatura disponível no período.',
        }

        resposta = cliente.post(f'/frota/avaliar_agendamento_viagem/{agendamento.pk}/', dados)

        assert_no_validation_errors(resposta)
        assert_redirects(resposta, '/admin/frota/viagemagendamento/')
        agendamento.refresh_from_db()
        assert agendamento.status == 'Indeferida'
        assert ViagemAgendamentoResposta.objects.get(agendamento=agendamento).viatura is None

    def test_registrar_saida(self, cliente, agendamento_deferido, coordenador):
        """A partir de um agendamento deferido, registrar a saída cria a viagem."""
        cenario = agendamento_deferido
        dados = {
            'agendamento_resposta': cenario.resposta.pk,
            'viatura': cenario.viatura.pk,
            'motoristas': cenario.motorista.pk,
            'saida_odometro': '1000',
            'saida_data': SAIDA.strftime('%d/%m/%Y'),
            'saida_data_time': '08:00:00',
            'saida_obs': '',
            'vinculos_passageiros': coordenador.vinculo.pk,
        }

        resposta = cliente.post(f'/frota/saida_viagem/{cenario.resposta.pk}/', dados)

        assert_no_validation_errors(resposta)
        assert_redirects(resposta, '/frota/viagens_agendadas/')
        assert Viagem.objects.filter(agendamento_resposta=cenario.resposta).exists()

    def test_registrar_chegada(self, cliente, viagem_iniciada):
        """A partir de uma viagem iniciada, registrar a chegada a finaliza."""
        viagem = viagem_iniciada.viagem
        dados = {
            'chegada_odometro': '1100',
            'chegada_data': CHEGADA.strftime('%d/%m/%Y'),
            'chegada_data_time': '18:00:00',
        }

        resposta = cliente.post(f'/frota/chegada_viagem/{viagem.pk}/', dados)

        assert_no_validation_errors(resposta)
        assert_redirects(resposta, '/frota/viagens_iniciadas/')
        viagem.refresh_from_db()
        assert viagem.chegada_data is not None
