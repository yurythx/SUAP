"""Fluxo da sugestão de melhoria (feature 004 do behave).

O servidor abre a sugestão pelo módulo da área de atuação, os colegas votam, o demandante
responsável assume a sugestão, a defere e gera a demanda a partir dela. No fim, o coordenador
de TI ajusta o público que pode abrir sugestões naquela área. A cadeia é independente da
demanda de ``test_01``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import SugestaoMelhoria

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAR_AREAS = '/demandas/listar_areas_atuacao_sugestao_melhoria/'
SUGESTOES_MODULO = '/demandas/sugestoes_modulo/{}/{}/'
ADICIONAR_SUGESTAO = '/demandas/adicionar_sugestao_melhoria/{}/'
SUGESTAO = '/demandas/sugestao_melhoria/{}/'
GERAR_DEMANDA = '/demandas/gerar_demanda_sugestao_melhoria/{}/'
ALTERAR_SITUACAO = '/demandas/alterar_situacao_sugestao/{}/{}/'
EDITAR_DADOS = '/demandas/editar_todos_dados_sugestao_melhoria/{}/'
EDITAR_DADOS_BASICOS = '/demandas/editar_dados_basicos_sugestao_melhoria/{}/'
ATRIBUIR_RESPONSAVEL = '/demandas/atribuir_se_como_responsavel_sugestao_melhoria/{}/'
# A listagem do módulo monta os links de voto SEM a barra final (o produto responde com o
# `APPEND_SLASH`); a constante fica com a barra, que é a rota declarada em `urls.py`.
CONCORDAR = '/demandas/concordar_sugestao/{}/'
DISCORDAR = '/demandas/discordar_sugestao/{}/'
CONCORDAR_HREF = '/demandas/concordar_sugestao/{}'
DISCORDAR_HREF = '/demandas/discordar_sugestao/{}'
TORNAR_INTERESSADO = '/demandas/tornar_se_interessado/{}/'
ANEXO_SUGESTAO = '/demandas/adicionar_anexo_sugestao/{}/'
AREA_ADMIN = '/admin/demandas/areaatuacaodemanda/'

TITULO = 'Melhoria Tag Especial'
DESCRICAO = 'Sugiro alterar a funcionalidade nos seguintes aspectos...'


def _area_e_tag() -> tuple[int, int]:
    """Resolve a área de atuação e o módulo que o seed criou."""
    from demandas.models import AreaAtuacaoDemanda, Tag

    area_atuacao = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    tag = Tag.objects.get(nome='Tag Especial')
    return area_atuacao.pk, tag.pk


def sugestao_da_cadeia() -> SugestaoMelhoria:
    """A sugestão aberta por este arquivo."""
    from demandas.models import SugestaoMelhoria

    sugestao = SugestaoMelhoria.objects.filter(titulo=TITULO).first()
    assert sugestao is not None, 'sugestão ausente: a cadeia deste arquivo é sequencial'
    return sugestao


def test_servidor_abre_a_sugestao_e_os_colegas_votam(logado_demandas: Callable[[str], Page]) -> None:
    """O servidor abre a sugestão pelo módulo; outro servidor concorda e discorda."""
    servidor = Tela(logado_demandas('servidor'))
    colega = Tela(logado_demandas('servidor2'))

    from demandas.models import SugestaoMelhoria, SugestaoVoto

    area_id, tag_id = _area_e_tag()
    servidor.ir(LISTAR_AREAS).ver_titulo('Módulos para abertura de Sugestões de melhorias para o SUAP')
    servidor.clicar_link('Tag Especial')
    expect(servidor.pagina).to_have_url(re.compile(rf'{SUGESTOES_MODULO.format(area_id, tag_id)}$'))
    servidor.ver_titulo('Sugestões de melhorias para Tag Especial (Tecnologia da Informação)')

    servidor.clicar_botao('Adicionar Sugestão')
    expect(servidor.pagina).to_have_url(re.compile(rf'{ADICIONAR_SUGESTAO.format(area_id)}\?tags_ids={tag_id}$'))
    servidor.preencher_formulario([('Título', 'Texto', TITULO), ('Descrição', 'TextArea', DESCRICAO)])
    servidor.clicar_botao('Salvar').sucesso('Sugestão de Melhoria salva com sucesso.')
    sugestao = SugestaoMelhoria.objects.get(titulo=TITULO)
    assert sugestao.requisitante.username == '105004', 'a UI disse que salvou, mas o requisitante não é quem abriu'
    assert sugestao.tags.filter(pk=tag_id).exists(), 'o módulo escolhido não foi vinculado à sugestão'
    assert sugestao.situacao == SugestaoMelhoria.SITUACAO_PENDENTE, 'a sugestão nova nasce Pendente'

    colega.ir(SUGESTOES_MODULO.format(area_id, tag_id)).ver_texto(TITULO)
    concordar = colega.loc(f'//a[@href="{CONCORDAR_HREF.format(sugestao.pk)}"]').first
    expect(concordar).to_be_visible()
    concordar.click()
    # O voto responde com redirect para a própria sugestão.
    expect(colega.pagina).to_have_url(re.compile(rf'{SUGESTAO.format(sugestao.pk)}$'))
    colega.sucesso('Voto cadastrado com sucesso.')
    assert SugestaoVoto.objects.filter(sugestao=sugestao, usuario__username='105005', concorda=True).exists(), (
        'a UI disse que registrou o voto, mas ele não persistiu'
    )

    colega.ir(SUGESTOES_MODULO.format(area_id, tag_id))
    discordar = colega.loc(f'//a[@href="{DISCORDAR_HREF.format(sugestao.pk)}"]').first
    expect(discordar).to_be_visible()
    discordar.click()
    expect(colega.pagina).to_have_url(re.compile(rf'{SUGESTAO.format(sugestao.pk)}$'))
    colega.sucesso('Voto cadastrado com sucesso.')
    sugestao.refresh_from_db()
    # A pontuação é `concordâncias - discordâncias`: o voto é o mesmo registro, invertido.
    assert sugestao.qtd_votos == -1, 'a discordância precisa substituir o voto anterior'
    assert SugestaoVoto.objects.filter(sugestao=sugestao, usuario__username='105005').count() == 1, (
        'a troca de voto não pode criar um segundo registro'
    )

    # Quem já votou pode se incluir como interessado pela tela da sugestão.
    colega.ir(SUGESTAO.format(sugestao.pk))
    expect(colega.loc(f'//a[@href="{TORNAR_INTERESSADO.format(sugestao.pk)}"]')).to_be_visible()
    colega.loc(f'//a[@href="{TORNAR_INTERESSADO.format(sugestao.pk)}"]').click()
    colega.sucesso('Você foi incluído como Interessado desta sugestão.')
    assert sugestao.interessados.filter(username='105005').exists(), 'a UI disse que incluiu, mas o interessado não persistiu'


def test_requisitante_edita_os_dados_basicos_da_sugestao(logado_demandas: Callable[[str], Page]) -> None:
    """O requisitante ajusta título e descrição enquanto a sugestão está pendente."""
    tela = Tela(logado_demandas('servidor'))

    from demandas.models import SugestaoMelhoria

    sugestao = sugestao_da_cadeia()
    assert sugestao.situacao == SugestaoMelhoria.SITUACAO_PENDENTE, 'a cadeia deste teste exige a sugestão pendente'
    tela.ir(SUGESTAO.format(sugestao.pk))
    expect(tela.loc(f'//a[@href="{EDITAR_DADOS_BASICOS.format(sugestao.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{EDITAR_DADOS_BASICOS.format(sugestao.pk)}"]').click()
    tela.ver_texto('Editar Sugestão de Melhoria')
    tela.preencher_formulario([('Título', 'Texto', TITULO), ('Descrição', 'TextArea', f'{DESCRICAO} (revisada)')])
    tela.clicar_botao('Salvar').sucesso('Sugestão de Melhoria salva com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.descricao.endswith('(revisada)'), 'a UI disse que salvou, mas a descrição não mudou'


def test_demandante_defere_a_sugestao_e_gera_a_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante assume a sugestão, a defere, anexa um arquivo e gera a demanda."""
    tela = Tela(logado_demandas('demandante'))

    from demandas.models import Demanda, SugestaoAnexo, SugestaoMelhoria

    area_id, tag_id = _area_e_tag()
    sugestao = sugestao_da_cadeia()
    tela.ir(f'/admin/demandas/sugestaomelhoria/?area_atuacao__id__exact={area_id}&tags__id__exact={tag_id}').ver_texto(TITULO)
    tela.linha(TITULO).clicar_icone('exibição')
    expect(tela.pagina).to_have_url(re.compile(rf'{SUGESTAO.format(sugestao.pk)}$'))
    tela.ver_texto(DESCRICAO)

    expect(tela.loc(f'//a[@href="{ATRIBUIR_RESPONSAVEL.format(sugestao.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{ATRIBUIR_RESPONSAVEL.format(sugestao.pk)}"]').click()
    tela.sucesso('Responsável definido com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.responsavel.username == '105001', 'a UI disse que definiu o responsável, mas ele não persistiu'

    # O anexo da sugestão é oferecido a quem pode anexar (o responsável recém-definido).
    expect(tela.loc(f'//a[@href="{ANEXO_SUGESTAO.format(sugestao.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{ANEXO_SUGESTAO.format(sugestao.pk)}"]').click()
    tela.preencher_formulario([('Descrição', 'Texto', 'Anexo da sugestão E2E'), ('Anexo', 'Arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar').sucesso('Anexo adicionado com sucesso.')
    assert SugestaoAnexo.objects.filter(sugestao=sugestao, descricao='Anexo da sugestão E2E').exists(), (
        'a UI disse que anexou, mas o anexo não persistiu'
    )

    # A edição completa leva a sugestão para "Em análise" — é o estado em que o produto
    # oferece o menu "Avaliar" (as transições de etapa só existem a partir dele).
    tela.ir(SUGESTAO.format(sugestao.pk))
    expect(tela.loc(f'//a[@href="{EDITAR_DADOS.format(sugestao.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{EDITAR_DADOS.format(sugestao.pk)}"]').click()
    tela.preencher('Situação', 'Lista', 'Em análise')
    tela.clicar_botao('Salvar').sucesso('Sugestão de Melhoria salva com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.situacao == SugestaoMelhoria.SITUACAO_EM_ANALISE, 'a UI disse que salvou, mas a situação não mudou'

    tela.ir(SUGESTAO.format(sugestao.pk))
    tela.clicar_botao('Avaliar')
    expect(tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(sugestao.pk, SugestaoMelhoria.SITUACAO_DEFERIDA)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{ALTERAR_SITUACAO.format(sugestao.pk, SugestaoMelhoria.SITUACAO_DEFERIDA)}"]').click()
    tela.sucesso('Etapa alterada com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.situacao == SugestaoMelhoria.SITUACAO_DEFERIDA, 'a UI disse que deferiu, mas a situação não mudou'

    # A sugestão deferida libera o "Gerar Demanda", que cria a demanda com os dados da sugestão.
    tela.ir(SUGESTAO.format(sugestao.pk))
    expect(tela.loc(f'//a[@href="{GERAR_DEMANDA.format(sugestao.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{GERAR_DEMANDA.format(sugestao.pk)}"]').click()
    tela.clicar_botao('Salvar').sucesso('Demanda gerada com sucesso.')
    sugestao.refresh_from_db()
    assert sugestao.demanda_gerada is not None, 'a UI disse que gerou a demanda, mas a sugestão não aponta para ela'
    assert Demanda.objects.filter(titulo=TITULO).exists(), 'a demanda gerada não persistiu'

    # A sugestão com demanda gerada não pode mais gerar outra.
    tela.ir(SUGESTAO.format(sugestao.pk)).ver_texto('Ver demanda')


def test_coordenador_de_ti_edita_o_publico_da_area(logado_demandas: Callable[[str], Page]) -> None:
    """O coordenador de TI edita o público que pode abrir sugestões na área de atuação."""
    tela = Tela(logado_demandas('coordenador_ti'))

    from demandas.models import AreaAtuacaoDemanda

    area_atuacao = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    tela.ir(AREA_ADMIN).ver_texto('Tecnologia da Informação')
    tela.linha('Tecnologia da Informação').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{AREA_ADMIN}{area_atuacao.pk}/change/$'))
    tela.preencher_formulario(
        [
            ('Recebe sugestões de melhorias de Alunos?', 'Checkbox', 'marcar'),
            ('Recebe sugestões de melhorias de Servidores?', 'Checkbox', 'desmarcar'),
            ('Recebe sugestões de melhorias de Prestadores de Serviço?', 'Checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Atualização realizada com sucesso.')
    area_atuacao.refresh_from_db()
    assert area_atuacao.recebe_sugestoes_publico_aluno is True, 'o checkbox de alunos não persistiu'
    assert area_atuacao.recebe_sugestoes_publico_servidor is False, 'o checkbox de servidores não persistiu'
    assert area_atuacao.recebe_sugestoes_publico_prestador_servico is True, 'o checkbox de prestadores não persistiu'
