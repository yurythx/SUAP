# Glossário — Documento Eletrônico

> ⚠️ REVISAR: definições foram extraídas dos nomes, validações e transições do código; a redação normativa deve ser confirmada pela área de negócio.

## Termos

| Termo | Definição técnica observada |
|---|---|
| Documento textual | Documento cujo conteúdo é mantido no SUAP, com corpo, cabeçalho/rodapé, histórico e estado de workflow. |
| Documento digitalizado | Documento representado por arquivo enviado ao sistema, com tipo, conferência e hash. |
| Documento pessoal | Documento sem setor dono, associado ao vínculo/pessoa do proprietário. |
| Documento setorial | Documento associado a um setor dono. |
| Anexo simples | Documento digitalizado anexado a outro documento e submetido às regras do documento pai. |
| Modelo de documento | Template de conteúdo associado a um tipo de documento textual e a níveis de acesso permitidos. |
| Tipo de documento | Catálogo que define identificação, vinculação a pessoa e capacidades de consulta/análise. |
| Classificação | Árvore MPTT que organiza documentos e mantém dados de retenção/classificação. |
| Hipótese legal | Base legal vinculada a documento restrito ou sigiloso. |
| Interessado | Vínculo/pessoa relacionado ao documento para fins de acesso, acompanhamento ou notificações. |
| Compartilhamento | Concessão de leitura ou leitura e edição a pessoa/setor, conforme tipo e nível de permissão. |
| Solicitação de revisão | Pedido para que outro vínculo revise um documento textual. |
| Solicitação de assinatura | Pedido para que um vínculo assine um documento textual, podendo ter dependências condicionais. |
| Assinatura | Registro do vínculo/papel, CPF, data e HMAC que representa a assinatura. |
| Identificador definitivo | Identificador que fixa tipo, número, ano e, conforme o caso, setor ou proprietário. |
| Finalização | Estado terminal operacional de documento textual assinado. |
| Nível de acesso | Classificação `sigiloso`, `restrito` ou `público` que orienta leitura e edição. |
| Ação do documento | Evento auditável associado a documento textual ou digitalizado. |
| Balizadora | Solicitação de assinatura que não depende de outras solicitações. |

## Siglas

| Sigla | Significado |
|---|---|
| HMAC | Código de autenticação de mensagem baseado em hash, usado na assinatura por senha. |
| PDF | Portable Document Format, formato de saída dos documentos. |
| PDF/A | Variante arquivística do PDF, gerada pela task de conversão. |
| GovBR | Serviço/identidade Gov.br usado nas rotas de autenticação e assinatura. |
| MPTT | Modified Preorder Tree Traversal, estrutura usada por `Classificacao`. |
| CPF | Cadastro de Pessoas Físicas, armazenado nos dados da assinatura/certificado. |

## Entidades ↔ termo

| Entidade | Termo relacionado |
|---|---|
| `DocumentoTexto` | documento textual, identificador definitivo, finalização |
| `DocumentoDigitalizado` | documento digitalizado |
| `DocumentoDigitalizadoAnexoSimples` | anexo simples |
| `ModeloDocumento` | modelo de documento |
| `TipoDocumento` / `TipoDocumentoTexto` | tipo de documento |
| `Classificacao` | classificação |
| `HipoteseLegal` | hipótese legal |
| `DocumentoTextoInteressado` / `DocumentoDigitalizadoInteressado` | interessado |
| `CompartilhamentoDocumentoPessoa` / `CompartilhamentoSetorPessoa` | compartilhamento |
| `SolicitacaoRevisao` | solicitação de revisão |
| `SolicitacaoAssinatura` | solicitação de assinatura, balizadora |
| `Assinatura` | assinatura, assinatura digital |
| `RegistroAcaoDocumentoTexto` / `RegistroAcaoDocumentoDigitalizado` | ação do documento |

Gerado/atualizado via subagent `documentador` em 2026-09-09.
