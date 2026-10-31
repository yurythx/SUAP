# Contratos

> Gerencia o ciclo de vida dos contratos administrativos da instituição, da publicação ao encerramento, incluindo fiscalização, medições e pagamento.

## Visão geral

O módulo `contratos` centraliza o acompanhamento dos contratos administrativos firmados pela
instituição a partir da sua publicação. Nele são registrados os dados do contrato (objeto,
vigência, valor, contratada, base legal), os fiscais designados por portaria, o cronograma
físico-financeiro com suas parcelas, as medições mensais da execução, os termos aditivos e
apostilamentos, as garantias contratuais, as ocorrências e a mão de obra terceirizada alocada.

Ele existe para dar rastreabilidade e controle à execução contratual: permite saber, a qualquer
momento, quanto de um contrato já foi executado, quem o fiscaliza, quais parcelas estão pendentes
de medição e quais documentos comprobatórios foram entregues pela contratada. Dentro do SUAP é o
principal consumidor de `documento_eletronico` (geração de relatórios de recebimento provisório e
termos de recebimento definitivo) e de `tesouro_gerencial` (vínculo com notas de empenho).

## Responsabilidades

- Cadastrar e manter o contrato administrativo e sua classificação (tipo, subtipo, continuidade, natureza, base legal, dedicação exclusiva de mão de obra e grau de risco).
- Registrar alterações contratuais: termos aditivos (prazo, valor, fiscal, outros) e apostilamentos (reajuste, repactuação, dotação).
- Designar e manter fiscais de contrato (com portaria, vigência e tipo de atuação, inclusive fiscal gestor).
- Manter o cronograma físico-financeiro (cronograma → parcelas) e controlar o saldo do contrato.
- Registrar as medições da execução, o IMR (Instrumento de Medição de Resultado) e vincular empenhos consumidos.
- Conduzir o recebimento provisório e o recebimento definitivo da medição, com conferência de documentos comprobatórios.
- Calcular e lançar a retenção de conta vinculada (13º, férias + 1/3, FGTS, submódulo 4.1) por trabalhador.
- Registrar garantias contratuais, penalidades, ocorrências (com notificação à contratada) e agenda de fiscalização.
- Manter o cadastro da mão de obra terceirizada (prestadores, verbas salariais, ocorrências, anexos).
- Publicar consulta pública de contratos e emitir relatórios/exportações (pendências, terceirizados, empenhos, consumo de energia, situação dos contratos, indicadores).
- Importar contratos e seus itens do ComprasGov.

**Fora de escopo:** processo licitatório e sua condução (o módulo apenas referencia o número/tipo
da licitação); execução orçamentária e empenho propriamente dito (`almoxarifado`/`tesouro_gerencial`);
cadastro de pessoas físicas/jurídicas e prestadores de serviço (`rh`/`comum`); tramitação e assinatura
dos documentos gerados (`documento_eletronico`/`processo_eletronico`); folha de pagamento dos
terceirizados (o módulo registra valores para fins de controle, não paga).

