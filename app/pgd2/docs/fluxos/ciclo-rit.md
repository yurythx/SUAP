# Fluxo: Ciclo RIT (Relatório Individual de Trabalho)

> Servidor elabora o relatório de execução do PIT, registra entregas realizadas e distribuição de horas, submete para aprovação e homologação do chefe.

- **Ator(es):** Servidor, Chefe imediato — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** Servidor acessa "Meu PGD" → PIT homologado → elaborar RIT
- **Pré-condições:** PIT homologado, RIT ainda não elaborado para o período
- **Pós-condições:** RIT homologado, distribuição de horas registrada
- **Depende de:** [Ciclo PIT](ciclo-pit.md) (RIT só pode ser elaborado com PIT `HOMOLOGADO`; é `situacao_rit` no mesmo `PlanoIndividualTrabalho`)
- **Habilita:** [Ciclo PES](ciclo-pes.md) (RIT homologado libera a avaliação da execução do PES) e [Envio de dados à API PGD](envio-api-pgd.md) (avaliação e registros de execução do RIT compõem o payload do plano)
- **Entrada no código:** `views.visualizar_rit`, `views.cadastrar_entrega_rit`, `views.aprovar_rit`, `views.homologar_rit`

## Sequência

```mermaid
sequenceDiagram
    participant U as Servidor
    participant V as Views
    participant M as Models
    participant DB as PostgreSQL
    U->>V: GET /pgd2/visualizar_rit/<pit_id>/
    V->>M: carrega PIT + RIT
    M->>DB: SELECT
    DB-->>M: dados
    M-->>V: RIT em branco
    V-->>U: tela de elaboração
    U->>V: cadastra entregas realizadas
    V->>M: cria/edita RelatorioIndividualTrabalhoEntregas
    M->>DB: INSERT/UPDATE
    U->>V: distribui horas (servidor_pgd_horas)
    V->>M: cria RelatorioIndividualTrabalhoDistribuicaoHoras
    M->>DB: INSERT
    U->>V: solicitar_aprovacao_homologacao_rit
    V->>M: situacao="aguardando_aprovacao"
    M->>DB: UPDATE
    Note over U,V: Chefe avalia
    U->>V: POST aprovar_rit
    V->>M: situacao="aprovado"
    U->>V: POST homologar_rit
    V->>M: situacao="homologado"
    V-->>U: redirect
```

## Observações

- Distribuição de horas é feita por tipo de atividade (presencial/teletrabalho)
- RIT pode ser reaberto após homologação (somente por quem tem permissão)
- Questionário opcional pode ser preenchido junto ao RIT
- ⚠️ REVISAR: distribuição de horas tem validação contra carga horária do servidor no `rh`; confirmar se consulta `ponto` para frequência real

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
