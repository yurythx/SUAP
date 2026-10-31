# Sentry SUAP-VPA: OU pai ausente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sincronizar OU pai ausente antes de mover OU filha no LDAP.

**Architecture:** Concentrar recuperação em `LdapConf.sync_ou`, caminho comum de sincronização de OUs e usuários. Ao receber `NO_SUCH_OBJECT`, sincronizar setor superior e repetir mesma operação, preservando tratamento existente para `OTHER`.

**Tech Stack:** Django, python-ldap, pytest, pre-commit.

## Global Constraints

- Alterar somente `ldap_backend/models.py` para correção funcional.
- Não criar/modificar testes neste commit; `generate-test` cobre MR separadamente.
- Manter tratamento de exceções LDAP restrito a OU pai ausente.

---

### Task 1: Recuperar OU pai antes de mover filha

**Files:**

- Modify: `ldap_backend/models.py:446-489`
- Test: suite existente de `ldap_backend/` (sanidade; nenhum teste novo)

**Interfaces:**

- Consumes: `LdapConf.sync_ou(newdn, description, admin_description, setor, test_mode=True, force=False)`.
- Produces: mesma assinatura; move da OU é repetido após sincronização recursiva do superior.

- [x] **Step 1: Confirmar comportamento atual no Sentry**

Verificar evento `SUAP-VPA`: `move_object` falha com `ldap.NO_SUCH_OBJECT` ao mover
`COSEFIN-RE` para `DCF-RE` inexistente.

- [x] **Step 2: Implementar recuperação mínima**

Alterar ramo de exceção de `sync_ou` para incluir `ldap.NO_SUCH_OBJECT`. Quando
`setor.superior` existir, chamar `sync_ou_setor(setor.superior, ...)` e repetir
`sync_ou(newdn, description, admin_description, setor, ...)`; sem superior,
relançar exceção.

- [x] **Step 3: Rodar sanidade existente**

Run: `pytest -q ldap_backend/`

Expected: suite termina sem regressão atribuível ao patch.

Resultado: bloqueado antes da coleta por ausência de `suap/settings.py` no
worktree; o arquivo é configuração local não versionada.

- [x] **Step 4: Rodar gate de commit**

Run: `ruff format ldap_backend/models.py && ruff check ldap_backend/models.py --fix --unsafe-fixes && uv run pre-commit run --from-ref origin/master --to-ref HEAD`

Expected: formatador, lint e hooks passam.

- [ ] **Step 5: Commit e MR**

Criar commit `fix(ldap_backend): sincronizar OU pai antes do move` com `Refs: SUAP-VPA`; enviar branch e abrir MR com link da issue Sentry e nota de cobertura delegada ao `generate-test`.
