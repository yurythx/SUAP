# Living Spec — MR Context Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich GitLab MRs with SUAP demanda context automatically, and persist approved spec deltas as `DecisaoEspecificacao` on merge.

**Architecture:** Two repos involved. `suap-mcp` gains a new `upsert_mr_suap_meta` tool that writes a `<!-- suap-meta -->` block into the MR description and the updated `demanda-workflow` prompt orchestrates the full enrichment flow. `suap` gains a CI script (`bin/scripts/update_demanda_spec.py`) that runs on every push to `master`, finds the merged MR, reads the approved spec-delta comment, and calls the existing `POST /api/demandas/{id}/spec-decisions/` endpoint. Phase 9 adds an optional fallback endpoint for MRs created without the agent.

**Tech Stack:** Python 3.12, httpx, FastMCP, Django Ninja, GitLab API v4, GitLab CI.

---

## Repos and working directories

- **suap-mcp:** `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`
- **suap:** `/Users/diegosaraiva/Workspace/ifrn/suap`

All `git` commands must be run from the correct repo root.

---

## File Map

### suap-mcp (Phase 7)

| File | Action | Responsibility |
|---|---|---|
| `src/suap_mcp/gitlab/client.py` | Modify | Add `get_merge_request` HTTP call |
| `src/suap_mcp/gitlab/models.py` | Modify | Add `UpsertMrSupaMetaInput` + `UpsertMrSupaMetaOutput` |
| `src/suap_mcp/gitlab/tools.py` | Modify | Add `upsert_mr_suap_meta` tool function |
| `src/suap_mcp/server.py` | Modify | Register new tool |
| `src/suap_mcp/modules/demandas/prompts.py` | Modify | Add MR enrichment steps to `demanda_workflow` |

### suap (Phase 8)

| File | Action | Responsibility |
|---|---|---|
| `demandas/models/decisao_especificacao.py` | Modify | Add `ORIGEM_AGENTE_CI = 'agente-ci'` choice |
| `demandas/migrations/0046_decisaoespecificacao_agente_ci.py` | Create | AlterField migration for new choice |
| `api/schemas/demandas.py` | Modify | Add `'agente-ci'` to validator |
| `bin/scripts/update_demanda_spec.py` | Create | CI script: find MR → extract approval → call SUAP |
| `.gitlab-ci.yml` | Modify | Add `post-merge` stage + `update-demanda-spec` job |

### suap (Phase 9, optional)

| File | Action | Responsibility |
|---|---|---|
| `api/schemas/demandas.py` | Modify | Add `ByMrResponseSchema` |
| `api/endpoints/demandas.py` | Modify | Add `GET /api/demandas/by-mr/` |

---

## Phase 7 — suap-mcp: upsert_mr_suap_meta tool

> Working directory: `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`

### Task 1: Add `get_merge_request` to GitLab client

**Files:**
- Modify: `src/suap_mcp/gitlab/client.py`

- [ ] **Step 1: Add `get_merge_request` after `get_merge_request_changes`**

Open `src/suap_mcp/gitlab/client.py` and add the following function immediately after `get_merge_request_changes` (around line 200):

```python
async def get_merge_request(
    base_url: str,
    token: str,
    project_path: str,
    mr_iid: int,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        result = await request_json(
            client,
            "GET",
            f"{_api_root(base_url)}/projects/{_encode_project(project_path)}/merge_requests/{mr_iid}",
            service=SERVICE,
            headers=gitlab_headers(token),
        )
    return result  # type: ignore[no-any-return]
```

- [ ] **Step 2: Verify import is not needed**

`httpx`, `request_json`, `_api_root`, `_encode_project`, `gitlab_headers`, `DEFAULT_TIMEOUT`, and `SERVICE` are already imported/defined in the file. No new imports needed.

- [ ] **Step 3: Verify the file compiles**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp && python -c "from suap_mcp.gitlab.client import get_merge_request; print('ok')"
```

Expected output: `ok`

---

### Task 2: Add Input/Output models

**Files:**
- Modify: `src/suap_mcp/gitlab/models.py`

- [ ] **Step 1: Add models at the end of `gitlab/models.py`**

Append the following to `src/suap_mcp/gitlab/models.py`:

```python
class UpsertMrSupaMetaInput(GitLabProjectInput):
    mr_iid: int = Field(description="Merge request IID (project-scoped number).")
    demanda_id: int = Field(description="SUAP demanda ID to link to this MR.")


