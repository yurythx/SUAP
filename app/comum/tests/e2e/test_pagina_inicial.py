"""Fluxo: a página inicial — os quadros, os alertas e as pendências que todo usuário vê ao entrar.

A tela `/` do SUAP é uma casca: ela sobe vazia e busca o conteúdo por **onze** endpoints de AJAX
do ``comum`` (``comum/static/comum/js/index.js``). Três montam as colunas de quadros, quatro
trazem as caixas de aviso/pendência da lateral, três gravam o leiaute do usuário e um é o painel
do secretário acadêmico. Todos moram em ``comum/urls.py`` e nenhum deles aparece numa barra de
endereço — a décima segunda rota desta família, ``/comum/index/exibir_quadro/``, é a única que é
tela de verdade, e é por ela que o usuário desfaz o que escondeu.

A regressão que este arquivo pega é a da casca vazia: se um desses endpoints começar a responder
erro ou branco, a página inicial continua carregando **sem nada** — sem 500, sem mensagem, sem
nenhum sinal para quem opera. O que se afirma aqui é o par (a página pede o endereço certo, o
endereço devolve o conteúdo certo).

Dois recortes deliberados, e é honesto dizê-los em vez de fingir cobertura:

* **quadro e pendência de outros apps não são montados aqui.** ``minhas_pendencias`` e o "Fique
  atento!" são alimentados por sinais (``index_atribuidos_a_mim``, ``index_inscricoes``) que ~30
  apps implementam; o ``comum`` implementa exatamente dois — a solicitação de reserva de sala
  aguardando avaliação e a manutenção programada —, e é sobre esses dois que estão as asserções
  de conteúdo. Montar o domínio de outro módulo aqui inverteria a dependência entre os apps.
* **``meus_avisos``, ``minhas_pendencias_coletivas`` e o painel do secretário só têm o estado
  vazio ao alcance** do ``comum``: nenhum produtor de ``index_infos_data`` nem de
  ``index_atribuidos_a_meus_grupos_data`` mora aqui, e o painel exige o grupo ``Secretário
  Acadêmico`` e a cadeia acadêmica do ``edu``. O vazio também é contrato — é o que faz o script
  remover a caixa em vez de deixar um bloco em branco —, então é ele que se afirma.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo, com `{}` no lugar do parâmetro — armadilha 17 da receita.
INICIO = '/'
MEUS_AVISOS = '/comum/index/meus_avisos/'
MEUS_ALERTAS = '/comum/index/meus_alertas/'
MINHAS_PENDENCIAS = '/comum/index/minhas_pendencias/'
MINHAS_PENDENCIAS_COLETIVAS = '/comum/index/minhas_pendencias_coletivas/'
MEUS_QUADROS = '/comum/index/meus_quadros/'
MEUS_QUADROS_POR_COLUNA = '/comum/index/meus_quadros_por_coluna/{coluna}/'
MEU_QUADRO = '/comum/index/meu_quadro/{id_quadro}/'
ESCONDER_QUADRO = '/comum/index/esconder_quadro/'
EXIBIR_QUADRO = '/comum/index/exibir_quadro/'
LAYOUT = '/comum/index/layout/'
MARCAR_QUADRO_COMO_LIDO = '/comum/index/marcar_quadro_como_lido/{hash}/'
PAINEL_SECRETARIO = '/comum/index/painel_controle_secretario_academico/'

# O quadro que esta fatia usa de cobaia, e o seu `id` (o `base64` do título em caixa alta, que é
# a chave com que `layout.quadro` registra o receptor — `dispatch_uid=titulo.upper()`).
#
# É o `Atalhos`, e não outro, por dois motivos medidos: é o único quadro do `comum` sem
# `global_cache` nem `session_cache` (os cacheados vêm de um `LocMemCache` de PROCESSO que
# sobrevive entre testes, e o teste leria o quadro da chamada anterior), e é o único cujo
# conteúdo o teste controla, porque lista `request.user.atalho_set`.
QUADRO_INICIO = 'Atalhos'
ID_QUADRO_INICIO = 'QVRBTEhPUw=='

# Hash arbitrário: a view grava em ``IndexLayout.hash_quadros`` o que vier na URL, sem
# interpretar. Ver a nota no teste do ciclo do quadro sobre o que isso deixa de fora.
HASH_DO_QUADRO = 'e2ehashquadro'


def test_pendencia_de_reserva_aparece_na_pagina_inicial(logado_comum, solicitacao_pendente):
    """A solicitação aguardando avaliação vira pendência do avaliador na página inicial.

    É a única pendência que o próprio ``comum`` produz (``index_atribuidos_a_mim``), e ela liga
    duas coisas que nada mais liga: a permissão ``pode_avaliar_solicitacao_reserva_de_sala`` e a
    contagem de ``salas_avaliadas``. Um avaliador que perdesse o vínculo com a sala continuaria
    vendo a tela de avaliação e pararia de ser avisado de que há o que avaliar — sem erro nenhum.

    O ``expect_response`` em volta da navegação é o que prova o fio: a página tem de **pedir**
    ``minhas_pendencias``. Sem ele, o teste passaria com o conteúdo vindo de qualquer outro
    lugar.
    """
    tela = Tela(logado_comum('avaliador_sala'))

    with tela.pagina.expect_response(lambda resposta: MINHAS_PENDENCIAS in resposta.url) as captura:
        tela.ir(INICIO)

    assert captura.value.status == 200, f'a página inicial pediu as pendências e recebeu HTTP {captura.value.status}'
    pendencias = tela.quadro('Minhas pendências')
    pendencias.ver_texto('Solicitação de Reserva de Salas')
    pendencias.ver_texto('aguardando avaliação')


def test_manutencao_programada_aparece_no_fique_atento(logado_efemero, usuario_do_inicio, manutencao_programada):
    """A manutenção em cartaz vira alerta na lateral da página inicial.

    ``index_inscricoes`` é o outro (e último) produtor de conteúdo de página inicial que mora no
    ``comum``, e a regra dele tem duas datas: a manutenção só aparece depois de
    ``data_hora_inicio_notificacao`` e antes de ``data_hora_atualizacao``. É a janela que decide
    se a comunidade é avisada da parada — e é o tipo de regra que se apaga numa refatoração sem
    ninguém perceber, porque o sintoma é a ausência de um aviso.
    """
    tela = Tela(logado_efemero('dono_do_inicio'))

    with tela.pagina.expect_response(lambda resposta: MEUS_ALERTAS in resposta.url) as captura:
        tela.ir(INICIO)

    assert captura.value.status == 200, f'a página inicial pediu os alertas e recebeu HTTP {captura.value.status}'
    tela.ver_texto('Manutenção programada')
    tela.ver_texto(manutencao_programada.sistema_ou_servico)


def test_endereco_de_alerta_sem_produtor_devolve_vazio(logado_efemero, usuario_do_inicio):
    """Sem nada a dizer, os endpoints de alerta devolvem corpo em branco — e a caixa some.

    Não é um teste de "deu 200": o branco **é** o contrato. ``index.js`` remove o bloco inteiro
    quando ``!data.trim()``, e o painel do secretário é escondido pela mesma regra. Se um deles
    passar a devolver marcação vazia (um ``<div>`` de moldura, por exemplo), a página inicial
    ganha uma caixa vazia permanente para todo mundo, sem erro nenhum.

    Os três estão juntos porque é o mesmo fato sobre o mesmo usuário, e nenhum deles tem produtor
    dentro do ``comum`` (ver o recorte declarado na docstring do módulo).
    """
    tela = Tela(logado_efemero('dono_do_inicio')).ir(INICIO)

    for rota in (MEUS_AVISOS, MINHAS_PENDENCIAS_COLETIVAS, PAINEL_SECRETARIO):
        resposta = tela.buscar(rota)
        assert resposta.status == 200, f'{rota} devolveu HTTP {resposta.status}'
        assert not resposta.text().strip(), f'{rota} devolveu marcação para um usuário sem nada a mostrar: {resposta.text()[:200]!r}'


def test_quadro_de_atalhos_responde_nos_tres_enderecos(logado_efemero, usuario_do_inicio, atalho_do_inicio):
    """O mesmo quadro sai pelos três endpoints que a página inicial usa, e leva o atalho do usuário.

    Os três existem porque são três consumidores diferentes (a coluna que a página monta, o
    quadro isolado e o pacote JSON das três colunas) e **cada um remonta o quadro por conta
    própria** — ``meus_quadros_por_coluna`` e ``meus_quadros`` repetem, lado a lado em
    ``comum/views.py``, a mesma lógica de coluna, cache e visibilidade. Duplicação que só
    permanece coerente por vigilância é exatamente o que um teste segura.

    O quadro é o ``Atalhos`` por dois motivos medidos: é o único do ``comum`` sem
    ``global_cache``/``session_cache`` (os cacheados vêm de um ``LocMemCache`` de processo que
    sobrevive entre testes) e é o único cujo conteúdo o teste controla, porque lista
    ``request.user.atalho_set``.
    """
    tela = Tela(logado_efemero('dono_do_inicio'))

    with tela.pagina.expect_response(lambda resposta: MEUS_QUADROS_POR_COLUNA.format(coluna='esquerda') in resposta.url) as captura:
        tela.ir(INICIO)

    assert captura.value.status == 200, f'a coluna da esquerda devolveu HTTP {captura.value.status}'
    tela.quadro(QUADRO_INICIO).ver_texto(atalho_do_inicio.nome)

    isolado = tela.buscar(MEU_QUADRO.format(id_quadro=ID_QUADRO_INICIO))

    assert isolado.status == 200, f'o quadro isolado devolveu HTTP {isolado.status}'
    assert atalho_do_inicio.nome in isolado.text(), 'o quadro isolado não trouxe o atalho do usuário'

    colunas = json.loads(tela.buscar(MEUS_QUADROS).text())

    assert set(colunas) == {'esquerda', 'centro', 'direita'}, f'o pacote de quadros mudou de forma: {sorted(colunas)}'
    chaves = [quadro[0] for coluna in colunas.values() for quadro in coluna]
    assert QUADRO_INICIO.upper() in chaves, f'o quadro {QUADRO_INICIO} sumiu do pacote das três colunas: {chaves}'


def test_ciclo_do_quadro_escondido(logado_efemero, usuario_do_inicio, atalho_do_inicio):
    """Esconder o quadro, reposicioná-lo, marcá-lo como lido e exibi-lo de volta.

    Uma cadeia e não quatro testes porque ``IndexLayout`` **só existe depois de esconder**: é
    ``esconder_quadro`` que cria a linha do usuário, ``layout`` e ``marcar_quadro_como_lido``
    dependem de ela existir, e ``exibir_quadro`` a apaga. Separados, os três últimos teriam de
    forjar a linha por ORM e passariam a afirmar o próprio setup.

    Terminar em ``exibir_quadro`` não é acabamento: é o que devolve a página inicial do usuário
    ao estado de origem, e é o que faz a segunda execução da suíte, no banco reusado, partir de
    onde a primeira partiu.

    Os três gravadores são ``POST`` de AJAX puro (``index.js``), sem gesto de tela que os alcance
    sozinhos — ``esconder_quadro`` responde ``PermissionDenied`` a um ``GET`` —, e são
    ``@csrf_exempt``. Só o primeiro tem botão: por isso ele vai pelo clique e os outros dois por
    ``Tela.postar``.

    **Coberto, mas não exercitado por inteiro**: ``marcar_quadro_como_lido`` grava o hash que
    vier na URL e nada mais; o efeito dele — esconder o quadro cujas notícias já foram vistas —
    só aparece em quadro que produza ``ItemNoticia``, e o único do ``comum`` é o de RSS, que
    depende de uma URL externa. O que se afirma aqui é a gravação.
    """
    from comum.models import IndexLayout

    usuario = usuario_do_inicio.get_user()
    tela = Tela(logado_efemero('dono_do_inicio')).ir(INICIO)

    quadro = tela.quadro(QUADRO_INICIO)
    # O botão vive num dropdown do bootstrap: só existe no DOM depois de o toggle ser clicado,
    # e `clicar_botao` exige elemento visível.
    quadro.loc('//button[contains(@class, "dropdown-toggle")]').first.click()
    with tela.pagina.expect_response(lambda resposta: ESCONDER_QUADRO in resposta.url) as captura:
        quadro.clicar_botao('Esconder quadro')

    assert captura.value.status in (200, 302), f'esconder o quadro devolveu HTTP {captura.value.status}'
    linha = IndexLayout.objects.get(usuario=usuario, quadro_nome=QUADRO_INICIO.upper())
    assert linha.escondido, 'o quadro sumiu da tela, mas o leiaute do usuário não registrou que ele está escondido'

    lido = tela.postar(MARCAR_QUADRO_COMO_LIDO.format(hash=HASH_DO_QUADRO), {'titulo': QUADRO_INICIO.upper()})

    assert lido.status == 302, f'marcar o quadro como lido devolveu HTTP {lido.status}'
    linha.refresh_from_db()
    assert linha.hash_quadros == HASH_DO_QUADRO, 'a view respondeu, mas não gravou o hash do quadro lido'

    movido = tela.postar(LAYOUT, {'titulo': QUADRO_INICIO.upper(), 'coluna': '2', 'ordem': '0'})

    assert movido.status == 200, f'reposicionar o quadro devolveu HTTP {movido.status}'
    linha.refresh_from_db()
    assert linha.quadro_coluna == 2, f'o quadro continuou na coluna {linha.quadro_coluna} depois de ser arrastado para a 2'

    tela.ir(EXIBIR_QUADRO)
    tela.loc(f'//input[@name="quadros" and @value="{linha.pk}"]').first.check()
    tela.clicar_botao('Exibir')

    tela.sucesso('Atualização exibida com sucesso.')
    assert not IndexLayout.objects.filter(pk=linha.pk).exists(), 'a UI disse que exibiu o quadro, mas o leiaute escondido continuou gravado'


def test_quadro_escondido_some_da_coluna(logado_efemero, usuario_do_inicio, atalho_do_inicio):
    """Escondido, o quadro deixa de sair na coluna — que é o efeito pelo qual o usuário paga.

    Separado do ciclo porque afirma outra coisa: lá o que importa é a **gravação** de cada um dos
    quatro gestos; aqui é a **consequência** da gravação sobre quem monta a página
    (``_quadros_list_da_coluna``). São dois trechos de código diferentes, e o segundo é o que o
    usuário enxerga.

    O leiaute é forjado por ORM de propósito: o efeito colateral de um teste nunca é o setup de
    outro, e quem cobre o gesto de esconder pela interface é o teste do ciclo.
    """
    from comum.models import IndexLayout

    usuario = usuario_do_inicio.get_user()
    escondido = IndexLayout.objects.create(usuario=usuario, quadro_nome=QUADRO_INICIO.upper(), quadro_coluna=1, quadro_ordem=1, escondido=True)

    tela = Tela(logado_efemero('dono_do_inicio'))
    coluna = tela.buscar(MEUS_QUADROS_POR_COLUNA.format(coluna='esquerda'))

    assert coluna.status == 200, f'a coluna devolveu HTTP {coluna.status}'
    assert atalho_do_inicio.nome not in coluna.text(), 'o quadro estava marcado como escondido e mesmo assim saiu na coluna'

    tela.ir(EXIBIR_QUADRO)
    expect(tela.loc(f'//input[@name="quadros" and @value="{escondido.pk}"]').first).to_be_visible()
