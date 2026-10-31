"""Importação SIAPE: recebe o zip do extrator SIAPE, identifica seus arquivos e importa os dados
para o SUAP em paralelo, com progresso e ocorrências visíveis na tela.

Visão geral do fluxo, do upload ao fim da execução:

1. **Upload** (`views.importacao_siape_lista` + `forms.ImportacaoSiapeUploadForm`): o usuário envia
   o zip do extrator.
2. **`preparacao`**: descompacta o zip, grava cada par REF/TXT na pasta da importação
   (`armazenamento`) e registra um `ImportacaoSiapeArquivo` por par, já identificado.
3. **`identificacao`**: compara o `.REF` de cada arquivo com os layouts conhecidos (`rh/refs`) para
   descobrir qual layout ele contém; sem correspondência exata, monta um diagnóstico (layout mais
   próximo, campos a mais/a menos) para ajudar a investigar.
4. **`layouts`**: fonte única dos layouts do extrator, seus grupos (Tabelas, Núcleo do servidor,
   Históricos), as dependências entre eles (o grafo de precedência) e, para os que podem ser
   divididos em lotes, a chave de partição (o que não pode cair em dois lotes).
5. **`lotes`**: divide os itens de um arquivo grande em lotes que podem rodar em paralelo, sem
   nunca separar linhas com a mesma chave de partição em lotes diferentes.
6. **`agendador`**: motor genérico de execução de um grafo de dependências, em série (um worker) ou
   num pool de threads (workers > 1); cada nó do grafo é expandido em etapas de unidades.
7. **`execucao`** / **`execucao_lotes`**: o motor da importação em si. `execucao` orquestra as
   transições de situação da `ImportacaoSiape` (identificada ⇄ agendada; identificada/agendada →
   executando → concluída, concluída com falhas ou falhou) e chama o `agendador` sobre o grafo de
   layouts selecionados. A falha é fechada por dois caminhos: `executar_importacao` finaliza a si
   mesma quando uma exceção escapa do grafo (fecha os arquivos/lotes ainda pendentes, grava o
   `Log` e apaga a pasta no seu próprio `try`/`except`/`finally`); `encerrar_com_falha` é o portão
   usado por quem precisa encerrar, de fora, uma importação presa em `executando` — a interrupção
   manual (`interromper_importacao`) e a falha de despacho da task (`views._iniciar`).
   `execucao_lotes` (`ExecucaoPorLotes`) fornece os callbacks do agendador para esse grafo: expande
   cada layout em lotes, executa cada lote com o `ImportadorSIAPE` (`rh.importador`) — tentando de
   novo, do zero, até duas vezes se o lote esbarrar num deadlock do Postgres (`_eh_deadlock`;
   `servidor2` e `historico_funcao` têm um efeito colateral por setor que nenhuma partição evita,
   ver `layouts._PARTICOES`) — e, ao fim do layout, consolida a situação de cada arquivo a partir
   dos lotes.
8. **`progresso`**: instrumenta a execução sem alterar as funções `importar_*` do
   `ImportadorSIAPE` — reporta quantos itens já foram percorridos e captura, via logging handler,
   os avisos/erros emitidos durante a importação (que `execucao_lotes` grava como
   `ImportacaoSiapeOcorrencia`).
9. **`armazenamento`**: acesso às pastas da importação no storage padrão (sistema de arquivos em
   dev, S3/MinIO em produção) e sua limpeza ao fim da execução.
10. **`views`** / **`forms`**: as telas (upload, seleção de arquivos, progresso, interrupção,
    ocorrências).

Fora do pacote, mas parte do mesmo fluxo: o comando `rh/management/commands/importar_siape.py`
(agendado no `beat` às 01:07 via `rh/beat.py`) roda as importações agendadas pela tela e, em
seguida, os zips deixados na pasta do extrator; a task `rh.tasks.executar_importacao_siape`
(`@task`: Celery ou thread, inline nos testes) é quem efetivamente chama
`execucao.executar_importacao` a partir da tela ("Importar selecionados agora"/"Executar agora"). Os
models (`ImportacaoSiape`, `ImportacaoSiapeArquivo`, `ImportacaoSiapeLote`,
`ImportacaoSiapeOcorrencia`, `SituacaoImportacaoSiape`, `SituacaoArquivoSiape`) vivem em
`rh/models/importacao/importacao_siape.py`, fora deste pacote.

Invariantes importantes:

- **Só uma importação `executando` por vez**: `execucao._travar` usa
  `pg_advisory_xact_lock` para serializar `iniciar_importacao`, `agendar_importacao`,
  `cancelar_agendamento` e `encerrar_com_falha` entre si, e `ImportacaoSiape.existe_em_execucao()`
  é checado antes de começar uma nova.
- **Uma chave de partição nunca fica em dois lotes** (`lotes.dividir_em_lotes`): evita que duas
  linhas do mesmo servidor/matrícula/cargo sejam processadas em paralelo e criem duplicatas ou
  se pisem. Isso não cobre efeitos colaterais fora do registro da própria linha: `servidor2` e
  `historico_funcao` gravam `ServidorFuncaoHistorico`, cujo post_save mexe em todo o SETOR da
  função (não só na linha), então esses dois não têm partição — rodam sempre num único lote (ver
  `layouts._PARTICOES`).
- **Um lote que esbarra num deadlock do Postgres tenta de novo, do zero**, até duas vezes
  (`execucao_lotes._eh_deadlock`/`_rodar_com_retentativa`). Antes de tentar de novo,
  `_preparar_retentativa` desfaz **tudo** que a tentativa perdedora já tinha contado: o
  `processadas` (arquivo e lote) e as próprias `ImportacaoSiapeOcorrencia` que ela tinha criado —
  apagadas, com `falhas`/`avisos` (arquivo e lote) subtraídos de volta (`_OcorrenciasDaTentativa`/
  `_desfazer_ocorrencias`), senão a retentativa duplicaria essas ocorrências na tela e um
  `error`/`critical` perdido faria a importação terminar `concluida_com_falhas` mesmo com a
  retentativa dando certo — e registra uma ocorrência `warning` própria (permanente, conta em
  `avisos`) avisando que houve uma retentativa; só esgotadas as tentativas (ou para qualquer erro
  que não seja deadlock) o lote falha como antes.
- **Os arquivos da importação são apagados em todo estado terminal**, por dois caminhos diferentes:
  `execucao.executar_importacao` finaliza a si mesma em qualquer desfecho (concluída, concluída
  com falhas ou falhou — essa última fechando antes os arquivos/lotes que ainda estavam
  pendentes), grava o `Log` e apaga a pasta no seu próprio `finally`; `execucao.encerrar_com_falha`
  faz o mesmo (trava, transição condicional, arquivos/lotes pendentes, `Log`, pasta) para quem
  precisa encerrar uma importação presa em `executando` de fora dela: a interrupção manual e a
  falha de despacho da task na tela (`views._iniciar`). Importações que nunca rodam
  (`identificada`) mantêm os arquivos.
- **Nunca `exists()` numa pasta do storage**: no S3/MinIO uma pasta é só um prefixo de chave, e
  `exists()` devolveria `False` mesmo com arquivos dentro (ver `armazenamento`).
- **Nos testes, as importações rodam, em regra, com `workers=1`** (execução em série, sem pool de
  threads), porque as threads do pool não enxergam a transação do teste: os testes de tela, de
  comando e de fluxo usam a fixture `importacao_serial` (`rh/tests/conftest.py`, que configura
  `importacao_siape_workers` do app `rh` como `1`, o mesmo caminho de produção com essa
  configuração). Um teste de fluxo passa `workers=2` de propósito, com `transaction=True`, para
  exercitar o pool.
"""
