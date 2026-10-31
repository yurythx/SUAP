"""Análise da solicitação de alteração de foto (validar, rejeitar e detalhe).

As três views exigiam só ``rh.view_solicitacaoalteracaofoto``, que o grupo Servidor tem: qualquer
servidor validava a foto de outro, que virava a foto oficial do vínculo (#17647). Agora validar e
rejeitar exigem ser RH (``eh_rh_sistemico`` ou ``eh_rh_campus``), e as três seguem o escopo da
listagem do admin: o RH do campus só alcança as solicitações do seu campus, e o servidor só as próprias.
"""

import pytest
from django.contrib.auth.models import Group

from rh.models import SolicitacaoAlteracaoFoto
from rh.tests.factories import ServidorFactory, SetorFactory, SolicitacaoAlteracaoFotoFactory

VALIDAR = '/rh/validaralteracaofoto/{}/'
REJEITAR = '/rh/rejeitaralteracaofoto/{}/'
DETALHE = '/rh/detalhe_solicitacao_alteracao_foto/{}/'


@pytest.fixture
def setor(db, sync_permissions):
    return SetorFactory()


def _aguardando(pk: int) -> bool:
    return SolicitacaoAlteracaoFoto.objects.filter(pk=pk, situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO).exists()


def test_servidor_nao_valida_nem_rejeita_foto_de_outro(client, setor):
    solicitacao = SolicitacaoAlteracaoFotoFactory(solicitante=ServidorFactory(setor=setor))
    client.force_login(ServidorFactory(setor=setor).get_user())

    assert client.get(VALIDAR.format(solicitacao.pk)).status_code == 403
    assert client.post(REJEITAR.format(solicitacao.pk), {'motivo_rejeicao': 'x'}).status_code == 403
    assert _aguardando(solicitacao.pk)


def test_servidor_ve_o_detalhe_so_da_propria_solicitacao(client, setor):
    servidor = ServidorFactory(setor=setor)
    propria = SolicitacaoAlteracaoFotoFactory(solicitante=servidor)
    alheia = SolicitacaoAlteracaoFotoFactory(solicitante=ServidorFactory(setor=setor))
    client.force_login(servidor.get_user())

    assert client.get(DETALHE.format(propria.pk)).status_code == 200
    assert client.get(DETALHE.format(alheia.pk)).status_code == 404


def test_rh_do_campus_valida_so_no_proprio_campus(client, setor):
    rh = ServidorFactory(setor=setor)
    rh.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas'))
    do_campus = SolicitacaoAlteracaoFotoFactory(solicitante=ServidorFactory(setor=setor))
    de_outro_campus = SolicitacaoAlteracaoFotoFactory(solicitante=ServidorFactory(setor=SetorFactory()))
    client.force_login(rh.get_user())

    assert client.get(VALIDAR.format(do_campus.pk)).status_code == 302
    assert SolicitacaoAlteracaoFoto.objects.filter(pk=do_campus.pk, situacao=SolicitacaoAlteracaoFoto.VALIDADA).exists()
    assert client.get(VALIDAR.format(de_outro_campus.pk)).status_code == 404
    assert _aguardando(de_outro_campus.pk)
