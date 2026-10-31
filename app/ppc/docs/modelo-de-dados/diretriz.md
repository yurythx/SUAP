# Modelo de dados — Diretriz (PPC)

> ERD das entidades que definem as regras curriculares por ano/tipo de oferta/modalidade.
> Models herdam `LogModel`. FKs externas marcadas como tal. Termos: ver
> [../GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    DIRETRIZ ||--o{ NUCLEO_DIRETRIZ : "nucleos"
    DIRETRIZ ||--o{ PERIODO_DIRETRIZ : "periodos"
    DIRETRIZ ||--o{ COMPONENTE_EXIGIDO_DIRETRIZ : "componentes exigidos"
    NUCLEO_DIRETRIZ ||--o{ EIXO_TECNOLOGICO_DIRETRIZ : "eixos"
    NUCLEO_DIRETRIZ ||--o{ MODALIDADE_PRATICA_PROFISSIONAL_DIRETRIZ : "praticas"
    DIRETRIZ }o--|| MODALIDADE : "tipo_oferta"
    DIRETRIZ }o--|| NATUREZA_PARTICIPACAO : "modalidade"
    DIRETRIZ }o--|| ANO : "ano"
    DIRETRIZ }o--|| ESTRUTURA_CURSO : "estrutura_curso"
    NUCLEO_DIRETRIZ }o--|| NUCLEO : "nucleo"
    EIXO_TECNOLOGICO_DIRETRIZ }o--|| EIXO_TECNOLOGICO : "eixo_tecnologico"
    MODALIDADE_PRATICA_PROFISSIONAL_DIRETRIZ }o--|| MODALIDADE_PRATICA_PROFISSIONAL : "modalidade"
    DIRETRIZ {
        string descricao
        int ch_min_curso
        int ch_max_curso
        bool exige_tcc
        bool emite_certificacao_parcial
    }
    NUCLEO_DIRETRIZ {
        int ch_min_pd
        int ch_max_pd
        bool exige_eixo_tecnologico
    }
    PERIODO_DIRETRIZ {
        int periodo
        int ch_min_componente
        int ch_max_componente
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Diretriz` | Regras de CH, períodos e estrutura por ano/tipo de oferta/modalidade | FK `comum.Ano`, `edu.EstruturaCurso`, `edu.Modalidade`, `edu.NaturezaParticipacao` |
| `NucleoDiretriz` | Configuração de um núcleo dentro da diretriz (CH de planos, prática, eixos) | FK `Diretriz`, `edu.Nucleo` |
| `EixoTecnologicoDiretriz` | CH por eixo tecnológico de um núcleo que exige eixo | FK `NucleoDiretriz`, `edu.EixoTecnologico` |
| `ModalidadePraticaProfissionalDiretriz` | Prática profissional exigida/optativa por núcleo | FK `NucleoDiretriz`, `edu.ModalidadePraticaProfissional` |
| `PeriodoDiretriz` | Limites de CH de componentes por período da diretriz | FK `Diretriz` |
| `ComponenteExigidoDiretriz` | Componente obrigatório (por nome) com CH mínima | FK `Diretriz` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Ano` | `comum` |
| `Modalidade`, `NaturezaParticipacao`, `EstruturaCurso`, `Nucleo`, `EixoTecnologico`, `ModalidadePraticaProfissional` | `edu` |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
