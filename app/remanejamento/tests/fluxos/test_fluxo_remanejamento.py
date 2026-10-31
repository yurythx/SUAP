"""Testes de fluxo da Remoção Interna (remanejamento).

Cada teste cobre uma etapa do ponto de vista do usuário (endpoint real) e é
independente: as pré-condições vêm das fixtures em `conftest.py`, não de um
teste chamando o outro.

Fluxo: coordenador abre o edital -> servidor elegível enxerga o link e se
inscreve; servidor de cargo não contemplado não vê o link.
"""

from datetime import datetime, timedelta

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from remanejamento.conftest import SENHA
from remanejamento.models import Edital, Inscricao


@pytest.mark.django_db(databases='__all__')
class TestFluxoRemanejamento:
    def test_cadastrar_edital(self, coordenador, candidato, campus):
        """O coordenador abre um edital pelo admin e ele passa a existir."""
        inicio_inscricoes = datetime.now()
        fim_inscricoes = inicio_inscricoes + timedelta(days=7)
        inicio_resultados = fim_inscricoes + timedelta(days=1)
        dados = {
            'categoria': Edital.TAE,
            'titulo': 'Remoção Interna para Cargo X',
            'descricao': 'Descrição de Remoção Interna para cargo X',
            'inicio_inscricoes': inicio_inscricoes.strftime('%d/%m/%Y'),
            'inicio_inscricoes_time': '00:00',
            'fim_inscricoes': fim_inscricoes.strftime('%d/%m/%Y'),
            'fim_inscricoes_time': '00:00:00',
            'inicio_resultados': inicio_resultados.strftime('%d/%m/%Y'),
            'inicio_resultados_time': '00:00:00',
            'resultado_recursos': (inicio_resultados + timedelta(days=2)).strftime('%d/%m/%Y'),
            'resultado_recursos_time': '00:00:00',
            'data_resultado_parcial': (inicio_resultados + timedelta(days=3)).strftime('%d/%m/%Y'),
            'data_homologacao_resultado': (fim_inscricoes + timedelta(days=5)).strftime('%d/%m/%Y'),
            'fim_recursos': (fim_inscricoes + timedelta(days=1)).strftime('%d/%m/%Y'),
            'fim_recursos_time': '00:00:00',
            'chave_hash': 'uma_chave_hash',
            'cargos': [candidato.cargo_emprego.pk],
            'coordenadores': [candidato.get_user().pk],
            'campus': [campus.pk],
        }

        resposta = coordenador.post('/admin/remanejamento/edital/add/', dados)

        assert_no_validation_errors(resposta)
        assert Edital.objects.filter(titulo='Remoção Interna para Cargo X').exists()

    def test_servidor_elegivel_ve_o_link_de_inscricao(self, edital, candidato, servidor_de_outro_cargo, suap_client):
        """Servidor de cargo contemplado vê o convite; servidor de outro cargo, não."""
        suap_client.login(username=candidato.get_user().username, password=SENHA)
        alertas_elegivel = suap_client.get('/comum/index/meus_alertas/').content.decode()
        assert edital.get_url_inscrever() in alertas_elegivel

        suap_client.login(username=servidor_de_outro_cargo.get_user().username, password=SENHA)
        alertas_inelegivel = suap_client.get('/comum/index/meus_alertas/').content.decode()
        assert edital.get_url_inscrever() not in alertas_inelegivel

    def test_servidor_elegivel_se_inscreve(self, edital, candidato, campus, suap_client):
        """O servidor elegível realiza a inscrição no edital aberto."""
        suap_client.login(username=candidato.get_user().username, password=SENHA)

        resposta = suap_client.post(
            edital.get_url_inscrever(),
            {
                'inicio_exercicio': '01/01/2000',
                'jornada_trabalho': candidato.jornada_trabalho,
                'concurso_ingresso_eh_ifrn': True,
                'classificacao_concurso': '1',
                'dou_numero': '1',
                'dou_data': '01/02/2000',
                'dou_pagina': '1',
                'dou_sessao': '1',
                f'campus_{campus.pk}': campus.pk,
            },
        )

        assert_no_validation_errors(resposta)
        assert Inscricao.objects.filter(edital=edital, servidor=candidato).exists()
