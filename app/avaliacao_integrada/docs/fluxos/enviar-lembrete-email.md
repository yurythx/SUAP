# Fluxo: Enviar lembrete por e-mail

> Cobrar, por e-mail, quem foi identificado no público-alvo e ainda não enviou as respostas.

- **Ator(es):** Administrador de Avaliação Institucional (`pode_enviar_email_lembrete`) — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** botão "Enviar lembrete por e-mail" na aba Público-Alvo → `GET/POST /avaliacao_integrada/avaliacao/<pk>/enviar-email/`. Há ainda o disparo automático (na criação do público-alvo) e o command `ai_enviar_emails`
- **Pré-condições:** público-alvo gerado; respondentes com e-mail válido e `finalizado=False`; `settings.DEFAULT_FROM_EMAIL` configurado
- **Pós-condições:** e-mail HTML enviado ao conjunto de endereços elegíveis (deduplicado); mensagem informando o total
- **Depende de:** [Gerar público-alvo](gerar-publico-alvo.md)
- **Habilita:** [Responder questionário (interno)](responder-questionario-interno.md)
- **Entrada no código:** `views.avaliacao_enviar_email` + `forms.EnviarEmailRespondentesForm` → `Avaliacao.enviar_emails`

## Sequência

```mermaid
sequenceDiagram
    participant A as Administrador
    participant V as "views.avaliacao_enviar_email"
    participant F as "EnviarEmailRespondentesForm"
    participant M as "Avaliacao.enviar_emails"
    participant DB as PostgreSQL
    participant SMTP as "Servidor de e-mail"
    A->>V: "GET /avaliacao/<pk>/enviar-email/"
    V-->>A: "form com Assunto e Mensagem (HTML) pré-preenchidos"
    A->>V: "POST (título, mensagem, confirmar_envio)"
    V->>F: valida
    V->>M: "enviar_emails(titulo=..., mensagem_html=...)"
    M->>DB: "Respondente: finalizado=False, segmento em LISTA_EMAIL, e-mail não vazio"
    M->>M: "Coalesce(dados_usuario_externo.email, user.email); normaliza e valida cada endereço"
    M->>SMTP: "send_mail(assunto, corpo, DEFAULT_FROM_EMAIL, lista)"
    M-->>V: "total de destinatários"
    V-->>A: "E-mail enviado para N respondente(s) elegíveis."
```

## Observações

- **Elegibilidade:** `finalizado=False` **e** `segmento__pk in Segmento.LISTA_EMAIL` **e** e-mail não
  nulo/não vazio. O endereço vem de `Coalesce(dados_usuario_externo__email, user__email)`; cada um é
  normalizado (remove espaços, troca vírgula por ponto, minúsculas, `retira_acentos`) e validado por
  `validate_email` — inválidos são descartados com log. O conjunto final é um `set`, então duplicatas
  não geram dois envios.
- **Quatro mensagens automáticas** convivem com a manual, escolhidas por data em
  `Avaliacao.enviar_emails`: criação do público-alvo, início da avaliação, ≈75% do prazo decorrido e
  véspera do término. A chamada manual sobrescreve assunto e corpo com o que veio do formulário.
- O envio usa `djtools.utils.send_mail` com `fail_silently=True` — falhas de SMTP não interrompem nem
  aparecem para o usuário.
- Não há registro de quem/quando recebeu: nada é persistido sobre o envio.
- **⚠️ Defeitos conhecidos** (ver [HLA §7](../HLA.md#7-riscos-e-débito-técnico)):
  fora das janelas de data a função retorna `None` e `views.py:1229` (`if enviados > 0`) levanta
  `TypeError`; e o cálculo `hoje.replace(day=hoje.day + int(tempo_total * 0.75))` levanta
  `ValueError` quando a soma ultrapassa o último dia do mês.
- Este é o único ponto do módulo em que o Administrador se distingue do Aplicador por uma ação (e não
  apenas por visibilidade de dados).

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
