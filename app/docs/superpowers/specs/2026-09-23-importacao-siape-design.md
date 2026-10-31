# Importação SIAPE paralela, parcial e acompanhada em tempo real — design

Data: 2026-09-23 · Branch: `importacao-siape-paralela`

## Objetivo

Uma tela própria no `rh` para importar os arquivos do extrator SIAPE em quatro passos:

1. **upload** do zip do extrator;
2. **identificação** de cada arquivo (layout, linhas, dependências) com diagnóstico dos não reconhecidos;
3. **seleção** do que será e do que não será importado (importação parcial);
4. **execução paralela** respeitando as precedências, com **acompanhamento em tempo real** e **log detalhado** de sucessos e falhas por layout.

O comando `importar_siape` (e o beat das 01:07) passa a usar o mesmo motor, com tudo selecionado.

Fora de escopo neste primeiro MR: retomar importação interrompida; cancelar no meio; distribuir layouts entre workers Celery; reescrever as 33 funções `importar_*` para granularidade por registro.

## Estado atual (análise de 2026-09-23)

- Upload: `rh/views.py` `upload_arquivos_extrator` grava o zip em `rh/arquivos_siape/` (apagando o anterior); a importação só roda no beat (`rh/beat.py`, comando `importar_siape`).
- Identificação: `comum/importador.py` `identificar_layout` compara o `.REF` do zip, sem espaços, com cada arquivo de `rh/refs/`. Sem match → layout `None`, arquivo ignorado com um `log.info`.
- Execução: serial, pela lista fixa `ordem` (33 layouts) de `ImportadorSIAPE`; o primeiro erro não tratado aborta tudo (`raise`); o registro é um `comum.Log` de uma linha.
- Os caches (`servidores_cache` etc.) vivem na instância (`calc_caches`) — uma instância não pode ser compartilhada entre threads.
- `Servidor.update_or_create` (usado por `servidor1..4`) faz `save()` do servidor e da pessoa física: duas escritas concorrentes no mesmo servidor podem perder campos.
- Progresso: existe `djtools.models.Task` (`total`/`partial`, página `/djtools/process/<uuid>/` com polling). Não há Channels/WebSocket no projeto.

Zip real analisado (`_extracao-22092026.zip`): 32 pares `NNNNNN.REF.gz`/`.TXT.gz`, todos reconhecidos. Maiores volumes: `historico_setor_siape` (107.796 linhas), `servidorafastamentos` (106.355), `historico_funcao` (96.297), `rubrica` (30.786). `historico_afastamento` (8.420) é reconhecido mas está fora da `ordem` desde `a9b0efbaaa` (substituído por `servidorafastamentos`). `servidor5` e `historico_ferias` não vieram.

## Decisões

| Tema | Decisão |
|---|---|
| Paralelismo | Uma `@task` orquestradora com `ThreadPoolExecutor` (N workers, padrão 4, configurável via `Configuracao` `rh`/`importacao_siape_workers`). Funciona igual com e sem Celery, no beat e no comando. |
| Tempo real | Polling de endpoint JSON a cada 2 s (JS simples), como `/djtools/process/`. |
| Seleção parcial | Opção C: marcar um layout marca junto as dependências presentes no zip, com aviso; o usuário pode desmarcar. Dependência ausente no zip ou desmarcada → aviso "usará os dados já existentes no banco" e é tratada como satisfeita. |
| Concorrência | Só uma importação `executando` por vez (tela e comando). |
| Arquivos | Cada importação tem sua pasta `rh/arquivos_siape/importacoes/<id>/`; o fluxo legado em `rh/arquivos_siape/` fica intocado. |
| Permissão | `rh.pode_gerenciar_extracao_siape` (a atual). |

## Precedências

Declaradas uma única vez em `rh/importacao_siape/layouts.py` (substitui a lista `ordem`):

