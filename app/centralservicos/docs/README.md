# Central de Serviços

> Central de Serviços (service desk / help desk) do SUAP: permite abrir, atender e
> acompanhar chamados de serviço para as diversas áreas de atuação da instituição.

## Visão geral

A Central de Serviços é o módulo de gestão de chamados (tickets) do SUAP. Servidores,
alunos e prestadores de serviço solicitam serviços ou reportam incidentes através de um
catálogo de serviços; os chamados são roteados para grupos de atendimento, atendidos por
atendentes, escalados entre níveis e finalizados com avaliação. Inspirado em práticas de
ITIL (Requisição/Incidente, SLA, base de conhecimento), o módulo centraliza o suporte
operacional da instituição em uma única ferramenta. Apoia-se também numa Base de
Conhecimento (artigos e FAQ) para padronizar e acelerar as resoluções.

## Responsabilidades

- Manter o catálogo de serviços (Áreas, Grupos de Serviço, Categorias, Serviços) e a
  estrutura de atendimento (Centros e Grupos de Atendimento, com hierarquia de níveis).
- Gerenciar o ciclo de vida do chamado: abertura, atribuição, atendimento, escalonamento/
  retorno entre níveis, reclassificação, suspensão, resolução, fechamento, reabertura e
  cancelamento (máquina de estados via `django_fsm`).
- Controlar o SLA (prazo de atendimento) de cada chamado, marcando estouros e notificando
  atendentes e responsáveis.
- Registrar a comunicação do chamado (comentários públicos, notas internas), anexos,
  interessados e o histórico de situações.
- Manter a Base de Conhecimento (artigos privados/públicos/sigilosos) com fluxo de
  supervisão, correção, avaliação e publicação como FAQ.
- Permitir tarefas vinculadas a chamados (workflow operacional interno) e a criação de
  processo eletrônico a partir de um chamado.

**Fora de escopo:** o cadastro de pessoas e vínculos (`rh`/`comum`), o cadastro
patrimonial de bens (`patrimonio`), a tramitação de processos/documentos
(`processo_eletronico`/`documento_eletronico`) e o cadastro de Áreas de Atuação
(`comum.AreaAtuacao`) — a Central de Serviços apenas referencia essas entidades.

## Atores e papéis

Derivados de `permissions.yaml`, dos decorators das views e de papéis relacionais
(FK/M2M de função nos models). Papéis relacionais são marcados como _derivados_.

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Solicitante (Servidor / Aluno / Prestador de Serviço) | grupos `Servidor` / `Aluno` / `Prestador de Serviço` (`add_chamado`, `view_chamado`, `close_chamado`, `reopen_chamado`, `cancel_chamado`, `add_comment`, `add_attachement`, `add_interested`) | Abrir chamado, comentar, anexar, adicionar interessados, fechar/reabrir/cancelar os próprios chamados |
| Atendente da Central de Serviços | grupo `Atendente da Central de Serviços` (`change_chamado`, `solve_chamado`, `add_auto_atribuicao`, `suspend_chamado`, `reclassify_chamado`, `add_internal_note`, `list_chamados_suporte`) | Assumir/atender chamados, colocar em atendimento, resolver, suspender, reclassificar, adicionar nota interna, vincular tarefas, criar processo |
| Responsável pelo Grupo de Atendimento | _derivado_ — `GrupoAtendimento.responsaveis` (M2M) | Fechar/reabrir/reclassificar chamados do grupo, escalar/retornar, editar o grupo |
| Gestor da Central de Serviços | grupo `Gestor da Central de Serviços` (cadastros de serviço/atendimento/BC) | Manter catálogo de serviços, centros/grupos, monitoramentos, perguntas de avaliação, tarefas; vinculado automaticamente a quem é `GestorAreaServico` |
| Gestor de Área de Serviço | _derivado_ — `GestorAreaServico` (FK `gestor`+`area`) | Gerir o catálogo/atendimento da(s) área(s) onde é gestor; editar grupos de atendimento da área |
| Supervisor / Publicador / Contribuinte da Base de Conhecimento | grupos homônimos (`review_baseconhecimento`, `add_public_baseconhecimento`, `add_active_baseconhecimento`, `pode_unificar_baseconhecimento`) | Criar/editar/revisar/aprovar/unificar artigos da Base de Conhecimento |
| Auditor | grupo `Auditor` (`view_chamado`, `list_chamados_suporte`, `pode_ver_indicadores`, `view_tarefa`) | Visualizar chamados, indicadores e tarefas (somente leitura) |
| Administrador da Central de Serviços | grupo `centralservicos Administrador` | Acesso amplo a chamados, cadastros e Áreas de Atuação (`comum.areaatuacao`); pode editar a área de um artigo |

## Estrutura interna

