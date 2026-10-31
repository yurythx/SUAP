"""Fatia 5 da doc de usuário do ``comum`` — a página inicial e a aparência do sistema.

É a fatia mais "de todo usuário" de todas: a página inicial é a primeira tela que qualquer
pessoa vê ao entrar no SUAP, e tema, atalhos e notificações acompanham essa pessoa em todas as
outras telas do sistema.

Cada teste é o roteiro de UMA tarefa da doc, na ordem em que ela as apresenta; as asserções
existem para a rodada falhar alto quando a tela muda de forma, e as ``anotar`` despejam
rótulos/opções que a redação copia em vez de deduzir de ``views.py``.

**A regra desta fatia** é a do e2e do módulo: tudo o que ela muda é *preferência gravada no
usuário* (tema, menu retraído, leiaute dos quadros, atalho, notificação lida), e o banco da doc
é reusado entre as seis fatias — mexer nisso com um papel compartilhado trocaria a aparência das
capturas de todas as outras. Daí o papel descartável ``dono_do_inicio``, sempre por
``logado_efemero`` (o menu retraído mora na **sessão**, que ``logado_comum`` compartilha por
matrícula), com a reposição feita no SETUP por ``usuario_do_inicio``.

A única exceção é a captura das *Minhas pendências*: a pendência é o que o **avaliador de sala**
vê, e ela é a única que o próprio ``comum`` produz. Ali o papel é o ``avaliador_sala``, aberto
por ``logado_comum`` — a tarefa só **lê** a página inicial, sem gravar preferência nenhuma.

Nenhuma tarefa desta fatia veio de ``.feature``: as cinco do ``comum`` são de cadastro e de
senha. As tarefas 24 a 27 foram **propostas** a partir do ``menu.yaml``, dos endereços de
``comum/urls.py`` e do encadeamento das telas.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from comum.tests.doc.conftest import (
    COMENTARIO_DOC,
    NOME_ATALHO_DOC,
    NOME_ATALHO_NOVO_DOC,
    SISTEMA_EM_PARADA_DOC,
    anotar,
)
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INICIO = '/'
EXIBIR_QUADRO = '/comum/index/exibir_quadro/'
MEUS_QUADROS_POR_COLUNA = '/comum/index/meus_quadros_por_coluna/{coluna}/'
MINHAS_PENDENCIAS = '/comum/index/minhas_pendencias/'
MEUS_ALERTAS = '/comum/index/meus_alertas/'
NOTIFICACOES = '/comum/notificacoes/'
TODAS_AS_NOTIFICACOES = '/admin/comum/registronotificacao/'
EXCLUIR_ANTIGAS = '/comum/excluir_notificacoes_antigas/'
MARCAR_TODAS_COMO_LIDAS = '/comum/marcar_todas_notificacoes_como_lidas/'
PUSH_WEB_NOTIFICATION = '/admin/djtools/pushsubscription/'
RETRAIR_MENU = '/comum/retrair_menu/'
EXPANDIR_MENU = '/comum/expandir_menu/'
TEMAS = '/comum/temas/'
ACESSIBILIDADE = '/comum/acessibilidade/'
CADASTRAR_ATALHO = '/comum/cadastrar_atalho/'
LISTAGEM_ATALHOS = '/admin/comum/atalho/'
MINHA_CONTA = '/comum/minha_conta/'
COMENTARIO_ADD = '/comum/comentario/add/{aplicacao}/{modelo}/{objeto}/'

# O quadro que a doc usa de ilustração, e o único cujo conteúdo esta fatia controla: ele lista
# `request.user.atalho_set`. É também o único quadro do `comum` sem cache de processo — os
# cacheados viriam da chamada de outro teste.
QUADRO_ATALHOS = 'Atalhos'


def _abrir_o_inicio(pagina) -> Tela:
    """Abre ``/`` e espera as onze chamadas de AJAX que preenchem a página.

    A página inicial sobe **vazia**, com esqueletos cinzentos no lugar dos quadros e dos alertas,
    e busca o conteúdo por AJAX (``comum/static/comum/js/index.js``). Capturar sem esperar
    produziria uma imagem de esqueletos — verde no teste, inútil no guia —, e é justamente o tipo
    de defeito que o revisor não pega, porque as capturas não entram no diff.
    """
    tela = Tela(pagina).ir(INICIO)
    tela.esperar()
    return tela


def test_pagina_inicial_mostra_quadros_alertas_e_atalhos(logado_efemero, usuario_do_inicio, manutencao_programada, atalho_do_inicio, capturar):
    """Tarefa 24 — a página inicial: os quadros, o *Fique atento!* e as portas do rodapé.

    O que se afirma aqui é o que a doc descreve, e nada além: que o quadro *Atalhos* traz os
    atalhos da pessoa, que a parada programada em cartaz vira aviso na lateral e que as portas
    citadas nas tarefas seguintes (Temas, Acessibilidade e *Adicionar atalho*) existem na tela
    para **qualquer** pessoa com conta — sem grupo nenhum além do ``Servidor``.

    As três visibilidades são verificadas ANTES da captura, de propósito: a página monta por
    AJAX e uma captura tirada cedo demais mostraria os esqueletos de carregamento.
    """
    pagina = logado_efemero('dono_do_inicio')
    tela = _abrir_o_inicio(pagina)
    anotar('inicio', tela)

    tela.quadro(QUADRO_ATALHOS).ver_texto(NOME_ATALHO_DOC)
    tela.ver_texto('Fique atento!')
    tela.ver_texto(SISTEMA_EM_PARADA_DOC)
    # Portas que as tarefas 26 e 27 mandam usar. Verificá-las aqui é o que transforma "o rodapé
    # tem Temas e Acessibilidade" de leitura de template em fato observado.
    expect(tela.loc(f'//footer//a[@href="{TEMAS}"]')).to_be_visible()
    expect(tela.loc(f'//footer//a[@href="{ACESSIBILIDADE}"]')).to_be_visible()
    expect(tela.loc('//a[@id="shortcutLink"]')).to_be_visible()
    capturar(pagina, 'inicio-pagina')


def test_pendencia_de_reserva_aparece_para_quem_avalia(logado_comum, solicitacao_pendente, capturar):
    """Tarefa 24 — *Minhas pendências*, a caixa que só aparece para quem tem o que responder.

    É a única pendência que o próprio ``comum`` produz (``index_atribuidos_a_mim``), e por isso a
    captura é feita com o papel que a recebe — o avaliador da sala. Por ``logado_comum`` e não
    por ``logado_efemero``: a tarefa **lê** a página inicial e não grava preferência nenhuma,
    então não há o que envenenar na sessão compartilhada do papel.
    """
    pagina = logado_comum('avaliador_sala')

    with Tela(pagina).pagina.expect_response(lambda resposta: MINHAS_PENDENCIAS in resposta.url) as captura:
        tela = _abrir_o_inicio(pagina)

    assert captura.value.status == 200, f'a página inicial pediu as pendências e recebeu HTTP {captura.value.status}'
    pendencias = tela.quadro('Minhas pendências')
    pendencias.ver_texto('Solicitação de Reserva de Salas')
    pendencias.ver_texto('aguardando avaliação')
    anotar('inicio-pendencias', tela)
    capturar(pagina, 'inicio-pendencias')


def test_esconder_um_quadro_e_traze_lo_de_volta(logado_efemero, usuario_do_inicio, atalho_do_inicio, capturar):
    """Tarefa 24, etapa 2 — o ciclo de esconder e reexibir um quadro da página inicial.

    Uma cadeia e não dois testes porque ``IndexLayout`` **só existe depois de esconder**: é o
    gesto de esconder que cria a linha do usuário, e *Gerenciar Quadros* a apaga. Terminar em
    "exibir" também é o que devolve a página inicial ao estado de origem — o banco é reusado, e a
    captura da tarefa 24 da execução seguinte sairia sem o quadro.

    O botão de esconder vive num menu suspenso (``meus_quadros_por_coluna.html``): ele só entra
    no DOM depois de o ícone de ações ser clicado, e ``clicar_botao`` exige elemento visível. Já
    a volta é pelo botão *Quadros* da barra inferior da própria página inicial
    (``index.html``), que é ``class="btn popup"`` — fancybox em iframe, com a mensagem de sucesso
    caindo na página de trás, recarregada.
    """
    from comum.models import IndexLayout

    usuario = usuario_do_inicio.get_user()
    pagina = logado_efemero('dono_do_inicio')
    tela = _abrir_o_inicio(pagina)

    quadro = tela.quadro(QUADRO_ATALHOS)
    quadro.loc('//button[contains(@class, "dropdown-toggle")]').first.click()
    capturar(pagina, 'inicio-acoes-do-quadro')
    quadro.clicar_botao('Esconder quadro')
    tela.esperar()

    linha = IndexLayout.objects.get(usuario=usuario, quadro_nome=QUADRO_ATALHOS.upper())
    assert linha.escondido, 'o quadro sumiu da tela, mas o leiaute do usuário não registrou que ele está escondido'
    coluna = tela.buscar(MEUS_QUADROS_POR_COLUNA.format(coluna='esquerda'))
    assert NOME_ATALHO_DOC not in coluna.text(), 'o quadro foi escondido e mesmo assim continuou saindo na coluna'

    tela = _abrir_o_inicio(pagina)
    tela.clicar_botao('Quadros')
    popup = tela.popup()
    popup.ver_titulo('Gerenciar Quadros')
    anotar('inicio-gerenciar-quadros', popup)
    popup.loc(f'//input[@name="quadros" and @value="{linha.pk}"]').first.check()
    capturar(pagina, 'inicio-gerenciar-quadros')
    popup.salvar_no_popup('Exibir')

    tela.sucesso('Atualização exibida com sucesso.')
    assert not IndexLayout.objects.filter(pk=linha.pk).exists(), 'a tela disse que exibiu o quadro, mas o leiaute escondido continuou gravado'


def test_caixa_de_notificacoes(logado_efemero, usuario_do_inicio, notificar_o_inicio, capturar):
    """Tarefa 25 — abrir a caixa, ler uma notificação e ver a lista completa.

    O login é a **primeira** linha do corpo e as notificações vêm depois, nessa ordem e não na
    inversa: o primeiro login de um dispositivo faz o próprio SUAP notificar o usuário ("Alerta
    de dispositivo desconhecido"), com bloqueio de leitura por três dias. Criado depois, esse
    alerta viraria a mais recente da caixa e a tela deixaria de marcar qualquer uma como lida —
    a doc afirmaria uma leitura automática que a captura não mostra. ``notificar_o_inicio``
    guarda a ordem com um ``assert``.

    A notificação que o teste abre é a **mais antiga**: a mais recente já é marcada como lida no
    carregamento da página, e clicar nela ilustraria um estado que a tela produziu sozinha.
    """
    from comum.models import RegistroNotificacao

    pagina = logado_efemero('dono_do_inicio')
    tela = Tela(pagina)
    # Sem aspas duplas no texto: `Tela.ver_texto` monta um XPath com `contains(., "…")`, e uma
    # aspa dupla no meio da mensagem quebra a expressão — o texto aparece na tela e a asserção
    # falha mesmo assim. Medido.
    mensagem = 'A sua reserva da Sala de Reuniões 101 foi deferida para o dia 12/05, das 08h às 10h.'
    antiga = notificar_o_inicio('Reserva de sala deferida', mensagem)[0]
    notificar_o_inicio('Documento pronto para retirada', 'A sua declaração de vínculo já pode ser retirada no setor.')
    recente = notificar_o_inicio('Senha próxima de expirar', 'A sua senha do SUAP expira em 7 dias.')[0]
    tela.ir(NOTIFICACOES)

    tela.ver_titulo('Notificações não lidas')
    anotar('notificacoes-caixa', tela)
    capturar(pagina, 'notificacoes-caixa')
    assert RegistroNotificacao.objects.get(pk=recente.pk).lida, 'a caixa abriu, mas não marcou a notificação mais recente como lida'

    tela.loc(f'//button[@data-notificacao="{antiga.pk}"]').click()
    tela.esperar()
    tela.ver_texto(mensagem)
    capturar(pagina, 'notificacoes-mensagem')
    assert RegistroNotificacao.objects.get(pk=antiga.pk).lida, 'a notificação foi aberta, mas continuou não lida'

    tela.ir(TODAS_AS_NOTIFICACOES)
    tela.ver_titulo('Notificações')
    anotar('notificacoes-todas', tela)
    capturar(pagina, 'notificacoes-todas')

    # Aviso bloqueado: nem tudo pode ser lido ou removido na hora, e a linha informa a data de
    # desbloqueio. É o caso do alerta de login em dispositivo novo, justamente o que a fixture
    # limpa para a caixa da captura ter só o que o teste criou — por isso o bloqueio é forjado
    # por ORM aqui, no FIM do teste, depois das capturas que mostram as linhas completas.
    # Sem este trecho a frase da doc sobre o desbloqueio seria leitura de template.
    daqui_a_tres_dias = datetime.now() + timedelta(days=3)
    RegistroNotificacao.objects.filter(pk=antiga.pk).update(
        lida=False, data_permite_marcar_lida=daqui_a_tres_dias, data_permite_excluir=daqui_a_tres_dias
    )
    tela.ir(NOTIFICACOES)

    tela.ver_texto('Desbloqueio para leitura')
    tela.ver_texto('Desbloqueio para remoção')


def test_limpeza_das_notificacoes(logado_efemero, usuario_do_inicio, notificar_o_inicio, capturar):
    """Tarefa 25, segunda metade — marcar todas como lidas e apagar as antigas.

    Os dois botões da barra de ações da caixa, no mesmo teste porque o segundo depende do
    primeiro: a faxina só apaga o que está **lido e** com mais de trinta dias, e o rótulo do
    botão só existe quando há o que apagar (``qtd_notificacoes_antigas``). A notificação recente
    fica no banco de propósito — é ela que prova a segunda metade da regra, e é o que a doc
    afirma ao leitor ("o que é recente fica").
    """
    from comum.models import RegistroNotificacao

    pagina = logado_efemero('dono_do_inicio')
    tela = Tela(pagina)
    vinculo = usuario_do_inicio.get_vinculo()
    antiga = notificar_o_inicio('Prazo encerrado', 'O prazo de inscrição do edital terminou.', dias_atras=90)[0]
    notificar_o_inicio('Reunião remarcada', 'A reunião do colegiado foi remarcada para a próxima terça.')
    tela.ir(NOTIFICACOES)
    tela.loc(f'//a[@href="{MARCAR_TODAS_COMO_LIDAS}" and contains(., "Marcar todas como lidas")]').first.click()

    tela.sucesso('Todas as suas notificações foram marcadas como lida com sucesso.')
    assert not RegistroNotificacao.objects.filter(vinculo=vinculo, lida=False).exists(), 'a tela disse que marcou todas, mas sobrou não lida'

    faxina = tela.loc(f'//a[@href="{EXCLUIR_ANTIGAS}" and contains(., "notificações antigas")]').first
    expect(faxina).to_be_visible()
    capturar(pagina, 'notificacoes-faxina')
    faxina.click()

    tela.sucesso('Todas as suas notificações lidas há mais de um mês foram excluídas.')
    assert not RegistroNotificacao.objects.filter(pk=antiga.pk).exists(), 'a tela disse que excluiu, mas a notificação antiga continua no banco'
    assert RegistroNotificacao.objects.filter(vinculo=vinculo).exists(), 'a faxina levou junto as notificações recentes'


def test_push_web_notification_e_tela_de_administracao(logado_comum):
    """Tarefa 25, nota — a tela *Push Web Notification* existe e é de administração.

    Sem captura e sem passo a passo: a doc a cita em *Telas de apoio*, e o que se afirma aqui é
    só que ela responde. Ela é o registro dos navegadores inscritos para receber aviso fora do
    SUAP, e o único gesto que a alimenta — o botão *Ativar notificações WEB* da caixa de
    notificações — é condicionado a ``request.user.is_superuser`` em ``notificacoes.html``, de
    modo que a doc não o descreve.

    ``djtools.add_pushsubscription``, a permissão que o ``menu.yaml`` exige, não é concedida por
    nenhum grupo padrão do SUAP — daí o superusuário do seed, e não um papel de ``PAPEIS``.
    """
    tela = Tela(logado_comum('admin')).ir(PUSH_WEB_NOTIFICATION)

    # O título vem de `verbose_name_plural`, que diverge do rótulo do menu (*Push Web
    # Notification*) — armadilha da fatia 3, confirmada aqui.
    tela.ver_titulo('Inscrições de Notificação')


def test_trocar_o_tema_e_ver_as_opcoes_de_acessibilidade(logado_efemero, usuario_do_inicio, capturar):
    """Tarefa 26 — a galeria de temas, o alto contraste e a volta ao tema Padrão.

    Termina no Padrão de propósito, e não por acabamento: a preferência é gravada no usuário e o
    banco da doc é reusado, então um tema deixado para trás mudaria a folha de estilo de todas as
    capturas da execução seguinte — inclusive as das outras fatias, se alguma vier a abrir este
    papel.

    O ``href`` do link de tema não leva barra antes da query string
    (``includes/tema_block.html``), de modo que todo clique de tema paga um 301 do
    ``APPEND_SLASH`` antes de chegar à view. Não quebra nada, mas é a URL real, e é por ela que o
    teste clica.
    """
    from comum.models import Preferencia

    usuario = usuario_do_inicio.get_user()
    pagina = logado_efemero('dono_do_inicio')
    tela = Tela(pagina).ir(TEMAS)

    tela.ver_titulo('Seleção de Tema')
    anotar('temas', tela)
    capturar(pagina, 'temas-galeria')
    tela.loc(f'//a[@href="/comum/alterar_tema?theme={Preferencia.DUNAS}"]').first.click()

    tela.sucesso('Tema alterado para "Dunas" com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).tema == Preferencia.DUNAS, 'a tela disse que trocou o tema, mas a preferência não mudou'
    capturar(pagina, 'tema-dunas')

    tela.ir(ACESSIBILIDADE)
    tela.ver_titulo('Acessibilidade')
    anotar('acessibilidade', tela)
    tela.ver_texto('Alto Contraste')
    tela.ver_texto('Teclas de acesso')
    capturar(pagina, 'acessibilidade')

    tela.ir(TEMAS)
    tela.loc(f'//a[@href="/comum/alterar_tema?theme={Preferencia.PADRAO}"]').first.click()

    tela.sucesso('Tema alterado para "Padrão" com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).tema == Preferencia.PADRAO, 'a volta ao tema Padrão não foi gravada'


def test_retrair_e_expandir_a_barra_lateral(logado_efemero, usuario_do_inicio, capturar):
    """Tarefa 26, segunda metade — esconder o menu lateral para ganhar espaço na tela.

    O que se afirma é justamente o que o clique sozinho não prova: o botão troca a classe
    ``hideSidebar`` do ``body`` por JS, de modo que a barra some na hora **mesmo que a gravação
    no servidor falhe**. É a página RECARREGADA que separa as duas coisas — ali a classe só volta
    se a escolha tiver sido gravada na sessão.

    Os dois sentidos no mesmo teste porque o segundo repõe o que o primeiro desfez.
    """
    pagina = logado_efemero('dono_do_inicio')
    tela = _abrir_o_inicio(pagina)
    corpo = tela.pagina.locator('body')

    expect(corpo).not_to_have_class(re.compile('hideSidebar'))
    # O clique dispara a gravação por AJAX e o JS esconde a barra na hora; navegar em seguida
    # sem esperar a resposta ABORTA a gravação — medido: a página recarregada voltou com a barra
    # aberta. Por isso a navegação só acontece depois de a rota responder.
    with tela.pagina.expect_response(lambda resposta: RETRAIR_MENU in resposta.url) as captura:
        tela.loc('//button[@id="toggleSidebar"]').click()

    assert captura.value.status == 200, f'retrair o menu devolveu HTTP {captura.value.status}'
    tela = _abrir_o_inicio(pagina)

    expect(corpo).to_have_class(re.compile('hideSidebar'))
    capturar(pagina, 'inicio-menu-retraido')

    with tela.pagina.expect_response(lambda resposta: EXPANDIR_MENU in resposta.url) as captura:
        tela.loc('//button[@id="toggleSidebar"]').click()

    assert captura.value.status == 200, f'expandir o menu devolveu HTTP {captura.value.status}'
    tela = _abrir_o_inicio(pagina)

    expect(corpo).not_to_have_class(re.compile('hideSidebar'))


def test_criar_um_atalho_para_a_tela_em_uso(logado_efemero, usuario_do_inicio, capturar):
    """Tarefa 27 — o *Adicionar atalho* do rodapé de qualquer tela, e o quadro que o publica.

    Os dois lados no mesmo teste porque um sem o outro não é a tarefa: o atalho existe para virar
    item do quadro *Atalhos* da página inicial, e a gravação sozinha não prova que ele chega lá.

    O endereço **não é digitado**: o formulário traz ``url`` como campo escondido, preenchido com
    o caminho da página de onde se clicou. É por isso que o teste afirma o endereço gravado e não
    só o nome — um atalho que aponte para o lugar errado é indistinguível de um certo na tela de
    cadastro.

    ``salvar_no_popup`` e não ``clicar_botao`` + ``sucesso``: o formulário vive num iframe do
    fancybox e a resposta fecha o popup, então a asserção seguinte contaria o próprio timeout no
    documento antigo.
    """
    from comum.models import Atalho

    usuario = usuario_do_inicio.get_user()
    Atalho.objects.filter(usuario=usuario, nome=NOME_ATALHO_NOVO_DOC).delete()
    pagina = logado_efemero('dono_do_inicio')
    tela = Tela(pagina).ir(NOTIFICACOES)
    tela.loc(f'//a[@id="shortcutLink" and starts-with(@href, "{CADASTRAR_ATALHO}")]').click()

    popup = tela.popup()
    popup.ver_titulo('Adicionar atalho')
    anotar('atalho-cadastrar', popup)
    popup.preencher('Nome', 'texto', NOME_ATALHO_NOVO_DOC)
    capturar(pagina, 'atalho-cadastrar')
    tela = popup.salvar_no_popup('Salvar')

    tela.sucesso('Atalho cadastrado com sucesso')
    atalho = Atalho.objects.filter(usuario=usuario, nome=NOME_ATALHO_NOVO_DOC).first()
    assert atalho is not None, 'a tela disse que cadastrou, mas o atalho não persistiu'
    assert atalho.url == NOTIFICACOES, f'o atalho gravou o endereço {atalho.url!r} em vez da tela de onde foi criado'

    tela = _abrir_o_inicio(pagina)
    tela.quadro(QUADRO_ATALHOS).ver_texto(NOME_ATALHO_NOVO_DOC)
    capturar(pagina, 'inicio-quadro-atalhos')

    tela.ir(LISTAGEM_ATALHOS)
    tela.ver_titulo('Atalhos')
    tela.linha(NOME_ATALHO_NOVO_DOC)
    capturar(pagina, 'atalhos-listagem')

    Atalho.objects.filter(pk=atalho.pk).delete()


def test_comentar_um_registro(logado_efemero, usuario_do_inicio, objeto_comentavel, capturar):
    """Nota da tarefa 24 — a caixa de comentários que várias telas do SUAP pendurarem em si.

    **Não vira tarefa**, e o motivo está aqui: nenhuma tela do ``comum`` publica a caixa. Quem a
    desenha é a templatetag ``comentarios`` do ``djtools``, usada por telas de outros módulos
    (processo eletrônico, compras, planejamento, central de serviços), e os botões *Adicionar
    Comentário* e *Responder* que ela imprime são condicionados ao ``pode_comentar`` de quem a
    chama. Descrever esses cliques seria documentar passo não executado, com uma condição que
    esta rodada não controla. A doc diz o que a caixa faz e remete o gesto à tela que a oferece;
    o formulário, este sim, é o que se navega e captura aqui.

    O rótulo do botão é *Enviar* e não *Salvar*: ``ComentarioForm`` é um ``FormPlus``, não um
    ``ModelForm``, e o ``render_form`` do djtools só põe *Salvar* nos segundos.
    """
    from django.contrib.contenttypes.models import ContentType

    from comum.models import Comentario, Predio

    autor = usuario_do_inicio.get_user()
    tipo = ContentType.objects.get_for_model(Predio)
    endereco = COMENTARIO_ADD.format(aplicacao='comum', modelo='predio', objeto=objeto_comentavel.pk)
    pagina = logado_efemero('dono_do_inicio')
    tela = Tela(pagina).ir(endereco)

    tela.ver_titulo('Adicionar Comentário')
    anotar('comentario', tela)
    tela.preencher('Texto', 'textarea', COMENTARIO_DOC)
    capturar(pagina, 'comentario-formulario')
    tela.clicar_botao('Enviar')

    tela.sucesso('Comentário adicionado com sucesso.')
    comentario = Comentario.objects.filter(content_type=tipo, object_id=objeto_comentavel.pk, texto=COMENTARIO_DOC).first()
    assert comentario is not None, 'a tela disse que adicionou, mas o comentário não persistiu no objeto informado no endereço'
    assert comentario.cadastrado_por == autor, 'o comentário foi gravado em nome de outra pessoa'
