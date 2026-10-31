"""Roteiro navegado das tarefas do ``pgd2`` — a fonte de ``pgd2/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

Fluxos completos (PGD → PES → PIT → RIT) exigem uma cadeia de estado que nenhum
``features/`` cobre (o módulo não tem behave). Onde o teste prepara estado por ORM — a
cadeia de adesões e calendários, a solicitação de aprovação pendente para o chefe —, o
passo DOCUMENTADO continua sendo navegado; o que foi semeado por ORM está declarado no
relatório final do subagente.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

SOLICITAR_ADESAO = '/pgd2/solicitar_adesao/'
CADASTRAR_PIT = '/pgd2/cadastrar_pit/'
ADESOES_A_APROVAR = '/admin/pgd2/solicitacaoadesaoservidor/'
PITS_CHEFE = '/pgd2/listar_pits_chefe_deve_pode_aprova_homologa/'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    main = ' '.join(tela.pagina.locator('//main').all_inner_texts())[:800]
    html = (
        tela.pagina.locator('//main//form').first.evaluate('(el) => el.outerHTML.slice(0, 6000)')
        if tela.pagina.locator('//main//form').count()
        else ''
    )
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}'
        f'\n  erros: {tela.erros_na_tela()}'
        f'\n  main: {main!r}'
        f'\n  form-html: {html[:6000]!r}\n'
    )


# ---------------------------------------------------------------------------------------
# Fixtures de estado de domínio (via ORM — ver docstring do módulo)
# ---------------------------------------------------------------------------------------


def _criar_pit(servidor, dados: dict) -> object:
    """PIT em EM_CADASTRO para o servidor da doc, com uma entrega vinculada ao PES."""
    from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoEntregas

    hoje = date.today()
    pit = PlanoIndividualTrabalho.objects.create(
        adesao=dados['adesao_pgd'],
        periodo_pit_rit=dados['periodo_pit_rit'],
        data_inicio=dados['periodo_pit_rit'].data_inicio,
        data_fim=dados['periodo_pit_rit'].data_fim,
        situacao=PlanoIndividualTrabalho.EM_CADASTRO,
        regime_execucacao=PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
        percentual_teletrabalho=100,
    )
    PlanoIndividualTrabalhoEntregas.objects.create(
        pit=pit,
        entrega_pes=dados['entrega_pes'],
        titulo='Entrega do PIT (doc de usuário)',
        descricao='Entrega de exemplo vinculada à entrega do PES.',
        data_prazo=hoje + timedelta(days=30),
        tempo_planejado=20,
    )
    pit.calcular_pit_setores_envolvidos()
    return pit


@pytest.fixture
def pit_em_cadastro(servidor_pgd, doc_seed):
    """PIT EM_CADASTRO com entrega — o estado em que o servidor navega o plano."""
    return _criar_pit(servidor_pgd, doc_seed)


@pytest.fixture
def pit_aguardando_aprovacao(pit_em_cadastro):
    """PIT AGUARDANDO_PARECER com a solicitação pendente — o que o chefe deve aprovar.

    Reproduz por ORM o efeito do view ``solicitar_aprovacao_homologacao_pit``
    (``pgd2/views.py:3150``): ``gerar_solicitacao_aprovacao_homologacao_pit_rit`` muda a
    situação para AGUARDANDO_PARECER e cria as ``PitSolicitacaoAnaliseSetor`` pendentes, e
    o ``RegistroAcaoPlanoIndividualTrabalho`` da solicitação é o que a tela de visualização
    lê para exibir a justificativa (``pgd2/views.py:2347`` — sem ele o view dá
    ``AttributeError: 'NoneType' object has no attribute 'observacao'``, medido nesta
    rodada).
    """
    from pgd2.models import PitSolicitacaoAnalise, RegistroAcaoPlanoIndividualTrabalho

    pit = pit_em_cadastro
    pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(objeto_parecer=PitSolicitacaoAnalise.PIT)
    RegistroAcaoPlanoIndividualTrabalho.objects.create(
        tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO,
        pit=pit,
        ip='127.0.0.1',
        observacao=f'Foi solicitado aprovação/homologação do "{pit}"',
    )
    return pit


@pytest.fixture
def pit_homologado_para_rit(servidor_pgd, doc_seed):
    """PIT HOMOLOGADO com RIT em EM_CADASTRO — o estado em que o servidor entrega o RIT.

    A entrega do PIT nasce com ``homologado=True``: é o que ``get_entregas_pit_para_rit``
    (``pgd2/models.py:4306``) exige — só entregas homologadas viram RIT.
    """
    from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoEntregas

    pit = _criar_pit(servidor_pgd, doc_seed)
    pit.situacao = PlanoIndividualTrabalho.HOMOLOGADO
    pit.situacao_rit = PlanoIndividualTrabalho.EM_CADASTRO_RIT
    pit.save()
    PlanoIndividualTrabalhoEntregas.objects.filter(pit=pit).update(homologado=True)
    return pit


# ---------------------------------------------------------------------------------------
# Tarefas
# ---------------------------------------------------------------------------------------


def test_solicitar_adesao_e_chefe_deferir(logado_doc, capturar):
    """Tarefa 1 — o servidor solicita a adesão ao PGD e o chefe do setor defere.

    As duas pontas no mesmo teste: a solicitação nasce SOLICITADO na mão do servidor e só
    vira adesão vigente depois do deferimento da chefia (a página de adesão muda de título).
    """
    from pgd2.models import SolicitacaoAdesaoServidor

    servidor = logado_doc('novato')
    tela = Tela(servidor).ir(SOLICITAR_ADESAO)
    tela.ver_titulo('Solicitar Adesão ao PGD')
    _anotar('adesao-formulario', tela)
    tela.preencher_formulario(
        [
            ('Preferência de contato', 'lista', 'Ligação'),
            ('Telefone para Contato PGD', 'texto', '(84) 99999-9999'),
            ('Código do país', 'texto', '55'),
            (
                'Confirmo esta Solicitação de Adesão e estou de acordo com todas as regras aqui descritas',
                'checkbox',
                'marcar',
            ),
        ]
    )
    # A senha vive num `.password-container` com botão "Exibir a senha" — o input não é
    # irmão do label, então a camada `Tela` não a alcança; preenche-se direto.
    tela.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    capturar(tela.pagina, 'adesao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação de Adesão submetida com sucesso.')
    sol = SolicitacaoAdesaoServidor.objects.filter(servidor__matricula='155104').order_by('-id').first()
    assert sol is not None, 'a UI disse que solicitou, mas não persistiu'
    assert sol.situacao == SolicitacaoAdesaoServidor.SOLICITADO, 'a UI disse que solicitou, mas não persistiu'
    tela.ver_titulo('Solicitação de Adesão do Servidor ao PGD')
    _anotar('adesao-solicitada', tela)
    capturar(tela.pagina, 'adesao-solicitada')

    # Do outro lado do balcão: o chefe do setor defere a solicitação que chegou.
    chefe = Tela(logado_doc('chefe')).ir(ADESOES_A_APROVAR)
    chefe.ver_titulo('Adesão do Servidor ao PGD - A Aprovar')
    _anotar('adesao-chefe-listagem', chefe)
    capturar(chefe.pagina, 'adesao-chefe-listagem')
    chefe.linha('Novato PGD Doc').clicar_icone('exibição')

    chefe.ver_titulo('Solicitação de Adesão do Servidor ao PGD')
    chefe.ver_botao('Deferir')
    _anotar('adesao-chefe-avaliar', chefe)
    capturar(chefe.pagina, 'adesao-chefe-avaliar')
    chefe.clicar_botao('Deferir')
    _anotar('adesao-chefe-confirmar', chefe)
    capturar(chefe.pagina, 'adesao-chefe-confirmar')
    chefe.preencher_formulario(
        [
            ('Justificativa/Observação', 'textarea', 'Deferido pela chefia do setor.'),
            ('Confirmo esta operação', 'checkbox', 'marcar'),
        ]
    )
    chefe.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    chefe.clicar_botao('Enviar')
    chefe.sucesso('Realizado com sucesso.')
    sol.refresh_from_db()
    assert sol.situacao == SolicitacaoAdesaoServidor.DEFERIDO, 'a UI disse que deferiu, mas não persistiu'


def test_cadastrar_pit_com_entrega_e_solicitar_aprovacao(logado_doc, capturar):
    """Tarefa 2 — o servidor cadastra o PIT, vincula uma entrega do PES e envia para o chefe.

    Os quatro atos de uma tacada só, como o usuário faz: adicionar o plano (com adesão e
    calendário), selecionar a entrega do PES, informar os dados dela e pedir a análise.
    """
    from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoEntregas

    tela = Tela(logado_doc('servidor')).ir(CADASTRAR_PIT)
    tela.ver_titulo('Adicionar PIT - Servidor PGD Doc')
    _anotar('pit-formulario', tela)
    # A única adesão vigente do servidor é a do seed; `index=1` pula o placeholder "---------".
    tela.campo('Selecione a adesão', 'lista').first.select_option(index=1)
    # A busca AJAX casa o TÍTULO ('PIT/RIT doc de usuário') mas o resultado exibe o `__str__`
    # ('Calendário de PIT/RIT de ...'), então `opcao` ancora o rótulo exibido.
    tela.preencher('Calendário PIT/RIT', 'autocomplete', 'PIT/RIT doc de usuário', 'Calendário de PIT/RIT de')
    tela.preencher('Confirmo este cadastro', 'checkbox', 'marcar')
    tela.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    capturar(tela.pagina, 'pit-formulario')
    tela.clicar_botao('Enviar')

    tela.sucesso('PIT adicionado com sucesso.')
    pit = PlanoIndividualTrabalho.objects.filter(adesao__servidor__matricula='155101').order_by('-id').first()
    assert pit is not None, 'a UI disse que salvou, mas não persistiu'
    tela.ver_titulo(pit.get_verbose_pit())
    _anotar('pit-visualizar', tela)
    capturar(tela.pagina, 'pit-visualizar')

    # Seleciona a entrega do PES do setor pela própria tela do PIT: na aba Entregas, o
    # botão Adicionar abre o menu com a opção de entrega vinculada ao PES.
    tela.clicar_aba('Entregas')
    tela.clicar_botao('Adicionar')
    tela.clicar_link('Entrega vinculada a entrega do PES')
    tela.ver_texto('Entrega de exemplo do PES')
    _anotar('pit-selecionar-entrega', tela)
    capturar(tela.pagina, 'pit-selecionar-entrega')
    tela.clicar_botao('Selecionar')

    tela.ver_titulo('Cadastrar Entrega - PIT -')
    _anotar('pit-entrega-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', 'Entrega do PIT (doc de usuário)'),
            ('Descrição', 'textarea', 'Entrega de exemplo vinculada à entrega do PES.'),
            ('Prazo', 'data', (date.today() + timedelta(days=30)).strftime('%d/%m/%Y')),
            ('Tempo planejado', 'texto', '20'),
        ]
    )
    capturar(tela.pagina, 'pit-entrega-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Dados cadastrados com sucesso.')
    assert PlanoIndividualTrabalhoEntregas.objects.filter(pit=pit, titulo='Entrega do PIT (doc de usuário)').exists(), (
        'a UI disse que salvou, mas não persistiu'
    )
    _anotar('pit-aba-entregas', tela)
    capturar(tela.pagina, 'pit-aba-entregas')

    # A solicitação de análise exige os dados básicos (regime e % de teletrabalho)
    # — sem eles a tela avisa "Não existem dados suficientes para uma solicitação".
    tela.clicar_aba('Dados básicos')
    tela.clicar_botao('Editar')
    tela.ver_titulo('Editar Dados Básicos - PIT -')
    _anotar('pit-dados-basicos', tela)
    tela.preencher_formulario(
        [
            ('Regime individual de execução no PGD', 'lista', 'Teletrabalho integral'),
            # Regra do SUAP: teletrabalho integral só com 100% (validação medida na tela).
            ('% de Teletrabalho', 'texto', '100'),
        ]
    )
    capturar(tela.pagina, 'pit-dados-basicos')
    tela.clicar_botao('Salvar')
    tela.sucesso('Dados editados com sucesso.')

    # O regime de teletrabalho exige o cronograma de atendimento em teletrabalho antes
    # da solicitação de análise (a tela de visualização avisa quando ele falta).
    tela.clicar_aba('Cronograma de Atendimento em Teletrabalho')
    tela.clicar_botao('Adicionar')
    tela.ver_titulo('Cadastrar Cronograma de Atendimento em Teletrabalho - PIT -')
    _anotar('pit-atendimento', tela)
    tela.preencher_formulario(
        [
            ('Data', 'data', date.today().strftime('%d/%m/%Y')),
            ('Hora Inicial', 'hora', '08:00'),
            ('Hora Final', 'hora', '12:00'),
        ]
    )
    capturar(tela.pagina, 'pit-atendimento')
    tela.clicar_botao('Salvar')
    tela.sucesso('Dados cadastrados com sucesso.')

    # Solicita a análise da chefia, já na página do PIT.
    tela.clicar_botao('Solicitar aprovação/homologação')
    tela.preencher_formulario(
        [
            ('Justificativa/Observação', 'textarea', 'Plano concluído, solicito análise.'),
            ('Confirmo esta operação', 'checkbox', 'marcar'),
        ]
    )
    tela.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    tela.clicar_botao('Enviar')
    tela.sucesso('Aprovação/homologação solicitada com sucesso.')
    pit.refresh_from_db()
    assert pit.situacao == PlanoIndividualTrabalho.AGUARDANDO_PARECER, 'a UI disse que enviou, mas não persistiu'


def test_chefe_aprovar_e_homologar_pit(logado_doc, pit_aguardando_aprovacao, capturar):
    """Tarefa 3 — o chefe do setor analisa o PIT enviado pelo servidor.

    A lista ``Deve aprovar/homologar`` é a porta de entrada documentada; o PIT aguardando é
    semeado por ORM (fixture ``pit_aguardando_aprovacao``) porque a cadeia completa
    PGD→PES→solicitação não é navegável em um teste isolado sem custo proibitivo.

    O PIT da doc tem um único setor envolvido, e ele é o setor principal apto a homologar
    (``PitSetores.pode_homologar=True``): por isso a análise da chefia JÁ É a homologação —
    o botão "Aprovar" só aparece quando o plano envolve entregas de outros setores, que são
    aprovadas pelos chefes deles antes da homologação do setor principal.
    """
    from pgd2.models import PlanoIndividualTrabalho

    pit = pit_aguardando_aprovacao

    tela = Tela(logado_doc('chefe')).ir(PITS_CHEFE)
    tela.ver_titulo('Planos Individuais de Trabalho para Aprovar/Homologar')
    _anotar('chefe-pits-listagem', tela)
    capturar(tela.pagina, 'chefe-pits-listagem')
    # O PIT que o test_02 enviou também está na lista, com o mesmo servidor, e a listagem não
    # tem ordem: a linha é escolhida pelo link do PIT da fixture, não pelo nome.
    tela.pagina.locator(f'a[href="/pgd2/visualizar_pit/{pit.pk}"]').first.click()

    try:
        tela.ver_titulo(pit.get_verbose_pit())
    except AssertionError:
        sys.stderr.write('\n[erro-visualizar] corpo: ' + repr(' '.join(tela.pagina.locator('//main').all_inner_texts())[:3000]) + '\n')
        raise
    tela.ver_botao('Homologar PIT')
    _anotar('chefe-pit-visualizar', tela)
    capturar(tela.pagina, 'chefe-pit-visualizar')
    tela.clicar_botao('Homologar PIT')
    tela.ver_titulo('Homologar - PIT -')
    _anotar('chefe-pit-homologar', tela)
    # O formulário de homologação traz as confirmações do que o plano declara (regime,
    # % de teletrabalho, cronograma presencial — só quando existe, atendimento e entregas).
    # Homologar é conferir cada uma e confirmar a operação.
    tela.preencher('Confirmo Regime individual de execução no PGD informado no PIT', 'checkbox', 'marcar')
    tela.preencher('Confirmo % de Teletrabalho informado no PIT', 'checkbox', 'marcar')
    tela.preencher('Confirmo Cronograma de Atendimento em Teletrabalho informado no PIT', 'checkbox', 'marcar')
    tela.preencher('Confirmo Entregas informadas no PIT', 'checkbox', 'marcar')
    tela.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    capturar(tela.pagina, 'chefe-pit-homologar')
    tela.clicar_botao('Enviar')
    tela.sucesso('Homologação cadastrada com sucesso.')
    pit.refresh_from_db()
    assert pit.situacao == PlanoIndividualTrabalho.HOMOLOGADO, 'a UI disse que homologou, mas não persistiu'


def test_entregar_rit(logado_doc, pit_homologado_para_rit, capturar):
    """Tarefa 4 — o servidor registra a execução no RIT e o chefe homologa.

    O RIT é por entrega do PIT: a tela lista cada entrega planejada com o tempo previsto e
    o botão "Adicionar entrega" abre o formulário de execução. Depois de enviado, o chefe
    homologa com a avaliação e o tempo homologado.
    """
    from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho

    pit = pit_homologado_para_rit
    entrega_pit = pit.get_entregas_pit_para_rit().first()
    assert entrega_pit is not None, 'fixture sem entrega de PIT para o RIT'

    tela = Tela(logado_doc('servidor')).ir(f'/pgd2/visualizar_rit/{pit.id}/')
    tela.ver_titulo(pit.get_verbose_rit())
    _anotar('rit-visualizar', tela)
    capturar(tela.pagina, 'rit-visualizar')
    # A entrega do PIT vive numa box recolhida (accordion) — expandir antes de agir.
    tela.pagina.locator(
        '//button[contains(@class, "accordion-button") and contains(normalize-space(.), "Entrega do PIT (doc de usuário)")]'
    ).first.click()
    tela.ver_botao('Adicionar entrega')
    tela.clicar_botao('Adicionar entrega')

    tela.ver_titulo('Cadastrar Entrega - Relatório Individual de Trabalho (RIT)')
    _anotar('rit-entrega-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', 'Execução da entrega (doc de usuário)'),
            ('Descrição', 'textarea', 'Execução registrada pelo servidor.'),
            ('Data Início', 'data', (date.today() - timedelta(days=5)).strftime('%d/%m/%Y')),
            ('Data Final', 'data', date.today().strftime('%d/%m/%Y')),
            ('Horas da Execução', 'texto', '20'),
            ('% executado em teletrabalho', 'texto', '50'),
        ]
    )
    capturar(tela.pagina, 'rit-entrega-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Dados cadastrados com sucesso.')
    assert RelatorioIndividualTrabalho.objects.filter(entrega_pit=entrega_pit).exists(), 'a UI disse que salvou, mas não persistiu'

    tela.clicar_botao('Solicitar aprovação/homologação')
    tela.preencher_formulario(
        [
            ('Justificativa/Observação', 'textarea', 'Execução concluída, solicito homologação.'),
            ('Confirmo esta operação', 'checkbox', 'marcar'),
        ]
    )
    tela.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    tela.clicar_botao('Enviar')
    tela.sucesso('Aprovação/homologação solicitada com sucesso.')
    pit.refresh_from_db()
    assert pit.situacao_rit == PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT, 'a UI disse que enviou, mas não persistiu'

    # O chefe homologa a execução.
    chefe = Tela(logado_doc('chefe')).ir(f'/pgd2/homologar_rit/{pit.id}/')
    chefe.ver_titulo(f'Homologar - {pit.get_verbose_rit()}')
    _anotar('chefe-rit-homologar', chefe)
    # O radio "Avaliar como" renderiza o input dentro do label da opção — o clique é no label.
    chefe.pagina.locator('//label[contains(normalize-space(.), "Adequado: plano de trabalho")]').first.click()
    chefe.preencher('Justificativa/Observação', 'textarea', 'Execução adequada.')
    chefe.preencher('Tempo homologado (Em horas)', 'texto', '20')
    chefe.preencher('Confirmo esta operação e que estou de acordo com as entregas informadas no RIT', 'checkbox', 'marcar')
    chefe.pagina.locator('//input[@type="password"]').first.fill(SENHA_E2E)
    capturar(chefe.pagina, 'chefe-rit-homologar')
    chefe.clicar_botao('Enviar')
    chefe.sucesso('Homologação cadastrada com sucesso.')
    pit.refresh_from_db()
    assert pit.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT, 'a UI disse que homologou, mas não persistiu'


def test_meu_pgd_e_pendencias(logado_doc, capturar):
    """Tarefa 5 — o servidor consulta o painel "Meu PGD" e a central de pendências."""
    tela = Tela(logado_doc('servidor')).ir('/pgd2/meu_pgd/')
    assert 'at /' not in tela.pagina.title(), f'meu_pgd respondeu página de erro: {tela.pagina.title()}'
    _anotar('meu-pgd', tela)
    capturar(tela.pagina, 'meu-pgd')

    tela.ir('/pgd2/pendencias_avisos_pgd/')
    assert 'at /' not in tela.pagina.title(), f'pendencias respondeu página de erro: {tela.pagina.title()}'
    _anotar('pendencias', tela)
    capturar(tela.pagina, 'pendencias')