## Atores e papéis

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Gerente de Contrato | grupo `Gerente de Contrato` | Cadastra, edita e exclui contratos; gerencia anexos, publicações, aditivos, cronograma, fiscais e empenhos; configura os documentos comprobatórios da medição; conduz o recebimento definitivo; encerra/rescinde e cancela contratos; vincula documentos eletrônicos ao contrato |
| Operador de Contrato | grupo `Operador de Contrato` | Praticamente o mesmo conjunto do gerente, **exceto** `pode_cancelar_contrato` e `pode_excluir_fiscal`; acompanha o contrato e edita aditivos, anexos e publicações |
| Fiscal de Contrato | grupo `Fiscal de Contrato` | Efetua e atualiza medições, informa IMR, registra ocorrências (contrato e mão de obra), gerencia mão de obra e verbas salariais, adiciona empenhos, gera o relatório de recebimento provisório; `pode_aditivar_contrato` |
| Coordenador de Contrato Sistêmico | grupo `Coordenador de Contrato Sistêmico` | Mantém as tabelas acessórias (tipos de contrato/anexo/fiscal/ocorrência/verba salarial/documento comprobatório, base legal, pré-configuração de agenda); tem ações equivalentes às do gerente em ocorrências, mão de obra, conta e agenda via `pode_executar_acoes_coordenador_gerente` |
| Auditor | grupo `Auditor` (app_manager `auditoria`) | Somente leitura de todos os contratos da instituição (contrato, aditivos, anexos, publicações, ocorrências) e acesso aos relatórios; é *visualizador sistêmico* (ignora a restrição por unidade) |
| Supervisor de Contratos | grupo `Supervisor de Contratos` | Mesmo escopo de leitura do Auditor; também é *visualizador sistêmico* |
| Servidor | grupo `Servidor` (app_manager `rh`) | Consulta contratos, aditivos, anexos, publicações e ocorrências; acessa "Fiscais de Contrato" e o rol de responsabilidades |
| Prestador de Serviço | grupo `Prestador de Serviço` (app_manager `comum`) | Consulta contratos, aditivos, anexos, publicações e ocorrências |
| Cidadão / anônimo | _sem grupo_ — `layout.servicos_anonimos` | Consulta pública de contratos (`/contratos/listar_contratos/`, `/contratos/contrato_publico/<id>/`) |
| Fiscal designado no contrato | _derivado_ — `Fiscal.servidor` (FK) | Habilita as ações que exigem ser fiscal **daquele** contrato (decorator `verificar_fiscal`, `Contrato.get_fiscal`). ⚠️ REVISAR: papel relacional, não é grupo — o grupo `Fiscal de Contrato` é atribuído automaticamente em `Contrato.adicionar_fiscal` |
| Fiscal gestor do contrato | _derivado_ — `Fiscal.tipo.eh_gestor_contrato` | Único perfil de fiscal que pode gerar o Termo de Recebimento Definitivo (`pode_gerenciar_recebimento_definitivo`) |
| Fiscal com gestão ampla de medições | _derivado_ — `Fiscal.tipo.pode_gerenciar_todas_medicoes_contrato` | Pode alterar/excluir medições e IMRs registrados por outros fiscais |

## Estrutura interna

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `contratos/models.py` (arquivo único, 44 models) | `Contrato` (fat model: saldos, percentuais, pendências e todos os `pode_gerenciar_*`), `Medicao` (histórico, recebimento definitivo, cálculo de conta vinculada), `Fiscal`, `Cronograma`/`Parcela`, `Aditivo`/`Apostilamento`, `MaoDeObra`, `ContaContrato` |
| Views | `contratos/views.py` (≈135 views funcionais) | CRUDs por aba do contrato, medição/recebimento, relatórios, consulta pública, integração ComprasGov, quadros do dashboard (`@layout.quadro`) |
| URLs | `contratos/urls.py` | 96 rotas sob `/contratos/` |
| API | `contratos/api.py` | _N/A — o módulo não expõe django-ninja próprio; os endpoints públicos vivem em `api/endpoints/administracao.py` e `dados_abertos/endpoints/`_ |
| Forms | `contratos/forms.py` (≈50 forms) | `ContratoForm` (validações de vigência x base legal, numeração, grau de risco), `MedicaoForm`/`MedicaoEletricaForm`, `ParcelaForm` (saldo), `ConfiguracaoForm` (config do módulo) |
| Admin | `contratos/admin.py` | `ContratoAdmin` (abas por situação, filtro por fiscal, exportação XLS, restrição por unidade) + admins das tabelas acessórias |
| Tasks | `contratos/tasks.py` + `contratos/beat.py` | 6 tasks de exportação XLS (`@task` de `djtools.assincrono`); `beat.py` agenda 4 `management commands` de notificação |
| Commands | `contratos/management/commands/` | `notificar_contratos_a_expirar`, `notificar_contratos_sem_garantia_vinculada`, `notificar_contratos_sem_mao_de_obra`, `notificar_fiscalizacao_contratos`, `importar_dados_contratos` |
| Outros | `contratos/utils.py`, `contratos/services.py` | `Notificar` (e-mails/notificações), `verificar_fiscal` (decorator), `add_log_entry`; `ApiContratosGovBRService` (cliente ComprasGov) |
| Templates | `contratos/templates/` | `contrato.html` + `tabs/` (16 abas), `contrato_publico.html`, relatórios e documentos (memorandos/despachos) |
| Workflows | `contratos/workflows/*.bpmn` | Diagramas BPMN de referência: `contratos`, `gerenciar-contratos`, `fiscalizar-contratos`, `cadastros-basicos` |

