# Bordas de merge/fechamento — Lançamento de execuções do PGD via GitLab (Plano 3 de 3)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development ou superpowers:executing-plans. Steps em checkbox (`- [ ]`). **Depende dos Planos 1 e 2** implantados (o RIT é criado no PR; aqui tratamos só as bordas pós-PR).

**Goal:** Fechar as duas bordas do ciclo do MR:
1. **RIT órfão** — MR **fechado sem merge** deixa um RIT em `EM_CADASTRO_RIT` que conta no PIT indevidamente. Removê-lo automaticamente.
2. **Confirmação no merge** (opcional) — comentar no MR, no merge, qual RIT foi lançado.

**Restrição de plataforma (decisiva):** o GitLab **não dispara pipeline no fechamento de MR sem merge** (só em `merge_request_event` de abertura/atualização/reabertura e em `push`). Logo a limpeza de órfãos **não pode** ser um job de CI — vive como **cron no SUAP** (management command + Celery beat), que consulta o estado do MR via `djtools/utils/gitlab.py`. O comentário no merge, esse sim, cabe num job de CI disparado por `push` na `master`.

**Spec:** `docs/specs/2026-05-29-pgd-execucao-gitlab-design.md` (seção "Bordas de merge/fechamento")
**Planos anteriores:** `...-backend.md` (Plano 1), `...-mcp-skill.md` (Plano 2)

---

## Referências de código (verificadas)

- `djtools/utils/gitlab.py` — wrapper GitLab do SUAP: `access_token()`, `base_url()`, `headers()`, `create_branch()` etc. (sem `get_merge_request` ainda — Task 1 adiciona).
- `pgd2/management/commands/` — padrão de command (ex.: `corrige_situacao_rit.py`, `monitoramento_pgd2.py`).
- `pgd2/beat.py` — agendamento Celery beat do pgd2 (registrar a tarefa periódica aqui).
- `pgd2/views.py:3752` (`remover_entrega_rit`) — caminho de remoção: `RelatorioIndividualTrabalho.objects.filter(...).delete()` + `pit.calcular_pit()`.
- `pgd2/models.py:4071` — `EM_CADASTRO_RIT`; RIT tem `gitlab_project_id`/`gitlab_mr_iid` (Plano 1).
- `.gitlab-ci.yml:181` (`.opencode-skill`) e `bin/ci/opencode-skill.sh` — execução headless de skill no CI (`<skill> <MR_IID> <PROJECT_ID> <SERVER_URL> <SUAP_BOT_TOKEN> ...`).

---

# Parte 3B — Limpeza de RIT órfão (SUAP cron) — núcleo do plano

### Task 1: Helper `get_merge_request` no wrapper GitLab

**Files:**
- Modify: `djtools/utils/gitlab.py`
- Test: `djtools/tests/test_gitlab_utils.py` (criar se não existir; senão, `pgd2/tests/test_descarte_orfaos.py` mocka direto)

- [ ] **Step 1: Implementar o helper**

Adicione a `djtools/utils/gitlab.py` (reusa `base_url()`, `headers()`, `access_token()` existentes):

```python
def get_merge_request(project_id: int, mr_iid: int) -> dict:
    """Retorna os dados de um MR (inclui ``state``: opened/closed/merged/locked).

    Args:
        project_id: ID numérico do projeto no GitLab.
        mr_iid: IID do MR no projeto.

    Returns:
        Dicionário JSON do MR.
    """
    import requests

    url = f'{base_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}'
    response = requests.get(url, headers=headers(), timeout=30)
    response.raise_for_status()
    return response.json()
```

> Confirme como `base_url()`/`headers()` montam a URL e o token (algumas funções do arquivo já chamam `/api/v4/...`). Espelhe o padrão real (ex.: se existe um `_api_v4()` helper, use-o).

- [ ] **Step 2: Commit**

```bash
git add djtools/utils/gitlab.py
git commit -m "feat(djtools): get_merge_request no wrapper GitLab (lê state do MR)"
```

---

### Task 2: Management command `descartar_rits_gitlab_orfaos`

**Files:**
- Create: `pgd2/management/commands/descartar_rits_gitlab_orfaos.py`
- Test: `pgd2/tests/test_descarte_orfaos.py`

- [ ] **Step 1: Write the failing test**

Crie `pgd2/tests/test_descarte_orfaos.py` (usa a fixture `cadeia_rit_pgd2` do Plano 1):

