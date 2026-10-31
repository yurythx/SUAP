---
name: rsc-tae
description: 'Especialista no módulo RSC-TAE (Reconhecimento de Saberes e Competências para Técnicos Administrativos). USE FOR: criar/editar models, views, forms, admin, templates, migrations, enums, URLs do módulo rsc_tae; entender o fluxo do processo RSC; implementar regras conforme Decreto regulamentador e Relatório CNS 01/2026; ajustar avaliação multi-avaliador; manipular fixtures de saberes/competências; criar templates Django com djtools (box, progressbar, rtr, format). DO NOT USE FOR: outros módulos SUAP que não rsc_tae ou djtools.'
---

# Módulo RSC-TAE — Reconhecimento de Saberes e Competências (Técnico-Administrativo)

Skill para atuar como especialista completo no módulo `rsc_tae` do SUAP. Cobre arquitetura, modelos, views, templates, formulários, admin, enums, permissões, fluxo de processo e integração com `djtools`.

---

## 1. Visão Geral do Domínio

O RSC-PCCTAE permite que servidores técnico-administrativos de IFEs obtenham o Incentivo à Qualificação (IQ) sem titulação formal, comprovando saberes e competências adquiridos na experiência profissional. Base legal: Lei 11.091/2005, Termo de Acordo 11/2024, Decreto regulamentador (Relatório CNS 01/2026).

### 1.1 Conceitos-chave
- **Nível RSC**: 6 níveis (I a VI) com pontuação mínima e nº mínimo de itens
- **Requisito (Eixo)**: 6 eixos de avaliação (Comissões, Projetos, Premiações, Responsabilidades, Funções de Direção, Produção de Conhecimento)
- **Grupo de Complexidade**: Subgrupos dentro de cada requisito, cada um com pontuação/unidade fixa
- **Item (Saber/Competência)**: 89 critérios específicos (Anexo III do Decreto), cada um pertence a um Grupo
- **Processo RSC**: Ciclo completo de requerimento, validação, avaliação multi-avaliador e decisão final
- **Interstício**: 3 anos obrigatórios entre concessões (Art. 3º, §3º)
- **Cumulatividade/Saldo de Pontos**: Pontuação não aproveitada é carregada como "banco de pontos" para futuras concessões (Art. 3º, §2º)

---

## 2. Estrutura do Módulo

