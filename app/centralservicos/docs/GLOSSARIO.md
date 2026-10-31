# Glossário — Central de Serviços

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| Chamado | Ticket de serviço aberto por um solicitante; tem ciclo de vida com situações controladas por máquina de estados. | `models.py` (`Chamado`) |
| Serviço | Item do catálogo que pode ser solicitado; é uma Requisição (REQ) ou um Incidente (INC), com um SLA em horas. | `models.py` (`Servico`) |
| Requisição (REQ) | Tipo de serviço: pedido de algo a ser provido (vs. incidente). | `Servico.TIPO_REQUISICAO` |
| Incidente (INC) | Tipo de serviço: relato de algo que não está funcionando. | `Servico.TIPO_INCIDENTE` |
| Grupo de Serviço / Categoria de Serviço | Agrupadores do catálogo de serviços (categoria é um nível dentro de grupo). | `GrupoServico`, `CategoriaServico` |
| Centro de Atendimento | Unidade lógica responsável pelo atendimento de uma área; pode ser local (por campus) ou global. | `CentroAtendimento` |
| Grupo de Atendimento | Equipe que atende chamados em um centro/campus; organiza-se em níveis (superior/inferior) e tem atendentes e responsáveis. | `GrupoAtendimento` |
| Nível de atendimento | Posição do grupo na hierarquia (1º nível atende primeiro; escalar sobe, retornar desce). | `GrupoAtendimento.grupo_atendimento_superior`, `eh_primeiro_nivel` |
| Atendente | Usuário vinculado a um grupo de atendimento que atende chamados. | `GrupoAtendimento.atendentes` (M2M), `Chamado.eh_atendente` |
| Responsável (chefe do atendimento) | Usuário responsável por um grupo de atendimento; pode fechar/reabrir/reclassificar/escalar. | `GrupoAtendimento.responsaveis` (M2M) |
| Atribuição | Vínculo do chamado a um grupo (e opcionalmente atendente); registra escalonamento/retorno/cancelamento. | `AtendimentoAtribuicao` |
| Auto-atribuição / Assumir | Atendente do grupo assume o chamado para si. | `views.auto_atribuir_chamado`, `Chamado.pode_assumir` |
| Escalar / Retornar | Subir o chamado ao grupo de atendimento superior / devolvê-lo ao inferior. | `Chamado.escalar_atendimento`, `retornar_atendimento` |
| Reclassificar | Trocar serviço/centro/campus do chamado, re-roteando o atendimento. | `Chamado.reclassificar` |
| Suspender | Pausar o atendimento (contabiliza tempo de suspensão, não conta no SLA ultrapassado). | `Chamado.suspender_chamado`, `get_tempo_total_suspenso` |
| Resolver / Fechar | Resolver = atendente conclui; Fechar = solicitante/responsável confirma e avalia (após resolvido). | `Chamado.resolver_chamado`, `fechar_chamado`, `pode_resolver_info` |
| Reabrir | Voltar um chamado resolvido para atendimento (Reaberto). | `Chamado.reabrir_chamado`, `pode_reabrir` |
| SLA | Prazo-limite de atendimento (`data_limite_atendimento`), derivado do `sla_em_horas` do serviço, descontando fins de semana e feriados. | `Servico.sla_em_horas`, `Chamado.calcula_data_limite_sem_feriados_fds` |
| SLA estourado | Chamado ativo cujo prazo-limite já passou; sinalizado e notificado. | `Chamado.sla_estourado`, `get_chamados_com_sla_estourado` |
| Histórico de Situações | Linha do tempo das mudanças de status, com tempos de resposta/atendimento/suspensão. | `HistoricoStatus` |
| Comunicação | Mensagem do chamado: Comentário (público aos interessados) ou Nota Interna (entre atendentes). | `Comunicacao` (`TIPO_COMENTARIO`/`TIPO_NOTA_INTERNA`) |
| Interessado / Requisitante / Outros Interessados | Quem é afetado pelo chamado / quem solicitou / acompanhantes adicionais (M2M). | `Chamado.interessado`, `requisitante`, `outros_interessados` |
| Grupo de Interessados | Conjunto pré-cadastrado de usuários que pode ser adicionado de uma vez como interessados. | `GrupoInteressado` |
| Base de Conhecimento (BC) | Artigos com solução padronizada; podem ser privados, públicos (FAQ) ou sigilosos. | `BaseConhecimento` |
| FAQ | Artigos públicos da BC, visíveis fora do círculo de atendentes (Perguntas Frequentes). | `BaseConhecimento.VISIBILIDADE_PUBLICA`, `get_bases_conhecimento_faq` |
| Supervisão pendente / Necessita correção | Estados de revisão de um artigo da BC antes de ficar disponível para uso. | `BaseConhecimento.supervisao_pendente`, `necessita_correcao` |
| Tarefa (cadastro) | Modelo prévio de tarefa associado a um serviço. | `Tarefa` |
| Tarefa de chamado | Tarefa operacional vinculada a um chamado específico, com situação e responsável. | `TarefaChamado` |
| Monitoramento | Painel (acessível por token) que acompanha chamados de grupos de atendimento. | `Monitoramento`, `views.monitoramento` |
| Resposta Padrão | Texto pré-definido do atendente para agilizar comunicações por situação. | `RespostaPadrao` |
| Gestor de Área de Serviço | Usuário responsável pela gestão do catálogo/atendimento de uma Área de Atuação. | `GestorAreaServico` |
| Meio de abertura | Como o chamado foi aberto: Web, Telefone, E-mail, Pessoalmente. | `Chamado.MEIO_ABERTURA_CHOICES` |

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| SLA | Service Level Agreement (Acordo de Nível de Serviço) | Prazo de atendimento do chamado |
| REQ | Requisição | Tipo de serviço |
| INC | Incidente | Tipo de serviço |
| BC | Base de Conhecimento | Artigos de solução / FAQ |
| FAQ | Frequently Asked Questions (Perguntas Frequentes) | Artigos públicos da BC |
| UO | Unidade Organizacional (campus) | `rh.UnidadeOrganizacional`, campo `campus` |
| FSM | Finite State Machine (Máquina de Estados Finita) | `django_fsm` no `Chamado` |
| DIAAC | _Designação não expandida no código_ | `centralservicos_configurarDIAAC` (command de configuração) |

> ⚠️ REVISAR: a sigla **DIAAC** aparece no nome do command `centralservicos_configurarDIAAC`
> mas não é expandida no código — confirmar o significado (provável setor/unidade).

## Entidades ↔ termo de negócio

> Mapeia o nome técnico do modelo para o conceito de negócio que ele representa
> (quando divergem).

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `AtendimentoAtribuicao` | Atribuição / roteamento do chamado | Cada registro é uma atribuição a um grupo; histórico de escalonamento/retorno |
| `HistoricoStatus` | Histórico de Situações | `verbose_name` "Histórico do Situações" (typo legado no código) |
| `Comunicacao` | Comentário ou Nota Interna | Um único model com dois tipos (`tipo`) |
| `AvaliaBaseConhecimento` | Avaliação de artigo da BC | Nota de 1 a 5 por pergunta de avaliação |
| `PerguntaAvaliacaoBaseConhecimento` | Pergunta da avaliação da BC | Critério de avaliação por área |
| `TarefaChamado` / `Tarefa` | Tarefa do chamado / Cadastro de tarefa | `Tarefa` é o modelo prévio; `TarefaChamado` é a instância vinculada |
| `GestorAreaServico` | Gestor da Área do Serviço | Tabela de associação gestor↔área |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
