# Modelo de dados — Relatórios

Este recorte reúne a configuração de relatórios gerenciais, gráficos e as especializações de relatório oferecidas pelo módulo.

```mermaid
erDiagram
    RelatorioGestao { int id }
    RelatorioGestaoBase { int id }
    RelatorioGrafico { int id }
    DadosRelatorioGrafico { int id }
    RelatorioGestaoAtendimentos { int id }
    RelatorioGestaoAuxilios { int id }
    RelatorioGestaoBolsas { int id }
    RelatorioGestaoProgramas { int id }
    RelatorioGestaoSaude { int id }
    RelatorioGestaoResumo { int id }
    EXT_UnidadeOrganizacional { int id }

    RelatorioGestao }o--|| EXT_UnidadeOrganizacional : "escopo campus"
    RelatorioGrafico }o--|| RelatorioGestao : "pertence ao relatório"
    DadosRelatorioGrafico }o--|| RelatorioGrafico : "alimenta gráfico"
    RelatorioGestaoBase ||--o| RelatorioGestaoAtendimentos : "base abstrata"
    RelatorioGestaoBase ||--o| RelatorioGestaoAuxilios : "base abstrata"
    RelatorioGestaoBase ||--o| RelatorioGestaoBolsas : "base abstrata"
    RelatorioGestaoBase ||--o| RelatorioGestaoProgramas : "base abstrata"
    RelatorioGestaoBase ||--o| RelatorioGestaoSaude : "base abstrata"
    RelatorioGestaoBase ||--o| RelatorioGestaoResumo : "base abstrata"
```

| Entidade | Descrição |
|---|---|
| `RelatorioGestao` | Configuração/raiz de relatório de gestão, com unidade e parâmetros. |
| `RelatorioGestaoBase` | Classe abstrata compartilhada pelas especializações de relatório. |
| `RelatorioGrafico` | Configuração de gráfico pertencente a um relatório. |
| `DadosRelatorioGrafico` | Dados persistidos para renderização de um gráfico. |
| `RelatorioGestaoAtendimentos` | Relatório especializado de atendimentos. |
| `RelatorioGestaoAuxilios` | Relatório especializado de auxílios. |
| `RelatorioGestaoBolsas` | Relatório especializado de bolsas. |
| `RelatorioGestaoProgramas` | Relatório especializado de programas. |
| `RelatorioGestaoSaude` | Relatório especializado de saúde. |
| `RelatorioGestaoResumo` | Relatório especializado de resumo gerencial. |

## Referências externas

| Entidade | App | Uso |
|---|---|---|
| `UnidadeOrganizacional` | `rh` | Escopo organizacional do relatório. |

_Gerado/atualizado via subagent `documentador` em 2026-09-09._