SUAP é Django clássico; a maior parte das regras de negócio vive nos **métodos dos
models** (fat models), com destaque para `Chamado`.

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `centralservicos/models.py` (arquivo único, 23 models) | Catálogo, atendimento, `Chamado` (FSM `django_fsm`), Base de Conhecimento, Tarefas |
| Views | `centralservicos/views.py` | ≈70 views funcionais (abertura, atendimento, escalonamento, reclassificação, BC, tarefas, indicadores, dashboard) |
| URLs | `centralservicos/urls.py` | Rotas sob `/centralservicos/` |
| API | _N/A_ | Não há `api.py` (django-ninja); endpoints AJAX são views funcionais com `JsonResponse` |
| Forms | `centralservicos/forms.py` | `ModelFormPlus`/`FormPlus` e _form factories_ (formulários parametrizados por contexto) |
| Admin | `centralservicos/admin.py` | `ModelAdminPlus` para todos os cadastros; `Chamado`/`Tarefa` com ações customizadas |
| Tasks | `centralservicos/beat.py` + `management/commands/` | Sem Celery; agendamento via `beat` chamando management commands |
| Commands | `centralservicos/management/commands/` | SLA, notificações diárias, sincronização de atendentes, relatórios, init de patrimônio |
| Outros | `utils.py` (`Notificar`), `widgets.py`, `templatetags/`, `signals` (em `models.py`) | Notificações por e-mail; sincronização de grupos via signals |

## Endpoints principais

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| GET | `/centralservicos/listar_area_servico/` | `listar_area_servico` | `view_chamado` + `change_chamado` |
| GET/POST | `/centralservicos/abrir_chamado/<servico_id>/` | `abrir_chamado` | `add_chamado` |
| GET | `/centralservicos/chamado/<chamado_id>/` | `visualizar_chamado` | `view_chamado` + `change_chamado` |
| POST | `/centralservicos/auto_atribuir_chamado/<chamado_id>/` | `auto_atribuir_chamado` | `add_auto_atribuicao` |
| POST | `/centralservicos/colocar_em_atendimento/<chamado_id>/` | `colocar_em_atendimento` | `view_chamado` + `change_chamado` |
| GET/POST | `/centralservicos/resolver_chamado/<chamado_id>/` | `resolver_chamado` | `solve_chamado` |
| GET/POST | `/centralservicos/fechar_chamado/<chamado_id>/` | `fechar_chamado` | `close_chamado` |
| POST | `/centralservicos/escalar_atendimento_chamado/<chamado_id>/` | `escalar_atendimento_chamado` | `change_atendimentoatribuicao` |
| GET/POST | `/centralservicos/reclassificar_chamado/<chamado_id>/` | `reclassificar_chamado` | `reclassify_chamado` |
| GET/POST | `/centralservicos/criar_processo_de_chamado/<chamado_id>/` | `criar_processo_de_chamado` | grupo `Atendente da Central de Serviços` + `processo_eletronico.add_processo` |
| GET | `/centralservicos/meus_chamados/` | `meus_chamados` | `view_chamado` + `change_chamado` |
| GET | `/centralservicos/listar_chamados_suporte/` | `listar_chamados_suporte` | `list_chamados_suporte` |
| GET | `/centralservicos/dashboard/` | `dashboard` | `change_chamado` |
| GET | `/centralservicos/indicadores/` | `indicadores` | `pode_ver_indicadores` |
| GET | `/centralservicos/baseconhecimento/` | `baseconhecimento_listar_area_servico` | `view_baseconhecimento` + `add_chamado` |
| GET | `/centralservicos/monitoramento/<token>/` | `monitoramento` (painel público por token) | _N/A — acesso por token_ |

> ⚠️ REVISAR: a view de monitoramento (`/monitoramento/<token>/`) não tem decorator de
> permissão visível na assinatura; o acesso parece controlado pelo token. Confirmar se há
> verificação adicional.

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `Chamado` | Ticket de serviço; máquina de estados (`django_fsm`) | FK `servico`, `aberto_por`/`requisitante`/`interessado` (User), `campus`, `patrimonio` |
| `Servico` | Item do catálogo (Requisição ou Incidente), com SLA | FK `area`, `grupo_servico`; M2M `centros_atendimento`, `publico_direcionado` |
| `GrupoAtendimento` | Equipe de atendimento por campus/centro, com hierarquia de níveis | FK `grupo_atendimento_superior` (auto), `centro_atendimento`, `campus`; M2M `atendentes`, `responsaveis` |
| `AtendimentoAtribuicao` | Atribuição do chamado a um grupo/atendente (histórico de roteamento) | FK `chamado`, `grupo_atendimento`, `atribuido_para` |
| `HistoricoStatus` | Registro de cada mudança de situação, com tempos (resposta/atendimento/suspensão) | FK `chamado`, `usuario`; O2O `comunicacao`; M2M `bases_conhecimento` |
| `Comunicacao` | Comentário público ou nota interna do chamado | FK `chamado`, `remetente`; M2M `bases_conhecimento` |
| `BaseConhecimento` | Artigo da base de conhecimento (privado/público/sigiloso) | FK `area`; M2M `grupos_atendimento`, `servicos` |
| `TarefaChamado` | Tarefa operacional vinculada a um chamado | FK `tarefa`, `chamado`, `responsavel` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/).

## Regras de negócio chave

