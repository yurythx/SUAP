"""Roteiro navegado das tarefas do ``erros`` — a fonte de ``erros/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas dos
e2e (título, botão, mensagem de sucesso, efeito no banco) e existem para a rodada falhar alto
quando a tela mudou de forma.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

Duas restrições herdadas do conftest dos e2e e que valem aqui igual:

* **nenhum teste pode reportar erro sobre ``VIEW_ABERTURA``** além de ``test_reportar_erro``:
  a tela de abertura decide entre o formulário e a lista de similares olhando se já existe
  erro não finalizado naquela view (``erros/views.py:238-243``), e um erro deixado para trás
  mandaria a captura do formulário para o outro ramo em silêncio. Por isso a captura dos
  similares é feita sobre ``VIEW_ORM``, que é onde as fixturas criam os erros;
* **as asserções são por chave própria e por delta**, nunca por contagem global: o CI roda
  ``pytest -m doc`` inteiro num banco só, compartilhado entre módulos e sem flush entre testes.
"""

from __future__ import annotations

import base64
import sys
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AREAS = '/erros/areas/'
LISTAGEM = '/admin/erros/erro/'
URL_ERRO = '/erros/erro/{}/'
URL_REPORTAR = '/erros/reportar_erro/'
URL_POR_CHAMADO = '/erros/reportar_erro_por_chamado/{}/'

DESCRICAO_LABEL = 'Descreva a operação que você estava realizando antes de ocorrer o erro e a mensagem de erro que o sistema apresentou'
DESCRICAO_LABEL_CHAMADO = 'Descreva a operação que você estava realizando antes de ocorrer o erro'

# A página em que os erros de fixtura moram (`VIEW_ORM` do conftest dos e2e).
PAGINA_DOS_ERROS_DE_FIXTURE = '/comum/temas/'
# Página real e diferente das outras duas: destino da correção de URL feita pelo atendente.
NOVA_URL = 'http://localhost:8000/comum/acessibilidade/'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}\n'
    )


def _aceitar_confirmacao(tela: Tela) -> None:
    """Aceita o ``confirm()`` nativo que o SUAP põe em links ``.confirm``/``.btn.danger``.

    ``comum/static/comum/js/main.js:458`` intercepta o clique e chama ``confirm()``; o
    Playwright **dispensa** diálogo por padrão, então sem isto o clique é cancelado e o teste
    falha afirmando que a ação não aconteceu. Uma linha no teste em vez de um método novo na
    camada ``Tela``: é o único ponto do módulo que precisa disso.
    """
    tela.pagina.on('dialog', lambda dialogo: dialogo.accept())


