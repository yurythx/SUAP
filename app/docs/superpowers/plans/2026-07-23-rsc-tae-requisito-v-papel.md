# Requisito V — Modelo fiel ao decreto (papel titular/substituto) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir o Requisito V do RSC-TAE para refletir o decreto (4 itens, não 8), tornando titular/substituto um atributo (`papel`) de cada comprovante em vez de itens separados — eliminando a dupla contagem que inflava o número de itens.

**Architecture:** Cada item canônico do Req V passa a carregar duas taxas (titular = `grupo.pontuacao_unidade`; substituto = novo campo `pontuacao_unidade_substituto`). Cada `RolSaberCompetenciaAnexo` ganha `papel`. Todo o cálculo de pontos por item passa a somar, por anexo, `anos_pontuáveis(anexo) × taxa(papel)` — centralizado num helper único por onde todos os sites de agregação passam. Uma migração de dados funde os 8 itens em 4 (repontando anexos/preenchimentos e marcando `papel`), preservando a pontuação.

**Tech Stack:** Django 5.2, `djtools.db.models.ModelPlus`, pytest, `settings_test` (Postgres tunado), fixtures JSON, JS vanilla (`rsc-tae.js`), templates Django (`super_template`).

## Global Constraints

- Idioma pt-BR em identificadores, comentários, mensagens e docs.
- Ruff: line length 150, single quotes; complexidade ciclomática ≤ 10 nas funções tocadas.
- Migrations sempre via `python manage.py makemigrations` — nunca escrever à mão.
- `USE_TZ=False` — usar `.date()`/`.strftime()` direto, sem `timezone.localtime()`/`make_aware`.
- Testes com `pytest` (não `manage.py test`); DB de teste via `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --reuse-db`.
- Soft-delete = `ativo=False` (convenção existente; itens inativos são filtrados por `ativo=True`).
- `papel` é **obrigatório** nos itens `aceita_papel` (sem valor padrão) — validado na conclusão do preenchimento.
- **Pontuação do histórico deve permanecer idêntica** após a migração.
- Pares canônicos do Req V (id titular → id substituto, taxas): CD-02 `33→34` (9,0 / 4,5); CD-03/04 `35→36` (7,5 / 3,0); FG-01/02 `37→38` (4,5 / 1,5); FG-03+ `39→40` (3,0 / 1,0). A migração deve casar por **título** (sufixo "— titular"/"— substituto"), não por id fixo.

---

### Task 1: Campos de model (`aceita_papel`, `pontuacao_unidade_substituto`, `papel`)

**Files:**
- Modify: `rsc_tae/models/rol.py` (classe `RolSaberCompetencia`)
- Modify: `rsc_tae/models/anexo.py` (classe `RolSaberCompetenciaAnexo`)
- Create (via makemigrations): `rsc_tae/migrations/0007_*.py`
- Test: `rsc_tae/tests/test_papel_reqv.py`

**Interfaces:**
- Produces:
  - `RolSaberCompetencia.aceita_papel: bool` (default `False`)
  - `RolSaberCompetencia.pontuacao_unidade_substituto: Decimal | None`
  - `RolSaberCompetencia.PAPEL_TITULAR = 'titular'`, `PAPEL_SUBSTITUTO = 'substituto'`, `PAPEL_CHOICES`
  - `RolSaberCompetenciaAnexo.papel: str | None` (choices `PAPEL_CHOICES`)

- [ ] **Step 1: Escrever o teste dos novos campos**

Criar `rsc_tae/tests/test_papel_reqv.py`:

