"""Fluxo: o site de documentação que o SUAP publica a partir da execução do behave.

``/comum/documentacao/`` é um site inteiro dentro do SUAP — índice, página de módulo, página de
funcionalidade, página de cenário, imagens dos passos e fluxogramas BPMN — montado **não** a
partir do código, mas dos artefatos que ``test_behave --behave_auto_doc`` deixa em
``settings.BEHAVE_AUTO_DOC_PATH`` ao rodar as ``.feature``. As seis rotas deste arquivo são esse
site, e ele é a única documentação de uso publicada para o usuário final.

Duas coisas governam o arquivo:

* **o par gerador↔leitor é o contrato.** Quem escreve o JSON é ``Documentacao.toJSON``
  (``djtools/new_tests/base_test.py:90-134``) e ``BehavePdfDocumentationService.build_index``
  (``djtools/new_tests/pdf_documentation.py:20``); quem o lê são estas seis views. A fixture
  ``documentacao_gerada`` reproduz exatamente a forma que o gerador grava, e é essa forma que os
  testes pinam — renomear uma chave de um lado quebra o outro em silêncio, porque não há
  esquema, só ``json.loads`` e indexação direta;
* **nenhuma das seis falha alto.** Sem os artefatos elas respondem ``httprr`` com aviso,
  ``HttpResponseBadRequest`` ou, no caso da imagem, ``httprr('/', 'Nenhuma imagem encontrada.')``.
  Um teste de status passaria com o site inteiro apagado do disco. Por isso toda asserção aqui é
  sobre o **conteúdo** renderizado.

As seis rotas são públicas — nenhuma tem ``login_required``, e é assim que a documentação é
consultada por quem ainda não entrou. Por isso os testes rodam em ``pagina_anonima``: exigir
sessão aqui seria a regressão.

Quatro das seis são **fragmentos de AJAX**, não páginas: o índice injeta o HTML delas no
``<main>`` por ``$.ajax``. Os links que disparam duas delas ficam no menu lateral, dentro de um
``<ul class="hide">`` que só a busca do próprio site expande — clicar num elemento escondido não
é o gesto do usuário, é uma encenação dele. Por isso o teste exercita o gesto real onde ele
existe (o índice e a página do módulo) e afirma o contrato do fragmento onde ele não existe.
"""

from __future__ import annotations

import pytest

from comum.tests.e2e.conftest import APLICACAO_DOCUMENTADA, BPMN_DOCUMENTADO, IMAGEM_DOCUMENTADA
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
DOCUMENTACAO = '/comum/documentacao/'
SOBRE_O_MODULO = '/comum/documentacao/about/{aplicacao}/'
SOBRE_A_FUNCIONALIDADE = '/comum/documentacao/about_feature/{aplicacao}/{funcionalidade}/'
SOBRE_O_CENARIO = '/comum/documentacao/cenario/{aplicacao}/{funcionalidade}/{cenario}/'
IMAGEM_DO_PASSO = '/comum/documentacao/imagem/'
FLUXOGRAMA_BPMN = '/comum/documentacao/bpmn/{aplicacao}/{bpmn}/'


def test_indice_publica_o_modulo_e_abre_a_pagina_dele(pagina_anonima, documentacao_gerada):
    """O índice lista o módulo por área, e clicar nele carrega a página do módulo no lugar.

    As duas rotas num teste porque a segunda é o que a primeira dispara: o índice não navega,
    ele faz ``$.ajax('/comum/documentacao/about/' + aplicacao + '/')`` e troca o conteúdo do
    ``<main>`` (``comum/templates/documentacao/docs.html``). O ``expect_response`` em volta do
    clique é o que liga o gesto à rota — sem ele o teste afirmaria só que o HTML mudou.

    O índice agrupa por **área**, uma chave que vem do JSON e não do Django: ``documentacao_view``
    percorre as aplicações do índice, abre o JSON de cada uma e indexa por ``aplicacao['area']``
    (``comum/views.py:3221-3231``). Se o gerador parar de gravar ``area``, a página abre com o
    menu vazio e status 200.

    A página do módulo, por sua vez, é a única das seis que mistura disco e banco: o título sai do
    ``AppConfig`` do Django (``app_config.verbose_name``), os perfis saem de ``GroupDetail`` e o
    fluxograma sai do JSON. É por isso que a asserção cita o ``verbose_name``, e não o nome que a
    fixture gravou.
    """
    from django.apps import apps

    rota_do_modulo = SOBRE_O_MODULO.format(aplicacao=APLICACAO_DOCUMENTADA)

    tela = Tela(pagina_anonima).ir(DOCUMENTACAO)
    tela.ver_texto('Selecione o módulo:')
    tela.ver_texto(documentacao_gerada['area'])
    tela.ver_texto(documentacao_gerada['nome'])

    with tela.pagina.expect_response(lambda resposta: rota_do_modulo in resposta.url) as captura:
        tela.loc(f'//main//a[@class="sobre"][@data-aplicacao="{APLICACAO_DOCUMENTADA}"]').first.click()
    assert captura.value.status == 200, f'a página do módulo respondeu HTTP {captura.value.status}'

    verbose_name = apps.get_app_config(APLICACAO_DOCUMENTADA).verbose_name
    tela.ver_texto(str(verbose_name))
    tela.ver_texto('Fluxogramas')

    # O fluxograma que a página do módulo publica é a rota de BPMN: é este `href` que liga as duas.
    opcao = tela.loc(f'//select[@id="js-url"]/option[@value="{FLUXOGRAMA_BPMN.format(aplicacao=APLICACAO_DOCUMENTADA, bpmn=BPMN_DOCUMENTADO)}"]')
    assert opcao.count(), 'a página do módulo não publicou o fluxograma declarado no JSON da documentação'


