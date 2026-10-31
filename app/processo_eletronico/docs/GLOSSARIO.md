# Glossário — processo_eletronico

## Termos do domínio

| Termo | Definição observada no código |
|---|---|
| Processo eletrônico | Unidade principal de expediente, identificada por NUP, com documentos, trâmites, interessados e status. |
| NUP 21 | Número de protocolo novo, gerado a partir da unidade organizacional e usado como identificador principal. |
| NUP 17 | Número de protocolo legado; pode ser sincronizado com o app `protocolo`. |
| Trâmite | Registro de encaminhamento/recebimento de um processo entre setores ou para pessoa, podendo conter despacho assinado. |
| Caixa de processos | Consulta operacional de trâmites agrupados por aba/estado: a receber, a encaminhar, saída, atribuição e pendências. |
| Remetente | Setor e/ou vínculo que envia o trâmite. |
| Destinatário | Setor e/ou vínculo que recebe o trâmite. Processo privado exige destinatário pessoa conforme validação. |
| Interessado | `comum.Vinculo` relacionado ao processo; recebe efeitos de acompanhamento/notificação conforme regra. |
| Acompanhante | Vínculo que acompanha o processo sem ser necessariamente interessado. |
| Vínculo | Relação de usuário/pessoa com o SUAP, usada na autorização e nos relacionamentos. |
| Tipo de processo | Cadastro que define nome, classificações, acesso padrão, consulta pública e se pode nascer de requerimento. |
| Nível de acesso | Público, Restrito ou Privado/Sigiloso; controla leitura, hipótese legal e compartilhamento. |
| Hipótese legal | Referência jurídica exigida para determinados níveis de acesso/documentos. |
| Documento de texto | Documento eletrônico textual, externo ao módulo, vinculado por `DocumentoTextoProcesso`. |
| Documento digitalizado | Arquivo digitalizado, externo ao módulo, vinculado por `DocumentoDigitalizadoProcesso`. |
| Minuta | Documento em elaboração associado a processo; pode gerar documento final. |
| Despacho | Conteúdo textual de um trâmite ou resposta a uma solicitação de despacho. |
| Solicitação de ciência | Pedido para que um vínculo tome ciência de um processo em prazo determinado. |
| Ciência | Registro de conhecimento pelo solicitado; gera termo de ciência e pode liberar o processo. |
| Solicitação de juntada | Pedido para adicionar documento ao processo, com prazo e avaliação posterior. |
| Juntada | Inclusão de documento no processo; a solicitação pode ser concluída, avaliada, deferida ou indeferida. |
| Solicitação de despacho | Pedido para que um vínculo produza despacho e encaminhe o processo. |
| Requerimento | Pré-processo editável; ao ser finalizado, gera processo eletrônico com documento e primeiro trâmite. |
| Anexação | Incorporação de um processo a outro; o processo anexado passa ao status `Anexado`. |
| Apensamento | Relação temporária/administrativa entre processos, com possibilidade de desapensamento. |
| Processo relacionado | Relação informativa entre processos, sem a mesma semântica de anexação/apensamento. |
| Rótulo | Marcador visual administrado por setor e aplicado ao trâmite. |
| Atribuição | Encaminhamento operacional de um processo para uma pessoa dentro do setor. |
| Distribuição | Regra ou registro que direciona processo por setor, pessoa e tipos atendidos. |
| Retorno programado | Data prevista para retorno associada a um trâmite. |
| Barramento | Integração de tramitação externa implementada em `conectagov_pen`. |
| Termo | PDF formal produzido para ciência, finalização, apensamento, reabertura ou juntada. |
| Remoção lógica | Desvinculação registrada com data, usuário, motivo e justificativa; o registro físico permanece. |
| Registro de ação | Auditoria de ação praticada no processo, com usuário, data, IP, tipo e observação. |

## Siglas e abreviações

| Sigla | Expansão |
|---|---|
| NUP | Número Único de Protocolo. |
| PDF | Portable Document Format. |
| ZIP | Formato de arquivo compactado usado na exportação do processo. |
| FSM | Finite State Machine; máquina de estados usada nas transições. |
| BPMN | Business Process Model and Notation; formato dos workflows. |
| UUID | Identificador universal usado nas variantes públicas de consulta. |
| URL | Uniform Resource Locator. |
| IP | Endereço de origem registrado em ações. |
| HLA | High-Level Architecture. |
| ERD | Entity-Relationship Diagram. |
| API | Application Programming Interface; o módulo não possui `api.py` local. |
| UO | Unidade Organizacional. |
| RH | Recursos Humanos; módulo `rh`. |

## Entidades ↔ termos de negócio

| Entidade Python | Termo de negócio |
|---|---|
| `Processo` | Processo eletrônico. |
| `Tramite` | Trâmite/encaminhamento. |
| `TipoProcesso` | Tipo de processo. |
| `ProcessoInteressado` | Interessado do processo. |
| `ProcessoAcompanhante` | Acompanhante do processo. |
| `DocumentoTextoProcesso` | Vínculo de documento de texto ao processo. |
| `DocumentoDigitalizadoProcesso` | Vínculo de documento digitalizado ao processo. |
| `Minuta` / `ProcessoMinuta` | Minuta e vínculo da minuta ao processo. |
| `Requerimento` | Requerimento pré-processo. |
| `SolicitacaoCiencia` | Solicitação de ciência. |
| `SolicitacaoJuntada` / `SolicitacaoJuntadaDocumento` | Solicitação e item de juntada. |
| `SolicitacaoDespacho` | Solicitação de despacho. |
| `SolicitacaoAlteracaoNivelAcesso` | Pedido de alteração de acesso. |
| `Anexacao` | Anexação de processo. |
| `Apensamento` / `ApensamentoProcesso` | Apensamento e seus processos. |
| `CompartilhamentoProcessoEletronico*` | Compartilhamento/permissão de operação. |
| `RegistroAcaoProcesso` | Auditoria de processo. |

⚠️ REVISAR: “documento”, “solicitação” e “processo” também possuem entidades-base em `documento_eletronico`; esta tabela registra somente o papel que assumem neste módulo.

_Gerado/atualizado via subagent `documentador` em 2026-09-10._
