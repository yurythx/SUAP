# Painel de avaliadores no dashboard RSC-TAE

Data: 2026-07-28
Módulo: `rsc_tae`
Status: aprovado, pronto para plano de implementação

## Contexto

O dashboard RSC-TAE (`rsc_tae/views/dashboard.py` → `templates/rsc_tae/dashboard.html`) reúne
hoje 8 KPIs, 5 gráficos Highcharts, a tabela de processos em andamento e a tabela de alertas de
SLA. Sobre avaliadores existe apenas um gráfico: carga (top 10 em `EM_ANALISE`).

A gestão pediu mais informação sobre avaliadores, **separada do restante do conteúdo**.

## Objetivos

1. Acrescentar métricas de avaliadores em três eixos: carga/produtividade, qualidade da
   avaliação e gargalos/SLA por avaliador.
2. Isolar essas métricas do resto do dashboard, usando as abas nativas do Design System.
3. Corrigir o N+1 de `ProcessoRSCTae.get_sla_status()`, que hoje custa 2 queries por processo.

## Fora de escopo

- Composição da comissão (membros ativos, presidente, impedimentos) — descartado pelo usuário.
- Cache ou materialização das métricas. As agregações são baratas; sem evidência de necessidade.
- Testes automatizados (o time escreve testes sob demanda). Alvos naturais registrados na §7.

## Decisões

| Decisão | Escolha | Razão |
|---|---|---|
| Layout | KPIs gerais fixos no topo + 2 abas (`Visão geral`, `Avaliadores`) | Preserva o "olhar rápido" do dashboard e isola avaliadores sem esconder os números-chave |
| Carregamento | Síncrono, agregado no banco | As abas do DS renderizam todos os painéis no HTML e alternam visibilidade no cliente; lazy load exigiria fugir do componente padrão para economizar 4 queries |
| Nomes de avaliadores | Só membros ativos da CRSC veem nomes | Coerente com `injetar_visibilidade_avaliadores` (`_helpers.py:1410`), cuja justificativa é evitar coação |
| Universo de avaliadores | Todos que já foram sorteados | Não existe cadastro de avaliadores: `_listar_candidatos_avaliadores` devolve todo vínculo ativo, então "todos os avaliadores" só é calculável a partir do histórico de sorteios |

## 1. Métricas

Base: `AvaliacaoProcessoRSCTae`, sempre filtrando `substituido=False`. O modelo já carrega prazo
por avaliador (`data_notificacao_sorteio`, `data_limite_avaliacao`), então gargalo e tempo médio
não dependem do histórico do processo.

### 1.1 Carga e produtividade — 1 query (`GROUP BY avaliador_vinculo`)

| Coluna | Origem |
|---|---|
| Pendentes | `finalizada=False` e `processo__situacao=EM_ANALISE` |
| Finalizadas | `finalizada=True` |
| Tempo médio | `Avg(data_finalizacao − data_notificacao_sorteio)` em dias |
| Taxa de resposta | aceites ÷ (aceites + recusas + impedimentos + pendentes), via `resposta` |

Registros legados sem `data_notificacao_sorteio` ficam fora do tempo médio (não entram como zero).

A lista percorre o mapa de rótulos, não o resultado da consulta: todo avaliador já sorteado
aparece, mesmo zerado. Vale igualmente para Qualidade e Processos por Avaliador, para que as três
tabelas tenham sempre as mesmas linhas.

### 1.2 Qualidade — 1 query

Por avaliador: `finalizadas`, `com_resultado` (deferidas + indeferidas), a proporção entre elas e a
média de `itens_validados` das finalizadas.

`finalizadas` usa a mesma contagem do card de carga, então os dois cards batem. `com_resultado` é a
base da taxa de deferimento; quando os dois números diferem, existe avaliação concluída sem
resultado gravado — a tabela destaca a diferença em vez de escondê-la.

### 1.3 Processos por avaliador — 2 queries

Lista **todos** os avaliadores já sorteados, inclusive os que estão sem processo em mãos, para que
a comissão enxergue quem está livre. Por avaliador: os processos em aberto (avaliação não
finalizada em processo `EM_ANALISE`), há quantos dias cada um está com ele, a situação do prazo
individual de cada processo, e os totais históricos de recusas e impedimentos.

O tempo "em mãos" conta de `data_notificacao_sorteio`; sorteios antigos sem essa data caem em
`data_cadastro` da avaliação, a melhor aproximação disponível.

**Apresentação:** uma caixa retrátil (`{% box titulo 'collapsed' boxid badge extra=... %}`) por
avaliador — fechada mostra nome, contador de processos e o resumo (mais antigo, recusas,
impedimentos); aberta mostra a tabela dos processos dele. Sem isso, um avaliador com 20 processos
esticava a linha da tabela. `boxid` é posicional (`processos-avaliador-N`) para não expor o id do
vínculo com os nomes anonimizados nem colidir entre homônimos. Avaliadores sem processo em mãos
não viram accordion vazio: saem numa linha única no rodapé do card.

Substituiu o card de divergência de pontuação entre avaliadores, descartado por ser informativo e
não operacional.

### 1.4 Gargalos e SLA — 1 query

Avaliações `finalizada=False` com `data_limite_avaliacao` vencida (atrasada) ou a 3 dias ou menos
(alerta), agrupadas por avaliador, com dias de atraso. Avaliações sem `data_limite_avaliacao`
são omitidas.

### 1.5 KPIs da aba

Avaliadores com carga, avaliações pendentes, avaliações atrasadas, tempo médio geral.

