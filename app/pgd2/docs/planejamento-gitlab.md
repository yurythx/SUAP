# Planejamento — Integração GitLab (pgd_gitlab.py)

## Contexto

O módulo `pgd2/pgd_gitlab.py` consulta a [API de eventos do GitLab][eventos-api]
(`/api/v4/users/{id}/events`) para registrar contribuições de um servidor no SUAP.
A função `get_contribuicoes(mes, ano)` retorna todos os eventos do usuário num período,
filtrados ao projeto SUAP.

[eventos-api]: https://docs.gitlab.com/api/events/

---

## Funcionalidades implementadas

### `get_contribuicoes(mes, ano)`
Busca todos os eventos do usuário no período via `/api/v4/users/{id}/events`.
Retorna lista de `acoes` com campos: `id`, `created_at`, `action_name`, `target_type`,
`target_iid`, `target_title`, `detalhes`.

### `get_work_item(issue_iid)`
Busca detalhes de uma issue via `/api/v4/projects/{id}/issues/{iid}`.

### `get_issues_vinculado(mes, ano)` ✅ implementado
Retorna issues em que o usuário está vinculado como **assignee** no período.
- Endpoint: `/api/v4/projects/{id}/issues?assignee_id=...&updated_after=...&updated_before=...`
- Retorno: `list[dict]` com `iid`, `title`, `web_url`, `state`
- Paginação automática via `x-total-pages`

### `get_issues_comentadas(acoes)` ✅ implementado
Recebe o resultado de `get_contribuicoes` e retorna issues em que o usuário **comentou**
no período (estando assignee ou não).
- Fontes: `target_type='Note'` + `note.noteable_type in ('Issue','WorkItem')`;
  e `target_type='WorkItem'` + `action_name='commented on'`
- Retorno: `dict[iid, {'iid', 'title'}]` deduplicado

### `get_issues_outras_acoes(acoes)` ✅ implementado
Recebe o resultado de `get_contribuicoes` e retorna issues em que o usuário realizou
**qualquer outra ação** (exceto comentários), especificando quais ações foram.
- Critério: `target_type='WorkItem'` e `action_name != 'commented on'`
- Retorno: `dict[iid, {'title', 'acoes': list[str]}]`

---

## Próximos passos / backlog

- [ ] **Issues vinculadas a milestone de bugs** — filtrar `get_issues_vinculado` (ou
  `get_issues_outras_acoes`) pelas issues cuja milestone contenha "bugs"; requer chamada
  a `get_work_item` por issue para verificar `milestone`.
- [ ] **MergeRequests** — ampliar as funções para cobrir `target_type='MergeRequest'`
  além de `WorkItem`, caso necessário para relatórios de PGD.
- [ ] **Configuração dinâmica de usuário** — remover o `_gitlab_username` hardcoded e
  receber o username como parâmetro (ou vincular ao `Servidor` do PGD2).
- [ ] **Cache de eventos** — evitar múltiplas chamadas à API quando várias funções
  processam o mesmo período; considerar memoização ou passar `acoes` já carregadas.
- [ ] **Integração com relatório de PGD** — expor os resultados dessas funções numa view
  ou endpoint da API para compor o relatório mensal de atividades GitLab do servidor.