def test_reportar_erro(logado_erros, capturar):
    """Tarefa 1 — o usuário reporta, da própria página, o erro que acabou de encontrar."""
    from erros.models import Erro

    tela = Tela(logado_erros('interessado')).ir('/')
    tela.clicar_link('Reportar erro')
    tela.ver_titulo('Reportar Erro no SUAP')
    # Âncora do ramo certo: com erro aberto para a mesma view a tela tem o MESMO título e
    # mostra os similares — a captura sairia da tela errada sem estourar nada.
    tela.ver_texto('Instruções para Abertura de Erro')
    _anotar('reportar-passo-1', tela)
    capturar(tela.pagina, 'reportar-instrucoes')

    tela.preencher_formulario(
        [
            ('Li as instruções', 'checkbox', 'marcar'),
            ('Concordo em compartilhar meus dados', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Continuar')

    descricao = f'O quadro de erros não está sendo exibido. (doc {uuid4().hex[:8]})'
    _anotar('reportar-passo-2', tela)
    tela.preencher(DESCRICAO_LABEL, 'textarea', descricao)
    capturar(tela.pagina, 'reportar-descricao')
    tela.clicar_botao('Finalizar')

    tela.sucesso('Erro reportado com sucesso.')
    erro = Erro.objects.filter(descricao=descricao).first()
    assert erro is not None, 'a UI disse que reportou, mas não persistiu'
    assert erro.view == 'comum.views.index', f'o erro deveria apontar para a view da página de origem, veio {erro.view!r}'
    assert erro.interessadoerro_set.filter(vinculo=erro.informante, ativo=True).exists(), 'quem reporta tem de nascer interessado no próprio erro'
    tela.ver_titulo(f'Erro {erro.pk}: {erro.modulo_afetado_display}')
    _anotar('erro-recem-reportado', tela)
    capturar(tela.pagina, 'erro-reportado')

    # O cartão da tela inicial é onde o informante reencontra o que reportou; a doc afirma
    # que ele existe, então esta rodada o executa.
    tela.ir('/')
    tela.ver_texto('Aguardando resolução')
    capturar(tela.pagina, 'inicio-quadro-erros')


def test_reportar_erro_ja_reportado_mostra_similares(logado_erros, vinculos_erros, erro_aberto, capturar):
    """Tarefa 1, desvio — a tela troca o formulário pela lista de similares e oferece o interesse.

    Executado com o ``atendente_auxiliar`` (que não informou nada) porque é o caso geral: quem
    chega a uma página já reportada por **outra** pessoa. O informante veria a outra lista
    ("já foi reportado por você").
    """
    from erros.models import InteressadoErro

    auxiliar = vinculos_erros['atendente_auxiliar']
    caminho = base64.b64encode(PAGINA_DOS_ERROS_DE_FIXTURE.encode()).decode()
    tela = Tela(logado_erros('atendente_auxiliar')).ir(f'{URL_REPORTAR}?url={caminho}')

    tela.ver_titulo('Reportar Erro no SUAP')
    tela.ver_texto('Verifique abaixo se este erro foi reportado por outros usuários')
    tela.ver_botao('Não encontrei erro similar. Desejo reportar um novo erro.')
    _anotar('reportar-similares', tela)
    capturar(tela.pagina, 'reportar-similares')

    # "Tornar-se Interessado" vive no próprio cartão do erro similar
    # (`erros/templates/includes/erro.html`), que é o que evita a duplicata.
    tela.ir(URL_ERRO.format(erro_aberto.pk))
    tela.clicar_botao('Tornar-se interessado')

    tela.sucesso('Você agora é um Interessado deste erro.')
    assert InteressadoErro.objects.filter(erro=erro_aberto, vinculo=auxiliar, ativo=True).exists(), (
        'a UI disse que registrou, mas o interesse não persistiu'
    )


def test_encontrar_erros_por_area_e_modulo(logado_erros, erro_aberto, capturar):
    """Tarefa 2 — achar erros já reportados: área → módulo → listagem com abas por situação."""
    tela = Tela(logado_erros('interessado')).ir(AREAS)
    tela.ver_titulo('Erros')
    _anotar('areas', tela)
    capturar(tela.pagina, 'areas')

    tela.clicar_link('Comum')
    tela.ver_titulo('Área Comum')
    tela.ver_texto('Comum')
    _anotar('modulos', tela)
    capturar(tela.pagina, 'modulos')

    tela.clicar_link('Comum')
    tela.ver_titulo('Erros')
    _anotar('listagem', tela)
    capturar(tela.pagina, 'listagem')

    # A listagem é o destino do menu: as abas por situação são o que o leitor usa para
    # filtrar, então a doc as nomeia e a rodada confirma que existem. `botoes_na_tela` não
    # serve — as abas são `a.nav-link` dentro de `ul.nav-tabs`
    # (`djtools/templates/admin/tablistfilter.html`), sem a classe `btn`.
    abas = [texto.strip() for texto in tela.pagina.locator('//ul[contains(@class, "nav-tabs")]//a').all_inner_texts()]
    for aba in ('Reportados', 'Em análise', 'Em correção', 'Aguardando feedback', 'Resolvidos', 'Cancelados', 'Todos'):
        assert any(aba in rotulo for rotulo in abas), f'a aba {aba!r} sumiu da listagem. Abas: {abas}'

    tela.clicar_aba('Em análise')
    tela.esperar()
    assert 'tab=tab_em_andamento' in tela.pagina.url, f'a aba deveria filtrar a listagem, URL veio {tela.pagina.url!r}'

    tela.ir(f'{LISTAGEM}?modulo_afetado=comum')
    tela.linha(erro_aberto.url).clicar_link('Visualizar')
    tela.ver_titulo(f'Erro {erro_aberto.pk}: {erro_aberto.modulo_afetado_display}')


def test_acompanhar_erro_comentando_e_anexando(logado_erros, erro_aberto, capturar):
    """Tarefa 3 — o interessado comenta na linha do tempo e anexa um arquivo."""
    from erros.models import AnexoErro, HistoricoComentarioErro

    tela = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro_aberto.pk))
    texto = f'O problema acontece também ao filtrar por campus. (doc {uuid4().hex[:8]})'
    _anotar('erro-interessado', tela)
    capturar(tela.pagina, 'erro-interessado')

    tela.preencher_textarea('Adicionar interação', texto)
    tela.clicar_botao('Adicionar interação')

    tela.sucesso('Comentário cadastrado com sucesso.')
    tela.ver_texto(texto)
    assert HistoricoComentarioErro.objects.filter(erro=erro_aberto, descricao=texto).exists(), (
        'a UI disse que cadastrou, mas o comentário não persistiu'
    )
    capturar(tela.pagina, 'linha-do-tempo')

    tela.clicar_aba('Anexos')
    tela.aba('Anexos').ver_texto('Nenhum anexo cadastrado.')
    tela.clicar_botao('Adicionar anexo')
    popup = tela.popup()
    popup.ver_texto(f'Adicionar anexo ao Erro {erro_aberto.pk}')
    _anotar('anexo-formulario', popup)
    capturar(tela.pagina, 'anexo-formulario')

    descricao = f'Print da tela com o erro (doc {uuid4().hex[:8]})'
    popup.preencher_formulario([('Descrição', 'texto', descricao), ('Arquivo', 'arquivo', 'arquivo.jpg')])
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Anexo adicionado com sucesso.')
    assert AnexoErro.objects.filter(erro=erro_aberto, descricao=descricao).exists(), 'a UI disse que anexou, mas não persistiu'


def test_responder_pedido_de_feedback(logado_erros, erro_aguardando_feedback, capturar):
    """Tarefa 3, etapa 2 — o interessado responde ao atendente que pediu mais informação."""
    from erros.models import Erro

    erro = erro_aguardando_feedback
    tela = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro.pk))
    tela.ver_texto('Enviar feedback')
    tela.ver_texto('O erro ainda não foi resolvido')
    _anotar('feedback', tela)
    capturar(tela.pagina, 'feedback')

    resposta = f'Continua acontecendo depois da última atualização. (doc {uuid4().hex[:8]})'
    tela.preencher_textarea('Adicionar interação', resposta)
    # O rótulo é o texto do próprio rádio (`erros/forms.py:171-174`); o `<label>` do campo não
    # é renderizado (a aba monta o formulário à mão), então o alvo é o input pelo valor.
    tela.pagina.locator(f'input[name="situacao"][value="{Erro.SITUACAO_EM_ANALISE}"]').first.check()
    tela.clicar_botao('Adicionar interação')

    tela.sucesso('Situação alterada com sucesso.')
    erro.refresh_from_db()
    assert erro.situacao == Erro.SITUACAO_EM_ANALISE, f'responder o feedback deveria devolver o erro à análise, veio {erro.get_situacao_display()!r}'