```
rsc_tae/
├── __init__.py
├── apps.py
├── enums.py                    # SituacaoProcesso, SituacaoAvaliacaoItem, SituacaoDocumentoPreliminar, Ordem
├── forms.py                    # DocumentoPreliminarUploadForm, ValidarProcessoForm, DefinirAvaliadoresForm, MemorialDescritivoForm, ProcessoRSCTaeAdminForm
├── menu.yaml                   # Menu: Gestão de Pessoas → Desenvolvimento de Pessoal → RSC → Técnico Administrativo
├── permissions.yaml            # Roles: Coord. GP, Coord. GP Sistêmico, Servidor, Avaliador RSC TAE
├── tests.py
├── urls.py                     # 21 URL patterns no namespace rsc_tae
├── admin/
│   ├── __init__.py
│   ├── processo.py             # ProcessoRSCTaeAdmin (principal — get_acoes, get_queryset customizado)
│   ├── nivel.py                # NivelAdmin
│   ├── requisito.py            # RequisitoAdmin
│   ├── grupo.py                # GrupoSaberCompetenciaAdmin
│   ├── rol_saber_competencia.py # RolSaberCompetenciaAdmin
│   ├── anexo.py                # RolSaberCompetenciaAnexoAdmin
│   ├── preenchimento.py        # RolSaberCompetenciaPreenchimentoAdmin
│   ├── avaliacao_anexo.py      # AvaliacaoAnexoRSCTaeAdmin
│   ├── avaliacao_processo.py   # AvaliacaoProcessoRSCTaeAdmin
│   ├── documento_preliminar.py # DocumentoPreliminarRSCTaeAdmin, AvaliacaoDocumentoPreliminarRSCTaeAdmin, LogAdmin
│   └── configuracao_rsc_tae.py # ConfiguracaoRSCTaeAdmin (singleton)
├── models/
│   ├── __init__.py             # Re-exporta todos os modelos (__all__)
│   ├── processo.py             # ProcessoRSCTae (modelo principal do processo)
│   ├── nivel.py                # Nivel (6 níveis RSC com pontuação mínima e IQ)
│   ├── requisito.py            # Requisito (6 eixos do Art. 3º)
│   ├── grupo.py                # GrupoSaberCompetencia (grupos de complexidade por requisito)
│   ├── rol.py                  # RolSaberCompetencia (89 itens/critérios do Anexo III)
│   ├── preenchimento.py        # RolSaberCompetenciaPreenchimento (quantidade declarada pelo servidor)
│   ├── anexo.py                # RolSaberCompetenciaAnexo (arquivos comprobatórios)
│   ├── avaliacao.py            # AvaliacaoAnexoRSCTae (avaliação de cada anexo por avaliador)
│   ├── avaliacao_processo.py   # AvaliacaoProcessoRSCTae (resultado geral de cada avaliador)
│   ├── documento_preliminar.py # DocumentoPreliminarRSCTae, AvaliacaoDocumentoPreliminarRSCTae, Log
│   ├── configuracao_rsc_tae.py # ConfiguracaoRSCTae (singleton de configurações)
│   └── memorial.py             # MemorialDescritivoRSCTae (memorial descritivo do servidor)
├── views/
│   ├── __init__.py
│   ├── processo.py             # Views principais (visualizar, avaliar, validar, definir_avaliador, etc.)
│   ├── api.py                  # Endpoints AJAX/JSON (upload_anexo, salvar_quantidade, listar_anexos)
│   └── _helpers.py             # Funções auxiliares (contextos, validações de acesso, cálculos de resumo)
├── templates/rsc_tae/
│   ├── visualizar.html         # Tela principal do processo (5 abas: Instruções, Doc. Preliminar, Formulário, Memorial, Resumo)
│   ├── avaliar.html            # Interface de avaliação do avaliador (herda avaliar → inclui resumo_avaliacao partial)
│   ├── avaliar_arquivo.html    # Avaliação individual de um anexo (popup)
│   ├── validar_processo.html   # Validação de documento preliminar pelo RH (com modal dialog)
│   ├── definir_avaliador.html  # Designação de avaliadores pelo RH
│   ├── minhas_avaliacoes.html  # Lista de processos designados ao avaliador
│   ├── finalizar_avaliacao.html # Tela de finalização da avaliação com impacto da decisão
│   ├── resumo_avaliacao.html   # Resumo readonly da avaliação (dono/RH)
│   ├── relatorio_avaliacao_pdf.html # Relatório PDF para processos finalizados
│   └── partials/
│       ├── resumo_preenchimento.html  # Tabela de preenchimento agrupada por requisito
│       └── resumo_avaliacao.html      # Detalhamento da avaliação por item (multi-avaliador)
├── static/rsc_tae/
│   ├── css/rsc-tae.css         # Estilos (tooltips CSS, dialog modal, badges, tabelas)
│   └── js/                     # JavaScript (upload AJAX, salvar quantidade, popup, etc.)
├── fixtures/
│   ├── initial_data_nivel.json
│   ├── initial_data_requisito.json
│   ├── initial_data_grupo.json
│   └── initial_data_saber_competencia.json
├── docs/
│   └── especificacoes.md       # Especificação completa do módulo (referência normativa, gaps, changelog)
└── migrations/
```

---

## 3. Modelos de Dados

### 3.1 Hierarquia de Dados

```
Nivel (6 níveis RSC)
  └─→ ProcessoRSCTae (processo do servidor)
         ├─→ DocumentoPreliminarRSCTae (diploma/certificado)
         │     └─→ AvaliacaoDocumentoPreliminarRSCTae (validação pelo RH)
         │     └─→ DocumentoPreliminarRSCTaeLog (log de ações)
         ├─→ MemorialDescritivoRSCTae (1:1 — memorial do servidor)
         ├─→ RolSaberCompetenciaAnexo (anexos comprobatórios)
         │     └─→ AvaliacaoAnexoRSCTae (avaliação por avaliador)
         └─→ AvaliacaoProcessoRSCTae (resultado individual de cada avaliador)

Requisito (6 eixos)
  └─→ GrupoSaberCompetencia (grupos de complexidade)
       └─→ RolSaberCompetencia (89 itens/critérios)
            └─→ RolSaberCompetenciaPreenchimento (quantidade declarada pelo servidor)
            └─→ RolSaberCompetenciaAnexo (anexos)

ConfiguracaoRSCTae (singleton — instruções de preenchimento/avaliação)
```

