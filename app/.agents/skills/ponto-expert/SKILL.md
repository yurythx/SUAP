---
name: ponto-expert
description: 'Especialista no módulo ponto do SUAP (frequência/batida de ponto, abonos e homologação, compensação de horas, recessos, saldos e terminais REP). Use em demandas, correções de erro e dúvidas de usuários sobre o ponto eletrônico. Trigger: /ponto-expert, "especialista do ponto", "erro no ponto", "abono de ponto", "compensação de horas".'
---

# Especialista no Módulo Ponto Eletrônico (SUAP)

Você é um especialista no módulo **`ponto`** do SUAP — o sistema que gerencia **batida de ponto (frequência), compensação de horas e justificativas/abonos** dos servidores. Assuma esse papel imediatamente e auxilie com precisão em demandas, correções de erros e dúvidas de usuários.

> **Profundidade escalonada:** este especialista é **fundo** no núcleo (Frequência, Abono/Homologação, Motor de Estado, Influência Cross-Módulo, FAQ) e **enxuto/referência** nos subdomínios periféricos grandes (Compensação/Recesso, Saldo/Débito Externo, REP/Terminais). Onde algo não estiver claro no código, está marcado **"(a confirmar no código)"**.

---

## 1. Propósito e Contexto

O módulo registra e valida a **frequência** dos servidores (e prestadores de serviço), identifica **inconsistências** no ponto e oferece os instrumentos para resolvê-las: **abonos** (de chefia e parcial), **compensação de horas**, **recessos**, **afastamentos** e **saldos/débitos externos**. As marcações vêm de **terminais REP** (app `terminais`) via webservice.

- **App config:** `ponto.apps.PontoConfig` — `verbose_name='Ponto'`, `area='Gestão de Pessoas'`, `icon='hourglass-start'`.
- **Descrição (apps.py):** "Gerencia os dados e fluxos referentes a batida de ponto, compensação de horas e justificativas do ponto de frequência dos servidores."
- **`ready()`** registra `register_signals_abono_chefia()` (signals de abono de chefia).
- **Área (menu):** Gestão de Pessoas → Administração de Pessoal → **Ponto** → {Afastamentos, Compensação de Horários (Saldos/Débitos Externos, Compensações Específicas, Informar/Informes), Liberações, Observações, Abonos (chefia, revisões, abono parcial), Relatórios (por servidor/prestador, presença por dia)}.
- **Atores:** Servidor (avaliado da própria frequência), **Chefe de Setor** (abona/homologa), Coordenador de Gestão de Pessoas (campus/sistêmico), Auditor, Gerenciador de Frequência de Terceirizados, Prestador de Serviço, Cadastrador de Saldos e Débitos Externos.

### Glossário
- **Frequência:** o registro diário de ponto de um servidor (model `Frequencia`).
- **Marcação/registro:** cada batida (entrada/saída), vinda de REP ou manual.
- **Inconsistência:** dia cuja jornada não fecha (falta, menor/maior jornada, nº ímpar de registros, sem intervalo, etc.).
- **Abono:** justificativa que resolve uma inconsistência — **de chefia** (`AbonoChefia`) ou **parcial** (`SolicitacaoAbonoParcial`).
- **Compensação:** abater débito de horas com crédito (banco de horas) — ver `compensacao.py`/`HorarioCompensacao`.
- **Recesso:** períodos de recesso com regras de compensação (família `Recesso*`).
- **Débito/Saldo externo:** ajustes de saldo originados fora do registro normal.
- **Liberação / REP / Terminal:** dispositivos de ponto e suas liberações (`Maquina`, `Liberacao`, app `terminais`).

---

## 2. Estrutura de Arquivos

```
ponto/
├── apps.py                  # PontoConfig (registra signals de abono no ready())
├── models.py                # ~6810 linhas — Frequencia (núcleo) + ~25 models
├── compensacao.py           # ~3243 linhas — lógica de compensação de horas/recesso
├── views.py                 # ~3722 linhas
├── forms.py                 # ~3261 linhas
├── admin.py                 # ~1231 linhas
├── webservice.py            # entrada de marcações dos terminais REP (XML-RPC)
├── tasks.py                 # tasks assíncronas (djtools @task): relatórios de frequência
├── signals.py               # post_save AbonoChefia -> processa_abono_chefia_salvo
├── enums.py / exceptions.py # enums e exceções de domínio
├── utils.py                 # utilitários (cálculo/relatório)
├── menu.yaml / permissions.yaml
├── management/commands/     # abono_parcial_init_chefes, atualizar_dias_a_compensar,
│                            #   clean_opcoes_compensacao, popular_validadores,
│                            #   revalidar/remover_recessos_escolhidos, corrigir_auto_validacao
├── features/                # testes BDD (behave)
├── fixtures/ · static/ · templates/ · templatetags/ · migrations/ · tests/
```

