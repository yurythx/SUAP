# Fluxo: Analisar indicador

> Ver, para uma avaliação, quais indicadores receberam resposta e abrir o detalhamento de um deles: distribuição de frequência, gráficos e medidas-resumo.

- **Ator(es):** Aplicador, Administrador ou Visualizador de Avaliação Institucional — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** `GET /avaliacao_integrada/relatorio/` (menu Des. Institucional › Avaliação Integrada › Relatórios) → `GET /avaliacao_integrada/relatorio/<pk>/<pk_avaliacao>/`
- **Pré-condições:** existir ao menos uma `Resposta` para a avaliação escolhida
- **Pós-condições:** nenhuma escrita — fluxo somente de leitura
- **Depende de:** [Responder questionário (interno)](responder-questionario-interno.md), [Responder questionário (sociedade civil)](responder-questionario-externo.md)
- **Habilita:** [Exportar respostas (XLSX)](exportar-respostas-xlsx.md)
- **Entrada no código:** `views.relatorio` (`pode_ver_relatorios`) + `forms.RelatorioForm`; `views.exibir_relatorio_indicador` (`pode_ver_relatorio_indicadores`) + `forms.FiltroIndicadorForm`

## Sequência

```mermaid
sequenceDiagram
    participant U as "Aplicador / Visualizador"
    participant V1 as "views.relatorio"
    participant F1 as "RelatorioForm"
    participant V2 as "views.exibir_relatorio_indicador"
    participant M as "Resposta.get / Respondente.apply_filters"
    participant DB as PostgreSQL
    U->>V1: "GET /relatorio/?avaliacao=..&tipos=.."
    V1->>F1: "processar()"
    F1->>DB: "indicadores com ao menos 1 resposta na avaliação"
    V1-->>U: "lista agrupada por eixo / dimensão / macroprocesso"
    U->>V2: "GET /relatorio/<indicador>/<avaliacao>/"
    V2->>M: "filtra respostas e respondentes (segmentos, áreas, campi, modalidades, cursos)"
    M->>DB: "SELECT respostas + universo de respondentes"
    V2->>V2: "distribuição de frequência (geral e efetiva); numpy: média ponderada, mediana, variância, desvio, moda, CV"
    V2-->>U: "tabelas + gráficos (StackedGroupedColumn / Pie / Bar)"
    U->>V2: "POST (Filtrar)"
    V2-->>U: "mesma tela recalculada com o recorte"
```

## Observações

- **A lista só mostra indicadores com resposta:** `RelatorioForm.processar` parte de `Resposta`, não de
  `Indicador` — indicador sem nenhuma resposta não aparece.
- **Universo × respondentes:** `qtd_respondentes` é o público-alvo filtrado; `qtd_respostas` conta
  respondentes **distintos** com resposta para aquele indicador. O percentual é a razão entre os dois.
- **Respostas efetivas** excluem os níveis cujo `tipo_criterio` é "Desconheço" ou "Não se aplica"; as
  medidas-resumo (numpy) usam apenas essas. A média é **ponderada** pelas frequências dos valores
  distintos, enquanto mediana, variância, desvio e moda usam a lista bruta de valores efetivos.
- **A visualização depende do tipo de resposta:**
  - Escala Likert / número inteiro → distribuição + colunas empilhadas + pizza + medidas-resumo;
  - escolha única → pizza de ranking; múltipla escolha → barras (o valor é desmembrado por `::`);
  - texto curto autocalculado → pizza de ranking; a exceção é "Data de nascimento", que vira
    histograma por ano (só anos entre 1930 e 2010).
- **Indicador com iterador** só é calculado após aplicar o filtro (`exibir_mensagem = True` no GET
  inicial): sem recorte, misturaria respostas de objetos diferentes.
- O `FiltroIndicadorForm` restringe `segmentos` aos segmentos do próprio indicador; sem POST, o cálculo
  usa todos eles.
- Os filtros são aplicados por `Resposta.get` e `Respondente.apply_filters`, que compartilham a mesma
  semântica (segmento, área de vinculação do setor do vínculo, campus, modalidade e curso do aluno) —
  é o que garante que numerador e denominador falem do mesmo universo.

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
