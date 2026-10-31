# pgd2

> Módulo de gestão do Programa de Gestão 2 — PGD (antigo PGD 1/IFRN). Gerencia o ciclo
> completo de adesão, planos setoriais (PES), planos individuais (PIT), relatórios (RIT)
> e monitoramento de servidores participantes, além da integração com a API nacional do
> PGD.

## Visão geral

O módulo `pgd2` implementa o **Programa de Gestão 2** do SUAP, substituto do legado
PGD1. Ele cobre todo o fluxo de vida de um servidor no programa: desde a solicitação de
adesão, passando pela elaboração e aprovação de Planos de Entregas Setoriais (PES),
Planos Individuais de Trabalho (PIT) e Relatórios Individuais de Trabalho (RIT), até o
desligamento e monitoramento contínuo. Também realiza o envio periódico de dados
consolidados para a API externa do governo federal (API PGD).

## Responsabilidades

- Gerenciar adesão e desligamento de servidores no PGD
- Gerir Planos de Entregas Setoriais (PES): cadastro, aprovação, avaliação e execução
- Gerir Planos Individuais de Trabalho (PIT): cadastro, aprovação e homologação
- Gerir Relatórios Individuais de Trabalho (RIT): elaboração, aprovação e homologação
- Controlar distribuição de horas entre atividades presenciais e teletrabalho
- Monitorar servidores com pendências e acionar desligamento automático
- Enviar dados à API PGD nacional (v1 e v2)
- Notificar chefes e servidores sobre pendências

**Fora de escopo:** PGD legado (PGD1) — migração unidirecional; cadastro de servidores
(no módulo `rh`); auth (no `djtools`/`comum`); geração de diário oficial (no
`processo_eletronico`/`documento_eletronico`).

## Atores e papéis

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Servidor PGD | Sem grupo específico; vinculado via `SolicitacaoAdesaoServidor` | Criar PIT, elaborar RIT, solicitar adesão, visualizar pendências |
| Chefe imediato | _Derivado_ — cargo/função no `rh` (`setores_que_sou_chefe_direto_hoje`) | Aprovar/reprovar PIT, homologar RIT, analisar PES |
| Comissão PGD (sistêmica) | `gestao_pgd2_comissao_sistemica` | Gerenciar PES/PIT/RIT de qualquer setor, configurar períodos |
| Comissão PGD (local) | `gestao_pgd2_comissao_local` | Gerenciar PES/PIT/RIT do seu setor de atuação |
| Gestão PGD | `gestao_pgd2` | Relatórios gerenciais, visão geral de participantes, desligamento em massa |
| API PGD (sistema externo) | _N/A — autenticação via token_ | Consumir dados via `api_pgd2.py`/`api_pgd2_v2.py` endpoints |

> ⚠️ REVISAR: papel "Chefe imediato" é relacional (derivado de vínculo funcional no
> módulo `rh`), não é grupo do `permissions.yaml`.

## Estrutura interna

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `pgd2/models.py` | ≈46 modelos: adesão, PES, PIT, RIT, comissão, logs, monitoramento |
| Views | `pgd2/views.py` | ≈100+ views funcionais: CRUD de PES/PIT/RIT, relatórios, APIs |
| URLs | `pgd2/urls.py` | Rotas sob `/pgd2/` |
| API | `pgd2/api_pgd2.py`, `pgd2/api_pgd2_v2.py` | Endpoints Django-Ninja (v1 legada, v2 atual) |
| Forms | `pgd2/forms.py` | `ModelFormPlus` para PES/PIT/RIT/adesão |
| Admin | `pgd2/admin.py` | `ModelAdminPlus` registrados para ≈20 modelos |
| Tasks | `pgd2/tasks.py` | task de relatório de desligamento |
| Commands | `pgd2/management/commands/` | 11 comandos: sincronização, monitoramento, notificação, envio API |
| Outros | `utils.py`, `monitoramento.py`, `pendencias_alertas.py`, `notificacoes.py` | Utilitários de domínio, motor de monitoramento, cálculo de pendências |

## Endpoints principais

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| GET | `/pgd2/meu_pgd/` | `servidor_pgd_pgd2` | `@login_required` |
| GET | `/pgd2/meu_pgd/<matricula>/` | `servidor_pgd_pgd2` | `@login_required` |
| GET/POST | `/pgd2/solicitar_adesao/` | `solicitar_adesao` | `@login_required` |
| GET/POST | `/pgd2/cadastrar_pit/` | `cadastrar_pit` | `@login_required` |
| GET | `/pgd2/visualizar_pit/<pit_id>/` | `visualizar_pit` | `@login_required` |
| POST | `/pgd2/aprovar_pit/<pit_id>/` | `aprovar_pit` | `@login_required` |
| POST | `/pgd2/homologar_pit/<pit_id>/` | `homologar_pit` | `@login_required` |
| GET | `/pgd2/visualizar_rit/<pit_id>/` | `visualizar_rit` | `@login_required` |
| POST | `/pgd2/aprovar_rit/<pit_id>/` | `aprovar_rit` | `@login_required` |
| POST | `/pgd2/homologar_rit/<pit_id>/` | `homologar_rit` | `@login_required` |
| GET/POST | `/pgd2/visualizar_pes/<pes_id>/` | `visualizar_pes` | `@login_required` |
| POST | `/pgd2/aprovar_pes/<pes_id>/` | `aprovar_pes` | `@login_required` |
| GET | `/pgd2/monitoramento_servidores/` | `monitoramento_servidores` | `@login_required` |
| GET | `/pgd2/listar_servidores_api_pgd2/` | `listar_servidores_api_pgd2` | Público (API) |