### 3.2 ProcessoRSCTae (modelo central)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `vinculo` | FK→comum.Vinculo | Servidor requerente |
| `nivel_requisitado` | FK→Nivel | Nível RSC solicitado (I-VI) |
| `avaliadores` | M2M→comum.Vinculo | Múltiplos avaliadores designados |
| `avaliador_atual` | FK→comum.Vinculo (nullable) | Compatibilidade com processos antigos |
| `situacao` | int (default=1) | Estado do processo (SituacaoProcesso) |
| `memorial` | TextField | Exposição de atividades conforme Art. 11 |
| `declaracao_conformidade` | BooleanField | Confirmação legal de autenticidade |
| `saldo_pontuacao_anterior` | DecimalField | Banco de pontos de concessão anterior |
| `processo_anterior` | FK→self (nullable) | Referência a processo anterior |
| `avaliacao_finalizada_por` | FK→comum.Vinculo (nullable) | Quem finalizou |
| `data_finalizacao_avaliacao` | DateTimeField (nullable) | Quando finalizou |
| `avaliacao_motivo_indeferimento` | TextField | Motivo se indeferido |

**Métodos:**
- `get_absolute_url()` → URL de detalhe
- `rsc_equivalente()` → Titulações equivalentes ao IQ deste nível
- `get_situacao_badge()` → HTML badge colorido
- `calcular_novo_processo(usuario)` (classmethod) → Cria novo processo com validação de interstício, titulação e cálculo de saldo

**Permissões customizadas:**
- `avaliar_processorsctae` — Permite avaliar processos
- `definir_avaliador_processorsctae` — Permite designar avaliadores

**Constantes:**
- `SEARCH_FIELDS = ('vinculo__pessoa__nome', 'vinculo__pessoa__pessoafisica__servidor_set__matricula')`
- `INTERSTICIO_ANOS = 3`

### 3.3 AvaliacaoProcessoRSCTae (resultado individual do avaliador)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `processo` | FK→ProcessoRSCTae | Processo avaliado |
| `avaliador_vinculo` | FK→comum.Vinculo | Avaliador |
| `aceite` | BooleanField (nullable) | True=aceitar, False=recusar, None=pendente |
| `motivo_recusa` | TextField | Texto se recusa |
| `pontuacao_final` | DecimalField (nullable) | Pontuação total na finalização |
| `resultado` | int (nullable) | DEFERIDO(4) ou INDEFERIDO(5) |
| `itens_validados` | PositiveIntegerField (nullable) | Qtd itens com pontuação > 0 |
| `data_finalizacao` | DateTimeField (nullable) | Quando finalizou avaliação |
| `motivo_indeferimento` | TextField | Razão do indeferimento |

**Constraint:** Unique(processo, avaliador_vinculo)

### 3.4 AvaliacaoAnexoRSCTae (avaliação de cada arquivo)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `anexo` | FK→RolSaberCompetenciaAnexo (related_name='avaliacoes') | Anexo avaliado |
| `avaliador_vinculo` | FK→comum.Vinculo (nullable) | Avaliador |
| `situacao` | int (default=PENDENTE) | PENDENTE(1), DEFERIDO(2), INDEFERIDO(3) |
| `pontuacao_validada` | DecimalField (nullable) | Unidades aceitas pelo avaliador |
| `observacao` | TextField | Justificativa de alteração/rejeição |
| `avaliado_por` | CurrentUserField | Django user que avaliou |
| `ip_avaliacao` | GenericIPAddressField | IP da avaliação |

**Constraint:** Unique(anexo, avaliador_vinculo) onde avaliador_vinculo NOT NULL

### 3.5 RolSaberCompetencia (89 itens de avaliação)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `numero` | PositiveIntegerField | Número do critério (1-89) |
| `grupo` | FK→GrupoSaberCompetencia | Grupo de complexidade |
| `titulo` | CharField(600) | Nome descritivo |
| `descricao` | TextField | Descrição completa |
| `documentos_comprobatorios` | TextField | Ex: "Portarias, Resoluções" |
| `unidade_medida` | CharField(300) | Ex: "horas", "meses", "atividades" |
| `item_temporal` | BooleanField (default=False) | Se True, cálculo automático por meses (data_fim - data_inicio) |

**Propriedades:**
- `pontuacao_unidade` → `grupo.pontuacao_unidade` (pontuação vem do grupo, não do item)
- `requisito` → `grupo.requisito`