```python
from decimal import Decimal

import pytest

from rsc_tae.models import GrupoSaberCompetencia, RolSaberCompetencia, Requisito


@pytest.mark.django_db(databases='__all__')
class TestCamposPapel:
    def test_item_aceita_papel_com_taxa_substituto(self):
        req = Requisito.objects.create(numero=99, descricao='X', descricao_curta='X', numeral_romano='X')
        grupo = GrupoSaberCompetencia.objects.create(requisito=req, numero=1, pontuacao_unidade=Decimal('9.000'), descricao='g')
        item = RolSaberCompetencia.objects.create(
            numero=1, grupo=grupo, titulo='CD-02', descricao='d', unidade_medida='ano',
            item_temporal=True, aceita_papel=True, pontuacao_unidade_substituto=Decimal('4.500'),
        )
        assert item.aceita_papel is True
        assert item.pontuacao_unidade == Decimal('9.000')          # titular vem do grupo
        assert item.pontuacao_unidade_substituto == Decimal('4.500')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: FAIL — `TypeError`/`FieldError` (campos inexistentes).

- [ ] **Step 3: Adicionar os campos em `rol.py`**

Em `RolSaberCompetencia`, logo após `item_temporal`:

```python
    PAPEL_TITULAR = 'titular'
    PAPEL_SUBSTITUTO = 'substituto'
    PAPEL_CHOICES = (
        (PAPEL_TITULAR, 'Titular'),
        (PAPEL_SUBSTITUTO, 'Substituto'),
    )

    aceita_papel = models.BooleanField(
        _('Aceita papel (titular/substituto)'),
        default=False,
        help_text=_('Item cuja pontuação por unidade muda conforme o papel: titular usa a taxa do grupo; substituto usa pontuacao_unidade_substituto.'),
    )
    pontuacao_unidade_substituto = models.DecimalField(
        _('Pontuação por unidade (substituto)'),
        max_digits=5,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Taxa por unidade quando o papel do comprovante é substituto. Só usada quando aceita_papel=True.'),
    )
```

- [ ] **Step 4: Adicionar `papel` em `anexo.py`**

Em `RolSaberCompetenciaAnexo` (após `data_fim`):

```python
    papel = models.CharField(
        _('Papel'),
        max_length=20,
        null=True,
        blank=True,
        choices=(('titular', 'Titular'), ('substituto', 'Substituto')),
        help_text=_('Titular ou substituto — obrigatório nos itens do Requisito V (aceita_papel). Define a taxa de pontuação do período.'),
    )
```

- [ ] **Step 5: Gerar a migration**

Run: `DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings uv run python manage.py makemigrations rsc_tae`
Expected: cria `0007_*` com os 3 campos.

- [ ] **Step 6: Rodar o teste e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -x --no-cov --create-db -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add rsc_tae/models/rol.py rsc_tae/models/anexo.py rsc_tae/migrations/0007_*.py rsc_tae/tests/test_papel_reqv.py
git commit -m "[rsc_tae] Campos de papel (titular/substituto) no Requisito V"
```

---

### Task 2: Helper de cálculo por papel (fonte única)

**Files:**
- Modify: `rsc_tae/models/anexo.py` (novas funções `taxa_por_papel`, `pontos_anexo`, `pontos_item_anexos`)
- Test: `rsc_tae/tests/test_papel_reqv.py`

**Interfaces:**
- Consumes: `RolSaberCompetencia.aceita_papel`, `.pontuacao_unidade`, `.pontuacao_unidade_substituto`; `unidades_pontuaveis(item, unidades)`.
- Produces:
  - `taxa_por_papel(item, papel) -> Decimal`
  - `pontos_anexo(item, unidades, papel) -> Decimal` — pontos pontuáveis de UM anexo (anos × taxa do papel).
  - `pontos_item_anexos(item, anexos) -> Decimal` — soma dos pontos de uma lista de anexos (cada um com `.pontuacao` e `.papel`).

- [ ] **Step 1: Escrever os testes do cálculo por papel**

Acrescentar a `rsc_tae/tests/test_papel_reqv.py`:

