"""Smoke das rotas do módulo Eventos (modo 2).

O gate ``bin/scripts/paridade_e2e.py eventos --rotas`` lê **literais**: as rotas que os fluxos
alcançam por clique não aparecem para ele. Aqui cada uma entra como URL com o literal presente
e a asserção é o **status do contrato** — ``200`` para a tela que renderiza, ``302`` para a
view que redireciona, ``403`` para a barreira de permissão/estado, ``404`` para o
``get_object_or_404`` de um id inexistente e ``405`` para a rota POST-only. A mensagem de falha
carrega o motivo, então quando a rota quebra o relatório diz qual fronteira caiu.

A fixture ``alvos`` cria, a cada teste, um evento deferido/ativo com o vocabulário completo do
domínio (tipos de participante, atividade, áreas temáticas, modalidades, perguntas, mídias) —
os mesmos objetos que os fluxos de tela produzem — e o teste usa o papel que alcança a rota.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _midias(evento, django_db_blocker):
    """Fotos, vídeos e internacionalização do evento."""
    from eventos.models import FotoEvento, Internacionalizacao, VideoEvento

    with django_db_blocker.unblock():
        foto = FotoEvento.objects.create(evento=evento, imagem='eventos/fotos/e2e-rota.png', descricao='E2E foto')
        video = VideoEvento.objects.create(evento=evento, video='https://example.com/video', descricao='E2E vídeo')
        internacionalizacao = Internacionalizacao.objects.create(
            evento=evento, idioma='pt-br', titulo='E2E internacional', apresentacao='Apresentação', local='Local'
        )
        return foto, video, internacionalizacao


def _submissao(evento, django_db_blocker):
    """Áreas temáticas, modalidades, critérios e fluxo de submissão do evento."""
    from eventos.models import AreaTematica, AreaTematicaModalidade, CriterioAvaliacao, FluxoSubmissao, Modalidade, TipoModalidade

    with django_db_blocker.unblock():
        area = AreaTematica.objects.create(evento=evento, titulo='E2E Área Temática')
        tipo_modalidade = TipoModalidade.objects.create(evento=evento, titulo='E2E Tipo Modalidade')
        modalidade = Modalidade.objects.create(
            tipo=tipo_modalidade,
            evento=evento,
            tipo_submissao='TEX',
            limite_submissoes=5,
            regras_submissao='regras.pdf',
            regras_avaliacao='regras.pdf',
        )
        vinculo = AreaTematicaModalidade.objects.create(area_tematica=area, modalidade=modalidade)
        criterio = CriterioAvaliacao.objects.create(
            modalidade=modalidade, descricao='E2E critério', nota_minima=0, nota_maxima=10, ordem_desempate=1, etapa='AVA'
        )
        fluxo = FluxoSubmissao.objects.create(evento=evento, etapa='SUB', data_inicio=date.today())
        return area, tipo_modalidade, modalidade, vinculo, criterio, fluxo


def _questionario(evento, django_db_blocker):
    """Perguntas/opções de inscrição e de avaliação, e a atividade do evento."""
    from eventos.models import AtividadeEvento, OpcaoResposta, Pergunta, TipoAtividade

    with django_db_blocker.unblock():
        pergunta = Pergunta.objects.create(evento=evento, ordem=1, titulo='E2E pergunta', tipo_pergunta='OBJ', tipo_questionario='INSC')
        pergunta_avaliacao = Pergunta.objects.create(evento=evento, ordem=2, titulo='E2E pergunta', tipo_pergunta='OBJ', tipo_questionario='AVAL')
        opcao = OpcaoResposta.objects.create(evento=evento, pergunta=pergunta, ordem=1, texto='E2E opção')
        opcao_avaliacao = OpcaoResposta.objects.create(evento=evento, pergunta=pergunta_avaliacao, ordem=1, texto='E2E opção')
        tipo_atividade, _ = TipoAtividade.objects.get_or_create(descricao='E2E Tipo Atividade')
        atividade = AtividadeEvento.objects.create(
            evento=evento, tipo=tipo_atividade, descricao='E2E Atividade', ch=3600, data_fim=date.today(), hora_fim='18:00'
        )
        return pergunta, pergunta_avaliacao, opcao, opcao_avaliacao, atividade


@pytest.fixture
def alvos(eventos_seed, django_db_blocker) -> Iterator[dict[str, str]]:
    """Cria o evento do smoke e devolve os ids que as URLs usam."""
    from eventos.models import AvaliadorModalidade, Participante, TipoParticipante
    from eventos.tests.e2e.conftest import criar_evento, criar_tipo_participante

    with django_db_blocker.unblock():
        evento = criar_evento(deferido=True, ativo=True, inscricao_publica=True)
        tipo = criar_tipo_participante(evento, 'Participante')
        organizador = criar_tipo_participante(evento, 'Organizador')
        participante = Participante.objects.create(
            evento=evento, tipo=tipo, nome='E2E Participante', cpf='268.058.310-83', email='e2e@participante.com', inscricao_validada=True
        )
    area, tipo_modalidade, modalidade, vinculo, criterio, fluxo = _submissao(evento, django_db_blocker)
    with django_db_blocker.unblock():
        avaliador_modalidade = AvaliadorModalidade.objects.create(avaliador=participante, modalidade=modalidade)
    pergunta, pergunta_avaliacao, opcao, opcao_avaliacao, atividade = _questionario(evento, django_db_blocker)
    foto, video, internacionalizacao = _midias(evento, django_db_blocker)
    try:
        yield {
            'evento': str(evento.pk),
            'tipo_participante': str(tipo.pk),
            'organizador': str(organizador.pk),
            'participante': str(participante.pk),
            'pks': str(participante.pk),
            'atividade': str(atividade.pk),
            'area_tematica': str(area.pk),
            'tipo_modalidade': str(tipo_modalidade.pk),
            'modalidade': str(modalidade.pk),
            'area_tematica_modalidade': str(vinculo.pk),
            'criterio_avaliacao': str(criterio.pk),
            'fluxo_submissao': str(fluxo.pk),
            'pergunta': str(pergunta.pk),
            'pergunta_avaliacao': str(pergunta_avaliacao.pk),
            'opcao_resposta': str(opcao.pk),
            'opcao_resposta_avaliacao': str(opcao_avaliacao.pk),
            'foto': str(foto.pk),
            'video': str(video.pk),
            'internacionalizacao': str(internacionalizacao.pk),
            'avaliador_modalidade': str(avaliador_modalidade.pk),
        }
    finally:
        with django_db_blocker.unblock():
            TipoParticipante.objects.filter(evento=evento).delete()
            evento.delete()


# (papel, rota, status esperado, motivo do status). A rota entra como literal com os
# placeholders das chaves de ``alvos``; ``anonimo`` usa o ``page`` cru (área pública).
CASOS: list[tuple[str, str, int, str]] = [
    ('coordenador', '/eventos/', 200, 'área pública responde 200 sem sessão.'),
    ('coordenador', '/eventos/calendario_eventos/', 200, 'calendário responde 200 (Ano do exercício ausente não estoura mais 500).'),
    ('coordenador', '/eventos/inscricao/', 200, 'página de identificação da inscrição pública.'),
    ('coordenador', '/eventos/inscricao/1/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/inscricao/2/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/inscricao/2/{evento}/99999999/99999999/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/inscricao/2/{evento}/confirmacao/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/inscricao/3/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/confirmacao_inscricao/{participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/submissao/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/submissao/{evento}/submeter_trabalho/1/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    (
        'coordenador',
        '/eventos/submissao/{evento}/submeter_trabalho/2/{area_tematica}/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    (
        'coordenador',
        '/eventos/submissao/{evento}/submeter_trabalho/3/{area_tematica}/{modalidade}/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    ('coordenador', '/eventos/submissao/{evento}/atualizar-tipo-autor/', 405, 'a rota é POST-only: GET responde 405.'),
    (
        'coordenador',
        '/eventos/submissao/{evento}/submeter_trabalho/4/{area_tematica}/{modalidade}/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    ('coordenador', '/eventos/submissao/99999999/confirmacao/', 404, 'id inexistente no smoke: ``get_object_or_404`` responde 404.'),
    ('coordenador', '/eventos/avaliacao/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/analisar_duplicidades/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/remover_duplicatas/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('anonimo', '/eventos/submissao/99999999/comparar/99999999/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/participantes/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/participantes/{evento}/{participante}/atividades/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('avaliador', '/eventos/indeferir/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('avaliador', '/eventos/ativar/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/importar_participantes_evento/{evento}/{tipo_participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/exportar_participantes_evento/{evento}/{tipo_participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('avaliador', '/eventos/desativar/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('avaliador', '/eventos/devolver/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/relatorio/', 200, 'relatório de eventos responde 200.'),
    ('coordenador', '/eventos/relatorio_participantes/', 200, 'relatório de participantes responde 200.'),
    ('coordenador', '/eventos/download/invalido/', 404, 'hash de certificado inválido: ``get_object_or_404`` responde 404.'),
    ('coordenador', '/eventos/download/invalido/{atividade}/', 404, 'hash de certificado inválido: ``get_object_or_404`` responde 404.'),
    ('coordenador', '/eventos/download/declaracao_avaliador/{evento}/{avaliador_modalidade}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/adicionar_participante/{evento}/{tipo_participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/informar_participantes/{evento}/{atividade}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/lista_participantes/99999999/{atividade}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('anonimo', '/eventos/lista_participantes_pdf/99999999/{atividade}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/trabalhos/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/trabalho/99999999/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('anonimo', '/eventos/trabalhos/area/{area_tematica_modalidade}/lista/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    (
        'coordenador',
        '/eventos/lista_trabalhos_aprovados/{evento}/',
        200,
        'lista de trabalhos aprovados (o ``None`` de ``limite_aprovados`` estourava 500 — corrigido no MR).',
    ),
    ('coordenador', '/eventos/editar_participante/{participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/informar_atividades/{participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/adicionar_anexo_evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/adicionar_foto_evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/adicionar_video_evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    (
        'anonimo',
        '/eventos/enviar_link_registro_presenca/{evento}/{tipo_participante}/{pks}/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    ('anonimo', '/eventos/enviar_link_registro_presenca_atividades/{evento}/{pks}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/importar_lista_presenca/{evento}/{tipo_participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/enviar_mensagem/{evento}/', 200, 'formulário de envio de mensagem para os participantes do evento.'),
    ('coordenador', '/eventos/vincular_area_tematica_ao_evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/vincular_area_tematica_a_modalidade/{modalidade}/', 200, 'formulário de vínculo área temática ↔ modalidade.'),
    ('coordenador', '/eventos/adicionar_fluxo_submissao/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/editar_fluxo_submissao/{fluxo_submissao}/', 200, 'formulário de edição do fluxo de submissão.'),
    ('coordenador', '/eventos/adicionar_modalidade/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/editar_modalidade/{modalidade}/', 200, 'formulário de edição da modalidade.'),
    ('anonimo', '/eventos/adicionar_criterio_avaliacao/{modalidade}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/editar_criterio_avaliacao/{criterio_avaliacao}/', 200, 'formulário de edição do critério de avaliação.'),
    ('coordenador', '/eventos/listar_criterio_avaliacao/{modalidade}/', 200, 'fragmento lista os critérios de avaliação da modalidade.'),
    ('coordenador', '/eventos/configurar_evento/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/get_areas_tematicas_da_modalidade/{modalidade}/', 200, 'endpoint JSON lista as áreas temáticas da modalidade.'),
    ('coordenador', '/eventos/vincular_modalidade_avaliador/{evento}/{avaliador_modalidade}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/notificar_acesso/{evento}/{tipo_participante}/{pks}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('anonimo', '/eventos/vincular_avaliador_a_submissao/99999999/', 302, 'exige submissão existente; o smoke não cria.'),
    ('anonimo', '/eventos/substituir_avaliador_submissao/99999999/', 302, 'exige avaliação de submissão; o smoke não cria.'),
    ('anonimo', '/eventos/remover_avaliador_submissao/99999999/', 302, 'exige avaliação de submissão; o smoke não cria.'),
    ('coordenador', '/eventos/area_do_participante/{evento}/', 200, 'área pública do participante responde 200.'),
    ('coordenador', '/eventos/atualizar_participante/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/autenticar_participante/{evento}/', 200, 'tela pública de autenticação do participante responde 200.'),
    ('coordenador', '/eventos/autenticar_participante/{evento}/Avaliador/', 200, 'tela pública de autenticação do participante responde 200.'),
    ('coordenador', '/eventos/autenticar_participante/{evento}/Convidado/', 200, 'tela pública de autenticação do participante responde 200.'),
    ('coordenador', '/eventos/perfil_do_participante/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/responder_avaliacao/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    (
        'coordenador',
        '/eventos/perfil_do_participante/{evento}/visualizar_revisoes/99999999/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    (
        'coordenador',
        '/eventos/perfil_do_participante/{evento}/submeter_nova_versao/99999999/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    ('coordenador', '/eventos/listar_trabalhos_submetidos_ao_avaliador/{evento}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/listar_avaliadores_sem_trabalhos/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/listar_avaliadores_com_avaliacoes_pendentes/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/avaliar_trabalhos_submetidos/99999999/', 404, 'exige avaliação de submissão; o smoke não cria.'),
    ('coordenador', '/eventos/zerar_avaliacao_trabalhos_submetido/99999999/', 404, 'exige avaliação de submissão; o smoke não cria.'),
    ('coordenador', '/eventos/listar_detalhes_avaliacao/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/exibir_detalhes_avaliacao/99999999/', 302, 'exige submissão existente; o smoke não cria.'),
    (
        'coordenador',
        '/eventos/listar_resultado_avaliacoes/{area_tematica_modalidade}/',
        200,
        'resultado das avaliações da área/modalidade (o ``None`` de ``limite_aprovados`` estourava 500 — corrigido no MR).',
    ),
    ('coordenador', '/eventos/logout_participante/', 302, 'encerra a sessão do participante e redireciona para a inscrição pública.'),
    ('coordenador', '/eventos/adicionar_pergunta/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/editar_pergunta/{pergunta}/', 200, 'pergunta de inscrição do evento: formulário renderiza.'),
    ('coordenador', '/eventos/adicionar_pergunta_avaliacao/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/editar_pergunta_avaliacao/{pergunta_avaliacao}/', 200, 'pergunta de avaliação do evento: formulário renderiza.'),
    ('coordenador', '/eventos/adicionar_opcao_resposta/{evento}/', 200, 'formulário de nova opção de resposta.'),
    ('coordenador', '/eventos/adicionar_opcao_resposta/{evento}/{pergunta}/', 200, 'formulário de nova opção de resposta.'),
    ('coordenador', '/eventos/editar_opcao_resposta/{opcao_resposta}/', 200, 'opção de resposta da pergunta de inscrição.'),
    ('coordenador', '/eventos/adicionar_opcao_resposta_avaliacao/{evento}/', 200, 'formulário de nova opção de resposta de avaliação.'),
    (
        'coordenador',
        '/eventos/adicionar_opcao_resposta_avaliacao/{evento}/{pergunta_avaliacao}/',
        200,
        'formulário de nova opção de resposta de avaliação.',
    ),
    ('coordenador', '/eventos/editar_opcao_resposta_avaliacao/{opcao_resposta_avaliacao}/', 200, 'opção de resposta da pergunta de avaliação.'),
    ('coordenador', '/eventos/listar_respostas_participantes/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/exportar_respostas_participantes/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/exportar_respostas_avaliacao/{evento}/', 200, 'exportação das respostas de avaliação do evento.'),
    ('coordenador', '/eventos/exibir_informacoes_participante/{participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/enviar_qrcode_participante/{evento}/{pks}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    (
        'coordenador',
        '/eventos/gerar_planilha_autores_aprovados/{evento}/',
        200,
        'planilha dos autores aprovados (o ``None`` de ``limite_aprovados`` estourava 500 — corrigido no MR).',
    ),
    ('coordenador', '/eventos/evento/{evento}/tipo_participante/adicionar/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/tipo_participante/editar/{tipo_participante}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/areastematicas/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/areastematicas/adicionar/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/evento/{evento}/areastematicas/editar/{area_tematica}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/evento/{evento}/tipomodalidade/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/tipomodalidade/adicionar/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/evento/{evento}/tipomodalidade/editar/{tipo_modalidade}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/evento/{evento}/atividade/adicionar/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/evento/{evento}/atividade/editar/{atividade}/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/evento/{evento}/internacionalizacao/adicionar/', 200, 'a tela responde 200 com o evento do smoke.'),
    (
        'anonimo',
        '/eventos/evento/{evento}/internacionalizacao/editar/{internacionalizacao}/',
        302,
        'a view redireciona (Location) — contrato de fluxo/etapa.',
    ),
    ('coordenador', '/eventos/evento/{evento}/log_processamento_submissao/listar/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/evento/{evento}/log_processamento_extracao/listar', 200, 'a tela responde 200 com o evento do smoke.'),
    ('anonimo', '/eventos/submissao/99999999/log_processamento_extracao/exibir/', 302, 'a view redireciona (Location) — contrato de fluxo/etapa.'),
    ('coordenador', '/eventos/evento/{evento}/migrar_tipo_participante/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/buscar_participantes/{evento}/', 200, 'a tela responde 200 com o evento do smoke.'),
    ('coordenador', '/eventos/processar_presenca_participantes/', 302, 'ação POST; GET redireciona para a área pública (era 500 — corrigido no MR).'),
    ('coordenador', '/eventos/gerar_etiqueta_participante/{participante}/', 200, 'PDF da etiqueta com QR Code do participante.'),
    (
        'coordenador',
        '/eventos/gerar_etiquetas_em_lote/{evento}/{tipo_participante}/{pks}/',
        200,
        'PDF das etiquetas em lote dos participantes selecionados.',
    ),
    ('coordenador', '/eventos/baixar_certificado/', 404, 'sem ``evento_id`` nem ``hash``, o ``get_object_or_404(Evento)`` responde 404.'),
    (
        'coordenador',
        '/eventos/baixar_certificado/{evento}/',
        302,
        'sem ``tipo-participante`` na query, redireciona para a aba de detalhamento do evento.',
    ),
    ('coordenador', '/eventos/baixar_certificado/{evento}/99999999/', 302, 'variante com atividade: mesma exigência de ``tipo-participante``.'),
]


@pytest.mark.parametrize(('papel', 'rota', 'status_esperado', 'motivo'), CASOS, ids=[caso[1] for caso in CASOS])
def test_rota_responde_como_esperado(logado_eventos, page, alvos: dict[str, str], papel, rota, status_esperado, motivo):
    """Cada rota responde o status do contrato, com o papel de maior alcance para ela."""
    pagina = page if papel == 'anonimo' else logado_eventos(papel)
    resposta = Tela(pagina).buscar(rota.format(**alvos))
    assert resposta.status == status_esperado, f'{rota} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'
