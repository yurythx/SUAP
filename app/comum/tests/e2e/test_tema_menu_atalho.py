"""Fluxo: as preferências de aparência do usuário — tema, barra lateral e atalhos.

São três gestos pequenos que o SUAP guarda por usuário e aplica em **toda** tela: o tema (uma
linha em ``Preferencia``, que decide a folha de estilo de todas as páginas), o menu retraído
(``request.session['retraido']``, que decide a classe ``hideSidebar`` do ``body``) e os atalhos
pessoais (que viram itens do quadro ``Atalhos`` da página inicial).

A regressão que este arquivo pega é a da preferência que não gruda: o fluxo inteiro consiste em
gravar uma escolha num lugar e lê-la noutro, numa request seguinte. Cada um dos três cruza uma
fronteira diferente — banco, sessão e banco+quadro —, e o sintoma da quebra é sempre o mesmo e
sempre mudo: a escolha do usuário some no próximo clique, sem erro nenhum.

Tudo roda sobre o papel descartável ``dono_do_inicio``, e por ``logado_efemero``: ``logado_comum``
entrega uma sessão **compartilhada** por matrícula (``storage_states``), e o menu retraído mora
exatamente na sessão — retrair pelo papel de outra fatia sumiria com a barra lateral de todos os
testes seguintes dela.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — armadilha 17 da receita.
TEMAS = '/comum/temas/'
ALTERAR_TEMA = '/comum/alterar_tema/'
RETRAIR_MENU = '/comum/retrair_menu/'
EXPANDIR_MENU = '/comum/expandir_menu/'
CADASTRAR_ATALHO = '/comum/cadastrar_atalho/'
INICIO = '/'

# O `href` que `includes/tema_block.html` imprime — **sem** a barra antes da query string.
# Achado de produção: todo link de tema do SUAP paga um 301 do `APPEND_SLASH` antes de chegar à
# view. Não quebra nada, mas é a URL real, e é por ela que o teste clica; a constante acima é a
# rota (é ela que o gate de `comum/urls.py` lê).
LINK_DE_TEMA = '/comum/alterar_tema?theme={tema}'

# A página onde o teste aciona "Adicionar atalho". Serve qualquer tela que estenda
# `comum/templates/admin/base.html` fora de popup; esta é a listagem dos próprios atalhos, que
# `AtalhoAdmin.has_change_permission` libera para qualquer usuário autenticado, então o teste não
# precisa de grupo nenhum além do `Servidor`.
LISTAGEM_ATALHOS = '/admin/comum/atalho/'


def test_ciclo_do_tema(logado_efemero, usuario_do_inicio):
    """Escolhe um tema pela galeria, confere que ele grudou, e volta ao Padrão.

    Uma cadeia e não dois testes por dois motivos que se somam: o segundo gesto só faz sentido
    depois do primeiro (só dá para "voltar" ao Padrão a partir de outro tema), e é ele que
    devolve o usuário ao estado de origem — a suíte não dá flush e o CI roda com ``--reuse-db``,
    então um tema deixado para trás mudaria a folha de estilo de todas as telas da execução
    seguinte.

    A asserção de ida é dupla e nos dois lados da fronteira: o banner com o nome do tema (que a
    view monta de ``Preferencia.get_tema_description``, e não do que veio na query string) e a
    linha de ``Preferencia``. Afirmar só o banner passaria com a gravação removida.

    O que NÃO se afirma, de propósito: o "N usuários usam este tema" de ``temas.html``. É uma
    contagem global sobre o banco inteiro, que cresce a cada execução do e2e reusado — asserção
    de magnitude absoluta, exatamente o que a convenção do repo veta.
    """
    from comum.models import Preferencia

    usuario = usuario_do_inicio.get_user()
    tela = Tela(logado_efemero('dono_do_inicio')).ir(TEMAS)

    tela.ver_titulo('Seleção de Tema')
    tela.loc(f'//a[@href="{LINK_DE_TEMA.format(tema=Preferencia.DUNAS)}"]').first.click()

    tela.sucesso('Tema alterado para "Dunas" com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).tema == Preferencia.DUNAS, 'a UI disse que trocou o tema, mas a preferência não mudou'

    tela.loc(f'//a[@href="{LINK_DE_TEMA.format(tema=Preferencia.PADRAO)}"]').first.click()

    tela.sucesso('Tema alterado para "Padrão" com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).tema == Preferencia.PADRAO, 'a volta ao tema Padrão não foi gravada'


def test_tema_desconhecido_cai_no_padrao(logado_efemero, usuario_do_inicio):
    """Um tema que não existe no ``TEMA_CHOICES`` grava o padrão, não a string recebida.

    Vale um teste próprio porque o valor vem da query string, isto é, do usuário: sem o
    ``if tema in dict(Preferencia.TEMA_CHOICES)`` da view, qualquer texto entraria no campo e
    viraria a classe do ``body`` (``theme-{{ theme|slugify }}``) em toda página do sistema.
    É a única validação da rota, e ela não tem formulário para segurá-la.
    """
    from comum.models import Preferencia

    usuario = usuario_do_inicio.get_user()
    tela = Tela(logado_efemero('dono_do_inicio'))
    tela.ir(ALTERAR_TEMA + '?theme=tema-que-nao-existe')

    tela.sucesso('Tema alterado para "Padrão" com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).tema == Preferencia.PADRAO, 'o SUAP gravou um tema fora do conjunto de opções'


def test_menu_retraido_sobrevive_ao_recarregamento(logado_efemero, usuario_do_inicio):
    """Retrair a barra lateral fica gravado na sessão; expandir a devolve.

    O que se afirma é justamente o que o clique sozinho não prova: o botão troca a classe
    ``hideSidebar`` no ``body`` por JS, de modo que a barra some na hora **mesmo que a gravação
    no servidor falhe**. É a página RECARREGADA que separa as duas coisas — ali a classe só volta
    se ``request.session['retraido']`` tiver sido gravado (``comum/templates/admin/base.html``).

    Os dois sentidos num teste porque o segundo repõe o que o primeiro desfez, e porque a
    preferência é de sessão: a sessão é efêmera aqui, mas o mesmo gesto num papel compartilhado
    sumiria com a barra lateral das outras fatias.
    """
    tela = Tela(logado_efemero('dono_do_inicio')).ir(INICIO)
    corpo = tela.pagina.locator('body')

    expect(corpo).not_to_have_class(re.compile('hideSidebar'))
    with tela.pagina.expect_response(lambda resposta: RETRAIR_MENU in resposta.url) as captura:
        tela.loc('//button[@id="toggleSidebar"]').click()

    assert captura.value.status == 200, f'retrair o menu devolveu HTTP {captura.value.status}'
    tela.ir(INICIO)
    expect(corpo).to_have_class(re.compile('hideSidebar'))

    with tela.pagina.expect_response(lambda resposta: EXPANDIR_MENU in resposta.url) as captura:
        tela.loc('//button[@id="toggleSidebar"]').click()

    assert captura.value.status == 200, f'expandir o menu devolveu HTTP {captura.value.status}'
    tela.ir(INICIO)
    expect(corpo).not_to_have_class(re.compile('hideSidebar'))


def test_cadastra_atalho_pelo_popup_e_ele_aparece_no_inicio(logado_efemero, usuario_do_inicio):
    """O "Adicionar atalho" de qualquer tela grava o endereço dela e o publica na página inicial.

    Os dois lados num teste porque um sem o outro não afirma o fluxo: o atalho existe para virar
    item do quadro ``Atalhos`` (``index_quadros_atalhos``), e a gravação sozinha não prova que
    ele chega lá.

    O endereço **não é digitado**: o formulário traz ``url`` como campo escondido, preenchido
    pelo ``base64`` do caminho da página de onde se clicou (``comum/templates/admin/base.html``).
    É por isso que o teste afirma o ``url`` gravado e não só o nome — um atalho com o endereço
    errado é indistinguível de um certo na tela de cadastro.

    ``salvar_no_popup`` e não ``clicar_botao`` + ``sucesso``: o formulário vive num iframe do
    fancybox e a resposta fecha o popup, então a asserção seguinte contaria o próprio timeout no
    documento antigo (armadilha 15 da receita).
    """
    from comum.models import Atalho

    usuario = usuario_do_inicio.get_user()
    nome = f'E2E Atalho do popup {usuario_do_inicio.matricula}'

    tela = Tela(logado_efemero('dono_do_inicio')).ir(LISTAGEM_ATALHOS)
    atalho_href = tela.loc(f'//a[@id="shortcutLink" and starts-with(@href, "{CADASTRAR_ATALHO}")]')
    expect(atalho_href).to_be_visible()
    atalho_href.click()

    popup = tela.popup()
    popup.preencher('Nome', 'texto', nome)
    tela = popup.salvar_no_popup('Salvar')

    tela.sucesso('Atalho cadastrado com sucesso')
    atalho = Atalho.objects.filter(usuario=usuario, nome=nome).first()
    assert atalho is not None, 'a UI disse que cadastrou, mas o atalho não persistiu'
    assert atalho.url == LISTAGEM_ATALHOS, f'o atalho gravou o endereço {atalho.url!r} em vez da tela de onde foi criado'

    tela.ir(INICIO)
    tela.quadro('Atalhos').ver_texto(nome)
