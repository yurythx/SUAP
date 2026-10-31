# Aval do Responsável LAI — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inserir a deliberação do Responsável LAI (por dataset em cada PDA) antes da liberação ao CKAN: status por `PDABaseDados`, disparo automático por etapa, tela de deliberação, gate no sync e invalidação por edição.

**Architecture:** Estado `situacao_lai` na relação `PDABaseDados` (PENDENTE→EM_ANALISE→LIBERADO/DEVOLVIDO); histórico auditável em `DeliberacaoLAI`; disparo por flag em `Etapa` engatado em `PlanoDadosAbertos.atualizar_etapa_atual()`; gate no sync CKAN via método de `BaseDados`; tela do LAI no padrão de `matriz_priorizacao` (view + service + template admin-context); grupo/permissão em `permissions.yaml`.

**Tech Stack:** Django 5.2 (SUAP/djtools), django-ninja (não usado aqui), admin `ModelAdminPlus`, templates admin-context.

**Spec:** `docs/superpowers/specs/2026-07-21-dados-abertos-responsavel-lai-design.md` (fonte da verdade das regras).

## Global Constraints

- Idioma pt-BR em código, docstrings, mensagens, templates e permissions.yaml.
- **Migrations só via `python manage.py makemigrations dados_abertos`** — nunca escrever à mão.
- Complexidade ciclomática ≤ 10 nas funções tocadas; tipar parâmetros/retorno das defs novas.
- **Sem testes novos e sem rodar pytest** — política do usuário (testes só sob demanda). Verificação por `ruff`, `makemigrations --check`/`migrate` e `sync_permissions`.
- **Commits são do usuário** — os "Pontos de commit" são sugestões; não commitar por conta própria salvo pedido explícito.
- Enums do módulo seguem o padrão `LABELS` + `get_choices()` (ver `dados_abertos/enums.py`).
- Templates ficam em `dados_abertos/templates/dadosabertos/`; URLs no namespace `dados_abertos:`.
- Sem `style=` inline em template; usar componentes/classes existentes do módulo (espelhar `matriz_priorizacao.html`).
- Branch: `dados-abertos-responsavel-lai` (já criada a partir da master).

---

### Task 1: Enum, campos, model `DeliberacaoLAI` e migração

**Files:**
- Modify: `dados_abertos/enums.py`
- Modify: `dados_abertos/models/pda_base_dados.py`
- Modify: `dados_abertos/models/etapa.py`
- Create: `dados_abertos/models/deliberacao_lai.py`
- Modify: `dados_abertos/models/__init__.py`
- Create (gerada): `dados_abertos/migrations/00NN_*.py`

**Interfaces:**
- Produces: `SituacaoLAI` (enum); `PDABaseDados.situacao_lai` (int, default PENDENTE), `PDABaseDados.motivo_reabertura` (char); `Etapa.dispara_analise_lai` (bool, default False); model `DeliberacaoLAI` com permissão `deliberar_lai`.

- [ ] **Step 1: Enum `SituacaoLAI` em `enums.py`** (adicionar ao fim do arquivo)

```python
class SituacaoLAI:
    PENDENTE = 1
    EM_ANALISE = 2
    LIBERADO = 3
    DEVOLVIDO = 4

    LABELS = {
        PENDENTE: 'Pendente',
        EM_ANALISE: 'Em análise do LAI',
        LIBERADO: 'Liberado',
        DEVOLVIDO: 'Devolvido para ajustes',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())
```

- [ ] **Step 2: Campos em `PDABaseDados`** — adicionar após `submetida_consulta_publica` (import do enum no topo do arquivo: `from ..enums import Periodicidade, SituacaoLAI`)

```python
    situacao_lai = models.IntegerField(
        _('Situação LAI'),
        choices=SituacaoLAI.get_choices(),
        default=SituacaoLAI.PENDENTE,
        help_text=_('Situação da deliberação do Responsável LAI para esta base neste PDA.'),
    )
    motivo_reabertura = models.CharFieldPlus(
        _('Motivo da reabertura'),
        max_length=255,
        blank=True,
        help_text=_('Preenchido quando a liberação é invalidada por edição do conteúdo.'),
    )
```

- [ ] **Step 3: Flag em `Etapa`** — adicionar após `descricao`

