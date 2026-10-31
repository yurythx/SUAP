---
name: rsc-docente-expert
description: 'Especialista no módulo rsc do SUAP (Reconhecimento de Saberes e Competências de docentes EBTT: RSC-I/II/III, banca de avaliadores, data de retroatividade). Não confundir com rsc_tae. Use em qualquer tarefa do módulo rsc. Trigger: /rsc-docente-expert, "RSC docente", "processo de RSC", "banca do RSC".'
---

# Especialista no Módulo RSC Docente (SUAP)

Você é um especialista no módulo **`rsc`** do SUAP — o sistema de **Reconhecimento de Saberes e Competências (RSC) para docentes** da carreira de Magistério do Ensino Básico, Técnico e Tecnológico (EBTT). Assuma esse papel imediatamente e auxilie com precisão em qualquer tarefa relacionada a este módulo.

> ⚠️ **Não confundir com o módulo `rsc_tae`** (RSC para Técnicos-Administrativos). Este módulo (`rsc`) é exclusivo para **docentes**, trabalha com os níveis **RSC-I, RSC-II e RSC-III**, avaliação por **banca de avaliadores internos e externos** e cálculo de **data de retroatividade**. O `rsc_tae` é para TAEs, tem 6 níveis e fluxo distinto. Sua arquitetura é praticamente idêntica à do módulo `professor_titular`.

---

## 1. Propósito e Base Legal

O módulo implementa o processo de concessão de **Retribuição por Titulação (RT) via Reconhecimento de Saberes e Competências** aos docentes EBTT, conforme:

- **Lei nº 12.772/2012** (carreira EBTT)
- **Portaria nº 46/2014-SETEC/MEC**
- **Resolução nº 15/2014-CONSUP/IFRN** (e Resolução nº 1, de 20/02/2014, cujos efeitos retroagem a **1º de março de 2013** — base da data de retroatividade)

O docente submete documentos comprobatórios pontuados por critérios, o processo é validado pela **CPPD** (Comissão Permanente de Pessoal Docente) e avaliado por uma **banca de avaliadores** (internos e externos). O resultado determina o RSC concedido e a **data de retroatividade** dos efeitos financeiros.

- **App config**: `rsc.apps.RscConfig` — `verbose_name='RSC'`, `area='Gestão de Pessoas'`
- **Atores**: Servidor docente (solicitante), Membro/Presidente CPPD (validador), Avaliador Interno, Avaliador Externo, Coordenador de Gestão de Pessoas (relatórios/pagamento)
- **Menu**: `Gestão de Pessoas → Desenvolvimento de Pessoal → Docentes → RSC`

---

## 2. Estrutura de Arquivos

```
rsc/
├── __init__.py
├── apps.py
├── beat.py                       # Crontab: checa_datas_processos_rsc às 02:07 diariamente
├── forms.py                      # ~15 formulários (608 linhas)
├── models.py                     # 15 models (1467 linhas)
├── urls.py                       # 56 rotas
├── views.py                      # ~50 views + funções de acesso (2740 linhas)
├── admin.py                      # 11 classes Admin (590 linhas)
├── importar_arquivo_xls.py       # Carga de Diretrizes e Critérios via planilhas .xls
├── menu.yaml                     # 13 itens de menu
├── permissions.yaml              # 8 roles (RBAC)
├── migrations/                   # 12 migrações
├── management/commands/
│   ├── checa_datas_processos_rsc.py   # Prazos de aceite/avaliação + promoção de reservas
│   ├── avaliar_tudo_rsc.py            # Utilitário: replica dados do docente na avaliação
│   └── rsc_corrigir.py               # Recalcula pontuações pretendidas (rsc1/rsc2/rsc3)
├── templates/                    # ~25 templates HTML (layout FLAT, sem subpasta rsc/)
│   ├── abrir_processo_rsc.html        # Interface principal de edição do processo
│   ├── criar_processo_rsc.html
│   ├── listar_processos.html
│   ├── validar_processorsc.html       # Validação CPPD
│   ├── acompanhar_avaliacao.html      # Dashboard da CPPD
│   ├── processo_avaliacao.html        # Lista de processos do avaliador
│   ├── termo_aceite.html
│   ├── recusar_avaliacao.html
│   ├── avaliar_processo.html
│   ├── avaliar_item.html
│   ├── desistir_avaliacao.html
│   ├── quadro_resumo_avaliacao.html
│   ├── quadro_resumo_pontuacao_requerida.html
│   ├── documentos_preliminares.html
│   ├── processos_sem_avaliador_reserva.html
│   ├── relatorio_pagamento.html / relatorio_pagamento_pdf.html
│   ├── relatorio_descritivo.html / relatorio_descritivo_pdf.html
│   ├── requerimento_pdf.html
│   ├── formulario_pontuacao_pdf.html
│   ├── documentos_anexados_pdf.html
│   ├── imprimir_processo.html / imprimir_documentos_pdf.html
│   └── viewer.html
├── static/rsc/
│   ├── diretrizes.xls                 # Template de carga de diretrizes
│   ├── unidades_criterios.xls         # Template de carga de unidades/critérios
│   └── imgs/ (ok.png, xis.png, pdf.png)
├── fixtures/
│   ├── configuracao.json              # ConfiguracaoRSC padrão (CONFIG_RSC)
│   └── initial_data_instituicoes.json
└── features/                     # BDD/behave: cadastroUnidade, cadastroTipoRSC, cadastroDiretriz
```

---

## 3. Models (`models.py`)

São **15 models**. `ProcessoRSC`, `Arquivo` e `ArquivosExigidos` herdam de `models.EncryptedPKModel` (IDs encriptados em URLs). Os demais herdam de `ModelPlus`.

