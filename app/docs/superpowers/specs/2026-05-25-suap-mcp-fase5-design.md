# SUAP MCP — Fase 5: Extensão do suap-mcp com 6 Ferramentas

**Data:** 2026-05-25
**Escopo:** Adicionar 6 ferramentas MCP ao servidor `suap-mcp` existente como fachada sobre os endpoints Ninja das Fases 3 e 4. Sem lógica de domínio — apenas tradução de protocolo.
**Pré-requisito:** Fases 3 e 4 concluídas (endpoints operacionais no SUAP).
**Projeto alvo:** `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`
**Próximo passo:** Fase 6 — documentação e exemplos de uso.

---

## 1. Ferramentas

### Leitura (4 ferramentas)

| Ferramenta | Endpoint SUAP | Anotações MCP |
|---|---|---|
| `get_demanda_context` | `GET /api/demandas/{id}/agent-context/` | readOnly, idempotent |
| `get_subdemandas` | `GET /api/demandas/{id}/subdemandas/` | readOnly, idempotent |
| `get_demanda_mr_status` | `GET /api/demandas/{id}/mr-status/` | readOnly, idempotent |
| `get_entrega_pipeline_status` | `GET /api/entregas/{id}/pipeline-status/` | readOnly, idempotent |

### Escrita (2 ferramentas)

| Ferramenta | Endpoint SUAP | Idempotência | Anotações MCP |
|---|---|---|---|
| `open_mr_for_demanda` | `POST /api/demandas/{id}/merge-request/` | Sim — retorna MR existente | destructive=False, idempotent=True |
| `append_spec_decision` | `POST /api/demandas/{id}/spec-decisions/` | Não — append | destructive=True |

Ferramentas de escrita têm `confirm: bool = False` para dry-run (padrão no projeto).

---

## 2. Inputs e Outputs

Todos os inputs herdam de `DemandaInput` (base comum):

```
suap_url: HttpUrl   # ex: "https://suap.ifrn.edu.br" — resolve o contexto
```

### `get_demanda_context` / `GetDemandaContextInput`
```
suap_url: HttpUrl
demanda_id: int
```
Output: `AgentContextOutput` (espelha o response do endpoint — ver Seção 3).

### `get_subdemandas` / `GetSubdemandasInput`
```
suap_url: HttpUrl
demanda_id: int
```
Output: `list[SubdemandaOutput]`

### `get_demanda_mr_status` / `GetDemandaMrStatusInput`
```
suap_url: HttpUrl
demanda_id: int
```
Output: `MrStatusOutput`

### `get_entrega_pipeline_status` / `GetEntregaPipelineStatusInput`
```
suap_url: HttpUrl
entrega_id: int
```
Output: `PipelineStatusOutput`

### `open_mr_for_demanda` / `OpenMrForDemandaInput`
```
suap_url: HttpUrl
demanda_id: int
confirm: bool = False
```
Output: `OpenMrOutput` (inclui `already_exists: bool`, `dry_run: bool`)

### `append_spec_decision` / `AppendSpecDecisionInput`
```
suap_url: HttpUrl
demanda_id: int
decisao: str
contexto: dict = {}
origem: str = 'agente'
confirm: bool = False
```
Output: `SpecDecisionOutput` (inclui `dry_run: bool`)

---

## 3. Schemas de Output

Espelham os response schemas dos endpoints SUAP (Fases 3 e 4):

### `SubdemandaOutput`
```
id: int
titulo: str
situacao: str
percentual_conclusao: int
```

### `DodEspecificacaoOutput`
```
nome: str
atividades: str
ordem: int
gitlab_issue_url: str | None
```

### `DodOutput`
```
descricao: str | None
especificacoes: list[DodEspecificacaoOutput]
```

### `DecisaoEspecificacaoOutput`
```
id: int
autor: str
criado_em: str          # ISO-8601
decisao: str
contexto: dict
origem: str
```

### `AgentContextOutput`
```
context: str            # nome do contexto MCP (ex: 'ifrn')
id: int
titulo: str
situacao: str
especificacao_tecnica: str
branch: str | None
id_merge_request: int | None
subdemandas: list[SubdemandaOutput]
dod: DodOutput | None
decisoes_especificacao: list[DecisaoEspecificacaoOutput]
```

### `MrStatusOutput`
```
context: str
demanda_id: int
branch: str | None
id_merge_request: int | None
situacao: str
mr_url: str | None
```

### `OpenMrOutput`
```
context: str
demanda_id: int
branch: str | None
id_merge_request: int | None
situacao: str
mr_url: str | None
already_exists: bool
dry_run: bool
```

### `PipelineStatusOutput`
```
context: str
entrega_id: int
pipeline_id: int | None
branch: str | None
id_merge_request: int | None
status: str
```

### `SpecDecisionOutput`
```
context: str
id: int
demanda_id: int
autor: str
criado_em: str          # ISO-8601
decisao: str
contexto: dict
origem: str
dry_run: bool
```

