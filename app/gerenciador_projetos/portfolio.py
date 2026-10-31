"""Portfólio de projetos: as regras de consulta que valem para *vários* projetos de uma vez.

Por que este módulo existe
--------------------------
Até outubro de 2026 o Gerenciador de Projetos só sabia olhar um projeto por vez: cada tela
(projeto, dashboard, Gantt, calendário, status, evolução) recebe um `projeto_id` e pergunta ao
próprio objeto (`Projeto.pode_ver_projeto`, `Projeto.total_progresso_automatico` etc.).

A gestão estratégica precisa acompanhar **todos** os projetos sem entrar um por um. Daí vieram:

- o grupo *Monitor de Projetos*, que lê todos os projetos **públicos** sem ser da equipe (os
  privados podem ter dados sensíveis, como senhas de acesso, e ficam só com a equipe);
- a comparação de projetos (Painel, Gráficos, Gantt e Calendário): percentual de evolução,
  situação e tarefas atrasadas ou próximas do prazo de vários projetos lado a lado.

Olhar vários projetos de uma vez trouxe três problemas que não cabiam no model nem nas views:

1. **Quem vê o quê precisa de uma regra só.** A listagem do admin filtrava por equipe com um
   `Q(...)` próprio, e a página do projeto checava papel por papel. Com o grupo Monitor e as
   telas de comparação, seriam três lugares para manter em sincronia — e um esquecido vira
   vazamento de projeto privado. `projetos_visiveis` é essa regra única: o admin, o formulário
   de seleção e as telas de comparação perguntam aqui.

2. **O % de evolução não escalava.** `Projeto.total_progresso_automatico` fazia uma query por
   tarefa raiz (contar subtarefas, contar as abertas). Para um projeto, tolerável; para um
   painel com 50 projetos de 30 tarefas, eram milhares de queries. `progresso_por_projeto`
   calcula a mesma regra para N projetos numa query só, e o model passou a delegar a ela:
   continua havendo **uma única fonte** do cálculo. Se a regra mudar (por exemplo, para
   um registro de evolução de 0 a 100), ela muda aqui, e a página do projeto e a
   comparação mudam juntas.

3. **"Atrasado" ainda não tem definição oficial.** O critério de atraso é provisório, ainda
   sujeito a validação com a gestão do módulo. Ele fica concentrado
   aqui (`DIAS_VENCENDO`, `status_prazo`, as contagens de `indicadores`) para mudar num lugar só,
   sem caçar comparações de data espalhadas por views e templates.

O que fica fora daqui
---------------------
Este módulo só **consulta**: não renderiza, não checa permissão de modelo (`view_projeto`, que é
das views) e não altera nada. As views de comparação (`views.py`) montam o contexto a partir
dele; os testes estão em `tests/models/test_portfolio.py`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Max, Min, Prefetch, Q, QuerySet

from comum.models import User
from gerenciador_projetos.enums import SituacaoProjeto, SituacaoTarefa, VisibilidadeProjeto
from gerenciador_projetos.models import Projeto, Tarefa


# Critério de atraso provisório (sujeito a validação): tarefa "atrasada" é a que não está
# concluída nem cancelada e já passou da conclusão estimada; "vencendo" é a que vence em até
# DIAS_VENCENDO dias, contando hoje.
DIAS_VENCENDO = 7
SITUACOES_ENCERRADAS = (SituacaoTarefa.CONCLUIDA, SituacaoTarefa.CANCELADA)
ORDEM_SITUACOES = (
    SituacaoTarefa.ABERTA,
    SituacaoTarefa.EM_ANDAMENTO,
    SituacaoTarefa.EM_ANALISE,
    SituacaoTarefa.SUSPENSA,
    SituacaoTarefa.CONCLUIDA,
    SituacaoTarefa.CANCELADA,
)


class StatusPrazo:
    """Situação do projeto diante da própria conclusão estimada."""

    CONCLUIDO = 'Concluído'
    CANCELADO = 'Cancelado'
    ATRASADO = 'Atrasado'
    NO_PRAZO = 'No prazo'
    SEM_PRAZO = 'Sem prazo'


@dataclass(frozen=True)
class IndicadoresProjeto:
    """Uma linha do painel de comparação. `inicio` e `fim` são a barra do projeto no Gantt."""

    projeto: Projeto
    por_situacao: dict[int, int]
    atrasadas: int
    vencendo: int
    progresso: float
    status_prazo: str
    inicio: date
    fim: date | None

    @property
    def contagens_ordenadas(self) -> list[int]:
        """Contagens na ordem das colunas do painel (a do fluxo da tarefa, não a dos `choices`)."""
        return [self.por_situacao[codigo] for codigo in ORDEM_SITUACOES]


def projetos_visiveis(user: User) -> QuerySet[Projeto]:
    """Projetos que o usuário pode ver: aqueles em que é gerente, membro ou interessado e, para o
    Monitor de Projetos, também todos os públicos. Projeto privado nunca sai da equipe.

    O resultado tem `distinct()` por causa do join com a equipe: quem agrega sobre ele deve
    refiltrar por `pk__in=projetos_visiveis(user).values('pk')`, senão as contagens multiplicam.
    """
    equipe = Q(gerentes=user) | Q(membros=user) | Q(interessados=user)
    if Projeto.eh_monitor_projetos(user):
        equipe |= Q(visibilidade=VisibilidadeProjeto.PUBLICO)
    return Projeto.objects.filter(equipe).distinct()


def projetos_selecionados(user: User, ids: list[str]) -> QuerySet[Projeto]:
    """Os projetos pedidos na URL (`?projeto=<id>`) que o usuário pode ver, por título.

    Id inválido, inexistente ou de projeto alheio é descartado em silêncio: responder "sem
    acesso" confirmaria que o projeto existe.
    """
    # `isdigit` aceita '²', que o `int` recusa: só dígitos ASCII viram id.
    validos = [int(i) for i in ids if i.isascii() and i.isdecimal()]
    return Projeto.objects.filter(pk__in=validos).filter(pk__in=projetos_visiveis(user).values('pk')).order_by('titulo')


def _progresso_raiz(situacao: int, qtd_subtarefas: int, qtd_subtarefas_abertas: int) -> float:
    """% de uma tarefa raiz: a fração das subtarefas concluídas; sem subtarefas, 100 se concluída."""
    if qtd_subtarefas:
        return 100 - (qtd_subtarefas_abertas * 100) / qtd_subtarefas
    return 100 if situacao == SituacaoTarefa.CONCLUIDA else 0


def progresso_por_projeto(projetos: Iterable[Projeto]) -> dict[int, float]:
    """% de evolução de cada projeto, numa query para todos.

    É a média do % das tarefas raiz não canceladas (`_progresso_raiz`); projeto sem tarefa raiz
    vale 0. A regra é a mesma que `Projeto.total_progresso_automatico` sempre usou — ele agora
    delega para cá. A subtarefa conta como concluída pela `data_conclusao`, a raiz sem subtarefas
    pela `situacao`, como antes.
    """
    ids = [projeto.pk for projeto in projetos]
    raizes = (
        Tarefa.objects.filter(projeto_id__in=ids, tarefa_pai__isnull=True)
        .exclude(situacao=SituacaoTarefa.CANCELADA)
        .annotate(
            qtd_sub=Count('gerenciador_tarefa_pai_set'),
            qtd_sub_abertas=Count('gerenciador_tarefa_pai_set', filter=Q(gerenciador_tarefa_pai_set__data_conclusao__isnull=True)),
        )
        # Sem o `order_by()` o `ordering` do Meta entra no GROUP BY e quebra a contagem.
        .order_by()
        .values_list('projeto_id', 'situacao', 'qtd_sub', 'qtd_sub_abertas')
    )
    por_projeto: dict[int, list[float]] = defaultdict(list)
    for projeto_id, situacao, qtd_sub, qtd_sub_abertas in raizes:
        por_projeto[projeto_id].append(_progresso_raiz(situacao, qtd_sub, qtd_sub_abertas))
    # Mesma expressão do cálculo antigo, para o arredondamento do `:.0f` não mudar.
    return {pk: (sum(por_projeto[pk]) / (len(por_projeto[pk]) * 100)) * 100 if por_projeto[pk] else 0 for pk in ids}


def status_prazo(projeto: Projeto, hoje: date) -> str:
    if projeto.situacao == SituacaoProjeto.CONCLUIDO:
        return StatusPrazo.CONCLUIDO
    if projeto.situacao == SituacaoProjeto.CANCELADO:
        return StatusPrazo.CANCELADO
    if not projeto.data_conclusao_estimada:
        return StatusPrazo.SEM_PRAZO
    return StatusPrazo.ATRASADO if projeto.data_conclusao_estimada < hoje else StatusPrazo.NO_PRAZO


def _anotados(projetos: QuerySet[Projeto], hoje: date) -> QuerySet[Projeto]:
    """Os projetos com as contagens de tarefas anotadas, numa query.

    Refiltra por pk: `projetos` pode vir de `projetos_visiveis`, cujo join com a equipe
    multiplicaria cada contagem pelo número de papéis do usuário no projeto.
    """
    aberta = ~Q(tarefa__situacao__in=SITUACOES_ENCERRADAS)
    vencendo = Q(tarefa__data_conclusao_estimada__range=(hoje, hoje + timedelta(days=DIAS_VENCENDO)))
    por_situacao = {f'qtd_{codigo}': Count('tarefa', filter=Q(tarefa__situacao=codigo)) for codigo, _ in SituacaoTarefa.choices}
    return (
        Projeto.objects.filter(pk__in=projetos.values('pk'))
        .select_related('uo')
        .prefetch_related('areas', Prefetch('gerentes', queryset=User.objects.select_related('vinculo__pessoa__pessoafisica')))
        .annotate(
            **por_situacao,
            qtd_atrasadas=Count('tarefa', filter=aberta & Q(tarefa__data_conclusao_estimada__lt=hoje)),
            qtd_vencendo=Count('tarefa', filter=aberta & vencendo),
            primeiro_inicio=Min('tarefa__data_inicio'),
            ultimo_prazo=Max('tarefa__data_conclusao_estimada'),
        )
        .order_by('titulo')
    )


def indicadores(projetos: QuerySet[Projeto], hoje: date) -> list[IndicadoresProjeto]:
    """Indicadores de cada projeto, por título, em número constante de queries.

    A barra do Gantt vai do primeiro início de tarefa (sem nenhum, da criação do projeto) até a
    conclusão estimada do projeto (sem ela, o último prazo das tarefas; sem nenhum, `None`).
    """
    anotados = list(_anotados(projetos, hoje))
    progresso = progresso_por_projeto(anotados)
    return [
        IndicadoresProjeto(
            projeto=p,
            por_situacao={codigo: getattr(p, f'qtd_{codigo}') for codigo, _ in SituacaoTarefa.choices},
            atrasadas=p.qtd_atrasadas,
            vencendo=p.qtd_vencendo,
            progresso=progresso[p.pk],
            status_prazo=status_prazo(p, hoje),
            inicio=p.primeiro_inicio or p.criado_em.date(),
            fim=p.data_conclusao_estimada or p.ultimo_prazo,
        )
        for p in anotados
    ]
