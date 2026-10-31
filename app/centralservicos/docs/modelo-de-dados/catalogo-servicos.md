# Modelo de dados — Catálogo de Serviços

> ERD das entidades do catálogo (o que pode ser solicitado e por quem é atendido). Models
> herdam `ModelPlus` de `djtools.db`. FKs para entidades de outras áreas aparecem como
> **externas**. Termos: ver Glossário (`../GLOSSARIO.md`).

```mermaid
erDiagram
    CATEGORIA_SERVICO }o--o{ GRUPO_SERVICO : "categorias (M2M)"
    GRUPO_SERVICO ||--o{ SERVICO : "agrupa"
    SERVICO }o--o{ CENTRO_ATENDIMENTO : "centros_atendimento (M2M)"
    SERVICO }o--o{ PUBLICO : "publico_direcionado (M2M, externo)"
    SERVICO }o--|| AREA_ATUACAO : "area (externo)"
    CATEGORIA_SERVICO }o--|| AREA_ATUACAO : "area (externo)"
    CENTRO_ATENDIMENTO }o--|| AREA_ATUACAO : "area (externo)"
    TAG }o--|| AREA_ATUACAO : "area (externo)"
    GESTOR_AREA_SERVICO }o--|| AREA_ATUACAO : "area (externo)"
    GESTOR_AREA_SERVICO }o--|| USER : "gestor (externo)"

    SERVICO {
        string nome
        string tipo "REQ/INC"
        int sla_em_horas
        bool ativo
        bool interno
        bool requer_numero_patrimonio
    }
    GRUPO_SERVICO {
        string nome
        string detalhamento
        string icone
    }
    CATEGORIA_SERVICO {
        string nome
    }
    CENTRO_ATENDIMENTO {
        string nome
        bool eh_local
    }
    TAG {
        string nome
    }
    GESTOR_AREA_SERVICO {
        FK gestor
        FK area
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Servico` | Item do catálogo (Requisição/Incidente) com SLA, anexos, público, etc. | FK `area`, `grupo_servico`; M2M `centros_atendimento`, `publico_direcionado` |
| `GrupoServico` | Agrupador de serviços, com ícone e descrição. | M2M `categorias` |
| `CategoriaServico` | Categoria de serviço dentro de uma área. | FK `area` |
| `CentroAtendimento` | Unidade responsável pelo atendimento; pode ser local (por campus). | FK `area` |
| `Tag` | Rótulo de área para classificar chamados. | FK `area` |
| `GestorAreaServico` | Associa um gestor (User) a uma Área de Atuação; `unique(gestor, area)`. | FK `gestor` (User), `area` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `AreaAtuacao` | comum |
| `Publico` | comum |
| `User` | comum |
| `GrupoAtendimento` | centralservicos (subdomínio Estrutura de Atendimento) — referencia `centro_atendimento` |
| `BaseConhecimento` | centralservicos (subdomínio Base de Conhecimento) — restringe-se a `servicos` |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
