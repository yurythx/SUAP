"""Fluxo: as telas que o próprio servidor abre para si — biometria, fiscal de concurso e calendário.

Três serviços que o servidor alcança pelo seu menu, sem passar por ninguém: pedir o autocadastro
da biometria (para cadastrar o dedo no terminal de ponto sem ir à Gestão de Pessoas), inscrever-se
como fiscal do concurso público e consultar o calendário administrativo do campus.

São telas de baixo tráfego e alta consequência — quebram sem ninguém notar, até o dia em que o
servidor precisa delas. A regressão que o arquivo pega é a do **desvio silencioso**: as três
respondem ``httprr`` com status 200 no caminho de falha, de modo que só a asserção positiva
(a solicitação gravada, o formulário renderizado, o evento desenhado no calendário) distingue a
tela que funciona da tela que redirecionou com um aviso.
"""

from __future__ import annotations

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
SOLICITAR_AUTOCADASTRO = '/comum/solicitar_autocadastro/'
REENVIAR_AUTOCADASTRO = '/comum/solicitar_autocadastro/reenviar/{pk}/'
FISCAL_CONCURSO = '/comum/fiscal_concurso/'
CALENDARIO_ADMINISTRATIVO = '/comum/calendario_administrativo/'


def test_solicitar_autocadastro_de_biometria_e_reenviar_o_codigo(logado_comum, biometria_do_zero):
    """Pedir o autocadastro e reenviar o código — as duas rotas num teste, porque a segunda vive da primeira.

    Encadeadas (regra 1 da receita): não há o que reenviar antes de solicitar, e o ``pk`` da rota
    de reenvio é o da solicitação que a primeira tela acabou de gravar.

    A confirmação é por senha real (``PasswordField`` autentica contra o usuário do threadlocal),
    porque o código gerado aqui vale como credencial no terminal de ponto: quem o obtém cadastra
    o próprio dedo no lugar do servidor.

    A asserção dos dois passos é o **e-mail**, e não a mensagem (#17397: o pedido respondia
    "verifique seu e-mail." sem enviar nada): ``enviar_email`` devolve ``False`` em
    silêncio quando o vínculo não tem endereço ou a solicitação já expirou
    (``rh/models/seguranca/biometria.py:107-120``), e a view responde "O código de autorização foi
    reenviado." de qualquer forma. Sob pytest, ``djtools.utils.send_mail`` cai em
    ``django_send_mail`` (``djtools/utils/email.py:256-257``) e o ``live_server`` roda no mesmo
    processo, então ``mail.outbox`` é o do teste.
    """
    from django.core import mail

    from rh.models import BiometriaSolicitacao

    dono = biometria_do_zero

    tela = Tela(logado_comum('solicitante')).ir(SOLICITAR_AUTOCADASTRO)
    tela.ver_titulo('Solicitação de autocadastro de biometria')
    tela.preencher_formulario([('Senha para confirmação', 'senha', SENHA_E2E), ('Confirma a solicitação', 'checkbox', 'marcar')])
    enviados_antes = len(mail.outbox)
    tela.clicar_botao('Enviar')
    tela.sucesso('Solicitação realizada, verifique seu e-mail.')

    solicitacao = BiometriaSolicitacao.objects.filter(pessoa_fisica=dono.pessoa_fisica).order_by('-id').first()
    assert solicitacao, 'a UI disse que solicitou, mas a solicitação de biometria não persistiu'
    codigo = solicitacao.codigo_verificacao
    assert codigo.isdigit(), f'a solicitação nasceu com um código que não é numérico: {codigo!r}'
    assert len(codigo) == 6, f'a solicitação nasceu com um código de {len(codigo)} dígitos; o terminal espera 6'
    assert solicitacao.ativo, 'a solicitação nasceu já expirada ou já utilizada'
    assert len(mail.outbox) == enviados_antes + 1, 'a UI disse "verifique seu e-mail", mas nenhum e-mail saiu'
    assert codigo in mail.outbox[-1].body, 'o e-mail da solicitação saiu sem o código de verificação'

    enviados_antes = len(mail.outbox)
    tela.ir(REENVIAR_AUTOCADASTRO.format(pk=solicitacao.pk))
    tela.sucesso('O código de autorização foi reenviado.')

    assert len(mail.outbox) == enviados_antes + 1, 'a UI disse que reenviou o código, mas nenhum e-mail saiu'
    mensagem = mail.outbox[-1]
    assert mensagem.to == [dono.get_vinculo().email_notificacao], f'o código foi para {mensagem.to}, e não para o e-mail de notificação do vínculo'
    assert solicitacao.codigo_verificacao in mensagem.body, 'o e-mail de reenvio saiu sem o código de verificação'


