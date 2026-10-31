# Aval do Responsável LAI nos datasets — Design

**Módulo:** `dados_abertos`
**Data:** 2026-07-21
**Branch:** `dados-abertos-responsavel-lai`

## 1. Contexto e objetivo

No IFRN existe o papel do **Responsável pelo Monitoramento da Lei de Acesso à Informação (LAI)**, encarregado de decidir quais informações podem ou não ser disponibilizadas nos datasets enviados ao CKAN. Hoje o módulo `dados_abertos` **não trata esse papel**: qualquer staff com permissão sincroniza um dataset ao CKAN (`action_sync_ckan` / botão `sync` no admin de `BaseDados`), sem nenhum aval prévio.

O objetivo é inserir, **antes do fechamento/liberação das informações que compõem cada dataset**, uma etapa de deliberação do Responsável LAI: ele analisa o conteúdo de cada dataset e informa quando está adequado a ser liberado. Sem o aval, o dataset não pode ser enviado ao CKAN.

## 2. Decisões (definidas no brainstorming)

| Tema | Decisão |
|------|---------|
| Unidade do aval | **Por dataset em cada PDA** — a deliberação mora na relação `PDABaseDados`. A mesma base em outro PDA (ou em revisão) exige novo aval. |
| Forma do passo | **Status de liberação por dataset**: `PENDENTE → EM_ANALISE → LIBERADO / DEVOLVIDO`, com tela própria do LAI. |
| Conteúdo da deliberação | **Decisão + parecer + auditoria** (Liberar/Devolver, parecer obrigatório ao devolver, quem/quando/IP). Devolvido volta ao gestor, que corrige e reenvia. |
| Disparo da análise | **Automático por etapa do PDA** — ao PDA atingir uma etapa marcada, todos os datasets do PDA entram em `EM_ANALISE`. |
| Gate no sync CKAN | **Só sincroniza base 100% liberada**: a base só pode ir ao CKAN se tiver ≥1 relação `PDABaseDados` e **todas** estiverem `LIBERADO`. Qualquer relação em `PENDENTE`, `EM_ANALISE` ou `DEVOLVIDO` bloqueia (ver §5.4). |
| Edição pós-aval | **Invalida**: editar a base ou seus recursos após `LIBERADO` reverte para `EM_ANALISE` e registra o motivo. |

## 3. Componentes

1. **Grupo e permissão** (`permissions.yaml`).
2. **Enum `SituacaoLAI`** (`enums.py`).
3. **Campo `situacao_lai`** em `PDABaseDados`.
4. **Model `DeliberacaoLAI`** (histórico/auditoria).
5. **Flag `dispara_analise_lai`** em `Etapa` + gancho de disparo em `PlanoDadosAbertos.atualizar_etapa_atual()`.
6. **Tela do LAI** (view `deliberacao_lai` + template) e ação "Reenviar ao LAI".
7. **Gate no sync CKAN** (admin de `BaseDados`).
8. **Invalidação por edição** (hook em `BaseDados`/`RecursoDados`).
9. **Migração** e **menu**.

## 4. Modelo de dados

### 4.1 `enums.py` — `SituacaoLAI`

```python
class SituacaoLAI:
    PENDENTE = 1
    EM_ANALISE = 2
    LIBERADO = 3
    DEVOLVIDO = 4

    LABELS = {
        PENDENTE: 'Pendente',
        EM_ANALISE: 'Em análise do LAI',
        LIBERADO: 'Liberado',
        DEVOLVIDO: 'Devolvido para ajustes',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())
```

### 4.2 `PDABaseDados.situacao_lai`

```python
situacao_lai = models.IntegerField(
    _('Situação LAI'),
    choices=SituacaoLAI.get_choices(),
    default=SituacaoLAI.PENDENTE,
    help_text=_('Situação da deliberação do Responsável LAI para esta base neste PDA.'),
)
```

- Default `PENDENTE`. Migração: relações existentes ficam `PENDENTE` (nenhuma foi avaliada).
- Não é editável livremente no admin — muda apenas via as transições definidas em §5.

### 4.3 Model `DeliberacaoLAI` (`models/deliberacao_lai.py`)

