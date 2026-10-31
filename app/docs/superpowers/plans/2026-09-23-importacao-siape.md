# Importação SIAPE paralela — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela no `rh` para enviar o zip do extrator SIAPE, ver os arquivos identificados, escolher o que importar e acompanhar em tempo real uma execução paralela que respeita as precedências; o comando/beat `importar_siape` passa a usar o mesmo motor.

**Architecture:** Pacote novo `rh/importacao_siape/` com unidades pequenas: `layouts` (grafo de precedência, puro), `identificacao` (REF → layout + diagnóstico, puro), `agendador` (executa um grafo num `ThreadPoolExecutor`, puro), `progresso` (lista que conta iteração + handler de log por thread), `preparacao` (zip → storage + registros), `execucao` (liga tudo ao `ImportadorSIAPE` e aos models), `views`/`forms`. Três models novos no `rh`. As 33 funções `importar_*` do `ImportadorSIAPE` não mudam.

**Tech Stack:** Django 5.2, `djtools.db.models`, `concurrent.futures`, `logging`, `@task` de `djtools.assincrono`, pytest + factory_boy, JS puro com `fetch` (polling).

**Spec:** `docs/superpowers/specs/2026-09-23-importacao-siape-design.md`

## Global Constraints

- Tudo em pt-BR (identificadores, mensagens, commits). Ruff: linha 150, aspas simples.
- Complexidade ciclomática ≤ 10 por função tocada (hook bloqueia). Tipar parâmetros e retorno das defs tocadas (`from __future__ import annotations`, `X | None`, `collections.abc`).
- Models herdam `djtools.db.models.ModelPlus` (`from djtools.db import models`).
- Permissão de todas as telas: `rh.pode_gerenciar_extracao_siape`.
- Workers: `Configuracao` `rh`/`importacao_siape_workers`, padrão **4**; `1` executa em série na thread atual (sem pool).
- Pasta de cada importação: `rh/arquivos_siape/importacoes/<id>/` (apagada ao fim da execução). A pasta legada `rh/arquivos_siape/` só é lida pelo comando.
- Só uma `ImportacaoSiape` com situação `executando` por vez.
- Polling a cada 2 s. Templates seguem `docs/design-system.md` (`{% box %}`, tabela com `<caption>` dentro de `div.table-responsive`, `span.status`, `{% progressbar %}`, sem `style=""`, sem cor hardcoded).
- Testes: factories, não `suap_data`; mínimo nas funcionalidades principais; nada de teste de helper trivial. Testes que executam importação com banco usam a fixture `importacao_serial` (workers = 1): threads abrem outra conexão e não enxergam a transação do teste.
- Commits sem trailer de atribuição (sem `Co-Authored-By`/`Claude-Session`).
- Desvios deliberados da spec: `ImportacaoSiape.arquivo` guarda o **nome** do zip (os pares extraídos ficam em `pasta`; o zip não é mantido) e não há FK para `djtools.Task` — a página acompanha o próprio model. `ImportacaoSiape.situacao` usa `falhou` só para erro fora dos layouts.
- Banco de teste: Postgres descartável na porta **5434** (`DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --reuse-db ...`; na primeira vez `--create-db`). Abaixo, `PYTEST` abrevia esse prefixo.

## Review Focus

1. **Layout lido duas vezes** (`importar_cargo_emprego`, `importar_uo`) ou reatribuído (`importar_pca`): o progresso não pode voltar nem passar de 100 % — coberto no teste de `ItensComProgresso` (Task 4).
2. **Seleção parcial que pula um layout intermediário** (ex.: `afastamentos` + `servidorafastamentos` sem `servidor1`): o dependente não pode rodar em paralelo com a tabela da qual depende transitivamente — coberto em `dependencias_efetivas` (Task 1).
3. **Zip que não é zip, ou zip sem par REF/TXT**: erro no formulário, nada criado — coberto no teste de views (Task 8).
4. **Duas importações disparadas ao mesmo tempo** (tela + beat): a segunda é recusada — coberto em `iniciar_importacao` (Task 6) e no comando (Task 7).
5. **Warning emitido por outra thread** enquanto um layout roda: não pode virar ocorrência do layout errado — coberto no teste do handler (Task 4).

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `rh/importacao_siape/__init__.py` | pacote (vazio) |
| `rh/importacao_siape/layouts.py` | `LAYOUTS`, `ordem_topologica`, `dependencias_efetivas`, `dependencias_transitivas` |
| `rh/importacao_siape/identificacao.py` | `carregar_refs`, `identificar` → `Identificacao` |
| `rh/importacao_siape/agendador.py` | `executar_grafo` (série ou pool) → `Resultado` |
| `rh/importacao_siape/progresso.py` | `ItensComProgresso`, `CapturaOcorrencias`, `capturando_ocorrencias` |
| `rh/importacao_siape/preparacao.py` | `criar_importacao`, `ArquivoExtratorInvalido` |
| `rh/importacao_siape/execucao.py` | `iniciar_importacao`, `executar_importacao`, `workers_configurados`, `ImportacaoNaoIniciada` |
| `rh/importacao_siape/forms.py` | `ImportacaoSiapeUploadForm` |
| `rh/importacao_siape/views.py` | 4 views (lista/upload, detalhe/disparo, progresso JSON, ocorrências) |
| `rh/models/importacao/__init__.py`, `rh/models/importacao/importacao_siape.py` | 3 models + choices |
| `rh/models/__init__.py` | + `from .importacao import *` |
| `rh/migrations/XXXX_importacao_siape.py` | gerada |
| `rh/importador.py` | `ordem` derivada de `ordem_topologica()` |
| `rh/tasks.py` | `executar_importacao_siape` |
| `rh/management/commands/importar_siape.py` | usa o motor |
| `rh/forms.py` | campo `importacao_siape_workers` no `ConfiguracaoForm` |
| `rh/urls.py`, `rh/menu.yaml` | rotas e menu |
| `rh/templates/importacao_siape_lista.html`, `importacao_siape_detalhe.html`, `importacao_siape_ocorrencias.html` | telas |
| `rh/static/rh/js/importacao_siape.js` | marcação de dependências + polling |
| `rh/tests/siape.py` | + `zip_do_extrator()` |
| `rh/tests/conftest.py` | + fixture `importacao_serial` |
| testes | ver cada task |

---

### Task 1: Grafo de precedência (`layouts.py`) e `ordem` do importador

**Files:**
- Create: `rh/importacao_siape/__init__.py` (vazio), `rh/importacao_siape/layouts.py`
- Modify: `rh/importador.py:91-126` (a lista `ordem`)
- Test: `rh/tests/models/test_importacao_siape_layouts.py`

**Interfaces:**
- Produces:
  - `Layout(nome: str, grupo: str, dependencias: tuple[str, ...] = (), ativo: bool = True, motivo_inativo: str = '')` (dataclass frozen)
  - `LAYOUTS: dict[str, Layout]`; constantes `GRUPO_TABELAS`, `GRUPO_NUCLEO`, `GRUPO_HISTORICOS`
  - `ordem_topologica(apenas_ativos: bool = True) -> list[str]` (levanta `ValueError` em ciclo)
  - `dependencias_efetivas(nome: str, selecionados: Collection[str]) -> set[str]`
  - `dependencias_transitivas(nome: str) -> set[str]`

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Grafo de precedência dos layouts do extrator SIAPE."""

from rh.importacao_siape.layouts import LAYOUTS, dependencias_efetivas, ordem_topologica


def test_ordem_topologica_respeita_as_dependencias_e_omite_inativos():
    ordem = ordem_topologica()

    for nome in ordem:
        for dependencia in LAYOUTS[nome].dependencias:
            if LAYOUTS[dependencia].ativo:
                assert ordem.index(dependencia) < ordem.index(nome), f'{dependencia} deveria vir antes de {nome}'
    assert 'historico_afastamento' not in ordem
    assert set(ordem) == {nome for nome, layout in LAYOUTS.items() if layout.ativo}


def test_dependencia_efetiva_atravessa_layout_nao_selecionado():
    # servidorafastamentos -> ... -> servidor1 -> afastamentos: sem o núcleo selecionado,
    # a tabela ainda precisa terminar antes.
    assert dependencias_efetivas('servidorafastamentos', {'afastamentos', 'servidorafastamentos'}) == {'afastamentos'}
    assert dependencias_efetivas('servidorafastamentos', {'servidorafastamentos'}) == set()
    assert dependencias_efetivas('servidor3', {'servidor1', 'servidor2', 'servidor3'}) == {'servidor2'}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST rh/tests/models/test_importacao_siape_layouts.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'rh.importacao_siape'`.

- [ ] **Step 3: Implementar `rh/importacao_siape/layouts.py`**

```python
"""Layouts do extrator SIAPE e as precedências entre eles.

Fonte única da ordem de importação: `ImportadorSIAPE.ordem` e o motor paralelo derivam daqui.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

GRUPO_TABELAS = 'Tabelas'
GRUPO_NUCLEO = 'Núcleo do servidor'
GRUPO_HISTORICOS = 'Históricos'


@dataclass(frozen=True)
class Layout:
    nome: str
    grupo: str
    dependencias: tuple[str, ...] = ()
    ativo: bool = True
    motivo_inativo: str = ''


_TABELAS = (
    'atividades',
    'afastamentos',
    'bancos',
    'grupo_cargo_emprego',
    'cargo_classe',
    'diploma_legal',
    'funcoes',
    'jornada_trabalho',
    'nivel_escolaridade',
    'pais',
    'regime_juridico',
    'rubrica',
    'estado_civil',
    'grupo_ocorrencia',
    'situacao_servidor',
    'uo',
    'titulacoes',
)
_TABELAS_DEPENDENTES = {'cargo_emprego': ('grupo_cargo_emprego',), 'ocorrencia': ('grupo_ocorrencia',)}
# servidor2..4 gravam pelo save() da linha inteira do servidor: rodam encadeados
_NUCLEO = (
    ('servidor1', (*_TABELAS, *_TABELAS_DEPENDENTES)),
    ('servidor2', ('servidor1',)),
    ('servidor3', ('servidor2',)),
    ('servidor4', ('servidor3',)),
    ('servidor5', ('servidor4',)),
    ('email_telefone_servidor', ('servidor4',)),
)
_FIM_DO_NUCLEO = ('servidor5', 'email_telefone_servidor')
_HISTORICOS = ('servidorafastamentos', 'historico_funcao', 'historico_setor_siape', 'servidor_matriculas', 'historico_ferias', 'pca')


