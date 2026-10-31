# SUAP MCP — Fase 4: Endpoints Ninja de Escrita

**Data:** 2026-05-25
**Escopo:** Dois endpoints Django Ninja de escrita para o módulo de demandas. Sem lógica MCP — isso vem na Fase 5.
**Pré-requisito:** Fase 3 concluída (endpoints de leitura operacionais no branch `demanda_2227`).
**Próximo passo:** Fase 5 — extensão do suap-mcp com as 6 ferramentas MCP.

---

## 1. Endpoints

### `POST /api/demandas/{id}/merge-request/`

Abre um MR no GitLab para a demanda. **Idempotente**: se a demanda já tem `id_merge_request`, retorna o estado atual sem chamar o GitLab.

**Fluxo:**

1. Busca a demanda (404 se não existir).
2. Verifica permissão (403 se negado).
3. **Fast path idempotente**: se `demanda.id_merge_request` já está setado, retorna `200` com `already_exists: true` e os dados atuais — sem chamar o GitLab.
4. Verifica se `demanda.branch` está definida. Se não, retorna `422 branch_missing`.
5. Verifica se a branch existe no GitLab via `Demanda.branch_existe()`. Se não, retorna `422 branch_not_found`.
6. Chama `demanda.criar_mergerequest_gitlab()`.
7. Faz `demanda.refresh_from_db()` e verifica se `id_merge_request` foi preenchido.
   - Se não foi: retorna `422 mr_creation_failed` (método silenciou uma exceção internamente).
8. Retorna `201` com `already_exists: false` e os dados do MR.

**Nota sobre `criar_mergerequest_gitlab()`:** O método é void e exception-safe — não lança, apenas loga. Por isso a verificação de sucesso é feita via `refresh_from_db()` após a chamada. Não usamos `transaction.on_commit` aqui: a chamada é síncrona para que o endpoint possa conferir o resultado antes de responder.

**Request body:** Nenhum (operação determinística baseada nos dados da demanda).

**Responses:**

| HTTP | Condição |
|---|---|
| `200` | MR já existia (`already_exists: true`) |
| `201` | MR criado com sucesso (`already_exists: false`) |
| `403` | Sem permissão |
| `404` | Demanda não encontrada |
| `422` | Pré-condição falhou (`branch_missing`, `branch_not_found`, `mr_creation_failed`) |

---

### `POST /api/demandas/{id}/spec-decisions/`

Registra uma decisão arquitetural na demanda. **Append-only** — nenhum registro existente é modificado.

**Fluxo:**

1. Busca a demanda (404 se não existir).
2. Verifica permissão (403 se negado).
3. Valida o body (`decisao` não pode ser vazio).
4. Cria `DecisaoEspecificacao` com `autor=request.user`, `demanda=demanda`, e os campos do body.
5. Retorna `201` com os dados do registro criado.

**Request body:**
```json
{
  "decisao": "string (obrigatório, não-vazio)",
  "contexto": {},
  "origem": "agente"
}
```

`contexto` é opcional (padrão `{}`). `origem` é opcional (padrão `'agente'`; valores válidos: `'manual'` | `'agente'`).

**Responses:**

| HTTP | Condição |
|---|---|
| `201` | Decisão registrada |
| `403` | Sem permissão |
| `404` | Demanda não encontrada |
| `422` | Body inválido (ex: `decisao` em branco, `origem` fora das choices). **Formato:** gerado automaticamente pelo Ninja/Pydantic — não segue o contrato `{error, hint, context}` do projeto. |

---

## 2. Schemas

### `OpenMRResponseSchema`
```
demanda_id: int
branch: str | None
id_merge_request: int | None
situacao: str
mr_url: str | None
already_exists: bool
```

`mr_url` segue a mesma lógica de `MRStatusSchema` da Fase 3.

### `SpecDecisionInputSchema`
```
decisao: str             # obrigatório, não-vazio (validator)
contexto: dict = {}      # opcional
origem: str = 'agente'  # 'manual' | 'agente'
```

### `SpecDecisionResponseSchema`
```
id: int
demanda_id: int
autor: str               # get_full_name()
criado_em: datetime
decisao: str
contexto: dict
origem: str
```

---

## 3. Contrato de Erro (extensão da Fase 1)

| `error` | Endpoint | HTTP | `hint` |
|---|---|---|---|
| `demanda_not_found` | todos | 404 | "Verifique se o ID da demanda está correto" |
| `permission_denied` | todos | 403 | "Seu JWT não tem permissão para esta demanda" |
| `branch_missing` | merge-request | 422 | "Defina um branch para a demanda antes de abrir um MR" |
| `branch_not_found` | merge-request | 422 | "O branch '{branch}' não foi encontrado no GitLab" |
| `mr_creation_failed` | merge-request | 422 | "Falha ao criar o MR. Verifique os logs do SUAP" |

---

## 4. Autenticação e Permissões

**Autenticação:** `auth=JWTAuth()` — igual à Fase 3.

**Permissões:** *Ver Seção 6 (Questões Abertas).*

---

## 5. Artefatos

| Artefato | Ação |
|---|---|
| `api/endpoints/demandas.py` | Modificar — adicionar 2 endpoints `@post` |
| `api/schemas/demandas.py` | Modificar — adicionar 3 schemas novos |

Nenhum arquivo novo. Nenhuma migration. Nenhuma alteração em `suap/api.py` (já tem `demandas` na lista).

---

## 6. Questões Abertas

### Q1 — Permissões para escrita

Na Fase 3 usamos `demanda.permite_visualizar(user)`, que verifica `atende_demanda`, `change_demanda` ou `view_demanda`.

Para escrita há duas opções:

**A) Mesma permissão `permite_visualizar`**
- Zero código extra.
- Qualquer usuário com `view_demanda` pode abrir MR ou registrar decisão.

**B) Permissão mais restrita para escrita**
- Exigir `atende_demanda` ou `change_demanda` explicitamente.
- Usuários observadores (`view_demanda` apenas) não criam efeitos colaterais no GitLab.
- Requer verificação extra no endpoint.

**Recomendação:** Opção A por ora — o JWT já é de um desenvolvedor que atua na demanda, e o MCP não expõe esses endpoints a usuários externos.

### Q2 — Testes

A spec original da Fase 4 menciona explicitamente: *"Testes incluindo cenários de retry e duplicação."*

As Fases 2 e 3 diferiram testes aguardando a migração para pytest. Mantemos o defer ou implementamos agora?

**Recomendação:** Diferir. Os cenários de retry envolvem mock de chamadas GitLab, que é complexo sem o harness pytest configurado. Os cenários ficam documentados na Seção 7 para referência futura.

---

## 7. Cenários de Teste (documentados para referência)

**merge-request:**
- MR criado com sucesso → 201, `already_exists: false`
- MR já existe (`id_merge_request` setado) → 200, `already_exists: true`
- `branch` não definida → 422, `branch_missing`
- Branch não encontrada no GitLab → 422, `branch_not_found`
- `criar_mergerequest_gitlab()` silencia exceção, `id_merge_request` permanece null → 422, `mr_creation_failed`
- Usuário sem permissão → 403
- Demanda inexistente → 404

**spec-decisions:**
- Decisão criada com sucesso → 201, campos corretos incluindo `autor`
- Múltiplas decisões na mesma demanda (append) → todas persistem, nenhuma sobrescreve
- `decisao` em branco → 422
- `origem` fora das choices → 422
- Usuário sem permissão → 403
- Demanda inexistente → 404
