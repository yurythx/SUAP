---
trigger: always_on
description: Guardrails operacionais do SUAP (terminal, uv, migrations, design system, pytest, .env)
---

# Guardrails operacionais - Python, Django ORM & SUAP Stack

## 1. Loop Prevention & Terminal Discipline (Fail-Safe)
- **Max Retry Rule:** Se qualquer comando no terminal (testes, migrations, check ou linter) falhar 2 vezes consecutivas pelo mesmo motivo ou erro, PARE IMEDIATAMENTE. Não tente uma 3ª execução. Analise o traceback, apresente suas hipóteses no chat e aguarde instruções antes de rodar outro comando.
- **No Blocking/Interactive Processes:** NUNCA execute comandos que mantenham o processo aberto ou bloqueiem o stdout:
  - Proibido: `python manage.py runserver`, `tail -f`, `docker compose up` sem `-d`, ou shells interativos (`python manage.py shell`).
  - Use apenas comandos com término determinístico.
- **Inspect Logs First:** Diante de um traceback ou falha de teste, leia o log completo e o trecho de código correspondente antes de disparar alterações. Não faça tentativas especulativas às cegas.

## 2. Environment & Execution Integrity
- **Virtual Environment & uv First:** Todos os comandos Python devem rodar com o gerenciador `uv` ou no venv local:
  - Prefira `uv run python manage.py <comando>` ou o caminho explícito: `./.venv/bin/python manage.py <comando>`.
  - Nunca execute comandos com `sudo`.
  - Nunca execute `pip install` nem altere dependências com `uv add`/`uv sync` sem solicitação expressa do usuário. O projeto é gerenciado via `uv` com `uv.lock`. Se uma biblioteca estiver faltando, informe no chat primeiro.

## 3. Django ORM & Migration Discipline
- **Two-Step Migration Workflow:**
  1. **Geração Pontual:** Ao alterar models, execute a migração apenas para o app modificado: `python manage.py makemigrations <app_name>`.
  2. **Inspeção Prévia:** Abra e inspecione o arquivo gerado dentro de `<app_name>/migrations/` para confirmar que apenas as mudanças desejadas foram detectadas antes de aplicar.
  3. **Aplicação Local:** Execute `python manage.py migrate <app_name>`.
- **Never Edit Applied Migrations:** NUNCA altere arquivos de migração que já foram aplicados anteriormente ou que façam parte do histórico estável do repositório. Para qualquer mudança de schema, gere sempre uma nova migração sequencial.
- **Strictly No Destructive Commands:** É expressamente proibido executar:
  - `python manage.py flush`
  - `python manage.py reset_db`
  - `python manage.py migrate <app_name> zero` (rollback total)
  - Comandos SQL diretos com `DROP`, `TRUNCATE` ou deleção em massa sem autorização prévia.
- **Non-destructive Model Changes:** Ao adicionar campos não nulos (`null=False`) em models existentes que já possuem registros, sempre defina um `default` explícito para evitar prompts interativos no terminal durante o `makemigrations`.

## 4. UI, Templates & SUAP Design System
- **Mandatory Reference:** Ao criar ou modificar templates HTML/Django templates (`.html`), consulte e siga rigorosamente as diretrizes documentadas em `docs/design-system.md`.
- **Component & Class Consistency:** Utilize exclusivamente os componentes, classes utilitárias, botões, modais, alertas e convenções de layout especificados pelo Design System do SUAP.
- **No Arbitrary Styles:** Não crie estilos inline (`style="..."`) nem classes CSS arbitrárias (Bootstrap puro, Tailwind, etc.) fora dos padrões estabelecidos em `docs/design-system.md`.
- **Template Inheritance & Blocks:** Respeite a estrutura de herança padrão do SUAP (extensão do template base correto, blocos de conteúdo e cabeçalhos de página previstos no guia).

