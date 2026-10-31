# Atividades Estudantis (AE)

> Serviço Social e gestão dos programas de assistência estudantil, desde a caracterização socioeconômica e a inscrição até a análise, participação, atendimento e comprovação.

## Visão geral

O módulo `ae` implementa a área de Atividades Estudantis do SUAP. Seu núcleo registra a situação socioeconômica de estudantes, disponibiliza editais e programas, conduz inscrições e análise de seleção, formaliza participações e controla atendimentos, refeições, auxílios, bolsas, passe estudantil e relatórios de gestão.

O módulo usa os modelos acadêmicos de `edu` para identificar o aluno e sua situação, as entidades organizacionais e funcionais de `rh`, máquinas de terminal de `ponto`, pessoas e vínculos de `comum` e, em um caso específico, participação de bolsa de `projetos`.

## Responsabilidades

- Manter a caracterização socioeconômica, histórico de alterações, renda familiar e documentos da inscrição.
- Configurar programas, editais, períodos, ofertas, critérios e parâmetros de seleção.
- Receber inscrições, dados do grupo familiar, documentos, respostas e termos de compromisso.
- Gerar análises de inscrição, calcular pontuação, sugerir benefícios e registrar pareceres.
- Abrir, editar, suspender, revogar e acompanhar participações nos programas.
- Registrar demandas, atendimentos setoriais, atividades, ações educativas e comprovantes.
- Solicitar, avaliar, agendar e registrar refeições, inclusive via terminal/refeitório.
- Calcular valores de transporte, alimentação, trabalho e programas genéricos para relatórios.
- Integrar e importar dados do CadÚnico e fornecer contratos consumidos por dados abertos.

Fora de escopo do módulo:

- Cadastro mestre de pessoas, vínculos, unidades, setores e bancos, mantido por `comum`/`rh`.
- Matrícula, curso e demais fatos acadêmicos, mantidos por `edu`.
- Cadastro e operação física dos terminais de refeitório, mantidos por `ponto`.
- Ciclo próprio de projetos e bolsas de pesquisa, mantido por `projetos`.
- Assinatura e infraestrutura de documentos eletrônicos, quando o app correspondente está instalado.

## Atores e papéis

| Ator | Grupo/permissão | O que pode fazer |
|---|---|---|
| Aluno | Grupo `Aluno`; `ae.view_inscricao` | Consultar programas e inscrições próprias, preencher caracterização, solicitar refeição, enviar documentos e comprovantes. |
| Assistente Social | Grupo `Assistente Social`; permissões `ae.*` de campus | Operar inscrições, documentos, pareceres, participações, refeições, critérios e relatórios do próprio campus. |
| Auditor | Grupo `Auditor`; permissões de leitura | Consultar dados, análises, participações e relatórios sem executar a gestão operacional. |
| Bolsista do Serviço Social | Grupo `Bolsista do Serviço Social`; `ae.add_demandaalunoatendida` | Registrar e consultar atendimento de demanda autorizado. |
| Coordenador de Atividades Estudantis | Grupo correspondente; permissões de campus | Coordenar programas, financeiro, participações, inscrições e atendimentos do campus. |
| Coordenador sistêmico | Grupo `Coordenador de Atividades Estudantis Sistêmico` | Administrar a operação entre campi, parâmetros, análises e importações sistêmicas. |
| Diretor Geral / Pró-Reitor | Grupos correspondentes | Consultar e acompanhar dados agregados e relatórios conforme permissões de gestão. |
| Operador do terminal | Grupo `Operador do Terminal do Refeitório` | Registrar consumo de refeição no terminal autorizado, inclusive pelo webservice offline. |
| Fiscal de contrato | Grupo `Fiscal de Contrato de Alimentação` | Consultar informações operacionais e relatórios de alimentação conforme permissões. |
| Scheduler/worker | Beat, Celery e comandos `ae` | Executar importações, geração de faltas, disponibilidade, comprovantes e manutenção. |

## Estrutura interna

