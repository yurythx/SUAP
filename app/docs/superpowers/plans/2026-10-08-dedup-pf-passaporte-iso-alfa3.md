# Dedup PF — chave do passaporte com ISO 3166-1 alfa-3: plano de implementação

> **Atualização de 09/10/2026:** o formato da chave mudou para `ARG-AB123456` e a tabela foi para o command `preencher_iso_paises` (spec, seções 6.1 e 6.2). Este plano registra a execução de 08/10.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O `documento_identificador` de quem não tem CPF passa a ser `<passaporte>/<ISO 3166-1 alfa-3>` (ex.: `AB123456/ARG`), e não mais `<passaporte>/<código SIAPE>`.

**Architecture:**
- **Campo novo.** `comum.Pais.iso_alfa3`, preenchido por uma tabela curada código SIAPE → alfa-3 (`comum/paises_iso.py`).
- **Quem preenche.** Uma migration de dados e os importadores do SIAPE, quando criam um país.
- **Quem usa.** Os pontos que montam a chave do passaporte (`chave_passaporte`) passam a receber o alfa-3. País sem alfa-3 não forma documento.

**Tech Stack:** Django 5.2, PostgreSQL 18, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`, seção 6.1.

**Onde:** branch do MR 2 (`claude/dedup-pf-mr2-comando`, Release 1 = 3.21.0). O MR 3 recebe por merge.

## Global Constraints

- **Formato da chave:** `<passaporte formatado>/<ISO3>`, com o ISO3 em 3 letras maiúsculas. Exemplo: `AB123456/ARG`.
- **Campo:** `comum.Pais.iso_alfa3`, `CharField(max_length=3, blank=True, default='')`, **sem** unicidade. O SIAPE tem a Suíça duas vezes (150 e 236); as duas viram `CHE`.
- **País sem alfa-3 não forma documento.**
  - **PF legada:** recebe sintético na higiene.
  - **PF nova sem CPF:** é recusada com a mensagem exata `País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.`
- **Preenchimento sem sobrescrever:** a migration e o importador só preenchem `iso_alfa3` **vazio**. Nunca sobrescrevem uma correção manual feita no admin.
- **Países extintos** (ALEMANHA ORIENTAL, URSS, IUGOSLÁVIA, TCHECOSLOVÁQUIA etc.) ficam fora da tabela, sem alfa-3.
- **Fora do escopo:** a UNIQUE `(pais_origem, passaporte)` do MR 3 e o `filtro_par_passaporte` (por FK de país) não mudam.
- **Regras do projeto:**
  - TDD;
  - pt-BR;
  - ruff 150, aspas simples;
  - C901 ≤ 10;
  - tipos nas defs tocadas;
  - nunca `--no-verify`.
- **Testes:** `DATABASE_PORT=5437 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_iso uv run pytest --create-db …`. Depois da primeira rodada, use `--reuse-db`. Nunca a porta 5432.

---

### Task 1: `comum.Pais.iso_alfa3`, tabela curada, migration, admin e importadores

**Files:**
- Create: `comum/paises_iso.py`
- Modify: `comum/models.py` (`class Pais`, ≈1828)
- Create: `comum/migrations/0121_pais_iso_alfa3.py` (confira a numeração: a última é a `0120_apiexterna_bearer_token_label`)
- Modify: `comum/admin.py` (`PaisAdmin`, ≈266)
- Modify: `rh/importador.py` (`importar_pais`, ≈255)
- Confira também: o motor `rh/importacao_siape` (a tabela `'pais'` está em `layouts.py:102`). Descubra que função grava o país e aplique a mesma regra.
- Test: `comum/tests/models/test_pais_iso.py`

**Interfaces:**
- Produces:
  - `comum.paises_iso.ISO_ALFA3_POR_CODIGO_SIAPE: dict[str, str]`;
  - `comum.paises_iso.preencher_iso(paises: Iterable[Pais]) -> list[Pais]`, que devolve os alterados;
  - o campo `Pais.iso_alfa3`.

- [ ] **Step 1: Curar a tabela.**
  - **Fonte:** os 282 países de `comum.Pais` do `suap_dev`, porta 5432, **só leitura**: `SELECT codigo, nome, excluido FROM pais ORDER BY codigo`.
  - **Para cada código:** escolha o alfa-3 ISO 3166-1. `edu_pais` (`sigla` = alfa-3, `nome` em pt-BR) ajuda a conferir. Os nomes do SIAPE vêm abreviados, por exemplo `REPUBL. DEMOCR. DO AFEGANISTAO` = `AFG`.
  - **Fora da tabela:** país extinto, ou território sem alfa-3 próprio.
  - **No relatório, liste:**
    - os códigos deixados de fora, com o motivo;
    - os códigos SIAPE diferentes que caíram no mesmo alfa-3, como a Suíça.
  - **Os 34 países usados hoje por estrangeiros** (Colômbia, Equador, Argentina, Chile, Uruguai, Espanha, Portugal, Itália, Alemanha, México, Tailândia, Venezuela, França, China…) **têm de estar** na tabela.

```python
"""ISO 3166-1 alfa-3 de cada país da tabela do SIAPE (``comum.Pais.codigo``). Os códigos do SIAPE são iguais em todas as instituições.

País extinto ou território sem alfa-3 próprio fica de fora: sem alfa-3, o passaporte não forma documento (spec da deduplicação, 6.1).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comum.models import Pais

ISO_ALFA3_POR_CODIGO_SIAPE: dict[str, str] = {
    '001': 'AFG',  # REPUBL. DEMOCR. DO AFEGANISTAO
    '002': 'ZAF',  # REPUBL. DA AFRICA DO SUL
    # … um por linha, com o nome do SIAPE no comentário …
    '011': 'ARG',  # ARGENTINA
    '024': 'BRA',  # BRASIL
}


def preencher_iso(paises: Iterable[Pais]) -> list[Pais]:
    """Preenche ``iso_alfa3`` vazio pela tabela; nunca sobrescreve (correção manual no admin vale). Devolve os alterados."""
    alterados = []
    for pais in paises:
        iso = ISO_ALFA3_POR_CODIGO_SIAPE.get(pais.codigo)
        if iso and not pais.iso_alfa3:
            pais.iso_alfa3 = iso
            alterados.append(pais)
    return alterados
```

- [ ] **Step 2: Testes que falham.** Arquivo `comum/tests/models/test_pais_iso.py`:

```python
import re

import pytest

from comum.models import Pais
from comum.paises_iso import ISO_ALFA3_POR_CODIGO_SIAPE, preencher_iso

USADOS_POR_ESTRANGEIROS = {'011': 'ARG', '024': 'BRA', '036': 'CHL', '040': 'COL', '053': 'ECU', '054': 'ESP', '129': 'PRT', '163': 'URY'}


def test_tabela_so_tem_alfa3_valido() -> None:
    assert all(re.fullmatch(r'[A-Z]{3}', iso) for iso in ISO_ALFA3_POR_CODIGO_SIAPE.values())


def test_paises_dos_estrangeiros_estao_na_tabela() -> None:
    assert {codigo: ISO_ALFA3_POR_CODIGO_SIAPE.get(codigo) for codigo in USADOS_POR_ESTRANGEIROS} == USADOS_POR_ESTRANGEIROS


@pytest.mark.django_db
def test_preenche_vazio_e_nao_sobrescreve_correcao() -> None:
    vazio = Pais.objects.create(codigo='011', nome='ARGENTINA')
    corrigido = Pais.objects.create(codigo='024', nome='BRASIL', iso_alfa3='XYZ')
    extinto = Pais.objects.create(codigo='999', nome='PAIS EXTINTO')

    assert preencher_iso([vazio, corrigido, extinto]) == [vazio]
    assert (vazio.iso_alfa3, corrigido.iso_alfa3, extinto.iso_alfa3) == ('ARG', 'XYZ', '')
```

Confira os códigos de `USADOS_POR_ESTRANGEIROS` contra o `suap_dev` (`SELECT codigo, nome FROM pais WHERE codigo IN (…)`) antes de rodar.

Run: `… uv run pytest -q comum/tests/models/test_pais_iso.py --create-db`
Expected: FAIL (`ModuleNotFoundError: comum.paises_iso`, depois `FieldError: iso_alfa3`).

- [ ] **Step 3: Campo, migration e admin.**
  - **Model.** Em `class Pais` (`comum/models.py`):

    ```python
        iso_alfa3 = models.CharField('ISO 3166-1 alfa-3', max_length=3, blank=True, default='')
    ```

  - **Migration.** `makemigrations comum -n pais_iso_alfa3`. Depois acrescente o `RunPython`, que importa a tabela, porque o dado é constante:

    ```python
    def preencher(apps, schema_editor):
        from comum.paises_iso import preencher_iso

        Pais = apps.get_model('comum', 'Pais')
        Pais.objects.bulk_update(preencher_iso(Pais.objects.all()), ['iso_alfa3'])
    ```

    ```python
        operations = [
            migrations.AddField(...),  # gerado
            migrations.RunPython(preencher, migrations.RunPython.noop),
        ]
    ```

  - **Admin.** No `PaisAdmin`, acrescente `'iso_alfa3'` a `list_display`, `list_editable` e `search_fields`.

- [ ] **Step 4: Importadores.** Em `rh/importador.py` `importar_pais`, troque o `update_or_create` por:

```python
            pais, criado = Pais.objects.update_or_create(codigo=codigo, defaults=kwargs)
            if criado:
                Pais.objects.bulk_update(preencher_iso([pais]), ['iso_alfa3'])
```

(`from comum.paises_iso import preencher_iso` no topo.) O país que já existe não muda: o admin cuida dele.

Faça o mesmo no motor `rh/importacao_siape`, onde o país é criado.

Teste: num teste de importação existente do SIAPE (procure por `importar_pais` ou pela tabela `pais` nos testes de `rh`), um país novo com código `011` sai com `iso_alfa3='ARG'`. Se não houver teste de importação de país, crie um mínimo que chame `importar_pais` com um item.

- [ ] **Step 5: Verde.** Rode os testes novos, `comum/tests` e os testes do importador do SIAPE. Também rode `makemigrations --check`.

- [ ] **Step 6: Commit.** `git commit -m "[comum] País com ISO 3166-1 alfa-3 (tabela do SIAPE curada)"`

### Task 2: chave do passaporte com o alfa-3

**Files:**
- Modify: `rh/deduplicacao/entrada.py`: `codigo_pais` (≈81), `_filtro_par` (≈98-101), `obter_ou_criar` (≈299) e a recusa de documento inválido.
- Modify: `rh/deduplicacao/plano.py`: `codigos` (≈66), `Pessoa.codigo_pais` (≈44), `_inferir_pais` (≈141).
- Modify: `rh/deduplicacao/aplicacao.py`: `codigos` (≈101, ≈189).
- Modify: `rh/models/pessoa/pessoa_fisica.py`: `_normalizar_documentos` (≈352).
- Modify: `rh/deduplicacao/documentos.py`: `chave_passaporte` (só a docstring e o nome do parâmetro).
- Modify: os testes que criam `Pais(codigo=…)` e conferem a chave `…/011`. Encontre com `grep -rn "/011\|codigo='0" --include=*.py */tests`. Cada um ganha `iso_alfa3`, e a chave esperada passa a ser `…/ARG`.
- Modify: `docs/operacoes/deduplicar-pessoas.md` (formato do documento nas ações `pais_preenchido`/`separada`).

**Interfaces:**
- Consumes: `Pais.iso_alfa3` (Task 1).
- Produces:
  - `rh.deduplicacao.entrada.iso_pais(dados: Mapping[str, Any]) -> str | None`, que substitui `codigo_pais`;
  - `chave_passaporte(passaporte, iso_alfa3)`.

- [ ] **Step 1: Testes que falham** (em `rh/tests/models/test_pessoa_fisica_documento.py` e `rh/tests/tasks/test_deduplicar_pessoas.py`):

```python
@pytest.mark.django_db
def test_save_sem_cpf_usa_passaporte_com_iso_do_pais() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')

    pessoa = PessoaFisicaFactory(cpf=None, passaporte='ab 123456', pais_origem=argentina)

    assert pessoa.documento_identificador == 'AB123456/ARG'


@pytest.mark.django_db
def test_pessoa_nova_com_pais_sem_iso_e_recusada() -> None:
    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')

    with pytest.raises(ValidationError, match='País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.'):
        PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=sem_iso)


def test_mesmo_passaporte_nos_dois_codigos_da_suica_agrupa() -> None:
    suica_150 = Pais.objects.create(codigo='150', nome='SUICA', iso_alfa3='CHE')
    suica_236 = Pais.objects.create(codigo='236', nome='SUICA', iso_alfa3='CHE')
    a = _legada(cpf=None, passaporte='X1234567', pais_origem=suica_150)
    b = _legada(cpf=None, passaporte='X1234567', pais_origem=suica_236)

    planejar()

    assert D.objects.filter(acao=D.MESCLADA, pf_id__in=[a.pk, b.pk]).count() == 1
```

Adapte ao helper `_legada` e à fixture `sem_unicidade_pessoa`, que o arquivo já usa. Na PF legada com país sem alfa-3, o `planejar` emite `sintetico` (`SEMDOC-`) e não usa o passaporte como chave.

Run: `… uv run pytest -q rh/tests/models/test_pessoa_fisica_documento.py rh/tests/tasks/test_deduplicar_pessoas.py -k "iso or suica" --reuse-db`
Expected: FAIL (`AB123456/011` ≠ `AB123456/ARG`; não levanta; não agrupa).

- [ ] **Step 2: Implementação.**
  - **`iso_pais`** substitui `codigo_pais` em `entrada.py`. Ele lê `pais_origem.iso_alfa3`, ou `Pais.objects.filter(pk=…).values_list('iso_alfa3', flat=True)`, e devolve `None` para `''`.
  - **`_filtro_par`:** `pais_origem__iso_alfa3=iso` no lugar de `pais_origem__codigo=codigo`. É o que junta os dois códigos da Suíça.
  - **`plano.py` e `aplicacao.py`:** `codigos = dict(Pais.objects.values_list('pk', 'iso_alfa3'))`. Renomeie as variáveis para `isos` e `Pessoa.iso_pais` se o diff ficar pequeno; se não, deixe o nome e ajuste o comentário.
  - **`pessoa_fisica.py`:** `chave_passaporte(self.passaporte, self.pais_origem.iso_alfa3 if self.pais_origem_id else None)`.
  - **Recusa da PF nova:** onde hoje a PF nova sem CPF e com passaporte + país recebe a chave, se o país não tiver alfa-3 levante `ValidationError('País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.')`. Isso vale no `save()` de PF nova (`_normalizar_documentos`, ramo `self.pk is None`) e no `obter_ou_criar`/`verificar_documento`: para uma PF nova sem CPF, passaporte válido + país sem alfa-3 dá a mesma mensagem.
  - **`chave_passaporte`:** o parâmetro passa a se chamar `iso_alfa3`, e a docstring dá o exemplo `AB123456/ARG`.

- [ ] **Step 3: Testes existentes.** Rode `rh/tests`, `edu/tests`, `comum/tests`, `pesquisa/tests`, `projetos/tests` e `projetos_ensino/tests` com `-n 3 -m "not e2e and not doc"`.
  - Conserte cada `Pais.objects.create(codigo=…)` cujo teste dependa da chave: acrescente `iso_alfa3`, e a chave esperada passa a ser `…/<ISO3>`.
  - Não mude teste que não dependa da chave.

- [ ] **Step 4: Runbook.** Em `docs/operacoes/deduplicar-pessoas.md`, troque toda menção a `AB123456/011` e a "código do país" na chave por `AB123456/ARG` e "ISO 3166-1 alfa-3 (`comum.Pais.iso_alfa3`)". Acrescente em "Problemas comuns" uma linha:

  | Sintoma | Causa e solução |
  |---|---|
  | `País sem código ISO 3166-1 alfa-3` | Preencha o campo ISO 3166-1 alfa-3 do país no admin de Países. Estrangeiros desse país, sem CPF, já gravados com sintético ganham a chave no próximo `planejar`/`aplicar`. |

- [ ] **Step 5: Commit.** `git commit -m "[rh] Chave do passaporte com ISO 3166-1 alfa-3 do país"`
