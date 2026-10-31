# Avaliação Integrada

> Aplica a autoavaliação institucional do IFRN: monta o instrumento (eixos → dimensões → macroprocessos → indicadores), identifica quem deve responder (servidores, alunos e sociedade civil), coleta as respostas e consolida os resultados.

## Visão geral

O módulo cobre o ciclo da avaliação institucional exigida pelo SINAES/CPA. Um **instrumento**
(catálogo de indicadores organizado em eixos, dimensões e macroprocessos) é reaproveitado a cada
**avaliação** — a aplicação desse instrumento num ano/período, para um público e um prazo. A partir
dos filtros da avaliação o sistema **materializa o público-alvo** em registros `Respondente` (um por
pessoa apta), cada um enxergando apenas os indicadores do seu segmento, campus, área de vinculação e
modalidade. As respostas são gravadas em `Resposta` e devolvidas em relatórios com distribuição de
frequência, medidas-resumo e exportação XLSX.

O módulo é a única porta do SUAP por onde alguém **sem conta** responde um formulário: avaliações com
segmento de Sociedade Civil publicam um link tokenizado em "Serviços de Acesso Público".

## Responsabilidades

- Manter o instrumento de avaliação: `Eixo`, `Dimensao`, `Macroprocesso`, `Indicador` (com `Variavel`,
  `OpcaoResposta`, `Iterador`), `EscalaLikert`/`NivelEscalaLikert`, `TipoAvaliacao` e `Segmento`.
- Cadastrar avaliações (ano, período, prazo, público, textos de instrução) e gerar seu público-alvo.
- Decidir **quais indicadores cada respondente vê** (`Respondente.get_indicadores`) e montar o
  formulário dinâmico correspondente (`views.montar_formulario`).
- Coletar, persistir e percentualizar respostas (`Resposta.processar`).
- Publicar o questionário externo (token + reCAPTCHA) para a sociedade civil.
- Disparar e-mails de convite/lembrete aos respondentes não finalizados.
- Consolidar resultados: relatório por indicador (gráficos e medidas), quadro-resumo por
  campus × segmento e exportação XLSX.
- Manter as Comissões CPA (central e por campus) e, como efeito colateral, a composição dos grupos
  `cpa_central` e `cpa_campus`.

**Fora de escopo:** cadastro de pessoas, setores e áreas de vinculação (`rh` — inclusive as duas telas
`"/rh/definir_areas_vinculacao/"` e `"/rh/areas_vinculacao_setor/"`, que este módulo apenas **publica**
no menu); cadastro acadêmico de alunos, cursos, diários e professores (`edu`); contratos e mão de obra
terceirizada (`contratos`); estágios/supervisores (`estagios`); a portaria em si (`documento_eletronico`).

## Atores e papéis

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Administrador de Avaliação Institucional | grupo `Administrador de Avaliação Institucional` (`permissions.yaml`) | Tudo: manter o instrumento e as comissões, criar avaliações, gerar público-alvo **com e sem exclusão de respostas**, ver dados identificáveis dos respondentes, enviar lembretes, ver relatórios e quadro-resumo, exportar respostas |
| Aplicador de Avaliação Institucional | grupo `Aplicador de Avaliação Institucional` | Cria/edita avaliações, gera público-alvo (sem exclusão), visualiza questionário de terceiros, vê relatórios e quadro-resumo, exporta respostas. **Não** vê dados identificáveis nem envia lembrete |
| Visualizador de Avaliação Institucional | grupo `Visualizador de Avaliação Institucional` | Somente leitura: `view_avaliacao`, `view_resposta`, `pode_ver_relatorios`, `pode_ver_relatorio_indicadores` |
| Membro de CPA | grupos `cpa_central` / `cpa_campus` | _derivado_ — escritos automaticamente por `ComissaoCPA` (`m2m_changed` em `vinculos_membros`). Não concedem permissões do módulo: servem para tornar o membro público-alvo dos segmentos `CPA Central`/`CPA Campus`. ⚠️ REVISAR: os grupos não constam de `permissions.yaml` deste módulo |
| Respondente (público interno) | _derivado_ — `Respondente.user` | Responde **apenas o próprio** questionário (`views.questionario` compara `respondente.user != request.user`). Nenhum grupo é exigido |
| Respondente externo (sociedade civil) | _sem autenticação_ — token na URL + reCAPTCHA | Identifica-se por e-mail/matrícula/CPF/CNPJ e responde o questionário do segmento escolhido |