```python
class DeliberacaoLAI(ModelPlus):
    DECISAO_LIBERADO = SituacaoLAI.LIBERADO
    DECISAO_DEVOLVIDO = SituacaoLAI.DEVOLVIDO
    DECISAO_CHOICES = [(DECISAO_LIBERADO, 'Liberado'), (DECISAO_DEVOLVIDO, 'Devolvido para ajustes')]

    pda_base_dados = models.ForeignKeyPlus('dados_abertos.PDABaseDados', on_delete=models.CASCADE, related_name='deliberacoes_lai')
    decisao = models.IntegerField(choices=DECISAO_CHOICES)
    parecer = models.TextField(blank=True, help_text='Parecer do Responsável LAI. Obrigatório na devolução.')
    deliberado_por = models.ForeignKeyPlus('comum.Vinculo', on_delete=models.SET_NULL, null=True)
    data_deliberacao = models.DateTimeFieldPlus(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Deliberação LAI'
        verbose_name_plural = 'Deliberações LAI'
        ordering = ('-data_deliberacao',)
        permissions = [('deliberar_lai', 'Pode deliberar sobre a liberação LAI de datasets')]
```

- Cada decisão do LAI gera **um registro** (histórico auditável). `PDABaseDados.situacao_lai` reflete a última decisão.
- A permissão customizada `deliberar_lai` é declarada aqui (via `Meta.permissions`).
- `clean()`/validação: se `decisao == DEVOLVIDO`, `parecer` é obrigatório.

## 5. Regras de negócio (máquina de estados)

```
PENDENTE ──(PDA atinge etapa com dispara_analise_lai)──▶ EM_ANALISE
EM_ANALISE ──(LAI delibera: Liberar)──▶ LIBERADO
EM_ANALISE ──(LAI delibera: Devolver + parecer)──▶ DEVOLVIDO
DEVOLVIDO ──(gestor: "Reenviar ao LAI")──▶ EM_ANALISE
LIBERADO ──(edição do conteúdo do dataset)──▶ EM_ANALISE   (invalidação)
```

### 5.1 Disparo automático por etapa

- `Etapa` ganha `dispara_analise_lai = BooleanField(default=False)`. O gestor marca no admin **qual** etapa dispara (normalmente a etapa anterior ao fechamento/publicação).
- Em `PlanoDadosAbertos.atualizar_etapa_atual()`, **após** definir `etapa_atual`, se a etapa atual tem `dispara_analise_lai=True`, executar um bulk update idempotente:
  ```python
  self.bases_relacionadas.filter(situacao_lai=SituacaoLAI.PENDENTE).update(situacao_lai=SituacaoLAI.EM_ANALISE)
  ```
  Só afeta `PENDENTE` → idempotente (reexecuções não mexem em LIBERADO/DEVOLVIDO/EM_ANALISE).
- Extração em helper (`_disparar_analise_lai_se_necessario()`) para manter `atualizar_etapa_atual` com complexidade ≤ 10.

### 5.2 Deliberação (tela do LAI)

- Lista os `PDABaseDados` em `EM_ANALISE` (agrupados por PDA) visíveis ao grupo LAI.
- Para cada dataset: link/visão do conteúdo (base + recursos + metadados) e formulário: decisão (Liberar/Devolver) + parecer.
- Ao submeter: cria `DeliberacaoLAI` (com IP/user_agent), atualiza `situacao_lai`. `parecer` obrigatório em Devolver.

### 5.3 Reenvio pelo gestor

- Ação "Reenviar ao LAI" (no admin de `PDABaseDados` e/ou na visão do PDA) disponível para o Gestor quando `situacao_lai == DEVOLVIDO`: volta para `EM_ANALISE`. (Não cria `DeliberacaoLAI`; é ação do gestor, não do LAI.)

### 5.4 Gate no envio ao CKAN

Regra: **uma `BaseDados` só pode ser sincronizada se `pode_liberar_ckan(base)` for verdadeiro**, onde:

```
pode_liberar_ckan(base) =
    existe ao menos uma PDABaseDados(base)
    E todas as PDABaseDados(base) têm situacao_lai == LIBERADO
```

