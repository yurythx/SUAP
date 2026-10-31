"""Teste da identificação do responsável no documento publicado do PDA."""

import pytest

from dados_abertos.templatetags.dados_abertos_filters import responsavel_publico
from rh.tests.factories import ServidorFactory


@pytest.mark.parametrize(
    ('nome_usual', 'esperado'),
    [
        ('Maria Silva', 'Maria Silva (123...)'),
        ('', 'MARIA DAS GRACAS SILVA SANTOS (123...)'),
    ],
    ids=['usa o nome do crachá', 'sem nome usual, cai para o nome civil'],
)
def test_responsavel_sai_com_nome_usual_e_matricula_truncada(nome_usual, esperado):
    """O documento é público: nome do crachá e só os três primeiros dígitos da matrícula."""
    servidor = ServidorFactory.build(matricula='1234567')
    servidor.pessoa_fisica.nome = 'MARIA DAS GRACAS SILVA SANTOS'
    servidor.pessoa_fisica.nome_usual = nome_usual

    assert responsavel_publico(servidor) == esperado


def test_sem_responsavel_nao_vira_none():
    """A marcação renderiza o vazio como vazio, não como 'None'."""
    assert responsavel_publico(None) == ''
