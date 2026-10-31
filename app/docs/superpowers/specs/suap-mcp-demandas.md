# SUAP MCP — Integração com módulo de Demandas

> Cole este documento em uma nova sessão do Claude Code, no diretório raiz do
> projeto SUAP. Com Superpowers instalado, a skill de brainstorming/spec deve
> ativar automaticamente. Não tente trigar skills manualmente.

## Contexto

Estamos estendendo o `suap-mcp` existente (referenciado em `.mcp.json`) com
primitivas do módulo de **Demandas**. O objetivo é fechar o ciclo
`demanda → código → MR → especificação`, permitindo que agentes de código
operem com conhecimento pleno do domínio.

**O que já existe no SUAP (não reimplementar):**

- Modelo `Demanda` em `demandas/models/demanda.py` com campos `branch` e
  `id_merge_request`.
- Método `Demanda.criar_mergerequest_gitlab()` que já monta título, descrição,
  target branch, squash, remove source branch e assignee.
- Hierarquia de sub-demandas (`Demanda` ⟶ `Subdemanda`).
- Modelo `Entrega` com `pipeline_id`, `branch` e `id_merge_request`.
- `django-reversion` para histórico de alterações.
- `sentry_sdk` com `capture_exception` para erros.
- Django Ninja para API (`/api/`).
- `suap-mcp` já configurado em `.mcp.json`.

**Convenções do projeto a respeitar:**

- Views são function-based, decoradas com `@rtr()`, retornam `locals()`.
- Forms herdam de `FormPlus` / `ModelFormPlus`.
- Models usam `ModelPlus`, `ForeignKeyPlus`, `CharFieldPlus` do `djtools`.
- Lógica de negócio fica em `services.py`, usando `transaction.on_commit`
  para efeitos externos.

## Problema

Hoje o ciclo de desenvolvimento envolve dois contextos desconectados:
a especificação da demanda (no SUAP) e o MR no GitLab. O agente opera sem
visibilidade sobre nenhum dos dois. Isso causa:

1. Contexto perdido a cada sessão de trabalho.
2. Especificação que não evolui com decisões tomadas durante a implementação.
3. Abertura de MR manual e despadronizada.

## Solução (escopo do MVP)

Estender o `suap-mcp` existente com as seguintes ferramentas:

| Ferramenta | Operação | Idempotência |
|---|---|---|
| `get_demanda_context(id)` | Lê demanda + sub-demandas + spec atual + status do MR | leitura |
| `get_subdemandas(id)` | Lista hierárquica de sub-demandas | leitura |
| `open_mr_for_demanda(id)` | Abre MR via `criar_mergerequest_gitlab()` existente | sim — retorna MR existente se já houver |
| `append_spec_decision(id, decisao, contexto)` | Registra decisão arquitetural na spec (append-only, com autoria e timestamp) | não — append |
| `get_demanda_mr_status(id)` | Status do MR vinculado à demanda | leitura |
| `get_entrega_pipeline_status(entrega_id)` | Status do pipeline da entrega | leitura |

**Princípios não-negociáveis:**

- **Sem regra de negócio duplicada no MCP.** O MCP é fachada fina sobre a API
  Django Ninja. Toda lógica de domínio vive no SUAP.
- **Append-only para spec.** Nada de `update_spec` livre. Decisões viram
  registros estruturados (tipo ADR) com autor, timestamp e contexto.
- **Autoria correta.** Toda chamada carrega a identidade do usuário em nome
  de quem o agente atua — não o token de serviço. O `django-reversion` precisa
  registrar o usuário real; o assignee do MR deve ser o desenvolvedor.
- **Contrato de erro acionável.** Todo erro do MCP retorna `error`, `hint`
  e contexto suficiente para o agente saber o próximo passo. Ex.:
  `{"error": "branch_missing", "hint": "Crie a branch X antes de chamar open_mr_for_demanda", "demanda_id": 123}`.
- **Idempotência explícita.** Operações de escrita declaram seu contrato:
  se o recurso já existe, retornam o existente em vez de duplicar.

## Arquitetura em três camadas

1. **API — Django Ninja (no SUAP)**
   Endpoints de caso de uso (não CRUD genérico):
   - `GET /api/ti/demandas/{id}/agent-context`
   - `GET /api/ti/demandas/{id}/subdemandas`
   - `POST /api/ti/demandas/{id}/merge-request`
   - `POST /api/ti/demandas/{id}/spec-decisions`
   - `GET /api/ti/demandas/{id}/mr-status`
   - `GET /api/ti/entregas/{id}/pipeline-status`

   Cada endpoint aplica permissão, auditoria e validação. Chama os
   `services.py` / métodos de modelo existentes.

2. **MCP Server — extensão do `suap-mcp` existente**
   Adapta as ferramentas listadas acima sobre os endpoints Ninja.
   Sem lógica de negócio. Apenas tradução do protocolo MCP para HTTP +
   tradução de erros HTTP para o formato acionável do agente.

3. **Plugin / Slash commands — fase futura**
   `/demanda 123`, `/abrir-mr-demanda`, `/registrar-decisao`.
   Fora do escopo do MVP.

## Plano de execução sugerido

Trabalhe nesta ordem, uma fase de cada vez, com TDD onde aplicável:

**Fase 1 — Spec e contrato de erro**
- Definir o formato exato de erro do MCP (schema padrão).
- Definir o mecanismo de autoria (header de impersonação? token escopado?).
- Documentar o contrato de idempotência de cada ferramenta.

**Fase 2 — Modelo `DecisaoEspecificacao`**
- Novo modelo para registrar decisões arquiteturais da demanda.
- Campos: `demanda`, `autor`, `criado_em`, `decisao`, `contexto`, `origem`
  (manual / agente).
- Migration. Sem alterar a spec textual existente — decisões coexistem.

**Fase 3 — Endpoints Ninja (read-only primeiro)**
- `agent-context`, `subdemandas`, `mr-status`, `pipeline-status`.
- Permissões, testes.

**Fase 4 — Endpoints Ninja de escrita**
- `merge-request` (idempotente, chama `criar_mergerequest_gitlab()`).
- `spec-decisions` (append-only, cria `DecisaoEspecificacao`).
- Testes incluindo cenários de retry e duplicação.

**Fase 5 — Extensão do suap-mcp**
- Adicionar as 6 ferramentas como fachada sobre os endpoints.
- Mapeamento de erros HTTP → erros MCP acionáveis.
- Testes do servidor MCP.

**Fase 6 — Documentação e exemplos de uso**
- README do suap-mcp atualizado.
- Exemplos de prompts que usam as ferramentas.

## Como quero trabalhar

- Uma fase por vez. Não pule etapas.
- TDD: teste primeiro, código depois.
- Antes de codar, me apresente a spec da fase atual para revisão.
- Use os padrões do projeto (`@rtr()`, `services.py`, `transaction.on_commit`,
  `capture_exception`, `ModelPlus`, etc.).
- Prefira evolução incremental a reescrita.
- Se identificar conflito com algo existente no código, pare e me consulte
  antes de decidir.

## Primeira ação

Comece pela **Fase 1**. Brainstorme comigo o formato do contrato de erro
e o mecanismo de autoria. Não escreva código ainda.
