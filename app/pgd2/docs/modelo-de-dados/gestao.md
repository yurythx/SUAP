# Modelo de dados — Gestão/Comissão

> ERD das entidades de gestão e comissão do PGD (models herdam `ModelPlus` de `djtools.db`).
> FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [Glossário](../GLOSSARIO.md).

```mermaid
erDiagram
    ComissaoPGD ||--o{ ParticipantePgd : "participantes"
    SetorHabilitacao ||--o{ ParticipantePgd : "participantes_habilitados"
    ComissaoPGD {
        int id PK
        int servidor FK "rh.Servidor"
        int setor FK "rh.Setor"
        string tipo "sistemica/local"
        boolean ativo
    }
    ParticipantePgd {
        int id PK
        int solicitacao_adesao FK "Adesao"
        int setor FK "rh.Setor"
        date data_inicio
        date data_fim
    }
    SetorHabilitacao {
        int id PK
        int setor FK "rh.Setor"
        int comissao FK
        boolean habilitado
    }
    JustificativaDesligamentoPgd {
        int id PK
        string descricao
        boolean ativo
    }
    ControleRecorrenciaPGD {
        int id PK
        string chave "unica"
        datetime ultima_execucao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `ComissaoPGD` | Membro da comissão de gestão do PGD | FK `servidor`, FK `setor` (rh); tipo: sistêmica/local |
| `ParticipantePgd` | Vínculo servidor-setor como participante ativo | FK `solicitacao_adesao`, FK `setor` (rh) |
| `SetorHabilitacao` | Habilitação de setor para participação no PGD | FK `setor` (rh), FK `comissao` |
| `JustificativaDesligamentoPgd` | Catálogo de justificativas para desligamento | — |
| `ControleRecorrenciaPGD` | Controle de execução de tarefas recorrentes | Chave única |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Servidor` | `rh` |
| `Setor` | `rh` |
| `SolicitacaoAdesaoServidor` | Adesão (mesmo módulo) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
