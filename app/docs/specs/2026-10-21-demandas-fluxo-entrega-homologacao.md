# Spec — Homologação da demanda pela Entrega

- **Data:** 2026-10-21
- **Status:** Aprovada (conversa com o mantenedor do módulo)
- **Módulo:** `demandas/`

## Problema

A expansão das entregas criou um segundo fluxo de homologação ao lado do antigo, e os dois não
conversam:

| | Fluxo antigo (etapa) | Fluxo das entregas |
|---|---|---|
| Entrada | Analista muda a etapa para "Em homologação" | Analista cadastra uma Entrega; a etapa não muda |
| Ambiente, URL e senha | Na `Demanda` | Na `Entrega` (campos duplicados) |
| Quem aprova | Só demandante | Qualquer um com `atende_demanda` ou `change_demanda`, inclusive quem entregou |
| Trava de consolidação com revisão pendente | Sim | Não |
| Reprovação | Volta para "Em negociação" | Volta para "Em desenvolvimento" |
| Prazo | Previsão da etapa | `prazo_feedback` + expiração automática sem efeito na demanda |

O sintoma visível: a demanda aparece "Em desenvolvimento" na régua com o selo "Aguardando
homologação" ao lado, porque a entrega pendente não move a etapa. Aprovar uma entrega com a
demanda em desenvolvimento também não tem efeito nenhum.

## Decisão

**A etapa "Em homologação" significa: existe uma entrega aguardando o demandante.** A etapa
deixa de ser editada à mão nesse trecho do fluxo e passa a ser consequência da entrega.

### Transições

```text
Em desenvolvimento ──(entrega cadastrada)──────────────────────▶ Em homologação
Em homologação ────(entrega reprovada)─────────────────────────▶ Em desenvolvimento
Em homologação ────(entrega cancelada pela equipe)─────────────▶ Em desenvolvimento
Em homologação ────(aprovada, ainda há especificação pendente)─▶ Em desenvolvimento
Em homologação ────(aprovada, escopo coberto)──────────────────▶ Homologada
```

- A entrega só pode ser cadastrada com a demanda **Em desenvolvimento** (ou "Em homologação"
  sem entrega pendente, caso legado). Continua valendo uma entrega pendente por vez.
- Ao cadastrar, a demanda vai para "Em homologação" com a **previsão da etapa = prazo para o
  demandante responder**, que passa a ser obrigatório. Há um relógio só.
- "Em homologação" sai das transições manuais a partir de "Em desenvolvimento" e "Suspensa";
  "Homologada" e "Em desenvolvimento" saem das transições manuais a partir de "Em homologação".
  Continuam manuais as saídas "Em negociação", "Suspensa" e "Cancelada": elas cancelam a
  entrega pendente.
- Ao voltar para "Em desenvolvimento", a previsão da etapa é a última previsão de
  desenvolvimento registrada.

### Cobertura do escopo

O escopo está coberto quando **toda especificação da consolidação está vinculada a alguma
entrega aprovada**. A cobertura é uma consulta, sem estado novo:

```python
Especificacao.objects.filter(dod__demanda=demanda).exclude(entregas__status=StatusEntrega.APROVADA)
```

- Demanda **com** especificações: a cobertura decide o destino da aprovação.
- Demanda **sem** especificações (consolidação antiga ou correção pequena): a entrega traz
  "Conclui a demanda?" (`Entrega.conclui_demanda`); aprovada com a marca, vai para
  "Homologada"; sem a marca, volta para desenvolvimento.
- A reprovação é da entrega inteira, não por especificação.

### Quem valida

- Aprovam ou reprovam: **os demandantes da demanda e o demandante responsável da área**.
  Quem cadastrou a entrega nunca a valida. Interessados acompanham e comentam.
- A aprovação é recusada enquanto houver revisão de especificação pendente na consolidação
  (a mesma trava do fluxo antigo).
- A equipe (`atende_demanda`) cadastra e cancela entregas.

### Prazo vencido

A entrega com prazo vencido **só é sinalizada** ("Entrega vencida" e atraso da etapa). Não há
mais expiração automática: o comando `expirar_entregas_vencidas` e seu agendamento saem. O
status `EXPIRADA` permanece apenas para os registros históricos.

### Etapa "Homologada"

Permanece. A aprovação que cobre o escopo leva a "Homologada", que cria o merge request a
partir da branch da entrega (ou da demanda), como o fluxo antigo já fazia. Daí a equipe leva a
"Em implantação" e "Concluída".

### Dados de homologação ficam só na Entrega

- `Demanda.ambiente_homologacao`, `Demanda.url_validacao` e `Demanda.senha_homologacao` saem
  do model. Ambiente, URL e senha vivem na entrega. As **colunas continuam no banco**, sem uso
  pelo Django (só a constraint de FK cai): preservam o histórico das demandas encerradas e
  não quebram os slaves que ainda rodam o código antigo durante o deploy. Dropá-las é decisão
  de outra release.
- A limpeza de ambientes (`remover_ambientes_homolog_expirados`) passa a achar a demanda pela
  entrega. Um ambiente que só estava ligado à demanda deixa de ser destruído quando ela é
  encerrada e espera a própria data de expiração.
- `Demanda.ambiente_homologacao_atual` devolve o ambiente da entrega pendente ou, sem ela, o da
  entrega mais recente que tenha ambiente; é o que a aba Entregas e a API
  (`/api/demandas/{id}/ambiente-homologacao/`) usam.
- Migração de dados: cada demanda "Em homologação" sem entrega pendente ganha uma entrega
  pendente com o ambiente, a URL e a senha que estavam na demanda, cadastrada por quem levou
  a demanda à etapa (ou o primeiro desenvolvedor/analista).
- A aba "Homologação" e as rotas `homologacao/<id>/aprovar|reprovar/` saem: aprovar e reprovar
  acontecem só na aba "Entregas".

## Fora do escopo (próximos passos)

- **Especificação revisada depois de aprovada.** Hoje a revisão aprovada altera a
  especificação no lugar e o vínculo com a entrega aprovada continua contando como cobertura.
  Tratar exige registrar quando a especificação mudou.
- **Validação após implantar** (correção pequena validada em produção, sem ambiente) e
  **entregas que não são código** (documento, configuração): seguem o mesmo fluxo por ora.
- **"Em desenvolvimento" → "Em implantação" direto** continua existindo e pula a validação.