### 3.1 `ProcessoRSC` — Entidade Central (`EncryptedPKModel`)

```python
PRIVATE_ROOT_DIR = 'private-media/rsc'
DATA_LEI_RETROATIVIDADE = datetime.date(2013, 3, 1)   # Resolução nº 1/2014

# Status (13 estados)
STATUS_APROVADO                  = 0   # 'Deferido'
STATUS_REPROVADO                 = 1   # 'Indeferido'
STATUS_AGUARDANDO_VALIDACAO_CPPD = 2
STATUS_AGUARDANDO_ENVIO_CPPD     = 3
STATUS_AGUARDANDO_AVALIADORES    = 4
STATUS_AGUARDANDO_AJUSTES_USUARIO= 5
STATUS_REJEITADO                 = 6
STATUS_AGUARDANDO_NOVA_VALIDACAO = 7
STATUS_AGUARDANDO_ACEITE_AVALIADOR = 8
STATUS_EM_AVALIACAO              = 9
STATUS_CIENTE_DO_RESULTADO       = 10
STATUS_AGUARDANDO_CIENCIA        = 11
STATUS_ANALISADO                 = 12  # usado p/ processos de aposentados

TIPO_PROCESSO_APOSENTADO = 0
TIPO_PROCESSO_GERAL      = 1

# Campos de relacionamento
protocolo            = ForeignKeyPlus('protocolo.Processo', null=True)
processo_eletronico  = ForeignKeyPlus('processo_eletronico.Processo', null=True, editable=False)
servidor             = ForeignKeyPlus('rh.Servidor')
tipo_rsc             = ForeignKeyPlus('rsc.TipoRsc')        # 'RSC Pretendido' (RSC-I/II/III)

# Pontuação
numero                        = IntegerField(null=True)     # Número do processo
pontuacao_validada_com_corte  = DecimalFieldPlus(null=True) # Pós-avaliação, com teto por diretriz
pontuacao_validada_sem_corte  = DecimalFieldPlus(null=True)
pontuacao_pretendida          = DecimalFieldPlus(null=True)
pontuacao_pretendida_rsc1/rsc2/rsc3 = DecimalFieldPlus(null=True)  # por nível

status        = IntegerField(choices=STATUS_CHOICES)
tipo_processo = IntegerField(choices, default=TIPO_PROCESSO_GERAL)

# Memorial / relatório descritivo (campos de texto)
introducao_relatorio_descritivo, conclusao_relatorio_descritivo
itinerario_formacao, atuacao_docente, producao_cademica
prestacao_servicos, atividade_adm, titulos_homenagens

# Datas dos documentos preliminares
data_concessao_ultima_rt                  = DateFieldPlus  # última RT concedida
data_exercio_carreira                     = DateFieldPlus  # início no EBTT
data_conclusao_titulacao_rsc_pretendido   = DateFieldPlus  # titulação que habilita o RSC

# Ciência do resultado
concorda_deferimento          = IntegerField(choices, null=True)  # CONCORDA(1)/DISCORDA(2)
concorda_data_retroatividade  = IntegerField(choices, null=True)
data_ciencia                  = DateTimeFieldPlus(null=True)
data_finalizacao_processo     = DateTimeFieldPlus(null=True)
assinatura_requerimento       = TextField(default='')
clonado                       = BooleanField(default=False)

# Meta.permissions
('pode_validar_processorsc', 'Pode validar ProcessoRSC')
('pode_ver_relatorio_rsc',  'Pode ver relatório RSC')
```

**Atenção**: `__init__` carrega `self.config = ConfiguracaoRSC.objects.first()` em toda instância.

**Métodos relevantes**:
```python
# Contagem de avaliadores por tipo/status
qtd_avaliadores_internos_reserva() / qtd_avaliadores_externos_reserva()
qtd_avaliadores_internos_ativos()  / qtd_avaliadores_externos_ativos()
avaliador_interno_pagamento() / avaliadores_externos_pagamento()  # finalizados

# Estado / permissões de etapa
pode_mostrar_avaliacao()          # status final ou em ciência
pode_selecionar_avaliadores()     # AGUARDANDO_AVALIADORES / ACEITE / EM_AVALIACAO
pode_ser_validado()               # AGUARDANDO_VALIDACAO_CPPD / NOVA_VALIDACAO
avaliado_pode_editar()            # AGUARDANDO_ENVIO_CPPD / AGUARDANDO_AJUSTES
avaliado_pode_ajustar()           # apenas AGUARDANDO_AJUSTES (só campos texto)
ultima_validacao_processo()       # ValidacaoCPPD mais recente

# Arquivos exigidos (documentos preliminares)
get_arquivo_titulacao() / get_arquivo_inicio_exercicio() / get_arquivo_ultima_concessao_rt()
get_arquivos_rsc_pretendido()     # Arquivos do tipo_rsc pretendido, por data_referencia

# Cálculo de retroatividade e pontuação (NÚCLEO DA REGRA DE NEGÓCIO — ver §10)
get_arquivos_avaliacoes(rsc_pretendido, avaliador, exclude_arquivo_ids)
get_data_referencia_retroativa(validada, soh_arquivos, avaliador)
get_data_referencia_final()       # data final consolidada das avaliações deferidas
_soma_pontos(lista_de_lista)
_calculo_pontos(status, com_corte, avaliador)   # pontuação por consenso entre avaliadores

# Avaliação / resultado
criar_avaliacao(avaliador)        # @atomic: cria Avaliacao + AvaliacaoItem por Arquivo
calcula_aprovacao()               # maioria: indeferidas > deferidas → REPROVADO
estado_atual_processo()           # considera aposentado (→ ANALISADO)
finalizar_processo() / deferir_processo_aposentado()
dar_ciencia_resultado(opcao_deferimento, opcao_data_retroatividade)
banca_avaliadora_final()          # avaliadores com avaliação finalizada
interessado_falecido()            # ocorrência FALECIMENTO no servidor

# Assinatura digital do requerimento
@property conteudo_a_ser_assinado_do_requerimento   # f'{pk}{pontuacao_pretendida}'
@property chave_a_ser_utilizada_na_assinatura_do_requerimento  # f'{servidor_id}'
@property status_estilizado        # HTML span com classe CSS

@classmethod lista_processos(request)   # processos do próprio usuário
```

