# Dedup PF — MR 2: comando `deduplicar_pessoas` e entrada única — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o comando `manage.py deduplicar_pessoas planejar|relatorio|aplicar`, que cada instituição roda para deixar 1 pessoa civil = 1 `PessoaFisica`, e fechar a entrada para que não nasçam duplicatas novas (todo ponto de criação passa por `PessoaFisica.objects.obter_ou_criar`).

**Architecture:** Pacote `rh/deduplicacao/` com módulos de responsabilidade única:
- `documentos` (regras puras de CPF/passaporte/sintético);
- `entrada` (`obter_ou_criar` + políticas);
- `campos` (resolução de conflito de campo);
- `referencias` (descoberta via ORM + trava de catálogo);
- `plano` (fase `planejar`);
- `aplicacao` (fase `aplicar`);
- `relatorio` (CSV).

O plano e a auditoria ficam em `rh.DeduplicacaoPessoa`. O `aplicar` é set-based: um `UPDATE … FROM dedup_mapa` por referência e por lote. Antes de apagar as perdedoras, passa por uma trava do `Collector`. Os pontos de criação/atualização de PF passam a usar `obter_ou_criar`/`aplicar_politica`, e o código que supunha 1 PF = 1 aluno é corrigido.

**Tech Stack:** Django 5.2, PostgreSQL 18, pytest + factory_boy, `pycpfcnpj` (já instalado).

**Spec:** `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`, seções 1, 2, 3 e 5.

**Pré-requisito:** MR 1 (`docs/superpowers/plans/2026-10-07-dedup-pf-mr1-remover-fantasmas.md`) mergeado. Sem ele, a trava de catálogo do `planejar` aborta listando as fantasmas.

## Global Constraints

- **Multi-instituição:** nenhuma regra calibrada nos dados do IFRN. A descoberta de referências é feita em tempo de execução, sobre os apps instalados.
- **CPF válido:** 11 dígitos, não repetidos, DV correto. Grava-se com máscara `000.000.000-00`.
- **Passaporte:** sem espaços, maiúsculo. Inválido se tiver menos de 5 caracteres ou for um caractere repetido.
- **Passaporte vale junto com o país (decisão do usuário, 07/10/2026).** A chave e o `documento_identificador` de quem não tem CPF é `PASSAPORTE/<comum.Pais.codigo>` (ex.: `AB123456/011`). Passaporte sem `pais_origem` não é documento: a PF recebe sintético e o número fica guardado. Grupos e unicidade de passaporte são por **(país, passaporte)**.
- **Sem CPF ⇒ `pais_origem` obrigatório**, exceto quem tem documento sintético. Vira CHECK no MR 3.
  - A higiene infere o país só para quem não tem CPF válido: aluno brasileiro vira Brasil; aluno estrangeiro tem o `edu.Pais` convertido para `comum.Pais` **pelo nome** (sem acento, maiúsculo).
  - **Nunca pelo `codigo`:** os dois models usam esquemas de código diferentes, e todas as 62 coincidências de código em prod apontam para países trocados.
- **Sintéticos:** `SEMDOC-<id>`, `CONFLITO-<id>-<documento original>`, `INVALIDO-<id>-<dígitos>`. `documento_identificador` passa a `max_length=80`.
- **PF nova** exige CPF, ou passaporte **e** país de origem.
- **Sobrevivente:** servidor ativo > aluno ativo > prestador ativo > maior `id`. Definido uma única vez, em `PessoaFisicaManager.com_prioridade()` + `chave_prioridade()`.
- **Suspeita:** nascimento divergente, ambos preenchidos, faz a PF ser separada, nunca mesclada.
- **Políticas:**
  - `AUTORITATIVA`: SIAPE de servidor; sobrescreve, nunca com vazio; divergência só é registrada.
  - `CAUTELOSA`: matrícula com data de nascimento; divergência → `DocumentoDeOutraPessoa`.
  - `PREENCHER`: gov.br, financeiro, dependente SIAPE, minicurso e PROITEC (estes dois confirmados pelo usuário em 07/10/2026: sem data de nascimento não há como checar a identidade).

  Nenhuma política grava valor vazio.
- **`save()` só formata.** Anular CPF com DV inválido é decisão auditada da higiene, nunca do `save()`. PF **nova** sem CPF e sem passaporte levanta `ValidationError`.
- **GFK:** reaponta só as declaradas no ORM (`GenericForeignKey`); log/histórico sem GFK declarada fica com o id antigo.
- **`Vinculo.secret`:** não é tocado; já guarda o `pessoa_id` original desde a criação do vínculo (`comum/models.py:762`).
- **Complexidade:** ciclomática ≤ 10 por função tocada (hook `check_complexity`). Anote tipos nas defs tocadas.
- **Idioma e estilo:** código, comentários e commits em pt-BR. Ruff com linha 150 e aspas simples.
- **Testes:**
  - factories, nunca `suap_data`;
  - comportamento observável;
  - categorias `models/` (sem banco), `fluxos/` e `tasks/`;
  - rodar com `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest …`. Use um `TEST_DATABASE_NAME` próprio, para não recriar o `test_suap` compartilhado.
- **Testes de duplicata sobrevivem à Release 2:** use a fixture `sem_unicidade_pessoa` (Task 2), que remove as constraints dentro da transação do teste.

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `rh/deduplicacao/__init__.py` | pacote (vazio) |
| `rh/deduplicacao/documentos.py` | normalização e validade de CPF/passaporte; chave país+passaporte; documento sintético |
| `rh/deduplicacao/paises.py` | `comum.Pais` pelo nome (sem acento, maiúsculo) |
| `rh/deduplicacao/entrada.py` | `Politica`, `DocumentoDeOutraPessoa`, `aplicar_politica`, `verificar_documento`, `obter_ou_criar` |
| `rh/deduplicacao/campos.py` | campos mescláveis e `resolver_campos` (puro) |
| `rh/deduplicacao/referencias.py` | `Referencia`, `ReferenciaGenerica`, `referencias()`, `referencias_genericas()`, `fks_desconhecidas()` |
| `rh/deduplicacao/plano.py` | `planejar()` |
| `rh/deduplicacao/aplicacao.py` | `aplicar()` |
| `rh/deduplicacao/relatorio.py` | `resumo()`, `exportar_csv()` |
| `rh/management/commands/deduplicar_pessoas.py` | o comando |
| `rh/models/pessoa/deduplicacao.py` | model `DeduplicacaoPessoa` |
| `rh/managers.py` | `PessoaFisicaManager` (`com_prioridade`, `obter_ou_criar`) |
| `rh/models/pessoa/pessoa_fisica.py` | `save()` formata; campos `passaporte`/`documento_identificador`; sai `clonar()` |
| `docs/operacoes/deduplicar-pessoas.md` | runbook para as instituições |

---

### Task 1: Regras de documento (puras)

**Files:**
- Create: `rh/deduplicacao/__init__.py` (vazio)
- Create: `rh/deduplicacao/documentos.py`
- Test: `rh/tests/models/test_documentos_pessoa.py`

**Interfaces:**
- Produces:
  - `digitos(valor: str | None) -> str`
  - `formatar_cpf(valor: str | None) -> str | None`
  - `cpf_valido(valor: str | None) -> bool`
  - `formatar_passaporte(valor: str | None) -> str | None`
  - `passaporte_valido(valor: str | None) -> bool`
  - `eh_sintetico(documento: str | None) -> bool`
  - `documento_sintetico(pf_id: int, conflito: str | None = None, cpf_invalido: str | None = None) -> str`
  - `chave_passaporte(passaporte: str | None, codigo_pais: str | None) -> str | None`
  - `normalizar_nome_pais(nome: str | None) -> str`
  - `rh.deduplicacao.paises.pais_por_nome(nome: str | None) -> comum.models.Pais | None`
  - `rh.deduplicacao.paises.ids_por_nome() -> dict[str, int]`

- [ ] **Step 1: Escrever os testes**

```python
import pytest

from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    documento_sintetico,
    eh_sintetico,
    formatar_cpf,
    formatar_passaporte,
    normalizar_nome_pais,
    passaporte_valido,
)


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('52998224725', '529.982.247-25'),
        ('529.982.247-25', '529.982.247-25'),
        ('529 982 247 25', '529.982.247-25'),
        ('___.___.___-__', None),
        ('-', None),
        ('', None),
        (None, None),
        (' 1234 ', '1234'),
    ],
)
def test_formatar_cpf_so_formata(entrada: str | None, esperado: str | None) -> None:
    assert formatar_cpf(entrada) == esperado


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('529.982.247-25', True),
        ('52998224725', True),
        ('529.982.247-24', False),
        ('111.111.111-11', False),
        ('000.000.000-00', False),
        ('1234', False),
        (None, False),
    ],
)
def test_cpf_valido(entrada: str | None, esperado: bool) -> None:
    assert cpf_valido(entrada) is esperado


@pytest.mark.parametrize(('entrada', 'esperado'), [(' ab 123456 ', 'AB123456'), ('', None), ('   ', None), (None, None)])
def test_formatar_passaporte(entrada: str | None, esperado: str | None) -> None:
    assert formatar_passaporte(entrada) == esperado


@pytest.mark.parametrize(('entrada', 'esperado'), [('AB123456', True), ('ab 123456', True), ('X', False), ('AAAAAA', False), ('1234', False), (None, False)])
def test_passaporte_valido(entrada: str | None, esperado: bool) -> None:
    assert passaporte_valido(entrada) is esperado


def test_documento_sintetico_guarda_o_documento_original() -> None:
    assert documento_sintetico(7) == 'SEMDOC-7'
    assert documento_sintetico(7, conflito='529.982.247-25') == 'CONFLITO-7-529.982.247-25'
    assert documento_sintetico(7, cpf_invalido='529.982.247-24') == 'INVALIDO-7-52998224724'
    assert documento_sintetico(7, cpf_invalido='___.___.___-__') == 'SEMDOC-7'


def test_chave_passaporte_exige_pais() -> None:
    assert chave_passaporte(' ab 123456 ', '011') == 'AB123456/011'
    assert chave_passaporte('AB123456', None) is None
    assert chave_passaporte(None, '011') is None


def test_normalizar_nome_pais() -> None:
    assert normalizar_nome_pais(' Itália ') == 'ITALIA'
    assert normalizar_nome_pais(None) == ''


def test_eh_sintetico() -> None:
    assert eh_sintetico('CONFLITO-1-529.982.247-25')
    assert eh_sintetico('SEMDOC-1')
    assert eh_sintetico('INVALIDO-1-123')
    assert not eh_sintetico('529.982.247-25')
    assert not eh_sintetico(None)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -q rh/tests/models/test_documentos_pessoa.py --create-db`
Expected: FAIL, `ModuleNotFoundError: No module named 'rh.deduplicacao'`.

- [ ] **Step 3: Implementar**

`rh/deduplicacao/__init__.py`: arquivo vazio.

`rh/deduplicacao/documentos.py`:

```python
"""Regras de documento de pessoa física: formatação, validade e documento sintético.

Fonte única usada pela higiene do comando ``deduplicar_pessoas`` e pela entrada de dados
(``PessoaFisica.save`` e ``PessoaFisica.objects.obter_ou_criar``).
"""

from __future__ import annotations

import re

from pycpfcnpj import cpfcnpj

PREFIXOS_SINTETICOS = ('SEMDOC-', 'CONFLITO-', 'INVALIDO-')
TAMANHO_MINIMO_PASSAPORTE = 5


def digitos(valor: str | None) -> str:
    return re.sub(r'\D', '', valor or '')


def formatar_cpf(valor: str | None) -> str | None:
    """Máscara ``000.000.000-00`` quando há 11 dígitos; ``None`` quando não há dígito nenhum.

    Só formata: um CPF com DV errado continua como está (anulá-lo é decisão auditada da higiene).
    """
    numeros = digitos(valor)
    if not numeros:
        return None
    if len(numeros) == 11:
        return f'{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}'
    return (valor or '').strip()


def cpf_valido(valor: str | None) -> bool:
    numeros = digitos(valor)
    return len(numeros) == 11 and len(set(numeros)) > 1 and cpfcnpj.validate(numeros)


def formatar_passaporte(valor: str | None) -> str | None:
    return re.sub(r'\s', '', valor or '').upper() or None


def passaporte_valido(valor: str | None) -> bool:
    passaporte = formatar_passaporte(valor)
    return bool(passaporte) and len(passaporte) >= TAMANHO_MINIMO_PASSAPORTE and len(set(passaporte)) > 1


def eh_sintetico(documento: str | None) -> bool:
    return (documento or '').startswith(PREFIXOS_SINTETICOS)


def documento_sintetico(pf_id: int, conflito: str | None = None, cpf_invalido: str | None = None) -> str:
    if conflito:
        return f'CONFLITO-{pf_id}-{conflito}'
    if digitos(cpf_invalido):
        return f'INVALIDO-{pf_id}-{digitos(cpf_invalido)}'
    return f'SEMDOC-{pf_id}'


def chave_passaporte(passaporte: str | None, codigo_pais: str | None) -> str | None:
    """Passaporte só identifica junto com o país emissor: ``AB123456/011``. Sem país, não é documento."""
    passaporte = formatar_passaporte(passaporte)
    return f'{passaporte}/{codigo_pais}' if passaporte and codigo_pais else None


def normalizar_nome_pais(nome: str | None) -> str:
    sem_acento = unicodedata.normalize('NFKD', nome or '').encode('ascii', 'ignore').decode()
    return sem_acento.upper().strip()
```

(acrescente `import unicodedata` ao topo do módulo).

`rh/deduplicacao/paises.py`:

```python
"""País de origem de pessoa física (comum.Pais) pelo nome.

edu.Pais e comum.Pais usam esquemas de código diferentes: nunca converter pelo código.
"""

from __future__ import annotations

from rh.deduplicacao.documentos import normalizar_nome_pais


def ids_por_nome() -> dict[str, int]:
    from comum.models import Pais

    return {normalizar_nome_pais(nome): pk for pk, nome in Pais.objects.values_list('pk', 'nome')}


def pais_por_nome(nome: str | None):
    from comum.models import Pais

    pk = ids_por_nome().get(normalizar_nome_pais(nome)) if nome else None
    return Pais.objects.get(pk=pk) if pk else None
```

Teste em `rh/tests/models/test_documentos_pessoa.py` (com banco):

```python
@pytest.mark.django_db
def test_pais_por_nome_ignora_acento_e_caixa() -> None:
    from comum.models import Pais
    from rh.deduplicacao.paises import pais_por_nome

    italia = Pais.objects.create(codigo='386', nome='ITALIA')

    assert pais_por_nome('Itália') == italia
    assert pais_por_nome('Atlântida') is None
```

- [ ] **Step 4: Rodar e ver passar**

Run: o comando do Step 2, com `--reuse-db`. Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add rh/deduplicacao/__init__.py rh/deduplicacao/documentos.py rh/deduplicacao/paises.py rh/tests/models/test_documentos_pessoa.py
git commit -m "[rh] Regras de documento de pessoa física para a deduplicação"
```

### Task 2: Model `DeduplicacaoPessoa`, campos de documento e fixture de duplicatas

**Files:**
- Create: `rh/models/pessoa/deduplicacao.py`
- Modify: `rh/models/pessoa/__init__.py` (exportar)
- Modify: `rh/models/pessoa/pessoa_fisica.py:142-144` (campos)
- Create: migration `rh/migrations/0108_deduplicacaopessoa.py` (gerada)
- Modify: `conftest.py` da raiz (fixture `sem_unicidade_pessoa`, usada por vários apps)

**Interfaces:**
- Produces:
  - `rh.models.DeduplicacaoPessoa` com as constantes de ação `CPF_ANULADO`, `PASSAPORTE_ANULADO`, `PASSAPORTE_PREENCHIDO`, `PAIS_PREENCHIDO` (o `documento` guarda o id do `comum.Pais`), `SINTETICO`, `MESCLADA`, `SEPARADA`, `CAMPO_DESCARTADO`, `DIVERGENCIA_ENTRADA` e `ERRO`, e com os campos `pf_id`, `sobrevivente_id`, `documento`, `acao`, `campo`, `valor_original`, `motivo`, `criado_em` e `aplicado_em`.
  - Fixture `sem_unicidade_pessoa`.

- [ ] **Step 1: Criar o model**

`rh/models/pessoa/deduplicacao.py`:

```python
from djtools.db import models


