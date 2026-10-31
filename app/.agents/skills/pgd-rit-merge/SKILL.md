---
name: pgd-rit-merge
description: >
  No merge de um MR (push na master, headless via CI), posta um comentário de
  confirmação no MR sobre o RIT que foi lançado no PGD durante a fase de PR:
  lê o RIT por (projeto, MR) com get_rit_do_mr_pgd2 e, se existir, comenta o id
  da execução, a entrega e as horas, lembrando o servidor de revisar e enviar o
  RIT do mês; se não houver RIT, comenta lembrando o lançamento manual no PGD.
  Não grava nada no PGD — é só comentário. Uso headless no merge (job de CI).
  Trigger: /pgd-rit-merge.
trigger: /pgd-rit-merge
---

Comenta no MR, no merge, qual RIT foi lançado no PGD durante a fase de PR (ou lembra o lançamento manual, se nenhum foi confirmado). **Só comenta — não grava RIT.** O RIT já foi criado na fase PR pela skill `pgd-rit`.

As tools MCP são referenciadas pelo nome OpenCode (`get_rit_do_mr_pgd2`, `post_gitlab_mr_comment`). No Claude Code, elas resolvem para `mcp__suap__<nome>` (carregue os schemas via `ToolSearch` antes de chamar).

## Pré-requisitos

- O MR já foi mergeado; o job de CI resolve o `MR_IID` + `PROJECT_ID` do commit de merge e passa para a skill.
- O comentário é informativo: não bloqueia nada e não altera estado no PGD.

## Processo (em ordem)

### Step 1 — Ler o RIT do MR

Use `get_rit_do_mr_pgd2` com o `gitlab_project_id` e o `gitlab_mr_iid` recebidos. Dois desfechos:

- **Retornou RIT** (200) → capture `rit_id`, `entrega_titulo`, `tempo_executado` (e `situacao_rit`) → Step 2.
- **Sem RIT** (404 / `Pgd2Error`) → nenhum RIT foi lançado para este MR na fase PR → Step 3.

Qualquer outro erro (rede/timeout): reporte e **PARE** sem comentar (evita comentário enganoso).

### Step 2 — Comentar a confirmação (RIT existe)

Poste no MR via `post_gitlab_mr_comment` algo como:

> ✅ RIT #<rit_id> lançado no PGD — entrega «<entrega_titulo>», <tempo_executado>h. Lembre de revisar e enviar o RIT do mês.

Tom: curto, informativo, em pt-BR. Não repita o conteúdo do MR; o RIT no SUAP referencia o GitLab.

### Step 3 — Comentar o lembrete (sem RIT)

Quando não há RIT para o MR (o servidor não confirmou nenhum rascunho na fase PR), poste via `post_gitlab_mr_comment` um lembrete de lançamento manual:

> ℹ️ Nenhuma execução foi lançada no PGD para este MR. Se o trabalho conta para o seu PIT, lance o RIT manualmente no PGD.

## Tabela de tools

| Step | Ação              | Tool (OpenCode → Claude Code)                                       |
| ---- | ----------------- | ------------------------------------------------------------------- |
| 1    | Ler RIT do MR     | `get_rit_do_mr_pgd2` → `mcp__suap__get_rit_do_mr_pgd2`              |
| 2/3  | Comentar no MR    | `post_gitlab_mr_comment` → `mcp__suap__post_gitlab_mr_comment`      |

## Boundaries

- **Só comenta — não grava RIT.** O RIT já foi criado na fase PR (skill `pgd-rit`); aqui só se lê e se informa.
- **Idempotência/tom:** mantenha o comentário curto e único por execução; não duplique o conteúdo do MR nem reescreva o RIT.
- **Sem RIT ≠ erro:** 404 é um desfecho esperado (commit direto / RIT não confirmado) → vira lembrete, não falha.
- **Erro de rede:** não comente nada se a leitura do RIT falhar por motivo diferente de 404 — evita confirmar/lembrar sem certeza.