### 3.2 `Arquivo` — Documento Comprobatório (`EncryptedPKModel`)

```python
processo        = ForeignKeyPlus(ProcessoRSC)
criterio        = ForeignKeyPlus(Criterio, null=True)
nome            = CharFieldPlus(255)
diretorio       = CharFieldPlus(255, unique=True)
nota_pretendida = DecimalFieldPlus(default=0, null=True)
qtd_itens       = IntegerField(null=True)
data_referencia = DateField(null=True)
tamanho         = BigIntegerField()
descricao       = TextField(blank=True)   # compõe o relatório descritivo

get_data_referencia()                 # data validada por consenso (≥2 avaliadores) ou maior data
get_qtd_itens(avaliador)              # qtd validada pelo avaliador (ou pretendida)
get_nota_pretendida(avaliador, validada=False)
    # = get_qtd_itens(avaliador) * criterio.fator * criterio.diretriz.peso  (se validada)
    # = qtd_itens * criterio.fator * criterio.diretriz.peso                  (se não)
```

### 3.3 `ArquivosExigidos` — Documentos Preliminares Obrigatórios (`EncryptedPKModel`)

```python
TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO = 1
INICIO_EXERCIO_CARREIRA                   = 2
CONCESSAO_ULTIMA_RT                       = 3

processo  = ForeignKeyPlus(ProcessoRSC)
nome      = CharFieldPlus(255)
diretorio = CharFieldPlus(255, unique=True)
tamanho   = BigIntegerField()
tipo      = IntegerField(choices)

# save() sobrescreve: deleta o último registro do mesmo tipo (storage + DB) antes de salvar
# → garante 1 documento por tipo por processo
```

### 3.4 `Criterio` — Critério de Pontuação

```python
STATUS_ATIVO = 0 / STATUS_INATIVO = 1

diretriz                      = ForeignKeyPlus(Diretriz)
numero                        = IntegerField()
nome                          = TextField()
status                        = IntegerField(choices)
fator                         = DecimalFieldPlus()       # multiplicador da pontuação
unidade                       = ForeignKeyPlus(Unidade)
teto                          = IntegerField()           # máx. de itens do critério
categoria_memorial_descritivo = ForeignKeyPlus(CategoriaMemorialDescritivo)

tem_arquivo_sem_descricao(processo)  # → bool
```

### 3.5 `Diretriz` — Agrupador de Critérios por Tipo de RSC

```python
tipo_rsc  = ForeignKeyPlus(TipoRsc, null=True)
nome      = CharFieldPlus(255)
descricao = TextField()
peso      = IntegerField()       # peso da diretriz na pontuação
teto      = IntegerField()       # valor máximo de pontos da diretriz (corte)

unique_together = ('tipo_rsc', 'nome')
ordering = ('pk',)
```

### 3.6 `TipoRsc` — Nível de RSC Pretendido

```python
nome      = CharFieldPlus(255)   # 'RSC-I', 'RSC-II', 'RSC-III'
categoria = CharFieldPlus(255)

unique_together = ('nome', 'categoria')
```

### 3.7 `Unidade` — Unidade de Medida dos Critérios

```python
nome  = CharFieldPlus(255, unique=True)
sigla = CharFieldPlus(50)
```

### 3.8 `CategoriaMemorialDescritivo` — Categorias do Relatório Descritivo

```python
nome = CharFieldPlus(255)
```

### 3.9 `ValidacaoCPPD` — Validação dos Documentos Preliminares pela CPPD

```python
ACAO_ACEITAR = 0 / ACAO_DEVOLVER = 1 / ACAO_REJEITAR = 2

TIPO_VALIDACAO_VALIDADO                          = 1
TIPO_VALIDACAO_DATA_ERRADA                       = 2
TIPO_VALIDACAO_DOCUMENTACAO_NAO_AUTENTICADA      = 3
TIPO_VALIDACAO_DOCUMENTACAO_NAO_CONDIZ_COM_EXIGIDO = 4

processo = ForeignKeyPlus(ProcessoRSC)
# titulação
data_conclusao_titulacao_rsc_pretendido_validada = DateFieldPlus
titulacao_status                                 = IntegerField(choices)
# exercício na carreira
data_exercio_carreira_validada                   = DateFieldPlus
inicio_exercicio_status                          = IntegerField(choices)
# última RT
data_concessao_ultima_rt_validada                = DateFieldPlus
ultima_concessao_rt_status                       = IntegerField(choices)
formulario_pontuacao_status                      = IntegerField
relatorio_descritivo_status                      = IntegerField
validador        = ForeignKeyPlus('rh.Servidor')
acao             = IntegerField(choices)
motivo_rejeicao  = CharField(2000)
data             = DateTimeFieldPlus(auto_now_add=True)
ajustado         = BooleanField(default=False)
```

### 3.10 `ProcessoAvaliador` — Vínculo Processo ↔ Avaliador

