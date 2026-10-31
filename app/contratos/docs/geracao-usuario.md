# Registro de geração do manual de Contratos

Rodada de 05/10/2026. Manual em `usuario.md`; roteiros executáveis em `../tests/doc/`.

## Ambiente e execução

Navegação real por pytest/Playwright, exclusivamente em PostgreSQL local com dados fictícios e banco `test_suap_doc_e2e`. Nenhum acesso a homologação ou produção. Reuso integral de `djtools.e2e_fixtures`, `Tela` e `capturas(DESTINO)`; nenhuma alteração na infraestrutura compartilhada.

```sh
DATABASE_HOST=127.0.0.1 DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
DATABASE_NAME=postgres TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \
.venv/bin/pytest -m doc --create-db contratos/tests/doc/ --durations=0 -q
```

As credenciais acima pertencem ao banco fictício local. Capturas WebP de desktop 1440 × 900, com `DEBUG=False`, em `usuario/`, ignoradas pelo Git. O seed cria um gerente, um fiscal, campus, processo, empresa, base legal, subtipo, ano corrente e nota de empenho com saldo. Como o módulo não possuía suíte e2e nem factories, o seed nasce na suíte doc; as factories de Protocolo e Tesouro Gerencial ficam nos módulos donos.

## Roteiro e papéis

Tarefas centrais vieram do inventário e do menu. Cronograma e parcelas foram unidos por objetivo. Cadastros básicos viraram apoio, sem tutorial. Consultas adicionais vieram das portas do menu e foram executadas no navegador.

| Tarefa | Papel efetivamente usado | Origem do papel mínimo publicado |
| --- | --- | --- |
| Cadastro, cronograma/parcelas, designação de fiscal | Gerente de Contrato | `bin/scripts/papeis.py`: `add_contrato`, `pode_gerar_cronograma`, `pode_adicionar_fiscal`; também Operador de Contrato. |
| Vincular empenho | Gerente de Contrato | `bin/scripts/papeis.py contratos.pode_adicionar_empenho`; complementado pela autorização do contrato. |
| Medir parcela | Fiscal de Contrato, previamente designado na UI | `bin/scripts/papeis.py contratos.pode_efetuar_medicao` + regra manual por vínculo em `Contrato.pode_efetuar_medicao` / `eh_fiscal`. |
| Consultar fiscais, indicadores, pendências, situação e exportação | Gerente de Contrato, também Servidor | Grupos/permissões do `menu.yaml`. Não foi ensaiado um servidor sem grupo adicional. |
| Relatórios de renovação, licitação, energia, terceirizados e empenhos | Gerente de Contrato | Grupos explícitos do `menu.yaml`. Auditor/Operador não foram autenticados nesta rodada. |
| Consulta interna | Gerente de Contrato | `bin/scripts/papeis.py contratos.view_contrato`: sete grupos; frase genérica no manual. |
| Consulta pública | Navegador sem sessão | Navegação real sem login e sem redirecionamento à autenticação. |

## Capturas geradas

28 telas/estados capturados; 27 referenciados diretamente pelo manual. `responsabilidades-fiscais` é captura de apoio, cujo conteúdo foi conferido e resumido em um parágrafo.

- Cadastro/consulta: `contratos-listagem`, `contrato-cadastro`, `contrato-detalhamento`, `contrato-consulta`.
- Cronograma: `cronograma-numero`, `cronograma-gerar-parcelas`, `cronograma-parcelas`.
- Fiscal: `fiscal-cadastro`, `fiscais`, `consulta-fiscais`, `responsabilidades-fiscais`.
- Empenho/medição: `empenho-cadastro`, `empenhos`, `medicao-formulario`, `medicao-registrada`.
- Consultas: `indicadores`, `notificar-pendencias`, `relatorio-aditivos`, `relatorio-licitacoes`, `relatorio-energia`, `relatorio-terceirizados`, `relatorio-empenhos`, `relatorio-pendencias`, `situacao-contratos`.
- Exportação: `exportacao`, `exportacao-resultado`; download XLS real, sem falha e não vazio.
- Público: `contratos-publicos`, `contrato-publico`.