def test_inscricao_de_fiscal_de_concurso_abre_uma_vez_so(logado_comum, inscricao_fiscal_limpa):
    """O servidor se inscreve pela tela, e o formulário some para quem já se inscreveu.

    Os dois desfechos num teste porque o segundo é consequência do primeiro: a view abre com
    ``if InscricaoFiscal.objects.filter(servidor=servidor)`` e redireciona com "Sua inscrição já
    foi realizada.". É o que impede a dupla inscrição.

    A asserção do envio é o **banco**: a inscrição tem de ficar em nome de quem está logado,
    porque o ``servidor`` não é campo do formulário — entra pela instância na view (#17396).

    A limpeza no setup (``inscricao_fiscal_limpa``) é o que torna a primeira metade repetível: sem
    ela, a segunda execução da suíte já entraria pelo desvio.
    """
    from comum.models import InscricaoFiscal

    servidor = inscricao_fiscal_limpa

    tela = Tela(logado_comum('solicitante')).ir(FISCAL_CONCURSO)
    tela.ver_titulo('Inscrição para fiscal do Concurso Público')
    tela.preencher_formulario(
        [('Número de filhos menores de 21 anos', 'número', '2'), ('Data do início do serviço na Instituição', 'data', '01/03/2019')]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Inscrição realizada com sucesso.')

    inscricao = InscricaoFiscal.objects.filter(servidor=servidor).first()
    assert inscricao, 'a UI disse que inscreveu, mas a inscrição não persistiu para o servidor logado'
    assert inscricao.numero_filhos_menores_21_anos == 2, f'gravou {inscricao.numero_filhos_menores_21_anos} filhos em vez de 2'

    tela.ir(FISCAL_CONCURSO)
    tela.sucesso('Sua inscrição já foi realizada.')


def test_calendario_administrativo_desenha_o_cronograma_da_folha(logado_comum, cronograma_da_folha, campus_e2e):
    """O calendário do ano corrente, com os eventos que o servidor precisa ver desenhados nele.

    A asserção é o **evento**, não a moldura: a view monta um ``Calendario`` e vai empilhando
    eventos de quatro origens conforme os apps instalados e o perfil de quem olha
    (``comum/views.py:3812-3878``). Um calendário que abre e não desenha nada é o desfecho de
    qualquer uma dessas quatro coletas ter parado de casar — e ele abre com status 200,
    bonito e vazio.

    O filtro também é exercitado: escolher o ano e o campus reenvia o formulário
    (``CalendarioForm``), e é por ele que o servidor consulta o calendário de outra unidade.

    ``ano_corrente`` (via ``cronograma_da_folha``) não é conforto: a view faz
    ``Ano.objects.filter(ano=date.today().year).first()`` e usa ``ano.ano`` sem guarda — num
    banco sem a linha do ano, esta tela é um 500 de ``AttributeError``.
    """
    ano = cronograma_da_folha.ano.ano

    tela = Tela(logado_comum('solicitante')).ir(CALENDARIO_ADMINISTRATIVO)
    tela.ver_titulo('Calendário Administrativo por Campus')
    tela.ver_texto('Consulta da Prévia da Folha')

    tela.preencher_formulario([('Ano', 'lista', str(ano)), ('Unidade Organizacional', 'lista', str(campus_e2e))])
    tela.clicar_botao('Enviar')

    tela.ver_titulo('Calendário Administrativo por Campus')
    tela.ver_texto('Consulta da Prévia da Folha')
