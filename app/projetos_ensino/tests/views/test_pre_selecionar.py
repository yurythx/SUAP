"""Pré-seleção: as rotas só aceitam a ação que a lista de pré-seleção oferece, e a quem ela oferece (#17579)."""

import pytest
from django.contrib.auth.models import Group

from projetos_ensino.models import Edital, OfertaProjeto, Projeto
from projetos_ensino.tests.conftest import _login, set_periodo_pre_selecao
from rh.tests.factories import ServidorFactory


def _urls(projeto: Projeto) -> tuple[str, str, str, str]:
    """(lista de pré-seleção, pre_selecionar, pre_aprovar, pre_rejeitar)."""
    return (
        f'/projetos_ensino/projetos_nao_avaliados/{projeto.edital.pk}/',
        f'/projetos_ensino/pre_selecionar/{projeto.pk}/',
        f'/projetos_ensino/pre_aprovar/{projeto.pk}/',
        f'/projetos_ensino/pre_rejeitar/{projeto.pk}/',
    )


@pytest.mark.django_db(databases='__all__')
def test_comissao_de_acompanhamento_nao_pre_seleciona(client, usuarios, projeto_enviado):
    """A lista não oferece a pré-seleção ao Integrante da Comissão de Acompanhamento, e a rota o recusa."""
    projeto = projeto_enviado
    set_periodo_pre_selecao(projeto.edital)
    lista, pre_selecionar, _, pre_rejeitar = _urls(projeto)
    integrante = ServidorFactory(setor=usuarios.coordenador.setor)
    integrante.get_user().groups.add(Group.objects.get(name='Integrante da Comissão de Acompanhamento'))

    _login(client, integrante)
    conteudo = client.get(lista).content.decode()
    assert projeto.titulo in conteudo
    assert pre_selecionar not in conteudo
    assert pre_rejeitar not in conteudo
    assert client.get(pre_selecionar).status_code == 403

    _login(client, usuarios.pre_avaliador)
    assert pre_selecionar in client.get(lista).content.decode()


@pytest.mark.django_db(databases='__all__')
def test_pre_aprovar_nao_inverte_o_pre_selecionado(client, usuarios, projeto_pre_selecionado):
    """``pre_aprovar``/``pre_selecionar`` em projeto já pré-selecionado recusam em vez de rejeitá-lo."""
    projeto = projeto_pre_selecionado
    _, pre_selecionar, pre_aprovar, _ = _urls(projeto)

    assert [client.get(url).status_code for url in (pre_aprovar, pre_selecionar)] == [403, 403]
    assert Projeto.objects.get(pk=projeto.pk).pre_aprovado is True


@pytest.mark.django_db(databases='__all__')
def test_fluxo_continuo_pre_selecionado_nao_e_desfeito(client, usuarios, projeto_enviado):
    """No fluxo contínuo, a pré-seleção aprova de vez: ``pre_rejeitar`` depois dela recusa."""
    projeto = projeto_enviado
    projeto.edital.tipo_edital = Edital.ENSINO_CONTINUO
    set_periodo_pre_selecao(projeto.edital)  # salva o edital inteiro, com o tipo
    lista, pre_selecionar, _, pre_rejeitar = _urls(projeto)

    _login(client, usuarios.pre_avaliador)
    assert client.get(pre_selecionar, HTTP_REFERER=lista).status_code == 302
    assert client.get(pre_rejeitar).status_code == 403
    projeto = Projeto.objects.get(pk=projeto.pk)
    assert (projeto.pre_aprovado, projeto.aprovado) == (True, True)


@pytest.mark.django_db(databases='__all__')
def test_oferta_sem_vaga_nao_pre_seleciona(client, usuarios, projeto_enviado):
    """Sem vaga na cota do campus, a lista mostra "Cota de pré-aprovados atingida" e a rota recusa."""
    projeto = projeto_enviado
    set_periodo_pre_selecao(projeto.edital)
    OfertaProjeto.objects.filter(edital=projeto.edital, uo=projeto.uo).update(qtd_aprovados=0)
    lista, pre_selecionar, _, _ = _urls(projeto)

    _login(client, usuarios.pre_avaliador)
    conteudo = client.get(lista).content.decode()
    assert 'Cota de pré-aprovados atingida' in conteudo
    assert pre_selecionar not in conteudo
    assert client.get(pre_selecionar).status_code == 403
    assert Projeto.objects.get(pk=projeto.pk).data_pre_avaliacao is None