def test_paginas_de_funcionalidade_e_de_cenario(pagina_anonima, documentacao_gerada):
    """Os dois fragmentos do menu lateral: a funcionalidade e o cenário dentro dela.

    Por ``buscar`` e não por clique: os links que os disparam ficam no ``<aside>``, dentro de um
    ``<ul class="hide">`` que só abre depois de o usuário expandir a árvore ou buscar no campo do
    site. Clicar num elemento escondido à força não seria o gesto do usuário — e o que há para
    afirmar num fragmento de AJAX é o HTML que ele devolve, que é o que o ``<main>`` recebe.

    As duas rotas juntas porque a diferença entre elas é só a profundidade da navegação na mesma
    estrutura: a de funcionalidade varre ``funcionalidades`` procurando a ``chave``, a de cenário
    varre também ``cenarios``. As duas respondem ``HttpResponseBadRequest`` quando não acham —
    nunca 404 —, então a asserção é o texto que só aparece quando acharam.

    A contagem de passos é afirmada de propósito: é ela que liga o cenário às capturas de tela que
    o behave produziu, e um cenário sem passos é o sintoma de a documentação ter sido gerada por
    uma execução que falhou no meio.
    """
    funcionalidade = documentacao_gerada['funcionalidades'][0]
    cenario = funcionalidade['cenarios'][0]
    tela = Tela(pagina_anonima)

    resposta = tela.buscar(SOBRE_A_FUNCIONALIDADE.format(aplicacao=APLICACAO_DOCUMENTADA, funcionalidade=funcionalidade['chave']))
    assert resposta.status == 200, f'a página da funcionalidade respondeu HTTP {resposta.status}'
    corpo = resposta.text()
    assert funcionalidade['nome'] in corpo, 'a página da funcionalidade não trouxe o nome dela'
    assert funcionalidade['descricao'][0] in corpo, 'a página da funcionalidade não trouxe a descrição vinda da `.feature`'

    resposta = tela.buscar(SOBRE_O_CENARIO.format(aplicacao=APLICACAO_DOCUMENTADA, funcionalidade=funcionalidade['chave'], cenario=cenario['chave']))
    assert resposta.status == 200, f'a página do cenário respondeu HTTP {resposta.status}'
    corpo = resposta.text()
    assert cenario['nome'] in corpo, 'a página do cenário não trouxe o nome dele'
    assert f'{len(cenario["passos"])} passos' in corpo, 'a página do cenário não contou os passos — as capturas de tela perderam o vínculo'
    assert cenario['passos'][0]['nome'] in corpo, 'a página do cenário não listou o passo'


def test_imagem_do_passo_e_servida_do_diretorio_da_documentacao(pagina_anonima, documentacao_gerada):
    """As capturas de tela dos passos, servidas por uma rota própria e não pelo static.

    A rota monta o caminho com ``os.path.join(BEHAVE_AUTO_DOC_PATH, app, imagem)`` e devolve os
    bytes crus (``comum/views.py:3340-3351``). Quando o arquivo não existe ela **não** dá 404:
    redireciona para ``/`` com "Nenhuma imagem encontrada." — e um ``<img>`` quebrado é
    exatamente o que ninguém repara. Por isso a asserção é a assinatura do PNG, e não o status.
    """
    tela = Tela(pagina_anonima)

    resposta = tela.buscar(f'{IMAGEM_DO_PASSO}?app={APLICACAO_DOCUMENTADA}&i={IMAGEM_DOCUMENTADA}')

    assert resposta.status == 200, f'a imagem do passo respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'image/png', f'a imagem veio como {resposta.headers["content-type"]!r}'
    assert resposta.body().startswith(b'\x89PNG\r\n\x1a\n'), 'a rota devolveu algo que não é um PNG'


def test_fluxograma_bpmn_e_lido_do_diretorio_da_aplicacao(pagina_anonima, documentacao_gerada):
    """O BPMN vem do repositório, não do diretório da documentação — e é XML cru para o visualizador.

    Assimetria que o teste registra: as outras cinco rotas leem de ``BEHAVE_AUTO_DOC_PATH``, esta
    abre ``<aplicacao>/workflows/<bpmn>`` relativo ao diretório de execução
    (``comum/views.py:3354-3355``), isto é, um arquivo **versionado** no repositório. Quem o
    consome é o ``bpmn-js`` embutido na página do módulo, por ``$.ajax(url, {dataType: 'text'})``:
    o contrato é ``text/plain`` com o XML do diagrama. Devolvê-lo como HTML, ou com o
    ``Content-Type`` de XML, faz o visualizador desenhar um canvas vazio sem erro nenhum.
    """
    resposta = Tela(pagina_anonima).buscar(FLUXOGRAMA_BPMN.format(aplicacao=APLICACAO_DOCUMENTADA, bpmn=BPMN_DOCUMENTADO))

    assert resposta.status == 200, f'o fluxograma respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'text/plain', f'o fluxograma veio como {resposta.headers["content-type"]!r}'
    corpo = resposta.text()
    assert corpo.startswith('<?xml'), f'o fluxograma não veio como XML: {corpo[:80]!r}'
    assert '<bpmn:definitions' in corpo, 'o arquivo entregue não é um diagrama BPMN'