## Endpoints principais

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| GET | `/contratos/redirect_contratos/` | `redirect_contratos` | `@login_required` (menu exige `contratos.view_contrato` + `rh.eh_servidor`) |
| GET | `/contratos/contrato/<contrato_id>/` | `contrato` | `@login_required` + restrição por unidade (`Configuracao restringir_por_unidade`) |
| GET/POST | `/contratos/adicionar_aditivo/<contrato_id>/` | `adicionar_aditivo` | `@permission_required('contratos.pode_aditivar_contrato')` |
| GET/POST | `/contratos/adicionar_apostilamento/<contrato_id>/` | `adicionar_apostilamento` | `@permission_required('contratos.pode_aditivar_contrato')` |
| GET/POST | `/contratos/adicionar_fiscal/<contrato_id>/` | `adicionar_fiscal` | `@permission_required('contratos.pode_adicionar_fiscal')` |
| GET/POST | `/contratos/definir_cronograma/<contrato_id>/` | `definir_cronograma` | `@permission_required('contratos.pode_gerar_cronograma')` |
| GET/POST | `/contratos/gerar_parcelas/<contrato_id>/` | `gerar_parcelas` | `@permission_required('contratos.pode_gerar_cronograma')` |
| GET/POST | `/contratos/efetuar_medicao/<parcela_id>/<contrato_id>/[<imr_id>/]` | `efetuar_medicao` | `@permission_required('contratos.pode_efetuar_medicao')` + `@verificar_fiscal()` + `@atomic()` |
| GET/POST | `/contratos/atualizar_medicao/<medicao_id>/<contrato_id>/` | `atualizar_medicao` | idem + só o fiscal autor (ou `pode_gerenciar_todas_medicoes_contrato`) |
| GET | `/contratos/gerar_despacho_eletronico/<medicao_id>/<contrato_id>/` | `gerar_despacho_documentotexto` | `@group_required('Fiscal de Contrato')` + `@verificar_fiscal()` |
| GET/POST | `/contratos/receber_definitivamente_medicao/<medicao_id>/` | `receber_definitivamente_medicao` | `@group_required('Fiscal de Contrato, Gerente de Contrato')` + `pode_gerenciar_recebimento_definitivo` |
| GET | `/contratos/gerar_termo_definitivo_documentotexto/<medicao_id>/<contrato_id>/` | `gerar_termo_definitivo_documentotexto` | idem |
| POST | `/contratos/calcular_conta_vinculada/<medicao_id>/` | `calcular_conta_vinculada_ajax` | `@group_required('Fiscal de Contrato, Gerente de Contrato')` (JSON) |
| GET/POST | `/contratos/deposito_conta/<medicao_id>/` · `/contratos/saque_conta/<conta_id>/` | `deposito_conta` / `saque_conta` | `@login_required` + `Contrato.pode_gerenciar_conta` |
| GET/POST | `/contratos/configurar_medicao/<contrato_id>/` | `configurar_medicao` | `@group_required('Gerente de Contrato')` |
| GET/POST | `/contratos/registrar_ocorrencia/<contrato_id>/` | `registrar_ocorrencia` | `@login_required` + `Contrato.pode_gerenciar_ocorrencia` |
| GET | `/contratos/notificar_ocorrencia/<ocorrencia_id>/` | `notificar_ocorrencia` | `@permission_required('contratos.pode_submeter_medicao')` |
| GET/POST | `/contratos/adicionar_maodeobra/<contrato_id>/` | `adicionar_maodeobra` | `@login_required` + `Contrato.pode_gerenciar_mao_de_obra` |
| GET/POST | `/contratos/concluir_contrato/<contrato_id>/` | `concluir_contrato` | `@permission_required('contratos.pode_encerrar_contrato')` |
| GET/POST | `/contratos/cancelar_contrato/<contrato_id>/` | `cancelar_contrato` | `@permission_required('contratos.pode_cancelar_contrato')` |
| GET | `/contratos/importar_novo_contrato_comprasgov/` | `importar_novo_contrato_comprasgov` | `@permission_required('contratos.add_contrato')` |
| GET | `/contratos/importar_itens_contrato_comprasgov/<contrato_id>/` | `importar_itens_contrato_comprasgov` | `@permission_required('contratos.change_contrato')` + fiscal/gestor ou coordenador sistêmico |
| GET/POST | `/contratos/listar_contratos/` · `/contratos/contrato_publico/<contrato_id>/` | `listar_contratos` / `contrato_publico` | **público** (serviço anônimo) |
| GET/POST | `/contratos/pendencias/` | `pendencias` | menu: grupos `Gerente de Contrato`, `Operador de Contrato` |
| GET/POST | `/contratos/relatorio_terceirizados/` · `relatorio_empenhos/` · `relatorio_consumo_energia/` | views homônimas | `@group_required('Fiscal de Contrato, Gerente de Contrato, Auditor')` |
| GET | `/contratos/visualizar_fiscais/` | `visualizar_fiscais` | `@group_required('Servidor')` |
| GET | `/contratos/indicadores/` | `indicadores` | `@login_required` (menu exige `rh.eh_servidor`) |

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `Contrato` | Instrumento contratual; núcleo do módulo, concentra saldos, situação e regras de permissão | FK `tipo`/`subtipo`/`base_legal`/`processo`/`empenho`/`campus_gerenciador`/`vinculo_contratado`; M2M `campi`, `setores_gerenciadores`, `documentos_empenho` |
| `Aditivo` | Termo aditivo de prazo, valor, fiscal ou outros; altera vigência e valor total | FK `contrato`, `processo`, `empenho`, `arquivo`; `unique_together (contrato, ordem)` |
| `Apostilamento` | Registro de reajuste/repactuação/dotação sem termo aditivo | FK `contrato` |
| `Fiscal` | Servidor designado por portaria para fiscalizar o contrato | FK `contrato`, `servidor` (rh), `tipo` (`TipoFiscal`), `campus`, `termo_aditivo` |
| `Cronograma` / `Parcela` | Cronograma físico-financeiro e suas parcelas previstas | `Cronograma` FK `contrato`; `Parcela` FK `cronograma` |
| `Medicao` | Medição da execução de uma parcela, com histórico versionado em JSON | FK `parcela`, `fiscal`, `processo`, `arquivo`; FKs para `DocumentoTexto` (despacho e termo definitivo); O2O `imr` |
| `MedicaoEletrica` | Extensão da medição para contratos de energia elétrica (consumo/demanda/multa) | O2O `medicao` |
| `IMR` | Instrumento de Medição de Resultado: percentual de qualidade por campus/parcela | FK `parcela`, `campus`, `fiscal` |
| `MaoDeObra` | Trabalhador terceirizado alocado ao contrato | FK `contrato`, `prestador_servico` (comum), `campus` |
| `ContaContrato` / `MovimentacaoContaContrato` | Conta vinculada do contrato e seus depósitos/saques | FK `contrato`; movimentação FK `conta`, `medicao`, `processo_eletronico` |
| `ContaVinculadaCalculo` / `...Item` | Memória de cálculo da retenção da conta vinculada, por trabalhador | FK `medicao`, `contrato`, `usuario`; item FK `calculo`, `maodeobra` |
| `Garantia` | Garantia contratual (seguro, fiança, caução, registro SIAFI) | FK `contrato` |
| `Penalidade` | Advertência, multa ou suspensão aplicada à contratada | FK `contrato`, `atualizado_por` |
| `Ocorrencia` | Ocorrência na execução do contrato, com prazo de resolução e notificação | FK `contrato`, `fiscal`, `servidor`, `campus`, `arquivo` |
| `Agenda` / `PreConfiguracaoAgenda` | Ações de fiscalização programadas e seu catálogo pré-configurado | `Agenda` FK `contrato`, `pre_configuracao`; M2M `fiscais` |
| `DocumentoEmpenhoContrato` / `...Medicao` | Vínculo do contrato com notas de empenho e o consumo por medição | FK `empenho` (`tesouro_gerencial.DocumentoEmpenho`), `contrato`, `medicao` |
| `ItemContrato` | Item (material/serviço) contratado, importável do ComprasGov | FK `contrato`; `UniqueConstraint (contrato, id_comprasgov)` |
| `ArrecadacaoReceita` | Valor de concessão arrecadado em contratos de receita | FK `contrato` |
| `DocumentoTextoContrato` | Vínculo (com remoção lógica) entre contrato e documento eletrônico | FK `contrato`, `documento` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/).