```python
    dispara_analise_lai = models.BooleanFieldPlus(
        _('Dispara análise do LAI'),
        default=False,
        help_text=_('Quando o PDA atinge esta etapa, todos os seus datasets pendentes entram em análise do Responsável LAI.'),
    )
```

- [ ] **Step 4: Model `DeliberacaoLAI`** — criar `dados_abertos/models/deliberacao_lai.py`

```python
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from djtools.db import models
from djtools.db.models import ModelPlus

from ..enums import SituacaoLAI


class DeliberacaoLAI(ModelPlus):
    """Registro (histórico) de cada deliberação do Responsável LAI sobre um dataset em um PDA."""

    DECISAO_CHOICES = [
        (SituacaoLAI.LIBERADO, 'Liberado'),
        (SituacaoLAI.DEVOLVIDO, 'Devolvido para ajustes'),
    ]

    pda_base_dados = models.ForeignKeyPlus(
        'dados_abertos.PDABaseDados',
        on_delete=models.CASCADE,
        related_name='deliberacoes_lai',
        verbose_name=_('Base de Dados no PDA'),
    )
    decisao = models.IntegerField(_('Decisão'), choices=DECISAO_CHOICES)
    parecer = models.TextField(_('Parecer'), blank=True, help_text=_('Parecer do Responsável LAI. Obrigatório na devolução.'))
    deliberado_por = models.ForeignKeyPlus('comum.Vinculo', on_delete=models.SET_NULL, null=True, verbose_name=_('Deliberado por'))
    data_deliberacao = models.DateTimeFieldPlus(_('Data da deliberação'), auto_now_add=True)
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.TextField(_('User agent'), blank=True)

    class Meta:
        verbose_name = _('Deliberação LAI')
        verbose_name_plural = _('Deliberações LAI')
        ordering = ('-data_deliberacao',)
        permissions = [('deliberar_lai', 'Pode deliberar sobre a liberação LAI de datasets')]

    def __str__(self):
        return f'{self.get_decisao_display()} — {self.pda_base_dados}'

    def clean(self):
        super().clean()
        if self.decisao == SituacaoLAI.DEVOLVIDO and not (self.parecer or '').strip():
            raise ValidationError({'parecer': _('O parecer é obrigatório ao devolver o dataset para ajustes.')})
```

- [ ] **Step 5: Re-export em `models/__init__.py`** — adicionar `from .deliberacao_lai import DeliberacaoLAI` e `'DeliberacaoLAI'` no `__all__` (ordem alfabética aproximada).

- [ ] **Step 6: Gerar a migração**

Run: `DATABASE_PASSWORD=postgres python manage.py makemigrations dados_abertos`
Esperado: cria migração com `DeliberacaoLAI` (+ permissão `deliberar_lai`), `PDABaseDados.situacao_lai`, `PDABaseDados.motivo_reabertura`, `Etapa.dispara_analise_lai`.

- [ ] **Step 7: Verificar**

```bash
uv run ruff check dados_abertos/enums.py dados_abertos/models/
DATABASE_PASSWORD=postgres python manage.py makemigrations dados_abertos --check --dry-run && echo "migração consistente"
```

- [ ] **Step 8: Ponto de commit (usuário)** — `[dados_abertos] Modelando deliberação LAI (situação por dataset, flag de etapa, histórico)`

---

### Task 2: Disparo automático da análise por etapa

**Files:**
- Modify: `dados_abertos/models/plano_dados_abertos.py`

**Interfaces:**
- Consumes: `Etapa.dispara_analise_lai`, `PDABaseDados.situacao_lai`, `SituacaoLAI` (Task 1).
- Produces: `PlanoDadosAbertos._disparar_analise_lai_se_necessario()` chamado ao fim de `atualizar_etapa_atual`.

- [ ] **Step 1: Import do enum** no topo de `plano_dados_abertos.py`: `from dados_abertos.enums import SituacaoPDA, SituacaoLAI` (mantendo o import existente de `SituacaoPDA`).

- [ ] **Step 2: Helper de disparo** — adicionar método na classe

