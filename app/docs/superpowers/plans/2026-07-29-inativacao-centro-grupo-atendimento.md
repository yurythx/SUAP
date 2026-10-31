# Inativação de Grupo de Atendimento e Centro de Atendimento — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir marcar `CentroAtendimento` e `GrupoAtendimento` como inativos no admin da Central de Serviços, impedindo a inativação quando houver `Servico` ativo vinculado, e mostrar quais Serviços bloqueiam a inativação apenas na tela de alteração/visualização de um único registro (não na listagem).

**Architecture:** Adiciona campo `ativo` (BooleanField, default=True) em `CentroAtendimento` e `GrupoAtendimento` (`centralservicos/models.py`). A regra de bloqueio fica no `clean()` de cada model, usando `.exists()` (parada no primeiro registro encontrado, sem contar nem listar) — só dispara quando o registro está de fato transicionando de ativo para inativo (evita custo em toda edição). Como os `ModelForm`s do admin (`CentroAtendimentoForm`, `GrupoAtendimentoForm`) usam `exclude = ()`, o novo campo aparece no formulário automaticamente. No admin, o campo `ativo` (booleano simples, sem custo) entra em `list_display`; a informação de **quais** Serviços ativos bloqueiam a inativação é exibida só via `readonly_fields` (renderizado apenas quando o usuário abre um registro específico), evitando N+1 queries na listagem.

**Tech Stack:** Django 5.2 admin (`ModelAdminPlus`), pytest (fixtures `suap_data` / `centralservicos_context`).

---

## File Structure

- Modify: `centralservicos/models.py` — campo `ativo` + `clean()` em `CentroAtendimento` (linhas ≈92-104) e `GrupoAtendimento` (linhas ≈338-375).
- Create: `centralservicos/migrations/0015_centroatendimento_ativo_grupoatendimento_ativo.py`.
- Modify: `centralservicos/admin.py` — `CentroAtendimentoAdmin` (linhas ≈117-135) e `GrupoAtendimentoAdmin` (linhas ≈342-407).
- Create: `centralservicos/tests/test_inativacao_atendimento.py` — testes de model (`clean()`) e de form (`CentroAtendimentoForm`, `GrupoAtendimentoForm`).

---

### Task 1: Campo `ativo` e bloqueio de inativação em `CentroAtendimento`

**Files:**
- Modify: `centralservicos/models.py:92-104`
- Test: `centralservicos/tests/test_inativacao_atendimento.py`

- [x] **Step 1: Escrever o teste que falha**

Criar o arquivo `centralservicos/tests/test_inativacao_atendimento.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from centralservicos.models import CentroAtendimento


@pytest.mark.usefixtures('suap_data')
class TestInativacaoCentroAtendimento:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context

    def test_nao_permite_inativar_centro_atendimento_com_servico_ativo_vinculado(self):
        centro = self.context.centro_atendimento
        centro.ativo = False

        with pytest.raises(ValidationError):
            centro.full_clean()

    def test_permite_inativar_centro_atendimento_sem_servico_ativo_vinculado(self):
        servico = self.context.servico
        servico.ativo = False
        servico.save()

        centro = self.context.centro_atendimento
        centro.ativo = False
        centro.full_clean()
        centro.save()

        centro.refresh_from_db()
        assert centro.ativo is False
```

- [x] **Step 2: Rodar o teste para confirmar que falha**

Run: `pytest -q centralservicos/tests/test_inativacao_atendimento.py -v`
Expected: `test_nao_permite_inativar_centro_atendimento_com_servico_ativo_vinculado` FAIL (`DID NOT RAISE <class 'django.core.exceptions.ValidationError'>`) — hoje `ativo` não é um campo do model, então `centro.ativo = False` só cria um atributo solto em Python, sem efeito no `full_clean()`.

- [x] **Step 3: Implementar o campo e a regra no model**

Em `centralservicos/models.py`, substituir a classe `CentroAtendimento` (linhas 92-104):

