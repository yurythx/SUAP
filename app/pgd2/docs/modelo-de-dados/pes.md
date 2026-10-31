# Modelo de dados — PES (Plano de Entregas Setorial)

> ERD das entidades de PES (models herdam `ModelPlus` de `djtools.db`).
> FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [Glossário](../GLOSSARIO.md).

```mermaid
erDiagram
    PeriodoPes ||--o{ PlanoEntregasSetorial : "planos"
    PlanoEntregasSetorial ||--o{ PlanoEntregasSetorialEntregas : "entregas"
    PlanoEntregasSetorial ||--o{ PlanoEntregasSetorialHorarioFuncionamentoSetor : "horarios"
    PlanoEntregasSetorial ||--o{ PlanoEntregasSetorialHorarioPlanejamentoSetor : "planejamentos"
    PlanoEntregasSetorial ||--o{ RegistroAcaoPES : "registros"
    PlanoEntregasSetorial ||--|| PlanoEntregasSetorialAprovacao : "aprovacao"
    PlanoEntregasSetorial ||--|| PlanoEntregasSetorialAvaliacao : "avaliacao"
    PlanoEntregasSetorial ||--|| PlanoEntregasSetorialConsulta : "consulta"
    PlanoEntregasSetorialEntregas ||--o{ PlanoIndividualTrabalhoEntregas : "entregas_pit"
    PlanoEntregasSetorial {
        int id PK
        int setor FK "rh.Setor"
        int periodo_pes FK
        int situacao "enum"
        int responsavel FK "rh.Servidor"
    }
    PeriodoPes {
        int id PK
        int ano
        date data_inicio
        date data_fim
        string titulo
        date data_prazo_solicitar_avaliacao_execucao
    }
    PlanoEntregasSetorialEntregas {
        int id PK
        int plano_entregas_setorial FK
        string titulo
        string descricao
        int situacao "enum"
    }
    PlanoEntregasSetorialHorarioFuncionamentoSetor {
        int id PK
        int plano_entregas_setorial FK
        string dia_semana
        time hora_inicio
        time hora_fim
    }
    PlanoEntregasSetorialHorarioPlanejamentoSetor {
        int id PK
        int plano_entregas_setorial FK
        string dia_semana
        time hora_inicio
        time hora_fim
    }
    RegistroAcaoPES {
        int id PK
        int plano_entregas_setorial FK
        string acao
        datetime data_hora
    }
    ConfiguracaoOrientacaoPlanoEntregasSetorial {
        int id PK
        string orientacao
        boolean ativo
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `PeriodoPes` | Período de referência do PES (ex.: 2024.1) | 1:N com `PlanoEntregasSetorial` |
| `PlanoEntregasSetorial` | Plano de entregas do setor | FK `setor` (rh), FK `periodo_pes` |
| `PlanoEntregasSetorialAprovacao` | Herda PES; proxy para aprovação | Herda `PlanoEntregasSetorial` |
| `PlanoEntregasSetorialAvaliacao` | Herda PES; proxy para avaliação | Herda `PlanoEntregasSetorial` |
| `PlanoEntregasSetorialConsulta` | Herda PES; proxy para consulta | Herda `PlanoEntregasSetorial` |
| `PlanoEntregasSetorialEntregas` | Entrega definida no PES | FK `plano_entregas_setorial` |
| `PlanoEntregasSetorialHorarioFuncionamentoSetor` | Horário de funcionamento do setor no PES | FK `plano_entregas_setorial` |
| `PlanoEntregasSetorialHorarioPlanejamentoSetor` | Horário de planejamento do setor no PES | FK `plano_entregas_setorial` |
| `ConfiguracaoOrientacaoPlanoEntregasSetorial` | Orientações/configuração para elaboração do PES | Singleton |
| `RegistroAcaoPES` | Log de ações no PES | Herda `RegistroAcaoPGD` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Setor` | `rh` |
| `Servidor` | `rh` |
| `PlanoIndividualTrabalhoEntregas` | PIT (mesmo módulo) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