```python
    def _disparar_analise_lai_se_necessario(self):
        """Ao atingir uma etapa marcada com dispara_analise_lai, joga os datasets PENDENTE para EM_ANALISE.

        Idempotente: só afeta relações em PENDENTE (não mexe em LIBERADO/DEVOLVIDO/EM_ANALISE).
        """
        etapa = self.etapa_atual
        if not etapa or not getattr(etapa, 'dispara_analise_lai', False):
            return
        self.bases_relacionadas.filter(situacao_lai=SituacaoLAI.PENDENTE).update(situacao_lai=SituacaoLAI.EM_ANALISE)
```

- [ ] **Step 3: Chamar ao fim de `atualizar_etapa_atual`** — em cada `return`/saída onde `etapa_atual` foi definida, o disparo precisa rodar. Para manter simples e com complexidade baixa, chamar o helper no início do `save`-driven flow: adicionar `self._disparar_analise_lai_se_necessario()` **imediatamente antes de cada `return`** dos ramos que definem `etapa_atual` para uma etapa (os dois ramos que fazem `self.etapa_atual = etapa`/`= ultima`). Alternativa mais limpa e preferida: extrair o corpo atual de `atualizar_etapa_atual` para `_recalcular_etapa_atual()` e fazer:

```python
    def atualizar_etapa_atual(self):
        self._recalcular_etapa_atual()
        self._disparar_analise_lai_se_necessario()
```

Renomear o método existente para `_recalcular_etapa_atual` (mesmo corpo atual, sem alterações internas). Isso mantém a complexidade de cada função ≤ 10 e centraliza o disparo.

- [ ] **Step 4: Verificar**

```bash
uv run ruff check dados_abertos/models/plano_dados_abertos.py
grep -n "_recalcular_etapa_atual\|_disparar_analise_lai" dados_abertos/models/plano_dados_abertos.py
```

- [ ] **Step 5: Ponto de commit (usuário)** — `[dados_abertos] Disparando análise do LAI ao PDA atingir a etapa marcada`

---

### Task 3: Gate no envio ao CKAN

**Files:**
- Modify: `dados_abertos/models/base_dados.py` (método de gate)
- Modify: `dados_abertos/admin/base_dados.py` (aplicar o gate)

**Interfaces:**
- Consumes: `PDABaseDados.situacao_lai`, `SituacaoLAI`.
- Produces: `BaseDados.lai_liberada_para_sync() -> bool` e `BaseDados.motivo_bloqueio_lai() -> str` (mensagem quando bloqueada).

- [ ] **Step 1: Métodos de gate em `BaseDados`** (import: `from dados_abertos.enums import EstadoCKAN, SituacaoLAI`)

```python
    def lai_liberada_para_sync(self) -> bool:
        """True se a base pode ir ao CKAN: tem ≥1 relação PDABaseDados e TODAS estão LIBERADO."""
        relacoes = list(self.relacoes_pda.values_list('situacao_lai', flat=True))
        return bool(relacoes) and all(s == SituacaoLAI.LIBERADO for s in relacoes)

    def motivo_bloqueio_lai(self) -> str:
        """Mensagem explicando por que o sync está bloqueado pela deliberação LAI (vazio se liberado)."""
        relacoes = list(self.relacoes_pda.values_list('situacao_lai', flat=True))
        if not relacoes:
            return 'Base não vinculada a nenhum PDA — não passou pela análise do Responsável LAI.'
        if all(s == SituacaoLAI.LIBERADO for s in relacoes):
            return ''
        return 'A base possui datasets pendentes, em análise ou devolvidos pelo Responsável LAI. Só é possível sincronizar após a liberação em todos os PDAs.'
```

- [ ] **Step 2: Aplicar o gate nas 3 entradas de sync** em `admin/base_dados.py`.

Em `sync_dataset_view` e `sync_dataset_resources_view`, após obter `obj` e antes de chamar o service:

```python
        if not obj.lai_liberada_para_sync():
            self.message_user(request, obj.motivo_bloqueio_lai(), level=messages.ERROR)
            return HttpResponseRedirect(list_url)
```

Em `action_sync_ckan` e `action_sync_resources_ckan`, filtrar o queryset e avisar o que foi bloqueado:

```python
        bloqueadas = [b for b in queryset if not b.lai_liberada_para_sync()]
        liberadas = queryset.exclude(pk__in=[b.pk for b in bloqueadas])
        if bloqueadas:
            nomes = ', '.join(str(b) for b in bloqueadas[:5])
            self.message_user(request, _('%(n)s base(s) bloqueada(s) pela análise LAI e ignorada(s): %(nomes)s') % {'n': len(bloqueadas), 'nomes': nomes}, level=messages.WARNING)
        if not liberadas:
            return
        # usar `liberadas` no lugar de `queryset` na chamada ao service
```