def _montar() -> dict[str, Layout]:
    layouts = [Layout(nome, GRUPO_TABELAS) for nome in _TABELAS]
    layouts += [Layout(nome, GRUPO_TABELAS, deps) for nome, deps in _TABELAS_DEPENDENTES.items()]
    layouts += [Layout(nome, GRUPO_NUCLEO, deps) for nome, deps in _NUCLEO]
    layouts += [Layout(nome, GRUPO_HISTORICOS, _FIM_DO_NUCLEO) for nome in _HISTORICOS]
    layouts += [
        Layout('ferias', GRUPO_HISTORICOS, ('historico_ferias',)),
        Layout('posicionamento_pca', GRUPO_HISTORICOS, ('pca',)),
        Layout(
            'historico_afastamento',
            GRUPO_HISTORICOS,
            _FIM_DO_NUCLEO,
            ativo=False,
            motivo_inativo='Substituído pela importação de servidorafastamentos.',
        ),
    ]
    return {layout.nome: layout for layout in layouts}


LAYOUTS = _montar()


def ordem_topologica(apenas_ativos: bool = True) -> list[str]:
    """Ordem serial válida (Kahn, estável pela ordem de declaração)."""
    nomes = [nome for nome, layout in LAYOUTS.items() if layout.ativo or not apenas_ativos]
    pendentes = {nome: {d for d in LAYOUTS[nome].dependencias if d in nomes} for nome in nomes}
    ordem: list[str] = []
    while pendentes:
        prontos = [nome for nome, deps in pendentes.items() if not deps]
        if not prontos:
            raise ValueError('Ciclo nas dependências dos layouts: ' + ', '.join(sorted(pendentes)))
        for nome in prontos:
            del pendentes[nome]
            ordem.append(nome)
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return ordem


def dependencias_efetivas(nome: str, selecionados: Collection[str]) -> set[str]:
    """Dependências de `nome` entre os selecionados, atravessando as não selecionadas."""
    efetivas: set[str] = set()
    visitar = list(LAYOUTS[nome].dependencias)
    vistos: set[str] = set()
    while visitar:
        dependencia = visitar.pop()
        if dependencia in vistos:
            continue
        vistos.add(dependencia)
        if dependencia in selecionados:
            efetivas.add(dependencia)
        else:
            visitar.extend(LAYOUTS[dependencia].dependencias)
    return efetivas


def dependencias_transitivas(nome: str) -> set[str]:
    """Todas as dependências diretas e indiretas (usado pela tela para marcar junto)."""
    todas: set[str] = set()
    visitar = list(LAYOUTS[nome].dependencias)
    while visitar:
        dependencia = visitar.pop()
        if dependencia not in todas:
            todas.add(dependencia)
            visitar.extend(LAYOUTS[dependencia].dependencias)
    return todas
```

- [ ] **Step 4: Trocar a lista `ordem` em `rh/importador.py`**

Em `ImportadorSIAPE.__init__`, substituir o `kwargs.setdefault('ordem', [ ... 33 nomes ... ])` por:

```python
        kwargs.setdefault('ordem', ordem_topologica())
```

e acrescentar no topo: `from rh.importacao_siape.layouts import ordem_topologica`.

- [ ] **Step 5: Rodar os testes novos e a regressão**

Run: `PYTEST rh/tests/models/test_importacao_siape_layouts.py rh/tests/models/test_importador.py comum/tests/tasks/test_importador.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add rh/importacao_siape rh/importador.py rh/tests/models/test_importacao_siape_layouts.py
git commit -m "[rh] Declarando as precedências dos layouts do extrator SIAPE num grafo"
```

---

### Task 2: Identificação com diagnóstico (`identificacao.py`)

**Files:**
- Create: `rh/importacao_siape/identificacao.py`
- Test: `rh/tests/models/test_importacao_siape_identificacao.py`

**Interfaces:**
- Produces:
  - `Identificacao(layout: str | None, diagnostico: str = '')` (dataclass frozen)
  - `PASTA_REFS: str` (`<BASE_DIR>/rh/refs`)
  - `carregar_refs(pasta: str = PASTA_REFS) -> dict[str, str]` (nome sem `.REF` → conteúdo)
  - `identificar(conteudo_ref: str, refs: Mapping[str, str]) -> Identificacao`

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Identificação do layout de um arquivo .REF do extrator."""

from rh.importacao_siape.identificacao import carregar_refs, identificar


def test_reconhece_ref_mesmo_com_espacos_diferentes():
    refs = carregar_refs()
    conteudo = refs['estado_civil'].replace('   ', '\t')

    assert identificar(conteudo, refs).layout == 'estado_civil'


def test_ref_alterado_aponta_o_layout_mais_proximo_e_os_campos_divergentes():
    refs = carregar_refs()
    alterado = refs['estado_civil'].replace('IT-NO-ESTADO-CIVIL', 'IT-DS-ESTADO-CIVIL')

    identificacao = identificar(alterado, refs)

    assert identificacao.layout is None
    assert 'estado_civil' in identificacao.diagnostico
    assert 'IT-DS-ESTADO-CIVIL' in identificacao.diagnostico
    assert 'IT-NO-ESTADO-CIVIL' in identificacao.diagnostico
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST rh/tests/models/test_importacao_siape_identificacao.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar**

```python
"""Identifica o layout de um arquivo do extrator comparando seu .REF com os de `rh/refs`.

O nome do arquivo (ex.: 676422.REF) não diz o que ele contém; o conteúdo do .REF, sim.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings

PASTA_REFS = os.path.join(settings.BASE_DIR, 'rh', 'refs')


@dataclass(frozen=True)
class Identificacao:
    layout: str | None
    diagnostico: str = ''


def carregar_refs(pasta: str = PASTA_REFS) -> dict[str, str]:
    refs = {}
    for nome in sorted(os.listdir(pasta)):
        if nome.endswith('.REF'):
            with open(os.path.join(pasta, nome), encoding='utf-8') as arquivo:
                refs[nome.removesuffix('.REF')] = arquivo.read()
    return refs


def identificar(conteudo_ref: str, refs: Mapping[str, str]) -> Identificacao:
    normalizado = _normalizar(conteudo_ref)
    for nome, conteudo in refs.items():
        if _normalizar(conteudo) == normalizado:
            return Identificacao(nome)
    return Identificacao(None, _diagnosticar(conteudo_ref, refs))


def _normalizar(conteudo: str) -> str:
    return ''.join(conteudo.split())


def _campos(conteudo: str) -> set[str]:
    return {linha.split()[0] for linha in conteudo.splitlines() if linha.strip()}


def _semelhanca(campos: set[str], outros: set[str]) -> float:
    return len(campos & outros) / len(campos | outros) if campos | outros else 0.0


def _diagnosticar(conteudo_ref: str, refs: Mapping[str, str]) -> str:
    campos = _campos(conteudo_ref)
    if not campos or not refs:
        return 'Arquivo de referência vazio ou sem layouts conhecidos para comparar.'
    mais_proximo = max(refs, key=lambda nome: _semelhanca(campos, _campos(refs[nome])))
    campos_ref = _campos(refs[mais_proximo])
    a_mais, a_menos = sorted(campos - campos_ref), sorted(campos_ref - campos)
    partes = [f'Layout mais próximo: {mais_proximo} ({_semelhanca(campos, campos_ref):.0%} dos campos em comum).']
    if a_mais:
        partes.append('Campos a mais: ' + ', '.join(a_mais) + '.')
    if a_menos:
        partes.append('Campos a menos: ' + ', '.join(a_menos) + '.')
    if not a_mais and not a_menos:
        partes.append('Mesmos campos, com tipo, tamanho ou ordem diferentes.')
    return ' '.join(partes)
```

- [ ] **Step 4: Rodar**

Run: `PYTEST rh/tests/models/test_importacao_siape_identificacao.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rh/importacao_siape/identificacao.py rh/tests/models/test_importacao_siape_identificacao.py
git commit -m "[rh] Identificando layouts do extrator com diagnóstico do layout mais próximo"
```

---

### Task 3: Agendador do grafo (`agendador.py`)

**Files:**
- Create: `rh/importacao_siape/agendador.py`
- Test: `rh/tests/models/test_importacao_siape_agendador.py`

**Interfaces:**
- Produces:
  - `Resultado` (dataclass): `concluidos: list[str]`, `falhos: dict[str, BaseException]`, `pulados: dict[str, str]` (nome → motivo)
  - `executar_grafo(dependencias: Mapping[str, Collection[str]], executar: Callable[[str], None], workers: int, ao_pular: Callable[[str, str], None] = _nada) -> Resultado`
  - Contrato: `dependencias` só referencia chaves do próprio mapa; `executar` sinaliza falha levantando exceção; `workers <= 1` roda em série na thread atual; ciclo → `ValueError`.

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Agendador que executa um grafo de dependências em paralelo."""

import threading
import time

import pytest

from rh.importacao_siape.agendador import executar_grafo

GRAFO = {'a': set(), 'b': set(), 'c': {'a'}, 'd': {'c'}, 'e': {'b'}}


@pytest.mark.parametrize('workers', [1, 3])
def test_respeita_precedencias_e_pula_dependentes_de_falha(workers):
    inicio, fim = {}, {}

    def executar(nome):
        inicio[nome] = time.monotonic()
        time.sleep(0.01)
        fim[nome] = time.monotonic()
        if nome == 'c':
            raise RuntimeError('quebrou')

    pulados = []
    resultado = executar_grafo(GRAFO, executar, workers, ao_pular=lambda nome, motivo: pulados.append(nome))

    assert set(resultado.concluidos) == {'a', 'b', 'e'}
    assert set(resultado.falhos) == {'c'}
    assert resultado.pulados == {'d': 'Dependência c não foi concluída.'}
    assert pulados == ['d']
    assert inicio['c'] >= fim['a'] and inicio['e'] >= fim['b']


def test_independentes_rodam_ao_mesmo_tempo():
    barreira = threading.Barrier(2, timeout=2)

    resultado = executar_grafo({'a': set(), 'b': set()}, lambda nome: barreira.wait(), workers=2)

    assert set(resultado.concluidos) == {'a', 'b'}
