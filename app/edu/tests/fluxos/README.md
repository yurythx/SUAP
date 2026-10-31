# edu/tests/fluxos — testes de fluxo (alto nível, DB-backed)

Suíte de **fluxos de ponta a ponta** do edu: exercitam o caminho real
`view → ORM → banco → response` (matrícula, lançamento de notas, matrícula online,
fechamento de período, emissão de diploma/certificado, ENADE, importação Q-Acadêmico),
ao contrário dos testes unitários DB-free em `edu/tests/test_*.py` (que cobrem lógica pura).

Estes arquivos são a migração **fiel e completa** dos antigos workflows legados
`_suap_edu_legacy_<x>.py` (que foram removidos junto com o agregador
`test_suap_edu_legacy.py`). Nenhum passo/validação foi descartado — apenas relocados
para a localização canônica `fluxos/`, com nomes `test_fluxo_*.py`.

## Fluxos

| Arquivo | Cobre |
|---|---|
| `test_fluxo_matricula_online_seriado.py` | matrícula online (pós seriado): pedido, validações (choque de horário, pré/co-requisitos), comprovante, processamento, notas |
| `test_fluxo_matricula_online_credito.py` | matrícula online (pós crédito): validações de qtd mín/máx de disciplinas, choque, processamento |
| `test_fluxo_fic.py` | FIC: matrícula → notas → relançamento de etapa → fechamento de período (com/sem pendência/forçamento) → diploma → mensagem → estatística |
| `test_fluxo_graduacao.py` | graduação: matrícula → ciclo ENADE (convocação, critérios, situação) |
| `test_fluxo_edu_pos.py` | pós-graduação completo + evasão em lote e desfazer procedimento |
| `test_fluxo_certificado_enem.py` | certificação ENEM: configuração (planilha INEP), solicitação, atendimento, rejeição |
| `test_fluxo_qedu.py` | importação Q-Acadêmico e ativação de curso importado |

## Infra reusada (NÃO são testes — não apagar)

O cenário acadêmico é montado por ≈10 helpers da `EduTestCase` que dirigem os wizards
reais via `self.client`. Essa maquinaria permanece em `edu/tests/`:

- `test_suap_edu_legacy_base.py` — `EduTestCase` (base com todos os helpers).
- `_suap_edu_legacy_matricula_online.py` — `MatriculaOnlineBaseWorkflowTestCase` (tem `fluxo_inicial`).
- `_suap_edu_legacy_pos.py` — `PosGraduacaoBaseWorkflowTestCase`.

Estes arquivos não têm métodos `test_` (são infraestrutura); `EduTestCase` também é
reusado por `edu/tests/test_estatistica_view.py` e `gestao/tests/test_dimensional.py`.

## Custo / como rodar

Cada fluxo dispara dezenas de requests reais ⇒ **≈30–60 s por teste** (custo inerente de
integração: HTTP real através do stack Django + construção do cenário). O schema completo
(≈100 apps, `--no-migrations`) é construído uma vez; use `--reuse-db`.

**Rode em paralelo** com `pytest-xdist` (`-n 4 --dist loadscope`): ≈225 s → ≈162 s (1.4×).
Não adianta aumentar muito os workers — cada worker é uma sessão separada que reconstrói o
cenário (`suap_data`/`_auto_setup`), então `-n 7` fica pior por contenção; `-n 4` é o ponto
ótimo aqui. (xdist está em `pyproject.toml` como dep de dev.)

```bash
# Postgres de teste efêmero (ver suap/settings_test.py)
docker run --rm -d --name suap-test-db -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 \
  -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements

DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
  DJANGO_SETTINGS_MODULE=suap.settings_test \
  uv run pytest --reuse-db -n 4 --dist loadscope edu/tests/fluxos/
```

> `--dist loadscope` mantém cada classe (= cada fluxo) num mesmo worker, respeitando o
> `suap_data` class-scoped. O global `addopts` do repo **não** foi alterado de propósito
> (xdist não é seguro para toda a suíte); a paralelização é opt-in só para `fluxos/`.

## Como adicionar um fluxo

1. Subclasse o workflow base que monta o cenário desejado (`MatriculaOnlineBaseWorkflowTestCase`,
   `PosGraduacaoBaseWorkflowTestCase`, ou `EduTestCase` direto).
2. Replique o `_auto_setup` (fixture autouse que chama `Base._auto_setup.__wrapped__(self, suap_data)`
   e fixa `initial_data` do curso).
3. Num método `test_*`, monte os passos do fluxo via os helpers herdados (dentro do
   `freeze_time` necessário) e adicione asserts de domínio.
4. Mantenha o teste independente e com nome que descreva o que verifica.