(Substituir `queryset` por `liberadas` nas chamadas `sync_dataset_with_ckan(...)` / `sync_dataset_resources_with_ckan(...)` dessas duas actions.)

- [ ] **Step 3: Verificar**

```bash
uv run ruff check dados_abertos/models/base_dados.py dados_abertos/admin/base_dados.py
```

- [ ] **Step 4: Ponto de commit (usuário)** — `[dados_abertos] Bloqueando sync CKAN de bases sem liberação LAI em todos os PDAs`

---

### Task 4: Invalidação da liberação por edição do conteúdo

**Files:**
- Modify: `dados_abertos/models/base_dados.py`
- Modify: `dados_abertos/models/recurso_dados.py`

**Interfaces:**
- Consumes: `PDABaseDados.situacao_lai`, `motivo_reabertura`, `SituacaoLAI`.
- Produces: reversão `LIBERADO → EM_ANALISE` quando o conteúdo relevante muda.

- [ ] **Step 1: Helper compartilhado** em `base_dados.py` (função de módulo, reutilizada pelos dois `save`)

```python
import datetime
import logging

logger = logging.getLogger(__name__)


def reabrir_lai_por_edicao(base) -> None:
    """Reverte para EM_ANALISE as relações LIBERADO da base (invalidação por edição de conteúdo)."""
    from dados_abertos.enums import SituacaoLAI

    liberadas = base.relacoes_pda.filter(situacao_lai=SituacaoLAI.LIBERADO)
    if not liberadas.exists():
        return
    hoje = datetime.date.today().strftime('%d/%m/%Y')
    liberadas.update(situacao_lai=SituacaoLAI.EM_ANALISE, motivo_reabertura=f'Reaberto por edição do conteúdo em {hoje}.')
    logger.info('LAI: base %s reaberta para análise por edição de conteúdo.', base.pk)
```

- [ ] **Step 2: Hook em `BaseDados.save`** — comparar campos relevantes e reabrir se mudou

```python
    _CAMPOS_CONTEUDO_LAI = ('titulo', 'notas', 'tags', 'tema_id', 'licenca_id', 'organizacao_id')

    def save(self, *args, **kwargs):
        conteudo_mudou = False
        if self.pk:
            anterior = BaseDados.objects.filter(pk=self.pk).only(*self._CAMPOS_CONTEUDO_LAI).first()
            if anterior:
                conteudo_mudou = any(getattr(anterior, c) != getattr(self, c) for c in self._CAMPOS_CONTEUDO_LAI)
        super().save(*args, **kwargs)
        if conteudo_mudou:
            reabrir_lai_por_edicao(self)
```

(Se `BaseDados` ainda não tiver `save`, este é novo; preservar o `clean()` existente.)

- [ ] **Step 3: Hook em `RecursoDados.save`** — o recurso muda o conteúdo do dataset (`self.dataset`). Ao fim do `save` existente, após `super().save(...)`:

```python
        # Invalidação LAI: editar/adicionar recurso muda o conteúdo publicado do dataset.
        from dados_abertos.models.base_dados import reabrir_lai_por_edicao

        if self.dataset_id:
            reabrir_lai_por_edicao(self.dataset)
```

(Aplica em criação e atualização de recurso — qualquer mexida nos arquivos/dados invalida, conforme §5.5.)

- [ ] **Step 4: Verificar**

```bash
uv run ruff check dados_abertos/models/base_dados.py dados_abertos/models/recurso_dados.py
```

- [ ] **Step 5: Ponto de commit (usuário)** — `[dados_abertos] Invalidando liberação LAI ao editar conteúdo do dataset`

---

### Task 5: Tela de deliberação do LAI

**Files:**
- Create: `dados_abertos/services/lai_service.py`
- Modify: `dados_abertos/views.py`
- Modify: `dados_abertos/urls.py`
- Create: `dados_abertos/templates/dadosabertos/deliberacao_lai.html`
- Modify: `dados_abertos/menu.yaml`

