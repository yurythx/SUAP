"""Gerenciamento de acessos manuais quando há chefia automática sobreposta."""

from comum.models import User
from django.test import Client
import pytest

from processo_eletronico.models import CompartilhamentoProcessoEletronicoPoderDeChefe
from processo_eletronico.tests.factories import CompartilhamentoPoderChefeFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, ServidorFuncaoChefiaFactory, SetorFactory, SetorSiapeFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_remover_acesso_manual_com_chefia_automatica_sobreposta(client: Client) -> None:
    setor = SetorFactory()
    chefe = ServidorFactory(setor=setor)
    removido = ServidorFactory(setor=setor)
    mantido = ServidorFactory(setor=setor)
    vinculo_chefe = chefe.get_vinculo()
    vinculo_removido = removido.get_vinculo()
    vinculo_mantido = mantido.get_vinculo()
    CompartilhamentoPoderChefeFactory(setor_dono=setor, vinculo_permitido=vinculo_chefe, de_oficio=True)
    for vinculo in (vinculo_chefe, vinculo_removido, vinculo_removido, vinculo_mantido):
        CompartilhamentoPoderChefeFactory(setor_dono=setor, vinculo_permitido=vinculo)

    client.force_login(chefe.get_user())
    url = f'/processo_eletronico/gerenciar_compartilhamento_processos_poder_de_chefe/?setor={setor.pk}'
    resposta = client.get(url)
    assert resposta.status_code == 200
    selecionados = list(resposta.context['form'].fields['vinculos_com_poder_de_chefe'].initial)
    assert set(selecionados) == {vinculo_removido.pk, vinculo_mantido.pk}
    assert selecionados.count(vinculo_removido.pk) == 1

    resposta = client.post(url, {'vinculos_com_poder_de_chefe': [pk for pk in selecionados if pk != vinculo_removido.pk]})
    assert resposta.status_code == 302
    acessos = CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(setor_dono=setor)
    assert not acessos.filter(vinculo_permitido=vinculo_removido).exists()
    assert acessos.filter(vinculo_permitido=vinculo_chefe, de_oficio=True).exists()
    assert not acessos.filter(vinculo_permitido=vinculo_chefe, de_oficio=False).exists()
    assert acessos.filter(vinculo_permitido=vinculo_mantido, de_oficio=False).exists()


def _chefes_de_oficio_na_tela(client: Client, usuario: User, setor: Setor) -> set[int]:
    client.force_login(usuario)
    resposta = client.get(f'/processo_eletronico/gerenciar_compartilhamento_processos_poder_de_chefe/?setor={setor.pk}')
    assert resposta.status_code == 200
    return set(resposta.context['vinculos_com_poder_de_chefe_oficio'].values_list('vinculo_permitido', flat=True))


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_chefes_de_oficio_acompanham_correcao_do_setor_suap_da_funcao(client: Client) -> None:
    proen = SetorFactory(sigla='PROEN')
    coordenacao = SetorFactory(superior=proen)
    pro_reitora = ServidorFactory(setor=proen)
    coordenador = ServidorFactory(setor=proen)
    ServidorFuncaoChefiaFactory(servidor=pro_reitora, setor=SetorSiapeFactory(), setor_suap=proen)
    funcao_coordenador = ServidorFuncaoChefiaFactory(servidor=coordenador, setor=SetorSiapeFactory(), setor_suap=proen)
    vinculo_pro_reitora = pro_reitora.get_vinculo().pk
    vinculo_coordenador = coordenador.get_vinculo().pk
    assert _chefes_de_oficio_na_tela(client, pro_reitora.get_user(), proen) == {vinculo_pro_reitora, vinculo_coordenador}

    funcao_coordenador.setor_suap = coordenacao
    funcao_coordenador.save()
    assert _chefes_de_oficio_na_tela(client, pro_reitora.get_user(), proen) == {vinculo_pro_reitora}
    assert _chefes_de_oficio_na_tela(client, coordenador.get_user(), coordenacao) == {vinculo_coordenador}

    funcao_coordenador.delete()
    assert not CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(setor_dono=coordenacao, de_oficio=True).exists()
    assert _chefes_de_oficio_na_tela(client, pro_reitora.get_user(), proen) == {vinculo_pro_reitora}