class UpsertMrSupaMetaOutput(BaseModel):
    context: str
    mr_iid: int
    demanda_id: int
    updated: bool = Field(description="False when the block was already correct (idempotent).")
```

- [ ] **Step 2: Verify models parse**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp && python -c "
from suap_mcp.gitlab.models import UpsertMrSupaMetaInput, UpsertMrSupaMetaOutput
print(UpsertMrSupaMetaInput.model_fields.keys())
print('ok')
"
```

Expected output includes `context_url`, `project_path`, `mr_iid`, `demanda_id` and `ok`.

---

### Task 3: Add `upsert_mr_suap_meta` tool function

**Files:**
- Modify: `src/suap_mcp/gitlab/tools.py`

- [ ] **Step 1: Add imports at the top of `gitlab/tools.py`**

In `src/suap_mcp/gitlab/tools.py`, make three additions to the existing import block at the top:

```python
# 1. Add to the stdlib imports at the very top of the file:
import re as _re

# 2. In the "from suap_mcp.gitlab.client import (" block, add:
    get_merge_request,

# 3. In the "from suap_mcp.gitlab.models import (" block, add:
    UpsertMrSupaMetaInput,
    UpsertMrSupaMetaOutput,
```

- [ ] **Step 2: Add the pattern constant and tool function at the end of `gitlab/tools.py`**

```python
_SUAP_META_PATTERN = _re.compile(
    r"<!--\s*suap-meta\s*\ndemanda_id:\s*\d+\s*\n-->",
    _re.DOTALL,
)


async def upsert_mr_suap_meta(
    payload: UpsertMrSupaMetaInput,
) -> UpsertMrSupaMetaOutput:
    """Insert or replace the <!-- suap-meta --> block in a GitLab MR description.

    Use when:
      - Opening or working on a MR linked to a SUAP demanda.
      - You need the CI pipeline to know which demanda this MR belongs to.

    Do not use when:
      - The MR is not linked to a SUAP demanda.

    Side effects:
      Updates MR description in GitLab. Idempotent: re-running with the same
      demanda_id produces no change.
    """
    context_url = str(payload.context_url)
    name, ctx = resolve_context(context_url)
    token = await async_keychain_get(ctx.gitlab.token_keychain)

    mr = await get_merge_request(
        ctx.gitlab.base_url, token, payload.project_path, payload.mr_iid
    )
    current_description = mr.get("description") or ""

    meta_block = (
        f"<!-- suap-meta\n"
        f"demanda_id: {payload.demanda_id}\n"
        f"-->"
    )

    if _SUAP_META_PATTERN.search(current_description):
        new_description = _SUAP_META_PATTERN.sub(meta_block, current_description)
    else:
        new_description = (
            meta_block + "\n\n" + current_description
            if current_description
            else meta_block
        )

    if new_description == current_description:
        _logger.info(
            "upsert_mr_suap_meta_noop",
            context=name,
            mr_iid=payload.mr_iid,
            demanda_id=payload.demanda_id,
        )
        return UpsertMrSupaMetaOutput(
            context=name,
            mr_iid=payload.mr_iid,
            demanda_id=payload.demanda_id,
            updated=False,
        )

    await update_merge_request(
        ctx.gitlab.base_url,
        token,
        payload.project_path,
        payload.mr_iid,
        {"description": new_description},
    )

    _logger.info(
        "upsert_mr_suap_meta",
        context=name,
        mr_iid=payload.mr_iid,
        demanda_id=payload.demanda_id,
    )
    return UpsertMrSupaMetaOutput(
        context=name,
        mr_iid=payload.mr_iid,
        demanda_id=payload.demanda_id,
        updated=True,
    )
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp && python -c "from suap_mcp.gitlab.tools import upsert_mr_suap_meta; print('ok')"
```

Expected output: `ok`

---

### Task 4: Register tool in server.py

**Files:**
- Modify: `src/suap_mcp/server.py`