### 3.6 Outros Modelos

- **Nivel**: `ordem`, `nome`, `valor_iq` (%), `numero_minimo_itens`, `pontuacao_minima`, `iq_requisito` (M2M→Titulacao), `iq_equivalente` (M2M→Titulacao). Propriedade `ordem_romana` retorna I-VI.
- **Requisito**: `numero` (1-6), `descricao`, `descricao_curta`, `numeral_romano`
- **GrupoSaberCompetencia**: `requisito` (FK), `numero`, `pontuacao_unidade`, `descricao`. Constraint: Unique(requisito, numero)
- **RolSaberCompetenciaAnexo**: `processo`, `rol_saber_competencia`, `arquivo`, `pontuacao` (unidades), `data_inicio`/`data_fim` (para itens temporais)
- **RolSaberCompetenciaPreenchimento**: `vinculo`, `rol_saber_competencia`, `quantidade`
- **DocumentoPreliminarRSCTae**: `processo`, `arquivo`, `data_obtencao_titulacao`
- **MemorialDescritivoRSCTae**: `processo` (1:1), `conclusao`
- **ConfiguracaoRSCTae**: `pontuacao_minima_geral`, `texto_instrucao_preenchimento`, `texto_instrucao_avaliacao` (singleton)

---

## 4. Enums (`rsc_tae/enums.py`)

### SituacaoProcesso (8 estados)
| Valor | Nome | Descrição |
|-------|------|-----------|
| 1 | AGUARDANDO_PREENCHIMENTO | Servidor preenche itens e anexos |
| 2 | AGUARDANDO_AVALIADOR | Documento validado, RH designa avaliadores |
| 3 | EM_ANALISE | Avaliadores analisando o processo |
| 4 | DEFERIDO | Processo aprovado por maioria |
| 5 | INDEFERIDO | Processo rejeitado |
| 6 | AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR | Documento preliminar aguardando RH |
| 7 | AGUARDANDO_CORRECAO | Servidor deve corrigir e reenviar |
| 8 | AGUARDANDO_ACEITE_AVALIADOR | Avaliadores designados, pendente aceite |

### SituacaoAvaliacaoItem (3 estados)
| Valor | Nome |
|-------|------|
| 1 | PENDENTE |
| 2 | DEFERIDO |
| 3 | INDEFERIDO |

### SituacaoDocumentoPreliminar (3 estados)
| Valor | Nome |
|-------|------|
| 1 | PENDENTE |
| 2 | VALIDADO |
| 3 | CORRECAO_SOLICITADA |

### Ordem (numerais romanos)
| Valor | Label |
|-------|-------|
| 1-6 | I, II, III, IV, V, VI |

---

## 5. Máquina de Estados (Fluxo do Processo)

```
AGUARDANDO_PREENCHIMENTO (1)
    → AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR (6)  [servidor conclui preenchimento]
    → AGUARDANDO_AVALIADOR (2)                       [se doc. já validado]

AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR (6)
    → AGUARDANDO_CORRECAO (7)                        [RH solicita correção]
    → AGUARDANDO_AVALIADOR (2)                       [RH valida doc. preliminar]

AGUARDANDO_CORRECAO (7)
    → AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR (6)  [servidor resubmete]

AGUARDANDO_AVALIADOR (2)
    → AGUARDANDO_ACEITE_AVALIADOR (8)                [RH designa avaliadores]
    → AGUARDANDO_CORRECAO (7)                        [RH devolve para correção]

AGUARDANDO_ACEITE_AVALIADOR (8)
    → EM_ANALISE (3)                                 [qualquer avaliador aceita → já pode avaliar]
    → AGUARDANDO_AVALIADOR (2)                       [qualquer avaliador recusa]
    → AGUARDANDO_CORRECAO (7)                        [RH devolve para correção]

EM_ANALISE (3)
    → DEFERIDO (4)                                   [todos finalizaram; maioria ≥ 50%]
    → INDEFERIDO (5)                                 [todos finalizaram; maioria < 50%]
    → AGUARDANDO_CORRECAO (7)                        [RH devolve para correção]

DEFERIDO (4) / INDEFERIDO (5)                        [estados finais]
```

**Regra importante:** Quando um avaliador aceita em AGUARDANDO_ACEITE_AVALIADOR, o processo transiciona imediatamente para EM_ANALISE. O avaliador que aceitou pode começar a avaliar imediatamente, mesmo que outros avaliadores ainda não tenham aceito.

