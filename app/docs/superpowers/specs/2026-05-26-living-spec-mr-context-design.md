# SUAP MCP — Spec Viva: Contexto de Demanda em MRs

**Data:** 2026-05-26
**Escopo:** Enriquecer automaticamente os MRs do GitLab com contexto das demandas SUAP e manter a especificação técnica atualizada a cada merge — sem ação manual do dev após o fluxo inicial.
**Pré-requisito:** Fases 1–6 concluídas (suap-mcp operacional, endpoints Ninja de leitura e escrita funcionando).
**Projetos alvo:** `suap-mcp` (Fases 7) e `suap` (Fases 8–9).

---

## 1. Problema

Especificações técnicas de demandas ficam desatualizadas: a implementação diverge da descrição inicial e o sistema evolui sem que ninguém atualize a spec. O resultado é documentação que mente sobre o comportamento real do sistema.

---

## 2. Solução

Um fluxo em dois momentos:

1. **Antes do merge (interativo):** o agente analisa o diff + spec atual, propõe um delta de spec como comment no MR. O dev revisa e aprova (ou edita) no próprio GitLab.
2. **No merge (automático):** um CI job detecta a proposta aprovada e persiste o delta como `DecisaoEspecificacao` no SUAP — sem ação adicional do dev.

A spec da demanda passa a ser um **documento vivo**, atualizado a cada MR relevante.

---

## 3. Arquitetura

```
Dev / Agente
    │
    ▼
[MCP Tool: upsert_mr_suap_meta]    — insere bloco suap-meta na descrição do MR
[MCP Tool: post_gitlab_mr_comment] — posta spec delta proposto (comment estruturado)
    │
    ▼
GitLab MR
    │  Dev: 👍 aprovação ou reply com versão corrigida
    │
    ▼ (merge para main)
[CI Job: update-demanda-spec]
    │  Lê MR → extrai demanda_id → encontra comment aprovado
    │  POST /api/demandas/{id}/spec-decisions/
    ▼
SUAP DB → DecisaoEspecificacao criada (origem: "agente-ci")
    │
    ▼
[get_demanda_context] — próxima sessão já vê spec atualizada
```

**Princípio:** tools MCP são chamadas HTTP pequenas e focadas. O LLM (agente) faz a análise semântica ("o que mudou nas regras de negócio?"). O CI job é lógica determinística, sem LLM.

---

## 4. Fluxo Detalhado

### 4.1 Fase 1 — Dev abre MR com agente

```
1. Dev: "abre MR para a demanda 123"
2. Agente: open_mr_for_demanda → cria MR no GitLab
3. Agente: get_gitlab_mr_diff → lê diff completo
4. Agente: get_demanda_context → lê spec atual, DoD, decisões anteriores
5. Agente: analisa se há mudanças de regra de negócio no diff
6. Agente: upsert_mr_suap_meta → insere na descrição do MR:

   <!-- suap-meta
   demanda_id: 123
   -->

7. Agente: post_gitlab_mr_comment → posta comment estruturado:

   ## 🤖 Proposta de Spec — Demanda #123
   ### Resumo das mudanças
   [gerado a partir do diff + spec atual]
   ### Delta proposto
   [texto a adicionar na especificação técnica]
   Para aprovar: 👍 neste comment
   Para editar: responda com sua versão corrigida
   Para ignorar: 🚫 neste comment
   <!-- spec-delta: {"demanda_id": 123, "status": "proposed"} -->
```

### 4.2 Fase 2 — Dev revisa no GitLab

```
8. Dev avalia o comment do agente.
   - Aprovado sem edição   → 👍 no comment do agente
   - Quer ajustar          → reply com versão corrigida
   - Não se aplica         → 🚫 ou simplesmente ignora
9. MR passa por code review normal, aprovação GitLab, pipeline verde.
10. Dev mergea o MR.
```

### 4.3 Fase 3 — CI job no merge (automático)

```
11. Pipeline na main é disparado.
12. Job update-demanda-spec executa:
    a. CI_COMMIT_SHA → GitLab API → encontra o MR mergeado
    b. Lê descrição do MR → extrai demanda_id do bloco suap-meta
       Fallback: regex no nome da branch (demanda-(\d+)-...)
       Se não encontrar → posta warning no commit, exit 0
    c. Busca comment com <!-- spec-delta --> no MR
       Se não encontrar → exit 0 silencioso
    d. Detecta sinal de aprovação:
       - 👍 reaction      → usa conteúdo do comment original
       - Reply do dev     → usa texto do último reply
       - 🚫 reaction      → pula, exit 0
       - Nenhum sinal     → posta comment de aviso no MR, exit 0
    e. POST /api/demandas/{id}/spec-decisions/
       { "decisao": <texto aprovado>,
         "origem": "agente-ci",
         "contexto": {"mr_iid": 42, "commit_sha": "abc123"} }
13. DecisaoEspecificacao criada. Spec atualizada.
```

---

## 5. Degradação Graciosa