```

(O `Barrier` só libera se `a` e `b` estiverem em execução ao mesmo tempo; em série estouraria o timeout e os dois cairiam em `falhos`.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST rh/tests/models/test_importacao_siape_agendador.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar**

```python
"""Executa um grafo de dependências: em série (workers <= 1) ou num pool de threads."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field


@dataclass
class Resultado:
    concluidos: list[str] = field(default_factory=list)
    falhos: dict[str, BaseException] = field(default_factory=dict)
    pulados: dict[str, str] = field(default_factory=dict)


def _nada(nome: str, motivo: str) -> None:
    return None


def executar_grafo(
    dependencias: Mapping[str, Collection[str]],
    executar: Callable[[str], None],
    workers: int,
    ao_pular: Callable[[str, str], None] = _nada,
) -> Resultado:
    pendentes = {nome: set(deps) for nome, deps in dependencias.items()}
    resultado = Resultado()
    if workers <= 1:
        _em_serie(pendentes, executar, ao_pular, resultado)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='importacao_siape') as pool:
            _em_paralelo(pendentes, executar, ao_pular, resultado, pool)
    return resultado


def _prontos(pendentes: dict[str, set[str]]) -> list[str]:
    prontos = [nome for nome, deps in pendentes.items() if not deps]
    for nome in prontos:
        del pendentes[nome]
    return prontos


def _erro_de_ciclo(pendentes: dict[str, set[str]]) -> ValueError:
    return ValueError('Ciclo ou dependência inexistente no grafo: ' + ', '.join(sorted(pendentes)))


def _em_serie(pendentes, executar, ao_pular, resultado: Resultado) -> None:
    while pendentes:
        prontos = _prontos(pendentes)
        if not prontos:
            raise _erro_de_ciclo(pendentes)
        for nome in prontos:
            try:
                executar(nome)
            except Exception as erro:
                _registrar(nome, erro, pendentes, ao_pular, resultado)
            else:
                _registrar(nome, None, pendentes, ao_pular, resultado)


def _em_paralelo(pendentes, executar, ao_pular, resultado: Resultado, pool: ThreadPoolExecutor) -> None:
    em_execucao: dict[Future, str] = {}
    while pendentes or em_execucao:
        for nome in _prontos(pendentes):
            em_execucao[pool.submit(executar, nome)] = nome
        if not em_execucao:
            raise _erro_de_ciclo(pendentes)
        feitos, _ = wait(em_execucao, return_when=FIRST_COMPLETED)
        for futuro in feitos:
            _registrar(em_execucao.pop(futuro), futuro.exception(), pendentes, ao_pular, resultado)


def _registrar(nome: str, erro: BaseException | None, pendentes, ao_pular, resultado: Resultado) -> None:
    if erro is None:
        resultado.concluidos.append(nome)
        for deps in pendentes.values():
            deps.discard(nome)
        return
    resultado.falhos[nome] = erro
    _pular_dependentes(nome, pendentes, ao_pular, resultado)


def _pular_dependentes(nome: str, pendentes: dict[str, set[str]], ao_pular, resultado: Resultado) -> None:
    for dependente in [n for n, deps in pendentes.items() if nome in deps]:
        if dependente not in pendentes:
            continue
        del pendentes[dependente]
        motivo = f'Dependência {nome} não foi concluída.'
        resultado.pulados[dependente] = motivo
        ao_pular(dependente, motivo)
        _pular_dependentes(dependente, pendentes, ao_pular, resultado)
```

Obs.: no teste parametrizado, `d` depende só de `c`; o motivo registrado é o do pai direto. Um dependente de um *pulado* recebe motivo com o nome do pulado — é o esperado.

- [ ] **Step 4: Rodar**

Run: `PYTEST rh/tests/models/test_importacao_siape_agendador.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add rh/importacao_siape/agendador.py rh/tests/models/test_importacao_siape_agendador.py
git commit -m "[rh] Agendador paralelo do grafo de layouts do extrator SIAPE"
```

---

### Task 4: Progresso e captura de ocorrências (`progresso.py`)

**Files:**
- Create: `rh/importacao_siape/progresso.py`
- Test: `rh/tests/models/test_importacao_siape_progresso.py`

**Interfaces:**
- Produces:
  - `ItensComProgresso(itens: Iterable[dict], ao_avancar: Callable[[int], None], passo: int | None = None)` — subclasse de `list`; atributo `posicao: int` (índice 1-based do item corrente); chama `ao_avancar(n)` a cada `passo` itens (padrão ≈2 %) e ao fim, **nunca com valor menor que o último reportado** e nunca acima de `len(self)`.
  - `CapturaOcorrencias(logging.Handler)` e `capturando_ocorrencias(registrar: Callable[[str, int | None, str], None], itens: ItensComProgresso | None = None, logger: str = 'rh.importador') -> ContextManager` — só registros `>= WARNING` emitidos **pela thread que abriu o contexto**; `registrar(nivel, linha, mensagem)` com `nivel` em minúsculas (`'warning'`, `'error'`, `'critical'`).

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Contagem de progresso e captura de ocorrências de um layout em execução."""

import logging
import threading

from rh.importacao_siape.progresso import ItensComProgresso, capturando_ocorrencias

log = logging.getLogger('rh.importador')


def test_progresso_nao_regride_quando_o_layout_percorre_os_itens_duas_vezes():
    reportados = []
    itens = ItensComProgresso([{'n': i} for i in range(10)], reportados.append, passo=3)

    for _ in itens:
        pass
    list(itens)  # segunda passada, como em importar_cargo_emprego

    assert reportados == [3, 6, 9, 10]


def test_captura_so_as_ocorrencias_da_propria_thread_com_a_linha():
    registradas = []
    itens = ItensComProgresso([{}, {}, {}], lambda n: None)

    with capturando_ocorrencias(lambda *args: registradas.append(args), itens):
        for indice, _ in enumerate(itens, start=1):
            if indice == 2:
                log.warning('matrícula %s sem setor', '123')
        outra = threading.Thread(target=lambda: log.error('de outro layout'))
        outra.start()
        outra.join()
        log.info('informativo não entra')

    assert registradas == [('warning', 2, 'matrícula 123 sem setor')]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST rh/tests/models/test_importacao_siape_progresso.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar**

```python
"""Instrumenta a execução de um layout sem alterar as funções `importar_*` do ImportadorSIAPE."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager


class ItensComProgresso(list):
    """Lista de itens que reporta quantos já foram percorridos."""

    def __init__(self, itens: Iterable[dict], ao_avancar: Callable[[int], None], passo: int | None = None) -> None:
        super().__init__(itens)
        self.posicao = 0
        self._ao_avancar = ao_avancar
        self._passo = passo or max(1, len(self) // 50)
        self._reportado = 0

    def __iter__(self) -> Iterator[dict]:
        for indice, item in enumerate(super().__iter__(), start=1):
            self.posicao = indice
            if indice % self._passo == 0:
                self._reportar(indice)
            yield item
        self._reportar(len(self))

    def _reportar(self, quantidade: int) -> None:
        if quantidade > self._reportado:
            self._reportado = quantidade
            self._ao_avancar(quantidade)


class CapturaOcorrencias(logging.Handler):
    def __init__(self, registrar: Callable[[str, int | None, str], None], itens: ItensComProgresso | None = None) -> None:
        super().__init__(level=logging.WARNING)
        self._thread = threading.get_ident()
        self._registrar = registrar
        self._itens = itens

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self._thread:
            return
        try:
            linha = self._itens.posicao if self._itens is not None else None
            self._registrar(record.levelname.lower(), linha, record.getMessage())
        except Exception:
            self.handleError(record)


@contextmanager
def capturando_ocorrencias(
    registrar: Callable[[str, int | None, str], None], itens: ItensComProgresso | None = None, logger: str = 'rh.importador'
) -> Iterator[CapturaOcorrencias]:
    alvo = logging.getLogger(logger)
    if alvo.getEffectiveLevel() > logging.WARNING:
        alvo.setLevel(logging.WARNING)
    handler = CapturaOcorrencias(registrar, itens)
    alvo.addHandler(handler)
    try:
        yield handler
    finally:
        alvo.removeHandler(handler)
```

- [ ] **Step 4: Rodar**

Run: `PYTEST rh/tests/models/test_importacao_siape_progresso.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rh/importacao_siape/progresso.py rh/tests/models/test_importacao_siape_progresso.py
git commit -m "[rh] Progresso e ocorrências por layout na importação SIAPE"
```

---

### Task 5: Models, migration e preparação do zip (`preparacao.py`)

**Files:**
- Create: `rh/models/importacao/__init__.py`, `rh/models/importacao/importacao_siape.py`, `rh/importacao_siape/preparacao.py`, `rh/migrations/XXXX_importacao_siape.py` (gerada), `rh/tests/fluxos/__init__.py` (vazio), `rh/tests/fluxos/test_fluxo_importacao_siape.py`
- Modify: `rh/models/__init__.py` (+ `from .importacao import *`), `rh/tests/siape.py` (+ `zip_do_extrator`), `rh/tests/conftest.py` (+ fixtures `importacao_serial`, `limpar_importacoes`)

**Interfaces:**
- Consumes: `identificar`, `carregar_refs` (Task 2); `LAYOUTS` (Task 1).
- Produces:
  - `SituacaoImportacaoSiape` (`TextChoices`): `IDENTIFICADA='identificada'`, `EXECUTANDO='executando'`, `CONCLUIDA='concluida'`, `CONCLUIDA_COM_FALHAS='concluida_com_falhas'`, `FALHOU='falhou'`
  - `SituacaoArquivoSiape` (`TextChoices`): `PENDENTE`, `AGUARDANDO`, `EXECUTANDO`, `CONCLUIDO`, `FALHOU`, `PULADO`, `IGNORADO` (valores minúsculos iguais aos nomes)
  - `ImportacaoSiape` (`arquivo`, `pasta`, `origem`, `enviado_por`, `enviado_em`, `situacao`, `inicio`, `fim`; `get_absolute_url()`, `classmethod existe_em_execucao() -> bool`, `property em_execucao`)
  - `ImportacaoSiapeArquivo` (`importacao` rel. `arquivos`, `nome_ref`, `nome_txt`, `layout`, `diagnostico`, `selecionado`, `total_linhas`, `processadas`, `falhas`, `situacao`, `motivo`, `inicio`, `fim`; `property percentual -> int`, `property classe_status -> str`)
  - `ImportacaoSiapeOcorrencia` (`arquivo` rel. `ocorrencias`, `nivel`, `linha`, `mensagem`, `criada_em`)
  - `PASTA_IMPORTACOES = 'rh/arquivos_siape/importacoes'`
  - `criar_importacao(nome: str, conteudo_zip: bytes, origem: str, usuario: User | None = None) -> ImportacaoSiape`
  - `ArquivoExtratorInvalido(Exception)`
  - `rh.tests.siape.zip_do_extrator() -> bytes` (zip com `NOME.REF.gz`/`NOME.TXT.gz` de `rh/tests/arquivos_siape_novo`, TXT transcodificado para UTF-8)

- [ ] **Step 1: Escrever os models**

`rh/models/importacao/__init__.py`:

```python
# ruff: noqa: F403

from .importacao_siape import *
```

`rh/models/importacao/importacao_siape.py`:

