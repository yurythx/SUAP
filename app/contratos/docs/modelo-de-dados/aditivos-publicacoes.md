# Modelo de dados — Aditivos e publicações

> ERD das entidades da sub-área **alterações contratuais e publicidade** (models herdam
> `ModelPlus` de `djtools.db`). FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [../GLOSSARIO.md](../GLOSSARIO.md). Índice: [_indice.md](_indice.md).

```mermaid
erDiagram
    CONTRATO ||--o{ ADITIVO : "aditivos"
    CONTRATO ||--o{ APOSTILAMENTO : "apostilamentos"
    CONTRATO ||--o{ PUBLICACAO_CONTRATO : "publicacoes"
    ADITIVO ||--o{ PUBLICACAO_ADITIVO : "publicacoes"
    TIPO_PUBLICACAO ||--o{ PUBLICACAO_CONTRATO : "tipo"
    TIPO_PUBLICACAO ||--o{ PUBLICACAO_ADITIVO : "tipo"
    ARQUIVO ||--|| ADITIVO : "anexo (O2O)"
    ARQUIVO ||--|| PUBLICACAO_CONTRATO : "anexo (O2O)"
    ARQUIVO ||--|| PUBLICACAO_ADITIVO : "anexo (O2O)"
    PROCESSO ||--o{ ADITIVO : "processo"
    EMPENHO ||--o{ ADITIVO : "empenho"

    ADITIVO {
        int id PK
        int contrato FK
        smallint ordem "unique com contrato"
        string numero "formato 99999/9999"
        decimal valor
        date data_inicio
        date data_fim
        bool de_prazo
        bool de_valor
        bool de_fiscal
        bool de_outro
        string tipo_termo_aditivo "MAJ|SUP"
        smallint numero_parcelas
        text especificacao
        string numero_processo
        string numero_empenho
    }
    APOSTILAMENTO {
        int id PK
        int contrato FK
        string numero "formato 99999/9999"
        string tipo "REPACTUACAO|REAJUSTE|DOTACAO|OUTROS"
        decimal valor
        date data_inicio
        date data_fim
        text especificacao
        file arquivo
        string numero_processo
        string numero_empenho
    }
    PUBLICACAO_CONTRATO {
        int id PK
        int contrato FK
        int tipo FK
        string numero
        date data
        string descricao
    }
    PUBLICACAO_ADITIVO {
        int id PK
        int aditivo FK
        int tipo FK
        string numero
        date data
        string descricao
    }
    TIPO_PUBLICACAO {
        int id PK
        string descricao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Aditivo` | Termo aditivo do contrato; as flags `de_prazo`/`de_valor`/`de_fiscal`/`de_outro` são combináveis e definem o efeito. Aditivo de prazo empurra `Contrato.data_vencimento`; de valor soma (majoração) ou subtrai (supressão) no `valor_total`. A `ordem` é atribuída automaticamente em `save()` via `Contrato.get_proxima_ordem()` | FK `contrato` (`related_name='aditivos'`), `processo`, `empenho`; O2O `arquivo`; `unique_together (contrato, ordem)` |
| `Apostilamento` | Alteração sem termo aditivo (reajuste, repactuação, dotação orçamentária ou outros); soma ao `valor_total` do contrato. Apostilamento do tipo repactuação em contrato com mão de obra exclusiva dispara notificação aos fiscais | FK `contrato` (`related_name='apostilamentos'`); arquivo em `FileFieldPlus` (caminho `contratos/contrato/<id>/apostilamento/`) |
| `PublicacaoContrato` | Publicação do contrato na imprensa oficial, com anexo | FK `contrato` (`related_name='publicacoes'`), `tipo`; O2O `arquivo` |
| `PublicacaoAditivo` | Publicação de um termo aditivo. Ao ser criada pela view, uma `PublicacaoContrato` equivalente é criada por espelhamento (`get_or_create`) | FK `aditivo` (`related_name='publicacoes'`), `tipo`; O2O `arquivo` |
| `TipoPublicacao` | Tabela acessória com os tipos de publicação | Referenciada pelas duas publicações |

## Observações de modelagem

- `Aditivo.save()`, `delete()` e `Apostilamento.save()`, `delete()` chamam `contrato.save()` para
  propagar a recomposição de `valor_total` e `data_vencimento`.
- `Aditivo.delete()` remove antes suas `PublicacaoAditivo` e, depois, o `Arquivo` associado —
  mesma estratégia usada por `Contrato.delete()`.
- Tanto `Aditivo` quanto `Apostilamento` mantêm os campos textuais legados `numero_processo` e
  `numero_empenho` (strings livres) além das FKs estruturadas. ⚠️ REVISAR: redundância com
  `processo`/`empenho`; nos formulários esses campos textuais ficam excluídos.

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Contrato` | `contratos` — subdomínio [contrato-nucleo.md](contrato-nucleo.md) |
| `Arquivo` | `comum` |
| `Processo` | `protocolo` |
| `Empenho` | `almoxarifado` |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-11._
