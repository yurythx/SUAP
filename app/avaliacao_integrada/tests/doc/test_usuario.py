"""Roteiro navegado das tarefas do ``avaliacao_integrada`` — a fonte de ``docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções existem para a
rodada falhar alto quando a tela mudou de forma — doc que descreve um passo inexistente é pior
que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito: o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

**Os testes são uma cadeia** (``NN`` no nome garante a ordem dentro do arquivo): a estrutura
sustenta o indicador, o indicador sustenta a avaliação, a avaliação sustenta o público-alvo, o
público-alvo sustenta a resposta e a resposta sustenta o relatório. É a mesma cadeia que o
usuário percorre, e é o que evita montar por ORM aquilo que a doc afirma ser feito pela tela.
O CI roda ``pytest -m doc -n 1 --dist loadgroup``, e o ``xdist_group`` por módulo (conftest
raiz) mantém o arquivo inteiro num worker só se o ``-n`` subir.

As asserções são por chave própria e por delta, nunca por contagem global: o banco é
compartilhado entre os módulos da rodada e a suíte não dá flush.
"""

from __future__ import annotations

import datetime
import sys

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ADMIN_EIXO = '/admin/avaliacao_integrada/eixo/'
ADMIN_DIMENSAO = '/admin/avaliacao_integrada/dimensao/'
ADMIN_MACROPROCESSO = '/admin/avaliacao_integrada/macroprocesso/'
ADMIN_TIPO = '/admin/avaliacao_integrada/tipoavaliacao/'
ADMIN_INDICADOR = '/admin/avaliacao_integrada/indicador/'
ADMIN_AVALIACAO = '/admin/avaliacao_integrada/avaliacao/'
ADMIN_COMISSAO = '/admin/avaliacao_integrada/comissaocpa/'
ADMIN_SEGMENTO = '/admin/avaliacao_integrada/segmento/'
ADMIN_ESCALA = '/admin/avaliacao_integrada/escalalikert/'

DEFINIR_AREAS = '/rh/definir_areas_vinculacao/'
AREAS_POR_SETOR = '/rh/areas_vinculacao_setor/'
RELATORIO = '/avaliacao_integrada/relatorio/'
RELATORIO_XLSX = '/avaliacao_integrada/relatorio_xlsx/'
URL_AVALIACAO = '/avaliacao_integrada/avaliacao/{}/'
URL_QUESTIONARIO = '/avaliacao_integrada/questionario/{}/'
URL_AVALIACAO_EXTERNA = '/avaliacao_integrada/avaliacao_externa/{}'

# O campus dos três servidores do seed (``campus('CZN')`` no ``doc_seed``).
CAMPUS = 'CZN'
# A raiz da árvore de setores do seed (``semear_base`` de ``djtools/e2e_fixtures.py``).
RAIZ = 'RAIZ'
# O `aspecto` do indicador da rodada: é ele, e não a denominação, que a tela do respondente
# e a listagem do relatório imprimem.
CRITERIO_DO_INDICADOR = 'A comunidade acadêmica participa da autoavaliação institucional.'
ANO = datetime.date.today().year

# Os textos de orientação: são o cabeçalho que o respondente lê antes das perguntas, um por
# público. Preenchidos porque a doc os descreve — e porque a tela do questionário sem eles
# renderiza um resto de marcação no lugar do aviso.
INSTRUCOES_SERVIDORES = 'Suas respostas são anônimas e levam cerca de 10 minutos.'
INSTRUCOES_SOCIEDADE_CIVIL = 'Sua opinião ajuda o IFRN a melhorar o atendimento à comunidade.'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}\n'
    )