```python
from djtools.db import models


class SituacaoImportacaoSiape(models.TextChoices):
    IDENTIFICADA = 'identificada', 'Identificada'
    EXECUTANDO = 'executando', 'Em execução'
    CONCLUIDA = 'concluida', 'Concluída'
    CONCLUIDA_COM_FALHAS = 'concluida_com_falhas', 'Concluída com falhas'
    FALHOU = 'falhou', 'Falhou'


class SituacaoArquivoSiape(models.TextChoices):
    PENDENTE = 'pendente', 'Pendente'
    AGUARDANDO = 'aguardando', 'Aguardando dependências'
    EXECUTANDO = 'executando', 'Em execução'
    CONCLUIDO = 'concluido', 'Concluído'
    FALHOU = 'falhou', 'Falhou'
    PULADO = 'pulado', 'Pulado'
    IGNORADO = 'ignorado', 'Não será importado'


CLASSE_STATUS_ARQUIVO = {
    SituacaoArquivoSiape.CONCLUIDO: 'status-success',
    SituacaoArquivoSiape.FALHOU: 'status-error',
    SituacaoArquivoSiape.PULADO: 'status-alert',
    SituacaoArquivoSiape.EXECUTANDO: 'status-info',
    SituacaoArquivoSiape.IGNORADO: 'disabled',
}


class ImportacaoSiape(models.ModelPlus):
    arquivo = models.CharFieldPlus(verbose_name='Arquivo', max_length=255)
    pasta = models.CharFieldPlus(verbose_name='Pasta', max_length=255, default='')
    origem = models.CharFieldPlus(verbose_name='Origem', max_length=20, choices=[('tela', 'Tela'), ('comando', 'Comando agendado')])
    enviado_por = models.ForeignKeyPlus('comum.User', verbose_name='Enviado por', null=True, on_delete=models.SET_NULL)
    enviado_em = models.DateTimeFieldPlus(verbose_name='Enviado em', auto_now_add=True)
    situacao = models.CharFieldPlus(
        verbose_name='Situação', max_length=30, choices=SituacaoImportacaoSiape.choices, default=SituacaoImportacaoSiape.IDENTIFICADA
    )
    inicio = models.DateTimeFieldPlus(verbose_name='Início', null=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Importação SIAPE'
        verbose_name_plural = 'Importações SIAPE'
        ordering = ['-id']

    def __str__(self) -> str:
        return f'Importação SIAPE #{self.pk} ({self.arquivo})'

    def get_absolute_url(self) -> str:
        return f'/rh/importacao_siape/{self.pk}/'

    @property
    def em_execucao(self) -> bool:
        return self.situacao == SituacaoImportacaoSiape.EXECUTANDO

    @classmethod
    def existe_em_execucao(cls) -> bool:
        return cls.objects.filter(situacao=SituacaoImportacaoSiape.EXECUTANDO).exists()


class ImportacaoSiapeArquivo(models.ModelPlus):
    importacao = models.ForeignKeyPlus(ImportacaoSiape, verbose_name='Importação', related_name='arquivos', on_delete=models.CASCADE)
    nome_ref = models.CharFieldPlus(verbose_name='Arquivo de referência', max_length=255)
    nome_txt = models.CharFieldPlus(verbose_name='Arquivo de dados', max_length=255)
    layout = models.CharFieldPlus(verbose_name='Layout', max_length=100, null=True, blank=True)
    diagnostico = models.TextField(verbose_name='Diagnóstico', blank=True, default='')
    selecionado = models.BooleanField(verbose_name='Selecionado', default=False)
    total_linhas = models.PositiveIntegerFieldPlus(verbose_name='Linhas', default=0)
    processadas = models.PositiveIntegerFieldPlus(verbose_name='Processadas', default=0)
    falhas = models.PositiveIntegerFieldPlus(verbose_name='Falhas', default=0)
    situacao = models.CharFieldPlus(
        verbose_name='Situação', max_length=20, choices=SituacaoArquivoSiape.choices, default=SituacaoArquivoSiape.PENDENTE
    )
    motivo = models.TextField(verbose_name='Motivo', blank=True, default='')
    inicio = models.DateTimeFieldPlus(verbose_name='Início', null=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Arquivo da Importação SIAPE'
        verbose_name_plural = 'Arquivos da Importação SIAPE'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.layout or "não reconhecido"} ({self.nome_txt.rsplit("/", 1)[-1]})'

    @property
    def percentual(self) -> int:
        if self.situacao == SituacaoArquivoSiape.CONCLUIDO:
            return 100
        return min(99, self.processadas * 100 // self.total_linhas) if self.total_linhas else 0

    @property
    def classe_status(self) -> str:
        return CLASSE_STATUS_ARQUIVO.get(self.situacao, 'status-default')

    @property
    def pode_ser_selecionado(self) -> bool:
        from rh.importacao_siape.layouts import LAYOUTS

        layout = LAYOUTS.get(self.layout or '')
        return bool(layout and layout.ativo) and self.importacao.situacao == SituacaoImportacaoSiape.IDENTIFICADA


class ImportacaoSiapeOcorrencia(models.ModelPlus):
    arquivo = models.ForeignKeyPlus(ImportacaoSiapeArquivo, verbose_name='Arquivo', related_name='ocorrencias', on_delete=models.CASCADE)
    nivel = models.CharFieldPlus(verbose_name='Nível', max_length=10)
    linha = models.PositiveIntegerFieldPlus(verbose_name='Linha', null=True)
    mensagem = models.TextField(verbose_name='Mensagem')
    criada_em = models.DateTimeFieldPlus(verbose_name='Registrada em', auto_now_add=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Ocorrência da Importação SIAPE'
        verbose_name_plural = 'Ocorrências da Importação SIAPE'
        ordering = ['id']
```

Acrescentar `from .importacao import *` em `rh/models/__init__.py` (ordem alfabética, depois de `.carreira`).

Se `PositiveIntegerFieldPlus`, `CharFieldPlus` com `choices` ou `DateTimeFieldPlus(auto_now_add=True)` não aceitarem algum kwarg, conferir em `djtools/db/models/fields.py` e usar o equivalente (ex.: `models.PositiveIntegerField`).

- [ ] **Step 2: Gerar a migration**

Run: `uv run python manage.py makemigrations rh -n importacao_siape`
Expected: cria `rh/migrations/XXXX_importacao_siape.py` só com os três models. Conferir o arquivo (nada de outros models do `rh` — se aparecer, remover do arquivo e investigar antes de seguir).

- [ ] **Step 3: Helper de teste e fixtures**

Em `rh/tests/siape.py`, acrescentar (reusa `ARQUIVOS_SIAPE`):

```python
def zip_do_extrator() -> bytes:
    """Zip no formato do extrator: pares NOME.REF.gz/NOME.TXT.gz, em UTF-8."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_:
        for nome in sorted(os.listdir(ARQUIVOS_SIAPE)):
            if nome.endswith(('.TXT', '.REF')):
                with open(os.path.join(ARQUIVOS_SIAPE, nome), encoding='latin-1') as fh:
                    zip_.writestr(f'{nome}.gz', gzip.compress(fh.read().encode('utf-8')))
    return buffer.getvalue()
```

Em `rh/tests/conftest.py`, acrescentar:

```python
@pytest.fixture
def importacao_serial():
    """Motor da importação SIAPE em série: threads não enxergam a transação do teste."""
    from comum.models import Configuracao

    Configuracao.objects.update_or_create(app='rh', chave='importacao_siape_workers', defaults={'valor': '1'})
    Configuracao.clear_cache()
    yield
    Configuracao.clear_cache()


@pytest.fixture
def limpar_importacoes():
    """Apaga do storage as pastas das importações criadas no teste."""
    from django.core.files.storage import default_storage

    from rh.models import ImportacaoSiape

    yield
    for pasta in ImportacaoSiape.objects.values_list('pasta', flat=True):
        if pasta and default_storage.exists(pasta):
            for nome in default_storage.listdir(pasta)[1]:
                default_storage.delete(f'{pasta}/{nome}')
```

(Conferir os campos reais de `comum.models.Configuracao` — `app`, `chave`, `valor` são os usados em `get_valor_por_chave`.)

- [ ] **Step 4: Escrever o teste de fluxo que falha**

`rh/tests/fluxos/test_fluxo_importacao_siape.py`:

```python
"""Fluxo da importação SIAPE: zip do extrator → identificação → seleção → execução."""

import pytest

from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao
from rh.models import ImportacaoSiape, SituacaoArquivoSiape
from rh.tests.siape import zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


def test_zip_do_extrator_vira_arquivos_identificados():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    bancos = importacao.arquivos.get(layout='bancos')
    parente = importacao.arquivos.get(nome_ref__endswith='PARENTE.REF')
    assert bancos.selecionado and bancos.situacao == SituacaoArquivoSiape.PENDENTE
    assert bancos.total_linhas > 0
    assert parente.layout is None and not parente.selecionado
    assert parente.situacao == SituacaoArquivoSiape.IGNORADO
    assert 'Layout mais próximo' in parente.diagnostico


def test_zip_invalido_nao_cria_importacao():
    with pytest.raises(ArquivoExtratorInvalido):
        criar_importacao('extracao.zip', b'isto nao e zip', origem='tela')

    assert not ImportacaoSiape.objects.exists()
```

Run: `PYTEST rh/tests/fluxos/test_fluxo_importacao_siape.py -q`
Expected: FAIL (`ModuleNotFoundError: rh.importacao_siape.preparacao`).

- [ ] **Step 5: Implementar `rh/importacao_siape/preparacao.py`**

