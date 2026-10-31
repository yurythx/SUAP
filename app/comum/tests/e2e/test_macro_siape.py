"""Fluxo: as três macros SIAPE que a Gestão de Pessoas baixa para extrair dados do sistema federal.

O SUAP não fala com o SIAPE por API: ele **gera uma macro** (um XML de automação de terminal 3270)
que o operador roda no emulador, e o resultado dessa extração é o que alimenta o cadastro de
pessoal. As três rotas deste arquivo produzem esse arquivo — a extração completa, a
personalizável (o operador escolhe que arquivos extrair) e a de histórico de PCA de servidores
escolhidos.

A regressão que o arquivo pega é dupla e nenhuma metade aparece no status HTTP:

* a **compilação** — a macro é um template renderizado com a UF e o código da instituição vindos
  da ``Configuracao``. Sem as duas chaves, ``baixar_macro_siape`` devolve 200 com um pedido de
  configuração em texto (até #17394 era um 500: o ``.lower()`` estourava no ``None`` antes do
  guard). Com as chaves erradas, ela devolve 200 com um XML que o emulador rejeita. Por isso a
  asserção é o valor compilado dentro do corpo;
* a **poda do XML** da macro personalizável — ao desmarcar um arquivo do extrator, a view reescreve
  ``entryscreen``/``exitscreen`` e religa as telas restantes em cadeia
  (``comum/views.py:1014-1027``). É o único lugar do SUAP que manipula a árvore do XML da macro, e
  um erro ali produz um arquivo sintaticamente válido que trava o terminal no meio da extração.

Os três desfechos são download (``Content-Disposition: attachment``), e é por isso que os bytes
vêm do ``expect_download`` do Playwright e não da página: o Chromium headless converte a navegação
em download e descarta o corpo.
"""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
MACRO_COMPLETA = '/comum/baixar_macro_siape/'
MACRO_PERSONALIZAVEL = '/comum/baixar_macro_siape_personalizavel/'
MACRO_HISTORICO_PCA = '/comum/baixar_macro_siape_historico_pca/'


def _baixar_pelo_botao(tela: Tela, rotulo: str = 'Enviar') -> bytes:
    """Clica no submit e devolve os bytes do arquivo que a resposta manda baixar.

    O clique não navega: a resposta vem com ``Content-Disposition: attachment`` e o Chromium a
    converte em download, deixando a página onde estava. Quem carrega os bytes é o evento de
    download — ler o corpo da página aqui devolveria o formulário, não a macro.
    """
    with tela.pagina.expect_download() as captura:
        tela.clicar_botao(rotulo)
    download = captura.value
    assert download.suggested_filename == 'macro_siape.mac', f'o nome do arquivo baixado mudou: {download.suggested_filename!r}'
    with open(download.path(), 'rb') as arquivo:
        return arquivo.read()


@pytest.mark.parametrize(
    ('consulta', 'marcador', 'compilados'),
    [
        ('', '<!-- BEGIN AFASTAMENTOS -->', ('26435', 'rn')),
        ('?instituicao_anterior=152', '<!-- BEGIN MATRICULAS PCA-->', ('152',)),
        ('?extracao_sem_posicionamentos_que_estejam_sem_documento_legal=1', '<!-- BEGIN POSICIONAMENTO-->', ('ps26435[enter]',)),
    ],
    ids=['completa', 'pca-da-instituicao-anterior', 'pca-sem-documento-legal'],
)
def test_macro_completa_compila_a_configuracao_da_instituicao(logado_comum, instituicao_configurada, consulta, marcador, compilados):
    """A mesma rota entrega TRÊS macros diferentes, escolhidas por parâmetro de query.

    Parametrizado porque o que se verifica é exatamente o par (parâmetro, template): a view é um
    encadeado de ``if`` sobre ``request.GET`` (``comum/views.py:1042-1047``) e trocar a ordem
    deles — ou renomear um parâmetro no link que a chama — faz o operador baixar a macro errada
    sem nenhum sinal na tela. O ``marcador`` é um comentário que existe num único dos três
    templates; os três respondem 200 com o mesmo ``Content-Disposition``, então é ele que separa
    "baixou alguma macro" de "baixou a macro certa".

    ``compilados`` é o que cada template de fato interpola, e difere entre os três:

    * a completa usa ``{{cod_instituicao}}`` e ``{{uf}}``;
    * a de PCA da instituição anterior usa só ``{{cod_instituicao}}`` — e nela o código vem do
      parâmetro, não da ``Configuracao`` (``comum/views.py:1043``), que é o ponto da extração de
      PCA de servidor vindo de outro órgão;
    * a de PCA sem documento legal usa só ``{{cod_instituicao}}``, no comando ``ps`` que o operador
      digita no terminal. Até #17394 o template escrevia ``{{codigo_instituicao}}``, chave que a
      view não passa, e a macro saía com ``value="ps[enter]"`` — sem código de instituição nenhum.

    Por ``buscar`` e não por ``ir``: a rota não tem formulário nenhum, é download direto, e o que
    há para afirmar é o contrato da resposta (status, tipo, nome do arquivo e conteúdo compilado).
    """
    tela = Tela(logado_comum('gestor_pessoal_sistemico'))

    resposta = tela.buscar(f'{MACRO_COMPLETA}{consulta}')

    assert resposta.status == 200, f'a macro respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'plain/mac', f'a macro veio como {resposta.headers["content-type"]!r}'
    assert 'macro_siape.mac' in resposta.headers['content-disposition'], 'o nome do arquivo da macro mudou'

    corpo = resposta.text()
    assert marcador in corpo, f'a rota entregou outra macro que não a marcada por {marcador!r}'
    for valor in compilados:
        assert valor in corpo, f'a macro não compilou {valor!r} (a configuração da instituição é {instituicao_configurada})'


