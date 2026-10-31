# Backend SUAP — Lançamento de execuções do PGD via GitLab (Plano 1 de 3)

> **Revisão 2026-06-01:** reescrito para o desenho enxuto — sem `RascunhoExecucaoGitLab`. O RIT é criado
> direto no estado nativo `EM_CADASTRO_RIT`, com 2 campos de proveniência (`gitlab_project_id`,
> `gitlab_mr_iid`) e idempotência por `(projeto, MR)`. Ver o "Histórico de revisão" da spec.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o núcleo SUAP que cria o `RelatorioIndividualTrabalho` (RIT) a partir de um MR do
GitLab, idempotente, exposto por endpoints ninja autenticados por token de máquina — reusando o estado
de rascunho nativo do PGD (`EM_CADASTRO_RIT`) e a validação nativa (envio mensal do RIT).

**Architecture:** Abordagem A enxuta do spec — SUAP é dono do estado e das regras. O próprio RIT carrega
a proveniência GitLab (2 campos nullable + unique parcial); uma camada de serviço (`pgd2/services.py`)
cria/atualiza o RIT reusando a regra do form manual; dois endpoints (`api/endpoints/pgd2.py`,
`TrustedAppAuth`) expõem listar-entregas / lançar-rit. Claude (Plano 2) e CI (Plano 3) só consomem.

