"""Fatia 2 da doc de usuário do ``comum`` — autenticação e conta pessoal.

Cobre o que **todo** usuário do SUAP faz com a própria conta: a ``Minha conta``, a troca de
senha (logado e pela porta de quem esqueceu), a verificação em duas etapas, os dispositivos e
as sessões em que a conta está aberta e as senhas vazadas. Só a última tem um segundo público
— quem cuida da segurança da informação vê os registros de todo mundo, e não só os seus.

Cada teste é o roteiro de UMA tarefa da doc, na ordem em que ela as apresenta; as asserções
existem para a rodada falhar alto quando a tela muda de forma, e as ``anotar`` despejam
rótulos/opções que a redação copia em vez de deduzir de ``views.py``.

**A regra desta fatia**: ela destrói o estado da conta que usa — troca a senha, habilita o 2FA,
derruba a sessão. Por isso nada aqui abre um papel por ``logado_comum``, que entrega uma página
autenticada por ``storage_states`` (UM login por matrícula para a sessão inteira do pytest): os
fluxos rodam sobre as contas descartáveis ``conta_pessoal``/``conta_dois_fatores``, por
``logado_efemero``, e as fixtures repõem o estado no **setup** — o banco da doc é reusado pelas
fatias 3 a 6 e uma rodada interrompida no meio não pode deixar uma conta com a senha trocada.
"""

from __future__ import annotations

import time

import onetimepass
import pytest

from comum.tests.doc.conftest import NOME_CELULAR_DOC, NOME_DISPOSITIVO_DOC, SENHA_VAZADA_DOC, anotar
from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LOGIN = '/'
MINHA_CONTA = '/comum/minha_conta/'
MINHAS_ACOES = '/comum/minhas_acoes_suap/'
LOGOUT = '/comum/logout/'
ALTERAR_SENHA = '/comum/alterar_senha/'
SOLICITAR_TROCAR_SENHA = '/comum/solicitar_trocar_senha/'
TROCAR_SENHA = '/comum/trocar_senha/{username}/{token}/'
HABILITAR_2FA = '/comum/habilitar_2fa_suap/'
VALIDAR_QRCODE_2FA = '/comum/validar_qrcode_2fa_otp/'
DESABILITAR_2FA_USUARIO = '/comum/desabilitar_2fa_usuario/{usuario}/'
ADMIN_USUARIOS = '/admin/comum/user/'
DISPOSITIVOS = '/admin/comum/device/'
SESSOES = '/admin/comum/sessioninfo/'
SENHAS_EXPOSTAS = '/admin/comum/senhaexposta/'
WEBMAIL = '/comum/webmail/'

# Senha que o fluxo de troca grava. A conta volta a `SENHA_E2E` no setup do próximo teste que
# pedir `conta_pessoal` (`_repor_conta`, no conftest do e2e).
SENHA_NOVA = 'SenhaValida1!'
# Curta de propósito: é o que provoca a recusa da tela, cuja mensagem a doc cita ao pé da letra.
SENHA_CURTA = 'abc123'

LINK_DA_TELA_DE_LOGIN = 'Esqueceu ou deseja alterar sua senha?'
# Apelido que o usuário dá ao próprio dispositivo — passa a ser o nome dele nas duas listagens.
APELIDO_DOC = 'Meu notebook'


def _codigo_otp(segredo: str) -> str:
    """Um TOTP válido para o segredo, com margem para o submit chegar na mesma janela.

    O código vale 30 segundos; gerá-lo no fim da janela e submetê-lo já na seguinte daria uma
    falha intermitente de poucos por cento. O zero à esquerda importa: ``get_totp`` devolve int.
    """
    restante = 30 - (time.time() % 30)
    if restante < 5:
        time.sleep(restante)
    return f'{onetimepass.get_totp(segredo):06d}'


def _chave_da_sessao(pagina) -> str:
    """O ``session_key`` da página autenticada, lido do cookie do contexto."""
    from django.conf import settings

    cookies = [c for c in pagina.context.cookies() if c['name'] == settings.SESSION_COOKIE_NAME]
    assert cookies, f'a página não tem cookie de sessão ({settings.SESSION_COOKIE_NAME})'
    return cookies[0]['value']


