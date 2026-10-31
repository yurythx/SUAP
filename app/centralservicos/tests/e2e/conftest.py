"""Substrato dos e2e do ``centralservicos``: os seis papéis do módulo e os estados de domínio.

O módulo não tem mais ``features/``: o behave dele foi removido depois de a paridade fechar em zero
órfãos e o pipeline do MR de geração passar verde (protocolo de deleção, #16975). A unidade de
cobertura passou a ser a **rota** — o gate é ``bin/scripts/paridade_e2e.py centralservicos --rotas`` —
e a rastreabilidade de cada arquivo é a sua docstring de módulo, não mais o marcador de cenário.

Decisões deste módulo (as quatro da seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — por factories (#17486): ``e2e_seed`` é só a base (``semear_base``) e os seis
   papéis nascem em ``centralservicos_seed`` via ``criar_servidores``, no setor ``DIAC/CZN`` do
   campus ``CZN`` (as siglas da antiga árvore do behave, que os testes citam). Nada de domínio
   vem do seed: o catálogo (área → gestor → categoria → grupo de serviço → centro → grupo de
   atendimento → serviço) é criado pelas fixtures
   abaixo, com nomes únicos (``uuid4``), porque a suíte não dá flush e o CI usa ``--reuse-db``
   (armadilha 8). A ``__str__`` dos cadastros ou é única no módulo (``CategoriaServico.nome``,
   ``GrupoServico.nome``, ``Servico.nome``) ou é a chave de um ``unique_together``
   (``CentroAtendimento``), então nome fixo colidiria na segunda execução.
2. **Papéis** — sim, os seis do módulo (nome, matrícula e grupo, como na antiga tabela do
   behave). O módulo é governado por grupo (``permissions.yaml``) e a base não cria usuário com
   grupo nenhum; a criação é eager e session-scoped por causa do cache de permissão por processo (armadilha 3). O grupo de cada
   usuário é atribuído no seed, mas o grupo da área (``Gestor da Central de Serviços`` via
   ``GestorAreaServico``) também é concedido pelo signal ``adiciona_grupo_gestor_area_servico``.
3. **Relógio** — NÃO congela: nenhum dado do seed tem data, e as do chamado são
   ``auto_now_add``/``timezone.now()`` do próprio teste. Consequências: dá para usar
   ``storage_states`` (login cacheado por papel) e não é preciso o aquecimento de urlconf da
   armadilha 4.
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``: cada teste cria o próprio
   estado. A cadeia que o behave descrevia (cada cenário herdava a área, o grupo e o serviço do
   anterior) virou uma **escada de fixtures de domínio**, não uma ordem de execução entre testes:
   onde o fluxo de origem exercita a tela, o objeto sob teste nasce pela tela; onde ele só **consome**
   um estado (a categoria que o grupo de serviço referencia, o centro que o grupo de atendimento
   exige), o estado nasce por ORM, que é o que mantém os testes independentes.

``ROTAS_DISPENSADAS`` fecha o ``--rotas`` — o gate deste módulo desde a remoção do behave. Rodar
(invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest centralservicos/tests/e2e --reuse-db

E o gate::

    python bin/scripts/paridade_e2e.py centralservicos --rotas
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from django.db.models import Q

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from centralservicos.models import BaseConhecimento, CentroAtendimento, Chamado, GrupoAtendimento, GrupoServico, Servico, Tarefa
    from comum.models import AreaAtuacao
    from rh.models import UnidadeOrganizacional

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor

# Prefixo de tudo que esta suíte cria. É a chave da limpeza do seed de sessão (armadilha 8) e o
# que impede o cruzamento com os cadastros das outras suítes do banco (doc, outros módulos).
PREFIXO = 'E2E Central'

# Apelido -> matrícula. O apelido é o papel do cenário; a matrícula, o que os testes usam.
PAPEIS = {
    'admin': '104001',
    'gestor': '104002',
    'responsavel': '104003',
    'supervisor': '104004',
    'atendente': '104005',
    'servidor': '104006',
}

# Matrícula -> (nome, grupos), da tabela `os seguintes usuários` da feature 001.
SERVIDORES = {
    '104001': ('Administrador da Central', ['centralservicos Administrador']),
    '104002': ('Gestor da Central', ['Gestor da Central de Serviços']),
    '104003': ('Responsável Grupo Atendimento', ['Atendente da Central de Serviços']),
    '104004': ('Supervisor da Base de Conhecimento', ['Supervisor da Base de Conhecimento']),
    '104005': ('Atendente da Central', ['Atendente da Central de Serviços']),
    '104006': ('Servidor da Central', ['Servidor']),
}

# Rotas que não viram teste. Cada motivo é uma condição verificável no código; as demais rotas
# de `urls.py` aparecem como literal nos testes (ver a docstring de `test_06_rotas.py`).
ROTAS_DISPENSADAS = {
    '/centralservicos/criar_processo_de_chamado/<int:chamado_id>/': (
        'exige `processo_eletronico.add_processo` além de ser o atendente do chamado Em Atendimento '
        '(`Chamado.pode_criar_processo`, models.py:2187) — permissão de outro app que o `centralservicos/permissions.yaml` '
        'não concede a nenhum grupo do módulo, e que o e2e teria de fabricar à mão. O corpo ainda gera o extrato do '
        'chamado em PDF (`generate_pdf`) e delega ao `CriarProcessoComTramiteForm`, com efeito assíncrono no outro módulo.'
    ),
    '/centralservicos/editar_patrimonio_relacionado/<int:chamado_id>/': (
        'só responde a chamado de serviço com `requer_numero_patrimonio=True` e para quem atende/abriu/requisitou '
        '(`Chamado.pode_editar_patrimonio_relacionado`, models.py:2464); o formulário vincula um '
        '`patrimonio.Inventario`, cuja árvore (complexo, conta, fornecedor) só a suíte do `patrimonio` monta — sem ela a '
        'tela renderizaria um seletor vazio, sem exercitar o que a rota existe para fazer.'
    ),
}


@dataclass
class Contexto:
    """O catálogo mínimo de uma área de serviço, para os testes que precisam dele pronto."""

    campus: UnidadeOrganizacional
    area: AreaAtuacao
    categoria: object
    grupo_servico: GrupoServico
    centro: CentroAtendimento
    grupo_atendimento: GrupoAtendimento | None = None
    servico: Servico | None = None
    artigo_privado: BaseConhecimento | None = None
    artigo_publico: BaseConhecimento | None = None


@pytest.fixture(scope='session')
def centralservicos_seed(e2e_seed):
    """Os seis usuários do módulo + a limpeza dos cadastros que a execução anterior deixou.

    Criados antes de qualquer request (cache de permissão por processo) e idempotentes
    (``ServidorFactory`` é get-or-create pela matrícula). A limpeza é do mesmo tipo do
    ``_limpar_credito`` do edu (armadilha 8): sem ela, cada run acumula áreas, serviços e chamados
    e as telas de listagem do admin iriam empurrando os registros do teste para a página 2 — e o
    indicador "Não Atribuídos" do Dashboard contaria as sobras.
    """
    criar_servidores(setor('DIAC/CZN', campus('CZN', 'Campus Zona Norte'), 'Diretoria Acadêmica'), SERVIDORES)
    _limpar_dados_e2e()


@pytest.fixture
def logado_central(logado, centralservicos_seed):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def contexto(centralservicos_seed) -> Contexto:
    """Catálogo novo (área, categoria, grupo de serviço, centro, grupo de atendimento, serviço).

    Sem artigos de propósito: é o estado em que ``visualizar_solucoes`` manda o solicitante direto
    para a abertura do chamado (o serviço não tem FAQ pública), que é o caminho da abertura de chamado
    do servidor.
    """
    return criar_contexto()


@pytest.fixture
def contexto_com_artigos(centralservicos_seed) -> Contexto:
    """O mesmo catálogo, com um artigo privado (para resolver chamado) e um público (FAQ)."""
    return criar_contexto(artigo_privado=True, artigo_publico=True, permite_anexos=True)


@pytest.fixture
def contexto_com_anexos(centralservicos_seed) -> Contexto:
    """Catálogo com ``permite_anexos=True`` e sem artigos — serviço que aceita arquivo na abertura."""
    return criar_contexto(permite_anexos=True)


@pytest.fixture
def chamado_aberto(contexto_com_artigos) -> Chamado:
    """Chamado do servidor, aberto pela tela, roteado ao grupo de primeiro nível do catálogo."""
    return criar_chamado(contexto_com_artigos, interessado=usuario(PAPEIS['servidor']))


@pytest.fixture
def chamado_em_atendimento(contexto_com_artigos) -> Chamado:
    """Chamado já atribuído ao atendente e Em Atendimento — o estado de partida do encaminhamento."""
    return criar_chamado(
        contexto_com_artigos,
        interessado=usuario(PAPEIS['servidor']),
        atendente=usuario(PAPEIS['atendente']),
        em_atendimento=True,
    )


@pytest.fixture
def chamado_nao_atribuido(contexto_com_artigos) -> tuple[Chamado, int]:
    """``(chamado, não_atribuídos_antes)``: o chamado novo e o indicador do Dashboard antes dele.

    O valor de antes é lido da mesma consulta que o Dashboard usa (``incidentes_nao_atribuidos``)
    **antes** de o chamado existir, para o teste afirmar o delta que ele mesmo produziu em vez de
    uma contagem global do banco compartilhado.
    """
    atendente = usuario(PAPEIS['atendente'])
    antes = incidentes_nao_atribuidos(atendente)
    chamado = criar_chamado(contexto_com_artigos, interessado=usuario(PAPEIS['servidor']))
    return chamado, antes


@pytest.fixture
def chamado_resolvido(contexto_com_artigos) -> Chamado:
    """Chamado resolvido pelo atendente com o artigo privado — o estado de partida do fechamento."""
    chamado = criar_chamado(
        contexto_com_artigos,
        interessado=usuario(PAPEIS['servidor']),
        atendente=usuario(PAPEIS['atendente']),
        em_atendimento=True,
    )
    chamado.resolver_chamado(usuario(PAPEIS['atendente']), [contexto_com_artigos.artigo_privado], observacao='Resolvido no e2e.')
    return chamado


@pytest.fixture
def tarefa(contexto_com_artigos) -> Tarefa:
    """Tarefa de catálogo do serviço, criada por ORM (o cadastro pela tela é o teste dela)."""
    from centralservicos.models import Tarefa

    return Tarefa.objects.create(
        servico=contexto_com_artigos.servico,
        titulo=nome_e2e('Tarefa'),
        descricao='Conferir o estado da impressora antes de acionar a assistência.',
    )


def usuario(matricula: str) -> User:
    """O ``User`` do servidor daquela matrícula (criado pelo ``centralservicos_seed``)."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.get(username=matricula)


