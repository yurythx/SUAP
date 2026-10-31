# Tools MCP + skill do Claude (fase PR) — Lançamento de execuções do PGD via GitLab (Plano 2 de 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) ou superpowers:executing-plans. Os steps usam checkbox (`- [ ]`). **Depende do Plano 1** (endpoints `entregas-disponiveis` e `lancar-rit` no SUAP) estar implantado.

**Goal:** Na criação do PR, o Claude lê a issue + diff do MR, infere a entrega do PGD casando o conteúdo contra a Entrega PES de cada categoria, estima horas, mostra um resumo, o servidor confirma, e grava **uma RIT por MR** (em `EM_CADASTRO_RIT`) no SUAP — via duas tools MCP novas.

**Architecture (do spec):** SUAP é a fonte da verdade (Plano 1). Este plano entrega **(A) as tools MCP** que conversam com os endpoints do Plano 1, e **(B) a skill** que orquestra inferência/estimativa/confirmação. A skill é determinística no fluxo (passos em ordem) e não-determinística só na inferência/estimativa — que o servidor confirma antes de gravar.

**Dois repositórios:**
- `suap-mcp` (`/Users/diegosaraiva/Workspace/ifrn/suap-mcp`) — Fase A (tools MCP, Python, TDD com `respx`).
- `suap` (este repo) — Fase B (skill em `.agents/skills/` + symlink em `.claude/skills/`).

**Spec:** `docs/specs/2026-05-29-pgd-execucao-gitlab-design.md`
**Plano 1:** `docs/plans/2026-05-29-pgd-execucao-gitlab-backend.md`

---

## Contrato com o Plano 1 (o que as tools consomem)

- `GET /api/pgd2/execucao-gitlab/entregas-disponiveis/?gitlab_username=<u>` → `{ entregas: [{ id, titulo, descricao, pit_id, pes_titulo, pes_descricao, pes_criterios_avaliacao, metrica, meta, periodo_titulo, pit_data_inicio, pit_data_fim, eh_periodo_corrente }] }`
- `POST /api/pgd2/execucao-gitlab/lancar-rit/` body `{ gitlab_username, gitlab_project_id, gitlab_mr_iid, entrega_pit_id, titulo, descricao, tempo_executado, perc_executada_em_teletrabalho, data_inicio, data_fim, quantidade_progresso }` → `{ rit_id, entrega_pit_id, gitlab_mr_iid, criado }`
- Auth: `TrustedAppAuth` (OAuth2 Bearer) — o token SUAP do MCP (`ctx.suap.token_keychain`) já satisfaz (mesmo esquema do módulo `demandas`).

---

## Padrão do `suap-mcp` a espelhar (referências reais)

- Módulo por domínio: `src/suap_mcp/modules/demandas/{client.py, models.py, tools.py, schemas.py, errors.py}`.
- Tool async: recebe `payload: <X>Input` (Pydantic), retorna `<X>Output`; resolve contexto com `resolve_context(str(payload.context_url))` (`contexts.py:33`), token com `await async_keychain_get(ctx.suap.token_keychain)` (`keychain.py:83`).
- HTTP SUAP: `suap_headers(token)` = `{"Authorization": f"Bearer {token}"}` (`modules/demandas/client.py:15`); `_api_root(base_url)` = `{base_url}/api`; requests via `request_json(...)` (`http.py:63`) com retries; erros 4xx → `DemandaError`/erro tratado, 5xx → `UpstreamHTTPError`.
- Registro: `from ... import <tool>` + `mcp.tool(<tool>, annotations={...})` em `server.py` (linhas 6-138).
- Testes: `pytest` + `respx`, fixtures `fake_contexts_yaml` e `env_secrets` (`tests/conftest.py`), exemplos em `tests/test_gitlab_tools.py:45`.
- Tools de leitura GitLab já disponíveis (para a skill): `get_gitlab_mr_diff` (diff + metadados), `list_gitlab_merge_requests`, `compare_gitlab_refs`. Cliente de baixo nível: `get_merge_request` (`gitlab/client.py:203`).

---

# Fase A — Tools MCP (repo `suap-mcp`)

> Todos os comandos desta fase rodam em `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`. Crie um branch: `git checkout -b feat/pgd2-lancar-rit`.

### Task A1: Módulo `modules/pgd2/` (client + models + errors)