### 4.1. Django Forms & SUAP UI Standardization
- **No Default Rendering:** NUNCA utilize `{{ form.as_p }}`, `{{ form.as_table }}` ou `{{ form.as_ul }}`.
- **Formulários Padronizados (Regra de Ouro):**
  - Conforme a Regra Inquebrável 5 de `docs/design-system.md`, formulários devem ser renderizados via `{% render_form form %}` (tag do `djtools`), **sem montar `<input>` à mão**.
  - No Python, formulários devem herdar preferencialmente de `djtools.forms.FormPlus` ou `ModelFormPlus`.
- **Button Row & Actions:**
  - As ações **Visualizar**, **Editar** e **Remover** (nunca "Excluir", conforme a regra de nomenclatura institucional) em tabelas devem ficar exclusivamente na primeira coluna com o cabeçalho **Ações** (ex.: `{% icon "view" url %}`, `{% icon "edit" url %}`, `{% icon "delete" url %}`). Demais ações devem ficar na última coluna com o cabeçalho **Opções**.


## 5. Targeted Testing (pytest)
- **Always Use pytest, Never manage.py test:** O SUAP usa estritamente `pytest`, NUNCA `python manage.py test`. Os testes dependem da infraestrutura do pytest (`--no-migrations`, `conftest.py` com extensões PG, etc.).
- **Never Run Full Suite Automatically:** Nunca execute a suíte inteira do projeto (`pytest` sem parâmetros) para validar edições pontuais.
- **Targeted Test Execution:**
  - Teste pontual com pytest: `uv run pytest path/to/test_file.py -k test_nome_especifico -s --tb=short` ou `uv run pytest path/to/test_file.py::TestClass::test_method`
  - Um módulo/app específico: `uv run pytest -q app_name`
  - Quando necessário apontar para Postgres de teste: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --reuse-db <app_name>`
- **Database Safety in Tests:** Assegure-se de que os testes rodem exclusivamente contra o banco de testes isolado (`pytest` com `--reuse-db` / `--create-db`), nunca tocando o banco de dados de desenvolvimento.

## 6. Secrets & Environment Safety (.env Discipline)
- **Never Read Secrets Directly:** NUNCA leia arquivos de variáveis de ambiente com ferramentas de leitura ou cat (`.env`, `.env.local`, `.env.production`).
- **Use Template for Reference:** Para consultar quais variáveis de ambiente o sistema espera, consulte estritamente `.env.dev.sample`, `suap/settings_sample.py` ou `docs/variaveis-ambiente.md`.
- **No Hardcoded Secrets:** Nunca insira chaves de API, senhas de banco ou o `SECRET_KEY` diretamente nos arquivos de código ou fixtures de teste. Utilize sempre `os.environ`, `python-decouple`, `django-environ` ou a biblioteca de settings em uso.

## 7. Token Conservation & Code Standards
- **Forbidden Directories:** Nunca leia, analise ou edite arquivos dentro de:
  - `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
  - `.venv/`, `env/`, `venv/`, `dist/`, `build/`, `staticfiles/`, `media/`
  - Migrações antigas consolidadas, a menos que seja explicitamente solicitado analisar o histórico do schema.
- **Minimal Diffs:** Ao modificar código, altere apenas os blocos estritamente necessários. Mantenha os padrões arquiteturais do SUAP/Django.
- **Complexity & Boundary-Typing Guardrails:**
  - **Complexidade Ciclomática ≤ 10:** Mantenha a complexidade das funções tocadas sempre ≤ 10 (`ruff C901`; checagem em `.agents/hooks/check_complexity.py`, ver `AGENTS.md`). Se passar de 10, refatore antes de prosseguir.
  - **Tipagem progressiva (boundary-typing):** Ao editar funções Python, anote tipos (parâmetros + retorno) nas defs tocadas.
- **Fast Syntax & Type Checks:** Para validações rápidas de sintaxe antes de rodar testes pesados, use comandos focados no arquivo editado:
  - `uv run ruff check path/to/file.py`
  - `uv run python manage.py check <app_name>`