```python
from types import SimpleNamespace

from rsc_tae.models.anexo import taxa_por_papel, pontos_anexo, pontos_item_anexos


class _ItemFake:
    def __init__(self, temporal, aceita, tit, sub):
        self.item_temporal = temporal
        self.aceita_papel = aceita
        self.pontuacao_unidade = tit
        self.pontuacao_unidade_substituto = sub


def test_taxa_por_papel_usa_substituto():
    item = _ItemFake(True, True, Decimal('9'), Decimal('4.5'))
    assert taxa_por_papel(item, 'titular') == Decimal('9')
    assert taxa_por_papel(item, 'substituto') == Decimal('4.5')


def test_taxa_item_sem_papel_ignora_substituto():
    item = _ItemFake(True, False, Decimal('9'), None)
    assert taxa_por_papel(item, 'substituto') == Decimal('9')  # aceita_papel=False -> sempre titular


def test_pontos_item_soma_por_papel():
    item = _ItemFake(True, True, Decimal('9'), Decimal('4.5'))
    # 13 meses -> 1 ano pontuável (fração <=6? 13-12=1 -> 1 ano); 7 meses -> 1 ano
    anexos = [SimpleNamespace(pontuacao=Decimal('13'), papel='titular'),
              SimpleNamespace(pontuacao=Decimal('7'), papel='substituto')]
    # titular: 1*9=9 ; substituto: 1*4.5=4.5 ; total=13.5
    assert pontos_item_anexos(item, anexos) == Decimal('13.5')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: FAIL — `ImportError` (funções inexistentes).

- [ ] **Step 3: Implementar em `anexo.py`** (após `unidades_pontuaveis_anexos`)

```python
def taxa_por_papel(item, papel) -> Decimal:
    """Taxa por unidade do item conforme o papel do comprovante.

    Para itens com ``aceita_papel``: 'substituto' usa ``pontuacao_unidade_substituto``;
    qualquer outro papel (inclusive None) usa a taxa titular (``pontuacao_unidade``).
    Para itens sem papel, sempre a taxa única.
    """
    if getattr(item, 'aceita_papel', False) and papel == item.PAPEL_SUBSTITUTO:
        return item.pontuacao_unidade_substituto or Decimal('0')
    return item.pontuacao_unidade or Decimal('0')


def pontos_anexo(item, unidades, papel) -> Decimal:
    """Pontos pontuáveis de UM anexo: anos pontuáveis (ou unidades) × taxa do papel."""
    return unidades_pontuaveis(item, unidades) * taxa_por_papel(item, papel)


def pontos_item_anexos(item, anexos) -> Decimal:
    """Soma dos pontos de uma coleção de anexos, cada um com ``.pontuacao`` (unidades/meses) e ``.papel``."""
    total = Decimal('0')
    for anexo in anexos:
        unidades = getattr(anexo, 'pontuacao', None) or Decimal('0')
        total += pontos_anexo(item, unidades, getattr(anexo, 'papel', None))
    return total
```

- [ ] **Step 4: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rsc_tae/models/anexo.py rsc_tae/tests/test_papel_reqv.py
git commit -m "[rsc_tae] Helper de cálculo de pontos por papel (titular/substituto)"
```

---

### Task 3: Rotear todos os sites de agregação pelo helper por papel

O cálculo atual `item.pontuacao_unidade × unidades_pontuaveis_anexos(item, unidades_anexos)` assume taxa única. Trocar por `pontos_item_anexos(item, anexos)` (passando os anexos com `.papel`), preservando resultado para itens sem papel.

**Files (todos os sites — enumerar com grep antes):**
- Modify: `rsc_tae/views/api.py:189,276,352,449,572` (respostas de listar/upload/salvar)
- Modify: `rsc_tae/views/_helpers.py:585,655,867-875` (resumo de preenchimento e agregação de avaliação)
- Modify: `rsc_tae/views/processo.py:1056,1745-1746` (agregação da avaliação/deliberação)
- Test: `rsc_tae/tests/test_papel_reqv.py` (teste de integração de um resumo)

**Interfaces:**
- Consumes: `pontos_item_anexos(item, anexos)`, `taxa_por_papel(item, papel)` (Task 2).

- [ ] **Step 1: Enumerar os sites**

Run: `grep -rn "pontuacao_unidade.*unidades_pontuaveis_anexos\|unidades_pontuaveis_anexos(item" rsc_tae/views/`
Expected: a lista de linhas acima. Cada uma calcula pontos de um item a partir de unidades.

- [ ] **Step 2: Escrever teste de integração (resumo por pontos com papel)**

