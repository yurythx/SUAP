# Modelo de dados — Contrato e classificação

> ERD das entidades da sub-área **núcleo do contrato** (models herdam `ModelPlus` de
> `djtools.db`). FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [../GLOSSARIO.md](../GLOSSARIO.md). Índice: [_indice.md](_indice.md).

```mermaid
erDiagram
    TIPO_CONTRATO ||--o{ SUBTIPO_CONTRATO : "classifica"
    TIPO_CONTRATO ||--o{ CONTRATO : "tipo"
    SUBTIPO_CONTRATO ||--o{ CONTRATO : "subtipo"
    TIPO_LICITACAO ||--o{ CONTRATO : "tipo_licitacao"
    BASE_LEGAL ||--o{ CONTRATO : "base_legal (SET_NULL)"
    MOTIVO_CONCLUSAO_CONTRATO ||--o{ CONTRATO : "motivo_conclusao"
    CONTRATO ||--o{ ITEM_CONTRATO : "itens contratados"
    VINCULO ||--o{ CONTRATO : "vinculo_contratado (contratada)"
    PESSOA_JURIDICA ||--o{ CONTRATO : "contratada"
    UNIDADE_ORGANIZACIONAL ||--o{ CONTRATO : "campus_gerenciador"
    UNIDADE_ORGANIZACIONAL }o--o{ CONTRATO : "campi atendidos (M2M)"
    SETOR }o--o{ CONTRATO : "setores_gerenciadores (M2M)"
    PROCESSO ||--o{ CONTRATO : "processo"
    EMPENHO ||--o{ CONTRATO : "empenho (legado)"
    ARQUIVO ||--|| CONTRATO : "arquivo digitalizado (O2O)"
    DOCUMENTO_TEXTO ||--o{ CONTRATO : "documento_digital_contrato"

    CONTRATO {
        int id PK
        string numero "formato 99999/9999"
        decimal valor
        decimal valor_executado "derivado"
        decimal valor_total "derivado: valor + aditivos + apostilamentos"
        decimal valor_previsto_parcela "derivado"
        date data_inicio
        date data_fim
        date data_vencimento "derivado: maior data_fim de aditivo de prazo"
        text objeto
        string continuidade "CONTINUO|ESCOPO|INDETERMINADO"
        string natureza "DESPESA|RECEITA|RECEITA_DESPESA|SEM_IMPACTO_FINANCEIRO"
        bool mao_obra_exclusiva
        smallint grau_risco "1|2|3"
        bool permite_medicao_sem_empenho
        bool exige_garantia_contratual
        smallint qtd_parcelas
        string pregao "numero da licitacao"
        date estimativa_licitacao
        bool concluido
        date data_conclusao
        bool cancelado
        text motivo_cancelamento
        datetime dh_cancelamento
        int usuario_cancelamento FK
        int id_comprasgov
        file arquivo_contrato
    }
    BASE_LEGAL {
        int id PK
        string titulo
        smallint vigencia "meses"
        smallint prorrogacao "meses"
        string conformidade_base_legal "texto usado nos documentos"
    }
    SUBTIPO_CONTRATO {
        int id PK
        string descricao
        int tipo FK
    }
    ITEM_CONTRATO {
        int id PK
        int contrato FK
        int numero_item
        string descricao
        string grupo
        int quantidade
        string tipo "material|servico"
        decimal valor_unitario
        decimal valor_total
        int id_comprasgov "unique com contrato"
        int atualizado_por FK
        datetime atualizado_em
    }
    TIPO_CONTRATO {
        int id PK
        string descricao
    }
    TIPO_LICITACAO {
        int id PK
        string descricao
    }
    MOTIVO_CONCLUSAO_CONTRATO {
        int id PK
        string descricao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Contrato` | Raiz do agregado. Guarda identificação, vigência, valores (com três campos derivados recalculados no `save()`), classificação, dados da licitação, conclusão e cancelamento | FK `tipo`, `subtipo`, `base_legal`, `motivo_conclusao`, `tipo_licitacao`, `processo`, `empenho`, `campus_gerenciador`, `vinculo_contratado`, `contratada`, `usuario_cancelamento`, `documento_digital_contrato`; O2O `arquivo`; M2M `campi`, `setores_gerenciadores`, `documentos_empenho` |
| `TipoContrato` | Tipo do contrato (tabela acessória) | Referenciado por `SubtipoContrato` e `Contrato` |
| `SubtipoContrato` | Subtipo, sempre subordinado a um tipo. O subtipo configurado em `tipo_contrato_energia_eletrica` aciona o fluxo de medição elétrica | FK `tipo` |
| `TipoLicitacao` | Modalidade da licitação que originou o contrato | Referenciado por `Contrato` |
| `BaseLegal` | Fundamento legal com vigência e prorrogação máximas (meses) e o texto de conformidade usado nos documentos | Referenciado por `Contrato` (`on_delete=SET_NULL`) |
| `MotivoConclusaoContrato` | Motivo do encerramento/rescisão | Referenciado por `Contrato` |
| `ItemContrato` | Item (material ou serviço) contratado; importável do ComprasGov | FK `contrato`, `atualizado_por` (`comum.Vinculo`); `UniqueConstraint(contrato, id_comprasgov)` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Vinculo` | `comum` (contratada e `atualizado_por`) |
| `User` | `comum` (usuário do cancelamento) |
| `Arquivo` | `comum` (arquivo digitalizado do contrato) |
| `PessoaJuridica` | `rh` (campo `contratada`) |
| `UnidadeOrganizacional` | `rh` (campus gerenciador e campi atendidos) |
| `Setor` | `rh` (setores gerenciadores) |
| `Processo` | `protocolo` |
| `Empenho` | `almoxarifado` (vínculo legado, mantido além de `DocumentoEmpenhoContrato`) |
| `DocumentoEmpenho` | `tesouro_gerencial` (M2M `documentos_empenho`, via `DocumentoEmpenhoContrato`) |
| `DocumentoTexto` | `documento_eletronico` (documento digital do contrato) |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-11._