**Interfaces:**
- Consumes: `PDABaseDados`, `DeliberacaoLAI`, `SituacaoLAI`.
- Produces: view `deliberacao_lai`, rota `dados_abertos:deliberacao_lai`, service `build_deliberacao_lai_data`/`registrar_deliberacao`.

- [ ] **Step 1: Service `lai_service.py`**

```python
from dataclasses import dataclass

from django.db import transaction

from dados_abertos.enums import SituacaoLAI
from dados_abertos.models import DeliberacaoLAI, PDABaseDados, PlanoDadosAbertos


@dataclass(frozen=True)
class DeliberacaoLAIData:
    pda: PlanoDadosAbertos | None
    relacoes: list  # PDABaseDados em EM_ANALISE do PDA


def build_deliberacao_lai_data(pda: PlanoDadosAbertos | None) -> DeliberacaoLAIData:
    """Datasets em análise do LAI para o PDA (base + recursos pré-carregados)."""
    if not pda:
        return DeliberacaoLAIData(pda=None, relacoes=[])
    relacoes = list(
        PDABaseDados.objects.filter(pda=pda, situacao_lai=SituacaoLAI.EM_ANALISE)
        .select_related('base_dados', 'base_dados__organizacao')
        .prefetch_related('base_dados__recursos')
        .order_by('base_dados__titulo')
    )
    return DeliberacaoLAIData(pda=pda, relacoes=relacoes)


def registrar_deliberacao(relacao_id: int, decisao: int, parecer: str, vinculo, ip: str, user_agent: str) -> PDABaseDados:
    """Registra a deliberação do LAI e atualiza a situação da relação. Transação atômica."""
    with transaction.atomic():
        relacao = PDABaseDados.objects.select_for_update().get(pk=relacao_id, situacao_lai=SituacaoLAI.EM_ANALISE)
        deliberacao = DeliberacaoLAI(
            pda_base_dados=relacao,
            decisao=decisao,
            parecer=(parecer or '').strip(),
            deliberado_por=vinculo,
            ip=ip or None,
            user_agent=(user_agent or '')[:500],
        )
        deliberacao.full_clean()  # valida parecer obrigatório na devolução
        deliberacao.save()
        relacao.situacao_lai = decisao  # LIBERADO ou DEVOLVIDO (mesmos valores do enum)
        relacao.motivo_reabertura = ''
        relacao.save(update_fields=['situacao_lai', 'motivo_reabertura'])
    return relacao
```

- [ ] **Step 2: View `deliberacao_lai`** em `views.py` (imports: `from .enums import EstadoCKAN, SituacaoLAI`; `from .services.lai_service import build_deliberacao_lai_data, registrar_deliberacao`; `from .models import DeliberacaoLAI` conforme necessário)

```python
def _client_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')


@login_required
def deliberacao_lai(request):
    if not request.user.has_perm('dados_abertos.deliberar_lai'):
        raise PermissionDenied

    title = 'Deliberação LAI'
    pda_id = request.GET.get('pda') or request.POST.get('pda')
    pda = PlanoDadosAbertos.objects.filter(pk=pda_id).first() if pda_id else PlanoDadosAbertos.objects.first()

    if request.method == 'POST':
        try:
            vinculo = request.user.get_vinculo()
        except Exception:
            vinculo = None
        try:
            registrar_deliberacao(
                relacao_id=int(request.POST['relacao_id']),
                decisao=int(request.POST['decisao']),
                parecer=request.POST.get('parecer', ''),
                vinculo=vinculo,
                ip=_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(request, 'Deliberação registrada.')
        except PDABaseDados.DoesNotExist:
            messages.warning(request, 'Este dataset não está mais em análise.')
        except ValidationError as e:
            messages.error(request, '; '.join(m for msgs in e.message_dict.values() for m in msgs))
        return redirect(f"{reverse('dados_abertos:deliberacao_lai')}?pda={pda.pk if pda else ''}")

    data = build_deliberacao_lai_data(pda)
    contexto = {
        **admin_site.each_context(request),
        'title': title,
        'pda': pda,
        'pdas': PlanoDadosAbertos.objects.all(),
        'relacoes': data.relacoes,
        'SituacaoLAI': SituacaoLAI,
    }
    return render(request, 'dadosabertos/deliberacao_lai.html', contexto)
```