```python
"""Recebe o zip do extrator, grava os pares REF/TXT na pasta da importação e os identifica."""

from __future__ import annotations

import gzip
import io
import zipfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from rh.importacao_siape.identificacao import carregar_refs, identificar
from rh.importacao_siape.layouts import LAYOUTS
from rh.models import ImportacaoSiape, ImportacaoSiapeArquivo, SituacaoArquivoSiape

PASTA_IMPORTACOES = 'rh/arquivos_siape/importacoes'


class ArquivoExtratorInvalido(Exception):
    pass


def criar_importacao(nome: str, conteudo_zip: bytes, origem: str, usuario=None) -> ImportacaoSiape:
    pares = _ler_pares(conteudo_zip)
    refs = carregar_refs()
    with transaction.atomic():
        importacao = ImportacaoSiape.objects.create(arquivo=nome, origem=origem, enviado_por=usuario)
        importacao.pasta = f'{PASTA_IMPORTACOES}/{importacao.pk}'
        importacao.save()
        for base, par in sorted(pares.items()):
            _registrar_arquivo(importacao, base, par, refs)
    return importacao


def _ler_pares(conteudo_zip: bytes) -> dict[str, dict[str, bytes]]:
    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except zipfile.BadZipFile as erro:
        raise ArquivoExtratorInvalido('O arquivo enviado não é um zip válido.') from erro
    pares: dict[str, dict[str, bytes]] = {}
    with arquivo_zip:
        for membro in arquivo_zip.infolist():
            nome, conteudo = _descomprimir(membro.filename.rsplit('/', 1)[-1], arquivo_zip.read(membro))
            base, _, extensao = nome.rpartition('.')
            if base and extensao.upper() in ('REF', 'TXT'):
                pares.setdefault(base, {})[extensao.upper()] = conteudo
    completos = {base: par for base, par in pares.items() if len(par) == 2}
    if not completos:
        raise ArquivoExtratorInvalido('O zip não contém pares de arquivos .REF/.TXT do extrator.')
    return completos


def _descomprimir(nome: str, conteudo: bytes) -> tuple[str, bytes]:
    if nome.lower().endswith('.gz'):
        return nome[:-3], gzip.decompress(conteudo)
    return nome, conteudo


def _situacao_inicial(layout: str | None) -> tuple[str, bool, str]:
    if layout is None:
        return SituacaoArquivoSiape.IGNORADO, False, 'Layout não reconhecido.'
    if layout not in LAYOUTS:
        return SituacaoArquivoSiape.IGNORADO, False, 'Layout reconhecido, mas sem rotina de importação.'
    if not LAYOUTS[layout].ativo:
        return SituacaoArquivoSiape.IGNORADO, False, LAYOUTS[layout].motivo_inativo
    return SituacaoArquivoSiape.PENDENTE, True, ''


def _registrar_arquivo(importacao: ImportacaoSiape, base: str, par: dict[str, bytes], refs: dict[str, str]) -> None:
    identificacao = identificar(par['REF'].decode('utf-8', 'replace'), refs)
    situacao, selecionado, motivo = _situacao_inicial(identificacao.layout)
    ImportacaoSiapeArquivo.objects.create(
        importacao=importacao,
        nome_ref=default_storage.save(f'{importacao.pasta}/{base}.REF', ContentFile(par['REF'])),
        nome_txt=default_storage.save(f'{importacao.pasta}/{base}.TXT', ContentFile(par['TXT'])),
        layout=identificacao.layout,
        diagnostico=identificacao.diagnostico,
        selecionado=selecionado,
        situacao=situacao,
        motivo=motivo,
        total_linhas=len(par['TXT'].splitlines()),
    )
```

- [ ] **Step 6: Rodar**

Run: `PYTEST rh/tests/fluxos/test_fluxo_importacao_siape.py -q`
Expected: PASS (2 testes).

- [ ] **Step 7: Commit**

```bash
git add rh/models/importacao rh/models/__init__.py rh/migrations/*_importacao_siape.py rh/importacao_siape/preparacao.py \
  rh/tests/siape.py rh/tests/conftest.py rh/tests/fluxos
git commit -m "[rh] Registrando e identificando os arquivos do extrator por importação"
```

---

### Task 6: Motor de execução (`execucao.py`)

**Files:**
- Create: `rh/importacao_siape/execucao.py`
- Modify: `rh/tests/fluxos/test_fluxo_importacao_siape.py` (+ 3 testes)

**Interfaces:**
- Consumes: `executar_grafo` (Task 3); `ItensComProgresso`, `capturando_ocorrencias` (Task 4); `dependencias_efetivas` (Task 1); models (Task 5); `comum.importador.get_itens(ref, txt)`; `ImportadorSIAPE(log_level=...)._get_map_layout_functions()`.
- Produces:
  - `WORKERS_PADRAO = 4`; `workers_configurados() -> int`
  - `class ImportacaoNaoIniciada(Exception)`
  - `iniciar_importacao(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> None` — só a partir de `identificada`; recusa se houver outra `executando`; marca `selecionado` pelos ids (só entre arquivos com layout ativo), selecionados → `aguardando`, demais reconhecidos → `ignorado`; importação → `executando` com `inicio`.
  - `executar_importacao(importacao: ImportacaoSiape, workers: int) -> ImportacaoSiape` — espera a importação já iniciada; ao final: pós-processamento, `comum.Log`, situação final, pasta apagada.

- [ ] **Step 1: Escrever os testes que falham** (acrescentar ao arquivo de fluxo)

```python
from unittest import mock

from comum.models import Log
from rh.importacao_siape.execucao import ImportacaoNaoIniciada, executar_importacao, iniciar_importacao
from rh.models import Banco, CargoEmprego, ImportacaoSiapeOcorrencia, SituacaoImportacaoSiape


def _iniciar(importacao, *layouts):
    ids = importacao.arquivos.filter(layout__in=layouts).values_list('pk', flat=True)
    iniciar_importacao(importacao, ids)
    return executar_importacao(importacao, workers=1)


def test_importacao_parcial_so_processa_o_que_foi_marcado():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    _iniciar(importacao, 'bancos')

    importacao.refresh_from_db()
    bancos = importacao.arquivos.get(layout='bancos')
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
    assert bancos.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert bancos.processadas == bancos.total_linhas
    assert Banco.objects.filter(codigo='001').exists()
    assert importacao.arquivos.get(layout='uo').situacao == SituacaoArquivoSiape.IGNORADO
    assert Log.objects.filter(app='rh', titulo='Importação de arquivos', texto__contains='bancos').exists()


def test_falha_de_um_layout_pula_os_dependentes_e_nao_para_os_demais():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    with mock.patch('rh.importador.ImportadorSIAPE.importar_grupo_cargo_emprego', side_effect=RuntimeError('layout quebrado')):
        _iniciar(importacao, 'grupo_cargo_emprego', 'cargo_emprego', 'bancos')

    importacao.refresh_from_db()
    grupo = importacao.arquivos.get(layout='grupo_cargo_emprego')
    cargo = importacao.arquivos.get(layout='cargo_emprego')
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS
    assert grupo.situacao == SituacaoArquivoSiape.FALHOU and 'layout quebrado' in grupo.motivo
    assert cargo.situacao == SituacaoArquivoSiape.PULADO and 'grupo_cargo_emprego' in cargo.motivo
    assert not CargoEmprego.objects.exists()
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.CONCLUIDO


def test_warning_do_importador_vira_ocorrencia_e_outra_importacao_e_recusada():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    def importar_bancos_com_aviso(self, itens):
        import logging

        for indice, _ in enumerate(itens, start=1):
            if indice == 2:
                logging.getLogger('rh.importador').warning('banco sem sigla')

    with mock.patch('rh.importador.ImportadorSIAPE.importar_bancos', importar_bancos_com_aviso):
        ids = importacao.arquivos.filter(layout='bancos').values_list('pk', flat=True)
        iniciar_importacao(importacao, ids)
        outra = criar_importacao('outra.zip', zip_do_extrator(), origem='tela')
        with pytest.raises(ImportacaoNaoIniciada):
            iniciar_importacao(outra, [])
        executar_importacao(importacao, workers=1)

    ocorrencia = ImportacaoSiapeOcorrencia.objects.get(arquivo__importacao=importacao)
    assert (ocorrencia.nivel, ocorrencia.linha, ocorrencia.mensagem) == ('warning', 2, 'banco sem sigla')
    assert ocorrencia.arquivo.falhas == 1
```

Run: `PYTEST rh/tests/fluxos/test_fluxo_importacao_siape.py -q`
Expected: FAIL (`ModuleNotFoundError: rh.importacao_siape.execucao`).

- [ ] **Step 2: Implementar `rh/importacao_siape/execucao.py`**