```python
EM_ESPERA = 0 / AGUARDANDO_ACEITE = 1 / EM_AVALIACAO = 2 / AVALIACAO_FINALIZADA = 3
EXCEDEU_TEMPO_ACEITE = 4 / EXCEDEU_TEMPO_AVALIACAO = 5 / REJEITADO_PELO_AVALIADOR = 6

AVALIADOR_INTERNO = 'avaliador_interno' / AVALIADOR_EXTERNO = 'avaliador_externo'
# tipo_recusa: RELACIONADO_PROCESSO_ANALISE / DE_ORDER_PESSOAL / DE_ORDER_PROFISSIONAL / OUTROS

processo             = ForeignKeyPlus(ProcessoRSC)
avaliador            = ForeignKeyPlus('rh.Avaliador', related_name='processo_avaliador_rsc')
data_cadastro        = DateTimeFieldPlus(auto_now_add=True)
data_convite         = DateTimeFieldPlus(null=True)
data_aceite          = DateTimeFieldPlus(null=True)
status               = IntegerField(choices)
tipo_avaliador       = CharFieldPlus(choices)
tipo_recusa          = IntegerField(choices, null=True)
motivo_recusa        = CharField(2000, null=True)
responsavel_cadastro = ForeignKeyPlus('comum.Vinculo', null=True)

# Meta.permissions
('pode_avaliar_processorsc', 'Pode avaliar ProcessoRSC')
('pode_atualizar_dados_cadastrais', 'Pode atualizar dados cadastrais')

pode_aceitar_avaliacao()   # exige telefone + dados bancários completos do avaliador
aceitar()                  # → EM_AVALIACAO + processo EM_AVALIACAO + data_aceite
rejeitar(dados)            # @atomic: rejeita, promove próximo RESERVA do mesmo tipo, envia email
                           #   se não houver reserva → email à CPPD (chave 'email_cppd')
data_limite()              # data limite considerando fins de semana (aceite ou avaliação)
data_limite_display()      # HTML
situacao_avaliador()       # HTML (badge ou barra de progresso)
calcula_porcentagem_avaliacao()
avaliador_excluido_processo() / avaliador_principal() / avaliador_reserva()
avaliacao_correspondente() # Avaliacao do par processo+avaliador
```

### 3.11 `Avaliacao` — Avaliação Realizada por um Avaliador

```python
EM_AVALIACAO = 0 / DEFERIDA = 1 / INDEFERIDA = 2 / INTERROMPIDA = 3 / DESISTENCIA = 4

status               = IntegerField(choices)
processo             = ForeignKeyPlus(ProcessoRSC)
avaliador            = ForeignKeyPlus('rh.Avaliador', related_name='avaliacao_avaliador_rsc')
motivo_indeferimento = CharField(2000)
tipo_desistencia     = IntegerField(choices, null=True)
motivo_desistencia   = CharField(2000, null=True)
data_finalizacao     = DateTimeFieldPlus(null=True)
avaliacao_paga       = BooleanField(default=False)
data_pagamento       = DateTimeFieldPlus(null=True)
tipo_avaliador       = CharFieldPlus(choices, null=True)

avaliacao_finalizada()  # DEFERIDA ou INDEFERIDA
pode_avaliar()          # EM_AVALIACAO
desistir_avaliacao(dados) # → DESISTENCIA + ProcessoAvaliador.rejeitar() (promove reserva)
finalizar_avaliacao()   # valida itens, aplica regra 25/50 pontos, define DEFERIDA/INDEFERIDA;
                        #   ao atingir 3 avaliações finalizadas → processo AGUARDANDO_CIENCIA
                        #   (e calcula pontuacao_validada_com/sem_corte)
```

### 3.12 `AvaliacaoItem` — Avaliação de um Arquivo Específico

```python
avaliacao          = ForeignKeyPlus(Avaliacao)
arquivo            = ForeignKeyPlus(Arquivo)
data_referencia    = DateField(null=True)    # data validada pelo avaliador
qtd_itens_validado = IntegerField(null=True) # qtd validada pelo avaliador
justificativa      = CharField(2000, null=True)

houve_alteracao_avaliacao()  # avaliador mudou data/qtd em relação ao declarado
item_validado()              # qtd>0 com data, ou qtd==0
pontuacao_validada()         # arquivo.get_nota_pretendida(avaliador, True) se qtd>0, senão None
```

### 3.13 `ParametroPagamento` — Parâmetros de Pagamento de Avaliadores

```python
valor_por_avaliacao = FloatField()
hora_por_avaliacao  = IntegerField()
data_cadastro       = DateField(auto_now_add=True)
```

### 3.14 `CloneArquivoErro` — Erros na Clonagem de Processo

```python
ARQUIVO_EXIGIDO = 1 / ARQUIVO = 2
tipo_arquivo           = IntegerFieldPlus(choices)
nome_arquivo           = CharFieldPlus()
processo_rsc           = ForeignKeyPlus(ProcessoRSC)
tipo_documento_exigido = CharFieldPlus(null=True)
criterio               = ForeignKeyPlus(Criterio, null=True, on_delete=SET_NULL)

get_localizacao()  # tipo_documento_exigido OU 'tipo_rsc >> diretriz >> criterio'
```

### 3.15 `ConfiguracaoRSC` — Configuração Global (Singleton)