## Estrutura interna

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `avaliacao_integrada/models.py` (arquivo único, 2.397 linhas) | 15 entidades + praticamente toda a regra de negócio ("fat model"): seleção de público-alvo, seleção de indicadores, percentuais, tokens, e-mails |
| Views | `avaliacao_integrada/views.py` | 18 views funcionais (uma por rota) + 2 hooks de layout (`servicos_anonimos`, `index_inscricoes`) + 4 helpers, dos quais `montar_formulario` é o núcleo do questionário dinâmico |
| URLs | `avaliacao_integrada/urls.py` | 18 rotas sob `/avaliacao_integrada/` |
| API | — | _N/A — o módulo não expõe django-ninja; a única resposta JSON é `respondente_externo_check`_ |
| Forms | `avaliacao_integrada/forms.py` | `EixoForm`, `IndicadorForm`, `AvaliacaoForm` (ambos via `SegmentacaoForm`), `AvaliacaoExternaForm` (reCAPTCHA), `RelatorioForm`, `RelatorioXLSXForm`, `FiltroIndicadorForm`, `ComissaoCPAForm`, `EscalaLikertForm`, `EnviarEmailRespondentesForm` |
| Admin | `avaliacao_integrada/admin.py` | 10 `ModelAdminPlus` registrados (Eixo, Dimensão, Macroprocesso, TipoAvaliação, Segmento, Indicador, Avaliação, Resposta, ComissaoCPA, EscalaLikert) + inlines `Variavel`, `OpcaoResposta`, `Iterador`, `NivelEscalaLikert`. É a interface principal do módulo — o `menu.yaml` aponta 9 das 12 entradas para `/admin/` |
| Tasks | `avaliacao_integrada/tasks.py` | `relatorio_xlsx`, `reprocessar_publico_alvo`, `exportar_crosstab_xlsx` (`@task` de `djtools.assincrono`) |
| Commands | `avaliacao_integrada/management/commands/` | 16 commands — ver tabela abaixo |
| Outros | `utils.py`, `respondente_helper.py`, `typing_defs.py`, `exceptions.py`, `static/avaliacao_integrada/js/` | `atualizar_parametro_tab` (navegação por abas); `RespondenteHelper` (versão cacheada em Redis de `get_indicadores`/percentual); TypedDicts do contrato de montagem e dos tokens; `AvaliacaoDataCleanupError`; 4 arquivos JS (`AvaliacaoExterna.js`, `IndicadorForm.js`, `quadro_resumo.js`, `inclui_membros_por_setor.js`) |

Não há `signals.py`: o único signal (`m2m_changed` dos membros da CPA) é registrado no fim de
`models.py`.

