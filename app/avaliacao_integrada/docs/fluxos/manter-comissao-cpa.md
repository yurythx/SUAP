# Fluxo: Manter comissão CPA

> Registrar a Comissão Própria de Avaliação designada por portaria — e, com isso, dar aos membros o acesso e a condição de público-alvo dos segmentos CPA.

- **Ator(es):** Administrador de Avaliação Institucional (`add/change/view/delete_comissaocpa`) — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** admin `/admin/avaliacao_integrada/comissaocpa/` (menu Des. Institucional › Avaliação Integrada › Comissões CPA)
- **Pré-condições:** setor ativo cadastrado em `rh`; vínculos (`comum.Vinculo`) dos membros; grupos `cpa_central` e `cpa_campus` existentes na base; opcionalmente a portaria em `documento_eletronico`
- **Pós-condições:** `ComissaoCPA` ativa única por tipo/campus; membros adicionados ao grupo correspondente; passam a ser identificados como público-alvo dos segmentos `CPA Central`/`CPA Campus`
- **Depende de:** _nenhum_
- **Habilita:** [Gerar público-alvo](gerar-publico-alvo.md) (para os segmentos CPA)
- **Entrada no código:** `admin.ComissaoCPAAdmin` + `forms.ComissaoCPAForm`; `ComissaoCPA.clean/save/delete` e o receiver `m2m_changed`; `views.lista_emails_comissao`, `views.obter_membros_por_setor`

## Sequência

```mermaid
sequenceDiagram
    participant A as Administrador
    participant AD as "Django admin"
    participant M as "ComissaoCPA (regras)"
    participant S as "signal m2m_changed"
    participant G as "auth.Group"
    participant DB as PostgreSQL
    A->>AD: "Adicionar Comissão CPA (tipo, setor, portaria, membros, ativo)"
    AD->>M: "clean(): já existe comissão ativa deste tipo/campus?"
    alt já existe
        M-->>A: "ValidationError: desative a anterior"
    else livre
        M->>DB: "save(): uo = setor.uo; INSERT (UniqueConstraint ativa por tipo/uo)"
        AD->>DB: "grava M2M vinculos_membros"
        DB->>S: "m2m_changed (post_add)"
        S->>G: "usuario.groups.add(cpa_central | cpa_campus)"
        AD-->>A: "Cadastro realizado com sucesso."
    end
    A->>AD: "remove membro / desativa comissão"
    DB->>S: "m2m_changed (post_remove)"
    S->>G: "remove do grupo, salvo se estiver em outra comissão ativa do mesmo tipo"
```

## Observações

- **Unicidade em duas camadas:** `clean()` produz a mensagem de negócio ("Comissão CPA Central já
  existe…" / "…para o campus X…") e a `UniqueConstraint('tipo', 'ativo', 'uo')` com
  `condition=Q(ativo=True)` garante a regra no banco.
- **O campus é derivado:** `save()` sobrescreve `uo` com `setor.uo` — o campo não é editável no
  formulário.
- **Grupos são efeito colateral do M2M.** O receiver cobre `post_add` e `post_remove`; desativar a
  comissão e regravar os membros também remove os grupos (`not instance.ativo and action == 'post_add'`).
  A remoção só ocorre se o usuário não pertencer a outra comissão ativa do mesmo tipo.
  `Group.objects.get(name=...)` levanta `DoesNotExist` se a base não estiver semeada.
- **Exclusão é atômica:** `delete()` desfaz os grupos dos membros antes de apagar o registro.
- **Ponte com a coleta sem FK:** `Avaliacao._filtrar_respondentes_por_segmento` traduz
  `Segmento.CPA_CENTRAL → ComissaoCPA.CPA_CENTRAL` e `Segmento.CPA_CAMPUS → ComissaoCPA.CPA_LOCAL` por
  um dicionário literal e busca os membros da comissão **ativa** daquele tipo. Cuidado com a assimetria
  de nomes (segmento "Campus" ↔ comissão "Local").
- **Telas de apoio:** `views.lista_emails_comissao` concatena os `email_notificacao` dos membros para
  colar num campo de destinatários; `views.obter_membros_por_setor` devolve os vínculos de servidores
  ativos com **setor adicional** igual ao informado (usada pelo JS `inclui_membros_por_setor.js`).
  ⚠️ REVISAR: `obter_membros_por_setor` monta uma lista de dicionários e a devolve como corpo de
  `HttpResponse` com `content_type='application/json'` sem serializar — o corpo não é JSON válido.

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
