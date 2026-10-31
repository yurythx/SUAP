# Registro da geração do manual de Auditoria

## Escolha e fontes

Auditoria não possuía `docs/usuario.md`. O levantamento encontrou 27 entradas em `menu.yaml`, incluindo os cadastros de apoio, e 1.502 símbolos de funções, métodos e classes no grafo do módulo. Essa contagem mede o código, não o número de telas. A comparação usada na escolha encontrou 2.090 símbolos em RH, 1.061 em Ponto e 947 em PGD. Auditoria foi escolhida entre os módulos grandes sem manual, considerando também as factories existentes e o encadeamento entre planejamento, recomendações, providências e benefícios.

O roteiro partiu de `auditoria/menu.yaml`, complementado pelas páginas e ações alcançadas durante a navegação e pela descoberta de handlers no grafo. Auditoria não consta em `docs/agents/inventario-tarefas.yaml`: as tarefas foram propostas, sem curadoria `@do_document` preexistente. O gabarito utilizado foi `docs/agents/PROTOTIPO-doc-usuario-eventos.md`.

Os passos e rótulos do manual foram executados no navegador. As consultas ao código serviram para descobrir portas, preparar os dados e conferir autorização; não substituíram a execução dos passos. A abertura das telas ocorreu por URL direta: o manual não afirma que caminhos de menu foram percorridos.

## Ambiente e dados

Roteiros em `auditoria/tests/doc/`, com os markers `doc` e `e2e`, usando `djtools/e2e_fixtures.py` e `djtools/e2e_ui.py` sem alterações. A fixture de captura compartilhada recebe apenas o destino `auditoria/docs/usuario/`. Os WebP são ignorados pelo Git e precisam acompanhar a publicação do manual; ainda não há host de documentação disponível para o envio automático.

Foi utilizado exclusivamente o banco fictício `test_suap_doc_e2e`, em Postgres local na porta 5433, com `max_locks_per_transaction=4096`, sob `suap.settings_test`. Nenhuma tela de homologação ou produção foi acessada.

O seed de sessão reutiliza as factories do módulo e dos módulos donos dos dados. Acrescenta o campus ADOC, três servidores fictícios, chefia vigente, jornada de 40 horas semanais, núcleo com coordenador e membros, ano corrente, ação e tipo de serviço, classes financeira e qualitativa, unidade afetada, alcance estratégico e opções de atendimento. As três factories novas são `ClasseBeneficioFactory`, `AlcanceEstrategicoFactory` e `UnidadeAfetadaFactory`.

| Conta fictícia | Papel executado |
| --- | --- |
| Ana Auditora (`auddoc1`) | Auditor, monitor da recomendação e dos benefícios |
| Carlos Coordenador (`auddoc2`) | Auditor e Auditor Sistêmico, coordenador do núcleo |
| Marina Responsável (`auddoc3`) | Servidora com chefia vigente da unidade ADOC |

## Papéis e limites da descoberta

`bin/scripts/papeis.py` foi consultado com o verbo da operação:

| Operação | Resultado da consulta | Precisão aplicada ao manual |
| --- | --- | --- |
| `auditoria.add_paint` | Auditor Sistêmico | Cadastro do PAINT |
| `auditoria.add_relatorio` | Auditor, Auditor Sistêmico | Cadastro do relatório |
| `auditoria.add_recomendacao` | Auditor, Auditor Sistêmico | Cadastro; início do acompanhamento condicionado ao monitor responsável |
| `auditoria.add_beneficio` | Auditor, Auditor Sistêmico | O roteiro usa a ação nativa Adicionar Benefício na recomendação, com o auditor monitor |
| `comum.is_auditor` | Nenhum grupo no YAML | Permissão gerada por `PermissionSyncer.sync` e atribuída ao grupo Auditor; usada na sincronização de CH e no vínculo nativo de benefício |
| `auditoria.add_manifestacao` | Nenhum grupo no YAML | Autorização por dados: chefia vigente da unidade, prazo aberto e acompanhamento ativo |
| `auditoria.add_posicionamento` | Nenhum grupo no YAML | Autorização por dados: auditor responsável, manifestação recebida e posicionamento ainda não publicado |