---

## 3. Frequência / Registro de ponto (núcleo)

> ⚠️ **Modelo mental correto:** `Frequencia` é o **registro de marcação** (cada linha = uma batida). A **inconsistência NÃO é um campo armazenado** — é **computada** sobre as marcações por classmethods (`get_inconsistencias` / `get_detalhamento_inconsistencias`). As constantes `INCONSISTENCIA_*` e `SITUACAO_INCONSISTENCIA_*` são parâmetros dessa engine.

### 3.1 Model `Frequencia` (l.55) — a marcação
```python
vinculo  = FK('comum.Vinculo', CASCADE)        # de quem é a batida
horario  = DateTimeField(db_index=True)         # quando
maquina  = FK('ponto.Maquina', CASCADE)         # REP/terminal de origem
acao     = CharField(max_length=1)              # tipo (entrada/saída) — confirmar valores
online   = BooleanField(default=True)
ip       = GenericIPAddressField(null=True)
# Meta: unique_together = ('vinculo', 'horario'); permissions = (...)
```

### 3.2 Tipos de inconsistência (constantes de classe, l.56-64)
`INCONSISTENCIA_MENOR_JORNADA`, `INCONSISTENCIA_MAIOR_JORNADA`, `INCONSISTENCIA_FALTA`,
`INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS`, `INCONSISTENCIA_TRABALHO_FDS`,
`INCONSISTENCIA_NUMERO_IMPAR_REGISTROS`, `INCONSISTENCIA_NENHUM_INTERVALO`.

### 3.3 Situações de resolução (parâmetros da engine, l.162-185)
- **Por abono** (`SITUACAO_INCONSISTENCIA_*_ABONO`): `desconsiderar_abono`, `com_abono`, `sem_abono`, `com_ou_sem_abono` (lista `SITUACAO_INCONSISTENCIA_ABONO_CHOICES`).
- **Por débito** (`SITUACAO_INCONSISTENCIA_*_DEBITO`): `desconsiderar_debito`, `com_debito_total_compensado`, `com_debito_parte_compensado`, `com_debito_nada_compensado`, `com_debito_nao_compensado`, `com_debito_compensado_ou_nao` (lista `SITUACAO_INCONSISTENCIA_DEBITO_CHOICES`).

### 3.4 Engine e API (classmethods/staticmethods)
- **Entrada de marcação:** `insere_frequencia(vinculo, maquina, horario, online, ip)` — ponto de entrada (usado pelo `webservice.py` dos REP).
- **Engine de inconsistência:** `get_inconsistencias(vinculo, data_inicio, data_fim, contexto_compensacao) -> OrderedDict[date, list]`; `get_detalhamento_inconsistencias(...) ` (com `tolerancia_15min`); `existe_liberacao_inconsistencia(...)`, `tem_saida_antecipada(...)`, `pode_aplicar_inconsistencia(data, inconsistencia)`, `get_aplicacao_inconsistencia(inconsistencia)`.
- **Cálculo de tempos:** `get_tempo_entre_frequencias`, `get_intervalos_entre_frequencias`, `get_turnos_entre_frequencias`, `get_horario_extra_noturno`, `segundos_para_time`/`time_para_segundos`.
- **Consulta:** `get_frequencias_por_periodo`, `get_frequencias_por_data`.
- **Relatórios:** `relatorio_ponto_pessoa(_novo/_update)`, `relatorio_cargo_emprego`, `relatorio_frequencias_setor`, `relatorio_frequencias_prestador`, `relatorio_terceirizados`, `relatorio_noturno` (vários alimentam as tasks assíncronas — ver §12). O agregador de dia é a classe auxiliar `RelatorioPontoPessoaDiaInfo` (models.py:6623).

---

## 4. Abono / Homologação (núcleo)

Fluxo central de resolução de inconsistências: o **servidor** solicita justificativa e a **chefia imediata** decide (abona, trata como hora extra, autoriza FDS, etc.). Há ainda **revisão** da decisão da chefia.

### 4.1 `AbonoChefia` (l.2513) — decisão da chefia sobre um dia
```python
# acao_abono (estado da decisão) — choices ACAO_ABONO_CHOICES:
NAO_ABONADO=0, ABONADO_COM_COMPENSACAO=1, ABONADO=2,
HORA_EXTRA_NAO_JUSTIFICADA=3, HORA_EXTRA_JUSTIFICADA=4, HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA=7,
TRABALHO_FDS_NAO_PERMITIDO=5, TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA=6, TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA=8,
TRABALHO_REMOTO=9, NUMERO_IMPAR_REGISTROS_NAO_PERMITIDO=10, INTERVALO_NAO_PERMITIDO=11, INTERVALO_AUSENTE=12

vinculo_pessoa          = FK('comum.Vinculo')           # servidor
vinculo_chefe_imediato  = FK('comum.Vinculo')           # quem decidiu
data                    = DateFieldPlus()                # dia abonado
descricao, acao_abono, data_cadastro, ultima_atualizacao
solicitacao_abono_parcial = FK('SolicitacaoAbonoParcial', null=True)   # vínculo c/ abono parcial
ch_descontada           = PositiveIntegerField(null=True)  # carga horária a descontar (segundos)
# Métodos: pode_visualizar_avaliacao, pode_solicitar_revisao_avaliacao, pode_editar_avaliacao,
#   pode_solicitar_abono_parcial, pode_solicitar_revisao_abono_chefia,
#   processa_abono_chefia_salvo (handler do post_save — ver §12)
```

