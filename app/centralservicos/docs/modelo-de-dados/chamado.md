# Modelo de dados — Chamado

> ERD do núcleo do módulo: o chamado e seus registros associados (atribuições, histórico de
> situações, comunicações, anexos, autorizações). Models herdam `ModelPlus` de `djtools.db`.
> FKs para entidades de outras áreas/subdomínios aparecem como **externas**. Termos: ver
> `../GLOSSARIO.md`.

```mermaid
erDiagram
    CHAMADO ||--o{ ATENDIMENTO_ATRIBUICAO : "atendimentoatribuicao_set"
    CHAMADO ||--o{ HISTORICO_STATUS : "historicostatus_set"
    CHAMADO ||--o{ COMUNICACAO : "comunicacao_set"
    CHAMADO ||--o{ CHAMADO_ANEXO : "chamadoanexo_set"
    CHAMADO ||--o{ AUTORIZACAO : "autorizacao_set"
    HISTORICO_STATUS |o--|| COMUNICACAO : "comunicacao (O2O)"
    HISTORICO_STATUS }o--o{ BASE_CONHECIMENTO : "bases_conhecimento (M2M, externo)"
    COMUNICACAO }o--o{ BASE_CONHECIMENTO : "bases_conhecimento (M2M, externo)"
    ATENDIMENTO_ATRIBUICAO }o--|| GRUPO_ATENDIMENTO : "grupo_atendimento (externo)"
    CHAMADO }o--|| SERVICO : "servico (externo)"
    CHAMADO }o--o{ TAG : "tags (M2M, externo)"
    CHAMADO }o--|| USER : "aberto_por/requisitante/interessado (externo)"
    CHAMADO }o--o{ USER : "outros_interessados (M2M, externo)"
    CHAMADO }o--|| UNIDADE_ORGANIZACIONAL : "campus (externo)"
    CHAMADO }o--o| INVENTARIO : "patrimonio (externo)"

    CHAMADO {
        int status "FSM"
        text descricao
        datetime aberto_em
        datetime data_limite_atendimento
        string meio_abertura
        bool sla_estourado
        bool autorizado
        int nota_avaliacao
        bool fechado_automaticamente
    }
    ATENDIMENTO_ATRIBUICAO {
        datetime atribuido_em
        datetime cancelado_em
        string tipo_justificativa
    }
    HISTORICO_STATUS {
        int status
        datetime data_hora
        float tempo_atendimento
        float tempo_resposta
        float tempo_suspensao
    }
    COMUNICACAO {
        string tipo "comentario/nota_interna"
        text texto
        bool mensagem_automatica
    }
    CHAMADO_ANEXO {
        string descricao
        file anexo
    }
    AUTORIZACAO {
        text texto
        datetime autorizado_em
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Chamado` | Ticket de serviço; `status` é `FSMIntegerField` (`django_fsm`, protegido). | FK `servico`, `aberto_por`/`requisitante`/`interessado` (User), `campus`, `patrimonio`; M2M `outros_interessados`, `tags` |
| `AtendimentoAtribuicao` | Atribuição do chamado a um grupo (e atendente); cancelamento registra escalonamento/retorno. | FK `chamado`, `grupo_atendimento`, `atribuido_para`, `atribuido_por`, `cancelado_por` |
| `HistoricoStatus` | Registro de cada mudança de situação, com tempos de resposta/atendimento/suspensão. | FK `chamado`, `usuario`; O2O `comunicacao`; M2M `bases_conhecimento` |
| `Comunicacao` | Comentário (público) ou nota interna do chamado. | FK `chamado`, `remetente`; M2M `usuarios_citados`, `bases_conhecimento` |
| `ChamadoAnexo` | Arquivo anexado ao chamado (extensões e visibilidade controladas). | FK `chamado`, `anexado_por` |
| `Autorizacao` | Solicitação/registro de autorização vinculada a um chamado. | FK `chamado`, `enviado_por`, `enviado_para`, `autorizado_por` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `User` | comum |
| `UnidadeOrganizacional` | rh |
| `Inventario` | patrimonio |
| `Servico` | centralservicos (subdomínio Catálogo de Serviços) |
| `Tag` | centralservicos (subdomínio Catálogo de Serviços) |
| `GrupoAtendimento` | centralservicos (subdomínio Estrutura de Atendimento) |
| `BaseConhecimento` | centralservicos (subdomínio Base de Conhecimento) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
