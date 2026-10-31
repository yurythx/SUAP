# Modelo de dados — API/Integração e Logs

> ERD das entidades de integração com API PGD e logs (models herdam `ModelPlus` de `djtools.db`).
> FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [Glossário](../GLOSSARIO.md).

```mermaid
erDiagram
    LogApi ||--o{ LogApiDetalhe : "detalhes"
    LogApi ||--o{ LogApiPesEnvio : "envios_pes"
    LogApi ||--o{ LogApiParticipanteEnvio : "envios_participante"
    LogApi ||--o{ LogApiPitEnvio : "envios_pit"
    LogApi {
        int id PK
        int servidor FK "rh.Servidor"
        datetime data_envio
        string status "sucesso/erro"
        string erro_impeditivo
        int qtd_envios
    }
    LogApiDetalhe {
        int id PK
        int log_api FK
        string endpoint
        string payload
        string response
        int status_code
    }
    LogApiPesEnvio {
        int id PK
        int log_api FK
        int plano_entregas_setorial FK "PES"
        string status_envio
    }
    LogApiParticipanteEnvio {
        int id PK
        int log_api FK
        int solicitacao_adesao FK "Adesao"
        string status_envio
    }
    LogApiPitEnvio {
        int id PK
        int log_api FK
        int plano_individual_trabalho FK "PIT"
        string status_envio
    }
    SetorPgdApi {
        int id PK
        int setor FK "rh.Setor"
        string cod_siape_grupo
        string sigla_diferente
        boolean eh_reitoria
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `LogApi` | Registro de envio de dados à API PGD | FK `servidor` (rh); 1:N com detalhes e envios específicos |
| `LogApiDetalhe` | Detalhe por chamada HTTP ao endpoint da API | FK `log_api` |
| `LogApiPesEnvio` | Status de envio de PES específico | FK `log_api`, FK `plano_entregas_setorial` |
| `LogApiParticipanteEnvio` | Status de envio de participante específico | FK `log_api`, FK `solicitacao_adesao` |
| `LogApiPitEnvio` | Status de envio de PIT específico | FK `log_api`, FK `plano_individual_trabalho` |
| `SetorPgdApi` | Mapeamento de setor SUAP para API PGD (códigos SIAPE, siglas) | FK `setor` (rh) |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Servidor` | `rh` |
| `Setor` | `rh` |
| `PlanoEntregasSetorial` | PES (mesmo módulo) |
| `SolicitacaoAdesaoServidor` | Adesão (mesmo módulo) |
| `PlanoIndividualTrabalho` | PIT (mesmo módulo) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
