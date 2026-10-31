# Modelo de dados — Projeto e equipe

> ERD do `Projeto` (entidade central) e dos models de equipe/histórico ligados a ele
> (models herdam `ModelPlus` de `djtools.db`). FKs para outras sub-áreas e módulos
> aparecem como **externas**. Termos: ver Glossário (`../GLOSSARIO.md`).

```mermaid
erDiagram
    PROJETO ||--o{ PARTICIPACAO : "tem participantes"
    PROJETO ||--o{ HISTORICO_EQUIPE : "registra movimentações"
    PROJETO ||--o{ PROJETO_ANEXO : "tem anexos"
    PROJETO ||--o{ FOTO_PROJETO : "tem fotos"
    PROJETO ||--o{ PROJETO_HISTORICO_ENVIO : "registra envios/devoluções"
    PROJETO ||--o{ HISTORICO_ORIENTACAO : "registra orientações"
    PROJETO ||--o{ HISTORICO_ALTERACAO_PERIODO : "registra mudança de período"
    PROJETO ||--o{ CARACTERIZACAO_BENEFICIARIO : "caracteriza público-alvo"
    PARTICIPACAO ||--o{ HISTORICO_EQUIPE : "tem histórico"
    PARTICIPACAO }o--o| PARTICIPACAO : "orientador do aluno"
    HISTORICO_ORIENTACAO }o--|| PARTICIPACAO : "orientado"
    HISTORICO_ORIENTACAO }o--|| PARTICIPACAO : "orientador"
    PROJETO {
        string titulo
        date inicio_execucao
        date fim_execucao
        bool pre_aprovado
        bool aprovado
        decimal pontuacao
        int classificacao
        bool inativado
        datetime data_conclusao_planejamento
        datetime data_finalizacao_conclusao
    }
    PARTICIPACAO {
        bool responsavel "coordenador"
        string vinculo "Bolsista/Voluntário"
        int carga_horaria
        bool ativo
        bool bolsa_concedida
        string numero_conta
    }
    HISTORICO_EQUIPE {
        int tipo_de_evento
        date data_movimentacao
        date data_movimentacao_saida
    }
    CARACTERIZACAO_BENEFICIARIO {
        int quantidade
        int quantidade_atendida
    }
    PROJETO }o--|| EDITAL : "edital"
    PROJETO }o--|| UO : "campus"
    PROJETO }o--|| SETOR : "setor"
    PROJETO }o--|| EIXO_TEMATICO : "eixo"
    PROJETO }o--o| VINCULO : "coordenador / monitor / autor pré-seleção"
    PROJETO }o--o{ COMPONENTE : "disciplinas"
    PROJETO }o--o{ CURSO_CAMPUS : "cursos"
    PARTICIPACAO }o--o| VINCULO : "participante"
    PARTICIPACAO }o--o| BANCO : "banco"
    PROJETO_ANEXO }o--o| EDITAL_ANEXO : "tipo exigido"
    CARACTERIZACAO_BENEFICIARIO }o--|| TIPO_BENEFICIARIO : "tipo"
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Projeto` | Entidade central. Concentra a máquina de estados (`get_status`/`get_periodo`), submissão, pré-seleção (`pre_aprovado`), seleção (`aprovado`, `pontuacao`, `classificacao`), execução e conclusão. Regras de negócio nos métodos `pode_*`. | FK `edital`, `uo`, `setor`, `eixo_tematico`; FK `vinculo_coordenador`/`vinculo_monitor`/`vinculo_autor_pre_avaliacao` → `comum.Vinculo`; M2M `componentes`/`cursos`/`disciplinas` → `edu` |
| `Participacao` | Vínculo de uma pessoa (aluno, servidor, colaborador) à equipe do projeto, com função (`responsavel`=coordenador), tipo (`Bolsista`/`Voluntário`), carga horária e dados bancários. | FK `projeto`, FK `vinculo_pessoa` → `comum.Vinculo`, FK `orientador` (auto), FK `instituicao` → `rh.Banco` |
| `HistoricoEquipe` | Histórico de movimentações de um participante (inserção, inativação, troca de coordenação, concessão de bolsa). | FK `projeto`, FK `participante` → `Participacao` |
| `ProjetoAnexo` | Anexo do projeto, podendo estar vinculado a um tipo exigido pelo edital e a um membro da equipe. | FK `projeto`, FK `anexo_edital` → `EditalAnexo`, FK `vinculo_membro_equipe`, FK `participacao` |
| `FotoProjeto` | Foto da execução (gera thumbnail via PIL no `save`). | FK `projeto` |
| `ProjetoHistoricoDeEnvio` | Registro das operações de envio/devolução/reabertura/finalização do projeto. | FK `projeto`, FK `operador` → `rh.Servidor`, FK `vinculo_operador` |
| `HistoricoOrientacaoProjeto` | Relação orientador↔orientado ao longo do tempo. | FK `projeto`, FK `orientado`/`orientador` → `Participacao` |
| `HistoricoAlteracaoPeriodoProjeto` | Registro de alterações no período de execução do projeto. | FK `projeto`, FK `vinculo_registrado_por` |
| `CaracterizacaoBeneficiario` | Quantidade prevista/atendida de beneficiários por tipo. | FK `projeto`, FK `tipo_beneficiario` → `TipoBeneficiario` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Edital`, `EixoTematico`, `EditalAnexo`, `TipoBeneficiario` | projetos_ensino (subdomínio [Edital e config](edital-e-config.md)) |
| `Vinculo` | comum |
| `Setor` | comum |
| `UnidadeOrganizacional` (UO), `Servidor`, `Banco` | rh |
| `Componente`, `CursoCampus`, `Disciplina` | edu |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-19._
