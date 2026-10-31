# Modelo de dados — Base de Conhecimento

> ERD dos artigos da Base de Conhecimento (BC), seus anexos e o sistema de avaliação. Models
> herdam `ModelPlus` de `djtools.db`. FKs para entidades de outras áreas/subdomínios aparecem
> como **externas**. Termos: ver `../GLOSSARIO.md`.

```mermaid
erDiagram
    BASE_CONHECIMENTO ||--o{ BASE_CONHECIMENTO_ANEXO : "baseconhecimentoanexo_set"
    BASE_CONHECIMENTO ||--o{ AVALIA_BASE_CONHECIMENTO : "avaliabaseconhecimento_set"
    PERGUNTA_AVALIACAO_BC ||--o{ AVALIA_BASE_CONHECIMENTO : "pergunta"
    BASE_CONHECIMENTO }o--o{ GRUPO_ATENDIMENTO : "grupos_atendimento (M2M, externo)"
    BASE_CONHECIMENTO }o--o{ SERVICO : "servicos (M2M, externo)"
    BASE_CONHECIMENTO }o--|| AREA_ATUACAO : "area (externo)"
    BASE_CONHECIMENTO }o--|| USER : "atualizado_por (externo)"
    PERGUNTA_AVALIACAO_BC }o--|| AREA_ATUACAO : "area (externo)"
    AVALIA_BASE_CONHECIMENTO }o--|| USER : "avaliado_por (externo)"

    BASE_CONHECIMENTO {
        string titulo
        text resumo
        text solucao
        string visibilidade "publica/privada/sigilosa"
        bool ativo
        bool supervisao_pendente
        bool necessita_correcao
    }
    BASE_CONHECIMENTO_ANEXO {
        file anexo
    }
    PERGUNTA_AVALIACAO_BC {
        string titulo
        bool ativo
    }
    AVALIA_BASE_CONHECIMENTO {
        int nota "1-5"
        datetime data
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `BaseConhecimento` | Artigo da BC (privado/público/sigiloso); fluxo de supervisão e correção. | FK `area`, `atualizado_por`; M2M `grupos_atendimento`, `servicos` |
| `BaseConhecimentoAnexo` | Arquivo anexado a um artigo (extensões controladas). | FK `base_conhecimento` |
| `PerguntaAvaliacaoBaseConhecimento` | Critério de avaliação dos artigos, por área. | FK `area` |
| `AvaliaBaseConhecimento` | Nota (1–5) de um usuário a um artigo por pergunta; `unique(base_conhecimento, pergunta, avaliado_por)`. | FK `base_conhecimento`, `pergunta`, `avaliado_por` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `AreaAtuacao` | comum |
| `User` | comum |
| `Servico` | centralservicos (subdomínio Catálogo de Serviços) |
| `GrupoAtendimento` | centralservicos (subdomínio Estrutura de Atendimento) |

> Nota: `HistoricoStatus` e `Comunicacao` (subdomínio Chamado) referenciam `BaseConhecimento`
> via M2M (artigos usados na resolução/sugestão).

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
