"""Fluxo: os cinco webservices que o terminal de ponto consome do SUAP.

Não são telas. São os endereços que o **terminal de ponto** (e o terminal do refeitório) busca
sozinho, de madrugada, para poder funcionar offline: a tabela de pessoas com as digitais e os dois
pacotes de fotos. Quem os quebra não vê nada quebrar — o SUAP continua inteiro; o que para é a
catraca do campus na manhã seguinte.

Três coisas governam o arquivo:

* **a autorização é por IP, não por sessão.** As cinco views abrem com
  ``ponto.Maquina.objects.get(ip=get_client_ip(request), ativo=True)`` e respondem
  ``PermissionDenied`` fora disso — não há login envolvido. Por isso os testes rodam em
  ``pagina_anonima``: exigir sessão aqui seria a regressão, não a proteção;
* **o que há para afirmar é o contrato**, não a aparência: status, tipo do conteúdo, nome do
  arquivo e a forma do que vem dentro do ``.zip``. O terminal é um cliente de terceiros e não
  tolera mudança de forma;
* **o dump é cacheado em disco por dia** (``comum/views.py:1302-1306``). A fixture
  ``terminal_sem_cache`` apaga o ``.zip`` no setup: sem isso a segunda execução do dia receberia
  o arquivo da primeira e o teste marcaria a rota como exercitada tendo rodado quatro linhas da
  view — inclusive depois de um ``--create-db``, porque o cache vive no disco e não no banco.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
DUMP_PESSOAS = '/comum/get_pessoas/'
DUMP_PESSOAS_VERSIONADO = '/comum/get_pessoas/{versao}/'
DUMP_PESSOA = '/comum/get_pessoa/{username}/{versao}/'
FOTOS_FUNCIONARIOS = '/comum/get_fotos_funcionarios/'
FOTOS_ALUNOS = '/comum/get_fotos_alunos/'

# Versão do firmware do terminal que liga as duas colunas extras do dump
# (`comum/views.py:1367-1372`: `pode_bater_ponto` e `senha_ponto` só saem de 1.2.0 para cima).
VERSAO_COM_SENHA_DE_PONTO = '1.2.0'

COLUNAS_SEM_SENHA_DE_PONTO = 10
COLUNAS_COM_SENHA_DE_PONTO = 12


def _linhas_do_dump(resposta) -> list[list[str]]:
    """Desempacota o ``.zip`` do terminal e devolve as linhas do ``COPY`` já separadas por coluna."""
    assert resposta.status == 200, f'o dump do terminal respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'application/zip', f'o dump veio como {resposta.headers["content-type"]!r}'
    assert 'dump_terminal.zip' in resposta.headers['content-disposition'], 'o nome do arquivo do dump mudou'

    pacote = zipfile.ZipFile(io.BytesIO(resposta.body()))
    assert pacote.namelist() == ['tabela_terminal.copy'], f'o dump mudou de estrutura: {pacote.namelist()}'
    texto = pacote.read('tabela_terminal.copy').decode()
    return [linha.split('\t') for linha in texto.splitlines() if linha]


def test_dump_de_pessoas_sem_versao_exporta_a_tabela_do_terminal(pagina_anonima, servidores_comum, terminal_sem_cache, maquina_e2e):
    """O terminal sem versão declarada recebe a tabela enxuta — e ela tem de chegar preenchida.

    Anônimo de propósito: quem chama é a catraca, que não tem sessão. A máquina do seed responde
    pelo ``127.0.0.1`` do ``live_server``, que é o que a view usa para autorizar.

    A asserção é dupla: a forma (dez colunas, um ``.zip`` com um único ``COPY``) e o conteúdo (um
    servidor conhecido está lá). Só a forma passaria com a tabela vazia — que é exatamente o
    desfecho de um ``JOIN`` que deixou de casar, o modo mais provável de esta view quebrar.
    """
    from ponto.models import MaquinaLog

    esperado = servidores_comum['solicitante']

    resposta = Tela(pagina_anonima).buscar(DUMP_PESSOAS)

    linhas = _linhas_do_dump(resposta)
    assert linhas, 'o dump do terminal saiu vazio: nenhuma pessoa foi exportada'
    assert all(len(linha) == COLUNAS_SEM_SENHA_DE_PONTO for linha in linhas), f'o dump mudou de largura: {sorted({len(linha) for linha in linhas})}'
    usernames = [linha[1] for linha in linhas]
    assert esperado.matricula in usernames, f'o servidor {esperado.matricula} não foi exportado para o terminal'

    assert MaquinaLog.objects.filter(maquina=maquina_e2e, operacao='comum_get_dump_pessoas').exists(), (
        'o dump foi servido sem registrar o acesso da máquina — é o log que audita o terminal'
    )


def test_dump_de_pessoas_versionado_acrescenta_a_senha_de_ponto(pagina_anonima, servidores_comum, terminal_sem_cache):
    """Declarar a versão do firmware muda o contrato: duas colunas a mais.

    Separado do teste anterior, e não parametrizado com ele, porque o que se afirma é justamente a
    **diferença**: ``obter_query`` monta colunas diferentes conforme a versão
    (``comum/views.py:1367-1372``), e um terminal antigo que recebesse as colunas novas — ou o
    contrário — lê a tabela deslocada e passa a barrar gente com digital válida.

    Declarar a versão também grava ``Maquina.versao_terminal`` (``comum/views.py:1298-1300``): é
    assim que o inventário de terminais do SUAP sabe qual firmware está em cada catraca.
    """
    from ponto.models import VersaoTerminal

    resposta = Tela(pagina_anonima).buscar(DUMP_PESSOAS_VERSIONADO.format(versao=VERSAO_COM_SENHA_DE_PONTO))

    linhas = _linhas_do_dump(resposta)
    assert linhas, 'o dump versionado do terminal saiu vazio'
    assert all(len(linha) == COLUNAS_COM_SENHA_DE_PONTO for linha in linhas), (
        f'o dump versionado mudou de largura: {sorted({len(linha) for linha in linhas})}'
    )

    assert VersaoTerminal.objects.filter(numero=VERSAO_COM_SENHA_DE_PONTO).exists(), 'a versão declarada pelo terminal não foi registrada'


def test_dump_de_uma_pessoa_traz_somente_ela(pagina_anonima, servidores_comum, terminal_sem_cache):
    """O terminal pede UMA pessoa quando alguém se cadastra na hora — e só ela pode vir.

    É a rota do cadastro de digital no terminal: a catraca busca o registro da pessoa que acabou
    de se apresentar em vez de rebaixar a tabela inteira. Se o filtro por ``matricula`` deixar de
    ser aplicado, a resposta continua 200 e o terminal continua funcionando — só fica lento e
    baixa a base inteira a cada cadastro. Por isso a asserção é a **contagem**, e não a presença.
    """
    esperado = servidores_comum['avaliador_sala']

    resposta = Tela(pagina_anonima).buscar(DUMP_PESSOA.format(username=esperado.matricula, versao=VERSAO_COM_SENHA_DE_PONTO))

    linhas = _linhas_do_dump(resposta)
    assert len(linhas) == 1, f'o dump de uma pessoa trouxe {len(linhas)} linhas: {[linha[1] for linha in linhas][:5]}'
    assert linhas[0][1] == esperado.matricula, f'o dump trouxe outra pessoa: {linhas[0][1]!r}'


@pytest.mark.parametrize(
    ('rota', 'operacao'),
    [(FOTOS_FUNCIONARIOS, 'comum_get_fotos_funcionarios'), (FOTOS_ALUNOS, 'comum_get_fotos_alunos')],
    ids=['funcionarios', 'alunos'],
)
def test_pacote_de_fotos_e_servido_ao_terminal(pagina_anonima, fotos_no_terminal, rota, operacao):
    """Os dois pacotes de fotos, servidos do storage temporário para a catraca e o refeitório.

    Parametrizado porque o que muda entre os dois é só o par (arquivo, condição da máquina): o das
    fotos de aluno exige ``Maquina.cliente_refeitorio`` e é particionado por campus
    (``fotos/fotos_alunos_{sigla}.zip``), o dos funcionários é único. As duas views são a mesma
    view escrita duas vezes.

    ``operacao`` é o ``MaquinaLog`` que cada pacote grava: o acesso do terminal às fotos é
    auditado nos dois casos (o das fotos de aluno não gravava até #17398).

    O ``Http404`` é o desfecho quando o pacote não foi gerado — e é o desfecho normal num ambiente
    novo, já que quem gera os arquivos é um comando fora do SUAP. Daí a fixture pôr os dois zips
    no storage: sem eles o teste afirmaria o 404.
    """
    from ponto.models import MaquinaLog

    resposta = Tela(pagina_anonima).buscar(rota)

    assert resposta.status == 200, f'o pacote de fotos respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'application/zip', f'o pacote veio como {resposta.headers["content-type"]!r}'
    assert 'fotos.zip' in resposta.headers['content-disposition'], 'o nome do arquivo do pacote de fotos mudou'
    assert zipfile.is_zipfile(io.BytesIO(resposta.body())), 'o pacote de fotos não chegou como zip íntegro'

    assert MaquinaLog.objects.filter(maquina=fotos_no_terminal, operacao=operacao).exists(), 'o pacote foi servido sem registrar o acesso da máquina'