### 4.2 `SolicitacaoAbonoParcial` (l.3051) — pedido do servidor
```python
# motivo (MOTIVO_CHOICES):
MOTIVO_CONSULTA_SAUDE=1, MOTIVO_ESQUECIMENTO_FREQUENCIA=2, MOTIVO_HORARIO_INTERVALO=3,
MOTIVO_SIASS=4, MOTIVO_OUTROS=5, MOTIVO_CONSULTA_SAUDE_COMO_PACIENTE=11,
MOTIVO_CONSULTA_SAUDE_ACOMPANHAR_GRAVIDEZ=12
# tipo de abono: ABONO_COM_COMPENSACAO=1, ABONO_SEM_COMPENSACAO=2
# situação (SITUACAO_CHOICES): SITUACAO_PENDENTE=1, SITUACAO_AVALIADO=2

vinculo_pessoa, vinculo_chefe_imediato, data_solicitacao, data_aplicacao (dia c/ inconsistência),
motivo, descricao, arquivo (PrivateFileField), ch_solicitada (segundos), abono_solicitado,
situacao, acompanhamento_gravidez (FK) + qtd_consultas, chefes_data_aplicacao (M2M),
ch_solicitada_alteracoes_chefe_imediato
# Métodos: get_situacao_display_html, pode_editar(user), pode_avaliar(user)
```

### 4.3 Apoio
- **`SolicitacaoAbonoParcialGravidez` (l.3590)** — variante para gravidez de esposa/companheira (acompanhamento de consultas).
- **`SolicitacaoRevisaoAbonoChefia` (l.3647)** — pedido de revisão da decisão da chefia.
- **`Observacao` (l.2471)** — anotação livre por dia (`vinculo`, `data`, `descricao`).
- **`DocumentoAnexo` (l.2490)** — anexo por dia (`PrivateFileField`).

---

## 5. Motor de Estado

> ⚠️ Diferente de um processo linear: o "estado" do **dia de frequência** é uma **classificação computada** (consistente/inconsistente) que é **resolvida** por instrumentos paralelos (abono de chefia, abono parcial, compensação/débito, liberação). Os ciclos de vida com `situacao`/`acao_abono` armazenados estão em `AbonoChefia` e `SolicitacaoAbonoParcial`.

### 5.1 Dia de Frequência (estado computado → resolução)
```
Marcações (Frequencia) ── get_inconsistencias() ──► classificação do dia
   │                                                     │
   ▼ (sem problema)                                      ▼ (INCONSISTENCIA_*)
 CONSISTENTE                                        INCONSISTENTE
                                                         │ resolvido por (paralelos):
        ┌────────────────────────────────────────────────┼───────────────────────────────┐
        ▼                         ▼                        ▼                                ▼
 AbonoChefia (chefia)   SolicitacaoAbonoParcial    Compensação/Débito              Liberação (REP/setor)
 acao_abono=...         (servidor) -> AVALIADO      (HorarioCompensacao/Débito)     existe_liberacao_inconsistencia()
```
A engine (`get_detalhamento_inconsistencias`) considera os parâmetros `SITUACAO_INCONSISTENCIA_*_ABONO` e `SITUACAO_INCONSISTENCIA_*_DEBITO` (§3.3) para decidir se um dia inconsistente é exibido/contado como resolvido. **Não há transição armazenada no dia** — o estado é recalculado.

### 5.2 `AbonoChefia.acao_abono` (decisão da chefia)
```
NAO_ABONADO (0, default)  ── chefia decide ──►  { ABONADO(2) | ABONADO_COM_COMPENSACAO(1)
                                                  | HORA_EXTRA_JUSTIFICADA(4)/NAO_JUSTIFICADA(3)/PARA_COMPENSACAO(7)
                                                  | TRABALHO_FDS_* (5/6/8) | TRABALHO_REMOTO(9)
                                                  | NUMERO_IMPAR_*(10) | INTERVALO_*(11/12) }
                          ── pode ser revisado ──►  SolicitacaoRevisaoAbonoChefia
```
| Estado | Ação | Ator | Pré-condição (método) | Resultado |
|--------|------|------|------------------------|-----------|
| NAO_ABONADO | decidir abono | Chefe de Setor | `pode_editar_avaliacao(user)` | `acao_abono` = decisão; `post_save` → `processa_abono_chefia_salvo` (§12) |
| (qualquer) | solicitar revisão | Servidor | `pode_solicitar_revisao_avaliacao` / `pode_solicitar_revisao_abono_chefia` | cria `SolicitacaoRevisaoAbonoChefia` |
| (qualquer) | visualizar | Servidor/Auditor/GP | `pode_visualizar_avaliacao` | leitura |

