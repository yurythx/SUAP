"""Smoke de rotas do ``centralservicos``: toda rota de ``urls.py`` que não está dispensada aparece
aqui como **literal** e é exercitada com uma requisição real da sessão do browser.

O gate ``bin/scripts/paridade_e2e.py centralservicos --rotas`` casa literais escritos nos
``test_*.py``; por isso os parâmetros são escritos como marcadores com nome
(``'/centralservicos/chamado/{chamado_aberto}/'``) e resolvidos com ``.format(**vars(estados))`` —
mesma forma de ``ae/tests/e2e/test_03_rotas.py`` e ``edu/tests/e2e/alvos_rotas.py``.

**Isto é um piso, não um teto**: o smoke prova que a view responde o status esperado (e onde faz
sentido, o conteúdo), mas quem cobre o comportamento dos fluxos são os arquivos ``test_0[1-5]``.
As rotas dispensadas estão em ``ROTAS_DISPENSADAS`` no conftest.

``Tela.buscar`` faz GET pela sessão do browser **sem renderizar** (sem JS/CSS) e sem seguir
redirect — o que é o certo aqui: um 302 da ``httprr`` é o desfecho esperado de uma ação de
transição, e seguir o redirect esconderia o status real. Rotas mutáveis por GET (``auto_atribuir``,
``colocar_em_atendimento``) mutam o estado do ``estados``, que é recriado por caso.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, adicionar_nivel_superior, criar_chamado, criar_contexto, nome_e2e, usuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def estados(centralservicos_seed) -> SimpleNamespace:
    """O grafo de domínio que as rotas do smoke exigem — um por caso parametrizado.

    Traz o catálogo com artigos, a estrutura em dois níveis (o que habilita Escalar/Retornar e a
    reclassificação para outro centro) e os chamados nos estados que cada rota cobra: aberto,
    atribuído-sem-atendimento, em atendimento, no grupo superior e resolvido.
    """
    from django.core.files.base import ContentFile

    from centralservicos.models import (
        BaseConhecimentoAnexo,
        Comunicacao,
        GrupoInteressado,
        Monitoramento,
        PerguntaAvaliacaoBaseConhecimento,
        Tag,
        Tarefa,
        TarefaChamado,
    )

    contexto = criar_contexto(artigo_privado=True, artigo_publico=True, permite_anexos=True)
    centro_sistemico, _ = adicionar_nivel_superior(contexto)
    atendente = usuario(PAPEIS['atendente'])
    responsavel = usuario(PAPEIS['responsavel'])
    servidor = usuario(PAPEIS['servidor'])

    chamado_aberto = criar_chamado(contexto, interessado=servidor)
    chamado_atribuido = criar_chamado(contexto, interessado=servidor)
    chamado_atribuido.atribuir_atendente(chamado_atribuido.get_atendimento_atribuicao_atual().grupo_atendimento, atendente, atendente)
    chamado_em_atendimento = criar_chamado(contexto, interessado=servidor, atendente=atendente, em_atendimento=True)
    chamado_no_superior = criar_chamado(contexto, interessado=servidor, atendente=atendente, em_atendimento=True, centro=centro_sistemico)
    chamado_resolvido = criar_chamado(contexto, interessado=servidor, atendente=atendente, em_atendimento=True)
    chamado_resolvido.resolver_chamado(atendente, [contexto.artigo_privado], observacao='Resolvido no smoke de rotas.')

    comentario = Comunicacao.objects.create(
        chamado=chamado_em_atendimento,
        remetente=servidor,
        tipo=Comunicacao.TIPO_COMENTARIO,
        texto='Comentário do smoke de rotas.',
    )
    tag = Tag.objects.create(nome=nome_e2e('Tag'), area=contexto.area)
    chamado_em_atendimento.tags.add(tag)

    grupo_interessado = GrupoInteressado.objects.create(titulo=nome_e2e('Grupo de Interessados'), grupo_atendimento=contexto.grupo_atendimento)
    grupo_interessado.interessados.add(usuario(PAPEIS['supervisor']))

    pergunta = PerguntaAvaliacaoBaseConhecimento.objects.create(area=contexto.area, titulo=nome_e2e('Pergunta'), ativo=True)

    anexo = BaseConhecimentoAnexo(base_conhecimento=contexto.artigo_privado)
    anexo.anexo.save('e2e-smoke.pdf', ContentFile(b'%PDF-1.4 e2e'), save=True)

    monitoramento = Monitoramento.objects.create(
        titulo=nome_e2e('Monitoramento'), token=nome_e2e('token').replace(' ', '-').lower()[:32], cadastrado_por=atendente
    )
    monitoramento.grupos.add(contexto.grupo_atendimento)

    tarefa = Tarefa.objects.create(servico=contexto.servico, titulo=nome_e2e('Tarefa'), descricao='Tarefa do smoke de rotas.')
    tarefa_chamado = TarefaChamado.objects.create(tarefa=tarefa, chamado=chamado_em_atendimento, responsavel=responsavel)

    return SimpleNamespace(
        area_id=contexto.area.pk,
        area_slug=contexto.area.slug,
        servico_id=contexto.servico.pk,
        centro_id=contexto.centro.pk,
        campus_id=contexto.campus.pk,
        chamado_aberto=chamado_aberto.pk,
        chamado_atribuido=chamado_atribuido.pk,
        chamado_em_atendimento=chamado_em_atendimento.pk,
        chamado_no_superior=chamado_no_superior.pk,
        chamado_resolvido=chamado_resolvido.pk,
        artigo_privado=contexto.artigo_privado.pk,
        artigo_publico=contexto.artigo_publico.pk,
        pergunta_id=pergunta.pk,
        anexo_id=anexo.pk,
        token=monitoramento.token,
        tarefa_id=tarefa.pk,
        tarefa_chamado_id=tarefa_chamado.pk,
        comentario_id=comentario.pk,
        tag_id=tag.pk,
        interessado_id=usuario(PAPEIS['supervisor']).pk,
    )


# (rota literal, papel, status esperado). Rotas de transição sem formulário respondem 302 (``httprr``);
# as POST-only com ``@require_POST`` respondem 405 a um GET — os dois desfechos são o contrato da
# rota, e é por isso que o status é afirmado em vez de um genérico "< 500".
CASOS = [
    ('/centralservicos/listar_area_servico/', 'servidor', 200),
    ('/centralservicos/selecionar_servico_abertura/{area_slug}/', 'servidor', 200),
    ('/centralservicos/abrir_chamado/{servico_id}/', 'servidor', 200),
    ('/centralservicos/indicadores/', 'atendente', 200),
    ('/centralservicos/atendimentos_por_ano/', 'atendente', 200),
    ('/centralservicos/relatorio_atendentes/', 'atendente', 200),
    ('/centralservicos/dashboard/', 'atendente', 200),
    ('/centralservicos/meus_chamados/', 'servidor', 200),
    ('/centralservicos/listar_chamados_suporte/', 'atendente', 200),
    ('/centralservicos/listar_chamados_a_fechar/', 'servidor', 200),
    ('/centralservicos/reabrir_chamado/{chamado_resolvido}/', 'servidor', 200),
    ('/centralservicos/suspender_chamado/{chamado_em_atendimento}/', 'atendente', 200),
    ('/centralservicos/escalar_atendimento_chamado/{chamado_em_atendimento}/', 'responsavel', 200),
    ('/centralservicos/retornar_atendimento_chamado/{chamado_no_superior}/', 'responsavel', 200),
    ('/centralservicos/chamado/{chamado_aberto}/', 'servidor', 200),
    ('/centralservicos/monitoramento/{token}/', 'servidor', 200),
    ('/centralservicos/baseconhecimento/', 'servidor', 200),
    ('/centralservicos/baseconhecimento/dashboard/{area_slug}/', 'servidor', 200),
    ('/centralservicos/baseconhecimento/{artigo_publico}/', 'servidor', 200),
    ('/centralservicos/baseconhecimento/publica/{artigo_publico}/', 'servidor', 200),
    ('/centralservicos/baseconhecimento/publica/{artigo_privado}/', 'servidor', 403),
    ('/centralservicos/baseconhecimento/chamados/{artigo_privado}/', 'atendente', 200),
    ('/centralservicos/baseconhecimento/avaliar/{artigo_privado}/{pergunta_id}/5/', 'atendente', 200),
    ('/centralservicos/baseconhecimento/editar_area/{artigo_privado}/', 'admin', 200),
    ('/centralservicos/baseconhecimento/marcar_para_correcao/{artigo_privado}/', 'supervisor', 200),
    ('/centralservicos/baseconhecimento/aprovar/{artigo_privado}/', 'supervisor', 302),
    ('/centralservicos/adicionar_anexo/{chamado_em_atendimento}/', 'servidor', 200),
    # `adicionar_comentario`/`adicionar_nota_interna` são endpoints de POST: o formulário vive na
    # própria página do chamado e um GET cai no ramo de erro do `ComunicacaoForm` (``httprr`` → 302).
    ('/centralservicos/adicionar_comentario/{chamado_em_atendimento}/', 'servidor', 302),
    ('/centralservicos/adicionar_nota_interna/{chamado_em_atendimento}/', 'atendente', 302),
    ('/centralservicos/adicionar_outros_interessados/{chamado_em_atendimento}/', 'servidor', 200),
    ('/centralservicos/adicionar_grupo_de_interessados/{chamado_em_atendimento}/', 'servidor', 200),
    ('/centralservicos/adicionar_tags_ao_chamado/{chamado_em_atendimento}/', 'atendente', 200),
    ('/centralservicos/remover_tag_do_chamado/{chamado_em_atendimento}/{tag_id}/', 'atendente', 200),
    ('/centralservicos/remover_outros_interessados/{chamado_em_atendimento}/{interessado_id}/', 'servidor', 200),
    ('/centralservicos/atribuir_chamado/{chamado_aberto}/', 'responsavel', 200),
    ('/centralservicos/reclassificar_chamado/{chamado_aberto}/', 'responsavel', 200),
    ('/centralservicos/cancelar_chamado/{chamado_aberto}/', 'servidor', 200),
    ('/centralservicos/fechar_chamado/{chamado_resolvido}/', 'servidor', 200),
    # O chamado do `estados` com tarefa vinculada pendente não pode ser resolvido
    # (`pode_resolver_info` → `tem_tarefas_vinculadas_pendentes`): a rota é exercitada no chamado
    # sem tarefa.
    ('/centralservicos/resolver_chamado/{chamado_no_superior}/', 'atendente', 200),
    ('/centralservicos/auto_atribuir_chamado/{chamado_aberto}/', 'atendente', 302),
    ('/centralservicos/colocar_em_atendimento/{chamado_atribuido}/', 'atendente', 302),
    ('/centralservicos/visualizar_chamados_semelhantes/{chamado_em_atendimento}/', 'atendente', 200),
    ('/centralservicos/visualizar_solucoes/{servico_id}/', 'servidor', 200),
    ('/centralservicos/visualizar_outros_chamados_do_interessado/{chamado_em_atendimento}/', 'atendente', 200),
    ('/centralservicos/estatisticas_servico/{servico_id}/', 'gestor', 200),
    ('/centralservicos/atualizar_estatisticas_servico/{servico_id}/', 'gestor', 200),
    ('/centralservicos/visualizar_tarefa/{tarefa_id}/', 'gestor', 200),
    ('/centralservicos/vincular_tarefa_chamado/{chamado_em_atendimento}/', 'atendente', 200),
    ('/centralservicos/visualizar_tarefa_chamado/{tarefa_chamado_id}/', 'responsavel', 200),
    ('/centralservicos/editar_tarefa_chamado/{tarefa_chamado_id}/', 'responsavel', 200),
    ('/centralservicos/visualizar_historico_tarefa_chamado/{tarefa_chamado_id}/', 'responsavel', 200),
    ('/centralservicos/arquivar_comentario/{comentario_id}/', 'servidor', 405),
    ('/centralservicos/desarquivar_comentario/{comentario_id}/', 'servidor', 405),
    ('/centralservicos/get_centros_atendimento_por_servico_e_campus/{servico_id}/{campus_id}/', 'atendente', 200),
    ('/centralservicos/get_centros_atendimento_por_area/{area_id}/', 'atendente', 200),
    ('/centralservicos/get_campus_com_centros_atendimento/{servico_id}/{chamado_aberto}/', 'atendente', 200),
]


@pytest.mark.parametrize(('rota', 'papel', 'status_esperado'), CASOS, ids=[caso[0] for caso in CASOS])
def test_rota_responde_como_esperado(logado_central, estados, rota, papel, status_esperado):
    """Cada rota de ``urls.py`` responde o status do contrato com o papel que tem acesso a ela."""
    tela = Tela(logado_central(papel))
    resposta = tela.buscar(rota.format(**vars(estados)))
    assert resposta.status == status_esperado, f'{rota} como {papel} respondeu HTTP {resposta.status}'


def test_endpoints_json_do_formulario_de_abertura(logado_central, estados):
    """Os três endpoints AJAX que alimentam o formulário respondem o JSON que o JS espera.

    Eles decidem quais centros e campi aparecem na abertura e na reclassificação do chamado; um
    filtro errado aqui faz a tela perder opções sem erro nenhum.
    """
    tela = Tela(logado_central('atendente'))

    centros = tela.buscar(f'/centralservicos/get_centros_atendimento_por_servico_e_campus/{estados.servico_id}/{estados.campus_id}/').json()[
        'centros'
    ]
    # `Servico.get_centros_atendimento` devolve os centros locais DO campus e os não locais de
    # qualquer campus (a segunda cláusula do `Q` da consulta): o centro sistêmico aparece mesmo
    # tendo sido criado depois e em outro "campus" de teste.
    ids = [centro[0] for centro in centros]
    assert estados.centro_id in ids, f'o centro local do campus deveria aparecer, veio {centros}'
    assert len(ids) >= 2, f'o serviço deveria oferecer mais de um centro, veio {centros}'
    assert ids[0] == estados.centro_id, f'os centros locais vêm antes dos sistêmicos na ordenação, veio {centros}'

    centros_da_area = tela.buscar(f'/centralservicos/get_centros_atendimento_por_area/{estados.area_id}/').json()['centros']
    assert estados.centro_id in [centro[0] for centro in centros_da_area], 'o centro da área não apareceu na listagem por área'

    campus = tela.buscar(f'/centralservicos/get_campus_com_centros_atendimento/{estados.servico_id}/{estados.chamado_aberto}/').json()['campus']
    assert [item[1] for item in campus] == ['CZN'], f'o serviço deveria oferecer o campus CZN, veio {campus}'
    assert campus[0][2] is True, 'o campus do próprio chamado deveria vir marcado como selecionado'