---

## 6. Permissões e Roles (`permissions.yaml`)

| Role | Permissões ProcessoRSCTae | Outras |
|------|---------------------------|--------|
| Coordenador de Gestão de Pessoas | add, view, change, avaliar, definir_avaliador | Nivel: add/view/change; RolSaberCompetencia: add/view/change |
| Coordenador de GP Sistêmico | add, view, change, delete, avaliar, definir_avaliador | Idem + delete; ConfiguracaoRSCTae: CRUD |
| Servidor | add, view | — |
| Avaliador RSC TAE | view, avaliar | — |

**Permissões customizadas no modelo:**
- `rsc_tae.avaliar_processorsctae` → Pode avaliar
- `rsc_tae.definir_avaliador_processorsctae` → Pode designar avaliadores (RH)

---

## 7. Views Principais (`views/processo.py`)

| View | URL Name | Método | Descrição |
|------|----------|--------|-----------|
| `visualizar` | `rsc_tae:visualizar` | GET | Tela principal com 5 abas (tabs) |
| `concluir_preenchimento` | `rsc_tae:concluir_preenchimento` | GET | Valida e transiciona para próximo estado |
| `editar_memorial` | `rsc_tae:editar_memorial` | POST | Salva declaração de conformidade |
| `upload_documento_preliminar` | `rsc_tae:upload_documento_preliminar` | POST | Upload de diploma/certificado |
| `validar_processo` | `rsc_tae:validar_processo` | GET/POST | RH valida ou solicita correção do doc. |
| `definir_avaliador_atual` | `rsc_tae:definir_avaliador_atual` | GET/POST | RH designa avaliadores |
| `aceitar_avaliacao` | `rsc_tae:aceitar_avaliacao` | POST | Avaliador aceita avaliar |
| `recusar_avaliacao` | `rsc_tae:recusar_avaliacao` | POST | Avaliador recusa (com motivo) |
| `devolver_para_correcao` | `rsc_tae:devolver_para_correcao` | POST | RH devolve (limpa avaliadores+avaliações) |
| `avaliar` | `rsc_tae:avaliar` | GET | Interface de avaliação de itens |
| `avaliar_arquivo` | `rsc_tae:avaliar_arquivo` | GET/POST | Avaliação de anexo individual (popup) |
| `finalizar_avaliacao` | `rsc_tae:finalizar_avaliacao` | GET/POST | Avaliador finaliza; se todos finalizaram → encerra |
| `resumo_avaliacao` | `rsc_tae:resumo_avaliacao` | GET | Resumo readonly |
| `relatorio_avaliacao` | `rsc_tae:relatorio_avaliacao` | GET | PDF do relatório |
| `minhas_avaliacoes` | `rsc_tae:minhas_avaliacoes` | GET | Lista de processos do avaliador |

### Views AJAX (`views/api.py`)

| View | URL Name | Método | Descrição |
|------|----------|--------|-----------|
| `resumo_preenchimento` | `rsc_tae:resumo_preenchimento` | GET | HTML atualizado do resumo |
| `salvar_quantidade_item` | `rsc_tae:salvar_quantidade_item` | POST | Salva quantidade declarada |
| `listar_anexos_item` | `rsc_tae:listar_anexos_item` | GET | Lista anexos de um item |
| `upload_anexo_item` | `rsc_tae:upload_anexo_item` | POST | Upload de anexo |
| `salvar_pontuacao_anexo` | `rsc_tae:salvar_pontuacao_anexo` | POST | Atualiza pontuação de anexo |
| `excluir_anexo_item` | `rsc_tae:excluir_anexo_item` | POST | Exclui anexo |

---

## 8. Helpers (`views/_helpers.py`)

Funções essenciais do módulo. Toda lógica de acesso, cálculo e montagem de contexto está aqui.

### Validação de Acesso
- `_validar_acesso_processo(request, processo)` — Dono pode acessar
- `_validar_acesso_processo_leitura(request, processo)` — Dono ou RH
- `_validar_acesso_avaliacao(request, processo)` — Avaliador designado com aceite=True; aceita EM_ANALISE e AGUARDANDO_ACEITE_AVALIADOR
- `_validar_acesso_aceite_avaliacao(request, processo)` — Estado AGUARDANDO_ACEITE_AVALIADOR
- `_validar_acesso_resumo_avaliacao(request, processo)` — Dono, RH ou avaliador
- `_pode_editar_preenchimento(request, processo)` — Dono e em AGUARDANDO_PREENCHIMENTO ou AGUARDANDO_CORRECAO