def nome_e2e(prefixo: str) -> str:
    """Nome único e reconhecível de cadastro — ``CategoriaServico``/``Servico`` são únicos."""
    return f'{PREFIXO} {prefixo} {uuid4().hex[:8]}'


def criar_contexto(
    *,
    com_grupo_de_atendimento: bool = True,
    com_servico: bool = True,
    artigo_privado: bool = False,
    artigo_publico: bool = False,
    permite_anexos: bool = False,
    requer_numero_patrimonio: bool = False,
) -> Contexto:
    """Cria o catálogo de uma área de serviço nova e devolve o contexto.

    Reproduz, por ORM, o que os cadastros do módulo criam pela tela — a mesma cadeia (área → gestor →
    categoria → grupo de serviço → centro → grupo de atendimento → serviço), sem as telas: quem as
    exercita é ``test_01_cadastros.py``. O gestor entra como atendente do grupo porque a Base de
    Conhecimento do admin só oferece as áreas dos grupos de atendimento do usuário
    (``GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento``), que é como ele fica depois de
    vinculado ao grupo pela tela.
    """
    from centralservicos.models import CategoriaServico, CentroAtendimento, GrupoAtendimento, GrupoServico, GestorAreaServico, Servico
    from comum.models import AreaAtuacao
    from rh.models import UnidadeOrganizacional

    campus = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    area = AreaAtuacao.objects.create(nome=nome_e2e('Área'), icone='wrench', ativo=True)
    GestorAreaServico.objects.create(gestor=usuario(PAPEIS['gestor']), area=area)

    categoria = CategoriaServico.objects.create(nome=nome_e2e('Categoria'), area=area)
    grupo_servico = GrupoServico.objects.create(
        nome=nome_e2e('Grupo de Serviço'),
        detalhamento='Serviço de impressão e digitalização de documentos.',
        icone='list',
    )
    grupo_servico.categorias.add(categoria)

    centro = CentroAtendimento.objects.create(nome=nome_e2e('Centro Local'), eh_local=True, area=area, ativo=True)

    contexto = Contexto(campus=campus, area=area, categoria=categoria, grupo_servico=grupo_servico, centro=centro)

    grupo_atendimento = None
    if com_grupo_de_atendimento:
        grupo_atendimento = GrupoAtendimento.objects.create(
            nome=nome_e2e('Grupo de Atendimento'), campus=campus, centro_atendimento=centro, ativo=True
        )
        grupo_atendimento.responsaveis.add(usuario(PAPEIS['responsavel']))
        grupo_atendimento.atendentes.add(usuario(PAPEIS['atendente']), usuario(PAPEIS['responsavel']))
        contexto.grupo_atendimento = grupo_atendimento

    if not com_servico:
        return contexto

    servico = Servico.objects.create(
        nome=nome_e2e('Serviço'),
        tipo=Servico.TIPO_INCIDENTE,
        area=area,
        grupo_servico=grupo_servico,
        texto_modelo='Por favor, informar o número do equipamento impresso na etiqueta.',
        sla_utilizado=Servico.SLA_MANUAL,
        sla_manual=12,
        permite_anexos=permite_anexos,
        requer_numero_patrimonio=requer_numero_patrimonio,
        ativo=True,
    )
    servico.centros_atendimento.add(centro)
    contexto.servico = servico

    if artigo_privado:
        from centralservicos.models import BaseConhecimento

        assert grupo_atendimento is not None, 'artigo com grupo de atendimento exige a flag com_grupo_de_atendimento'
        contexto.artigo_privado = criar_artigo(
            area,
            servicos=[servico],
            grupos=[grupo_atendimento],
            visibilidade=BaseConhecimento.VISIBILIDADE_PRIVADA,
        )
    if artigo_publico:
        from centralservicos.models import BaseConhecimento

        assert grupo_atendimento is not None, 'artigo com grupo de atendimento exige a flag com_grupo_de_atendimento'
        contexto.artigo_publico = criar_artigo(
            area,
            servicos=[servico],
            grupos=[grupo_atendimento],
            visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA,
        )
    return contexto


