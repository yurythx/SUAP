"""Fluxo: autenticação em dois fatores (OTP) — habilitar, validar o QR Code, remover.

O 2FA é a única barreira do SUAP que sobrevive ao vazamento de uma senha, e ele tem duas portas
independentes: o **ciclo do próprio usuário** (habilitar com o código do aplicativo, revisitar o
QR Code, remover) e a **desabilitação administrativa**, que o superusuário faz quando alguém
perde o celular — e que, mal guardada, viraria um botão de desligar o 2FA de qualquer um.

A regressão que este arquivo pega: o código TOTP deixar de ser conferido (qualquer número
habilita), o segredo não ser gerado, ou a tela de desabilitação administrativa parar de exigir
superusuário.

Tudo roda sobre ``conta_dois_fatores`` com ``logado_efemero``: habilitar 2FA num papel
compartilhado mudaria o que o login exige dele em todos os testes seguintes.
"""

from __future__ import annotations

import time

import onetimepass
import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_senha.py`.
HABILITAR_2FA = '/comum/habilitar_2fa_suap/'
VALIDAR_QRCODE_2FA = '/comum/validar_qrcode_2fa_otp/'
REMOVER_2FA = '/comum/remover_2fa_suap/'
ATIVAR_2FA = '/comum/ativar_autenticacao_dois_fatores/'
DESABILITAR_2FA_USUARIO = '/comum/desabilitar_2fa_usuario/{usuario}/'
LOGIN_EXIGE_DUPLO_FATOR = '/comum/login_exige_duplo_fator/{username}/'


def _codigo_otp(segredo: str) -> str:
    """Um TOTP válido para o segredo, com margem para o submit chegar na mesma janela.

    O TOTP vale por 30 segundos. Gerar o código no fim da janela e submetê-lo já na seguinte
    daria uma falha intermitente de poucos por cento — do tipo que se lê como "flake do
    Playwright". Esperar a virada quando sobra menos de 5 segundos custa isso, no pior caso, e
    elimina a corrida. O zero à esquerda importa: ``get_totp`` devolve ``int``.
    """
    restante = 30 - (time.time() % 30)
    if restante < 5:
        time.sleep(restante)
    return f'{onetimepass.get_totp(segredo):06d}'


def test_ciclo_do_2fa_por_aplicativo(logado_efemero, conta_dois_fatores):
    """Habilita o 2FA com o código do aplicativo, revisita o QR Code e remove.

    Um teste só para as três telas porque elas são degraus do mesmo estado: a tela de
    habilitação é a que **cria o segredo**, a de validação exige o 2FA já ativo e a remoção só
    tem o que remover depois das duas. Separá-las obrigaria cada uma a recriar o estado da
    anterior por ORM — e aí nenhuma exercitaria a tela que o produz.

    O código é calculado a partir do segredo que a tela acabou de gravar: é exatamente o que o
    aplicativo autenticador faria ao ler o QR Code.
    """
    from comum.models import AutenticacaoDoisFatores

    user = conta_dois_fatores.get_user()
    tela = Tela(logado_efemero('conta_dois_fatores')).ir(HABILITAR_2FA)
    tela.ver_titulo('Habilitar Autenticação por Dois Fatores')

    # O GET acima é quem cria o registro (e o segredo) — antes dele não há o que ler.
    registro = AutenticacaoDoisFatores.objects.get(usuario=user)
    assert registro.otp_secret_user, 'a tela abriu sem gerar o segredo do aplicativo autenticador'

    tela.preencher('Codigo', 'texto', _codigo_otp(registro.otp_secret_user))
    tela.clicar_botao('Enviar')
    tela.sucesso('A autenticação por Dois Fatores está habilitada.')

    registro.refresh_from_db()
    assert registro.ativo, 'a UI disse que habilitou, mas o registro continuou inativo'
    assert registro.validou_qrcode(), 'a UI disse que habilitou, mas o QR Code não consta validado'

    tela.ir(VALIDAR_QRCODE_2FA)
    tela.ver_titulo('Validar Autenticação por Dois Fatores')
    tela.preencher('Codigo', 'texto', _codigo_otp(registro.otp_secret_user))
    tela.clicar_botao('Enviar')
    tela.sucesso('A autenticação por Dois Fatores está ativida.')

    tela.ir(REMOVER_2FA)
    tela.sucesso('Autenticação com dois fatores removida com sucesso')
    assert not AutenticacaoDoisFatores.objects.filter(usuario=user).exists(), 'a UI disse que removeu, mas o registro persistiu'


def test_chave_do_2fa_alterna_pelo_endpoint_da_minha_conta(logado_efemero, conta_dois_fatores):
    """O AJAX do interruptor de 2FA da "Minha conta": a primeira chamada liga, a segunda desliga.

    Sem tela própria — o interruptor de ``minha_conta.html`` chama este endereço por ``$.ajax``
    e só lê o status —, então a asserção é o corpo da resposta mais o registro no banco. As duas
    chamadas existem porque a view é um **alternador**: cada ramo é um caminho diferente.

    O interruptor só aparece na tela quando a ``Configuracao('comum',
    'permite_autenticacao_duplo_fator')`` está ligada, e o seed do e2e não a traz — ligá-la aqui
    passaria a exigir o código TOTP no **login** de quem tem 2FA ativo, o que atingiria as
    outras fatias. Por isso o endereço é exercitado direto.
    """
    from comum.models import AutenticacaoDoisFatores

    user = conta_dois_fatores.get_user()
    tela = Tela(logado_efemero('conta_dois_fatores'))

    ligou = tela.buscar(ATIVAR_2FA)
    assert ligou.status == 200, f'a view respondeu HTTP {ligou.status}'
    assert ligou.text() == 'OK', 'o interruptor devolveu erro ao ligar o 2FA'
    assert AutenticacaoDoisFatores.objects.get(usuario=user).ativo, 'o endpoint respondeu OK, mas o 2FA não ficou ativo'

    desligou = tela.buscar(ATIVAR_2FA)
    assert desligou.text() == 'OK', 'o interruptor devolveu erro ao desligar o 2FA'
    assert not AutenticacaoDoisFatores.objects.get(usuario=user).ativo, 'o endpoint respondeu OK, mas o 2FA continuou ativo'


def test_superusuario_desabilita_o_2fa_de_outro_usuario(logado_comum, conta_dois_fatores):
    """A porta administrativa: só o superusuário desliga o 2FA de terceiro, e com motivo.

    A asserção de permissão vem primeiro e é por status HTTP: quem não é superusuário leva 403
    na mesma URL em que o superusuário vê o formulário. É a metade da tela que importa —
    desabilitar 2FA alheio é, na prática, remover a segunda barreira da conta de outra pessoa.
    """
    from datetime import datetime

    from comum.models import AutenticacaoDoisFatores

    user = conta_dois_fatores.get_user()
    AutenticacaoDoisFatores.objects.create(usuario=user, tipo=AutenticacaoDoisFatores.OTP, ativo=True, data_ultima_ativacao=datetime.now())
    rota = DESABILITAR_2FA_USUARIO.format(usuario=user.pk)

    negado = Tela(logado_comum('solicitante')).buscar(rota)
    assert negado.status == 403, f'servidor comum deveria levar 403 na desabilitação de 2FA alheio, veio {negado.status}'

    tela = Tela(logado_comum('admin')).ir(rota)
    tela.ver_titulo(f'Desabilitar 2FA - {user}')
    tela.preencher('Motivo', 'textarea', 'Servidor perdeu o aparelho com o aplicativo autenticador.')
    tela.clicar_botao('Desabilitar 2FA')

    tela.sucesso(f'Autenticação com dois fatores removida para {user.username}')
    assert not AutenticacaoDoisFatores.objects.filter(usuario=user).exists(), 'a UI disse que desabilitou, mas o registro persistiu'


def test_login_exige_duplo_fator(pagina_anonima, conta_dois_fatores):
    """O endereço que a tela de login consulta por AJAX para decidir se pede o código.

    Sob teste a view responde ``OK`` incondicionalmente (``running_tests()`` em
    ``comum/views.py``), justamente para as suítes de browser não precisarem de um aplicativo
    autenticador na tela de login — então o que este teste afirma é o contrato com o JS da tela
    (200 + ``OK``), não o ramo de produção, que é inalcançável aqui.
    """
    resposta = Tela(pagina_anonima).buscar(LOGIN_EXIGE_DUPLO_FATOR.format(username=conta_dois_fatores.matricula))

    assert resposta.status == 200, f'a view respondeu HTTP {resposta.status}'
    assert resposta.text() == 'OK', 'a tela de login espera OK deste endereço quando o duplo fator é aplicável'
