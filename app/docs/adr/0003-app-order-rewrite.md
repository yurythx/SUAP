# ADR-0003 — Reescrita de `INSTALLED_APPS` em comandos de schema

- **Status:** aceito
- **Data:** 2026-05-25 (registro retroativo)
- **Decisores:** equipe COSINF/IFRN

## Contexto

Django carrega apps na ordem listada em `INSTALLED_APPS` e resolve dependências entre migrations seguindo essa ordem. O SUAP precisa que `djtools` carregue **antes** de `django.contrib.admin` em runtime (para que `ModelAdminPlus` substitua o admin padrão e os campos `Plus` estejam disponíveis na renderização). Por outro lado, `makemigrations` e `migrate` precisam de uma ordem diferente, garantindo que:

- Apps de baixo nível (`comum`, `rh`, `edu`) materializem suas tabelas antes dos dependentes.
- Apps "pós" — utilitários, logs, integrações — fechem a cadeia depois.

Manter manualmente uma única lista que satisfaça as duas restrições é frágil: qualquer reorganização ergonômica em runtime quebra a topologia de migrations, e vice-versa.

## Decisão

Manter duas perspectivas separadas:

- **Em `suap/settings_base.py`:** uma `INSTALLED_APPS` otimizada para runtime, com `djtools` no início e o restante na ordem que faz sentido para carregamento e overrides de admin.
- **Em `suap/__init__.py`:** um hook que detecta os comandos `makemigrations`, `migrate` e `sync` e **reescreve** `INSTALLED_APPS` para `PRE_INSTALLED_APPS_SUAP + APPS_SUAP + POS_INSTALLED_APPS_SUAP`. Essa é a topologia que respeita as dependências de migração declaradas em `module_dependencies.json`.

Em runtime normal (`runserver`, gunicorn, pytest), a reescrita **não** acontece — a ordem do `settings_base.py` vale.

## Consequências

**Positivas**

- Migrations geradas têm grafo de dependência previsível e estável.
- Runtime mantém `djtools` antes de `django.contrib.admin`, preservando o admin custom.
- Adicionar/remover um app é uma operação local: atualizar `APPS_SUAP` em `settings_base.py` e o `module_dependencies.json`. O comando `python manage.py module_dependencies --check --all` valida que os dois batem.

**Negativas / a aceitar**

- Comportamento "mágico" em `suap/__init__.py`: alguém que `print(settings.INSTALLED_APPS)` durante `migrate` vê uma lista diferente de quando roda `runserver`. Causa surpresa em onboarding.
- Adicionar um comando custom que também precise da ordem "pós-reescrita" exige editar o gatilho em `suap/__init__.py`. Hoje só os três comandos canônicos são contemplados.
- Difícil testar diretamente: a reescrita acontece a partir de `sys.argv`, não de uma flag explícita.

## Alternativas rejeitadas

- **Manter uma única `INSTALLED_APPS` que sirva para tudo.** Tentado; quebra ou as migrations, ou o override de admin.
- **Mover `djtools` para `POS_INSTALLED_APPS_SUAP`.** Faria o admin custom não funcionar em runtime.
- **Usar `MIGRATION_MODULES` para forçar ordem.** Resolve parte da topologia, mas não resolve a ordem de carregamento de `AppConfig` em runtime.

## Como tocar nessa decisão

Reabrir antes de:

- Adicionar um quarto comando que precise da reescrita.
- Trocar o mecanismo de detecção (`sys.argv` → flag explícita ou variável de ambiente).
- Reorganizar `PRE_INSTALLED_APPS_SUAP` / `POS_INSTALLED_APPS_SUAP` de modo que o invariante "djtools antes de admin" deixe de valer.

Adicionar um app dentro de `APPS_SUAP` e atualizar `module_dependencies.json` **não** exige nova ADR.