| Camada | Localização | Papel |
|---|---|---|
| Models | [`models.py`](../models.py) | Domínio completo de caracterização, inscrição, seleção, participação, alimentação, auxílios, bolsas e relatórios; 96 classes de modelo. |
| Views | [`views.py`](../views.py) | Fluxos web e páginas de consulta, cadastro, análise, gestão, alimentação e relatórios. |
| URLs | [`urls.py`](../urls.py) | Aproximadamente 150 rotas sob `/ae/`, organizadas por caracterização, inscrição, participação, alimentação, análise e relatórios. |
| Forms | [`forms.py`](../forms.py) | Formulários `FormPlus`, `ModelFormPlus` e wizard para caracterização, inscrições, seleção, ofertas e atendimentos. |
| Admin | [`admin.py`](../admin.py) | Cadastros e operação administrativa com `ModelAdminPlus`, filtros e ações. |
| Tasks | [`tasks.py`](../tasks.py) | Relatórios, folha de pagamento, análise, pontuação e impressão assíncronos. |
| Commands | [`management/commands/`](../management/commands/) | Importações, backfills, consistência, faltas, comprovantes e manutenção de dados. |
| Beat | [`beat.py`](../beat.py) | Agenda os comandos recorrentes de CadÚnico, bolsas, faltas, comprovantes e inativação. |
| Integrações | [`webservice.py`](../webservice.py), [`utils.py`](../utils.py) | Consumo offline de refeições e funções financeiras reutilizadas por `dados_abertos`. |

## Endpoints principais

As rotas abaixo são os pontos de entrada dos fluxos; a lista exaustiva permanece em [`urls.py`](../urls.py).

| Método | Rota | View | Permissão/controle |
|---|---|---|---|
| GET/POST | `/ae/caracterizacao/` | `caracterizacao` | `ae.save_caracterizacao_*`, `edu.pode_editar_caracterizacao` ou aluno próprio. |
| GET/POST | `/ae/inscricao_identificacao/` | `inscricao_identificacao` | `ae.pode_ver_motivo_solicitacao`; abre o período e o programa. |
| GET/POST | `/ae/inscricao_caracterizacao/<aluno>/<periodo>/<programa>/` | `inscricao_caracterizacao` | Login e autenticação de dois fatores. |
| GET/POST | `/ae/inscricao_grupo_familiar/.../` | `inscricao_grupo_familiar` | Login; exige caracterização quando o programa a requer. |
| GET/POST | `/ae/inscricao_documentacao/.../` | `inscricao_documentacao` | Login; controla documentos pendentes e obrigatórios. |
| GET/POST | `/ae/inscricao_confirmacao/<tipo>/<id>/` | `inscricao_confirmacao` | Login; conclui a inscrição. |
| GET | `/ae/programa/<programa_id>/` | `programa` | `ae.view_programa`. |
| GET/POST | `/ae/inscricao/<pk>/` | `inscricao` | `ae.pode_ver_inscricao`. |
| GET/POST | `/ae/parecer_inscricao/<inscricao_id>/` | `parecer_inscricao` | Permissões de parecer; atualiza histórico e pendências. |
| GET/POST | `/ae/adicionar_participacao/<inscricao_id>/` | `adicionar_participacao` | `ae.pode_editar_participacao`; inscrição deferida e documentada. |
| GET/POST | `/ae/editar_participacao/<participacao_id>/` | `editar_participacao` | `ae.pode_editar_participacao`. |
| GET/POST | `/ae/revogar_participacao/<participacao_id>/` | `revogar_participacao` | `ae.pode_revogar_participacao`. |
| GET/POST | `/ae/solicitar_refeicao/<programa_id>/` | `solicitar_refeicao` | `edu.view_mensagementrada`; aluno próprio e regras de oferta/horário. |
| GET/POST | `/ae/avaliar_solicitacao_refeicao/<programa_id>/` | `avaliar_solicitacao_refeicao` | `ae.add_agendamentorefeicao`; ordenação e disponibilidade. |
| GET/POST | `/ae/analise_inscricoes/` | `analise_inscricoes` | Permissões de análise por campus ou sistema. |
| POST | `/ae/gerar_analise_inscricoes/<edital_id>/<programa_id>/<ordenacao>/` | `gerar_analise_inscricoes` | Permissão de análise; delega para task Celery. |
| GET/POST | `/ae/relatorio_gestao/` | `relatorio_gestao` | Permissões de relatório e escopo organizacional. |
| POST | `/ae/importar_caracterizacao_edital_ano/` | `importar_caracterizacao_edital_ano` | `ae.pode_importar_caracterizacao`; importa dados de edital. |
| POST | `/ae/importar_cadunico/<pessoafisica_id>/` | `importar_cadunico` | Assistente Social; integração CadÚnico ativa. |
| GET/POST | `/ae/cadastrar_comprovante_mensal/<comprovante_id>/` | `cadastrar_comprovante_mensal` | Aluno próprio com comprovante pendente. |

