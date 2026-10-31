# Migração de call-sites: campos Pessoa/PessoaFisica → Vinculo (breaking)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development para executar fatia a fatia. Steps usam checkbox (`- [ ]`).

**Goal:** Reescrever ≈654 call-sites para lerem/escreverem os 8 campos via o VÍNCULO do papel/user, e remover os campos de Pessoa/PessoaFisica (RemoveField), sem quebra silenciosa.

**Architecture:** Chokepoint-first. `AbstractRelacionamento` (base de Servidor via AbstractFuncionario, Prestador, e Aluno) ganha/ativa properties que roteiam `self.get_vinculo().<campo>` — cobrindo a maioria dos sites de papel sem edição por-site. Sites que vão explícito por `pessoa_fisica.<campo>`, sites ambíguos (só pessoa), templates e ORM-traversals são reescritos. RemoveField entra no fim da fatia de cada campo, ligando o tripwire de `AttributeError` progressivamente. Tudo numa branch só, fatiado por campo.

**Tech Stack:** Django 5.2, djtools, pytest, Postgres. Codemod: edição dirigida por inventário (`docs/superpowers/inventory/inv-*.md`), validada por pyright (comum/djtools/suap) + suíte + grep-de-sobras.

**Spec/base:** `docs/superpowers/specs/2026-07-01-mover-campos-pessoa-para-vinculo-design.md` (passo aditivo S0, já na branch) e `docs/superpowers/inventory/README.md`.

## Global Constraints

- Branch única: `claude/admiring-sanderson-66903f`. Empilhar commits fatiados; merge como um MR grande.
- **Regra do vínculo (decisão do usuário):** obter o vínculo do PAPEL/USER em escopo (`servidor`/`aluno`/`prestador`/`user` → `.get_vinculo()`), **NUNCA** `pessoa_fisica.get_vinculo()`. As properties de chokepoint ficam em `AbstractRelacionamento`/papéis, **nunca** em PessoaFisica.
- **Sites ambíguos (só pessoa/pessoa_fisica, ≈168):** refactor threading o papel/user até o site (decisão do usuário). Não introduzir accessor pessoa→vínculo.
- **RemoveField por fatia**, não tudo junto. Cada campo sai da origem só no fim da sua fatia.
- **Templates falham em silêncio:** todo site de template do campo da fatia deve ser reescrito ANTES do RemoveField dele; validação por grep-de-sobras + revisão visual das telas-chave.
- Nomes: `email`→`email_pessoal`, `email_secundario`→`email_notificacao` (rename nos call-sites). `setores_adicionais`/`sistema_origem`/`foto`/`raca`/`povo_indigena`/`deficiencia` mantêm nome.
- ruff 150/aspas simples; complexidade ≤10 nas funções tocadas; pt-BR; testes via pytest (`DATABASE_HOST=127.0.0.1 DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --reuse-db ...`).
- Inventário é fuzzy: revalidar a lista do campo (`inv-*.md`) contra o código antes de reescrever.

## Chokepoints (referência)

- `rh/models/pessoa/abstract.py` `AbstractRelacionamento`: já tem `email_pessoal`(→pessoa_fisica.email, a corrigir p/ vínculo), `email_notificacao`(→get_vinculo().get_email()), `foto` comentado, e `__getattr__` que delega atributo desconhecido a `pessoa_fisica`. É o ponto mestre dos papéis (Servidor/Prestador/Aluno).
- `edu/models/alunos.py` `Aluno` herda `AbstractRelacionamento` (get_vinculo em 4712).
- `edu/models/professores.py` `Professor` NÃO herda (get_vinculo em 145) — tratar à parte.
- `comum.User.get_profile()`→PessoaFisica; `User.get_vinculo()` existe (comum/models.py:364).
- `Vinculo.get_email()` existe (comum/models.py:800); adicionar `get_foto_75x100_url()`/`get_foto_150x200_url()`/`get_foto_*_url` no Vinculo na fatia de foto.

## Procedimento por fatia (aplicar a cada campo)

