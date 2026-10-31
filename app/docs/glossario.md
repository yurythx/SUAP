# Glossário SUAP

Termos de domínio com sentido específico no projeto. Use sempre o termo canônico em commits, issues, identificadores e documentação. Termos rejeitados são listados para evitar drift.

Quando precisar de um termo que não está aqui, é sinal de uma de duas coisas: (1) está inventando vocabulário que o projeto não usa — reconsidere; ou (2) há lacuna real — adicione com `/grill-with-docs` ou em PR dedicado.

---

## Identidade

### PessoaFisica
A entidade física (CPF + nome). Mora em `comum.models`. Não confundir com `User`: uma `PessoaFisica` pode ter zero ou múltiplos `User`s associados via `Vinculo`.

### Vinculo
A projeção de uma `PessoaFisica` em um papel dentro do SUAP (aluno, servidor, externo, prestador). É o ponto canônico de identidade para permissões, auditoria e ownership. **Sempre prefira `Vinculo` a `User`** quando estiver decidindo "quem fez/pode fazer".

- **Termo rejeitado:** "Perfil". Reservado a outro conceito histórico em `djtools`.

### Setor
Unidade organizacional do IFRN (campus, departamento, coordenação). Tem hierarquia (`setor_pai`). Servidores são *lotados* em setores; processos *tramitam* entre setores. Não confundir com `Campus` (subset).

### Servidor / Docente / Técnico-administrativo
Subtipos de `Vinculo` originados do SIAPE. "Docente" e "Técnico" são distinções **funcionais**; não criar models separadas.

### Aluno
`Vinculo` com cadastro acadêmico (`Matricula`). Tem `Curso`, `Matriz Curricular`, `Polo` (EaD), `Situacao`.

---

## Acadêmico

### Matricula
Vínculo de aluno com um curso/turma. Identifica o aluno academicamente. Tem prefixo de campus.

### Matriz Curricular
Plano de disciplinas + estrutura (`tipo_avaliacao`, regime, carga horária). Um aluno tem uma `matriz`. Não confundir com **Curso** (entidade administrativa pai).

### Diario
Registro de uma disciplina ofertada em um período letivo, com docente(s) e turma. Faltas, notas e abonos vivem ligados a um `Diario`.

- **Termo rejeitado:** "Turma do diário". Use só `Diario`.

### Calendario Academico
Período letivo (semestre/ano) com `data_inicio` e `data_fim`. Filtra `Diarios` válidos.

### Requerimento
Pedido formal do aluno (matrícula em disciplina, trancamento, aproveitamento de estudos, justificativa de falta, etc.). Tem `tipo` (constantes em `Requerimento.TIPO_*_CHOICES`) e ciclo deferir/indeferir/arquivar.

### Procedimento
Operação acadêmica que materializa um `Requerimento` aprovado (criar matrícula, registrar abono, etc.). Implementação em `edu/forms/procedimentos.py` e `edu/models/procedimentos.py`.

### AbonoFaltas (Justificativa de Falta)
`Requerimento` específico para justificar ausências. Avaliado em `/edu/avaliar_abono_faltas/{pk}/`. Quando deferido, gera `SolicitacaoReposicaoAtividade`.

### Aproveitamento de Estudos
`Requerimento` em que o aluno solicita reconhecimento de disciplinas já cursadas.

---

## Processo Eletrônico

### Processo
Documento administrativo formal que tramita entre `Setor`es. Identificado por `numero_processo` (ex.: `23421.002970.2026-31`). Pode ser apensado a outros (`get_processos_apensados`).

### Tramite
Movimento de um `Processo` entre setores ou vínculos. Cada `Processo` tem um `ultimo_tramite` (`OneToOneField`). **Atenção:** acessar `processo.ultimo_tramite` pode levantar `Tramite.DoesNotExist` se o FK aponta para registro removido — `hasattr` **não** captura.

### TramiteBarramento
Tramite externo, via PEN/Gov. Tem `status` próprio (`STATUS_RECUSADO`, `STATUS_RECEBIDO`, etc.).

### Caixa de Entrada / Saída
Visões de processos pendentes em um setor — não são tabelas, são consultas (`esta_na_caixa_entrada`, `esta_na_caixa_saida`).

### Interessado
`Vinculo` listado como parte interessada em um processo. Permite acessos diferenciados.

---

## Infra / convenções

### ModelPlus
Base de modelo em `djtools.db.models`. **Sempre** use no lugar de `models.Model`. Detalhes em ADR-0001.

### djtools
App-framework interno do SUAP. Define `ModelPlus`, `ModelAdminPlus`, forms, tables, PDF, middleware. Tudo em `PRE_INSTALLED_APPS_SUAP`. Não é dependência externa; vive no monorepo.

### LPS
"Linha de Produto de Software" — mecanismo de override por instituição. Cada app pode ter `lps/{LPS}/urls.py` etc. para variantes. Pouco usado fora do IFRN.

### Tarefa assíncrona
Função decorada/agendada com Celery. Mora em `<app>/tasks.py` (executadas pelo worker) ou `cron/` (agendadas). Sempre tratar inputs como não-confiáveis.

### httprr
Helper do `djtools` (`djtools.utils.response`) para resposta HTTP redirecionada com mensagem flash. Usado em views como `return httprr(url, 'mensagem', 'success')`.

### sync (manage.py sync)
Bootstrap completo: `migrate` + `initial_data` + `sync_permissions` + `collectstatic` + `carregar_apis`. **Não** é só migração.

### sync_permissions
Comando que aplica `permissions.yaml` de cada app. Idempotente.

### menu.yaml / permissions.yaml
Arquivos por-app que declaram navegação e grupos de permissão. Carregados em runtime — não confundir com `Meta.permissions`.

---

## Termos de fluxo de trabalho

### MR
Merge Request (GitLab). Sempre referenciar por `!<iid>`. Formato padrão via skill `mr-format`.

### Skill (de agente)
Documento `SKILL.md` que orienta um agente automático (Claude Code, opencode) a executar um fluxo (ex.: `sentry-fix`, `mr-format`). Fonte única em `.agents/skills/`; o Claude Code as enxerga por symlink em `.claude/skills/`.

### Sentry Issue
Erro agregado em Sentry, com short-id `SUAP-XXX`. Referenciar em commits/MRs como `Refs: SUAP-XXX`.

---

## Termos rejeitados (não usar)

- "Funcionário" → use **Servidor**.
- "Disciplina ofertada" → use **Diario**.
- "Tramite interno/externo" como entidades separadas → existe um único `Tramite`, com flag `eh_tramite_externo` e relação `tramite_barramento`.
- "Perfil de usuário" como sinônimo de `Vinculo` → `Perfil` tem significado próprio em `djtools`.