def _texto_da_pagina(tela: Tela) -> str:
    """Todo o texto visível do corpo da tela — para afirmar o que NÃO está lá."""
    return ' '.join(tela.pagina.locator('//main').all_inner_texts())


def test_minha_conta_e_saida_do_sistema(logado_efemero, conta_pessoal, duplo_fator_habilitado, webmail_configurado, capturar):
    """Tarefa 7 — o painel da conta, o histórico de ações e a saída do sistema.

    É a porta de todas as outras tarefas desta fatia: a troca de senha, o 2FA e as sessões só
    são alcançáveis pelo usuário a partir daqui. O bloco da verificação em duas etapas depende
    da ``Configuracao`` que ``duplo_fator_habilitado`` liga — sem ela a doc estaria ilustrando
    uma porta que o usuário não vê.

    Termina saindo do sistema porque *Sair* é o último botão da própria tela, e porque a saída
    só é afirmável numa sessão descartável.
    """
    from comum.models import SessionInfo

    pagina = logado_efemero('conta_pessoal')
    chave = _chave_da_sessao(pagina)

    tela = Tela(pagina).ir(MINHA_CONTA)
    tela.ver_titulo('Minha conta')
    anotar('minha-conta', tela)
    capturar(pagina, 'minha-conta')

    # Os três botões da barra de ações e o bloco do 2FA são o que a doc promete nesta tela.
    tela.ver_botao('Alterar senha')
    tela.ver_botao('Alterar emails')
    tela.ver_botao('Sair do sistema')
    tela.ver_texto('Verificação em duas etapas')
    tela.ver_botao('Habilitar autenticação com dois fatores')

    # "Minhas ações" é um dos atalhos em círculo do topo; o clique é o que prova que ele leva lá.
    tela.clicar_link('Minhas ações')
    tela.esperar()
    assert MINHAS_ACOES in tela.pagina.url, f'o atalho "Minhas ações" não levou ao histórico: {tela.pagina.url}'
    tela.ver_texto('Utilize o filtro para buscar')
    anotar('minhas-acoes', tela)
    tela.clicar_botao('Enviar')
    # Vazio por construção: quem publica ação aqui são os OUTROS apps do SUAP, e montar o
    # domínio de um deles no seed do `comum` inverteria a dependência entre os apps.
    tela.ver_texto('Nenhuma ação foi encontrada para o período passado.')
    capturar(tela.pagina, 'minhas-acoes')

    # O atalho do webmail é a única entrada de menu desta fatia SEM tela própria: ele resolve a
    # `Configuracao` da instituição e encaminha. Sem este passo a frase da doc sobre ele seria
    # afirmação lida de `views.py`.
    resposta = tela.buscar(WEBMAIL)
    assert resposta.status == 302, f'o atalho do webmail devolveu HTTP {resposta.status} em vez do encaminhamento'
    assert resposta.headers['location'] == webmail_configurado, 'o atalho apontou para um endereço diferente do configurado'

    # Sair — o botão traz `data-confirm`, isto é, um `confirm()` nativo (`comum/js/main.js:459`),
    # que o handler de diálogo de `logado_efemero` aceita.
    tela.ir(MINHA_CONTA)
    tela.clicar_botao('Sair do sistema')
    tela.ver_texto(LINK_DA_TELA_DE_LOGIN)
    assert SessionInfo.objects.get(session_id=chave).expired, 'a tela voltou ao login, mas a sessão continuou ativa no banco'


