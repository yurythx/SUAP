# processo_eletronico

Documentação técnica do módulo **Processos Eletrônicos** do SUAP. O módulo registra processos, documentos, solicitações e trâmites, controla visibilidade por nível de acesso e expõe a operação interna e a consulta pública.

## Visão geral

`processo_eletronico` é um app Django clássico. Seu núcleo está concentrado em `models.py`, `views.py`, `forms.py`, `admin.py`, `urls.py`, templates HTML e quatro workflows BPMN. A unidade de movimentação é o `Processo`; cada encaminhamento é um `Tramite`; documentos internos/externos são vinculados ao processo por modelos próprios.

O estado do processo é uma máquina de estados (`ProcessoStatus`). A leitura não é equivalente à operação: `Processo.pode_ler()` resolve acesso público, interessado, setor, usuário, cargo e solicitações; a edição e a tramitação possuem verificações adicionais.

## Responsabilidades

- Criar processos diretamente ou a partir de requerimentos.
- Gerar e manter NUP 21; sincronizar NUP 17 quando o app `protocolo` estiver instalado.
- Vincular documentos de texto, documentos digitalizados, minutas e despachos.
- Encaminhar, receber, atribuir, atender, distribuir e consultar processos.
- Controlar níveis Público, Restrito e Privado, hipóteses legais e solicitações de alteração.
- Gerenciar ciência, juntada de documentos, despacho e assinatura.
- Relacionar, apensar e anexar processos.
- Registrar ações, remoções lógicas, integridade e compartilhamentos.
- Emitir PDF, ZIP, capa, termos, etiquetas e estatísticas.
- Integrar tramitação externa pelo `conectagov_pen` e criação opcional de compras.

## Atores e papéis

| Ator/grupo | Capacidades declaradas em `permissions.yaml` |
|---|---|
| Operador de Processo Eletrônico | Criar/alterar/visualizar processos, tramitar, administrar grupos de interessados e cadastros auxiliares previstos no arquivo. |
| Chefe de Setor | Criar/alterar/visualizar e tramitar; administrar distribuição de trâmites. |
| Tramitador de Processos Eletrônicos | Tramitar processos. |
| Servidores Com Poder de Chefe | Gerenciar permissões do setor. |
| Gerente Sistêmico de Processo Eletrônico | Configurar módulo, tipos, modelos, configurações de trâmite, processos e etiquetas. |
| Servidor, Aposentado, Prestador de Serviço | Visualizar processos; abrir requerimentos conforme o grupo. |
| Aluno | Visualizar processos e administrar as próprias solicitações de alteração conforme permissão. |
| Auditor, Procurador, Usuário Externo | Visualização conforme grupo e regras de acesso do processo. |
| Gestão Nível de Acesso dos Processos Documentos Eletrônicos | Alterar nível de acesso e analisar solicitações. |

`permissions.yaml` não documenta toda a matriz efetiva de setor, vínculo, cargo, interessado e nível de acesso. ⚠️ REVISAR: manter uma matriz operacional derivada das regras de `ProcessoPermissionMixin`, `Tramite` e compartilhamentos.

## Estrutura interna

| Arquivo/área | Papel |
|---|---|
| `apps.py` | Registra sinais de `Processo` e `SolicitacaoJuntadaDocumento`. |
| `models.py` | 57 classes de modelo/entidades, incluindo bases abstratas, estados, permissões, documentos, requerimentos, solicitações, auditoria e indicadores. |
| `status.py` | Constantes e escolhas de estado. |
| `managers.py` | Querysets ativos e solicitações pendentes. |
| `views.py` | Interface autenticada, pública, administrativa, PDFs, wizards e ações. |
| `forms.py` | Validação de criação, edição, tramitação, documentos, acesso, solicitações e consulta pública. |
| `urls.py` | Rotas do módulo; não há `api.py` local. |
| `admin.py` | Administração de processos, tipos, requerimentos, modelos, distribuição, compartilhamento, rótulos e solicitações de acesso. |
| `utils.py`, `pdf.py`, `etiqueta.py`, `tables.py`, `exceptions.py` | Notificação, permissões, composição de PDF/ZIP, etiqueta, tabelas/filtros e exceções de domínio. |
| `tasks.py`, `beat.py`, `management/commands/` | Processamento assíncrono, agendamento e manutenção. |
| `signals.py` | Compatibilidade com `protocolo` e integração opcional com `compras`. |
| `templates/` | Telas, conteúdo e documentos imprimíveis. |
| `static/` | JavaScript auxiliar dos formulários/telas do módulo. |
| `workflows/` | `processo_eletronico.bpmn`, `anexacao.bpmn`, `apensar_desapensar.bpmn` e `adicionar_documentos.bpmn`. |

## Endpoints principais

Todas as rotas abaixo são relativas a `/processo_eletronico/`; o inventário normativo é `urls.py`.

