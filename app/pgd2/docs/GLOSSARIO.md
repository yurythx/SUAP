# Glossário — pgd2

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| PGD | Programa de Gestão 2 — substituto do PGD1/IFRN. Regime de trabalho com entregas por teletrabalho e/ou presencial. | `apps.py` (`ProgramaGestaoConfig`) |
| Adesão | Processo de ingresso do servidor no PGD, desde a solicitação até a assinatura do documento de adesão. | `SolicitacaoAdesaoServidor`, `DocumentoAdesaoServidor` |
| PES | Plano de Entregas Setorial — plano do setor definindo entregas, horários de funcionamento e planejamento para um período. | `PlanoEntregasSetorial`, `PlanoEntregasSetorialEntregas` |
| PIT | Plano Individual de Trabalho — plano do servidor com entregas, trabalho presencial e atendimento de teletrabalho. | `PlanoIndividualTrabalho`, `PlanoIndividualTrabalhoEntregas` |
| RIT | Relatório Individual de Trabalho — relatório de execução do PIT, com entregas realizadas e distribuição de horas. | `RelatorioIndividualTrabalho`, `RelatorioIndividualTrabalhoDistribuicaoHoras` |
| Desligamento | Saída do servidor do PGD, voluntária ou por gestão, com justificativa. | `DesligamentoPgdServidor`, `JustificativaDesligamentoPgd` |
| Monitoramento | Processo automático que verifica pendências de servidores e pode acionar desligamento. | `MonitoramentoServidor`, `monitoramento.py` |
| Comissão PGD | Grupo de servidores responsável pela gestão do PGD, podendo ser sistêmica (todo o órgão) ou local (setor específico). | `ComissaoPGD`, `permissions.yaml` |
| Distribuição de horas | Rateio da carga horária do servidor entre atividades presenciais e de teletrabalho no RIT. | `RelatorioIndividualTrabalhoDistribuicaoHoras`, `views.servidor_pgd_horas` |
| Homologação | Aprovação final do PIT ou RIT pelo chefe, após aprovação. | `views.homologar_pit`, `views.homologar_rit` |
| ADE | Acordo de Distribuição de Entregas — documento gerado a partir da adesão. | `DocumentoAdesaoServidor` (sigla não explícita no código) |
| PGD Exterior | Servidores do PGD que estão em exercício no exterior. | `PGDExterior` |
| API PGD | API externa do governo federal para envio de dados consolidados do PGD. | `api_pgd2.py`, `api_pgd2_v2.py` |

> ⚠️ REVISAR: confirmar se "ADE" é a sigla correta para o documento gerado pela
> adesão e se ele é tramitado como processo eletrônico ou documento eletrônico.

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| PGD | Programa de Gestão | Nome do módulo `pgd2` no SUAP |
| PES | Plano de Entregas Setorial | Entidade `PlanoEntregasSetorial` |
| PIT | Plano Individual de Trabalho | Entidade `PlanoIndividualTrabalho` |
| RIT | Relatório Individual de Trabalho | Entidade `RelatorioIndividualTrabalho` |
| ADE | Acordo de Distribuição de Entregas | Documento de adesão |
| PAD | Plano de Atividades (PIT) | Termo usado em alguns contextos/nomes de views |
| API | Application Programming Interface | Endpoints de integração externa |
| SIAPE | Sistema Integrado de Administração de Pessoal | Base de servidores (módulo `rh`) |

## Entidades ↔ termo de negócio

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `SolicitacaoAdesaoServidor` | Pedido de adesão | Termo técnico ~ termo de negócio |
| `DesligamentoPgdServidor` | Desligamento | Termo técnico ~ termo de negócio |
| `PlanoEntregasSetorial` | PES (Plano de Entregas Setorial) | Termo técnico ~ termo de negócio |
| `PlanoIndividualTrabalho` | PIT (Plano Individual de Trabalho) | Termo técnico ~ termo de negócio |
| `RelatorioIndividualTrabalho` | RIT (Relatório Individual de Trabalho) | Termo técnico ~ termo de negócio |
| `ParticipantePgd` | Participante PGD | Relacionamento servidor-setor no PGD |
| `ComissaoPGD` | Comissão PGD | Termo técnico ~ termo de negócio |
| `MonitoramentoServidor` | Monitoramento de servidor | Termo técnico ~ termo de negócio |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