**Files (criar):**
- `src/suap_mcp/modules/pgd2/__init__.py`
- `src/suap_mcp/modules/pgd2/errors.py`
- `src/suap_mcp/modules/pgd2/models.py`
- `src/suap_mcp/modules/pgd2/client.py`
- `tests/test_pgd2_tools.py`

- [ ] **Step 1: Espelhar `errors.py` do módulo demandas**

Copie o padrão de `modules/demandas/errors.py` para `modules/pgd2/errors.py` (ex.: classe `Pgd2Error(Exception)` com `status_code` e `message`, para mapear 4xx do SUAP em mensagem amigável ao agente). Confirme o nome/forma reais no arquivo de demandas antes.

- [ ] **Step 2: Models Pydantic (`modules/pgd2/models.py`)**

```python
from pydantic import BaseModel, Field, HttpUrl


class EntregasDisponiveisInput(BaseModel):
    context_url: HttpUrl = Field(description="Any URL on the target SUAP host; used to resolve the context.")
    gitlab_username: str = Field(description="GitLab username of the MR author (maps to the servidor).")


class EntregaDisponivel(BaseModel):
    id: int
    titulo: str
    descricao: str | None = None
    pit_id: int
    pes_titulo: str | None = None
    pes_descricao: str | None = None
    pes_criterios_avaliacao: str | None = None
    metrica: int | None = None
    meta: float | None = None
    periodo_titulo: str
    pit_data_inicio: str | None = None
    pit_data_fim: str | None = None
    eh_periodo_corrente: bool = False


class EntregasDisponiveisOutput(BaseModel):
    context: str
    gitlab_username: str
    entregas: list[EntregaDisponivel]


class LancarRitInput(BaseModel):
    context_url: HttpUrl = Field(description="Any URL on the target SUAP host; used to resolve the context.")
    gitlab_username: str
    gitlab_project_id: int = Field(description="Numeric GitLab project id (stable across renames).")
    gitlab_mr_iid: int
    entrega_pit_id: int
    titulo: str
    descricao: str
    tempo_executado: float = Field(description="Estimated hours for this MR.")
    perc_executada_em_teletrabalho: float = 0
    data_inicio: str | None = None  # ISO date
    data_fim: str | None = None
    quantidade_progresso: float = 1  # 1 por MR (um MR = um trabalho)
    confirm: bool = Field(default=False, description="If False, returns a dry-run preview without writing.")


class LancarRitOutput(BaseModel):
    context: str
    gitlab_mr_iid: int
    entrega_pit_id: int
    rit_id: int | None = None
    criado: bool | None = None
    dry_run: bool = False
```

> Ajuste tipos `float`→`Decimal` se o módulo demandas usar `Decimal` em valores monetários/horas; siga o padrão local.

- [ ] **Step 3: Client HTTP (`modules/pgd2/client.py`)**

Espelhe `modules/demandas/client.py` (mesmo `suap_headers`, `_api_root`, tratamento de erro):

```python
from typing import Any

import httpx

from suap_mcp.http import DEFAULT_TIMEOUT, request_json

SERVICE = "suap"


def _api_root(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api"


def suap_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def get_entregas_disponiveis(base_url: str, token: str, gitlab_username: str) -> Any:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        return await request_json(
            client,
            "GET",
            f"{_api_root(base_url)}/pgd2/execucao-gitlab/entregas-disponiveis/",
            service=SERVICE,
            headers=suap_headers(token),
            params={"gitlab_username": gitlab_username},
        )


async def lancar_rit(base_url: str, token: str, payload: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        return await request_json(
            client,
            "POST",
            f"{_api_root(base_url)}/pgd2/execucao-gitlab/lancar-rit/",
            service=SERVICE,
            headers=suap_headers(token),
            json=payload,
        )
```

> Confirme em `modules/demandas/client.py` se o helper de POST trata 4xx convertendo para erro de domínio (ex.: 403 entrega de outro servidor, 404 username não mapeado). Replique esse tratamento para `lancar_rit`/`get_entregas_disponiveis`.

- [ ] **Step 4: Commit**

```bash
git add src/suap_mcp/modules/pgd2/
git commit -m "feat(pgd2): módulo MCP (client + models) para execução via GitLab"
```

---

### Task A2: Tool `get_entregas_disponiveis_pgd2` (read)

