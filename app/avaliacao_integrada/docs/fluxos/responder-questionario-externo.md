# Fluxo: Responder questionário (sociedade civil)

> Quem não tem conta no SUAP — pais, egressos, empresas, prestadores, supervisores de estágio — identifica-se por um link público e responde o questionário do seu segmento.

- **Ator(es):** Público externo (anônimo) — ver [README → Atores e papéis](../README.md#atores-e-papéis)
- **Gatilho:** abertura do link `"/avaliacao_integrada/avaliacao_externa/<token>"` (divulgado pela instituição ou listado no rodapé "Serviços de Acesso Público › Avaliações")
- **Pré-condições:** avaliação vigente (`data_inicio <= hoje <= data_termino`) **e** com ao menos um segmento de Sociedade Civil; reCAPTCHA configurado
- **Pós-condições:** `Respondente` do segmento escolhido criado/reaproveitado (chave: os dados informados) e `Resposta` gravada; retornar ao link com o **mesmo e-mail** reabre o questionário no ponto em que parou
- **Depende de:** [Cadastrar avaliação](cadastrar-avaliacao.md) (para o link existir) e [Gerar público-alvo](gerar-publico-alvo.md) (para o segmento ser reconhecido a partir dos dados)
- **Habilita:** [Analisar indicador](analisar-indicador.md)
- **Entrada no código:** `views.servicos_anonimos` (publicação), `views.avaliacao_externa` (identificação), `views.questionario_avaliacao_externa` (preenchimento), `views.respondente_externo_check` (checagem AJAX), `views.remover_respostas_avaliacao` (cancelamento)

## Sequência

```mermaid
sequenceDiagram
    participant U as "Visitante (sem login)"
    participant VE as "views.avaliacao_externa"
    participant AJ as "views.respondente_externo_check (AJAX)"
    participant VQ as "views.questionario_avaliacao_externa"
    participant M as "Avaliacao / Respondente / Resposta"
    participant DB as PostgreSQL
    U->>VE: "GET /avaliacao_externa/<token>"
    VE->>M: "obter_dados(token); is_vigente(); possui_segmento_sociedade_civil()"
    VE-->>U: "AvaliacaoExternaForm (e-mail, tipo de respondente, matrícula/CPF/CNPJ, reCAPTCHA)"
    U->>AJ: "POST (checagem do segmento antes de enviar)"
    AJ->>M: "check_respondente_segmento(...)"
    M-->>AJ: "segmento divergente? token_respondente para confirmação"
    U->>VE: "POST do formulário"
    VE->>M: "obter_respondentes_sociedade_civil(dados)"
    alt segmento diverge do já gerado
        VE-->>U: "aviso: excluir o questionário anterior e recomeçar?"
        U->>VE: "POST com token_respondente (confirmação)"
        VE->>DB: "DELETE respostas + respondente anteriores"
    end
    VE-->>U: "redirect /avaliacao_externa/<token_atualizado>/<segmento_id>/"
    U->>VQ: "GET"
    VQ->>M: "identifica respondente; montar_formulario"
    VQ-->>U: "questionário do segmento"
    U->>VQ: "POST (Salvar e Continuar)"
    VQ->>M: "Resposta.processar(...)"
    M->>DB: "DELETE + INSERT respostas (atômico)"
    VQ-->>U: "Avaliação respondida com sucesso."
```

## Observações

- **Identificação sem senha:** o par (e-mail + dado do segmento) é a chave.
  `Avaliacao.obter_respondentes_sociedade_civil` procura, nessa ordem, `respondente_id`, e-mail,
  matrícula, CPF, CNPJ dentro de `dados_usuario_externo`. Se o e-mail informado for diferente do
  gravado, o registro é **atualizado** com o novo e-mail.
- **Campos obrigatórios por segmento** (`Respondente.obter_dados_publico_alvo`): matrícula do aluno
  para Pais/Responsável; CPF para Aluno Egresso e Profissional Prestador; CNPJ para Empresa
  Prestadora; e-mail para Supervisor de Estágio.
- **Conflito de segmento:** se os dados apontarem para um respondente de outro segmento,
  `check_respondente_segmento` devolve aviso e um `token_respondente`; confirmar **apaga** respondente
  e respostas anteriores. Se os dados apontarem para mais de um segmento, o acesso é recusado
  ("não permitem identificar um perfil único").
- **Cancelar avaliação:** `views.remover_respostas_avaliacao` apaga as respostas do `respondente_id`
  contido no token — **não** apaga o respondente.
- O token é `base64(json)` **sem assinatura nem expiração**: qualquer `respondente_id` forjado é
  aceito pelo cancelamento e pelo fluxo de troca de segmento. Ver
  [HLA §7](../HLA.md#7-riscos-e-débito-técnico).
- **⚠️ Defeito conhecido — o primeiro acesso sempre falha.** Em `montar_formulario`, quando o
  respondente ainda não existe, `views.py:387` chama `Respondente.get_or_create(...)` e descarta o
  retorno; `respondente` continua `None` e `views.py:517` estoura `AttributeError` ("Erro no
  Sistema"). O registro **é** criado, então repetir a identificação com o mesmo e-mail funciona — é o
  contorno descrito em [usuario.md](../usuario.md).
- O rodapé público lista uma entrada por avaliação vigente com segmento de sociedade civil
  (`views.servicos_anonimos`, categoria "Avaliações"), cada uma com um token novo gerado a cada
  renderização.

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
