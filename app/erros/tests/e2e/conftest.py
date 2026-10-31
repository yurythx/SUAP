"""Substrato dos e2e do erros: os servidores das features e os erros de domínio por ORM.

Decisões deste módulo (as quatro da seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — por factories (#17486): ``semear_base()`` e os servidores de ``SERVIDORES`` via
   ``servidor_com_login``, lotados no campus CEN. O seed do behave que esta suíte substituiu criava também um
   *aluno* interessado, e para isso disparava a cadeia de seed do ``edu``
   (``edu.tests.e2e.seed.step_cadastros_feature_002``) — cara, e nenhum teste desta suíte loga
   com esse aluno. Se um teste novo precisar de aluno, é essa conta que ele reabre.
2. **Papéis** — sim, e é o que separa os três lados do fluxo. As três permissões do módulo
   moram em grupo, não em ``permissions.yaml``, e o seed global não cria usuário com grupo
   nenhum:

   * ``Erro.vinculo_pode_ser_atendente`` (``erros/models.py:139``) é literalmente
     ``in_group(user, 'Analista')`` — daí ``atendente`` e ``atendente_auxiliar``;
   * ``pode_atribuir``/``pode_unificar``/``pode_cancelar_por_erro_de_abertura``
     (``erros/models.py:174-210``) são ``in_group(user, 'Recebedor de Demandas')`` — daí
     ``gerente``, que **não** é Analista de propósito: pôr os dois grupos no mesmo usuário o
     tornaria candidato do próprio ``AtribuirErroForm`` (``erros/forms.py:275``) e ligaria
     ``pode_comentar``/``pode_ver_comentarios``, embaralhando o que os testes de triagem e os
     de negativa de permissão afirmam;
   * ``pode_comentar`` exige ser interessado **ou** Analista — daí ``interessado``.

   A criação é eager e session-scoped por causa do cache de permissão por processo
   (armadilha 3).
3. **Relógio** — NÃO congela. O behave posicionava o relógio em 10/03/2021 só porque o replay
   do ``edu`` exige ano letivo; o domínio de erros não tem data no seed — as únicas datas são
   ``auto_now_add``. Logo dá para usar ``storage_states`` (login cacheado por papel) e não é
   preciso o aquecimento de urlconf da armadilha 4.
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``. Cada teste cria o seu erro
   (URL única com ``uuid4``), porque a suíte não dá flush e o CI usa ``--reuse-db``
   (armadilha 8).

Duas views diferentes de propósito (ver ``VIEW_ABERTURA``/``VIEW_ORM``): a tela de abertura
decide entre o formulário e a lista de "erros similares" olhando se já existe erro aberto
para a mesma view (``erros/views.py:238-243``), então os erros que os outros testes criam por
ORM não podem morar na view que o teste de abertura exercita. **Nenhum teste novo pode
reportar erro sobre ``VIEW_ABERTURA``**: o erro sobreviveria ao teste (a suíte não dá flush) e
mandaria ``test_reportar_erro.py`` para o ramo dos similares em silêncio.

O gate deste módulo, agora que ``erros/features/`` não existe mais (removida depois de a
paridade fechar em 0 órfãos e a suíte rodar 21/21 em duas execuções consecutivas)::

    python bin/scripts/paridade_e2e.py erros --rotas                              # modo 2

A unidade de cobertura passa a ser a rota, e cada teste se rastreia pela docstring de módulo.
Como o gate de rota casa **literal** escrito no teste,
toda rota com parâmetro é escrita como constante com marcador (``'/erros/erro/{}/'``) e
resolvida com ``.format`` — mesma forma de ``edu/tests/e2e/alvos_rotas.py``.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest erros/tests/e2e --reuse-db
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:  # os models só são importados dentro dos corpos (padrão dos e2e do repo)
    from comum.models import Vinculo
    from erros.models import Erro

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

# Apelido -> matrícula, para os testes não ficarem cheios de números mágicos.
PAPEIS = {'interessado': '103013', 'atendente': '103011', 'atendente_auxiliar': '103012', 'gerente': '103015'}

# Matrícula -> (nome, grupos). Os nomes vêm do seed do behave que esta suíte substituiu. O
# `gerente` é o único que não vem do `given.py` do behave: nenhum cenário das duas features
# exercita a triagem (atribuir/unificar/cancelar por erro de abertura), que é o lado
# "Recebedor de Demandas" do módulo. A matrícula segue a numeração do módulo (103014 é o
# aluno interessado do behave, que esta suíte não cria).
SERVIDORES: dict[str, tuple[str, list[str]]] = {
    '103011': ('Atendente Principal do Erro', ['Servidor', 'Analista']),
    '103012': ('Atendente Secundário do Erro', ['Servidor', 'Analista']),
    '103013': ('Servidor Interessado no Erro', ['Servidor']),
    '103015': ('Gerente de Erros', ['Servidor', 'Recebedor de Demandas']),
}


# A view do erro que o fluxo de ABERTURA produz: o cenário reporta a partir de "/", que
# `resolve()` leva a `comum.views.index` (`suap/urls.py:24`).
VIEW_ABERTURA = 'comum.views.index'

# A view dos erros criados por ORM. Precisa ser OUTRA (ver docstring do módulo) e continuar
# no módulo `comum`, porque a listagem por área/módulo dos cenários passa por "Comum".
URL_ORM = 'http://localhost:8000/comum/temas/'
VIEW_ORM = 'comum.views.temas'

# Terceira view: o destino dos erros que a suíte MOVE para fora de `VIEW_ORM` — o de
# `test_erro_atendente` (que troca a URL) e o de `test_erro_por_chamado` (que nasce nela). Ela
# existe para que `VIEW_ORM` só tenha erros informados pelo papel `interessado`: é essa
# exclusividade que deixa `test_navegacao` afirmar qual das duas listas de similares NÃO
# aparece para cada papel.
VIEW_SECUNDARIA = 'comum.views.acessibilidade'
URL_SECUNDARIA = 'http://localhost:8000/comum/acessibilidade/'

# Gate do modo 2 (`paridade_e2e.py erros --rotas`). Cada motivo é uma condição verificável no
# código, não uma dificuldade: as duas primeiras rotas não têm tela que possa ser afirmada
# neste ambiente.
ROTAS_DISPENSADAS = {
    '/erros/reportar_erro_500/': (
        'só é alcançável pelo formulário da tela 500 customizada (`comum/views.py:3659` + `comum/templates/500.html`), '
        'que o Django só usa quando `DEBUG=False` — e o e2e roda com DEBUG=True obrigatoriamente '
        '(`suap/settings_test.py:63` e `djtools/e2e_fixtures.py:327`, sem o que o pipeline referencia bundles '
        'inexistentes e o JS não carrega). Além disso o corpo da view é integração com o Sentry, e sem `sentry_url` em '
        '`Configuracao` ela faz 20 tentativas com `sleep(1)` (`erros/views.py:155-165`): 20 s por chamada.'
    ),
    '/erros/exception/': (
        'endpoint de fumaça do Sentry: levanta exceção de propósito e devolve `handler500` com status 500 '
        '(`erros/views.py:677-688`). Não há tela nem fato positivo a afirmar — e fora de DEBUG a rota nem é registrada '
        '(`erros/urls.py:24`), de modo que em produção ela não existe.'
    ),
    '/erros/exception/<int:pk>/': (
        'mesma view de `/erros/exception/` com um pk que ela ignora (`erros/views.py:677`): levanta exceção de '
        'propósito, devolve 500 e fora de DEBUG não é registrada.'
    ),
}


@pytest.fixture(scope='session')
def erros_seed(e2e_seed):
    """Os servidores com papel, criados antes da primeira request (idempotente: a suíte não
    dá flush e o CI usa ``--reuse-db``).

    A limpeza é do mesmo tipo do ``_limpar_credito`` do edu (armadilha 8), mas a chave é a
    **view** e não o informante: ``reportar_erro`` (``erros/views.py:238-243``) decide entre
    mostrar o formulário e mostrar a lista de "erros similares" perguntando se existe
    QUALQUER erro não finalizado com aquela view. Um erro deixado pela execução anterior
    — de quem quer que seja — mandaria o teste de abertura para o outro ramo em silêncio.

    ``VIEW_SECUNDARIA`` entra na limpeza pelo mesmo motivo, e conserta um vazamento: os erros
    que ``test_erro_atendente`` move para lá (ao trocar a URL) sobreviviam a toda execução,
    porque a limpeza só conhecia as duas primeiras views.
    """
    from erros.models import Erro

    criar_servidores(campus('CEN', 'Campus Central'), SERVIDORES)
    Erro.objects.filter(view__in=(VIEW_ABERTURA, VIEW_ORM, VIEW_SECUNDARIA)).delete()


@pytest.fixture(scope='session')
def vinculos_erros(erros_seed) -> dict:
    """``{apelido: Vinculo}`` dos papéis de ``PAPEIS``. É o vínculo, não o usuário, que o
    domínio de erros usa em toda parte (informante, interessado, atendente)."""
    from rh.models import Servidor

    return {papel: Servidor.objects.get(matricula=matricula).get_vinculo() for papel, matricula in PAPEIS.items()}


@pytest.fixture
def logado_erros(logado, vinculos_erros):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in vinculos_erros, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


def criar_erro(informante: Vinculo, **campos: Any) -> Erro:
    """Erro novo, reportado por ``informante``, com URL única e situação "Reportado".

    Usa ``Erro.criar()`` e não ``objects.create()``: é ele que registra o informante como
    interessado (``erros/models.py:107-114``), sem o que ``pode_comentar`` é falso e a
    linha do tempo nem renderiza o formulário de interação.

    A URL leva um ``uuid4`` porque é ela que aparece na listagem do admin, e é por ela que os
    testes recortam a própria linha — nome fixo colidiria entre execuções (armadilha 8).
    """
    from erros.models import Erro

    marca = uuid4().hex[:8]
    valores: dict[str, Any] = {
        'descricao': f'O quadro de erros não está sendo exibido. (e2e {marca})',
        'url': f'{URL_ORM}?e2e={marca}',
        'view': VIEW_ORM,
        'informante': informante,
        'agent': 'e2e',
        'ip_address': '127.0.0.1',
    }
    valores.update(campos)
    erro = Erro(**valores)
    erro.criar()
    return erro


@pytest.fixture
def erro_aberto(vinculos_erros) -> Erro:
    """Erro recém-reportado pelo interessado, sem atendente — o estado em que a feature 001
    encontra o erro que ela mesma abriu no cenário anterior."""
    return criar_erro(vinculos_erros['interessado'])


@pytest.fixture
def erro_em_analise(vinculos_erros) -> Erro:
    """Erro já assumido pelo atendente: o estado que o 2º cenário da feature 002 herda do 1º.

    Assumir é feito pelo domínio (``gerenciar_atendente``) e não por ``update``, porque é ele
    que grava o ``AtendenteErro``, move a situação para "Em análise" e registra o histórico —
    ``pode_alterar_url`` (``erros/models.py:198``) depende de o vínculo ser o atendente atual.
    Só comentários **automáticos** nascem daí, o que importa: comentário do próprio usuário
    renderiza um ícone de engrenagem cujo texto acessível é "Opções", e ele disputaria o
    clique com o botão "Opções" da barra de ações.
    """
    erro = criar_erro(vinculos_erros['interessado'])
    erro.gerenciar_atendente(vinculos_erros['atendente'], forcar_assumir=True)
    erro.refresh_from_db()
    return erro


@pytest.fixture
def erro_com_atendente_auxiliar(vinculos_erros) -> Erro:
    """Erro com atendente principal E auxiliar — o estado que ``remover_atendente`` exige.

    A view (``erros/views.py:568-578``) só remove quem **não** é o atendente atual
    (``exclude(vinculo=obj.atendente_atual)``), então o auxiliar precisa existir como
    ``AtendenteErro`` sem ser o principal. É o que ``gerenciar_atendente`` sem
    ``forcar_assumir`` faz (``erros/models.py:387-389``): cria o vínculo e registra "se
    habilitou como atendente auxiliar", mantendo o principal.
    """
    erro = criar_erro(vinculos_erros['interessado'])
    erro.gerenciar_atendente(vinculos_erros['atendente'], forcar_assumir=True)
    erro.gerenciar_atendente(vinculos_erros['atendente_auxiliar'])
    erro.refresh_from_db()
    return erro


@pytest.fixture
def chamado_reclassificavel(vinculos_erros):
    """Chamado aberto da central de serviços que o ``atendente`` pode reclassificar em erro.

    É o único ponto em que a suíte toca outro módulo, e ele é inevitável: a view
    ``reportar_erro_por_chamado`` exige um ``centralservicos.Chamado`` de verdade e a
    permissão sai de lá (``Chamado.pode_reclassificar``, ``centralservicos/models.py:1932``).
    O grafo mínimo é o que ``Chamado.save`` cobra: serviço → grupo/categoria/centro de
    atendimento, mais um grupo de atendimento de primeiro nível **com atendente**, senão o
    save levanta ``ValidationError`` (``centralservicos/models.py:252-260``).

    Três armadilhas medidas, todas do save:

    * ``centro_atendimento`` **não** é campo — ``Chamado.__init__`` o zera
      (``centralservicos/models.py:946-948``) e o formulário o injeta antes de gravar; aqui
      é preciso fazer o mesmo à mão;
    * ``aberto_em`` é ``auto_now_add``, mas ``calcula_data_limite_sem_feriados_fds`` o lê
      **antes** de ``super().save()`` (``:247``): sem um valor explícito, estoura em ``None``;
    * o ``eh_local=True`` do centro é o que faz ``get_grupo_primeiro_nivel`` filtrar por
      campus e achar o grupo criado aqui (``:386-395``).

    Quem reclassifica é o ``atendente``, por ser **responsável** do grupo de atendimento — não
    por ser superusuário, que seria o atalho que não afirma permissão nenhuma. O interessado do
    chamado é outro usuário de propósito: é ele que o formulário migra para o erro novo.

    Só o ``Chamado`` é criado a cada teste; o cadastro de apoio é ``get_or_create`` porque a
    suíte não dá flush e o CI usa ``--reuse-db`` (armadilha 8).
    """
    import datetime

    from centralservicos.models import CategoriaServico, CentroAtendimento, Chamado, GrupoAtendimento, GrupoServico, Servico
    from comum.models import AreaAtuacao

    atendente = vinculos_erros['atendente']
    area = AreaAtuacao.objects.get_or_create(nome='Tecnologia da Informação (e2e erros)')[0]
    centro = CentroAtendimento.objects.get_or_create(nome='Central e2e', area=area, defaults={'eh_local': True})[0]
    categoria = CategoriaServico.objects.get_or_create(nome='Categoria e2e', defaults={'area': area})[0]
    grupo_servico = GrupoServico.objects.get_or_create(nome='Grupo e2e', defaults={'detalhamento': 'Serviços do e2e do módulo erros'})[0]
    grupo_servico.categorias.add(categoria)
    servico = Servico.objects.get_or_create(
        nome='Serviço e2e',
        defaults={'tipo': Servico.TIPO_REQUISICAO, 'area': area, 'grupo_servico': grupo_servico},
    )[0]
    servico.centros_atendimento.add(centro)

    campus = atendente.relacionamento.setor.uo
    equipe = GrupoAtendimento.objects.get_or_create(campus=campus, centro_atendimento=centro, defaults={'nome': 'Equipe e2e'})[0]
    equipe.atendentes.add(atendente.user)
    equipe.responsaveis.add(atendente.user)

    chamado = Chamado(
        servico=servico,
        descricao=f'Chamado da central de serviços (e2e {uuid4().hex[:8]})',
        aberto_por=atendente.user,
        requisitante=atendente.user,
        interessado=vinculos_erros['interessado'].user,
        meio_abertura=Chamado.MEIO_ABERTURA_WEB,
        campus=campus,
        aberto_em=datetime.datetime.now(),
    )
    chamado.centro_atendimento = centro
    chamado.save()
    return chamado