def test_trocar_a_senha(logado_efemero, pagina_anonima, conta_pessoal, capturar):
    """Tarefa 8 — pedir o link por e-mail, escolher a senha nova e entrar com ela.

    As três telas num teste só porque nenhuma existe sozinha: o token é o que a primeira produz
    e a segunda consome, e o único fato que prova a troca é o **login com a senha nova** — a
    mensagem de sucesso, por si, não diz que a credencial mudou.

    A recusa da senha curta é provocada de propósito: a doc cita a mensagem ao pé da letra, e
    citar o número certo seria impossível de deduzir do código (``comum/forms.py:2348-2349``
    recusa menos de 8 caracteres numa mensagem que fala em 10).
    """
    from comum.models import TrocarSenha

    matricula = conta_pessoal.matricula
    email_pessoal = conta_pessoal.get_vinculo().email_pessoal

    tela = Tela(logado_efemero('conta_pessoal')).ir(MINHA_CONTA)
    tela.clicar_botao('Alterar senha')
    tela.esperar()
    assert ALTERAR_SENHA in tela.pagina.url, f'o botão da Minha conta não levou à solicitação de troca: {tela.pagina.url}'
    tela.ver_titulo('Alterar senha')
    anotar('senha-solicitar', tela)
    capturar(tela.pagina, 'senha-solicitar')
    tela.clicar_botao('Enviar')

    tela.sucesso(f'Foi enviado um email para {email_pessoal}')
    token = TrocarSenha.objects.filter(username=matricula).order_by('-id').first()
    assert token is not None, 'a UI disse que enviou o e-mail, mas nenhum token de troca foi gravado'
    # O destino é o e-mail PESSOAL, nunca o institucional — que usa a mesma senha do SUAP.
    assert token.email == email_pessoal, 'o token foi endereçado a outro e-mail que não o pessoal'

    # A tela do link do e-mail. Aberta sem sessão, que é como ela chega a quem esqueceu a senha.
    tela = Tela(pagina_anonima).ir(TROCAR_SENHA.format(username=matricula, token=token.token))
    anotar('senha-nova', tela)
    capturar(tela.pagina, 'senha-nova')

    # Senha curta: a recusa é a regra que a doc afirma.
    tela.preencher_formulario([('Senha', 'senha', SENHA_CURTA), ('Confirmação de senha', 'senha', SENHA_CURTA)])
    tela.clicar_botao('Enviar')
    # `erro` e não `erros_na_tela`: aquele é um instantâneo sem espera, e o `clicar_botao`
    # devolve com o POST ainda em voo — a leitura cai no documento ANTIGO, que não tem erro
    # nenhum. Era a causa do flake que consumia as duas retentativas do `gerar-doc`.
    tela.erro('10 caracteres')

    tela.preencher_formulario([('Senha', 'senha', SENHA_NOVA), ('Confirmação de senha', 'senha', SENHA_NOVA)])
    tela.clicar_botao('Enviar')
    tela.sucesso('Senha alterada com sucesso.')
    assert not TrocarSenha.token_valido(matricula, token.token), 'o token continuou válido depois de usado — ele é de uso único'

    # `login_ui` só devolve quando o crachá do vínculo está visível: entrar com a senha nova é o
    # fato positivo que prova a troca.
    logado_efemero('conta_pessoal', SENHA_NOVA)


def test_recuperar_a_senha_sem_conseguir_entrar(pagina_anonima, conta_pessoal, capturar):
    """Tarefa 8, variante — a porta de quem não consegue entrar, a partir da tela de login.

    Separada do teste acima porque parte de outro lugar (a tela de login, sem sessão) e porque
    o passo que a doc descreve é o **clique no link**, não o endereço: ele é o único caminho
    que o usuário tem para cá.
    """
    from comum.models import TrocarSenha

    matricula = conta_pessoal.matricula
    email_pessoal = conta_pessoal.get_vinculo().email_pessoal

    tela = Tela(pagina_anonima).ir(LOGIN)
    tela.clicar_link(LINK_DA_TELA_DE_LOGIN)
    tela.esperar()
    assert SOLICITAR_TROCAR_SENHA in tela.pagina.url, f'o link da tela de login não levou à recuperação de senha: {tela.pagina.url}'
    anotar('senha-esqueci', tela)
    tela.preencher_formulario([('Usuário', 'texto', matricula), ('CPF/Passaporte', 'texto', conta_pessoal.pessoa_fisica.cpf)])
    capturar(tela.pagina, 'senha-esqueci')
    tela.clicar_botao('Enviar')

    tela.sucesso(f'Foi enviado um email para {email_pessoal}')
    assert TrocarSenha.objects.filter(username=matricula).exists(), 'a UI disse que enviou o e-mail, mas nenhum token de troca foi gravado'