def adicionar_nivel_superior(contexto: Contexto) -> tuple[CentroAtendimento, GrupoAtendimento]:
    """Cria o centro e o grupo de nível superior e aponta o grupo local para ele.

    É o degrau que habilita Escalar/Retornar (``Chamado.pode_escalar``/``pode_retornar``) e o
    destino da reclassificação para o centro sistêmico: o chamado roteia para o grupo do centro
    escolhido, e o grupo local deixa de ser "primeiro nível" quando tem um superior ativo.
    """
    from centralservicos.models import CentroAtendimento, GrupoAtendimento

    centro = CentroAtendimento.objects.create(nome=nome_e2e('Centro Sistêmico'), eh_local=False, area=contexto.area, ativo=True)
    grupo = GrupoAtendimento.objects.create(nome=nome_e2e('Grupo Sistêmico'), campus=contexto.campus, centro_atendimento=centro, ativo=True)
    grupo.responsaveis.add(usuario(PAPEIS['responsavel']))
    grupo.atendentes.add(usuario(PAPEIS['atendente']), usuario(PAPEIS['responsavel']))
    assert contexto.grupo_atendimento is not None, 'a estrutura em níveis exige o grupo local'
    contexto.grupo_atendimento.grupo_atendimento_superior = grupo
    contexto.grupo_atendimento.save()
    # O centro novo precisa estar entre os centros do serviço: a reclassificação só oferece os
    # centros do próprio serviço (``ReclassificarChamadoFormFactory``) e o roteamento do chamado
    # depende do grupo de primeiro nível do centro escolhido.
    assert contexto.servico is not None, 'a estrutura em níveis exige o serviço'
    contexto.servico.centros_atendimento.add(centro)
    return centro, grupo