| Área | Rotas/names principais |
|---|---|
| Processo | `processo`, `processo_por_numero`, `busca_processo`, `processo_editar_interessados`, `registro_acoes_processo`, `processo_finalizar`, `processo_desfinalizar`, `processo_acompanhar`, `processo_desacompanhar`, `processo_editar_assunto`, `linha_tempo`. |
| Relacionamentos | `anexar_processos`, `apensar_processos`, `desapensar_processo`, `desapensar_todos_processos`, `listar_processos_relacionado`, `adicionar_processo_relacionado`, `remover_relacionamento_processos`. |
| Trâmite | `selecao_caixa_processos`, `caixa_processos`, `processo_encaminhar`, `encaminhar_sem_despacho`, `processo_encaminhar_lote`, `processo_receber`, `processo_receber_lote`, `processo_remover_ultimo_tramite`, `atribuir_processo`, `atender_processo`, `movimentacao_interna_processo`, `adicionar_prioridade`, `adicionar_rotulo`. |
| Documentos | `listar_documentos_adicionar`, `adicionar_documento_processo`, `documento_upload`, `remover_documento_texto_processo`, `remover_documento_digitalizado_processo`, verificações de integridade e edição de upload. |
| Minuta | `listar_minutas_adicionar`, `adicionar_processo_minuta`, `visualizar_minuta`, `conteudo_minuta`, `clonar_minuta_em_documento`. |
| Solicitações | `solicitar_ciencia`, `dar_ciencia`, `cancelar_solicitacao_ciencia`, `solicitar_despacho`, CRUD/análise de despacho, envio/conclusão/análise de juntada e `remover_documento_juntada`. |
| Requerimento | `cadastrar_requerimento`, `gerenciar_requerimento`, `editar_requerimento`, `cancelar_requerimento`, `finalizar_requerimento`, inclusão/upload/remoção/visualização de documentos. |
| Acesso | `consulta_publica`, `visualizar_processo_publica`, `visualizar_capa_processo_publica`, `tramite_conteudo` público, solicitação/análise/indeferimento de alteração de nível. |
| Administração | `/admin/processo_eletronico/processo/`, `requerimento/`, `tipoprocesso/`, `modelodespacho/`, `configuracaotramiteprocesso/`, `configuracaoprocessoeletronico/`, `tramitedistribuicao/`, `rotulo/`, `solicitacaoalteracaonivelacesso/`. |
| Barramento | `processo_encaminhar_externo` (view importada de `conectagov_pen`), `encaminhar_externamente`, recibos e reativação. |

⚠️ REVISAR: conferir o inventário desta tabela após cada alteração em `urls.py`; a lista completa contém rotas auxiliares sem nome, variantes UUID públicas e rotas de integridade/PDF.

## Modelos de domínio

O ERD foi particionado por responsabilidade porque `models.py` contém 57 entidades/base-modelos. O índice e a regra de unicidade estão em [`modelo-de-dados/_indice.md`](modelo-de-dados/_indice.md).

- Processo e relações: [`modelo-de-dados/processo.md`](modelo-de-dados/processo.md).
- Tramitação e solicitações operacionais: [`modelo-de-dados/tramitacao.md`](modelo-de-dados/tramitacao.md).
- Documentos e minutas: [`modelo-de-dados/documentos.md`](modelo-de-dados/documentos.md).
- Requerimentos: [`modelo-de-dados/requerimentos.md`](modelo-de-dados/requerimentos.md).
- Solicitações e níveis de acesso: [`modelo-de-dados/solicitacoes.md`](modelo-de-dados/solicitacoes.md).
- Configuração, compartilhamento e indicadores: [`modelo-de-dados/operacao-e-indicadores.md`](modelo-de-dados/operacao-e-indicadores.md).

## Regras de negócio chave

- NUP 21 é gerado a partir da unidade organizacional; o NUP 17 é compatibilidade opcional.
- Público, Restrito e Privado/Sigiloso determinam leitura, compartilhamento e exigência de hipótese legal.
- Processo não deve ser encaminhado se houver pendência documental, processo anexado/bloqueio ou trâmite não concluído.
- Documento de texto precisa estar finalizado/assinado para entrar no processo; remoção do vínculo é lógica.
- Trâmite assinado não deve ser alterado; integridade é verificável por rota própria.
- Recebimento e encaminhamento atualizam o último trâmite, setor atual, prazo, histórico e notificações.
- Ciência, despacho e juntada possuem estados próprios; vencimento pode liberar o processo e gerar termo/notificação.
- Anexação e apensamento não são equivalentes: anexação incorpora o processo e o marca como anexado; apensamento mantém a relação processual.
- Alteração de nível pode exigir trâmite para pessoa/setor; solicitação aberta bloqueia nova alteração.
- PDF/ZIP respeitam `pode_ler`; conteúdo restrito pode ser reduzido a dados básicos conforme o contexto.
- Acesso público requer processo público e tipo habilitado, salvo regras externas documentadas no código.

## Jobs / Tasks Celery

