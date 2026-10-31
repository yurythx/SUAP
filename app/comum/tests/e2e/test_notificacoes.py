"""Fluxo: a caixa de notificações — o único canal em que o SUAP fala com o usuário dentro do SUAP.

``RegistroNotificacao`` é o aviso que cada app manda para um vínculo (``send_notification``), e
esta é a tela que o entrega: lista as não lidas, abre uma, marca leitura nos dois sentidos,
remove e faz a faxina do que passou de trinta dias. São doze rotas para um único objeto, o que
por si já diz onde mora o risco.

A regressão que este arquivo pega é a que não dá sintoma: o estado de leitura é o que decide o
que aparece na caixa e o que conta no contador do cabeçalho, e as doze views o gravam por
caminhos independentes (item, lote, "todas", ao abrir a tela). Se um deles parar de gravar,
ninguém recebe erro — o aviso simplesmente continua lá, ou some antes da hora.

Tudo roda sobre o papel descartável ``dono_do_inicio``, por ``logado_efemero``: metade destas
rotas apaga ou marca **todas** as notificações do vínculo, e fazer isso num papel compartilhado
mudaria o cabeçalho das telas das outras quatro fatias (ver a nota da 5ª fatia no ``conftest``).

Em todos eles o login é a **primeira** linha do corpo e as notificações vêm depois, nessa ordem e
não na inversa: o primeiro login de um dispositivo faz o próprio SUAP notificar o usuário
("Alerta de dispositivo desconhecido"), com bloqueio de leitura por três dias. Criado depois das
notificações do teste, esse alerta vira a mais recente da caixa — até o #17388 isso fazia
``/comum/notificacoes/`` deixar de marcar qualquer uma como lida; hoje ela pula a travada, mas o
alerta ainda seria um item a mais na caixa. ``notificar_o_inicio`` guarda a ordem com um
``assert``; o raciocínio inteiro está na docstring dela.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo, com `{}` no lugar do parâmetro — ver a armadilha 17 da
# receita: a UP032 do `ruff --unsafe-fixes` reescreveria um `.format` sobre literal como
# f-string, e o gate de rotas deixaria de enxergar o caminho. Sobre um NOME a UP032 não dispara.
NOTIFICACOES = '/comum/notificacoes/'
NOTIFICACAO = '/comum/notificacao/{registro}/'
MARCAR_COMO_LIDA = '/comum/marcar_como_lida/{registro}/'
MARCAR_COMO_NAO_LIDA = '/comum/marcar_como_nao_lida/{registro}/'
MARCAR_COMO_LIDA_EM_LOTE = '/comum/marcar_como_lida_em_lote/'
MARCAR_COMO_NAO_LIDA_EM_LOTE = '/comum/marcar_como_nao_lida_em_lote/'
MARCAR_TODAS_COMO_LIDAS = '/comum/marcar_todas_notificacoes_como_lidas/'
REMOVER_NOTIFICACAO = '/comum/remover_notificacao/{registro}/'
REMOVER_EM_LOTE = '/comum/remover_notificacoes_em_lote/'
EXCLUIR_ANTIGAS = '/comum/excluir_notificacoes_antigas/'
BUSCA_NOTIFICACAO = '/comum/busca_notificacao/{ultimo_pk}/'
CONTADOR = '/comum/contador_minhas_notificacoes/'

# A listagem do admin que hospeda as ações em massa e o botão de remoção de uma linha.
# Rota do admin, então fora do gate de `comum/urls.py` — mas é o que o `menu.yaml` publica como
# "Usuários::Notificações::Todas as notificações", e é de onde saem as três rotas `_em_lote`.
LISTAGEM_ADMIN = '/admin/comum/registronotificacao/'


def test_caixa_lista_as_nao_lidas_e_le_a_primeira(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """Abrir a caixa mostra as não lidas e marca a mais recente como lida — sem clique nenhum.

    A leitura automática da primeira não é efeito colateral: é o que ``notificacoes`` faz de
    propósito (a primeira legível da lista + ``save()``), e é a razão de o contador do
    cabeçalho baixar assim que a tela abre. Um teste que só afirmasse a listagem passaria com
    essa linha removida.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    registros = notificar_o_inicio('Prazo encerrando', 'O prazo do seu processo termina amanhã.', quantidade=2)
    mais_recente = registros[-1]
    tela.ir(NOTIFICACOES)

    tela.ver_titulo('Notificações não lidas')
    expect(tela.loc(f'//button[@data-notificacao="{mais_recente.pk}"]')).to_be_visible()
    assert RegistroNotificacao.objects.get(pk=mais_recente.pk).lida, 'a caixa abriu, mas não marcou a primeira notificação como lida'
    assert not RegistroNotificacao.objects.get(pk=registros[0].pk).lida, 'a caixa marcou como lida uma notificação que não era a primeira'


