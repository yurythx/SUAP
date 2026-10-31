# Modelo de dados — documentos e conteúdo

> Este subdomínio reúne os documentos mantidos pelo módulo, seus interessados, tipos de conferência e relações de anexação. Pessoas, vínculos e setores são entidades externas.

```mermaid
erDiagram
    DOCUMENTO_TEXTO {
        uuid uuid UK
        string identificador
        int status
        int modelo_id FK
        text corpo
        datetime data_ultima_modificacao
    }
    DOCUMENTO_DIGITALIZADO {
        uuid uuid UK
        int tipo_id FK
        file arquivo
        bool interno
        string orgao_externo
        int tipo_conferencia_id FK
        int dono_documento_id FK
        bool anexo_simples
    }
    TIPO_CONFERENCIA {
        int id PK
        string descricao
    }
    DOCUMENTO_TEXTO_INTERESSADO {
        int documento_texto_id FK
        int vinculo_id FK
    }
    DOCUMENTO_DIGITALIZADO_INTERESSADO {
        int documento_digitalizado_id FK
        int vinculo_id FK
    }
    DOCUMENTO_TEXTO_ANEXO_DOCUMENTO_TEXTO {
        int documento_texto_id FK
        int documento_texto_anexo_id FK
    }
    DOCUMENTO_TEXTO_ANEXO_DOCUMENTO_DIGITALIZADO {
        int documento_texto_id FK
        int documento_digitalizado_id FK
    }

    DOCUMENTO_TEXTO ||--o{ DOCUMENTO_TEXTO_INTERESSADO : "possui"
    DOCUMENTO_DIGITALIZADO ||--o{ DOCUMENTO_DIGITALIZADO_INTERESSADO : "possui"
    DOCUMENTO_TEXTO ||--o{ DOCUMENTO_TEXTO_ANEXO_DOCUMENTO_TEXTO : "anexa textos"
    DOCUMENTO_TEXTO ||--o{ DOCUMENTO_TEXTO_ANEXO_DOCUMENTO_DIGITALIZADO : "anexa digitalizados"
    DOCUMENTO_DIGITALIZADO }o--|| TIPO_CONFERENCIA : "é conferido por"
    DOCUMENTO_TEXTO_INTERESSADO }o--|| COMUM_VINCULO : "referencia"
    DOCUMENTO_DIGITALIZADO_INTERESSADO }o--|| COMUM_VINCULO : "referencia"
    DOCUMENTO_DIGITALIZADO }o--|| COMUM_VINCULO : "tem dono"
    DOCUMENTO_TEXTO }o--|| MODELO_DOCUMENTO : "usa modelo"
```

## Entidades

| Entidade | Papel | Relações principais |
|---|---|---|
| `DocumentoTexto` | corpo, estado, identificador, cabeçalho/rodapé, favoritos e interessados | modelo, histórico de conteúdo, assinaturas, revisão, compartilhamento e anexos |
| `DocumentoDigitalizado` | arquivo digitalizado, tipo, conferência e proprietário | tipo, conferência, vínculo dono, interessados e anexação |
| `TipoConferencia` | catálogo do tipo de conferência do arquivo digitalizado | referenciado por `DocumentoDigitalizado` |
| `DocumentoTextoInteressado` | tabela intermediária de interessados do texto | texto ↔ `comum.Vinculo` |
| `DocumentoDigitalizadoInteressado` | tabela intermediária de interessados do digitalizado | digitalizado ↔ `comum.Vinculo` |
| `DocumentoTextoAnexoDocumentoTexto` | relação de anexação entre dois textos | texto pai ↔ texto filho |
| `DocumentoTextoAnexoDocumentoDigitalizado` | relação de anexação entre texto e digitalizado | texto pai ↔ digitalizado filho |

## Entidades externas referenciadas

| Entidade | Origem | Uso |
|---|---|---|
| `MODELO_DOCUMENTO` | `documento_eletronico` / catálogo | modelo usado pelo texto |
| `COMUM_VINCULO` | `comum` | interessado e dono do digitalizado |

Gerado/atualizado via subagent `documentador` em 2026-09-09.
