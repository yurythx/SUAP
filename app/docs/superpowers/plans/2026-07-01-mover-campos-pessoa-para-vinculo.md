# Mover campos de Pessoa/PessoaFisica para Vínculo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar 8 campos ao modelo `comum.Vinculo` e copiar (backfill) os valores atuais de `Pessoa`/`PessoaFisica`, de forma aditiva e reversível.

**Architecture:** Passo 1 (aditivo) da unificação de `PessoaFisica`. Uma migration de schema (`AddField` ×7 + M2M) seguida de uma migration de dados (`RunPython`) que itera `Vinculo` e copia de `vinculo.pessoa`. Nada é removido de `Pessoa`/`PessoaFisica`; call-sites não mudam. Fonte da verdade continua em `Pessoa`/`PessoaFisica` até o passo de codemod (fora deste plano).

**Tech Stack:** Django 5.2, `djtools` (ModelPlus/ImageWithThumbsField), pytest, Postgres.

**Spec:** `docs/superpowers/specs/2026-07-01-mover-campos-pessoa-para-vinculo-design.md`

## Global Constraints

- Branch de trabalho: `claude/admiring-sanderson-66903f` (worktree já ativo). Não criar worktree novo.
- `Vinculo` vive em `comum/models.py` (classe na linha ≈654). Última migration do `comum`: `0113_atalho`.
- Ruff: line length 150, aspas simples, `*/migrations/*` excluído do ruff.
- Complexidade ciclomática ≤ 10 nas funções tocadas.
- pt-BR em identificadores, comentários e mensagens de commit.
- Testes: `pytest`, NÃO `manage.py test`. Precisa de Postgres com `max_locks_per_transaction` alto (ver `AGENTS.md`).
- Backfill roda para **todos** os vínculos, inclusive `PessoaJuridica` (copia os 4 campos de `Pessoa`; os 4 campos de `PessoaFisica` ficam null em vínculos PJ).
- Hoje é **1 Pessoa ↔ 1 Vínculo** — backfill 1:1.
- Tipos/`choices`/`on_delete` dos campos novos espelham exatamente a origem (`rh/models/pessoa/pessoa.py` e `rh/models/pessoa/pessoa_fisica.py`).

---

### Task 1: Adicionar os 8 campos ao modelo `Vinculo` + migration de schema

**Files:**
- Modify: `comum/models.py` (import no topo; 8 campos na classe `Vinculo`, após `secret`, antes de `objects = VinculoManager()`)
- Create: `comum/migrations/0114_vinculo_campos_pessoa.py` (gerada por `makemigrations`)
- Test: `comum/tests/test_vinculo_campos_migrados.py`

**Interfaces:**
- Produces: modelo `comum.Vinculo` com os campos `email_pessoal` (EmailField), `email_notificacao` (EmailField), `setores_adicionais` (M2M `rh.Setor`, related_name `vinculos_setor_adicional`), `sistema_origem` (CharField), `foto` (ImageWithThumbsField), `raca` (FK `comum.Raca`), `povo_indigena` (FK `comum.PovoIndigena`), `deficiencia` (FK `rh.Deficiencia`). Task 2 consome esses campos.

- [ ] **Step 1: Escrever o teste que falha**

Criar `comum/tests/test_vinculo_campos_migrados.py`:

```python
from comum.models import Vinculo


def test_vinculo_tem_os_8_campos_migrados():
    nomes = {campo.name for campo in Vinculo._meta.get_fields()}
    esperados = {
        'email_pessoal',
        'email_notificacao',
        'setores_adicionais',
        'sistema_origem',
        'foto',
        'raca',
        'povo_indigena',
        'deficiencia',
    }
    assert esperados <= nomes
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/test_vinculo_campos_migrados.py -q`
Expected: FAIL — `AssertionError` (campos ainda não existem).

- [ ] **Step 3: Adicionar o import no topo de `comum/models.py`**

Logo após a linha `from djtools.storages.utils import cache_file, download_media_content, get_overwrite_storage` (~linha 58), adicionar:

```python
from djtools.thumbs import ImageWithThumbsField
```