def _escolher_no_popup_de_lista(tela: Tela, campo: str, *opcoes: str) -> None:
    """Preenche um ``ModelMultiplePopupChoiceField`` — o campo "Escolha uma ou mais opções".

    Não é o popup de iframe do fancybox que ``Tela.popup()`` conhece: este widget
    (``djtools/templates/popup_multiple_choice_field_widget.html``) abre o fancybox em modo
    ``ajax``, injetando o conteúdo no **mesmo** documento. Os checkboxes carregam o rótulo no
    atributo ``title`` e o botão de fechar chama-se **Confirmar**.

    Fica local ao módulo e não vira método da ``Tela``: é uma linha de XPath e o único ponto
    do ``avaliacao_integrada`` que precisa disso é o campo *Áreas de Vinculação* da avaliação.
    """
    tela.pagina.locator(f'input#__{campo}__').first.click()
    caixa = tela.pagina.locator('#__x__')
    caixa.wait_for(state='visible', timeout=15000)
    for opcao in opcoes:
        caixa.locator(f'//input[@type="checkbox" and @title="{opcao}"]').first.check()
    caixa.locator('//button[contains(normalize-space(.), "Confirmar")]').first.click()
    tela.esperar()


def _preencher_editor_rico(tela: Tela, campo: str, texto: str) -> None:
    """Preenche um ``TinyMCEFormField`` pelo **nome do campo**, e não pelo rótulo.

    ``Tela.preencher(..., 'texto rico')`` ancora no ``<label>``, e o formulário da avaliação
    tem TRÊS editores com o mesmo rótulo *Texto com instruções* (um por público: servidores,
    alunos, sociedade civil) — o ancoramento pelo rótulo sempre acertaria o primeiro. O
    TinyMCE nomeia o iframe como ``<id_do_textarea>_ifr``, que é único.
    """
    corpo = tela.pagina.frame_locator(f'#id_{campo}_ifr').locator('body')
    corpo.wait_for(state='visible', timeout=15000)
    corpo.fill(texto)


def _responder_todos_os_radios(tela: Tela) -> int:
    """Marca a última opção de cada grupo de rádios visível — o questionário Likert.

    Devolve quantos grupos foram respondidos. A última opção é *Concordo* na escala padrão
    (``nivel=4``); qual delas é marcada não importa para a doc, importa que a tela aceite.
    """
    nomes = tela.pagina.eval_on_selector_all(
        'form input[type=radio]',
        'els => [...new Set(els.filter(e => e.offsetParent !== null).map(e => e.name))]',
    )
    for nome in nomes:
        tela.pagina.locator(f'form input[type=radio][name="{nome}"]').last.check()
    return len(nomes)


def test_01_associar_areas_de_vinculacao_aos_setores(logado_doc, capturar):
    """Tarefa 1 — o pré-requisito de tudo: dizer a que área cada setor pertence.

    Sem isso a avaliação recusa gerar o público-alvo (``avaliacao.html:105-118``) e o
    questionário do público interno nem abre (``Respondente.possui_area_vinculacao``).
    """
    from rh.models import Setor

    tela = Tela(logado_doc('administrador')).ir(DEFINIR_AREAS)
    tela.ver_titulo('Definir Áreas dos Setores')
    _anotar('definir-areas-passo-1', tela)
    capturar(tela.pagina, 'areas-vinculacao-filtro')

    # A raiz com "Definir Recursivamente" é o caminho realista: enquanto UM setor com
    # técnico-administrativo ativo estiver sem área, a avaliação esconde os botões de
    # reprocessar público-alvo e mostra "Setores com pendências" (`avaliacao.html:105-118`).
    tela.preencher('Palavra-chave', 'texto', RAIZ)
    tela.clicar_botao('Continuar')

    tela.ver_texto('Seleção dos Setores')
    _anotar('definir-areas-passo-2', tela)
    tela.preencher('Setores', 'checkbox multiplo', RAIZ)
    tela.preencher('Áreas de Vinculação', 'checkbox multiplo', 'Ensino')
    tela.preencher('Definir Recursivamente', 'checkbox', 'marcar')
    capturar(tela.pagina, 'areas-vinculacao-selecao')
    tela.clicar_botao('Finalizar')

    tela.sucesso('Áreas vinculadas com sucesso.')
    setor = Setor.objects.suap_ativos().get(sigla=CAMPUS)
    assert setor.areas_vinculacao.filter(descricao='Ensino').exists(), 'a UI disse que vinculou, mas o setor continua sem a área'

    # A tela de conferência é o outro item de menu do par, e é só leitura.
    tela.ir(AREAS_POR_SETOR)
    tela.ver_titulo('Áreas de Vinculação dos Setores')
    _anotar('areas-por-setor', tela)
    capturar(tela.pagina, 'areas-vinculacao-arvore')