## Regras de negócio chave

- **Recalculo em cascata dos totais do contrato:** `Contrato.save()` recalcula `data_vencimento`, `valor_executado`, `valor_total` e `valor_previsto_parcela` a cada gravação; `Aditivo`, `Apostilamento`, `Parcela`, `Cronograma`, `Medicao` e `MedicaoEletrica` chamam `contrato.save()` no seu próprio `save()`/`delete()` para propagar (`models.py`).
- **Vigência limitada pela base legal:** `ContratoForm.clean()` impede data final maior que `data_inicio + base_legal.tempo_maximo_prorrogacao` (vigência + prorrogação, em meses); sem base legal o teto é 5 anos. Continuidade "Indeterminado" não admite data final.
- **Número do contrato:** `Contrato.clean_numero()` exige o formato `99999/9999` e normaliza com zeros à esquerda; a unicidade é checada em `ContratoForm.clean_numero()` entre contratos **ativos**, global ou por campus gerenciador conforme a configuração `habilitar_numeracao_por_campi_gerenciador`.
- **Saldo do contrato como trava:** `ParcelaForm.clean()` recusa parcela cujo valor previsto exceda `get_saldo_atual() + valor_previsto_original`; `MedicaoForm.clean()` recusa medição maior que o saldo; `SaqueContaContratoForm.clean()` recusa saque maior que o saldo da conta.
- **Autoria da medição:** só o fiscal que registrou a medição pode alterá-la, excluí-la ou informar ocorrência — salvo se seu `TipoFiscal.pode_gerenciar_todas_medicoes_contrato` for verdadeiro (`views.atualizar_medicao`, `excluir_medicao`, `adicionar_ocorrencia_medicao`, `excluir_imr`).
- **Ordem do recebimento:** o recebimento definitivo exige recebimento provisório emitido (despacho assinado ou finalizado) e termo definitivo ainda editável (`Medicao.recebimento_provisorio_emitido`, `termo_definitivo_permite_atualizacao`, `pode_ser_recebida_definitivamente`); o termo definitivo só é gerado após o gestor concluir a conferência (`pode_gerar_termo_definitivo`).
- **Dois fluxos de recebimento definitivo:** com checklist de documentos comprobatórios (quando o contrato tem `ContratoTipoDocumentoComprobatorio`) ou simplificado; `Medicao.usa_fluxo_recebimento_definitivo_com_documentos()` decide, e `sincronizar_documentos_comprobatorios_com_contrato()` cria os registros faltantes na medição.
- **Retenção de conta vinculada:** `Medicao.calcular_conta_vinculada()` aplica os percentuais de 13º, férias, FGTS e submódulo 4.1 (este último conforme `Contrato.grau_risco` 1/2/3) sobre o salário de cada `MaoDeObra`, admitindo *overrides* por trabalhador (base, manual, isento) que **exigem justificativa**; a persistência apaga e recria o cálculo dentro de `transaction.atomic()`.
- **Estorno automático:** excluir uma medição gera movimentações inversas na conta vinculada (`Medicao.registrar_estorno_conta_vinculada_por_exclusao`), preservando o histórico em vez de apagar lançamentos.
- **Permissão contextual (não só por grupo):** `Contrato.pode_gerenciar()` e a família `pode_gerenciar_empenho/conta/ocorrencia/penalidade/mao_de_obra/agenda_fiscalizacao/recebimento_definitivo` combinam grupo, campus gerenciador, setores gerenciadores, papel de fiscal e a flag `cancelado`. A configuração `restringir_por_unidade` liga/desliga o confinamento por unidade (Auditor, Supervisor de Contratos e superusuário são isentos).
- **Fiscal ganha grupo automaticamente:** `Contrato.adicionar_fiscal()` adiciona o usuário do servidor ao grupo `Fiscal de Contrato` se ele ainda não pertencer.
- **Multa por ultrapassagem de demanda:** em contratos elétricos, se a demanda medida exceder em mais de 5% a contratada, o valor da multa passa a ser obrigatório e uma ocorrência é gravada automaticamente na medição (`MedicaoEletrica.deve_solicitar_valor_multa`, `views.efetuar_medicao`).
- **Publicação de aditivo espelha a do contrato:** `adicionar_publicacao_aditivo` cria também a `PublicacaoContrato` equivalente (`get_or_create`), e `upload_publicacao_aditivo` replica o arquivo na publicação do contrato.
- **Pendências do contrato:** `Contrato.get_pendencias(uo)` classifica como pendente o contrato sem arquivo digitalizado, sem publicações (ou com publicação/aditivo sem anexo), sem fiscal, sem cronograma ou com cronograma sem parcelas.
- **Exclusão em cascata manual:** `Contrato.delete()` remove explicitamente publicações, anexos e aditivos (para acionar os `delete()` que apagam os `Arquivo` associados) antes de apagar o próprio contrato.
- ⚠️ REVISAR: `ContratoQueryset.a_serem_licitados()` calcula `data_5_anos_atras` e `data_5_anos_mais_prazo_licitacao` com a **mesma** expressão, resultando em um intervalo degenerado (`range` de um único dia); a intenção provavelmente era somar o prazo de licitação à segunda data.
- ⚠️ REVISAR: `ContratoForm.clean()` compara `cleaned_data.get('tipo')` com as strings `'Despesa'`/`'Receita'`, mas `tipo` é uma instância de `TipoContrato` — as validações de empenho/processo obrigatórios nunca disparam (há `# TODO` no próprio código).

