# Modelo de dados — Matriz (PPC)

> ERD do subdomínio de matriz curricular do PPC: o planejamento da matriz, a configuração
> de optativas, o vínculo dos planos e as modalidades de prática profissional. A geração
> efetiva escreve em `edu.Matriz` (entidade externa). Models herdam `LogModel`. Termos:
> ver [../GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    MATRIZ_PPC ||--o{ CONFIGURACAO_OPTATIVAS_MATRIZ_PPC : "config optativas"
    MATRIZ_PPC ||--o{ PLANO_DISCIPLINA_PPC : "planos vinculados"
    MATRIZ_PPC ||--o{ MODALIDADE_PRATICA_PROFISSIONAL_PPC : "praticas"
    MATRIZ_PPC }o--|| PROJETO_PEDAGOGICO_CURSO : "ppc (externo)"
    MATRIZ_PPC }o--o| MATRIZ : "matriz (externo edu)"
    MATRIZ_PPC }o--o| TURNO : "turno (externo edu)"
    MATRIZ_PPC }o--o{ CURSO_CAMPUS : "cursos M2M (externo edu)"
    PLANO_DISCIPLINA_PPC }o--|| PLANO_DISCIPLINA : "plano_disciplina (externo)"
    MODALIDADE_PRATICA_PROFISSIONAL_PPC }o--|| NUCLEO : "nucleo (externo edu)"
    CONFIGURACAO_OPTATIVAS_MATRIZ_PPC }o--o| NUCLEO_DIRETRIZ : "nucleo_diretriz (externo)"
    MATRIZ_PPC {
        string nome
        int quantidade_periodos
        string situacao_matriz
        string situacao_modalidadepraticaprofissional
    }
    PLANO_DISCIPLINA_PPC {
        int periodo_oferta
        bool optativo
        int tipo
        int ch_teorica
        int ch_extensao
    }
    CONFIGURACAO_OPTATIVAS_MATRIZ_PPC {
        int periodo
        int ch_exigida
    }
    MODALIDADE_PRATICA_PROFISSIONAL_PPC {
        bool optativa
        int periodo_inicial
        int ch_requerida
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `MatrizPPC` | Planejamento da matriz curricular do PPC; gera a `edu.Matriz`; máquinas de estado de matriz e de prática | FK `ProjetoPedagogicoCurso`, `edu.Matriz`, `edu.Turno`; M2M `edu.CursoCampus` |
| `ConfiguracaoOptativasMatrizPPC` | CH exigida de optativas por período da matriz | FK `MatrizPPC`, `NucleoDiretriz` |
| `PlanoDisciplinaPPC` | Vínculo de um plano de disciplina à matriz (período, tipo, CH teórica/extensão/EAD) | FK `PlanoDisciplina`, `MatrizPPC` |
| `ModalidadePraticaProfissionalPPC` | Prática profissional definida na matriz do PPC, por núcleo | FK `MatrizPPC`, `edu.ModalidadePraticaProfissional`, `edu.Nucleo` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `ProjetoPedagogicoCurso` | `ppc` (subdomínio Projeto) |
| `PlanoDisciplina` | `ppc` (subdomínio Plano de Disciplina) |
| `NucleoDiretriz` | `ppc` (subdomínio Diretriz) |
| `Matriz`, `Turno`, `CursoCampus`, `Nucleo`, `ModalidadePraticaProfissional` | `edu` |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
