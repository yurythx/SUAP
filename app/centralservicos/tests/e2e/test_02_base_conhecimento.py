"""Fluxo: a Base de Conhecimento (modo 2) — o gestor cria o artigo e o ciclo de supervisão que o
behave não cobria (aprovar, marcar para correção, unificar, avaliar, anexos).

Por que importa: o artigo é o que o atendente usa para resolver o chamado e o que o solicitante lê
antes de abrir um. A parte que mais dói em regressão é a **supervisão**: um artigo pendente que
passa a ser usado na resolução, ou um artigo publicado que fica preso em "necessita correção",
quebra o fluxo de quem atende sem nenhum erro visível na tela.

Os testes de leitura usam ``Tela.buscar`` (GET pela sessão do browser, sem renderizar) onde o que se
afirma é o conteúdo devolvido pelo servidor; os de escrita usam a tela.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, criar_artigo, criar_chamado, criar_contexto, nome_e2e, usuario, ver_campos

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

BASE_MENU = '/centralservicos/baseconhecimento/'
ARTIGO_ADMIN = '/admin/centralservicos/baseconhecimento/'
APROVAR = '/centralservicos/baseconhecimento/aprovar/{}/'
PUBLICA = '/centralservicos/baseconhecimento/publica/{}/'
RESOLVIDOS = '/centralservicos/baseconhecimento/chamados/{}/'
AVALIAR = '/centralservicos/baseconhecimento/avaliar/{}/{}/{}/'
REMOVER_ANEXO = '/centralservicos/baseconhecimento/remover_anexo/{}/{}/'
UNIFICAR = '/centralservicos/baseconhecimento/unificar/'
REVISAR = '/centralservicos/baseconhecimento/revisar/'


def test_gestor_cria_artigo_para_base_de_conhecimento(logado_central):
    """O gestor percorre o menu da Base, abre o admin e cadastra o artigo.

    O gestor entra como atendente do grupo de atendimento da área: é o vínculo que faz o admin da
    Base enxergar a área (``GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento``), como
    acontece quando ele é vinculado ao grupo pela tela.
    """
    from centralservicos.models import BaseConhecimento

    contexto = criar_contexto()
    contexto.grupo_atendimento.atendentes.add(usuario(PAPEIS['gestor']))
    titulo = nome_e2e('Artigo')

    tela = Tela(logado_central('gestor')).ir(BASE_MENU)
    tela.ver_titulo('Listar Áreas de serviço')
    tela.clicar_link(contexto.area.nome)
    tela.ver_titulo(f'Base de Conhecimentos: {contexto.area.nome}')
    tela.clicar_botao('Visualizar todos')
    tela.ver_titulo('Bases de Conhecimento')
    tela.clicar_botao('Adicionar Base de Conhecimento')
    tela.ver_titulo('Adicionar Base de Conhecimento')
    ver_campos(tela, ['Área do Serviço', 'Título', 'Resumo', 'Ativo?', 'Visibilidade', 'Solução'])
    tela.preencher_formulario(
        [
            ('Área do Serviço', 'autocomplete', contexto.area.nome),
            ('Título', 'texto', titulo),
            ('Resumo', 'textarea', 'Usuário reclama que a impressora está indicando atolamento de papel.'),
            ('Ativo?', 'checkbox', 'Marcar'),
            ('Visibilidade', 'lista', 'Privada'),
            ('Solução', 'texto rico', 'Verificar e remover o papel atolado da impressora.'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    artigo = BaseConhecimento.objects.filter(titulo=titulo).first()
    assert artigo is not None, 'a UI disse que salvou, mas o artigo não persistiu'
    assert artigo.area == contexto.area, 'o artigo foi gravado em outra área'
    assert artigo.ativo, 'o artigo não nasceu ativo'
    assert artigo.visibilidade == BaseConhecimento.VISIBILIDADE_PRIVADA, 'o artigo não nasceu privado'


def test_supervisor_aprova_artigo_pendente(logado_central):
    """O artigo sem ``add_active_baseconhecimento`` nasce pendente e só o supervisor o libera.

    A regressão que pega: artigo pendente sendo oferecido na resolução do chamado — o form do
    resolver filtra por ``supervisao_pendente=False``, e é isso que a asserção de ORM confirma.
    """
    from centralservicos.models import BaseConhecimento

    contexto = criar_contexto()
    contexto.grupo_atendimento.atendentes.add(usuario(PAPEIS['supervisor']))
    artigo = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento], pendente=True)
    assert artigo.supervisao_pendente, 'pré-condição: o artigo deveria estar pendente de supervisão'

    tela = Tela(logado_central('supervisor')).ir(BASE_MENU)
    tela.clicar_link(contexto.area.nome)
    tela.ver_titulo(f'Base de Conhecimentos: {contexto.area.nome}')
    tela.clicar_link(artigo.titulo)
    tela.ver_titulo(artigo.titulo)
    tela.clicar_botao('Aprovar alterações')
    tela.sucesso('Base de conhecimento revisada com sucesso.')
    artigo.refresh_from_db()
    assert not artigo.supervisao_pendente, 'a UI disse que aprovou, mas a supervisão continua pendente'


def test_supervisor_marca_artigo_para_correcao(logado_central):
    """Marcar para correção tira o artigo da resolução e registra o motivo como comentário."""
    from centralservicos.models import BaseConhecimento
    from comum.models import Comentario

    contexto = criar_contexto()
    contexto.grupo_atendimento.atendentes.add(usuario(PAPEIS['supervisor']))
    artigo = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento])

    tela = Tela(logado_central('supervisor')).ir(f'/centralservicos/baseconhecimento/{artigo.pk}/')
    tela.ver_titulo(artigo.titulo)
    tela.clicar_link('Marcar para correção')
    tela.ver_titulo('Solicitar correção de artigo da Base de Conhecimentos')
    tela.preencher('Comentário', 'textarea', 'O caminho do papel na bandeja mudou; atualizar o passo a passo.')
    tela.clicar_botao('Enviar')
    tela.sucesso('Base de conhecimento marcada para correção.')

    artigo.refresh_from_db()
    assert artigo.necessita_correcao, 'a UI disse que marcou, mas o artigo não está pendente de correção'
    assert not artigo.estah_disponivel_para_uso(), 'artigo marcado para correção continua disponível para uso'
    assert Comentario.objects.filter(object_id=artigo.pk, texto__contains='bandeja').exists(), (
        'o motivo da correção deveria ficar registrado como comentário do artigo'
    )
    # A área do artigo é lida de novo por query: é a mesma classe de checagem do ORM acima,
    # e garante que o BaseConhecimento em memória não é uma cópia divergente do banco.
    assert BaseConhecimento.objects.get(pk=artigo.pk).necessita_correcao is True


def test_supervisor_unifica_bases_de_conhecimento(logado_central):
    """Unificar move o histórico de uso das bases secundárias para a principal e apaga as outras.

    A regressão que pega: chamados resolvidos com o artigo excluído perderem o vínculo — o que some
    do histórico sem erro nenhum na tela.
    """
    from centralservicos.models import BaseConhecimento, HistoricoStatus

    contexto = criar_contexto()
    principal = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento])
    secundaria = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento])
    chamado = criar_chamado(contexto, interessado=usuario(PAPEIS['servidor']), atendente=usuario(PAPEIS['atendente']), em_atendimento=True)
    chamado.resolver_chamado(usuario(PAPEIS['atendente']), [secundaria], observacao='Resolvido com a base secundária.')

    tela = Tela(logado_central('supervisor')).ir(f'{UNIFICAR}?bases={principal.pk},{secundaria.pk}')
    tela.ver_titulo('Unificar Bases de Conhecimento')
    tela.loc(f'//input[@name="base_id" and @value="{principal.pk}"]').check()
    tela.clicar_botao('Unificar bases de conhecimento')
    tela.sucesso('Bases de conhecimento unificadas com sucesso.')

    assert BaseConhecimento.objects.filter(pk=principal.pk).exists(), 'a base principal deveria continuar existindo'
    assert not BaseConhecimento.objects.filter(pk=secundaria.pk).exists(), 'a base secundária deveria ter sido apagada'
    assert HistoricoStatus.objects.filter(chamado=chamado, bases_conhecimento=principal).exists(), (
        'o histórico do chamado deveria apontar para a base principal depois da unificação'
    )


def test_supervisor_revisa_bases_em_lote(logado_central):
    """A ação em massa do admin da Base aprova vários artigos de uma vez (rota ``revisar``).

    É o caminho que o supervisor usa quando chegam vários artigos pendentes; ele limpa
    ``necessita_correcao`` **e** ``supervisao_pendente`` dos selecionados.
    """
    from centralservicos.models import BaseConhecimento

    contexto = criar_contexto()
    contexto.grupo_atendimento.atendentes.add(usuario(PAPEIS['supervisor']))
    um = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento], pendente=True)
    dois = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento], pendente=True)

    tela = Tela(logado_central('supervisor')).ir(f'{REVISAR}?bases={um.pk},{dois.pk}')
    tela.ver_titulo('Revisar Bases de Conhecimento')
    tela.loc(f'//input[@name="base_id" and @value="{um.pk}"]').check()
    tela.loc(f'//input[@name="base_id" and @value="{dois.pk}"]').check()
    tela.clicar_botao('Aprovar bases de conhecimento')
    tela.sucesso('Bases de conhecimento revisadas com sucesso.')

    assert not BaseConhecimento.objects.filter(pk__in=[um.pk, dois.pk], supervisao_pendente=True).exists(), (
        'a UI disse que revisou, mas os artigos continuam pendentes'
    )


def test_solicitante_le_artigo_publico_e_nao_le_privado(logado_central):
    """A visibilidade do artigo é fronteira de permissão: pública abre, privada dá 403 ao solicitante.

    Só o artigo público interessa ao solicitante — é ele que evita a abertura do chamado.
    """
    contexto = criar_contexto(artigo_privado=True, artigo_publico=True)
    tela = Tela(logado_central('servidor'))

    publica = tela.buscar(PUBLICA.format(contexto.artigo_publico.pk))
    assert publica.status == 200, f'a página pública do artigo deveria responder 200, veio {publica.status}'
    assert contexto.artigo_publico.titulo in publica.text(), 'o título do artigo público não está na página devolvida'

    privada = tela.buscar(PUBLICA.format(contexto.artigo_privado.pk))
    assert privada.status == 403, f'artigo privado deveria dar 403 ao solicitante, veio {privada.status}'


def test_atendente_avalia_artigo_da_base_de_conhecimento(logado_central):
    """A avaliação alimenta a média que ordena os artigos mais úteis na resolução do chamado."""
    from centralservicos.models import AvaliaBaseConhecimento, PerguntaAvaliacaoBaseConhecimento

    contexto = criar_contexto(artigo_privado=True)
    pergunta = PerguntaAvaliacaoBaseConhecimento.objects.create(area=contexto.area, titulo=nome_e2e('Pergunta'), ativo=True)

    tela = Tela(logado_central('atendente'))
    resposta = tela.buscar(AVALIAR.format(contexto.artigo_privado.pk, pergunta.pk, 5))
    assert resposta.status == 200, f'a avaliação deveria responder 200, veio {resposta.status}'
    assert resposta.json()['ok'] is True, 'a avaliação não confirmou o registro'
    assert AvaliaBaseConhecimento.objects.filter(
        base_conhecimento=contexto.artigo_privado, pergunta=pergunta, avaliado_por=usuario(PAPEIS['atendente']), nota=5
    ).exists(), 'a UI disse que avaliou, mas a nota não persistiu'


def test_artigo_mostra_chamados_resolvidos_com_ele(logado_central):
    """A tela de chamados resolvidos é o que dá contexto ao artigo: quais chamados ele já resolveu."""
    contexto = criar_contexto(artigo_privado=True)
    chamado = criar_chamado(contexto, interessado=usuario(PAPEIS['servidor']), atendente=usuario(PAPEIS['atendente']), em_atendimento=True)
    chamado.resolver_chamado(usuario(PAPEIS['atendente']), [contexto.artigo_privado], observacao='Resolvido com o artigo.')

    tela = Tela(logado_central('atendente'))
    resposta = tela.buscar(RESOLVIDOS.format(contexto.artigo_privado.pk))
    assert resposta.status == 200, f'a tela deveria responder 200, veio {resposta.status}'
    assert contexto.artigo_privado.titulo in resposta.text(), 'o título do artigo deveria abrir a tela de chamados resolvidos'
    # O template linka o chamado como `#{{ chamado.id }}` (sem o prefixo de tipo), daí a asserção
    # ser pelo href e não pelo texto do link.
    assert f'/centralservicos/chamado/{chamado.pk}/' in resposta.text(), 'o chamado resolvido com o artigo não apareceu na listagem'


def test_supervisor_remove_anexo_do_artigo(logado_central):
    """Anexo do artigo é removido pela aba Anexos; o arquivo some do artigo e o vínculo do banco."""
    from django.core.files.base import ContentFile

    from centralservicos.models import BaseConhecimentoAnexo

    contexto = criar_contexto()
    contexto.grupo_atendimento.atendentes.add(usuario(PAPEIS['supervisor']))
    artigo = criar_artigo(contexto.area, servicos=[contexto.servico], grupos=[contexto.grupo_atendimento])
    anexo = BaseConhecimentoAnexo(base_conhecimento=artigo)
    anexo.anexo.save('e2e-artigo.pdf', ContentFile(b'%PDF-1.4 e2e'), save=True)

    tela = Tela(logado_central('supervisor')).ir(f'/centralservicos/baseconhecimento/{artigo.pk}/')
    tela.ver_titulo(artigo.titulo)
    tela.clicar_aba('Anexos')
    tela.clicar_botao('Remover')
    tela.sucesso('Anexo removido com sucesso.')
    assert not BaseConhecimentoAnexo.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo continua no banco'
