# Modelo de dados — catálogos e classificação

> Este subdomínio reúne os cadastros que parametrizam documentos. Relações com pessoas, cargos e setores são externas ao subdomínio.

```mermaid
erDiagram
    TIPO_DOCUMENTO {
        int id PK
        string nome
        string sigla
        bool vincular_pessoa
        bool ativo
        bool permite_busca_corpo
        bool permite_consulta_publica
    }
    TIPO_DOCUMENTO_TEXTO {
        int tipo_documento_ptr_id PK_FK
        text cabecalho
        text rodape
        bool permite_anexos
        int tipo_sequencia
    }
    TIPO_DOCUMENTO_TEXTO_HISTORICO_CONTEUDO {
        int id PK
        text cabecalho
        text rodape
    }
    RESTRICAO_ASSINATURA {
        int id PK
        int tipo_documento_texto_id FK
        string papel
    }
    TIPO_VINCULO_DOCUMENTO {
        int id PK
        string descricao
        string descricao_ativa
        string descricao_passiva
    }
    VINCULO_DOCUMENTO_TEXTO {
        int id PK
        int documento_texto_id FK
        int tipo_vinculo_id FK
        int documento_texto_relacionado_id FK
    }
    HIPOTESE_LEGAL {
        int id PK
        string descricao
        int nivel_acesso
    }
    MODELO_DOCUMENTO {
        int id PK
        string nome
        int tipo_documento_texto_id FK
        text corpo_padrao
        int nivel_acesso_padrao
        bool ativo
    }
    CLASSIFICACAO {
        int id PK
        int pai_id FK
        string codigo
        text descricao
        string fase_corrente
        string fase_intermediaria
        string destinacao_final
        bool ativo
    }

    TIPO_DOCUMENTO ||--|| TIPO_DOCUMENTO_TEXTO : "especializa"
    TIPO_DOCUMENTO_TEXTO ||--o{ TIPO_DOCUMENTO_TEXTO_HISTORICO_CONTEUDO : "mantém histórico"
    TIPO_DOCUMENTO_TEXTO ||--o{ RESTRICAO_ASSINATURA : "restringe papéis"
    TIPO_DOCUMENTO_TEXTO ||--o{ MODELO_DOCUMENTO : "possui modelos"
    TIPO_VINCULO_DOCUMENTO ||--o{ VINCULO_DOCUMENTO_TEXTO : "classifica vínculo"
    MODELO_DOCUMENTO }o--o{ CLASSIFICACAO : "permite classificação"
    CLASSIFICACAO ||--o{ CLASSIFICACAO : "tem filhos"
    VINCULO_DOCUMENTO_TEXTO }o--|| DOCUMENTO_TEXTO : "origem"
    VINCULO_DOCUMENTO_TEXTO }o--|| DOCUMENTO_TEXTO : "relacionado"
    DOCUMENTO_TEXTO }o--|| HIPOTESE_LEGAL : "pode usar"
```

## Entidades

| Entidade | Papel | Relações principais |
|---|---|---|
| `TipoDocumento` | catálogo geral de tipos de documento | base de `TipoDocumentoTexto` e referenciado por digitalizados |
| `TipoDocumentoTexto` | parametrização de documentos textuais | cabeçalho/rodapé, sequência, anexos, restrições, modelos e histórico |
| `TipoDocumentoTextoHistoricoConteudo` | preserva versões de cabeçalho/rodapé | referenciado pelo documento textual |
| `RestricaoAssinatura` | restringe assinatura por papel/cargo/função | tipo textual ↔ papel externo |
| `TipoVinculoDocumento` | catálogo do vínculo entre documentos | usado por `VinculoDocumentoTexto` |
| `VinculoDocumentoTexto` | relação tipada entre dois documentos textuais | texto origem ↔ texto relacionado |
| `HipoteseLegal` | base legal para nível restrito/sigiloso | referenciada pelo documento |
| `ModeloDocumento` | conteúdo padrão e políticas de acesso do tipo textual | tipo textual e classificações |
| `Classificacao` | árvore MPTT e dados de retenção/destinação | auto-relação pai/filhos e modelos |

## Entidades externas referenciadas

| Entidade | Origem | Uso |
|---|---|---|
| `DOCUMENTO_TEXTO` | subdomínio documentos e conteúdo | origem/destino do vínculo tipado e uso de hipótese legal |
| cargo/função/papel | `rh` / `comum` | alvo lógico de `RestricaoAssinatura`; ⚠️ REVISAR: a resolução concreta varia por generic foreign key |

Gerado/atualizado via subagent `documentador` em 2026-09-09.
