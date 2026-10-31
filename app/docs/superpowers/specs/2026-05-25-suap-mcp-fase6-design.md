# SUAP MCP — Fase 6: Documentação e Exemplos de Uso

**Data:** 2026-05-25
**Escopo:** Atualizar `README.md` do `suap-mcp` para documentar o módulo de demandas e adicionar um prompt MCP reutilizável.
**Projeto alvo:** `/Users/diegosaraiva/Workspace/ifrn/suap-mcp`
**Fase final do MVP.**

---

## 1. Artefatos

| Artefato | Ação |
|---|---|
| `README.md` | Modificar — 5 seções atualizadas (ver abaixo) |
| `src/suap_mcp/modules/demandas/prompts.py` | Modificar — adicionar 1 prompt MCP |
| `src/suap_mcp/server.py` | Modificar — registrar o prompt do módulo demandas |

---

## 2. Mudanças no README.md

### 2.1 Linha 1-10 (introdução)

Adicionar SUAP como 4ª integração na lista:
```
- SUAP (módulo de Demandas)
```

### 2.2 Seção "Architecture"

Adicionar SUAP ao diagrama:
```text
AI Agent
↓
MCP Client (Codex / OpenCode / Claude)
↓
suap-mcp
↓
contexts.yaml + macOS Keychain
↓
Sentry / GitLab / SUAP APIs
```

### 2.3 Seção "Features — Current tools"

Adicionar bloco de ferramentas SUAP Demandas (após as ferramentas GitLab):

```
SUAP Demandas tools:
- `get_demanda_context` — read-only, retorna contexto completo da demanda (spec, DoD, decisões, sub-demandas, MR).
- `get_subdemandas` — read-only, lista sub-demandas diretas com percentual de conclusão.
- `get_demanda_mr_status` — read-only, retorna status do MR conforme registrado no SUAP.
- `get_entrega_pipeline_status` — read-only, retorna status do pipeline de uma entrega.
- `open_mr_for_demanda` — idempotente (não-destrutivo), abre MR via SUAP; requer `confirm=True`.
- `append_spec_decision` — **append-only**, registra decisão arquitetural na demanda; requer `confirm=True`.
```

Adicionar prompt MCP à seção "Current prompts":
```
- `demanda-workflow` — prompt estruturado para iniciar uma sessão de trabalho em uma demanda: busca contexto, verifica MR, instrui sobre como registrar decisões.
```

### 2.4 Seção "Configuration" — adicionar subsection SUAP

Nova subseção após a explicação do `contexts.yaml`:

```markdown
## SUAP

Para usar as ferramentas de demandas, adicione a chave `suap` ao contexto:

```yaml
contexts:
  ifrn:
    suap:
      base_url: "https://suap.ifrn.edu.br"
      token_keychain: "coding-agents/suap/ifrn"
    sentry:
      ...
    gitlab:
      ...
```

O token SUAP é um JWT de desenvolvedor gerado pelo próprio SUAP. Armazene-o
no Keychain:

```bash
security add-generic-password \
  -a "$USER" \
  -s "coding-agents/suap/ifrn" \
  -w
```

### Token scopes (SUAP)

| Use case | Permissão necessária no SUAP |
|---|---|
| Todas as ferramentas de leitura (`get_*`) | `view_demanda` ou `atende_demanda` |
| `open_mr_for_demanda`, `append_spec_decision` | `atende_demanda` ou `change_demanda` |
```

### 2.5 Seção "Project Structure"

Adicionar `modules/demandas/` ao diagrama:

```text
│   ├── modules/
│   │   └── demandas/   # SUAP Demandas client + tools + I/O models
```

### 2.6 Seção "MCP Client Configuration" — atualizar lista de tools

Adicionar as 6 ferramentas à lista de tools esperados (ambos Claude Code e Codex).

---

## 3. Prompt MCP — `modules/demandas/prompts.py`

Adicionar um prompt chamado `demanda-workflow` análogo ao `review-sentry-issue` existente.

O prompt recebe `demanda_id: int` e `suap_url: str` e retorna instruções estruturadas para o agente:

1. Buscar contexto com `get_demanda_context`.
2. Verificar status do MR com `get_demanda_mr_status`.
3. Se necessário, abrir MR com `open_mr_for_demanda(confirm=True)`.
4. Registrar decisões com `append_spec_decision(confirm=True)` ao longo do trabalho.

### Registro em `server.py`

```python
from suap_mcp.modules.demandas.prompts import demanda_workflow

mcp.prompt(demanda_workflow)
```

---

## 4. Testes

Diferidos — consistente com as demais fases.
