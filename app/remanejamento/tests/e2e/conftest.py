"""Substrato dos e2e do remanejamento (Remoção Interna): papéis, cargos/áreas e editais por fase.

**Modo 2 (geração), não tradução.** O módulo tem ``remanejamento/old_features/`` com duas
``.feature``, mas elas NÃO são a fonte desta suíte, por três razões verificáveis:

1. o diretório se chama ``old_features``: ``bin/scripts/paridade_e2e.py`` só lê
   ``<modulo>/features/`` (``cenarios_ativos``, e o ``main`` sai por
   "sem diretório features/ — use --rotas"), e o ``manage.py test_behave`` também procura
   ``features/``. Marcador ``@pytest.mark.cenario`` apontando para lá não seria verificado por
   gate nenhum — seria ruído no manifesto;
2. a renomeação ``features/`` → ``old_features/`` foi feita **pelo commit que reescreveu o
   módulo** (``c6939711f1``, Demanda 1779: 789 linhas em ``models.py``, 282 em ``forms.py``,
   ``urls.py`` refeito, ``gerenciar_edital.html``/``tabs/`` criados). Aposentar os cenários foi
   parte da mudança, não descuido;
3. o que sobrou lá descreve telas que não existem mais nesta forma — o cadastro de edital sem
   ``Categoria`` (hoje obrigatória, com ``clean_cargos`` amarrando categoria a código de cargo)
   e o fluxo de disciplina por ``remanejamento.Disciplina``, substituído por
   ``VagaEdital.disciplina`` (``edu.Disciplina``).

A unidade de cobertura aqui é, portanto, a **rota** (``paridade_e2e.py remanejamento --rotas``),
e cada arquivo se rastreia pela própria docstring. Os fluxos das duas ``old_features``
continuam cobertos como fluxo (recurso ao edital, resposta ao recurso, inscrição, recurso ao
resultado, resposta ao recurso do resultado) — só não como cenário declarado.

Decisões deste módulo (as quatro da seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — por factories (#17486): ``semear_base`` dá catálogos, raiz e ``admin``; a árvore
   (A0 com A1, B0 — nas duas árvores, SUAP e SIAPE, ver ``_criar_arvore``), os servidores
   (``servidor_com_login``) e o domínio (cargos, áreas, editais, inscrições) são montados neste
   arquivo.
2. **Papéis** — sim, e o módulo é governado por grupo: ``Edital.pode_editar``
   (``remanejamento/models.py:247``) e o ``group_required`` de ``gerenciar_edital``
   (``views.py:140``) olham ``Coordenador de Remanejamento`` / ``Avaliador de Remanejamento``.
   A criação é eager e session-scoped por causa do cache de permissão por processo
   (armadilha 3).
3. **Relógio** — NÃO congela, apesar de o domínio inteiro ser dirigido por data (o edital tem
   12 marcos temporais). Em vez de congelar, cada edital nasce por ORM com os prazos escritos
   **relativos a ``datetime.now()``**, na fase que o teste precisa (ver ``criar_edital`` e as
   fixtures de fase). Congelar custaria caro aqui: sessão de login validada contra
   ``expire_date`` (sem ``storage_states``), aquecimento de urlconf por causa do pydantic
   (armadilha 4) e uma data por arquivo — enquanto o custo de posicionar prazos é uma linha
   por fixture. O teste de cadastro pela tela também escreve os prazos relativos a hoje.
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``: nenhum arquivo depende do
   estado que outro produziu. Cada teste cria o seu edital (título único com ``uuid4``), porque
   a suíte não dá flush e o CI usa ``--reuse-db`` (armadilha 8).

Armadilha de ambiente herdada dos testes de integração
(``remanejamento/tests/fluxos/test_fluxo_remocao_interna.py``): **``comum.models.User.VINCULOS``
é cache de processo** e não é invalidado por um ``update()`` direto no banco — por isso cargo,
área e início de exercício dos servidores são gravados na criação, antes de qualquer request.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_remanejamento_e2e DATABASE_PORT=5433 \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest remanejamento/tests/e2e -m e2e --reuse-db
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:  # os models só são importados dentro dos corpos (padrão dos e2e do repo)
    from remanejamento.models import Edital, Inscricao
    from rh.models import Servidor, Setor

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import servidor_com_login, setor
from djtools.e2e_fixtures import campus as campus_suap  # `campus` aqui é a consulta de UO, abaixo

# Apelido -> matrícula, para os testes não ficarem cheios de números mágicos.
PAPEIS = {
    'coordenador': '117001',
    'candidato': '117002',
    'candidata_correlata': '117003',
    'servidor_de_fora': '117004',
    'avaliador': '117005',
    'concorrente': '117006',
    'inscrevente': '117007',
}

# Prefixo de tudo que esta suíte cria. Serve de âncora para a limpeza de `remanejamento_seed`.
PREFIXO = 'E2E Remoção Interna'

# Cargos e áreas deste módulo. Código local (não numérico) para não colidir com o espaço de
# códigos do SIAPE — a convenção está em `rh/models/carreira/cargo_emprego.py:11-18`.
CARGO_TAE = ('RIE2E1', 'Assistente e2e')
CARGO_COM_AREA = ('RIE2E2', 'Técnico de Laboratório e2e')
CARGO_DOCENTE = ('707E2E', 'PROFESSOR e2e')
CARGO_DE_FORA = ('RIE2E3', 'Auxiliar e2e')  # cargo de nenhum edital: o do `servidor_de_fora`
AREA_PRINCIPAL = 'Informática e2e'
AREA_CORRELATA = 'Sistemas de Computação e2e'
AREA_DE_FORA = 'Redes e2e'

# Siglas dos campi (as da árvore legada, que os testes citam), nas árvores SUAP e SIAPE.
CAMPUS_ORIGEM = 'A0'
CAMPUS_DESTINO = 'B0'

# Gate do modo 2 (`paridade_e2e.py remanejamento --rotas`). Cada motivo é uma condição
# verificável no código, não uma dificuldade.
ROTAS_DISPENSADAS = {
    '/remanejamento/adicionar_disciplinas/<int:edital_pk>/': (
        'view marcada `@deprecated(reason="View não utilizada", expire_date="2026-12-31")` em `remanejamento/views.py:993`, '
        'com um `# FIXME: remover essa view não utilizada no sistema` logo acima. Ela grava `remanejamento.Disciplina`, o '
        'model que a Demanda 1779 substituiu por `VagaEdital.disciplina` (`edu.Disciplina`): nenhum template do módulo '
        'aponta para ela (grep por `adicionar_disciplinas` em `remanejamento/templates/` não retorna nada). Testá-la '
        'fixaria em suíte um caminho que já tem data de remoção.'
    ),
    '/remanejamento/adicionar_disciplina_itens/<int:edital_pk>/': (
        'mesma situação: `@deprecated` em `remanejamento/views.py:1013`, exige `is_superuser` e grava `DisciplinaItem`, '
        'do mesmo model aposentado. Sem link em template algum.'
    ),
}


# --------------------------------------------------------------------------- seed


# Papel -> (nome, grupo além de `Servidor`, cargo, área, início de exercício no cargo). Todos em
# A1, que fica no campus A0: o campus de ORIGEM de toda remoção desta suíte.
#
# As datas de início de exercício são diferentes de propósito: é o critério de desempate do
# processamento (mais tempo de serviço primeiro), então empate deixaria a classificação
# dependente da ordem de inserção.
#
# O `inscrevente` é usado SÓ em `test_inscricao_servidor.py`, e de propósito: `inscrever`
# (`views.py:511`) procura a última inscrição VALIDADA do servidor e, se existir, marca os campos
# do formulário como `readonly` (`forms.py:303-308`). Como a suíte não dá flush, qualquer papel
# que outro teste valide passaria a chegar ao formulário com os campos travados — e `fill` num
# input readonly falha. Este papel não é validado por teste nenhum.
USUARIOS: dict[str, tuple[str, str | None, tuple[str, str], str | None, datetime.date]] = {
    'coordenador': ('Coordenadora de Remoção Interna', 'Coordenador de Remanejamento', CARGO_TAE, None, datetime.date(2005, 1, 1)),
    'candidato': ('Candidato da Remoção Interna', None, CARGO_TAE, None, datetime.date(2010, 1, 1)),
    'candidata_correlata': ('Candidata de Área Correlata', None, CARGO_COM_AREA, AREA_CORRELATA, datetime.date(2012, 1, 1)),
    'servidor_de_fora': ('Servidor de Cargo Fora do Edital', None, CARGO_DE_FORA, None, datetime.date(2015, 1, 1)),
    'avaliador': ('Avaliador de Remoção Interna', 'Avaliador de Remanejamento', CARGO_TAE, None, datetime.date(2016, 1, 1)),
    'concorrente': ('Concorrente da Remoção Interna', None, CARGO_TAE, None, datetime.date(2018, 1, 1)),
    'inscrevente': ('Servidor que se Inscreve pela Tela', None, CARGO_TAE, None, datetime.date(2011, 1, 1)),
}


def _campus_siape(sigla: str, superior: Setor | None, equivalente: Setor | None = None) -> Setor:
    """Setor SIAPE (``codigo`` = sigla) e, para campus, a UO SIAPE equivalente à do setor SUAP.

    A UO SIAPE leva a **sigla** do campus: o processamento do resultado resolve o campus de
    destino por ela (``remanejamento/models.py:536``) e lê a lotação atual do servidor de
    ``setor_lotacao.uo.sigla`` (``:315``) — com sigla vazia ninguém é alocado, em silêncio. E leva
    ``equivalente`` porque é o que o ``Servidor.save`` confere entre ``setor_exercicio`` e
    ``setor``: sem ele, o save anula o setor SUAP e o middleware desloga o servidor. ``tipo=None``
    como no SIAPE real: a UO SIAPE não é campus para ``UnidadeOrganizacional.objects.uo()``.
    """
    from rh.models import Setor, UnidadeOrganizacional
    from rh.tests.factories import SetorSiapeFactory, UnidadeOrganizacionalFactory

    setor_siape = Setor.objects.filter(sigla=sigla, codigo=sigla).first() or SetorSiapeFactory(
        sigla=sigla, codigo=sigla, nome=sigla, superior=superior
    )
    if equivalente is not None and not UnidadeOrganizacional.objects.filter(setor=setor_siape).exists():
        # UnidadeOrganizacional.save regrava todos os setores: é o que preenche a `uo` dos filhos.
        UnidadeOrganizacionalFactory(setor=setor_siape, sigla=sigla, nome=sigla, equivalente=equivalente.uo, tipo=None)
    return Setor.objects.get(pk=setor_siape.pk)


def _criar_arvore() -> dict[str, Setor]:
    """A0 (origem, com A1) e B0 (destino), nas árvores SUAP e SIAPE. ``{'A1': suap, 'A1_siape': siape}``.

    O SIAPE vem inteiro depois do SUAP, e os setores são relidos no fim: cada UO criada regrava
    todos os setores, e o ``Servidor.save`` compara a ``uo`` da instância que recebe.
    """
    from rh.models import Setor

    a0 = campus_suap(CAMPUS_ORIGEM)
    a1 = setor('A1', a0)
    b0 = campus_suap(CAMPUS_DESTINO)
    a0_siape = _campus_siape(CAMPUS_ORIGEM, None, a0)
    a1_siape = _campus_siape('A1', a0_siape)
    _campus_siape(CAMPUS_DESTINO, None, b0)
    return {'A1': Setor.objects.get(pk=a1.pk), 'A1_siape': Setor.objects.get(pk=a1_siape.pk)}


def _criar_cargos_e_areas() -> None:
    """Os cargos desta suíte e as áreas do cargo com área.

    ``EditalForm.cargos`` usa ``CargoEmprego.utilizados`` (``rh/.../cargo_emprego.py:43``), que
    só enxerga cargo com pelo menos um servidor vinculado — por isso os cargos são criados
    aqui, antes dos servidores que os ocupam, e não sob demanda no teste.

    ``PROFESSOR`` no nome não é decoração: ``Edital.eh_edital_remocao_docente``
    (``models.py:929``) é ``cargos__nome__contains='PROFESSOR'`` **ou** categoria docente. O
    nome dos outros evita a palavra de propósito.
    """
    from rh.models import CargoEmprego, CargoEmpregoArea
    from rh.tests.factories import GrupoCargoEmpregoFactory

    grupo = GrupoCargoEmpregoFactory()
    for codigo, nome in (CARGO_TAE, CARGO_COM_AREA, CARGO_DOCENTE, CARGO_DE_FORA):
        CargoEmprego.objects.get_or_create(
            codigo=codigo, defaults={'nome': nome, 'grupo_cargo_emprego': grupo, 'sigla_escolaridade': '01', 'cargo_suap': True}
        )
    cargo_com_area = CargoEmprego.objects.get(codigo=CARGO_COM_AREA[0])
    for descricao in (AREA_PRINCIPAL, AREA_CORRELATA, AREA_DE_FORA):
        CargoEmpregoArea.objects.get_or_create(cargo_emprego=cargo_com_area, descricao=descricao)


def _criar_servidores(setores: dict[str, Setor]) -> None:
    """Os papéis de ``PAPEIS``, com cargo, área e início de exercício já na criação.

    Lotação e exercício SIAPE em A1 (campus A0) — é deles que o processamento lê o campus de
    origem. Falha alto se o ``Servidor.save`` anulou o setor SUAP (equivalência SIAPE↔SUAP
    quebrada): o sintoma, sem isto, é um login que volta para a tela de entrada.
    """
    from rh.models import CargoEmprego, CargoEmpregoArea, Servidor

    for papel, (nome, grupo, (codigo_cargo, _), area, inicio) in USUARIOS.items():
        cargo = CargoEmprego.objects.get(codigo=codigo_cargo)
        servidor_com_login(
            PAPEIS[papel],
            setores['A1'],
            grupos=[grupo] if grupo else (),
            staff=True,
            pessoa_fisica__nome=nome,
            setor_lotacao=setores['A1_siape'],
            setor_exercicio=setores['A1_siape'],
            cargo_emprego=cargo,
            cargo_emprego_area=area and CargoEmpregoArea.objects.get(cargo_emprego=cargo, descricao=area),
            data_inicio_exercicio_no_cargo=inicio,
        )
    sem_setor = list(Servidor.objects.filter(matricula__in=PAPEIS.values(), setor__isnull=True).values_list('matricula', flat=True))
    assert not sem_setor, f'Servidor.save anulou o setor SUAP de {sem_setor}: confira a equivalência das UOs SIAPE'


def _criar_criterios_classificacao() -> None:
    """Os critérios de classificação do cadastro de apoio, que o ``semear_base`` não traz.

    ``remanejamento/fixtures/initial_data_criterioclassificacao.json`` existe, mas não se
    chama ``initial_data.json`` e portanto não entra no ``loaddata`` do ``semear_base``. Sem
    nenhum ``CriterioClassificacao`` a tela "Adicionar Critério de classificação" do edital
    não tem o que oferecer e o processamento classifica por tupla vazia — isto é, mantém a
    ordem de inserção e nenhuma asserção sobre classificação significaria coisa alguma
    (``models.py:463-498``).
    """
    from remanejamento.models import CriterioClassificacao, CriterioClassificacaoChoices

    for nome, _rotulo in CriterioClassificacaoChoices.CRITERIO_CHOICES:
        CriterioClassificacao.objects.get_or_create(nome=nome, defaults={'ativo': True})


def _criar_afastamento() -> None:
    """Um afastamento SIAPE que desconta tempo, e o usufruto passado do ``candidato``.

    É o insumo de duas rotas: ``atualizar_afastamentos`` (que copia
    ``AfastamentoRemocaoInterna`` para ``EditalAfastamento``) e ``validar_afastamentos`` (que
    só mostra linha quando o servidor tem ``ServidorAfastamento`` de um afastamento que o
    edital marcou como ``desconta_exercicio``).

    ``impeditivo=False`` e usufruto **no passado** de propósito: afastamento impeditivo vigente
    faz ``inscrever`` exibir o bloqueio no lugar do formulário (``views.py:528``) e derrubaria o teste de inscrição.
    """
    from remanejamento.models import AfastamentoRemocaoInterna
    from rh.models import AfastamentoSiape, Servidor, ServidorAfastamento

    afastamento, _ = AfastamentoSiape.objects.get_or_create(
        codigo='9901', defaults={'sigla': 'E2ECAP', 'nome': 'Licença para capacitação (e2e)', 'tipo': AfastamentoSiape.OUTROS}
    )
    AfastamentoRemocaoInterna.objects.get_or_create(afastamento=afastamento, defaults={'impeditivo': False, 'desconta_exercicio': True})
    servidor = Servidor.objects.get(matricula=PAPEIS['candidato'])
    ServidorAfastamento.objects.get_or_create(
        servidor=servidor,
        afastamento=afastamento,
        data_inicio=datetime.date(2018, 3, 1),
        defaults={'data_termino': datetime.date(2018, 5, 30), 'quantidade_dias_afastamento': 90},
    )


def _criar_infra_documentos() -> None:
    """O que ``publicar_resultado`` exige do ``documento_eletronico`` para não cair no 500.

    Três dependências, todas lidas por nome/pk fixo em ``remanejamento/views.py:252-284``:
    o ``ModeloDocumento`` chamado exatamente "Resultado de Remoção Interna", a
    ``HipoteseLegal`` de ``pk=6`` e a ``Configuracao`` ``rh.setor_remocaointerna_rh``, que
    aponta o setor dono do documento.

    O corpo do modelo é só ``{{ resultado_html }}`` porque é essa a variável que a view
    calcula (``views.py:269``); o resto do template padrão do IFRN não acrescenta nada
    verificável ao teste.
    """
    from comum.models import Configuracao
    from documento_eletronico.models import Documento, HipoteseLegal, ModeloDocumento, TipoDocumentoTexto
    from rh.models import Setor

    tipo, _ = TipoDocumentoTexto.objects.get_or_create(
        nome='Resultado de Remoção Interna - Tipo', defaults={'sigla': 'RRIE2E', 'vincular_pessoa': False}
    )
    ModeloDocumento.objects.get_or_create(
        nome='Resultado de Remoção Interna',
        defaults={
            'corpo_padrao': '{{ resultado_html }}',
            'tipo_documento_texto': tipo,
            'permite_nivel_acesso_publico': True,
            'nivel_acesso_padrao': Documento.NIVEL_ACESSO_PUBLICO,
            'ativo': True,
        },
    )
    HipoteseLegal.objects.get_or_create(pk=6, defaults={'nivel_acesso': 'Público', 'descricao': 'Hipótese e2e', 'base_legal': 'Art. X'})
    setor = Setor.objects.filter(sigla='A1', codigo__isnull=True).first()
    Configuracao.objects.update_or_create(
        app='rh', chave='setor_remocaointerna_rh', defaults={'valor': str(setor.pk), 'descricao': 'Setor da Remoção Interna (e2e)'}
    )


def _limpar_editais_de_execucoes_anteriores() -> None:
    """Apaga os editais que esta suíte deixou para trás — armadilha 8 (sem flush + ``--reuse-db``).

    Sem isto, cada execução soma um edital em período de inscrição para os mesmos servidores,
    e a página inicial do candidato acumula um link "Inscrever-se..." por execução; a listagem
    do admin também empurra o edital do teste para a página 2 com o tempo.

    Os três FKs de documento são anulados **antes** do delete porque são ``on_delete=PROTECT``
    (``models.py:83-109``): um edital cujo resultado parcial chegou a ser publicado não pode
    ser apagado enquanto apontar para o ``DocumentoTexto``.
    """
    from remanejamento.models import Edital

    antigos = Edital.objects.filter(titulo__startswith=PREFIXO)
    antigos.update(
        edital_documentotexto=None,
        resultado_parcial_documentotexto=None,
        resultado_final_documentotexto=None,
        resultado_final_homologacao_documentotexto=None,
    )
    antigos.delete()


@pytest.fixture(scope='session')
def remanejamento_seed(e2e_seed):
    """Árvore, cargos/áreas, papéis, afastamento e infra de documento — tudo antes da 1ª request.

    Cada passo é idempotente (``get_or_create``/``update_or_create``), obrigatório porque a
    suíte não dá flush e o CI usa ``--reuse-db``. A ordem importa: a árvore e os cargos precisam
    existir antes dos servidores, e os servidores antes de qualquer request por causa do cache de
    vínculo/permissão por processo (armadilha 3).
    """
    setores = _criar_arvore()
    _criar_cargos_e_areas()
    _criar_servidores(setores)
    _criar_criterios_classificacao()
    _criar_afastamento()
    _criar_infra_documentos()
    _limpar_editais_de_execucoes_anteriores()


@pytest.fixture(scope='session')
def servidores(remanejamento_seed) -> dict[str, Servidor]:
    """``{apelido: Servidor}`` dos papéis de ``PAPEIS``, já criados por ``remanejamento_seed``.

    Existe para o teste falhar com "papel desconhecido" em vez de com um login em branco
    quando alguém escreve um apelido que não está na tabela.
    """
    from rh.models import Servidor

    return {papel: Servidor.objects.get(matricula=matricula) for papel, matricula in PAPEIS.items()}


@pytest.fixture
def logado_remanejamento(logado, servidores):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in servidores, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


# --------------------------------------------------------------- fábricas de domínio


def campus(sigla: str, siape: bool = False):
    """A ``UnidadeOrganizacional`` do campus, na árvore SUAP (default) ou SIAPE.

    As duas existem para o mesmo campus e não são intercambiáveis: ``Edital.campus`` e
    ``VagaEdital.campus`` são SUAP; ``InscricaoContemplada.campus_destino`` é SIAPE, porque o
    processamento a busca por ``setor__codigo__isnull=False`` (``models.py:536``).
    """
    from rh.models import UnidadeOrganizacional

    consulta = UnidadeOrganizacional.objects.filter(setor__sigla=sigla)
    return consulta.filter(setor__codigo__isnull=False).first() if siape else consulta.filter(setor__codigo__isnull=True).first()


def nome_na_listagem(servidor: Servidor) -> str:
    """O nome do servidor **como as tabelas do módulo o exibem** — não é ``str(servidor)``.

    Os templates passam o servidor pelo filtro ``format`` (``tabs/inscricoes.html``), que para
    vínculo cai em ``format_user`` e imprime ``nome_social or nome_usual or nome``
    (``djtools/templatetags/filters/utils.py:483``) — o nome **usual**, que o SUAP deriva como
    primeiro + último nome. Medido: "Candidato da Remoção Interna (117002)" aparece na linha
    como "Candidato Interna", e recortar a linha pela matrícula não encontra nada.
    """
    perfil = servidor.get_user().get_profile()
    return perfil.nome_social or perfil.nome_usual or perfil.nome


def criar_edital(**campos: Any) -> Edital:
    """Edital TAE com prazos relativos a ``now()``, coordenado pelo papel ``coordenador``.

    A linha do tempo default é a de um edital **com inscrições abertas hoje**; cada fixture de
    fase sobrescreve só os marcos que precisa mover (ver ``edital_para_processar``,
    ``edital_em_recurso_ao_edital`` etc.). Escrever prazo relativo em vez de congelar o relógio
    é a decisão 3 da docstring do módulo.

    ``permite_recursos_contra_edital`` é ligado aqui e não pela tela porque o campo **não está
    em nenhum fieldset do ``EditalAdmin``** (``admin.py:77-104``): não há como marcá-lo pela
    interface, mas é ele que faz o atalho "Recurso ao Edital ..." aparecer na página inicial do
    servidor (``views.py:71``).
    """
    from remanejamento.models import Edital
    from rh.models import CargoEmprego, Servidor

    agora = datetime.datetime.now()
    valores: dict[str, Any] = {
        'categoria': Edital.TAE,
        'titulo': f'{PREFIXO} {uuid4().hex[:8]}',
        'descricao': 'Edital de Remoção Interna criado pela suíte e2e.',
        'chave_hash': uuid4().hex,
        'permite_recursos_contra_edital': True,
        'inicio_recursos_edital': agora - datetime.timedelta(days=20),
        'fim_recursos_edital': agora - datetime.timedelta(days=19),
        'resultado_recursos_edital': agora - datetime.timedelta(days=18),
        'inicio_inscricoes': agora - datetime.timedelta(days=1),
        'fim_inscricoes': agora + datetime.timedelta(days=7),
        'inicio_desistencias': agora - datetime.timedelta(days=1),
        'fim_desistencias': agora + datetime.timedelta(days=7),
        'inicio_recursos': agora + datetime.timedelta(days=10),
        'fim_recursos': agora + datetime.timedelta(days=15),
        'resultado_recursos': agora + datetime.timedelta(days=16),
        'data_resultado_parcial': agora + datetime.timedelta(days=9),
        'inicio_resultados': agora + datetime.timedelta(days=16),
        'data_homologacao_resultado': agora + datetime.timedelta(days=20),
    }
    valores.update(campos)
    edital = Edital.objects.create(**valores)
    edital.campus.add(campus(CAMPUS_ORIGEM), campus(CAMPUS_DESTINO))
    edital.cargos.add(CargoEmprego.objects.get(codigo=CARGO_TAE[0]), CargoEmprego.objects.get(codigo=CARGO_COM_AREA[0]))
    edital.coordenadores.add(Servidor.objects.get(matricula=PAPEIS['coordenador']).get_user())
    return edital


def configurar_vagas(edital: Edital, vagas_no_destino: int = 1) -> dict[str, Any]:
    """Cria as ``VagaEdital`` do edital como a tela "Configurar cargos" + "Editar vagas" criaria.

    Reproduz ``ConfigurarCargosVagasEditalForm.processar`` (``forms.py:748``): uma linha por
    (campus, cargo) e, para o cargo com área, uma por (campus, cargo, área). As vagas ficam só
    no campus de **destino** — vaga na origem faria o classificador manter todo mundo onde está.

    ``areas_correlatas`` recebe a área da ``candidata_correlata``: é o que a torna elegível a
    concorrer às vagas da área principal (``models.py:226-229`` e ``:570-584``).
    """
    from remanejamento.models import VagaEdital
    from rh.models import CargoEmprego, CargoEmpregoArea

    cargo_tae = CargoEmprego.objects.get(codigo=CARGO_TAE[0])
    cargo_com_area = CargoEmprego.objects.get(codigo=CARGO_COM_AREA[0])
    area_principal = CargoEmpregoArea.objects.get(cargo_emprego=cargo_com_area, descricao=AREA_PRINCIPAL)
    area_correlata = CargoEmpregoArea.objects.get(cargo_emprego=cargo_com_area, descricao=AREA_CORRELATA)

    vagas = {}
    for chave, sigla, quantidade in (('origem', CAMPUS_ORIGEM, 0), ('destino', CAMPUS_DESTINO, vagas_no_destino)):
        vagas[f'tae_{chave}'] = VagaEdital.objects.create(
            edital=edital, campus=campus(sigla), cargo=cargo_tae, qtd_edital=quantidade, qtd_remanescente=quantidade
        )
        vaga_area = VagaEdital.objects.create(
            edital=edital,
            campus=campus(sigla),
            cargo=cargo_com_area,
            cargo_emprego_area=area_principal,
            qtd_edital=quantidade,
            qtd_remanescente=quantidade,
        )
        vaga_area.areas_correlatas.add(area_correlata)
        vagas[f'area_{chave}'] = vaga_area
    return vagas


def criar_inscricao(edital: Edital, servidor: Servidor, preferencia: str = CAMPUS_DESTINO, **campos: Any) -> Inscricao:
    """Inscrição confirmada com uma ordem de preferência — o que ``InscreverFormFactory.save`` grava.

    ``atualizar_frases()`` no fim não é enfeite: é ele que preenche ``frase_pura``/``frase_hash``,
    os campos de autenticidade que a tela do comprovante exibe (``inscricao.html``).

    O ``dou_numero`` é único por inscrição, e isso é funcional: ``Inscricao`` não declara
    ``SEARCH_FIELDS``, então o autocomplete do SUAP cai no fallback "todo ``CharField`` do
    model" (``djtools/utils/autocomplete.py:75-81``) — os únicos campos pesquisáveis da
    inscrição são os do DOU. Com todas as inscrições gravando ``dou_numero='1'`` não há como
    escolher uma delas na tela de inclusão extraordinária.
    """
    from remanejamento.models import Inscricao, InscricaoItem

    valores: dict[str, Any] = {
        'edital': edital,
        'servidor': servidor,
        'inicio_exercicio': servidor.data_inicio_exercicio_no_cargo,
        'concurso_ingresso_eh_ifrn': True,
        'classificacao_concurso': 1,
        'dou_numero': str(uuid4().int % 1000000).zfill(6),
        'dou_data': datetime.date(2000, 2, 1),
        'dou_pagina': '1',
        'dou_sessao': '1',
        'jornada_trabalho': servidor.jornada_trabalho,
    }
    valores.update(campos)
    inscricao = Inscricao.objects.create(**valores)
    InscricaoItem.objects.create(inscricao=inscricao, campus=campus(preferencia), preferencia=1)
    inscricao.atualizar_frases()
    return inscricao


def validar_inscricao(inscricao: Inscricao, servidores: dict[str, Servidor]) -> None:
    """Marca a inscrição como validada pelo coordenador, sem passar pela tela.

    ``Edital.existem_inscricoes_com_avaliacoes_pendentes`` (``models.py:979``) bloqueia o
    processamento do resultado enquanto houver inscrição confirmada sem ``validado_por`` **e**
    sem ``licenca_afastamento_verificado_por``. Os testes que exercitam a tela de validação
    fazem isso pela interface; os que precisam apenas do resultado processado usam este atalho.
    """
    from remanejamento.models import Inscricao

    Inscricao.objects.filter(pk=inscricao.pk).update(
        validado_por=servidores['coordenador'].get_vinculo(),
        validado_em=datetime.datetime.now(),
    )


# ------------------------------------------------------------------ fixtures de fase


@pytest.fixture
def edital_com_inscricoes_abertas(servidores) -> Edital:
    """Edital TAE com vagas configuradas e inscrições abertas hoje — a fase default."""
    edital = criar_edital()
    configurar_vagas(edital)
    return edital


@pytest.fixture
def edital_sem_vagas(servidores) -> Edital:
    """Edital recém-cadastrado, ainda sem nenhuma ``VagaEdital`` — o que a tela de configuração encontra."""
    return criar_edital()


@pytest.fixture
def edital_em_recurso_ao_edital(servidores) -> Edital:
    """Edital cujo período de recurso **ao edital** está aberto hoje.

    O resultado dos recursos fica no futuro: é ele que separa "o coordenador ainda pode
    responder" de "o servidor já pode ver a resposta" (``models.py:1003-1006`` e
    ``views.py:125``).
    """
    agora = datetime.datetime.now()
    return criar_edital(
        inicio_recursos_edital=agora - datetime.timedelta(days=1),
        fim_recursos_edital=agora + datetime.timedelta(days=5),
        resultado_recursos_edital=agora + datetime.timedelta(days=6),
        inicio_inscricoes=agora + datetime.timedelta(days=7),
        fim_inscricoes=agora + datetime.timedelta(days=14),
    )


def adicionar_criterio(edital: Edital, nome: str, ordem: int = 1) -> None:
    """Vincula um ``CriterioClassificacao`` ao edital — o que a tela do admin grava.

    Sem critério vinculado, ``classificar_por_criterios`` devolve tupla vazia e o ``sorted``
    vira estável na ordem de inserção (``models.py:463-498``): a classificação deixa de ser
    verificável.
    """
    from remanejamento.models import CriterioClassificacao, EditalCriterioClassificacao

    EditalCriterioClassificacao.objects.get_or_create(
        edital=edital, criterio_classificacao=CriterioClassificacao.objects.get(nome=nome), defaults={'ordem': ordem}
    )


@pytest.fixture
def edital_para_processar(servidores) -> tuple[Edital, dict[str, Any]]:
    """``(edital, inscricoes)`` com as inscrições encerradas e o resultado parcial liberado.

    Três condições simultâneas, e cada uma tem um dono no código:
    ``processar_resultado`` exige vaga cadastrada e nenhuma inscrição pendente de avaliação
    (``views.py:215-222``); ``pode_publicar_resultado_parcial`` exige
    ``now() >= data_resultado_parcial`` (``models.py:936``); e o botão "Processar Resultado" só
    aparece fora do período de inscrição (``tabs/inscricoes.html``).

    Três inscrições, e cada uma responde por uma pergunta diferente do classificador:

    * ``candidato`` (exercício desde 2010) e ``concorrente`` (2018) disputam a **única** vaga do
      cargo TAE no destino — com uma inscrição só, qualquer ordenação passaria. O critério
      vinculado é o de maior tempo de serviço, então o esperado é ``candidato`` contemplado e
      ``concorrente`` não;
    * ``candidata_correlata`` concorre pela vaga da área **correlata**, que é o ramo menos óbvio
      (``models.py:570-584``): o cargo dela não é o da vaga, a área é.
    """
    from remanejamento.models import CriterioClassificacaoChoices

    agora = datetime.datetime.now()
    edital = criar_edital(
        inicio_inscricoes=agora - datetime.timedelta(days=20),
        fim_inscricoes=agora - datetime.timedelta(days=10),
        inicio_desistencias=agora - datetime.timedelta(days=20),
        fim_desistencias=agora - datetime.timedelta(days=10),
        data_resultado_parcial=agora - datetime.timedelta(days=1),
        inicio_recursos=agora + datetime.timedelta(days=5),
        fim_recursos=agora + datetime.timedelta(days=10),
        resultado_recursos=agora + datetime.timedelta(days=11),
        inicio_resultados=agora + datetime.timedelta(days=12),
        data_homologacao_resultado=agora + datetime.timedelta(days=15),
    )
    configurar_vagas(edital)
    adicionar_criterio(edital, CriterioClassificacaoChoices.DATA_INICIO_EXERCICIO_CARGO_NO_ORGAO)
    inscricoes = {papel: criar_inscricao(edital, servidores[papel]) for papel in ('candidato', 'concorrente', 'candidata_correlata')}
    for inscricao in inscricoes.values():
        validar_inscricao(inscricao, servidores)
    return edital, inscricoes


@pytest.fixture
def inscricao_em_periodo_de_recurso(servidores) -> tuple[Edital, Any]:
    """``(edital, inscricao)`` com o período de recurso **ao resultado** aberto hoje.

    ``Inscricao.pode_cadastrar_recurso`` (``models.py:1369``) pede quatro coisas ao mesmo
    tempo: ser o dono da inscrição, ela estar confirmada, o edital estar em período de recurso
    para o cargo do servidor e ainda não haver texto de recurso. O resultado dos recursos fica
    no futuro para que ``pode_ver_resultado_recurso`` seja falso — é isso que separa este
    estado do da fixture seguinte.
    """
    agora = datetime.datetime.now()
    edital = criar_edital(
        inicio_inscricoes=agora - datetime.timedelta(days=20),
        fim_inscricoes=agora - datetime.timedelta(days=10),
        data_resultado_parcial=agora - datetime.timedelta(days=5),
        inicio_recursos=agora - datetime.timedelta(days=1),
        fim_recursos=agora + datetime.timedelta(days=5),
        resultado_recursos=agora + datetime.timedelta(days=6),
        inicio_resultados=agora + datetime.timedelta(days=7),
        data_homologacao_resultado=agora + datetime.timedelta(days=10),
    )
    configurar_vagas(edital)
    return edital, criar_inscricao(edital, servidores['candidato'])


@pytest.fixture
def inscricao_com_afastamento(servidores) -> tuple[Edital, Any]:
    """``(edital, inscricao)`` de um edital que já importou os afastamentos configurados.

    ``validar_afastamentos`` (``views.py:922``) só lista alguma coisa quando existe
    ``EditalAfastamento`` com ``desconta_exercicio=True`` **e** o servidor tem
    ``ServidorAfastamento`` daquele afastamento começando depois do início do exercício no
    cargo — o par é montado por ``_criar_afastamento`` (2018) e pelo início de exercício do
    ``candidato`` (2010).
    """
    from remanejamento.models import AfastamentoRemocaoInterna, EditalAfastamento

    edital = criar_edital()
    configurar_vagas(edital)
    for afastamento in AfastamentoRemocaoInterna.objects.all():
        EditalAfastamento.objects.get_or_create(
            edital=edital,
            afastamento=afastamento.afastamento,
            defaults={'impeditivo': afastamento.impeditivo, 'desconta_exercicio': afastamento.desconta_exercicio},
        )
    return edital, criar_inscricao(edital, servidores['candidato'])


@pytest.fixture
def edital_docente(servidores) -> Edital:
    """Edital da categoria Docente, sem disciplina configurada ainda.

    A categoria basta para ``eh_edital_remocao_docente`` (``models.py:929``) e é ela que troca
    a tela de configuração de cargos pela de disciplinas, e as áreas correlatas por disciplinas
    correlatas (``tabs/edital_info.html``).
    """
    from remanejamento.models import Edital
    from rh.models import CargoEmprego

    edital = criar_edital(categoria=Edital.DOCENTE)
    edital.cargos.set([CargoEmprego.objects.get(codigo=CARGO_DOCENTE[0])])
    return edital


@pytest.fixture
def disciplina_edu():
    """Uma ``edu.Disciplina`` para a configuração de disciplinas do edital docente.

    ``ConfigurarDisciplinasEditalForm.disciplina`` (``forms.py:772``) e
    ``CadastrarDisciplinasCorrelatasVagaEditalForm`` consultam o cadastro do ``edu``, que o
    seed base não popula.
    """
    from edu.models import Disciplina

    return {
        'principal': Disciplina.objects.get_or_create(descricao='Informática Básica e2e')[0],
        'correlata': Disciplina.objects.get_or_create(descricao='Programação de Computadores e2e')[0],
    }