class DeduplicacaoPessoa(models.ModelPlus):
    """Plano, auditoria e mapa de id antigo → novo da deduplicação de PessoaFisica.

    Escrito pelo comando ``deduplicar_pessoas`` (fase ``planejar``) e pela entrada de dados
    (``divergencia_entrada``). ``pf_id``/``sobrevivente_id`` não são FK: a PF perdedora é apagada.
    """

    CPF_ANULADO = 'cpf_anulado'
    PASSAPORTE_ANULADO = 'passaporte_anulado'
    PASSAPORTE_PREENCHIDO = 'passaporte_preenchido'
    PAIS_PREENCHIDO = 'pais_preenchido'
    SINTETICO = 'sintetico'
    MESCLADA = 'mesclada'
    SEPARADA = 'separada'
    CAMPO_DESCARTADO = 'campo_descartado'
    DIVERGENCIA_ENTRADA = 'divergencia_entrada'
    ERRO = 'erro'
    ACAO_CHOICES = [
        [CPF_ANULADO, 'CPF anulado'],
        [PASSAPORTE_ANULADO, 'Passaporte anulado'],
        [PASSAPORTE_PREENCHIDO, 'Passaporte copiado do aluno'],
        [PAIS_PREENCHIDO, 'País de origem inferido do aluno'],
        [SINTETICO, 'Documento sintético'],
        [MESCLADA, 'Mesclada'],
        [SEPARADA, 'Separada'],
        [CAMPO_DESCARTADO, 'Campo descartado'],
        [DIVERGENCIA_ENTRADA, 'Divergência na entrada'],
        [ERRO, 'Erro'],
    ]

    pf_id = models.IntegerField(db_index=True)
    sobrevivente_id = models.IntegerField(null=True, db_index=True)
    documento = models.CharField(max_length=80, blank=True)
    acao = models.CharField(max_length=30, choices=ACAO_CHOICES, db_index=True)
    campo = models.CharField(max_length=100, blank=True)
    valor_original = models.TextField(blank=True)
    motivo = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(null=True, db_index=True)

    class Meta:
        verbose_name = 'Deduplicação de Pessoa'
        verbose_name_plural = 'Deduplicações de Pessoas'

    def __str__(self) -> str:
        return f'{self.acao} PF {self.pf_id}'
```

Em `rh/models/pessoa/__init__.py`, acrescentar `from .deduplicacao import *` (em ordem alfabética, depois de `.abstract`).

- [ ] **Step 2: Alterar os campos de documento da PessoaFisica**

Em `rh/models/pessoa/pessoa_fisica.py`, trocar:

```python
    passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', blank=True, default='')
    # TODO verificar documento identificador
    documento_identificador = models.CharFieldPlus(max_length=50, null=True, blank=False, db_index=True)
```

por:

```python
    passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', null=True, blank=True)
    # CPF, senão passaporte, senão sintético (SEMDOC-/CONFLITO-/INVALIDO-): ver rh/deduplicacao/documentos.py
    documento_identificador = models.CharFieldPlus(max_length=80, null=True, blank=False, db_index=True)
```

- [ ] **Step 3: Gerar a migration**

Run: `DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py makemigrations rh -n deduplicacaopessoa`
Expected: `rh/migrations/0108_deduplicacaopessoa.py` com `CreateModel(name='DeduplicacaoPessoa', …)`, `AlterField(model_name='pessoafisica', name='passaporte', …)` e `AlterField(model_name='pessoafisica', name='documento_identificador', …)`. Nada de outros apps; se aparecer, é pendência alheia, a investigar.

- [ ] **Step 4: Fixture de duplicatas**

Acrescentar no `conftest.py` da raiz (junto das outras fixtures; `pytest` já é importado lá):

```python
@pytest.fixture
def sem_unicidade_pessoa(db: None) -> None:
    """Remove, dentro da transação do teste, a unicidade e a obrigatoriedade de documento da PessoaFisica
    e a unicidade da PessoaInfoComplementar.

    Monta duplicatas como as da base legada; vale antes e depois da Release 2 (a DDL é desfeita no
    rollback do teste).
    """
    from django.db import connection

    from rh.models import PessoaFisica, PessoaInfoComplementar

    with connection.cursor() as cursor:
        for tabela in (PessoaFisica._meta.db_table, PessoaInfoComplementar._meta.db_table):
            cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'u'", [tabela])
            for (nome,) in cursor.fetchall():
                cursor.execute(f'ALTER TABLE {tabela} DROP CONSTRAINT {connection.ops.quote_name(nome)}')
        cursor.execute(f'ALTER TABLE {PessoaFisica._meta.db_table} ALTER COLUMN documento_identificador DROP NOT NULL')
```

- [ ] **Step 5: Smoke**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -q rh/tests/models --create-db`
Expected: verde, igual ao master (o schema é criado a partir dos models).

- [ ] **Step 6: Commit**

```bash
git add rh/models/pessoa/deduplicacao.py rh/models/pessoa/__init__.py rh/models/pessoa/pessoa_fisica.py rh/migrations/0108_deduplicacaopessoa.py conftest.py
git commit -m "[rh] Model de auditoria da deduplicação e passaporte nulo"
```

### Task 3: `PessoaFisica.save()` formata e exige documento; sai o `clonar()`

**Files:**
- Modify: `rh/models/pessoa/pessoa_fisica.py` (`save()`, `clonar()`, `aluno_set.first()` em `:386/401/410/418`)
- Modify: `rh/models/pessoa/pessoa.py:259-260` (`pessoaendereco`)
- Delete: `rh/management/commands/duplicar_pessoas_por_vinculo.py`, `rh/tests/tasks/test_duplicar_pessoas_por_vinculo.py`
- Modify: `rh/tests/models/test_importador_ws.py` (remover `PessoaFisicaCloneTestCase`)
- Test: `rh/tests/models/test_pessoa_fisica_documento.py`

**Interfaces:**
- Consumes: `formatar_cpf`, `formatar_passaporte`, `eh_sintetico` (Task 1).
- Produces: `PessoaFisica.save()` normaliza CPF e passaporte e recalcula `documento_identificador`; PF nova sem documento levanta `ValidationError`; `Pessoa.pessoaendereco` devolve o endereço mais recente.

- [ ] **Step 1: Escrever os testes**

`rh/tests/models/test_pessoa_fisica_documento.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from comum.models import PessoaEndereco
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db


def test_save_formata_cpf_e_usa_como_documento() -> None:
    pessoa = PessoaFisicaFactory(cpf='52998224725')

    pessoa.refresh_from_db()
    assert pessoa.cpf == '529.982.247-25'
    assert pessoa.documento_identificador == '529.982.247-25'


def test_save_sem_cpf_usa_passaporte_com_pais() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte=' ab 123456 ', pais_origem=argentina)

    pessoa.refresh_from_db()
    assert pessoa.passaporte == 'AB123456'
    assert pessoa.documento_identificador == 'AB123456/011'


def test_passaporte_sem_pais_nao_e_documento() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica(nome='Estrangeira', passaporte='AB123456').save()


def test_save_nao_anula_cpf_com_dv_errado() -> None:
    pessoa = PessoaFisicaFactory(cpf='529.982.247-24')

    pessoa.refresh_from_db()
    assert pessoa.cpf == '529.982.247-24'


def test_pessoa_nova_sem_documento_e_recusada() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica(nome='Sem Documento').save()


def test_pessoa_legada_sem_documento_continua_salvavel(sem_unicidade_pessoa: None) -> None:
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, passaporte=None, documento_identificador='SEMDOC-1')

    pessoa = PessoaFisica.objects.get(pk=pessoa.pk)
    pessoa.nome_mae = 'Maria'
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == 'SEMDOC-1'


def test_corrigir_documento_troca_o_sintetico(sem_unicidade_pessoa: None) -> None:
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, documento_identificador='CONFLITO-1-529.982.247-25')

    pessoa = PessoaFisica.objects.get(pk=pessoa.pk)
    pessoa.cpf = '390.533.447-05'
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == '390.533.447-05'


def test_endereco_e_o_mais_recente() -> None:
    pessoa = PessoaFisicaFactory()
    PessoaEndereco.objects.create(pessoa=pessoa, logradouro='Rua Antiga')
    PessoaEndereco.objects.create(pessoa=pessoa, logradouro='Rua Nova')

    assert pessoa.pessoaendereco.logradouro == 'Rua Nova'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -q rh/tests/models/test_pessoa_fisica_documento.py --reuse-db`
Expected: falham `test_save_formata_cpf…`, `test_save_sem_cpf…`, `test_pessoa_nova_sem_documento…`, `test_corrigir_documento…` e `test_endereco…`.

- [ ] **Step 3: Implementar o `save()`**

Em `rh/models/pessoa/pessoa_fisica.py`, no `save()`, trocar o bloco:

```python
        if self.cpf:
            self.documento_identificador = self.cpf
        else:
            self.cpf = None
            if aluno_com_passaporte:
                self.documento_identificador = aluno_com_passaporte.passaporte
            else:
                self.documento_identificador = self.passaporte
```

por:

```python
        self._normalizar_documentos()
```

Apague também a variável `aluno_com_passaporte` do início do `save()`: a inicialização (`aluno_com_passaporte = None`) e a linha `aluno_com_passaporte = self.aluno_set.exclude(passaporte='').last()`. O `save()` não copia mais o passaporte do aluno. Se copiasse, cada `save()` desfaria o `passaporte_anulado` da higiene e reintroduziria passaportes repetidos depois da Release 2. O legado é coberto pela ação `passaporte_preenchido` do `planejar`; o aluno estrangeiro novo traz o passaporte nos `dados` do `obter_ou_criar`.

Acrescente o método logo abaixo do `save()`:

```python
    def _normalizar_documentos(self) -> None:
        """Formata CPF/passaporte e recalcula ``documento_identificador`` (CPF, senão passaporte/país, senão sintético).

        Só formata: anular documento inválido é decisão auditada do comando ``deduplicar_pessoas``.
        """
        from rh.deduplicacao.documentos import chave_passaporte, eh_sintetico, formatar_cpf, formatar_passaporte

        self.cpf = formatar_cpf(self.cpf)
        self.passaporte = formatar_passaporte(self.passaporte)
        chave = self.cpf or chave_passaporte(self.passaporte, self.pais_origem.codigo if self.pais_origem_id else None)
        if chave:
            self.documento_identificador = chave
        elif self.pk is None:
            raise ValidationError('Informe o CPF, ou o passaporte e o país de origem da pessoa.')
        elif not eh_sintetico(self.documento_identificador):
            # ponytail: legado sem documento fica sem identificador até o deduplicar_pessoas gerar o sintético
            self.documento_identificador = None
```

- [ ] **Step 4: Remover o `clonar()` e o comando que duplica pessoas**

- Apagar o método `clonar()` inteiro de `rh/models/pessoa/pessoa_fisica.py`.
- Apagar o comando: `git rm rh/management/commands/duplicar_pessoas_por_vinculo.py rh/tests/tasks/test_duplicar_pessoas_por_vinculo.py`.
- Em `rh/tests/models/test_importador_ws.py`, apagar a classe `PessoaFisicaCloneTestCase` inteira. O `ImportadorWsDependentesTestCase` é reescrito na Task 5.

- [ ] **Step 5: Endereço e aluno mais recentes**

Em `rh/models/pessoa/pessoa.py`:

```python
    @property
    def pessoaendereco(self):
        return self.pessoaendereco_set.order_by('-pk').first()
```

Em `rh/models/pessoa/pessoa_fisica.py`, trocar as 4 ocorrências de `aluno = self.aluno_set.first()` por `aluno = self.aluno_set.order_by('-pk').first()`. Depois do merge, a PF tem vários alunos, e a foto/dados do aluno passam a vir do mais recente.

- [ ] **Step 6: Helpers de teste que criavam PF sem documento**

O spike (suíte inteira com este `save()`) quebrou 10 testes porque os helpers criam PF sem CPF:

- `rh/tests/models/test_emails_disponiveis.py`: em `_criar_servidor`, passar `cpf=cpf_valido(int(matricula) + 100_000_000)` à pessoa "Descartada" e `cpf=cpf_valido(int(matricula))` à do servidor. Em `_criar_aluno`, passar `cpf=cpf_valido(int(matricula))`. Os intervalos não se cruzam: as matrículas de servidor começam em 7000001, e as de aluno dão 154510001+ depois do `% 10**9`. Import: `from rh.tests.factories import cpf_valido`.
- `boletim_servico/tests/conftest.py`: nos `baker.make(Servidor, ...)` das linhas ≈90 e ≈102, acrescentar `pessoa_fisica__cpf=cpf_valido(<n>)` com um `n` fixo e diferente em cada um (ex.: `900001`, `900002`).

- [ ] **Step 7: Rodar os testes**

Run: o comando do Step 2, mais `rh/tests/models/test_importador_ws.py rh/tests/models/test_emails_disponiveis.py boletim_servico`.
Expected: verde, exceto `test_deve_clonar_pessoa_fisica_existente_ao_criar_prestador_dependente`, que é reescrito na Task 5.

- [ ] **Step 8: Commit**

```bash
git add -A rh/models/pessoa rh/tests/models rh/management/commands rh/tests/tasks boletim_servico/tests/conftest.py
git commit -m "[rh] PessoaFisica.save formata documentos e exige documento; remove clonagem de pessoa"
```

### Task 4: `obter_ou_criar`, políticas e prioridade

**Files:**
- Modify: `rh/managers.py` (novo `PessoaFisicaManager`)
- Modify: `rh/models/pessoa/pessoa_fisica.py:206` (`objects = PessoaFisicaManager()`)
- Create: `rh/deduplicacao/entrada.py`
- Test: `rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py`

**Interfaces:**
- Consumes: Task 1 e `DeduplicacaoPessoa` (Task 2).
- Produces:
  - `rh.deduplicacao.entrada.Politica` (StrEnum `AUTORITATIVA`/`CAUTELOSA`/`PREENCHER`);
  - `DocumentoDeOutraPessoa(ValidationError)`;
  - `aplicar_politica(pf: PessoaFisica, dados: Mapping[str, Any], politica: Politica) -> None` (não salva);
  - `verificar_documento(*, cpf: str | None = None, passaporte: str | None = None, pais=None, nascimento_data: date | str | None = None) -> None` (`pais` é `comum.Pais`);
  - `obter_ou_criar(dados: Mapping[str, Any], politica: Politica) -> tuple[PessoaFisica, bool]` (o país vem em `dados['pais_origem']`, uma instância de `comum.Pais`, ou em `dados['pais_origem_id']`);
  - `chave_prioridade(pf) -> tuple[bool, bool, bool, int]`;
  - `PessoaFisica.objects.com_prioridade()` (anota `servidor_ativo`, `aluno_ativo`, `prestador_ativo`);
  - `PessoaFisica.objects.obter_ou_criar(dados, politica)`.

- [ ] **Step 1: Escrever os testes**

`rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py`:

```python
from datetime import date

import pytest
from django.core.exceptions import ValidationError

from rh.deduplicacao.entrada import DocumentoDeOutraPessoa, Politica, verificar_documento
from rh.models import DeduplicacaoPessoa, PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def test_cria_quando_documento_nao_existe() -> None:
    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': '52998224725', 'nome': 'Ana Souza'}, Politica.CAUTELOSA)

    assert criada
    assert pessoa.documento_identificador == CPF


def test_exige_documento() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica.objects.obter_ou_criar({'nome': 'Sem Documento'}, Politica.CAUTELOSA)


def test_reusa_pessoa_com_cpf_em_outro_formato() -> None:
    existente = PessoaFisicaFactory(cpf=CPF)

    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': '52998224725', 'nome': 'Ana Souza'}, Politica.CAUTELOSA)

    assert not criada
    assert pessoa.pk == existente.pk


def test_cautelosa_recusa_nascimento_divergente() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))

    with pytest.raises(DocumentoDeOutraPessoa):
        PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, Politica.CAUTELOSA)


def test_cautelosa_sobrescreve_sem_apagar() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria', nome_pai='José')

    pessoa, _ = PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nome_mae': 'Maria Silva', 'nome_pai': ''}, Politica.CAUTELOSA)

    pessoa.refresh_from_db()
    assert pessoa.pk == existente.pk
    assert pessoa.nome_mae == 'Maria Silva'
    assert pessoa.nome_pai == 'José'


def test_autoritativa_sobrescreve_e_registra_divergencia() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))

    PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, Politica.AUTORITATIVA)

    existente.refresh_from_db()
    assert existente.nascimento_data == date(1991, 1, 1)
    assert DeduplicacaoPessoa.objects.filter(pf_id=existente.pk, acao=DeduplicacaoPessoa.DIVERGENCIA_ENTRADA, aplicado_em__isnull=False).exists()


def test_preencher_so_completa_vazios() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria', nome_pai=None)

    PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nome_mae': 'Outra', 'nome_pai': 'José'}, Politica.PREENCHER)

    existente.refresh_from_db()
    assert existente.nome_mae == 'Maria'
    assert existente.nome_pai == 'José'


def test_com_duplicata_legada_usa_a_de_maior_prioridade(sem_unicidade_pessoa: None) -> None:
    PessoaFisicaFactory(cpf=CPF)
    mais_nova = PessoaFisicaFactory(cpf=CPF)

    pessoa, _ = PessoaFisica.objects.obter_ou_criar({'cpf': CPF}, Politica.PREENCHER)

    assert pessoa.pk == mais_nova.pk


def test_passaporte_vale_com_pais() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    chile = Pais.objects.create(codigo='158', nome='CHILE')
    existente = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)

    mesma, criada_mesma = PessoaFisica.objects.obter_ou_criar({'passaporte': 'ab123456', 'pais_origem': argentina}, Politica.PREENCHER)
    outra, criada_outra = PessoaFisica.objects.obter_ou_criar({'passaporte': 'AB123456', 'pais_origem': chile, 'nome': 'Outra'}, Politica.PREENCHER)

    assert (mesma.pk, criada_mesma) == (existente.pk, False)
    assert criada_outra and outra.documento_identificador == 'AB123456/158'
    with pytest.raises(ValidationError):
        PessoaFisica.objects.obter_ou_criar({'passaporte': 'ZZ999999', 'nome': 'Sem País'}, Politica.PREENCHER)


def test_verificar_documento_nao_escreve_e_recusa_divergencia() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    total = PessoaFisica.objects.count()

    with pytest.raises(DocumentoDeOutraPessoa):
        verificar_documento(cpf=CPF, nascimento_data='1991-01-01')
    verificar_documento(cpf=CPF, nascimento_data=date(1990, 1, 1))
    verificar_documento(cpf='390.533.447-05', nascimento_data=date(1991, 1, 1))

    assert PessoaFisica.objects.count() == total
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -q rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py --reuse-db`
Expected: FAIL, `ModuleNotFoundError: rh.deduplicacao.entrada`.

