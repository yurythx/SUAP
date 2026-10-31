"""Substrato da rodada de geração da doc de usuário do ``avaliacao_integrada``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é o roteiro de uma tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma.

O módulo **não tem** ``tests/e2e/``, então não há substrato para reusar: o seed inteiro nasce
aqui. Só o star-import de ``djtools.e2e_fixtures`` é herdado — obrigatório em conftest, porque
é a precedência de conftest sobre plugin que faz os overrides privados
(``_django_db_helper``, ``_exige_banco_de_e2e``) valerem.

Decisões deste módulo:

1. **Papéis** — três, e é o que separa os três lados do fluxo:

   * ``administrador`` (grupo *Administrador de Avaliação Institucional*) monta o instrumento
     — eixos, dimensões, macroprocessos, indicadores — e mantém as comissões CPA;
   * ``aplicador`` (grupo *Aplicador de Avaliação Institucional*) cria a avaliação, gera o
     público-alvo e lê os relatórios. **Não** cadastra indicador: o ``permissions.yaml`` só
     lhe dá ``view_indicador``;
   * ``respondente`` é servidor sem grupo nenhum do módulo. Responder não exige permissão:
     a view ``questionario`` (``avaliacao_integrada/views.py:541``) só compara
     ``respondente.user`` com ``request.user``. É autorização **por linha**, e por isso o
     "Quem pode" dessa tarefa na doc foi escrito à mão.

   A criação é eager e session-scoped por causa do cache de permissão por processo.

2. **Tabelas de apoio** — o módulo não tem nenhuma carga inicial (nem ``initial_data``, nem
   fixture), e quatro delas são pré-requisito de tela que abre. Foram acrescentadas ao seed:

   * ``Segmento`` — os 14 do behave, **com pk explícito**: ``Segmento.DOCENTE`` e companhia
     são constantes inteiras no código (``avaliacao_integrada/models.py:154-167``) e o
     domínio inteiro (público-alvo, questionário externo, relatório) compara por id. Criar
     por ``get_or_create(descricao=...)`` e torcer pela ordem dos ids é o que a suíte do
     behave faz; aqui é explícito porque o banco da doc é compartilhado entre módulos;
   * ``EscalaLikert`` "Escala Padrão" + 5 níveis — sem ela o indicador do tipo *Escala
     Likert* (o padrão do formulário) não pode ser salvo (``IndicadorForm.clean``);
   * ``rh.AreaVinculacao`` — tabela **vazia** no SUAP recém-instalado. É pré-requisito duplo:
     a avaliação filtra o público-alvo de técnico-administrativo por ela, e
     ``Respondente.possui_area_vinculacao`` (``models.py:2136``) devolve ``False`` quando a
     avaliação não tem nenhuma — e aí o questionário do público interno **recusa abrir**;
   * ``comum.Ano`` do ano corrente — ``IndicadorForm`` limita os anos de referência a
     ``2015..hoje`` e o ``initial_data`` só cria 2018-2020.

3. **Relógio** — NÃO congela. As datas da avaliação são escritas em torno de
   ``date.today()`` no próprio teste, o que mantém ``Avaliacao.vigentes()`` verdadeiro sem
   ``freezegun`` — e assim dá para usar ``storage_states`` (login cacheado por papel).

4. **Encadeamento** — os testes formam uma cadeia (estrutura → indicador → avaliação →
   público-alvo → resposta → relatório), na ordem em que a doc apresenta as tarefas. Os nomes
   dos objetos criados pela UI são fixos (``NOMES``) porque aparecem nas capturas: o CI roda
   ``pytest -m doc`` inteiro num banco só, compartilhado entre módulos e sem flush entre
   testes, e a colisão com a execução anterior é resolvida no seed, renomeando os homônimos
   (``_aposentar_geracoes_anteriores``) em vez de marcando os nomes desta rodada. As
   asserções são por chave própria e por delta.

Rodar::

    DATABASE_HOST=localhost DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_aval_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db avaliacao_integrada/tests/doc/

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI (o job ``gerar-doc`` roda
``pytest -m doc`` sobre o serviço recém-subido, sem flag nenhuma) e as suítes de doc **não**
são idempotentes entre execuções — medido em 05/08/2026 no ``eventos`` (CPF fixo do visitante
já inscrito) e no ``edu`` (vínculos de diretoria já criados). As limpezas daqui continuam
necessárias pelo que sobra: banco compartilhado entre módulos e sem flush **dentro** da
rodada. O preço é o seed frio a cada iteração.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

DESTINO = Path(settings.BASE_DIR) / 'avaliacao_integrada' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Apelido -> matrícula. As matrículas seguem a numeração das duas `.feature` do módulo
# (8181001 e 8181002 são literalmente as de lá); 8181003 é novo: o behave usava um *aluno*
# como respondente, o que arrastaria a cadeia de seed do `edu` inteira para uma tarefa que um
# servidor exercita igual.
PAPEIS = {'administrador': '8181001', 'aplicador': '8181002', 'respondente': '8181003'}

# Matrícula -> (nome, grupos); os três no campus CZN.
SERVIDORES = {
    '8181001': ('Adm AvalInt', ['Servidor', 'Administrador de Avaliação Institucional']),
    '8181002': ('Aplicador AvalInt', ['Servidor', 'Aplicador de Avaliação Institucional']),
    '8181003': ('Respondente AvalInt', ['Servidor']),
}

# Os nomes que a cadeia cria pela UI e reencontra depois. Eles aparecem nas capturas, então
# são nomes de trabalho plausíveis e SEM sufixo de unicidade; quem libera os nomes para esta
# rodada é `_aposentar_geracoes_anteriores`, que renomeia os homônimos deixados pelas
# execuções anteriores antes de o primeiro teste rodar.
NOMES = SimpleNamespace(
    eixo='Planejamento e Avaliação Institucional',
    dimensao='Planejamento e Avaliação',
    macroprocesso='Autoavaliação Institucional',
    indicador='Participação da comunidade na autoavaliação',
    tipo_avaliacao='Autoavaliação Institucional',
    avaliacao=f'Avaliação Integrada CPA {datetime.date.today().year}',
    comissao='CPA Local do Campus Zona Norte',
)

# `(modelo, campo do nome, chave em NOMES)` de tudo que a rodada cria pela UI com nome próprio.
NOMEADOS: tuple[tuple[str, str, str], ...] = (
    ('Eixo', 'descricao', 'eixo'),
    ('Dimensao', 'descricao', 'dimensao'),
    ('Macroprocesso', 'descricao', 'macroprocesso'),
    ('TipoAvaliacao', 'descricao', 'tipo_avaliacao'),
    ('Indicador', 'nome', 'indicador'),
    ('Avaliacao', 'nome', 'avaliacao'),
    ('ComissaoCPA', 'nome', 'comissao'),
)

# Áreas de vinculação: o SUAP as instala vazias, e o `IndicadorForm` pré-seleciona exatamente
# estas quatro descrições (`avaliacao_integrada/forms.py:146`).
AREAS_VINCULACAO = ('Ensino', 'Extensão', 'Pesquisa e Inovação', 'Atividades Estudantis')

# Os 14 segmentos, com o pk que o código espera. Ordem = a das constantes do model.
SEGMENTOS: tuple[tuple[int, str, str], ...] = (
    (1, 'CPA_CENTRAL', 'PI'),
    (2, 'CPA_CAMPUS', 'PI'),
    (3, 'GESTOR', 'PI'),
    (4, 'TECNICO', 'PI'),
    (5, 'ETEP', 'PI'),
    (6, 'DOCENTE', 'PI'),
    (7, 'ESTUDANTE', 'PI'),
    (8, 'DESLIGADO', 'PE'),
    (9, 'ALUNO_EGRESSO', 'PE'),
    (10, 'PAIS', 'PE'),
    (11, 'EMPRESA_PRESTADORA_SERVICO', 'PE'),
    (12, 'OUTRO_SOCIEDADE_CIVIL', 'PE'),
    (13, 'PROFISSIONAL_PRESTADOR_SERVICO', 'PE'),
    (14, 'SUPERVISOR_ESTAGIO', 'PE'),
)

# Os 5 níveis da escala padrão, na ordem em que o respondente os vê.
NIVEIS_ESCALA: tuple[tuple[int, str, str, str], ...] = (
    (0, 'Desconheço', '😶', 'E'),
    (1, 'Discordo', '☹️', 'D'),
    (2, 'Discordo parcialmente', '😐', 'C'),
    (3, 'Concordo parcialmente', '🙂', 'B'),
    (4, 'Concordo', '😃', 'A'),
)


def _semear_tabelas_de_apoio() -> None:
    """As quatro tabelas de apoio que o SUAP não instala e sem as quais telas não abrem."""
    from comum.models import Ano
    from rh.models import AreaVinculacao

    from avaliacao_integrada.models import EscalaLikert, NivelEscalaLikert, Segmento

    Ano.objects.get_or_create(ano=datetime.date.today().year)

    for pk, descricao, tipo in SEGMENTOS:
        Segmento.objects.update_or_create(pk=pk, defaults={'descricao': descricao, 'tipo': tipo})

    for ordem, descricao in enumerate(AREAS_VINCULACAO, start=1):
        # `get_or_create` NÃO serve: `AreaVinculacao.save()` (`rh/models/organizacao/
        # area_vinculacao.py:17`) é `def save(self)` — sem `*args`/`**kwargs` —, e o
        # `force_insert=True` que o `create()` passa estoura em `TypeError`.
        if not AreaVinculacao.objects.filter(descricao=descricao).exists():
            AreaVinculacao(descricao=descricao, ordem=ordem).save()

    escala = EscalaLikert.objects.get_or_create(nome='Escala Padrão', defaults={'ativo': True})[0]
    for nivel, descricao, emoji, criterio in NIVEIS_ESCALA:
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=nivel, defaults={'descricao': descricao, 'emoji': emoji, 'tipo_criterio': criterio}
        )


def _aposentar_geracoes_anteriores() -> None:
    """Tira de circulação o que as execuções anteriores desta suíte deixaram no banco.

    Vale quando o banco é reusado — depuração local com ``--reuse-db``; no CI, que nasce com
    banco novo, é no-op. Mesma necessidade do ``erros`` (que apaga os erros da view de
    abertura): a suíte não dá flush, então tudo o que a rodada anterior criou continua lá — e
    aqui isso não é ruído, é mudança de tela:

    * indicador antigo continua ``em_uso``, casa com o mesmo ano/segmento e **entra no
      questionário** desta rodada, dobrando as perguntas e as abas;
    * avaliação antiga continua vigente, aparece de novo na tela inicial do respondente e no
      *Serviços* da página pública;
    * comissão CPA antiga bate na ``UniqueConstraint`` de comissão ativa por campus e o
      cadastro desta rodada falharia na validação.

    Além do estado, **o nome**: os nomes de ``NOMES`` são fixos (é o que a captura mostra),
    então o homônimo da rodada anterior é renomeado para liberá-los. Sem isso o nome fixo
    apareceria duas vezes no autocomplete de *Eixo*/*Dimensão*, no select de *Avaliação* e nos
    ``.get(nome=...)`` da cadeia. Roda no ``doc_seed``, antes do primeiro teste: tudo que casa
    neste instante é de execução anterior.

    ``update`` e não ``delete`` de propósito: o histórico das rodadas anteriores fica no banco
    para inspeção, e apagar esbarraria nos ``on_delete=PROTECT`` do módulo. ``queryset.update``
    e não ``objeto.save()``: o ``save`` de vários models do SUAP tem efeito colateral, e aqui
    só se quer trocar uma coluna.
    """
    from avaliacao_integrada import models as modelos
    from avaliacao_integrada.models import Avaliacao, ComissaoCPA, Indicador

    Indicador.objects.filter(nome__startswith=NOMES.indicador).update(em_uso=False)
    Avaliacao.objects.filter(nome__startswith=NOMES.avaliacao).update(data_inicio=datetime.date(1999, 1, 1), data_termino=datetime.date(1999, 12, 31))
    ComissaoCPA.objects.filter(nome__startswith=NOMES.comissao).update(ativo=False)

    for nome_modelo, campo, chave in NOMEADOS:
        modelo = getattr(modelos, nome_modelo)
        # `startswith` e não `exact`: o indicador replicado nasce como `<nome> [Replicado]`.
        for pk, atual in modelo.objects.filter(**{f'{campo}__startswith': getattr(NOMES, chave)}).values_list('pk', campo):
            modelo.objects.filter(pk=pk).update(**{campo: f'{atual} [rodada anterior {pk}]'})


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Os três servidores com papel e as tabelas de apoio, antes da primeira request.

    Session-scoped e eager por causa do cache de permissão por processo: usuário que ganha
    grupo depois do primeiro login continua sem acesso. Tudo é idempotente
    (``update_or_create``/``get_or_create``), o que é obrigatório porque o banco é
    compartilhado entre os módulos da rodada e não há flush entre eles.
    """
    criar_servidores(campus('CZN', 'Campus Zona Norte'), SERVIDORES)
    _semear_tabelas_de_apoio()
    _aposentar_geracoes_anteriores()


@pytest.fixture(scope='session')
def servidores_doc(doc_seed) -> dict:
    """``{apelido: Servidor}`` dos papéis de ``PAPEIS``."""
    from rh.models import Servidor

    return {papel: Servidor.objects.get(matricula=matricula) for papel, matricula in PAPEIS.items()}


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def publico_alvo(nomes):
    """A avaliação da rodada com os respondentes já identificados.

    **Único ponto desta suíte em que o efeito de um botão é reproduzido por ORM**, e por um
    defeito de produção medido nesta rodada: ``Avaliacao.gerar_respondentes`` estoura em
    ``ZeroDivisionError`` sempre que o público-alvo tem **menos de 100 pessoas** —
    ``avaliacao_integrada/models.py:1334`` faz ``contador % (total // 100)`` para imprimir o
    progresso a cada 1%, e ``total // 100`` é ``0`` abaixo de cem. Com os 8 servidores do
    seed, clicar em *Reprocessar Público-Alvo* devolve a tela "Erro no Sistema" (medido).

    O que se reproduz aqui é só o laço de gravação: a consulta que decide **quem** entra é a
    de produção (``obter_publicoalvo``), e os campos gravados são os mesmos de
    ``_gerar_respondentes_segmento`` (``models.py:1300-1320``). Assim as telas que consomem o
    público-alvo — aba *Público-Alvo*, questionário, relatório — continuam sendo navegadas
    sobre dado que o próprio módulo produziria.
    """
    from rh.models import Setor

    from avaliacao_integrada.models import Avaliacao, Respondente, Segmento

    avaliacao = Avaliacao.objects.get(nome=nomes.avaliacao)
    # No `pytest -m doc` inteiro o banco é dos módulos todos: quem semeia técnico-administrativo
    # num setor fora da árvore do test_01 (ou depois dele) deixa "Setores com pendências", e a
    # aba Público-Alvo esconde os botões de reprocessar (`avaliacao.html:105-118`).
    pendentes = avaliacao.obter_servidores_sem_areas_vinculacao() or []
    for setor in Setor.objects.filter(pk__in={servidor['setor__id'] for servidor in pendentes}):
        setor.areas_vinculacao.add(*avaliacao.areas_vinculacao.all())
    for segmento_id, lista_dados in avaliacao.obter_publicoalvo().items():
        segmento = Segmento.objects.get(pk=segmento_id)
        for dados in lista_dados:
            if dados['uo_id']:
                Respondente.objects.get_or_create(avaliacao=avaliacao, user_id=dados['user_id'], uo_id=dados['uo_id'], segmento=segmento)
    return avaliacao


@pytest.fixture(scope='session')
def nomes(doc_seed) -> SimpleNamespace:
    """Os nomes que a cadeia de testes cria pela UI e reencontra depois (``NOMES``).

    Depende de ``doc_seed`` de propósito: é lá que ``_aposentar_geracoes_anteriores`` libera
    esses nomes renomeando os homônimos da execução anterior. Sem essa ordem, um nome fixo
    colidiria no banco compartilhado (o ``Eixo`` seria encontrado duas vezes e o ``.get()``
    estouraria) — foi por isso que a primeira versão marcou os nomes com um ``uuid4``, o que
    vazava a marca de teste para dentro das capturas.
    """
    return NOMES