def criar_artigo(
    area: AreaAtuacao,
    *,
    servicos: list | None = None,
    grupos: list | None = None,
    visibilidade: str | None = None,
    pendente: bool = False,
) -> BaseConhecimento:
    """Artigo de Base de Conhecimento na área, com título único.

    Criado com ``atualizado_por`` = gestor (que tem ``add_active_baseconhecimento``), logo nasce
    publicado; ``pendente=True`` força "Supervisão pendente" por ``update``, que é o estado do
    artigo que o supervisor aprova.
    """
    from centralservicos.models import BaseConhecimento

    base = BaseConhecimento(
        area=area,
        titulo=nome_e2e('Artigo'),
        resumo='A impressora indica atolamento de papel mesmo sem papel preso.',
        solucao='Verifique e remova o papel atolado da bandeja.',
        ativo=True,
        visibilidade=visibilidade or BaseConhecimento.VISIBILIDADE_PRIVADA,
        atualizado_por=usuario(PAPEIS['gestor']),
    )
    base.save()
    if servicos:
        base.servicos.add(*servicos)
    if grupos:
        base.grupos_atendimento.add(*grupos)
    if pendente:
        BaseConhecimento.objects.filter(pk=base.pk).update(supervisao_pendente=True)
        base.refresh_from_db()
    return base