### Cálculos
- `_montar_resumo_preenchimento(processo)` → Retorna `linhas_preenchidas`, `grupos_requisito`, totais de itens e pontos
- `_montar_contexto_avaliacao(request, processo, title)` → Contexto completo de avaliação: `pode_avaliar_anexos`, `linhas_avaliacao` (com avaliação de cada anexo), `grupos_requisito_avaliacao`, resumo de pontos/itens, resultado por avaliador, votação por maioria
- `_agrupar_por_requisito(linhas)` → Agrupa linhas por requisito (Req I, II, ...) com subtotais
- `_calcular_resumo_por_pontos(...)` → Calcula total_pontos, itens_preenchidos, percentuais
- `_contexto_acesso_processo(request, processo)` → Dict com `eh_dono`, `eh_rh_sistemico`, `eh_rh_campus`, `eh_mesmo_campus`

### Regra `pode_avaliar_anexos`
```python
situacao_permite_avaliar = (
    processo.situacao == SituacaoProcesso.EM_ANALISE
    or (
        processo.situacao == SituacaoProcesso.AGUARDANDO_ACEITE_AVALIADOR
        and avaliacao_processo
        and avaliacao_processo.aceite == True
    )
)
pode_avaliar_anexos = bool(
    (not eh_dono)
    and request.user.has_perm('rsc_tae.avaliar_processorsctae')
    and situacao_permite_avaliar
    and avaliador_contexto
    and vinculo_usuario
    and avaliador_contexto.id == vinculo_usuario.id
    and (not avaliacao_finalizada)
)
```

---

## 9. Admin (`admin/processo.py`)

### ProcessoRSCTaeAdmin

**Herda:** `ModelAdminPlus` (de `djtools.contrib.admin`)

**list_display:** `get_servidor_info`, `nivel_requisitado`, `get_avaliadores`, `get_situacao`, `get_resumo_preenchimento`, `get_acoes`

**`get_acoes(obj)`** — Renderiza botões dinâmicos baseados na situação e permissões:
- **Resumo**: Visível para RH/dono/avaliador quando situação ≥ EM_ANALISE
- **Imprimir Relatório**: Apenas processos DEFERIDO/INDEFERIDO
- **Avaliar**: Avaliador designado que aceitou, situação EM_ANALISE ou AGUARDANDO_ACEITE_AVALIADOR (com aceite=True)
- **Validar processo**: RH, situação AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR
- **Definir avaliadores**: RH, situação AGUARDANDO_AVALIADOR

**`get_queryset(request)`** — Filtragem por role:
- RH sistêmico: todos
- RH campus: mesma UO
- Avaliador: processos que avalia + próprio
- Usuário comum: apenas próprio

**`add_autocreate_view(request)`** — Endpoint para "Iniciar seu processo": verifica interstício, duplicidade, calcula nível.

---

## 10. Formulários (`forms.py`)

| Form | Campos | Uso |
|------|--------|-----|
| `DocumentoPreliminarUploadForm` | `arquivo` (FileFieldPlus, pdf/jpeg/jpg/png), `data_obtencao_titulacao` (DateFieldPlus) | Upload de diploma/certificado |
| `ValidarProcessoForm` | `acao` (validar/solicitar_correcao), `observacao` (textarea) | RH valida documento |
| `DefinirAvaliadoresForm` | `avaliadores` (MultipleModelChoiceFieldPlus, AutocompleteWidget) | RH designa avaliadores |
| `MemorialDescritivoForm` | `declaracao_conformidade` (BooleanField required) | Declaração legal do servidor |
| `ProcessoRSCTaeAdminForm` | fields='__all__' | Admin form com validação: avaliador ≠ dono |

---

## 11. Integração com djtools

O módulo `djtools` é a camada de extensões Django usada em todo o SUAP. Ao trabalhar no `rsc_tae`, é essencial conhecer:

### 11.1 Decoradores

**`@rtr(template=None)`** — (de `djtools.utils.response`)
- Decorator de views que automatiza a renderização do template
- Se a view retorna um `dict`, renderiza no template especificado
- Se retorna `HttpResponse`, passa direto
- Template padrão: `{app_name}/{function_name}.html`
- Suporta LPS (variantes de template)

