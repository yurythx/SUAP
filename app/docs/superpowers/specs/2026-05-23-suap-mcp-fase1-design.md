# SUAP MCP — Fase 1: Contrato de Erro e Autoria

**Data:** 2026-05-23
**Escopo:** Decisões de infraestrutura para o módulo de demandas do suap-mcp. Sem código novo além das definições aqui documentadas.
**Próximo passo:** Fase 2 — modelo `DecisaoEspecificacao`.

---

## 0. Estrutura de Diretórios do suap-mcp

O suap-mcp separa integrações externas (gitlab, sentry) de módulos de domínio SUAP sob `modules/`:

```
src/suap_mcp/
├── gitlab/          # integrações externas (existente)
├── sentry/          # integrações externas (existente)
└── modules/         # módulos de domínio SUAP
    └── demandas/
        ├── __init__.py
        ├── tools.py     # tools MCP
        ├── client.py    # cliente HTTP para a API Ninja do SUAP
        ├── errors.py    # McpError + DemandaError
        ├── schemas.py   # TypedDicts de request/response
        └── prompts.py   # prompts/resources (se houver)
```

Novos módulos SUAP futuros (ex.: `rh/`, `ensino/`) vão em `modules/` seguindo o mesmo layout.

---

## 1. Mecanismo de Autoria

### Decisão

Autenticação via **JWT por desenvolvedor**, armazenado no keychain local. Padrão idêntico ao GitLab e Sentry já configurados no suap-mcp.

### Configuração (uma vez por desenvolvedor)

```bash
# Gerar token via API
curl -X POST https://suap.ifrn.edu.br/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "SEU_LOGIN", "password": "SUA_SENHA"}' | jq .access

# Armazenar no keychain (macOS)
security add-generic-password \
  -a "$USER" \
  -s "coding-agents/suap/ifrn" \
  -w
```

### contexts.yaml

O arquivo `~/.config/coding-agents/contexts.yaml` recebe uma chave `suap` por contexto:

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
```

### Header HTTP

```python
def suap_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

### Validade do token

Token de acesso com validade longa (dias/semanas), configurado no SUAP via `NINJA_JWT["ACCESS_TOKEN_LIFETIME"]`. Sem refresh automático no cliente. Em caso de expiração (401), o MCP retorna erro com hint claro para o dev regenerar o token.

### Por que funciona com django-reversion

O `JWTAuth` do SUAP já executa `tl.context.user = request.user` antes de chamar o endpoint. O `django-reversion` registra `request.user` automaticamente — nenhuma mudança de middleware necessária.

---

## 2. Contrato de Erro do MCP

### Schema

Novo arquivo: `src/suap_mcp/modules/demandas/errors.py`

```python
from typing import Any, TypedDict


class McpError(TypedDict):
    error: str              # código snake_case
    hint: str               # orientação legível para o agente/dev
    context: dict[str, Any] # dados contextuais variáveis
```

### Exceção de domínio

Estende `SuapMCPError` existente em `suap_mcp/exceptions.py`. O `DemandaError` fica em `errors.py` — erros de outros módulos futuros (ex.: `modules/rh/errors.py`) seguem o mesmo padrão:

```python
class DemandaError(SuapMCPError):
    def __init__(self, *, error: str, hint: str, **context: Any) -> None:
        super().__init__(error)
        self.error = error
        self.hint = hint
        self.context = context

    def to_mcp_error(self) -> McpError:
        return {"error": self.error, "hint": self.hint, "context": self.context}
```

### Catálogo de códigos de erro

| `error` | Situação | `hint` |
|---|---|---|
| `branch_missing` | `open_mr_for_demanda` chamado sem branch definido na demanda | "Defina o campo `branch` na demanda antes de abrir um MR" |
| `demanda_not_found` | ID de demanda inexistente | "Verifique se o ID da demanda está correto" |
| `pipeline_not_linked` | Entrega sem `pipeline_id` | "Esta entrega não tem pipeline associado" |
| `permission_denied` | 403 do Django Ninja | "Seu JWT não tem permissão para esta demanda" |
| `token_expired` | 401 do SUAP | "Token JWT expirado — regenere via POST /api/token/ e atualize o keychain" |
| `upstream_error` | Erro genérico do SUAP | "SUAP retornou erro {status_code}" |

### Padrão de retorno nas tools

As tools retornam `dict` em ambos os casos — sucesso e erro. O agente distingue pela presença da chave `error`. MR já existente **não é erro** — é retorno de sucesso com `already_existed: true` (ver Seção 3):

```python
async def open_mr_for_demanda(demanda_id: int) -> dict:
    try:
        return await suap_client.post_merge_request(demanda_id)
    except DemandaError as exc:
        return exc.to_mcp_error()
```

Exemplo de erro retornado:

```json
{
  "error": "branch_missing",
  "hint": "Defina o campo `branch` na demanda antes de abrir um MR",
  "context": {"demanda_id": 42}
}
```

---

## 3. Contrato de Idempotência

### Mapeamento por ferramenta

| Ferramenta | `idempotentHint` FastMCP | Comportamento se recurso já existe |
|---|---|---|
| `get_demanda_context` | `True` | Retorna estado atual (leitura pura) |
| `get_subdemandas` | `True` | Retorna lista atual (leitura pura) |
| `get_demanda_mr_status` | `True` | Retorna status atual (leitura pura) |
| `get_entrega_pipeline_status` | `True` | Retorna status atual (leitura pura) |
| `open_mr_for_demanda` | `True` | Retorna MR existente com `already_existed: true` |
| `append_spec_decision` | `False` | Sempre cria novo registro (append-only por design) |

### Campo `already_existed` no retorno de escrita idempotente

`open_mr_for_demanda` retorna em caso de MR já existente:

```json
{
  "mr_url": "https://gitlab.ifrn.edu.br/.../merge_requests/42",
  "mr_iid": 42,
  "already_existed": true,
  "status": "opened"
}
```

### Registro nas anotações FastMCP

```python
mcp.tool(
    open_mr_for_demanda,
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
```

---

## Resumo das decisões

| Decisão | Escolha |
|---|---|
| Autenticação no SUAP | JWT por desenvolvedor, keychain local |
| Validade do token | Longa (sem refresh automático) |
| Schema de erro | `{error, hint, context}` — contexto estruturado |
| Hint do erro | Texto livre legível por humano |
| Idempotência | Declarada via `idempotentHint` + campo `already_existed` |
| Append-only | `append_spec_decision` explicitamente não idempotente |