1. **Property de chokepoint:** em `AbstractRelacionamento`, garantir property `@property def <campo>(self): v = self.get_vinculo(); return v.<campo> if v else None` (M2M: retornar `v.<campo>` só quando `v`, senão levantar/`none`). Guardar `None` de get_vinculo(). Ajustar `Professor` se o campo for usado nele.
2. **Sites .py de papel explícito:** `<papel>.pessoa_fisica.<campo>` → `<papel>.<campo>` (usa a property). `<papel>.<campo_antigo>` → `<papel>.<campo_novo>` (rename email).
3. **Sites .py com vínculo em mãos:** `vinculo.pessoa.pessoafisica.<campo>` → `vinculo.<campo>`.
4. **Sites ambíguos .py:** threading do papel/user até o site; se impossível, escalar (não usar pessoa→vínculo).
5. **ORM-traversals:** `filter(pessoa_fisica__<campo>=)` / `values_list('pessoa_fisica__<campo>')` → caminho via Vinculo (ex.: `pessoa_fisica__vinculo__<campo>` conforme related_name) ou reestruturar a query. Validar cada uma (algumas não têm tradução trivial → escalar).
6. **Templates:** reescrever todo site do campo (inv-templates.md) usando o objeto de papel/user disponível no contexto → `<papel>.get_vinculo.<campo>` ou property. Onde só há `pessoa`, a view passa o vínculo no contexto (threading).
7. **RemoveField:** migration removendo o campo da origem (PessoaFisica: raca/povo_indigena/deficiencia/foto; Pessoa: email/email_secundario/setores_adicionais/sistema_origem). Depender da migration de RemoveField da fatia anterior.
8. **Verificação:** `uv run pyright` (0 erros novos em comum/djtools/suap); suíte pytest dos apps tocados; `grep -rIn '\.<campo>\b\|pessoa_fisica__<campo>' --include='*.py' --include='*.html'` = 0 sobras reais; smoke visual das telas-chave do campo.

---

## Fatia S1: campos triviais — `deficiencia`, `sistema_origem`, `setores_adicionais`, `povo_indigena`, `raca` (≈50 sites)

Valida o padrão end-to-end (property → rewrite → RemoveField → tripwire) no menor risco. `deficiencia` = 0 call-sites (só property opcional + RemoveField).

### Task S1.1: Properties de chokepoint para os 5 campos triviais

**Files:** Modify `rh/models/pessoa/abstract.py` (`AbstractRelacionamento`); talvez `edu/models/professores.py` (Professor) se algum site de papel for professor.

**Interfaces:** Produces properties `raca`, `povo_indigena`, `sistema_origem`, `setores_adicionais` (e opcional `deficiencia`) em AbstractRelacionamento roteando via `self.get_vinculo()`.

- [ ] **Step 1: Teste falhando** — em `rh/tests/` criar teste que monta um Servidor com Vinculo cujo `raca`/`sistema_origem`/`setores_adicionais` estão setados no VÍNCULO, e assere `servidor.raca == vinculo.raca`, `servidor.sistema_origem == vinculo.sistema_origem`, `list(servidor.setores_adicionais.all())` reflete o vínculo. (Reusar base RHBase/factories.)
- [ ] **Step 2: Rodar e ver falhar** — `... uv run pytest --reuse-db rh/tests/test_<novo>.py -q` → FAIL (hoje `servidor.raca` cai em pessoa_fisica via __getattr__).
- [ ] **Step 3: Implementar properties** em `AbstractRelacionamento` (após as properties existentes):
```python
    @property
    def raca(self):
        v = self.get_vinculo()
        return v.raca if v else None

    @property
    def povo_indigena(self):
        v = self.get_vinculo()
        return v.povo_indigena if v else None

    @property
    def sistema_origem(self):
        v = self.get_vinculo()
        return v.sistema_origem if v else ''

    @property
    def setores_adicionais(self):
        # Retorna o manager M2M do vínculo; chamadas .all()/.add() operam no vínculo.
        return self.get_vinculo().setores_adicionais
```
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** `[rh] Properties de raca/povo_indigena/sistema_origem/setores_adicionais roteando via vínculo do papel`.

### Task S1.2: Reescrever sites .py + ORM dos triviais/raca

**Files:** conforme `docs/superpowers/inventory/inv-trivial-raca.md` (36 attr + 20 ORM). Test: apps tocados.

- [ ] **Step 1:** Revalidar a lista do inv-trivial-raca.md contra o código (marcar sobras/ruído).
- [ ] **Step 2:** Para cada site de papel: `<papel>.pessoa_fisica.raca` → `<papel>.raca`; idem povo_indigena/sistema_origem/setores_adicionais. Sites com vínculo em mãos → `vinculo.<campo>`.
- [ ] **Step 3:** Sites AMBIGUOUS (≈6, ex. `pessoa_fisica.py::clean()` self.raca, `comum/utils.py` profile.setores_adicionais): threading do papel/user; escalar se impossível.
- [ ] **Step 4:** ORM-traversals: reescrever `pessoa_fisica__raca`/`__setores_adicionais`/`__sistema_origem` via caminho do Vinculo; validar cada query.
- [ ] **Step 5:** pyright + pytest dos apps tocados; `grep` de sobras `.raca`/`.povo_indigena`/`.sistema_origem`/`.setores_adicionais` reais = 0 (fora defs/migrations).
- [ ] **Step 6: Commit** por app ou agrupado `[<apps>] Migra leitura de raca/... para o vínculo do papel`.