**Files:**
- Create: `src/suap_mcp/modules/pgd2/tools.py`
- Modify: `src/suap_mcp/server.py`
- Test: `tests/test_pgd2_tools.py`

- [ ] **Step 1: Write the failing test**

Em `tests/test_pgd2_tools.py` (espelhe `tests/test_gitlab_tools.py:45`):

```python
import pytest
import respx
from httpx import Response

from suap_mcp.modules.pgd2.models import EntregasDisponiveisInput
from suap_mcp.modules.pgd2.tools import get_entregas_disponiveis_pgd2


@pytest.mark.asyncio
@respx.mock
async def test_entregas_disponiveis_ok(fake_contexts_yaml, env_secrets):
    route = respx.get(
        "https://suap.ifrn.edu.br/api/pgd2/execucao-gitlab/entregas-disponiveis/"
    ).mock(return_value=Response(200, json={"entregas": [
        {"id": 10, "titulo": "Atendimento de erros e chamados", "descricao": "", "pit_id": 5,
         "pes_titulo": "Atendimento de erros e chamados", "pes_descricao": "Primeiro atendimento...",
         "pes_criterios_avaliacao": "90% ... Excelente", "metrica": 2, "meta": 80.0,
         "periodo_titulo": "PIT/RIT 2026-06", "pit_data_inicio": "2026-06-01", "pit_data_fim": "2026-06-30",
         "eh_periodo_corrente": True},
    ]}))

    result = await get_entregas_disponiveis_pgd2(
        EntregasDisponiveisInput(context_url="https://suap.ifrn.edu.br/", gitlab_username="dev.fulano")
    )

    assert route.called
    assert route.calls.last.request.url.params["gitlab_username"] == "dev.fulano"
    assert route.calls.last.request.headers["Authorization"].startswith("Bearer ")
    assert result.entregas[0].pes_descricao.startswith("Primeiro atendimento")
    assert result.entregas[0].metrica == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_pgd2_tools.py::test_entregas_disponiveis_ok`
Expected: FAIL — `ModuleNotFoundError: ... pgd2.tools`.

- [ ] **Step 3: Implementar a tool (`modules/pgd2/tools.py`)**

```python
import structlog

from suap_mcp.contexts import resolve_context
from suap_mcp.keychain import async_keychain_get
from suap_mcp.modules.pgd2 import client
from suap_mcp.modules.pgd2.models import (
    EntregasDisponiveisInput,
    EntregasDisponiveisOutput,
    LancarRitInput,
    LancarRitOutput,
)

_logger = structlog.get_logger(__name__)


async def get_entregas_disponiveis_pgd2(payload: EntregasDisponiveisInput) -> EntregasDisponiveisOutput:
    """List the PGD deliveries (entregas) the servidor can launch a RIT against.

    Use when:
      - Opening a MR and you need to map the work to a planned PGD delivery.
      - You need the Entrega PES description/criteria to infer the right category.

    Returns:
      context, gitlab_username, and `entregas` — each with the PES content
      (pes_titulo/pes_descricao/pes_criterios_avaliacao/metrica/meta) and PIT period.

    Side effects: none (read-only).
    """
    name, ctx = resolve_context(str(payload.context_url))
    token = await async_keychain_get(ctx.suap.token_keychain)
    data = await client.get_entregas_disponiveis(ctx.suap.base_url, token, payload.gitlab_username)
    _logger.info("pgd2_entregas_disponiveis", context=name, n=len(data.get("entregas", [])))
    return EntregasDisponiveisOutput(
        context=name, gitlab_username=payload.gitlab_username, entregas=data.get("entregas", [])
    )
```

- [ ] **Step 4: Registrar no `server.py`**

Adicione o import (junto aos demais, ~linha 36) e o registro (junto aos `mcp.tool(...)`, ~linha 138):

```python
from suap_mcp.modules.pgd2.tools import get_entregas_disponiveis_pgd2, lancar_rit_execucao_gitlab
...
mcp.tool(get_entregas_disponiveis_pgd2, annotations={"readOnlyHint": True})
```

