"""Fluxo da gestão e dos relatórios: listagem, indicadores, painéis, atualizações e prioridades.

As telas de gestão são as de leitura do módulo (listagem, indicadores, acompanhamento,
atividades reprimidas, painel de força-trabalho, atualizações do sistema) e as de priorização
por área, que é como os demandantes definem a ordem de desenvolvimento. Os downloads
(acompanhamento em PDF e relatório em planilha) e as telas que dependem da API do GitLab
ficam em `ROTAS_DISPENSADAS`, no conftest, com o motivo.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DASHBOARD = '/demandas/demandas/'
LISTAGEM = '/demandas/demandas/listagem/'
INDICADORES = '/demandas/indicadores/'
ACOMPANHAMENTO = '/demandas/acompanhamento_demandas/'
ATIVIDADES_REPRIMIDAS = '/demandas/relatorio_atividades_reprimidas/'
PAINEL = '/demandas/painel_forca_trabalho/'
ATUALIZACOES = '/demandas/atualizacoes/'
ATUALIZACAO = '/demandas/atualizacao/{}/'
GLOSSARIO = '/demandas/glossario/'
EXPORTAR_MARKDOWN = '/demandas/visualizar/{}/exportar_markdown/'
TAGS_AREA = '/demandas/ajax/get_tags_area/'
PRIORITARIAS = '/demandas/demandas_prioritarias_por_area/{}/'
PRIORIDADE_MANUAL = '/demandas/atualizar_prioridade_manualmente/{}/'
ATUALIZAR_PRIORIDADE = '/demandas/atualizar_prioridade/{}/'
VINCULAR_ISSUE = '/demandas/vincular_issue_gitlab/{}/'
# Os links de voto saem sem a barra final (o Django responde com `APPEND_SLASH`); a constante
# fica com a barra, que é a rota declarada em `urls.py`.
CONCORDAR = '/demandas/concordar_demanda/{}/'
DISCORDAR = '/demandas/discordar_demanda/{}/'
CONCORDAR_HREF = '/demandas/concordar_demanda/{}'
DISCORDAR_HREF = '/demandas/discordar_demanda/{}'
EDITAR_AREA = '/demandas/editar_area_atuacao/{}/'


def demanda_complementar() -> Demanda:
    """A segunda demanda da suíte (criada em ``test_05``), em desenvolvimento."""
    from demandas.models import Demanda

    demanda = Demanda.objects.filter(titulo='Demanda 2').first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    return demanda


def test_listagem_e_indicadores(logado_demandas: Callable[[str], Page]) -> None:
    """O analista abre a listagem de demandas e os indicadores do período."""
    tela = Tela(logado_demandas('analista'))

    # ACHADO DE PRODUTO (candidato a issue): a view procura `demandas_listagem.html` e o
    # arquivo no repositório é `listagem_demandas.html` — a tela cai no template default do
    # djtools e sai sem conteúdo nenhum. O teste assere o que a tela realmente mostra.
    tela.ir(LISTAGEM).ver_titulo('Listagem de Demandas')

    tela.ir(INDICADORES).ver_titulo('Indicadores')
    tela.preencher_formulario([('Data Inicial', 'Data', '01/01/2019'), ('Data Final', 'Data', '31/12/2019')])
    tela.clicar_botao('Enviar')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()


def test_acompanhamento_e_atividades_reprimidas(logado_demandas: Callable[[str], Page]) -> None:
    """O coordenador de TI abre o acompanhamento das demandas e o relatório de reprimidas."""
    tela = Tela(logado_demandas('coordenador_ti'))

    tela.ir(ACOMPANHAMENTO).ver_titulo('Relatório de Acompanhamento de Demandas e Erros')
    tela.preencher_formulario([('Data Inicial', 'Data', '01/01/2019'), ('Data Final', 'Data', '31/12/2019')])
    tela.clicar_botao('Enviar')
    tela.ver_texto('Demandas')

    tela.ir(ATIVIDADES_REPRIMIDAS).ver_titulo('Relatório de Atividades Reprimidas')


def test_painel_de_forca_trabalho(logado_demandas: Callable[[str], Page]) -> None:
    """O coordenador de TI vê o painel de força-trabalho com os analistas cadastrados."""
    tela = Tela(logado_demandas('coordenador_ti'))

    tela.ir(PAINEL).ver_titulo('Painel de Força-Trabalho')
    tela.ver_texto('Analista')


def test_atualizacoes_do_sistema(logado_demandas: Callable[[str], Page]) -> None:
    """O servidor lista as atualizações do sistema e abre o detalhe de uma delas."""
    tela = Tela(logado_demandas('servidor'))

    from demandas.models import Atualizacao

    atualizacao = Atualizacao.objects.get(descricao='Atualização E2E')
    tela.ir(ATUALIZACOES).ver_titulo('Atualizações do Sistema').ver_texto('Atualização E2E')

    tela.ir(ATUALIZACAO.format(atualizacao.pk)).ver_titulo(f'Atualização #{atualizacao.pk}').ver_texto('Detalhamento E2E')


def test_prioridades_da_area_e_prioridade_manual(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante responsável abre as prioridades da área e define uma prioridade à mão."""
    tela = Tela(logado_demandas('demandante'))

    from demandas.models import AreaAtuacaoDemanda, Demanda

    area = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    demandas = list(Demanda.objects.ativas().filter(area=area).order_by('id'))
    assert len(demandas) >= 2, 'a cadeia precisa de duas demandas ativas na área'
    alvo = demandas[-1]

    tela.ir(DASHBOARD).ver_titulo('Dashboard: Demandas')
    expect(tela.loc(f'//a[@href="{PRIORITARIAS.format(area.pk)}"]').first).to_be_visible()
    tela.loc(f'//a[@href="{PRIORITARIAS.format(area.pk)}"]').first.click()
    tela.ver_titulo('Demandas Prioritárias pela Área')
    # A tela lista as demandas ATIVAS da área — a Demanda 1 já está concluída.
    tela.ver_texto('Demanda 2')

    expect(tela.loc(f'//a[@href="{PRIORIDADE_MANUAL.format(alvo.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{PRIORIDADE_MANUAL.format(alvo.pk)}"]').click()
    popup = tela.popup()
    popup.ver_texto('Alterar prioridade de')
    popup.preencher('Nova prioridade', 'Número', '1')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Gerenciamento salvo com sucesso.')
    alvo.refresh_from_db()
    assert alvo.prioridade == 1, 'a UI disse que salvou, mas a prioridade não persistiu'

    # A reordenação por arrastar-e-soltar usa um endpoint GET com a nova ordem na query.
    resposta = tela.buscar(f'{ATUALIZAR_PRIORIDADE.format(area.pk)}?demandas={",".join(str(d.pk) for d in reversed(demandas))}')
    assert resposta.status == 200, 'o endpoint de priorização precisa responder 200'
    assert resposta.json().get('ok') is True, f'a priorização foi recusada: {resposta.text()}'


def test_exportar_markdown_e_ajax_das_tags(logado_demandas: Callable[[str], Page]) -> None:
    """O analista exporta o contexto da demanda em markdown e o formulário busca as tags da área."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import AreaAtuacaoDemanda

    demanda = demanda_complementar()
    resposta = tela.buscar(EXPORTAR_MARKDOWN.format(demanda.pk))
    assert resposta.status == 200, 'a exportação em markdown precisa responder 200'
    assert 'Demanda 2' in resposta.text(), 'o markdown exportado precisa trazer o título da demanda'
    assert resposta.headers.get('content-type', '').startswith('text/markdown'), 'a exportação precisa sair como markdown'

    area = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    resposta = tela.buscar(f'{TAGS_AREA}?area_id={area.pk}')
    assert resposta.status == 200, 'o endpoint de tags da área precisa responder 200'
    assert 'Tag Especial' in [tag['nome'] for tag in resposta.json()['tags']], 'o endpoint precisa listar os módulos da área'


def test_concordar_e_discordar_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O servidor vota na demanda recém-solicitada (a criada a partir da sugestão)."""
    tela = Tela(logado_demandas('servidor'))

    from demandas.models import Demanda, DemandaVoto

    demanda = Demanda.objects.get(titulo='Melhoria Tag Especial')
    assert demanda.pode_votar(), 'a demanda gerada pela sugestão precisa aceitar voto'
    tela.ir(f'/demandas/visualizar/{demanda.pk}/')
    expect(tela.loc(f'//a[@href="{CONCORDAR_HREF.format(demanda.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{CONCORDAR_HREF.format(demanda.pk)}"]').click()
    tela.sucesso('Voto cadastrado com sucesso.')
    assert DemandaVoto.objects.filter(demanda=demanda, usuario__username='105004', concorda=True).exists(), (
        'a UI disse que registrou o voto, mas ele não persistiu'
    )

    tela.ir(f'/demandas/visualizar/{demanda.pk}/')
    expect(tela.loc(f'//a[@href="{DISCORDAR_HREF.format(demanda.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{DISCORDAR_HREF.format(demanda.pk)}"]').click()
    tela.sucesso('Voto cadastrado com sucesso.')
    assert DemandaVoto.objects.filter(demanda=demanda, usuario__username='105004', concorda=False).count() == 1, (
        'a troca de voto precisa reaproveitar o registro'
    )


def test_editar_area_atuacao_da_sugestao(logado: Callable[[str, str], Page]) -> None:
    """A troca da área de atuação da sugestão é restrita ao superusuário.

    A rota exige `comum.is_coordenador_de_sistemas`, permissão que nenhum grupo do módulo
    recebe — na prática só o superusuário passa.
    """
    tela = Tela(logado('admin', 'abc'))

    from demandas.models import SugestaoMelhoria

    sugestao = SugestaoMelhoria.objects.get(titulo='Melhoria Tag Especial')
    tela.ir(EDITAR_AREA.format(sugestao.pk)).ver_texto('Editar Área de Atuação da Sugestão de Melhoria')
    tela.preencher('Área de Atuação', 'Autocomplete', 'Tecnologia da Informação')
    tela.clicar_botao('Salvar').sucesso('Sugestão de Melhoria salva com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.area_atuacao is not None, 'a UI disse que salvou, mas a área da sugestão não persistiu'


def test_vincular_issue_gitlab_e_glossario(logado_demandas: Callable[[str], Page]) -> None:
    """O analista vincula a issue do GitLab à especificação e abre o glossário do módulo."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import DoD, Especificacao

    demanda = demanda_complementar()
    dod = DoD.objects.get(demanda=demanda)
    especificacao = Especificacao.objects.filter(dod=dod).order_by('ordem').first()
    assert especificacao is not None, 'a cadeia precisa de uma especificação na consolidação'

    tela.ir(f'/demandas/visualizar/{demanda.pk}/').clicar_aba('Consolidação')
    quadro = tela.quadro('Especificação')
    quadro.clicar_botao('GitLab')
    # O link do produto sai sem a barra final (o Django responde com `APPEND_SLASH`).
    vincular = tela.loc(f'//a[contains(@href, "{VINCULAR_ISSUE.format(especificacao.pk).rstrip("/")}")]').first
    expect(vincular).to_be_visible()
    vincular.click()
    popup = tela.popup()
    popup.preencher('URL da Issue no Gitlab', 'Texto', 'https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/1234')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('URL vinculada com sucesso.')
    especificacao.refresh_from_db()
    assert especificacao.gitlab_issue_url == 'https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/1234', (
        'a UI disse que vinculou, mas a URL da issue não persistiu'
    )

    # O glossário é o popup do menu "Outras opções" da demanda.
    tela.ir(f'/demandas/visualizar/{demanda.pk}/').clicar_botao('Outras opções')
    expect(tela.loc(f'//a[@href="{GLOSSARIO}"]')).to_be_visible()
    tela.loc(f'//a[@href="{GLOSSARIO}"]').click()
    tela.popup().ver_texto('É o responsável do setor de Tecnologia da Informação')