## Modelos de domínio

| Modelo | Descrição | Relações relevantes |
|---|---|---|
| `Caracterizacao` | Retrato socioeconômico atual do aluno. | `edu.Aluno`, históricos, grupo familiar, lookup tables e renda. |
| `Programa` | Configuração de um programa de atividade estudantil. | Demandas, campus, tipo, edital/período e ofertas. |
| `Inscricao` | Candidatura do aluno a um programa. | Programa, aluno, documentos, período, parecer, análise e participação. |
| `AnaliseInscricao` | Snapshot e pontuação para seleção. | Edital, programa, inscrição, aluno, critérios e parâmetros. |
| `Participacao` | Concretização da inscrição deferida. | Subtipos de alimentação, idioma, trabalho e passe. |
| `DemandaAlunoAtendida` | Registro de demanda/benefício efetivamente atendido. | Aluno, demanda, programa, campus e terminal. |
| `AgendamentoRefeicao` | Refeição agendada para um aluno. | Programa, aluno, tipo de refeição, justificativa e atendimento. |
| `OfertaAlimentacao` | Capacidade e configuração de refeições por campus/dia. | Unidade organizacional e valores de refeição. |
| `DocumentoInscricaoAluno` | Documento comprobatório da inscrição. | Aluno, inscrição, grupo familiar, estados de pendência e validação. |
| `ComprovanteParticipacao` | Evidência mensal de participação/pagamento. | Aluno, programa, participação e unidade. |
| `SolicitacaoAuxilioAluno` | Solicitação de auxílio eventual. | Aluno, tipo de auxílio, parecer e vínculo avaliador. |
| `RelatorioGestao` | Configuração e dados de relatório de gestão. | Unidade, gráficos e classes especializadas. |

O inventário completo, particionado por subdomínio, está no [índice do modelo de dados](modelo-de-dados/_indice.md).

## Regras de negócio chave

- Uma inscrição é vinculada a aluno, programa e período; a análise só é criada quando há caracterização utilizável.
- A participação é a concretização da inscrição; o subtipo é derivado do tipo do programa e possui regras próprias de configuração.
- O parecer altera a situação da inscrição, registra autor/data e mantém histórico; pendência de documentação impede a continuidade do fluxo.
- A caracterização vigente é versionada em `HistoricoCaracterizacao`; sua gravação também atualiza histórico de renda e renda per capita.
- A solicitação de refeição valida aluno, campus, caracterização, horário, dia útil/feriado, oferta, disponibilidade e duplicidade antes de criar o pedido.
- A avaliação de refeição ordena pedidos por prioridade, documentação, renda per capita e horário; o deferimento cria ou atualiza `AgendamentoRefeicao`.
- Faltas de alimentação são geradas por comando agendado e podem atualizar/suspender a participação conforme a quantidade de faltas.
- O fechamento de uma participação de trabalho pode reabrir a disponibilidade da `OfertaBolsa`; a oferta também é sincronizada por comando recorrente.
- Valores financeiros são calculados por sobreposição de datas e pró-rata; a folha usa cache por programa, ano e mês.
- Ao inativar um aluno, sinal e comando de manutenção encerram inscrições/participações abertas com motivo de inativação.