### 5.3 `SolicitacaoAbonoParcial.situacao` (pedido do servidor)
```
(servidor cria) PENDENTE (1) ── chefia avalia ──► AVALIADO (2)  ── gera ──► AbonoChefia (vinculado)
```
| Estado | Ação | Ator | Pré-condição (método) | Resultado |
|--------|------|------|------------------------|-----------|
| (criação) | solicitar abono parcial | Servidor | `AbonoChefia.pode_solicitar_abono_parcial(...)` | `SolicitacaoAbonoParcial` PENDENTE |
| PENDENTE | editar | Servidor | `pode_editar(user)` | atualiza solicitação |
| PENDENTE | avaliar (deferir/indeferir) | Chefe de Setor | `pode_avaliar(user)` | situacao=AVALIADO; gera/atualiza `AbonoChefia` |

### 5.4 Matriz Ator × Ação (resumo)
| Ação | Servidor | Chefe de Setor | Coord. GP (campus/sist.) | Auditor |
|------|:---:|:---:|:---:|:---:|
| Registrar marcação (REP) | ✔ (bate ponto) | — | — | — |
| Solicitar abono parcial / anexar documento/observação | ✔ | — | — | — |
| Decidir abono de chefia (`acao_abono`) | — | ✔ | (a confirmar) | — |
| Avaliar solicitação de abono parcial | — | ✔ | (a confirmar) | — |
| Solicitar revisão do abono | ✔ | — | — | — |
| Liberar inconsistência / configurar | — | (a confirmar) | ✔ | — |
| Visualizar frequência/abonos | ✔ (própria) | ✔ (do setor) | ✔ | ✔ |

> Permissões reais via métodos `pode_*` de `AbonoChefia`/`SolicitacaoAbonoParcial` + papéis do `permissions.yaml` (§11). Onde marcado "(a confirmar)", verificar no código antes de afirmar.

---

## 6. Compensação / Recesso (referência)

> Subdomínio extenso e entrelaçado. O **motor de cálculo** vive em `compensacao.py`; os **modelos** em `models.py` (l.3814-5573).

### 6.1 Motor (`compensacao.py`, ≈3243 linhas)
- **`Contexto` (l.281)** — núcleo de cálculo de saldo/débito de um servidor num período (consolida marcações, abonos, afastamentos, compensações, débitos/saldos externos). Subclasses: `ContextoTotais`, `PontoPeriodo`, `PontoDia`.
- **`SituacaoDia` (l.1263)** + `SituacaoDiaOrigemDebito` (Enum) / `CompensacaoInfoDia` — situação de um dia para fins de compensação.
- **Filtros** (entrada de dados): `filter_relatorio_de_ponto`, `filter_compensacoes_informadas`, `filter_acompanhamentos`, `filter_debitos_externos`, `filter_saldos_externos`, `filter_afastamentos_parciais`, `filter_historico_funcao`.
- **Cálculos-chave:** `debito_pendente(servidor, ini, fim, data_limite_compensacao)`, `saldo_restante(servidor, ini, fim)`, `get_periodo_info(...)`, `get_periodo_processamento_info(...)`, `get_periodos_de_dias_a_atualizar(...)`, `formatar_segundos(...)`.

### 6.2 `HorarioCompensacao` (l.3814) — o Informe de Compensação
O servidor (ou chefia) **informa** que um débito foi compensado por um saldo:
```python
funcionario       = FK(...)                 # de quem é
data_aplicacao    = DateFieldPlus()          # dia com DÉBITO de carga horária
data_compensacao  = DateFieldPlus(null=True) # dia com SALDO (crédito)
ch_compensada     = TimeFieldPlus()          # quanto (HH:MM)
saldo_externo_compensacao = FK('ponto.SaldoExterno', null=True)  # se compensa contra saldo externo
chefe             = FK(...)                   # chefe imediato (set_chefe())
abono_na_data_compensacao / abono_na_data_aplicacao = FK('AbonoChefia', null=True)  # abonos ligados
observacoes
situacao          = IntegerField(choices, default=SITUACAO_VALIDO, editable=False)
# SITUACAO_VALIDO=1 ('Válido'), SITUACAO_INVALIDO=2 ('Invalidado/Sem Efeito')
# SALDO_MINIMO_EM_SEGUNDOS = 1; DEBITO_MINIMO_EM_SEGUNDOS = 1
# ordering = ('funcionario', '-data_aplicacao', '-data_compensacao')
# Métodos: is_compensacao_no_sabado, frequencia_duracao, set_chefe, ch_compensada_em_segundos,
#   opcoes_compensacao_envolvidas, save_observacao_no_ponto (gera Observacao automática nas duas datas),
#   pode_visualizar_detalhamento_compensacao
```
⚠️ **Acoplamento com abono:** `HorarioCompensacao` tem os handlers `inspecionar_informes_abono_chefia_salvo` / `inspecionar_informes_abono_chefia_excluido` — quando um `AbonoChefia` ligado é salvo/excluído, o informe pode ser **invalidado** (`situacao=SITUACAO_INVALIDO`). É o elo entre abono e compensação.

