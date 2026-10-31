"""Gastos do plano de desembolso ("Gerenciar Gasto" da aba "Plano de Desembolso" de `projeto.html`)."""

import datetime

import pytest
from django.contrib.messages import get_messages

from projetos_ensino.models import Desembolso, RegistroGasto
from projetos_ensino.tests.conftest import _login, set_periodo_execucao
from projetos_ensino.tests.factories import DesembolsoFactory, RegistroGastoFactory

ROTA = '/projetos_ensino/registro_gasto/{}/'


def _em_execucao(projeto):
    set_periodo_execucao(projeto.edital)
    return Desembolso.objects.get(projeto=projeto)


def _dados_do_gasto(desembolso):
    return {'ano': desembolso.ano.pk, 'mes': desembolso.mes, 'descricao': 'Gasto alterado', 'qtd': 7, 'valor_unitario': '10,00'}


@pytest.mark.django_db(databases='__all__')
def test_gasto_so_e_editado_pelo_proprio_desembolso(client, usuarios, projeto_aprovado):
    """``?editar_registro_id`` de gasto de outro desembolso não abre nem move o gasto (#17564)."""
    desembolso = _em_execucao(projeto_aprovado)
    outro = DesembolsoFactory(item=desembolso.item, mes=2)
    gasto = RegistroGastoFactory(desembolso=outro)
    rota = f'{ROTA.format(desembolso.pk)}?editar_registro_id={gasto.pk}'

    _login(client, usuarios.coordenador)
    assert client.get(rota).status_code == 404
    assert client.post(rota, _dados_do_gasto(desembolso)).status_code == 404
    gasto.refresh_from_db()
    assert (gasto.desembolso_id, gasto.qtd) == (outro.pk, 1)


@pytest.mark.django_db(databases='__all__')
def test_gasto_so_e_gerenciado_com_o_projeto_em_execucao(client, usuarios, projeto_aprovado):
    """Projeto finalizado: o coordenador não registra gasto pela URL; o Gerente Sistêmico segue gerenciando (#17565)."""
    desembolso = _em_execucao(projeto_aprovado)
    rota = ROTA.format(desembolso.pk)

    _login(client, usuarios.coordenador)
    assert client.get(rota).status_code == 200

    projeto_aprovado.data_finalizacao_conclusao = datetime.date.today()
    projeto_aprovado.save()
    assert client.get(rota).status_code == 403
    assert client.post(rota, _dados_do_gasto(desembolso)).status_code == 403
    assert not RegistroGasto.objects.filter(desembolso=desembolso).exists()

    _login(client, usuarios.gerente)
    assert client.get(rota).status_code == 200


@pytest.mark.django_db(databases='__all__')
def test_gasto_avaliado_nao_e_excluido(client, usuarios, projeto_aprovado):
    """``?registro_id`` de gasto já aprovado pelo monitor é recusado, como no `pesquisa` (#17565)."""
    desembolso = _em_execucao(projeto_aprovado)
    gasto = RegistroGastoFactory(desembolso=desembolso, aprovado=True, dt_avaliacao=datetime.date.today())

    _login(client, usuarios.coordenador)
    resposta = client.get(f'{ROTA.format(desembolso.pk)}?registro_id={gasto.pk}')
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == ['Não é possível excluir um registro de gasto avaliado.']
    assert RegistroGasto.objects.filter(pk=gasto.pk).exists()


@pytest.mark.django_db(databases='__all__')
def test_prestacao_de_contas_so_oferece_cadastrar_onde_a_rota_abre(client, usuarios, projeto_aprovado):
    """ "Cadastrar" (comprovante/cotação) some onde ``registro_gasto`` recusa: gasto avaliado com nota fiscal e projeto finalizado."""
    desembolso = _em_execucao(projeto_aprovado)
    livre = RegistroGastoFactory(desembolso=desembolso)
    avaliado = RegistroGastoFactory(
        desembolso=desembolso, aprovado=True, dt_avaliacao=datetime.date.today(), arquivo='projetos_ensino/registrogasto/comprovantes/nota.pdf'
    )
    relatorio = f'/projetos_ensino/prestacao_contas/{projeto_aprovado.pk}/?tipo_relatorio=2'

    def cadastrar(gasto):
        return f'{ROTA.format(desembolso.pk)}?editar_registro_id={gasto.pk}'

    _login(client, usuarios.coordenador)
    pagina = client.get(relatorio).content.decode()
    assert cadastrar(livre) in pagina
    assert cadastrar(avaliado) not in pagina
    assert client.get(cadastrar(livre)).status_code == 200
    assert client.get(cadastrar(avaliado)).status_code == 302  # a rota recusa: "registro de gasto avaliado"

    projeto_aprovado.data_finalizacao_conclusao = datetime.date.today()
    projeto_aprovado.save()
    assert cadastrar(livre) not in client.get(relatorio).content.decode()
    assert client.get(cadastrar(livre)).status_code == 403


@pytest.mark.django_db(databases='__all__')
def test_avaliador_nao_recebe_link_para_os_gastos(client, usuarios, projeto_aprovado):
    """Só o responsável e o gerente veem os gastos: o avaliador não recebe "Visualizar Gasto" (#17566)."""
    desembolso = _em_execucao(projeto_aprovado)
    pagina = f'/projetos_ensino/projeto/{projeto_aprovado.pk}/?tab=plano_desembolso'
    link = f'href="{ROTA.format(desembolso.pk)}"'

    _login(client, usuarios.coordenador)
    assert link in client.get(pagina).content.decode()

    _login(client, usuarios.avaliador)
    resposta = client.get(pagina)
    assert resposta.status_code == 200
    assert link not in resposta.content.decode()
    assert client.get(ROTA.format(desembolso.pk)).status_code == 403
