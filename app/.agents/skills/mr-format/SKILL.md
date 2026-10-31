---
name: mr-format
description: >
  Formats GitLab MR title and description following SUAP convention.
  Title: `[module] Brief description`. Body: # Descrição com seções
  Sumário, Problema, Alterações, Refs, Revisores, Changelog.
  Trigger: /mr-format <url>, "format mr", "padronizar mr",
  "formatar descrição do mr".
trigger: /mr-format
---

Padroniza título, descrição, assignee e milestone de um MR existente no formato SUAP.

## Execução não interativa

Roda headless no CI (job `mr-auto`, primeiro pipeline de todo MR; job manual `mr-format`). Recebe
só a URL do MR. **Nunca pergunte nem ofereça alternativas** ("se preferir, posso…"): ninguém
responde. Toda ambiguidade tem regra abaixo; o que não puder ser resolvido fica sem alterar e vai
para o relatório final, que é log de CI, em pt-BR.

## Ferramentas e fallback

Os nomes `gitlab_*` abaixo são contratos lógicos do catálogo compartilhado. Resolva-os
para a ferramenta GitLab equivalente disponível no cliente. No Codex, quando o conector
não expuser uma operação, use `glab api`/`glab mr update` autenticado; `curl` exige
`GITLAB_TOKEN` explícito. Se nenhuma opção autenticada existir, reporte a dependência e
não tente descobrir tokens em arquivos pessoais.

## Formato

Título: `[modulo] Descrição concisa em português` — verbo no gerúndio, sem ponto final, ≈72 caracteres.

```
[edu] Otimizando o processamento dos abonos de faltas em lote
[almoxarifado] Corrigindo data_prazo do empenho quando a data_recebimento é inválida
[ci] Repartindo o unitario-modulo em 3 shards com pytest-split
```

Corpo:

~~~markdown
# Descrição

## Sumário

<o que foi feito e por quê>

## Problema

<problema resolvido; erro do Sentry/chamado se houver>

```
<stacktrace ou mensagem de erro, se houver>
```

## Alterações

- **`<caminho/do/arquivo>`**: <o que mudou>

Closes #<issue>
Refs: SUAP-XXXX

## Revisores

@user1 @user2

Changelog: <categoria>
~~~

- `Problema`: omita a seção quando não houver problema a descrever (feature pura).
- `Closes #<n>` para issue do GitLab (fecha no merge); `Refs:` para Sentry. Omita a linha sem referência.

## Processo

### 1. Coletar

Extraia `project_id` e `merge_request_iid` da URL e busque:

- `gitlab_get_merge_request`: título, descrição, `source_branch`, `target_branch`, `author.id`, `author.username`, `labels`.
- `gitlab_get_branch_diffs` (`from=target_branch`, `to=source_branch`): arquivos alterados.
- `gitlab_list_commits` (`ref_name=source_branch`): mensagens de commit.
- `gitlab_get_file_contents` (`.gitlab/CODEOWNERS`, `ref=target_branch`).

### 2. Módulo

Primeira regra que resolver:

1. Título atual já no formato `[x] ...` → `x`.
2. App dominante nos paths do diff (diretório de topo com mais arquivos alterados).
3. Só arquivos fora de app: `.gitlab-ci.yml`/`bin/ci/` → `ci`; `.agents/`, `.claude/`, `.opencode/`, `.codex/`, `AGENTS.md`, `CLAUDE.md` → `agents`; demais → `djtools`.

Vários apps: use o dominante no título e cite os demais no Sumário.

### 3. Revisores

Entrada do `.gitlab/CODEOWNERS` cuja chave (sem a `/` final) é o módulo → seus owners. Sem
correspondência → `@hugo.sena`. Remova `author.username` da lista; se esvaziar, `@hugo.sena`.
Formato `@user1 @user2`. Os revisores ficam **só no corpo**: não altere o campo `reviewers` do MR.

### 4. Changelog

Primeira regra que resolver:

1. A descrição atual já tem `Changelog: <x>` com `<x>` entre as chaves de `categories` em `.gitlab/changelog_config.yml` → mantenha.
2. Inferir: correção de bug (verbo "Corrigindo", issue com label de bug, referência a Sentry/chamado de erro) → `fixed`; funcionalidade nova → `added`; mudança de comportamento existente → `changed`; remoção → `removed`; vulnerabilidade → `security`.
3. Fallback: `fixed`.

Os commits do SUAP seguem `[modulo] Gerúndio`, não Conventional Commits: não procure prefixo `fix:`/`feat:`.

### 5. Título e corpo — idempotente

- **Descrição já no formato** (tem `# Descrição` e `## Sumário`): preserve o texto do autor
  integralmente. Só acrescente o que falta (`## Revisores`, `Changelog:`, `Closes`/`Refs`) e
  corrija os revisores se divergirem do passo 3. Não resuma, não reescreva, não reordene.
- **Fora do formato**: gere o corpo a partir de commits + diff, preservando todo o conteúdo útil
  da descrição atual (texto do autor, links, menções, `Refs` de Sentry, stacktraces).
- Título já conforme → mantenha. Senão, monte `[modulo] <gerúndio + descrição>`.
- Remova quick actions (`/assign`, `/milestone`, `/draft`, `/subscribe`) que tenham sobrado do template.

### 6. Milestone

| Changelog | Milestone |
|---|---|
| `fixed`, `security`, `performance`, `bug` | `Bugs` |
| demais | `Backlog - Atividades` |

Busque o id **pelo título exato**, só entre os ativos:

```bash
glab api "projects/<project_id>/milestones?state=active&title=Bugs"
```

(ou `curl -s --header "PRIVATE-TOKEN: $GITLAB_TOKEN" "https://gitlab.ifrn.edu.br/api/v4/projects/<project_id>/milestones?state=active&title=Bugs"`; título com espaço vai URL-encoded.)
Lista vazia → não atribua milestone e registre no relatório. Nunca escolha id por semelhança de nome.

### 7. Atualizar — uma chamada

`gitlab_update_merge_request` com `title`, `description`, `assignee_ids: [author.id]` e
`milestone_id`. Se a ferramenta não aceitar `milestone_id`, faça um PUT
`projects/<project_id>/merge_requests/<iid>` com `{"milestone_id": <id>}` via `glab api`/`curl`.
Releia o MR e confira que título, milestone e assignee ficaram gravados — o PUT responde 200 mesmo
quando ignora o milestone.

### 8. Relatório

```
MR formatado: <url>
- Título: mantido | alterado para `<novo>`
- Descrição: preservada (+<seções acrescentadas>) | gerada
- Changelog: <x> (<regra usada>)
- Milestone: <título> | não atribuído: <motivo>
- Assignee: @<author.username>
```

## Boundaries

- Não cria MR, não faz merge, não muda draft, não toca branch/commits/código.
- Só altera título, descrição, assignee e milestone.