### 6.3 Recesso — configuração → escolha → compensação
**Configuração (`RecessoOpcao` l.4199):**
```python
responsavel = FK('rh.Servidor'); tipo (TIPO_PERMITE_ESCOLHA_LIVRE=1 / TIPO_OUTRO=2 / TIPO_CADASTRO_EXTERNO=3)
descricao; periodo_de_escolha_data_inicial/final
situacao (EM_FASE_DE_CADASTRO=1 → ABERTO_PARA_ESCOLHA=2 → FECHADO=3, editable=False)
qtde_max_dias_escolhidos; qtde_max_periodos_escolhidos
publico_alvo_campi (M2M); publico_alvo_servidores (M2M); origem GenericFK
```
Sub-config: `RecessoDia` (l.4723, dia de recesso/folga) · `RecessoPeriodo` (l.4751, período a compensar + `qtde_max_dias_a_escolher` + `dias_excluidos`) · `RecessoPeriodoDiaDefinido` (l.4883) · `RecessoPeriodoCompensacao` (l.4708, janela em que se pode compensar).

**Escolha do servidor (`RecessoOpcaoEscolhida` l.4907):**
```python
funcionario; recesso_opcao; data_escolha (auto)
validacao (VALIDACAO_AGUARDANDO=1 → AUTORIZADO=2 / NAO_AUTORIZADO=3 / NAO_AUTORIZADO_REMARCAR=4)
validador; motivo_nao_autorizacao; data_validacao; pode_validar_apos_prazo
dias_efetivos_a_compensar_cache (cache, editable=False)
```
Itens da escolha: `RecessoDiaEscolhido` (l.5464, FK→`RecessoDia`) · `RecessoPeriodoEscolhido` (l.5483, FK→`RecessoPeriodo`) · `RecessoPeriodoEscolhidoDiaIndividual` (l.5529).

**Materialização:** `RecessoCompensacao(HorarioCompensacao)` (l.5556) — herda de `HorarioCompensacao` e liga um `RecessoDiaEscolhido` a uma compensação efetiva (`dia_escolhido` FK). Ou seja: a escolha de recesso autorizada vira um informe de compensação.

### 6.4 Estados (resumo)
| Entidade | Estados | Transição |
|----------|---------|-----------|
| `HorarioCompensacao.situacao` | VÁLIDO ↔ INVALIDADO | invalidado quando abono ligado muda (handlers `inspecionar_informes_abono_chefia_*`) |
| `RecessoOpcao.situacao` | EM_FASE_DE_CADASTRO → ABERTO_PARA_ESCOLHA → FECHADO | gestão do recesso pelo responsável |
| `RecessoOpcaoEscolhida.validacao` | AGUARDANDO → AUTORIZADO / NÃO_AUTORIZADO / NÃO_AUTORIZADO_REMARCAR | validação pelo `validador` (com `pode_validar_apos_prazo`) |

Comandos de apoio (`management/commands/`): `atualizar_dias_a_compensar`, `clean_opcoes_compensacao`, `revalidar_recessos_escolhidos`, `remover_recessos_escolhidos`.

---

## 7. Afastamentos (referência)

```python
class TipoAfastamento (l.3711):  descricao, codigo
class Afastamento (l.3730):
    vinculo  = FK('comum.Vinculo')
    tipo     = FK(TipoAfastamento, null=True)
    data_ini = DateFieldPlus(db_index=True); data_fim = DateFieldPlus(null=True)
    descricao
    # Manager: AfastamentoManager
    # Métodos: buscar(cls, vinculo, ini, fim), buscar_afastamento_periodo(...),
    #          buscar_afastamentos_parciais(...)
```
Os afastamentos cobrem dias e influenciam a engine de inconsistência/compensação (um dia afastado não gera inconsistência de falta). Origem tipicamente **SIAPE** (importação via `rh`) — ver §10.

---

## 8. Saldo / Débito Externo (referência)