```python
"""Executa uma importação SIAPE: grafo de layouts em paralelo, com progresso e ocorrências no banco."""

from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from collections.abc import Collection
from datetime import datetime
from functools import partial

from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.db.models import F

from comum.importador import get_itens
from comum.models import Configuracao, Log
from rh.importacao_siape.agendador import Resultado, executar_grafo
from rh.importacao_siape.layouts import LAYOUTS, dependencias_efetivas
from rh.importacao_siape.progresso import ItensComProgresso, capturando_ocorrencias
from rh.models import (
    ImportacaoSiape,
    ImportacaoSiapeArquivo,
    ImportacaoSiapeOcorrencia,
    Servidor,
    SituacaoArquivoSiape,
    SituacaoImportacaoSiape,
)

log = logging.getLogger(__name__)

WORKERS_PADRAO = 4


class ImportacaoNaoIniciada(Exception):
    pass


def workers_configurados() -> int:
    valor = Configuracao.get_valor_por_chave('rh', 'importacao_siape_workers')
    try:
        return max(1, int(valor))
    except TypeError, ValueError:
        return WORKERS_PADRAO


def iniciar_importacao(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> None:
    with transaction.atomic():
        if importacao.situacao != SituacaoImportacaoSiape.IDENTIFICADA:
            raise ImportacaoNaoIniciada('Esta importação já foi executada.')
        if ImportacaoSiape.existe_em_execucao():
            raise ImportacaoNaoIniciada('Já existe uma importação SIAPE em execução. Aguarde o término.')
        importaveis = importacao.arquivos.filter(layout__in=[n for n, layout in LAYOUTS.items() if layout.ativo])
        importaveis.filter(pk__in=ids_selecionados).update(selecionado=True, situacao=SituacaoArquivoSiape.AGUARDANDO)
        importaveis.exclude(pk__in=ids_selecionados).update(selecionado=False, situacao=SituacaoArquivoSiape.IGNORADO)
        _atualizar(importacao, situacao=SituacaoImportacaoSiape.EXECUTANDO, inicio=datetime.now())


def executar_importacao(importacao: ImportacaoSiape, workers: int) -> ImportacaoSiape:
    por_layout: dict[str, list[ImportacaoSiapeArquivo]] = defaultdict(list)
    for arquivo in importacao.arquivos.filter(selecionado=True).exclude(layout=None):
        por_layout[arquivo.layout].append(arquivo)
    dependencias = {nome: dependencias_efetivas(nome, por_layout.keys()) for nome in por_layout}
    try:
        resultado = executar_grafo(
            dependencias,
            partial(_executar_layout, por_layout, workers > 1),
            workers,
            ao_pular=partial(_marcar_pulado, por_layout),
        )
        _pos_processar()
    except Exception:
        _atualizar(importacao, situacao=SituacaoImportacaoSiape.FALHOU, fim=datetime.now())
        raise
    finally:
        _apagar_pasta(importacao.pasta)
    _atualizar(importacao, situacao=_situacao_final(importacao, resultado), fim=datetime.now())
    Log.objects.create(titulo='Importação de arquivos', texto=_resumo(importacao, resultado), app='rh')
    return importacao


def _executar_layout(por_layout: dict[str, list[ImportacaoSiapeArquivo]], fechar_conexao: bool, nome: str) -> None:
    try:
        for arquivo in por_layout[nome]:
            _processar_arquivo(arquivo, nome)
    finally:
        if fechar_conexao:
            connection.close()


def _processar_arquivo(arquivo: ImportacaoSiapeArquivo, nome: str) -> None:
    from rh.importador import ImportadorSIAPE

    _atualizar(arquivo, situacao=SituacaoArquivoSiape.EXECUTANDO, inicio=datetime.now())
    funcao = ImportadorSIAPE(log_level='INFO')._get_map_layout_functions()[nome]
    itens = ItensComProgresso(get_itens(arquivo.nome_ref, arquivo.nome_txt), partial(_registrar_progresso, arquivo.pk))
    with capturando_ocorrencias(partial(_registrar_ocorrencia, arquivo.pk), itens):
        try:
            funcao(itens)
        except Exception:
            _atualizar(arquivo, situacao=SituacaoArquivoSiape.FALHOU, motivo=traceback.format_exc(), fim=datetime.now())
            raise
    _atualizar(arquivo, situacao=SituacaoArquivoSiape.CONCLUIDO, processadas=arquivo.total_linhas, fim=datetime.now())


def _atualizar(obj: ImportacaoSiape | ImportacaoSiapeArquivo, **campos: object) -> None:
    for campo, valor in campos.items():
        setattr(obj, campo, valor)
    type(obj).objects.filter(pk=obj.pk).update(**campos)


def _registrar_progresso(arquivo_id: int, processadas: int) -> None:
    ImportacaoSiapeArquivo.objects.filter(pk=arquivo_id).update(processadas=processadas)


def _registrar_ocorrencia(arquivo_id: int, nivel: str, linha: int | None, mensagem: str) -> None:
    ImportacaoSiapeOcorrencia.objects.create(arquivo_id=arquivo_id, nivel=nivel, linha=linha, mensagem=mensagem)
    ImportacaoSiapeArquivo.objects.filter(pk=arquivo_id).update(falhas=F('falhas') + 1)


def _marcar_pulado(por_layout: dict[str, list[ImportacaoSiapeArquivo]], nome: str, motivo: str) -> None:
    for arquivo in por_layout[nome]:
        _atualizar(arquivo, situacao=SituacaoArquivoSiape.PULADO, motivo=motivo)


def _pos_processar() -> None:
    # mesmo comportamento de comum.importador.Importador._process
    if Configuracao.get_valor_por_chave('rh', 'executar_save_pos_importacao'):
        for servidor in Servidor.objects.ativos().all():
            servidor.save()
    cache.delete('data_ultima_importacao_siape')


def _situacao_final(importacao: ImportacaoSiape, resultado: Resultado) -> str:
    houve_erro = ImportacaoSiapeOcorrencia.objects.filter(arquivo__importacao=importacao, nivel__in=['error', 'critical']).exists()
    if resultado.falhos or resultado.pulados or houve_erro:
        return SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS
    return SituacaoImportacaoSiape.CONCLUIDA


def _resumo(importacao: ImportacaoSiape, resultado: Resultado) -> str:
    partes = [f'Importação SIAPE #{importacao.pk} ({importacao.arquivo}).']
    if resultado.concluidos:
        partes.append('Importados: ' + ', '.join(sorted(resultado.concluidos)) + '.')
    if resultado.falhos:
        partes.append('Falharam: ' + ', '.join(sorted(resultado.falhos)) + '.')
    if resultado.pulados:
        partes.append('Pulados: ' + ', '.join(sorted(resultado.pulados)) + '.')
    return ' '.join(partes)


def _apagar_pasta(pasta: str) -> None:
    if not pasta or not default_storage.exists(pasta):
        return
    for nome in default_storage.listdir(pasta)[1]:
        default_storage.delete(f'{pasta}/{nome}')
    default_storage.delete(pasta)
```

Notas:
- `except TypeError, ValueError:` é a sintaxe PEP 758 que o ruff (target py314) produz; pode escrever com parênteses que o format ajusta.
- Confirmar que `Servidor.objects.ativos()` existe (é o que `comum/importador.py:225` usa).
- O arquivo em `_executar_layout` roda dentro da thread do pool: o `connection.close()` só quando `workers > 1` — em série ele fecharia a conexão (e a transação) do chamador.

- [ ] **Step 3: Rodar os testes de fluxo e a regressão do importador**

Run: `PYTEST rh/tests/fluxos/test_fluxo_importacao_siape.py rh/tests/models/test_importador.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add rh/importacao_siape/execucao.py rh/tests/fluxos/test_fluxo_importacao_siape.py
git commit -m "[rh] Motor paralelo da importação SIAPE com progresso e ocorrências por layout"
```

---

### Task 7: Task assíncrona, comando `importar_siape` e configuração de workers

**Files:**
- Modify: `rh/tasks.py` (+ `executar_importacao_siape`), `rh/management/commands/importar_siape.py` (reescrito), `rh/forms.py:~284` (`ConfiguracaoForm` + campo)
- Test: `rh/tests/tasks/test_importar_siape_command.py`

**Interfaces:**
- Consumes: `criar_importacao`, `iniciar_importacao`, `executar_importacao`, `workers_configurados`, `ImportacaoNaoIniciada`.
- Produces:
  - `rh.tasks.executar_importacao_siape(importacao_id: int, task=None) -> None` (decorada com `@task('Importação SIAPE')`)
  - comando `importar_siape [--pasta rh/arquivos_siape]`

- [ ] **Step 1: Escrever o teste que falha**

```python
"""Comando importar_siape (beat das 01:07) sobre o motor novo."""

import os

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from rh.models import Banco, ImportacaoSiape, SituacaoImportacaoSiape
from rh.tests.siape import zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


@pytest.fixture
def pasta():
    pasta = f'rh/arquivos_siape_comando_{os.environ.get("PYTEST_XDIST_WORKER", "gw0")}'
    yield pasta
    if default_storage.exists(pasta):
        for nome in default_storage.listdir(pasta)[1]:
            default_storage.delete(f'{pasta}/{nome}')


def test_comando_importa_o_zip_da_pasta_e_o_remove(pasta):
    caminho = default_storage.save(f'{pasta}/extracao.zip', ContentFile(zip_do_extrator()))

    call_command('importar_siape', pasta=pasta)

    importacao = ImportacaoSiape.objects.get()
    assert importacao.origem == 'comando'
    assert importacao.situacao in (SituacaoImportacaoSiape.CONCLUIDA, SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS)
    assert importacao.arquivos.get(layout='bancos').situacao == 'concluido'
    assert Banco.objects.filter(codigo='001').exists()
    assert not default_storage.exists(caminho)


def test_comando_sem_zip_nao_cria_importacao(pasta):
    call_command('importar_siape', pasta=pasta)

    assert not ImportacaoSiape.objects.exists()
```

Run: `PYTEST rh/tests/tasks/test_importar_siape_command.py -q`
Expected: FAIL (`unrecognized arguments: --pasta` / `TypeError` do `call_command`).

- [ ] **Step 2: Reescrever `rh/management/commands/importar_siape.py`**

```python
from django.core.files.storage import default_storage

from djtools.management.commands import BaseCommandPlus
from rh.importacao_siape.execucao import ImportacaoNaoIniciada, executar_importacao, iniciar_importacao, workers_configurados
from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao

PASTA_EXTRATOR = 'rh/arquivos_siape'


class Command(BaseCommandPlus):
    help = 'Importa os zips do extrator SIAPE enviados para a pasta do extrator'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--pasta', default=PASTA_EXTRATOR)
        parser.add_argument('--log', dest='log', default='DEBUG', help='Mantido por compatibilidade; sem efeito.')

    def handle(self, *args, **options) -> None:
        pasta = options['pasta']
        zips = [nome for nome in default_storage.listdir(pasta)[1] if nome.endswith('.zip')] if default_storage.exists(pasta) else []
        if not zips:
            self.stdout.write('Nenhum arquivo do extrator para importar.')
            return
        for nome in sorted(zips):
            self._importar(f'{pasta}/{nome}', nome)

    def _importar(self, caminho: str, nome: str) -> None:
        with default_storage.open(caminho, 'rb') as arquivo:
            conteudo = arquivo.read()
        try:
            importacao = criar_importacao(nome, conteudo, origem='comando')
            iniciar_importacao(importacao, importacao.arquivos.filter(selecionado=True).values_list('pk', flat=True))
        except (ArquivoExtratorInvalido, ImportacaoNaoIniciada) as erro:
            self.stderr.write(f'{nome}: {erro}')
            return
        executar_importacao(importacao, workers_configurados())
        default_storage.delete(caminho)
        self.stdout.write(f'{nome}: importação #{importacao.pk} {importacao.get_situacao_display().lower()}.')
```

Nota: se `iniciar_importacao` recusar (outra em execução), a importação criada fica `identificada` e o zip permanece na pasta para a próxima execução do beat.

- [ ] **Step 3: Task em `rh/tasks.py`**

Acrescentar (junto às demais `@task`; `task` já é importado no arquivo — conferir o import existente de `djtools.assincrono`):

```python
@task('Importação SIAPE')
def executar_importacao_siape(importacao_id: int, task=None) -> None:
    from rh.importacao_siape.execucao import executar_importacao, workers_configurados
    from rh.models import ImportacaoSiape

    importacao = ImportacaoSiape.objects.get(pk=importacao_id)
    executar_importacao(importacao, workers_configurados())
    task.finalize(f'Importação SIAPE #{importacao.pk} finalizada.', importacao.get_absolute_url())
```

- [ ] **Step 4: Campo de configuração em `rh/forms.py`** (`ConfiguracaoForm`, logo após `executar_save_pos_importacao`)

```python
    importacao_siape_workers = forms.IntegerField(
        label='Arquivos do extrator importados em paralelo',
        required=False,
        min_value=1,
        max_value=16,
        help_text='Quantos layouts do extrator SIAPE são importados ao mesmo tempo. Em branco: 4. Use 1 para importar em série.',
    )
```

- [ ] **Step 5: Rodar**

Run: `PYTEST rh/tests/tasks/test_importar_siape_command.py rh/tests/fluxos -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add rh/tasks.py rh/management/commands/importar_siape.py rh/forms.py rh/tests/tasks/test_importar_siape_command.py
git commit -m "[rh] Comando importar_siape e tarefa assíncrona sobre o motor paralelo"
```

---

### Task 8: Telas (upload, detalhe com seleção e progresso em tempo real, ocorrências)

**Files:**
- Create: `rh/importacao_siape/forms.py`, `rh/importacao_siape/views.py`, `rh/templates/importacao_siape_lista.html`, `rh/templates/importacao_siape_detalhe.html`, `rh/templates/importacao_siape_ocorrencias.html`, `rh/static/rh/js/importacao_siape.js`
- Modify: `rh/urls.py` (4 rotas), `rh/menu.yaml` (entrada nova)
- Test: `rh/tests/views/test_importacao_siape_views.py`

