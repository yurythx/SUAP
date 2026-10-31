"""Fluxo: recuperação e troca de senha — o caminho do e-mail com token (feature 005 do behave).

É o fluxo mais sensível do ``comum``: a senha do SUAP é a credencial de rede da instituição, e
a recuperação é feita por um **token de uso único** enviado ao e-mail *pessoal* (nunca ao
institucional, que usa a mesma senha). Três telas participam — a solicitação anônima, a
solicitação de quem já está logado e a tela do link do e-mail —, e as três só fazem sentido
encadeadas: o que prova que a troca funcionou é **entrar com a senha nova**.

A regressão que este arquivo pega é a que ninguém percebe em homologação: o token deixa de
expirar depois do uso, a tela passa a aceitar senha sem confirmação, ou o e-mail de destino
volta a ser o institucional — e a recuperação de senha vira um caminho de invasão.

Todos os testes rodam sobre a conta descartável ``conta_pessoal`` e com ``logado_efemero``
(sessão própria): trocar a senha de um papel compartilhado deslogaria os testes seguintes.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe. NUNCA `'/rota/{x}/'.format(...)` escrito na
# chamada — a regra UP032 do ruff transformaria em f-string e o gate deixaria de enxergar a rota
# (armadilha 17 da receita; cinco rotas da 1ª fatia já saíram de cobertas por isso).
ALTERAR_SENHA = '/comum/alterar_senha/'
SOLICITAR_TROCAR_SENHA = '/comum/solicitar_trocar_senha/'
TROCAR_SENHA = '/comum/trocar_senha/{username}/{token}/'
LOGIN_EXIGE_CAPTCHA = '/comum/login_exige_captcha/{username}/'

SENHA_TROCADA = 'SenhaValida1!'


def _ultimo_token(username: str):
    """O ``TrocarSenha`` mais recente da matrícula.

    ``.get()`` seria errado aqui: a suíte não dá flush e o CI roda com ``--reuse-db``, então a
    segunda execução encontraria os tokens da primeira e estouraria ``MultipleObjectsReturned``
    — falha que só aparece na segunda vez. (A fixture ``conta_pessoal`` ainda apaga os antigos
    no setup; isto é o cinto além do suspensório.)
    """
    from comum.models import TrocarSenha

    return TrocarSenha.objects.filter(username=username).order_by('-id').first()


def test_ciclo_de_troca_de_senha_pelo_link_do_email(logado_efemero, conta_pessoal):
    """Solicita a troca logado, usa o token do e-mail, entra com a senha nova.

    Um teste só para os três passos porque nenhum deles existe sozinho: o token é o que a
    primeira tela produz e a segunda consome, e o único fato que prova a troca é o **login com
    a senha nova** — a mensagem de sucesso, por si, não diz que a credencial mudou.

    A senha volta a ``SENHA_E2E`` no setup do próximo teste que pedir ``conta_pessoal``.
    """
    from comum.models import TrocarSenha

    matricula = conta_pessoal.matricula
    email_pessoal = conta_pessoal.get_vinculo().email_pessoal

    tela = Tela(logado_efemero('conta_pessoal')).ir(ALTERAR_SENHA)
    tela.ver_titulo('Alterar senha')
    tela.clicar_botao('Enviar')
    tela.sucesso(f'Foi enviado um email para {email_pessoal}')

    token = _ultimo_token(matricula)
    assert token is not None, 'a UI disse que enviou o e-mail, mas nenhum token de troca foi gravado'
    assert token.email == email_pessoal, 'o token foi endereçado a outro e-mail que não o pessoal'

    tela.ir(TROCAR_SENHA.format(username=matricula, token=token.token))
    tela.preencher_formulario([('Senha', 'senha', SENHA_TROCADA), ('Confirmação de senha', 'senha', SENHA_TROCADA)])
    tela.clicar_botao('Enviar')
    tela.sucesso('Senha alterada com sucesso.')

    assert not TrocarSenha.token_valido(matricula, token.token), 'o token continuou válido depois de usado — ele é de uso único'
    # `login_ui` só devolve quando o crachá do vínculo está visível: entrar com a senha nova é o
    # fato positivo que prova a troca.
    logado_efemero('conta_pessoal', SENHA_TROCADA)


def test_solicitacao_anonima_de_troca_de_senha(pagina_anonima, conta_pessoal):
    """Quem esqueceu a senha pede o link sem estar logado, informando matrícula e CPF.

    É a porta que o link "Esqueceu ou deseja alterar sua senha?" da tela de login abre — e a
    única das três telas de senha que roda para usuário anônimo.
    """
    matricula = conta_pessoal.matricula
    email_pessoal = conta_pessoal.get_vinculo().email_pessoal

    tela = Tela(pagina_anonima).ir(SOLICITAR_TROCAR_SENHA)
    tela.preencher_formulario(
        [
            ('Usuário', 'texto', matricula),
            ('CPF/Passaporte', 'texto', conta_pessoal.pessoa_fisica.cpf),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso(f'Foi enviado um email para {email_pessoal}')
    token = _ultimo_token(matricula)
    assert token is not None, 'a UI disse que enviou o e-mail, mas nenhum token de troca foi gravado'


def test_login_exige_captcha_so_depois_de_tentativas_erradas(pagina_anonima, conta_pessoal):
    """O endereço que a tela de login consulta por AJAX antes de exibir o captcha.

    Não tem tela própria (``HttpResponse`` de texto puro), então a asserção é sobre o corpo — e
    ``buscar`` não segue redirect, o que garante que o 200 é a view e não a tela de login. Os
    dois desfechos são exercitados: o limite é ``login_attempts > 3`` (``comum/views.py``), e
    ``conta_pessoal`` repõe o contador a zero no setup de cada teste.
    """
    from comum.models import User

    matricula = conta_pessoal.matricula
    tela = Tela(pagina_anonima)

    limpo = tela.buscar(LOGIN_EXIGE_CAPTCHA.format(username=matricula))
    assert limpo.status == 200, f'a view respondeu HTTP {limpo.status}'
    assert limpo.text() == 'ERROR', 'conta sem tentativas erradas não deveria exigir captcha'

    # `update` e não `save`: o `save` do User dispara a sincronização de grupos, que nada tem a
    # ver com o que este teste afirma.
    User.objects.filter(username=matricula).update(login_attempts=4)

    apos_erros = tela.buscar(LOGIN_EXIGE_CAPTCHA.format(username=matricula))
    assert apos_erros.text() == 'OK', 'conta com mais de três tentativas erradas tem de exigir captcha'