Ajustes de saldo originados **fora** do registro normal (com `validador` e `situacao` própria; `origem` é GenericFK para o objeto que gerou).

```python
class SaldoExterno (l.5574):
    servidor, data_inicio, data_fim, valor_saldo (segundos), detalhamento,
    origem_type/origem_id (GenericFK), validador (+observacoes),
    situacao (choices; default SITUACAO_EM_FASE_DEFINICAO)
class DebitoExternoCadastro (l.6044):
    servidor, total_debito (segundos), detalhamento, origem GenericFK,
    validador (+observacoes), situacao (default SITUACAO_EM_FASE_DEFINICAO)
class DebitoExterno (l.6521):           # dias do cadastro
    cadastro = FK(DebitoExternoCadastro, related_name='debitos_externos_dias')
    data_debito, valor_debito (segundos), observacoes
```
Entram no cálculo da compensação via `filter_saldos_externos`/`filter_debitos_externos` (§6.1). Menu: *Compensação de Horários → Saldos/Débitos Externos*; papel **Cadastrador de Saldos e Débitos Externos**.

---

## 9. REP / Terminais & Webservice (referência)

> Como as **marcações entram** no SUAP. O app `terminais` é o dono dos dispositivos físicos; o `ponto` recebe as batidas e modela a máquina/log/liberação.

### 9.1 Modelos
```python
class Maquina (l.2188):     # o terminal
    descricao, ip (unique), porta_servico, ativo,
    cliente_ponto / cliente_chaves / cliente_refeitorio / cliente_cadastro_impressao_digital (flags de função),
    uo (Campus), predios (M2M), usuarios (M2M), versao_terminal (FK), ultimo_log
class MaquinaLog (l.2257):  # log de operações
    maquina, status (STATUS_MAQUINA_LOG_CHOICES: SUCESSO/ERRO), operacao, mensagem, horario
class Liberacao (l.2288):   # libera inconsistência por UO/período
    uo, data_inicio, data_fim, descricao, tipo (TipoLiberacao), ch_maxima_exigida
class VersaoTerminal (l.2181): numero (versão)
```

### 9.2 Entrada de marcações (`webservice.py`, XML-RPC)
- **`registrar_frequencias_offline(registros)`** (exposto) — identifica a `Maquina` por **IP** (`cliente_ponto=True, ativo=True`); se não achar → erro "Máquina com ip X não tem permissão". Parseia `registros` no formato `username;YYYY-MM-DD HH:MM:SS|...`, ignora já existentes e chama **`Frequencia.insere_frequencia(vinculo, maquina, horario, online=False)`** para cada nova. Erros vão para `MaquinaLog`.
- Ou seja: **terminal REP → webservice → `Frequencia.insere_frequencia` → registro `Frequencia`** (que depois a engine de inconsistência avalia).

---

## 10. Mapa de Influência Cross-Módulo ⭐

> Como o `ponto` e os módulos vizinhos se influenciam. Cada linha cita o **ponto de integração concreto** verificável no código.

### 10.1 Módulos dos quais o `ponto` DEPENDE
| Módulo | Ponto de integração (evidência) | Como influencia o ponto |
|--------|----------------------------------|--------------------------|
| **`comum`** | `Frequencia/Abono*/Observacao/...` FK → **`comum.Vinculo`** (7 FKs); `Configuracao`, `PrestadorServico`, `Predio`, `User`; `comum.utils.tl`/`get_setor`/`get_uo`; `comum.webservice` | **`Vinculo` é a identidade central** — toda marcação/abono pertence a um vínculo. Configurações globais e prestadores de serviço definem regras/escopo. |
| **`rh`** | `from rh.models import Servidor, Setor, Funcao, CargoEmprego, UnidadeOrganizacional, ServidorFuncaoHistorico`; **`from rh.utils import periodos_estah_no_pgd1_pgd2`** | Servidor/Setor/UO definem hierarquia e chefia; jornada/cargo afetam a inconsistência; **`periodos_estah_no_pgd1_pgd2` injeta regra de PGD dentro do cálculo do ponto** (isenção/teletrabalho). Afastamentos SIAPE entram via `rh`. |
| **`pit_rit`** (bidirecional) | `ponto/models.py` importa `from pit_rit.views import frequencia_docente` / `from pit_rit.utils import PontoDocente` | Ponto **docente** (PIT/RIT) reusa/ajusta o relatório de frequência para docentes. |

