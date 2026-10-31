"""Fluxo: o lado do atendente (modo 2) — atender, encaminhar, suspender, marcar com tags,
reclassificar — e os desfechos do solicitante: cancelar, reabrir, fechar e avaliar.

Por que importa: é a máquina de estados do chamado (``django_fsm``) vista pela tela. Cada transição
tem permissão própria (assumir, escalar, retornar, reclassificar, suspender, resolver, fechar,
reabrir, cancelar), e a regressão típica não dá erro: o botão some porque a permissão deixou de ser
concedida, ou o chamado fica preso em um estado sem que ninguém consiga fechá-lo.

O fluxo de atendimento é a cadeia inteira num teste só (dashboard → fila → assumir → atender →
resolver com artigo): cada passo depende do anterior, e é a regra 1 de granularidade. O valor do
indicador "Não Atribuídos" é afirmado como **delta** do que o próprio teste criou — nunca como
contagem global, que o banco compartilhado torna imprevisível.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, adicionar_nivel_superior, criar_chamado, nome_e2e, popup_em, postar, usuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DASHBOARD = '/centralservicos/dashboard/'
REMOVER_TAG = '/centralservicos/remover_tag_do_chamado/{}/{}/'


def _valor_do_indicador(tela: Tela, indicador: str) -> str:
    """Lê o número do indicador dentro do quadro "Chamados de Incidentes" do Dashboard."""
    alvo = (
        tela.quadro('Chamados de Incidentes')
        .loc(f'//a[contains(@class, "total-item")][.//p[contains(normalize-space(.), "{indicador}")]]//p[contains(@class, "total")]')
        .first
    )
    expect(alvo).to_be_visible()
    return alvo.inner_text().strip()


def test_atendente_atende_chamado(logado_central, contexto_com_artigos, chamado_nao_atribuido):
    """O indicador do dashboard, a fila, assumir, atender e resolver com o artigo.

    O ``refresh`` do chamado é por query nova, e não ``refresh_from_db``: ``Chamado.status`` é
    ``FSMIntegerField(protected=True)`` e o descriptor recusa a releitura direta.
    """
    from centralservicos.models import Chamado

    chamado, antes = chamado_nao_atribuido
    artigo = contexto_com_artigos.artigo_privado

    tela = Tela(logado_central('atendente')).ir(DASHBOARD)
    tela.ver_titulo('Dashboard')
    valor = _valor_do_indicador(tela, 'Não Atribuídos')
    assert valor == str(antes + 1), f'o indicador "Não Atribuídos" deveria mostrar {antes + 1} (o chamado novo), mostrou {valor!r}'

    tela.quadro('Chamados de Incidentes').clicar_link('Não Atribuídos')
    tela.ver_titulo('Chamados')
    tela.clicar_link(f'INC #{chamado.pk}')
    tela.ver_titulo(f'Chamado {chamado.pk}')

    tela.clicar_botao('Assumir')
    tela.sucesso('Atribuição realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.get_atendimento_atribuicao_atual().atribuido_para_id == usuario(PAPEIS['atendente']).pk, (
        'a UI disse que assumiu, mas o chamado não ficou com o atendente'
    )

    tela.clicar_botao('Alterar para Em Atendimento')
    tela.sucesso('Alteração de situação realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.estah_em_atendimento(), 'o chamado não foi para Em Atendimento'

    tela.clicar_aba('Artigos relacionados')
    tela.selecionar_cartao(artigo.titulo)
    tela.preencher('Comentário', 'textarea', 'Chamado resolvido com a remoção do papel preso na bandeja.')
    tela.clicar_botao('Alterar para Resolvido')
    tela.sucesso('Alteração de situação realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.estah_resolvido(), 'o chamado não foi resolvido'
    assert atual.historicostatus_set.filter(bases_conhecimento__titulo=artigo.titulo).exists(), (
        'o artigo usado na resolução não ficou registrado no histórico'
    )


def test_responsavel_atribui_escala_retorna_e_reclassifica(logado_central, contexto_com_artigos):
    """O responsável pelo grupo atribui a um atendente, escala ao nível superior, retorna e reclassifica.

    Quem enxerga Atribuir/Escalar/Retornar é o **responsável** pelo grupo atual, não o atendente
    comum — é a diferença de papel que o teste prova de passagem. A reclassificação troca o centro
    do chamado e, com ele, o grupo que o atende.
    """
    from centralservicos.models import Chamado

    centro_sistemico, grupo_sistemico = adicionar_nivel_superior(contexto_com_artigos)
    grupo_local = contexto_com_artigos.grupo_atendimento
    chamado = criar_chamado(contexto_com_artigos, interessado=usuario(PAPEIS['servidor']))

    tela = Tela(logado_central('responsavel')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')

    tela.clicar_botao('Ações')
    tela.clicar_link('Atribuir')
    popup = popup_em(tela, 'atribuir_chamado')
    popup.preencher('Atribuido para', 'lista', str(usuario(PAPEIS['atendente'])))
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atribuição realizada com sucesso para')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.get_atendente_do_chamado() == usuario(PAPEIS['atendente']), 'a atribuição não ficou com o atendente'

    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Escalar')
    tela.ver_titulo('Escalar Atendimento')
    tela.preencher('Texto', 'textarea', 'Caso exige acesso à rede; encaminhando ao nível superior.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.get_atendimento_atribuicao_atual().grupo_atendimento_id == grupo_sistemico.pk, 'o chamado não escalou para o grupo superior'

    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Retornar')
    tela.ver_titulo('Retornar Atendimento')
    tela.preencher('Texto', 'textarea', 'O nível superior orientou o procedimento; retornando ao grupo local.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Operação realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.get_atendimento_atribuicao_atual().grupo_atendimento_id == grupo_local.pk, 'o chamado não retornou ao grupo local'

    tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_botao('Ações')
    tela.clicar_link('Reclassificar')
    tela.ver_titulo(f'Reclassificar Chamado: {chamado.pk}')
    tela.preencher('Campus', 'lista', 'CZN')
    tela.preencher('Centro de Atendimento', 'radio', centro_sistemico.nome)
    tela.preencher('Justificativa', 'textarea', 'Atendimento passa a ser sistêmico, não local.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Reclassificação de chamado realizada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.get_atendimento_atribuicao_atual().grupo_atendimento_id == grupo_sistemico.pk, (
        'a reclassificação deveria reencaminhar o chamado ao grupo do novo centro'
    )


def test_atendente_suspende_e_gerencia_tags(logado_central, contexto_com_artigos, chamado_em_atendimento):
    """Suspender (aguardar terceiros) e marcar o chamado com tag — e remover a tag depois.

    A tag vive num cadastro de apoio por área; o popup só oferece as da área dos grupos do
    atendente, e a remoção é POST-only (o botão do menu lateral é um ícone sem texto).
    """
    from centralservicos.models import Tag

    chamado = chamado_em_atendimento
    tag = Tag.objects.create(nome=nome_e2e('Tag'), area=contexto_com_artigos.area)

    tela = Tela(logado_central('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_botao('Ações')
    tela.clicar_link('Adicionar tags')
    popup = popup_em(tela, 'adicionar_tags_ao_chamado')
    popup.preencher('Tags', 'checkbox multiplo', tag.nome)
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Adição de tags realizada com sucesso.')
    assert chamado.tags.filter(pk=tag.pk).exists(), 'a UI disse que tagueou, mas a tag não foi vinculada'

    tela.clicar_botao('Suspender')
    tela.ver_titulo('Alterar Situação para Suspenso')
    tela.preencher('Comentário', 'textarea', 'Aguardando a chegada da peça de reposição.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    atual = type(chamado).objects.get(pk=chamado.pk)
    assert atual.estah_suspenso(), 'o chamado não foi suspenso'

    resposta = postar(tela.pagina, REMOVER_TAG.format(chamado.pk, tag.pk))
    assert resposta.status == 302, f'a remoção de tag deveria redirecionar, respondeu HTTP {resposta.status}'
    tela = tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.sucesso('Tag removida com sucesso.')
    assert not atual.tags.filter(pk=tag.pk).exists(), 'a UI disse que removeu, mas a tag continua vinculada'


def test_solicitante_cancela_chamado_aberto(logado_central, contexto_com_artigos):
    """Cancelar é do solicitante e vale para o chamado aberto por engano — antes de alguém atender."""
    from centralservicos.models import Chamado

    chamado = criar_chamado(contexto_com_artigos, interessado=usuario(PAPEIS['servidor']))

    tela = Tela(logado_central('servidor')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_link('Cancelar')
    tela.ver_titulo(f'Cancelar {chamado}')
    tela.preencher('Comentário', 'textarea', 'Abri o chamado no serviço errado; vou abrir no serviço correto.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.estah_cancelado(), 'o chamado não foi cancelado'


def test_solicitante_reabre_chamado_resolvido(logado_central, chamado_resolvido):
    """Reabrir volta o chamado ao atendimento **com o atendente anterior** — a regressão é perdê-lo.

    O chamado resolvido é a única origem possível do Reaberto (``Chamado.reabrir_chamado``), e a
    view reatribui explicitamente o atendente que constava na atribuição anterior.
    """
    from centralservicos.models import Chamado, StatusChamado

    chamado = chamado_resolvido
    tela = Tela(logado_central('servidor')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_link('Reabrir chamado')
    tela.ver_titulo('Alterar Situação para Reaberto')
    tela.preencher('Comentário', 'textarea', 'A impressora apresentou o mesmo defeito dois dias depois.')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.status == StatusChamado.get_status_reaberto(), 'o chamado deveria ficar Reaberto'
    assert atual.get_atendente_do_chamado() == usuario(PAPEIS['atendente']), 'o atendente anterior deveria ser mantido'


def test_solicitante_fecha_e_avalia_chamado(logado_central, chamado_resolvido):
    """Fechar é do solicitante, e é na mesma tela que ele avalia o atendimento (nota de 1 a 5).

    O formulário é escrito à mão: as notas são radios escondidos pelo ``stars.js`` (clica-se a
    estrela, isto é, o ``label``), e o botão de confirmação é um ``input[type=submit]`` sem
    ``value`` — daí o clique pelo XPath do form em vez de ``clicar_botao``.
    """
    from centralservicos.models import Chamado

    chamado = chamado_resolvido
    tela = Tela(logado_central('servidor')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_link('Fechar Chamado')
    tela.ver_titulo('Fechar Chamado')
    tela.loc('//label[@for="rating-5"]').first.click()
    tela.preencher('Comentário', 'textarea', 'Atendimento rápido e resolveu o problema.')
    tela.loc('//form[@id="fechareavaliarchamado_form"]//input[@type="submit"]').first.click()
    tela.sucesso('Alteração de situação realizada com sucesso.')

    atual = Chamado.objects.get(pk=chamado.pk)
    assert atual.estah_fechado(), 'o chamado não foi fechado'
    assert atual.nota_avaliacao == 5, 'a avaliação não foi registrada'
