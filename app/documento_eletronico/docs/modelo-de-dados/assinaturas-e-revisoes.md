# Modelo de dados — assinaturas e revisões

> Este subdomínio modela solicitações e evidências de assinatura/revisão. Documentos e vínculos são entidades externas referenciadas.

```mermaid
erDiagram
    SOLICITACAO_ASSINATURA {
        int id PK
        int documento_texto_id FK
        int vinculo_solicitado_id FK
        int status
        datetime data_solicitacao
        bool balizadora
    }
    SOLICITACAO_REVISAO {
        int id PK
        int documento_texto_id FK
        int vinculo_revisor_id FK
        int vinculo_avaliador_id FK
        int status
    }
    ASSINATURA {
        int id PK
        int vinculo_id FK
        string cpf
        string nome_papel
        datetime data
        string hmac UK
    }
    ASSINATURA_DOCUMENTO_TEXTO {
        int id PK
        int assinatura_id FK
        int documento_texto_id FK
    }
    ASSINATURA_DOCUMENTO_DIGITALIZADO {
        int id PK
        int assinatura_id FK
        int documento_digitalizado_id FK
    }

    DOCUMENTO_TEXTO ||--o{ SOLICITACAO_ASSINATURA : "recebe"
    DOCUMENTO_TEXTO ||--o{ SOLICITACAO_REVISAO : "recebe"
    SOLICITACAO_ASSINATURA }o--|| COMUM_VINCULO : "é solicitada a"
    SOLICITACAO_REVISAO }o--|| COMUM_VINCULO : "tem revisor"
    SOLICITACAO_ASSINATURA }o--o{ SOLICITACAO_ASSINATURA : "depende de"
    ASSINATURA ||--o{ ASSINATURA_DOCUMENTO_TEXTO : "assina"
    ASSINATURA ||--o{ ASSINATURA_DOCUMENTO_DIGITALIZADO : "assina"
    ASSINATURA_DOCUMENTO_TEXTO }o--|| DOCUMENTO_TEXTO : "referencia"
    ASSINATURA_DOCUMENTO_DIGITALIZADO }o--|| DOCUMENTO_DIGITALIZADO : "referencia"
    ASSINATURA }o--|| COMUM_VINCULO : "pertence ao vínculo"
```

## Entidades

| Entidade | Papel | Relações principais |
|---|---|---|
| `SolicitacaoAssinatura` | pedido de assinatura, com status e condicionantes | documento textual, vínculo solicitado e auto-relação de dependências |
| `SolicitacaoRevisao` | pedido e avaliação de revisão | documento textual, solicitante, revisor e avaliador |
| `Assinatura` | evidência de assinatura por vínculo/papel | vínculo e relações com documentos |
| `AssinaturaDocumentoTexto` | associação de assinatura a documento textual | assinatura ↔ texto |
| `AssinaturaDocumentoDigitalizado` | associação de assinatura a digitalizado | assinatura ↔ digitalizado |

## Entidades externas referenciadas

| Entidade | Origem | Uso |
|---|---|---|
| `DOCUMENTO_TEXTO` | subdomínio documentos e conteúdo | documento de revisão/assinatura |
| `DOCUMENTO_DIGITALIZADO` | subdomínio documentos e conteúdo | documento associado à assinatura |
| `COMUM_VINCULO` | `comum` | solicitante, revisor, avaliador e assinante |

Gerado/atualizado via subagent `documentador` em 2026-09-09.