def test_macro_personalizavel_poda_o_xml_ao_desmarcar_um_arquivo(logado_comum, instituicao_configurada):
    """Desmarcar "Unidades Organizacionais" tem de mover a tela de entrada da macro.

    Este é o teste que justifica a rota existir. A macro completa entra pela tela
    ``unidadeorganizacional1`` e sai por ``historicosetorfim``; tirando o primeiro arquivo do
    extrator, a view precisa desligar ``entryscreen`` do bloco removido e promover o próximo
    (``comum/views.py:1014-1019``). O arquivo continua sendo um XML válido nos dois casos — quem
    percebe o erro é o terminal 3270 do operador, semanas depois.

    A asserção é feita no XML **parseado**, e não por substring: o que importa é qual ``screen``
    carrega o atributo, não que o atributo apareça em algum lugar do texto.
    """
    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(MACRO_PERSONALIZAVEL)
    tela.ver_titulo('Baixar macro SIAPE')

    # Todos os arquivos vêm marcados por `initial`; o fluxo real é o operador desmarcar o que não
    # quer. `preencher` só marca (`_preencher_escolha`), daí o `uncheck` pelo localizador.
    tela.campo('Arquivos do Extrator', 'checkbox multiplo', 'Unidades Organizacionais').first.uncheck()
    corpo = _baixar_pelo_botao(tela)

    raiz = ElementTree.fromstring(corpo)
    telas_de_entrada = [tela_xml.attrib['name'] for tela_xml in raiz.iter('screen') if tela_xml.attrib.get('entryscreen') == 'true']
    assert 'unidadeorganizacional1' not in telas_de_entrada, 'o arquivo desmarcado continuou sendo a tela de entrada da macro'
    assert telas_de_entrada, f'a macro saiu sem nenhuma tela de entrada; telas: {[t.attrib["name"] for t in raiz.iter("screen")][:5]}'
    assert raiz[0].attrib['entryscreen'] == 'false', 'o bloco do arquivo desmarcado continuou marcado como entrada'


def test_macro_de_historico_de_pca_leva_a_matricula_sipe_do_servidor(logado_comum, servidor_com_matricula_sipe):
    """A macro de histórico de PCA é gerada POR SERVIDOR: a matrícula SIAPE entra no arquivo.

    A escolha é um autocomplete múltiplo sobre os servidores com ``matricula_sipe`` — e é a
    matrícula SIAPE, não a do SUAP, que a macro digita no terminal. Trocar um campo pelo outro
    daria um arquivo perfeitamente válido que extrai o histórico da pessoa errada, e nada na tela
    diria isso; por isso a asserção é o valor de ``matricula_sipe`` dentro do corpo baixado.
    """
    servidor, matricula_sipe = servidor_com_matricula_sipe

    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(MACRO_HISTORICO_PCA)
    tela.ver_titulo('Macro para recuperar históricos de PCAs dos servidores')

    tela.preencher('Servidores', 'autocomplete multiplo', servidor.matricula, opcao=servidor.pessoa_fisica.nome)
    corpo = _baixar_pelo_botao(tela)

    assert matricula_sipe.encode() in corpo, 'a macro de histórico saiu sem a matrícula SIAPE do servidor escolhido'