- [ ] **Step 3: Manager**

Em `rh/managers.py`, acrescentar:

```python
from model_utils.managers import InheritanceManager


class PessoaFisicaManager(InheritanceManager):
    def com_prioridade(self):
        """Anota a prioridade de sobrevivência (servidor ativo > aluno ativo > prestador ativo > maior id)."""
        from django.conf import settings
        from django.db.models import BooleanField, Exists, OuterRef, Value

        from comum.models import PrestadorServico
        from rh.models import Servidor

        qs = self.get_queryset().annotate(
            servidor_ativo=Exists(Servidor.objects.filter(pessoa_fisica=OuterRef('pk'), ativo=True)),
            prestador_ativo=Exists(PrestadorServico.objects.filter(pessoa_fisica=OuterRef('pk'), ativo=True)),
        )
        if 'edu' not in settings.INSTALLED_APPS:
            return qs.annotate(aluno_ativo=Value(False, output_field=BooleanField()))
        from edu.models import Aluno

        return qs.annotate(aluno_ativo=Exists(Aluno.objects.filter(pessoa_fisica=OuterRef('pk'), situacao__ativo=True)))

    def obter_ou_criar(self, dados, politica):
        from rh.deduplicacao.entrada import obter_ou_criar

        return obter_ou_criar(dados, politica)
```

Em `rh/models/pessoa/pessoa_fisica.py`, trocar `objects = InheritanceManager()` por `objects = PessoaFisicaManager()` (importar de `rh.managers`). Se o import de `InheritanceManager` ficar sem uso, remova-o.

- [ ] **Step 4: `rh/deduplicacao/entrada.py`**

```python
"""Entrada de dados de pessoa física: obter ou criar pela identidade civil (CPF/passaporte).

Único caminho para criar PessoaFisica: spec 2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 3.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from rh.deduplicacao.documentos import chave_passaporte, digitos, formatar_cpf, formatar_passaporte

if TYPE_CHECKING:
    from rh.models import PessoaFisica

MENSAGEM_OUTRA_PESSOA = 'CPF/passaporte já cadastrado para outra pessoa (data de nascimento diferente). Procure a secretaria acadêmica ou o RH.'


class Politica(StrEnum):
    AUTORITATIVA = 'autoritativa'
    CAUTELOSA = 'cautelosa'
    PREENCHER = 'preencher'


class DocumentoDeOutraPessoa(ValidationError):
    """O documento informado já pertence a uma pessoa com outra data de nascimento."""


def chave_prioridade(pf: Any) -> tuple[bool, bool, bool, int]:
    """Ordem de sobrevivência; exige um objeto vindo de ``PessoaFisica.objects.com_prioridade()``."""
    return (pf.servidor_ativo, pf.aluno_ativo, pf.prestador_ativo, pf.pk)


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ''


def _como_data(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return date.fromisoformat(valor[:10]) if valor else None
    return valor


def nascimento_diverge(atual: Any, informado: Any) -> bool:
    atual, informado = _como_data(atual), _como_data(informado)
    return atual is not None and informado is not None and atual != informado


def codigo_pais(dados: Mapping[str, Any]) -> str | None:
    if dados.get('pais_origem') is not None:
        return dados['pais_origem'].codigo
    if dados.get('pais_origem_id'):
        from comum.models import Pais

        return Pais.objects.filter(pk=dados['pais_origem_id']).values_list('codigo', flat=True).first()
    return None


def buscar_existente(cpf: str | None, passaporte: str | None, codigo: str | None = None) -> PessoaFisica | None:
    """A PF dona do documento (CPF, ou passaporte + país); com duplicata legada, a de maior prioridade."""
    from rh.models import PessoaFisica

    filtro = Q()
    if cpf:
        filtro |= Q(cpf__in={cpf, digitos(cpf)}) | Q(documento_identificador=cpf)
    chave = chave_passaporte(passaporte, codigo)
    if chave:
        filtro |= Q(documento_identificador=chave) | Q(passaporte__iexact=formatar_passaporte(passaporte), pais_origem__codigo=codigo)
    if not filtro:
        return None
    return max(PessoaFisica.objects.com_prioridade().filter(filtro), key=chave_prioridade, default=None)


def _registrar_divergencia(pf: PessoaFisica, informado: Any) -> None:
    from rh.models import DeduplicacaoPessoa

    DeduplicacaoPessoa.objects.create(
        pf_id=pf.pk,
        documento=pf.documento_identificador or '',
        acao=DeduplicacaoPessoa.DIVERGENCIA_ENTRADA,
        campo='nascimento_data',
        valor_original=str(pf.nascimento_data),
        motivo=f'Fonte autoritativa informou {_como_data(informado)}',
        aplicado_em=timezone.now(),
    )


def aplicar_politica(pf: PessoaFisica, dados: Mapping[str, Any], politica: Politica) -> None:
    """Aplica ``dados`` em ``pf`` (sem salvar) conforme a política. Nunca grava valor vazio."""
    informado = dados.get('nascimento_data')
    if nascimento_diverge(pf.nascimento_data, informado):
        if politica == Politica.CAUTELOSA:
            raise DocumentoDeOutraPessoa(MENSAGEM_OUTRA_PESSOA)
        if politica == Politica.AUTORITATIVA:
            _registrar_divergencia(pf, informado)
    for campo, valor in dados.items():
        if _vazio(valor) or (politica == Politica.PREENCHER and not _vazio(getattr(pf, campo, None))):
            continue
        setattr(pf, campo, valor)


def verificar_documento(*, cpf: str | None = None, passaporte: str | None = None, pais: Any = None, nascimento_data: Any = None) -> None:
    """Sem escrita, para o ``clean()`` de formulário: recusa documento de pessoa com outro nascimento."""
    pf = buscar_existente(formatar_cpf(cpf), formatar_passaporte(passaporte), pais.codigo if pais else None)
    if pf is not None and nascimento_diverge(pf.nascimento_data, nascimento_data):
        raise DocumentoDeOutraPessoa(MENSAGEM_OUTRA_PESSOA)


def obter_ou_criar(dados: Mapping[str, Any], politica: Politica) -> tuple[PessoaFisica, bool]:
    """Obtém a PF dona do CPF/passaporte de ``dados`` (aplicando a política) ou a cria."""
    from rh.models import PessoaFisica

    dados = {**dados, 'cpf': formatar_cpf(dados.get('cpf')), 'passaporte': formatar_passaporte(dados.get('passaporte'))}
    codigo = codigo_pais(dados)
    chave = dados['cpf'] or chave_passaporte(dados['passaporte'], codigo)
    if not chave:
        raise ValidationError('Informe o CPF, ou o passaporte e o país de origem da pessoa.')
    with transaction.atomic():
        with connection.cursor() as cursor:
            # ponytail: lock por documento evita duas matrículas simultâneas criarem a mesma pessoa antes da UNIQUE (Release 2)
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', [chave])
        pf = buscar_existente(dados['cpf'], dados['passaporte'], codigo)
        criada = pf is None
        if criada:
            # setattr simples: um default não vazio do model (False, 0) não pode barrar o valor informado
            pf = PessoaFisica()
            for campo, valor in dados.items():
                if not _vazio(valor):
                    setattr(pf, campo, valor)
        else:
            aplicar_politica(pf, dados, politica)
        pf.save()
    return pf, criada
```

- [ ] **Step 5: Rodar e ver passar**

Run: o comando do Step 2. Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add rh/managers.py rh/models/pessoa/pessoa_fisica.py rh/deduplicacao/entrada.py rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py
git commit -m "[rh] PessoaFisica.objects.obter_ou_criar com políticas por fonte"
```

### Task 5: Pontos de criação/atualização em `rh`, `comum`, `djtools` e `financeiro`

**Files:**
- Modify: `rh/models/carreira/servidor.py:236-246` (`Servidor.update_or_create`)
- Modify: `rh/importador_ws.py:1919-1932` (dependentes)
- Modify: `comum/models.py:2058-2059` (`PrestadorServico.update_or_create`)
- Modify: `rh/models/pessoa/pessoa_externa.py:175-205` (`PessoaExterna.save`)
- Modify: `djtools/middleware/govbr.py:253` (`create_user`)
- Modify: `financeiro/importador.py:441-450` (`importar_credores`)
- Modify: `rh/forms.py:722-726` (`PessoaFisicaForm.clean_cpf`)
- Test: `rh/tests/models/test_importador_ws.py` (reescrever `ImportadorWsDependentesTestCase`)
- Test: `rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py` (acrescentar casos)

**Interfaces:**
- Consumes: `Politica`, `aplicar_politica`, `PessoaFisica.objects.obter_ou_criar` (Task 4).

- [ ] **Step 1: Reescrever o teste de dependentes (falha hoje)**

Em `rh/tests/models/test_importador_ws.py`, trocar o corpo de `ImportadorWsDependentesTestCase` por:

```python
class ImportadorWsDependentesTestCase(RHBase):
    def test_dependente_reusa_a_pessoa_fisica_existente(self):
        importador = ImportadorWs.__new__(ImportadorWs)
        pessoa_fisica_original = self.servidor_a.pessoa_fisica
        total_inicial = PessoaFisica.objects.count()
        matricula_dependente = ''.join(filter(str.isdigit, pessoa_fisica_original.cpf))
        PrestadorServico.objects.filter(matricula=matricula_dependente).delete()

        importador._importar_dependentes(
            self.servidor_a,
            [{'cpf': pessoa_fisica_original.cpf, 'nome': 'Outro Nome', 'codCondicao': '001', 'arrayBeneficios': {}}],
        )

        prestador = PrestadorServico.objects.get(matricula=matricula_dependente)
        assert Dependente.objects.get(usuario_externo=prestador).servidor == self.servidor_a
        assert prestador.pessoa_fisica_id == pessoa_fisica_original.pk
        assert PessoaFisica.objects.count() == total_inicial
        pessoa_fisica_original.refresh_from_db()
        assert pessoa_fisica_original.nome != 'Outro Nome'  # PREENCHER não sobrescreve
```

Acrescentar em `rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py`:

```python
def test_pessoa_externa_nova_reusa_pf_e_nao_sobrescreve() -> None:
    from rh.models import PessoaExterna

    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria')

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Antiga')
    externa.save()
    externa.nome_mae = 'Outra'
    externa.save()

    existente.refresh_from_db()
    assert externa.pessoa_fisica_id == existente.pk
    assert existente.nome_mae == 'Maria'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `… uv run pytest -q rh/tests/models/test_importador_ws.py rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py --reuse-db`
Expected: os 2 testes novos falham. O dependente cria uma PF nova (ou quebra porque `clonar` não existe), e a externa sobrescreve `nome_mae`.

- [ ] **Step 3: `Servidor.update_or_create` (AUTORITATIVA nos dois ramos)**

Em `rh/models/carreira/servidor.py`, importar no topo do módulo `from rh.deduplicacao.entrada import Politica, aplicar_politica`, ou dentro do método, se houver ciclo de import. Trocar:

```python
        if not servidor:
            pessoa_fisica = PessoaFisica.objects.create(**pessoa_fisica_dict)
            pessoa_fisica_created = True
            dados['pessoa_fisica'] = pessoa_fisica
            servidor = Servidor.objects.create(**dados)
            servidor_created = True
        else:
            pessoa_fisica, pessoa_fisica_created = PessoaFisica.objects.update_or_create(pk=servidor.pessoa_fisica.pk, defaults=pessoa_fisica_dict)
            dados['pessoa_fisica'] = pessoa_fisica
            servidor, servidor_created = Servidor.objects.update_or_create(pk=servidor.pk, defaults=dados)
```

por:

```python
        if not servidor:
            pessoa_fisica, pessoa_fisica_created = PessoaFisica.objects.obter_ou_criar(pessoa_fisica_dict, Politica.AUTORITATIVA)
            dados['pessoa_fisica'] = pessoa_fisica
            servidor = Servidor.objects.create(**dados)
            servidor_created = True
        else:
            # SIAPE é a fonte mais confiável: sobrescreve tudo, exceto com valor nulo/vazio
            pessoa_fisica, pessoa_fisica_created = servidor.pessoa_fisica, False
            aplicar_politica(pessoa_fisica, pessoa_fisica_dict, Politica.AUTORITATIVA)
            pessoa_fisica.save()
            dados['pessoa_fisica'] = pessoa_fisica
            servidor, servidor_created = Servidor.objects.update_or_create(pk=servidor.pk, defaults=dados)
```

- [ ] **Step 4: Dependentes do SIAPE (PREENCHER)**

Em `rh/importador_ws.py`, trocar:

```python
            # PrestadorServico.matricula é unique — lookup seguro
            # PessoaFisica.cpf não é unique, então evita get_or_create direto. O ordering padrão do
            # model é por nome, que empata entre cadastros de mesmo CPF e nome: ordena por pk para
            # clonar sempre o cadastro mais antigo, em vez de um registro qualquer.
            prestador = PrestadorServico.objects.filter(matricula=matricula_ps).first()
            if not prestador:
                pessoa_fisica = PessoaFisica.objects.filter(cpf=cpf_masked).order_by('pk').first()
                if pessoa_fisica:
                    pessoa_fisica = pessoa_fisica.clonar()
                else:
                    pessoa_fisica = PessoaFisica(cpf=cpf_masked, nome=nome_normalizado)
                    pessoa_fisica.save()
                prestador = PrestadorServico(matricula=matricula_ps, pessoa_fisica=pessoa_fisica, ativo=True)
                prestador.save()
```

por:

```python
            # PrestadorServico.matricula é unique — lookup seguro. Do dependente o SIAPE só traz nome e CPF:
            # reusa a pessoa existente e só completa o que estiver vazio.
            prestador = PrestadorServico.objects.filter(matricula=matricula_ps).first()
            if not prestador:
                pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': cpf_masked, 'nome': nome_normalizado}, Politica.PREENCHER)
                prestador = PrestadorServico(matricula=matricula_ps, pessoa_fisica=pessoa_fisica, ativo=True)
                prestador.save()
```

(import `from rh.deduplicacao.entrada import Politica`).

- [ ] **Step 5: `PrestadorServico.update_or_create` (CAUTELOSA)**

Em `comum/models.py`, trocar:

```python
        pessoa, pessoa_fisica_created = PessoaFisica.objects.update_or_create(vinculo__user__username=matricula, defaults=pessoa_dict)
        pessoa.save()
```

por:

```python
        pessoa = PessoaFisica.objects.filter(vinculo__user__username=matricula).first()
        if pessoa:
            aplicar_politica(pessoa, pessoa_dict, Politica.CAUTELOSA)
            pessoa.save()
            pessoa_fisica_created = False
        else:
            pessoa, pessoa_fisica_created = PessoaFisica.objects.obter_ou_criar(pessoa_dict, Politica.CAUTELOSA)
```

(import local `from rh.deduplicacao.entrada import Politica, aplicar_politica` dentro do método, porque `comum.models` é importado por `rh`).

- [ ] **Step 6: `PessoaExterna.save()` neutralizada**

Em `rh/models/pessoa/pessoa_externa.py`, trocar o `save()` inteiro por:

```python
    def save(self, *args, **kwargs):
        from comum.models import Vinculo
        from rh.deduplicacao.entrada import Politica

        from .pessoa_fisica import PessoaFisica

        self.matricula = re.sub(r'\D', '', str(self.cpf or '')) or None
        if not self.pessoa_fisica_id:
            # ponytail: as colunas copiadas de PessoaFisica estão mortas (revisão da PessoaExterna em spec próprio);
            # só alimentam a obtenção da pessoa e nunca sobrescrevem uma PF existente.
            self.pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(self._dados_pessoa_fisica(PessoaFisica), Politica.CAUTELOSA)
        super().save(*args, **kwargs)

        defaults = {'pessoa': self.pessoa_fisica.pessoa_ptr, 'ativo': False}
        tipo_relacionamento = ContentType.objects.get_for_model(self)
        vinculo, _ = Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
        self._espelhar_campos_migrados(vinculo)
        return self

    def _dados_pessoa_fisica(self, modelo_pessoa_fisica: type) -> dict:
        campos_pessoa = {campo.attname for campo in modelo_pessoa_fisica._meta.concrete_fields}
        ignorados = {'id', 'pessoa_ptr_id', 'matricula', 'pessoa_fisica_id', 'excluido', *self.CAMPOS_MIGRADOS_VINCULO}
        return {
            campo.attname: getattr(self, campo.attname)
            for campo in self._meta.concrete_fields
            if campo.attname in campos_pessoa and campo.attname not in ignorados
        }
```