def test_reabrir_erro_resolvido(logado_erros, erro_resolvido, capturar):
    """Tarefa 3, etapa 3 — o informante reabre o erro que voltou a acontecer."""
    from erros.models import Erro

    erro = erro_resolvido
    tela = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro.pk))
    tela.ver_botao('O erro persiste?')
    _anotar('erro-resolvido', tela)
    capturar(tela.pagina, 'erro-resolvido')

    _aceitar_confirmacao(tela)
    tela.clicar_botao('O erro persiste?')
    popup = tela.popup()
    popup.ver_texto('Criar Atualização')
    motivo = f'O erro voltou a acontecer nesta semana. (doc {uuid4().hex[:8]})'
    popup.preencher('Motivo', 'textarea', motivo)
    capturar(tela.pagina, 'reabrir-motivo')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Situação alterada com sucesso.')
    erro.refresh_from_db()
    assert erro.situacao == Erro.SITUACAO_REABERTO, f'a UI disse que reabriu, mas a situação é {erro.get_situacao_display()!r}'


def test_atender_erro(logado_erros, vinculos_erros, erro_aberto, capturar):
    """Tarefa 4 — o analista assume, acompanha, registra a atualização e resolve.

    Uma tarefa só, e não uma por tela: ninguém assume um erro sem pretender fechá-lo. As
    etapas são as da doc, na ordem em que ela as apresenta.
    """
    from erros.models import Erro, HistoricoComentarioErro, RespostaFrequente

    erro = erro_aberto
    # A resposta frequente é a única tela de apoio do módulo, e o efeito dela é aparecer como
    # "Resposta padrão" na caixa de interação de quem atende (`erros/templates/abas/
    # comentarios.html:20-30`). `get_or_create` porque a suíte não dá flush.
    RespostaFrequente.objects.get_or_create(
        atendente=vinculos_erros['atendente'].user, texto='Estamos analisando; assim que houver novidade, avisaremos por aqui.'
    )

    tela = Tela(logado_erros('atendente')).ir(URL_ERRO.format(erro.pk))
    tela.ver_botao('Assumir')
    _anotar('erro-atendente', tela)
    capturar(tela.pagina, 'erro-atendente')

    tela.clicar_botao('Assumir')
    tela.sucesso('Você agora é o Atendente Principal deste erro.')
    tela.ver_status('Em análise')
    erro.refresh_from_db()
    assert erro.situacao == Erro.SITUACAO_EM_ANALISE, 'assumir deveria mover a situação para Em análise'
    assert erro.atendente_atual is not None, 'a UI disse que assumiu, mas o atendente atual não mudou'
    capturar(tela.pagina, 'erro-em-analise')

    tela.ver_texto('Resposta padrão')

    # Nota interna: visível só para quem atende (`pode_ver_nota_interna`).
    nota = f'Reproduzido em homologação; parece regressão do último deploy. (doc {uuid4().hex[:8]})'
    tela.clicar_aba('Notas Internas')
    tela.preencher_textarea('Adicionar Nota interna', nota)
    capturar(tela.pagina, 'nota-interna')
    tela.clicar_botao('Adicionar Nota interna')
    tela.sucesso('Comentário cadastrado com sucesso.')
    assert HistoricoComentarioErro.objects.filter(erro=erro, descricao=nota, tipo=HistoricoComentarioErro.TIPO_NOTA_INTERNA).exists(), (
        'a UI disse que cadastrou, mas a nota interna não persistiu'
    )

    # Corrigir a URL: é ela que define o módulo afetado e a triagem de duplicidade.
    tela.ir(URL_ERRO.format(erro.pk))
    tela.clicar_botao('Opções')
    _anotar('opcoes-atendente', tela)
    capturar(tela.pagina, 'opcoes-atendente')
    tela.clicar_botao('Editar URL do Erro')
    popup = tela.popup()
    popup.ver_texto(f'Alterar URL do Erro {erro.pk}')
    popup.preencher('Nova URL do Erro', 'texto', NOVA_URL)
    popup.salvar_no_popup('Enviar')
    tela.sucesso('URL do erro alterada com sucesso.')
    erro.refresh_from_db()
    assert erro.url == NOVA_URL, 'a UI disse que alterou, mas a URL não persistiu'

    tela.clicar_botao('Alterar situação')
    tela.clicar_botao('Em correção')
    tela.sucesso('Situação alterada com sucesso.')
    tela.ver_status('Em correção')

    # A atualização é a nota de versão que o SUAP mostra a todos os usuários; ela só é
    # publicada quando o erro vai para "Resolvido" (`erros/models.py:358`).
    tela.clicar_aba('Atualização')
    tela.aba('Atualização').ver_texto('Não há atualização informada.')
    tela.aba('Atualização').clicar_botao('Editar')
    popup = tela.popup()
    popup.ver_texto('Atualização')
    _anotar('atualizacao-formulario', popup)
    capturar(tela.pagina, 'atualizacao-formulario')
    titulo = f'Correção do quadro de erros (doc {uuid4().hex[:8]})'
    popup.preencher_formulario(
        [
            ('Título', 'texto', titulo),
            ('Tipo', 'lista', 'Bug'),
            ('Grupos Envolvidos', 'autocomplete multiplo', 'Analista'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atualização editada com sucesso.')

    tela.clicar_botao('Alterar situação')
    tela.clicar_botao('Resolvido')
    popup = tela.popup()
    popup.ver_texto('Atualização')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Situação alterada com sucesso.')
    erro.refresh_from_db()
    assert erro.situacao == Erro.SITUACAO_RESOLVIDO, f'a UI disse que resolveu, mas a situação é {erro.get_situacao_display()!r}'
    assert erro.atualizacao is not None, 'resolver deveria publicar a atualização (a nota de versão)'
    capturar(tela.pagina, 'erro-resolvido-atendente')


def test_triar_erros(logado_erros, vinculos_erros, erro_aberto, erro_em_analise, capturar):
    """Tarefa 5 — o Recebedor de Demandas atribui o erro a um analista e unifica duplicatas."""
    from erros.models import Erro, HistoricoComentarioErro

    atendente = vinculos_erros['atendente']
    tela = Tela(logado_erros('gerente')).ir(URL_ERRO.format(erro_aberto.pk))
    tela.clicar_botao('Opções')
    tela.ver_botao('Atribuir atendente')
    _anotar('opcoes-gerente', tela)
    capturar(tela.pagina, 'opcoes-gerente')

    tela.clicar_botao('Atribuir atendente')
    popup = tela.popup()
    popup.ver_texto('Atribuir Atendente')
    _anotar('atribuir-formulario', popup)
    capturar(tela.pagina, 'atribuir-formulario')
    # A busca é pela matrícula, que o `SearchField` de Vinculo indexa (`comum/models.py:680`).
    popup.preencher('Atendente', 'autocomplete', atendente.user.username)
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Usuário atribuído com sucesso.')
    erro_aberto.refresh_from_db()
    assert erro_aberto.atendente_atual == atendente, 'a UI disse que atribuiu, mas o atendente atual não mudou'
    assert erro_aberto.situacao == Erro.SITUACAO_EM_ANALISE, 'atribuir deveria tirar o erro de "Reportado"'

    tela.clicar_botao('Opções')
    tela.clicar_botao('Unificar erros')
    popup = tela.popup()
    popup.ver_texto('Unificar erros')
    _anotar('unificar-formulario', popup)
    capturar(tela.pagina, 'unificar-formulario')
    popup.preencher('Erros', 'autocomplete multiplo', erro_em_analise.url, opcao=f'Erro {erro_em_analise.pk}:')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Erros unificados com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.situacao == Erro.SITUACAO_UNIFICADO, 'a UI disse que unificou, mas o erro absorvido não mudou de situação'
    assert HistoricoComentarioErro.objects.filter(erro=erro_aberto, descricao=erro_em_analise.descricao).exists(), (
        'a descrição do erro absorvido deveria virar comentário do principal'
    )


def test_cancelar_erro_de_abertura(logado_doc, erro_aberto):
    """Tarefa 5, etapa 3 — o que não é defeito sai da fila.

    Executado com o ``triador`` (Analista **e** Recebedor de Demandas) e não com o ``gerente``:
    o item aparece no menu para qualquer Recebedor, mas o tratamento do parâmetro está dentro
    do ``if eh_atendente:`` da view (``erros/views.py:328`` e ``:360``). Medido: só Recebedor,
    o clique navega e nada acontece — nem mensagem de erro. A doc registra a exigência dos
    dois papéis; este teste é o que a sustenta.

    Sem captura: a tela é a mesma de ``opcoes-gerente``, só muda o item clicado.
    """
    from erros.models import Erro

    tela = Tela(logado_doc('triador')).ir(URL_ERRO.format(erro_aberto.pk))
    tela.clicar_botao('Opções')
    tela.ver_botao('Cancelar por erro de abertura')

    _aceitar_confirmacao(tela)
    tela.clicar_botao('Cancelar por erro de abertura')

    tela.sucesso('Cancelado por não atender às instruções exibidas na tela de abertura deste Erro.')
    erro_aberto.refresh_from_db()
    assert erro_aberto.situacao == Erro.SITUACAO_CANCELADO, f'a UI disse que cancelou, mas a situação é {erro_aberto.get_situacao_display()!r}'


def test_reportar_erro_a_partir_de_chamado(logado_erros, vinculos_erros, chamado_reclassificavel, capturar):
    """Tarefa 6 — quem atende um chamado percebe que é defeito e o reclassifica em erro."""
    from erros.models import Erro

    descricao = f'Ao abrir a página de acessibilidade o sistema apresentou erro. (doc {uuid4().hex[:8]})'
    tela = Tela(logado_erros('atendente')).ir(URL_POR_CHAMADO.format(chamado_reclassificavel.pk))
    tela.ver_titulo(f'Reportar erro a partir do chamado #{chamado_reclassificavel.pk}')
    _anotar('chamado-formulario', tela)

    tela.preencher_formulario(
        [
            ('URL com Erro', 'texto', NOVA_URL),
            (DESCRICAO_LABEL_CHAMADO, 'textarea', descricao),
        ]
    )
    capturar(tela.pagina, 'chamado-formulario')
    tela.clicar_botao('Enviar')

    tela.sucesso('Erro reportado com sucesso.')
    erro = Erro.objects.filter(descricao=descricao).first()
    assert erro is not None, 'a UI disse que reportou, mas o erro não persistiu'
    assert erro.informante == vinculos_erros['atendente'], 'o erro deveria nascer em nome de quem reclassificou'
    assert erro.interessadoerro_set.filter(vinculo=vinculos_erros['interessado'], ativo=True).exists(), (
        'o interessado do chamado deveria ter sido transferido para o erro'
    )