---

## 4. Mapeamento de Erros HTTP → MCP

O SUAP retorna `{error, hint, context}` em respostas 4xx. O cliente SUAP deve:

1. Chamar o endpoint via `httpx` diretamente (não via `request_json` do `suap_mcp.http`),
   pois precisamos inspecionar o body de erros 4xx antes de propagá-los.
2. Para respostas 4xx com body JSON: parsear e levantar `DemandaError(error=..., hint=..., **context)`.
3. Para respostas 5xx ou erros de rede: deixar propagar como `UpstreamHTTPError`.

**Fluxo do client:**
```python
response = await client.get(url, headers=suap_headers(token))
if response.is_success:
    return response.json()
body = _try_parse_error(response)
if body and response.status_code < 500:
    raise DemandaError(error=body['error'], hint=body['hint'], **body.get('context', {}))
response.raise_for_status()  # lança httpx.HTTPStatusError para 5xx
```

**No tool function:** `DemandaError` é capturado e retornado como `McpError` via `to_mcp_error()`.
`UpstreamHTTPError` e `httpx.HTTPStatusError` propagam livremente (FastMCP os serializa como erro MCP).

---

## 5. Resolução de Contexto (fix necessário em `contexts.py`)

`resolve_context(url)` atualmente só verifica hosts de Sentry e GitLab. Para SUAP,
os tools passam `suap_url` — mas essa URL não casa com nenhum contexto.

**Fix:** Estender o loop em `resolve_context` para verificar também `ctx.suap.base_url`:

```python
for name, ctx in contexts.items():
    sentry_host = _host_from_base_url(ctx.sentry.base_url)
    gitlab_host = _host_from_base_url(ctx.gitlab.base_url)
    suap_host = _host_from_base_url(ctx.suap.base_url) if ctx.suap else None
    if host in {sentry_host, gitlab_host, suap_host}:
        return name, ctx
```

Sem esse fix, `resolve_context("https://suap.ifrn.edu.br/api/demandas/1/agent-context/")` lança `ContextNotFoundError`.

---

## 6. Artefatos

| Artefato | Ação |
|---|---|
| `src/suap_mcp/contexts.py` | Modificar — adicionar suap_host ao resolve_context |
| `src/suap_mcp/modules/demandas/client.py` | Modificar — adicionar funções HTTP para cada endpoint |
| `src/suap_mcp/modules/demandas/models.py` | Criar — Input/Output Pydantic models |
| `src/suap_mcp/modules/demandas/schemas.py` | Modificar — schemas de dados compartilhados |
| `src/suap_mcp/modules/demandas/tools.py` | Modificar — 6 funções de tool async |
| `src/suap_mcp/server.py` | Modificar — registrar as 6 ferramentas |

Sem novos arquivos além de `models.py` (que não existe ainda).

---

## 7. Registro no server.py

```python
from suap_mcp.modules.demandas.tools import (
    get_demanda_context,
    get_subdemandas,
    get_demanda_mr_status,
    get_entrega_pipeline_status,
    open_mr_for_demanda,
    append_spec_decision,
)

mcp.tool(get_demanda_context,        annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
mcp.tool(get_subdemandas,            annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
mcp.tool(get_demanda_mr_status,      annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
mcp.tool(get_entrega_pipeline_status,annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
mcp.tool(open_mr_for_demanda,        annotations={"readOnlyHint": False, "idempotentHint": True,  "destructiveHint": False, "openWorldHint": True})
mcp.tool(append_spec_decision,       annotations={"readOnlyHint": False, "idempotentHint": False, "destructiveHint": True,  "openWorldHint": True})
```

---

## 8. Testes

Diferidos — consistente com Fases 2, 3 e 4. Cenários ficam documentados para referência futura.

**Cenários a cobrir quando pytest estiver configurado:**

- Resolução de contexto SUAP (fix em `contexts.py`)
- `get_demanda_context` — 200, 403, 404
- `open_mr_for_demanda` dry-run (confirm=False), MR criado (201), MR existente (200)
- `append_spec_decision` dry-run, criação, `decisao` em branco (422 auto do Ninja)
- `get_entrega_pipeline_status` — 200, 404, 422 `pipeline_not_linked`
- Erro 5xx do SUAP → UpstreamHTTPError propagado

---

## 9. Logging

Padrão do projeto — `structlog` via `get_logger(__name__)`:

```python
_logger.info(
    "get_demanda_context",
    context=name,
    demanda_id=payload.demanda_id,
)
```

---

## 10. Resumo de Dependências

Sem novos pacotes Python. O módulo usa apenas:
- `httpx` (já instalado)
- `pydantic` (já instalado)
- `fastmcp` (já instalado)
- `suap_mcp.{contexts, keychain, http, logging, exceptions}` (internos)
