# SUAP MCP — Fase 1: Contrato de Erro e Autoria

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estabelecer a infraestrutura da Fase 1: estrutura de diretórios `modules/demandas/`, contrato de erro (`McpError` + `DemandaError`), suporte a JWT SUAP no `Context` model, e helper `suap_headers()`.

**Architecture:** Novo pacote `src/suap_mcp/modules/demandas/` agrupa toda lógica de domínio SUAP separada das integrações externas (gitlab, sentry). O `Context` model ganha campo `suap` opcional (backward-compatible). `DemandaError` estende `SuapMCPError` existente e serializa para `McpError` TypedDict.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, uv. Repositório: `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`. Rodar testes com `uv run pytest <path> -v`.

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/suap_mcp/modules/__init__.py` | Criar | Marca pacote |
| `src/suap_mcp/modules/demandas/__init__.py` | Criar | Marca pacote |
| `src/suap_mcp/modules/demandas/errors.py` | Criar | `McpError` TypedDict + `DemandaError` exception |
| `src/suap_mcp/modules/demandas/client.py` | Criar | `suap_headers()` + cliente HTTP base (stub por ora) |
| `src/suap_mcp/modules/demandas/schemas.py` | Criar | Stub — TypedDicts de request/response (Fases 3–4) |
| `src/suap_mcp/modules/demandas/tools.py` | Criar | Stub — tools MCP (Fase 5) |
| `src/suap_mcp/modules/demandas/prompts.py` | Criar | Stub — prompts/resources (Fase 5) |
| `src/suap_mcp/contexts.py` | Modificar | Adiciona `suap: ServiceContext \| None = None` ao `Context` |
| `tests/modules/__init__.py` | Criar | Marca pacote de testes |
| `tests/modules/demandas/__init__.py` | Criar | Marca pacote de testes |
| `tests/modules/demandas/test_errors.py` | Criar | Testes de `McpError` e `DemandaError` |
| `tests/modules/demandas/test_client.py` | Criar | Testes de `suap_headers()` |
| `tests/test_contexts.py` | Modificar | Adiciona testes para campo `suap` no Context |
| `tests/conftest.py` | Modificar | Atualiza fixtures com dados SUAP |
| `contexts.yaml.example` | Modificar | Adiciona seção `suap` de exemplo |

---

## Task 1: Scaffold — criar estrutura de diretórios

**Files:**
- Create: `src/suap_mcp/modules/__init__.py`
- Create: `src/suap_mcp/modules/demandas/__init__.py`
- Create: `src/suap_mcp/modules/demandas/errors.py`
- Create: `src/suap_mcp/modules/demandas/client.py`
- Create: `src/suap_mcp/modules/demandas/schemas.py`
- Create: `src/suap_mcp/modules/demandas/tools.py`
- Create: `src/suap_mcp/modules/demandas/prompts.py`
- Create: `tests/modules/__init__.py`
- Create: `tests/modules/demandas/__init__.py`

- [ ] **Step 1: Criar os pacotes e stubs**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp

# Pacotes src
mkdir -p src/suap_mcp/modules/demandas
touch src/suap_mcp/modules/__init__.py
touch src/suap_mcp/modules/demandas/__init__.py

# Stubs de conteúdo futuro
cat > src/suap_mcp/modules/demandas/schemas.py << 'EOF'
from __future__ import annotations
EOF

cat > src/suap_mcp/modules/demandas/tools.py << 'EOF'
from __future__ import annotations
EOF

cat > src/suap_mcp/modules/demandas/prompts.py << 'EOF'
from __future__ import annotations
EOF

# errors.py e client.py serão implementados nas tasks seguintes
touch src/suap_mcp/modules/demandas/errors.py
touch src/suap_mcp/modules/demandas/client.py

# Pacotes de teste
mkdir -p tests/modules/demandas
touch tests/modules/__init__.py
touch tests/modules/demandas/__init__.py
```

- [ ] **Step 2: Verificar que o pytest não quebra**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest --collect-only -q
```

Esperado: lista de testes existentes sem erros de importação. Nenhum teste novo ainda.

- [ ] **Step 3: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add src/suap_mcp/modules/ tests/modules/
git commit -m "feat: scaffold modules/demandas directory structure"
```

---

## Task 2: McpError TypedDict + DemandaError (TDD)

**Files:**
- Create: `src/suap_mcp/modules/demandas/errors.py`
- Create: `tests/modules/demandas/test_errors.py`

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/modules/demandas/test_errors.py`:

```python
from __future__ import annotations

import pytest

from suap_mcp.exceptions import SuapMCPError
from suap_mcp.modules.demandas.errors import DemandaError, McpError


def test_mcp_error_is_typed_dict() -> None:
    err: McpError = {
        "error": "branch_missing",
        "hint": "Defina o campo branch na demanda",
        "context": {"demanda_id": 42},
    }
    assert err["error"] == "branch_missing"
    assert err["hint"] == "Defina o campo branch na demanda"
    assert err["context"] == {"demanda_id": 42}