(Adicionar `from django.core.exceptions import PermissionDenied, ValidationError` ao import existente de `django.core.exceptions`.)

- [ ] **Step 3: Rota** em `urls.py` — adicionar após a rota `matriz_priorizacao`:

```python
    path('deliberacao_lai/', views.deliberacao_lai, name='deliberacao_lai'),
```

- [ ] **Step 4: Template** `deliberacao_lai.html` — espelhar a estrutura de `matriz_priorizacao.html` (admin-context). Estrutura mínima:

```html
{% extends "admin/base_site.html" %}
{% block content %}
<h1>Deliberação LAI{% if pda %} — {{ pda }}{% endif %}</h1>

<form method="get" class="mb-3">
    <label>PDA:
        <select name="pda" onchange="this.form.submit()">
            {% for p in pdas %}
                <option value="{{ p.pk }}" {% if pda and p.pk == pda.pk %}selected{% endif %}>{{ p }}</option>
            {% endfor %}
        </select>
    </label>
</form>

{% if not relacoes %}
    <p>Nenhum dataset em análise do LAI neste PDA.</p>
{% else %}
    {% for relacao in relacoes %}
        <div class="module">
            <h2>{{ relacao.base_dados.titulo }}</h2>
            <p>{{ relacao.base_dados.notas }}</p>
            <ul>
                {% for r in relacao.base_dados.recursos.all %}
                    <li>{{ r.nome }} ({{ r.formato }})</li>
                {% endfor %}
            </ul>
            <form method="post">
                {% csrf_token %}
                <input type="hidden" name="pda" value="{{ pda.pk }}">
                <input type="hidden" name="relacao_id" value="{{ relacao.pk }}">
                <label>Parecer:<br><textarea name="parecer" rows="3" cols="60"></textarea></label><br>
                <button type="submit" name="decisao" value="{{ SituacaoLAI.LIBERADO }}" class="button">Liberar</button>
                <button type="submit" name="decisao" value="{{ SituacaoLAI.DEVOLVIDO }}" class="button">Devolver para ajustes</button>
            </form>
        </div>
    {% endfor %}
{% endif %}
{% endblock %}
```

(Se `matriz_priorizacao.html` usar um base template/estilo específico do módulo, seguir o mesmo `{% extends %}` e blocos; validar com `djlint` no Step 6.)

- [ ] **Step 5: Menu** — adicionar em `dados_abertos/menu.yaml`:

```yaml
Dados Abertos::Deliberação LAI:
  permissions_required:
  - dados_abertos.deliberar_lai
  url: /dados_abertos/deliberacao_lai/
```

- [ ] **Step 6: Verificar**

```bash
uv run ruff check dados_abertos/services/lai_service.py dados_abertos/views.py
uv run djlint dados_abertos/templates/dadosabertos/deliberacao_lai.html --profile django || true
DATABASE_PASSWORD=postgres python manage.py shell -c "import dados_abertos.views"  # importa sem erro
```

- [ ] **Step 7: Ponto de commit (usuário)** — `[dados_abertos] Tela de deliberação do Responsável LAI`

---

### Task 6: Grupo/permissão, admin e "Reenviar ao LAI"

**Files:**
- Modify: `dados_abertos/permissions.yaml`
- Modify: `dados_abertos/admin/pda_base_dados.py`
- Modify: `dados_abertos/admin/etapa.py`
- Create/Modify: `dados_abertos/admin/deliberacao_lai.py` + `dados_abertos/admin/__init__.py`

**Interfaces:**
- Consumes: tudo das tasks 1–5.
- Produces: grupo "Responsável LAI"; `situacao_lai` visível no admin; ação "Reenviar ao LAI"; admin read-only de `DeliberacaoLAI`.

- [ ] **Step 1: Grupo em `permissions.yaml`** — adicionar ao fim:

```yaml
Responsável LAI:
  app_manager: dados_abertos
  dados_abertos:
    deliberacaolai:
    - deliberar_lai
    - view_deliberacaolai
    - add_deliberacaolai
    pdabasedados:
    - view_pdabasedados
    basedados:
    - view_basedados
    recursodados:
    - view_recursodados
    planodadosabertos:
    - view_planodadosabertos
```

