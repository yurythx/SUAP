"""Fluxo: as rotas de apoio do ``comum`` — prévia de público-alvo, leitor SIAFI e chaves públicas.

Quatro rotas que não pertencem a nenhum fluxo de tela e que, por isso mesmo, ninguém percebe
quando quebram:

* ``/comum/publico/<id>/visualizar/`` — a prévia de um ``Publico``, o objeto que define "para quem
  esta notificação/este edital vai". Ele guarda um filtro de queryset em texto, montado no admin;
  a prévia é a **única** forma de conferir se o filtro resolve antes de disparar a comunicação;
* ``/comum/ver_arquivo_siafi/`` — o leitor de arquivos de largura fixa do SIAFI, usado pela
  contabilidade;
* ``/comum/get_chave_publica_suap/`` e ``/comum/jwk/`` — os dois endpoints **de máquina**, sem
  autenticação: o primeiro entrega a chave SSH pública que o instalador do terminal de ponto
  consome, o segundo publica a chave de assinatura no formato JWK que valida os tokens emitidos
  pelo SUAP. Não são telas; o que há para afirmar é o contrato (status, tipo do conteúdo e forma
  do corpo), e é o que estes testes afirmam;
* ``/comum/get_subojetivos_ods_onu/`` — o autocomplete dos Objetivos de Desenvolvimento
  Sustentável da ONU, que vários formulários do SUAP (projetos, pesquisa, extensão) usam para
  classificar uma proposta. Também é contrato de JSON, e no dialeto do select2 (``results``,
  ``id``, ``text``).

Divisão de trabalho com os fluxos: o cruzamento dos dois arquivos de largura fixa (filtro,
paginação pela sessão) é afirmado em ``comum/tests/fluxos/test_fluxo_arquivo_siafi.py``; aqui o
envio é feito pelo navegador, que é o único que pega o que o cliente de teste do Django deixa
passar.

Histórico (#17394): o POST era inalcançável duas vezes. ``comum/views.formatar_ref`` iterava o
arquivo enviado — que o Django entrega em **bytes** — e fazia ``i[41:].split(',')`` com separador
``str`` (``TypeError``; corrigido decodificando como latin-1, como a irmã ``get_itens``). E o
template montava o ``<form method=post>`` sem ``{% csrf_token %}``: todo envio real respondia 403.
"""

from __future__ import annotations

import json

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
VISUALIZAR_PUBLICO = '/comum/publico/{pk}/visualizar/'
VER_ARQUIVO_SIAFI = '/comum/ver_arquivo_siafi/'
CHAVE_PUBLICA = '/comum/get_chave_publica_suap/'
JWK = '/comum/jwk/'
SUBOBJETIVOS_ODS = '/comum/get_subojetivos_ods_onu/'


def test_previa_do_publico_alvo_executa_o_filtro(logado_comum, publico_e2e, servidores_comum):
    """A prévia resolve o filtro do público e lista quem ele alcança.

    O filtro do ``Publico`` é texto interpretado em tempo de execução, e a view o executa dentro
    de um ``try`` que transforma **qualquer** erro num redirect com mensagem. Quer dizer: um
    filtro quebrado não aparece como erro de programação, aparece como uma tela que some. Por isso
    a asserção é o nome de quem o público alcança, e não o cabeçalho da página.
    """
    esperado = servidores_comum['gestor_pessoal']

    tela = Tela(logado_comum('gestor_pessoal')).ir(VISUALIZAR_PUBLICO.format(pk=publico_e2e.pk))

    tela.ver_texto(f'Público: {publico_e2e.nome}')
    tela.ver_texto(esperado.pessoa_fisica.nome)


def test_leitor_de_arquivo_siafi_mostra_o_arquivo_cruzado_com_o_layout(logado_comum):
    """O leitor SIAFI recebe o layout e os dados e devolve a tabela com as colunas do layout.

    Pelo navegador, de ponta a ponta: é o que pega o formulário sem token CSRF (403 no envio),
    que o cliente de teste do Django não impõe. O formulário é montado com ``form.as_table`` num
    template próprio, fora do ``render_form`` do djtools.
    """
    tela = Tela(logado_comum('solicitante')).ir(VER_ARQUIVO_SIAFI)
    tela.ver_titulo('Visualizar Arquivos SIAFI')

    # Layout: 40 posições de descrição, 1 de tipo, o resto tamanho. Dados: posicionais.
    layout = f'{"UNIDADE GESTORA":<40}N6\n{"CREDOR":<40}A10'.encode('latin-1')
    dados = b'153080PAPELARIA \n153081GRAFICA   '
    tela.campo('Arquivo Ref', 'arquivo').first.set_input_files({'name': 'ref.txt', 'mimeType': 'text/plain', 'buffer': layout})
    tela.campo('Arquivo Siafe', 'arquivo').first.set_input_files({'name': 'siafi.txt', 'mimeType': 'text/plain', 'buffer': dados})
    tela.clicar_botao('Visualizar')

    tela.ver_texto('Conteúdo do arquivo siafe siafi.txt')
    tela.ver_texto('PAPELARIA')
    tela.ver_texto('153081')