Acrescentar a `rsc_tae/tests/test_papel_reqv.py` um teste que cria processo + item `aceita_papel` + 2 anexos (titular/substituto) e verifica que `_calcular_resumo_por_pontos`/`verificar_criterios_nivel` contam **1 item** e somam os pontos pelas duas taxas. (Usar as fixtures `suap_data`/`light_data`; criar `Nivel`, `ProcessoRSCTae`, `RolSaberCompetenciaAnexo` com `papel` e `data_inicio/fim`.)

```python
@pytest.mark.django_db(databases='__all__')
def test_resumo_conta_par_como_um_item(suap_data):
    # ... montar nivel, processo, item aceita_papel=True (tit 9 / sub 4,5), 2 anexos
    # anexo titular 13 meses (1 ano) e substituto 13 meses (1 ano)
    # esperado: itens_validados/preenchidos == 1 ; pontos == 1*9 + 1*4.5 == 13.5
    ...
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -k resumo_conta_par -x --no-cov -p no:cacheprovider`
Expected: FAIL (hoje conta 2 itens / pontos errados, ou o site ainda usa taxa única).

- [ ] **Step 4: Substituir em cada site**

Padrão de troca (aplicar em cada linha enumerada). ANTES:

```python
unidades_anexos = [(getattr(a, 'pontuacao', None) or Decimal('0')) for a in anexos]
pontuacao_total_item = (item.pontuacao_unidade or Decimal('0')) * unidades_pontuaveis_anexos(item, unidades_anexos)
```

DEPOIS:

```python
pontuacao_total_item = pontos_item_anexos(item, anexos)
```

Onde o site só tem **unidades validadas do avaliador** (não os anexos), somar por anexo usando `pontos_anexo(item, unidades_validadas_do_anexo, anexo.papel)` — i.e. iterar os anexos com sua unidade validada e o `papel` do próprio anexo. Ex.: `rsc_tae/views/processo.py:1056`:

ANTES:
```python
return pontuacao_unidade * unidades_pontuaveis_anexos(item, unidades_validadas)
```
DEPOIS (iterando os anexos com papel):
```python
from rsc_tae.models.anexo import pontos_anexo
return sum((pontos_anexo(item, u, papel) for (u, papel) in unidades_e_papeis_validados), Decimal('0'))
```
(ajustar a montagem de `unidades_e_papeis_validados` para carregar `(unidade_validada, anexo.papel)` por anexo; o `papel` vem do anexo avaliado.)

Atualizar imports: onde importava `unidades_pontuaveis_anexos`, importar também/usar `pontos_item_anexos`/`pontos_anexo`.

- [ ] **Step 5: Rodar o teste de integração e a suíte do resumo**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Ruff + guarda de complexidade**

Run: `uv run ruff format rsc_tae/views/api.py rsc_tae/views/_helpers.py rsc_tae/views/processo.py && uv run ruff check --select C901 rsc_tae/views/api.py rsc_tae/views/_helpers.py rsc_tae/views/processo.py`
Expected: sem C901 novo nas funções tocadas.

- [ ] **Step 7: Commit**

```bash
git add rsc_tae/views/api.py rsc_tae/views/_helpers.py rsc_tae/views/processo.py rsc_tae/tests/test_papel_reqv.py
git commit -m "[rsc_tae] Agregação de pontos por papel em todos os sites de cálculo"
```

---

### Task 4: Capturar `papel` no upload/salvar de anexo + API

**Files:**
- Modify: `rsc_tae/views/api.py` (`upload_anexo_item` ≈219; endpoint de salvar dados do anexo — `salvar_pontuacao_anexo`/`salvar_descricao_anexo`)
- Test: `rsc_tae/tests/test_papel_reqv.py`

**Interfaces:**
- Consumes: `RolSaberCompetencia.aceita_papel`, `PAPEL_CHOICES`.
- Produces: anexo persistido com `papel` quando `item.aceita_papel`; retorno JSON inclui `papel`.

- [ ] **Step 1: Teste — upload de item aceita_papel grava papel e recusa papel inválido**

