# ADR-0002 — Pytest sem migrações; schema vindo dos models

- **Status:** aceito
- **Data:** 2026-05-25 (registro retroativo)
- **Decisores:** equipe COSINF/IFRN

## Contexto

O SUAP tem ≈90 apps e centenas de migrations acumuladas. Aplicar todas em uma DB nova leva minutos. Rodadas locais e CI repetem esse custo várias vezes por dia. Além disso, migrations antigas referenciam código que não existe mais ou que mudou de assinatura, exigindo manutenção retroativa apenas para a suíte de testes passar.

Outras restrições:

- O projeto pinou Python 3.14, Django 5.2 e usa Postgres com extensões específicas (`unaccent`, `pg_trgm`, `pg_stat_statements`) e a colação ICU `ignore_accents_case`. Recriar esse estado via migrations é frágil.
- A suíte usa `pytest` (não `python manage.py test`), com fixtures pesadas (`suap_data`, `light_data`) que carregam grafos de objetos.

## Decisão

Em ambiente de testes:

1. Forçar `MIGRATE=False` e `--no-migrations` (configurado em `[tool.pytest.ini_options]`).
2. O schema é derivado direto dos models atuais via `syncdb`-like.
3. As extensões Postgres e o `f_unaccent`/colação são criados no `conftest.py` raiz, **antes** das fixtures de dados rodarem.
4. Sentry, Redis e Celery são forçados a "off" no `conftest.py` para isolar o teste.
5. Variáveis específicas de teste: `USUARIOGRUPO_AS_ABSTRACT=1`, `USE_EDU_LOG=False`.

Migrations existem **apenas** para o caminho de deploy. A suíte nunca as executa.

## Consequências

**Positivas**

- Suíte sobe em segundos, não minutos.
- Refactor de modelos não exige reescrever migrations só para o teste rodar.
- Testes refletem o estado *atual* do schema — não há "drift" entre model e migração no test runner.

**Negativas / a aceitar**

- Bugs específicos de migração (ex.: `RunPython` que quebra com schema novo) só aparecem em staging.
- Adicionar uma extensão Postgres exige editar `conftest.py` raiz, não basta uma migration.
- Devs precisam lembrar que `manage.py migrate` é etapa de deploy, não de "preparar o ambiente de teste".

## Alternativas rejeitadas

- **Rodar migrations com `pytest-django --create-db --reuse-db`.** Reduz, mas não elimina, o custo; mantém o problema de migrations quebradas.
- **`migrate --fake-initial` + squash periódico.** Squash em monolito desse tamanho é projeto próprio e introduz riscos sem o ganho proporcional na suíte.
- **Teste de migrações em job dedicado.** Ainda válido como ideia futura para uma fração das migrations recentes; não invalida esta ADR.

## Como tocar nessa decisão

Reabrir antes de:

- Habilitar migrations no `pytest`.
- Mover criação de extensão Postgres para fora do `conftest.py`.
- Introduzir fixture que assume estado intermediário de migração.

Adicionar uma extensão nova ou ajustar `USE_EDU_LOG` **não** exige nova ADR — basta editar `conftest.py`.