**Interfaces:**
- Consumes: tudo das tasks 1, 5, 6, 7 (`rh.tasks.executar_importacao_siape`).
- Produces: rotas
  - `GET/POST /rh/importacao_siape/` → `importacao_siape_lista`
  - `GET/POST /rh/importacao_siape/<importacao_id>/` → `importacao_siape_detalhe`
  - `GET /rh/importacao_siape/<importacao_id>/progresso.json` → `importacao_siape_progresso`
  - `GET /rh/importacao_siape/<importacao_id>/arquivo/<arquivo_id>/ocorrencias/` → `importacao_siape_ocorrencias`

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Telas da importação SIAPE."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from rh.models import ImportacaoSiape
from rh.tests.siape import zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


@pytest.fixture
def cliente(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


def test_upload_identifica_e_importar_selecionados_conclui(cliente):
    resposta = cliente.post('/rh/importacao_siape/', {'arquivo': SimpleUploadedFile('extracao.zip', zip_do_extrator())})
    importacao = ImportacaoSiape.objects.get()
    assert resposta.status_code == 302 and resposta.url.endswith(importacao.get_absolute_url())

    detalhe = cliente.get(importacao.get_absolute_url()).content.decode()
    assert 'bancos' in detalhe and 'Layout mais próximo' in detalhe

    bancos = importacao.arquivos.get(layout='bancos')
    cliente.post(importacao.get_absolute_url(), {'arquivos': [bancos.pk]})

    progresso = cliente.get(f'{importacao.get_absolute_url()}progresso.json').json()
    assert progresso['situacao'] == 'concluida'
    assert {'id': bancos.pk, 'situacao': 'concluido'}.items() <= next(a for a in progresso['arquivos'] if a['id'] == bancos.pk).items()


def test_upload_de_arquivo_que_nao_e_zip_do_extrator_mostra_erro(cliente):
    resposta = cliente.post('/rh/importacao_siape/', {'arquivo': SimpleUploadedFile('extracao.zip', b'nada')})

    assert resposta.status_code == 200
    assert 'não é um zip válido' in resposta.content.decode()
    assert not ImportacaoSiape.objects.exists()


def test_nao_inicia_com_outra_importacao_em_execucao(cliente):
    cliente.post('/rh/importacao_siape/', {'arquivo': SimpleUploadedFile('a.zip', zip_do_extrator())})
    cliente.post('/rh/importacao_siape/', {'arquivo': SimpleUploadedFile('b.zip', zip_do_extrator())})
    primeira, segunda = ImportacaoSiape.objects.order_by('id')
    ImportacaoSiape.objects.filter(pk=primeira.pk).update(situacao='executando')

    resposta = cliente.post(segunda.get_absolute_url(), {'arquivos': []}, follow=True)

    assert 'Já existe uma importação SIAPE em execução' in resposta.content.decode()
    segunda.refresh_from_db()
    assert segunda.situacao == 'identificada'
```

Run: `PYTEST rh/tests/views/test_importacao_siape_views.py -q`
Expected: FAIL (404 nas rotas).

- [ ] **Step 2: Formulário `rh/importacao_siape/forms.py`**

```python
from djtools import forms


class ImportacaoSiapeUploadForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo do extrator (.zip)', required=True)

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        if not arquivo.name.lower().endswith('.zip'):
            raise forms.ValidationError('Envie o arquivo compactado (.zip) gerado pelo extrator SIAPE.')
        return arquivo
```

(Conferir que `rh/forms.py` importa `forms` de `djtools` — mesmo import do `UploadArquivosExtratorForm`.)

- [ ] **Step 3: Views `rh/importacao_siape/views.py`**

```python
from __future__ import annotations

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from djtools.utils import JsonResponse, httprr, permission_required, rtr
from rh.importacao_siape.execucao import ImportacaoNaoIniciada, iniciar_importacao
from rh.importacao_siape.forms import ImportacaoSiapeUploadForm
from rh.importacao_siape.layouts import GRUPO_HISTORICOS, GRUPO_NUCLEO, GRUPO_TABELAS, LAYOUTS, dependencias_transitivas, ordem_topologica
from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao
from rh.models import ImportacaoSiape, ImportacaoSiapeArquivo

PERMISSAO = 'rh.pode_gerenciar_extracao_siape'
GRUPO_OUTROS = 'Não reconhecidos ou sem importação'


@rtr()
@permission_required(PERMISSAO)
def importacao_siape_lista(request: HttpRequest):
    title = 'Importação SIAPE'
    form = ImportacaoSiapeUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo = form.cleaned_data['arquivo']
        try:
            importacao = criar_importacao(arquivo.name, arquivo.read(), origem='tela', usuario=request.user)
        except ArquivoExtratorInvalido as erro:
            form.add_error('arquivo', str(erro))
        else:
            return httprr(importacao.get_absolute_url(), 'Arquivos identificados. Marque o que será importado.')
    importacoes = ImportacaoSiape.objects.select_related('enviado_por')[:30]
    return locals()


@rtr()
@permission_required(PERMISSAO)
def importacao_siape_detalhe(request: HttpRequest, importacao_id: int):
    importacao = get_object_or_404(ImportacaoSiape, pk=importacao_id)
    if request.method == 'POST':
        return _iniciar(request, importacao)
    title = f'Importação SIAPE #{importacao.pk}'
    grupos = _agrupar(importacao)
    dependencias = {nome: sorted(dependencias_transitivas(nome)) for nome in LAYOUTS}
    return locals()


def _iniciar(request: HttpRequest, importacao: ImportacaoSiape):
    from rh.tasks import executar_importacao_siape

    ids = {int(valor) for valor in request.POST.getlist('arquivos') if valor.isdigit()}
    try:
        iniciar_importacao(importacao, ids)
    except ImportacaoNaoIniciada as erro:
        return httprr(importacao.get_absolute_url(), str(erro), 'error')
    executar_importacao_siape(importacao.pk)
    return httprr(importacao.get_absolute_url(), 'Importação iniciada. Acompanhe o andamento abaixo.')


def _agrupar(importacao: ImportacaoSiape) -> list[tuple[str, list[dict]]]:
    ordem = {nome: indice for indice, nome in enumerate(ordem_topologica(apenas_ativos=False))}
    presentes = set(importacao.arquivos.exclude(layout=None).values_list('layout', flat=True))
    grupos: dict[str, list[dict]] = {GRUPO_TABELAS: [], GRUPO_NUCLEO: [], GRUPO_HISTORICOS: [], GRUPO_OUTROS: []}
    for arquivo in importacao.arquivos.select_related('importacao'):
        layout = LAYOUTS.get(arquivo.layout or '')
        grupo = layout.grupo if layout and layout.ativo else GRUPO_OUTROS
        ausentes = sorted(set(layout.dependencias) - presentes) if layout else []
        grupos[grupo].append({'arquivo': arquivo, 'dependencias': layout.dependencias if layout else (), 'ausentes': ausentes})
    for linhas in grupos.values():
        linhas.sort(key=lambda linha: ordem.get(linha['arquivo'].layout, len(ordem)))
    return [(nome, linhas) for nome, linhas in grupos.items() if linhas]


@permission_required(PERMISSAO)
def importacao_siape_progresso(request: HttpRequest, importacao_id: int):
    importacao = get_object_or_404(ImportacaoSiape, pk=importacao_id)
    arquivos = [
        {
            'id': arquivo.pk,
            'situacao': arquivo.situacao,
            'situacao_display': arquivo.get_situacao_display(),
            'classe_status': arquivo.classe_status,
            'processadas': arquivo.processadas,
            'total_linhas': arquivo.total_linhas,
            'percentual': arquivo.percentual,
            'falhas': arquivo.falhas,
            'motivo': arquivo.motivo[-2000:],
        }
        for arquivo in importacao.arquivos.all()
    ]
    return JsonResponse(
        {
            'situacao': importacao.situacao,
            'situacao_display': importacao.get_situacao_display(),
            'em_execucao': importacao.em_execucao,
            'arquivos': arquivos,
        }
    )


@rtr()
@permission_required(PERMISSAO)
def importacao_siape_ocorrencias(request: HttpRequest, importacao_id: int, arquivo_id: int):
    arquivo = get_object_or_404(ImportacaoSiapeArquivo, pk=arquivo_id, importacao_id=importacao_id)
    title = f'Ocorrências de {arquivo}'
    ocorrencias = arquivo.ocorrencias.all()[:2000]
    return locals()
```

Conferir: (a) `get_app_name` de `rh.importacao_siape.views` resolve para `rh` — se não, passar o template explícito, ex. `@rtr('rh/templates/importacao_siape_lista.html')`; (b) `djtools.utils.JsonResponse` aceita um `dict` (é o uso em `rh/views.py:2630`).

- [ ] **Step 4: Rotas e menu**

`rh/urls.py` — importar `from rh.importacao_siape import views as views_importacao_siape` e acrescentar após `upload_arquivos_extrator/`:

```python
    path('importacao_siape/', views_importacao_siape.importacao_siape_lista),
    path('importacao_siape/<int:importacao_id>/', views_importacao_siape.importacao_siape_detalhe),
    path('importacao_siape/<int:importacao_id>/progresso.json', views_importacao_siape.importacao_siape_progresso),
    path(
        'importacao_siape/<int:importacao_id>/arquivo/<int:arquivo_id>/ocorrencias/',
        views_importacao_siape.importacao_siape_ocorrencias,
    ),
```

`rh/menu.yaml` — após `Gestão de Pessoas::SIAPE::Extrator`:

```yaml
Gestão de Pessoas::SIAPE::Importação do Extrator:
  order: 103
  permissions_required:
  - rh.pode_gerenciar_extracao_siape
  url: /rh/importacao_siape/
```

- [ ] **Step 5: Templates**

Seguir `docs/design-system.md` e validar cada classe com grep em `/comum/design_system/` / `comum/templates/tabs/guia_*.html` antes de usar. Se preferir, delegar este step ao subagente `suap-frontend` passando o contexto (variáveis abaixo).

`rh/templates/importacao_siape_lista.html`:

```django
{% extends super_template %}

{% block content %}
    {% box 'Enviar arquivo do extrator' %}
        {% render_form form %}
    {% endbox %}

    {% box 'Importações' %}
        {% if importacoes %}
            <div class="table-responsive">
                <table>
                    <caption>Últimas importações do extrator SIAPE</caption>
                    <thead>
                        <tr>
                            <th>#</th><th>Arquivo</th><th>Origem</th><th>Enviado por</th><th>Enviado em</th><th>Situação</th><th>Fim</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for importacao in importacoes %}
                            <tr>
                                <td><a href="{{ importacao.get_absolute_url }}">{{ importacao.pk }}</a></td>
                                <td>{{ importacao.arquivo }}</td>
                                <td>{{ importacao.get_origem_display }}</td>
                                <td>{{ importacao.enviado_por|default:"-" }}</td>
                                <td>{{ importacao.enviado_em }}</td>
                                <td><span class="status status-{{ importacao.situacao }}">{{ importacao.get_situacao_display }}</span></td>
                                <td>{{ importacao.fim|default:"-" }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% else %}
            <p class="msg alert">Nenhuma importação registrada.</p>
        {% endif %}
    {% endbox %}
{% endblock %}
```

`rh/templates/importacao_siape_detalhe.html`:

```django
{% extends super_template %}
{% load static %}

{% block extrahead %}
    <script src="{% static 'rh/js/importacao_siape.js' %}" defer></script>
{% endblock %}

{% block object-status %}
    <span class="status status-{{ importacao.situacao }}" data-situacao-importacao>{{ importacao.get_situacao_display }}</span>
{% endblock %}

{% block content %}
    {{ dependencias|json_script:"importacao-siape-dependencias" }}
    <form method="post" data-importacao-siape
          data-progresso-url="{{ importacao.get_absolute_url }}progresso.json"
          data-em-execucao="{{ importacao.em_execucao|yesno:'1,0' }}">
        {% csrf_token %}
        <div class="msg info" data-avisos-dependencias hidden></div>
        {% for grupo, linhas in grupos %}
            {% box grupo %}
                <div class="table-responsive">
                    <table>
                        <caption>{{ grupo }}</caption>
                        <thead>
                            <tr>
                                <th>Importar</th><th>Layout</th><th>Arquivo</th><th>Linhas</th><th>Depende de</th>
                                <th>Situação</th><th>Progresso</th><th>Falhas</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for linha in linhas %}
                                {% with arquivo=linha.arquivo %}
                                    <tr data-arquivo="{{ arquivo.pk }}">
                                        <td>
                                            <input type="checkbox" name="arquivos" value="{{ arquivo.pk }}" data-layout="{{ arquivo.layout|default:'' }}"
                                                   aria-label="Importar {{ arquivo.layout|default:'arquivo' }}"
                                                   {% if arquivo.selecionado %}checked{% endif %}
                                                   {% if not arquivo.pode_ser_selecionado %}disabled{% endif %}>
                                        </td>
                                        <td>{{ arquivo.layout|default:"Não reconhecido" }}</td>
                                        <td>{{ arquivo.nome_txt|cut:importacao.pasta }}</td>
                                        <td>{{ arquivo.total_linhas }}</td>
                                        <td>
                                            {{ linha.dependencias|join:", "|default:"-" }}
                                            {% if linha.ausentes %}<p class="help">Não vieram no zip: {{ linha.ausentes|join:", " }} — serão usados os dados já existentes no banco.</p>{% endif %}
                                        </td>
                                        <td>
                                            <span class="status {{ arquivo.classe_status }}" data-campo="situacao">{{ arquivo.get_situacao_display }}</span>
                                            <p class="help" data-campo="motivo">{{ arquivo.motivo|default:arquivo.diagnostico|truncatechars:300 }}</p>
                                        </td>
                                        <td data-campo="progresso">{% progressbar arquivo.percentual %}</td>
                                        <td>
                                            <a href="{{ importacao.get_absolute_url }}arquivo/{{ arquivo.pk }}/ocorrencias/" data-campo="falhas">{{ arquivo.falhas }}</a>
                                        </td>
                                    </tr>
                                {% endwith %}
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            {% endbox %}
        {% endfor %}
        {% if importacao.situacao == 'identificada' %}
            <div class="submit-row">
                <input type="submit" class="btn success" value="Importar selecionados" data-botao-importar>
            </div>
        {% endif %}
    </form>
{% endblock %}
```

`pode_ser_selecionado` (Task 5) consulta `self.importacao`: em `_agrupar`, iterar `importacao.arquivos.select_related('importacao')` para não gerar uma query por linha.

`rh/templates/importacao_siape_ocorrencias.html`:

```django
{% extends super_template %}