```python
# POST upload com papel='substituto' -> anexo.papel == 'substituto'
# POST upload com papel ausente em item aceita_papel -> 400 (ou salva None e conclusão bloqueia — ver Task 6)
# POST upload com papel='xpto' -> 400 'Papel inválido.'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -k upload -x --no-cov -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Capturar `papel` em `upload_anexo_item`** (bloco `if item.item_temporal:`)

```python
    papel = (request.POST.get('papel') or '').strip() or None
    if item.aceita_papel and papel not in (item.PAPEL_TITULAR, item.PAPEL_SUBSTITUTO):
        return JsonResponse({'ok': False, 'msg': 'Selecione o papel (titular ou substituto) deste documento.'}, status=400)
    if not item.aceita_papel:
        papel = None
```
e passar `papel=papel` ao construir o `RolSaberCompetenciaAnexo`. Incluir `papel` no dict de retorno JSON dos endpoints que serializam anexo (ver `listar_anexos_item`: adicionar `item_data['papel'] = a.papel` quando `item.aceita_papel`).

- [ ] **Step 4: Endpoint para alterar o papel de um anexo já enviado**

Se existir endpoint de edição inline do anexo (ex.: `salvar_descricao_anexo`), adicionar aceitação de `papel` (mesma validação). Caso contrário, criar `salvar_papel_anexo(request, processo_id, anexo_id)` análogo a `salvar_descricao_anexo`, registrando a URL em `urls.py` e exportando em `views/__init__.py`.

- [ ] **Step 5: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -k upload -x --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add rsc_tae/views/api.py rsc_tae/urls.py rsc_tae/views/__init__.py rsc_tae/tests/test_papel_reqv.py
git commit -m "[rsc_tae] Captura e validação do papel no upload/edição de anexo"
```

---

### Task 5: UI — seletor de papel no card do comprovante

**Files:**
- Modify: `rsc_tae/templates/rsc_tae/visualizar.html` (≈299, dentro de `{% if linha.item.item_temporal %}`)
- Modify: `rsc_tae/static/rsc_tae/js/rsc-tae.js` (enviar `papel` no upload e no salvar; mostrar/ocultar o seletor)
- Modify: `rsc_tae/static/rsc_tae/css/rsc-tae.css` (classe `rsc-anexo-papel`, sem cores)

**Interfaces:**
- Consumes: `linha.item.aceita_papel`, `anexo.papel`, endpoints da Task 4.

- [ ] **Step 1: Adicionar o seletor no card** (editável), logo antes do bloco "Período":

```django
{% if linha.item.aceita_papel %}
    <div class="rsc-anexo-campo">
        <span>Papel <abbr title="Obrigatório" class="rsc-obrigatorio">*</abbr></span>
        <div class="rsc-anexo-papel" role="radiogroup" aria-label="Papel do documento">
            <label><input type="radio" name="papel-{{ anexo.id }}" value="titular" class="js-anexo-papel" data-anexo-id="{{ anexo.id }}" data-item-id="{{ linha.item.id }}" {% if anexo.papel == 'titular' %}checked{% endif %}> Titular</label>
            <label><input type="radio" name="papel-{{ anexo.id }}" value="substituto" class="js-anexo-papel" data-anexo-id="{{ anexo.id }}" data-item-id="{{ linha.item.id }}" {% if anexo.papel == 'substituto' %}checked{% endif %}> Substituto</label>
        </div>
    </div>
{% endif %}
```

E no bloco read-only (`{% else %}` do `pode_editar_preenchimento`), exibir `{% if linha.item.aceita_papel %}<div class="text-muted"><strong>Papel:</strong> {{ anexo.get_papel_display|default:'—' }}</div>{% endif %}`.

- [ ] **Step 2: JS — enviar `papel` e recalcular ao mudar**

Em `rsc-tae.js`: no handler de upload, ler o papel selecionado do formulário do item e incluir no `FormData`. Adicionar listener em `.js-anexo-papel` (change) que faz POST para o endpoint de salvar papel (Task 4) e dispara o recálculo do resumo (mesma função já usada pelas datas). Marcar o campo como inválido (classe existente `rsc-campo-invalido`) quando nenhum papel estiver marcado.

- [ ] **Step 3: CSS — layout do radiogroup (sem cores)**

