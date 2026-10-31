# Modelo de dados — Instrumento

> ERD das entidades do catálogo de perguntas: a árvore eixo → dimensão → macroprocesso → indicador
> e seus acessórios (variáveis, opções, iteradores, escalas Likert, tipos de avaliação).
> Models herdam `ModelPlus` de `djtools.db`. FKs para entidades de outras áreas aparecem como
> **externas**. Termos: ver [GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    EIXO ||--o{ DIMENSAO : "agrupa"
    DIMENSAO ||--o{ MACROPROCESSO : "agrupa"
    MACROPROCESSO ||--o{ INDICADOR : "agrupa"
    INDICADOR ||--o{ VARIAVEL : "compoe (tipo Conjunto de Variaveis)"
    INDICADOR ||--o{ OPCAO_RESPOSTA : "oferece (escolha unica/multipla)"
    INDICADOR ||--o{ ITERADOR : "repete por objeto"
    ESCALA_LIKERT ||--o{ NIVEL_ESCALA_LIKERT : "tem niveis"
    ESCALA_LIKERT |o--o{ INDICADOR : "define a regua de"
    TIPO_AVALIACAO }o--o{ INDICADOR : "subsidio_para (M2M)"
    SEGMENTO }o--o{ INDICADOR : "segmentos (M2M)"
    SEGMENTO ||--o{ ITERADOR : "restringe iteracao"
    ANO }o--o{ INDICADOR : "anos_referencia (M2M)"
    AREA_VINCULACAO }o--o{ INDICADOR : "areas_vinculacao (M2M)"
    MODALIDADE }o--o{ INDICADOR : "modalidades (M2M)"
    UNIDADE_ORGANIZACIONAL }o--o{ INDICADOR : "uos (M2M)"

    EIXO {
        int id PK
        string descricao
        text texto_ajuda
        int ordem "auto: max+1 se vazio"
    }
    DIMENSAO {
        int id PK
        int eixo_id FK "PROTECT"
        string descricao
        text texto_ajuda
        int ordem "auto por eixo"
    }
    MACROPROCESSO {
        int id PK
        int dimensao_id FK "PROTECT"
        string descricao
        text texto_ajuda
        int ordem "auto por dimensao"
    }
    INDICADOR {
        int id PK
        int macroprocesso_id FK "PROTECT"
        int escala_id FK "PROTECT, nulo"
        string nome "denominacao; chave dos autocalculados"
        string aspecto "criterio de analise = texto lido"
        int tipo_resposta "1..7, 99=Escala Likert"
        bool automatico
        bool obrigatorio
        bool em_uso
        int periodo_curso "periodo minimo do estudante"
        bool envolve_reitoria
        bool envolve_campus_ead
        bool envolve_campus_produtivos
        bool envolve_campus_nao_produtivos
        int valor_minimo
        int valor_maximo
        string formula "obrigatoria p/ Conjunto de Variaveis"
        bool gestor_responde_como_docente
        int ordem
    }
    VARIAVEL {
        int id PK
        int indicador_id FK "PROTECT"
        string sigla
        string nome
        int tipo "inteiro ou decimal"
        int valor_minimo
        int valor_maximo
    }
    OPCAO_RESPOSTA {
        int id PK
        int indicador_id FK "CASCADE"
        string descricao
    }
    ITERADOR {
        int id PK
        int indicador_id FK "CASCADE"
        int segmento_id FK "CASCADE"
        string objeto "edu.CursoCampus | edu.Modalidade | edu.Professor | edu.Turma"
    }
    ESCALA_LIKERT {
        int id PK
        string nome
        bool ativo
    }
    NIVEL_ESCALA_LIKERT {
        int id PK
        int escala_id FK "CASCADE"
        int nivel
        string descricao
        string emoji
        string tipo_criterio "A|B|C|D|E|- (padroniza graficos)"
    }
    TIPO_AVALIACAO {
        int id PK
        string descricao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `Eixo` | Primeiro nível do instrumento; vira uma aba no questionário. `ordem` é atribuída automaticamente no `save()` quando vazia, e reordenada em bloco por `EixoForm.save` | ← `Dimensao` |
| `Dimensao` | Segundo nível | FK `Eixo` (PROTECT) |
| `Macroprocesso` | Terceiro nível; é o título sob o qual os indicadores aparecem | FK `Dimensao` (PROTECT) |
| `Indicador` | A pergunta. Concentra os filtros de aplicabilidade (segmentos, áreas, modalidades, campi, tipo de campus, período mínimo, anos de referência) e o tipo de resposta. `get_form_field()` constrói o campo Django correspondente, incluindo o comportamento especial dos autocalculados | FK `Macroprocesso`, FK `EscalaLikert`; M2M `TipoAvaliacao`, `Ano`, `Segmento`, `AreaVinculacao`, `Modalidade`, `UnidadeOrganizacional` |
| `Variavel` | Sub-campo numérico de um indicador do tipo "Conjunto de Variáveis"; a combinação é dada pela `formula` do indicador. ⚠️ REVISAR: `Variavel.get_form_field` referencia `self.aspecto`, campo que só existe em `Indicador` — na prática o tipo não renderiza (ver [HLA §7](../HLA.md#7-riscos-e-débito-técnico)) | FK `Indicador` (PROTECT) |
| `OpcaoResposta` | Alternativa dos tipos escolha única/múltipla | FK `Indicador` (CASCADE) |
| `Iterador` | Declara que, para determinado segmento, o indicador deve ser repetido para cada objeto de `edu` (curso, modalidade, professor ou turma) do respondente. `objeto` guarda o label do model como string | FK `Indicador` (CASCADE), FK `Segmento` (CASCADE) |
| `EscalaLikert` | Régua de resposta reutilizável. `em_uso()` indica se algum indicador a referencia; PK 5 é tratada como escala padrão (`ESCALA_PADRAO`) | ← `NivelEscalaLikert`; ← `Indicador` |
| `NivelEscalaLikert` | Nível da régua. `tipo_criterio` classifica o nível para padronizar gráficos e excluir "Desconheço"/"Não se aplica" das medidas-resumo | FK `EscalaLikert` (CASCADE); ← `Resposta.nivel_escala` |
| `TipoAvaliacao` | Finalidade a que o indicador serve e de que a avaliação é feita. PK 10 = `AVALIACAO_PLANEJAMENTO_PDI`, usada como valor inicial no formulário | M2M com `Indicador` (`subsidio_para`) e com `Avaliacao` (`tipos`) |

**Ordenação:** `Indicador.Meta.ordering` percorre a árvore inteira
(`macroprocesso__dimensao__eixo__ordem`, `…dimensao__ordem`, `macroprocesso__ordem`, `ordem`) — é o
que garante que o questionário e os relatórios saiam na sequência cadastrada.

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Segmento` | Este módulo, subdomínio [Aplicação e coleta](aplicacao-e-coleta.md) |
| `Ano` | `comum` |
| `AreaVinculacao`, `UnidadeOrganizacional` | `rh` |
| `Modalidade`, `CursoCampus`, `Turma`, `Professor` | `edu` (as três últimas apenas como **string** em `Iterador.objeto` — não há FK) |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