### 10.2 Módulos que DEPENDEM do `ponto` (dependentes reversos)
| Módulo | Importa de `ponto` | Como é influenciado / relação |
|--------|--------------------|-------------------------------|
| **`terminais`** | `Frequencia`, `Maquina`, `MaquinaLog` | Gerencia os **REP físicos** que alimentam a frequência (coleta/sincronização de marcações). |
| **`pgd`** / **`pgd2`** | `compensacao.Contexto`, `Frequencia`, `RecessoOpcaoEscolhida`, `RecessoPeriodoCompensacao`, `SaldoExterno` | **Teletrabalho** consome o motor de ponto/compensação e o saldo para apurar cumprimento; combinado com `periodos_estah_no_pgd1_pgd2` (§10.1) há **influência mútua** ponto↔PGD. |
| **`pit_rit`** | `AbonoChefia`, `Frequencia`, `compensacao.Contexto`, `forms.FrequenciaDocenteFormFactory` | Apuração de ponto/abono **docente**. |
| **`ae`** | `Maquina`, `MaquinaLog`, `VersaoTerminal` | Usa terminais (ex.: refeitório) modelados no ponto. |
| **`acompanhamentofuncional`** | `Afastamento`, `TipoAfastamento` | Lê afastamentos para acompanhamento funcional. |
| **`auditoria`** | `Liberacao`, `TipoLiberacao` | Audita liberações de inconsistência. |

> Regra de ouro ao mexer no ponto: mudanças em `Frequencia`, `compensacao.Contexto`, `RecessoOpcaoEscolhida`/`SaldoExterno` ou nos modelos de terminal **propagam** para `terminais`, `pgd/pgd2`, `pit_rit`, `ae` — verifique esses consumidores. (a confirmar no código a extensão exata em cada consumidor.)

---

## 11. RBAC — Papéis e Permissões (`permissions.yaml`)

14 papéis (com `app_manager`):

| Papel | App Manager | Foco no ponto |
|-------|-------------|----------------|
| **Servidor** | rh | Vê a própria frequência; solicita abono parcial; anexa documento/observação. |
| **Chefe de Setor** | rh | Abona/decide (`AbonoChefia.acao_abono`), avalia solicitações de abono do setor. |
| **Coordenador de Gestão de Pessoas** (+ **Sistêmico**) | rh | Gestão de ponto no campus / sistêmica (liberações, configurações, relatórios). |
| **Auditor** | auditoria | Auditoria (liberações, leitura). |
| **Aposentado** | rh | Acesso restrito (histórico). |
| **Coordenador PRONATEC** (+ **Sistêmico**) | comum | Frequência no contexto PRONATEC. |
| **Coordenador de TI de campus** / **sistêmico** | comum | Gestão de máquinas/terminais. |
| **Gerenciador de Frequência de Terceirizados** | (—) | Frequência de terceirizados. |
| **Gerenciador de Prestador de Serviço** | comum | Frequência de prestadores. |
| **Prestador de Serviço** | comum | Registra/vê a própria frequência. |
| **Visualizador de Informações de Servidores** | rh | Leitura. |
| **Cadastrador de Saldos e Débitos Externos** | ponto | Cadastra `SaldoExterno`/`DebitoExterno`. |

> Gating fino vem dos métodos `pode_*` em `AbonoChefia`/`SolicitacaoAbonoParcial` (§4-5) e das permissões custom em `Frequencia.Meta.permissions`. Usar sempre esses, nunca checagem ad-hoc.

---

## 12. Tarefas Assíncronas

- **Tasks (`tasks.py`, djtools `@task`):** `relatorio_frequencia_cargo_emprego(cargo_emprego, faixa_0, faixa_1, request)` e `relatorio_frequencia_setor(servidores, faixa_0, faixa_1, request)` — geram relatórios pesados de frequência em background (`task.finalize(...)` com arquivo).
- **Signals (`signals.py`, registrado em `apps.ready()`):** `post_save` em **`AbonoChefia`** → `AbonoChefia.processa_abono_chefia_salvo` — ao salvar um abono de chefia, dispara o processamento (recalcular efeito do abono no dia/saldo). ⚠️ Qualquer alteração em `AbonoChefia` passa por esse handler.
- (Sem `beat.py` no app; agendamentos, se houver, ficam fora do app — a confirmar.)

---

## 13. Regras de Negócio Críticas

- **Tipos de inconsistência** (com descrição de usuário, l.70-80): `MENOR_JORNADA` = "Tempo inferior ao expediente"; `MAIOR_JORNADA` = "Tempo excedente ao expediente"; `TEMPO_MAIOR_DEZ_HORAS` = "Tempo de trabalho superior a 10h"; `TRABALHO_FDS`; `NUMERO_IMPAR_REGISTROS`; `NENHUM_INTERVALO`; (turno ininterrupto > 6h15min — comentado/condicional, a confirmar).
- **Tolerância:** a engine `get_detalhamento_inconsistencias(..., tolerancia_15min=True)` aplica tolerância de 15 min.
- **Unidades:** carga horária e saldos/débitos são em **segundos** (`ch_solicitada`, `ch_descontada`, `valor_saldo`, `valor_debito`, `total_debito`).
- **Resolução de inconsistência:** por abono (chefia/parcial), por compensação/débito, ou por liberação (`Liberacao.ch_maxima_exigida` por UO/período). Ver §5/§6.
- **Abono com/sem compensação:** `ABONO_COM_COMPENSACAO` desconta carga horária; `ABONO_SEM_COMPENSACAO` apenas justifica.
- **Compensação/banco de horas e recesso:** apurados por `compensacao.Contexto` (`debito_pendente`, `saldo_restante`); recesso tem regras próprias de escolha/compensação (§6).
- **Marcação:** `unique_together(vinculo, horario)` — não duplica batida; webservice ignora já existentes.