O “Quem pode” das tarefas com autorização por dados foi definido manualmente, consultando os métodos de autorização e conferindo o botão e a execução com pessoas reais do seed. Não foram usados superusuários nem permissões simuladas. Os relatórios e indicadores utilizam os grupos Auditor e Auditor Sistêmico declarados no menu.

A sincronização de CH exige o perfil Auditor; a operação não exige coordenação do núcleo. O ator usado também possui Auditor Sistêmico porque cadastra o PAINT na mesma tarefa de geração. A consulta estática de `papeis.py` não identifica as permissões `is_<grupo>` criadas durante a sincronização dos grupos.

## Recortes e operações dispensadas

| Tela ou operação | Motivo |
| --- | --- |
| Cadastros de apoio e Permissões de Chefe | Configuração inicial ou manutenção administrativa; relacionados no parágrafo Telas de apoio, sem roteiro de cadastro |
| Listagens isoladas de monitoramentos e benefícios | Portas alternativas para os mesmos objetivos; o roteiro acompanha a recomendação e cadastra benefícios pela ação nativa da unidade |
| Documentos eletrônicos/externos e anexos | Integrações documentais não percorridas; o manual apenas identifica a área de documentos visível no relatório |
| Comentários, revisão, supervisão e designação de servidor | Variações do acompanhamento que não foram executadas; não recebem instruções no manual |
| Prorrogação, cancelamento, fechamento, reabertura, remoção e edição | Operações alternativas ao fluxo de registro, resposta, atendimento e conclusão executado |
| Outros tipos de manifestação e de posicionamento | O roteiro executa Encaminhamento de Providências seguido de Atendimento; não generaliza seus efeitos para outras escolhas |
| Alteração dos filtros, exportação XLS e impressão | Controles observados nas consultas, sem submissão ou download; não há instruções para executar essas operações |
| Falhas de validação e tentativas sem autorização | Não provocadas; as restrições consultadas no código não são apresentadas como mensagens verificadas |

A busca livre de recomendação no cadastro isolado de benefício não foi concluída. A tarefa usa **Adicionar Benefício** na aba da unidade, que preenche a associação pelo fluxo nativo. Não foi demonstrado erro HTTP nessa busca.

O painel de benefícios retornou erro quando ainda não havia benefícios. A leitura de `generate_chart_evolucao_por_tipo` sugere acesso à coluna `ano` em um conjunto vazio; a causa não foi validada por traceback. Após cadastrar os benefícios, a tela abriu e foi capturada. Esse estado vazio não é um fluxo documentado e não motivou alteração no produto.

## Tarefas e roteiro

| Tarefa do manual | Roteiro de geração |
| --- | --- |
| 1. Criar o planejamento anual | `test_01_cadastrar_paint` |
| 2. Atualizar CH e consultar planejamento individual | `test_01_cadastrar_paint` |
| 3. Registrar relatório de auditoria | `test_02_cadastrar_relatorio` |
| 4. Registrar recomendação e solicitar providências | `test_03_cadastrar_recomendacao` |
| 5. Responder à solicitação | `test_04_responder_recomendacao` |
| 6. Analisar e publicar posicionamento | `test_06_analisar_manifestacao` |
| 7. Registrar, acompanhar e concluir benefício financeiro | `test_05_cadastrar_beneficio`, caso Financeiro |
| 8. Registrar e publicar benefício qualitativo | `test_05_cadastrar_beneficio`, caso Qualitativo |
| 9. Consultar resultados e estoque | `test_10_consultar_relatorios`, seis consultas |
| 10. Acompanhar indicadores | `test_10_consultar_relatorios`, dois painéis |

Os casos dependem dos registros criados pelo roteiro e compartilham o seed de sessão. Não constituem uma suíte de regressão nem declaram cobertura integral das rotas do módulo. Os prazos usam a data da geração: a solicitação vence em 30 dias e a recomendação em 60 dias.

## Afirmações conferidas por leitura

A interpretação dos papéis e as pré-condições de autorização foram conferidas no código, além da execução com o ator autorizado. Não foram tentados usuários sem permissão, prazos expirados ou combinações inválidas de campos. O vínculo entre núcleo e membros e a jornada de trabalho foram completados no seed para viabilizar o planejamento. O manual não lista mensagens de validação não provocadas.

