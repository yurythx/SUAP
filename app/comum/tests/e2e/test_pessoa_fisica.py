"""Fluxo: os dados da pessoa física — contatos de emergência, e-mail e nome sugerido.

``PessoaFisica`` é o registro que o SUAP inteiro referencia: servidor, aluno, prestador e
pensionista são papéis **sobre** a mesma pessoa. As quatro rotas deste arquivo são as que escrevem
nesse registro (ou no vínculo dele) fora do admin, e cada uma tem um motivo próprio de existir:

* **contatos de emergência** — o único dado do SUAP consultado em urgência médica, e o único que
  o próprio servidor mantém sem passar pela Gestão de Pessoas;
* **atualização de e-mail** — a porta pela qual a TI corrige o endereço de alguém que perdeu o
  acesso. Ela é protegida por **duplo fator** (``@rtr(two_factor_authentication=True)``), e o
  teste passa pelo duplo fator de verdade, porque é essa a tela;
* **nome sugerido** — o endpoint que alimenta as opções de nome do crachá.

A regressão que o arquivo pega é de **autorização e de efeito**: as quatro views decidem
quem pode o quê por uma conjunção escrita à mão no corpo (``verificacao_propria``,
``pode_gerenciar_contatos``, a lista de cinco ``has_perm`` de ``atualizar_email``), fora de
qualquer ``permission_required`` — é o tipo de condição que se inverte numa refatoração sem que
nenhuma tela mude de aparência.

Nenhum fluxo daqui grava num papel de ``PAPEIS`` a não ser o contato de emergência (que é aditivo
e a fixture zera no setup): o e-mail roda sobre pessoas descartáveis.
"""

from __future__ import annotations

import json

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
# As duas de contato NÃO têm barra final — é assim que `comum/urls.py:82-83` as declara.
LISTAR_CONTATOS = '/comum/pessoa_fisica/{pk}/listar_contatos_de_emergencia'
ADICIONAR_CONTATO = '/comum/pessoa_fisica/{pk}/adicionar_contato_de_emergencia'
ATUALIZAR_EMAIL = '/comum/atualizar_email_secundario/{pk}/'
POPULA_NOME_SUGERIDO = '/comum/popula_nome_sugerido/'
ADICIONAR_TELEFONE = '/comum/setor_adicionar_telefone/{setor}/'

# `TwoFactorAuthenticationCode.save` fixa o código sob teste (`djtools/models.py:152-153`), em vez
# de sorteá-lo e mandar por e-mail. É o que torna o duplo fator navegável.
CODIGO_DE_DUPLO_FATOR = '123456'