def criar_chamado(
    contexto: Contexto,
    *,
    interessado: User,
    atendente: User | None = None,
    em_atendimento: bool = False,
    descricao: str | None = None,
    centro: CentroAtendimento | None = None,
) -> Chamado:
    """Chamado do contexto, roteado ao grupo de primeiro nível; opcionalmente já em atendimento.

    ``Chamado.save()`` cria a ``AtendimentoAtribuicao`` e o ``HistoricoStatus`` iniciais, e é o
    ``centro_atendimento`` (atributo de instância, não campo) que decide o grupo — por isso ele é
    preenchido antes do save, como a view de abertura faz.
    """
    from centralservicos.models import Chamado

    chamado = Chamado(
        descricao=descricao or f'Chamado de teste e2e {uuid4().hex[:8]}',
        servico=contexto.servico,
        aberto_por=interessado,
        requisitante=interessado,
        interessado=interessado,
        campus=contexto.campus,
        meio_abertura=Chamado.MEIO_ABERTURA_WEB,
    )
    chamado.centro_atendimento = centro or contexto.centro
    chamado.save()
    if em_atendimento:
        assert atendente is not None, 'chamado em atendimento exige atendente'
        grupo = chamado.get_atendimento_atribuicao_atual().grupo_atendimento
        chamado.atribuir_atendente(grupo, atendente, atendente)
        chamado.colocar_em_atendimento(atendente)
    return chamado


def incidentes_nao_atribuidos(user: User) -> int:
    """O mesmo número que o Dashboard mostra em "Chamados de Incidentes > Não Atribuídos".

    Duplica de propósito o filtro de ``dashboard()`` (views.py:1257-1276) para o teste afirmar o
    **delta** que o próprio chamado produziu — nunca a contagem global, que o banco compartilhado
    torna imprevisível. O ``meus_grupos_com_servicos_ou_chamados_ativos`` do dashboard devolve os
    mesmos grupos que o ``meus_grupos`` daqui para o caso em teste: um grupo só fica de fora se não
    tiver serviço ativo **nem** chamado ativo, e aí também não contribui para a contagem.
    """
    from centralservicos.models import AtendimentoAtribuicao, Chamado, GrupoAtendimento, Servico

    grupos = GrupoAtendimento.objects.filter(Q(atendentes=user) | Q(responsaveis=user))
    atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__in=grupos, cancelado_em__isnull=True, atribuido_para__isnull=True)
    return Chamado.ativos.filter(pk__in=atendimentos.values('chamado'), servico__tipo=Servico.TIPO_INCIDENTE).count()