(`get_overwrite_storage` já está importado; não reimportar.)

- [ ] **Step 4: Adicionar os 8 campos na classe `Vinculo`**

Em `comum/models.py`, na classe `Vinculo`, logo após a linha `secret = models.IntegerField(...)` e antes de `objects = VinculoManager()`:

```python
    # Campos migrados de Pessoa/PessoaFisica (passo 1 da unificação de PessoaFisica).
    # ponytail: por ora é um snapshot preenchido pelo backfill; a fonte da verdade segue
    # em Pessoa/PessoaFisica até o passo de codemod. Sem dual-write.
    email_pessoal = models.EmailField('E-mail Pessoal', blank=True)
    email_notificacao = models.EmailField('E-mail de Notificação', blank=True, help_text='E-mail utilizado para recuperação de senha.')
    setores_adicionais = models.ManyToManyField(
        'rh.Setor',
        verbose_name='Setores Adicionais',
        blank=True,
        related_name='vinculos_setor_adicional',
        help_text='O funcionário terá acesso aos processos dos setores adicionais no sistema de protocolo.',
    )
    sistema_origem = models.CharField(
        max_length=50,
        blank=True,
        choices=[['', 'Cadastro manual'], ['SIAPE', 'SIAPE'], ['WS-SIAPE', 'WS-SIAPE'], ['SIAFI', 'SIAFI']],
        help_text='Indica de qual sistema a pessoa veio: SIAPE, SIAFI etc',
    )
    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(), use_id_for_name=True, upload_to='fotos', sizes=((75, 100), (150, 200)), null=True, blank=True
    )
    # ponytail: on_delete=CASCADE espelha a origem em PessoaFisica (dubioso p/ tabela de domínio);
    # trocar por SET_NULL num passo futuro se virar problema. Mantido fiel à origem por ora.
    raca = models.ForeignKeyPlus('comum.Raca', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE)
    povo_indigena = models.ForeignKeyPlus('comum.PovoIndigena', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE)
    deficiencia = models.ForeignKeyPlus('rh.Deficiencia', verbose_name='Deficiência', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE)
```

- [ ] **Step 5: Gerar a migration de schema**

Run: `uv run python manage.py makemigrations comum --name vinculo_campos_pessoa`
Expected: cria `comum/migrations/0114_vinculo_campos_pessoa.py` com `AddField` ×7 + `AddField` da M2M `setores_adicionais`. O Django adiciona automaticamente a dependência da última migration do `rh` (por causa das FKs `rh.Setor`/`rh.Deficiencia`).

Verificar que não sobrou migration pendente:
Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 6: Rodar o teste e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/test_vinculo_campos_migrados.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add comum/models.py comum/migrations/0114_vinculo_campos_pessoa.py comum/tests/test_vinculo_campos_migrados.py
git commit -m "[comum] Adiciona campos migrados de Pessoa/PessoaFisica ao Vinculo (schema)"
```

---

### Task 2: Migration de dados (backfill) + teste comportamental

**Files:**
- Create: `comum/migrations/0115_backfill_campos_vinculo.py`
- Test: `comum/tests/test_vinculo_campos_migrados.py` (adicionar teste do backfill no mesmo arquivo)

**Interfaces:**
- Consumes: campos do `Vinculo` criados na Task 1.
- Produces: função `copiar_campos_para_vinculo(apps, schema_editor)` no módulo da migration 0115, importável e chamável com o registry real de apps (`django.apps.apps`). Reverse: `limpar_campos_vinculo(apps, schema_editor)`.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar ao final de `comum/tests/test_vinculo_campos_migrados.py`:

```python
import importlib

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType

import pytest

from comum.models import PovoIndigena, Raca, Vinculo
from rh.models import GrupoDeficiencia, PessoaFisica, PessoaJuridica, Servidor, Setor
from rh.models.pcd.pcd import Deficiencia


def _criar_vinculo(pessoa, id_relacionamento):
    # relacionamento não é lido pelo backfill; basta um ContentType válido e um id único.
    tipo = ContentType.objects.get_for_model(Servidor)
    return Vinculo.objects.create(
        pessoa=pessoa,
        tipo_relacionamento=tipo,
        id_relacionamento=id_relacionamento,
        secret=pessoa.pk,
    )