def test_chave_publica_ssh_do_suap(pagina_anonima, chaves_publicas_configuradas):
    """O endpoint que o instalador do terminal de ponto consome, sem autenticação.

    Anônimo porque é assim que ele é usado: o script de instalação do terminal baixa a chave para
    liberar o acesso SSH sem senha. Exigir sessão aqui quebraria a instalação de todo terminal
    novo — e nada na tela avisaria.

    O ``Content-Disposition`` faz parte do contrato: o instalador salva o arquivo pelo nome que
    vem no cabeçalho.
    """
    resposta = Tela(pagina_anonima).buscar(CHAVE_PUBLICA)

    assert resposta.status == 200, f'a chave pública respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'].startswith('text/plain'), f'a chave veio como {resposta.headers["content-type"]!r}'
    assert 'suap-chave-publica.pub' in resposta.headers['content-disposition'], 'o nome do arquivo da chave pública mudou'
    assert resposta.text() == chaves_publicas_configuradas['chave_publica'], 'o endpoint não devolveu a chave gravada na configuração'


def test_jwk_publica_a_chave_de_assinatura(pagina_anonima, chaves_publicas_configuradas):
    """O JWKS do SUAP: JSON com a lista ``keys``, sem autenticação.

    É o endereço que um consumidor de token do SUAP busca para validar assinatura, então a forma
    do corpo **é** o contrato — uma chave fora da lista ``keys``, ou a lista renomeada, quebra
    todo cliente sem quebrar nada aqui dentro.
    """
    resposta = Tela(pagina_anonima).buscar(JWK)

    assert resposta.status == 200, f'o JWKS respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'].startswith('application/json'), f'o JWKS veio como {resposta.headers["content-type"]!r}'
    corpo = json.loads(resposta.text())
    assert list(corpo) == ['keys'], f'o JWKS mudou de forma: {sorted(corpo)}'
    assert corpo['keys'] == [{}], 'nenhuma chave deveria ter sido retornada, pois ela ainda não foi configurada.'


def test_subobjetivos_da_ods_filtram_pelo_objetivo_escolhido(logado_comum, ods_e2e):
    """O autocomplete de subobjetivos da ONU só pode devolver os do objetivo escolhido.

    É um endpoint de select2: quem o consome é o segundo campo de um par encadeado — escolhido o
    objetivo, o formulário repopula os subobjetivos. Se o filtro deixar de ser aplicado, a tela
    continua funcionando e passa a oferecer as 169 metas da ONU misturadas; por isso a asserção
    é dupla, o que **veio** e o que **não veio**.

    Sem ``?ids`` a rota respondia 500: ``''.split(',')`` é ``['']`` e o
    ``filter(objetivo__in=[''])`` levantava ``ValueError`` (#17395). Agora os pedaços vazios e não
    numéricos são descartados e, sem objetivo escolhido, a resposta é lista vazia — não "todos",
    porque é autocomplete.
    """
    (objetivo, subobjetivo), (_, ignorado) = ods_e2e

    tela = Tela(logado_comum('solicitante'))
    resposta = tela.buscar(f'{SUBOBJETIVOS_ODS}?ids={objetivo.pk}')

    assert resposta.status == 200, f'o autocomplete de subobjetivos respondeu HTTP {resposta.status}'
    corpo = json.loads(resposta.text())
    assert list(corpo) == ['results'], f'o endpoint saiu do dialeto do select2: {sorted(corpo)}'

    devolvidos = {item['id']: item['text'] for item in corpo['results']}
    assert subobjetivo.pk in devolvidos, f'o subobjetivo do objetivo escolhido não foi oferecido: {devolvidos}'
    assert ignorado.pk not in devolvidos, 'o autocomplete ofereceu um subobjetivo de OUTRO objetivo: o filtro por objetivo deixou de ser aplicado'
    assert devolvidos[subobjetivo.pk] == f'{subobjetivo.numero} - {subobjetivo.descricao}', (
        f'o rótulo do subobjetivo mudou de forma: {devolvidos[subobjetivo.pk]!r}'
    )

    sem_ids = tela.buscar(SUBOBJETIVOS_ODS)
    assert sem_ids.status == 200, f'o autocomplete sem ?ids respondeu HTTP {sem_ids.status}'
    assert json.loads(sem_ids.text()) == {'results': []}, 'sem objetivo escolhido o autocomplete deveria vir vazio'