- Qualquer relação em `PENDENTE`, `EM_ANALISE` ou `DEVOLVIDO` **bloqueia** o sync — só sincroniza a base cujo aval LAI esteja liberado em todos os PDAs em que ela aparece. Base sem nenhuma relação `PDABaseDados` também não sincroniza (nunca passou pelo LAI).
- Aplicado em `sync_dataset_view`, `action_sync_ckan` e `action_sync_resources_ckan` (bloquear também os recursos, já que representam o conteúdo publicado). Mensagem clara indicando o motivo (pendente / em análise / devolvida / sem vínculo a PDA).

### 5.5 Invalidação por edição pós-liberação

- Em `BaseDados.save()` e `RecursoDados.save()` (edição, não criação): quando houver **mudança de conteúdo** e a base tiver relações `LIBERADO`, reverter essas relações `LIBERADO → EM_ANALISE` e gravar `PDABaseDados.motivo_reabertura` (ex.: "Reaberto por edição do conteúdo em DD/MM/AAAA") + `logger.info`.
- A criação de `DeliberacaoLAI` permanece **exclusiva do LAI** — a reabertura por edição é ação de sistema e NÃO gera registro de deliberação (não polui o histórico do LAI).
- "Mudança de conteúdo" = alteração em campos relevantes, comparados no `save` (evita disparar em gravação trivial): da base — `titulo`, `notas`, `tags`, `tema`, `licenca`, `organizacao`; do recurso — `arquivo`, `url`, `formato`, `nome`, `descricao`.
- `PDABaseDados.motivo_reabertura = models.CharFieldPlus(max_length=255, blank=True)` — exibido na tela do LAI para contextualizar por que o dataset voltou à análise.

## 6. Permissões e segurança

- **Grupo "Responsável LAI"** em `permissions.yaml`:
  ```yaml
  Responsável LAI:
    app_manager: dados_abertos
    dados_abertos:
      deliberacaolai:
        - deliberar_lai
        - view_deliberacaolai
        - add_deliberacaolai
      pdabasedados:
        - view_pdabasedados
      basedados:
        - view_basedados
      recursodados:
        - view_recursodados
      planodadosabertos:
        - view_planodadosabertos
  ```
  (Sem `change_*` de conteúdo — o LAI só delibera e visualiza.)
- A tela `deliberacao_lai` exige `dados_abertos.deliberar_lai`.
- O botão/ação "Reenviar ao LAI" exige permissão de Gestor (`change_pdabasedados`), não do LAI.
- Auditoria: `DeliberacaoLAI` grava `deliberado_por`, `data_deliberacao`, `ip`, `user_agent`.

## 7. UI

- **Tela do LAI** (`/dados_abertos/deliberacao_lai/`): padrão da `matriz_priorizacao` (view + template `dados_abertos/deliberacao_lai.html`). Filtro por PDA; lista datasets `EM_ANALISE`; form de decisão/parecer.
- **Menu** (`menu.yaml`): nova entrada `Dados Abertos::Deliberação LAI` com `permissions_required: [dados_abertos.deliberar_lai]`.
- **Admin**: `PDABaseDadosAdmin` (ou inline) exibe `situacao_lai` (badge) e histórico de `DeliberacaoLAI` (inline read-only); ação "Reenviar ao LAI" para devolvidos. `EtapaAdmin` expõe `dispara_analise_lai`. `BaseDadosAdmin` mostra o status LAI consolidado e a mensagem do gate no sync.

## 8. Migração

- `makemigrations dados_abertos` (nunca escrever à mão): novo model `DeliberacaoLAI` (+ permissão `deliberar_lai`), campo `PDABaseDados.situacao_lai` (default PENDENTE), campo `Etapa.dispara_analise_lai` (default False), opcional `PDABaseDados.motivo_reabertura`.
- `sync_permissions` cria o grupo "Responsável LAI" a partir do `permissions.yaml`.

## 9. Fora de escopo (YAGNI)

- Deliberação recurso-a-recurso (foi descartada na escolha "Decisão + parecer").
- Assinatura criptográfica da deliberação (basta auditoria quem/quando/IP; pode ser adicionada depois se exigido).
- Notificações por e-mail ao LAI/gestor nas transições (pode ser follow-up).
- Versionamento de snapshot do conteúdo aprovado (a invalidação por edição já cobre a integridade mínima).

## 10. Notas de decisão

- **Gate de sync**: confirmado que **`PENDENTE` também bloqueia** — só sincroniza a base cujas relações `PDABaseDados` estejam **todas** `LIBERADO` (§5.4).