def test_rolagem_carrega_a_11a_depois_de_a_caixa_ler_a_primeira(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """Com 11 não lidas, a 11ª chega pela rolagem mesmo depois de a caixa ler a 1ª ao abrir (#17451).

    A tela renderiza as 10 mais recentes e o script pede a seguinte já no carregamento. Por
    posição, a lista encolhida (a 1ª acabou de ser lida) dava o fim antes da 11ª; por cursor
    (pk da 10ª exibida), a 11ª vem.
    """
    tela = Tela(logado_efemero('dono_do_inicio'))
    registros = notificar_o_inicio('Rolagem por cursor', 'Notificação da rolagem por cursor.', quantidade=11)
    tela.ir(NOTIFICACOES)

    expect(tela.loc(f'//button[@data-notificacao="{registros[0].pk}"]')).to_be_visible()


def test_marca_leitura_pela_ancora_e_desmarca_pela_rota(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """Clicar no título da notificação a marca como lida; a rota inversa a devolve ao estado anterior.

    O clique na âncora é o gesto real (``notificacoes.html`` dispara o ``GET`` de
    ``marcar_como_lida`` por AJAX e tira a classe ``non-read``), e a volta é pela mesma URL que
    o mesmo script chama no sentido contrário — por isso ela vai por ``Tela.buscar``, que é um
    ``GET`` pela sessão do browser, e não por um segundo clique: o botão de "não lida" da barra
    de ações depende de um handler que só existe na tela de notificações do usuário.

    A notificação exercitada é a **mais antiga** das duas: a mais recente é lida no carregamento
    da página, e clicar nela afirmaria um estado que a tela já tinha gravado sozinha.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    registros = notificar_o_inicio('Documento disponível', 'Seu documento já pode ser retirado.', quantidade=2)
    mais_antiga = registros[0]

    rota_de_leitura = MARCAR_COMO_LIDA.format(registro=mais_antiga.pk)
    tela.ir(NOTIFICACOES)
    ancora = tela.loc(f'//button[@data-notificacao="{mais_antiga.pk}"]')
    expect(ancora).to_be_visible()
    # O par (clique, rota) é o contrato: o script monta a URL concatenando o `data-notificacao`,
    # e um `pk` errado ali marcaria a notificação de outra linha sem nenhum sintoma na tela.
    with tela.pagina.expect_response(lambda resposta: rota_de_leitura in resposta.url):
        ancora.click()
    tela.esperar()

    assert RegistroNotificacao.objects.get(pk=mais_antiga.pk).lida, 'a âncora foi clicada, mas a notificação continuou não lida'

    resposta = tela.buscar(MARCAR_COMO_NAO_LIDA.format(registro=mais_antiga.pk))

    assert resposta.status == 200, f'marcar como não lida devolveu HTTP {resposta.status}'
    assert not RegistroNotificacao.objects.get(pk=mais_antiga.pk).lida, 'a rota respondeu OK, mas a notificação continuou lida'


def test_marca_todas_como_lidas_pela_barra_de_acoes(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """O botão "Marcar todas como lidas" zera a caixa inteira do vínculo.

    Vale um teste próprio porque a view é a única que grava por ``queryset.update`` — sem passar
    pelo ``save()`` de ``RegistroNotificacao``, que é quem limpa o cache do contador. A limpeza
    está lá, mas por uma chamada explícita (``RegistroNotificacao.limpar_cache``) que nada obriga
    a existir.

    O botão carrega ``data-confirm``, que o SUAP resolve com um ``confirm()`` nativo
    (``comum/static/comum/js/main.js``): a página aceita o diálogo sozinha, porque
    ``logado_efemero`` registra o ``on('dialog')``.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    notificar_o_inicio('Reunião marcada', 'A reunião do colegiado foi remarcada.', quantidade=3)
    vinculo = usuario_do_inicio.get_vinculo()
    tela.ir(NOTIFICACOES)
    botao = tela.loc(f'//a[@href="{MARCAR_TODAS_COMO_LIDAS}" and contains(., "Marcar todas como lidas")]').first
    expect(botao).to_be_visible()
    botao.click()

    tela.sucesso('Todas as suas notificações foram marcadas como lida com sucesso.')
    assert not RegistroNotificacao.objects.filter(vinculo=vinculo, lida=False).exists(), 'a UI disse que marcou todas, mas sobrou não lida'


def test_visualiza_uma_notificacao_isolada(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """A tela de uma notificação mostra a mensagem e a marca como lida.

    É a URL que ``RegistroNotificacao.get_absolute_url`` publica, isto é, o link que chega ao
    usuário por fora da caixa (e-mail, notificação do navegador). O que se afirma é o par:
    o corpo da mensagem na tela **e** a leitura gravada — a view faz as duas coisas e nada além
    disso.
    """
    from comum.models import RegistroNotificacao

    mensagem = 'Sua solicitação de sala foi deferida pelo avaliador.'
    tela = Tela(logado_efemero('dono_do_inicio'))
    registro = notificar_o_inicio('Reserva deferida', mensagem)[0]
    tela.ir(NOTIFICACAO.format(registro=registro.pk))

    tela.ver_texto(mensagem)
    assert RegistroNotificacao.objects.get(pk=registro.pk).lida, 'a notificação foi aberta, mas continuou não lida'


def test_remove_uma_notificacao_pela_listagem(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """O botão "Remover" da listagem apaga o registro — e só o dono o enxerga.

    A listagem do admin filtra por ``vinculo=request.user.get_vinculo()``
    (``RegistroNotificacaoAdmin.get_queryset``), então o botão só existe para quem recebeu a
    notificação: o que se afirma aqui é a remoção, mas o caminho já depende desse recorte.

    O botão é localizado pelo ``href`` **e** pelo rótulo, como na fatia de preferências: a
    listagem monta esses links à mão (``get_opcoes``), e um ``pk`` errado ali apagaria a
    notificação de outra linha sem nenhum sintoma visível.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    registro = notificar_o_inicio('Aviso a remover', 'Este aviso será removido pelo teste.')[0]
    tela.ir(LISTAGEM_ADMIN)
    botao = tela.loc(f'//a[@href="{REMOVER_NOTIFICACAO.format(registro=registro.pk)}" and contains(., "Remover")]').first
    expect(botao).to_be_visible()
    botao.click()

    tela.sucesso('A notificação foi removida com sucesso.')
    assert not RegistroNotificacao.objects.filter(pk=registro.pk).exists(), 'a UI disse que removeu, mas o registro continua no banco'


def test_marca_leitura_em_lote_pela_acao_do_admin(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """Marca como lida pela ação em massa e desmarca chamando a rota em lote diretamente.

    Os dois sentidos num teste só porque o segundo repõe o que o primeiro desfez. A ida é pela
    ação em massa do admin, que é o único lugar que monta a URL com ``?ids=``
    (``RegistroNotificacaoAdmin.marcar_como_lida``). A volta é por ``Tela.buscar``: sem
    ``Referer`` a view redireciona para si mesma **sem a query string** e o ``ids`` da segunda
    passada viria ``None`` — por isso o que se afirma ali é o 302 e o banco, não a tela seguinte.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    registro = notificar_o_inicio('Lote de leitura', 'Notificação marcada em lote pelo teste.')[0]
    tela.ir(LISTAGEM_ADMIN)
    tela.selecionar_item(str(registro))
    tela.preencher('Ação', 'lista', 'Marcar como lida')
    # A ação do admin não grava: ela redireciona para a rota em lote com `?ids=`. Capturar esse
    # 302 é o que prova o fio entre a ação e a view — sem isso o teste passaria com a ação
    # apontando para qualquer outra rota que também marcasse a leitura.
    with tela.pagina.expect_response(lambda resposta: MARCAR_COMO_LIDA_EM_LOTE in resposta.url) as captura:
        tela.clicar_acao('Aplicar')

    assert captura.value.status == 302, f'a ação em massa devolveu {captura.value.status} na rota em lote'
    tela.sucesso('Notificações marcadas como lida com sucesso.')
    assert RegistroNotificacao.objects.get(pk=registro.pk).lida, 'a ação em massa não marcou a notificação como lida'

    resposta = tela.buscar(MARCAR_COMO_NAO_LIDA_EM_LOTE + f'?ids={registro.pk}')

    assert resposta.status == 302, f'a rota em lote devolveu {resposta.status} em vez de redirecionar de volta'
    assert not RegistroNotificacao.objects.get(pk=registro.pk).lida, 'a rota em lote não desmarcou a leitura'


def test_remove_em_lote_pela_acao_do_admin(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """A ação "Remover" em massa apaga as selecionadas, respeitando o bloqueio de remoção.

    Separada da ação de leitura porque a view tem uma regra que a outra não tem: ela só apaga o
    registro cujo ``data_permite_excluir`` já passou, e **pula** em silêncio o que ainda está
    bloqueado. A segunda notificação do teste tem o desbloqueio no futuro justamente para essa
    metade da regra não ficar sem asserção.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    livre = notificar_o_inicio('Lote a remover', 'Notificação removida em lote pelo teste.')[0]
    bloqueada = notificar_o_inicio('Lote bloqueado', 'Notificação que ainda não pode ser removida.')[0]
    RegistroNotificacao.objects.filter(pk=bloqueada.pk).update(data_permite_excluir=bloqueada.data_permite_excluir.replace(year=2999))
    tela.ir(LISTAGEM_ADMIN)
    resposta = tela.buscar(REMOVER_EM_LOTE + f'?ids={livre.pk},{bloqueada.pk}')

    assert resposta.status == 302, f'a rota em lote devolveu {resposta.status} em vez de redirecionar de volta'
    assert not RegistroNotificacao.objects.filter(pk=livre.pk).exists(), 'a rota em lote não removeu a notificação liberada'
    assert RegistroNotificacao.objects.filter(pk=bloqueada.pk).exists(), 'a rota em lote removeu uma notificação ainda bloqueada'


def test_exclui_as_notificacoes_lidas_ha_mais_de_um_mes(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """A faxina apaga só o que está lido **e** tem mais de trinta dias.

    As duas condições juntas são a regra inteira da view, e a única forma de observar a segunda
    é ter no banco uma notificação recente que sobrevive à faxina. O botão só aparece quando há
    o que excluir (``qtd_notificacoes_antigas``), então o número no rótulo também é afirmação:
    o teste clica por "notificações antigas" e confere no banco quem ficou.
    """
    from comum.models import RegistroNotificacao

    tela = Tela(logado_efemero('dono_do_inicio'))
    antiga = notificar_o_inicio('Aviso antigo', 'Notificação lida há muito tempo.', dias_atras=90)[0]
    RegistroNotificacao.objects.filter(pk=antiga.pk).update(lida=True)
    recente = notificar_o_inicio('Aviso recente', 'Notificação lida hoje mesmo.')[0]
    RegistroNotificacao.objects.filter(pk=recente.pk).update(lida=True)
    tela.ir(NOTIFICACOES)
    botao = tela.loc(f'//a[@href="{EXCLUIR_ANTIGAS}" and contains(., "notificações antigas")]').first
    expect(botao).to_be_visible()
    botao.click()

    tela.sucesso('Todas as suas notificações lidas há mais de um mês foram excluídas.')
    assert not RegistroNotificacao.objects.filter(pk=antiga.pk).exists(), 'a UI disse que excluiu, mas a notificação antiga continua no banco'
    assert RegistroNotificacao.objects.filter(pk=recente.pk).exists(), 'a faxina levou junto uma notificação lida hoje'


def test_contador_e_rolagem_infinita_do_cabecalho(logado_efemero, usuario_do_inicio, notificar_o_inicio):
    """Os dois endpoints de AJAX do cabeçalho: quantas faltam ler e a próxima âncora da lista.

    Não são telas, mas têm contrato afirmável e é por eles que a caixa cresce ao rolar
    (``notificacoes.html``), então entram como exercício e não como dispensa. O contador é
    espelhado no ORM em vez de fixado numa magnitude — o banco de e2e é reusado e o número
    absoluto dependeria da execução anterior.

    O fim da lista também é JSON (``{"itens": ""}``), e não HTML: antes do #17389 a view
    devolvia ``None`` e o ``@rtr()`` o renderizava como ``default.html`` com status 200, o que
    fazia o ``$.ajax`` do cabeçalho (``dataType: "json"``) cair no ``.fail()``. Por isso o teste
    afirma o JSON decodificado, e não o status: um ``assert status == 200`` não afirmaria nada.

    A rolagem pagina por cursor (#17451): o parâmetro é o pk do último item exibido, e a resposta
    é a não lida seguinte a ele — depois da mais recente vem a do meio; depois da mais antiga, o fim.
    """
    import json

    from comum.models import RegistroNotificacao

    assunto = 'Rolagem infinita'
    tela = Tela(logado_efemero('dono_do_inicio'))
    registros = notificar_o_inicio(assunto, 'Notificação usada na rolagem da caixa.', quantidade=3)
    vinculo = usuario_do_inicio.get_vinculo()
    resposta = tela.buscar(CONTADOR)

    assert json.loads(resposta.text())['contador'] == RegistroNotificacao.objects.filter(vinculo=vinculo, lida=False).count(), (
        'o contador do cabeçalho divergiu das notificações não lidas do vínculo'
    )

    corpo = json.loads(tela.buscar(BUSCA_NOTIFICACAO.format(ultimo_pk=registros[-1].pk)).text())

    assert f'data-article="{registros[-2].pk}"' in corpo['itens'], 'a rolagem infinita não devolveu a âncora seguinte à mais recente'

    fim = tela.buscar(BUSCA_NOTIFICACAO.format(ultimo_pk=registros[0].pk))

    assert fim.headers['content-type'] == 'application/json', 'o fim da lista virou HTML e o $.ajax do cabeçalho cai no .fail()'
    assert json.loads(fim.text()) == {'itens': ''}, 'o fim da lista não devolveu o JSON de "acabou"'
