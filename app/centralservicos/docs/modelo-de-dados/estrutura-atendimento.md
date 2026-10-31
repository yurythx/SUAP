# Modelo de dados — Estrutura de Atendimento

> ERD das entidades que organizam quem atende e como (grupos, monitoramentos, grupos de
> interessados, respostas padrão). Models herdam `ModelPlus` de `djtools.db`. FKs para
> entidades de outras áreas aparecem como **externas**. Termos: ver `../GLOSSARIO.md`.

```mermaid
erDiagram
    GRUPO_ATENDIMENTO ||--o{ GRUPO_ATENDIMENTO : "grupo_atendimento_superior (auto-FK)"
    GRUPO_ATENDIMENTO }o--|| CENTRO_ATENDIMENTO : "centro_atendimento (externo)"
    GRUPO_ATENDIMENTO }o--|| UNIDADE_ORGANIZACIONAL : "campus (externo)"
    GRUPO_ATENDIMENTO }o--o{ USER : "atendentes / responsaveis (M2M, externo)"
    MONITORAMENTO }o--o{ GRUPO_ATENDIMENTO : "grupos (M2M)"
    MONITORAMENTO }o--|| USER : "cadastrado_por (externo)"
    GRUPO_INTERESSADO }o--|| GRUPO_ATENDIMENTO : "grupo_atendimento"
    GRUPO_INTERESSADO }o--o{ USER : "interessados (M2M, externo)"
    RESPOSTA_PADRAO }o--|| USER : "atendente (externo)"

    GRUPO_ATENDIMENTO {
        string nome
        FK centro_atendimento
        FK campus
        FK grupo_atendimento_superior
    }
    MONITORAMENTO {
        string titulo
        string token UK
        bool organizar_por_tipo
    }
    GRUPO_INTERESSADO {
        string titulo
    }
    RESPOSTA_PADRAO {
        int status
        text texto
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `GrupoAtendimento` | Equipe de atendimento de um centro/campus; hierarquia por `grupo_atendimento_superior` (auto-FK). | FK `centro_atendimento`, `campus`, auto-FK superior; M2M `atendentes`, `responsaveis` |
| `Monitoramento` | Painel de acompanhamento de chamados de grupos, acessível por `token`. | M2M `grupos`; FK `cadastrado_por` |
| `GrupoInteressado` | Conjunto pré-cadastrado de usuários a adicionar como interessados em lote. | FK `grupo_atendimento`; M2M `interessados` |
| `RespostaPadrao` | Texto padrão de um atendente para uma situação de chamado. | FK `atendente` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `User` | comum |
| `UnidadeOrganizacional` | rh |
| `CentroAtendimento` | centralservicos (subdomínio Catálogo de Serviços) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