- **Tabelas** (sem dependência): `atividades`, `afastamentos`, `bancos`, `grupo_cargo_emprego`, `cargo_classe`, `diploma_legal`, `funcoes`, `jornada_trabalho`, `nivel_escolaridade`, `pais`, `regime_juridico`, `rubrica`, `estado_civil`, `grupo_ocorrencia`, `situacao_servidor`, `uo`, `titulacoes`.
  - `cargo_emprego` ← `grupo_cargo_emprego`; `ocorrencia` ← `grupo_ocorrencia`.
- **Núcleo do servidor**: `servidor1` ← todas as tabelas.
  - `servidor2` ← `servidor1`; `servidor3` ← `servidor2`; `servidor4` ← `servidor3` (encadeados por causa do `save()` da linha inteira).
  - `servidor5` ← `servidor4`; `email_telefone_servidor` ← `servidor4` (ambos gravam por `.update()` em campos próprios; rodam em paralelo entre si).
- **Históricos** ← fim do núcleo (`servidor5`, `email_telefone_servidor`), paralelos entre si: `servidorafastamentos`, `historico_funcao`, `historico_setor_siape`, `servidor_matriculas`, `historico_ferias`, `pca`.
  - `ferias` ← `historico_ferias` (ambos gravam `Ferias`); `posicionamento_pca` ← `pca`.
- **Inativo**: `historico_afastamento` (`ativo=False`, motivo: substituído por `servidorafastamentos`). Aparece na tela, desabilitado.

A ordem serial atual é uma ordenação topológica válida desse grafo, então rodar com 1 worker reproduz o comportamento de hoje.

## Modelo de dados (`rh`)

- `ImportacaoSiape`: `arquivo` (zip), `enviado_por`, `enviado_em`, `origem` (`tela`/`comando`), `situacao` (`identificada`, `executando`, `concluida`, `concluida_com_falhas`, `falhou`), `inicio`, `fim`, `task` (FK `djtools.Task`, opcional).
- `ImportacaoSiapeArquivo` (um por par REF/TXT): `importacao`, `nome_ref`, `nome_txt`, `layout` (nulo = não reconhecido), `diagnostico` (texto: ref mais próximo, campos a mais/a menos), `selecionado`, `total_linhas`, `processadas`, `falhas`, `situacao` (`pendente`, `aguardando`, `executando`, `concluido`, `falhou`, `pulado`, `ignorado`), `motivo` (traceback ou "dependência X falhou"), `inicio`, `fim`.
  - Um layout pode vir em mais de um par (o importador atual já aceita lista); cada par é uma linha, e as dependências são avaliadas por layout.
- `ImportacaoSiapeOcorrencia`: `arquivo` (FK), `nivel` (`warning`/`error`), `linha` (nº do item quando conhecido), `mensagem`, `criada_em`.

## Componentes

`rh/importacao_siape/` (pacote novo, unidades pequenas):

- `layouts.py` — `LAYOUTS: dict[str, Layout]` (`dependencias`, `ativo`, `motivo_inativo`, `rotulo`) e `fechamento_dependencias(selecionados)`; valida acíclico.
- `identificacao.py` — `identificar(conteudo_ref) -> Identificacao(layout, diagnostico)`: reusa a normalização de `comum.importador.identificar_layout`; sem match, calcula o ref mais próximo por Jaccard dos nomes de campo e lista campos a mais/a menos.
- `preparacao.py` — `preparar(importacao)`: descompacta o zip e os `.gz` na pasta da importação, cria os `ImportacaoSiapeArquivo` com layout, diagnóstico e `total_linhas`, marca por padrão os ativos reconhecidos.
- `execucao.py` — `executar(importacao, workers)`: agenda o grafo só com os arquivos selecionados; submete ao pool os layouts cujas dependências selecionadas terminaram com sucesso; em falha, marca os dependentes transitivos como `pulado`. Cada layout roda com **uma instância própria** de `ImportadorSIAPE`, em `ItensComProgresso` e sob o handler de ocorrências, e fecha a conexão do banco ao final (`connection.close()`). Ao terminar: `executar_save_pos_importacao`, `cache.delete('data_ultima_importacao_siape')`, `comum.Log` de resumo, `situacao` final.
- `progresso.py` — `ItensComProgresso(list)`: `__iter__` conta e grava `processadas` a cada ≈2 % (update direto, sem `save()`); `CapturaOcorrencias(logging.Handler)` ligado ao logger `rh.importador`, filtrando pela thread do layout, grava `warning`/`error` como `ImportacaoSiapeOcorrencia`.