def test_demanda_error_is_suap_mcp_error() -> None:
    exc = DemandaError(
        error="branch_missing",
        hint="Defina o campo branch na demanda",
        demanda_id=42,
    )
    assert isinstance(exc, SuapMCPError)


def test_demanda_error_to_mcp_error() -> None:
    exc = DemandaError(
        error="branch_missing",
        hint="Defina o campo branch na demanda",
        demanda_id=42,
    )
    result = exc.to_mcp_error()
    assert result["error"] == "branch_missing"
    assert result["hint"] == "Defina o campo branch na demanda"
    assert result["context"] == {"demanda_id": 42}


def test_demanda_error_context_with_multiple_kwargs() -> None:
    exc = DemandaError(
        error="upstream_error",
        hint="SUAP retornou erro 500",
        demanda_id=7,
        status_code=500,
    )
    assert exc.to_mcp_error()["context"] == {"demanda_id": 7, "status_code": 500}


def test_demanda_error_empty_context() -> None:
    exc = DemandaError(error="demanda_not_found", hint="Verifique o ID")
    assert exc.to_mcp_error()["context"] == {}


def test_demanda_error_can_be_caught_as_suap_mcp_error() -> None:
    with pytest.raises(SuapMCPError):
        raise DemandaError(error="permission_denied", hint="JWT sem permissão")
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/modules/demandas/test_errors.py -v
```

Esperado: `ImportError` ou `ModuleNotFoundError` em `suap_mcp.modules.demandas.errors`.

- [ ] **Step 3: Implementar errors.py**

Escrever `src/suap_mcp/modules/demandas/errors.py`:

```python
from __future__ import annotations

from typing import Any, TypedDict

from suap_mcp.exceptions import SuapMCPError


class McpError(TypedDict):
    error: str
    hint: str
    context: dict[str, Any]


class DemandaError(SuapMCPError):
    def __init__(self, *, error: str, hint: str, **context: Any) -> None:
        super().__init__(error)
        self.error = error
        self.hint = hint
        self.context = context

    def to_mcp_error(self) -> McpError:
        return {"error": self.error, "hint": self.hint, "context": dict(self.context)}
```

- [ ] **Step 4: Rodar para confirmar que passa**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/modules/demandas/test_errors.py -v
```

Esperado: 6 testes passando.

- [ ] **Step 5: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add src/suap_mcp/modules/demandas/errors.py tests/modules/demandas/test_errors.py
git commit -m "feat: add McpError TypedDict and DemandaError exception"
```

---

## Task 3: suap_headers() em client.py (TDD)

**Files:**
- Modify: `src/suap_mcp/modules/demandas/client.py`
- Create: `tests/modules/demandas/test_client.py`

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/modules/demandas/test_client.py`:

```python
from __future__ import annotations

from suap_mcp.modules.demandas.client import suap_headers


def test_suap_headers_bearer() -> None:
    headers = suap_headers("my-jwt-token")
    assert headers == {"Authorization": "Bearer my-jwt-token"}


def test_suap_headers_returns_new_dict_each_call() -> None:
    h1 = suap_headers("tok")
    h2 = suap_headers("tok")
    assert h1 is not h2
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/modules/demandas/test_client.py -v
```

Esperado: `ImportError` em `suap_mcp.modules.demandas.client`.

- [ ] **Step 3: Implementar client.py**

Escrever `src/suap_mcp/modules/demandas/client.py`:

```python
from __future__ import annotations


def suap_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 4: Rodar para confirmar que passa**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/modules/demandas/test_client.py -v
```

Esperado: 2 testes passando.

- [ ] **Step 5: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add src/suap_mcp/modules/demandas/client.py tests/modules/demandas/test_client.py
git commit -m "feat: add suap_headers() in modules/demandas/client"
```

---

## Task 4: Estender Context model para suap (TDD)

**Files:**
- Modify: `src/suap_mcp/contexts.py`
- Modify: `tests/test_contexts.py`
- Modify: `tests/conftest.py`
- Modify: `contexts.yaml.example`

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_contexts.py`:

```python
def test_load_contexts_suap_is_none_when_absent(fake_contexts_yaml: Path) -> None:
    contexts = load_contexts()
    assert contexts["ifrn"].suap is None


def test_load_contexts_suap_parses_when_present(fake_contexts_yaml_with_suap: Path) -> None:
    contexts = load_contexts()
    assert contexts["ifrn"].suap is not None
    assert contexts["ifrn"].suap.base_url == "https://suap.ifrn.edu.br"
    assert contexts["ifrn"].suap.token_keychain == "coding-agents/suap/ifrn"
```

Adicionar nova fixture ao `tests/conftest.py` (após as fixtures existentes):