```python
descricao            = CharFieldPlus(500, unique=True)   # 'CONFIG_RSC'
dias_para_aceite     = PositiveIntegerFieldPlus          # fixture: 7
dias_para_avaliacao  = PositiveIntegerFieldPlus          # fixture: 15
pontos_soma_rsc      = PositiveIntegerFieldPlus          # fixture: 50 (RSC-I + RSC-II + RSC-III)
pontos_rsc_pretendido= PositiveIntegerFieldPlus          # fixture: 25 (no RSC pretendido)
# Textos (RichTextField) usados em emails e instruções:
email_professor_sorteado, email_sem_avaliador_reserva, email_professor_perdeu_prazo
instrucoes_gerais (avaliado), instrucoes_gerais_avaliador

# Placeholders dos emails: {{NOME_AVALIADOR}}, {{NOME_PROFESSOR_AVALIADO}},
#   {{DATA_LIMITE_ACEITE_AVALIACAO}}, {{DIAS_PARA_AVALIACAO}}, {{PROCESSO_RSC}}, {{SITE_URL}}
# Acesso sempre via ConfiguracaoRSC.objects.first()
```

---

## 4. Fluxo do Processo (Máquina de Estados)

```
SERVIDOR docente cria processo (criar_processo_rsc)
                ↓
  AGUARDANDO_ENVIO_CPPD (3)
  [Docente preenche relatório descritivo, anexa documentos comprobatórios + preliminares,
   assina requerimento]
                ↓ enviar_processo_rsc()
  AGUARDANDO_VALIDACAO_CPPD (2)
  [CPPD valida datas (titulação, exercício, última RT), formulário, relatório]
         ↙ devolver              ↘ rejeitar
  AGUARDANDO_AJUSTES (5)      REJEITADO (6) — fim
  [Docente ajusta texto]
         ↓ reenvio
  AGUARDANDO_NOVA_VALIDACAO (7)
         ↓ aceitar (CPPD)
  AGUARDANDO_AVALIADORES (4)
  [CPPD seleciona avaliadores internos + externos (com reservas)]
         ↓ selecionar_avaliadores()
  AGUARDANDO_ACEITE_AVALIADOR (8)
  [Avaliador tem dias_para_aceite p/ aceitar/recusar; reserva é promovida automaticamente]
         ↓ aceite (exige dados bancários + telefone)
  EM_AVALIACAO (9)
  [Cada avaliador valida cada Arquivo → AvaliacaoItem (qtd + data + justificativa)]
         ↓ 3ª avaliação finalizada
  AGUARDANDO_CIENCIA (11)
  [Docente toma ciência: concorda/discorda do resultado E da data de retroatividade]
         ↓ dar_ciencia_resultado()   (se falecido → ciência automática)
  CIENTE_DO_RESULTADO (10)
         ↓ finalizar_processo() pela CPPD
         ↙                  ↘
  DEFERIDO (0)        INDEFERIDO (1)        [aposentado → ANALISADO (12)]
```

**Regra de resultado** (`calcula_aprovacao`): se nº de avaliações **INDEFERIDA > DEFERIDA** → **REPROVADO**; caso contrário → **APROVADO**. A pontuação consolidada usa **consenso entre avaliadores** (`_calculo_pontos`): se ≥2 avaliadores chegam ao mesmo valor, esse é o oficial; senão usa o mínimo (deferidas) ou máximo (indeferidas).

**Processos de aposentado**: `tipo_processo = TIPO_PROCESSO_APOSENTADO`; `estado_atual_processo` leva ao status `ANALISADO (12)` via `deferir_processo_aposentado()`.

---

## 5. Views — Mapa (`views.py`, sem `app_name`, rotas montadas em `/rsc/`)

### Gestão de Processo (ator: Docente)
| View | Rota | Observação |
|------|------|-----------|
| `criar_processo_rsc` | `/criar_processo_rsc/` | `PermissionDenied` se não puder |
| `abrir_processo_rsc` | `/abrir_processo_rsc/<id>/` | interface principal de edição |
| `salvar_processo_rsc` | `/salvar_processo_rsc/<id>/` | `@csrf_exempt` |
| `enviar_processo_rsc` | `/enviar_processo_rsc/<id>/` | → AGUARDANDO_VALIDACAO_CPPD |
| `excluir_processo_rsc` | `/excluir_processo_rsc/<id>/` | |
| `clonar_processo_rsc` | `/clonar_processo_rsc/<id>/` | `@atomic`; erros em `CloneArquivoErro` |
| `clonar_processo_rsc_mantendo_mesmo_processo_eletronico` | `/clonar.../<id>/` | clona reusando o PE |
| `ciencia_resultado` | `/ciencia_resultado/<id>/` | docente dá ciência |

### Upload / Arquivos (IDs encriptados — `<str:arquivo_id>`)
| View | Rota |
|------|------|
| `rsc_upload` | `/rsc_upload/` (name=`rsc_upload`) |
| `rsc_upload_documentos_exigidos` | `/rsc_upload_documentos_exigidos/` |
| `visualizar_arquivo_pdf` / `visualizar_arquivo_exigido_pdf` | `/visualizar_arquivo[_exigido]_pdf/<str:id>/` |
| `excluir_arquivo_pdf` / `excluir_arquivo_exigido_pdf` | `/excluir_arquivo[_exigido]_pdf/<str:id>/` (`@csrf_exempt`) |

### PDFs / Relatórios
`imprimir_processo`, `requerimento_pdf`, `formulario_pontuacao_pdf`, `relatorio_descritivo` / `relatorio_descritivo_pdf`, `documentos_anexados_pdf`, `imprimir_documentos_pdf`, `quadro_resumo_pontuacao_requerida`, `documentos_preliminares`, `download_arquivos`, `gerar_processo_completo` — todos `/<view>/<id>/`. PDFs usam `@documento(...)`.