- [ ] **Step 1: Add import in `server.py`**

In `src/suap_mcp/server.py`, find the existing import block for gitlab tools and add `upsert_mr_suap_meta`:

```python
# Find the existing import that looks like:
from suap_mcp.gitlab.tools import (
    ...
)
# Add upsert_mr_suap_meta to it
```

- [ ] **Step 2: Register the tool**

In `build_server()`, after the last GitLab `mcp.tool(...)` call, add:

```python
    mcp.tool(
        upsert_mr_suap_meta,
        annotations={"readOnlyHint": False, "idempotentHint": True, "destructiveHint": False, "openWorldHint": True},
    )
```

- [ ] **Step 3: Verify server builds**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp && python -c "from suap_mcp.server import build_server; s = build_server(); print('ok')"
```

Expected output: `ok`

---

### Task 5: Update `demanda-workflow` prompt

**Files:**
- Modify: `src/suap_mcp/modules/demandas/prompts.py`

- [ ] **Step 1: Add MR enrichment block to the prompt**

In `src/suap_mcp/modules/demandas/prompts.py`, replace the `demanda_workflow` function body with the version below. The only change is adding steps 5–9 (MR enrichment) and updating the Constraints and Expected output sections:

```python
from __future__ import annotations


def demanda_workflow(
    demanda_id: int,
    suap_url: str,
) -> str:
    """Build a structured prompt for starting a work session on a SUAP demanda."""

    return f"""Inicie uma sessão de trabalho na demanda {demanda_id} do SUAP.

SUAP URL: {suap_url}
Demanda ID: {demanda_id}

Workflow:
1. Chame get_demanda_context com suap_url="{suap_url}" e demanda_id={demanda_id}.
   Leia com atenção: especificacao_tecnica, dod, decisoes_especificacao e subdemandas.
2. Chame get_demanda_mr_status para verificar se já há um MR aberto.
   - Se id_merge_request for null e houver branch definida, o MR ainda não foi aberto.
   - Se id_merge_request estiver preenchido, o MR já existe — use a mr_url para referência.
3. Se o trabalho exigir abrir um MR e ele ainda não existir:
   - Confirme com o usuário antes de chamar open_mr_for_demanda.
   - Chame open_mr_for_demanda com confirm=True apenas após confirmação explícita.
4. Ao longo da implementação, registre decisões arquiteturais relevantes:
   - Use append_spec_decision com confirm=False primeiro para revisar o payload.
   - Chame com confirm=True após o usuário confirmar o texto da decisão.
   - Inclua no campo contexto: arquivos afetados, alternativas consideradas, trade-offs.

Enriquecimento do MR (execute quando um MR estiver aberto para esta demanda):
5. Chame get_gitlab_mr_diff com o mr_iid e project_path do MR da demanda.
6. Compare o diff com a especificacao_tecnica e decisoes_especificacao atuais:
   - Identifique mudanças de regra de negócio (novas validações, fluxos alterados,
     permissões modificadas, campos novos com significado de domínio).
   - Ignore mudanças puramente técnicas (refactoring, renaming, formatação).
7. Se houver mudanças de regra de negócio:
   a. Chame upsert_mr_suap_meta com mr_iid, project_path e demanda_id={demanda_id}
      para garantir que o bloco <!-- suap-meta --> está na descrição do MR.
   b. Monte o comment de proposta de spec no seguinte formato e chame
      post_gitlab_mr_comment com confirm=True:

      ## 🤖 Proposta de Spec — Demanda #{demanda_id}
      ### Resumo das mudanças
      [resumo objetivo do que mudou nas regras de negócio, máx. 5 linhas]
      ### Delta proposto
      [texto conciso a adicionar na especificação técnica — escreva como doc, não como diff]
      Para aprovar: 👍 neste comment
      Para editar: responda com sua versão corrigida
      Para ignorar: 🚫 neste comment
      <!-- spec-delta: {{"demanda_id": {demanda_id}, "status": "proposed"}} -->

8. Se não houver mudanças de regra de negócio, informe o usuário e não poste o comment.

Constraints:
- Nunca abra um MR sem confirmação explícita do usuário.
- Nunca registre uma decisão sem o usuário revisar o texto antes.
- Nunca poste o comment de spec delta sem mostrar o conteúdo ao usuário primeiro.
- Se get_demanda_context retornar erro permission_denied, informe o usuário e pare.
- Se a demanda não tiver branch definida, não tente abrir o MR — informe o usuário.
- O comment de spec delta deve ser postado com confirm=True pois é visível no GitLab.

Expected output:
- Resumo da demanda: título, situação, especificação técnica.
- Status do MR (aberto / não aberto / branch ausente).
- Lista das sub-demandas com situação e percentual de conclusão.
- Decisões arquiteturais registradas até o momento.
- Se MR aberto: confirmação de que suap-meta e spec-delta comment foram postados,
  ou informação de que não havia mudanças de regra de negócio neste MR.
- Próximos passos sugeridos com base no contexto.
"""
```

- [ ] **Step 2: Verify prompt renders**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp && python -c "
from suap_mcp.modules.demandas.prompts import demanda_workflow
p = demanda_workflow(123, 'https://suap.ifrn.edu.br')
assert 'upsert_mr_suap_meta' in p
assert 'spec-delta' in p
print('ok')
"
```