```python
@pytest.fixture
def fake_contexts_yaml_with_suap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """contexts.yaml com suap configurado."""

    data = {
        "contexts": {
            "ifrn": {
                "sentry": {
                    "base_url": "https://sentry.ifrn.edu.br",
                    "token_keychain": "coding-agents/sentry/ifrn",
                },
                "gitlab": {
                    "base_url": "https://gitlab.ifrn.edu.br",
                    "token_keychain": "coding-agents/gitlab/ifrn",
                },
                "suap": {
                    "base_url": "https://suap.ifrn.edu.br",
                    "token_keychain": "coding-agents/suap/ifrn",
                },
            },
        }
    }
    path = tmp_path / "contexts.yaml"
    path.write_text(yaml.safe_dump(data))

    monkeypatch.setattr("suap_mcp.config.CONFIG_PATH", path)
    return path
```

Também adicionar SUAP ao fixture `env_secrets` existente (no final do `yield` block):

```python
@pytest.fixture
def env_secrets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide secrets via environment variables (the first resolution step)."""

    monkeypatch.setenv("CODING_AGENTS_SENTRY_IFRN", "sentry-token")
    monkeypatch.setenv("CODING_AGENTS_GITLAB_IFRN", "gitlab-token")
    monkeypatch.setenv("CODING_AGENTS_SUAP_IFRN", "suap-token")
    yield
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/test_contexts.py -v -k "suap"
```

Esperado: `AttributeError: 'Context' object has no attribute 'suap'`.

- [ ] **Step 3: Adicionar campo suap ao Context**

Editar `src/suap_mcp/contexts.py`, mudar apenas a classe `Context`:

```python
class Context(BaseModel):
    """A named context grouping one Sentry, one GitLab and an optional SUAP service."""

    sentry: ServiceContext
    gitlab: ServiceContext
    suap: ServiceContext | None = None
```

- [ ] **Step 4: Rodar para confirmar que passa**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest tests/test_contexts.py -v
```

Esperado: todos os testes do arquivo passando (incluindo os antigos, que não devem quebrar).

- [ ] **Step 5: Atualizar contexts.yaml.example**

Editar `contexts.yaml.example` — substituir o bloco do contexto `ifrn` existente por:

```yaml
contexts:
  ifrn:
    suap:
      base_url: "https://suap.ifrn.edu.br"
      token_keychain: "coding-agents/suap/ifrn"
    sentry:
      base_url: "https://sentry.ifrn.edu.br"
      token_keychain: "coding-agents/sentry/ifrn"
    gitlab:
      base_url: "https://gitlab.ifrn.edu.br"
      token_keychain: "coding-agents/gitlab/ifrn"

  # mec:
  #   suap:
  #     base_url: "https://suap.mec.gov.br"
  #     token_keychain: "coding-agents/suap/mec"
  #   sentry:
  #     base_url: "https://sentry.mec.gov.br"
  #     token_keychain: "coding-agents/sentry/mec"
  #   gitlab:
  #     base_url: "https://gitlab.mec.gov.br"
  #     token_keychain: "coding-agents/gitlab/mec"
```

- [ ] **Step 6: Rodar suite completa**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest -v
```

Esperado: todos os testes existentes passando. Nenhuma regressão.

- [ ] **Step 7: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add src/suap_mcp/contexts.py tests/test_contexts.py tests/conftest.py contexts.yaml.example
git commit -m "feat: add optional suap field to Context model with JWT support"
```

---

## Task 5: Suite final e verificação de tipos

**Files:** Nenhum arquivo novo — apenas verificações.

- [ ] **Step 1: Rodar suite completa**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run pytest -v
```

Esperado: todos os testes passando, incluindo os das Tasks 2, 3 e 4.

- [ ] **Step 2: Verificar tipos com mypy**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run mypy src/suap_mcp/modules/
```

Esperado: `Success: no issues found in N source files`.

Se aparecerem erros de tipo:
- `Missing return type annotation` → adicionar anotação na função indicada
- `Incompatible return value` → verificar se `dict(self.context)` retorna `dict[str, Any]` corretamente

- [ ] **Step 3: Verificar linting**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
uv run ruff check src/suap_mcp/modules/ tests/modules/
```

Esperado: nenhuma violação.

- [ ] **Step 4: Commit final (somente se houve ajustes)**

Se houve correções de tipo ou lint nos steps anteriores:

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap-mcp
git add -p
git commit -m "fix: type annotations and lint for modules/demandas"
```

---

## Referência: catálogo de erros da Fase 1

Para uso nas Fases 3 e 4 ao lançar `DemandaError`:

| `error` | Situação |
|---|---|
| `branch_missing` | `open_mr_for_demanda` sem branch na demanda |
| `demanda_not_found` | ID inexistente (404 do Ninja) |
| `pipeline_not_linked` | Entrega sem `pipeline_id` |
| `permission_denied` | 403 do Django Ninja |
| `token_expired` | 401 do SUAP |
| `upstream_error` | Erro genérico |
