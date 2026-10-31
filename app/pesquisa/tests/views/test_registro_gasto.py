"""Quem lança gasto no desembolso e em que estado do projeto (#17577).

Só a equipe do projeto (o coordenador, enquanto o projeto está em execução e não é somente
leitura) e o Diretor de Pesquisa gravam gasto — a mesma condição do botão "Gerenciar Gasto" e
do ``registro_gasto`` do ``projetos``. O avaliador indicado e o Coordenador de Pesquisa do campus
só visualizam.
"""

import datetime

import pytest

from comum.models import Ano
from pesquisa.models import Desembolso, Projeto, RegistroGasto
from pesquisa.tests.conftest import _login, _login_gerente, set_periodo_execucao


def _gasto(descricao: str) -> dict:
    return {
        'ano': Ano.objects.get_or_create(ano=str(datetime.date.today().year))[0].pk,
        'mes': '10',
        'descricao': descricao,
        'qtd': '1',
        'valor_unitario': '100,00',
    }


@pytest.mark.django_db(databases='__all__')
def test_so_equipe_e_diretor_lancam_gasto_e_so_no_projeto_editavel(client, usuarios, projeto_aprovado):
    projeto = projeto_aprovado
    set_periodo_execucao(projeto.edital)
    desembolso = Desembolso.objects.get(projeto=projeto)
    url = f'/pesquisa/registro_gasto/{desembolso.pk}/'

    _login(client, usuarios.avaliador)
    assert client.get(url).status_code == 200
    assert client.post(url, _gasto('Gasto do avaliador')).status_code == 403

    _login(client, usuarios.pre_avaliador)
    assert url not in client.get(f'/pesquisa/projeto/{projeto.pk}/').content.decode()
    assert client.post(url, _gasto('Gasto do Coordenador de Pesquisa')).status_code == 403
    assert not RegistroGasto.objects.filter(desembolso=desembolso).exists()

    _login(client, usuarios.coordenador)
    assert client.post(url, _gasto('Gasto do coordenador')).status_code == 302
    assert RegistroGasto.objects.filter(desembolso=desembolso, descricao='Gasto do coordenador').exists()

    # Concluído: somente leitura para a equipe; o status segue "em execução", então é o
    # `eh_somente_leitura` que barra. `update` para não passar pelos efeitos do `Projeto.save`.
    Projeto.objects.filter(pk=projeto.pk).update(data_finalizacao_conclusao=datetime.datetime.now())
    assert client.post(url, _gasto('Gasto após a conclusão')).status_code == 403
    assert not RegistroGasto.objects.filter(desembolso=desembolso, descricao='Gasto após a conclusão').exists()

    _login_gerente(client, usuarios.gerente)
    assert client.post(url, _gasto('Gasto do Diretor')).status_code == 302
    assert RegistroGasto.objects.filter(desembolso=desembolso, descricao='Gasto do Diretor').exists()
