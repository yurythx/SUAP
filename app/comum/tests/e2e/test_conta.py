"""Fluxo: as telas da conta do usuário — Minha conta, Ações, Acessibilidade e os atalhos externos.

São as telas que todo usuário do SUAP alcança pelo menu do próprio nome, sem permissão nenhuma
além de estar autenticado: o painel da conta (de onde saem a troca de senha e o 2FA), o
histórico de ações, as opções de acessibilidade, a referência do Design System e os três
atalhos para serviços externos (webmail, Azure, Google Classroom).

A regressão que este arquivo pega é a mais barata do módulo e a que mais aparece: uma dessas
views quebra quando um relacionamento de ``Vinculo``/``Preferencia`` muda, e o sintoma é 500 na
primeira tela que o usuário abre depois de entrar. Os três atalhos externos entram aqui porque
**são guardas**, não telas: cada um decide, antes de redirecionar, se aquele usuário tem o
serviço — e é a decisão, não o destino, que precisa continuar valendo.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_senha.py`.
MINHA_CONTA = '/comum/minha_conta/'
MINHAS_ACOES_SUAP = '/comum/minhas_acoes_suap/'
ACESSIBILIDADE = '/comum/acessibilidade/'
DESIGN_SYSTEM = '/comum/design_system/'
WEBMAIL = '/comum/webmail/'
AZURE = '/comum/azure/'
GOOGLE_CLASSROOM = '/comum/google_classroom/'


def test_minha_conta_reune_os_acessos_do_usuario(logado_comum):
    """O painel da conta abre e traz a porta da troca de senha.

    O botão não é enfeite: ``/comum/alterar_senha/`` só é alcançável pelo usuário a partir
    daqui, e o painel é também quem decide exibir (ou não) o interruptor do 2FA.
    """
    tela = Tela(logado_comum('solicitante')).ir(MINHA_CONTA)

    tela.ver_titulo('Minha conta')
    tela.ver_botao('Alterar senha')


def test_minhas_acoes_suap_consulta_o_periodo(logado_comum):
    """O filtro por período roda e responde — a tela sai do "use o filtro" para o resultado.

    A transição entre os dois avisos é o que se afirma: antes do envio a tela pede o filtro;
    depois, informa o resultado da consulta. Só o segundo prova que o formulário ``GET`` validou
    (data de início, data de término e o limite de 90 dias) e que a agregação das ações rodou.

    O resultado é vazio de propósito: quem publica ação em ``minhas_acoes`` são os **outros**
    apps (``processo_eletronico``, ``centralservicos``, ``erros``, ``edu``…), e montar o domínio
    de um deles no seed do ``comum`` inverteria a dependência entre os apps — a mesma razão que
    já dispensa a reserva de diário na fatia de salas.
    """
    tela = Tela(logado_comum('solicitante')).ir(MINHAS_ACOES_SUAP)

    tela.ver_texto('Utilize o filtro para buscar')
    tela.clicar_botao('Enviar')

    tela.ver_texto('Nenhuma ação foi encontrada para o período passado.')


def test_acessibilidade_lista_as_opcoes_de_contraste(logado_comum):
    """A tela de acessibilidade abre com os temas de contraste que o usuário pode escolher.

    O link do tema leva o slug (``alto-contraste``), não o nome: com o nome, ``alterar_tema`` caía
    no tema padrão. E a miniatura é a do tema, que existe — a antiga apontava para um PNG removido.
    """
    pagina = logado_comum('solicitante')
    tela = Tela(pagina).ir(ACESSIBILIDADE)

    tela.ver_titulo('Acessibilidade')
    tela.ver_texto('Alto Contraste')
    tela.ver_texto('Modo Daltonismo')
    assert pagina.locator('a[href="/comum/alterar_tema?theme=alto-contraste"]').count() > 0
    miniaturas = pagina.locator('img[src^="/static/comum/img/temas/"]')
    assert miniaturas.count() == 2
    assert all(img.evaluate('e => e.complete && e.naturalWidth > 0') for img in miniaturas.all())


def test_design_system_abre_a_referencia_visual(logado_comum):
    """A referência do Design System renderiza — é o catálogo de componentes que as telas usam.

    Vale como teste porque a view monta a paleta de **todos** os temas: um tema novo mal
    declarado derruba esta página antes de derrubar qualquer outra.
    """
    tela = Tela(logado_comum('solicitante')).ir(DESIGN_SYSTEM)

    tela.ver_titulo('Design System')


def test_atalho_do_webmail_redireciona_para_o_endereco_configurado(logado_comum, webmail_configurado):
    """O atalho do webmail leva ao endereço da ``Configuracao`` — não há tela própria.

    ``buscar`` não segue o redirect de propósito: o destino é externo à aplicação, e o que
    importa afirmar é que a view resolveu a configuração e apontou para lá.
    """
    resposta = Tela(logado_comum('solicitante')).buscar(WEBMAIL)

    assert resposta.status == 302, f'o atalho devolveu HTTP {resposta.status} em vez do redirecionamento'
    assert resposta.headers['location'] == webmail_configurado, 'o atalho apontou para um endereço diferente do configurado'


def test_atalhos_externos_barram_quem_nao_tem_o_servico(logado_comum):
    """Azure e Google Classroom recusam o servidor que não tem o serviço — por status HTTP.

    A guarda é o corpo inteiro das duas views. Para o Azure ela conjuga cargo, e-mail
    institucional e grupo (``Servidor.tem_acesso_servicos_microsoft``); para o Classroom exige
    integração LDAP ativa, que o ambiente de teste não tem por definição
    (``djtools/utils/ldap.py`` desliga fora de produção). Logo o **403 é o único desfecho
    alcançável aqui**, e é o que protege: liberar serviço externo a quem não tem direito é o
    defeito que essas duas linhas existem para evitar.
    """
    tela = Tela(logado_comum('solicitante'))

    assert tela.buscar(AZURE).status == 403, 'servidor sem serviços Microsoft não deveria ser encaminhado ao Azure'
    assert tela.buscar(GOOGLE_CLASSROOM).status == 403, 'servidor sem conta no Classroom não deveria ser encaminhado a ele'