Mudanças em código existente:

- `rh/importador.py`: `_get_map_layout_functions` passa a ser a fonte das funções; `ordem` deriva de `LAYOUTS` (ordenação topológica) para manter compatível quem ainda chama `run()`.
- `rh/management/commands/importar_siape.py`: cria `ImportacaoSiape(origem='comando')` a partir do zip em `rh/arquivos_siape/`, prepara com tudo ativo selecionado e executa o motor de forma síncrona.
- `rh/tasks.py`: `@task('Importação SIAPE') executar_importacao_siape(importacao, task=None)`.

## Telas

`rh/urls.py` + `rh/views.py`, templates seguindo o design system (`docs/design-system.md`; tabela com `<caption>` dentro de `div.table-responsive`):

- `importacao_siape/` — listagem das importações (data, enviado por, origem, situação, duração, falhas) + formulário de upload do zip.
- `importacao_siape/<id>/` — detalhe: tabela por grupo (Tabelas, Núcleo do servidor, Históricos, Não reconhecidos/Inativos) com checkbox, layout, arquivo, linhas, dependências, situação, progresso. JS aplica a opção C ao marcar. Botão **Importar selecionados** (POST) → dispara a task, fica na própria página.
- `importacao_siape/<id>/progresso.json` — situação da importação e, por arquivo, `situacao`, `processadas`, `total_linhas`, `falhas`, `motivo`; o JS consulta a cada 2 s enquanto `executando`.
- `importacao_siape/<id>/arquivo/<arquivo_id>/ocorrencias/` — lista das ocorrências do layout.
- Entrada no `menu.yaml` junto de "Upload Arquivo Extrator".

## Erros

- Exceção não tratada num layout → `falhou` com traceback em `motivo`; dependentes (transitivos) → `pulado` ("dependência X falhou"); independentes seguem.
- Situação final: `concluida` (nenhuma falha), `concluida_com_falhas` (há layout `falhou`/`pulado` ou ocorrência `error`), `falhou` (erro fora dos layouts, ex.: preparação).
- Zip inválido ou sem par REF/TXT → erro de validação no formulário de upload; nada é criado.
- Importação já em execução → botão desabilitado e POST recusado com mensagem; o comando sai com aviso.
- Limitação conhecida: o `importador.py` só tem 7 `log.warning`/`log.error`; várias funções fazem `continue` silencioso. As ocorrências por registro cobrem o que já é logado; granularidade maior fica para iterações seguintes, função a função.

## Testes (enxutos)

- `rh/tests/models/test_importacao_siape_execucao.py` — motor sem banco (funções de layout falsas): respeita precedências; pula dependentes de um layout que falhou; independentes seguem; seleção parcial trata dependência não selecionada como satisfeita.
- `rh/tests/models/test_importacao_siape_identificacao.py` — ref reconhecido; ref com campo alterado gera diagnóstico com o ref mais próximo.
- `rh/tests/fluxos/test_fluxo_importacao_siape.py` — upload do zip montado de `rh/tests/arquivos_siape_novo` → seleção parcial → execução → situações e ocorrências persistidas; endpoint de progresso responde.
- Regressão: `rh/tests/models/test_importador.py` continua verde.

## Riscos

- Carga no Postgres com 4 threads + comandos pesados (`historico_*`): N configurável; 1 reproduz o serial.
- `Servidor.save()` dispara efeitos colaterais (usuário, chaves, histórico de setor); por isso o núcleo do servidor fica encadeado. Se surgir contenção nos históricos, basta acrescentar a dependência em `LAYOUTS`.
- Thread fora do Celery (`method='thread'`) morre com o processo web; aceitável neste primeiro MR (sem retomada).
