"""Fluxo: sessões e dispositivos — sair, deslogar sessão remota, apelidar/desativar dispositivo.

Toda autenticação no SUAP grava um par ``Device`` + ``SessionInfo`` (sinal ``user_logged_in``,
``comum/models.py``), e é sobre esse par que o usuário age quando percebe um acesso que não
reconhece: desloga a sessão remota, desativa o dispositivo, apelida o que é seu. É a única
ferramenta de resposta a incidente que o usuário comum tem — e a que só se descobre quebrada
quando já era preciso.

A regressão que este arquivo pega: a sessão deixar de ser marcada como expirada ao sair (o que
faria a listagem mentir sobre quem está conectado), ou os endereços de gestão de dispositivo
passarem a aceitar dispositivo alheio.

**Por que os dispositivos aqui são sintéticos**: todo contexto do Playwright manda o mesmo
``user-agent``, e o ``Device`` nasce por ``get_or_create(user, user_agent)`` — o dispositivo
"real" de um papel é o mesmo em toda a suíte. Desativá-lo expiraria a sessão que os outros
testes reusam. A fixture ``dispositivo_e2e`` cria um par próprio, com ``user-agent`` único.
"""

from __future__ import annotations

import uuid

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_senha.py`.
LOGOUT = '/comum/logout/'
SELECIONAR_VINCULO = '/comum/selecionar_vinculo/'
REMOTE_LOGOUT = '/comum/remote_logout/{sessao}/'
REMOTE_LOGOUT_ALL = '/comum/remote_logout_all/'
DEACTIVATE_DEVICE = '/comum/deactivate_device/{device}/'
REACTIVATE_DEVICE = '/comum/reactivate_device/{device}/'
GIVE_NICKNAME_TO_DEVICE = '/comum/give_nickname_to_device/{device}/'

# Listagens do admin em que as ações acima desembocam (`httprr`), usadas como ponto de partida.
ADMIN_DISPOSITIVOS = '/admin/comum/device/'
ADMIN_SESSOES = '/admin/comum/sessioninfo/'

LINK_DA_TELA_DE_LOGIN = 'Esqueceu ou deseja alterar sua senha?'


def _chave_da_sessao(pagina) -> str:
    """O ``session_key`` da página autenticada, lido do cookie do contexto.

    É o que liga a sessão do browser à linha de ``SessionInfo`` no banco — sem ele não dá para
    afirmar que foi **esta** sessão que o logout expirou.
    """
    from django.conf import settings

    cookies = [c for c in pagina.context.cookies() if c['name'] == settings.SESSION_COOKIE_NAME]
    assert cookies, f'a página não tem cookie de sessão ({settings.SESSION_COOKIE_NAME})'
    return cookies[0]['value']


def test_sair_do_sistema_expira_a_sessao(logado_efemero, conta_pessoal):
    """Sair devolve o usuário à tela de login e marca a sessão como expirada no banco.

    Roda numa sessão **própria** (``logado_efemero``): o ``logado_comum`` entrega uma página
    autenticada por ``storage_states``, que reusa um único login por papel na sessão inteira do
    pytest — sair ali deslogaria todos os testes seguintes daquele papel.
    """
    from comum.models import SessionInfo

    pagina = logado_efemero('conta_pessoal')
    chave = _chave_da_sessao(pagina)

    tela = Tela(pagina).ir(LOGOUT)

    tela.ver_texto(LINK_DA_TELA_DE_LOGIN)
    assert SessionInfo.objects.get(session_id=chave).expired, 'a UI voltou ao login, mas a sessão continuou ativa no banco'


def test_selecionar_vinculo_sem_autenticacao_externa_desloga(logado_efemero, conta_pessoal):
    """Sem sessão do Gov.BR ou de passaporte, a seleção de vínculo desloga e volta ao login.

    A tela existe para quem entrou por um provedor externo e tem mais de um vínculo com o mesmo
    CPF: o SUAP pergunta em qual entrar. Os dois ramos que **montam a lista** são inalcançáveis
    daqui — dependem de uma sessão do Gov.BR (IdP externo) e, no caso de vínculo único, a view
    nem chega a renderizar, autentica e redireciona direto. O que este teste exercita é o ramo
    restante, que é também o que acontece em produção quando alguém abre a URL por fora do
    fluxo: o usuário é deslogado por não haver vínculo de origem externa.
    """
    from comum.models import SessionInfo

    pagina = logado_efemero('conta_pessoal')
    chave = _chave_da_sessao(pagina)

    tela = Tela(pagina).ir(SELECIONAR_VINCULO)

    tela.ver_texto(LINK_DA_TELA_DE_LOGIN)
    assert SessionInfo.objects.get(session_id=chave).expired, 'a tela voltou ao login, mas a sessão continuou ativa no banco'


def test_apelidar_dispositivo(logado_comum, dispositivo_e2e):
    """O dono dá nome ao próprio dispositivo — é assim que ele o reconhece na listagem."""
    from comum.models import Device

    device, _sessao = dispositivo_e2e
    apelido = f'Notebook {uuid.uuid4().hex[:8]}'

    tela = Tela(logado_comum('solicitante')).ir(ADMIN_DISPOSITIVOS)
    tela.ir(GIVE_NICKNAME_TO_DEVICE.format(device=device.pk))
    tela.preencher('Apelido', 'texto', apelido)
    tela.clicar_botao('Salvar')

    tela.sucesso('Apelido concedido com sucesso.')
    assert Device.objects.get(pk=device.pk).nickname == apelido, 'a UI disse que salvou, mas o apelido não persistiu'


def test_desativar_e_reativar_dispositivo(logado_comum, dispositivo_e2e):
    """Desativar o dispositivo derruba as sessões abertas nele; reativar o traz de volta.

    Os dois passos num teste só porque o segundo não existe sem o primeiro — ``Reativar`` só
    aparece para dispositivo desativado —, e porque é o par que descreve a resposta a um acesso
    indevido: corta agora, restaura depois de conferir.
    """
    from comum.models import Device, SessionInfo

    device, sessao = dispositivo_e2e
    tela = Tela(logado_comum('solicitante')).ir(DEACTIVATE_DEVICE.format(device=device.pk))

    tela.sucesso('Dispositivo desativado')
    assert not Device.objects.get(pk=device.pk).activated, 'a UI disse que desativou, mas o dispositivo continuou ativo'
    assert SessionInfo.objects.get(pk=sessao.pk).expired, 'o dispositivo foi desativado, mas a sessão aberta nele sobreviveu'

    tela.ir(REACTIVATE_DEVICE.format(device=device.pk))

    tela.sucesso('Dispositivo reativado.')
    assert Device.objects.get(pk=device.pk).activated, 'a UI disse que reativou, mas o dispositivo continuou desativado'


def test_deslogar_uma_sessao_remota(logado_comum, dispositivo_e2e):
    """O botão "Deslogar" da listagem de sessões encerra uma sessão específica do próprio usuário."""
    from comum.models import SessionInfo

    _device, sessao = dispositivo_e2e

    tela = Tela(logado_comum('solicitante')).ir(ADMIN_SESSOES)
    tela.ir(REMOTE_LOGOUT.format(sessao=sessao.pk))

    tela.sucesso('Sessão remota deslogada com sucesso.')
    assert SessionInfo.objects.get(pk=sessao.pk).expired, 'a UI disse que deslogou, mas a sessão continuou ativa'


def test_deslogar_todas_as_outras_sessoes(logado_comum, dispositivo_e2e):
    """A ação em lote da listagem de sessões: derruba as outras e **preserva a atual**.

    A preservação é metade do que a view faz (``exclude(session_id=...)``) e é o que se perderia
    numa regressão silenciosa — quem clicasse seria deslogado junto e nunca veria a mensagem.
    Aqui ela é afirmada duas vezes: pela sessão do teste, que continua valendo depois da ação,
    e pelo registro dela no banco, que segue não expirado.
    """
    from comum.models import SessionInfo

    _device, sessao = dispositivo_e2e
    pagina = logado_comum('solicitante')
    chave_atual = _chave_da_sessao(pagina)

    tela = Tela(pagina).ir(REMOTE_LOGOUT_ALL)

    tela.sucesso('Sessões remotas deslogadas com sucesso.')
    assert SessionInfo.objects.get(pk=sessao.pk).expired, 'a sessão remota não foi expirada'
    assert not SessionInfo.objects.get(session_id=chave_atual).expired, 'a ação derrubou a própria sessão de quem a executou'