def ver_campos(tela, nomes: list[str]) -> None:
    """Afirma que cada campo está rotulado na tela (o passo ``vejo os seguintes campos``).

    Compara por prefixo porque o rótulo renderizado ganha dois-pontos quando o campo não termina em
    pontuação (``Descrição`` → ``Descrição:``) — mesma normalização de ``djtools/e2e_ui.py:_rotulo``.
    """
    rotulos = tela.rotulos_na_tela()
    for nome in nomes:
        assert any(rotulo.startswith(nome) for rotulo in rotulos), f'campo {nome!r} não está na tela. Rótulos: {rotulos}'


def postar(pagina, url: str, dados: dict | None = None):
    """POST pela sessão do browser, com o CSRF do cookie — para as rotas POST-only.

    ``pagina.request`` é o ``APIRequestContext`` do mesmo contexto: compartilha cookies e
    permissões. O token vai no header ``X-CSRFToken`` porque o ``APIRequestContext`` não preenche o
    campo oculto de um formulário que nunca renderizou; o ``Referer`` é o que vistas de transição
    usam para voltar à tela de origem (``auto_atribuir_chamado``).

    Não segue o redirect de propósito (``max_redirects=0``), como o ``Tela.buscar``: a mensagem de
    sucesso do ``httprr`` é enfileirada na sessão e renderizada na **próxima** página. Seguindo o
    redirect aqui, o ``APIRequestContext`` consumiria a mensagem numa renderização que o teste não
    vê, e o ``tela.sucesso()`` seguinte falharia com "banners: 0". Quem chama afirma o 302, faz o
    ``tela.ir`` e aí vê a mensagem.
    """
    token = next(cookie['value'] for cookie in pagina.context.cookies() if cookie['name'] == 'csrftoken')
    return pagina.request.post(url, form=dados or {}, headers={'X-CSRFToken': token, 'Referer': pagina.url}, max_redirects=0)


def _limpar_dados_e2e() -> None:
    """Apaga só o que esta suíte cria (prefixo ``E2E Central``), na ordem das dependências.

    A ``ÁreaAtuacao`` está no topo do grafo (serviço, centro, categoria, artigo e tag apontam para
    ela com ``CASCADE``), mas o ``GrupoServico`` não: ele só se liga à área por M2M com a
    categoria, então precisa da própria remoção.
    """
    from centralservicos.models import (
        CategoriaServico,
        Chamado,
        GrupoAtendimento,
        GrupoInteressado,
        GrupoServico,
        Monitoramento,
        PerguntaAvaliacaoBaseConhecimento,
        Servico,
        Tag,
        Tarefa,
    )
    from comum.models import AreaAtuacao

    # `Chamado.ativos` não serve aqui: a limpeza tem de alcançar também resolvido/fechado/cancelado.
    Chamado.objects.filter(servico__nome__startswith=PREFIXO).delete()
    Tarefa.objects.filter(titulo__startswith=PREFIXO).delete()
    Monitoramento.objects.filter(titulo__startswith=PREFIXO).delete()
    GrupoInteressado.objects.filter(titulo__startswith=PREFIXO).delete()
    PerguntaAvaliacaoBaseConhecimento.objects.filter(titulo__startswith=PREFIXO).delete()
    GrupoAtendimento.objects.filter(nome__startswith=PREFIXO).delete()
    AreaAtuacao.objects.filter(nome__startswith=PREFIXO).delete()
    GrupoServico.objects.filter(nome__startswith=PREFIXO).delete()
    CategoriaServico.objects.filter(nome__startswith=PREFIXO).delete()
    Servico.objects.filter(nome__startswith=PREFIXO).delete()
    Tag.objects.filter(nome__startswith=PREFIXO).delete()
