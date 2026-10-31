"""Bloqueio da inscrição por afastamento impeditivo (``inscrever``).

O servidor bloqueado precisa saber **qual** afastamento o impede: o caso típico é um afastamento
importado do SIAPE sem data de término (requisição, exercício externo), que segue "vigente" depois
que o servidor voltou e só a Gestão de Pessoas consegue encerrar.
"""

import datetime

import pytest

from remanejamento.conftest import SENHA
from remanejamento.models import EditalAfastamento, Inscricao
from rh.tests.factories import AfastamentoSiapeFactory, ServidorAfastamentoFactory

URL = '/remanejamento/inscrever/{}/'

HOJE = datetime.date.today()


def _impeditivo(edital, nome):
    afastamento = AfastamentoSiapeFactory(nome=nome)
    EditalAfastamento.objects.create(edital=edital, afastamento=afastamento, impeditivo=True)
    return afastamento


def _abrir_inscricao(suap_client, servidor, edital):
    suap_client.login(username=servidor.get_user().username, password=SENHA)
    return suap_client.get(URL.format(edital.pk))


@pytest.mark.django_db
def test_inscricao_bloqueada_lista_os_afastamentos_impeditivos(suap_client, candidato, edital):
    requisicao = _impeditivo(edital, 'REQUISICAO')
    ServidorAfastamentoFactory(servidor=candidato, afastamento=requisicao, data_inicio=datetime.date(2021, 11, 29), data_termino=None)
    licenca = _impeditivo(edital, 'LICENCA PARA TRATAR DE INTERESSES PARTICULARES')
    inicio, termino = HOJE - datetime.timedelta(days=10), HOJE + datetime.timedelta(days=10)
    ServidorAfastamentoFactory(servidor=candidato, afastamento=licenca, data_inicio=inicio, data_termino=termino)

    resposta = _abrir_inscricao(suap_client, candidato, edital)

    assert resposta.status_code == 200
    conteudo = ' '.join(resposta.content.decode().split())
    assert 'não é possível se inscrever devido aos seguintes afastamentos impeditivos vigentes' in conteudo
    assert f'{requisicao} (desde 29/11/2021, sem data de término registrada)' in conteudo
    assert f'{licenca} (desde {inicio:%d/%m/%Y}, até {termino:%d/%m/%Y})' in conteudo
    assert 'procure a Gestão de Pessoas' in conteudo
    assert 'name="concurso_ingresso_eh_ifrn"' not in conteudo, 'o formulário não deveria ser exibido ao servidor bloqueado'

    suap_client.post(URL.format(edital.pk), {'concurso_ingresso_eh_ifrn': 'True', 'classificacao_concurso': '1'})
    assert not Inscricao.objects.filter(edital=edital, servidor=candidato).exists(), 'o bloqueio precisa valer também no POST'


@pytest.mark.django_db
def test_afastamento_impeditivo_cancelado_futuro_ou_encerrado_nao_bloqueia(suap_client, candidato, edital):
    """Só bloqueia o afastamento em usufruto no dia da inscrição (``EditalAfastamento``)."""
    afastamento = _impeditivo(edital, 'REQUISICAO')
    ServidorAfastamentoFactory(
        servidor=candidato, afastamento=afastamento, data_inicio=datetime.date(2021, 11, 29), data_termino=None, cancelado=True
    )
    ServidorAfastamentoFactory(servidor=candidato, afastamento=afastamento, data_inicio=HOJE + datetime.timedelta(days=5), data_termino=None)
    ServidorAfastamentoFactory(servidor=candidato, afastamento=afastamento, data_inicio=datetime.date(2020, 1, 1), data_termino=HOJE)

    resposta = _abrir_inscricao(suap_client, candidato, edital)

    assert resposta.status_code == 200
    assert 'name="concurso_ingresso_eh_ifrn"' in resposta.content.decode(), 'o formulário de inscrição deveria ser exibido'