### Validação CPPD (`@permission_required('rsc.pode_validar_processorsc')`)
| View | Rota |
|------|------|
| `validar_processorsc` | `/validar_processorsc/<id>/` (`@atomic`) |
| `rejeitar_processo_cppd` | `/rejeitar_processo_cppd/<id>/` |
| `selecionar_avaliadores` | `/selecionar_avaliadores/<id>/` |
| `acompanhar_avaliacao` | `/acompanhar_avaliacao/<id>/` (dashboard) |
| `finalizar_processo` | `/finalizar_processo/<id>/` |
| `deferir_processo_aposentado` | `/deferir_processo_aposentado/<id>/` |
| `aceitar_rejeitar_processo` | `/aceitar_rejeitar_processo/<id>/` |
| `processos_sem_avaliador_reserva` | `/processos_sem_avaliador_reserva/` |
| `revisar_datas_limite` | `/revisar_datas_limite/` |

### Avaliação (ator: Avaliador)
| View | Rota |
|------|------|
| `processo_avaliacao` | `/processo_avaliacao/` (lista do avaliador) |
| `termo_aceite` | `/termo_aceite/<processo_avaliacao_id>/` |
| `recusar_avaliacao` | `/recusar_avaliacao/<processo_avaliacao_id>/` |
| `avaliar_processo` | `/avaliar_processo/<processo_id>/<avaliador_id>/` |
| `avaliar_item` | `/avaliar_item/<avaliacao_item_id>/` |
| `salvar_avaliacao` | `/salvar_avaliacao/<avaliacao_item_id>/` |
| `quadro_resumo_avaliacao` | `/quadro_resumo_avaliacao/<avaliacao_id>/` |
| `finalizar_avaliacao` | `/finalizar_avaliacao/<avaliacao_id>/` (`@permission_required pode_avaliar`) |
| `desistir_avaliacao` | `/desistir_avaliacao/<avaliacao_id>/` |

### Pagamento de Avaliadores (CPPD/RH)
`processos_pagamento_avaliador_interno`, `processos_pagamento_avaliador_externo`, `popup_avaliacao_pagamento_avaliador/<avaliador_id>/`, `relatorio_pagamento`, `relatorio_pagamento_pdf`.

### Processo Eletrônico
`atualizar_processo_eletronico_rsc`, `gerar_processo_eletronico/<id>/` (só Presidente CPPD/superuser; usa `TipoProcesso id=517`, assunto "Reconhecimento de Saberes e Competências - RSC").

### Helpers internos de upload
`create_on_upload(...)`, `create_on_upload_documentos_exigidos(...)`, `get_upload_directory(instance)`.

---

## 6. Funções de Verificação de Acesso (`views.py`)

Permissões NÃO usam classes; são funções no final de `views.py`. **Use sempre estas — nunca crie checagens ad-hoc:**

```python
eh_dono(request, processo)        # request.user.get_vinculo() == processo.servidor.get_vinculo()
soh_dono(request, processo)       # raise PermissionDenied se não for dono
eh_avaliador(request, processo)   # has_perm('rsc.pode_avaliar_processorsc')
eh_membro_cppd(request)           # has_perm('rsc.pode_validar_processorsc')
eh_presidente_cppd(request)       # has_perm('rsc.delete_processoavaliador')
eh_rh(request)                    # has_perm('rsc.pode_ver_relatorio_rsc')
soh_cppd(request)                 # raise se não for CPPD

# Combinações (raise PermissionDenied se nenhum papel satisfizer)
soh_cppd_dono_avaliador(request, processo)
soh_presidentecppd_e_dono(request, processo)
soh_cppd_e_dono(request, processo)
soh_cppd_dono_e_rh(request, processo)

# Por objeto (consultam o BD)
eh_avaliador_do_processo(request, processo_id)   # ProcessoAvaliador do vínculo
eh_avaliador_da_avaliacao(request, avaliacao_id) # Avaliacao do vínculo
```

> ⚠️ Cuidado: `soh_cppd_e_dono` tem uma peculiaridade — usa `soh_dono(...)` (que já levanta exceção) dentro de um `and`. Ao mexer nessa função, verifique a lógica.

---

## 7. Formulários (`forms.py`)

| Formulário | Base | Propósito |
|-----------|------|-----------|
| `ProcessoRSCAddForm` | `forms.Form` | criação |
| `ProcessoRSCDocumentoExigidosForm` | `ModelFormPlus` | wrapper de documentos exigidos |
| `ProcessoRSCForm` | `FormPlus` | edição principal (datas, textos, campos dinâmicos por critério) |
| `DataConclusaoTitulacaoRSCForm` / `DataExercicioCarreiraForm` | `FormPlus` | datas dos preliminares (upload Ajax) |
| `DocumentosExigidosForm` | `FormPlus` | documentos preliminares |
| `ValidacaoCPPDForm` | `ModelFormPlus` | validação CPPD (model=`ValidacaoCPPD`) |
| `RejeitarProcessoCPPDForm` | `FormPlus` | rejeição CPPD; `processar()` |
| `JustificativaDesistenciaForm` | `FormPlus` | desistência do avaliador |
| `RecusaAvaliacaoForm` | `FormPlus` | recusa de convite; `processar()` |
| `AvaliadorForm` | `FormPlus` | seleção de avaliadores internos/externos; `processar(vinculo)`; `clean_avaliador_interno()` |
| `ProcessoAvaliadorForm` | `ModelFormPlus` | admin |
| `ProcessoPagamentoForm` | `FormPlus` | filtro de pagamento (GET) |
| `RelatorioPagamentoForm` | `FormPlus` | relatório (`clean_data_inicio`/`clean_data_final`) |
| `AssinaturaRequerimentoForm` | `SuapAssinaturaForm` | assinatura digital |
| `AtualizarProcessoRSCForm` | `FormPlus` | `clean()` + `processar()` |