## Endpoints principais

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| GET | `/avaliacao_integrada/avaliacao/<pk>/` | `avaliacao` | `view_avaliacao` **e** `change_avaliacao` |
| GET | `/avaliacao_integrada/avaliacao/<pk>/?identificar_respondentes` | `avaliacao` → `tasks.reprocessar_publico_alvo` | `pode_gerar_publico_alvo` |
| GET | `/avaliacao_integrada/avaliacao/<pk>/?excluir_e_identificar_respondentes` | `avaliacao` → `tasks.reprocessar_publico_alvo(excluir=True)` | `pode_reprocessar_publico_alvo_com_exclusao` |
| GET | `/avaliacao_integrada/avaliacao/<avaliacao_id>/setores_sem_areas_de_vinculacao` | `setores_sem_areas_de_vinculacao` | `view_avaliacao` **e** `change_avaliacao` |
| GET/POST | `/avaliacao_integrada/avaliacao/<pk>/enviar-email/` | `avaliacao_enviar_email` | `pode_enviar_email_lembrete` |
| GET | `/avaliacao_integrada/avaliacao/<pk>/quadro-resumo/<bloco>/` | `avaliacao_quadro_resumo_bloco` (`@cache_page` 30 min) | `pode_ver_quadro_resumo` |
| GET | `/avaliacao_integrada/avaliacao/<pk>/quadro-resumo-xlsx` | `quadro_resumo_xlsx` | `pode_exportar_respostas` |
| GET/POST | `/avaliacao_integrada/questionario/<pk>/` | `questionario` | _autenticado_ — dono do respondente, ou `pode_visualizar_questionario_terceiros` |
| GET/POST | `/avaliacao_integrada/avaliacao_externa/<token>` | `avaliacao_externa` | _pública_ (token + reCAPTCHA) |
| GET/POST | `/avaliacao_integrada/avaliacao_externa/<token>/<segmento_id>/` | `questionario_avaliacao_externa` | _pública_ (token) |
| POST | `/avaliacao_integrada/respondente_externo_check/` | `respondente_externo_check` (JSON) | _pública_ (token no corpo) |
| GET | `/avaliacao_integrada/remover_respostas_avaliacao/<token>/` | `remover_respostas_avaliacao` | _pública_ (token) |
| GET | `/avaliacao_integrada/indicador/<pk>/` | `indicador` (prévia do formulário) | `change_indicador` |
| GET | `/avaliacao_integrada/replicar_indicador/<pk>/` | `replicar_indicador` | `pode_replicar_indicador` |
| GET | `/avaliacao_integrada/relatorio/` | `relatorio` | `pode_ver_relatorios` |
| GET | `/avaliacao_integrada/relatorio/<pk>/<pk_avaliacao>/` | `exibir_relatorio_indicador` | `pode_ver_relatorio_indicadores` |
| GET | `/avaliacao_integrada/relatorio_xlsx/` | `relatorio_xlsx` → `tasks.relatorio_xlsx` | `pode_exportar_respostas` |
| GET | `/avaliacao_integrada/lista_emails_comissao/<comissao_id>/` | `lista_emails_comissao` | `view_comissaocpa` |
| GET | `/avaliacao_integrada/obter_membros_por_setor/<setor_id>/` | `obter_membros_por_setor` (JSON) | `view_comissaocpa` |
| GET | `/avaliacao_integrada/escalalikert/<pk>/` | `escalalikert` | `rh.view_escalalikert` — ⚠️ REVISAR: permissão de app inexistente, ver [HLA §7](HLA.md#7-riscos-e-débito-técnico) |

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `Eixo` | Nível 1 do instrumento; vira uma aba no questionário | ← `Dimensao` |
| `Dimensao` | Nível 2 | FK `Eixo` (PROTECT) |
| `Macroprocesso` | Nível 3; agrupa os indicadores | FK `Dimensao` (PROTECT) |
| `Indicador` | A pergunta. Concentra os filtros de aplicabilidade (segmentos, áreas, modalidades, campi, período mínimo) e o tipo de resposta | FK `Macroprocesso`, FK `EscalaLikert`; M2M `TipoAvaliacao`, `comum.Ano`, `Segmento`, `rh.AreaVinculacao`, `edu.Modalidade`, `rh.UnidadeOrganizacional` |
| `Variavel` | Componente de um indicador do tipo "Conjunto de Variáveis" | FK `Indicador` (PROTECT) |
| `OpcaoResposta` | Alternativa de escolha única/múltipla | FK `Indicador` (CASCADE) |
| `Iterador` | Faz o indicador se repetir por objeto de `edu` (curso, modalidade, professor, turma) | FK `Indicador`, FK `Segmento` |
| `TipoAvaliacao` | Finalidade do indicador/avaliação (ex.: Autoavaliação, Planejamento PDI) | M2M com `Indicador` e `Avaliacao` |
| `EscalaLikert` | Régua de resposta reutilizável | ← `NivelEscalaLikert` |
| `NivelEscalaLikert` | Nível da régua (valor, descrição, emoji, critério de padronização de gráficos) | FK `EscalaLikert` (CASCADE) |
| `Segmento` | Público respondente (14 registros de PK fixa em código); classifica em Público Interno ou Sociedade Civil | referenciado por `Indicador`, `Avaliacao`, `Respondente`, `Iterador` |
| `Avaliacao` | Aplicação do instrumento: ano, período, prazo, público, textos de instrução | FK `comum.Ano`; M2M `TipoAvaliacao`, `Segmento`, `rh.AreaVinculacao`, `edu.Modalidade`, `rh.UnidadeOrganizacional`, `comum.Ocupacao` |
| `Respondente` | Materialização de "pessoa X deve responder a avaliação Y pelo segmento Z"; guarda `finalizado` e `percentual_resposta` | FK `Avaliacao`, `comum.User` (nulo p/ externos), `rh.UnidadeOrganizacional`, `Segmento`; `dados_usuario_externo` (JSON) |
| `Resposta` | Valor respondido para um indicador (opcionalmente por variável e por objeto genérico) | FK `Indicador`, `Respondente`, `Variavel`, `NivelEscalaLikert`; `GenericForeignKey` (`content_type`/`object_id`) |
| `ComissaoCPA` | Comissão Própria de Avaliação, central ou de campus | FK `rh.Setor`, `rh.UnidadeOrganizacional`, `documento_eletronico.DocumentoTexto`; M2M `comum.Vinculo` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/).

