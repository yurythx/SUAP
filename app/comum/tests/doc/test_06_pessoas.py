"""Fatia 6 da doc de usuário do ``comum`` — pessoas, prestadores e usuários externos.

É a última fatia, e a que mexe no substrato: ``PessoaFisica`` e ``Vinculo`` são o registro que
o SUAP inteiro referencia — servidor, aluno, prestador e pensionista são papéis **sobre** a
mesma pessoa. Daí a regra que governa o arquivo, herdada do conftest do e2e: nenhum fluxo que
mute pessoa toca um papel de ``PAPEIS``. A pessoa que aparece em sete capturas
(``prestador_e2e``, sobrescrita no conftest da doc com nome de gente) nasce e morre no teste, e
as duas telas que gravam num papel compartilhado — contatos de emergência e biometria do
``solicitante`` — são aditivas e zeradas no SETUP.

Cada teste é o roteiro de UMA tarefa da doc, na ordem em que ela as apresenta; as asserções
existem para a rodada falhar alto quando a tela muda de forma, e as ``anotar`` despejam
rótulos/opções que a redação copia em vez de deduzir de ``views.py``.

Três telas do escopo desta fatia **não** viraram tarefa, e o motivo é medido, não de gosto:

* *Inscrição para fiscal do Concurso Público* — quando esta fatia foi escrita, o envio era
  inalcançável (``TypeError`` no ``POST``; corrigido em #17396 e exercitado pelo e2e do módulo).
  A tarefa ainda não foi redigida;
* os **webservices do terminal de ponto** (``get_pessoas``, ``get_fotos_*``) — não são telas:
  são endereços que a catraca busca sozinha, autorizados por IP e sem login. Não há gesto de
  usuário para documentar;
* o endpoint de **subobjetivos do desenvolvimento sustentável** — é o JSON que alimenta o
  ``select`` de outro módulo, não tela.

Nenhuma tarefa desta fatia veio de ``.feature``: as cinco do ``comum`` são de cadastro e de
senha. As tarefas 28 a 36 foram **propostas** a partir do ``menu.yaml``, dos endereços de
``comum/urls.py``, do ``comum/admin.py`` e do encadeamento das telas.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from playwright.sync_api import expect

from comum.tests.doc.conftest import (
    CONTATO_EMERGENCIA_DOC,
    EMAIL_CORRIGIDO_DOC,
    LOCAL_REUNIAO_DOC,
    NOME_PRESTADOR_DOC,
    PAUTA_REUNIAO_DOC,
    PERFIL_EXTERNO_DOC,
    TELEFONE_EMERGENCIA_DOC,
    TITULO_REUNIAO_DOC,
    TITULO_REUNIAO_NOVA_DOC,
    anotar,
)
from comum.tests.e2e.conftest import EMPRESA_DO_SEED, OCUPACAO_DO_SEED
from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM_EXTERNOS = '/admin/comum/prestadorservico/'
FICHA_DO_EXTERNO = '/comum/prestador_servico/{pk}/'
PAGINA_DO_SERVIDOR = '/rh/servidor/{matricula}/'
LISTAR_CONTATOS = '/comum/pessoa_fisica/{pk}/listar_contatos_de_emergencia'
ADICIONAR_CONTATO = '/comum/pessoa_fisica/{pk}/adicionar_contato_de_emergencia'
MINHA_CONTA = '/comum/minha_conta/'
PAINEL_ADMINISTRACAO = '/comum/admin/'
MACRO_PERSONALIZAVEL = '/comum/baixar_macro_siape_personalizavel/'
CADASTRO_DE_REUNIOES = '/admin/comum/reuniaoorgaocolegiado/'
CALENDARIO_DE_REUNIOES = '/comum/orgaos_colegiados_reunioes_consultar_calendario/'
DETALHAR_REUNIAO = '/comum/orgaos_colegiados_detalhar_reuniao/{pk}/'
CALENDARIO_ADMINISTRATIVO = '/comum/calendario_administrativo/'
DOCUMENTACAO = '/comum/documentacao/'

# `TwoFactorAuthenticationCode.save` fixa o código sob teste (`djtools/models.py:152-153`) em vez
# de sorteá-lo: é o que torna o duplo fator navegável.
CODIGO_DE_DUPLO_FATOR = '123456'


def _abrir_menu_editar(tela: Tela) -> Tela:
    """Abre o menu suspenso *Editar* da barra de ações e devolve a ``Tela``.

    O submenu está no DOM desde o início, mas escondido por CSS até o clique no pai
    (``comum/static/comum/js/main.js:373`` liga o ``.action-bar .has-child > a``), e
    ``clicar_botao`` exige elemento visível. É por este menu que passam três dos quatro
    caminhos de manutenção do cadastro (Dados, Foto e E-mail), então o gesto é o do usuário —
    não um ``goto`` na URL de dentro.
    """
    tela.loc('//ul[@class="action-bar"]//li[contains(@class, "has-child")]/a').first.click()
    return tela


def test_cadastrar_um_usuario_externo(logado_comum, perfil_de_usuario_externo, cadastro_de_externo_limpo, capturar):
    """Tarefa 28 — dar cadastro no SUAP a quem não é servidor nem aluno.

    É a única tela desta fatia sem precedente no e2e do módulo (lá o prestador nasce de
    ``factory``), e é a porta de entrada de todo o resto: sem este cadastro não há vínculo,
    ocupação, papel nem login.

    O que a fixture acrescenta ao seed — e sem o que a tarefa não existe — é o **Perfil**
    (``JustificativaUsuarioExterno``): o campo é obrigatório e sua lista sai de
    ``objects.filter(ativo=True)``, que no seed é vazia. Com a lista vazia o formulário
    abre e nunca envia.

    A asserção é o ``PrestadorServico`` no banco, e não a mensagem: ``response_add`` responde
    *"Usuário Externo cadastrado com sucesso…"* a partir do ``obj`` que o admin já tem em mãos,
    de modo que ela sairia igual se ``save_model`` tivesse gravado outra coisa.
    """
    from comum.models import PrestadorServico

    nome, cpf, email = cadastro_de_externo_limpo
    pagina = logado_comum('gestor_pessoal_sistemico')

    tela = Tela(pagina).ir(LISTAGEM_EXTERNOS)
    tela.ver_titulo('Usuários Externos')
    anotar('externos-listagem', tela)
    capturar(pagina, 'externos-listagem')

    tela.clicar_botao('Adicionar Usuário Externo')
    anotar('externo-cadastro', tela)
    tela.preencher_formulario(
        [
            ('Nome de Registro', 'texto', nome),
            ('Sexo', 'lista', 'Masculino'),
            ('Nacionalidade', 'lista', 'Brasileiro Nato'),
            ('CPF', 'texto', cpf),
            ('Perfil', 'lista', PERFIL_EXTERNO_DOC),
            ('Email Pessoal', 'texto', email),
            ('Confirmação de E-mail', 'texto', email),
        ]
    )
    capturar(pagina, 'externo-cadastro')
    tela.clicar_botao('Salvar')

    tela.sucesso('Usuário Externo cadastrado com sucesso.')
    cadastrado = PrestadorServico.objects.filter(pessoa_fisica__cpf=cpf).first()
    assert cadastrado, 'a UI disse que cadastrou, mas o usuário externo não persistiu'
    assert cadastrado.pessoa_fisica.nome == nome, f'o cadastro gravou o nome {cadastrado.pessoa_fisica.nome!r}'
    assert cadastrado.get_vinculo(), 'o usuário externo foi cadastrado sem vínculo — sem ele não há login nem papel'


def test_vincular_a_ocupacao_do_usuario_externo(logado_comum, prestador_e2e, capturar):
    """Tarefa 29 — o ato que faz o usuário externo existir para o resto do SUAP.

    Três capturas, três estados da mesma ficha: sem ocupação (com o aviso que a própria tela
    dá), o formulário do vínculo e a ficha já com a ocupação publicada.

    A asserção mais importante não está na tela: ``OcupacaoPrestador.save`` cria um ``rh.Papel``
    do tipo ocupação, e é esse papel — não a linha da ocupação — que o processo eletrônico e a
    assinatura digital consultam. Uma regressão que gravasse a ocupação sem o papel deixaria a
    tela perfeita e a pessoa incapaz de assinar qualquer coisa.

    O botão *Vincular ocupação* da ficha é ``class="btn success popup"``: fancybox em iframe, com
    o ``httprr`` caindo na página de trás, que recarrega (armadilha 1 da fatia 1).

    A ficha é alcançada pelo **ícone de exibição da listagem**, e não por ``goto``, porque é esse
    o passo que a doc escreve — e a asserção na URL é o que prova que o ícone leva à ficha do
    ``comum``, e não à tela de edição do admin.
    """
    from rh.models import Papel

    from comum.models import OcupacaoPrestador

    inicio = date.today() - timedelta(days=7)
    fim = date.today() + timedelta(days=365)
    pagina = logado_comum('gestor_pessoal_sistemico')

    # A porta é o ícone de exibição da linha, e não o endereço da ficha: é o gesto que o passo 1
    # da doc manda fazer. `list_display_icons = True` no `PrestadorServicoAdmin` é o que o põe lá.
    tela = Tela(pagina).ir(LISTAGEM_EXTERNOS)
    tela.linha(NOME_PRESTADOR_DOC).clicar_icone('exibição')
    tela.esperar()
    assert tela.pagina.url.endswith(FICHA_DO_EXTERNO.format(pk=prestador_e2e.pk)), f'o ícone de exibição da listagem levou a {tela.pagina.url}'

    tela.ver_titulo(str(prestador_e2e))
    tela.ver_texto('Este usuário não tem nenhuma ocupação associada')
    anotar('externo-ficha-sem-ocupacao', tela)
    capturar(pagina, 'externo-ficha-sem-ocupacao')

    tela.clicar_botao('Vincular ocupação')
    popup = tela.popup()
    anotar('externo-ocupacao', popup)
    popup.preencher_formulario(
        [
            ('Ocupação', 'autocomplete', OCUPACAO_DO_SEED),
            ('Pessoa Jurídica', 'autocomplete', EMPRESA_DO_SEED),
            ('Data de início', 'data', inicio.strftime('%d/%m/%Y')),
            ('Data fim', 'data', fim.strftime('%d/%m/%Y')),
            ('Setor suap', 'autocomplete', prestador_e2e.setor.sigla),
        ]
    )
    capturar(pagina, 'externo-ocupacao')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Ocupação vinculada com sucesso.')
    ocupacao = OcupacaoPrestador.objects.filter(prestador=prestador_e2e).first()
    assert ocupacao, 'a UI disse que vinculou, mas não gravou a ocupação'
    assert ocupacao.data_fim == fim, f'a ocupação foi gravada com data fim {ocupacao.data_fim}, e não a informada'
    assert Papel.objects.filter(vinculo=prestador_e2e.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_OCUPACAO).exists(), (
        'a ocupação foi gravada sem criar o papel — a pessoa existe na tela e não existe para o processo eletrônico'
    )

    tela.ir(FICHA_DO_EXTERNO.format(pk=prestador_e2e.pk))
    tela.ver_texto(str(ocupacao.ocupacao))
    tela.ver_texto('É prestador de serviço')
    capturar(pagina, 'externo-ficha')


def test_encerrar_a_ocupacao(logado_comum, ocupacao_ativa, prestador_e2e, capturar):
    """Tarefa 29, etapa final — encerrar o contrato, com confirmação por senha.

    A regra que só o ORM revela, e que a doc precisa dizer: encerrar **não** apaga a ocupação
    nem grava "encerrada" — recua a data fim para **ontem**, porque o histórico do vínculo
    precisa continuar existindo para os documentos já assinados sob ele.

    A senha é a de quem está logado de verdade (``PasswordField.clean`` autentica contra o
    request do threadlocal): é a confirmação que separa encerrar por engano de encerrar de
    propósito, e é por isso que ela entra no passo da doc.
    """
    from comum.models import OcupacaoPrestador

    pagina = logado_comum('gestor_pessoal_sistemico')

    tela = Tela(pagina).ir(FICHA_DO_EXTERNO.format(pk=prestador_e2e.pk))
    tela.clicar_botao('Encerrar ocupação')
    popup = tela.popup()
    popup.ver_texto('a data fim da ocupação será alterada para a data de ontem')
    anotar('externo-encerrar-ocupacao', popup)
    popup.preencher('Senha para confirmação', 'senha', SENHA_E2E)
    capturar(pagina, 'externo-encerrar-ocupacao')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Ocupação encerrada com sucesso.')
    encerrada = OcupacaoPrestador.objects.get(pk=ocupacao_ativa.pk)
    assert encerrada.data_fim == date.today() - timedelta(days=1), f'a UI disse que encerrou, mas a data fim ficou em {encerrada.data_fim}'
    assert not encerrada.eh_ativa(), 'a ocupação continuou ativa depois de encerrada'


def test_ligar_e_desligar_a_conta_do_usuario_externo(logado_comum, prestador_e2e, capturar):
    """Tarefa 30 — criar o papel de acesso, desligar a conta e religá-la.

    Os três atos num teste porque eles são a **mesma coluna** da listagem (*Opções*) e se
    desfazem em cadeia: criar o papel some com o próprio botão (``get_opcoes`` só o publica
    quando ``not tem_papel_ativo_usuario_externo()``), e ativar só prova alguma coisa depois de
    inativar.

    O papel é o ``gestor_ti``, e não a Gestão de Pessoas: ``ativar/inativar_usuario_externo``
    são guardadas por ``@group_required('Coordenador de TI sistêmico')``, que checa o **nome do
    grupo** e não a permissão — nenhum perfil de pessoal as alcança, por mais permissões de
    prestador que tenha. É o que a doc precisa dizer, e a captura mostra: os botões só existem
    para quem está nesse grupo.

    As três ações respondem a mesma mensagem de sucesso independentemente do que aconteceu no
    banco, então quem decide o teste é sempre a asserção no ORM. ``User.is_active`` vai junto
    com ``PrestadorServico.ativo`` porque é o segundo que decide se a pessoa consegue entrar.
    """
    from rh.models import Papel

    from comum.models import PrestadorServico

    pagina = logado_comum('gestor_ti')

    tela = Tela(pagina).ir(LISTAGEM_EXTERNOS)
    linha = tela.linha(NOME_PRESTADOR_DOC)
    anotar('externo-opcoes', tela)
    capturar(pagina, 'externo-opcoes')

    linha.clicar_botao('Criar papel de Usuário Externo')
    tela.sucesso('Papel de Usuário Externo Criado com Sucesso.')
    assert Papel.objects.filter(vinculo=prestador_e2e.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO, data_fim__isnull=True).exists(), (
        'a UI disse que criou o papel de usuário externo, mas ele não existe'
    )

    tela.linha(NOME_PRESTADOR_DOC).clicar_botao('Inativar usuário')
    tela.sucesso('Usuário Externo Desativado com Sucesso.')
    inativo = PrestadorServico.objects.get(pk=prestador_e2e.pk)
    assert not inativo.ativo, 'a UI disse que desativou, mas o usuário externo continuou ativo'
    assert not inativo.get_vinculo().user.is_active, 'o cadastro foi desativado mas a pessoa continuou podendo entrar no SUAP'

    tela.linha(NOME_PRESTADOR_DOC).clicar_botao('Ativar usuário')
    tela.sucesso('Usuário Externo Ativado com Sucesso.')
    ativo = PrestadorServico.objects.get(pk=prestador_e2e.pk)
    assert ativo.ativo, 'a UI disse que ativou, mas o usuário externo continuou inativo'
    assert ativo.get_vinculo().user.is_active, 'o cadastro foi ativado mas a pessoa continuou sem poder entrar'


def test_corrigir_o_email_do_usuario_externo(logado_comum, prestador_e2e, capturar):
    """Tarefa 31, etapa 1 — trocar o e-mail pessoal, atrás do duplo fator.

    A tela exige duplo fator **antes** de aparecer (``@rtr(two_factor_authentication=True)``):
    sem ``session['2fa']`` o SUAP gera um código, manda para o e-mail pessoal de **quem está
    logado** e intercepta com a tela de autenticação. O roteiro passa por ela de verdade, porque
    é essa etapa que faz a tarefa ser o que é — quem troca o e-mail de recuperação de alguém
    assume a conta dessa pessoa.

    Tudo acontece dentro do fancybox: o item *E-mail* do menu *Editar* é ``class="popup"``, e o
    ``custom.js`` acrescenta ``_popup=1`` ao endereço — que o redirecionamento do duplo fator
    preserva (``next_url`` carrega a query string), de modo que o ``httprr`` final fecha o
    diálogo e recarrega a ficha atrás.
    """
    from comum.models import Vinculo

    vinculo = prestador_e2e.get_vinculo()
    pagina = logado_comum('gestor_ti')

    tela = Tela(pagina).ir(FICHA_DO_EXTERNO.format(pk=prestador_e2e.pk))
    _abrir_menu_editar(tela)
    capturar(pagina, 'externo-menu-editar')
    tela.clicar_botao('E-mail')

    popup = tela.popup()
    popup.ver_titulo('Autenticação via E-mail')
    anotar('externo-duplo-fator', popup)
    popup.preencher('Código', 'número', CODIGO_DE_DUPLO_FATOR)
    capturar(pagina, 'externo-duplo-fator')
    popup.clicar_botao('Autenticar')

    popup = tela.popup()
    popup.ver_titulo('Atualização do E-mail')
    anotar('externo-email', popup)
    popup.preencher('E-mail Pessoal', 'texto', EMAIL_CORRIGIDO_DOC)
    capturar(pagina, 'externo-email')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('E-mail atualizado com sucesso.')
    assert Vinculo.objects.get(pk=vinculo.pk).email_pessoal == EMAIL_CORRIGIDO_DOC, 'a UI disse que atualizou, mas o e-mail do vínculo não mudou'


def test_trocar_a_foto(logado_comum, prestador_e2e, capturar):
    """Tarefa 31 — a foto do crachá.

    Detalhe não óbvio, e que a doc precisa acertar: a foto é gravada no **vínculo**, e não na
    pessoa física — ``AtualizarFotoPessoaFisicaForm`` tem "PessoaFisica" no nome e salva em
    ``self.vinculo.foto``. Quem exibe a foto no crachá e na barra do SUAP lê do vínculo.
    """
    pagina = logado_comum('gestor_pessoal_sistemico')

    tela = Tela(pagina).ir(FICHA_DO_EXTERNO.format(pk=prestador_e2e.pk))
    _abrir_menu_editar(tela)
    tela.clicar_botao('Foto')

    tela.ver_titulo(f'Alterar Foto do Usuário Externo {prestador_e2e}')
    anotar('externo-foto', tela)
    tela.preencher('Arquivo', 'arquivo', 'foto.jpg')
    capturar(pagina, 'externo-foto')
    tela.clicar_botao('Enviar')
    tela.sucesso('Foto atualizada com sucesso.')

    vinculo = prestador_e2e.get_vinculo()
    vinculo.refresh_from_db()
    assert vinculo.foto, 'a UI disse que atualizou a foto, mas o vínculo continuou sem nenhuma'


def test_cadastrar_um_contato_de_emergencia(logado_comum, contatos_de_emergencia_limpos, capturar):
    """Tarefa 32 — o único dado do SUAP consultado em urgência médica.

    O roteiro é o do **dono** dos contatos, e não o de um gestor: é o caminho de uso real, e
    a própria pessoa abre as duas telas sem permissão nenhuma. Para terceiros, a listagem pede
    ``view_contatoemergencia`` e a adição pede ``add_contatoemergencia`` (#17399).

    A porta é *Minha conta -> Meus dados* (``comum/templates/minha_conta.html:108``), e o teste
    passa por ela: o endereço da página de servidor não é digitado.

    O endereço de adição não é montado pelo teste: é o ``href`` do botão da própria listagem.
    Afirmá-lo antes de clicar é o que liga a adição à pessoa certa — um botão achado só pelo
    rótulo provaria apenas que existe um botão com aquele texto.
    """
    from comum.models import ContatoEmergencia

    dono = contatos_de_emergencia_limpos
    pessoa = dono.pessoa_fisica
    pagina = logado_comum('solicitante')

    tela = Tela(pagina).ir(MINHA_CONTA)
    tela.loc('//a[contains(@class, "box-item")][.//h4[normalize-space(text())="Meus dados"]]').first.click()
    tela.esperar()
    assert tela.pagina.url.endswith(PAGINA_DO_SERVIDOR.format(matricula=dono.matricula)), (
        f'o atalho *Meus dados* da Minha conta levou a {tela.pagina.url}'
    )
    _abrir_menu_editar(tela)
    tela.clicar_botao('Contatos de Emergência')

    tela.ver_titulo(f'Contatos de Emergência de {pessoa.nome}')
    anotar('contatos-listagem', tela)
    capturar(pagina, 'contatos-listagem')

    botao = tela.loc(f'//a[@href="{ADICIONAR_CONTATO.format(pk=pessoa.pk)}"]').first
    assert botao.count(), 'a listagem não ofereceu a adição para o próprio dono dos contatos'
    botao.click()

    tela.ver_titulo(f'Novo Contato de Emergência de {pessoa.nome}')
    anotar('contato-formulario', tela)
    tela.preencher_formulario([('Nome do Contato', 'texto', CONTATO_EMERGENCIA_DOC), ('Telefone', 'texto', TELEFONE_EMERGENCIA_DOC)])
    capturar(pagina, 'contato-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Contato adicionado com sucesso.')

    contato = ContatoEmergencia.objects.filter(pessoa_fisica=pessoa).first()
    assert contato, 'a UI disse que adicionou, mas o contato de emergência não persistiu'
    assert contato.nome_contato == CONTATO_EMERGENCIA_DOC, f'o contato foi gravado como {contato.nome_contato!r}'

    tela.ir(LISTAR_CONTATOS.format(pk=pessoa.pk))
    tela.ver_texto(CONTATO_EMERGENCIA_DOC)
    capturar(pagina, 'contatos-cadastrado')


def test_solicitar_o_autocadastro_da_biometria(logado_comum, biometria_do_zero, capturar):
    """Tarefa 33 — pedir o código que libera o cadastro da digital no terminal de ponto.

    Encadeado até o reenvio porque a segunda tela vive da primeira: não há o que refazer antes
    de solicitar, e o botão *Refazer autocadastro* só aparece na linha de uma solicitação ativa.

    A confirmação é por senha real porque o código gerado aqui vale como credencial no terminal:
    quem o obtém cadastra o próprio dedo no lugar do servidor.

    A expiração do código depende da ``Configuracao`` ``comum/biometria_expiracao``, que a fixture
    herdada do e2e grava — sem ela a tela do reenvio é um 500.
    """
    from django.core import mail

    from rh.models import BiometriaSolicitacao

    dono = biometria_do_zero
    pagina = logado_comum('solicitante')

    tela = Tela(pagina).ir(MINHA_CONTA)
    tela.ver_texto('Biometria')
    tela.clicar_botao('Solicitar autocadastro')

    popup = tela.popup()
    popup.ver_titulo('Solicitação de autocadastro de biometria')
    anotar('biometria-solicitar', popup)
    popup.preencher_formulario([('Senha para confirmação', 'senha', SENHA_E2E), ('Confirma a solicitação', 'checkbox', 'marcar')])
    capturar(pagina, 'biometria-solicitar')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Solicitação realizada, verifique seu e-mail.')
    solicitacao = BiometriaSolicitacao.objects.filter(pessoa_fisica=dono.pessoa_fisica).order_by('-id').first()
    assert solicitacao, 'a UI disse que solicitou, mas a solicitação de biometria não persistiu'
    assert len(solicitacao.codigo_verificacao) == 6, f'a solicitação nasceu com um código de {len(solicitacao.codigo_verificacao)} dígitos'
    assert solicitacao.ativo, 'a solicitação nasceu já expirada ou já utilizada'

    tela.ir(MINHA_CONTA)
    tela.ver_texto('Refazer autocadastro')
    anotar('biometria-minha-conta', tela)
    capturar(pagina, 'biometria-minha-conta')

    enviados_antes = len(mail.outbox)
    tela.clicar_botao('Refazer autocadastro')
    tela.sucesso('O código de autorização foi reenviado.')
    assert len(mail.outbox) == enviados_antes + 1, 'a UI disse que reenviou o código, mas nenhum e-mail saiu'
    assert solicitacao.codigo_verificacao in mail.outbox[-1].body, 'o e-mail de reenvio saiu sem o código de verificação'


def test_baixar_a_macro_do_siape(logado_comum, instituicao_configurada, capturar):
    """Tarefa 34 — o arquivo que automatiza a extração de dados no terminal do SIAPE.

    O SUAP não fala com o SIAPE por API: ele gera uma **macro** (um XML de automação de terminal
    3270) que o operador roda no emulador. Por isso não há tela de resultado para capturar — o
    desfecho é um arquivo baixado —, e o que a doc mostra é a tela de personalização.

    Dois gestos, dois contratos: o link direto do painel (que é a porta que a tarefa 19 já
    descreve) e a macro personalizável, em que desmarcar um arquivo do extrator obriga a view a
    reescrever a árvore do XML — é o único lugar do SUAP que faz isso, e um erro ali produz um
    arquivo válido que trava o terminal no meio da extração.

    ``instituicao_configurada`` não é conforto: sem a UF e o código da instituição na
    ``Configuracao``, ``baixar_macro_siape`` devolve um pedido de configuração em texto, não a macro.
    """
    from xml.etree import ElementTree

    pagina = logado_comum('gestor_pessoal_sistemico')

    tela = Tela(pagina).ir(PAINEL_ADMINISTRACAO)
    tela.ver_texto('SIAPE Completa')
    with pagina.expect_download() as baixado:
        tela.clicar_link('SIAPE Completa')
    assert baixado.value.suggested_filename == 'macro_siape.mac', f'o nome do arquivo baixado mudou: {baixado.value.suggested_filename!r}'

    tela.ir(MACRO_PERSONALIZAVEL)
    tela.ver_titulo('Baixar macro SIAPE')
    anotar('macro-siape', tela)
    capturar(pagina, 'macro-siape')

    # Todos os arquivos vêm marcados; o gesto real é o operador desmarcar o que não quer.
    tela.campo('Arquivos do Extrator', 'checkbox multiplo', 'Unidades Organizacionais').first.uncheck()
    with pagina.expect_download() as baixado:
        tela.clicar_botao('Enviar')
    with open(baixado.value.path(), 'rb') as arquivo:
        corpo = arquivo.read()

    raiz = ElementTree.fromstring(corpo)
    telas_de_entrada = [tela_xml.attrib['name'] for tela_xml in raiz.iter('screen') if tela_xml.attrib.get('entryscreen') == 'true']
    assert 'unidadeorganizacional1' not in telas_de_entrada, 'o arquivo desmarcado continuou sendo a tela de entrada da macro'
    assert telas_de_entrada, 'a macro saiu sem nenhuma tela de entrada'
    assert instituicao_configurada['instituicao_identificador'].encode() in corpo, 'a macro não compilou o código da instituição'


def test_cadastrar_uma_reuniao_de_orgao_colegiado(logado_comum, reuniao_cadastrada_pela_tela, capturar):
    """Tarefa 35, etapa 1 — publicar a reunião do conselho no calendário.

    O papel navegado é o **superusuário** do seed, e a razão é estrutural: nenhum papel de
    ``PAPEIS`` tem ``comum.add_reuniaoorgaocolegiado``, e acrescentar um exigiria editar
    ``servidores_comum``, a fixture de sessão de que as outras cinco fatias dependem (o SUAP
    resolve permissão com cache por processo, então grupo novo tem de nascer no seed). A linha
    *Quem pode* da doc nomeia o perfil que a permissão de fato concede — *Administrador de
    Reuniões de Órgãos Colegiados Superiores* —, obtido por ``bin/scripts/papeis.py``.

    A asserção é o registro no banco: o *Salvar* do admin do SUAP não volta para a listagem
    (armadilha 2 da fatia 1), de modo que "voltei para algum lugar" não distingue gravou de
    não gravou.
    """
    from comum.models import ReuniaoOrgaoColegiado

    hoje = date.today()
    pagina = logado_comum('admin')

    tela = Tela(pagina).ir(CADASTRO_DE_REUNIOES)
    tela.ver_titulo('Reuniões de Órgãos Colegiados Superiores')
    tela.clicar_botao('Adicionar Reunião de Órgão Colegiado Superior')
    anotar('colegiado-cadastro', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', TITULO_REUNIAO_NOVA_DOC),
            ('Órgão Colegiado', 'lista', 'CONSUP'),
            ('Descrição', 'textarea', PAUTA_REUNIAO_DOC),
            ('Local', 'textarea', LOCAL_REUNIAO_DOC),
            ('Data Início', 'data', hoje.strftime('%d/%m/%Y')),
            ('Data Fim', 'data', hoje.strftime('%d/%m/%Y')),
            ('Hora Início', 'hora', '14:00'),
            ('Hora Fim', 'hora', '17:00'),
        ]
    )
    capturar(pagina, 'colegiado-cadastro')
    tela.clicar_botao('Salvar')

    cadastrada = ReuniaoOrgaoColegiado.objects.filter(titulo=TITULO_REUNIAO_NOVA_DOC).first()
    assert cadastrada, 'a tela de cadastro foi enviada, mas a reunião não persistiu'
    assert cadastrada.local == LOCAL_REUNIAO_DOC, f'a reunião foi gravada com o local {cadastrada.local!r}'


def test_consultar_o_calendario_de_reunioes(logado_comum, reuniao_colegiado, capturar):
    """Tarefa 35, etapa 2 — o calendário que qualquer servidor consulta, e a ficha da reunião.

    O papel é um servidor **sem** grupo de gestão, de propósito: ``pode_consultar_calendarios``
    está no grupo ``Servidor``, e é para esse público que a tela existe. Abrir com um
    administrador esconderia uma regressão que passasse a exigir ``change`` para ler.

    O teste confere primeiro que a tela **sem filtro** não mostra a reunião. Não é redundância:
    é o que distingue "o filtro funcionou" de "o calendário mostra tudo sempre" — e é a
    diferença que o passo da doc descreve, já que a consulta é por ``GET`` e o calendário nasce
    vazio.

    O evento no calendário é um link para a ficha (``comum/html.py:541``), e é por ele que o
    teste chega ao detalhamento — o gesto do usuário, e não um endereço montado à mão. Ele é
    ``class="popup"``: a ficha abre **dentro** do calendário, em fancybox, e não numa tela
    nova; a doc descreve o que o usuário vê, e a captura sai do viewport com o diálogo aberto.
    """
    from djtools.choices import Meses

    hoje = date.today()
    pagina = logado_comum('solicitante')

    tela = Tela(pagina).ir(CALENDARIO_DE_REUNIOES)
    tela.ver_titulo('Calendário de Reuniões de Órgãos Colegiados Superiores')
    assert TITULO_REUNIAO_DOC not in pagina.content(), 'o calendário sem filtro já mostrava a reunião: o filtro por período deixou de restringir'
    anotar('colegiado-calendario', tela)

    tela.preencher_formulario(
        [
            ('Formato', 'lista', 'Mensal'),
            ('Filtrar por Mês:', 'lista', Meses.get_mes(hoje.month)),
            ('Filtrar por Ano:', 'lista', str(hoje.year)),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.ver_texto(TITULO_REUNIAO_DOC)
    capturar(pagina, 'colegiado-calendario')

    tela.loc(f'//a[contains(@href, "{DETALHAR_REUNIAO.format(pk=reuniao_colegiado.pk)}")]').first.click()
    ficha = tela.popup()
    ficha.ver_texto(TITULO_REUNIAO_DOC)
    ficha.ver_texto(LOCAL_REUNIAO_DOC)
    ficha.ver_texto(PAUTA_REUNIAO_DOC)
    anotar('colegiado-reuniao', ficha)
    capturar(pagina, 'colegiado-reuniao')


def test_consultar_o_calendario_administrativo(logado_comum, cronograma_da_folha, campus_e2e, capturar):
    """Tarefa 36 — as datas administrativas do campus, mês a mês.

    A asserção é o **evento**, não a moldura: a view empilha eventos de quatro origens conforme
    os apps instalados e o perfil de quem olha, e um calendário que abre e não desenha nada é o
    desfecho de qualquer uma delas ter parado de casar — com status 200, bonito e vazio.

    O ``Ano`` corrente (via ``cronograma_da_folha``) não é conforto: a view faz
    ``Ano.objects.filter(ano=hoje.year).first()`` e usa ``ano.ano`` sem guarda; num banco sem a
    linha do ano esta tela é um 500.
    """
    ano = cronograma_da_folha.ano.ano
    pagina = logado_comum('solicitante')

    tela = Tela(pagina).ir(CALENDARIO_ADMINISTRATIVO)
    tela.ver_titulo('Calendário Administrativo por Campus')
    tela.ver_texto('Consulta da Prévia da Folha')
    anotar('calendario-administrativo', tela)

    tela.preencher_formulario([('Ano', 'lista', str(ano)), ('Unidade Organizacional', 'lista', str(campus_e2e))])
    tela.clicar_botao('Enviar')
    tela.ver_texto('Consulta da Prévia da Folha')
    capturar(pagina, 'calendario-administrativo')


def test_documentacao_publica_do_sistema(pagina_anonima, documentacao_gerada, capturar):
    """Para o público externo — o site de documentação que o SUAP publica sem login.

    Seis rotas formam um site inteiro dentro do SUAP (índice, módulo, funcionalidade, cenário,
    imagens e fluxogramas), e nenhuma delas tem ``login_required``: é assim que a documentação é
    consultada por quem ainda não entrou. O que a doc de usuário registra é a porta e o que se
    encontra atrás dela; o conteúdo vem dos artefatos que a execução do behave deixa em disco —
    na captura, portanto, o módulo listado é o da fixture, e não a documentação real de uma
    instituição em operação.

    Nenhuma das seis falha alto sem os artefatos (respondem ``httprr`` com aviso), então a
    asserção é sobre o **conteúdo** renderizado, nunca sobre o status.
    """
    tela = Tela(pagina_anonima).ir(DOCUMENTACAO)
    tela.ver_texto('Selecione o módulo:')
    tela.ver_texto(documentacao_gerada['nome'])
    anotar('documentacao-indice', tela)
    expect(tela.loc('//main//a[@class="sobre"]').first).to_be_visible()
    capturar(pagina_anonima, 'documentacao-indice')
