---
name: code-review
description: |
  Revisa MRs do SUAP (Django/Python, templates, JS) e publica os achados como draft notes
  no GitLab. Use ao revisar um MR, um diff ou mudanças de código, inclusive quando a
  entrada é só a URL de um MR (modo CI).
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash # executar lint/test/build para verificar qualidade do código
  - WebFetch # consultar documentação e melhores práticas atuais
  - gitlab_get_merge_request # obter detalhes do MR
  - gitlab_list_merge_request_changed_files # listar arquivos alterados
  - gitlab_get_merge_request_diffs # obter diffs do MR
  - gitlab_get_merge_request_file_diff # obter diff de arquivo específico
  - gitlab_create_draft_note # criar nota de revisão (rascunho)
  - gitlab_bulk_publish_draft_notes # publicar todas as notas como revisão (fora do CI; no CI é o pipeline que publica)
  - gitlab_create_merge_request_note # criar comentário geral no MR
---

# Code Review Excellence

Transform code reviews from gatekeeping to knowledge sharing through constructive feedback, systematic analysis, and collaborative improvement.

## Ferramentas e fallback

`allowed-tools` registra nomes lógicos usados pelo workflow OpenCode/CI. Em outros
clientes, inclusive Codex, resolva cada `gitlab_*` para a ferramenta GitLab equivalente.
Leitura de MR/diff pode usar `glab mr view`, `glab api` e `git diff`; publicação de draft
notes exige uma API/ferramenta que preserve exatamente o fluxo de rascunho abaixo. Se ela
não existir, entregue a revisão em texto e informe a limitação — não converta achados em
notas gerais nem tente publicar por outro fluxo.

## Idioma

Escreva todo o review (comentários inline, resumo, veredito) em português do Brasil — é o idioma do time e do repositório. Código, logs e mensagens de erro/exception mantêm o idioma original.

## Core Principles

### 1. The Review Mindset

**Goals of Code Review:**

- Catch bugs and edge cases
- Ensure code maintainability
- Share knowledge across team
- Enforce coding standards
- Improve design and architecture
- Build team culture

**Not the Goals:**

- Show off knowledge
- Nitpick formatting (use linters)
- Block progress unnecessarily
- Rewrite to your preference

### 2. Effective Feedback

**Good Feedback is:**

- Specific and actionable
- Educational, not judgmental
- Focused on the code, not the person
- Balanced (praise good work too)
- Prioritized (critical vs nice-to-have)

```markdown
❌ Bad: "This is wrong."
✅ Good: "This could cause a race condition when multiple users
access simultaneously. Consider using a mutex here."

❌ Bad: "Why didn't you use X pattern?"
✅ Good: "Have you considered the Repository pattern? It would
make this easier to test. Here's an example: [link]"

❌ Bad: "Rename this variable."
✅ Good: "[nit] Consider `userCount` instead of `uc` for
clarity. Not blocking if you prefer to keep it."
```

### 3. Review Scope

**What to Review:**

- Logic correctness and edge cases
- Security vulnerabilities
- Performance implications
- Test coverage and quality
- Error handling
- Documentation and comments
- API design and naming
- Architectural fit

**What Not to Review Manually:**

- Code formatting (use Prettier, Black, etc.)
- Import organization
- Linting violations
- Simple typos

## Autonomia no CI / Execução Automática

Quando o input do usuário contiver **apenas uma URL de Merge Request do GitLab** (ex: `https://gitlab.ifrn.edu.br/cosinf/suap/-/merge_requests/1234`), **execute o workflow completo automaticamente** sem fazer perguntas. Vá diretamente para o Phase 5 (Post Review to GitLab MR), realizando todas as etapas de context gathering, high-level review, line-by-line review internamente, e postando o resultado como draft notes no MR.

## Review Process

### Phase 1: Context Gathering

Before diving into code, understand:

1. Read PR description and linked issue
3. Review CI/CD status (tests passing?)
4. Understand the business requirement
5. Note any relevant architectural decisions

### Phase 2: High-Level Review

1. **Architecture & Design** - Does the solution fit the problem?
   - For significant changes, consult [Architecture Review Guide](reference/architecture-review-guide.md)
   - Check: SOLID principles, coupling/cohesion, anti-patterns
2. **Performance Assessment** - Are there performance concerns?
   - For performance-critical code, consult [Performance Review Guide](reference/performance-review-guide.md)
   - Check: Algorithm complexity, N+1 queries, memory usage
3. **File Organization** - Are new files in the right places?
4. **Testing Strategy** - Are there tests covering edge cases?

### Phase 3: Line-by-Line Review

For each file, check:

- **Logic & Correctness** - Edge cases, off-by-one, null checks, race conditions
- **Security** - Input validation, injection risks, XSS, sensitive data
- **Performance** - N+1 queries, unnecessary loops, memory leaks
- **Maintainability** - Clear names, single responsibility, comments

### Phase 4: Summary & Decision

1. Summarize key concerns
2. Highlight what you liked
3. Make clear decision:
   - ✅ Approve
   - 💬 Comment (minor suggestions)
   - 🔄 Request Changes (must address)

### Phase 5: Post Review to GitLab MR (if MR URL provided)

When the user provides a GitLab Merge Request URL, post the review directly to the MR using GitLab's review system (draft notes → publish). This creates a proper review, not just individual comments.

**Step 5.1 — Extract MR info:**

1. Parse the MR URL to extract `project_id` (URL-encoded path like `group/project`) and `merge_request_iid`
2. Call `gitlab_get_merge_request` to get MR metadata (title, description, branch, diff_refs)
3. Call `gitlab_list_merge_request_changed_files` to identify changed files
4. Call `gitlab_get_merge_request_diffs` for full diff content of changed files

**Step 5.2 — Create draft notes for each finding:**

For each code review finding:

- **Inline comment (line-specific):** Use `gitlab_create_draft_note` with `position` containing:
  - `base_sha`, `head_sha`, `start_sha` from MR's `diff_refs`
  - `position_type: "text"`
  - `new_path` / `old_path` (use same value if file wasn't renamed)
  - `new_line` for added/modified lines or `old_line` for deleted lines
  - Body: the review comment with severity label (🔴🟡🟢💡📚)
  - Nunca use inline comment para elogio. Comentários inline devem existir apenas para apontar problema, risco, dúvida, ou sugestão acionável.

  ⚠️ **A linha PRECISA existir dentro de um hunk do diff.** O GitLab aceita o rascunho com
  qualquer linha (o `create` não valida a posição), mas na publicação a nota some: o
  `bulk_publish` devolve **500** e a nota nunca é criada — as demais são publicadas, então
  o achado desaparece em silêncio. Foi o que aconteceu com um achado do !18709 (âncora em
  `dashboard.html:144`, fora dos hunks `@@ +92,14 @@`, `@@ +111,15 @@`, `@@ +131,8 @@`).

  Antes de cada `position`, confira nos hunks de `gitlab_get_merge_request_diffs` que a
  linha está no intervalo de algum `@@`. Se o ponto que você quer comentar não foi tocado
  pelo MR (código pré-existente, ou o efeito colateral está longe da mudança), **não force
  a âncora**: use comentário de arquivo (`position_type: "file"`) ou deixe o achado no sumário.

- **File-level comment:** Use `gitlab_create_draft_note` with `position` containing:
  - `position_type: "file"`
  - `base_sha`, `head_sha`, `start_sha` from diff_refs
  - `new_path` and `old_path` set to the file path
  - Nunca use file-level comment para elogio. Elogios ficam apenas no sumário final.

**Step 5.3 — Create summary draft note:**

Create one final draft note (no position, just body) with the full review summary:

```markdown
## Sumário

### Melhorias

- [o que foi bem feito]

### Mudanças Necessárias

- 🔴 [tarefas bloqueantes]

### Sugestões Importantes

- 🟡 [importantes mas não bloqueantes]

### Sugestões Menores

- 🟢 [nits]

### Pontos Positivos

- [elogios gerais, sem virar comentário inline]

### Veredito

✅ Approve / 💬 Comment / 🔄 Request Changes
```

**Step 5.4 — Publicar a revisão (uma única vez) e ENCERRAR:**

Criados os rascunhos, a revisão está pronta. A publicação é **um passo único e irrepetível**:

- **No CI (pipeline do SUAP):** não publique. As ferramentas `gitlab_bulk_publish_draft_notes`, `gitlab_publish_draft_note` e `gitlab_list_draft_notes` **não existem** nesse ambiente, de propósito — `bin/ci/opencode-skill.sh` publica os rascunhos ao final do job. Depois do último `gitlab_create_draft_note`, **encerre** e escreva o resumo em texto.
- **Fora do CI:** chame `gitlab_bulk_publish_draft_notes` **exatamente uma vez** e encerre.

**Nunca**, em nenhum ambiente:

- repetir o `bulk_publish`, **inclusive quando ele falhar**. Resposta vazia (`204`/`[]`) é sucesso, não falha. E um erro tampouco autoriza retentativa: o `bulk_publish` **não é atômico** — no !18709 ele devolveu `500` por causa de um rascunho com âncora fora do diff *depois* de já ter publicado os outros cinco, então cada retentativa republicou os cinco. Erro na publicação quase sempre significa posição inválida (ver 5.2), e a correção é a âncora, não repetir a chamada;
- listar rascunhos para "conferir" se a publicação funcionou — os rascunhos continuam visíveis por alguns segundos depois de publicados, e ler isso como falha foi o que gerou 3 cópias de cada comentário no MR !18709;
- publicar rascunho por rascunho com `gitlab_publish_draft_note`;
- reescrever os achados como notas gerais (`gitlab_create_merge_request_note`) porque a publicação "pareceu" não ter funcionado.

Se alguma ferramenta de publicação estiver indisponível, isso é intencional — **não improvise um caminho alternativo**.

**Important rules:**

- Findings go in draft notes (`gitlab_create_draft_note`), summary included, so they publish together as one review; individual notes (`gitlab_create_merge_request_note`) bypass the review workflow and are not used for findings.
- Include a severity label (🔴🟡🟢💡📚) in every draft note body.
- Extract diff_refs from the MR object: `diff_refs.base_sha`, `diff_refs.head_sha`, `diff_refs.start_sha`.

## Review Techniques

### Technique 1: The Checklist Method

Use checklists for consistent reviews. See [Security Review Guide](reference/security-review-guide.md) for comprehensive security checklist.

### Technique 2: The Question Approach

Instead of stating problems, ask questions:

```markdown
❌ "This will fail if the list is empty."
✅ "What happens if `items` is an empty array?"

❌ "You need error handling here."
✅ "How should this behave if the API call fails?"
```

### Technique 3: Suggest, Don't Command

Use collaborative language:

```markdown
❌ "You must change this to use async/await"
✅ "Suggestion: async/await might make this more readable. What do you think?"

❌ "Extract this into a function"
✅ "This logic appears in 3 places. Would it make sense to extract it?"
```

### Technique 4: Differentiate Severity

Use labels to indicate priority:

- 🔴 `[blocking]` - Must fix before merge
- 🟡 `[important]` - Should fix, discuss if disagree
- 🟢 `[nit]` - Nice to have, not blocking
- 💡 `[suggestion]` - Alternative approach to consider
- 📚 `[learning]` - Educational comment, no action needed
- 🎉 `[praise]` - Good work, keep it up!

## Language-Specific Guides

Consulte o guia específico para cada linguagem:

| Language/Framework | Reference File                              | Key Topics                                                           |
| ------------------ | ------------------------------------------- | -------------------------------------------------------------------- |
| **React**          | [React Guide](reference/react.md)           | Hooks, useEffect, React 19 Actions, RSC, Suspense, TanStack Query v5 |
| **Vue 3**          | [Vue Guide](reference/vue.md)               | Composition API, Reatividade, Props/Emits, Watchers, Composables      |
| **Rust**           | [Rust Guide](reference/rust.md)             | Propriedade/Empréstimo, Unsafe, Código Assíncrono, Tratamento de Erros|
| **TypeScript**     | [TypeScript Guide](reference/typescript.md) | Segurança de Tipos, async/await, Imutabilidade                        |
| **Python**         | [Python Guide](reference/python.md)         | Parâmetros Mutáveis, Tratamento de Exceções, Atributos de Classe      |
| **Java**           | [Java Guide](reference/java.md)             | Java 17/21, Spring Boot 3, Virtual Threads, Stream/Optional           |
| **Go**             | [Go Guide](reference/go.md)                 | Tratamento de Erros, goroutine/channel, context, Design de Interfaces |
| **C**              | [C Guide](reference/c.md)                   | Ponteiros/Buffer, Segurança de Memória, UB, Tratamento de Erros       |
| **C++**            | [C++ Guide](reference/cpp.md)               | RAII, Ciclo de Vida, Rule of 0/3/5, Segurança de Exceções             |
| **CSS/Less/Sass**  | [CSS Guide](reference/css-less-sass.md)     | Convenções de Variáveis, !important, Otimização, Responsivo, Compatib.|
| **Qt**             | [Qt Guide](reference/qt.md)                 | Modelo de Objetos, Sinais/Slots, Gerenciamento de Memória, Thread Safe|

## Additional Resources

- [Architecture Review Guide](reference/architecture-review-guide.md) — Guia de Revisão de Arquitetura (SOLID, Anti-Padrões, Acoplamento)
- [Performance Review Guide](reference/performance-review-guide.md) — Guia de Revisão de Performance (Web Vitals, N+1, Complexidade)
- [Common Bugs Checklist](reference/common-bugs-checklist.md) — Lista de Erros Comuns por Linguagem
- [Security Review Guide](reference/security-review-guide.md) — Guia de Revisão de Segurança
- [Code Review Best Practices](reference/code-review-best-practices.md) — Melhores Práticas de Revisão de Código
- [PR Review Template](assets/pr-review-template.md) — Modelo de Comentário de Revisão de PR
- [Review Checklist](assets/review-checklist.md) — Lista de Verificação Rápida