```css
.rsc-anexo-papel { display: flex; gap: 1rem; align-items: center; }
```

- [ ] **Step 4: Verificar renderização (djlint) e um smoke via test client**

Run: `uv run djlint rsc_tae/templates/rsc_tae/visualizar.html --profile=django`
Expected: 0 erros. Smoke: GET `visualizar` de um processo com item aceita_papel mostra o radiogroup.

- [ ] **Step 5: Commit**

```bash
git add rsc_tae/templates/rsc_tae/visualizar.html rsc_tae/static/rsc_tae/js/rsc-tae.js rsc_tae/static/rsc_tae/css/rsc-tae.css
git commit -m "[rsc_tae] Seletor de papel (titular/substituto) no card do comprovante"
```

---

### Task 6: Exigir `papel` na conclusão do preenchimento

**Files:**
- Modify: `rsc_tae/views/processo.py` (`concluir_preenchimento` e/ou o validador que hoje exige Descrição)
- Test: `rsc_tae/tests/test_papel_reqv.py`

**Interfaces:**
- Consumes: `RolSaberCompetenciaAnexo.papel`, `item.aceita_papel`.

- [ ] **Step 1: Teste — concluir com anexo de item aceita_papel sem papel é bloqueado**

```python
# processo AGUARDANDO_PREENCHIMENTO, item aceita_papel, 1 anexo com papel=None
# concluir_preenchimento -> não transiciona; mensagem 'Informe o papel ...'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -k conclui -x --no-cov -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Adicionar a validação** onde já se valida a Descrição obrigatória

```python
    faltando_papel = RolSaberCompetenciaAnexo.objects.filter(
        processo=processo, rol_saber_competencia__aceita_papel=True, papel__isnull=True,
    ).exists()
    if faltando_papel:
        return httprr(processo.get_absolute_url(), 'Informe o papel (titular ou substituto) em todos os documentos dos itens do Requisito V.', tag='error')
```

- [ ] **Step 4: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_papel_reqv.py -k conclui -x --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rsc_tae/views/processo.py rsc_tae/tests/test_papel_reqv.py
git commit -m "[rsc_tae] Exigir papel dos comprovantes do Requisito V na conclusão"
```

---

### Task 7: Management command de migração de dados (dry-run + commit)

**Files:**
- Create: `rsc_tae/management/commands/migrar_papel_requisito_v.py`
- Test: `rsc_tae/tests/test_migrar_papel_reqv.py`

**Interfaces:**
- Consumes: model fields das Tasks 1-2.
- Produces: command `migrar_papel_requisito_v [--commit]` que, para cada par (titular/substituto do Req V):
  1. no item titular: `aceita_papel=True`, `pontuacao_unidade_substituto = grupo(substituto).pontuacao_unidade`, `titulo` sem "— titular";
  2. repontar `RolSaberCompetenciaAnexo` do substituto → titular com `papel='substituto'`;
  3. `papel='titular'` nos anexos do titular;
  4. repontar `RolSaberCompetenciaPreenchimento` do substituto → titular (somando `quantidade` se colidir no unique);
  5. `ativo=False` no item substituto.
  Idempotente; casa por título; **simulação por padrão**, grava só com `--commit`.

- [ ] **Step 1: Teste — dry-run não grava; commit funde e preserva pontos**

Criar `rsc_tae/tests/test_migrar_papel_reqv.py`: montar 1 par (titular 9,0 / substituto 4,5), 1 anexo em cada (13 meses), rodar sem `--commit` (nada muda) e com `--commit` (2 anexos passam ao item titular; substituto fica `papel='substituto'`; item substituto `ativo=False`; `pontos_item_anexos` = 9 + 4,5 = 13,5, igual à soma anterior 9 + 4,5).

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_migrar_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: FAIL (command inexistente).

- [ ] **Step 3: Implementar o command**