def test_verificacao_em_duas_etapas(logado_efemero, conta_dois_fatores, duplo_fator_habilitado, capturar):
    """Tarefa 9 — habilitar a verificação em duas etapas, revisitar o QR Code e remover.

    As três telas são degraus do mesmo estado: a de habilitação é a que **cria o segredo**, a de
    validação exige o 2FA já ativo e a remoção só tem o que remover depois das duas.

    O código é calculado a partir do segredo que a tela acabou de gravar — exatamente o que o
    aplicativo autenticador faz ao ler o QR Code. E o login acontece **antes** de o 2FA ficar
    ativo: com a ``Configuracao`` ligada, relogar passaria a exigir o código na tela de entrada.
    """
    from comum.models import AutenticacaoDoisFatores

    user = conta_dois_fatores.get_user()
    tela = Tela(logado_efemero('conta_dois_fatores')).ir(MINHA_CONTA)
    tela.clicar_botao('Habilitar autenticação com dois fatores')
    tela.esperar()
    assert HABILITAR_2FA in tela.pagina.url, f'o botão da Minha conta não levou à habilitação do 2FA: {tela.pagina.url}'
    tela.ver_titulo('Habilitar Autenticação por Dois Fatores')
    anotar('2fa-habilitar', tela)
    capturar(tela.pagina, '2fa-habilitar')

    # O GET acima é quem cria o registro (e o segredo) — antes dele não há o que ler.
    registro = AutenticacaoDoisFatores.objects.get(usuario=user)
    assert registro.otp_secret_user, 'a tela abriu sem gerar o segredo do aplicativo autenticador'

    tela.preencher('Codigo', 'texto', _codigo_otp(registro.otp_secret_user))
    tela.clicar_botao('Enviar')
    tela.sucesso('A autenticação por Dois Fatores está habilitada.')
    registro.refresh_from_db()
    assert registro.ativo, 'a UI disse que habilitou, mas o registro continuou inativo'
    assert registro.validou_qrcode(), 'a UI disse que habilitou, mas o QR Code não consta validado'

    # De volta à Minha conta, o bloco do 2FA troca de botões: some o de habilitar, aparecem o
    # interruptor, o "Visualizar QR Code" e a remoção. É o estado que a doc descreve.
    tela.ir(MINHA_CONTA)
    tela.ver_botao('Visualizar QR Code')
    tela.ver_botao('Remover autenticação com dois fatores')
    capturar(tela.pagina, '2fa-minha-conta')

    tela.clicar_botao('Visualizar QR Code')
    tela.esperar()
    assert VALIDAR_QRCODE_2FA in tela.pagina.url, f'o botão não levou à revisita do QR Code: {tela.pagina.url}'
    tela.ver_titulo('Validar Autenticação por Dois Fatores')
    anotar('2fa-qrcode', tela)
    capturar(tela.pagina, '2fa-qrcode')
    tela.preencher('Codigo', 'texto', _codigo_otp(registro.otp_secret_user))
    tela.clicar_botao('Enviar')
    tela.sucesso('A autenticação por Dois Fatores está ativida.')

    tela.ir(MINHA_CONTA)
    tela.clicar_botao('Remover autenticação com dois fatores')
    tela.sucesso('Autenticação com dois fatores removida com sucesso')
    assert not AutenticacaoDoisFatores.objects.filter(usuario=user).exists(), 'a UI disse que removeu, mas o registro persistiu'


def test_desabilitar_a_verificacao_de_outra_pessoa(logado_comum, conta_dois_fatores, capturar):
    """Tarefa 9, saída de emergência — quem perdeu o aparelho não consegue mais entrar sozinho.

    A porta é do superusuário e vive na listagem de usuários do sistema: o botão *Desabilitar
    2FA* só é renderizado para superusuário e só quando o alvo tem a verificação ativa
    (``comum/admin.py:1715-1730``). Aqui o estado é montado por ORM porque o ciclo que o produz
    já é a tarefa 9, e refazê-lo custaria a habilitação inteira de novo.
    """
    from datetime import datetime

    from comum.models import AutenticacaoDoisFatores

    user = conta_dois_fatores.get_user()
    AutenticacaoDoisFatores.objects.create(usuario=user, tipo=AutenticacaoDoisFatores.OTP, ativo=True, data_ultima_ativacao=datetime.now())
    rota = DESABILITAR_2FA_USUARIO.format(usuario=user.pk)

    # A guarda é metade da tela: desabilitar o 2FA alheio é remover a segunda barreira da conta
    # de outra pessoa. Quem não é superusuário leva 403 na mesma URL.
    negado = Tela(logado_comum('solicitante')).buscar(rota)
    assert negado.status == 403, f'servidor comum deveria levar 403 na desabilitação de 2FA alheio, veio {negado.status}'

    tela = Tela(logado_comum('admin')).ir(f'{ADMIN_USUARIOS}?q={user.username}')
    tela.linha(user.username).clicar_botao('Desabilitar 2FA')
    tela.esperar()
    assert rota in tela.pagina.url, f'o botão da listagem de usuários não levou à desabilitação: {tela.pagina.url}'
    tela.ver_titulo(f'Desabilitar 2FA - {user}')
    anotar('2fa-desabilitar', tela)
    tela.preencher('Motivo', 'textarea', 'Servidor perdeu o aparelho com o aplicativo autenticador.')
    capturar(tela.pagina, '2fa-desabilitar')
    tela.clicar_botao('Desabilitar 2FA')

    tela.sucesso(f'Autenticação com dois fatores removida para {user.username}')
    assert not AutenticacaoDoisFatores.objects.filter(usuario=user).exists(), 'a UI disse que desabilitou, mas o registro persistiu'