| Mecanismo | Identificador | Efeito |
|---|---|---|
| Task | `Gerar Processo PDF` | Compõe capa, requerimento, documentos, despachos e minutas. |
| Task | `Gerar Zip do Processo` | Gera partes PDF e empacota em ZIP temporário. |
| Task | `Criar Processo com Trâmite` | Converte arquivos suportados, valida integridade, cria documentos e primeiro trâmite. |
| Beat 01:07 | `processo_eletronico_atualizar_status_geral_processo` | Atualiza estados gerais e solicitações. |
| Beat 01:37 | `processo_eletronico_gerar_numeros` | Gera/atualiza indicadores de números. |
| Beat 02:07 | `processo_eletronico_atualizar_permissoes` | Atualiza permissões/compartilhamentos derivados. |
| Beat 02:37 | `processo_eletronico_checar_prazos_recebimento` | Verifica decurso de prazos de recebimento. |

Comandos de manutenção/carga observados em `management/commands/`: `processo_eletronico_ajustar_status_processos_antigos` (status legados), `processo_eletronico_ajustar_vinculos_duplicados` (migração de vínculos duplicados), `processo_eletronico_atualizar_permissoes` (remove permissões de servidores inativos), `processo_eletronico_atualizar_status_ciencia` (atualiza ciência), `processo_eletronico_atualizar_status_geral_processo` (status e log), `processo_eletronico_atualizar_termo_ciencia` (nível de acesso de termos), `processo_eletronico_checar_prazos_recebimento` (recebimento por decurso), `processo_eletronico_corrigir_despachos_violados`, `processo_eletronico_corrigir_setor_ultimo_tramite`, `processo_eletronico_corrigir_tramites_descasados`, `processo_eletronico_destravar_processo_juntada_documento`, `processo_eletronico_dump_pessoafisica`, `processo_eletronico_dump_vinculo`, `processo_eletronico_gerar_numeros`, `processo_eletronico_gerar_nup17`, `processo_eletronico_initial`, `processo_eletronico_popular_search_field_processo` e `processo_eletronico_reassinar_modelos`.

O armazenamento temporário e a execução Celery dependem da configuração global. ⚠️ REVISAR: documentar retenção, limpeza e limite operacional de arquivos temporários.

## Dependências

Dependências declaradas para o módulo em `module_dependencies.json`: `comum`, `documento_eletronico`, `rh`, `conectagov_pen` e `contenttypes`. Integrações opcionais: `protocolo` e `compras`. Dependências de entrada e contratos estão detalhados em [`FRONTEIRA.md`](FRONTEIRA.md).

## Configuração

As chaves são armazenadas por `comum.Configuracao`, namespace `processo_eletronico`. O formulário `ConfiguracaoForm` referencia:

`email_processo_eletronico`, `hipotese_legal_documento_abertura_requerimento`, `base_conhecimento_permissao_acesso_processo` (se `centralservicos` estiver instalado), `tamanho_maximo_upload_personalizado`, `pessoas_permitidas_realizar_upload_personalizado`, `tipo_processo_solicitar_emissao_diploma`, `tipo_processo_demanda_externa_do_cidadao`, `blacklist`, `termo_ciencia_publico`, `permite_recebimento_lote`, `permite_encaminhamento_lote`, `permite_anexar_aquivos_media`, `permite_distribuir_ao_tramitar`, `permite_excluir_comentario_processo`, `atribuir_permissao_servidores_funcao`, `exibir_numeracao_nup21`, `exibir_dados_basicos_listagem`, `bloquear_processos_apensados`, `texto_termo_ciencia`, `impedir_exclusao_minuta_anexao_processo`, `impedir_inativacao_servidor`, `permitir_grupos_interessados`, `registrar_acoes_processos_publicos`, `termo_decurso_prazo_solicitacao_ciencia`, `cores_rotulos`, `exibir_setor_inativo_no_filtro`, `prazo_recebimento_processo` e `habilitar_impressao_etiqueta`. O código também consulta `email_processo_eletronico` e `blacklist` em regras de domínio.

⚠️ REVISAR: não há neste módulo um catálogo central com tipo, valor padrão, proprietário e impacto de cada chave; consolidar isso antes de operar configuração em produção.

## Como testar

O módulo contém features legadas em `features/` e depende dos fixtures/cadastros de `comum`, `rh` e `documento_eletronico`. Para BDD: `python manage.py test_behave --behave_stop --noinput processo_eletronico`. Para a suíte geral: `pytest -q processo_eletronico`. O banco de teste deve ser PostgreSQL configurado conforme `AGENTS.md`.

Esta documentação não altera nem descreve como fonte normativa arquivos em `processo_eletronico/tests/`; ⚠️ REVISAR: alinhar cenários automatizados e esta documentação quando a suíte for mantida.

## Links

- [HLA](HLA.md)
- [Glossário](GLOSSARIO.md)
- [ERD particionado](modelo-de-dados/_indice.md)
- [Fronteira](FRONTEIRA.md)
- [Fluxos](fluxos/criar-processo-e-primeiro-tramite.md)
- [Workflow BPMN principal](../workflows/processo_eletronico.bpmn)
- [Menu](../menu.yaml), [permissões](../permissions.yaml), [rotas](../urls.py)

_Gerado/atualizado via subagent `documentador` em 2026-09-10._