(O `lancar_rit_execucao_gitlab` é registrado na Task A3, mas pode importar já.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest -q tests/test_pgd2_tools.py::test_entregas_disponiveis_ok`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/suap_mcp/modules/pgd2/tools.py src/suap_mcp/server.py tests/test_pgd2_tools.py
git commit -m "feat(pgd2): tool MCP get_entregas_disponiveis_pgd2 (read)"
```

---

### Task A3: Tool `lancar_rit_execucao_gitlab` (write, com dry-run)

**Files:**
- Modify: `src/suap_mcp/modules/pgd2/tools.py`
- Modify: `src/suap_mcp/server.py`
- Test: `tests/test_pgd2_tools.py`

- [ ] **Step 1: Write the failing tests** (dry-run e confirmado — espelha `test_create_mr_*`)

```python
@pytest.mark.asyncio
async def test_lancar_rit_dry_run_nao_chama_suap(fake_contexts_yaml, env_secrets):
    with respx.mock(assert_all_called=False) as mock:
        result = await lancar_rit_execucao_gitlab(LancarRitInput(
            context_url="https://suap.ifrn.edu.br/", gitlab_username="dev.fulano",
            gitlab_project_id=42, gitlab_mr_iid=7, entrega_pit_id=10,
            titulo="Corrige bug X", descricao="Resolve #7 — https://gitlab.../-/issues/7",
            tempo_executado=3, confirm=False,
        ))
    assert result.dry_run is True
    assert result.rit_id is None
    assert mock.calls.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_lancar_rit_confirmado_posta(fake_contexts_yaml, env_secrets):
    route = respx.post(
        "https://suap.ifrn.edu.br/api/pgd2/execucao-gitlab/lancar-rit/"
    ).mock(return_value=Response(200, json={"rit_id": 99, "entrega_pit_id": 10, "gitlab_mr_iid": 7, "criado": True}))

    result = await lancar_rit_execucao_gitlab(LancarRitInput(
        context_url="https://suap.ifrn.edu.br/", gitlab_username="dev.fulano",
        gitlab_project_id=42, gitlab_mr_iid=7, entrega_pit_id=10,
        titulo="Corrige bug X", descricao="Resolve #7", tempo_executado=3, confirm=True,
    ))

    assert route.called
    body = route.calls.last.request.read().decode()
    assert '"quantidade_progresso": 1' in body or '"quantidade_progresso":1' in body
    assert result.dry_run is False
    assert result.rit_id == 99 and result.criado is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_pgd2_tools.py -k lancar_rit`
Expected: FAIL — `lancar_rit_execucao_gitlab` não existe.

- [ ] **Step 3: Implementar a tool**

Adicione a `modules/pgd2/tools.py`:

```python
async def lancar_rit_execucao_gitlab(payload: LancarRitInput) -> LancarRitOutput:
    """Create/update ONE RIT (PGD execution) for a GitLab MR, in EM_CADASTRO_RIT.

    Use when:
      - The servidor confirmed the inferred delivery and estimated hours for a MR.
      - One MR == one RIT (quantidade_progresso = 1); the category total is summed by SUAP.

    Do not use when:
      - The issue does not match any planned PGD delivery (advise manual launch instead).

    Idempotent by (gitlab_project_id, gitlab_mr_iid): re-running updates the same RIT.
    With confirm=False, returns a dry-run preview without writing.

    Side effects:
      Creates/updates a RIT in SUAP (counts toward the PIT until the servidor edits/sends the month).
    """
    name, ctx = resolve_context(str(payload.context_url))

    if not payload.confirm:
        _logger.info("pgd2_lancar_rit_dry_run", context=name, mr=payload.gitlab_mr_iid)
        return LancarRitOutput(
            context=name, gitlab_mr_iid=payload.gitlab_mr_iid, entrega_pit_id=payload.entrega_pit_id, dry_run=True
        )

    token = await async_keychain_get(ctx.suap.token_keychain)
    body = payload.model_dump(exclude={"context_url", "confirm"}, mode="json")
    data = await client.lancar_rit(ctx.suap.base_url, token, body)
    _logger.info("pgd2_lancar_rit", context=name, mr=payload.gitlab_mr_iid, rit_id=data.get("rit_id"))
    return LancarRitOutput(
        context=name,
        gitlab_mr_iid=payload.gitlab_mr_iid,
        entrega_pit_id=payload.entrega_pit_id,
        rit_id=data.get("rit_id"),
        criado=data.get("criado"),
        dry_run=False,
    )
```

- [ ] **Step 4: Registrar no `server.py`**

```python
mcp.tool(lancar_rit_execucao_gitlab, annotations={"destructiveHint": False, "idempotentHint": True})
```

- [ ] **Step 5: Run tests + suíte do módulo**

Run: `uv run pytest -q tests/test_pgd2_tools.py`
Expected: PASS (todos).
Run: `uv run pytest -q` (suíte completa, garantir que server.py ainda carrega).

- [ ] **Step 6: Commit**

```bash
git add src/suap_mcp/modules/pgd2/tools.py src/suap_mcp/server.py tests/test_pgd2_tools.py
git commit -m "feat(pgd2): tool MCP lancar_rit_execucao_gitlab (write, dry-run, idempotente)"
```

---

### Task A4 (opcional): leitura da issue vinculada

Se a skill precisar dos **labels de mês/ano** ou do corpo da issue (não só do MR), e não houver tool de issue:

- [ ] Adicione `get_issue` em `gitlab/client.py` (GET `/projects/:id/issues/:iid`) e uma tool fina `get_gitlab_issue` em `gitlab/tools.py`, espelhando `get_merge_request`/`get_gitlab_mr_diff`. Registre no `server.py` com `readOnlyHint: True`. Teste com `respx`.
- Alternativa sem código novo: usar `get_gitlab_mr_diff` (traz título/descrição/labels do MR) — se o label de mês fica no MR, a Task A4 é dispensável.

---

# Fase B — Skill do Claude (repo `suap`)

> Volte para `/Users/diegosaraiva/Workspace/ifrn/suap`. Branch: `spec/pgd-execucao-gitlab` (ou um novo `feat/skill-pgd-rit`).

### Task B1: Skill `pgd-rit`

**Files (criar):**
- `.agents/skills/pgd-rit/SKILL.md`
- Symlink: `.claude/skills/pgd-rit -> ../../.agents/skills/pgd-rit`
- Modify: `CLAUDE.md` (registrar a skill na seção "# Skills")

- [ ] **Step 1: Escrever o `SKILL.md`** (espelha o formato de `.agents/skills/sentry-fix/SKILL.md`)

Frontmatter + processo:

```markdown
---
name: pgd-rit
description: >
  Ao abrir/atualizar um MR, lança UMA execução (RIT) no PGD do SUAP para aquele MR:
  lê a issue + diff, infere a entrega planejada casando o conteúdo contra a descrição
  e os critérios da Entrega PES de cada categoria, estima as horas pelo diff, mostra um
  resumo, o servidor confirma, e grava o RIT (em EM_CADASTRO_RIT) idempotente por (projeto, MR).
  Trigger: /pgd-rit, "lançar execução no pgd", "registrar o rit desse MR".
trigger: /pgd-rit
---

Lança a execução do PGD a partir de um MR. **Uma RIT por MR.** O servidor confirma antes de gravar.

## Pré-requisitos
- O MR já existe (rode após o `open-pr`/`new-feat`, ou aponte o MR explicitamente).
- O autor do MR tem `username_gitlab` mapeado no SUAP (senão: avise e pare).

## Processo (em ordem)

### Step 1 — Contexto do MR
Use `get_gitlab_mr_diff` (mcp__suap__get_gitlab_mr_diff) para obter: título, descrição, labels,
branch, autor (`username_gitlab`), 1º commit (→ data_inicio) e o diff. Capture `gitlab_project_id`
(numérico) e `gitlab_mr_iid`. Se precisar de labels/corpo da issue vinculada, use `get_gitlab_issue`
(se disponível) ou os dados do próprio MR.

### Step 2 — Entregas candidatas
Use `get_entregas_disponiveis_pgd2` com o `gitlab_username` do autor. Recebe as categorias com
`pes_descricao` + `pes_criterios_avaliacao` + `metrica` + período (`periodo_titulo`, datas,
`eh_periodo_corrente`).
- Se o username não mapear (404) → avise o servidor e PARE (lançamento manual).

### Step 3 — Inferir a entrega (categoria)
Case o trabalho do MR (título/descrição/diff/labels) contra a `pes_descricao` e
`pes_criterios_avaliacao` de cada categoria:
- bug/chamado → categoria de atendimento de erros/chamados;
- feature/demanda → categoria de desenvolvimento de sistemas;
- review → categoria de revisão de código; etc.
**Mês/PIT:** se a issue/MR tem label de mês/ano (ex.: `2026-06`), escolha a entrega cujo período casa;
senão, use a do período corrente (`eh_periodo_corrente: true`).
- **Se nenhuma categoria casar** → avise e NÃO grave (servidor escolhe manual ou pede a entrega ao gestor).
- Se ambíguo (várias casam) → liste o top-N e peça o servidor escolher.

### Step 4 — Estimar horas e montar o RIT
- `tempo_executado`: estimativa pelo tamanho/natureza do diff (informe a heurística no resumo).
- `quantidade_progresso = 1` (um MR = um trabalho), qualquer que seja a métrica.
- `titulo`: título da issue/MR. `descricao`: resumo curto + **link do MR/issue no GitLab** (evita duplicar
  conteúdo no SUAP — a fonte continua o GitLab).
- `data_inicio`: data do 1º commit do branch. `data_fim`: hoje (servidor ajusta).
- `perc_executada_em_teletrabalho`: default (deixe a cargo do servidor confirmar).

### Step 5 — Resumo + confirmação (dry-run)
Mostre ao servidor: entrega escolhida (+período), horas estimadas, título/descrição, link.
Chame `lancar_rit_execucao_gitlab` com `confirm=false` para validar o payload (dry-run, sem gravar) e
mostre o preview. **Só prossiga após o servidor confirmar.**

### Step 6 — Gravar
Chame `lancar_rit_execucao_gitlab` com `confirm=true`. Reporte `rit_id` e se foi `criado` (ou atualizado).
- Erros tratados: 403 entrega de outro servidor / período fechado / mês já enviado → explique e oriente
  lançamento manual; 404 → username não mapeado.

## Tabela de tools

| Step | Ação | Tool |
|------|------|------|
| 1 | Diff/metadados do MR | `mcp__suap__get_gitlab_mr_diff` |
| 2 | Entregas candidatas | `mcp__suap__get_entregas_disponiveis_pgd2` |
| 5 | Preview (dry-run) | `mcp__suap__lancar_rit_execucao_gitlab` (confirm=false) |
| 6 | Gravar RIT | `mcp__suap__lancar_rit_execucao_gitlab` (confirm=true) |
```

- [ ] **Step 2: Criar o symlink para o Claude Code**

```bash
ln -s ../../.agents/skills/pgd-rit .claude/skills/pgd-rit
```

- [ ] **Step 3: Registrar a skill no `CLAUDE.md`**

Na seção `# Skills` (lista de workflows), adicione uma linha descrevendo `pgd-rit` (trigger + 1 frase), no mesmo estilo das demais. Exposta ao Claude Code via symlink.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/pgd-rit/ .claude/skills/pgd-rit CLAUDE.md
git commit -m "feat(pgd2): skill pgd-rit (infere entrega, estima horas, lança RIT no PR)"
```

---

### Task B2: Verificação manual (fim a fim, dry-run)

- [ ] Em um MR de teste (com `username_gitlab` mapeado e um PIT aberto com entregas homologadas no SUAP de homologação/staging), rode `/pgd-rit`:
  - Confirme que `get_entregas_disponiveis_pgd2` retorna as categorias com `pes_descricao`.
  - Confirme que a inferência escolhe uma categoria plausível e o resumo aparece.
  - Confirme que o dry-run (`confirm=false`) NÃO grava.
  - Após confirmar, valide que o RIT aparece no PGD em `EM_CADASTRO_RIT`, com `quantidade_progresso = 1` e o link no `descricao`.
  - Rode `/pgd-rit` de novo no mesmo MR → deve **atualizar** o mesmo RIT (idempotência), não duplicar.
- [ ] Borda: username não mapeado → a skill avisa e não grava. Issue sem categoria → avisa e não grava.

---

## Pendências/decisões herdadas (já resolvidas no spec)
- `quantidade_progresso = 1` sempre; entregas `PERCENTUAL` podem somar >100% (SUAP conta como horas extras) — sem tratamento especial.
- Mês alvo: label de mês/ano da issue; default corrente; lista de todos os PITs abertos.
- Quando não casa: avisa e não grava.

## Próximo plano
- **Plano 3 — Bordas de CI (opcional, leve):** comentário de confirmação no merge; limpeza de RIT órfão no fechamento de MR sem merge (RIT em `EM_CADASTRO_RIT`); reestimação no merge fica adiada.