## Limites e exclusões

| Tela/fluxo | Motivo e alcance |
| --- | --- |
| Cadastros básicos | Apoio citado sem passo a passo, conforme anatomia do manual; não foram executados CRUDs dessas tabelas. |
| Energia, terceirizados, renovação/licitação e situação | Telas e filtros executados; resultados vazios neste conjunto fictício. Não há demonstração de consumo elétrico, trabalhador terceirizado ou contrato candidato à renovação/licitação. |
| Relatório de Empenhos | Tela aberta e capturada. Não houve submissão dos filtros dessa tela; a vinculação de empenho e o valor na medição foram executados em seus fluxos próprios. |
| Notificar Pendências | Filtro por campus executado e tela sem contratos apresentada. Não foi enviado aviso a destinatários nem exercitada seleção/envio de notificações. |
| Aditivos, apostilamentos, garantias, penalidades, cancelamento e encerramento/rescisão | Ações de ciclo de vida fora do roteiro central do inventário desta rodada. Não executadas; não há passos dessas ações no manual. |
| Ocorrências independentes, mão de obra, conta vinculada, agenda, itens contratados, IMR e recebimentos | Exigem roteiros e dados adicionais de domínio. Não executados; o manual cobre a medição simples sem dedicação exclusiva e com empenho. |
| Publicações, anexos/documentos relacionados, despacho e ComprasGov | Não foram cadastrados/importados; a pendência de publicação ausente foi observada no relatório. Sem instruções de execução dessas ações. |
| Download de PDF na consulta pública | Link visível e citado; download desse PDF não foi acionado. O download validado nesta rodada foi o XLS da exportação. |

## Separação de evidências

Todos os passos numerados descrevem navegação executada. As telas foram abertas diretamente pelas URLs; o manual evita instruir um caminho de menu que não foi clicado. Nomes dos cadastros de apoio e os perfis mínimos vieram de menu/permissões, não de uma tentativa de todos os perfis.

A exigência de designação do fiscal e as limitações de gestão por contrato foram complementadas pela leitura das regras de autorização. O caso positivo foi executado; acesso negado, designação vencida, restrição por unidade e setores gerenciadores não foram provocados. Não foram provocadas validações de número duplicado, data invertida, risco de mão de obra, prorrogação legal, formato inválido, excesso de saldo, nota repetida ou arquivo inválido. Orientações de formato/limite no manual vêm da própria tela renderizada.

## Validação e custo

A suíte inteira foi executada com banco recriado. Ruff format/check e C901 ≤ 10 passaram em todos os arquivos Python novos. O pytest emite `UnorderedObjectListWarning` na paginação existente de fiscais; a consulta filtrada retornou o fiscal esperado.

Resultado final: **19 testes passaram**, nenhuma falha, em **86,33 s**. Conferência automática: **27 referências de imagens**, **28 WebP gerados**, nenhum arquivo ausente. Gráficos foram recapturados após aguardar a animação observada; barras finais de R$ 6.000,00 conferidas visualmente.

| Parcela de custo | Tempo medido |
| --- | --- |
| Criação do schema (`django_db_setup`, uma vez por sessão) | 21,55 s |
| Seed base compartilhado (`e2e_seed`, uma vez por sessão) | 8,53 s |
| Seed específico de contratos (uma vez por sessão) | 0,49 s |
| Setup total, incluindo browser e servidor | 30,99 s |
| Navegação, preenchimento, gravações, capturas e download (soma das chamadas) | 54,61 s |
| Rodada completa com teardown | 86,33 s |

Esses tempos são da rodada completa final, não uma estimativa nem o tempo de autoria do manual. A recriação do banco foi medida separadamente; navegação/captura é a parcela que se repete a cada módulo. Rodadas diagnósticas anteriores não entram nesse custo.