```python
class CentroAtendimento(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=80, help_text='Informe um nome para o Centro de Atendimento')
    eh_local = models.BooleanField('Centro de Atendimento Local?', default=False)
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        unique_together = ('nome', 'area')
        ordering = ['nome']
        verbose_name = 'Centro de Atendimento'
        verbose_name_plural = 'Centros de Atendimento'

    def __str__(self):
        return f'{self.nome} / Área: {self.area}'

    def clean(self):
        if self.pk and not self.ativo:
            estava_ativo = CentroAtendimento.objects.filter(pk=self.pk, ativo=True).exists()
            if estava_ativo and Servico.objects.filter(centros_atendimento=self, ativo=True).exists():
                raise ValidationError('Não é possível inativar. Existem Serviços ativos vinculados a este Centro de Atendimento.')
```

Nota: `Servico` e `ValidationError` já são resolvidos em tempo de chamada (o método só executa depois que o módulo inteiro — incluindo a classe `Servico`, definida mais abaixo no mesmo arquivo — já foi carregado); `ValidationError` já está importado no arquivo (usado em `GrupoAtendimento.clean()`).

A checagem só dispara quando o registro **está** ativo no banco (`estava_ativo`) e o valor recebido é `False` — evita bloquear salvamentos de um registro que já estava inativo.

- [x] **Step 4: Rodar o teste para confirmar que passa**

Run: `pytest -q centralservicos/tests/test_inativacao_atendimento.py -v`
Expected: as duas funções da classe `TestInativacaoCentroAtendimento` PASS.

- [x] **Step 5: Commit**

```bash
git add centralservicos/models.py centralservicos/tests/test_inativacao_atendimento.py
git commit -m "[centralservicos] Bloqueia inativação de Centro de Atendimento com Serviço ativo vinculado"
```

---

### Task 2: Campo `ativo` e bloqueio de inativação em `GrupoAtendimento`

**Files:**
- Modify: `centralservicos/models.py:338-375`
- Test: `centralservicos/tests/test_inativacao_atendimento.py`

Serviço não tem vínculo direto com `GrupoAtendimento` — o vínculo é via `centro_atendimento` do grupo (mesma lógica já usada em `GrupoAtendimentoAdmin.get_servicos_ativos`, `centralservicos/admin.py:383-390`).

- [x] **Step 1: Escrever o teste que falha**

Adicionar ao final de `centralservicos/tests/test_inativacao_atendimento.py`:

```python
from centralservicos.models import GrupoAtendimento


@pytest.mark.usefixtures('suap_data')
class TestInativacaoGrupoAtendimento:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_nao_permite_inativar_grupo_atendimento_com_servico_ativo_vinculado_ao_centro(self):
        grupo = self.grupo
        grupo.ativo = False

        with pytest.raises(ValidationError):
            grupo.full_clean()

    def test_permite_inativar_grupo_atendimento_sem_servico_ativo_vinculado_ao_centro(self):
        servico = self.context.servico
        servico.ativo = False
        servico.save()

        grupo = self.grupo
        grupo.ativo = False
        grupo.full_clean()
        grupo.save()

        grupo.refresh_from_db()
        assert grupo.ativo is False
```

(mover o `from centralservicos.models import GrupoAtendimento` para o topo do arquivo, junto com o `import` de `CentroAtendimento`.)

- [x] **Step 2: Rodar o teste para confirmar que falha**

Run: `pytest -q centralservicos/tests/test_inativacao_atendimento.py -v`
Expected: `test_nao_permite_inativar_grupo_atendimento_com_servico_ativo_vinculado_ao_centro` FAIL (`DID NOT RAISE`), pelo mesmo motivo do Task 1 — `ativo` ainda não existe em `GrupoAtendimento`.

- [x] **Step 3: Implementar o campo e a regra no model**