Expected output: `ok`

---

### Task 6: Commit Phase 7

- [ ] **Step 1: Commit suap-mcp changes**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add src/suap_mcp/gitlab/client.py \
        src/suap_mcp/gitlab/models.py \
        src/suap_mcp/gitlab/tools.py \
        src/suap_mcp/server.py \
        src/suap_mcp/modules/demandas/prompts.py
git commit -m "feat: add upsert_mr_suap_meta tool and MR enrichment steps in demanda-workflow"
```

---

## Phase 8 — suap: ORIGEM_AGENTE_CI + CI script

> Working directory: `/Users/diegosaraiva/Workspace/ifrn/suap`

### Task 7: Add `ORIGEM_AGENTE_CI` to DecisaoEspecificacao

**Files:**
- Modify: `demandas/models/decisao_especificacao.py`
- Create: `demandas/migrations/0046_decisaoespecificacao_agente_ci.py`

- [ ] **Step 1: Add the new choice to the model**

In `demandas/models/decisao_especificacao.py`, update `ORIGEM_CHOICES`:

```python
class DecisaoEspecificacao(ModelPlus):
    ORIGEM_MANUAL = 'manual'
    ORIGEM_AGENTE = 'agente'
    ORIGEM_AGENTE_CI = 'agente-ci'
    ORIGEM_CHOICES = (
        (ORIGEM_MANUAL, 'Manual'),
        (ORIGEM_AGENTE, 'Agente'),
        (ORIGEM_AGENTE_CI, 'Agente CI'),
    )
```

Leave all other fields unchanged.

- [ ] **Step 2: Create the migration**

Create `demandas/migrations/0046_decisaoespecificacao_agente_ci.py`:

```python
import djtools.db.models.fields.string
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('demandas', '0045_remove_ambientehomologacao_usuarios_alter_demanda_id_merge_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='decisaoespecificacao',
            name='origem',
            field=djtools.db.models.fields.string.CharFieldPlus(
                choices=[('manual', 'Manual'), ('agente', 'Agente'), ('agente-ci', 'Agente CI')],
                default='manual',
                max_length=10,
                verbose_name='Origem',
            ),
        ),
    ]
```

- [ ] **Step 3: Run migration check**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python manage.py migrate --check
```

Expected: exit 0 (migrations not yet applied, but no errors). Then apply:

```bash
python manage.py migrate demandas 0046
```

Expected: `Applying demandas.0046_decisaoespecificacao_agente_ci... OK`

---

### Task 8: Update `SpecDecisionInputSchema` validator

**Files:**
- Modify: `api/schemas/demandas.py`

- [ ] **Step 1: Update the `origem_valida` validator to accept `'agente-ci'`**

In `api/schemas/demandas.py`, the validator at line ≈168 currently uses `DecisaoEspecificacao.ORIGEM_CHOICES`. Since the model now includes `'agente-ci'`, the validator picks it up automatically — **no code change needed** as long as the model import is live.