O fluxo financeiro usa uma parcela efetivada no mesmo dia, com valor esperado e efetivo iguais ao valor total do benefício. A regra que compara o total efetivo das parcelas ao benefício foi consultada para preparar esse caso; não foram exercitadas parcelas parciais, divergentes ou ainda não efetivadas.

## Execução e custo medido

Rodada final em 05/10/2026: **15 casos passaram**, sem falhas, erros ou dispensas na execução. Foram geradas **39 capturas**, totalizando **2.579 KiB**. O financeiro chegou a **Concluído**, após registro da parcela, e o qualitativo chegou a **Publicado**. A recomendação chegou a **Atendida**, com o parecer consultado pela chefia da unidade.

```sh
DATABASE_HOST=127.0.0.1 DATABASE_PORT=5433 \
DATABASE_USER=postgres DATABASE_PASSWORD=postgres DATABASE_NAME=postgres \
TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \
.venv/bin/pytest -m doc --create-db auditoria/tests/doc/ --durations=0 -q -s
```

Os valores `postgres/postgres` acima são credenciais do banco fictício local. O comando recria somente o banco exclusivo de documentação. O registro integral da rodada ficou em `/tmp/auditoria-doc.log` durante a geração.

| Etapa medida | Tempo |
| --- | ---: |
| Criação do esquema (`django_db_setup`) | 69,78 s |
| Seed compartilhado (`e2e_seed`) | 10,30 s |
| Dados do módulo (`dados_auditoria`) | 1,33 s |
| Playwright, navegador e servidor local | 0,79 s |
| Navegação, conferência e captura dos 15 casos | 97,44 s |
| Total da sessão pytest | 180,86 s |

O total inclui coleta, outras fixtures e encerramento. O setup do banco e o seed compartilhado ocorrem uma vez na sessão; os dados do módulo e seus 97,44 s de navegação e captura representam o custo adicional deste manual. A medição é da rodada final, sem somar escrita, leituras ou tentativas anteriores. Os tempos variaram entre rodadas e não representam uma previsão garantida para outros ambientes.

Ruff format não alterou os três arquivos Python. `ruff check` e a conferência de complexidade `C901` passaram. As funções dos roteiros e do seed têm parâmetros e retorno anotados. Nenhuma alteração no código do produto ou na infraestrutura compartilhada foi necessária.

## Capturas geradas

O revisor do diff vê os textos e roteiros; os WebP ficam fora do Git. Todos os nomes abaixo são arquivos em `auditoria/docs/usuario/` e estão referenciados no manual.

| Tarefa | Arquivos WebP |
| --- | --- |
| PAINT | `paint-listagem`, `paint-formulario` |
| CH e planejamento individual | `paint-detalhe`, `planejamento-anual` |
| Relatório | `relatorio-listagem`, `relatorio-formulario`, `relatorio-detalhe` |
| Recomendação e solicitação | `recomendacao-formulario`, `recomendacao-detalhe`, `monitorar-formulario`, `recomendacao-monitorada` |
| Manifestação da unidade | `minhas-recomendacoes`, `monitoramento-gestor`, `manifestacao-formulario`, `manifestacao-registrada`, `manifestacao-enviada` |
| Análise e publicação | `manifestacao-auditor`, `posicionamento-formulario`, `posicionamento-registrado`, `posicionamento-publicado`, `posicionamento-gestor` |
| Benefício financeiro | `beneficio-origem`, `beneficio-financeiro-formulario`, `beneficio-financeiro-detalhe`, `beneficio-financeiro-monitorado`, `parcela-formulario`, `beneficio-financeiro-parcelas`, `beneficio-financeiro-concluido` |
| Benefício qualitativo | `beneficio-qualitativo-formulario`, `beneficio-qualitativo-detalhe`, `beneficio-qualitativo-publicado` |
| Consultas gerenciais | `recomendacoes-setor`, `raint`, `estoque-monitoramentos`, `estoque-recomendacoes`, `relatorio-financeiro`, `relatorio-qualitativo` |
| Indicadores | `indicadores-monitoramento`, `indicadores-beneficios` |

Cada nome recebe o sufixo `.webp`. As capturas têm viewport desktop fixo, dados fictícios e `DEBUG=False`, conforme a fixture compartilhada.
