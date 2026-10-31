"""Fluxo: quem liga o 2FA pelo interruptor da "Minha conta" e depois abre a tela do OTP.

O interruptor (``ativar_autenticacao_dois_fatores``) cria o registro de
``AutenticacaoDoisFatores`` sem ``tipo``. A tela ``habilitar_2fa_suap`` vem depois e precisa
reaproveitar esse mesmo registro — o ``OneToOne`` só admite um por usuário — em vez de tentar
criar outro e cair num ``IntegrityError`` (#17391).

Com o segundo fator ligado, o destino de origem (``next``) tem de atravessar a verificação
inteiro, com todos os parâmetros da query, e só para o próprio host (#15440).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

import onetimepass
import pytest

from comum.models import AutenticacaoDoisFatores, Configuracao, Vinculo
from rh.tests.factories import ServidorFactory

ATIVAR_2FA = '/comum/ativar_autenticacao_dois_fatores/'
HABILITAR_2FA = '/comum/habilitar_2fa_suap/'
REMOVER_2FA = '/comum/remover_2fa_suap/'


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_interruptor_e_depois_habilitar_otp_reaproveita_o_registro(client) -> None:
    user = ServidorFactory().get_user()
    client.force_login(user)

    ligou = client.get(ATIVAR_2FA)
    assert ligou.content == b'OK'

    resposta = client.get(HABILITAR_2FA)

    assert resposta.status_code == 302
    registros = AutenticacaoDoisFatores.objects.filter(usuario=user)
    assert list(registros.values_list('tipo', flat=True)) == [AutenticacaoDoisFatores.OTP]


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_interruptor_e_depois_remover_2fa_apaga_o_registro(client) -> None:
    user = ServidorFactory().get_user()
    client.force_login(user)
    client.get(ATIVAR_2FA)

    client.get(REMOVER_2FA)

    assert not AutenticacaoDoisFatores.objects.filter(usuario=user).exists()


# --- Destino preservado através do segundo fator (#15440) -------------------------------------
#
# O ``next`` carrega a URL de origem inteira — no OAuth2, ``/o/authorize/`` com ``client_id``,
# ``redirect_uri`` e ``state``. Se a URL da etapa de verificação o leva sem codificar, os ``&``
# viram parâmetros da própria página de verificação e o destino chega truncado em
# ``/o/authorize/?response_type=code`` ("Missing client_id parameter").

AUTHORIZE = '/o/authorize/?response_type=code&scope=identificacao&client_id=abc123&redirect_uri=https://app.exemplo/cb/&state=xyz'
SENHA = 'senha-de-teste-15440'
CODIGO_2FA_EMAIL = '123456'  # `TwoFactorAuthenticationCode.save` fixa o código sob teste


def _next_do_redirect(resposta) -> tuple[str, str]:
    """Devolve a URL do redirect e o ``next`` que ela carrega, já decodificado."""
    assert resposta.status_code == 302
    url = resposta['Location']
    return url, parse_qs(urlsplit(url).query)['next'][0]


def _servidor_com_email_pessoal():
    """Servidor com e-mail pessoal, o único destino aceito para o código do 2FA por e-mail."""
    servidor = ServidorFactory()
    # ``User.get_vinculo`` guarda o vínculo num cache de processo: atualiza também a instância dele.
    vinculo = servidor.get_user().get_vinculo()
    vinculo.email_pessoal = 'servidor@pessoal.exemplo'
    Vinculo.objects.filter(pk=vinculo.pk).update(email_pessoal=vinculo.email_pessoal)
    return servidor


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_login_oauth2_com_otp_segue_para_o_authorize_completo(client) -> None:
    user = ServidorFactory().get_user()
    user.set_password(SENHA)
    user.save()
    otp = AutenticacaoDoisFatores.objects.create(usuario=user, tipo=AutenticacaoDoisFatores.OTP, ativo=True)
    Configuracao.objects.create(app='comum', chave='permite_autenticacao_duplo_fator', valor='True', descricao='')
    Configuracao.clear_cache()

    tela_de_login, next_url = _next_do_redirect(client.get(AUTHORIZE))
    assert next_url == AUTHORIZE

    resposta = client.post(
        tela_de_login,
        {'username': user.username, 'password': SENHA, 'auth_code': f'{onetimepass.get_totp(otp.otp_secret_user):06d}'},
    )

    assert resposta.status_code == 302, resposta.context['form'].errors
    assert resposta['Location'] == AUTHORIZE


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_codigo_por_email_segue_para_a_url_protegida_completa(client) -> None:
    servidor = _servidor_com_email_pessoal()
    client.force_login(servidor.get_user())
    protegida = f'/comum/atualizar_email_secundario/{servidor.get_vinculo().pk}/?origem=perfil&aba=email&ordem=2'

    verificacao, next_url = _next_do_redirect(client.get(protegida))
    assert next_url == protegida

    resposta = client.post(verificacao, {'code': CODIGO_2FA_EMAIL})

    assert resposta.status_code == 302
    assert resposta['Location'] == protegida


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_codigo_por_email_em_popup_mantem_a_query_da_url_protegida(client) -> None:
    servidor = _servidor_com_email_pessoal()
    client.force_login(servidor.get_user())
    protegida = f'/comum/atualizar_email_secundario/{servidor.get_vinculo().pk}/?origem=perfil&_popup=1'

    verificacao, _ = _next_do_redirect(client.get(protegida))
    resposta = client.post(verificacao, {'code': CODIGO_2FA_EMAIL})

    assert resposta.status_code == 302
    assert resposta['Location'] == protegida


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_codigo_por_email_nao_redireciona_para_outro_host(client) -> None:
    servidor = _servidor_com_email_pessoal()
    client.force_login(servidor.get_user())
    client.get(f'/comum/atualizar_email_secundario/{servidor.get_vinculo().pk}/')  # gera o código

    resposta = client.post(f'/djtools/two_factor_authentication/?{urlencode({"next": "https://malicioso.exemplo/"})}', {'code': CODIGO_2FA_EMAIL})

    assert resposta.status_code == 302
    assert resposta['Location'] == '/'