## Jobs / Tasks Celery

| Task | Decorator | Dispara | Idempotência |
|---|---|---|---|
| `exportar_fiscais_para_xls` | `@task` (`djtools.assincrono`) | View `visualizar_fiscais` com "Exportar para XLS" | Sim — só lê e gera arquivo |
| `buscar_contrato_export_to_xls` | `@task` | View `buscar_contrato_export_to_xls` | Sim — somente leitura |
| `exportar_contratos_xls` | `@task` | View `exportacao` (limite de 50.000 registros) | Sim — somente leitura |
| `relatorio_consumo_energia_xls` | `@task` | View `relatorio_consumo_energia` | Sim — somente leitura |
| `relatorio_terceirizados_xls` | `@task` | View `relatorio_terceirizados` | Sim — somente leitura |
| `relatorio_empenhos_xls` | `@task` | View `relatorio_empenhos` (`?xls=1`) | Sim — somente leitura |

Agendamentos (`contratos/beat.py`, via `beat.utils.carregar_call_command`):

| Comando | Horário (crontab) | O que faz | Idempotência |
|---|---|---|---|
| `notificar_contratos_sem_garantia_vinculada` | 04:07 | Notifica fiscais de contratos que exigem garantia e não a têm (ou cuja garantia expirou após aditivo), em D+15/30/60 do início | Parcial — após D+60 usa `NotificacaoSistema` para não repetir; nas datas exatas reenviaria se executado duas vezes no mesmo dia |
| `notificar_contratos_a_expirar` | 04:37 | Notifica fiscais quando faltam exatamente 15, 30 ou 45 dias para o fim | Parcial — depende da execução única no dia |
| `notificar_contratos_sem_mao_de_obra` | 04:52 | Notifica fiscais de contratos com dedicação exclusiva sem nenhum registro de mão de obra 30 dias após o início | Não — reenviaria a cada execução enquanto a pendência existir |
| `notificar_fiscalizacao_contratos` | 05:07 | Notifica fiscais das agendas previstas para hoje, D-15 e D-30 ainda não executadas | Parcial — depende da execução única no dia |

