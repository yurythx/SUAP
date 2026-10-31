"""Rodada de geração da doc de usuário do módulo ``demandas``.

Cada teste percorre uma tarefa fim-a-fim pelo sistema real e grava as telas que a doc
referencia. As premissas que valem para o arquivo inteiro:

* **O banco é compartilhado e não há flush entre testes** (ver ``_django_db_helper`` em
  ``djtools/e2e_fixtures.py``) — por isso todo título leva um sufixo único e as asserções são
  sobre a própria linha, nunca sobre contagens globais.
* **As tabelas de apoio do módulo** (Áreas de Atuação e Módulos) já existem no seed; a
  demanda criada em cada teste é da área "Tecnologia da Informação" e do módulo "Tag Especial".
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

SENHA = SENHA_E2E
URL_DASHBOARD = '/demandas/demandas/'
URL_AREAS_SUGESTAO = '/demandas/listar_areas_atuacao_sugestao_melhoria/'


# -- helpers -----------------------------------------------------------------------


def _sufixo() -> str:
    return uuid4().hex[:7]


def _preencher_senha(tela: Tela, senha: str = SENHA) -> None:
    """Preenche o campo ``senha`` das confirmações.

    O campo vem do ``PasswordField`` do djtools, que envolve o ``input`` num
    ``div.password-container`` — o rótulo não é irmão do campo, então o preenchimento por
    rótulo do harness não o encontra.
    """
    tela.pagina.locator('input[name="senha"]').fill(senha)


def _abrir_demanda(logado_demandas, titulo: str) -> tuple[Tela, str]:
    """Tarefa 1: o demandante abre uma demanda e devolve a tela e a URL da demanda criada."""
    tela = Tela(logado_demandas('demandante'))
    tela.ir(URL_DASHBOARD)
    tela.clicar_botao('Adicionar demanda')
    _preencher_dados_da_demanda(tela, titulo)
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    return tela, tela.pagina.url


def _preencher_dados_da_demanda(tela: Tela, titulo: str) -> None:
    """Preenche o formulário de cadastro da demanda.

    A **Área de Atuação** é escolhida primeiro e a espera é explícita: os **Módulos** são
    recarregados por requisição assíncrona quando a área muda, e marcar o módulo antes de a
    lista chegar faz o formulário voltar com "Este campo é obrigatório" sem dizer qual campo
    (medido: falha intermitente de ~1 em 4 rodadas). As duas asserções trocam essa falha
    tardia por uma no ponto certo.
    """
    tela.preencher('Área de Atuação', 'autocomplete', 'Tecnologia da Informação')
    tela.esperar()
    assert 'Tecnologia da Informação' in tela.pagina.locator('select[name="area"] + span.select2').inner_text()
    tela.preencher_formulario(
        [
            ('Tipo', 'radio', 'Melhoria'),
            ('Módulos', 'checkbox multiplo', 'Tag Especial'),
            ('Título da Demanda', 'texto', titulo),
            ('Descrição da Demanda', 'textarea', 'Descrição da demanda registrada na documentação.'),
            ('Demandantes', 'autocomplete multiplo', 'Demandante'),
        ]
    )
    marcados = tela.pagina.locator('form input[type="checkbox"]:checked').evaluate_all('els => els.map(e => e.closest("label")?.innerText ?? "")')
    assert any('Tag Especial' in texto for texto in marcados), f'o módulo obrigatório não ficou marcado: {marcados}'


def _vincular_analista(tela: Tela, sufixo: str) -> None:
    """O analista se vincula à demanda pela listagem do admin."""
    tela.ir('/admin/demandas/demanda/')
    tela.filtros().preencher('Texto', 'texto', sufixo)
    tela.filtros().clicar_botao('Filtrar')
    tela.clicar_icone('edição')
    tela.preencher_formulario([('Analistas', 'autocomplete multiplo', 'Analista do Demandas')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')


def _alterar_etapa(tela: Tela, etapa: str, dados: list[tuple[str, ...]] | None = None) -> Tela:
    """Abre o menu "Alterar etapa" e escolhe uma das etapas oferecidas."""
    tela.clicar_botao('Alterar etapa')
    tela.clicar_botao(etapa)
    if dados:
        tela.preencher_formulario(dados)
    tela.clicar_botao('Enviar')
    tela.sucesso('A etapa da demanda foi alterada.')
    return tela


def _preencher_atividades(tela: Tela, texto: str) -> None:
    """Preenche o campo de texto rico da especificação e espera o editor assumir o conteúdo.

    ``Tela.preencher(..., 'texto rico')`` cobre o caso comum, mas o editor é montado depois
    do formulário: sob carga a gravação chega antes de o editor existir, o ``textarea`` fica
    preenchido, o editor nasce vazio e o submit envia vazio — o servidor responde "Este campo é
    obrigatório" num campo que a tela mostra preenchido (medido: 2 em 6 rodadas da suíte
    inteira, sempre aqui). Esperar o editor ficar registrado e devolver o ``textarea`` a ele
    fecha a corrida.
    """
    tela.preencher('Atividade(s)', 'texto rico', texto)
    tela.pagina.wait_for_function(
        """() => {
            const ta = document.querySelector('textarea[name="atividades"]');
            if (!ta) return false;
            const tm = ta.ownerDocument.defaultView?.tinymce;
            const editor = tm?.get?.(ta.id) ?? [...(tm?.editors ?? [])].find((e) => e.getElement?.() === ta);
            if (!editor) return false;
            if (!editor.getContent().trim() && ta.value.trim()) editor.setContent(ta.value);
            return !!editor.getContent().trim();
        }""",
        timeout=15000,
    )


def _registrar_consolidacao(tela: Tela, sufixo: str) -> Tela:
    """Tarefa 2: especificação + consolidação, sem mudar a etapa."""
    tela.clicar_botao('Adicionar especificação')
    tela.preencher('Nome', 'texto', f'Especificação {sufixo}')
    _preencher_atividades(tela, 'Alterar a funcionalidade indicada na sugestão.')
    tela.clicar_botao('Salvar')
    tela.sucesso('A especificação foi adicionada.')
    tela.clicar_botao('Editar')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', f'Consolidação da demanda {sufixo}'),
            ('Novos Grupos de Usuários', 'textarea', 'Servidores da área responsável.'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('A demanda foi atualizada.')
    return tela


def _registrar_entrega(analista: Tela, url: str, titulo: str, sufixo: str, capturar=None) -> None:
    """Tarefa 4: o analista registra uma entrega com a especificação da demanda, o que a leva à homologação."""
    analista.ir(url)
    analista.clicar_aba('Entregas')
    analista.aba('Entregas').clicar_botao('Nova entrega')
    popup = analista.popup()
    anotar_tela('formulario-nova-entrega', popup)
    popup.preencher_formulario(
        [
            ('Título da entrega', 'texto', titulo),
            ('O que está sendo entregue', 'textarea', 'Relatório com o filtro solicitado.'),
            ('Notas para o demandante (o que testar, fluxos, dados de exemplo)', 'textarea', 'Gere o relatório filtrando por campus.'),
            ('Prazo para o demandante responder', 'data', '20/12/2030'),
            ('URL para Validação', 'texto', 'http://localhost/'),
        ]
    )
    popup.campo('Especificações entregues', 'checkbox multiplo', f'Especificação {sufixo}').check()
    if capturar:
        capturar(analista.pagina, 'demanda-homologar')
    popup.salvar_no_popup('Salvar')
    analista.sucesso('Entrega registrada. A demanda está em homologação.')


def _demanda_em_analise(logado_demandas, sufixo: str) -> tuple[Tela, Tela, str]:
    """Leva uma demanda nova até "Em análise" e devolve (tela do analista, tela do demandante, url)."""
    _, url = _abrir_demanda(logado_demandas, f'Demanda {sufixo}')
    analista = Tela(logado_demandas('analista'))
    _vincular_analista(analista, sufixo)
    analista.ir(url)
    _alterar_etapa(analista, 'Negociar')
    _registrar_consolidacao(analista, sufixo)
    _alterar_etapa(analista, 'Analisar', [('Comentário', 'textarea', 'Consolidação encaminhada para análise.'), ('Previsão', 'data', '20/12/2030')])
    return analista, Tela(logado_demandas('demandante')), url


def _sugestao_aberta(logado_demandas, titulo: str) -> Tela:
    """Tarefa 6: um servidor abre uma sugestão de melhoria."""
    servidor = Tela(logado_demandas('servidor'))
    servidor.ir(URL_AREAS_SUGESTAO)
    servidor.clicar_link('Tag Especial')
    servidor.clicar_botao('Adicionar Sugestão')
    servidor.preencher_formulario(
        [
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Sugiro alterar a funcionalidade nos seguintes aspectos.'),
        ]
    )
    servidor.clicar_botao('Salvar')
    servidor.sucesso('Sugestão de Melhoria salva com sucesso.')
    return servidor


# -- tarefas -----------------------------------------------------------------------


def test_abrir_demanda(logado_demandas, capturar):
    """Tarefa 1: o demandante abre uma demanda."""
    sufixo = _sufixo()
    tela = Tela(logado_demandas('demandante'))
    tela.ir(URL_DASHBOARD)
    anotar_tela('dashboard', tela)
    tela.ver_item_de_menu('Tec. da Informação::Desenvolvimento::Demandas')
    capturar(tela.pagina, 'dashboard-demandas')

    tela.clicar_botao('Adicionar demanda')
    anotar_tela('formulario-nova-demanda', tela)
    _preencher_dados_da_demanda(tela, f'Demanda {sufixo}')
    capturar(tela.pagina, 'formulario-nova-demanda')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    tela.ver_status('Solicitada')
    capturar(tela.pagina, 'demanda-aberta')


def test_registrar_consolidacao(logado_demandas, capturar):
    """Tarefa 2: o analista assume a demanda, registra a consolidação e a encaminha para análise."""
    sufixo = _sufixo()
    _, url = _abrir_demanda(logado_demandas, f'Demanda {sufixo}')
    analista = Tela(logado_demandas('analista'))

    analista.ir('/admin/demandas/demanda/')
    analista.filtros().preencher('Texto', 'texto', sufixo)
    analista.filtros().clicar_botao('Filtrar')
    analista.clicar_icone('edição')
    anotar_tela('editar-analistas', analista)
    analista.preencher_formulario([('Analistas', 'autocomplete multiplo', 'Analista do Demandas')])
    capturar(analista.pagina, 'demanda-editar-analistas')
    analista.clicar_botao('Salvar')
    analista.sucesso('Atualização realizada com sucesso.')

    analista.ir(url)
    _alterar_etapa(analista, 'Negociar')

    # Sem consolidação registrada a demanda não avança para Em análise — a própria tela
    # devolve o aviso.
    analista.clicar_botao('Alterar etapa')
    analista.clicar_botao('Analisar')
    analista.erro('Não é possível alterar uma demanda para Em Análise caso ela não tenha Consolidação')

    analista.clicar_botao('Adicionar especificação')
    anotar_tela('formulario-especificacao', analista)
    analista.preencher('Nome', 'texto', f'Especificação {sufixo}')
    _preencher_atividades(analista, 'Alterar a funcionalidade indicada na sugestão.')
    capturar(analista.pagina, 'demanda-especificacao')
    analista.clicar_botao('Salvar')
    analista.sucesso('A especificação foi adicionada.')

    analista.clicar_botao('Editar')
    anotar_tela('formulario-consolidacao', analista)
    analista.preencher_formulario(
        [
            ('Descrição', 'texto', f'Consolidação da demanda {sufixo}'),
            ('Novos Grupos de Usuários', 'textarea', 'Servidores da área responsável.'),
        ]
    )
    capturar(analista.pagina, 'demanda-consolidacao')
    analista.clicar_botao('Salvar')
    analista.sucesso('A demanda foi atualizada.')

    analista.clicar_aba('Consolidação')
    analista.clicar_botao('Alterar etapa')
    analista.clicar_botao('Analisar')
    anotar_tela('formulario-analisar', analista)
    analista.preencher_formulario([('Comentário', 'textarea', 'Consolidação encaminhada para análise.'), ('Previsão', 'data', '20/12/2030')])
    capturar(analista.pagina, 'demanda-analisar')
    analista.clicar_botao('Enviar')
    analista.sucesso('A etapa da demanda foi alterada.')
    analista.ver_status('Em análise')


def test_aprovar_e_reprovar_consolidacao(logado_demandas, capturar):
    """Tarefa 3: o demandante reprova e depois aprova a consolidação."""
    sufixo = _sufixo()
    analista, demandante, url = _demanda_em_analise(logado_demandas, sufixo)

    demandante.ir(url)
    demandante.clicar_aba('Consolidação')
    anotar_tela('demanda-em-analise', demandante)
    capturar(demandante.pagina, 'demanda-em-analise')
    demandante.clicar_botao('Reprovar')
    anotar_tela('formulario-reprovar', demandante)
    demandante.preencher_formulario([('Confirma a operação', 'checkbox', 'Marcar')])
    _preencher_senha(demandante)
    capturar(demandante.pagina, 'demanda-reprovar')
    demandante.clicar_botao('Enviar')
    demandante.sucesso('A consolidação da demanda foi reprovada.')
    demandante.ver_status('Em negociação')

    # A tela do analista é anterior à reprovação: recarrega antes de reencaminhar.
    analista.ir(url)
    _alterar_etapa(analista, 'Analisar', [('Comentário', 'textarea', 'Consolidação reenviada para análise.'), ('Previsão', 'data', '20/12/2030')])
    analista.ver_status('Em análise')

    demandante.ir(url)
    demandante.clicar_aba('Consolidação')
    demandante.clicar_botao('Aprovar')
    anotar_tela('formulario-aprovar', demandante)
    demandante.preencher_formulario([('Confirma a operação', 'checkbox', 'Marcar')])
    _preencher_senha(demandante)
    demandante.clicar_botao('Enviar')
    demandante.sucesso('A consolidação da demanda foi aprovada.')
    demandante.ver_status('Aprovada')


def test_conduzir_demanda_ate_a_conclusao(logado_demandas, capturar):
    """Tarefas 4 e 5: o analista conduz a demanda e registra entregas; o demandante as valida."""
    sufixo = _sufixo()
    analista, demandante, url = _demanda_em_analise(logado_demandas, sufixo)
    demandante.ir(url)
    demandante.clicar_aba('Consolidação')
    demandante.clicar_botao('Aprovar')
    demandante.preencher_formulario([('Confirma a operação', 'checkbox', 'Marcar')])
    _preencher_senha(demandante)
    demandante.clicar_botao('Enviar')
    demandante.sucesso('A consolidação da demanda foi aprovada.')

    analista.ir(url)
    _alterar_etapa(analista, 'Desenvolver', [('Comentário', 'textarea', 'Desenvolvimento iniciado.'), ('Previsão', 'data', '20/12/2030')])
    analista.ver_status('Em desenvolvimento')

    analista.clicar_botao('Alterar etapa')
    # O menu de etapas também oferece suspender e encerrar; homologar não está lá: é a entrega que leva a demanda à homologação.
    for opcao in ('Suspender', 'Cancelar'):
        expect(analista.pagina.locator(f'//a[normalize-space(.) = "{opcao}"]').first).to_be_attached()
    expect(analista.pagina.locator('//a[normalize-space(.) = "Homologar"]')).to_have_count(0)

    _registrar_entrega(analista, url, f'Primeira entrega {sufixo}', sufixo, capturar=capturar)
    analista.ver_status('Em homologação')

    # O demandante reprova a entrega e a demanda volta para o desenvolvimento.
    demandante.ir(url)
    demandante.ver_status('Em homologação').clicar_aba('Entregas')
    anotar_tela('demanda-em-homologacao', demandante)
    capturar(demandante.pagina, 'demanda-em-homologacao')
    demandante.aba('Entregas').clicar_botao('Reprovar')
    popup = demandante.popup()
    anotar_tela('formulario-reprovar-entrega', popup)
    popup.preencher('Motivo da reprovação', 'textarea', 'O relatório não traz o filtro por campus.')
    popup.salvar_no_popup('Enviar')
    demandante.sucesso('Entrega reprovada. Demanda retornou para desenvolvimento.')
    demandante.ver_status('Em desenvolvimento')

    # Nova entrega com a correção; o demandante aprova e, com todas as especificações aprovadas, a demanda fica Homologada.
    _registrar_entrega(analista, url, f'Entrega corrigida {sufixo}', sufixo)
    demandante.ir(url)
    demandante.clicar_aba('Entregas')
    demandante.aba('Entregas').clicar_botao('Aprovar')
    popup = demandante.popup()
    anotar_tela('formulario-aprovar-entrega', popup)
    capturar(demandante.pagina, 'demanda-aprovar-homologacao')
    popup.salvar_no_popup('Enviar')
    demandante.sucesso('Entrega aprovada. A demanda está "Homologada".')
    demandante.ver_status('Homologada')

    analista.ir(url)
    _alterar_etapa(analista, 'Implantar', [('Comentário', 'textarea', 'Demanda em implantação.'), ('Previsão', 'data', '20/12/2030')])
    analista.ver_status('Em implantação')

    analista.clicar_botao('Alterar etapa')
    anotar_tela('alterar-etapa-implantacao', analista)
    analista.clicar_botao('Concluir')
    analista.preencher_formulario([('Comentário', 'textarea', 'Demanda concluída.'), ('Conclusão', 'data', '20/12/2030')])
    analista.clicar_botao('Enviar')
    analista.sucesso('A etapa da demanda foi alterada.')
    analista.ver_status('Concluída')
    capturar(analista.pagina, 'demanda-concluida')


def test_sugerir_melhoria(logado_demandas, capturar):
    """Tarefa 6: um servidor abre uma sugestão de melhoria para um módulo."""
    sufixo = _sufixo()
    tela = Tela(logado_demandas('servidor'))
    tela.ir(URL_AREAS_SUGESTAO)
    anotar_tela('areas-sugestao', tela)
    tela.ver_item_de_menu('Tec. da Informação::Desenvolvimento::Sugestões de melhorias')
    capturar(tela.pagina, 'sugestoes-areas')

    tela.clicar_link('Tag Especial')
    anotar_tela('sugestoes-modulo', tela)
    tela.clicar_botao('Adicionar Sugestão')
    anotar_tela('formulario-sugestao', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', f'Melhoria {sufixo}'),
            ('Descrição', 'textarea', 'Sugiro alterar a funcionalidade nos seguintes aspectos.'),
        ]
    )
    capturar(tela.pagina, 'sugestao-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Sugestão de Melhoria salva com sucesso.')
    anotar_tela('sugestao-detalhe', tela)
    capturar(tela.pagina, 'sugestao-detalhe')


def test_concordar_e_discordar_de_sugestao(logado_demandas, capturar):
    """Tarefa 7: outros usuários votam na sugestão."""
    sufixo = _sufixo()
    titulo = f'Melhoria {sufixo}'
    _sugestao_aberta(logado_demandas, titulo)

    # O cartão é recortado pelo título: a listagem do módulo acumula as sugestões de todos
    # os testes da sessão, e o botão solto votaria na primeira delas.
    segundo = Tela(logado_demandas('servidor2'))
    segundo.ir(URL_AREAS_SUGESTAO)
    segundo.clicar_link('Tag Especial')
    anotar_tela('sugestoes-com-voto', segundo)
    segundo.cartao(titulo).clicar_botao('Concordar com a sugestão')
    segundo.esperar()
    segundo.pagina.locator('p#feedback_message', has_text='Voto cadastrado com sucesso.').wait_for()
    capturar(segundo.pagina, 'sugestao-concordar')

    demandante = Tela(logado_demandas('demandante'))
    demandante.ir(URL_AREAS_SUGESTAO)
    demandante.clicar_link('Tag Especial')
    demandante.cartao(titulo).clicar_botao('Discordar da sugestão')
    demandante.esperar()
    demandante.pagina.locator('p#feedback_message', has_text='Voto cadastrado com sucesso.').wait_for()
    anotar_tela('sugestao-votos', demandante)


def test_transformar_sugestao_em_demanda(logado_demandas, capturar):
    """Tarefa 8: o demandante assume a sugestão, defere e gera a demanda."""
    sufixo = _sufixo()
    titulo = f'Melhoria {sufixo}'
    _sugestao_aberta(logado_demandas, titulo)

    demandante = Tela(logado_demandas('demandante'))
    demandante.ir('/admin/demandas/sugestaomelhoria/')
    anotar_tela('sugestoes-admin', demandante)
    demandante.filtros().preencher('Texto', 'texto', sufixo)
    demandante.filtros().clicar_botao('Filtrar')
    demandante.clicar_icone('exibição')
    demandante.esperar()
    demandante = Tela(demandante.pagina).esperar()
    demandante.clicar_botao('Atribuir-se como Responsável')
    demandante.esperar()
    demandante.pagina.locator('p#feedback_message', has_text='Responsável definido com sucesso.').wait_for()
    demandante.loc('//span[contains(@class, "status") and normalize-space(.) = "Em análise"]').first.wait_for()

    demandante.clicar_botao('Editar')
    anotar_tela('sugestao-editar', demandante)
    demandante.preencher_formulario([('Situação', 'lista', 'Deferida')])
    capturar(demandante.pagina, 'sugestao-deferir')
    demandante.clicar_botao('Salvar')
    demandante.sucesso('Sugestão de Melhoria salva com sucesso.')

    demandante.clicar_botao('Gerar Demanda')
    anotar_tela('formulario-gerar-demanda', demandante)
    capturar(demandante.pagina, 'sugestao-gerar-demanda')
    demandante.clicar_botao('Salvar')
    demandante.sucesso('Demanda gerada com sucesso.')
    capturar(demandante.pagina, 'demanda-gerada-da-sugestao')


def test_definir_publicos_da_area_de_atuacao(logado_demandas, capturar):
    """Tarefa 9: o coordenador de TI define quem pode sugerir melhorias na área."""
    ti = Tela(logado_demandas('ti'))
    ti.ir('/admin/demandas/areaatuacaodemanda/')
    anotar_tela('areas-de-atuacao', ti)
    capturar(ti.pagina, 'areas-de-atuacao')
    ti.clicar_icone('edição')
    # A URL da área é lida da tela: o banco é compartilhado entre os módulos da rodada e o
    # identificador não é necessariamente 1.
    url_area = ti.pagina.url
    anotar_tela('area-editar', ti)
    ti.preencher_formulario(
        [
            ('Recebe sugestões de melhorias de Alunos?', 'checkbox', 'Marcar'),
            ('Recebe sugestões de melhorias de Servidores?', 'checkbox', 'Desmarcar'),
            ('Recebe sugestões de melhorias de Prestadores de Serviço?', 'checkbox', 'Marcar'),
        ]
    )
    capturar(ti.pagina, 'area-publicos')
    ti.clicar_botao('Salvar')
    ti.sucesso('Atualização realizada com sucesso.')

    # Com o público Servidores desmarcado, a área sai da lista de sugestões de um servidor.
    servidor = Tela(logado_demandas('servidor'))
    servidor.ir(URL_AREAS_SUGESTAO)
    servidor.ver_texto('Nenhuma área de atuação disponível.')
    capturar(servidor.pagina, 'sugestoes-sem-area')

    # Devolve a área ao estado inicial: o seed é da sessão e os outros testes dependem dele.
    ti.ir(url_area)
    ti.preencher_formulario(
        [
            ('Recebe sugestões de melhorias de Alunos?', 'checkbox', 'Desmarcar'),
            ('Recebe sugestões de melhorias de Servidores?', 'checkbox', 'Marcar'),
            ('Recebe sugestões de melhorias de Prestadores de Serviço?', 'checkbox', 'Desmarcar'),
        ]
    )
    ti.clicar_botao('Salvar')
    ti.sucesso('Atualização realizada com sucesso.')


def test_acompanhar_demandas_e_indicadores(logado_demandas, capturar):
    """Tarefa 10: o coordenador acompanha as demandas pelos relatórios e pelo painel."""
    ti = Tela(logado_demandas('ti'))
    ti.ir('/demandas/acompanhamento_demandas/')
    anotar_tela('acompanhamento', ti)
    capturar(ti.pagina, 'acompanhamento-demandas')

    ti.ir('/demandas/indicadores/')
    anotar_tela('indicadores', ti)
    capturar(ti.pagina, 'demandas-indicadores')

    ti.ir('/demandas/painel_forca_trabalho/')
    anotar_tela('painel-forca-trabalho', ti)
    capturar(ti.pagina, 'painel-forca-trabalho')

    ti.ir('/demandas/relatorio/geral/')
    anotar_tela('relatorio-tags', ti)
    capturar(ti.pagina, 'relatorio-demandas-por-tags')


def test_atualizacoes_do_sistema_sem_login(new_context, capturar):
    """Módulo tem face pública: a lista de atualizações do sistema abre sem login."""
    contexto = new_context()
    page = contexto.new_page()
    page.goto('/demandas/atualizacoes/')
    page.wait_for_load_state('load')
    tela = Tela(page)
    anotar_tela('atualizacoes-publicas', tela)
    tela.ver_titulo('Atualizações do Sistema')
    capturar(page, 'atualizacoes-do-sistema')