Estrutura (com helpers pequenos para C901 ≤ 10): parsear pares por título (`re` no sufixo "— titular"/"— substituto") dentro do Requisito `numero=5`; para cada par, executar os 5 passos dentro de `transaction.atomic()`; em modo simulação, `raise _Rollback` ao final (padrão do `reverter_deliberacao_final`). Emitir relatório por par (qtd anexos repontados, colisões de preenchimento resolvidas). Tratar `unique_together` de `Preenchimento` somando quantidades. Nunca usar `.update(situacao=)` (não aplicável aqui).

- [ ] **Step 4: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest rsc_tae/tests/test_migrar_papel_reqv.py -x --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Dry-run contra a réplica de produção**

Run: `DJANGO_SETTINGS_MODULE=suap.settings uv run python manage.py migrar_papel_requisito_v`
Expected: relatório mostrando ≈729 anexos → substituto, ≈823 → titular, 4 pares, sem gravar.

- [ ] **Step 6: Commit**

```bash
git add rsc_tae/management/commands/migrar_papel_requisito_v.py rsc_tae/tests/test_migrar_papel_reqv.py
git commit -m "[rsc_tae] Command de migração do Requisito V (funde 8->4 itens, papel)"
```

---

### Task 8: Atualizar fixtures para a estrutura de 4 itens

**Files:**
- Modify: `rsc_tae/fixtures/initial_data_saber_competencia.json` (remover os 4 substitutos; nos 4 titulares: `aceita_papel=true`, `pontuacao_unidade_substituto`, título sem sufixo)
- Modify: `rsc_tae/fixtures/initial_data_grupo.json` se algum grupo ficar órfão

**Interfaces:** nenhuma (dados de referência).

- [ ] **Step 1: Ajustar o JSON** dos 4 itens titulares (pks 33, 35, 37, 39): `fields.aceita_papel: true`, `fields.pontuacao_unidade_substituto` = 4.5/3/1.5/1, `fields.titulo` sem "— titular"; remover os objetos pks 34, 36, 38, 40.

- [ ] **Step 2: Validar carga em banco limpo**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run python -c "import django; django.setup()"` e um teste que faz `loaddata` das fixtures do Req V e confere 4 itens com `aceita_papel`.

- [ ] **Step 3: Commit**

```bash
git add rsc_tae/fixtures/initial_data_saber_competencia.json rsc_tae/fixtures/initial_data_grupo.json
git commit -m "[rsc_tae] Fixtures do Requisito V com 4 itens (papel/duas taxas)"
```

---

### Task 9: Admin — expor papel e taxa substituto (auditoria)

**Files:**
- Modify: `rsc_tae/admin/rol_saber_competencia.py` (list/fieldset: `aceita_papel`, `pontuacao_unidade_substituto`)
- Modify: `rsc_tae/admin/anexo.py` (list/filter: `papel`)

**Interfaces:** nenhuma.

- [ ] **Step 1: Adicionar campos** aos `list_display`/`list_filter`/`fields` correspondentes.

- [ ] **Step 2: Smoke via test client (changelist 200)**

Run: teste `client.get('/admin/rsc_tae/rolsabercompetencia/')` como superuser → 200.

- [ ] **Step 3: Commit**

```bash
git add rsc_tae/admin/rol_saber_competencia.py rsc_tae/admin/anexo.py
git commit -m "[rsc_tae] Admin expõe papel e taxa de substituto do Requisito V"
```

---

## Ordem de deploy (produção)

1. Deploy do código (Tasks 1-6, 8, 9) + `migrate rsc_tae` (migration 0007).
2. `migrar_papel_requisito_v` (dry-run) → conferir relatório.
3. `migrar_papel_requisito_v --commit` → funde os dados.
4. Reiniciar app. Conferir um processo em andamento (item do Req V mostra 1 linha com seletor de papel) e um deferido (pontos e ≥ mínimo preservados).

## Notas de impacto (medido na réplica)

- 179 processos com o par duplicado; 175 em andamento (recontam certo), 4 deferidos — **nenhum cai abaixo do mínimo** (deferimentos preservados). Pontuação inalterada em 100%.
- ≈1.552 anexos no Req V (729 substituto → repontados; 823 titular). 1 preenchimento (>0). Snapshots `AvaliacaoProcessoRSCTae.itens_validados` ficam como registro histórico.