## Regras de negócio chave

- **Quem responde o quê** — `Respondente.get_indicadores` (`models.py`) filtra por ano de referência,
  tipo do campus, campi da avaliação, segmento, áreas de vinculação do setor do servidor, modalidades
  e (para estudante) período atual do aluno. É a regra mais consultada do módulo.
- **Quem é público-alvo** — `Avaliacao.obter_publicoalvo` combina três coletas
  (`_obter_publicoalvo_servidores`, `_obter_publicoalvo_alunos`, `_obter_publicoalvo_sociedade_civil`)
  e as recorta por segmento em `_filtrar_respondentes_por_segmento`. Os segmentos ETEP e Técnico são
  separados por **códigos de cargo** (`701079`, `701058`, `701060`) + área de vinculação contendo
  "ensino".
- **Bloqueio por área de vinculação** — se qualquer servidor técnico ativo estiver em setor sem área,
  `views.avaliacao` recusa a geração de público-alvo (`BusinessRuleFailure`); e um respondente cujo
  setor não casa com as áreas da avaliação é barrado na entrada do questionário
  (`Respondente.possui_area_vinculacao`).
- **Percentual respondido** — `Respondente.get_percentual_respondido` (variante "realmente respondido"
  exclui automáticos e opcionais). O campo `percentual_resposta` é **cache** desse cálculo; ver o
  débito registrado no [HLA §7](HLA.md#7-riscos-e-débito-técnico).
- **Indicadores autocalculados** — `Indicador.INDICADORES_AUTOCALCULADOS` mapeia 13 denominações
  exatas para métodos `Respondente.get_*`; o formulário pré-preenche e trava o campo. `IndicadorForm.clean`
  recusa marcar "Autocalculado" com denominação fora dessa lista.
- **Identidade do respondente externo** — não há login: `Avaliacao.obter_respondentes_sociedade_civil`
  procura por `respondente_id`, e-mail, matrícula, CPF ou CNPJ dentro de `dados_usuario_externo`.
  Divergência entre o segmento escolhido e o segmento já gerado dispara o diálogo de confirmação
  (`views.check_respondente_segmento`).
- **Token opaco, não assinado** — `Avaliacao.gerar_token`/`obter_dados` são apenas
  `urlsafe_base64_encode(json)`. Ver [HLA §7](HLA.md#7-riscos-e-débito-técnico).
- **Unicidade da CPA** — `ComissaoCPA.clean` + `UniqueConstraint` garantem uma comissão ativa por
  tipo/campus; `membros_atualizar_grupos_de_usuarios` sincroniza os grupos `cpa_central`/`cpa_campus`.

## Jobs / Tasks Celery

| Task | Decorator | Dispara | Idempotência |
|---|---|---|---|
| `reprocessar_publico_alvo(user, avaliacao, excluir)` | `@task('Reprocessar público alvo')` | `views.avaliacao` (`?identificar_respondentes` / `?excluir_e_identificar_respondentes`) | Sim para os respondentes (`get_or_create` por avaliação+user+uo+segmento, e remoção prévia dos respondentes sem resposta); **não** para o efeito colateral de e-mail — `gerar_respondentes` termina em `enviar_emails(criacao=True)`, reenviando a todo público a cada execução |
| `relatorio_xlsx(respostas)` | `@task('Relatório em XLSX')` | `views.relatorio_xlsx` (form válido) | Sim — só lê e gera arquivo temporário |
| `exportar_crosstab_xlsx(tabelas)` | `@task('Relatório crosstab em XLSX', method='thread')` | `views.quadro_resumo_xlsx` | Sim — `method='thread'` evita serializar `TabelaBidimensional` na fila |

Não há `beat.py` nem agendamento próprio: o envio periódico de e-mails depende do command
`ai_enviar_emails` ser acionado externamente.

### Commands

| Command | Natureza |
|---|---|
| `ai_enviar_emails` | Operacional — percorre avaliações e chama `enviar_emails()` (gatilho de calendário) |
| `gerar_respondentes_avaliacao` | Operacional — gera/inspeciona respondentes de uma avaliação (`--gerar --avaliacao_id`, `--identificacoes`) |
| `recalcular_percentual_respondentes` | Operacional — `help`: "Recalcula o campo percentual_resposta dos respondentes, com processamento em lotes e suporte a retomada por checkpoint de PK". Único consumidor de `RespondenteHelper` |
| `ai_definir_areas_vinculacao_setores`, `set_areas_vinculacao_em_setores` | Carga de dados — áreas de vinculação dos setores |
| `ai_definir_cursos_professores` | Carga de dados |
| `atualizar_texto_instrucoes`, `incluir_ajustar_tipo_segmento` | Migração de dados (`help`: "Aplica migração de dados para Segmento.") |
| `adaptar_escala_likert`, `nao_usar_adaptar_escala_likert`, `nao_usar_incluir_escala_likert_padrao` | Migração de escala Likert; os prefixados `nao_usar_` são versões aposentadas mantidas no repositório |
| `gerar_aai_2024` | Carga pontual a partir de CSV (instrumento AAI 2024) |
| `mover_indicador_avaliacao_21`, `mover_respondentes_avaliacao_17` | Correções pontuais de produção, com IDs fixos no código |
| `preparar_ambiente_homologacao` | Apoio a homologação |
| `aai_restore_respostas` | Restauração/dump de respostas (1.229 linhas). ⚠️ REVISAR: não auditado nesta documentação |

## Dependências

- **Módulos internos:** `comum` (`Ano`, `User`, `Vinculo`, `Ocupacao`, `BusinessRuleFailure`), `rh`
  (`Servidor`, `Setor`, `AreaVinculacao`, `UnidadeOrganizacional`, `Situacao`, `ServidorQueryset`),
  `edu` (`Aluno`, `CursoCampus`, `Modalidade`, `Diario`, `Turma`, `ProfessorDiario`, `MatriculaPeriodo`,
  `MatriculaDiario`, `SituacaoMatricula`, `FormaIngresso`), `contratos` (`MaoDeObra`), `estagios`
  (`PraticaProfissional`), `documento_eletronico` (`DocumentoTexto`), `django.contrib.contenttypes`.
  ⚠️ REVISAR: `module_dependencies.json` declara apenas `comum`, `rh`, `edu`, `documento_eletronico`,
  `contenttypes` — `contratos` e `estagios` estão faltando.
- **Integrações:** `djtools` (ModelPlus, forms, `assincrono.task`, `crosstab`, `html.graficos`,
  `layout`, `send_mail`); Redis (cache do `RespondenteHelper` e `@cache_page` do quadro-resumo);
  servidor de e-mail (via `djtools.utils.send_mail`); reCAPTCHA (`djtools.forms.ReCaptchaField`) no
  formulário externo; TinyMCE nos textos de instrução e no lembrete.

## Configuração

| Origem | Chave | Uso |
|---|---|---|
| `settings` | `SITE_URL` | Monta o link de compartilhamento da avaliação externa (`views.avaliacao`) |
| `settings` | `DEFAULT_FROM_EMAIL` | Remetente dos convites/lembretes (`Avaliacao.enviar_emails`) |
| `settings` (via `djtools`) | reCAPTCHA | `AvaliacaoExternaForm.recaptcha` — o formulário público não abre sem a chave configurada |
| Código (constante) | `RespondenteHelper.TTL_USER_SCOPED` = 24 h, `TTL_BASE_INDICADORES` = 1 h | TTLs do cache Redis do cálculo de indicadores |
| Código (constante) | `@cache_page(60 * 30)` | Blocos do quadro-resumo |

Não há chaves em `comum.Configuracao` nem variáveis de ambiente próprias.

## Como testar

Não existem testes unitários/pytest de regressão para este módulo. O que existe:

```bash
# Suíte Playwright que gera a documentação de usuário (marcada `doc`, banco próprio) —
# é instrumentação de documentação, não cobertura
uv run pytest -m doc --reuse-db avaliacao_integrada/tests/doc/

# Cenários behave (2 arquivos .feature: cadastros gerais e cadastro de avaliação)
python manage.py test_behave --behave_stop --noinput avaliacao_integrada
```

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)
- Documentação de usuário final (complementar a esta): [usuario.md](usuario.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