Verify this by running:

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python -c "
from api.schemas.demandas import SpecDecisionInputSchema
s = SpecDecisionInputSchema(decisao='test', origem='agente-ci')
print(s.origem)
"
```

Expected output: `agente-ci`

If the validator raises a `ValueError`, it means the import is stale. In that case, add `'agente-ci'` explicitly to the choices list in `SpecDecisionInputSchema.origem_valida`.

---

### Task 9: Create CI script

**Files:**
- Create: `bin/scripts/update_demanda_spec.py`

- [ ] **Step 1: Create the `scripts/` directory and the script**

```bash
mkdir -p /Users/diegosaraiva/Workspace/ifrn/suap/scripts
```

Create `bin/scripts/update_demanda_spec.py`:

```python
#!/usr/bin/env python3
"""CI script: on merge to master, reads the approved spec-delta comment from
the merged MR and creates a DecisaoEspecificacao in SUAP.

Required env vars:
  GITLAB_TOKEN   - GitLab token (use CI_JOB_TOKEN in CI)
  SUAP_TOKEN     - SUAP service account JWT
  CI_COMMIT_SHA  - provided by GitLab CI
  CI_PROJECT_ID  - provided by GitLab CI
  GITLAB_BASE_URL - default: https://gitlab.ifrn.edu.br
  SUAP_BASE_URL   - default: https://suap.ifrn.edu.br
"""
from __future__ import annotations

import os
import re
import sys

import httpx

GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
SUAP_TOKEN = os.environ["SUAP_TOKEN"]
COMMIT_SHA = os.environ["CI_COMMIT_SHA"]
PROJECT_ID = os.environ["CI_PROJECT_ID"]
GITLAB_BASE = os.environ.get("GITLAB_BASE_URL", "https://gitlab.ifrn.edu.br")
SUAP_BASE = os.environ.get("SUAP_BASE_URL", "https://suap.ifrn.edu.br")

_GITLAB_HEADERS = {"PRIVATE-TOKEN": GITLAB_TOKEN}
_SUAP_HEADERS = {"Authorization": f"Bearer {SUAP_TOKEN}"}
_API = f"{GITLAB_BASE}/api/v4"

_META_RE = re.compile(r"<!--\s*suap-meta\s*\ndemanda_id:\s*(\d+)\s*\n-->")
_BRANCH_RE = re.compile(r"demanda-(\d+)")
_DELTA_MARKER = "<!-- spec-delta:"
_DELTA_CONTENT_RE = re.compile(r"### Delta proposto\n(.+?)(?=\n##|\n<!--|$)", re.DOTALL)