## Jobs / Tasks Celery

| Task/comando | Decorator/agenda | Dispara | Idempotência/observação |
|---|---|---|---|
| `relatorio_atendimento` | `@task` | Relatório de atendimento | Gera arquivo/resultado assíncrono. |
| `exportar_folha_pagamento_xls` / `processar_folha_pagamento` | `@task` | Folha mensal | Cálculo usa cache por programa/período. |
| `exportar_relatorio_atendimento_pnaes_xls` | `@task` | Relatório PNAES | Exportação assíncrona. |
| `relatorio_aluno_rendimento_frequencia_xls` | `@task` | Rendimento/frequência | Exportação assíncrona. |
| `imprimir_lista_diaria` / `imprimir_relatorio_refeicoes` | `@task` | Listas e refeições | Relatórios assíncronos. |
| `gerar_analise_inscricoes` / `recalcular_pontuacao` | `@task` | Análise e pontuação | Recria/atualiza snapshots; repetir pode atualizar análises existentes. |
| `exportar_analises_deferidas_pdf` / `exportar_analises_inscricoes_pdf` | `@task` | PDFs de análise | Exportação assíncrona. |
| `exportar_relatorio_sispnaes` | `@task` | Exportação SISPNAES | Exportação assíncrona; formato deve ser conferido no consumidor. |
| `importacao_cadunico` | Beat: a cada hora | `call_command` | Processa importações pendentes do dia e marca conclusão. |
| `gerar_bolsas_ae` / `gerar_bolsas_ae_pesquisa` | Beat: 01:07/01:37 | `call_command` | Geração periódica de bolsas. |
| `gera_faltas_alimentacao` | Beat: 02:07 | `call_command` | Cria históricos de faltas e atualiza/suspende participações. |
| `ofertabolsa_ae_verificar_disponibilidade` | Beat: 02:37 | `call_command` | Sincroniza disponibilidade de ofertas. |
| `gera_solicitacoes_comprovantes_mensais` | Beat: 03:07 | `call_command` | Cria comprovantes mensais pendentes. |
| `edu_inativar_participacao_ae` | Beat: 03:37 | `call_command` | Encerra participação de alunos inativos. |

## Dependências

Dependências de domínio declaradas em `module_dependencies.json`: `comum`, `rh`, `edu`, `ponto` e `projetos`. O módulo também usa `djtools`, `beat`, Celery, cache, arquivos privados e a integração configurável `APIExterna.CADUNICO`.

## Configuração

| Chave/recurso | Uso |
|---|---|
| `ae.prazo_expiracao_documentacao` | Prazo de expiração de documentação; o modelo usa 365 dias quando a chave não está definida. |
| `ae.permitir_varios_editais_ativos` | Permite ou restringe múltiplos editais ativos nos formulários/fluxos. |
| `comum.salario_minimo` | Base para histórico de renda e faixas de renda. |
| `APIExterna.CADUNICO` | Habilita a importação de dados do CadÚnico. |
| `documento_eletronico` instalado | Habilita campos/fluxos de termo de compromisso digital. |
| Cache Django/Redis | Disponibilidade de refeições e relatórios/folha. |
| Upload privado | Documentos, comprovantes, solicitações e anexos ficam em caminhos privados do módulo. |

## Como testar

- Testes unitários/integração: `pytest -q ae`.
- BDD legado, quando aplicável: `python manage.py test_behave --behave_stop --noinput ae`.
- Antes de testar com banco, seguir a receita de Postgres ajustado e `--no-migrations` descrita no `AGENTS.md` da raiz.
- Para alterações de documentação deste diretório, não foram executados testes de aplicação.

## Links

- [HLA](HLA.md)
- [Glossário](GLOSSARIO.md)
- [Modelo de dados](modelo-de-dados/_indice.md)
- [Fronteira](FRONTEIRA.md)
- [Fluxos](fluxos/)
- [Design System](../../docs/design-system.md)

_Gerado/atualizado via subagent `documentador` em 2026-09-09._