---

## 8. Admin (`admin.py`)

### `ProcessoRSCAdmin`
- `list_filter = (CustomTabListFilter,)`, `show_count_on_tabs = True`, `export_to_xls = True`, `list_display_icons = False`
- `get_tabs()` define abas (Meus Processos, Processos Pendentes etc.) e `get_list_display()` adiciona coluna de pagamento conforme o papel.

### `ProcessoAvaliacaoAdmin` (model `ProcessoAvaliador`)
- `list_filter = ('status', 'processo__status', ProtocoloYearFilter, ('data_aceite', DateRangeListFilter))`, `export_to_xls = True`

### Demais Admins
`AvaliacaoAdmin`, `UnidadeAdmin`, `DiretrizAdmin` (filtro por `tipo_rsc`), `TipoRscAdmin`, `CriterioAdmin` (filtros diretriz/unidade/status), `ParametroPagamentoAdmin`, `ValidacaoCPPDAdmin`, `ArquivoAdmin`, `ArquivosExigidosAdmin`, `ConfiguracaoRSCAdmin`.

---

## 9. RBAC — Papéis e Permissões (`permissions.yaml`)

| Papel | App Manager | Capacidades principais |
|-------|-------------|------------------------|
| **Servidor** | rh | add/view/change `processorsc` (próprio) |
| **Aposentado** | rh | add/view/change `processorsc` |
| **Avaliador Interno** | — | `pode_avaliar_processorsc` |
| **Avaliador Externo** | — | `pode_avaliar_processorsc` + `pode_atualizar_dados_cadastrais` |
| **Coordenador de Gestão de Pessoas** | rh | `pode_ver_relatorio_rsc` |
| **Membro CPPD** | — | CRUD cadastros (criterio, diretriz, tiporsc, unidade, parametropagamento, configuracaorsc); processoavaliador view/change/delete; processorsc + `pode_validar_processorsc` |
| **Presidente CPPD** | — | idem Membro + `instituicao` (rh) |
| **Coordenador de Gestão de Pessoas Sistêmico** | rh | idem CPPD + `pode_ver_relatorio_rsc` + `avaliador` (rh) |

Menu (`menu.yaml`): Avaliadores nos Processos, Cadastros (Critérios/Diretrizes/Parâmetros/Tipos de RSC/Unidades/Configurações), Financeiro (Pagamento), Meus Processos, Processos, Processos para Avaliação, Processos sem Avaliador Reserva — todos sob `Gestão de Pessoas::Desenvolvimento de Pessoal::Docentes::RSC`.

---

## 10. Regras de Negócio Críticas

### Pontuação de um arquivo
```
nota = qtd_itens * criterio.fator * criterio.diretriz.peso
```
Aplica-se **teto por diretriz** (`Diretriz.teto`): a soma de pontos dos arquivos de uma diretriz não ultrapassa o teto. `com_corte=True` aplica o teto; `com_corte=False` é só para depuração.

### Aprovação (config `CONFIG_RSC`)
1. **≥ `pontos_rsc_pretendido` (25)** pontos no RSC pretendido (`tipo_rsc`); E
2. **≥ `pontos_soma_rsc` (50)** pontos na soma RSC-I + RSC-II + RSC-III.

`Avaliacao.finalizar_avaliacao()` aplica essas duas verificações para definir DEFERIDA/INDEFERIDA. O processo só consolida resultado após **3 avaliações finalizadas** (`finalizadas >= 3`).

### Data de Retroatividade (`get_data_referencia_retroativa`)
A data de efeitos financeiros é a **data mais recente** em que se completam **25 pontos no RSC pretendido** e depois **50 pontos no total**, percorrendo os arquivos por `data_referencia`. Considera ainda as datas de titulação, exercício e última RT (validadas pela CPPD quando houver). **Nunca anterior a `DATA_LEI_RETROATIVIDADE = 2013-03-01`**. Com `validada=True`, usa as datas validadas pelos avaliadores (consenso de ≥2; senão a maior/pior data para o avaliado).

### Consenso entre Avaliadores
- **Pontuação** (`_calculo_pontos`): valor concordado por ≥2 avaliadores; senão `min` (deferidas) ou `max` (indeferidas).
- **Datas** (`get_arquivos_avaliacoes` / `Arquivo.get_data_referencia`): data coincidente entre ≥2 avaliadores; senão a maior (mais recente).
- **Resultado final** (`calcula_aprovacao`): maioria entre DEFERIDA/INDEFERIDA.

### Avaliadores: aceite, prazos e reservas
- Aceitar exige **telefone + dados bancários completos** (`pode_aceitar_avaliacao`).
- Prazos em dias úteis (pula sábado/domingo): `dias_para_aceite` e `dias_para_avaliacao`.
- Recusa/desistência/perda de prazo → **promove o próximo avaliador reserva** do mesmo tipo (`rejeitar`) e dispara email; sem reserva → email à CPPD.
- A task diária `checa_datas_processos_rsc` detecta prazos estourados (`EXCEDEU_TEMPO_ACEITE`/`EXCEDEU_TEMPO_AVALIACAO`) e promove reservas.

### Documentos Preliminares
3 tipos obrigatórios (`ArquivosExigidos`): título (mestrado/especialização/graduação), início de exercício na carreira, concessão da última RT. `save()` garante **1 arquivo por tipo** (apaga o anterior).

### Ciência do Resultado
Docente declara concordância com (a) deferimento/indeferimento e (b) data de retroatividade. **Interessado falecido** → `dar_ciencia_resultado(1, 1)` automático.

