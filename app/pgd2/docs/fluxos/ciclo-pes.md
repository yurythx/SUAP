# Fluxo: Ciclo PES (Plano de Entregas Setorial)

> Gestor/comissão cria o Plano de Entregas Setorial, define entregas e horários, submete para aprovação e, após uso no PIT/RIT, recebe avaliação.

- **Ator(es):** Gestor/Comissão PGD — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** Acessar `/pgd2/visualizar_pes/<pes_id>/`
- **Pré-condições:** `PeriodoPes` vigente, setor habilitado para PGD
- **Pós-condições:** PES aprovado, entregas vinculadas a PITs, avaliação registrada
- **Depende de:** _nenhum_ na criação/aprovação. A etapa de **avaliação/análise da execução** depende do [Ciclo RIT](ciclo-rit.md) (a view checa `tem_servidor_sem_rit_homologado` antes de avaliar o PES)
- **Habilita:** [Ciclo PIT](ciclo-pit.md) (entregas do PES aprovado viram referência das entregas do PIT) e [Envio de dados à API PGD](envio-api-pgd.md) (PES é enviado junto com os PITs)
- **Entrada no código:** `views.visualizar_pes`, `views.cadastrar_entrega_pes`, `views.solicitar_aprovacao_pes`, `views.aprovar_pes`, `views.analisar_pes`, `views.avaliar_pes`

## Sequência

```mermaid
sequenceDiagram
    participant U as Gestor
    participant V as Views
    participant M as Models
    participant DB as PostgreSQL
    U->>V: GET /pgd2/visualizar_pes/<id>/
    V->>M: carrega PlanoEntregasSetorial + entregas
    M->>DB: SELECT
    DB-->>M: dados
    M-->>V: plano + entregas
    V-->>U: tela de gestão
    U->>V: cadastra/edita entregas, horários
    V->>M: salva PlanoEntregasSetorialEntregas
    M->>DB: INSERT/UPDATE
    U->>V: POST solicitar_aprovacao_pes
    V->>M: muda situacao="aguardando_aprovacao"
    M->>DB: UPDATE
    Note over U,V: Chefe/Comissão aprova
    U->>V: POST aprovar_pes
    V->>M: situacao="aprovado"
    Note over M,DB: PES vira referência para PITs
    Note over U,V: Após período de execução
    U->>V: POST avaliar_pes
    V->>M: registra avaliação
```

## Observações

- PES tem subtipos: `PlanoEntregasSetorialAprovacao` (proxy de aprovação), `PlanoEntregasSetorialAvaliacao` (proxy de avaliação), `PlanoEntregasSetorialConsulta` (proxy de consulta)
- Entregas do PES podem ser vinculadas a entregas do PIT (`PlanoIndividualTrabalhoEntregas.entrega_pes`)
- Horários de funcionamento e planejamento são registrados separadamente
- ⚠️ REVISAR: transição exata de situações (rascunho → aguardando_aprovacao → aprovado → em_execucao → avaliado)

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04.
