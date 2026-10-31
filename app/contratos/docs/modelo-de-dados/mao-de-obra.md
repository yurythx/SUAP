# Modelo de dados — Mão de obra terceirizada

> ERD das entidades da sub-área **mão de obra terceirizada** (models herdam `ModelPlus` de
> `djtools.db`). FKs para entidades de outras áreas aparecem como **externas**.
> Termos: ver [../GLOSSARIO.md](../GLOSSARIO.md). Índice: [_indice.md](_indice.md).

```mermaid
erDiagram
    CONTRATO ||--o{ MAO_DE_OBRA : "maosdeobra"
    PRESTADOR_SERVICO ||--o{ MAO_DE_OBRA : "prestador_servico (PROTECT)"
    UNIDADE_ORGANIZACIONAL ||--o{ MAO_DE_OBRA : "campus"
    MAO_DE_OBRA ||--o{ ANEXO_MAO_DE_OBRA : "anexos"
    MAO_DE_OBRA ||--o{ OCORRENCIA_MAO_DE_OBRA : "ocorrencias (PROTECT)"
    MAO_DE_OBRA ||--o{ VERBA_SALARIAL_MAO_DE_OBRA : "verbas_salariais (PROTECT)"
    TIPO_OCORRENCIA ||--o{ OCORRENCIA_MAO_DE_OBRA : "tipo (PROTECT)"
    TIPO_VERBA_SALARIAL ||--o{ VERBA_SALARIAL_MAO_DE_OBRA : "tipo (PROTECT)"

    MAO_DE_OBRA {
        int id PK
        int contrato FK
        int prestador_servico FK
        int campus FK
        date data_nascimento
        string categoria "CBO"
        string funcao
        string escolaridade
        string jornada_trabalho
        time hora_inicio_jornada
        time hora_fim_jornada
        time hora_inicio_intervalo
        time hora_fim_intervalo
        decimal salario_bruto
        decimal custo_mensal
        string numero_cct
        date inicio_vigencia
        date desligamento "nulo enquanto ativo"
        datetime data_criacao
        datetime data_atualizacao
    }
    ANEXO_MAO_DE_OBRA {
        int id PK
        int maodeobra FK
        string descricao
        file arquivo
        datetime data
    }
    OCORRENCIA_MAO_DE_OBRA {
        int id PK
        int maodeobra FK
        int tipo FK
        string descricao
        date data_inicio
        date data_fim
        file arquivo
    }
    TIPO_OCORRENCIA {
        int id PK
        string nome
        bool obrigatorio_informar_data_fim
        bool ativo
    }
    VERBA_SALARIAL_MAO_DE_OBRA {
        int id PK
        int maodeobra FK
        int tipo FK
        decimal valor
        date data_inicio
        date data_fim
    }
    TIPO_VERBA_SALARIAL {
        int id PK
        string nome
        bool obrigatorio_informar_data_fim
        bool ativo
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `MaoDeObra` | Trabalhador terceirizado alocado ao contrato: função, CBO, escolaridade, jornada (com horários de entrada/saída e intervalo), remuneração e campus de atuação. Ativo enquanto `desligamento` for nulo | FK `contrato` (`related_name='maosdeobra'`), `prestador_servico` (`comum.PrestadorServico`, `PROTECT`), `campus` |
| `AnexoMaoDeObra` | Documento do trabalhador anexado ao registro (contracheques, documentos pessoais etc.) | FK `maodeobra` (`related_name='anexos'`) |
| `OcorrenciaMaoDeObra` | Evento relativo ao trabalhador (afastamento, substituição etc.), por tipo e período de vigência, com anexo opcional | FK `maodeobra` (`related_name='ocorrencias'`, `PROTECT`), `tipo` (`PROTECT`) |
| `TipoOcorrencia` | Catálogo dos tipos de ocorrência de mão de obra; `obrigatorio_informar_data_fim` torna a data final obrigatória no formulário | Referenciado por `OcorrenciaMaoDeObra` |
| `VerbaSalarialMaoDeObra` | Componente da remuneração do trabalhador, por tipo, valor e vigência | FK `maodeobra` (`related_name='verbas_salariais'`, `PROTECT`), `tipo` (`PROTECT`) |
| `TipoVerbaSalarial` | Catálogo dos tipos de verba salarial; também controla a obrigatoriedade da data final | Referenciado por `VerbaSalarialMaoDeObra` |

## Observações de modelagem

- Esta sub-área só é relevante para contratos com `mao_obra_exclusiva=True`: a aba "Mão de Obra"
  e as permissões `pode_gerenciar_mao_de_obra` giram em torno dessa marca, e é dela que sai a
  base de cálculo da conta vinculada.
- **Duas fontes de remuneração convivem:** o campo `MaoDeObra.salario_bruto` e a soma das
  `VerbaSalarialMaoDeObra` (`MaoDeObra.valor_total_das_verbas`). O cálculo da conta vinculada usa
  `salario_bruto` **ou**, se ausente, o total das verbas
  (`Medicao._calcular_item_conta_vinculada`). ⚠️ REVISAR: qual é a fonte canônica não está
  explícito, e as duas podem divergir.
- `VerbaSalarialMaoDeObraForm.clean()` impede duas verbas do mesmo tipo para o mesmo trabalhador —
  regra que **não** existe como constraint no banco. ⚠️ REVISAR: unicidade apenas no formulário.
- Os `PROTECT` em ocorrências e verbas impedem apagar uma `MaoDeObra` que tenha histórico; a via
  normal de "desligar" é preencher `desligamento`, não excluir.
- `copiar_maodeobra` (view) clona registros para outro contrato zerando o `id` — o novo registro
  aponta para o mesmo `PrestadorServico`, sem copiar anexos, ocorrências nem verbas.
  ⚠️ REVISAR: cópia parcial, possivelmente intencional.
- `relatorio_terceirizados_xls` expõe o CPF do trabalhador, com opção de mascarar
  (`anonimizar_cpf`) — dado pessoal sensível trafegando em exportação.

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `Contrato` | `contratos` — subdomínio [contrato-nucleo.md](contrato-nucleo.md) |
| `PrestadorServico` | `comum` |
| `UnidadeOrganizacional` | `rh` |
| `ContaVinculadaCalculoItem` | `contratos` — subdomínio [conta-vinculada.md](conta-vinculada.md) (referencia `MaoDeObra` com `SET_NULL`) |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-11._