```python
@rtr('rsc_tae/avaliar.html')
@login_required
@require_GET
def avaliar(request, processo_id):
    # ... retorna dict que é renderizado no template
    return {'processo': processo, 'pode_avaliar_anexos': True}
```

**`httprr(url, message='', tag='success')`** — (de `djtools.utils.response`)
- Shortcut para `HttpResponseRedirect` com mensagem
- Tags: `success`, `warning`, `error`, `info`
- Suporta `close_popup=True` e `anchor`

```python
return httprr(processo.get_absolute_url(), 'Avaliação aceita com sucesso.', tag='success')
```

**`@documento()`** — (de `djtools.utils.pdf`)
- Decorator para gerar PDF a partir de template HTML
- Usado em `relatorio_avaliacao`

### 11.2 Template Tags e Filtros

**Tags** (de `djtools/templatetags/tags/utils.py`):
- `{% box 'Título' %}...{% endbox %}` — Container com título e estilo padrão SUAP. Aceita parâmetros: `class`, `boxid`, `badge`, `extra`
- `{% progressbar percent %}` — Barra de progresso. Aceita float (50.5), string ("50%"), ou fração ("50/100")
- `{% icon 'nome' %}` — Ícone Font Awesome
- `{% render_table table %}` — Renderiza django-tables2
- `{% filter_box %}...{% endfilter_box %}` — Filtros colapsáveis
- `{% comentarios %}` — Seção de comentários

**Filtros** (de `djtools/templatetags/filters/utils.py`):
- `{{ valor|format }}` — Formatação genérica (números, datas, etc.)
- `{{ valor|format_money }}` — Formatação monetária
- `{{ valor|format_datetime }}` — Data/hora dd/mm/yyyy HH:MM:SS
- `{{ valor|format_bool }}` — Boolean → "Sim"/"Não"
- `{{ valor|format_phone }}` — Telefone com DDD

### 11.3 Base Classes

**`ModelAdminPlus`** (de `djtools.contrib.admin.options`):
- Base para todos os ModelAdmin do SUAP
- Atributos extras: `list_display_icons`, `show_count_on_tabs`, `export_to_xls`, `filters_ajax`
- Inlines: `TabularInlinePlus`, `StackedInlinePlus`
- `ReadOnlyAdmin` para admins somente-leitura

**`FormPlus`/`ModelFormPlus`** (de `djtools.forms.base`):
- Base forms com `self.request` disponível
- `DtModelForm` — Auto-widget selection (AutocompleteWidget para querysets grandes)

**Campos de formulário djtools:**
- `FileFieldPlus` — Upload com validação de extensões
- `DateFieldPlus` — Datepicker
- `CharFieldPlus` — CharField com extras
- `MultipleModelChoiceFieldPlus` — Multi-select com autocomplete

### 11.4 Context Processor (`super_template`)

```python
# djtools/context_processor.py
'super_template': request.user.is_authenticated and 'admin/base.html' or 'admin/base_anonima.html'
```

Todos os templates herdam com:
```django
{% extends super_template %}
```

### 11.5 Utilidades

- `djtools.utils.http.get_client_ip(request)` — Obtém IP real do cliente
- `djtools.utils.response.httprr()` — Redirect com mensagem
- `djtools.db.models.modelplus.ModelPlus` — Base model com SEARCH_FIELDS
- `djtools.contrib.admin.options.ModelAdminPlus` — Base admin

---

## 12. Padrões de Código do Módulo

### 12.1 Padrão de View com @rtr
```python
@rtr('rsc_tae/nome_template.html')
@login_required
def minha_view(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_xxx(request, processo)  # helper de acesso
    
    if request.method == 'POST':
        form = MeuForm(request.POST)
        if form.is_valid():
            # ...
            return httprr(processo.get_absolute_url(), 'Sucesso!', tag='success')
    else:
        form = MeuForm()
    
    return {
        'title': 'Título da página',
        'processo': processo,
        'form': form,
    }
```

### 12.2 Padrão de View AJAX/JSON
```python
@login_required
@require_POST
def minha_api(request, processo_id, item_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_xxx(request, processo)
    
    # ... lógica
    
    return JsonResponse({'status': 'ok', 'data': resultado})
```