(Só `view` + `deliberar_lai`. A tela do LAI atualiza `situacao_lai` via `registrar_deliberacao` (service, autorizado pela permissão `deliberar_lai` na view) — não depende de `change_pdabasedados`. A ação "Reenviar ao LAI" é do Gestor, no admin de `PDABaseDados`, sob a permissão de admin já existente do gestor.)

- [ ] **Step 2: `PDABaseDadosAdmin`** — exibir `situacao_lai` (com `get_situacao_lai_display`) no `list_display`, adicionar a `list_filter`, e ação "Reenviar ao LAI":

```python
    @admin.action(description=_('Reenviar ao LAI (datasets devolvidos)'))
    def action_reenviar_lai(self, request, queryset):
        from dados_abertos.enums import SituacaoLAI

        n = queryset.filter(situacao_lai=SituacaoLAI.DEVOLVIDO).update(situacao_lai=SituacaoLAI.EM_ANALISE, motivo_reabertura='')
        self.message_user(request, _('%(n)s dataset(s) reenviado(s) ao LAI.') % {'n': n})
```

Adicionar `'action_reenviar_lai'` em `actions`. (Se o admin não existir/for mínimo, criar com `ModelAdminPlus`.)

- [ ] **Step 3: `EtapaAdmin`** — expor `dispara_analise_lai` em `list_display` e `fields`/`list_editable` (para o gestor marcar a etapa).

- [ ] **Step 4: Admin read-only de `DeliberacaoLAI`** — `dados_abertos/admin/deliberacao_lai.py`

```python
from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus

from dados_abertos.models import DeliberacaoLAI


@admin.register(DeliberacaoLAI)
class DeliberacaoLAIAdmin(ModelAdminPlus):
    list_display = ('pda_base_dados', 'get_decisao_display', 'deliberado_por', 'data_deliberacao')
    list_filter = ('decisao',)
    readonly_fields = ('pda_base_dados', 'decisao', 'parecer', 'deliberado_por', 'data_deliberacao', 'ip', 'user_agent')

    def has_add_permission(self, request):
        return False  # deliberação só via tela do LAI

    def has_change_permission(self, request, obj=None):
        return False
```

Registrar em `admin/__init__.py`: `from .deliberacao_lai import *` (e garantir `__all__`/import compatível com o padrão do módulo).

- [ ] **Step 5: Verificar**

```bash
uv run ruff check dados_abertos/admin/
DATABASE_PASSWORD=postgres python manage.py sync_permissions dados_abertos 2>&1 | tail -5   # cria o grupo "Responsável LAI"
```

- [ ] **Step 6: Ponto de commit (usuário)** — `[dados_abertos] Grupo Responsável LAI, admin e ação Reenviar ao LAI`

---

### Task 7: Verificação integrada

- [ ] **Step 1: Migrar e checar consistência**

```bash
DATABASE_PASSWORD=postgres python manage.py makemigrations dados_abertos --check --dry-run && echo "sem migração pendente"
DATABASE_PASSWORD=postgres python manage.py migrate dados_abertos 2>&1 | tail -5
```

- [ ] **Step 2: Lint completo dos arquivos tocados**

```bash
uv run ruff format dados_abertos/
uv run ruff check dados_abertos/
```

- [ ] **Step 3: Sanidade de import sob Django**

```bash
DATABASE_PASSWORD=postgres python manage.py shell -c "
import dados_abertos.views, dados_abertos.admin
from dados_abertos.models import DeliberacaoLAI, PDABaseDados, Etapa, BaseDados
from dados_abertos.enums import SituacaoLAI
from dados_abertos.services.lai_service import build_deliberacao_lai_data, registrar_deliberacao
assert hasattr(PDABaseDados, 'situacao_lai') and hasattr(Etapa, 'dispara_analise_lai')
assert hasattr(BaseDados, 'lai_liberada_para_sync')
print('OK')
"
```

- [ ] **Step 4: `sync_permissions`** confirma o grupo "Responsável LAI" com `deliberar_lai`.

- [ ] **Step 5 (opcional, sob pedido do usuário):** escrever testes cobrindo disparo por etapa, gate de sync (todas LIBERADO), invalidação por edição e registrar_deliberacao (parecer obrigatório).

- [ ] **Step 6: Usuário revisa o diff e commita/pusha; abrir MR (mr-format) quando pedido.**