```python
from decimal import Decimal

import pytest
from django.core.management import call_command

from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho


@pytest.fixture
def _rit_gitlab(cadeia_rit_pgd2):
    return RelatorioIndividualTrabalho.objects.create(
        entrega_pit=cadeia_rit_pgd2.entrega_pit,
        titulo='Execução do MR !7',
        descricao='Resolve #7',
        tempo_executado=Decimal('4'),
        gitlab_project_id=42,
        gitlab_mr_iid=7,
    )


class TestDescarteOrfaos:
    def test_remove_rit_de_mr_fechado_sem_merge(self, cadeia_rit_pgd2, _rit_gitlab, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'closed'})

        call_command('descartar_rits_gitlab_orfaos')

        assert not RelatorioIndividualTrabalho.objects.filter(id=_rit_gitlab.id).exists()

    def test_mantem_rit_de_mr_merged(self, cadeia_rit_pgd2, _rit_gitlab, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'merged'})

        call_command('descartar_rits_gitlab_orfaos')

        assert RelatorioIndividualTrabalho.objects.filter(id=_rit_gitlab.id).exists()

    def test_mantem_rit_de_mr_aberto(self, cadeia_rit_pgd2, _rit_gitlab, monkeypatch):
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'opened'})

        call_command('descartar_rits_gitlab_orfaos')

        assert RelatorioIndividualTrabalho.objects.filter(id=_rit_gitlab.id).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q pgd2/tests/test_descarte_orfaos.py -v`
Expected: FAIL — `Unknown command: 'descartar_rits_gitlab_orfaos'`.

- [ ] **Step 3: Implementar o command**

Crie `pgd2/management/commands/descartar_rits_gitlab_orfaos.py` (espelhe o cabeçalho/estilo de `corrige_situacao_rit.py`):

```python
from django.core.management.base import BaseCommand

from djtools.utils import gitlab
from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho


class Command(BaseCommand):
    help = 'Remove RITs lançados via GitLab cujo MR foi fechado sem merge (órfãos em EM_CADASTRO_RIT).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas lista, não remove.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        # Só candidatos: têm proveniência GitLab E o RIT do mês ainda está editável.
        candidatos = RelatorioIndividualTrabalho.objects.filter(
            gitlab_mr_iid__isnull=False,
            entrega_pit__pit__situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT,
        ).select_related('entrega_pit__pit')

        removidos = 0
        for rit in candidatos:
            try:
                mr = gitlab.get_merge_request(rit.gitlab_project_id, rit.gitlab_mr_iid)
            except Exception as erro:  # noqa: BLE001 — rede; loga e segue
                self.stderr.write(f'MR {rit.gitlab_project_id}!{rit.gitlab_mr_iid}: erro ao consultar ({erro}); pulando.')
                continue

            if mr.get('state') == 'closed':  # 'merged'/'opened' não são órfãos
                pit = rit.entrega_pit.pit
                self.stdout.write(f'Removendo RIT {rit.id} (MR {rit.gitlab_project_id}!{rit.gitlab_mr_iid} fechado sem merge).')
                if not dry_run:
                    rit.delete()
                    pit.calcular_pit()
                removidos += 1

        self.stdout.write(self.style.SUCCESS(f'{"(dry-run) " if dry_run else ""}{removidos} RIT(s) órfão(s) processado(s).'))
```