{% block content %}
    {% if arquivo.motivo %}
        {% box 'Erro do layout' %}
            <pre>{{ arquivo.motivo }}</pre>
        {% endbox %}
    {% endif %}
    {% box 'Ocorrências' %}
        {% if ocorrencias %}
            <div class="table-responsive">
                <table>
                    <caption>Ocorrências registradas durante a importação de {{ arquivo.layout }}</caption>
                    <thead><tr><th>Linha</th><th>Nível</th><th>Mensagem</th><th>Registrada em</th></tr></thead>
                    <tbody>
                        {% for ocorrencia in ocorrencias %}
                            <tr>
                                <td>{{ ocorrencia.linha|default:"-" }}</td>
                                <td><span class="status {% if ocorrencia.nivel == 'warning' %}status-alert{% else %}status-error{% endif %}">{{ ocorrencia.nivel }}</span></td>
                                <td>{{ ocorrencia.mensagem }}</td>
                                <td>{{ ocorrencia.criada_em }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% else %}
            <p class="msg alert">Nenhuma ocorrência registrada.</p>
        {% endif %}
    {% endbox %}
{% endblock %}
```

- [ ] **Step 6: JS `rh/static/rh/js/importacao_siape.js`**

```javascript
(function () {
    'use strict';

    const INTERVALO_MS = 2000;

    function iniciar() {
        const form = document.querySelector('[data-importacao-siape]');
        if (!form) {
            return;
        }
        const dependencias = JSON.parse(document.getElementById('importacao-siape-dependencias').textContent);
        ligarMarcacao(form, dependencias);
        if (form.dataset.emExecucao === '1') {
            acompanhar(form);
        }
    }

    function caixas(form) {
        return Array.from(form.querySelectorAll('input[name="arquivos"]'));
    }

    function ligarMarcacao(form, dependencias) {
        const avisos = form.querySelector('[data-avisos-dependencias]');
        form.addEventListener('change', function (evento) {
            const caixa = evento.target;
            if (caixa.name !== 'arquivos' || !caixa.dataset.layout) {
                return;
            }
            const mensagens = caixa.checked ? marcarDependencias(form, dependencias, caixa.dataset.layout) : avisarDependentes(form, dependencias, caixa.dataset.layout);
            avisos.textContent = mensagens;
            avisos.hidden = !mensagens;
        });
    }

    function marcarDependencias(form, dependencias, layout) {
        const marcadas = [];
        caixas(form).forEach(function (outra) {
            if (!outra.disabled && !outra.checked && (dependencias[layout] || []).includes(outra.dataset.layout)) {
                outra.checked = true;
                marcadas.push(outra.dataset.layout);
            }
        });
        return marcadas.length ? 'Dependências marcadas junto com ' + layout + ': ' + marcadas.join(', ') + '. Você pode desmarcá-las.' : '';
    }

    function avisarDependentes(form, dependencias, layout) {
        const dependentes = caixas(form)
            .filter(function (outra) { return outra.checked && (dependencias[outra.dataset.layout] || []).includes(layout); })
            .map(function (outra) { return outra.dataset.layout; });
        return dependentes.length ? layout + ' foi desmarcado, mas ' + dependentes.join(', ') + ' depende dele: serão usados os dados já existentes no banco.' : '';
    }

    function acompanhar(form) {
        caixas(form).forEach(function (caixa) { caixa.disabled = true; });
        fetch(form.dataset.progressoUrl, { credentials: 'same-origin' })
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                atualizar(form, dados);
                if (dados.em_execucao) {
                    window.setTimeout(function () { acompanhar(form); }, INTERVALO_MS);
                }
            })
            .catch(function () { window.setTimeout(function () { acompanhar(form); }, INTERVALO_MS * 2); });
    }

    function atualizar(form, dados) {
        const situacao = document.querySelector('[data-situacao-importacao]');
        if (situacao) {
            situacao.textContent = dados.situacao_display;
            situacao.className = 'status status-' + dados.situacao;
        }
        dados.arquivos.forEach(function (arquivo) {
            const linha = form.querySelector('tr[data-arquivo="' + arquivo.id + '"]');
            if (!linha) {
                return;
            }
            const rotulo = linha.querySelector('[data-campo="situacao"]');
            rotulo.textContent = arquivo.situacao_display;
            rotulo.className = 'status ' + arquivo.classe_status;
            if (arquivo.motivo) {
                linha.querySelector('[data-campo="motivo"]').textContent = arquivo.motivo.slice(-300);
            }
            const barra = linha.querySelector('[data-campo="progresso"] progress');
            barra.value = arquivo.percentual;
            barra.nextElementSibling.textContent = arquivo.percentual + '%';
            linha.querySelector('[data-campo="falhas"]').textContent = arquivo.falhas;
        });
    }

    document.addEventListener('DOMContentLoaded', iniciar);
})();
```

- [ ] **Step 7: Rodar os testes de view**

Run: `PYTEST rh/tests/views/test_importacao_siape_views.py -q`
Expected: PASS.

- [ ] **Step 8: Conferir a tela no navegador** (manual, dev server)

Run: `uv run python manage.py runserver` e, logado com permissão, abrir `/rh/importacao_siape/`; enviar `deploy/media/rh/arquivos_siape/_extracao-22092026.zip`; conferir os 32 arquivos agrupados, `historico_afastamento` desabilitado com o motivo, a marcação de dependências e, ao importar só as tabelas, as barras avançando e a situação final.

- [ ] **Step 9: Commit**

```bash
git add rh/importacao_siape/forms.py rh/importacao_siape/views.py rh/templates/importacao_siape_*.html rh/static/rh/js/importacao_siape.js \
  rh/urls.py rh/menu.yaml rh/models/importacao rh/tests/views/test_importacao_siape_views.py
git commit -m "[rh] Tela de importação SIAPE com seleção de layouts e acompanhamento em tempo real"
```

---

### Task 9: Fechamento

- [ ] **Step 1: Suíte do rh e do importador genérico**

Run: `PYTEST rh comum/tests/tasks/test_importador.py -q -n 4`
Expected: PASS (sem regressão).

- [ ] **Step 2: Lint / CI parity**

Run: `ruff format . && ruff check . --fix --unsafe-fixes && pre-commit run --from-ref origin/master --to-ref HEAD`
Expected: sem erros. Corrigir e commitar o que o pre-commit apontar.

- [ ] **Step 3: Dependências de módulo**

Run: `uv run python manage.py module_dependencies --check --all`
Expected: OK (o pacote novo só usa `rh`, `comum`, `djtools`).
