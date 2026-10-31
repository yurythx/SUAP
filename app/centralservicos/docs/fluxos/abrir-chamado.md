# Fluxo: Abrir chamado

> O solicitante registra uma requisição ou incidente para um serviço do catálogo, criando o chamado e seu roteamento inicial.

- **Ator(es):** Solicitante (Servidor / Aluno / Prestador de Serviço) — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** POST `/centralservicos/abrir_chamado/<servico_id>/`
- **Pré-condições:** serviço ativo e acessível ao público do usuário (`Servico.pode_acessar_servico`); usuário com ocupação ativa (campus via `get_uo`); existe Grupo de Atendimento de 1º nível para a UO/centro; permissão `add_chamado`.
- **Pós-condições:** `Chamado` criado em situação **Aberto**; `AtendimentoAtribuicao` inicial para o grupo de 1º nível; `HistoricoStatus` inicial; `data_limite_atendimento` (SLA) calculada; interessados e responsáveis notificados por e-mail.
- **Depende de:** _nenhum_
- **Habilita:** [Assumir e colocar em atendimento](atender-chamado.md), [Notificar SLA estourado](notificar-sla-estourado.md)
- **Entrada no código:** `views.abrir_chamado` → `ChamadoFormFactory` → `Chamado.save` → `Notificar.chamado_aberto`

## Sequência

```mermaid
sequenceDiagram
    participant U as Solicitante
    participant V as "View (abrir_chamado)"
    participant M as "Chamado (save)"
    participant DB as PostgreSQL
    U->>V: "POST abrir_chamado/<servico_id>/"
    V->>V: "valida serviço (ativo/público/campus)"
    V->>M: "form.save() (centro_atendimento, campus)"
    M->>M: "calcula data_limite (SLA, sem feriados/fds)"
    M->>DB: "INSERT Chamado"
    M->>M: "get_grupo_primeiro_nivel(campus, centro)"
    M->>DB: "INSERT AtendimentoAtribuicao + HistoricoStatus"
    M-->>V: "chamado criado"
    V->>V: "Notificar.chamado_aberto"
    V-->>U: "redirect chamado + mensagem de sucesso"
```

## Observações

- Tudo dentro de `Chamado.save` roda em `@transaction.atomic`; se não houver grupo de 1º nível, lança `ValidationError` e nada é gravado.
- Serviços marcados como `interno` só podem ser abertos por atendentes do(s) grupo(s) da área.
- Anexos só são salvos se `servico.permite_anexos`; patrimônio é exigido se `servico.requer_numero_patrimonio`.
- O e-mail de cópia ao interessado é condicionado a `enviar_copia_email` do formulário; responsáveis do grupo são sempre notificados.

---
_Gerado/atualizado via subagent `documentador` em 2026-06-08._