- [ ] **Step 7: gov.br (PREENCHER)**

Em `djtools/middleware/govbr.py:253`, trocar:

```python
            pessoa_fisica = PessoaFisica.objects.create(nome=user_data['name'], cpf=cpf)
```

por:

```python
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': cpf, 'nome': user_data['name']}, Politica.PREENCHER)
```

(import `from rh.deduplicacao.entrada import Politica`). O `update_user` continua atualizando `nome_registro` como hoje (decisão do spec).

- [ ] **Step 8: Credores do SIAFI (PREENCHER)**

Em `financeiro/importador.py`, `importar_credores`:
- apagar a linha `cpfs_existentes = set(PessoaFisica.objects.order_by('cpf').values_list('cpf', flat=True))`;
- trocar o ramo de pessoa física e o `update` comum por:

```python
        elif len(i['IT-CO-CREDOR']) == 11:  # pessoa física
            cpf = mask_cpf(i['IT-CO-CREDOR'])

            # Caso a pessoa já seja um funcionário do SUAP, assume-se
            # que a informação do SIAPE é mais recente que a SIAFI
            if cpf in funcionarios_cpfs:
                continue

            dados_credor = {'cpf': cpf, 'nome': i['IT-NO-CREDOR'], 'nome_usual': i['IT-NO-MNEMONICO-CREDOR']}
            pk = PessoaFisica.objects.obter_ou_criar(dados_credor, Politica.PREENCHER)[0].pk
```

Mover o `Pessoa.objects.filter(pk=pk).update(...)` para dentro do ramo de pessoa jurídica, logo após o `get_or_create` do CNPJ: o credor PF já foi tratado pelo PREENCHER. O `sistema_origem` desse `update` é o bug da issue cosinf/suap#17640, fora deste MR.

No tratamento de endereço, trocar:

```python
        PessoaEndereco.objects.filter(pessoa__id=pk).delete()
```

por (o SIAFI não apaga o endereço de uma pessoa física que já tem):

```python
        if len(i['IT-CO-CREDOR']) == 11 and PessoaEndereco.objects.filter(pessoa__id=pk).exists():
            continue
        PessoaEndereco.objects.filter(pessoa__id=pk).delete()
```

(import `from rh.deduplicacao.entrada import Politica`).

- [ ] **Step 9: CPF repetido no formulário de PF (admin)**

Em `rh/forms.py`, `PessoaFisicaForm.clean_cpf`:

```python
    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if not cpfcnpj.validate(cpf):
            self.add_error('cpf', 'O CPF informado não é válido')
        elif PessoaFisica.objects.filter(cpf=formatar_cpf(cpf)).exclude(pk=self.instance.pk).exists():
            self.add_error('cpf', 'Já existe uma pessoa física com este CPF.')
        return cpf
```

(import `from rh.deduplicacao.documentos import formatar_cpf`).

- [ ] **Step 10: Rodar os testes**

Run: `… uv run pytest -q -n 3 rh comum financeiro --reuse-db`
Expected: verde, incluindo os 2 testes do Step 1.

- [ ] **Step 11: Commit**

```bash
git add rh comum djtools/middleware/govbr.py financeiro/importador.py
git commit -m "[rh] Criação de pessoa por obter_ou_criar em SIAPE, prestador, externa, gov.br e SIAFI"
```

### Task 6: Pontos de criação/atualização no `edu` e no `processo_seletivo`

**Files:**
- Modify: `edu/forms/matriculas.py` (`clean_data_nascimento` ~`:528-542`; `processar` ~`:941-947`)
- Modify: `edu/q_academico.py:447-450` e `:1723`
- Modify: `edu/tasks.py:3226-3236`
- Modify: `edu/management/commands/edu_importar_csv.py` (bloco `pf = …` até `pf.save()`, ~`:212-246`)
- Modify: `edu/forms/mini_cursos.py:182-185`, `:344-347`, `:420-423`
- Modify: `edu/models/turmas.py:493-497` (`adicionar_novo_aluno`)
- Modify: `edu/models/internacionalizacao.py` (`importar`… `:628-641`; `gerar_matricula` `:513-518`)
- Modify: `edu/models/alunos.py:1506-1510`
- Modify: `processo_seletivo/tasks.py:390-401`
- Test: `edu/tests/fluxos/conftest.py` (fixture `com_cpf_unico`) + os 4 fluxos de matrícula

**Interfaces:**
- Consumes: `Politica`, `aplicar_politica`, `verificar_documento`, `DocumentoDeOutraPessoa`, `PessoaFisica.objects.obter_ou_criar` (Task 4).

- [ ] **Step 1: Regressão: matrícula de quem já existe não pode duplicar a pessoa**

O spike mostrou 4 fluxos do `edu` que matriculam uma pessoa já cadastrada e quebram em `edu/forms/matriculas.py:947` assim que existe UNIQUE em `cpf`: `FicWorkflowTestCase`, `PosGraduacaoWorkflowTestCase`, `MatriculaOnlineCreditoWorkflowTestCase` e `MatriculaOnlineSeriadoWorkflowTestCase`. Eles passam a rodar com uma UNIQUE temporária.

Criar `edu/tests/fluxos/conftest.py`:

```python
import pytest
from django.db import connection


@pytest.fixture
def com_cpf_unico(db: None) -> None:
    """UNIQUE em pessoa_fisica.cpf dentro da transação do teste: a matrícula não pode duplicar a pessoa.

    Redundante depois da Release 2 (a constraint passa a existir de verdade); remover no MR 3.
    """
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS tmp_cpf_unico ON pessoa_fisica (cpf)')
```