| Situação | Comportamento |
|---|---|
| MR criado manualmente sem suap-meta | Dev adiciona o bloco `<!-- suap-meta -->` na descrição; CI funciona normalmente |
| `demanda_id` errado | Dev edita o bloco na descrição e re-roda o pipeline manualmente |
| Demanda não existe no SUAP (404) | CI posta warning no commit, exit 0 |
| MR de infra/chore sem demanda | Sem bloco `suap-meta` → CI silencioso, exit 0 |
| Dev não quer atualizar spec | Reage com 🚫 ou não interage com o comment |
| Nenhum sinal de aprovação no comment | CI avisa no MR mas não bloqueia merge |

---

## 6. Novos Componentes

### Phase 7 — suap-mcp: nova ferramenta + prompt atualizado

#### `upsert_mr_suap_meta` (`gitlab/tools.py`)

```
Input (herda de GitLabProjectInput):
  context_url: HttpUrl   # qualquer URL no host GitLab alvo — resolve contexto
  project_path: str      # ex: "cosinf/suap"
  mr_iid: int
  demanda_id: int

Ação:
  GET /projects/:path/merge_requests/:mr_iid → lê descrição atual
  Insere/substitui bloco <!-- suap-meta\ndemanda_id: X\n--> sem sobrescrever o resto
  PUT /projects/:path/merge_requests/:mr_iid → atualiza descrição

Anotações MCP:
  readOnlyHint: False
  idempotentHint: True   (re-executar com mesmo demanda_id é seguro)
  destructiveHint: False
```

#### `demanda-workflow` prompt atualizado (`modules/demandas/prompts.py`)

Adicionar ao prompt existente a sequência de enriquecimento de MR:

```
1. get_demanda_context         → spec atual, DoD, decisões
2. get_gitlab_mr_diff          → o que mudou no código
3. [LLM analisa]               → identifica mudanças de regra de negócio
4. upsert_mr_suap_meta         → garante suap-meta na descrição
5. post_gitlab_mr_comment      → posta delta proposto com instruções de aprovação
```

---

### Phase 8 — suap: CI job

#### `bin/scripts/update_demanda_spec.py`

Script Python standalone. Dependências: `httpx`, `python-gitlab` (ou requests diretos).

Variáveis de ambiente esperadas:
- `SUAP_TOKEN` — token de serviço CI (não token pessoal do dev)
- `GITLAB_TOKEN` — `CI_JOB_TOKEN` (disponível automaticamente no CI)
- `CI_COMMIT_SHA` — fornecido pelo GitLab CI
- `CI_PROJECT_ID` — fornecido pelo GitLab CI
- `SUAP_BASE_URL` — ex: `https://suap.ifrn.edu.br`
- `GITLAB_BASE_URL` — ex: `https://gitlab.ifrn.edu.br`

#### `.gitlab-ci.yml` — novo job

```yaml
update-demanda-spec:
  stage: post-merge
  rules:
    - if: '$CI_COMMIT_BRANCH == "main" && $CI_PIPELINE_SOURCE == "push"'
  variables:
    SUAP_TOKEN: $SUAP_CI_TOKEN
    GITLAB_TOKEN: $CI_JOB_TOKEN
  script:
    - python bin/scripts/update_demanda_spec.py
  allow_failure: true   # nunca bloqueia o pipeline principal
```

`SUAP_CI_TOKEN` é configurado como CI variable protegida no GitLab (escopo: grupo ou projeto).

---

### Phase 9 — suap: endpoint de fallback (opcional)

#### `GET /api/demandas/by-mr/?mr_iid=X`

- Retorna a demanda cujo `id_merge_request == X`
- Usado pelo CI quando o bloco `suap-meta` não está na descrição (MR criado manualmente)
- Sem esse endpoint, MRs manuais sem `suap-meta` são ignorados — comportamento aceitável
- Pode ser implementado em iteração futura sem impactar as Phases 7–8

---

## 7. Resumo de Artefatos

| Artefato | Fase | Projeto | Ação |
|---|---|---|---|
| `src/suap_mcp/gitlab/tools.py` | 7 | suap-mcp | Adicionar `upsert_mr_suap_meta` |
| `src/suap_mcp/modules/demandas/prompts.py` | 7 | suap-mcp | Atualizar `demanda-workflow` |
| `src/suap_mcp/server.py` | 7 | suap-mcp | Registrar `upsert_mr_suap_meta` |
| `bin/scripts/update_demanda_spec.py` | 8 | suap | Criar script CI |
| `.gitlab-ci.yml` | 8 | suap | Adicionar job `update-demanda-spec` |
| `demandas/api.py` | 9 | suap | Adicionar `GET /api/demandas/by-mr/` (opcional) |

---

## 8. Fora do Escopo

- Reescrita completa do campo `especificacao_tecnica` — o fluxo usa apenas `DecisaoEspecificacao` (append-only). Reescrever o texto principal da spec é uma ação humana deliberada.
- UI de inbox de decisões pendentes no SUAP — revisão acontece no GitLab.
- Suporte a múltiplas demandas por MR — um MR tem exatamente um `demanda_id`.
- Análise de diff por LLM no CI job — o CI é determinístico; a análise semântica é responsabilidade do agente na Fase 1.
