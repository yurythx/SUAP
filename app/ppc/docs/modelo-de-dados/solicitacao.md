# Modelo de dados — Solicitação (PPC)

> ERD do subdomínio de solicitação de PPC (pedido, colegiado, indicação de elaboradores
> e movimentações). Models herdam `LogModel`. Termos: ver [../GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    SOLICITACAO_PPC ||--o{ MEMBRO_COLEGIADO : "colegiado"
    SOLICITACAO_PPC ||--o{ INDICACAO_ELABORADOR_PPC : "indicacoes"
    SOLICITACAO_PPC ||--o{ MOVIMENTACAO_SOLICITACAO_PPC : "movimentacoes"
    SOLICITACAO_PPC }o--|| SERVIDOR : "solicitante"
    SOLICITACAO_PPC }o--|| SETOR : "setor_solicitacao"
    SOLICITACAO_PPC }o--|| MODALIDADE : "tipo_oferta"
    SOLICITACAO_PPC }o--o| PROJETO_PEDAGOGICO_CURSO : "ppc_adequacao (externo)"
    MEMBRO_COLEGIADO }o--|| SERVIDOR : "servidor"
    INDICACAO_ELABORADOR_PPC }o--|| SERVIDOR : "servidor"
    MOVIMENTACAO_SOLICITACAO_PPC }o--o| VINCULO : "usuario"
    SOLICITACAO_PPC {
        string situacao
        string tipo_solicitacao
        text justificativa
        string nome_curso
        int id_ata
        int id_portaria
    }
    INDICACAO_ELABORADOR_PPC {
        string funcao
        string representacao
        bool deferido
    }
    MOVIMENTACAO_SOLICITACAO_PPC {
        datetime data
        string situacao
        string acao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `SolicitacaoPPC` | Pedido de criação/adequação de PPC; máquina de estado (`SOLICITADA`→…→`FINALIZADA`) | FK `rh.Servidor`, `rh.Setor`, `edu.Modalidade`, `edu.NaturezaParticipacao`, `edu.EixoTecnologico`, `edu.Convenio`, `ProjetoPedagogicoCurso` (adequação) |
| `MembroColegiado` | Membro do colegiado que aprova a ata da solicitação | FK `SolicitacaoPPC`, `rh.Servidor` |
| `IndicacaoElaboradorPPC` | Indicação (com representação) de um servidor para a comissão de elaboração | FK `SolicitacaoPPC`, `rh.Servidor` (indicado e avaliador) |
| `MovimentacaoSolicitacaoPPC` | Registro de cada transição de situação da solicitação | FK `SolicitacaoPPC`, `comum.Vinculo` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Servidor`, `Setor` | `rh` |
| `Modalidade`, `NaturezaParticipacao`, `EixoTecnologico`, `Convenio` | `edu` |
| `Vinculo` | `comum` |
| `ProjetoPedagogicoCurso` | `ppc` (subdomínio Projeto) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