Comando manual: `importar_dados_contratos` faz o *bulk create* das `PreConfiguracaoAgenda` a partir de
`contratos/fixtures/pre_configuracao_agenda.csv` (⚠️ REVISAR: não é idempotente — reexecutar duplica os registros).

## Dependências

- **Módulos internos:** `comum`, `rh`, `protocolo`, `almoxarifado`, `documento_eletronico`, `processo_eletronico`, `tesouro_gerencial` (conforme `module_dependencies.json`); além destes, `contratos/admin.py` importa `Configuracao` de `edu.models` — reexport de `comum.models.Configuracao` (⚠️ REVISAR: acoplamento acidental não declarado).
- **Integrações:** `documento_eletronico` (relatório de recebimento provisório, termo de recebimento definitivo, ofícios/despachos e vínculo documento↔contrato; uso condicionado a `'documento_eletronico' in settings.INSTALLED_APPS`), `processo_eletronico` (processo da movimentação de conta), `tesouro_gerencial` (notas de empenho), **ComprasGov** (`https://contratos.comprasnet.gov.br/api`, via `comum.APIExterna.CONTRATOSGOVBR` e `contratos/services.py`), armazenamento de arquivos via `comum.Arquivo` e `PrivateFileField`/`FileFieldPlus`, e-mail/notificações via `djtools.utils.send_mail`/`send_notification` e `comum.Notificador`.

