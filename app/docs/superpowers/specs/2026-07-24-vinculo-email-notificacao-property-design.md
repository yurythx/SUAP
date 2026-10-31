# `Vinculo.email_notificacao`: campo → property

**Data:** 2026-07-24 · **Branch:** `migrar-campos-pessoa` · **MR:** !18460

## Problema

Na unificação de `PessoaFisica`, `Vinculo.email_notificacao` virou campo armazenado
redundante: seu valor sempre pode ser derivado do e-mail institucional do papel
(`relacionamento.email_institucional`) ou, na falta, do `email_pessoal` do próprio
vínculo. Guardá-lo obriga backfill (0115), normalização no `save()` e ≈18 writers a
manter dois campos sincronizados.

## Decisão

Converter `email_notificacao` em **property somente-leitura**:

```python
@property
def email_notificacao(self) -> str:
    """E-mail de notificação: o institucional do papel, senão o pessoal."""
    return getattr(self.relacionamento, 'email_institucional', '') or self.email_pessoal
```

Regra: **institucional tem prioridade, fallback para pessoal**. PJ/PessoaExterna não têm
`email_institucional` → caem no `email_pessoal`.

## Mudanças

1. **Modelo** (`comum/models.py`): remove o `EmailField email_notificacao`, adiciona a
   property. Remove a normalização `email_notificacao is None → ''` do `Vinculo.save()`.
   `get_email()` e `AbstractRelacionamento.email_notificacao` (property que delega ao
   vínculo) continuam válidos — passam a ler a property.

2. **Migrations** (não shipadas ainda): editar em vez de add+remove.
   - `0114`: remover o `AddField email_notificacao`.
   - `0115`: remover a linha de backfill e tirar `'email_notificacao'` de `CAMPOS_ATUALIZADOS`.

3. **Writers (≈18)** — todos escrevem e-mail **pessoal**: redirecionar
   `v.email_notificacao = X` → `v.email_pessoal = X` (ajustando `update_fields`). Sites:
   processo_seletivo/tasks.py, egressos/forms.py, edu/tasks.py, edu/forms/{mini_cursos,
   alunos,matriculas}.py, edu/management/commands/{edu_importar_csv,
   edu_atualizar_dados_pessoas_alunos_proitec}.py, comum/forms.py,
   rh/.../limpar_emails_servidor.py, interceptor comum/models.py, features/steps/given.py.

4. **Interceptor** (`comum/models.py`, update_or_create de vínculo): hoje seta
   `email_pessoal` (de `email`) **e** `email_notificacao` (de `email_secundario`). Passa a
   computar `email_pessoal = 1º não-institucional entre [email_secundario, email]` (regra do
   backfill 0115) e some com `email_notificacao`.

5. **Sites ORM** (property não é filtrável):
   - `comum/management/commands/sync_emails.py`: o bloco que **zera** `email_notificacao`
     institucional vira moot (derivado nunca guarda institucional) → remover; o
     `update(email_notificacao=email_siape)` → `update(email_pessoal=email_siape)` com filtro
     `email_pessoal=''`.
   - `edu/models/comunicador.py`: `vinculos__email_notificacao` → `vinculos__email_pessoal`.

6. **Testes/BDD**: `test_vinculo_properties_papel` e steps que setam `email_notificacao=...`
   passam a setar `email_pessoal`.

## Consequência aceita

Forms que hoje têm `email_pessoal` E `email_secundario` como campos distintos passam a
alimentar ambos o mesmo `email_pessoal` (o de notificação some do armazenamento). É o
esperado de "campo desnecessário".

## Validação

- `manage.py check` + `makemigrations --check`.
- Gate: testes de `Vinculo` (properties/papel) no Postgres efêmero.