Em `centralservicos/models.py`, no início da classe `GrupoAtendimento` (linha ≈338), adicionar o campo depois de `atendentes`:

```python
    atendentes = models.ManyToManyFieldPlus(User, related_name='atendentes_set', blank=True, verbose_name='Atendentes Vinculados ao Grupo')
    ativo = models.BooleanField('Ativo?', default=True)
```

E no `clean()` existente (linhas ≈361-375), acrescentar a nova checagem ao final do método:

```python
    def clean(self):
        # Não pode existir mais de um grupo de atendimento, no mesmo nível, na mesma UO,
        # no mesmo centro de atendimento
        if not hasattr(self, 'centro_atendimento'):
            raise ValidationError('Nenhum centro de atendimento encontrado.')
        if not hasattr(self, 'campus'):
            raise ValidationError('Nenhum campus encontrado.')
        if (
            GrupoAtendimento.objects.filter(
                grupo_atendimento_superior=self.grupo_atendimento_superior, campus=self.campus, centro_atendimento=self.centro_atendimento
            )
            .exclude(pk=self.id)
            .exists()
        ):
            raise ValidationError('Não pode existir mais de um grupo de atendimento, no mesmo nível, na mesma UO, no mesmo centro de atendimento.')

        if self.pk and not self.ativo:
            estava_ativo = GrupoAtendimento.objects.filter(pk=self.pk, ativo=True).exists()
            if estava_ativo and Servico.objects.filter(centros_atendimento=self.centro_atendimento, ativo=True).exists():
                raise ValidationError(
                    'Não é possível inativar. Existem Serviços ativos vinculados ao Centro de Atendimento deste Grupo de Atendimento.'
                )
```

- [x] **Step 4: Rodar o teste para confirmar que passa**

Run: `pytest -q centralservicos/tests/test_inativacao_atendimento.py -v`
Expected: todas as 4 funções (Task 1 + Task 2) PASS.

- [x] **Step 5: Commit**

```bash
git add centralservicos/models.py centralservicos/tests/test_inativacao_atendimento.py
git commit -m "[centralservicos] Bloqueia inativação de Grupo de Atendimento com Serviço ativo vinculado ao centro"
```

---

### Task 3: Migration

**Files:**
- Create: `centralservicos/migrations/0015_centroatendimento_ativo_grupoatendimento_ativo.py`

- [x] **Step 1: Gerar a migration**

Run: `python manage.py makemigrations centralservicos`

Expected output: um novo arquivo `centralservicos/migrations/0015_centroatendimento_ativo_grupoatendimento_ativo.py` (o nome exato pode variar; renomeie para esse padrão se o Django gerar outro nome), com o conteúdo abaixo. Se o ambiente local não tiver Postgres acessível para outro comando, `makemigrations` **não** depende de banco — só falha se o Django não conseguir importar os apps.

Conteúdo esperado:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("centralservicos", "0014_alter_tarefa_options_alter_tarefachamado_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="centroatendimento",
            name="ativo",
            field=models.BooleanField(default=True, verbose_name="Ativo?"),
        ),
        migrations.AddField(
            model_name="grupoatendimento",
            name="ativo",
            field=models.BooleanField(default=True, verbose_name="Ativo?"),
        ),
    ]
