"""Substrato dos e2e do eventos: nomenclatura do módulo, dois servidores com grupo e
eventos de domínio criados por ORM.

O módulo não tem mais ``features/``: o behave dele foi removido ao converter a suíte para o
**modo 2**, em que a unidade de cobertura é a rota — o gate é
``bin/scripts/paridade_e2e.py eventos --rotas`` — e a rastreabilidade de cada arquivo é a sua
docstring de módulo. A nomenclatura que era o step de setup virou ``eventos/tests/e2e/seed.py``.

Decisões deste módulo (as quatro da seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — não existe ``eventos/features/test_initial_data.py``; o replay ORM estava em
   ``eventos/features/steps/given.py`` (``os dados básicos para eventos``) e hoje é
   ``seed.dados_basicos_eventos()``. Os dois usuários saem de ``criar_servidores`` (factories,
   #17486), no campus CZN, sobre o ``semear_base()``.
2. **Papéis** — sim. O módulo é governado por grupo: ``Evento.pode_avaliar``
   (``eventos/models.py:1618``) casa o grupo do usuário com
   ``Dimensao.grupos_avaliadores_locais``, e o seed global não cria usuário com grupo
   nenhum. A criação é eager e session-scoped por causa do cache de permissão por processo
   (armadilha 3).
3. **Relógio** — NÃO congela. O critério da receita é "congele só se o domínio do módulo
   tiver data embutida no seed": o seed cria apenas nomenclatura (dimensões, tipos, portes,
   públicos, participações) — **zero campo de data** —, ao contrário dos calendários de 2019
   do edu (``edu/tests/e2e/conftest.py:28-29``). Todas as datas dos cenários são criadas pelo
   próprio teste, então elas são escritas relativas a ``date.today()`` e preservam a forma
   temporal do domínio (evento futuro no cadastro, evento já realizado na finalização).
   Consequências: dá para usar ``storage_states`` (login cacheado por papel) e não é preciso
   o aquecimento de urlconf da armadilha 4.
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``: nenhum arquivo depende do
   estado que outro produziu. Cada teste cria o seu evento (nome único com ``uuid4``),
   porque a suíte não dá flush e o CI usa ``--reuse-db`` (armadilha 8).

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest eventos/tests/e2e --reuse-db
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:  # os models só são importados dentro dos corpos (padrão dos e2e do repo)
    from eventos.models import Evento, TipoParticipante

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

# Apelido -> matrícula, para os testes não ficarem cheios de números mágicos.
PAPEIS = {'coordenador': '155001', 'avaliador': '155002'}

# Matrícula -> (nome, grupos), da tabela `os seguintes usuários` da feature 001.
SERVIDORES = {
    '155001': ('Coord Evento', ['Servidor']),
    '155002': ('Avaliador Evento', ['Secretário Acadêmico']),
}

# Prefixo de tudo que esta suíte cria. Serve de âncora para a limpeza de `eventos_seed`.
PREFIXO = 'E2E Evento'

# Rotas que não viram teste. Cada motivo é uma condição verificável no código.
#
# Todas **mudam estado por GET** (nenhuma tem ``require_POST``): visitá-las no smoke
# deferiria/ativaria/cancelaria/removeria dado do evento que as outras suítes compartilham.
# Travar um teste nelas seria endossar o comportamento — o achado vai no MR.
ROTAS_DISPENSADAS = {
    '/eventos/aceitar_convite/<int:evento_id>/<int:participante_id>/<str:hash_assinado>/': 'idem ``aceitar_convite``: altera a participação por GET a partir do link com hash.',
    '/eventos/cancelar/<int:evento_id>/': 'cancela o evento por GET.',
    '/eventos/cancelar_avaliacao/<int:evento_id>/': 'cancela a avaliação do evento por GET.',
    '/eventos/cancelar_presenca/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'cancela a presença da lista ``<str:pks>`` por GET.',
    '/eventos/confirmar_inscricao/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'confirma as inscrições da lista ``<str:pks>`` por GET.',
    '/eventos/confirmar_presenca/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'confirma a presença da lista ``<str:pks>`` por GET.',
    '/eventos/confirmar_presenca_por_link/<int:evento_id>/<int:participante_id>/': 'confirma a presença do participante por GET a partir do link enviado.',
    '/eventos/confirmar_presenca_por_link_atividade/<int:atividade_id>/<int:participante_id>/': 'confirma a presença do participante na atividade por GET a partir do link enviado.',
    '/eventos/convidar_participante/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'convida e notifica os participantes da lista ``<str:pks>`` por GET.',
    '/eventos/deferir/<int:evento_id>/': 'defere o evento e o ativa por GET (sem ``require_POST``).',
    '/eventos/desfazer_cancelamento/<int:evento_id>/': 'desfaz o cancelamento do evento por GET.',
    '/eventos/desfazer_finalizacao/<int:evento_id>/': 'desfaz a finalização do evento por GET.',
    '/eventos/enviar_avaliacao/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'envia a avaliação aos participantes da lista ``<str:pks>`` por GET.',
    '/eventos/enviar_certificados/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'emite e envia os certificados da lista ``<str:pks>`` por GET.',
    '/eventos/evento/<int:evento_id>/areastematicas/remover/<int:area_tematica_id>/': 'remove a área temática do evento por GET (``delete()``).',
    '/eventos/evento/<int:evento_id>/atividade/remover/<int:atividade_id>/': 'remove a atividade do evento por GET.',
    '/eventos/evento/<int:evento_id>/desvincular_avaliadores_automaticamente/': 'desvincula avaliadores automaticamente por GET.',
    '/eventos/evento/<int:evento_id>/internacionalizacao/remover/<int:internacionalizacao_id>/': 'remove a internacionalização do evento por GET.',
    '/eventos/evento/<int:evento_id>/log_processamento_submissao/<int:log_id>/remover/': 'remove o log de processamento da submissão por GET.',
    '/eventos/evento/<int:evento_id>/processar_avaliacoes/': 'dispara o processamento das avaliações por GET (task + mudança de estado).',
    '/eventos/evento/<int:evento_id>/processar_resultados_finais/': 'dispara o processamento dos resultados finais por GET.',
    '/eventos/evento/<int:evento_id>/processar_resultados_para_avaliacao_presencial/': 'dispara o processamento dos resultados para a avaliação presencial por GET.',
    '/eventos/evento/<int:evento_id>/tipo_participante/remover/<int:tipo_participante_id>/': 'remove o tipo de participante do evento por GET.',
    '/eventos/evento/<int:evento_id>/tipomodalidade/remover/<int:tipo_modalidade_id>/': 'remove o tipo de modalidade do evento por GET.',
    '/eventos/evento/<int:evento_id>/vincular_avaliadores_automaticamente/': 'vincula avaliadores automaticamente por GET.',
    '/eventos/finalizar/<int:evento_id>/': 'finaliza o evento por GET.',
    '/eventos/notificar_resultado_avaliacoes/<int:evento_id>/': 'notifica os autores sobre o resultado por GET.',
    '/eventos/recusar_convite/<int:evento_id>/<int:participante_id>/<str:hash_assinado>/': 'idem ``aceitar_convite``: altera a participação por GET a partir do link com hash.',
    '/eventos/reenviar_confirmacao_inscricao/<int:evento_id>/<int:participante_id>/': 'reenvia a confirmação de inscrição do participante por GET.',
    '/eventos/reenviar_credenciais_acesso/<int:evento_id>/<int:tipo_participante_id>/<str:pks>/': 'reenvia as credenciais da lista ``<str:pks>`` por GET.',
    '/eventos/remover_criterio_avaliacao/<int:criterio_avaliacao_id>/': 'remove o critério de avaliação por GET.',
    '/eventos/remover_fluxo_submissao/<int:fluxo_submissao_id>/': 'remove o fluxo de submissão por GET.',
    '/eventos/remover_foto_evento/<int:foto_id>/': 'remove a foto do evento por GET.',
    '/eventos/remover_modalidade/<int:modalidade_id>/': 'remove a modalidade do evento por GET.',
    '/eventos/remover_modalidade_avaliador/<int:avaliador_id>/': 'remove a modalidade do avaliador por GET (``delete()``).',
    '/eventos/remover_opcao_resposta/<int:opcao_resposta_id>/': 'remove a opção de resposta da pergunta de inscrição por GET.',
    '/eventos/remover_opcao_resposta_avaliacao/<int:opcao_resposta_id>/': 'remove a opção de resposta da pergunta de avaliação por GET.',
    '/eventos/remover_pergunta/<int:pergunta_id>/': 'remove a pergunta de inscrição por GET.',
    '/eventos/remover_pergunta_avaliacao/<int:pergunta_id>/': 'remove a pergunta de avaliação por GET.',
    '/eventos/remover_video_evento/<int:video_id>/': 'remove o vídeo do evento por GET.',
    '/eventos/submeter/<int:evento_id>/': 'submete o evento para avaliação por GET.',
    '/eventos/submissao/<int:submissao_id>/restaurar/': 'restaura a submissão removida por GET.',
}


def campus_eventos():
    """O campus dos eventos e dos dois servidores: ``Evento.pode_avaliar`` exige o mesmo campus."""
    return campus('CZN', 'Campus Zona Norte')


@pytest.fixture(scope='session')
def eventos_seed(e2e_seed):
    """Nomenclatura do módulo + os dois servidores da feature 001, antes da 1ª request.

    Ambos são idempotentes (``get_or_create`` / factory get-or-create pela matrícula), o que é
    obrigatório porque a suíte não dá flush e o CI usa ``--reuse-db``.

    A limpeza dos eventos da execução anterior é do mesmo tipo do ``_limpar_credito`` do edu
    (armadilha 8): sem ela, cada run deixa para trás um evento aguardando avaliação, e a
    listagem do admin (25 por página) acabaria empurrando o evento do teste para a página 2.

    Os tipos de participante saem ANTES dos eventos, e não por cascade: o ``post_delete`` de
    ``TipoParticipante`` (``eventos/signals.py:240-251``) agenda um ``on_commit`` que relê
    ``instance.evento``, e num cascade o evento já não existe na hora do commit — o delete
    estoura ``Evento.DoesNotExist`` fora do stack do próprio delete.
    """
    from eventos.models import Evento, TipoParticipante
    from eventos.tests.e2e import seed as seed_eventos

    seed_eventos.dados_basicos_eventos()
    criar_servidores(campus_eventos(), SERVIDORES)
    antigos = Evento.objects.filter(nome__startswith=PREFIXO)
    TipoParticipante.objects.filter(evento__in=antigos).delete()
    antigos.delete()


@pytest.fixture(scope='session')
def servidores_eventos(eventos_seed) -> dict:
    """``{apelido: Servidor}`` dos papéis de ``PAPEIS``, já criados por ``eventos_seed``.

    Existe para o teste falhar com "papel desconhecido" em vez de com um login em branco
    quando alguém escreve um apelido que não está na tabela.
    """
    from rh.models import Servidor

    return {papel: Servidor.objects.get(matricula=matricula) for papel, matricula in PAPEIS.items()}


@pytest.fixture
def logado_eventos(logado, servidores_eventos):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in servidores_eventos, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


def criar_evento(**campos: Any) -> Evento:
    """Cria um evento do campus CZN coordenado pelo 155001, com nome único.

    Os valores default reproduzem o evento que a feature 001 cadastra pela tela (mesma
    dimensão, classificação, porte, tipo e subtipo), com as datas escritas relativas a
    ``date.today()`` — ver a decisão 3 da docstring do módulo. ``campus`` é CZN porque
    ``Evento.pode_avaliar`` exige que o campus do evento seja o do avaliador local.
    """
    from eventos.models import ClassificacaoEvento, Dimensao, Espacialidade, Evento, PorteEvento, PublicoAlvoEvento, SubtipoEvento, TipoEvento
    from rh.models import Servidor, UnidadeOrganizacional

    hoje = date.today()
    setor = campus_eventos()
    valores: dict[str, Any] = {
        'nome': f'{PREFIXO} {uuid4().hex[:8]}',
        'apresentacao': 'Descrição do evento',
        'local': 'Local do Evento',
        'data_inicio': hoje + timedelta(days=30),
        'hora_inicio': time(8, 0),
        'data_fim': hoje + timedelta(days=40),
        'hora_fim': time(18, 0),
        'campus': UnidadeOrganizacional.objects.suap().get(setor=setor),
        'setor': setor,
        'coordenador': Servidor.objects.get(matricula=PAPEIS['coordenador']),
        'classificacao': ClassificacaoEvento.objects.get(descricao='Local'),
        'porte': PorteEvento.objects.get(descricao='Pequeno Porte'),
        'tipo': TipoEvento.objects.get(descricao='Científico/tecnológico'),
        'subtipo': SubtipoEvento.objects.get(nome='Palestras'),
        # Segundos, não o `carga_horaria_str`: é `carga_horaria` que `pode_enviar_certificado`
        # (`eventos/models.py:1668`) consulta para liberar o botão "Enviar certificado".
        'carga_horaria': 10 * 3600,
        'carga_horaria_str': '10:00',
        'gera_certificado': True,
        'submetido': True,
        'deferido': None,
        'ativo': False,
    }
    valores.update(campos)
    evento = Evento.objects.create(**valores)
    evento.dimensoes.add(Dimensao.objects.get(descricao=' Ensino'))
    evento.espacialidades.add(Espacialidade.objects.get(descricao='Ambiente Virtual'))
    evento.publico_alvo.add(PublicoAlvoEvento.objects.get(pk=PublicoAlvoEvento.PUBLICO_EXTERNO))
    return evento


def criar_tipo_participante(evento: Evento, descricao: str, **campos: Any) -> TipoParticipante:
    """Tipo de participante do evento, pela descrição da participação ('Organizador' etc.).

    Não passe ``limite_inscricoes`` sem necessidade: ``TipoParticipante.__str__``
    (``eventos/models.py:2475``) muda para "X - Limite de inscrições: N" quando ele existe,
    e é esse texto que entra na mensagem de sucesso do cadastro de participante.
    """
    from eventos.models import TipoParticipacao, TipoParticipante

    return TipoParticipante.objects.create(evento=evento, tipo_participacao=TipoParticipacao.objects.get(descricao=descricao), **campos)


@pytest.fixture
def evento_submetido(eventos_seed):
    """Evento novo, submetido e ainda sem avaliação — o estado que a feature 002 consome."""
    return criar_evento()


@pytest.fixture
def evento_deferido(eventos_seed):
    """``(evento, tipo_organizador)`` já deferido e ativo, aceitando participantes.

    Deferido e ativo é o que ``Evento.pode_gerenciar`` + ``eh_editavel`` exigem para a tela
    de participantes exibir o botão "Adicionar" — é o estado em que a feature 003 começa,
    produzido pela feature 002 no encadeamento do behave.
    """
    evento = criar_evento(deferido=True, ativo=True)
    return evento, criar_tipo_participante(evento, 'Organizador')


@pytest.fixture
def evento_realizado_com_organizador(eventos_seed):
    """``(evento, tipo, participante)`` de um evento já encerrado, com um organizador inscrito.

    ``data_fim`` no passado porque ``pode_finalizar`` e ``enviar_certificados`` dependem de
    ``estah_realizado()`` (``eventos/models.py:1388``). É assim que a feature 004 avança o
    relógio para 11/02/2020 no meio do cenário; aqui o evento já nasce encerrado, o que
    dispensa mover o relógio (e o relogin que isso exigiria).

    O participante nasce com ``inscricao_validada=True`` de propósito: é o que faz
    "Confirmar inscrição" responder "Nenhuma inscrição confirmada." (``views.py:3050``),
    a primeira asserção do cenário.
    """
    from eventos.models import Participante

    hoje = date.today()
    evento = criar_evento(deferido=True, ativo=True, data_inicio=hoje - timedelta(days=10), data_fim=hoje - timedelta(days=1))
    tipo = criar_tipo_participante(evento, 'Organizador')
    participante = Participante.objects.create(
        evento=evento,
        tipo=tipo,
        nome=f'Participante {uuid4().hex[:8]}',
        cpf='268.058.310-83',
        email='email@participante.com',
        inscricao_validada=True,
    )
    return evento, tipo, participante


@pytest.fixture
def evento_com_inscricoes_abertas(eventos_seed):
    """Evento na área pública com inscrição direta aberta hoje — o cenário da feature 005.

    Cinco condições de ``Evento.pode_inscrever`` (``eventos/models.py:1355``) precisam valer
    ao mesmo tempo, e duas janelas de inscrição diferentes: a do evento
    (``estah_em_periodo_inscricao``) e a do tipo de participante
    (``get_tipo_participacoes_area_publica``, que anota as datas do próprio
    ``TipoParticipante``). O tipo tem de ser o de participação "Participante": é por ele que
    ``tem_vagas_disponiveis`` procura.
    """
    from eventos.models import Evento, TipoParticipante

    antigos = Evento.objects.filter(nome__startswith=PREFIXO)
    TipoParticipante.objects.filter(evento__in=antigos).delete()
    antigos.delete()

    hoje = date.today()
    evento = criar_evento(
        deferido=True,
        ativo=True,
        inscricao_publica=True,
        data_inicio=hoje + timedelta(days=90),
        data_inicio_inscricoes=hoje - timedelta(days=1),
        data_fim_inscricoes=hoje + timedelta(days=1),
    )
    criar_tipo_participante(
        evento,
        'Participante',
        permite_inscricao_direta=True,
        data_inicio_inscricoes=hoje - timedelta(days=1),
        data_fim_inscricoes=hoje + timedelta(days=1),
    )
    return evento