---

## 14. FAQ de Usuários ⭐

Respostas ancoradas no comportamento real (referência entre parênteses):

- **"Por que minha frequência aparece inconsistente?"** — A inconsistência é **calculada** sobre suas marcações do dia (§3). Tipos: tempo inferior/excedente ao expediente, >10h, trabalho em FDS, nº ímpar de registros, sem intervalo (§3.2/§13). Não é um "erro de cadastro" — é a jornada do dia que não fechou.
- **"Como justifico/abono um dia inconsistente?"** — Você (servidor) abre uma **Solicitação de Abono Parcial** informando motivo e carga horária; a **chefia imediata** avalia (PENDENTE→AVALIADO) e isso gera o **Abono de Chefia** (§4-5). A chefia também pode abonar diretamente (`acao_abono`).
- **"Minha marcação não apareceu no sistema."** — As batidas vêm do **terminal REP** via webservice (§9). Verifique: o terminal está **ativo** e marcado como `cliente_ponto`? O **IP** dele tem permissão (`Maquina`)? Erros ficam em **`MaquinaLog`**. Marcação duplicada (mesmo `vinculo`+`horario`) é ignorada.
- **"Como compenso horas? O que é débito?"** — Débito/crédito são apurados pelo motor de **compensação** (§6, `compensacao.Contexto` → `debito_pendente`/`saldo_restante`). Há ainda **saldos/débitos externos** (§8). Tudo em **segundos**. Abono "com compensação" desconta carga horária; "sem compensação" só justifica.
- **"Estou em teletrabalho (PGD), preciso bater ponto?"** — A regra de PGD é injetada no cálculo do ponto via `rh.utils.periodos_estah_no_pgd1_pgd2` e os módulos `pgd`/`pgd2` consomem o motor de ponto (§10). A apuração considera o período de PGD.
- **"Como funciona o recesso?"** — Configuração + escolha do servidor na família `Recesso*` (§6), com regras próprias de compensação. Menu: *Compensação de Horários*.
- **"Sou chefe — onde abono o setor?"** — Menu *Ponto → Abonos → Abonos de chefia*; permissões por papel **Chefe de Setor** + métodos `pode_*` (§5/§11).

---

## 15. Como Atuar como Especialista

1. **Identifique o contexto** pelo vocabulário: "frequência", "batida/marcação", "inconsistência", "abono (de chefia/parcial)", "homologar", "compensação/banco de horas", "recesso", "débito/saldo externo", "REP/terminal/máquina", "liberação", "afastamento" → este módulo.
2. **Leia antes de sugerir**: `ponto/models.py` (núcleo `Frequencia`), `ponto/compensacao.py` (cálculo), `ponto/webservice.py` (entrada de marcações), `ponto/forms.py`/`views.py` para fluxos.
3. **Inconsistência é COMPUTADA, não armazenada** (§3): para "consertar" um dia, atue nos instrumentos de resolução (abono/compensação/liberação), não num "campo de status".
4. **Respeite o motor de estado (§5)**: `AbonoChefia.acao_abono` e `SolicitacaoAbonoParcial.situacao` são os ciclos reais; ao salvar `AbonoChefia`, o signal `processa_abono_chefia_salvo` recalcula efeitos (§12).
5. **Unidades em segundos** (carga horária, saldos, débitos). Não confunda com minutos/horas.
6. **Pense no cross-módulo (§10)** antes de alterar `Frequencia`/`compensacao.Contexto`/`Recesso*`/`SaldoExterno` ou os modelos de terminal: há consumidores em `terminais`, `pgd/pgd2`, `pit_rit`, `ae`, `acompanhamentofuncional`, `auditoria`.
7. **Permissões pelos métodos `pode_*`** e papéis do `permissions.yaml` (§11), nunca ad-hoc.
8. **Profundidade escalonada:** Compensação/Recesso (§6) está documentado em nível de modelos/campos/estados; para a **lógica fina de cálculo** (`compensacao.Contexto`/`SituacaoDia`, ≈3.2k linhas) e detalhes de Saldo/Débito, **leia o código** (`compensacao.py`, `models.py` 3814-6622); marque "(a confirmar)" quando não tiver certeza.

$ARGUMENTS