```

- [x] **Step 2: Conferir que não sobrou nenhuma alteração de model pendente**

Run: `python manage.py makemigrations centralservicos --check --dry-run`
Expected: `No changes detected` (exit code 0).

- [x] **Step 3: Commit**

```bash
git add centralservicos/migrations/0015_centroatendimento_ativo_grupoatendimento_ativo.py
git commit -m "[centralservicos] Adiciona migration do campo ativo em CentroAtendimento e GrupoAtendimento"
```

---

### Task 4: Admin de `CentroAtendimento` — coluna `Ativo?` e detalhe dos Serviços que bloqueiam

**Files:**
- Modify: `centralservicos/admin.py:117-135`

- [x] **Step 1: Implementar**

Substituir a classe `CentroAtendimentoAdmin`:

```python
class CentroAtendimentoAdmin(ModelAdminPlus):
    form = CentroAtendimentoForm
    search_fields = ('nome', 'area__nome')
    list_filter = ('area', 'ativo')
    list_display = ('id', 'nome', 'area', 'eh_local', 'ativo')
    list_display_icons = True
    list_per_page = 25
    readonly_fields = ('get_servicos_ativos_vinculados',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['area'].queryset = AreaAtuacao.objects.filter(pk__in=GestorAreaServico.minhas_areas(request.user))
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(area__in=GestorAreaServico.minhas_areas(request.user)).distinct()

    def get_servicos_ativos_vinculados(self, obj):
        if not obj or not obj.pk:
            return '-'
        servicos_ativos = Servico.objects.filter(centros_atendimento=obj, ativo=True)
        if not servicos_ativos.exists():
            return mark_safe('<span class="false">Nenhum</span>')
        lista = ['<ul>']
        for servico in servicos_ativos:
            lista.append(f'<li>{servico}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_servicos_ativos_vinculados.short_description = 'Serviços Ativos Vinculados (impedem a inativação)'
```

`readonly_fields` sem `fields`/`fieldsets` explícitos no admin faz o Django anexar o campo somente-leitura ao final do formulário de alteração/visualização (`ModelAdmin.get_fields`) — **não** entra na listagem, então não gera consulta extra por linha.

- [x] **Step 2: Commit**

```bash
git add centralservicos/admin.py
git commit -m "[centralservicos] Exibe Ativo? na listagem e Serviços que bloqueiam a inativação no detalhe do Centro de Atendimento"
```

---

### Task 5: Admin de `GrupoAtendimento` — coluna `Ativo?` e detalhe dos Serviços que bloqueiam

**Files:**
- Modify: `centralservicos/admin.py:342-407`

`GrupoAtendimentoAdmin` já tem a coluna `get_servicos_ativos` na listagem (contagem de Serviços ativos do `centro_atendimento`, `centralservicos/admin.py:383-390`) — não é código novo deste demanda, mantenha como está. Só falta o campo `ativo` na listagem e o detalhamento (quais Serviços) na tela de um único registro.

- [x] **Step 1: Implementar**

Em `centralservicos/admin.py`, dentro de `GrupoAtendimentoAdmin`:

1. Ajustar `list_filter` e `list_display`:

```python
    list_filter = ('centro_atendimento__area', 'centro_atendimento', 'campus', 'ativo')
    search_fields = ('nome', 'responsaveis__first_name', 'responsaveis__last_name', 'atendentes__first_name', 'atendentes__last_name')
    list_display = (
        'nome',
        'ativo',
        'grupo_atendimento_superior',
        'campus',
        'get_responsaveis',
        'centro_atendimento',
        'get_atendentes',
        'get_servicos_ativos',
    )
    list_display_icons = True
    list_per_page = 20
    readonly_fields = ('get_servicos_ativos_vinculados',)
```

2. Adicionar, junto aos demais métodos `get_*` da classe (após `get_servicos_ativos`, `centralservicos/admin.py:383-390`):

```python
    def get_servicos_ativos_vinculados(self, obj):
        if not obj or not obj.pk:
            return '-'
        servicos_ativos = Servico.objects.filter(centros_atendimento=obj.centro_atendimento, ativo=True)
        if not servicos_ativos.exists():
            return mark_safe('<span class="false">Nenhum</span>')
        lista = ['<ul>']
        for servico in servicos_ativos:
            lista.append(f'<li>{servico}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_servicos_ativos_vinculados.short_description = 'Serviços Ativos Vinculados (impedem a inativação)'
```

- [x] **Step 2: Commit**

```bash
git add centralservicos/admin.py
git commit -m "[centralservicos] Exibe Ativo? na listagem e Serviços que bloqueiam a inativação no detalhe do Grupo de Atendimento"
```

---

### Task 6: Teste de integração via formulário do admin

**Files:**
- Test: `centralservicos/tests/test_inativacao_atendimento.py`

Garante que a regra do model realmente é aplicada quando os dados chegam pelo caminho que o admin usa (`CentroAtendimentoForm` / `GrupoAtendimentoForm`, ambos com `exclude = ()`, então `full_clean()` do model roda dentro de `form.is_valid()`).

- [x] **Step 1: Escrever o teste que falha**

Adicionar ao final de `centralservicos/tests/test_inativacao_atendimento.py` (e importar `CentroAtendimentoForm`, `GrupoAtendimentoForm` de `centralservicos.forms` no topo do arquivo):

```python
from centralservicos.forms import CentroAtendimentoForm, GrupoAtendimentoForm


@pytest.mark.usefixtures('suap_data')
class TestFormularioAdminInativacao:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_form_centro_atendimento_recusa_inativacao_com_servico_ativo(self):
        centro = self.context.centro_atendimento
        form = CentroAtendimentoForm(
            instance=centro,
            data={'nome': centro.nome, 'eh_local': centro.eh_local, 'area': centro.area_id, 'ativo': False},
        )

        assert form.is_valid() is False
        assert 'Não é possível inativar' in str(form.errors)

    def test_form_grupo_atendimento_recusa_inativacao_com_servico_ativo(self):
        grupo = self.grupo
        form = GrupoAtendimentoForm(
            instance=grupo,
            data={
                'nome': grupo.nome,
                'campus': grupo.campus_id,
                'centro_atendimento': grupo.centro_atendimento_id,
                'responsaveis': [str(self.context.servidor_atendente.get_user().pk)],
                'ativo': False,
            },
        )

        assert form.is_valid() is False
        assert 'Não é possível inativar' in str(form.errors)
```

- [x] **Step 2: Rodar o teste para confirmar que falha**

Run: `pytest -q centralservicos/tests/test_inativacao_atendimento.py -v`
Expected: sem as Tasks 1/2/3 aplicadas isso não aconteceria — mas como este Task roda depois, o esperado aqui é já ver as duas novas funções PASS de primeira (o model já bloqueia). Rode mesmo assim para confirmar que o form realmente propaga o erro do model (não é redundante: form/model podem divergir, ex. se `exclude` do form mudar no futuro).

- [x] **Step 3: Rodar toda a suíte do app para checar regressão**

Run: `pytest -q centralservicos/tests/`
Expected: todos os testes (os novos e os existentes em `test_chamados.py`) PASS.

- [x] **Step 4: Commit**

```bash
git add centralservicos/tests/test_inativacao_atendimento.py
git commit -m "[centralservicos] Testa que os formulários do admin recusam inativação com Serviço ativo vinculado"
```

---

## Self-Review

**Cobertura da demanda** (`.tmp/demandas/demanda-2487/demanda-2487-consolidacao.md`):
- Especificação 1 (permitir inativar, bloqueando com Serviço ativo vinculado) → Tasks 1, 2, 3.
- Especificação 2 (indicação, na listagem/detalhe, do que impede a inativação) → Tasks 4, 5, ajustada conforme feedback do usuário: contagem/booleano cabe na listagem (custo desprezível), mas o detalhamento de **quais** Serviços só é calculado ao abrir um registro específico — evita N+1 queries na listagem de `CentroAtendimento` (que hoje não tem nenhuma coluna calculada) e não duplica o que já existe em `GrupoAtendimento.get_servicos_ativos`.

**Placeholders:** nenhum "TODO"/"implementar depois" — todo código está completo em cada step.

**Consistência de nomes:** `get_servicos_ativos_vinculados` usado igual nos dois admins; `ativo` como nome de campo nos dois models; mensagens de erro começam com "Não é possível inativar." nos dois `clean()`, usadas na asserção dos testes de form.
