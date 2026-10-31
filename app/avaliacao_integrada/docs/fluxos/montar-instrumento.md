# Fluxo: Montar o instrumento

> Cadastrar a árvore eixo → dimensão → macroprocesso e pendurar nela os indicadores (as perguntas) que serão aplicados nas avaliações.

- **Ator(es):** Administrador de Avaliação Institucional — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** cadastros no Django admin (`/admin/avaliacao_integrada/eixo/`, `.../dimensao/`, `.../macroprocesso/`, `.../indicador/`), nessa ordem
- **Pré-condições:** existir ao menos um `TipoAvaliacao`, os `Ano` de referência (`comum.Ano`) e — para indicadores de escala — uma `EscalaLikert` com seus níveis
- **Pós-condições:** indicadores com `em_uso=True` e o ano de referência marcado passam a entrar em qualquer avaliação daquele ano cujos tipos e segmentos casem
- **Depende de:** _nenhum_
- **Habilita:** [Cadastrar avaliação](cadastrar-avaliacao.md)
- **Entrada no código:** `admin.EixoAdmin`/`DimensaoAdmin`/`MacroprocessoAdmin`/`IndicadorAdmin` + `forms.EixoForm`, `forms.IndicadorForm`; prévia em `views.indicador` (`/avaliacao_integrada/indicador/<pk>/`)

## Sequência

```mermaid
sequenceDiagram
    participant A as Administrador
    participant AD as "Django admin (ModelAdminPlus)"
    participant F as "Forms (EixoForm / IndicadorForm)"
    participant M as "Models (Eixo..Indicador)"
    participant DB as PostgreSQL
    A->>AD: "Adicionar Eixo (descrição, ordem)"
    AD->>F: valida
    F->>M: "EixoForm.save reordena os demais eixos"
    M->>DB: "INSERT/UPDATE eixo"
    A->>AD: "Adicionar Dimensão / Macroprocesso"
    M->>DB: "ordem = max(ordem)+1 no save() quando vazia"
    A->>AD: "Adicionar Indicador (27 campos, 7 blocos)"
    AD->>F: "IndicadorForm.clean: escala obrigatória p/ Likert; nome válido p/ autocalculado"
    F->>M: "save_model (SegmentoSaveMixin) recombina os 3 campos de segmento"
    M->>DB: "INSERT indicador + M2M (segmentos, áreas, modalidades, campi, anos, tipos)"
    AD-->>A: "Cadastro realizado com sucesso."
    A->>AD: "Replicar Indicador (opcional)"
    AD->>M: "views.replicar_indicador clona + sufixo [Replicado]"
    M-->>A: "redireciona para a edição da cópia"
```

## Observações

- A **ordem** é o que define a sequência no questionário: `Eixo.save`/`Dimensao.save`/`Macroprocesso.save`
  atribuem `max(ordem)+1` quando o campo vem vazio, e `EixoForm.save` **reordena os demais eixos** ao
  inserir numa posição já ocupada.
- `IndicadorForm` traz padrões fortes: áreas de vinculação Ensino/Extensão/Pesquisa e Inovação/Atividades
  Estudantis, 7 modalidades, tipo de resposta `ESCALA_LIKERT`, escala PK 5 e subsídio `PDI` (PK 10).
  Os anos de referência oferecidos vão de 2015 ao ano corrente.
- Os segmentos são editados em **três caixas** (servidores / alunos / sociedade civil) por
  `SegmentacaoForm`, e recombinados no M2M único `segmentos` pelo `SegmentoSaveMixin.save_model`.
- **Autocalculado** só é aceito para as 13 denominações de `Indicador.INDICADORES_AUTOCALCULADOS`
  (`clean` adiciona erro em `nome` caso contrário) — o casamento é por string exata.
- `Iterador` (inline do indicador) faz a pergunta se repetir por curso, modalidade, professor ou turma
  do respondente; sem ele, a pergunta é única e vale para a instituição.
- **Replicar** (`views.replicar_indicador`, permissão `pode_replicar_indicador`) copia o indicador,
  seus `subsidio_para`, segmentos, áreas, modalidades e `OpcaoResposta`. ⚠️ REVISAR: não copia
  `anos_referencia`, `uos` nem os `Iterador` — a cópia precisa ser completada à mão.
- `views.indicador` renderiza o campo isolado para conferência visual, sem respondente (todos os
  autocalculados aparecem vazios e somente-leitura).
- Aposentar uma pergunta = desmarcar **Em uso**; ela some dos questionários novos e os dados históricos
  permanecem nos relatórios.

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
