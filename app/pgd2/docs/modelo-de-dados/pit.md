# Modelo de dados — PIT (Plano Individual de Trabalho)

> ERD das entidades de PIT (models herdam `ModelPlus` de `djtools.db`).
> FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [Glossário](../GLOSSARIO.md).

```mermaid
erDiagram
    PlanoIndividualTrabalho ||--o{ PlanoIndividualTrabalhoEntregas : "entregas"
    PlanoIndividualTrabalho ||--o{ PlanoIndividualTrabalhoPresencial : "presenciais"
    PlanoIndividualTrabalho ||--o{ PlanoIndividualTrabalhoAtendimento : "atendimentos"
    PlanoIndividualTrabalho ||--o{ PitSetores : "setores"
    PlanoIndividualTrabalho ||--o{ RegistroAcaoPlanoIndividualTrabalho : "registros"
    PlanoIndividualTrabalho ||--|| RelatorioIndividualTrabalho : "rit"
    PlanoIndividualTrabalho ||--o{ PlanoIndividualTrabalhoCopia : "copias"
    PlanoIndividualTrabalho ||--o{ PitSolicitacaoAnalise : "solicitacoes_analise"
    PitSolicitacaoAnalise ||--o{ PitSolicitacaoAnaliseSetor : "setores_analise"
    PlanoIndividualTrabalho {
        int id PK
        int solicitacao_adesao FK
        int setor FK "rh.Setor"
        int situacao "enum"
        date data_inicio
        date data_fim
    }
    PlanoIndividualTrabalhoEntregas {
        int id PK
        int pit FK
        int entrega_pes FK "PES"
        string titulo
        string descricao
        int situacao "enum"
    }
    PlanoIndividualTrabalhoPresencial {
        int id PK
        int pit FK
        string dia_semana
        string turno
    }
    PlanoIndividualTrabalhoAtendimento {
        int id PK
        int pit FK
        string dia_semana
        string turno
    }
    PitSetores {
        int id PK
        int pit FK
        int setor FK "rh.Setor"
    }
    PlanoIndividualTrabalhoCopia {
        int id PK
        int pit_origem FK "pit"
        int pit_destino FK "pit"
    }
    PitSolicitacaoAnalise {
        int id PK
        int pit FK
        int solicitante FK "rh.Servidor"
        datetime data_solicitacao
    }
    PitSolicitacaoAnaliseSetor {
        int id PK
        int solicitacao_analise FK
        int setor FK "rh.Setor"
    }
    RegistroAcaoPlanoIndividualTrabalho {
        int id PK
        int pit FK
        string acao
        datetime data_hora
    }
    ConfiguracaoOrientacaoPit {
        int id PK
        string orientacao
        boolean ativo
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `PlanoIndividualTrabalho` | PIT — plano do servidor, principal entidade do ciclo | FK `solicitacao_adesao`; 1:N com entregas, presencial, atendimento |
| `PlanoIndividualTrabalhoEntregas` | Entrega vinculada ao PIT, opcionalmente ligada a entrega do PES | FK `pit`; FK opcional `entrega_pes` |
| `PlanoIndividualTrabalhoPresencial` | Registro de dia/horário de trabalho presencial | FK `pit` |
| `PlanoIndividualTrabalhoAtendimento` | Registro de dia/horário de teletrabalho/atendimento | FK `pit` |
| `PitSetores` | Setores adicionais onde o servidor atua no PIT | FK `pit`, FK `setor` (rh) |
| `PlanoIndividualTrabalhoCopia` | Relação de cópia entre PITs (reaproveitamento) | FK `pit_origem`, FK `pit_destino` |
| `PitSolicitacaoAnalise` | Solicitação de análise do PIT por setor | FK `pit`, FK `solicitante` |
| `PitSolicitacaoAnaliseSetor` | Setor alvo da solicitação de análise | FK `solicitacao_analise` |
| `RegistroAcaoPlanoIndividualTrabalho` | Log de ações no PIT | Herda `RegistroAcaoPGD` |
| `ConfiguracaoOrientacaoPit` | Orientações/configuração para elaboração do PIT | Singleton |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Servidor` | `rh` |
| `Setor` | `rh` |
| `SolicitacaoAdesaoServidor` | Adesão (mesmo módulo) |
| `PlanoEntregasSetorialEntregas` | PES (mesmo módulo) |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
