---
name: loop-bugfix
description: >
  Corrige uma fila de issues de bug em paralelo, numa janela deslizante de N MRs em voo:
  um subagente por MR em worktree próprio → revisão do diff → push + MR → vigia de estado,
  pipeline e comentários → próximo item da fila a cada merge. Opcionalmente registra tempo e
  RIT por rodada. Só o usuário dispara (efeitos colaterais: push, MR, merge).
  Trigger: /loop-bugfix <issues|label|milestone> [janela=N], "corrige essas issues em lote",
  "loop de bugfix", "deixa sempre N MRs abertos".
trigger: /loop-bugfix
disable-model-invocation: true
---

# Loop de bugfix em janela deslizante

Esteira para fechar muitas issues de bug sem ficar ociosa: há sempre **N MRs em voo**
(subagente corrigindo ou MR aberto aguardando CI/revisão). A cada merge ou abandono, o próximo
item da fila é despachado. Não espere a "rodada" fechar para despachar.

Os nomes de ferramenta abaixo são genéricos. Mapeamento:

| Conceito | Claude Code | OpenCode / Codex |
|---|---|---|
| subagente em worktree próprio | `Agent` com `isolation: "worktree"` | subagente apontado para um `git worktree add` dedicado |
| vigia em background | `Monitor` (ou Bash em background) | processo em background no shell |
| pergunta em lote | `AskUserQuestion` | pergunta no chat |

## 0. Combinar uma vez, no início

Pergunte **uma vez**, em lote, e anote as respostas no arquivo de fila (passo 1):

1. **Janela** (N MRs em voo). Sem resposta, use 4.
2. **Merge**: auto-merge após CI verde, ou o usuário mescla cada um à mão.
3. **Tempo/RIT**: registrar? Por MR na abertura ou por rodada no merge? Qual entrega do PGD?
   (skills `carga-horaria` e `pgd-rit`). Nunca assuma a entrega.
4. **Decisões de produto/permissão já visíveis nas issues** ("papel X perde acesso pela URL?"),
   com a opção recomendada primeiro. Decisão em aberto não vira MR: pergunte antes de despachar.

## 1. Montar a fila

No scratchpad da sessão, crie:

- `fila.md`: issue → estado (`fila`/`em correção`/`MR !iid`/`mesclado`/`abandonado`), base do
  loop (`git rev-parse origin/master` no início), respostas do passo 0 e tempo já lançado.
- `em_voo.txt`: um iid de MR por linha (lido pela vigia, passo 4).
- Um subdiretório **por issue** (`h<iid>/`) para os artefatos de cada subagente. O scratchpad
  é compartilhado: dois subagentes já sobrescreveram o harness um do outro.

Issues que caem na mesma view/arquivo viram **um** MR e contam como 1 na janela. Antes de
despachar uma issue que mexe em arquivo já tocado no loop, leia as discussões dos MRs
anteriores desse arquivo (`glab api projects/cosinf%2Fsuap/merge_requests/<iid>/discussions`):
um revisor pode ter pedido para excluir o código em vez de corrigi-lo.

## 2. Despachar um subagente por MR

Modelo de risco médio ou maior (um modelo barato já ignorou o passo de criar a branch e
commitou na branch automática do worktree). Prompt comum, com estes itens **explícitos**:

1. Primeiro passo: `git fetch -q origin master && git checkout -q -b <branch> origin/master`;
   copiar o `suap/settings.py` do checkout da sessão se o worktree não o tiver;
   `uv sync --all-groups --frozen`.
2. Editar **só com as ferramentas de edição** (Edit/Write ou equivalente), **nunca por shell**
   (`sed`, heredoc, `python -c`): editar por shell pula os hooks de ruff e de C901. Se a edição
   for recusada, parar e reportar, não contornar.
3. Banco de teste próprio: o `docker run` do `AGENTS.md` (`## Commands`) com `--shm-size=1g`,
   nome `suap-test-db-<iid>` e porta `55` + os 3 últimos dígitos do iid (55000–55999); rodar
   com `DATABASE_PORT=<porta>` e um `TEST_DATABASE_NAME` exclusivo. O Postgres compartilhado dá `DiskFull`
   com 4–5 agentes e um agente recria o banco do outro. Parar o container no fim.