def test_ciclo_dos_contatos_de_emergencia(logado_comum, contatos_de_emergencia_limpos):
    """Listar vazio, adicionar e ver na lista — as duas rotas num teste, porque uma publica a outra.

    Encadeadas (regra 1 da receita): a listagem sem contato nenhum não afirma nada, e o endereço
    de adição não é montado pelo teste — é o ``href`` do botão da própria listagem. Afirmá-lo
    antes de clicar é o que liga a adição à pessoa certa; um botão achado só pelo rótulo provaria
    apenas que existe um botão com aquele texto.

    O papel é o **dono** dos contatos, e não um gestor: ``verificacao_propria`` abre as duas telas
    sem permissão nenhuma. O terceiro com permissão (``view`` lista, ``add`` adiciona — #17399)
    é coberto em ``comum/tests/views/test_contatos_de_emergencia.py``.
    """
    from comum.models import ContatoEmergencia

    dono = contatos_de_emergencia_limpos
    pessoa = dono.pessoa_fisica
    url_adicionar = ADICIONAR_CONTATO.format(pk=pessoa.pk)

    tela = Tela(logado_comum('solicitante')).ir(LISTAR_CONTATOS.format(pk=pessoa.pk))
    tela.ver_titulo(f'Contatos de Emergência de {pessoa.nome}')

    botao = tela.loc(f'//a[@href="{url_adicionar}"]').first
    assert botao.count(), f'a listagem não ofereceu a adição em {url_adicionar} para o próprio dono dos contatos'
    botao.click()

    tela.ver_titulo(f'Novo Contato de Emergência de {pessoa.nome}')
    tela.preencher_formulario([('Nome do Contato', 'texto', 'Maria da Silva (mãe)'), ('Telefone', 'texto', '(84) 3215-1234')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Contato adicionado com sucesso.')

    contato = ContatoEmergencia.objects.filter(pessoa_fisica=pessoa).first()
    assert contato, 'a UI disse que adicionou, mas o contato de emergência não persistiu'
    assert contato.nome_contato == 'Maria da Silva (mãe)', f'o contato foi gravado como {contato.nome_contato!r}'

    tela.ir(LISTAR_CONTATOS.format(pk=pessoa.pk))
    tela.ver_texto('Maria da Silva (mãe)')


def test_atualizar_email_do_prestador_passa_pelo_duplo_fator(logado_comum, prestador_e2e):
    """A tela de e-mail exige duplo fator antes de aparecer — e o teste passa por ele.

    ``@rtr(two_factor_authentication=True)`` intercepta **antes** da view: sem ``session['2fa']``
    o SUAP gera um ``TwoFactorAuthenticationCode`` e redireciona para
    ``/djtools/two_factor_authentication/`` (``djtools/utils/response.py:217-222``). Pular essa
    etapa — testando a view direto — deixaria de proteger justamente o que faz esta rota ser
    perigosa: quem troca o e-mail de recuperação de alguém assume a conta dessa pessoa.

    O alvo é o **prestador**, e o papel é a TI: ``gestor_ti`` tem
    ``rh.pode_editar_email_secundario_prestador`` (``rh/permissions.yaml:477``) e o prestador é
    descartável. Trocar o e-mail de um papel de ``PAPEIS`` mudaria o ``email_notificacao`` que as
    outras fatias leem.
    """
    from comum.models import Vinculo

    vinculo = prestador_e2e.get_vinculo()
    novo_email = f'{prestador_e2e.matricula}@gmail.com'

    tela = Tela(logado_comum('gestor_ti')).ir(ATUALIZAR_EMAIL.format(pk=vinculo.pk))

    # O duplo fator: a tela de e-mail só aparece depois daqui.
    tela.ver_titulo('Autenticação via E-mail')
    tela.preencher('Código', 'número', CODIGO_DE_DUPLO_FATOR)
    tela.clicar_botao('Autenticar')
    tela.sucesso('Código de autenticação validado com sucesso.')

    tela.ver_titulo('Atualização do E-mail')
    tela.preencher('E-mail Pessoal', 'texto', novo_email)
    tela.clicar_botao('Enviar')
    tela.sucesso('E-mail atualizado com sucesso.')

    assert Vinculo.objects.get(pk=vinculo.pk).email_pessoal == novo_email, 'a UI disse que atualizou, mas o e-mail do vínculo não mudou'


def test_nome_sugerido_para_o_cracha(logado_comum, servidores_comum):
    """As opções de nome do crachá, geradas a partir do nome da pessoa escolhida.

    **Não é tela.** É o endpoint que ``comum/static/comum/js/solicitacao_documento.js`` chama por
    ``POST`` quando o operador troca o solicitante no formulário de solicitação de documento do
    admin, para repopular o ``select`` de nome sugerido. O gesto que o dispara não é alcançável no
    banco de e2e: o formulário do admin exige um ``DocumentoControleTipo`` com identificador
    ``cracha`` **e** uma ``ConfiguracaoImpressaoDocumento`` que inclua o campus do operador
    (``comum/forms.py:1000-1010``), e o seed não traz nenhum dos dois — medido: a tela de
    adição responde 403. Fabricar os dois cadastros faria o teste afirmar uma configuração
    inventada; o que o endpoint é, e o que o JS consome, é o **contrato** do JSON.

    Por que o token de CSRF vai na mão: a view é ``@login_required`` e **não** ``@csrf_exempt``,
    e o ``APIRequestContext`` de ``Tela.postar`` compartilha os cookies da sessão mas não monta o
    ``csrfmiddlewaretoken`` que um formulário de verdade envia. Sem ele a resposta volta 403 e o
    diagnóstico apontaria para a permissão em vez do token.

    A asserção é o conteúdo: ``gera_nomes`` (``djtools/utils/strings.py:373-381``) combina os
    tokens do nome dois a dois, em maiúsculas e sem acento — é exatamente o que o crachá imprime.
    """
    solicitante = servidores_comum['solicitante']
    vinculo = solicitante.get_vinculo()

    # O token sai da tela de telefones do próprio setor do operador (só GET, nada é gravado). Até
    # a #17399 vinha da adição de contato de emergência, que o operador só abria porque as
    # permissões de listar e adicionar estavam trocadas.
    setor = servidores_comum['gestor_pessoal'].setor
    tela = Tela(logado_comum('gestor_pessoal')).ir(ADICIONAR_TELEFONE.format(setor=setor.pk))
    token = tela.loc('//input[@name="csrfmiddlewaretoken"]').first.get_attribute('value')
    assert token, 'não foi possível colher o token de CSRF de uma tela com formulário'

    resposta = tela.postar(POPULA_NOME_SUGERIDO, {'csrfmiddlewaretoken': token, 'solicitante_vinculo': str(vinculo.pk)})

    assert resposta.status == 200, f'o endpoint de nome sugerido respondeu HTTP {resposta.status}'
    corpo = json.loads(resposta.text())
    assert list(corpo) == ['nomes'], f'o endpoint mudou de forma: {sorted(corpo)}'

    opcoes = corpo['nomes']
    assert opcoes[0] == ['', 'Selecione umas das opções'], f'a opção vazia inicial sumiu: {opcoes[:1]}'
    sugeridos = [opcao[0] for opcao in opcoes[1:]]
    assert sugeridos, f'nenhum nome foi sugerido para {solicitante.pessoa_fisica.nome!r}'
    assert all(nome == nome.upper() for nome in sugeridos), f'o crachá recebeu nome fora de caixa alta: {sugeridos}'
    assert 'E2E SOLICITANTE' in sugeridos, f'o nome da pessoa não entrou nas combinações sugeridas: {sugeridos}'