## Configuração

Todas as chaves ficam em `comum.Configuracao` (app `contratos`), editáveis pelo `ConfiguracaoForm`
(`contratos/forms.py`) — não há configuração por variável de ambiente própria do módulo.

| Origem | Chave | Uso |
|---|---|---|
| `comum.Configuracao` (app `contratos`) | `dias_nova_licitacao` | Janela (em dias, padrão 90) usada por `proximos_a_vencer()` e pelos quadros do dashboard |
| `comum.Configuracao` (app `contratos`) | `restringir_por_unidade` | Confina operadores/gerentes ao próprio campus gerenciador (views, admin e `ContratoForm`) |
| `comum.Configuracao` (app `contratos`) | `habilitar_numeracao_por_campi_gerenciador` | Permite numeração sequencial por campus (afeta a unicidade do número do contrato) |
| `comum.Configuracao` (app `contratos`) | `tipo_contrato_energia_eletrica` | ID do `SubtipoContrato` que aciona o formulário/aba de medição elétrica |
| `comum.Configuracao` (app `contratos`) | `tipo_documento_contrato` | IDs (CSV) dos `TipoDocumento` aceitos como documento digital do contrato |
| `comum.Configuracao` (app `contratos`) | `conta_vinculada.perc_13`, `conta_vinculada.perc_ferias`, `conta_vinculada.perc_fgts` | Percentuais da retenção da conta vinculada (padrões 8,333333% / 12,1% / 4%) |
| `comum.Configuracao` (app `contratos`) | `conta_vinculada.perc_submodulo_grau1..3` | Percentual do submódulo 4.1 por grau de risco (padrões 7,39% / 7,60% / 7,82%) |
| `comum.APIExterna` | `CONTRATOSGOVBR` | URL base, credenciais e flag `ativo` da integração ComprasGov |
| `settings` | `SITE_URL`, `DEFAULT_FROM_EMAIL` | Montagem de links e remetente nas notificações (`contratos/utils.py`, `models.Ocorrencia`) |
| `settings.INSTALLED_APPS` | `documento_eletronico` | Habilita o vínculo de documentos eletrônicos ao contrato |

## Como testar

```bash
pytest contratos/tests/
```

Testes existentes: `test_aditivo.py`, `test_bases.py`, `test_contacontrato.py`, `test_contrato_clean.py`,
`test_contrato_properties.py`, `test_contrato_queryset.py`, `test_medicao_conta_vinculada.py`,
`test_medicao_eletrica.py`, `test_recebimento_definitivo_permissoes.py`, `contratos_tests.py`.
Há também suíte behave em `contratos/features/` (`python manage.py test_behave --behave_stop --noinput contratos`).

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-08-11._