4. Teste no estilo do `AGENTS.md` (`## Testes`); remover `xfail` só quando o teste passa,
   nunca afrouxar assert. Asserts por id/ORM, não por posição na página: MRs irmãos mudam a
   mesma tela e quebram testes posicionais no pipeline de merged-result.
5. Não decidir permissão nem produto: reportar a dúvida.
6. Commit no formato do MR (`[modulo] ...`), **sem push**. Relatório: caminho do worktree,
   branch, arquivos, comando de teste e saída.

## 3. Revisar e abrir o MR

O verde do subagente não é prova. Para cada um:

- `git branch --show-current` no worktree; se for a branch automática, `git branch -m <branch>`.
- Ler o diff inteiro. Conferir C901 com `ruff check --select C901 <arquivos>` (o hook pode
  medir no checkout errado quando o subagente está em outro worktree).
- Rodar o teste como o CI roda: `pytest -n 3 -x -m "not e2e and not doc" <escopo>`, duas vezes.
- `git push -u origin <branch>` e `glab mr create` **de dentro do repo** (nunca `-R`). Conferir
  com `glab mr list --source-branch <branch>`: às vezes o create não cria nada e não dá erro.
- Trocar título de MR em draft: passe `--draft` junto, senão o MR vira "pronto" em silêncio.
- Acrescentar o iid em `em_voo.txt`.

**Auto-merge (se combinado):** só arme com `head_pipeline.status == running`. Com o pipeline
`pending`/`created`/ausente, `glab mr merge --auto-merge` **mescla na hora, sem CI**. Qualquer
push no branch desarma: rearme com a mesma espera. Depois de armar, confira na API
`merge_when_pipeline_succeeds == true` e `state == opened`.

## 4. Vigiar

```bash
<dir-desta-skill>/vigiar_mrs.py <scratchpad>/em_voo.txt 60
```

Imprime uma linha por mudança de estado, pipeline ou **número de comentários**, mostra os erros
do `glab` no stderr e termina quando todos os MRs listados saem de `opened`. Antes de deixar
uma vigia nova rodando, teste-a com `timeout 20`: vigia que morre calada é indistinguível de
"ainda rodando". Em espera longa e ociosa (usuário revisando), não rearme a vigia em laço: cada
rearme vira "tempo ativo" na medição de horas. Prefira uma vigia longa ou pare e espere.

A cada evento:

- `comentarios` subiu → ler as notes e agir (ou perguntar).
- `pipeline=failed` → diagnosticar (o subagente retoma pelo id, com o worktree intacto).
- `state=merged` → atualizar `fila.md`, tirar o iid de `em_voo.txt`, **despachar o próximo**.

## 5. Tempo e RIT (se combinado)

No OpenCode não há transcrição para medir: `--horas` cai no backfiring por LOC (≈50 LOC/h), que
não mede espera nem revisão. Todas as branches partem do mesmo master, então as janelas de tempo se sobrepõem: somar o
`--horas` de cada MR conta o mesmo tempo várias vezes. Por rodada:

1. `.agents/hooks/register_mr_time_spent.py --horas <base do loop>` − já lançado (em `fila.md`).
   Descontar esperas ociosas com vigia rearmada.
2. Dividir pelos MRs mesclados na rodada e lançar em cada um com
   `glab api -X POST projects/cosinf%2Fsuap/merge_requests/<iid>/add_spent_time?duration=<N>m`.
   Não use `REGISTRAR_TEMPO=True` em cada `mr create`: isso lançaria a sessão inteira em todos.
3. RIT: dry-run de todos numa tabela (MR | issue | horas), uma confirmação, depois gravar
   (skill `pgd-rit`). Use o título atual do MR, lido da API: um bot pode tê-lo reescrito.

## 6. Achados fora de escopo e parada

- Achado relevante (acesso indevido, 500, dado errado): confirmar com um subagente só de leitura,
  informar o usuário e só abrir issue se ele pedir. Achado cosmético não vira issue.
- Fila vazia e `em_voo.txt` vazio → resumo final (MRs, horas, pendências).
- Limpeza: `git worktree remove` (sem `--force`) só nos worktrees limpos com MR mesclado, e
  `git branch -D` da branch local. Worktree de outra sessão, só com ok do usuário.