## 2. Anonimização

```python
def rotulos_avaliadores(request) -> dict:
    """vinculo_id -> nome real (membro ativo da CRSC) ou 'Avaliador N' (demais)."""
```

Ordem estável por `vinculo_id`, mesma convenção de `rotulos_anonimos_avaliadores`
(`_helpers.py:1394`). Aplicada a todas as séries e tabelas da aba nova **e ao gráfico
"carga por avaliador" já existente** — este mostra `pessoa__nome` para todo usuário com acesso
ao dashboard, inclusive RH sistêmico, contrariando a regra que o módulo aplica nas telas de
processo. A correção faz parte deste trabalho.

O dashboard continua acessível a `rh.eh_rh_sistemico` ou `rsc_tae.definir_avaliador_processorsctae`;
o que muda é apenas o rótulo exibido.

## 3. Arquitetura

```
rsc_tae/views/dashboard_avaliadores.py                          (novo)
    rotulos_avaliadores(request) -> dict
    carga_por_avaliador(rotulos) -> list[dict]
    qualidade_por_avaliador(rotulos) -> list[dict]
    processos_por_avaliador(rotulos) -> list[dict]
    gargalos_por_avaliador(rotulos) -> list[dict]
    montar_painel_avaliadores(request) -> dict

rsc_tae/views/dashboard.py                                      (chama e injeta 1 chave)
rsc_tae/templates/rsc_tae/dashboard.html                        (KPIs + 2 includes)
rsc_tae/templates/rsc_tae/partials/dashboard_geral.html         (recorte do template atual)
rsc_tae/templates/rsc_tae/partials/dashboard_avaliadores.html   (novo)
```

As quatro funções de métrica são puras: recebem `rotulos` e devolvem listas de dicts, sem tocar
em `request`. `dashboard.py` volta a ser orquestração e KPIs.

Nenhuma tabela é cortada por limite de linhas: a comissão precisa da lista completa de avaliadores.
"Gargalos" é a exceção natural, porque só lista quem tem prazo vencido ou vencendo. O gráfico de
carga também omite os zerados de propósito — barra de tamanho zero não comunica nada.

Abas via componente nativo do DS (`comum/templates/tabs/guia_navegacao.html:64`): cada painel
envolvido em `<div class="tab-pane" data-title="…">`, com `data-counter` na aba de avaliadores.
Sem CSS e sem JS novos; nenhum `style=""` e nenhuma cor hardcoded.

## 4. Fix do N+1 de SLA

`ProcessoRSCTae.get_sla_status()` hoje executa, por processo: `ConfiguracaoRSCTae.objects.first()`
(`processo.py:490`, sem cache) e a busca do último `HistoricoSituacaoProcessoRSCTae`
(`processo.py:430`).

Alteração retrocompatível — chamada sem argumentos mantém o comportamento atual:

```python
def get_sla_status(self, configuracao=None, data_entrada=None):
    config = configuracao or self._get_configuracao()
    ...
    if data_entrada is None:
        data_entrada = getattr(self, 'sla_data_entrada', None)
    if data_entrada is None:
        <busca o histórico como hoje>
```

Mais um método de queryset `anotar_sla_data_entrada()`, que traz a data por `Subquery` do último
`HistoricoSituacaoProcessoRSCTae` com `situacao_nova=OuterRef('situacao')`.

Aplicar nos três chamadores:

| Arquivo | Situação hoje |
|---|---|
| `rsc_tae/views/dashboard.py:120` | 2 queries por processo ativo |
| `rsc_tae/admin/processo.py:342` | 2 queries por linha da listagem |
| `rsc_tae/views/processo.py:380` | 2 queries por processo da lista |

Cada um passa a buscar a configuração uma vez e a usar o queryset anotado.

## 5. Fluxo de dados

1. `dashboard()` valida permissão (inalterado).
2. Calcula KPIs gerais e os dados da aba "Visão geral" (inalterado, exceto o queryset anotado e a
   configuração injetada em `get_sla_status`).
3. Chama `montar_painel_avaliadores(request)`, que resolve os rótulos e roda as agregações das quatro métricas.
4. Injeta `painel_avaliadores` no contexto; o template distribui entre os dois `tab-pane`.

## 6. Erros e casos-limite

- Sem comissão ativa ou sem avaliadores: blocos renderizam vazios com mensagem, sem quebrar.
- `data_notificacao_sorteio` ou `data_limite_avaliacao` nulos: registro omitido da métrica
  correspondente, nunca tratado como zero.
- Avaliador sem processo em mãos: aparece em "Processos por Avaliador" com a lista vazia, não é omitido.
- Divisão por zero em taxas: retorna `None`, exibido como `—`.

## 7. Critérios de aceitação

1. O dashboard mostra KPIs fixos no topo e duas abas abaixo; a aba de avaliadores traz os três
   blocos e seus quatro KPIs.
2. Usuário com `rh.eh_rh_sistemico` e sem vínculo ativo na CRSC vê `Avaliador N` em todos os
   pontos da tela, incluindo o gráfico de carga preexistente.
3. Membro ativo da CRSC vê os nomes reais.
4. O número de queries do dashboard deixa de crescer com a quantidade de processos ativos.
5. `ruff format` e `ruff check` passam; nenhuma classe CSS fora do Design System.

Alvos naturais de teste, se o time pedir: as quatro funções puras de `dashboard_avaliadores.py` e
uma asserção de contagem de queries no dashboard com N processos ativos.