**Tech Stack:** Django 5.2, `djtools.db.models` (ModelPlus/*Plus fields), django-ninja (`djtools.ninja.router` + `TrustedAppAuth`), pytest (`SuapAPITestCase` / fixtures `suap_data`, `suap_client`, `api_auth_mocks`).

**Spec:** `docs/specs/2026-05-29-pgd-execucao-gitlab-design.md`

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `pgd2/models.py` | 2 campos `gitlab_*` + `UniqueConstraint` parcial no `RelatorioIndividualTrabalho` (`models.py:8828`) | Modificar |
| `pgd2/migrations/XXXX_rit_gitlab_provenance.py` | Migração dos campos + constraint | Criar (gerada) |
| `pgd2/services.py` | `resolver_servidor_por_gitlab_username`, `get_entregas_disponiveis_para_servidor`, `lancar_rit_via_gitlab` | Criar |
| `api/schemas/pgd2.py` | Schemas ninja de request/response | Criar |
| `api/endpoints/pgd2.py` | Router + 2 endpoints | Criar |
| `suap/api.py:15` | Adicionar `'pgd2'` à lista de áreas | Modificar |
| `pgd2/tests/conftest.py` | Fixture `cadeia_rit_pgd2` (adesão→PIT→entrega) | Criar |
| `pgd2/tests/test_execucao_gitlab.py` | Testes de model + serviço | Criar |
| `api/tests/test_pgd2.py` | Testes dos endpoints | Criar |

**Decisão de teste (do spec):** testamos o contrato (mapeamento de campos, idempotência, autenticação, resolução `username→servidor`), não as regras internas do PGD. Onde o gate `pode_cadastrar_entrega_rit` exige o fluxo completo de homologação, os testes fazem `monkeypatch` desse método para isolar o código sob teste; há um teste dedicado que NÃO faz patch e verifica `PermissionDenied` quando o gate retorna `False`.

---

### Task 1: Campos de proveniência GitLab no RIT

**Files:**
- Modify: `pgd2/models.py` (campos no `RelatorioIndividualTrabalho`, linha 8828)
- Create: `pgd2/migrations/XXXX_rit_gitlab_provenance.py` (gerada)
- Test: `pgd2/tests/test_execucao_gitlab.py`

- [ ] **Step 1: Write the failing test**

Crie `pgd2/tests/test_execucao_gitlab.py`:

```python
import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError

from pgd2.models import RelatorioIndividualTrabalho


class TestRitProvenienciaGitLab:
    def test_cria_rit_com_proveniencia_gitlab(self, cadeia_rit_pgd2):
        rit = RelatorioIndividualTrabalho.objects.create(
            entrega_pit=cadeia_rit_pgd2.entrega_pit,
            titulo='Corrige bug no histórico',
            descricao='Ajuste descrito na issue #7.',
            tempo_executado=Decimal('3'),
            data_inicio=datetime.date.today(),
            data_fim=datetime.date.today(),
            gitlab_project_id=42,
            gitlab_mr_iid=7,
        )
        assert rit.gitlab_project_id == 42
        assert rit.gitlab_mr_iid == 7

    def test_unique_parcial_projeto_mr(self, cadeia_rit_pgd2):
        kwargs = dict(
            entrega_pit=cadeia_rit_pgd2.entrega_pit,
            descricao='d',
            tempo_executado=Decimal('1'),
            gitlab_project_id=42,
            gitlab_mr_iid=7,
        )
        RelatorioIndividualTrabalho.objects.create(titulo='a', **kwargs)
        with pytest.raises(IntegrityError):
            RelatorioIndividualTrabalho.objects.create(titulo='b', **kwargs)

    def test_rits_manuais_sem_gitlab_nao_colidem(self, cadeia_rit_pgd2):
        # ambos com gitlab_* NULL: a constraint parcial NÃO deve bloquear
        RelatorioIndividualTrabalho.objects.create(
            entrega_pit=cadeia_rit_pgd2.entrega_pit, titulo='m1', descricao='d', tempo_executado=Decimal('1')
        )
        RelatorioIndividualTrabalho.objects.create(
            entrega_pit=cadeia_rit_pgd2.entrega_pit, titulo='m2', descricao='d', tempo_executado=Decimal('1')
        )
        assert RelatorioIndividualTrabalho.objects.filter(gitlab_mr_iid__isnull=True).count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'gitlab_project_id'` (e/ou `fixture 'cadeia_rit_pgd2' not found`).

- [ ] **Step 3: Criar a fixture `cadeia_rit_pgd2`**

Crie `pgd2/tests/conftest.py`:

```python
import datetime
from decimal import Decimal

import pytest

from pgd2.models import (
    DocumentoAdesaoServidor,
    PeriodoPes,
    PeriodoPitRit,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoEntregas,
    SolicitacaoAdesaoServidor,
)


class CadeiaRit:
    def __init__(self, servidor, pit, entrega_pit):
        self.servidor = servidor
        self.pit = pit
        self.entrega_pit = entrega_pit


@pytest.fixture
def cadeia_rit_pgd2(suap_data):
    servidor = suap_data['servidor_a']
    inicio = datetime.date.today().replace(day=1)
    fim = inicio + datetime.timedelta(days=27)

    documento = DocumentoAdesaoServidor.objects.create(descricao='Regras de adesão ao PGD', data_inicio=inicio)
    adesao = SolicitacaoAdesaoServidor.objects.create(
        servidor=servidor,
        documento_adesao=documento,
        situacao=SolicitacaoAdesaoServidor.DEFERIDO,
        data_inicio=inicio,
    )
    periodo_pes = PeriodoPes.objects.create(
        titulo='PES mensal', data_inicio=inicio, data_fim=fim, data_prazo_solicitar_avaliacao_execucao=fim,
    )
    periodo_pit_rit = PeriodoPitRit.objects.create(
        periodo_pes=periodo_pes,
        titulo='PIT/RIT mensal',
        data_inicio=inicio,
        data_fim=fim,
        data_prazo_entrega_pit=fim,
        data_prazo_entrega_rit=fim,
        data_prazo_homologacao_pit=fim,
        data_prazo_homologacao_rit=fim,
    )
    pit = PlanoIndividualTrabalho.objects.create(
        adesao=adesao,
        periodo_pit_rit=periodo_pit_rit,
        data_inicio=inicio,
        data_fim=fim,
        regime_execucacao=PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
        percentual_teletrabalho=100,
        situacao=PlanoIndividualTrabalho.HOMOLOGADO,
        situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT,
    )
    entrega_pit = PlanoIndividualTrabalhoEntregas.objects.create(
        pit=pit,
        titulo='Executar entrega institucional',
        descricao='Trabalho planejado.',
        tempo_planejado=Decimal('8'),
        data_prazo=fim,
        homologado=True,
    )
    return CadeiaRit(servidor=servidor, pit=pit, entrega_pit=entrega_pit)
```

> **Verificar antes de codar:** confirme os nomes/constantes citados na fixture contra o código atual —
> `SolicitacaoAdesaoServidor.DEFERIDO`, `PlanoIndividualTrabalho.HOMOLOGADO`/`EM_CADASTRO_RIT`,
> `TRABALHO_TELETRABALHO_INTEGRAL`, e os campos obrigatórios de `PeriodoPes`/`PeriodoPitRit`. Ajuste a
> fixture ao schema real (a fixture é o ponto mais frágil deste plano).

- [ ] **Step 4: Implementar os campos + constraint no RIT**

Em `pgd2/models.py`, no `class RelatorioIndividualTrabalho` (linha 8828), acrescente os campos (após `anexo`) e a `Meta.constraints`. Garanta `from django.db.models import Q` disponível (ou use `models.Q` conforme o import do arquivo):

```python
    gitlab_project_id = models.PositiveIntegerFieldPlus('ID do projeto GitLab', null=True, blank=True, editable=False)
    gitlab_mr_iid = models.PositiveIntegerFieldPlus('IID do MR no GitLab', null=True, blank=True, editable=False)
```

Na `Meta` (mantendo `verbose_name`/`verbose_name_plural` existentes), adicione:

```python
        constraints = [
            models.UniqueConstraint(
                fields=['gitlab_project_id', 'gitlab_mr_iid'],
                condition=Q(gitlab_mr_iid__isnull=False),
                name='uniq_rit_gitlab_mr',
            )
        ]
```

> Se `PositiveIntegerFieldPlus` não existir em `djtools.db.models`, use `PositiveIntegerField`. Confirme o
> nome real no arquivo (o RIT já usa `DecimalFieldPlus`, `CharFieldPlus`, `DateFieldPlus`).

- [ ] **Step 5: Gerar a migração**

Run: `python manage.py makemigrations pgd2`
Expected: cria `pgd2/migrations/XXXX_*.py` com `AddField` (x2) + `AddConstraint`.
(Observação: sob pytest as migrações são ignoradas — `--no-migrations` — então os testes pegam o schema dos models; a migração é necessária para o banco real.)

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestRitProvenienciaGitLab -v`
Expected: PASS (3 testes).

- [ ] **Step 7: Commit**

```bash
git add pgd2/models.py pgd2/migrations/ pgd2/tests/conftest.py pgd2/tests/test_execucao_gitlab.py
git commit -m "feat(pgd2): proveniência GitLab no RIT (campos + unique parcial)"
```

---

### Task 2: Serviço `resolver_servidor_por_gitlab_username`

**Files:**
- Create: `pgd2/services.py`
- Test: `pgd2/tests/test_execucao_gitlab.py`

- [ ] **Step 1: Write the failing test**

Adicione a `pgd2/tests/test_execucao_gitlab.py`:

```python
from demandas.models import AnalistaDesenvolvedor
from pgd2 import services


class TestResolverServidor:
    def test_resolve_servidor_por_username_gitlab(self, cadeia_rit_pgd2):
        user = cadeia_rit_pgd2.servidor.get_user()
        AnalistaDesenvolvedor.objects.create(usuario=user, username_gitlab='dev.fulano', ativo=True)
        servidor = services.resolver_servidor_por_gitlab_username('dev.fulano')
        assert servidor == cadeia_rit_pgd2.servidor

    def test_username_inexistente_levanta_valueerror(self, db):
        with pytest.raises(ValueError):
            services.resolver_servidor_por_gitlab_username('nao.existe')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestResolverServidor -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgd2.services'`.

- [ ] **Step 3: Implementar o serviço**

Crie `pgd2/services.py`:

```python
from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from rh.models import Servidor


def resolver_servidor_por_gitlab_username(username_gitlab: str) -> Servidor:
    """Resolve o ``rh.Servidor`` a partir do username do GitLab.

    Args:
        username_gitlab: username do autor no GitLab.

    Returns:
        O servidor vinculado.

    Raises:
        ValueError: se não houver analista/desenvolvedor ativo com esse username,
            ou se o usuário não estiver vinculado a um servidor.
    """
    # Import local: evita acoplamento estático pgd2 -> demandas no carregamento do app.
    from demandas.models import AnalistaDesenvolvedor

    dev = AnalistaDesenvolvedor.objects.filter(username_gitlab=username_gitlab, ativo=True).first()
    if dev is None:
        raise ValueError(f'Nenhum analista/desenvolvedor ativo com username_gitlab={username_gitlab!r}.')
    servidor = dev.usuario.get_relacionamento()
    if not isinstance(servidor, Servidor):
        raise ValueError(f'Usuário {dev.usuario} não está vinculado a um servidor.')
    return servidor
```

> Confirme o nome do campo de vínculo em `AnalistaDesenvolvedor` (`usuario` vs `user`) e o método
> `get_relacionamento()` antes de assumir.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestResolverServidor -v`
Expected: PASS.

- [ ] **Step 5: Verificar grafo de dependências de módulos**

Run: `python manage.py module_dependencies --check --all`
Expected: PASS. Se reportar uma aresta nova `pgd2 -> demandas`, adicione `"demandas"` à lista de dependências de `pgd2` em `module_dependencies.json` e rode o comando de novo até passar.

- [ ] **Step 6: Commit**

```bash
git add pgd2/services.py pgd2/tests/test_execucao_gitlab.py module_dependencies.json
git commit -m "feat(pgd2): resolve servidor a partir do username do GitLab"
```

---

### Task 3: Serviço `get_entregas_disponiveis_para_servidor`

**Files:**
- Modify: `pgd2/services.py`
- Test: `pgd2/tests/test_execucao_gitlab.py`

- [ ] **Step 1: Write the failing test**

Adicione a `pgd2/tests/test_execucao_gitlab.py`:

```python
from pgd2.models import PlanoIndividualTrabalho


class TestEntregasDisponiveis:
    def test_lista_entregas_quando_gate_permite(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        entregas = services.get_entregas_disponiveis_para_servidor(cadeia_rit_pgd2.servidor)
        assert cadeia_rit_pgd2.entrega_pit in entregas

    def test_nao_lista_quando_gate_nega(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
        entregas = services.get_entregas_disponiveis_para_servidor(cadeia_rit_pgd2.servidor)
        assert entregas == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestEntregasDisponiveis -v`
Expected: FAIL — `AttributeError: module 'pgd2.services' has no attribute 'get_entregas_disponiveis_para_servidor'`.

- [ ] **Step 3: Implementar**

Adicione a `pgd2/services.py`:

```python
def get_entregas_disponiveis_para_servidor(servidor: Servidor) -> list:
    """Lista as ``PlanoIndividualTrabalhoEntregas`` em que o servidor pode lançar RIT agora.

    Percorre as adesões não canceladas do servidor, seus PITs, e — quando o PIT
    permite cadastrar RIT (validação básica) — coleta as entregas elegíveis a RIT
    (``get_entregas_pit_para_rit``: não canceladas e homologadas).
    """
    from pgd2.models import SolicitacaoAdesaoServidor

    user = servidor.get_user()
    resultado: list = []
    for adesao in SolicitacaoAdesaoServidor.objects.filter(servidor=servidor):
        for pit in adesao.get_pits():
            if pit.pode_cadastrar_entrega_rit(user, valida_apenas_o_basico=True):
                resultado.extend(pit.get_entregas_pit_para_rit())
    return resultado
```

> Confirme `adesao.get_pits()` (`models.py:2682`) e `pit.get_entregas_pit_para_rit()` (`models.py:4308`).
> **Decisão:** NÃO restringir ao período corrente — lista entregas de **todos os PITs abertos** (o servidor
> pode estar entregando para um mês não-corrente). O período corrente vira só anotação no endpoint
> (`eh_periodo_corrente`), pra skill usar de default quando a issue não tiver label de mês/ano.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestEntregasDisponiveis -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgd2/services.py pgd2/tests/test_execucao_gitlab.py
git commit -m "feat(pgd2): lista entregas elegíveis a RIT de um servidor"
```

---

### Task 4: Serviço `lancar_rit_via_gitlab` (idempotente)

**Files:**
- Modify: `pgd2/services.py`
- Test: `pgd2/tests/test_execucao_gitlab.py`

- [ ] **Step 1: Write the failing test**

Adicione a `pgd2/tests/test_execucao_gitlab.py`:

```python
from pgd2.models import RelatorioIndividualTrabalho


class TestLancarRitViaGitlab:
    def _dados(self, **over):
        dados = dict(
            titulo='Execução do MR !7',
            descricao='Trabalho entregue.',
            tempo_executado=Decimal('4'),
            perc_executada_em_teletrabalho=Decimal('50'),
            data_inicio=datetime.date.today(),
            data_fim=datetime.date.today(),
            quantidade_progresso=Decimal('100'),
        )
        dados.update(over)
        return dados

    def test_cria_rit_mapeando_campos(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)

        rit = services.lancar_rit_via_gitlab(
            cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7
        )

        assert isinstance(rit, RelatorioIndividualTrabalho)
        assert rit.titulo == 'Execução do MR !7'
        assert rit.tempo_executado == Decimal('4')
        # tempo_executada_em_teletrabalho = 50% de 4 = 2
        assert rit.tempo_executada_em_teletrabalho == Decimal('2')
        assert rit.gitlab_project_id == 42 and rit.gitlab_mr_iid == 7

    def test_idempotente_atualiza_mesmo_rit(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)

        rit1 = services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)
        rit2 = services.lancar_rit_via_gitlab(
            cadeia_rit_pgd2.entrega_pit, self._dados(tempo_executado=Decimal('6')), gitlab_project_id=42, gitlab_mr_iid=7
        )

        assert rit1.id == rit2.id
        assert rit2.tempo_executado == Decimal('6')
        assert RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=42, gitlab_mr_iid=7).count() == 1

    def test_permissao_negada_levanta_permissiondenied(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
        with pytest.raises(PermissionDenied):
            services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestLancarRitViaGitlab -v`
Expected: FAIL — `AttributeError: ... has no attribute 'lancar_rit_via_gitlab'`.

- [ ] **Step 3: Implementar**

Adicione a `pgd2/services.py`:

```python
def lancar_rit_via_gitlab(entrega_pit, dados: dict, *, gitlab_project_id: int, gitlab_mr_iid: int, request=None):
    """Cria/atualiza o ``RelatorioIndividualTrabalho`` a partir de um MR do GitLab.

    Idempotente por ``(gitlab_project_id, gitlab_mr_iid)``: se já existe RIT para esse MR e o mês
    continua em ``EM_CADASTRO_RIT``, atualiza-o; senão cria. Reusa a regra do form manual
    (cálculo do tempo em teletrabalho + ``calcular_pit``).

    Args:
        entrega_pit: ``PlanoIndividualTrabalhoEntregas`` inferida.
        dados: campos do RIT (titulo, descricao, tempo_executado, perc_executada_em_teletrabalho,
            data_inicio, data_fim, quantidade_progresso).
        gitlab_project_id: ID do projeto no GitLab.
        gitlab_mr_iid: IID do MR no GitLab.
        request: requisição HTTP, usada apenas para auditoria (quando ausente, é pulada).

    Returns:
        O ``RelatorioIndividualTrabalho`` criado/atualizado.

    Raises:
        PermissionDenied: se o PGD não permite cadastrar RIT nesta entrega agora
            (período fechado, mês já enviado, servidor errado).
    """
    from pgd2.models import RegistroAcaoPlanoIndividualTrabalho, RelatorioIndividualTrabalho

    pit = entrega_pit.pit
    servidor = pit.adesao.servidor
    user = servidor.get_user()

    if not pit.pode_cadastrar_entrega_rit(user, entrega_pit.id):
        raise PermissionDenied('Servidor não pode cadastrar RIT nesta entrega agora (período fechado, mês já enviado ou regra do PGD).')

    rit = RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=gitlab_project_id, gitlab_mr_iid=gitlab_mr_iid).first()
    if rit is None:
        rit = RelatorioIndividualTrabalho(gitlab_project_id=gitlab_project_id, gitlab_mr_iid=gitlab_mr_iid)

    rit.entrega_pit = entrega_pit
    rit.titulo = dados.get('titulo')
    rit.descricao = dados.get('descricao', '')
    rit.tempo_executado = dados.get('tempo_executado')
    rit.perc_executada_em_teletrabalho = dados.get('perc_executada_em_teletrabalho') or 0
    rit.data_inicio = dados.get('data_inicio')
    rit.data_fim = dados.get('data_fim')
    rit.quantidade_progresso = dados.get('quantidade_progresso') or 0

    if rit.perc_executada_em_teletrabalho and rit.tempo_executado:
        rit.tempo_executada_em_teletrabalho = (rit.perc_executada_em_teletrabalho / 100) * rit.tempo_executado
    rit.save()

    pit.calcular_pit()

    if request is not None:
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request,
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA_RIT,
            pit=pit,
            obs=f'Lançado automaticamente a partir do MR !{gitlab_mr_iid}.',
        )

    return rit
```

> **Trade-off (do spec):** este upsert sobrescreve o RIT a cada chamada para o mesmo MR — inclusive
> edições manuais. Se isso incomodar, restrinja a 2ª gravação aos campos não tocados pelo servidor, ou
> só crie (sem atualizar) quando já existir. Decidir aqui.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py::TestLancarRitViaGitlab -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add pgd2/services.py pgd2/tests/test_execucao_gitlab.py
git commit -m "feat(pgd2): lança RIT a partir do MR (idempotente, com guarda de permissão)"
```

---

### Task 5: Schemas ninja

**Files:**
- Create: `api/schemas/pgd2.py`

- [ ] **Step 1: Implementar os schemas**

Crie `api/schemas/pgd2.py`:

```python
import datetime
from decimal import Decimal

from ninja import Schema


class EntregaDisponivelSchema(Schema):
    id: int
    titulo: str
    descricao: str
    pit_id: int
    # Conteúdo da Entrega PES — é contra isto que a skill casa a issue (significado da categoria).
    pes_titulo: str | None = None
    pes_descricao: str | None = None
    pes_criterios_avaliacao: str | None = None
    metrica: int | None = None  # 1=PERCENTUAL, 2=QUANTIDADE — guia o quantidade_progresso do RIT
    meta: Decimal | None = None
    # Período do PIT — a skill casa o label de mês/ano da issue (ex.: '2026-06') com data_inicio/data_fim.
    periodo_titulo: str
    pit_data_inicio: datetime.date | None = None
    pit_data_fim: datetime.date | None = None
    eh_periodo_corrente: bool = False


class EntregasDisponiveisOutput(Schema):
    entregas: list[EntregaDisponivelSchema]


class LancarRitInput(Schema):
    gitlab_username: str
    gitlab_project_id: int
    gitlab_mr_iid: int
    entrega_pit_id: int
    titulo: str
    descricao: str
    tempo_executado: Decimal
    perc_executada_em_teletrabalho: Decimal = Decimal('0')
    data_inicio: datetime.date | None = None
    data_fim: datetime.date | None = None
    quantidade_progresso: Decimal = Decimal('1')  # 1 por MR (um MR = um trabalho); soma vira o total da categoria


class RitLancadoOutput(Schema):
    rit_id: int
    entrega_pit_id: int
    gitlab_mr_iid: int
    criado: bool
```

- [ ] **Step 2: Verificar import**

Run: `python manage.py shell -c "from api.schemas import pgd2; print(pgd2.LancarRitInput.__name__)"`
Expected: imprime `LancarRitInput` sem erro.

- [ ] **Step 3: Commit**

```bash
git add api/schemas/pgd2.py
git commit -m "feat(api): schemas ninja para execução do PGD via GitLab"
```

---

### Task 6: Endpoint `entregas-disponiveis` + registro do router

**Files:**
- Create: `api/endpoints/pgd2.py`
- Modify: `suap/api.py:15`
- Test: `api/tests/test_pgd2.py`

- [ ] **Step 1: Write the failing test**

Crie `api/tests/test_pgd2.py`:

```python
from decimal import Decimal

import pytest

from comum.tests import SuapAPITestCase
from demandas.models import AnalistaDesenvolvedor
from pgd2.models import PlanoIndividualTrabalho


class APIPgd2EntregasTestCase(SuapAPITestCase):
    def _mapear_dev(self, servidor, username='dev.fulano'):
        return AnalistaDesenvolvedor.objects.create(usuario=servidor.get_user(), username_gitlab=username, ativo=True)

    def test_entregas_disponiveis_ok(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        self._mapear_dev(cadeia_rit_pgd2.servidor)
        response = self.client.get(
            '/api/pgd2/execucao-gitlab/entregas-disponiveis/?gitlab_username=dev.fulano',
            user=cadeia_rit_pgd2.servidor.get_user(),
        )
        assert response.status_code == 200, response.content
        ids = [e['id'] for e in response.json()['entregas']]
        assert cadeia_rit_pgd2.entrega_pit.id in ids

    def test_entregas_disponiveis_username_inexistente_404(self, cadeia_rit_pgd2):
        response = self.client.get(
            '/api/pgd2/execucao-gitlab/entregas-disponiveis/?gitlab_username=nao.existe',
            user=cadeia_rit_pgd2.servidor.get_user(),
        )
        assert response.status_code == 404, response.content
```

(Observação: `SuapAPITestCase` injeta as fixtures `suap_data` e `api_auth_mocks` na classe; `cadeia_rit_pgd2` e `monkeypatch` são fixtures de função do pytest, recebidas como argumento do método.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q api/tests/test_pgd2.py::APIPgd2EntregasTestCase -v`
Expected: FAIL — 404 da rota inexistente, pois `api/endpoints/pgd2.py` ainda não existe e `'pgd2'` não está registrado.

- [ ] **Step 3: Criar o router e o endpoint**

Crie `api/endpoints/pgd2.py`:

```python
from ninja import Router

from api.schemas.pgd2 import EntregasDisponiveisOutput
from djtools.ninja.auth import TrustedAppAuth
from djtools.ninja.router import get
from pgd2 import services

router = Router(tags=['PGD2'])
router.api_url_prefix = 'pgd2'


@get(
    router,
    'execucao-gitlab/entregas-disponiveis/',
    auth=TrustedAppAuth(),
    response=EntregasDisponiveisOutput,
    summary='Lista entregas do PIT em que o servidor pode lançar RIT',
)
def entregas_disponiveis(request, gitlab_username: str):
    from pgd2.models import PeriodoPitRit

    try:
        servidor = services.resolver_servidor_por_gitlab_username(gitlab_username)
    except ValueError as erro:
        return 404, {'message': str(erro)}

    periodo_corrente = PeriodoPitRit.get_periodo_pit_atual()
    entregas = services.get_entregas_disponiveis_para_servidor(servidor)
    resultado = []
    for e in entregas:
        pes = e.entrega_pes  # pode ser None
        resultado.append(
            {
                'id': e.id,
                'titulo': e.titulo,
                'descricao': e.descricao or '',
                'pit_id': e.pit_id,
                'pes_titulo': pes.titulo if pes else None,
                'pes_descricao': pes.descricao if pes else None,
                'pes_criterios_avaliacao': pes.criterios_avaliacao if pes else None,
                'metrica': pes.metrica if pes else None,
                'meta': pes.meta if pes else None,
                'periodo_titulo': e.pit.periodo_pit_rit.titulo,
                'pit_data_inicio': e.pit.data_inicio,
                'pit_data_fim': e.pit.data_fim,
                'eh_periodo_corrente': bool(periodo_corrente and e.pit.periodo_pit_rit_id == periodo_corrente.id),
            }
        )
    return {'entregas': resultado}
```

> Confirme a assinatura de `get`/`post` em `djtools/ninja/router.py` e o exemplo em
> `api/endpoints/terminais.py` antes de assumir a forma do decorator.

- [ ] **Step 4: Registrar a área `pgd2`**

Em `suap/api.py:15`, adicione `'pgd2'` ao fim da lista:

```python
for area in ['rh', 'ensino', 'ti', 'midia', 'administracao', 'pesquisa', 'institucional', 'eventos', 'extensao', 'terminais', 'pgd2']:
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest -q api/tests/test_pgd2.py::APIPgd2EntregasTestCase -v`
Expected: PASS (2 testes).

- [ ] **Step 6: Commit**

```bash
git add api/endpoints/pgd2.py suap/api.py api/tests/test_pgd2.py
git commit -m "feat(api): endpoint GET entregas-disponiveis do PGD via GitLab"
```

---

### Task 7: Endpoint `lancar-rit` (upsert do RIT)

**Files:**
- Modify: `api/endpoints/pgd2.py`
- Test: `api/tests/test_pgd2.py`

- [ ] **Step 1: Write the failing test**

Adicione a `api/tests/test_pgd2.py`:

```python
from pgd2.models import RelatorioIndividualTrabalho


class APIPgd2LancarRitTestCase(SuapAPITestCase):
    def _payload(self, cadeia, **over):
        dados = dict(
            gitlab_username='dev.fulano',
            gitlab_project_id=42,
            gitlab_mr_iid=7,
            entrega_pit_id=cadeia.entrega_pit.id,
            titulo='Execução do MR !7',
            descricao='Trabalho entregue.',
            tempo_executado='4',
            perc_executada_em_teletrabalho='50',
            quantidade_progresso='100',
        )
        dados.update(over)
        return dados

    def test_upsert_cria_e_atualiza(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        AnalistaDesenvolvedor.objects.create(usuario=cadeia_rit_pgd2.servidor.get_user(), username_gitlab='dev.fulano', ativo=True)

        r1 = self.client.post('/api/pgd2/execucao-gitlab/lancar-rit/', data=self._payload(cadeia_rit_pgd2), user=cadeia_rit_pgd2.servidor.get_user())
        assert r1.status_code == 200, r1.content
        rid = r1.json()['rit_id']
        assert r1.json()['criado'] is True

        r2 = self.client.post('/api/pgd2/execucao-gitlab/lancar-rit/', data=self._payload(cadeia_rit_pgd2, titulo='Título atualizado'), user=cadeia_rit_pgd2.servidor.get_user())
        assert r2.status_code == 200, r2.content
        assert r2.json()['rit_id'] == rid  # mesmo (projeto, MR) => mesmo RIT
        assert r2.json()['criado'] is False
        assert RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=42, gitlab_mr_iid=7).count() == 1

    def test_entrega_de_outro_servidor_403(self, cadeia_rit_pgd2, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        servidor_b = self.dict_initial_data['servidor_b']
        AnalistaDesenvolvedor.objects.create(usuario=servidor_b.get_user(), username_gitlab='outro.dev', ativo=True)
        response = self.client.post(
            '/api/pgd2/execucao-gitlab/lancar-rit/',
            data=self._payload(cadeia_rit_pgd2, gitlab_username='outro.dev'),
            user=servidor_b.get_user(),
        )
        assert response.status_code == 403, response.content

    def test_lancar_sem_rascunho_mes_enviado_403(self, cadeia_rit_pgd2, monkeypatch):
        # gate nega (mês já enviado): NÃO faz patch de pode_cadastrar_entrega_rit
        AnalistaDesenvolvedor.objects.create(usuario=cadeia_rit_pgd2.servidor.get_user(), username_gitlab='dev.fulano', ativo=True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
        response = self.client.post('/api/pgd2/execucao-gitlab/lancar-rit/', data=self._payload(cadeia_rit_pgd2), user=cadeia_rit_pgd2.servidor.get_user())
        assert response.status_code == 403, response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q api/tests/test_pgd2.py::APIPgd2LancarRitTestCase -v`
Expected: FAIL — rota `lancar-rit/` não existe (404).

- [ ] **Step 3: Implementar o endpoint**

Atualize os imports do topo de `api/endpoints/pgd2.py` e acrescente o handler:

```python
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from api.schemas.pgd2 import EntregasDisponiveisOutput, LancarRitInput, RitLancadoOutput
from djtools.ninja.router import get, post
from pgd2.models import PlanoIndividualTrabalhoEntregas, RelatorioIndividualTrabalho
```

```python
@post(
    router,
    'execucao-gitlab/lancar-rit/',
    auth=TrustedAppAuth(),
    response=RitLancadoOutput,
    summary='Cria/atualiza o RIT (em EM_CADASTRO_RIT) a partir de um MR',
)
def lancar_rit(request, payload: LancarRitInput):
    entrega_pit = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=payload.entrega_pit_id)
    try:
        servidor = services.resolver_servidor_por_gitlab_username(payload.gitlab_username)
    except ValueError as erro:
        return 404, {'message': str(erro)}

    if entrega_pit.pit.adesao.servidor_id != servidor.id:
        return 403, {'message': 'A entrega não pertence ao servidor informado.'}

    ja_existia = RelatorioIndividualTrabalho.objects.filter(
        gitlab_project_id=payload.gitlab_project_id, gitlab_mr_iid=payload.gitlab_mr_iid
    ).exists()

    dados = dict(
        titulo=payload.titulo,
        descricao=payload.descricao,
        tempo_executado=payload.tempo_executado,
        perc_executada_em_teletrabalho=payload.perc_executada_em_teletrabalho,
        data_inicio=payload.data_inicio,
        data_fim=payload.data_fim,
        quantidade_progresso=payload.quantidade_progresso,
    )
    try:
        rit = services.lancar_rit_via_gitlab(
            entrega_pit, dados, gitlab_project_id=payload.gitlab_project_id, gitlab_mr_iid=payload.gitlab_mr_iid, request=request
        )
    except PermissionDenied as erro:
        return 403, {'message': str(erro)}

    return {'rit_id': rit.id, 'entrega_pit_id': rit.entrega_pit_id, 'gitlab_mr_iid': rit.gitlab_mr_iid, 'criado': not ja_existia}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q api/tests/test_pgd2.py::APIPgd2LancarRitTestCase -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Rodar a suíte completa do backend novo + pre-commit**

Run: `pytest -q pgd2/tests/test_execucao_gitlab.py api/tests/test_pgd2.py`
Expected: PASS (todos).

Run: `ruff format . && ruff check . --fix --unsafe-fixes`
Expected: sem alterações pendentes / sem erros.

- [ ] **Step 6: Commit**

```bash
git add api/endpoints/pgd2.py api/tests/test_pgd2.py
git commit -m "feat(api): endpoint POST lancar-rit (cria RIT do MR, idempotente)"
```

---

## Planos seguintes (esboço — cada um vira seu próprio plano)

### Plano 2 — MCP + skill do Claude (fase PR)
- Nova tool MCP `lancar_rit_execucao_gitlab` em `suap-mcp/src/suap_mcp/gitlab/{models,tools}.py` (espelha `upsert_mr_suap_meta`), que chama `POST /api/pgd2/execucao-gitlab/lancar-rit/`.
- Tool/uso de `GET entregas-disponiveis` para alimentar a inferência.
- Skill do Claude no momento do PR: lê issue+diff, infere a entrega, estima horas, mostra resumo, confirma com o usuário, chama a tool.
- Critério de pronto: ao pedir o PR, um RIT em `EM_CADASTRO_RIT` aparece no SUAP chaveado por `(projeto, MR)`.

### Plano 3 — Bordas de CI (opcional, leve)
- Job/comentário no merge: como o RIT já existe, apenas comenta "RIT lançado no PGD — entrega «Y», Zh." (confirmação).
- Limpeza de RIT órfão: ao fechar MR **sem merge**, remover o RIT se ainda em `EM_CADASTRO_RIT` (mesmo caminho de `remover_entrega_rit` + `calcular_pit`). Pode ser job CI ou rotina/cron.
- (Reestimação no merge foi adiada; reintroduzível depois lendo o RIT por `(projeto, MR)` e atualizando enquanto `EM_CADASTRO_RIT`.)
- Critério de pronto: MR mergeado recebe comentário de confirmação; MR fechado sem merge não deixa RIT órfão.