def _gitlab_get(path: str, **kwargs) -> list | dict:
    r = httpx.get(f"{_API}{path}", headers=_GITLAB_HEADERS, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _find_merged_mr() -> dict | None:
    mrs = _gitlab_get(
        f"/projects/{PROJECT_ID}/repository/commits/{COMMIT_SHA}/merge_requests"
    )
    merged = [m for m in mrs if m.get("state") == "merged"]
    return merged[0] if merged else None


def _extract_demanda_id(mr: dict) -> int | None:
    description = mr.get("description") or ""
    m = _META_RE.search(description)
    if m:
        return int(m.group(1))
    branch = mr.get("source_branch", "")
    m = _BRANCH_RE.search(branch)
    if m:
        return int(m.group(1))
    return None


def _find_spec_delta_note(mr_iid: int) -> dict | None:
    notes = _gitlab_get(
        f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes",
        params={"per_page": 100, "sort": "asc"},
    )
    for note in notes:
        if _DELTA_MARKER in note.get("body", ""):
            return note
    return None


def _get_approved_content(mr_iid: int, note: dict) -> str | None:
    note_id = note["id"]
    note_body = note["body"]

    # Check for explicit rejection (🚫)
    reactions = _gitlab_get(
        f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes/{note_id}/award_emoji"
    )
    emoji_names = {r["name"] for r in reactions}
    if "no_entry_sign" in emoji_names:
        print(f"[skip] 🚫 reaction on spec-delta comment — explicitly rejected")
        return None

    # Check for thumbsup (👍) reaction → use comment content
    if "thumbsup" in emoji_names:
        m = _DELTA_CONTENT_RE.search(note_body)
        return m.group(1).strip() if m else note_body.strip()

    # Check for dev reply in the same discussion thread
    discussions = _gitlab_get(
        f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/discussions"
    )
    for discussion in discussions:
        notes_in = discussion.get("notes", [])
        note_ids = [n["id"] for n in notes_in]
        if note_id in note_ids:
            replies = [n for n in notes_in if n["id"] != note_id]
            if replies:
                return replies[-1]["body"].strip()

    return None  # No approval signal


def _post_mr_comment(mr_iid: int, body: str) -> None:
    httpx.post(
        f"{_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes",
        headers=_GITLAB_HEADERS,
        json={"body": body},
        timeout=30,
    )


def _apply_spec_delta(demanda_id: int, decisao: str, mr_iid: int) -> None:
    r = httpx.post(
        f"{SUAP_BASE}/api/demandas/{demanda_id}/spec-decisions/",
        headers=_SUAP_HEADERS,
        json={
            "decisao": decisao,
            "origem": "agente-ci",
            "contexto": {"mr_iid": mr_iid, "commit_sha": COMMIT_SHA},
        },
        timeout=30,
    )
    if r.status_code == 404:
        print(f"[warn] Demanda {demanda_id} not found in SUAP — skipping")
        sys.exit(0)
    if r.status_code == 403:
        print(f"[warn] SUAP token lacks permission for demanda {demanda_id} — skipping")
        sys.exit(0)
    r.raise_for_status()
    print(f"[ok] DecisaoEspecificacao created for demanda {demanda_id} (MR !{mr_iid})")


def main() -> None:
    mr = _find_merged_mr()
    if not mr:
        print("[skip] No merged MR found for this commit")
        sys.exit(0)

    mr_iid = mr["iid"]
    demanda_id = _extract_demanda_id(mr)
    if demanda_id is None:
        print(f"[warn] No demanda_id in MR !{mr_iid} (no suap-meta block, no demanda-N branch)")
        sys.exit(0)

    note = _find_spec_delta_note(mr_iid)
    if not note:
        print(f"[skip] No spec-delta comment found in MR !{mr_iid}")
        sys.exit(0)

    approved = _get_approved_content(mr_iid, note)
    if approved is None:
        _post_mr_comment(
            mr_iid,
            "⚠️ **Spec delta não aplicado** — nenhum sinal de aprovação encontrado.\n"
            "Adicione 👍 ao comment de proposta ou responda com a versão corrigida "
            "para que a spec seja atualizada automaticamente no próximo push.",
        )
        print(f"[warn] No approval signal on spec-delta comment in MR !{mr_iid}")
        sys.exit(0)

    _apply_spec_delta(demanda_id, approved, mr_iid)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python -m py_compile bin/scripts/update_demanda_spec.py && echo "ok"
```

Expected output: `ok`

---

### Task 10: Add CI job to `.gitlab-ci.yml`

**Files:**
- Modify: `.gitlab-ci.yml`

- [ ] **Step 1: Add `post-merge` to the stages list**

In `.gitlab-ci.yml`, find the `stages:` block (line 15) and add `post-merge` after `deploy`:

```yaml
stages:
  - ai-review
  - quality-assurance
  - test
  - coverage
  - development
  - homologate
  - build
  - deploy
  - post-merge      # ← add this line
  - containers
  - special-tasks
```

- [ ] **Step 2: Add the `update-demanda-spec` job**

Append the following job to `.gitlab-ci.yml` (at the end of the file, before or after `special-tasks` jobs):

```yaml
update-demanda-spec:
  stage: post-merge
  tags:
    - tests-v3
  rules:
    - if: '$CI_COMMIT_BRANCH == "master" && $CI_PIPELINE_SOURCE == "push"'
  before_script:
    - pip install httpx --quiet
  variables:
    GITLAB_TOKEN: $CI_JOB_TOKEN
    SUAP_TOKEN: $SUAP_CI_TOKEN
    SUAP_BASE_URL: "https://suap.ifrn.edu.br"
    GITLAB_BASE_URL: "https://gitlab.ifrn.edu.br"
  script:
    - python bin/scripts/update_demanda_spec.py
  allow_failure: true
```

> **Note:** `SUAP_CI_TOKEN` must be configured as a protected CI variable in GitLab (Settings → CI/CD → Variables) with the JWT of a SUAP service account that has `atende_demanda` permission. This is a one-time ops task, not a code change.

- [ ] **Step 3: Validate YAML syntax**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('ok')"
```

Expected output: `ok`

---

### Task 11: Commit Phase 8

- [ ] **Step 1: Commit suap changes**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
git add demandas/models/decisao_especificacao.py \
        demandas/migrations/0046_decisaoespecificacao_agente_ci.py \
        api/schemas/demandas.py \
        bin/scripts/update_demanda_spec.py \
        .gitlab-ci.yml
git commit -m "feat: add agente-ci origem, CI script and update-demanda-spec job for living spec"
```

---

## Phase 9 — suap: fallback endpoint `GET /api/demandas/by-mr/` (optional)

> Skip this phase if MRs will always be created via `open_mr_for_demanda` (suap-meta block always present). Implement if you need to support MRs created manually without the agent.

> Working directory: `/Users/diegosaraiva/Workspace/ifrn/suap`

### Task 12: Add `ByMrResponseSchema`

**Files:**
- Modify: `api/schemas/demandas.py`

- [ ] **Step 1: Append schema at the end of `api/schemas/demandas.py`**

```python
class ByMrResponseSchema(Schema):
    id: int
    titulo: str
    branch: str | None
    id_merge_request: int | None
    situacao: str
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python -c "from api.schemas.demandas import ByMrResponseSchema; print('ok')"
```

Expected output: `ok`

---

### Task 13: Add `GET /api/demandas/by-mr/` endpoint

**Files:**
- Modify: `api/endpoints/demandas.py`

- [ ] **Step 1: Add import for `ByMrResponseSchema`**

In `api/endpoints/demandas.py`, add `ByMrResponseSchema` to the existing import from `api.schemas.demandas`:

```python
from api.schemas.demandas import (
    AgentContextSchema,
    ByMrResponseSchema,   # ← add
    ErrorSchema,
    MRStatusSchema,
    OpenMRResponseSchema,
    SpecDecisionInputSchema,
    SpecDecisionResponseSchema,
    SubdemandaSchema,
)
```

- [ ] **Step 2: Add the endpoint at the end of `api/endpoints/demandas.py`**

```python
@get(
    router,
    'by-mr/',
    response={200: ByMrResponseSchema, 403: ErrorSchema, 404: ErrorSchema},
    auth=JWTAuth(),
    summary='Demanda vinculada a um MR',
    description='Retorna a demanda cujo id_merge_request corresponde ao mr_iid informado.',
)
def demanda_by_mr(request, mr_iid: int):
    try:
        demanda = Demanda.objects.get(id_merge_request=mr_iid)
    except Demanda.DoesNotExist:
        return 404, {
            'error': 'demanda_not_found',
            'hint': f'Nenhuma demanda vinculada ao MR !{mr_iid}',
            'context': {'mr_iid': mr_iid},
        }
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'mr_iid': mr_iid}}
    return 200, demanda
```

- [ ] **Step 3: Verify endpoint registers**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap && python manage.py show_urls 2>/dev/null | grep "by-mr" || python -c "from api.endpoints.demandas import router; print([r.path for r in router._routers if hasattr(r,'path')]); print('ok')"
```

Expected: the `by-mr/` path appears in the output.

---

### Task 14: Commit Phase 9

- [ ] **Step 1: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
git add api/schemas/demandas.py api/endpoints/demandas.py
git commit -m "feat: add GET /api/demandas/by-mr/ fallback endpoint"
```

---

## Post-implementation ops checklist

These are one-time configuration steps, not code changes:

- [ ] Create `SUAP_CI_TOKEN` as a protected CI variable in GitLab (Settings → CI/CD → Variables) with the JWT of a SUAP service account that has `atende_demanda` permission.
- [ ] Verify the GitLab runner tagged `tests-v3` has Python 3.12+ available (`python --version`).
- [ ] Run one test MR end-to-end: open MR via agent → verify suap-meta block in description → post spec-delta comment → react with 👍 → merge → check SUAP for new `DecisaoEspecificacao`.