> `state == 'closed'` = fechado sem merge; MR mergeado tem `state == 'merged'`. Confirme esses valores na API do GitLab da instância.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q pgd2/tests/test_descarte_orfaos.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add pgd2/management/commands/descartar_rits_gitlab_orfaos.py pgd2/tests/test_descarte_orfaos.py
git commit -m "feat(pgd2): command que remove RITs órfãos (MR fechado sem merge)"
```

---

### Task 3: Agendar o cron (Celery beat)

**Files:**
- Modify: `pgd2/beat.py`

- [ ] **Step 1: Registrar a tarefa periódica**

Em `pgd2/beat.py`, espelhando as tarefas existentes, adicione uma entrada que rode o command diariamente (ex.: `call_command('descartar_rits_gitlab_orfaos')` dentro de uma `@shared_task`, agendada via `crontab`). Confirme o padrão exato do arquivo (alguns usam `PeriodicTask`/`CrontabSchedule`, outros decorators) e siga-o.

- [ ] **Step 2: Verificar import/registro**

Run: `python manage.py shell -c "import pgd2.beat"` (sem erro) e, se o projeto listar tarefas, confirme que a nova aparece.

- [ ] **Step 3: Commit**

```bash
git add pgd2/beat.py
git commit -m "feat(pgd2): agenda limpeza diária de RITs órfãos do GitLab"
```

---

# Parte 3A — Comentário de confirmação no merge (opcional)

> Valor menor (o RIT já foi criado no PR, com o servidor presente). Implemente só se a equipe quiser o aviso no MR. Requer um endpoint de leitura + tool MCP + skill + job de CI.

### Task 4 (opcional): endpoint de leitura `rit-do-mr`

**Files:**
- Modify: `api/endpoints/pgd2.py`, `api/schemas/pgd2.py`
- Test: `api/tests/test_pgd2.py`

- [ ] Endpoint `GET .../execucao-gitlab/rit-do-mr?gitlab_project_id&gitlab_mr_iid` (`TrustedAppAuth`) → `{ rit_id, situacao_rit, entrega_titulo, tempo_executado }` ou 404 se não houver RIT para o MR. Lê `RelatorioIndividualTrabalho` por `(gitlab_project_id, gitlab_mr_iid)`. Teste: existe → 200 com dados; não existe → 404. (Mesmo padrão das Tasks 6-8 do Plano 1.)

### Task 5 (opcional): tool MCP `get_rit_do_mr_pgd2`

**Files:** `suap-mcp` — `modules/pgd2/{client,models,tools}.py`, `server.py`, `tests/test_pgd2_tools.py`

- [ ] Tool read espelhando `get_entregas_disponiveis_pgd2` (Plano 2 Task A2): chama o endpoint `rit-do-mr`, retorna `{ rit_id, situacao_rit, entrega_titulo, tempo_executado }` (ou `None`). `readOnlyHint: True`. Teste com `respx`.

### Task 6 (opcional): skill `pgd-rit-merge` + job de CI

**Files:**
- Create: `.agents/skills/pgd-rit-merge/SKILL.md` (+ symlink `.claude/skills/`)
- Modify: `.gitlab-ci.yml`, `bin/ci/opencode-skill.sh` (se precisar resolver MR do commit de merge)

- [ ] **Skill `pgd-rit-merge`:** recebe MR_IID + PROJECT_ID; chama `get_rit_do_mr_pgd2`:
  - RIT existe → comenta no MR (`post_gitlab_mr_comment`): *"RIT #<id> lançado no PGD — entrega «<titulo>», <h>h. Lembre de revisar e enviar o RIT do mês."*
  - Sem RIT (404) → comenta lembrando o lançamento manual.
- [ ] **Job de CI** disparado por **push na `master`** (`$CI_PIPELINE_SOURCE == 'push' && $CI_COMMIT_BRANCH == 'master'`): resolve o MR a partir do commit de merge — `GET $CI_API_V4_URL/projects/$CI_PROJECT_ID/repository/commits/$CI_COMMIT_SHA/merge_requests` (pega o IID) — e chama `bin/ci/opencode-skill.sh pgd-rit-merge <MR_IID> <PROJECT_ID> ...`. Se o commit não tiver MR associado, encerra silenciosamente (commit direto). `allow_failure: true`.

> Alternativa mais simples (sem skill/LLM): um job shell puro que chama os endpoints com `curl` e posta o comentário via API GitLab. Mais barato e determinístico para um texto fixo.

---

## Critérios de pronto

- **3B (núcleo):** ao fechar um MR **sem merge** que tinha RIT lançado, a próxima rodada do cron remove o RIT e o `calcular_pit` ajusta o total — sem RIT órfão inflando o PIT. MR mergeado/aberto não é tocado.
- **3A (opcional):** ao mergear um MR com RIT, o MR recebe o comentário de confirmação; sem RIT, recebe lembrete de lançamento manual.

## Trade-offs / notas

- O cron tem **latência** (roda 1×/dia): o RIT órfão persiste até a próxima execução. Aceitável — o servidor revê no envio do mês de qualquer forma; pode-se aumentar a frequência se incomodar.
- **Reestimação no merge** (se o diff cresceu no review) segue **fora de escopo** (decisão do spec). Reintroduzível depois: a tool `lancar_rit_execucao_gitlab` já é idempotente por `(projeto, MR)`, então um job de merge poderia reestimar e regravar o mesmo RIT enquanto `EM_CADASTRO_RIT`.
