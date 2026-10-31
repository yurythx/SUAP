---
name: sentry-fix
description: >
  Given a Sentry issue URL, automatically: fetches issue details, analyzes the error,
  creates a fix branch, writes the code fix, runs pre-commit, commits, pushes, and
  opens a GitLab MR. References the Sentry issue ID in the commit message and MR
  description. Does NOT write tests — test coverage is added separately on the resulting MR.
  Trigger: /sentry-fix <url>, "fix this sentry error", "corrige esse erro do sentry".
trigger: /sentry-fix
---

Fix Sentry errors end-to-end. One URL in, one MR out. **Code fix only — no tests.**

## Ferramentas e fallback

Os nomes `sentry_get_sentry_resource` e `gitlab_create_merge_request` são nomes lógicos
do catálogo compartilhado, não universais. Use a ferramenta Sentry/GitLab equivalente
que o cliente disponibilizar. Para GitLab, `glab mr create` é o fallback autenticado.
Se não houver conector Sentry nem API/CLI autenticada disponível, pare antes de criar a
branch e informe a dependência; não invente dados do incidente nem leia credenciais locais.

## Process

The branch must exist before the first edit, and pre-commit must pass before the push; the rest is the usual order, not a script.

### Step 1 - Fetch Sentry issue details

Use `sentry_get_sentry_resource` with the full URL the user provided. Extract:

- **Issue ID** (e.g. `SUAP-PJ9`) from the response
- **Culprit** (file + function, e.g. `rh.importador_ws in _call_service_siape`)
- **Stacktrace** (the most relevant frame — file, line number, local variables)
- **Error message** (the exception message)
- **Tags** (environment, release, logger)

### Step 2 - Analyze the error

Find the root cause from the stacktrace, the local variables and the code around the failing
frame — a fix at the symptom leaves the other callers of the same function broken.

### Step 3 - Create fix branch

```bash
git checkout master && git pull origin master
git checkout -b fix/sentry-<ISSUE_ID>-<short-description>
```

- `<ISSUE_ID>`: the Sentry short ID (e.g. `SUAP-PJ9`)
- `<short-description>`: 2-4 kebab-case words describing the fix (e.g. `empty-status-codes`)

### Step 4 - Write the fix

Edit the source file to resolve the root cause. Follow existing code conventions:

- Mimic the code style of surrounding lines
- Use existing libraries and patterns from the codebase
- Do NOT add comments unless asked
- Keep the fix minimal and targeted — fix the root cause, nothing else
- Do NOT add or modify any test files. Test coverage is added separately on the resulting MR.

### Step 5 - Sanity-check existing tests still pass

Run the existing test suite for the touched app to confirm the fix did not break anything:

```bash
source .venv/bin/activate && pytest -q <app>/
```

If anything fails:

1. Diagnose: is it the fix, or a pre-existing flake?
2. If the fix caused it, revise the fix and re-run.
3. Do NOT add new tests or modify existing tests to make them pass.

### Step 6 - Commit

Pre-commit checks run automatically via the OpenCode/Codex adapter on `git commit`.
No Claude Code, run the sequence documented by the `pre-commit` skill manually.

```bash
git add -A
git commit -m "<type>(<scope>): <imperative summary>

<body explaining why, if not obvious>

Refs: <ISSUE_ID>"
```

Commit message guidelines:

- **type**: `fix` for bug fixes, `feat` for new features
- **scope**: the app or module (e.g. `rh`, `comum`)
- **subject**: imperative, ≤50 chars
- **body**: explain the _why_, reference the Sentry issue ID

Example:

```
fix(rh): tratar fault codes 0030 e 0002 como dados vazios no SIAPENET

Os códigos 0030 e 0002 ambos indicam ausência de dados.
Apenas o 0030 era tratado, fazendo o 0002 gerar exceções.

Refs: SUAP-PJ9
```

### Step 7 - Push and create MR (SUAP format)

```bash
git push -u origin <branch-name>
```

Then create the MR using `gitlab_create_merge_request`. Include in the MR description:

- The URL of the Sentry issue
- A summary of the fix
- A note: *"Cobertura de testes será adicionada em commit separado."*

After creating the MR, return to master branch:

```bash
git checkout master
```

### Step 8 - Report

After the MR is created, report to the user:

```
Fix applied. MR: <MR URL>
Test coverage still pending (separate commit).
```

## Quick Reference

| Step | Action          | Command/Tool                                       |
| ---- | --------------- | -------------------------------------------------- |
| 1    | Fetch issue     | `sentry_get_sentry_resource`                       |
| 2    | Analyze         | Read source, understand root cause                 |
| 3    | Branch          | `git checkout -b fix/sentry-<ID>-<desc>`           |
| 4    | Fix code        | Edit source file only — NO test changes            |
| 5    | Sanity check    | `pytest -q <app>/` (existing tests still pass)     |
| 6    | Commit          | `git add -A && git commit` (pre-commit via plugin) |
| 7    | MR              | Push + `gitlab_create_merge_request`               |
| 7b   | Cleanup         | `git checkout master`                              |
| 8    | Report          | MR URL + note that test coverage is pending        |

## Boundaries

- Does NOT resolve the Sentry issue automatically. Only references it.
- Does NOT push to master directly. Always uses a branch + MR.
- Does NOT skip pre-commit. Mandatory gate.
- Does NOT modify files unrelated to the fix. Keep the diff minimal.
- **Does NOT write, modify, or extend any test files.** Test coverage is added separately on the resulting MR.
- If the fix is ambiguous or complex, stop and ask the user for clarification before proceeding.