### Task S1.3: Reescrever templates dos triviais/raca

**Files:** `docs/superpowers/inventory/inv-templates.md` (raca 12, setores 4, povo 1, deficiencia 1, sistema_origem 0).

- [ ] **Step 1:** Para cada template: `<papel>.pessoa_fisica.raca` → `<papel>.get_vinculo.raca` (ou property); sites só-`pessoa` → view passa `vinculo` no contexto.
- [ ] **Step 2:** `grep --include='*.html'` de sobras dos 4 campos = 0.
- [ ] **Step 3: Commit** `[<apps>] Migra templates de raca/... para o vínculo`.

### Task S1.4: RemoveField dos 5 campos triviais

**Files:** Create migration em `rh/migrations/` (raca/povo_indigena/deficiencia de PessoaFisica) e `rh/migrations/`/`comum` conforme app do modelo (sistema_origem/setores_adicionais de Pessoa). Remove as defs em `rh/models/pessoa/pessoa.py` (setores_adicionais, sistema_origem) e `pessoa_fisica.py` (raca, povo_indigena, deficiencia).

- [ ] **Step 1:** Remover as 5 defs de campo dos modelos.
- [ ] **Step 2:** `makemigrations` → migration RemoveField (depende de comum/0115 backfill).
- [ ] **Step 3:** Suíte completa dos apps tocados + `uv run python manage.py migrate --plan` sanity; `grep` global de qualquer `pessoa_fisica.raca`/`pessoa.sistema_origem` etc. remanescente (em .py e .html) = 0.
- [ ] **Step 4:** Smoke visual: telas de servidor/aluno que exibem raça/setores.
- [ ] **Step 5: Commit** `[rh] RemoveField raca/povo_indigena/deficiencia/sistema_origem/setores_adicionais (migrados p/ Vinculo)`.

---

## Fatia S2: `foto` (≈82 py + ≈148 templates)

Mesmo procedimento. Especificidades:
- **Ativar** a property `foto` comentada em `AbstractRelacionamento` → `v = self.get_vinculo(); return v.foto if v else None`.
- **Adicionar no `Vinculo`** (comum/models.py) os métodos `get_foto_75x100_url()`, `get_foto_150x200_url()` (e afins) espelhando os de PessoaFisica, lendo `self.foto`. Sites de template `<papel>.pessoa_fisica.get_foto_75x100_url` → `<papel>.get_vinculo.get_foto_75x100_url`; `user.get_profile.get_foto_*` → `user.get_vinculo.get_foto_*`.
- Sites `vinculo.pessoa.pessoafisica.get_foto_*` → `vinculo.get_foto_*`.
- Mover/duplicar as defs `get_foto_*_url` de PessoaFisica para Vinculo; decidir se PessoaFisica mantém stubs até o RemoveField.
- Lista: `inv-foto.md` + linhas de foto em `inv-templates.md`. RemoveField `foto` de PessoaFisica no fim.

## Fatia S3: `email_secundario` → `email_notificacao` (≈116 py + 20 templates)

- Property `email_notificacao` já existe (→ get_vinculo().get_email()); confirmar que `get_email()` do Vinculo retorna `email_notificacao`/`email_pessoal` corretamente (ajustar se preciso). Adicionar `email_notificacao` como leitura do campo do vínculo.
- Rename call-sites `email_secundario` → `email_notificacao`. Lista: `inv-email_secundario.md` + templates. WRITE sites (20) exigem escrever no vínculo.
- RemoveField `email_secundario` de Pessoa no fim.

## Fatia S4: `email` → `email_pessoal` (≈68 py + 113 templates + 14 ORM)

- Corrigir property `email_pessoal` em AbstractRelacionamento p/ `self.get_vinculo().email_pessoal` (hoje aponta pessoa_fisica.email).
- Rename `email` → `email_pessoal` nos sites de Pessoa/PessoaFisica (cuidado com o ruído: NÃO tocar User.email/Setor.email/email_institucional/email_academico). Lista: `inv-email.md` + templates + ORM.
- RemoveField `email` de Pessoa no fim.

---

## Self-Review

- Cobertura: cada um dos 8 campos tem fatia (deficiencia dentro de S1; email/email_secundario/foto em S4/S3/S2). ✓
- Ordem de risco: triviais→foto→email_secundario→email. ✓
- Regra do vínculo (papel/user, nunca pf.get_vinculo) refletida nas properties (em AbstractRelacionamento) e no threading dos ambíguos. ✓
- RemoveField por fatia + tripwire progressivo; templates reescritos antes do RemoveField do campo (mitiga falha silenciosa). ✓
- Placeholders: listas de site referenciam `inv-*.md` (não inline — 654 sites); é a fonte por-fatia, revalidada antes de cada rewrite. Procedimento e código das properties/migrations são concretos.
