---
name: pgd-rit
description: >
  Ao abrir/atualizar um MR, lança UMA execução (RIT) no PGD do SUAP para aquele MR:
  lê a issue + diff, infere a entrega planejada casando o conteúdo contra a descrição
  e os critérios da Entrega PES de cada categoria, usa as horas registradas no MR via
  /spend (ou estima pelo diff), mostra um resumo, o servidor confirma, e grava o RIT
  (em EM_CADASTRO_RIT) idempotente por (projeto, MR). Modo lote: lança de uma vez os
  RITs dos MRs mergeados num mês que ainda não têm RIT.
  Trigger: /pgd-rit, /pgd-rit lote <AAAA-MM>, "lançar execução no pgd",
  "registrar o rit desse MR", "lançar os RITs de setembro".
trigger: /pgd-rit
---

Lança a execução do PGD a partir de um MR. **Uma RIT por MR.** O servidor confirma antes de gravar.

Dois modos:

- **Um MR** (padrão) — o MR atual ou o que o servidor apontar. Segue o [Processo](#processo-em-ordem).
- **Lote** — `/pgd-rit lote <AAAA-MM>` ou um pedido como "lançar os RITs de setembro". Todos os MRs do servidor mergeados no mês que ainda não têm RIT. Segue o [Modo lote](#modo-lote-um-mês).

As tools MCP são referenciadas pelo nome OpenCode (`get_entregas_disponiveis_pgd2`, `get_horas_pit_pgd2`, `lancar_rit_execucao_gitlab`, `get_rit_do_mr_pgd2`, `get_gitlab_mr_diff`, `list_gitlab_merge_requests`, `post_gitlab_mr_comment`). No Claude Code, elas resolvem para `mcp__suap__<nome>` (carregue os schemas via `ToolSearch` antes de chamar).

## Pré-requisitos

- O MR já existe (rode após o `open-pr`/`new-feat`, ou aponte o MR explicitamente).
- O autor do MR tem `username_gitlab` mapeado no SUAP (senão: avise e pare).

## Processo (em ordem)

Execute os passos **em ordem**. Não pule passos. **Nunca grave** (Step 6) sem a confirmação explícita do servidor após o dry-run (Step 5).

### Step 1 — Contexto do MR

Use `get_gitlab_mr_diff` para obter título, branch, autor, `project_id` e o diff, e `get_gitlab_mr_status` para o tempo registrado no MR. Capture:

- `gitlab_project_id` (`project_id`, numérico, estável a renomeação) e `gitlab_mr_iid`;
- `gitlab_username` do autor (`author_username`);
- data do 1º commit do branch (→ `data_inicio`);
- `time_spent_seconds` (horas medidas pelo hook `register_mr_time_spent` via `/spend` → Step 4);
- o diff (tamanho/natureza → estimativa de horas no Step 4, quando não há tempo registrado).

Se precisar dos labels/corpo da issue vinculada e eles não estiverem no MR, use `get_gitlab_issue` (se disponível); caso contrário, trabalhe com os dados do próprio MR.

### Step 2 — Entregas candidatas

Use `get_entregas_disponiveis_pgd2` com o `gitlab_username` do autor. Recebe as categorias (entregas) com `pes_descricao` + `pes_criterios_avaliacao` + `metrica` + período (`periodo_titulo`, `pit_data_inicio`, `pit_data_fim`, `eh_periodo_corrente`).

- Se o username **não mapear (404)** ou a tool retornar `Pgd2Error` → avise o servidor e **PARE** (oriente lançamento manual). Não prossiga.

### Step 3 — Inferir a entrega (categoria)

Case o trabalho do MR (título/descrição/diff/labels) contra a `pes_descricao` e os `pes_criterios_avaliacao` de **cada** categoria:

- bug/chamado → categoria de **atendimento de erros/chamados**;
- feature/demanda → categoria de **desenvolvimento de sistemas**;
- review → categoria de **revisão de código**; etc.

**Mês/PIT:** se a issue/MR tem label de mês/ano (ex.: `2026-06`), escolha a entrega cujo período (`pit_data_inicio`..`pit_data_fim`) casa com esse mês; senão, use a do período corrente (`eh_periodo_corrente: true`).

- **Se nenhuma categoria casar** → avise e **NÃO grave** (o servidor escolhe manualmente ou pede a entrega ao gestor).
- Se **ambíguo** (várias casam) → liste o top-N e peça ao servidor para escolher antes de seguir.

### Step 4 — Estimar horas e montar o RIT

- `tempo_executado`:
  - **medido** — se `time_spent_seconds > 0`, use `time_spent_seconds / 3600` (2 casas). É o tempo que o hook registrou no MR; prefira-o à estimativa.
  - **estimado** — senão, estime pelo tamanho/natureza do diff (nº de arquivos/linhas, complexidade). **Explique a heurística no resumo** do Step 5.
  - Diga no resumo qual das duas fontes usou.
- `quantidade_progresso = 1` (um MR = um trabalho), qualquer que seja a métrica da categoria.
- `titulo`: título da issue/MR.
- `descricao`: resumo curto + **link do MR/issue no GitLab** (evita duplicar conteúdo no SUAP — a fonte da verdade do trabalho continua o GitLab).
- `data_inicio`: data do 1º commit do branch. `data_fim`: hoje (servidor ajusta).
- `perc_executada_em_teletrabalho`: **100** — a TI do IFRN é 100% remota (é também o padrão da tool). Se o `percentual_teletrabalho` do PIT, lido em `get_horas_pit_pgd2`, vier diferente de 100, avise o servidor no resumo e use o que ele confirmar.

### Step 5 — Resumo + confirmação (dry-run)

Mostre ao servidor: entrega escolhida (+ período), horas (medidas ou estimadas, com a heurística), % em teletrabalho, título, descrição e o link. Mostre também as horas do PIT da entrega, de `get_horas_pit_pgd2`: previsto, já lançado e quanto falta depois deste RIT.

Chame `lancar_rit_execucao_gitlab` com `confirm=false` para validar o payload (dry-run, **sem gravar**) e mostre o preview retornado.

**Só prossiga para o Step 6 após o servidor confirmar explicitamente.**

### Step 6 — Gravar

Chame `lancar_rit_execucao_gitlab` com `confirm=true`. Reporte `rit_id` e se foi `criado` (ou atualizado — a operação é idempotente por `(gitlab_project_id, gitlab_mr_iid)`).

Erros tratados:

- **403** — entrega de outro servidor / período fechado / mês já enviado → explique a causa e oriente o lançamento manual no PGD.
- **404** — `username_gitlab` não mapeado no SUAP → explique e oriente o servidor a regularizar o mapeamento (ou lançar manual).

Opcionalmente, após gravar, registre um comentário no MR com `post_gitlab_mr_comment` informando o `rit_id` lançado.

## Modo lote (um mês)

Lança, numa só confirmação, os RITs dos MRs do servidor **mergeados no mês** que ainda não têm RIT. Mesmas regras do modo de um MR (entrega por PES, `quantidade_progresso = 1`, descrição curta + link, nada gravado sem confirmação); muda a coleta, que é em lote, e a confirmação, que é por tabela.

### L1 — Mês, autor e projetos

- **Mês:** `AAAA-MM`. Um nome de mês sem ano ("setembro") é do ano corrente; se cair no futuro, é do ano anterior. Confirme o mês se houver dúvida.
- **Janela de merge** no fuso do IFRN: `merged_after = AAAA-MM-01T00:00:00-03:00` e `merged_before = <1º dia do mês seguinte>T00:00:00-03:00` (o fim é exclusivo).
- **Autor:** o `username` GitLab do servidor. Se ele não disser, pergunte; não deduza.
- **Projetos:** `cosinf/suap` por padrão; inclua outros projetos se o servidor pedir.

### L2 — MRs mergeados no mês

Para cada projeto, chame `list_gitlab_merge_requests` com `state="merged"`, `author`, `merged_after`, `merged_before` e `limit=200`. Cada MR traz `iid`, `project_id`, `title`, `web_url`, `created_at`, `merged_at` e `time_spent_seconds`.

- Se a resposta vier com `truncated: true` → avise e repita por quinzena; não siga com uma lista incompleta.
- MRs abertos ou fechados sem merge ficam de fora: o lote é do trabalho entregue no mês. Para um MR ainda aberto, use o modo de um MR.
- Nenhum MR → informe e **PARE**.

### L3 — Separar o que já tem RIT

Para cada MR, chame `get_rit_do_mr_pgd2` com `project_id` e `iid`:

- **Retornou RIT** → **já lançado**: liste com `rit_id`, entrega e horas, e **não relance**. O lançamento é idempotente, então relançar sobrescreveria o que o servidor ajustou no SUAP.
- **Sem RIT** (404 / `Pgd2Error` "Nenhum RIT para este MR.") → **pendente**, segue para L4.
- Qualquer outro erro → reporte e **PARE**.

### L4 — Entregas do mês

Chame `get_entregas_disponiveis_pgd2` **uma vez**, com o `username` do servidor. Fique só com as entregas cujo PIT (`pit_data_inicio`..`pit_data_fim`) contém o mês.

- Username não mapeado (404) ou `Pgd2Error` → avise e **PARE** (vale para o lote inteiro).
- Nenhuma entrega para o mês → avise (o mês não está num PIT do servidor) e **PARE**.

Chame também `get_horas_pit_pgd2` **uma vez** e fique com o PIT do mês. Ele traz:

- `tempo_previsto` — a **meta do mês**: a CH prevista do servidor no período, vinda do ponto (já desconta afastamentos e férias);
- `tempo_executado_total` — o que já está lançado nos RITs do PIT;
- `tempo_restante` — quanto falta para a meta (nunca negativo);
- `percentual_teletrabalho` — o % pactuado no PIT; se vier diferente de 100, avise o servidor (o padrão dos RITs é 100).

Se `tempo_previsto` vier 0, o SUAP não tem a CH do ponto para o período: pergunte a meta ao servidor em vez de assumir.

### L5 — Entrega, horas e datas de cada MR pendente

- **Entrega:** como no Step 3, casando o título contra `pes_descricao`/`pes_criterios_avaliacao`. Se só o título não basta, leia o diff com `get_gitlab_mr_diff` (`max_files=20`, `max_lines_per_file=50`). Nada casa → **sem entrega** (não grava). Várias casam → **ambíguo** (o servidor escolhe em L6).
- **Horas:** `time_spent_seconds > 0` → **medido** (`/ 3600`, 2 casas). Senão → **estimado** pelo diff (`get_gitlab_mr_diff`), como no Step 4.
- **Datas:** `data_inicio` = data de `created_at`; `data_fim` = data de `merged_at`, ambas convertidas para −03:00 antes de cortar a data (um merge às 01:00Z ainda é do dia anterior).
- **Título/descrição:** título do MR; descrição curta + `web_url`.
- **Teletrabalho:** `perc_executada_em_teletrabalho` = 100 (a TI é 100% remota), salvo se o servidor pedir outro valor.

### L6 — Tabela + confirmação

Mostre uma tabela única com os pendentes:

| MR | Título | Entrega | Horas | Fonte | Início | Fim |
| -- | ------ | ------- | ----- | ----- | ------ | --- |

Acima dela, a meta do mês (L4): **previsto X h · já lançado Y h · faltam Z h**, e o % de teletrabalho que vai em cada RIT. Abaixo: o total de horas dos pendentes comparado ao que falta, os **já lançados** (L3), os **sem entrega** e os **ambíguos** (com as opções de entrega). Valide cada linha com `lancar_rit_execucao_gitlab` `confirm=false` (dry-run) antes de mostrar.

Se o total dos pendentes passa do que falta, diga quanto passa e quais linhas, na ordem da tabela, cabem na meta; o servidor decide o corte. Não ajuste estimativas para fechar a conta sem dizer: qualquer ajuste de horas aparece na tabela.

Peça uma confirmação explícita do lote. O servidor pode tirar linhas, trocar a entrega ou corrigir as horas de qualquer uma; aplique e mostre a tabela de novo antes de gravar. Ambíguos sem escolha e sem entrega **não** são gravados.

### L7 — Gravar

Para cada linha confirmada, **em sequência**, chame `lancar_rit_execucao_gitlab` com `confirm=true`.

- **403** num MR (período fechado / mês já enviado) → registre o motivo e siga com os demais.
- **404** (username não mapeado) → **PARE**: vale para todos.
- Erro de rede/timeout → **PARE** e reporte o que já foi gravado. Rodar o lote de novo é seguro: o que foi gravado volta como "já lançado" em L3.

Ao final, chame `get_horas_pit_pgd2` de novo e mostre a tabela com `rit_id` e `criado` de cada MR, as falhas com o motivo, o novo **já lançado / faltam** do mês, e lembre o servidor de revisar e enviar o RIT do mês no PGD. **Não comente nos MRs** no modo lote (são MRs já mergeados; o comentário seria ruído).

## Tabela de tools

| Step | Ação                  | Tool (OpenCode → Claude Code)                                                   |
| ---- | --------------------- | ------------------------------------------------------------------------------- |
| 1    | Diff/metadados do MR  | `get_gitlab_mr_diff` → `mcp__suap__get_gitlab_mr_diff`                           |
| 1    | Tempo registrado      | `get_gitlab_mr_status` → `mcp__suap__get_gitlab_mr_status`                       |
| 2    | Entregas candidatas   | `get_entregas_disponiveis_pgd2` → `mcp__suap__get_entregas_disponiveis_pgd2`    |
| 5    | Preview (dry-run)     | `lancar_rit_execucao_gitlab` (`confirm=false`) → `mcp__suap__lancar_rit_execucao_gitlab` |
| 6    | Gravar RIT            | `lancar_rit_execucao_gitlab` (`confirm=true`) → `mcp__suap__lancar_rit_execucao_gitlab`  |
| 6    | Comentar no MR (opc.) | `post_gitlab_mr_comment` → `mcp__suap__post_gitlab_mr_comment`                   |
| L2   | MRs mergeados no mês  | `list_gitlab_merge_requests` → `mcp__suap__list_gitlab_merge_requests`           |
| L3   | RIT já lançado?       | `get_rit_do_mr_pgd2` → `mcp__suap__get_rit_do_mr_pgd2`                           |
| L4   | Entregas do mês       | `get_entregas_disponiveis_pgd2` → `mcp__suap__get_entregas_disponiveis_pgd2`    |
| 5/L4/L7 | Meta e saldo do PIT | `get_horas_pit_pgd2` → `mcp__suap__get_horas_pit_pgd2`                           |
| L5   | Diff (se precisar)    | `get_gitlab_mr_diff` → `mcp__suap__get_gitlab_mr_diff`                           |
| L6/L7 | Dry-run e gravação   | `lancar_rit_execucao_gitlab` → `mcp__suap__lancar_rit_execucao_gitlab`           |

## Boundaries

- **NÃO grava sem confirmação.** O dry-run (`confirm=false`) é obrigatório antes do `confirm=true`.
- **NÃO inventa entrega.** Se nada casa, avisa e para — sem gravar.
- **Uma RIT por MR.** `quantidade_progresso = 1`; o total da categoria é somado pelo SUAP.
- **Não duplica conteúdo no SUAP.** A `descricao` é um resumo + link; o GitLab continua a fonte.
- Idempotente por `(gitlab_project_id, gitlab_mr_iid)`: rodar de novo no mesmo MR atualiza o mesmo RIT.
- Se a inferência for ambígua, para e pede ao servidor para escolher.
- **Horas medidas primeiro.** Com `time_spent_seconds > 0`, use o tempo registrado no MR; estimar pelo diff é só o plano B, e o resumo diz qual fonte foi usada.
- **Lote não relança.** MR que já tem RIT fica como está; o lote só cria os que faltam.