@pytest.mark.django_db(databases='__all__')
def test_backfill_copia_campos_de_pessoa_e_pessoafisica():
    setor = Setor.objects.create(sigla='TST-BF', nome='Setor Backfill')
    raca = Raca.objects.create(descricao='Parda')
    povo = PovoIndigena.objects.create(nome='Tupi-BF')
    grupo = GrupoDeficiencia.objects.create(nome='Grupo BF')
    deficiencia = Deficiencia.objects.create(grupo_deficiencia=grupo, codigo='BF', descricao='Deficiência BF')

    pf = PessoaFisica.objects.create(nome='Fulano Backfill', cpf='000.000.000-00')
    pf.email = 'pessoal@ex.com'
    pf.email_secundario = 'notif@ex.com'
    pf.sistema_origem = 'SIAPE'
    pf.raca = raca
    pf.povo_indigena = povo
    pf.deficiencia = deficiencia
    pf.foto = 'fotos/1.jpg'
    pf.save()
    pf.setores_adicionais.add(setor)

    pj = PessoaJuridica.objects.create(nome='Empresa Backfill', cnpj='00.000.000/0001-00')
    pj.email = 'pj@ex.com'
    pj.email_secundario = 'pjnotif@ex.com'
    pj.sistema_origem = 'SIAFI'
    pj.save()
    pj.setores_adicionais.add(setor)

    v_pf = _criar_vinculo(pf.pessoa_ptr, id_relacionamento=900001)
    v_pj = _criar_vinculo(pj.pessoa_ptr, id_relacionamento=900002)

    modulo = importlib.import_module('comum.migrations.0115_backfill_campos_vinculo')
    modulo.copiar_campos_para_vinculo(django_apps, None)

    v_pf.refresh_from_db()
    v_pj.refresh_from_db()

    # PF: os 8 campos copiados
    assert v_pf.email_pessoal == 'pessoal@ex.com'
    assert v_pf.email_notificacao == 'notif@ex.com'
    assert v_pf.sistema_origem == 'SIAPE'
    assert v_pf.raca_id == raca.id
    assert v_pf.povo_indigena_id == povo.id
    assert v_pf.deficiencia_id == deficiencia.id
    assert v_pf.foto.name == 'fotos/1.jpg'
    assert list(v_pf.setores_adicionais.values_list('id', flat=True)) == [setor.id]

    # PJ: os 4 campos de Pessoa copiados; os 4 de PessoaFisica ficam null
    assert v_pj.email_pessoal == 'pj@ex.com'
    assert v_pj.email_notificacao == 'pjnotif@ex.com'
    assert v_pj.sistema_origem == 'SIAFI'
    assert list(v_pj.setores_adicionais.values_list('id', flat=True)) == [setor.id]
    assert v_pj.raca_id is None
    assert v_pj.povo_indigena_id is None
    assert v_pj.deficiencia_id is None
    assert not v_pj.foto
```

Nota p/ o executor: se `PessoaFisica`/`PessoaJuridica`/`Setor`/`Deficiencia`/`GrupoDeficiencia` exigirem campos obrigatórios além dos preenchidos, o próprio ciclo red-green revela o `IntegrityError`/`ValidationError`; preencha o mínimo necessário (ex.: `Servidor` NÃO é instanciado, só usado como ContentType). Os caminhos de import de `Deficiencia`/`GrupoDeficiencia` podem variar — ajuste conforme `rh/models/pcd/pcd.py`.

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/test_vinculo_campos_migrados.py::test_backfill_copia_campos_de_pessoa_e_pessoafisica -q`
Expected: FAIL — `ModuleNotFoundError` (migration 0115 ainda não existe).

- [ ] **Step 3: Criar a migration de backfill**

Criar `comum/migrations/0115_backfill_campos_vinculo.py`:

```python
from django.db import migrations

CAMPOS_ATUALIZADOS = ['email_pessoal', 'email_notificacao', 'sistema_origem', 'foto', 'raca', 'povo_indigena', 'deficiencia']


def copiar_campos_para_vinculo(apps, schema_editor):
    """Copia os campos de Pessoa/PessoaFisica para cada Vinculo (backfill 1:1)."""
    Vinculo = apps.get_model('comum', 'Vinculo')
    for vinculo in Vinculo.objects.select_related('pessoa').iterator():
        pessoa = vinculo.pessoa
        vinculo.email_pessoal = pessoa.email
        vinculo.email_notificacao = pessoa.email_secundario
        vinculo.sistema_origem = pessoa.sistema_origem
        # hasattr(pessoa, 'pessoafisica') é o idiomma já usado em Pessoa.__str__ (rh/models/pessoa/pessoa.py).
        pf = pessoa.pessoafisica if hasattr(pessoa, 'pessoafisica') else None
        if pf is not None:
            vinculo.foto = pf.foto.name if pf.foto else None
            vinculo.raca_id = pf.raca_id
            vinculo.povo_indigena_id = pf.povo_indigena_id
            vinculo.deficiencia_id = pf.deficiencia_id
        vinculo.save(update_fields=CAMPOS_ATUALIZADOS)
        vinculo.setores_adicionais.set(pessoa.setores_adicionais.all())


def limpar_campos_vinculo(apps, schema_editor):
    """Reverse: zera os campos migrados (no-op seguro)."""
    Vinculo = apps.get_model('comum', 'Vinculo')
    for vinculo in Vinculo.objects.iterator():
        vinculo.email_pessoal = ''
        vinculo.email_notificacao = ''
        vinculo.sistema_origem = ''
        vinculo.foto = None
        vinculo.raca_id = None
        vinculo.povo_indigena_id = None
        vinculo.deficiencia_id = None
        vinculo.save(update_fields=CAMPOS_ATUALIZADOS)
        vinculo.setores_adicionais.clear()


class Migration(migrations.Migration):
    dependencies = [
        ('comum', '0114_vinculo_campos_pessoa'),
    ]

    operations = [
        migrations.RunPython(copiar_campos_para_vinculo, limpar_campos_vinculo),
    ]
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/test_vinculo_campos_migrados.py -q`
Expected: PASS (os 2 testes).

- [ ] **Step 5: Sanidade da suíte do `comum` afetada por Vinculo**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/test_user_model.py -q`
Expected: PASS (o `related_name` da M2M não colide com `Vinculo.setor`).

- [ ] **Step 6: Commit**

```bash
git add comum/migrations/0115_backfill_campos_vinculo.py comum/tests/test_vinculo_campos_migrados.py
git commit -m "[comum] Backfill dos campos migrados de Pessoa/PessoaFisica no Vinculo (data migration)"
```

---

## Self-Review

**Spec coverage:**
- 8 campos adicionados ao Vinculo (nomes/tipos da tabela da spec) → Task 1, Step 4. ✓
- Migration de schema → Task 1. Migration de dados/backfill → Task 2. ✓
- Backfill copia campos de Pessoa p/ todos os vínculos e campos de PessoaFisica só quando há `pessoafisica` (PJ fica null) → Task 2, função + teste (asserts PF e PJ). ✓
- Colisão de `related_name` da M2M tratada (`vinculos_setor_adicional`) + Step 5 de sanidade → Task 1/Task 2. ✓
- `foto` com import de `ImageWithThumbsField` (get_overwrite_storage já importado) → Task 1, Steps 3-4. ✓
- Reversibilidade (reverse limpa os campos) → Task 2, `limpar_campos_vinculo`. ✓
- Teto sem dual-write documentado como comentário `ponytail:` no modelo → Task 1, Step 4. ✓
- Fora de escopo (RemoveField, UNIQUE, codemod, signals, dedup) → não há tasks para isso, conforme spec. ✓

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra o código. Nota ao executor sobre campos obrigatórios é orientação de TDD, não placeholder de implementação.

**Type consistency:** `copiar_campos_para_vinculo(apps, schema_editor)` e `limpar_campos_vinculo` usados de forma consistente entre migration e teste; nomes de campos idênticos entre modelo, backfill, `CAMPOS_ATUALIZADOS` e asserts.