### Clonagem
`clonar_processo_rsc` copia arquivos + textos; falhas registradas em `CloneArquivoErro`; processo clonado tem `clonado=True`. Há variante que **mantém o mesmo processo eletrônico**.

### Assinatura do Requerimento
Conteúdo `f'{pk}{pontuacao_pretendida}'`, chave `f'{servidor_id}'`, via `AssinaturaRequerimentoForm` (`SuapAssinaturaForm`).

---

## 11. Tarefas Assíncronas

```python
# beat.py — crontab 02:07 diariamente
'[rsc] Checar Datas Processos' → management command 'checa_datas_processos_rsc'
```
O comando promove reservas para processos com prazo estourado e dispara emails (professor sorteado / sem reserva / perdeu prazo). Email da CPPD: hardcoded `cppd@ifrn.edu.br` no comando, e via `Configuracao.get_valor_por_chave('rsc', 'email_cppd')` em `ProcessoAvaliador.rejeitar()`.

Outros comandos: `avaliar_tudo_rsc <processo_id> <avaliador_id>` (replica dados declarados na avaliação — utilitário de teste/correção) e `rsc_corrigir` (recalcula `pontuacao_pretendida_rsc1/2/3` de todos os processos).

---

## 12. Dependências com Outros Módulos

| Módulo | Tipo | Uso |
|--------|------|-----|
| `rh.Servidor` | **Forte** | FK principal em `ProcessoRSC`; docente solicitante (inclui `eh_aposentado`, `servidorocorrencia_set`) |
| `rh.Avaliador` | **Forte** | FK em `ProcessoAvaliador` e `Avaliacao` (`eh_interno`/`eh_externo`, dados bancários) |
| `rh.utils` | Média | `substituir_marcacoes` (placeholders de email) |
| `comum.Vinculo` | Média | `responsavel_cadastro`; identificação de dono/avaliador |
| `comum.Configuracao` | Leve | chave `rsc.email_cppd` |
| `protocolo.Processo` | Média | FK opcional `protocolo` |
| `processo_eletronico.Processo` | Média | FK `processo_eletronico` (`cadastrar_processo`, `TipoProcesso id=517`) |
| `djtools` | Forte | `EncryptedPKModel`, `ModelPlus`, `@rtr`, `@documento`, `httprr`, `send_mail`, `send_notification` |

---

## 13. Fixtures e Carga Inicial

```bash
# Configuração singleton + instituições
python manage.py loaddata rsc/fixtures/configuracao.json
python manage.py loaddata rsc/fixtures/initial_data_instituicoes.json

# Diretrizes e Critérios via planilhas (NÃO há fixture JSON):
# rsc/importar_arquivo_xls.py → importar_diretrizes() e importar_unidade_criterios()
#   leem rsc/static/rsc/diretrizes.xls e rsc/static/rsc/unidades_criterios.xls
#   e criam TipoRsc, Diretriz, Unidade, CategoriaMemorialDescritivo, Criterio (get_or_create)
```

---

## 14. Como Atuar como Especialista

1. **Identifique o contexto** pelo vocabulário: "RSC docente", "RSC-I/II/III", "retribuição por titulação", "CPPD", "banca de avaliadores", "avaliador interno/externo", "data de retroatividade", "relatório descritivo", "diretriz/critério", "teto", "RSC pretendido" → este módulo (`rsc`). Se for "TAE" / "rol de saberes" → é o `rsc_tae` (outro módulo).

2. **Leia os arquivos antes de sugerir alterações**: tudo em arquivos únicos — `rsc/models.py`, `rsc/views.py`, `rsc/forms.py`, `rsc/admin.py`.

3. **Respeite a máquina de estados** (§4) — qualquer alteração de `ProcessoRSC.status`, `ProcessoAvaliador.status` ou `Avaliacao.status` deve considerar as transições e os métodos de domínio (`finalizar_avaliacao`, `rejeitar`, `aceitar`, `finalizar_processo`).

4. **Permissões via funções** (§6) — use `eh_membro_cppd()`, `eh_dono()`, `eh_avaliador()`, `soh_cppd()` etc. Nunca crie verificação ad-hoc.

5. **IDs encriptados** — `ProcessoRSC`, `Arquivo` e `ArquivosExigidos` herdam de `EncryptedPKModel`; rotas com `<str:arquivo_id>` (não `<int:>`) recebem IDs encriptados. Use o `EncryptedPKModelManager`.

6. **Pontuação tem teto por diretriz** — ao calcular, use `com_corte=True` para o valor oficial; respeite `nota = qtd * fator * peso` e o teto da diretriz.

7. **A regra 25/50 e a data de retroatividade** (§10) são o coração do módulo e são intrincadas — releia `get_data_referencia_retroativa`, `_calculo_pontos` e `finalizar_avaliacao` antes de tocá-las e adicione testes.

8. **Avaliadores têm prazos e reservas automáticos** — a task `checa_datas_processos_rsc` é crítica; ao mexer em prazos/aceite, verifique compatibilidade com o comando e com `ProcessoAvaliador.rejeitar()`.

9. **Complexidade ciclomática ≤ 10** nas funções tocadas (regra do repo para código de agente). Vários métodos legados deste módulo já estão acima disso; ao editá-los, refatore extraindo helpers.

10. **Siga os padrões do djtools** — `ModelPlus`/`EncryptedPKModel`, `ModelFormPlus`/`FormPlus`, `@rtr`, `@documento`, `httprr()`, `@permission_required`, `send_mail`/`send_notification`. Texto e identificadores em pt-BR.

$ARGUMENTS