### 12.3 Padrão de Template
```django
{% extends super_template %}
{% load static %}

{% block extracss %}
<link rel="stylesheet" href="{% static 'rsc_tae/css/rsc-tae.css' %}">
{% endblock %}

{% block action-bar %}
    <ul class="action-bar">
        <li><a href="{% url 'rsc_tae:alguma_view' processo.id %}" class="btn success">Ação</a></li>
    </ul>
{% endblock %}

{% block content %}
{% box 'Seção' %}
    <dl class="definition-list flex">
        <div class="list-item">
            <dt>Campo</dt>
            <dd>{{ valor }}</dd>
        </div>
    </dl>
{% endbox %}
{% endblock %}
```

### 12.4 Padrão de Admin com get_acoes
```python
class ProcessoRSCTaeAdmin(ModelAdminPlus):
    list_display = ('campo1', 'campo2', 'get_acoes')
    
    def get_acoes(self, obj):
        acoes = []
        user = self.request.user if hasattr(self, 'request') else None
        
        if condicao:
            acoes.append(f'<a href="{url}" class="btn default">Texto</a>')
        
        return mark_safe(' '.join(acoes)) if acoes else '—'
    get_acoes.short_description = 'Ações'
```

### 12.5 Padrão de Helper de Acesso
```python
def _validar_acesso_xxx(request, processo):
    user = request.user
    vinculo_usuario = user.get_vinculo()
    
    # Verificar permissões
    if not user.has_perm('rsc_tae.permissao'):
        raise PermissionDenied('Permissão negada.')
    
    # Verificar estado do processo
    if processo.situacao not in (SituacaoProcesso.ESTADO_X, SituacaoProcesso.ESTADO_Y):
        raise PermissionDenied('Processo não está no estado correto.')
    
    # Verificar se é avaliador designado
    if not processo.avaliadores.filter(id=vinculo_usuario.id).exists():
        raise PermissionDenied('Você não é avaliador deste processo.')
```

### 12.6 Padrão de Modal com `<dialog>`
```html
<dialog class="rsc-dialog" id="meuModal">
    <div class="rsc-dialog-header">
        <h3>Título</h3>
        <button type="button" class="rsc-dialog-close" onclick="this.closest('dialog').close()">&times;</button>
    </div>
    <div class="rsc-dialog-body">
        <form method="post">{% csrf_token %}{{ form }}
            <button type="submit" class="btn success">Enviar</button>
        </form>
    </div>
</dialog>
<script>
document.addEventListener('DOMContentLoaded', function() {
    var dialog = document.getElementById('meuModal');
    // Auto-abrir se tem erros de validação
    if (dialog.querySelector('.error, .errorlist, .has-error, .is-invalid')) {
        dialog.showModal();
    }
});
</script>
```

---

## 13. Convenções Importantes

1. **Backward compatibility**: Sempre manter suporte ao campo `avaliador_atual` (FK single) para processos antigos — novo fluxo usa `avaliadores` (M2M)
2. **N+1 queries**: Admin usa `select_related`/`prefetch_related` extensivamente
3. **Auditoria**: `DocumentoPreliminarRSCTaeLog` registra todas ações sobre documentos
4. **Pontuação vem do Grupo**: Itens herdam `pontuacao_unidade` do seu `GrupoSaberCompetencia`, nunca do item diretamente
5. **Item temporal**: Quando `item_temporal=True`, pontuação é calculada automaticamente de `data_fim - data_inicio` em meses
6. **Multi-avaliador**: Resultado final por votação — maioria simples (≥50%) → DEFERIDO
7. **Singleton ConfiguracaoRSCTae**: `has_add_permission` retorna False se já existe
8. **URLs**: Namespace `rsc_tae`, ex: `{% url 'rsc_tae:visualizar' processo.id %}`
9. **Popup pattern**: Links com `class="popup"` e `?_popup=1` abrem em janela popup do SUAP
10. **CSRF**: Todos os forms POST incluem `{% csrf_token %}`
11. **Permissão PermissionDenied**: Usar `from django.core.exceptions import PermissionDenied` (não `Http403`)

---

## 14. Especificação Normativa

A referência completa (níveis, requisitos, 89 critérios, regras, gaps, changelog) está em:

- [rsc_tae/docs/especificacoes.md](./../../rsc_tae/docs/especificacoes.md)

Consulte este arquivo para:
- Tabela dos 6 níveis com pontuação mínima e IQ correspondente
- Lista dos 89 critérios específicos (Anexo III) com grupo e pontuação
- Gap analysis (implementado vs. pendente)
- Registro de implementação e changelog
