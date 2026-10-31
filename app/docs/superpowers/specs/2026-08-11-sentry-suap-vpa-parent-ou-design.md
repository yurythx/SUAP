# Spec — Sentry SUAP-VPA: OU pai ausente no LDAP

- **Data:** 2026-08-11
- **Status:** Aprovado para implementação
- **Módulo-alvo:** `ldap_backend/`

## Objetivo

Evitar `ldap.NO_SUCH_OBJECT` ao mover uma OU para um novo superior ainda ausente
no AD. O caso observado move `COSEFIN-RE` para dentro de `DCF-RE`.

## Decisão

No fluxo compartilhado `LdapConf.sync_ou`, tratar `ldap.NO_SUCH_OBJECT` como
dependência de OU pai ausente: sincronizar `setor.superior` e repetir a
sincronização da OU atual. Manter tratamento existente de `ldap.OTHER`.

## Fluxo

`sync_user` → `sync_ou_setor` → `sync_ou` → falha de move → sincroniza pai →
repete `sync_ou` → move usuário.

## Fora de escopo

- Alterar fluxo de login ou upload de documento.
- Criar comportamento para erros LDAP não relacionados.
- Testes neste commit; serão gerados separadamente pelo `generate-test`.

## Critério de sucesso

Quando OU pai falta, ela é criada/sincronizada antes da OU filha e o usuário é
movido sem emitir `NO_SUCH_OBJECT`.