def test_02_montar_estrutura(logado_doc, nomes, capturar):
    """Tarefa 2 — a árvore que organiza as perguntas: eixo, dimensão e macroprocesso.

    Mais o **tipo de avaliação**, que é o que a avaliação e o indicador usam para se
    encontrarem (``subsidio_para``). Uma tarefa só porque ninguém cadastra um eixo sem
    pendurar nele uma dimensão — a árvore vazia não serve para nada.
    """
    from avaliacao_integrada.models import Dimensao, Eixo, Macroprocesso, TipoAvaliacao

    tela = Tela(logado_doc('administrador')).ir(ADMIN_TIPO)
    tela.ver_titulo('Tipos de Avaliação')
    tela.clicar_botao('Adicionar Tipo de Avaliação')
    tela.preencher('Descrição', 'texto', nomes.tipo_avaliacao)
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert TipoAvaliacao.objects.filter(descricao=nomes.tipo_avaliacao).exists(), 'a UI disse que cadastrou, mas o tipo não persistiu'

    tela.ir(ADMIN_EIXO)
    tela.ver_titulo('Eixos')
    tela.ver_botao('Adicionar Eixo')
    _anotar('eixos-listagem', tela)
    capturar(tela.pagina, 'eixos-listagem')

    tela.clicar_botao('Adicionar Eixo')
    tela.ver_titulo('Adicionar Eixo')
    _anotar('eixo-formulario', tela)
    tela.preencher('Descrição', 'texto', nomes.eixo)
    tela.preencher('Texto de Ajuda', 'textarea', 'Eixo do instrumento de autoavaliação institucional.')
    capturar(tela.pagina, 'eixo-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    eixo = Eixo.objects.get(descricao=nomes.eixo)

    tela.ir(ADMIN_DIMENSAO)
    tela.ver_titulo('Dimensões')
    tela.clicar_botao('Adicionar Dimensão')
    tela.ver_titulo('Adicionar Dimensão')
    _anotar('dimensao-formulario', tela)
    tela.preencher('Eixo', 'autocomplete', nomes.eixo)
    tela.preencher('Descrição', 'texto', nomes.dimensao)
    capturar(tela.pagina, 'dimensao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    dimensao = Dimensao.objects.get(descricao=nomes.dimensao)
    assert dimensao.eixo == eixo, 'a dimensão deveria nascer pendurada no eixo escolhido'

    tela.ir(ADMIN_MACROPROCESSO)
    tela.ver_titulo('Macroprocessos')
    tela.clicar_botao('Adicionar Macroprocesso')
    tela.ver_titulo('Adicionar Macroprocesso')
    _anotar('macroprocesso-formulario', tela)
    tela.preencher('Dimensão', 'autocomplete', nomes.dimensao)
    tela.preencher('Descrição', 'texto', nomes.macroprocesso)
    capturar(tela.pagina, 'macroprocesso-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    macroprocesso = Macroprocesso.objects.get(descricao=nomes.macroprocesso)
    assert macroprocesso.dimensao == dimensao, 'o macroprocesso deveria nascer pendurado na dimensão escolhida'


def test_03_cadastrar_indicador(logado_doc, nomes, capturar):
    """Tarefa 3 — a pergunta em si, com a régua de resposta e o público que a responde."""
    from avaliacao_integrada.models import Indicador

    tela = Tela(logado_doc('administrador')).ir(ADMIN_INDICADOR)
    tela.ver_titulo('Indicadores')
    tela.ver_botao('Adicionar Indicador')
    _anotar('indicadores-listagem', tela)
    capturar(tela.pagina, 'indicadores-listagem')

    tela.clicar_botao('Adicionar Indicador')
    tela.ver_titulo('Adicionar Indicador')
    _anotar('indicador-formulario', tela)

    tela.preencher_formulario(
        [
            ('Anos de Referência', 'checkbox multiplo', str(ANO)),
            ('Macroprocesso', 'autocomplete', nomes.macroprocesso),
            ('Denominação do Indicador', 'texto', nomes.indicador),
            ('Critério de Análise', 'texto', CRITERIO_DO_INDICADOR),
            ('Subsídio p/ Avaliações', 'checkbox multiplo', nomes.tipo_avaliacao),
            ('Escala Likert', 'lista', 'Escala Padrão'),
        ]
    )
    tela.quadro('Respondentes Servidores').preencher('Segmentos', 'FilteredSelectMultiple', 'TECNICO')
    tela.quadro('Respondentes Sociedade Civil').preencher('Segmentos', 'FilteredSelectMultiple', 'OUTRO_SOCIEDADE_CIVIL')
    capturar(tela.pagina, 'indicador-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    indicador = Indicador.objects.get(nome=nomes.indicador)
    assert indicador.escala is not None, 'o indicador de escala Likert deveria gravar a escala escolhida'
    assert set(indicador.segmentos.values_list('descricao', flat=True)) == {'TECNICO', 'OUTRO_SOCIEDADE_CIVIL'}, (
        f'os segmentos do indicador não persistiram: {list(indicador.segmentos.values_list("descricao", flat=True))}'
    )

    # "Replicar Indicador" é a coluna Opções da listagem: clona o indicador e abre a edição.
    antes = Indicador.objects.filter(nome__startswith=nomes.indicador).count()
    tela.ir(ADMIN_INDICADOR)
    tela.linha(nomes.indicador).clicar_link('Replicar Indicador')
    tela.sucesso('Indicador replicado com sucesso.')
    assert Indicador.objects.filter(nome__startswith=nomes.indicador).count() == antes + 1, 'replicar deveria criar um indicador a mais'
    replicado = Indicador.objects.get(nome=f'{nomes.indicador} [Replicado]')
    capturar(tela.pagina, 'indicador-replicado')

    # O clone não pode entrar no questionário desta rodada: dobraria as perguntas.
    Indicador.objects.filter(pk=replicado.pk).update(em_uso=False)


def test_04_criar_avaliacao(logado_doc, nomes, capturar):
    """Tarefa 4 — a aplicação: prazo, público e textos de orientação."""
    from avaliacao_integrada.models import Avaliacao

    hoje = datetime.date.today()
    tela = Tela(logado_doc('aplicador')).ir(ADMIN_AVALIACAO)
    tela.ver_titulo('Avaliações')
    tela.ver_botao('Adicionar Avaliação')
    _anotar('avaliacoes-listagem', tela)
    capturar(tela.pagina, 'avaliacoes-listagem')

    tela.clicar_botao('Adicionar Avaliação')
    tela.ver_titulo('Adicionar Avaliação')
    _anotar('avaliacao-formulario', tela)

    tela.preencher_formulario(
        [
            ('Tipos', 'checkbox multiplo', nomes.tipo_avaliacao),
            ('Ano de Referência', 'autocomplete', str(ANO)),
            ('Nome', 'texto', nomes.avaliacao),
            ('Descrição', 'textarea', 'Autoavaliação institucional conduzida pela CPA.'),
            ('Data de Início', 'data', (hoje - datetime.timedelta(days=1)).strftime('%d/%m/%Y')),
            ('Data de Término', 'data', (hoje + datetime.timedelta(days=30)).strftime('%d/%m/%Y')),
        ]
    )
    _escolher_no_popup_de_lista(tela, 'areas_vinculacao', 'Ensino')
    tela.quadro('Respondentes Servidores').preencher('Segmentos', 'FilteredSelectMultiple', 'TECNICO')
    tela.quadro('Respondentes Sociedade Civil').preencher('Segmentos', 'FilteredSelectMultiple', 'OUTRO_SOCIEDADE_CIVIL')
    _preencher_editor_rico(tela, 'texto_instrucoes_servidores', INSTRUCOES_SERVIDORES)
    _preencher_editor_rico(tela, 'texto_instrucoes_sociedade_civil', INSTRUCOES_SOCIEDADE_CIVIL)
    capturar(tela.pagina, 'avaliacao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    avaliacao = Avaliacao.objects.get(nome=nomes.avaliacao)
    assert avaliacao.areas_vinculacao.filter(descricao='Ensino').exists(), 'a área de vinculação não persistiu — o questionário não abriria'
    assert avaliacao.possui_segmento_sociedade_civil(), 'sem segmento de sociedade civil a avaliação não ganha link público'
    # O editor grava HTML com entidades (`s&atilde;o`), então a asserção é por um trecho sem
    # acento — o que interessa é que o texto chegou ao campo certo dos três homônimos.
    assert 'levam cerca de 10 minutos' in (avaliacao.texto_instrucoes_servidores or ''), (
        f'o texto de instruções dos servidores não persistiu: {avaliacao.texto_instrucoes_servidores!r}'
    )
    assert 'atendimento' in (avaliacao.texto_instrucoes_sociedade_civil or ''), (
        f'o texto de instruções da sociedade civil não persistiu: {avaliacao.texto_instrucoes_sociedade_civil!r}'
    )


def test_05_publico_alvo(logado_doc, publico_alvo, capturar):
    """Tarefa 4, etapa 2 — identificar quem responde e acompanhar o preenchimento.

    O clique em *Reprocessar Público-Alvo* **não** é executado aqui: com menos de 100 pessoas
    no público-alvo ele devolve "Erro no Sistema" (ver a docstring da fixture ``publico_alvo``
    e o relatório do MR). O que esta rodada afirma é o que ela consegue afirmar: que o botão
    existe para quem tem a permissão, que ele pede confirmação e como fica a aba depois.
    """
    from avaliacao_integrada.models import Respondente

    avaliacao = publico_alvo
    tela = Tela(logado_doc('aplicador')).ir(URL_AVALIACAO.format(avaliacao.pk))
    tela.ver_titulo(avaliacao.nome)
    _anotar('avaliacao-detalhe', tela)

    botao = tela.botao('Reprocessar Público-Alvo')
    assert 'reprocessar o público-alvo' in (botao.get_attribute('data-confirm') or ''), 'o botão deveria pedir confirmação antes de reprocessar'
    # `Reprocessar Público-Alvo e Respostas` exige a permissão de exclusão, que o Aplicador
    # não tem — é a diferença de alçada entre os dois grupos, e a doc a afirma.
    assert tela.pagina.locator('//a[contains(normalize-space(.), "Reprocessar Público-Alvo e Respostas")]').count() == 0, (
        'o Aplicador não deveria enxergar o reprocessamento com exclusão de respostas'
    )

    respondentes = Respondente.objects.filter(avaliacao=avaliacao)
    assert respondentes.exists(), 'sem respondente a aba Público-Alvo não teria o que mostrar'
    tela.ver_texto('Público-Alvo')
    tela.ver_texto('% Respondido')
    _anotar('publico-alvo', tela)
    capturar(tela.pagina, 'avaliacao-publico-alvo')

    tela.clicar_aba('Resumo')
    tela.esperar()
    _anotar('quadro-resumo', tela)
    capturar(tela.pagina, 'avaliacao-quadro-resumo')

    # A MESMA tela, vista pelo Administrador: ele tem `pode_ver_dados_identificaveis`,
    # `pode_enviar_email_lembrete` e `pode_reprocessar_publico_alvo_com_exclusao`, que o
    # Aplicador não tem. É a diferença que a doc afirma, e é aqui que ela é medida.
    # A lista pagina de 50 em 50 e, no `pytest -m doc` inteiro, os outros módulos engordam o
    # público-alvo: o respondente da doc é achado pelo "Buscar" da aba, como faria o usuário.
    admin = Tela(logado_doc('administrador')).ir(f'{URL_AVALIACAO.format(avaliacao.pk)}?tab=respondentes&q=Respondente+Avalint')
    admin.ver_botao('Reprocessar Público-Alvo e Respostas')
    admin.ver_texto('Respondente Avalint')
    _anotar('publico-alvo-administrador', admin)
    capturar(admin.pagina, 'avaliacao-publico-alvo-administrador')

    # O formulário do lembrete é aberto e conferido, mas **não é enviado**: o
    # `EMAIL_BACKEND` padrão é SMTP (`suap/settings_base.py:54`) com host vazio, e o envio
    # trava a request até o timeout. A doc, por isso, descreve o formulário e para aí.
    admin.clicar_link('Enviar lembrete por e-mail')
    popup = admin.popup()
    popup.ver_texto('Confirmo o envio para todos os respondentes elegíveis desta avaliação')
    popup.ver_botao('Enviar e-mail')
    _anotar('lembrete-formulario', popup)
    capturar(admin.pagina, 'avaliacao-lembrete')


def test_06_responder_avaliacao(logado_doc, servidores_doc, publico_alvo, capturar):
    """Tarefa 5 — o servidor responde o questionário que lhe coube.

    É a tarefa com mais gente do módulo e a única que nenhuma ``.feature`` cobre (o cenário
    correspondente está comentado em ``002.AVALIACAO_INTEGRADA.cadastrar_avaliacao.feature``).
    """
    from avaliacao_integrada.models import Respondente, Resposta

    avaliacao = publico_alvo
    respondente = Respondente.objects.get(avaliacao=avaliacao, user=servidores_doc['respondente'].get_user())

    tela = Tela(logado_doc('respondente')).ir('/')
    tela.ver_texto(avaliacao.nome)
    _anotar('inicio-inscricoes', tela)
    capturar(tela.pagina, 'inicio-chamada')

    tela.ir(URL_QUESTIONARIO.format(respondente.pk))
    tela.ver_titulo(avaliacao.nome)
    _anotar('questionario', tela)
    capturar(tela.pagina, 'questionario')

    antes = Resposta.objects.filter(respondente=respondente).count()
    grupos = _responder_todos_os_radios(tela)
    assert grupos, 'o questionário abriu sem nenhuma pergunta de escala Likert'
    tela.clicar_botao('Salvar e Continuar')
    tela.esperar()

    assert Resposta.objects.filter(respondente=respondente).count() > antes, 'a UI disse que salvou, mas nenhuma resposta persistiu'
    respondente.refresh_from_db()
    _anotar('questionario-respondido', tela)
    capturar(tela.pagina, 'questionario-respondido')

    # "Enviar respostas" só existe a 100% (`questionario.html:169`) e fecha o questionário.
    # O clique dispara um `confirm()` nativo, que a fixture `logado` já aceita
    # (`djtools/e2e_fixtures.py:514`).
    # Quem sabe o percentual é a TELA: `Respondente.percentual_resposta` é um campo gravado
    # que só o reprocessamento do público-alvo atualiza, e continua em 0 depois de salvar
    # (medido). O sinal confiável é o botão existir — ele só é renderizado a 100%.
    tela.ver_texto('Você completou 100% da avaliação')
    tela.ver_botao('Enviar respostas')
    tela.clicar_botao('Enviar respostas')
    tela.esperar()

    respondente.refresh_from_db()
    assert respondente.finalizado, 'a UI disse que enviou, mas o questionário não foi marcado como finalizado'
    tela.ver_texto('Sua avaliação foi registrada com sucesso')
    _anotar('questionario-finalizado', tela)
    capturar(tela.pagina, 'questionario-finalizado')


def test_07_relatorios(logado_doc, nomes, publico_alvo, capturar):
    """Tarefa 6 — ler o resultado: relatório por indicador e exportação das respostas."""
    avaliacao = publico_alvo
    tela = Tela(logado_doc('aplicador')).ir(RELATORIO)
    tela.ver_titulo('Relatórios')
    _anotar('relatorio-filtro', tela)
    capturar(tela.pagina, 'relatorio-filtro')

    # `RelatorioForm.avaliacao` é `ModelChoiceField` puro (`forms.py:293`), não a variante
    # `Plus`: o widget é um `<select>` comum, sem select2.
    tela.preencher('Avaliação', 'lista', nomes.avaliacao)
    tela.clicar_botao('Enviar')
    tela.esperar()
    _anotar('relatorio-resultado', tela)
    # A listagem identifica o indicador pelo **Critério de Análise**, não pela denominação:
    # a coluna "Indicador" imprime `indicador.aspecto`.
    tela.ver_texto(CRITERIO_DO_INDICADOR)
    tela.ver_texto(nomes.eixo)
    capturar(tela.pagina, 'relatorio-indicadores')

    tela.linha(CRITERIO_DO_INDICADOR).clicar_link('Visualizar')
    tela.esperar()
    _anotar('relatorio-indicador', tela)
    capturar(tela.pagina, 'relatorio-indicador')

    tela.ir(RELATORIO_XLSX)
    tela.ver_titulo('Relatório em XLSX')
    _anotar('relatorio-xlsx', tela)
    capturar(tela.pagina, 'relatorio-xlsx')
    assert avaliacao.pk


def test_08_manter_comissao_cpa(logado_doc, servidores_doc, nomes, capturar):
    """Tarefa 7 — a comissão própria de avaliação: quem a compõe e por qual portaria."""
    from avaliacao_integrada.models import ComissaoCPA

    servidor = servidores_doc['respondente']
    tela = Tela(logado_doc('administrador')).ir(ADMIN_COMISSAO)
    tela.ver_titulo('Comissões CPA')
    tela.ver_botao('Adicionar Comissão CPA')
    _anotar('comissoes-listagem', tela)
    capturar(tela.pagina, 'comissoes-listagem')

    tela.clicar_botao('Adicionar Comissão CPA')
    _anotar('comissao-formulario', tela)
    tela.preencher_formulario(
        [
            ('Tipo', 'lista', 'CPA Local'),
            ('Nome', 'texto', nomes.comissao),
            ('Setor', 'autocomplete', CAMPUS),
            ('Data da Portaria', 'data', datetime.date.today().strftime('%d/%m/%Y')),
            ('Membro', 'autocomplete multiplo', servidor.matricula),
        ]
    )
    capturar(tela.pagina, 'comissao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    comissao = ComissaoCPA.objects.get(nome=nomes.comissao)
    assert comissao.vinculos_membros.exists(), 'a UI disse que cadastrou, mas a comissão ficou sem membro'
    assert servidor.get_user().groups.filter(name='cpa_campus').exists(), 'entrar na CPA local deveria pôr o membro no grupo cpa_campus'

    # Só pode haver UMA comissão ativa de cada tipo por campus (`ComissaoCPA.clean`). A doc
    # afirma a mensagem, então a rodada a provoca.
    tela.ir(f'{ADMIN_COMISSAO}add/')
    tela.preencher_formulario(
        [
            ('Tipo', 'lista', 'CPA Local'),
            ('Nome', 'texto', f'{nomes.comissao} [duplicada]'),
            ('Setor', 'autocomplete', CAMPUS),
            ('Data da Portaria', 'data', datetime.date.today().strftime('%d/%m/%Y')),
            ('Membro', 'autocomplete multiplo', servidor.matricula),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.ver_texto('já existe. Para adicionar uma nova, deve-se antes desativar a anterior')
    assert not ComissaoCPA.objects.filter(nome__endswith='[duplicada]').exists(), (
        'a validação avisou, mas gravou a segunda comissão ativa mesmo assim'
    )

    tela.ir(ADMIN_COMISSAO)
    tela.linha(nomes.comissao).clicar_link('Lista de Emails dos Membros')
    # O link tem classe `popup`: abre o fancybox em iframe, e sem esperar o iframe a captura
    # sai da listagem, sem o diálogo.
    popup = tela.popup()
    popup.ver_texto('Lista de Emails')
    _anotar('comissao-emails', popup)
    capturar(tela.pagina, 'comissao-emails')


def test_09_responder_como_publico_externo(page, base_url, nomes, capturar):
    """Fluxo público — sociedade civil responde pelo link, **sem conta no SUAP**.

    Usa ``page`` cru (sem ``logado``) de propósito: o que se afirma aqui é que o link funciona
    para quem não tem sessão. O reCAPTCHA não atrapalha — ``ReCaptchaField.validate``
    (``djtools/forms/fields/captcha.py:60``) devolve ``True`` sob teste.
    """
    from avaliacao_integrada.models import Avaliacao, Respondente

    avaliacao = Avaliacao.objects.get(nome=nomes.avaliacao)
    token = Avaliacao.gerar_token(avaliacao.pk)
    email = f'participante.{avaliacao.pk}@example.org'

    tela = Tela(page).ir(f'{base_url}{URL_AVALIACAO_EXTERNA.format(token)}')
    tela.ver_titulo(f'Acessar {avaliacao.nome}')
    _anotar('externa-identificacao', tela)
    capturar(tela.pagina, 'externa-identificacao')

    def _identificar_se() -> None:
        """O formulário de identificação, do jeito que quem está de fora o preenche."""
        tela.ir(f'{base_url}{URL_AVALIACAO_EXTERNA.format(token)}')
        tela.preencher('Tipo do Respondente', 'lista', 'OUTRO_SOCIEDADE_CIVIL')
        tela.preencher('E-mail', 'texto', email)
        tela.clicar_botao('Acessar')
        # Duas navegações em sequência (o `httprr` do form + a página do questionário): sem
        # esperar a URL final, o `_anotar` cai num contexto de execução já destruído.
        tela.pagina.wait_for_url('**/avaliacao_externa/**/*/', timeout=30000)
        tela.esperar()

    # 1ª identificação. **Medido**: devolve "Erro no Sistema" — `montar_formulario`
    # (`views.py:380`) cria o respondente com `Respondente.get_or_create(...)` mas DESCARTA o
    # retorno, então `respondente` continua `None` e `finalizado = respondente.finalizado`
    # (`views.py:516`) estoura em AttributeError. O respondente, porém, fica gravado.
    _identificar_se()
    respondentes = Respondente.objects.filter(avaliacao=avaliacao, dados_usuario_externo__email=email)
    assert respondentes.exists(), 'o acesso pelo link deveria criar o respondente da sociedade civil'
    _anotar('externa-primeiro-acesso', tela)

    # 2ª identificação, com o mesmo e-mail: agora o respondente é encontrado e o questionário
    # abre. É esta a tela que a doc mostra.
    _identificar_se()
    tela.ver_titulo(avaliacao.nome)
    tela.ver_texto('Perfil OUTRO_SOCIEDADE_CIVIL')
    _anotar('externa-questionario', tela)
    capturar(tela.pagina, 'externa-questionario')

    grupos = _responder_todos_os_radios(tela)
    assert grupos, 'o questionário externo abriu sem nenhuma pergunta de escala Likert'
    tela.clicar_botao('Salvar e Continuar')
    tela.esperar()

    from avaliacao_integrada.models import Resposta

    assert Resposta.objects.filter(respondente__in=respondentes).exists(), 'a UI disse que salvou, mas nenhuma resposta externa persistiu'
    _anotar('externa-respondido', tela)
    capturar(tela.pagina, 'externa-respondido')


def test_10_telas_de_apoio(logado_doc):
    """As duas telas que a doc lista como *telas de apoio* — abertas para não serem alegação.

    Sem captura e sem passo a passo, que é o que a anatomia da doc de usuário manda para
    tabela de apoio. O que se afirma aqui é só que elas existem, abrem para o Administrador e
    se chamam o que a doc diz que se chamam.
    """
    tela = Tela(logado_doc('administrador'))
    tela.ir(ADMIN_SEGMENTO).ver_titulo('Segmentos Respondentes')
    # O cadastro de segmentos não tem "Adicionar": os 14 são fixos, referenciados por id no
    # código (`Segmento.DOCENTE` e companhia), e o `permissions.yaml` não concede `delete`.
    tela.ir(ADMIN_ESCALA).ver_titulo('Escalas Likert')
    tela.ver_botao('Adicionar Escala Likert')