> ⚠️ REVISAR: permissões exatas por view não mapeadas (decorators variam entre
> `@login_required`, `@permission_required` e verificações relacionais).

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `SolicitacaoAdesaoServidor` | Pedido de adesão do servidor ao PGD | FK `servidor` (rh), `chefe` (rh) |
| `DesligamentoPgdServidor` | Desligamento do servidor do PGD | FK `solicitacao_adesao` |
| `PlanoEntregasSetorial` (PES) | Plano de entregas do setor | FK `setor` (rh), `periodo_pes` |
| `PlanoEntregasSetorialEntregas` | Entrega definida no PES | FK `plano_entregas_setorial` |
| `PeriodoPes` | Período/ano de referência do PES | — |
| `PlanoIndividualTrabalho` (PIT) | Plano individual do servidor | FK `solicitacao_adesao`, `setor` (rh) |
| `PlanoIndividualTrabalhoEntregas` | Entrega vinculada ao PIT | FK `pit`, `entrega_pes` |
| `PlanoIndividualTrabalhoPresencial` | Registro de trabalho presencial no PIT | FK `pit` |
| `PlanoIndividualTrabalhoAtendimento` | Registro de teletrabalho/atendimento no PIT | FK `pit` |
| `RelatorioIndividualTrabalho` (RIT) | Relatório de execução do PIT | FK `pit` |
| `RelatorioIndividualTrabalhoDistribuicaoHoras` | Distribuição de horas entre atividades no RIT | FK `rit` |
| `ComissaoPGD` | Membros da comissão de gestão do PGD | FK `servidor` (rh), FK `setor` (rh) |
| `ParticipantePgd` | Vínculo servidor-setor no PGD | FK `solicitacao_adesao`, FK `setor` (rh) |
| `LogApi` | Registro de envio à API PGD | FK `servidor` (rh) |
| `MonitoramentoServidor` | Regra/estado de monitoramento do servidor | FK `solicitacao_adesao` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/).

## Regras de negócio chave

- **Adesão obrigatória:** servidor precisa de solicitação aprovada + documento de adesão para criar PIT
- **PES precede PIT:** entregas do PIT são vinculadas a entregas do PES do setor
- **PIT → RIT:** cada PIT gera exatamente um RIT; só é possível elaborar RIT após PIT homologado
- **Distribuição de horas:** horas entre presencial e teletrabalho são distribuídas no RIT, com validação de carga horária do servidor
- **Monitoramento:** servidores com pendências (PIT/RIT atrasados) são monitorados; após período configurado, desligamento automático
- **Envio API PGD:** dados de PES/PIT/RIT/participantes são enviados periodicamente à API nacional; v2 é a versão ativa com concorrência e `APIExternaService`

## Jobs / Tasks Celery

| Task | Decorator | Dispara | Idempotência |
|---|---|---|---|
| `notifica_pgd2` | `@shared_task` | Beat (01:27 BRT) | Não — notificação diária |
| `monitoramento_pgd2` | `@shared_task` | Beat (02:02 BRT) | Sim — upsert de regras |
| `enviar_dados_api_pgd2` | `@shared_task` | Beat (02:27 BRT) | Sim — controle por log |
| `sincronizar_permissoes_comissao_pgd2` | `@shared_task` | Beat (01:02 BRT) | Sim — destrutivo/reconstrói |

> ⚠️ REVISAR: as tasks usam `@shared_task` de `djtools.assincrono`; confirmar
> idempotência exata de cada uma no código.

## Dependências

- **Módulos internos:** comum, rh, plan_estrategico, processo_eletronico, documento_eletronico, ponto
- **Integrações:** API PGD nacional (via HTTP), Documento eletrônico (geração de ADE/PAD), Processo eletrônico (abertura de processo)

## Configuração

| Origem | Chave | Uso |
|---|---|---|
| `settings` / env | `API_PGD2_URL` | URL base da API PGD nacional |
| `settings` / env | `API_PGD2_TOKEN` | Token de autenticação da API |
| `comum.Configuracao` (app pgd2) | Diversas (`configuracao_perfil_servidor`, etc.) | Orientações, prazos, regras de desligamento |

## Como testar

```bash
pytest pgd2/tests/
```

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