e decorar as 4 classes com `@pytest.mark.usefixtures('com_cpf_unico')` (`edu/tests/fluxos/test_fluxo_fic.py:5`, `test_fluxo_edu_pos.py:6`, `test_fluxo_matricula_online_credito.py:6`, `test_fluxo_matricula_online_seriado.py:6`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `… uv run pytest -q edu/tests/fluxos/test_fluxo_fic.py edu/tests/fluxos/test_fluxo_edu_pos.py edu/tests/fluxos/test_fluxo_matricula_online_credito.py edu/tests/fluxos/test_fluxo_matricula_online_seriado.py --reuse-db`
Expected: 4 FAIL com `IntegrityError: duplicate key value violates unique constraint "tmp_cpf_unico"` vindo de `edu/forms/matriculas.py`.

- [ ] **Step 3: `adicionar_novo_aluno` deixa de clonar**

Em `edu/models/turmas.py`, trocar:

```python
        aluno = Aluno()
        pessoa_fisica.id = None
        pessoa_fisica.pk = None
        pessoa_fisica.uuid = uuid.uuid4()
        pessoa_fisica.save()
        aluno.pessoa_fisica = pessoa_fisica
```

por:

```python
        aluno = Aluno()
        aluno.pessoa_fisica = pessoa_fisica
```

(remover o `import uuid` se ficar sem uso).

- [ ] **Step 4: Minicurso: participante por `obter_ou_criar` (PREENCHER, sem data de nascimento)**

Em `edu/forms/mini_cursos.py`, nos 3 pontos que fazem:

```python
            pessoa_fisica = PessoaFisica()
            pessoa_fisica.cpf = participante['cpf']
            pessoa_fisica.nome = participante['nome']
```

(e a variante com `self.cleaned_data['cpf']`/`['nome']`), trocar por:

```python
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': participante['cpf'], 'nome': participante['nome']}, Politica.PREENCHER)
```

usando `self.cleaned_data[...]` onde o original usava. Import: `from rh.deduplicacao.entrada import Politica`.

- [ ] **Step 5: Transferência de curso e matrícula de intercâmbio reusam a PF**

Em `edu/models/alunos.py`, trocar:

```python
        pessoa_fisica = self.pessoa_fisica
        pessoa_fisica.id = None
        pessoa_fisica.pk = None
        pessoa_fisica.uuid = uuid.uuid4()
        pessoa_fisica.save()

        aluno.pessoa_fisica = pessoa_fisica
```

por:

```python
        aluno.pessoa_fisica = self.pessoa_fisica
```

Em `edu/models/internacionalizacao.py`, `gerar_matricula`, trocar:

```python
            pessoa_fisica = self.vinculo.pessoa.pessoafisica
            pessoa_fisica.eh_prestador = False
            pessoa_fisica.id = None
            pessoa_fisica.pk = None
            pessoa_fisica.uuid = uuid.uuid4()
            pessoa_fisica.save()
```

por:

```python
            pessoa_fisica = self.vinculo.pessoa.pessoafisica
```

(os `eh_*` são recalculados pelo `save()` da PF; remover `import uuid` se ficar sem uso).

- [ ] **Step 6: Importação de estrangeiros (CAUTELOSA, tem data de nascimento)**

Em `edu/models/internacionalizacao.py`, acrescentar ao dicionário `dados` (o da linha `'passaporte': passaporte,`) a entrada `'pais_origem': pais_por_nome(linha['PAIS'])` (import `from rh.deduplicacao.paises import pais_por_nome`). Sem país correspondente, o `obter_ou_criar` recusa a linha; isso precisa sair numa mensagem com o nome da coluna `PAIS`, não num 500. Depois trocar:

```python
                if prestador_servico is None:
                    pessoa_fisica = PessoaFisica.objects.create(**dados)
                    prestador_servico = PrestadorServico.objects.create(
                        pessoa_fisica=pessoa_fisica, justificativa_cadastro=JustificativaUsuarioExterno.objects.first(), ativo=True
                    )
                else:
                    PessoaFisica.objects.filter(pk=prestador_servico.pessoa_fisica_id).update(**dados)
```

por:

```python
                if prestador_servico is None:
                    pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(dados, Politica.CAUTELOSA)
                    prestador_servico = PrestadorServico.objects.create(
                        pessoa_fisica=pessoa_fisica, justificativa_cadastro=JustificativaUsuarioExterno.objects.first(), ativo=True
                    )
                else:
                    aplicar_politica(prestador_servico.pessoa_fisica, dados, Politica.CAUTELOSA)
                    prestador_servico.pessoa_fisica.save()
```

- [ ] **Step 7: Matrícula institucional (CAUTELOSA + verificação no formulário)**

Em `edu/forms/matriculas.py`, `EfetuarMatriculaForm.processar`, trocar:

```python
        pessoa_fisica = PessoaFisica()
        pessoa_fisica.cpf = self.cleaned_data['cpf']
        pessoa_fisica.nome_registro = self.cleaned_data['nome']
        pessoa_fisica.nome_social = self.cleaned_data['nome_social']
        pessoa_fisica.sexo = self.cleaned_data['sexo']
        pessoa_fisica.nascimento_data = self.cleaned_data['data_nascimento']
        pessoa_fisica.save()
```

por:

```python
        pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(
            {
                'cpf': self.cleaned_data['cpf'],
                'passaporte': self.cleaned_data.get('passaporte'),
                'nome_registro': self.cleaned_data['nome'],
                'nome_social': self.cleaned_data['nome_social'],
                'sexo': self.cleaned_data['sexo'],
                'nascimento_data': self.cleaned_data['data_nascimento'],
                # o formulário usa edu.Pais; a pessoa usa comum.Pais (conversão só pelo nome)
                'pais_origem': pais_por_nome(getattr(self.cleaned_data.get('pais_origem'), 'nome', None)),
            },
            Politica.CAUTELOSA,
        )
```

(import `from rh.deduplicacao.paises import pais_por_nome`). Estrangeiro sem CPF cujo país não exista em `comum.Pais` com o mesmo nome cai no `ValidationError` do `obter_ou_criar`. Para a mensagem sair no formulário e não virar 500, acrescente ao `clean_pais_origem` do mesmo formulário: se não há CPF, há passaporte e `pais_por_nome(pais.nome)` é `None`, `raise forms.ValidationError('País sem correspondência no cadastro de países do SUAP; procure a secretaria.')`.

Em `clean_data_nascimento`, antes do `return self.cleaned_data['data_nascimento']`:

```python
        try:
            verificar_documento(
                cpf=self.get_entered_data('cpf'),
                passaporte=self.get_entered_data('passaporte'),
                pais=pais_por_nome(getattr(self.get_entered_data('pais_origem'), 'nome', None)),
                nascimento_data=self.cleaned_data['data_nascimento'],
            )
        except DocumentoDeOutraPessoa as erro:
            raise forms.ValidationError(erro.messages) from erro
```

Import: `from rh.deduplicacao.entrada import DocumentoDeOutraPessoa, Politica, verificar_documento`. Se `clean_data_nascimento` passar de complexidade 10, extraia a checagem de idade para um helper.

- [ ] **Step 8: Importações legadas do acadêmico**

Em `edu/q_academico.py:447-450`, trocar:

```python
                if aluno_pf_id:
                    PessoaFisica.objects.filter(id=aluno_pf_id).update(**pf_args)
                    pf_id = aluno_pf_id
                else:
                    pf_id = PessoaFisica.objects.create(**pf_args).id
```

por:

```python
                try:
                    if aluno_pf_id:
                        pessoa_fisica = PessoaFisica.objects.get(pk=aluno_pf_id)
                        aplicar_politica(pessoa_fisica, pf_args, Politica.CAUTELOSA)
                        pessoa_fisica.save()
                        pf_id = aluno_pf_id
                    else:
                        pf_id = PessoaFisica.objects.obter_ou_criar(pf_args, Politica.CAUTELOSA)[0].id
                except ValidationError as erro:
                    logger.warning(f'Aluno {matricula} não importado: {erro.messages}')
                    continue
```

(`from django.core.exceptions import ValidationError` se ainda não importado). Em `:1723`, trocar `pf_id = PessoaFisica.objects.create(**pf_args)` por `pf_id = PessoaFisica.objects.obter_ou_criar(pf_args, Politica.CAUTELOSA)[0]`.

Em `edu/tasks.py` (`importar_alunos_csv_v2`), trocar:

```python
                        pessoa_fisica = aluno.pessoa_fisica
                        for key, value in pessoa_fisica_data.items():
                            setattr(pessoa_fisica, key, value)
                        pessoa_fisica.save()
                    else:
                        pessoa_fisica = PessoaFisica.objects.create(**pessoa_fisica_data)
```

por:

```python
                        pessoa_fisica = aluno.pessoa_fisica
                        aplicar_politica(pessoa_fisica, pessoa_fisica_data, Politica.CAUTELOSA)
                        pessoa_fisica.save()
                    else:
                        pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(pessoa_fisica_data, Politica.CAUTELOSA)
```

Em `edu/management/commands/edu_importar_csv.py`, trocar o trecho de `pf = PessoaFisica.objects.filter(vinculo__user__username=matricula).first()` até `pf.save()` (inclusive) por um dicionário `dados_pf` com os mesmos campos que hoje são atribuídos um a um: `nome`, `cpf`, `nascimento_data` (quando `!= '-'`), `sexo`, `nome_mae`, `nome_pai`, `rg`, `rg_orgao` (`[0:10]`), `rg_uf`, `rg_data` (quando `!= '-'`) e `passaporte`. Mantenha o `email_notificacao = dados[EMAIL]`, o cálculo de `raca` e o `print` de depuração como estão. Depois:

```python
        pf = PessoaFisica.objects.filter(vinculo__user__username=matricula).first()
        if pf:
            aplicar_politica(pf, dados_pf, Politica.CAUTELOSA)
            pf.save()
        else:
            pf, _ = PessoaFisica.objects.obter_ou_criar(dados_pf, Politica.CAUTELOSA)
        pf.username = matricula
```

- [ ] **Step 9: PROITEC (PREENCHER, sem data de nascimento)**

Em `processo_seletivo/tasks.py`, trocar:

```python
        if qs.exists():
            aluno = qs[0]
            aluno.pessoa_fisica.cpf = candidato_vaga.candidato.cpf
            aluno.pessoa_fisica.nome = candidato_vaga.candidato.nome
            aluno.telefone_principal = candidato_vaga.candidato.telefone
            aluno.pessoa_fisica.save()

        else:
            pessoa_fisica = PessoaFisica()
            pessoa_fisica.cpf = candidato_vaga.candidato.cpf
            pessoa_fisica.nome = candidato_vaga.candidato.nome
            pessoa_fisica.save()
```

por:

```python
        dados_pessoa = {'cpf': candidato_vaga.candidato.cpf, 'nome': candidato_vaga.candidato.nome}
        if qs.exists():
            aluno = qs[0]
            aplicar_politica(aluno.pessoa_fisica, dados_pessoa, Politica.PREENCHER)
            aluno.telefone_principal = candidato_vaga.candidato.telefone
            aluno.pessoa_fisica.save()

        else:
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(dados_pessoa, Politica.PREENCHER)
```

- [ ] **Step 10: Rodar os testes dos apps**

Run: `… uv run pytest -q -n 3 edu processo_seletivo --reuse-db`
Expected: verde, incluindo os 4 fluxos do Step 1.

- [ ] **Step 11: Commit**

```bash
git add edu processo_seletivo
git commit -m "[edu] Aluno novo reusa a pessoa física do documento em vez de cloná-la"
```

### Task 6b: País de origem nos formulários que aceitam passaporte

Sem CPF, o passaporte só vale com país (Global Constraints). Os formulários que criam ou editam pessoa com passaporte passam a pedir o país (`comum.Pais`), obrigatório quando não há CPF.

**Files:**
- Modify: `comum/forms.py` (`PrestadorServicoForm`, ~`:794-910`)
- Modify: `pesquisa/forms.py` (formulário de colaborador externo, ~`:4372-4455`)
- Modify: `projetos/forms.py` (~`:2850-2925`)
- Modify: `projetos_ensino/forms.py` (~`:2123-2195`)
- Modify: `edu/forms/professores.py` (~`:78`, `save` em `:293-340`)
- Verify: `edu/forms/alunos.py:48`. Só entra se o formulário gravar `pessoa_fisica.passaporte`; nesse caso, converte o `edu.Pais` do aluno com `pais_por_nome`, como na matrícula.
- Fora: `eventos/forms.py`, cujo passaporte é do próprio `Participante`, não da PF.
- Test: `comum/tests/views/test_prestador_estrangeiro.py`

- [ ] **Step 1: Teste (falha hoje: o formulário não tem o campo)**

```python
import pytest

from comum.forms import PrestadorServicoForm
from comum.models import Pais
from rh.enums import Nacionalidade

pytestmark = pytest.mark.django_db


def _dados(**extra: object) -> dict:
    return {'nome_registro': 'Ana Estrangeira', 'sexo': 'F', 'nacionalidade': Nacionalidade.ESTRANGEIRO, 'passaporte': 'AB123456', **extra}


def test_estrangeiro_sem_cpf_exige_pais() -> None:
    form = PrestadorServicoForm(data=_dados())

    assert not form.is_valid()
    assert 'pais_origem' in form.errors


def test_estrangeiro_com_pais_passa_na_validacao_do_documento() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    form = PrestadorServicoForm(data=_dados(pais_origem=argentina.pk))

    form.is_valid()
    assert 'pais_origem' not in form.errors
```

Os campos obrigatórios do `PrestadorServicoForm` além desses (setor, e-mail etc.) vão em `_dados` conforme o próprio formulário. O que importa é o erro em `pais_origem`.

- [ ] **Step 2: Rodar e ver falhar.** Expected: `assert 'pais_origem' in form.errors` falha.

- [ ] **Step 3: Campo e validação, iguais nos 5 formulários**

Em cada formulário, ao lado do campo `passaporte`:

```python
    pais_origem = forms.ModelChoiceFieldPlus(
        Pais.objects.all(), label='País de Origem', required=False, help_text='Obrigatório para estrangeiros sem CPF: o passaporte vale junto com o país emissor.'
    )
```

(`from comum.models import Pais`; se o módulo já importar um `Pais` do `edu`, importe como `from comum.models import Pais as PaisPessoa` e use esse nome). No `clean()`, no ramo que hoje exige passaporte para estrangeiro:

```python
            if passaporte and not cpf and not cleaned_data.get('pais_origem'):
                self.add_error('pais_origem', 'Informe o país de origem do passaporte.')
```

Na montagem do dicionário da pessoa, ao lado de `'passaporte': …`, acrescentar `'pais_origem': self.cleaned_data.get('pais_origem')`. No modo edição, inicialize o campo com `self.instance….pessoa_fisica.pais_origem`, como é feito com o passaporte. Onde o passaporte vira `ReadOnlyField`, o país também vira.

A checagem "passaporte já usado" desses formulários (`PrestadorServico.objects.filter(pessoa_fisica__passaporte=passaporte)`) passa a filtrar também `pessoa_fisica__pais_origem=cleaned_data.get('pais_origem')`.

- [ ] **Step 4: Rodar**

Run: `… uv run pytest -q -n 3 comum pesquisa projetos projetos_ensino edu --reuse-db`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add comum/forms.py pesquisa/forms.py projetos/forms.py projetos_ensino/forms.py edu/forms comum/tests/views/test_prestador_estrangeiro.py
git commit -m "[comum] País de origem obrigatório para estrangeiro sem CPF"
```

### Task 7: Código que supunha 1 PF = 1 aluno; consumidores do documento

**Files:**
- Modify: `ae/forms.py:1268-1270`
- Modify: `avaliacao_cursos/models.py:390`
- Modify: `saude/models.py:2067-2070` (`get_aluno`)
- Modify: `pedagogia/views.py:441`, `pedagogia/forms.py:83` e `:126`
- Modify: `edu/models/alunos.py:719`
- Modify: `edu/views/napne.py:321`, `eventos/admin.py:466`
- Modify: `api/endpoints/rh.py:131`
- Modify: `edu/templates/declaracao_participacao_projeto_final_pdf.html:14`
- Test: `saude/tests/models/test_cartao_vacinal_aluno.py`

**Interfaces:**
- Consumes: `User.get_relacionamento()` (`comum/models.py:419`), `Aluno.get_user()` (`edu/models/alunos.py:4883`).

- [ ] **Step 1: Teste (falha com dois alunos na mesma PF, como fica depois do merge)**

`saude/tests/models/test_cartao_vacinal_aluno.py`. Usa as fixtures `aluno` e `prontuario` de `saude/tests/conftest.py`. `get_aluno` é de `CartaoVacinal` (`saude/models.py:2067`).

```python
import pytest

from edu.tests.factories import AlunoFactory
from saude.models import CartaoVacinal, Vacina

pytestmark = pytest.mark.django_db


def test_get_aluno_com_dois_alunos_na_mesma_pessoa(aluno, prontuario) -> None:
    AlunoFactory(pessoa_fisica=aluno.pessoa_fisica)  # mesma pessoa, outra matrícula
    cartao = CartaoVacinal.objects.create(prontuario=prontuario, vacina=Vacina.objects.create(nome='Hepatite B', doses=3), numero_dose=1)

    assert cartao.get_aluno() == aluno
```

- [ ] **Step 2: Rodar e ver falhar**

Expected: `MultipleObjectsReturned`.

- [ ] **Step 3: Trocar as buscas de aluno por pessoa pela busca pelo vínculo**

`saude/models.py`:

```python
    def get_aluno(self):
        relacionamento = self.prontuario.vinculo.relacionamento
        return relacionamento if isinstance(relacionamento, Aluno) else None
```

`ae/forms.py`:

```python
        aluno = user.get_relacionamento()
        if isinstance(aluno, Aluno):
            self.fields['primeira_opcao'].queryset = self.fields['primeira_opcao'].queryset.filter(campus=aluno.curso_campus.diretoria.setor.uo)
            self.fields['segunda_opcao'].queryset = self.fields['segunda_opcao'].queryset.filter(campus=aluno.curso_campus.diretoria.setor.uo)
        else:
```

`avaliacao_cursos/models.py:390`: `aluno = self.vinculo.relacionamento`.
`pedagogia/views.py:441`: `aluno = request.user.get_relacionamento()`.
`pedagogia/forms.py:83` e `:126`: `aluno = tl.get_user().get_relacionamento()`.
`edu/models/alunos.py:719`: `user = self.get_user()`.

Vínculo pego pela PF, que depois do merge devolve o do servidor para quem é prestador ou aluno:
- `edu/views/napne.py:321`: trocar `profissional_apoio_especializado.profissional.pessoa_fisica.get_vinculo()` por `profissional_apoio_especializado.profissional.get_vinculo()` (`profissional` é `PrestadorServico`).
- `eventos/admin.py:466`: trocar `coordenador_obj.pessoa_fisica.get_vinculo()` por `coordenador_obj.get_vinculo()` (`coordenador` é `Servidor`).

Os demais `pessoa.get_vinculo()` (`pesquisa/models.py:3501`, `projetos/models.py:3595`, `projetos_ensino/models.py:2527`) já são chamados no papel e só leem o nome; `protocolo/.../importar_sei.py:146` só imprime. Ficam como estão.

- [ ] **Step 4: Passaporte nulo e documento sintético nos consumidores**

`api/endpoints/rh.py:131`: `passaporte = getattr(pessoa_fisica, 'passaporte', '') or ''`.

`edu/templates/declaracao_participacao_projeto_final_pdf.html:14`: trocar `{{ vinculo.pessoa.pessoafisica.documento_identificador|format }}` por `{{ vinculo.pessoa.pessoafisica.get_cpf_ou_passaporte|format }}`. Um sintético `CONFLITO-…` não pode sair impresso numa declaração.

Varredura de outros leitores:

Run: `grep -rnE "passaporte\s*==\s*['\"]['\"]|passaporte=['\"]['\"]|exclude\(passaporte=['\"]|documento_identificador" --include='*.py' --include='*.html' . | grep -v "migrations\|/tests/\|rh/deduplicacao\|get_variaveis\|documento_identificador=(''|None)"`
Expected: só `rh/models/pessoa/pessoa_fisica.py` (o `aluno_set.exclude(passaporte='')` sobre o campo do **aluno**) e `comum/admin.py:809` (exibição no admin). Qualquer outro leitor de `PessoaFisica.passaporte == ''` vira `not pf.passaporte`.

- [ ] **Step 5: Rodar**

Run: `… uv run pytest -q -n 3 saude ae avaliacao_cursos pedagogia api edu eventos --reuse-db`
Expected: verde.

- [ ] **Step 6: Commit**

```bash
git add ae avaliacao_cursos saude pedagogia edu api eventos
git commit -m "[comum] Aluno pelo vínculo em vez de pela pessoa física"
```

### Task 8: Trava contra criação de PF fora do `obter_ou_criar`

**Files:**
- Test: `rh/tests/models/test_criacao_pessoa_fisica_centralizada.py`

- [ ] **Step 1: Escrever o teste**

```python
"""Ninguém cria PessoaFisica fora do obter_ou_criar (spec da deduplicação, seção 3)."""

import re
from pathlib import Path

from django.apps import apps

RAIZ = Path(__file__).resolve().parents[3]
PADRAO = re.compile(
    r'PessoaFisica(\.objects)?\.(create|get_or_create|update_or_create|bulk_create)\('
    r'|PessoaFisica\(\s*\)|PessoaFisica\(\s*\w+\s*='
    r'|pessoa_?fisica\.(pk|id)\s*=\s*None'  # clonagem por pk=None (minicurso, transferência, intercâmbio)
)
PERMITIDOS = {
    'rh/deduplicacao/entrada.py',  # o próprio obter_ou_criar
    'rh/deduplicacao/aplicacao.py',  # instâncias só para bulk_update da higiene
    'edu/forms/matriculas.py',  # PessoaFisica() só para calcular a idade nos clean_* (não salva)
    'comum/webservice.py',  # PF fictícia pk=-1 do superusuário no terminal (não salva)
}


def _arquivos_dos_apps() -> set[Path]:
    arquivos = set()
    for config in apps.get_app_configs():
        base = Path(config.path)
        if RAIZ in base.parents:
            arquivos.update(base.rglob('*.py'))
    return arquivos


def test_pessoa_fisica_so_e_criada_por_obter_ou_criar() -> None:
    ofensores = []
    for arquivo in sorted(_arquivos_dos_apps()):
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if '/migrations/' in relativo or '/tests/' in relativo or '/features/' in relativo or 'new_tests' in relativo or relativo in PERMITIDOS:
            continue
        for numero, linha in enumerate(arquivo.read_text(errors='ignore').splitlines(), 1):
            if PADRAO.search(linha):
                ofensores.append(f'{relativo}:{numero}: {linha.strip()}')
    assert not ofensores, '\n'.join(ofensores)
```

- [ ] **Step 2: Rodar**

Run: `… uv run pytest -q rh/tests/models/test_criacao_pessoa_fisica_centralizada.py --reuse-db`
Expected: PASS depois das Tasks 5 e 6. Se listar ofensor, troque-o por `obter_ou_criar` com a política da fonte (tabela do Global Constraints); só acrescente a `PERMITIDOS` quem comprovadamente não salva.

- [ ] **Step 3: Commit**

```bash
git add rh/tests/models/test_criacao_pessoa_fisica_centralizada.py
git commit -m "[rh] Teste que impede criar PessoaFisica fora do obter_ou_criar"
```

### Task 9: Descoberta de referências e trava de catálogo

**Files:**
- Create: `rh/deduplicacao/referencias.py`
- Test: `rh/tests/tasks/test_referencias_pessoa.py`

**Interfaces:**
- Produces:
  - `Referencia(tabela: str, coluna: str, alvo: str, pk: str, unicidades: tuple[tuple[str, ...], ...])`, com as propriedades `um_para_um: bool` e `compostas: tuple[tuple[str, ...], ...]`;
  - `ReferenciaGenerica(tabela: str, coluna_tipo: str, coluna_id: str, id_texto: bool)`;
  - `referencias() -> list[Referencia]`;
  - `referencias_genericas() -> list[ReferenciaGenerica]`;
  - `fks_desconhecidas(conhecidas: list[Referencia]) -> list[str]`.

- [ ] **Step 1: Escrever os testes**

```python
import pytest
from django.db import connection

from rh.deduplicacao.referencias import fks_desconhecidas, referencias

pytestmark = pytest.mark.django_db


def _por_coluna() -> dict[tuple[str, str], object]:
    return {(r.tabela, r.coluna): r for r in referencias()}


def test_referencias_incluem_fk_para_pf_e_para_pessoa_sem_parent_link() -> None:
    refs = _por_coluna()

    assert refs[('edu_aluno', 'pessoa_fisica_id')].alvo == 'pessoa_fisica'
    assert refs[('comum_vinculo', 'pessoa_id')].alvo == 'pessoa'
    assert ('pessoa_fisica', 'pessoa_ptr_id') not in refs


def test_banco_criado_dos_models_nao_tem_fk_desconhecida() -> None:
    assert fks_desconhecidas(referencias()) == []


def test_fk_fora_do_orm_e_apontada() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_fantasma (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')

    assert fks_desconhecidas(referencias()) == ['tmp_fantasma.pf']


def test_unicidade_vem_do_banco() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
        cursor.execute('CREATE UNIQUE INDEX tmp_par_telefone ON comum_pessoatelefone (pessoa_id, numero)')

    refs = _por_coluna()
    assert refs[('comum_contatoemergencia', 'pessoa_fisica_id')].um_para_um
    assert refs[('comum_pessoatelefone', 'pessoa_id')].compostas == (('pessoa_id', 'numero'),)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `… uv run pytest -q rh/tests/tasks/test_referencias_pessoa.py --reuse-db`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
"""Descoberta das referências a PessoaFisica/Pessoa, em tempo de execução (apps instalados na instituição)."""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import connection

SQL_UNICIDADES = """
    SELECT array_agg(a.attname::text ORDER BY k.ordem)
    FROM pg_index i
    CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ordem)
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
    WHERE i.indrelid = %s::regclass AND i.indisunique AND NOT i.indisprimary
    GROUP BY i.indexrelid
"""
SQL_FKS = """
    SELECT c.conrelid::regclass::text, a.attname::text
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.confrelid IN ('pessoa_fisica'::regclass, 'pessoa'::regclass)
"""


@dataclass(frozen=True)
class Referencia:
    tabela: str
    coluna: str
    alvo: str
    pk: str
    unicidades: tuple[tuple[str, ...], ...]

    @property
    def um_para_um(self) -> bool:
        return (self.coluna,) in self.unicidades

    @property
    def compostas(self) -> tuple[tuple[str, ...], ...]:
        return tuple(u for u in self.unicidades if u != (self.coluna,))


@dataclass(frozen=True)
class ReferenciaGenerica:
    tabela: str
    coluna_tipo: str
    coluna_id: str
    id_texto: bool


def _modelos(include_auto_created: bool = True) -> list:
    return [m for m in apps.get_models(include_auto_created=include_auto_created) if m._meta.managed and not m._meta.proxy]


def _unicidades(tabela: str, coluna: str) -> tuple[tuple[str, ...], ...]:
    with connection.cursor() as cursor:
        cursor.execute(SQL_UNICIDADES, [tabela])
        return tuple(tuple(colunas) for (colunas,) in cursor.fetchall() if coluna in colunas)


def referencias() -> list[Referencia]:
    from rh.models import Pessoa, PessoaFisica

    alvos = {PessoaFisica: PessoaFisica._meta.db_table, Pessoa: Pessoa._meta.db_table}
    encontradas = []
    for modelo in _modelos():
        for campo in modelo._meta.local_fields:
            alvo = alvos.get(campo.related_model) if campo.is_relation else None
            if alvo and not campo.remote_field.parent_link:
                tabela = modelo._meta.db_table
                encontradas.append(Referencia(tabela, campo.column, alvo, modelo._meta.pk.column, _unicidades(tabela, campo.column)))
    return encontradas


def referencias_genericas() -> list[ReferenciaGenerica]:
    encontradas = []
    for modelo in _modelos(include_auto_created=False):
        for campo in modelo._meta.private_fields:
            if isinstance(campo, GenericForeignKey):
                coluna_id = modelo._meta.get_field(campo.fk_field)
                texto = coluna_id.get_internal_type() in ('CharField', 'TextField')
                encontradas.append(ReferenciaGenerica(modelo._meta.db_table, modelo._meta.get_field(campo.ct_field).column, coluna_id.column, texto))
    return encontradas


def fks_desconhecidas(conhecidas: list[Referencia]) -> list[str]:
    """FKs do banco para pessoa/pessoa_fisica que o ORM não conhece: bloqueiam o DELETE da perdedora."""
    sabidas = {(r.tabela, r.coluna) for r in conhecidas} | {('pessoa_fisica', 'pessoa_ptr_id'), ('pessoa_juridica', 'pessoa_ptr_id')}
    with connection.cursor() as cursor:
        cursor.execute(SQL_FKS)
        return sorted(f'{tabela}.{coluna}' for tabela, coluna in cursor.fetchall() if (tabela.strip('"'), coluna) not in sabidas)
```

- [ ] **Step 4: Rodar e ver passar.** Mesmo comando. Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add rh/deduplicacao/referencias.py rh/tests/tasks/test_referencias_pessoa.py
git commit -m "[rh] Descoberta das referências a pessoa e trava de catálogo"
```

### Task 10: Conflito de campo (puro) e fase `planejar`

**Files:**
- Create: `rh/deduplicacao/campos.py`
- Create: `rh/deduplicacao/plano.py`
- Test: `rh/tests/models/test_campos_deduplicacao.py` (sem banco)
- Test: `rh/tests/tasks/test_deduplicar_pessoas.py` (parte `planejar`)

**Interfaces:**
- Produces:
  - `campos_mesclaveis() -> list[str]` (attnames);
  - `resolver_campos(vencedor: dict, perdedoras: list[dict]) -> tuple[dict[str, Any], list[tuple[int, str, Any]]]`;
  - `planejar() -> dict[str, int]` (contagem por ação). Levanta `CommandError` se houver FK desconhecida.

- [ ] **Step 1: Testes de `resolver_campos` (sem banco)**

```python
from rh.deduplicacao.campos import resolver_campos


def test_preenche_vazio_do_vencedor_com_a_perdedora_mais_recente() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'rg': None}, [{'pk': 2, 'rg': '111'}, {'pk': 3, 'rg': '222'}])

    assert preenchimentos == {'rg': '222'}
    assert descartes == [(2, 'rg', '111')]


def test_valor_do_vencedor_prevalece_e_o_diferente_vai_para_auditoria() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'nome_mae': 'Maria'}, [{'pk': 2, 'nome_mae': 'Joana'}, {'pk': 3, 'nome_mae': 'Maria'}])

    assert preenchimentos == {}
    assert descartes == [(2, 'nome_mae', 'Joana')]


def test_passaporte_so_e_auditado() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'passaporte': None}, [{'pk': 2, 'passaporte': 'AB123456'}])

    assert preenchimentos == {}
    assert descartes == [(2, 'passaporte', 'AB123456')]
```

- [ ] **Step 2: Testes do `planejar` (com banco)**

`rh/tests/tasks/test_deduplicar_pessoas.py`:

```python
from datetime import date

import pytest
from django.core.management import CommandError
from django.db import connection

from rh.deduplicacao.plano import planejar
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa')
CPF = '529.982.247-25'


def _acoes(pk: int) -> set[str]:
    return set(D.objects.filter(pf_id=pk).values_list('acao', flat=True))


def _legada(**campos: object) -> PessoaFisica:
    """PF como as da base legada: grava direto, sem passar pelo save()."""
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(**campos)
    return PessoaFisica.objects.get(pk=pessoa.pk)


def test_planejar_nao_escreve_em_pessoa() -> None:
    a, b = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)

    planejar()

    assert PessoaFisica.objects.filter(pk__in=[a.pk, b.pk]).count() == 2
    assert D.objects.get(pf_id=a.pk, acao=D.MESCLADA).sobrevivente_id == b.pk


def test_nascimento_divergente_separa_com_documento_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))  # sem papel, vence o maior id

    planejar()

    linha = D.objects.get(pf_id=separada.pk, acao=D.SEPARADA)
    assert linha.documento == f'CONFLITO-{separada.pk}-{CPF}'
    assert (linha.campo, linha.valor_original) == ('cpf', CPF)


def test_sem_documento_e_cpf_invalido_viram_sinteticos() -> None:
    sem = _legada(cpf='___.___.___-__', documento_identificador=None)
    invalido = _legada(cpf='529.982.247-24')

    planejar()

    assert D.objects.get(pf_id=sem.pk, acao=D.SINTETICO).documento == f'SEMDOC-{sem.pk}'
    assert {D.CPF_ANULADO, D.SINTETICO} <= _acoes(invalido.pk)
    assert D.objects.get(pf_id=invalido.pk, acao=D.SINTETICO).documento == f'INVALIDO-{invalido.pk}-52998224724'


def test_um_para_um_colidindo_separa_o_grupo() -> None:
    from comum.models import ContatoEmergencia

    a, b = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
    for pessoa in (a, b):
        ContatoEmergencia.objects.create(pessoa_fisica=pessoa, nome_contato='Mãe', telefone='84999999999')

    planejar()

    assert D.objects.get(pf_id=a.pk, acao=D.SEPARADA).motivo.startswith('unicidade em comum_contatoemergencia')


def test_passaporte_repetido_entre_pessoas_diferentes_fica_com_a_prioritaria() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    a = PessoaFisicaFactory(cpf=CPF, passaporte='AB123456', pais_origem=argentina)
    b = PessoaFisicaFactory(cpf='390.533.447-05', passaporte='AB123456', pais_origem=argentina)

    planejar()

    assert D.objects.get(pf_id=a.pk, acao=D.PASSAPORTE_ANULADO).valor_original == 'AB123456'
    assert D.PASSAPORTE_ANULADO not in _acoes(b.pk)


def test_mesmo_passaporte_em_paises_diferentes_nao_agrupa() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    chile = Pais.objects.create(codigo='158', nome='CHILE')
    a = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    b = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=chile)

    planejar()

    assert not D.objects.filter(pf_id__in=[a.pk, b.pk], acao__in=[D.MESCLADA, D.SEPARADA, D.PASSAPORTE_ANULADO]).exists()


def test_sem_cpf_aluno_brasileiro_ganha_brasil() -> None:
    from comum.models import Pais
    from edu.tests.factories import AlunoFactory

    brasil = Pais.objects.create(codigo='024', nome='BRASIL')
    sem_cpf = _legada(cpf=None, documento_identificador=None)
    AlunoFactory(pessoa_fisica=sem_cpf, nacionalidade='Brasileira')
    com_cpf = PessoaFisicaFactory()
    AlunoFactory(pessoa_fisica=com_cpf, nacionalidade='Brasileira')

    planejar()

    assert D.objects.get(pf_id=sem_cpf.pk, acao=D.PAIS_PREENCHIDO).documento == str(brasil.pk)
    assert D.PAIS_PREENCHIDO not in _acoes(com_cpf.pk)


def test_fk_desconhecida_aborta() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_fantasma (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')

    with pytest.raises(CommandError, match='tmp_fantasma.pf'):
        planejar()


def test_replanejar_descarta_so_o_que_nao_foi_aplicado() -> None:
    PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    aplicada = D.objects.create(pf_id=1, acao=D.MESCLADA, sobrevivente_id=2, aplicado_em='2026-01-01T00:00:00Z')

    planejar()
    planejar()

    assert D.objects.filter(pk=aplicada.pk).exists()
    assert D.objects.filter(acao=D.MESCLADA, aplicado_em__isnull=True).count() == 1
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `… uv run pytest -q rh/tests/models/test_campos_deduplicacao.py rh/tests/tasks/test_deduplicar_pessoas.py --reuse-db`
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: `rh/deduplicacao/campos.py`**

```python
"""Conflito de campo entre a PF sobrevivente e as perdedoras (puro, usado no planejar e no aplicar)."""

from __future__ import annotations

from typing import Any

# Derivados, identidade ou recalculados pelo save(): não se mesclam.
IGNORADOS = {
    'id',
    'pessoa_ptr_id',
    'cpf',
    'documento_identificador',
    'nome',
    'nome_usual',
    'eh_servidor',
    'eh_aluno',
    'eh_prestador',
    'eh_usuarioexterno',
    'search_fields_optimized',
    'uuid',
}
# Só auditados: o passaporte do sobrevivente não é trocado pelo da perdedora.
SO_AUDITORIA = {'passaporte'}


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ''


def campos_mesclaveis() -> list[str]:
    from rh.models import PessoaFisica

    return [campo.attname for campo in PessoaFisica._meta.concrete_fields if campo.attname not in IGNORADOS]


def resolver_campos(vencedor: dict, perdedoras: list[dict]) -> tuple[dict[str, Any], list[tuple[int, str, Any]]]:
    """Preenche os vazios do vencedor com a perdedora de maior id; devolve o que foi descartado."""
    preenchimentos: dict[str, Any] = {}
    descartes: list[tuple[int, str, Any]] = []
    ordenadas = sorted(perdedoras, key=lambda p: p['pk'], reverse=True)
    for campo, atual in vencedor.items():
        if campo == 'pk':
            continue
        for perdedora in ordenadas:
            valor = perdedora[campo]
            if _vazio(valor) or valor == atual:
                continue
            if _vazio(atual) and campo not in SO_AUDITORIA:
                preenchimentos[campo] = atual = valor
            else:
                descartes.append((perdedora['pk'], campo, valor))
    descartes.sort()
    return preenchimentos, descartes
```

- [ ] **Step 5: `rh/deduplicacao/plano.py`**

```python
"""Fase ``planejar`` do deduplicar_pessoas: higiene, grupos e separações, sem escrever em PessoaFisica.

Resultado em rh.DeduplicacaoPessoa. Regras: spec 2026-10-07-deduplicacao-pessoa-fisica-design.md, seções 1 e 2.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.management import CommandError
from django.db import connection, transaction

from rh.deduplicacao.campos import campos_mesclaveis, resolver_campos
from comum.models import Pais
from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    documento_sintetico,
    eh_sintetico,
    formatar_cpf,
    formatar_passaporte,
    normalizar_nome_pais,
    passaporte_valido,
)
from rh.deduplicacao.entrada import nascimento_diverge
from rh.deduplicacao.paises import ids_por_nome
from rh.deduplicacao.referencias import Referencia, fks_desconhecidas, referencias
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaFisica


@dataclass
class Pessoa:
    pk: int
    cpf: str | None
    passaporte: str | None
    nascimento: date | None
    prioridade: tuple[bool, bool, bool, int]
    documento: str | None = None  # documento_identificador atual (sintético já gravado é preservado)
    pais_id: int | None = None
    codigo_pais: str | None = None
    cpf_invalido: str | None = None
    passaporte_em_conflito: str | None = None
    sobrevivente: int | None = None
    separacao: tuple[str, str, str] | None = None  # (campo, documento original, motivo)

    @property
    def chave(self) -> str | None:
        return self.cpf or chave_passaporte(self.passaporte, self.codigo_pais)


def planejar() -> dict[str, int]:
    refs = referencias()
    desconhecidas = fks_desconhecidas(refs)
    if desconhecidas:
        raise CommandError('FKs para pessoa que o ORM não conhece (remova ou trate antes de deduplicar): ' + ', '.join(desconhecidas))
    acoes: list[D] = []
    pessoas = _carregar_pessoas()
    passaportes_de_aluno, paises_de_aluno = _passaportes_de_aluno(), _paises_de_aluno()
    codigos = dict(Pais.objects.values_list('pk', 'codigo'))
    for pessoa in pessoas:
        _higienizar(pessoa, passaportes_de_aluno.get(pessoa.pk), acoes)
        _inferir_pais(pessoa, paises_de_aluno.get(pessoa.pk), codigos, acoes)
    grupos = _mesclas(pessoas)
    _separar_colisoes_um_para_um(grupos, refs)
    _emitir_mesclas_e_separacoes(pessoas, acoes)
    _emitir_conflitos_de_campo(grupos, acoes)
    _resolver_passaportes_repetidos(pessoas, acoes)
    _emitir_sinteticos(pessoas, acoes)
    with transaction.atomic():
        D.objects.filter(aplicado_em__isnull=True).delete()
        D.objects.bulk_create(acoes, batch_size=5000)
    return dict(Counter(acao.acao for acao in acoes))


def _carregar_pessoas() -> list[Pessoa]:
    # ponytail: toda a tabela em memória (~555 mil PFs no IFRN ≈ 150 MB); paginar por documento se uma instituição estourar
    linhas = PessoaFisica.objects.com_prioridade().values_list(
        'pk', 'cpf', 'passaporte', 'nascimento_data', 'servidor_ativo', 'aluno_ativo', 'prestador_ativo', 'documento_identificador', 'pais_origem_id'
    )
    return [
        Pessoa(pk, cpf, passaporte, nasc, (srv, alu, pre, pk), documento, pais)
        for pk, cpf, passaporte, nasc, srv, alu, pre, documento, pais in linhas.iterator(chunk_size=5000)
    ]


def _passaportes_de_aluno() -> dict[int, str]:
    if 'edu' not in settings.INSTALLED_APPS:
        return {}
    from edu.models import Aluno

    return dict(Aluno.objects.exclude(passaporte__isnull=True).exclude(passaporte='').order_by('pk').values_list('pessoa_fisica_id', 'passaporte'))


def _paises_de_aluno() -> dict[int, int]:
    """pf_id → comum.Pais pelo aluno mais recente: brasileiro → Brasil; estrangeiro → edu.Pais convertido pelo nome."""
    if 'edu' not in settings.INSTALLED_APPS:
        return {}
    from edu.models import Aluno

    por_nome = ids_por_nome()
    brasil = por_nome.get('BRASIL')
    paises: dict[int, int] = {}
    alunos = Aluno.objects.order_by('pk').values_list('pessoa_fisica_id', 'nacionalidade', 'pais_origem__nome')
    for pf_id, nacionalidade, nome_pais in alunos.iterator(chunk_size=5000):
        pais = brasil if (nacionalidade or '').upper().startswith('BRASIL') else por_nome.get(normalizar_nome_pais(nome_pais))
        if pais:
            paises[pf_id] = pais
    return paises


def _inferir_pais(pessoa: Pessoa, pais_do_aluno: int | None, codigos: dict[int, str], acoes: list[D]) -> None:
    """Sem CPF, o país é obrigatório (CHECK da Release 2): infere do aluno quando falta."""
    if pessoa.pais_id is None and not pessoa.cpf and pais_do_aluno:
        acoes.append(D(pf_id=pessoa.pk, acao=D.PAIS_PREENCHIDO, campo='pais_origem', documento=str(pais_do_aluno)))
        pessoa.pais_id = pais_do_aluno
    pessoa.codigo_pais = codigos.get(pessoa.pais_id)


def _higienizar(pessoa: Pessoa, passaporte_do_aluno: str | None, acoes: list[D]) -> None:
    if pessoa.cpf and not cpf_valido(pessoa.cpf):
        acoes.append(D(pf_id=pessoa.pk, acao=D.CPF_ANULADO, campo='cpf', valor_original=pessoa.cpf))
        pessoa.cpf_invalido, pessoa.cpf = pessoa.cpf, None
    else:
        pessoa.cpf = formatar_cpf(pessoa.cpf)
    passaporte = formatar_passaporte(pessoa.passaporte)
    if not passaporte and formatar_passaporte(passaporte_do_aluno):
        passaporte = formatar_passaporte(passaporte_do_aluno)
        acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_PREENCHIDO, campo='passaporte', documento=passaporte))
    if passaporte and not passaporte_valido(passaporte):
        acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_ANULADO, campo='passaporte', valor_original=passaporte))
        passaporte = None
    pessoa.passaporte = passaporte


def _mesclas(pessoas: list[Pessoa]) -> dict[int, list[Pessoa]]:
    """Agrupa por documento e decide sobrevivente/separadas; devolve {sobrevivente: perdedoras mescladas}."""
    por_chave: dict[str, list[Pessoa]] = defaultdict(list)
    for pessoa in pessoas:
        if pessoa.chave:
            por_chave[pessoa.chave].append(pessoa)
    grupos: dict[int, list[Pessoa]] = {}
    for grupo in por_chave.values():
        if len(grupo) < 2:
            continue
        vencedora = max(grupo, key=lambda p: p.prioridade)
        for pessoa in grupo:
            if pessoa is vencedora:
                continue
            if nascimento_diverge(vencedora.nascimento, pessoa.nascimento):
                _separar(pessoa, f'nascimento {pessoa.nascimento} ≠ {vencedora.nascimento} da PF {vencedora.pk}')
            else:
                pessoa.sobrevivente = vencedora.pk
                grupos.setdefault(vencedora.pk, []).append(pessoa)
    return grupos


def _separar(pessoa: Pessoa, motivo: str) -> None:
    campo = 'cpf' if pessoa.cpf else 'passaporte'
    pessoa.separacao = (campo, pessoa.chave, motivo)
    pessoa.sobrevivente = None
    setattr(pessoa, campo, None)


def _separar_colisoes_um_para_um(grupos: dict[int, list[Pessoa]], refs: list[Referencia]) -> None:
    for ref in (r for r in refs if r.um_para_um):
        membros = [pk for sobrevivente, perdedoras in grupos.items() for pk in (sobrevivente, *(p.pk for p in perdedoras))]
        q = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT DISTINCT {q(ref.coluna)} FROM {q(ref.tabela)} WHERE {q(ref.coluna)} = ANY(%s)', [membros])
            com_linha = {pk for (pk,) in cursor.fetchall()}
        for sobrevivente, perdedoras in list(grupos.items()):
            if sum(pk in com_linha for pk in (sobrevivente, *(p.pk for p in perdedoras))) > 1:
                for pessoa in perdedoras:
                    _separar(pessoa, f'unicidade em {ref.tabela}.{ref.coluna}')
                del grupos[sobrevivente]


def _emitir_mesclas_e_separacoes(pessoas: list[Pessoa], acoes: list[D]) -> None:
    for pessoa in pessoas:
        if pessoa.sobrevivente:
            acoes.append(D(pf_id=pessoa.pk, sobrevivente_id=pessoa.sobrevivente, acao=D.MESCLADA, documento=pessoa.chave))
        elif pessoa.separacao:
            campo, original, motivo = pessoa.separacao
            sintetico = documento_sintetico(pessoa.pk, conflito=original)
            acoes.append(D(pf_id=pessoa.pk, acao=D.SEPARADA, campo=campo, valor_original=original, documento=sintetico, motivo=motivo))


def _emitir_conflitos_de_campo(grupos: dict[int, list[Pessoa]], acoes: list[D]) -> None:
    campos = campos_mesclaveis()
    itens = list(grupos.items())
    for inicio in range(0, len(itens), 2000):
        fatia = itens[inicio : inicio + 2000]
        pks = [pk for sobrevivente, perdedoras in fatia for pk in (sobrevivente, *(p.pk for p in perdedoras))]
        valores = {v['pk']: v for v in PessoaFisica.objects.filter(pk__in=pks).values('pk', *campos)}
        for sobrevivente, perdedoras in fatia:
            _, descartes = resolver_campos(valores[sobrevivente], [valores[p.pk] for p in perdedoras])
            acoes.extend(
                D(pf_id=pk, sobrevivente_id=sobrevivente, acao=D.CAMPO_DESCARTADO, campo=campo, valor_original=str(valor)[:2000])
                for pk, campo, valor in descartes
            )


def _resolver_passaportes_repetidos(pessoas: list[Pessoa], acoes: list[D]) -> None:
    """Unicidade por (país, passaporte) entre as pessoas que sobram; passaporte sem país não é documento."""
    por_passaporte: dict[str, list[Pessoa]] = defaultdict(list)
    for pessoa in pessoas:
        chave = chave_passaporte(pessoa.passaporte, pessoa.codigo_pais)
        if chave and not pessoa.sobrevivente:
            por_passaporte[chave].append(pessoa)
    for repetidas in (g for g in por_passaporte.values() if len(g) > 1):
        mantida = max(repetidas, key=lambda p: p.prioridade)
        for pessoa in repetidas:
            if pessoa is not mantida:
                acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_ANULADO, campo='passaporte', valor_original=pessoa.passaporte))
                pessoa.passaporte_em_conflito = chave_passaporte(pessoa.passaporte, pessoa.codigo_pais)
                pessoa.passaporte = None


def _emitir_sinteticos(pessoas: list[Pessoa], acoes: list[D]) -> None:
    for pessoa in pessoas:
        if pessoa.chave or pessoa.sobrevivente or pessoa.separacao or eh_sintetico(pessoa.documento):
            continue  # sintético já gravado (CONFLITO-/INVALIDO-) sobrevive a um novo planejar
        documento = documento_sintetico(pessoa.pk, conflito=pessoa.passaporte_em_conflito, cpf_invalido=pessoa.cpf_invalido)
        acoes.append(D(pf_id=pessoa.pk, acao=D.SINTETICO, documento=documento))
```

- [ ] **Step 6: Rodar e ver passar.** Mesmo comando do Step 3. Expected: verde. Rode `uv run ruff check rh/deduplicacao` e confirme que o hook de complexidade não reclamou.

- [ ] **Step 7: Commit**

```bash
git add rh/deduplicacao/campos.py rh/deduplicacao/plano.py rh/tests/models/test_campos_deduplicacao.py rh/tests/tasks/test_deduplicar_pessoas.py
git commit -m "[rh] Fase planejar da deduplicação de pessoas"
```

### Task 11: Fase `aplicar`

**Files:**
- Create: `rh/deduplicacao/aplicacao.py`
- Test: `rh/tests/tasks/test_deduplicar_pessoas.py` (parte `aplicar`)

**Interfaces:**
- Consumes: `referencias`, `referencias_genericas` (Task 9), `campos_mesclaveis`, `resolver_campos` (Task 10), `DeduplicacaoPessoa` (Task 2).
- Produces: `aplicar(lote: int = 1000) -> dict[str, int]` (`mescladas`, `erros`, `higiene`).

- [ ] **Step 1: Testes do `aplicar`**

Acrescentar a `rh/tests/tasks/test_deduplicar_pessoas.py`. Os imports abaixo vão para o **topo** do arquivo, junto dos da Task 10 (ruff E402):

```python
from comum.models import ContatoEmergencia, PessoaEndereco, PessoaTelefone, Vinculo
from rh.deduplicacao.aplicacao import aplicar
from rh.models import PessoaExterna, PessoaInfoComplementar


def _deduplicar() -> dict[str, int]:
    planejar()
    return aplicar()


def test_mescla_reaponta_fk_de_pf_e_de_pessoa_e_preserva_secret() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    contato = ContatoEmergencia.objects.create(pessoa_fisica=perdedora, nome_contato='Mãe', telefone='84999999999')
    endereco = PessoaEndereco.objects.create(pessoa=perdedora, logradouro='Rua A')
    externa = PessoaExterna(pessoa_fisica=perdedora, cpf=CPF, nome='Ana')
    externa.save()

    _deduplicar()

    assert not PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    contato.refresh_from_db()
    endereco.refresh_from_db()
    vinculo = Vinculo.objects.get(id_relacionamento=externa.pk, tipo_relacionamento__model='pessoaexterna')
    assert contato.pessoa_fisica_id == sobrevivente.pk
    assert endereco.pessoa_id == sobrevivente.pk
    assert vinculo.pessoa_id == sobrevivente.pk
    assert vinculo.secret == perdedora.pk
    assert D.objects.get(pf_id=perdedora.pk, acao=D.MESCLADA).aplicado_em is not None


def test_separada_fica_com_documento_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))

    _deduplicar()

    separada.refresh_from_db()
    assert separada.cpf is None
    assert separada.documento_identificador == f'CONFLITO-{separada.pk}-{CPF}'


def test_higiene_grava_sinteticos() -> None:
    sem = _legada(cpf='___.___.___-__', documento_identificador=None)
    invalido = _legada(cpf='529.982.247-24')

    _deduplicar()

    sem.refresh_from_db()
    invalido.refresh_from_db()
    assert (sem.cpf, sem.documento_identificador) == (None, f'SEMDOC-{sem.pk}')
    assert (invalido.cpf, invalido.documento_identificador) == (None, f'INVALIDO-{invalido.pk}-52998224724')


def test_passaporte_vira_documento_so_com_pais() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    com_pais = _legada(cpf=None, passaporte='AB123456', pais_origem=argentina, documento_identificador='AB123456')
    sem_pais = _legada(cpf=None, passaporte='CD654321', documento_identificador='CD654321')

    _deduplicar()

    com_pais.refresh_from_db()
    sem_pais.refresh_from_db()
    assert com_pais.documento_identificador == 'AB123456/011'
    assert (sem_pais.passaporte, sem_pais.documento_identificador) == ('CD654321', f'SEMDOC-{sem_pais.pk}')


def test_vazio_do_sobrevivente_e_preenchido_e_divergencia_auditada() -> None:
    perdedora = PessoaFisicaFactory(cpf=CPF, rg='111', nome_mae='Joana')
    sobrevivente = PessoaFisicaFactory(cpf=CPF, rg=None, nome_mae='Maria')

    _deduplicar()

    sobrevivente.refresh_from_db()
    assert (sobrevivente.rg, sobrevivente.nome_mae) == ('111', 'Maria')
    assert D.objects.get(pf_id=perdedora.pk, acao=D.CAMPO_DESCARTADO, campo='nome_mae').valor_original == 'Joana'


def test_par_unico_repetido_fica_uma_vez() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_par_telefone ON comum_pessoatelefone (pessoa_id, numero)')
    for pessoa in (perdedora, sobrevivente):
        PessoaTelefone.objects.create(pessoa=pessoa, numero='84999999999')

    _deduplicar()

    assert PessoaTelefone.objects.filter(pessoa=sobrevivente, numero='84999999999').count() == 1


def test_info_complementar_mantem_a_consulta_mais_recente() -> None:
    from comum.models import APIExterna

    api = APIExterna.objects.first() or pytest.skip('sem APIExterna no banco de teste')
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    antiga = PessoaInfoComplementar.objects.create(pessoa=sobrevivente, api_origem=api, informacoes={'v': 'antiga'})
    nova = PessoaInfoComplementar.objects.create(pessoa=perdedora, api_origem=api, informacoes={'v': 'nova'})

    _deduplicar()

    assert list(PessoaInfoComplementar.objects.filter(pessoa=sobrevivente).values_list('pk', flat=True)) == [nova.pk]
    assert not PessoaInfoComplementar.objects.filter(pk=antiga.pk).exists()


def test_referencia_fora_do_plano_marca_erro_sem_apagar() -> None:
    perdedora, _ = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    planejar()
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_ref (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')
        cursor.execute('INSERT INTO tmp_ref (pf) VALUES (%s)', [perdedora.pk])

    resumo = aplicar()

    assert resumo['erros'] == 1
    assert PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert D.objects.filter(acao=D.ERRO).exists()


def test_replanejar_depois_de_aplicar_preserva_o_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))
    _deduplicar()

    _deduplicar()  # o runbook manda replanejar para recuperar de `erro`

    separada.refresh_from_db()
    assert separada.documento_identificador == f'CONFLITO-{separada.pk}-{CPF}'


def test_aplicar_de_novo_nao_faz_nada() -> None:
    PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    _deduplicar()

    assert aplicar()['mescladas'] == 0
```

Se o `APIExterna` precisar de dados obrigatórios, crie-o no teste com os campos do model (`comum/models.py`, `class APIExterna`) em vez do `skip`.

- [ ] **Step 2: Rodar e ver falhar.** Expected: `ModuleNotFoundError: rh.deduplicacao.aplicacao`.

- [ ] **Step 3: Implementar `rh/deduplicacao/aplicacao.py`**

```python
"""Fase ``aplicar`` do deduplicar_pessoas: grava a higiene e mescla os grupos do plano, em lotes.

Set-based: por lote, um ``UPDATE … FROM dedup_mapa`` por referência. Antes de apagar as perdedoras,
o Collector confirma que nada além da própria PF/Pessoa seria apagado.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.models.deletion import Collector
from django.utils import timezone

from rh.deduplicacao.campos import campos_mesclaveis, resolver_campos
from rh.deduplicacao.documentos import chave_passaporte, eh_sintetico, formatar_cpf, formatar_passaporte
from rh.deduplicacao.referencias import Referencia, ReferenciaGenerica, referencias, referencias_genericas
from rh.models import DeduplicacaoPessoa as D
from rh.models import Pessoa, PessoaFisica, PessoaInfoComplementar

ORDEM_HIGIENE = [D.CPF_ANULADO, D.PAIS_PREENCHIDO, D.PASSAPORTE_PREENCHIDO, D.PASSAPORTE_ANULADO, D.SEPARADA, D.SINTETICO]


class ReferenciaRemanescente(Exception):
    """O DELETE da perdedora apagaria algo além da própria PF/Pessoa."""


def aplicar(lote: int = 1000) -> dict[str, int]:
    higiene = _aplicar_higiene()
    refs, genericas = referencias(), referencias_genericas()
    mescladas = erros = 0
    for grupos in _fatias(_grupos_pendentes(), lote):
        try:
            with transaction.atomic():
                _mesclar(grupos, refs, genericas)
            mescladas += len(grupos)
        except (DatabaseError, ReferenciaRemanescente, ValidationError):
            ok, falhas = _mesclar_um_a_um(grupos, refs, genericas)
            mescladas, erros = mescladas + ok, erros + falhas
    return {'higiene': higiene, 'mescladas': mescladas, 'erros': erros}


def _mesclar_um_a_um(grupos: dict[int, list[int]], refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> tuple[int, int]:
    ok = falhas = 0
    for sobrevivente, perdedoras in grupos.items():
        try:
            with transaction.atomic():
                _mesclar({sobrevivente: perdedoras}, refs, genericas)
            ok += 1
        except (DatabaseError, ReferenciaRemanescente, ValidationError) as erro:
            D.objects.create(pf_id=sobrevivente, sobrevivente_id=sobrevivente, acao=D.ERRO, motivo=str(erro)[:2000])
            falhas += 1
    return ok, falhas


def _aplicar_higiene() -> int:
    total = 0
    with transaction.atomic():
        for acao in ORDEM_HIGIENE:
            pendentes = D.objects.filter(acao=acao, aplicado_em__isnull=True)
            for linha in pendentes.iterator(chunk_size=2000):
                PessoaFisica.objects.filter(pk=linha.pf_id).update(**_alteracao_de_higiene(linha))
                total += 1
            pendentes.update(aplicado_em=timezone.now())
        _normalizar_documentos()
    return total


def _alteracao_de_higiene(linha: D) -> dict[str, str | int | None]:
    if linha.acao == D.CPF_ANULADO:
        return {'cpf': None}
    if linha.acao == D.PAIS_PREENCHIDO:
        return {'pais_origem_id': int(linha.documento)}
    if linha.acao == D.PASSAPORTE_ANULADO:
        return {'passaporte': None}
    if linha.acao == D.PASSAPORTE_PREENCHIDO:
        return {'passaporte': linha.documento}
    if linha.acao == D.SEPARADA:
        return {linha.campo: None, 'documento_identificador': linha.documento}
    return {'documento_identificador': linha.documento}


def _normalizar_documentos() -> None:
    """Formata CPF/passaporte e recalcula documento_identificador (mesma regra do PessoaFisica.save)."""
    from comum.models import Pais

    codigos = dict(Pais.objects.values_list('pk', 'codigo'))
    alteradas = []
    linhas = PessoaFisica.objects.values_list('pk', 'cpf', 'passaporte', 'pais_origem_id', 'documento_identificador')
    for pk, cpf, passaporte, pais_id, documento in linhas.iterator(chunk_size=5000):
        novo_cpf, novo_passaporte = formatar_cpf(cpf), formatar_passaporte(passaporte)
        chave = novo_cpf or chave_passaporte(novo_passaporte, codigos.get(pais_id))
        novo_documento = chave or (documento if eh_sintetico(documento) else None)
        if (novo_cpf, novo_passaporte, novo_documento) != (cpf, passaporte, documento):
            alteradas.append(PessoaFisica(pk=pk, cpf=novo_cpf, passaporte=novo_passaporte, documento_identificador=novo_documento))
    PessoaFisica.objects.bulk_update(alteradas, ['cpf', 'passaporte', 'documento_identificador'], batch_size=2000)


def _grupos_pendentes() -> dict[int, list[int]]:
    grupos: dict[int, list[int]] = defaultdict(list)
    for pf_id, sobrevivente in D.objects.filter(acao=D.MESCLADA, aplicado_em__isnull=True).values_list('pf_id', 'sobrevivente_id'):
        grupos[sobrevivente].append(pf_id)
    return grupos


def _fatias(grupos: dict[int, list[int]], tamanho: int) -> Iterator[dict[int, list[int]]]:
    itens = list(grupos.items())
    for inicio in range(0, len(itens), tamanho):
        yield dict(itens[inicio : inicio + tamanho])


def _mesclar(grupos: dict[int, list[int]], refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> None:
    pares = [(perdedora, sobrevivente) for sobrevivente, perdedoras in grupos.items() for perdedora in perdedoras]
    with connection.cursor() as cursor:
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')  # FKs deferidas falham aqui, não no COMMIT
        cursor.execute('DROP TABLE IF EXISTS pg_temp.dedup_mapa')
        cursor.execute('CREATE TEMP TABLE dedup_mapa (perdedora integer PRIMARY KEY, sobrevivente integer NOT NULL) ON COMMIT DROP')
        cursor.executemany('INSERT INTO dedup_mapa VALUES (%s, %s)', pares)
        _manter_info_complementar_recente(cursor)
        for ref in refs:
            _reapontar(cursor, ref)
        tipos = [ContentType.objects.get_for_model(PessoaFisica).pk, ContentType.objects.get_for_model(Pessoa).pk]
        for generica in genericas:
            _reapontar_generica(cursor, generica, tipos)
    _preencher_sobreviventes(grupos)
    _apagar_perdedoras([perdedora for perdedora, _ in pares])
    D.objects.filter(sobrevivente_id__in=list(grupos), acao__in=[D.MESCLADA, D.CAMPO_DESCARTADO], aplicado_em__isnull=True).update(
        aplicado_em=timezone.now()
    )


def _manter_info_complementar_recente(cursor) -> None:
    meta, q = PessoaInfoComplementar._meta, connection.ops.quote_name
    tabela, pessoa, api = q(meta.db_table), q(meta.get_field('pessoa').column), q(meta.get_field('api_origem').column)
    cursor.execute(
        f"""DELETE FROM {tabela} x USING (
            SELECT i.id, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(m.sobrevivente, i.{pessoa}), i.{api} ORDER BY i.data_hora_consulta DESC NULLS LAST, i.id DESC
            ) AS ordem
            FROM {tabela} i LEFT JOIN dedup_mapa m ON m.perdedora = i.{pessoa}
            WHERE i.{pessoa} IN (SELECT perdedora FROM dedup_mapa UNION SELECT sobrevivente FROM dedup_mapa)
        ) d WHERE x.id = d.id AND d.ordem > 1"""
    )


def _reapontar(cursor, ref: Referencia) -> None:
    q = connection.ops.quote_name
    tabela, coluna, pk = q(ref.tabela), q(ref.coluna), q(ref.pk)
    for unicidade in ref.compostas:
        outras = ', '.join(f'r.{q(c)}' for c in unicidade if c != ref.coluna)
        cursor.execute(
            f"""DELETE FROM {tabela} x USING (
                SELECT r.{pk} AS id, ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(m.sobrevivente, r.{coluna}), {outras} ORDER BY (m.perdedora IS NULL) DESC, r.{pk}
                ) AS ordem
                FROM {tabela} r LEFT JOIN dedup_mapa m ON m.perdedora = r.{coluna}
                WHERE r.{coluna} IN (SELECT perdedora FROM dedup_mapa UNION SELECT sobrevivente FROM dedup_mapa)
            ) d WHERE x.{pk} = d.id AND d.ordem > 1"""
        )
    cursor.execute(f'UPDATE {tabela} SET {coluna} = m.sobrevivente FROM dedup_mapa m WHERE {tabela}.{coluna} = m.perdedora')


def _reapontar_generica(cursor, ref: ReferenciaGenerica, tipos: list[int]) -> None:
    q = connection.ops.quote_name
    tabela, tipo, objeto = q(ref.tabela), q(ref.coluna_tipo), q(ref.coluna_id)
    cast = '::text' if ref.id_texto else ''
    cursor.execute(
        f'UPDATE {tabela} SET {objeto} = m.sobrevivente{cast} FROM dedup_mapa m '
        f'WHERE {tabela}.{tipo} = ANY(%s) AND {tabela}.{objeto} = m.perdedora{cast}',
        [tipos],
    )


def _preencher_sobreviventes(grupos: dict[int, list[int]]) -> None:
    campos = campos_mesclaveis()
    pks = [*grupos, *(pk for perdedoras in grupos.values() for pk in perdedoras)]
    valores = {v['pk']: v for v in PessoaFisica.objects.filter(pk__in=pks).values('pk', *campos)}
    for sobrevivente, perdedoras in grupos.items():
        preenchimentos, _ = resolver_campos(valores[sobrevivente], [valores[pk] for pk in perdedoras])
        pessoa = PessoaFisica.objects.get(pk=sobrevivente)
        for campo, valor in preenchimentos.items():
            setattr(pessoa, campo, valor)
        # ponytail: save() por sobrevivente recalcula eh_* e a busca (~20 queries); trocar por UPDATE em lote se o ensaio estourar a janela
        pessoa.save()


def _apagar_perdedoras(pks: list[int]) -> None:
    perdedoras = PessoaFisica.objects.filter(pk__in=pks)
    coletor = Collector(using=perdedoras.db)
    coletor.collect(perdedoras)
    proprios = {PessoaFisica, Pessoa}
    alheios = {modelo for modelo, objetos in coletor.data.items() if objetos and modelo not in proprios}
    alheios |= {qs.model for qs in coletor.fast_deletes if qs.model not in proprios and qs.exists()}
    alheios |= {campo.model for campo, _valor in coletor.field_updates}
    if alheios:
        raise ReferenciaRemanescente('O DELETE apagaria: ' + ', '.join(sorted(m._meta.label for m in alheios)))
    perdedoras.delete()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `… uv run pytest -q rh/tests/tasks/test_deduplicar_pessoas.py --reuse-db`
Expected: verde.

Se `coletor.field_updates` tiver outro formato na versão instalada do Django, confira em `.venv/lib/python3.14/site-packages/django/db/models/deletion.py` (`self.field_updates`) e ajuste a desestruturação.

- [ ] **Step 5: Commit**

```bash
git add rh/deduplicacao/aplicacao.py rh/tests/tasks/test_deduplicar_pessoas.py
git commit -m "[rh] Fase aplicar da deduplicação de pessoas"
```

### Task 12: Relatório e comando `deduplicar_pessoas`

**Files:**
- Create: `rh/deduplicacao/relatorio.py`
- Create: `rh/management/commands/deduplicar_pessoas.py`
- Test: `rh/tests/tasks/test_comando_deduplicar_pessoas.py`

**Interfaces:**
- Produces:
  - `resumo() -> dict[str, int]`;
  - `exportar_csv(caminho: Path) -> int`;
  - o comando `deduplicar_pessoas {planejar,relatorio,aplicar} [--csv PATH] [--lote N]`.

- [ ] **Step 1: Testes**

```python
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa')


def test_planejar_relatorio_aplicar(tmp_path: Path) -> None:
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')
    saida = StringIO()

    call_command('deduplicar_pessoas', 'planejar', stdout=saida)
    call_command('deduplicar_pessoas', 'relatorio', '--csv', str(tmp_path / 'plano.csv'), stdout=saida)
    call_command('deduplicar_pessoas', 'aplicar', stdout=saida)

    assert 'mesclada: 1' in saida.getvalue()
    assert (tmp_path / 'plano.csv').read_text().startswith('id,pf_id,sobrevivente_id,documento,acao')
    assert 'mescladas: 1' in saida.getvalue()


def test_relatorio_recusa_csv_dentro_do_media(settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)

    with pytest.raises(CommandError):
        call_command('deduplicar_pessoas', 'relatorio', '--csv', str(tmp_path / 'plano.csv'))
```

- [ ] **Step 2: Rodar e ver falhar.** Expected: `Unknown command: 'deduplicar_pessoas'`.

- [ ] **Step 3: `rh/deduplicacao/relatorio.py`**

```python
"""Relatório do plano/auditoria da deduplicação. O CSV contém CPF: é dado pessoal (LGPD)."""

from __future__ import annotations

import csv
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError
from django.db.models import Count

from rh.models import DeduplicacaoPessoa

COLUNAS = ['id', 'pf_id', 'sobrevivente_id', 'documento', 'acao', 'campo', 'valor_original', 'motivo', 'criado_em', 'aplicado_em']


def resumo() -> dict[str, int]:
    linhas = DeduplicacaoPessoa.objects.values('acao', 'aplicado_em__isnull').annotate(total=Count('id'))
    return {f"{linha['acao']} ({'pendente' if linha['aplicado_em__isnull'] else 'aplicada'})": linha['total'] for linha in linhas}


def exportar_csv(caminho: Path) -> int:
    if caminho.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
        raise CommandError('O CSV tem CPF (dado pessoal): grave fora do MEDIA_ROOT.')
    total = 0
    with caminho.open('w', newline='', encoding='utf-8') as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(COLUNAS)
        for linha in DeduplicacaoPessoa.objects.order_by('pk').values_list(*COLUNAS).iterator(chunk_size=5000):
            escritor.writerow(linha)
            total += 1
    return total
```

- [ ] **Step 4: `rh/management/commands/deduplicar_pessoas.py`**

```python
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Deduplica PessoaFisica por documento (CPF/passaporte): planejar → relatorio → aplicar. Ver docs/operacoes/deduplicar-pessoas.md.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('etapa', choices=['planejar', 'relatorio', 'aplicar'])
        parser.add_argument('--csv', type=Path, help='relatorio: grava as linhas do plano/auditoria neste CSV (contém CPF).')
        parser.add_argument('--lote', type=int, default=1000, help='aplicar: grupos por transação.')

    def handle(self, *args: Any, etapa: str, csv: Path | None = None, lote: int = 1000, **options: Any) -> None:
        from rh.deduplicacao import relatorio
        from rh.deduplicacao.aplicacao import aplicar
        from rh.deduplicacao.plano import planejar

        if etapa == 'planejar':
            totais = planejar()
        elif etapa == 'aplicar':
            totais = aplicar(lote=lote)
        else:
            totais = relatorio.resumo()
            if csv:
                self.stdout.write(f'Atenção: {csv} contém CPF (dado pessoal).')
                totais['linhas no CSV'] = relatorio.exportar_csv(csv)
        for chave, total in sorted(totais.items()):
            self.stdout.write(f'{chave}: {total}')
```

- [ ] **Step 5: Rodar e ver passar.** Mesmo comando. Expected: verde.

- [ ] **Step 6: Commit**

```bash
git add rh/deduplicacao/relatorio.py rh/management/commands/deduplicar_pessoas.py rh/tests/tasks/test_comando_deduplicar_pessoas.py
git commit -m "[rh] Comando deduplicar_pessoas"
```

### Task 13: Runbook e atualização do spec

**Files:**
- Create: `docs/operacoes/deduplicar-pessoas.md`
- Modify: `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`

- [ ] **Step 1: Runbook**

`docs/operacoes/deduplicar-pessoas.md`, em pt-BR, contendo:
- **Pré-requisito:** Release 1 instalada (MR 1 e MR 2).
- **Passos:**
  1. Backup (`pg_dump -Fc`), que inclui as colunas fantasmas apagadas pela Release 1.
  2. `python manage.py migrate`.
  3. `python manage.py deduplicar_pessoas planejar`. Se abortar com "FKs para pessoa que o ORM não conhece", a instituição remove ou trata cada `tabela.coluna` listada (no IFRN: `financeiro_empenho`, `temp_rh_resposta`, `temp_enquete_cnat_resposta`) e repete.
  4. `python manage.py deduplicar_pessoas relatorio --csv /caminho/fora/do/media/plano.csv` e revisão. O CSV é dado pessoal: guardar com acesso restrito e apagar após a revisão.
  5. `python manage.py deduplicar_pessoas aplicar` em janela (lote padrão 1000; `--lote` menor reduz o tempo de lock).
  6. `python manage.py deduplicar_pessoas relatorio` deve mostrar zero pendentes e zero `erro`. Se houver `erro`, ler o `motivo` no CSV, corrigir e voltar ao passo 3 (o `planejar` refaz só o que não foi aplicado).
  7. Só então atualizar para a Release 2.
- **Tabela das ações** (`cpf_anulado`, `passaporte_anulado`, `passaporte_preenchido`, `pais_preenchido`, `sintetico`, `mesclada`, `separada`, `campo_descartado`, `divergencia_entrada`, `erro`), com o que cada uma significa.
- **Como corrigir uma PF `CONFLITO-…`:** informar o CPF certo na tela da pessoa; o `save()` troca o sintético pelo documento.

- [ ] **Step 2: Spec**

No spec, seção 2, acrescentar `passaporte_preenchido` e `pais_preenchido` à lista de ações. Na seção 3, registrar estas decisões tomadas no plano:
- dependente SIAPE usa `PREENCHER`; minicurso e PROITEC conforme a resposta do usuário (ver Global Constraints);
- `PessoaExterna` existente não empurra nada para a PF;
- o `save()` deixa de copiar o passaporte do aluno (o legado é coberto pela ação `passaporte_preenchido`);
- o `planejar` preserva o sintético já gravado (`CONFLITO-`/`INVALIDO-`) ao ser rodado de novo;
- a assinatura passa a ser `obter_ou_criar(dados, politica) -> (pf, criada)`, com `cpf`/`passaporte` dentro de `dados`;
- `aplicar_politica` também vale para os ramos de **atualização** (SIAPE, prestador, importações);
- na matrícula, a recusa sai em `clean_data_nascimento`, porque é ali que o formulário tem CPF e data juntos.

- [ ] **Step 3: Commit**

```bash
git add docs/operacoes/deduplicar-pessoas.md docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md
git commit -m "[rh] Runbook da deduplicação de pessoas"
```

### Task 14: Suíte completa, ensaio e MR

- [ ] **Step 1: Suíte unitária inteira**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -n 3 -q -m "not e2e and not doc" --maxfail=100000 --create-db`
Expected: mesmo resultado do master (compare com uma rodada no master se houver falha preexistente).

- [ ] **Step 2: Seeds, bootstrap e e2e (o `save()` novo é global)**

Varredura de criação de PF sem documento fora da suíte unitária:

Run: `grep -rnE "baker\.make\((Servidor|PessoaFisica|PrestadorServico|Aluno)|PessoaFisica(\.objects)?\.(create|get_or_create)\(" --include='*.py' djtools/new_tests */features/steps */tests/e2e tests/e2e djtools/e2e_fixtures.py comum/management rh/management */management/commands/gerar_banco_mock*.py 2>/dev/null`
Expected: cada ocorrência passa CPF (`cpf=`/`pessoa_fisica__cpf=` com `cpf_valido(n)`) ou usa `obter_ou_criar`. Corrija as que não passam.

Run: `python manage.py sync` num banco novo (o bootstrap de instituição nova) e `python manage.py gerar_banco_mock`.
Expected: sem `ValidationError: Informe o CPF ou o passaporte`.

Run: `SUAP_CHECK=e2e SUAP_APPS=geral python manage.py suap_check`
Expected: verde.

- [ ] **Step 3: Ensaio num snapshot restaurado de produção**

Com o MR 1 aplicado e as `temp_*`/`financeiro_empenho` removidas manualmente na cópia:

```bash
time python manage.py deduplicar_pessoas planejar
python manage.py deduplicar_pessoas relatorio --csv /tmp/plano.csv
time python manage.py deduplicar_pessoas aplicar
python manage.py deduplicar_pessoas relatorio
```

Expected:
- números na ordem dos do spec: cerca de 105 mil grupos, cerca de 243 mil PFs mescladas, cerca de 840 separações por nascimento, cerca de 26,8 mil `cpf_anulado`, cerca de 30 mil `pais_preenchido` e cerca de 19,5 mil sem documento e sem país (sintéticos isentos da CHECK);
- zero pendentes e zero `erro` ao final;
- tempo total registrado no MR.

Smoke com pessoas mescladas, que a suíte unitária nunca exercita (as factories criam uma PF por papel): na mesma cópia, escolher de 20 a 50 usuários cuja PF ficou com servidor e aluno, ou prestador e aluno, por exemplo:

```sql
SELECT v.user_id FROM comum_vinculo v JOIN pessoa_fisica pf ON pf.pessoa_ptr_id = v.pessoa_id
WHERE pf.eh_servidor AND pf.eh_aluno LIMIT 50;
```

Para cada um, logar (`client.force_login`, num `manage.py shell` contra a cópia) e fazer GET em `/`, no perfil (`/rh/servidor/<matricula>/` ou `/edu/aluno/<matricula>/`) e no início de `edu`, `saude` e `ae`. Expected: nenhum 500. Cada 500 vira correção neste MR (o padrão é pegar aluno/vínculo pelo usuário ou pelo papel, nunca pela PF).

Depois rodar a query de duplicatas:

```sql
SELECT count(*) FROM (SELECT documento_identificador FROM pessoa_fisica GROUP BY 1 HAVING count(*) > 1) g;
SELECT count(*) FROM pessoa_fisica WHERE documento_identificador IS NULL;
```

Expected: `0` e `0`.

- [ ] **Step 4: Gate de CI e MR**

Run: `pre-commit run --from-ref origin/master --to-ref HEAD`.

```bash
git push -u origin HEAD
REGISTRAR_TEMPO=True glab mr create --title "[rh] Comando deduplicar_pessoas e criação única de pessoa física" --description "<seguir a skill mr-format: Sumário, Problema, Alterações, Refs (spec + plano + MR 1 + cosinf/suap#17640), Revisores, Changelog; registrar o tempo do ensaio>"
```
