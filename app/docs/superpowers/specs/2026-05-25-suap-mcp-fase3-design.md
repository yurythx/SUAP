# SUAP MCP — Fase 3: Endpoints Ninja de Leitura

**Data:** 2026-05-25
**Escopo:** Quatro endpoints Django Ninja read-only para o módulo de demandas. Sem escrita, sem lógica MCP — isso vem nas Fases 4 e 5.
**Próximo passo:** Fase 4 — endpoints de escrita (`merge-request`, `spec-decisions`).

---

## 1. Endpoints

### `GET /api/demandas/{id}/agent-context/`

Contexto completo da demanda para o agente. Agrega três fontes de spec:

- `especificacao_tecnica` (campo de texto da Demanda)
- `dod` — primeiro DoD via `dod_set.first()` com `especificacao_set` prefetchado.
  Se não houver DoD, `dod` é `null`. Se houver mais de um (raro mas possível), usa
  apenas o primeiro ordenado por `pk`.
- `decisoes_especificacao` — todos os registros `DecisaoEspecificacao` da demanda
  ordenados por `criado_em` (já definido no `Meta.ordering`).

Também inclui resumo das sub-demandas diretas e campos GitLab.

### `GET /api/demandas/{id}/subdemandas/`

Lista hierárquica das sub-demandas diretas, via `demanda.get_subdemandas()`.
Inclui `id`, `titulo`, `situacao` e `percentual_conclusao` de cada sub-demanda.
Não é recursivo (sub-sub-demandas não são incluídas — o agente pode chamar o
endpoint novamente com o `id` da sub-demanda).

### `GET /api/demandas/{id}/mr-status/`

Retorna o estado do MR **conforme registrado no banco** (não chama o GitLab).

**Justificativa do DB-only:** Phase 3 é "read-only first". Chamadas ao GitLab
introduzem latência, falhas externas e autenticação de serviço fora do escopo.
A redundância com `agent-context` é intencional: o agente pode chamar `mr-status`
quando precisa checar apenas o MR sem carregar o contexto completo.

Retorna `mr_url` construída com base no `gitlab_url` configurado no SUAP +
`id_merge_request`, ou `null` se não houver MR.

### `GET /api/entregas/{id}/pipeline-status/`

Retorna o estado da entrega **conforme registrado no banco** (não chama o GitLab).
O `pipeline_id` é o ID do pipeline no GitLab — o agente usa esse ID para consultar
o GitLab diretamente se precisar do status ao vivo.

Erro `pipeline_not_linked` se `entrega.pipeline_id` for `None`.

---

## 2. Autenticação

`auth=JWTAuth()` (de `djtools.ninja.auth`) em todos os endpoints.
Decisão da Fase 1: JWT por desenvolvedor via keychain.

---

## 3. Permissões

### Demanda

`Demanda.permite_visualizar(user)` — verifica `atende_demanda`, `change_demanda`
ou `view_demanda`. **É uma permissão de projeto, não por demanda individual.**
Ou seja: quem pode ver uma demanda pode ver todas.

Pergunta aberta: isso é intencional? Desenvolvedores que atuam via agente
presumivelmente têm `atende_demanda`. Se a intenção for restringir por demanda
(checando `eh_demandante`, `privada`, etc.), isso pode ser adicionado como uma
segunda camada aqui. **Aguarda confirmação do usuário.**

Por ora, aplica apenas `permite_visualizar`.

### Entrega

Não há `permite_visualizar` em `Entrega`. Delegamos para:
`entrega.demanda.permite_visualizar(user)`.

---

## 4. Contrato de erro (Fase 1)

| `error` | Endpoint | HTTP | `hint` |
|---|---|---|---|
| `demanda_not_found` | todos de demanda | 404 | "Verifique se o ID da demanda está correto" |
| `permission_denied` | todos | 403 | "Seu JWT não tem permissão para esta demanda" |
| `entrega_not_found` | pipeline-status | 404 | "Verifique se o ID da entrega está correto" |
| `pipeline_not_linked` | pipeline-status | 422 | "Esta entrega não tem pipeline associado" |

---

## 5. Roteamento

Criamos dois arquivos novos, um por namespace:

- `api/endpoints/demandas.py` — `router.api_url_prefix = 'demandas'`
- `api/endpoints/entregas.py` — `router.api_url_prefix = 'entregas'`

Modificamos `suap/api.py` para incluir `'demandas'` e `'entregas'` na lista de
áreas carregadas dinamicamente.

---

## 6. Schemas

### `EspecificacaoSchema`
```
nome: str
atividades: str
ordem: int
gitlab_issue_url: str | None
```

### `DodSchema`
```
descricao: str | None
especificacoes: list[EspecificacaoSchema]
```

### `DecisaoEspecificacaoSchema`
```
id: int
autor: str          # nome do usuário (resolve via user.get_full_name())
criado_em: datetime
decisao: str
contexto: dict
origem: str         # 'manual' | 'agente'
```

### `SubdemandaSchema`
```
id: int
titulo: str
situacao: str
percentual_conclusao: int
```

### `AgentContextSchema`
```
id: int
titulo: str
situacao: str
especificacao_tecnica: str
branch: str | None
id_merge_request: int | None
subdemandas: list[SubdemandaSchema]
dod: DodSchema | None
decisoes_especificacao: list[DecisaoEspecificacaoSchema]
```

### `MRStatusSchema`
```
demanda_id: int
branch: str | None
id_merge_request: int | None
situacao: str
mr_url: str | None
```

### `PipelineStatusSchema`
```
entrega_id: int
pipeline_id: int | None
branch: str | None
id_merge_request: int | None
status: str
```

### `ErrorSchema`
```
error: str
hint: str
context: dict
```

---

## 7. Testes

Diferidos, igual à Fase 2 — aguardando migração para pytest. Cenários ficam
documentados no plano de implementação para referência futura.

---

## Resumo

| Artefato | Ação |
|---|---|
| `api/schemas/demandas.py` | Criar |
| `api/endpoints/demandas.py` | Criar |
| `api/endpoints/entregas.py` | Criar |
| `suap/api.py` | Modificar — adicionar `demandas` e `entregas` na lista |