- **Máquina de estados do chamado** (`models.py`, classe `Chamado` + `StatusChamado`):
  transições com `@transition` do `django_fsm` (resolver, suspender, reabrir, escalar,
  cancelar, colocar em atendimento, colocar em aberto, fechar). Os wrappers (`resolver_chamado`,
  `colocar_em_atendimento`, etc.) gravam `HistoricoStatus`, calculam tempos e notificam.
- **Roteamento na abertura** (`Chamado.save`): ao criar o chamado, o sistema cria a
  `AtendimentoAtribuicao` inicial para o grupo de primeiro nível
  (`GrupoAtendimento.get_grupo_primeiro_nivel`) e o `HistoricoStatus` inicial; falha se não
  houver grupo de atendimento para a UO/centro.
- **Cálculo do SLA** (`Chamado.calcula_data_limite_sem_feriados_fds`): a `data_limite_atendimento`
  é o `aberto_em + sla_em_horas` do serviço, descontando fins de semana e feriados.
- **Reclassificação** (`Chamado.reclassificar`): muda serviço/centro/campus; se mudar o
  centro/campus, cancela a atribuição atual, re-roteia para o 1º nível do novo centro e volta
  o chamado para Aberto.
- **Resolução condicionada a tarefas** (`Chamado.pode_resolver_info`): só o atendente
  resolve, e não pode haver tarefas vinculadas pendentes — regra também na transição FSM, então
  nenhuma via (resolução em conjunto, criação de processo) a contorna; cancelar o chamado cancela
  as tarefas pendentes.
- **Supervisão da Base de Conhecimento** (`BaseConhecimento.save`): se quem atualiza não tem
  `add_active_baseconhecimento`, o artigo entra em `supervisao_pendente=True` e notifica os
  supervisores.
- **Sincronização de grupos via signals** (`models.py`): salvar `GestorAreaServico` adiciona
  o usuário ao grupo `Gestor da Central de Serviços`; alterar `atendentes`/`responsaveis` de
  um `GrupoAtendimento` (m2m_changed) sincroniza o grupo `Atendente da Central de Serviços`.
- **Fechamento automático**: chamados Resolvidos há ≥ 90 dias são fechados pelo command
  diário (`centralservicos_notificacoes_diarias.fechar_chamados_automaticamente`).

## Jobs / Tasks Celery

Não há tasks Celery (`@task`/`@shared_task`). O processamento agendado é feito por
**management commands** registrados no `beat` (`centralservicos/beat.py` → `django-celery-beat`).

| Command (agendado via beat) | Decorator | Dispara | Idempotência |
|---|---|---|---|
| `centralservicos_verifica_sla_estourado` | `BaseCommandPlus` | beat, de hora em hora | Sim — `.exclude(sla_estourado=True)` antes de marcar |
| `centralservicos_notificacoes_diarias` | `BaseCommandPlus` | beat, diário (04:07) | Sim — notifica só `notificacao_enviada=False`; fecha só Resolvidos ≥ 90 dias (sai do estado) |
| `centralservicos_sincronizar_atendentes` | `BaseCommandPlus` | manual / sync | Sim — reconcilia grupo a partir de vínculos |
| `centralservicos_relatorios_xls` | `BaseCommandPlus` | manual | N/A — geração de relatório |
| `centralservicos_inicializar_patrimonio` | `BaseCommandPlus` | manual (migração de dados) | Inicializa FK `patrimonio` a partir do legado `numero_patrimonio` |
| `centralservicos_forcar_atribuicao` / `_configurarDIAAC` / `_verifica_anexos` | `BaseCommandPlus` | manual | — |

> Notificação assíncrona real é delegada a `djtools.utils.send_notification` (e-mail/push),
> não a tasks próprias do módulo.

## Dependências

- **Módulos internos:** `comum` (User, AreaAtuacao, Publico, Comentario, Configuracao),
  `rh` (UnidadeOrganizacional), `patrimonio` (Inventario) — confirmados em
  `module_dependencies.json`.
- **Framework SUAP:** `djtools` (`ModelPlus`, `ModelAdminPlus`, forms, `layout`, `send_notification`,
  `generate_pdf`, `BaseCommandPlus`), `beat` (agendamento).
- **Bibliotecas:** `django_fsm` (máquina de estados do `Chamado`), `django-reversion`
  (versionamento da Base de Conhecimento).
- **Integrações condicionais (`in settings.INSTALLED_APPS`):** `processo_eletronico`
  (criar processo a partir do chamado), `erros` (reportar erro a partir do chamado).

## Configuração

| Origem | Chave | Uso |
|---|---|---|
| `settings` | `SITE_URL`, `DEFAULT_FROM_EMAIL`, `DEBUG` | URLs em notificações; remetente de e-mail |
| `settings` | `ACCESS_LOG_MODULES` (inclui `centralservicos`) | Habilita log de acesso para o módulo |
| `comum.Configuracao` | `comum` / `instituicao` | Nome da instituição no extrato PDF do chamado (criação de processo) |

## Como testar

```bash
pytest centralservicos/tests/
```

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
