# Modelo de dados — Plano de Disciplina (PPC)

> ERD do subdomínio de planos de disciplina: o plano, suas seções, revisões/comentários,
> movimentações e revisores. Models herdam `LogModel`. Termos: ver
> [../GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    PLANO_DISCIPLINA ||--o{ SECAO_PLANO_DISCIPLINA : "secoes"
    PLANO_DISCIPLINA ||--o{ REVISAO_PLANO_DISCIPLINA : "revisoes"
    REVISAO_PLANO_DISCIPLINA ||--o{ COMENTARIO_REVISAO_PLANO_DISCIPLINA : "comentarios"
    PLANO_DISCIPLINA ||--o{ MOVIMENTACAO_PLANO_DISCIPLINA : "movimentacoes"
    PLANO_DISCIPLINA }o--|| MODELO_PLANO_DISCIPLINA : "modelo (externo)"
    PLANO_DISCIPLINA }o--o| DIRETRIZ : "diretriz (externo)"
    PLANO_DISCIPLINA }o--o| COMISSAO_PTDEM : "comissao_ptdem (externo)"
    PLANO_DISCIPLINA }o--|| NUCLEO : "nucleo (externo edu)"
    PLANO_DISCIPLINA }o--o| SERVIDOR : "avaliador (externo rh)"
    PLANO_DISCIPLINA }o--o| COMPONENTE : "componente gerado (externo edu)"
    SECAO_PLANO_DISCIPLINA }o--|| MODELO_SECAO_PLANO_DISCIPLINA : "modelo_secao (externo)"
    REVISOR_PLANO_DISCIPLINA }o--|| SERVIDOR : "servidor (externo rh)"
    REVISAO_PLANO_DISCIPLINA }o--|| VINCULO : "vinculo (externo comum)"
    PLANO_DISCIPLINA {
        string situacao
        string nome_disciplina
        int ch_disciplina
        text ementa
        bool ativo
    }
    SECAO_PLANO_DISCIPLINA {
        text texto
        bool versao_ead
    }
    REVISAO_PLANO_DISCIPLINA {
        text texto
        bool resolvido
        int numero_revisao
    }
    REVISOR_PLANO_DISCIPLINA {
        bool ativo
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `PlanoDisciplina` | Plano de disciplina (ementa/programa); ciclo elaboração→análise→aprovado | FK `ModeloPlanoDisciplina`, `Diretriz`, `ComissaoPTDEM`, `edu.Modalidade`, `edu.Nucleo`, `rh.Servidor` (avaliador), `edu.Componente` |
| `SecaoPlanoDisciplina` | Seção preenchida do plano (texto; versão EAD opcional) | FK `PlanoDisciplina`, `ModeloSecaoPlanoDisciplina` |
| `RevisaoPlanoDisciplina` | Apontamento de revisão sobre o plano | FK `PlanoDisciplina`, `comum.Vinculo` |
| `ComentarioRevisaoPlanoDisciplina` | Comentário (manual/automático) em uma revisão | FK `RevisaoPlanoDisciplina`, `comum.Vinculo` |
| `MovimentacaoPlanoDisciplina` | Registro de cada transição de situação do plano | FK `PlanoDisciplina`, `comum.Vinculo` |
| `RevisorPlanoDisciplina` | Servidor habilitado a revisar planos de disciplina (cadastro global) | FK `rh.Servidor` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `ModeloPlanoDisciplina`, `ModeloSecaoPlanoDisciplina` | `ppc` (subdomínio Modelos) |
| `Diretriz` | `ppc` (subdomínio Diretriz) |
| `ComissaoPTDEM` | `ppc` (subdomínio Configuração) |
| `Servidor` | `rh` |
| `Vinculo` | `comum` |
| `Modalidade`, `Nucleo`, `Componente` | `edu` |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