def test_dispositivos_e_sessoes(logado_efemero, conta_pessoal, acessos_pessoais, capturar):
    """Tarefa 10 — ver onde a conta está aberta, apelidar, desativar e derrubar sessões.

    É a única ferramenta de resposta a incidente que o usuário comum tem, e a que só se descobre
    quebrada quando já era preciso. O recorte "você vê só os seus acessos" é **observado**, e não
    lido do ``get_queryset``: a fixture põe um dispositivo de outra pessoa no banco e o teste
    afirma que ele não aparece.

    A ordem dos passos é ditada pelo efeito colateral, não pela estética: desativar o dispositivo
    expira **todas** as sessões dele, então o "Deslogar" individual da tela de sessões roda sobre
    o *outro* dispositivo do dono. Trocar a ordem faria o teste clicar num botão que o admin já
    teria escondido (sessão expirada não oferece ação).
    """
    from comum.models import Device, SessionInfo

    acessos = acessos_pessoais
    pagina = logado_efemero('conta_pessoal')
    chave_atual = _chave_da_sessao(pagina)

    tela = Tela(pagina).ir(DISPOSITIVOS)
    tela.ver_titulo('Dispositivos')
    tela.ver_texto(NOME_DISPOSITIVO_DOC)
    assert acessos.alheio.friendly_name not in _texto_da_pagina(tela), (
        'a listagem mostrou o dispositivo de outra pessoa a quem não é da segurança da informação'
    )
    # O dispositivo em uso é identificado na coluna Situação e NÃO oferece "Desativar"
    # (`DeviceAdmin.acoes`): é o que a doc avisa ao leitor.
    tela.ver_texto('Dispositivo Atual')
    anotar('dispositivos', tela)
    capturar(pagina, 'dispositivos')

    # `class="btn popup"` no `acoes` do admin: apelidar abre num fancybox em iframe.
    tela.linha(NOME_DISPOSITIVO_DOC).clicar_botao('Apelidar')
    popup = tela.popup()
    anotar('dispositivo-apelidar', popup)
    popup.preencher('Apelido', 'texto', APELIDO_DOC)
    capturar(pagina, 'dispositivo-apelidar')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Apelido concedido com sucesso.')
    assert Device.objects.get(pk=acessos.notebook.pk).nickname == APELIDO_DOC, 'a UI disse que salvou, mas o apelido não persistiu'

    # A partir daqui o dispositivo é identificado pelo APELIDO: `Device.get_name` prefere o
    # apelido ao nome detectado, nas duas listagens.
    tela.ir(DISPOSITIVOS)
    tela.linha(APELIDO_DOC).clicar_botao('Desativar')
    tela.sucesso('Dispositivo desativado')
    assert not Device.objects.get(pk=acessos.notebook.pk).activated, 'a UI disse que desativou, mas o dispositivo continuou ativo'
    assert SessionInfo.objects.get(pk=acessos.sessao_notebook.pk).expired, 'o dispositivo foi desativado, mas a sessão aberta nele sobreviveu'

    tela.ir(DISPOSITIVOS)
    tela.linha(APELIDO_DOC).clicar_botao('Reativar')
    tela.sucesso('Dispositivo reativado.')
    assert Device.objects.get(pk=acessos.notebook.pk).activated, 'a UI disse que reativou, mas o dispositivo continuou desativado'

    # Etapa 2 — as sessões. A do teste é a "Sessão atual" e não traz o botão de deslogar.
    tela.ir(SESSOES)
    tela.ver_titulo('Informações de Sessões')
    tela.ver_texto('Sessão atual')
    assert acessos.alheio.friendly_name not in _texto_da_pagina(tela), (
        'a listagem mostrou a sessão de outra pessoa a quem não é da segurança da informação'
    )
    anotar('sessoes', tela)
    capturar(pagina, 'sessoes')

    tela.linha(NOME_CELULAR_DOC).clicar_botao('Deslogar')
    tela.sucesso('Sessão remota deslogada com sucesso.')
    assert SessionInfo.objects.get(pk=acessos.sessao_celular.pk).expired, 'a UI disse que deslogou, mas a sessão continuou ativa'

    # A ação em lote da barra preserva a própria sessão — metade do que ela faz, e o que se
    # perderia numa regressão silenciosa (quem clicasse seria deslogado junto).
    tela.ir(SESSOES)
    tela.clicar_botao('Deslogar todas as outras sessões')
    tela.sucesso('Sessões remotas deslogadas com sucesso.')
    assert not SessionInfo.objects.get(session_id=chave_atual).expired, 'a ação derrubou a própria sessão de quem a executou'


