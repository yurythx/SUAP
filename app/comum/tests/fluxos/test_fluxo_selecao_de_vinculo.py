"""Fluxo: quem tem dois vínculos escolhe com qual deles entra, depois de autenticar no Gov.BR.

O Gov.BR autentica a **pessoa** (pelo CPF), não o usuário do SUAP. Quem acumula dois vínculos
— o caso comum é o servidor que também é aluno, mas duas matrículas de servidor dão no mesmo —
chega ao SUAP autenticado e ainda sem saber "como quem" vai trabalhar. É o que a tela de
seleção de vínculo resolve, e é por isso que ela autentica *de novo*, agora no ``User`` do
vínculo escolhido.

O que este fluxo percorre, em sequência:

1. A pessoa, recém-autenticada no Gov.BR, vê os dois vínculos ativos listados.
2. Escolhe o segundo — e a sessão passa a ser a do usuário daquele vínculo, preservando as
   marcas da autenticação Gov.BR (é isso que impede o middleware de mandá-la logar de novo).
3. Quando a conta Gov.BR não atende ao nível de confiabilidade exigido pela instituição, a
   sessão é encerrada e a pessoa volta para a porta da rua.

Por que este fluxo e não outro: a suíte e2e do módulo só anda o caminho negativo desta tela
(``test_selecionar_vinculo_sem_autenticacao_externa_desloga``), que sai pelo primeiro ``if``.
Todo o miolo — montar a lista, casar o hash com o vínculo, reautenticar e conferir a
confiabilidade — nunca é executado por teste nenhum, unitário ou de browser.
"""

from __future__ import annotations

import hashlib

import pytest

from comum.models import Configuracao, Vinculo
from rh.tests.factories import PessoaFisicaFactory, ServidorFactory, SetorFactory

SELECIONAR_VINCULO = '/comum/selecionar_vinculo/'


def _hash_do_vinculo(vinculo: Vinculo) -> str:
    """Reproduz o identificador opaco que a tela usa no lugar do id do vínculo."""
    return hashlib.md5(str(vinculo.id).encode()).hexdigest()


def _marcar_sessao_como_govbr(client, confiabilidade: str = '3') -> None:
    """Grava na sessão as marcas que o middleware do Gov.BR deixa após autenticar."""
    sessao = client.session
    sessao['autenticou_com_govbr'] = True
    sessao['confiabilidade_govbr'] = confiabilidade
    sessao['token_govbr'] = {'decoded_data': {'amr': ['urn:gov:br:mfa']}}
    sessao.save()


def _usuario_autenticado(client) -> str | None:
    return client.session.get('_auth_user_id')


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
class TestFluxoSelecaoDeVinculo:
    def test_escolhe_o_segundo_vinculo_e_passa_a_trabalhar_nele(self, client) -> None:
        setor = SetorFactory(sigla='SV0')
        pessoa = PessoaFisicaFactory()
        primeiro = ServidorFactory(pessoa_fisica=pessoa, setor=setor)
        segundo = ServidorFactory(pessoa_fisica=pessoa, setor=setor)

        vinculo_primeiro = primeiro.get_vinculo()
        vinculo_segundo = segundo.get_vinculo()
        assert vinculo_primeiro != vinculo_segundo, 'as duas matrículas deveriam render dois vínculos da mesma pessoa'

        client.force_login(primeiro.get_user())
        _marcar_sessao_como_govbr(client)

        # 1. Os dois vínculos da pessoa aparecem na tela de escolha.
        resposta = client.get(SELECIONAR_VINCULO)
        assert resposta.status_code == 200
        hashes_na_tela = {dados['vinculo_hash'] for dados in resposta.context['vinculos_ativos_']}
        assert hashes_na_tela == {_hash_do_vinculo(vinculo_primeiro), _hash_do_vinculo(vinculo_segundo)}
        assert len(resposta.context['vinculos_ativos_']) == Vinculo.objects.filter(pessoa__pessoafisica__cpf=pessoa.cpf, user__is_active=True).count()
        selecionados = [dados['vinculo_hash'] for dados in resposta.context['vinculos_ativos_'] if dados['selecionado']]
        assert selecionados == [_hash_do_vinculo(vinculo_primeiro)], 'a tela deveria marcar o vínculo em que a pessoa já está'

        # 2. Escolhido o segundo vínculo, a sessão passa a ser a do usuário dele.
        resposta = client.get(SELECIONAR_VINCULO, {'vp': _hash_do_vinculo(vinculo_segundo)})
        assert resposta.status_code == 302
        assert _usuario_autenticado(client) == str(segundo.get_user().pk), 'a escolha do vínculo não trocou o usuário da sessão'
        assert client.session.get('autenticou_com_govbr') is True, 'a nova sessão perdeu a marca da autenticação Gov.BR'
        assert client.session.get('confiabilidade_govbr') == '3'

        # 3. Reabrir a tela já no vínculo escolhido não desfaz a escolha.
        resposta = client.get(SELECIONAR_VINCULO)
        assert resposta.status_code == 200
        selecionados = [dados['vinculo_hash'] for dados in resposta.context['vinculos_ativos_'] if dados['selecionado']]
        assert selecionados == [_hash_do_vinculo(vinculo_segundo)]

    def test_confiabilidade_govbr_abaixo_do_exigido_encerra_a_sessao(self, client) -> None:
        """A instituição pode exigir um nível mínimo de confiabilidade da conta Gov.BR.

        Abaixo dele a pessoa não escolhe vínculo nenhum: é deslogada na própria tela.
        """
        setor = SetorFactory(sigla='SV1')
        pessoa = PessoaFisicaFactory()
        servidor = ServidorFactory(pessoa_fisica=pessoa, setor=setor)

        Configuracao.objects.create(app='comum', chave='nível_minimo_para_autenticacao_govbr', valor='3', descricao='Nível mínimo Gov.BR')
        Configuracao.clear_cache()

        client.force_login(servidor.get_user())
        _marcar_sessao_como_govbr(client, confiabilidade='1')

        resposta = client.get(SELECIONAR_VINCULO)

        assert resposta.status_code == 302
        assert resposta.url == '/'
        assert _usuario_autenticado(client) is None, 'a sessão continuou autenticada apesar da confiabilidade insuficiente'

    def test_vinculo_unico_dispensa_a_escolha(self, client) -> None:
        """Com um vínculo só não há o que escolher: a tela encaminha direto para o destino."""
        setor = SetorFactory(sigla='SV2')
        pessoa = PessoaFisicaFactory()
        servidor = ServidorFactory(pessoa_fisica=pessoa, setor=setor)

        client.force_login(servidor.get_user())
        _marcar_sessao_como_govbr(client)

        resposta = client.get(SELECIONAR_VINCULO)

        assert resposta.status_code == 302
        assert _usuario_autenticado(client) == str(servidor.get_user().pk)