def test_senhas_expostas(logado_efemero, conta_pessoal, senhas_expostas, capturar):
    """Tarefa 11 — as senhas da conta que apareceram em vazamentos conhecidos.

    Listagem de consulta apenas: o admin nega adicionar, alterar e remover
    (``SenhaExpostaAdmin.has_*_permission``). O recorte por dono é observado, como na tarefa 10.
    """
    do_dono, alheia = senhas_expostas

    tela = Tela(logado_efemero('conta_pessoal')).ir(SENHAS_EXPOSTAS)
    tela.ver_titulo('Senhas Expostas')
    tela.ver_texto(SENHA_VAZADA_DOC)
    assert alheia.senha not in _texto_da_pagina(tela), 'a listagem mostrou a senha exposta de outra pessoa a quem não é da segurança da informação'
    # Quem não consulta as contas alheias não ganha sequer a coluna "Usuário"
    # (`SenhaExpostaAdmin.get_list_display`).
    assert do_dono.email in _texto_da_pagina(tela), 'a listagem não trouxe o e-mail em que a senha apareceu'
    anotar('senhas-expostas', tela)
    capturar(tela.pagina, 'senhas-expostas')

    # Consulta e nada mais: não há como adicionar registro daqui. O rótulo é o do admin do SUAP
    # ("Adicionar <nome do cadastro>") — "Adicionar" cru bateria no "Adicionar atalho" da barra,
    # que toda tela tem.
    assert 'Adicionar Senha Exposta' not in ' '.join(tela.botoes_na_tela()), 'a listagem de senhas expostas ofereceu adição'


def test_a_senha_volta_ao_padrao_para_as_fatias_seguintes(conta_pessoal, conta_dois_fatores):
    """Guarda da fatia: as contas que estes fluxos destroem voltam ao estado inicial.

    Não é tarefa nenhuma da doc — é a asserção de que a fatia não envenenou o banco reusado. As
    duas fixtures repõem no **setup**; este teste roda por último no arquivo e afirma o efeito.
    """
    from comum.models import AutenticacaoDoisFatores, Configuracao

    for servidor in (conta_pessoal, conta_dois_fatores):
        assert servidor.get_user().check_password(SENHA_E2E), f'{servidor.matricula} ficou com a senha trocada'
        assert not AutenticacaoDoisFatores.objects.filter(usuario=servidor.get_user()).exists(), f'{servidor.matricula} ficou com 2FA ativo'

    # Pela LINHA e não por `get_valor_por_chave`: aquele caminho lê `_CONFIGURACAO_CACHED`, que o
    # próprio `update_or_create` da reposição acabou de limpar — a asserção passaria por
    # construção, sem dizer nada sobre o que as fatias 3 a 6 vão encontrar no banco.
    configuracao = Configuracao.objects.filter(app='comum', chave='permite_autenticacao_duplo_fator').first()
    assert not (configuracao and configuracao.valor), (
        'a verificação em duas etapas ficou ligada na configuração — as demais fatias veriam outra Minha conta'
    )
