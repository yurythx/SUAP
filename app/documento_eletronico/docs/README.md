# Documento Eletrônico

> ⚠️ REVISAR: este documento descreve o comportamento observado no código do módulo e não substitui validação funcional com as áreas responsáveis.

## Visão geral

O módulo `documento_eletronico` centraliza a criação, edição, classificação, compartilhamento, revisão, assinatura, finalização, consulta e auditoria de documentos eletrônicos e documentos digitalizados. Ele fornece a persistência dos documentos, os fluxos de estado e assinatura, a geração de PDF/PDF-A e pontos de integração com processos eletrônicos e módulos consumidores.

### Responsabilidades

- manter documentos textuais e digitalizados, seus interessados, anexos e identificadores;
- aplicar níveis de acesso (`sigiloso`, `restrito` e `público`) e hipóteses legais;
- controlar revisão, solicitações de assinatura, assinaturas digitais e finalização;
- compartilhar documentos com pessoas e setores, registrando permissões;
- gerar conteúdo e arquivos PDF/PDF-A, incluindo anexos;
- consultar autenticidade, integridade e documentos públicos;
- registrar ações relevantes e fornecer comandos de manutenção e indexação.

### Fora de escopo

- tramitação, juntada e gestão do processo eletrônico, que pertencem ao módulo `processo_eletronico`;
- cadastro mestre de pessoas, vínculos, servidores e setores, mantido por `comum`/`rh`;
- provimento da identidade/certificado GovBR e de serviços externos;
- definição das políticas institucionais que alimentam as configurações persistidas.

## Atores e papéis

| Papel/grupo | Capacidades observadas |
|---|---|
| Operador de Documento Eletrônico | operações de criação, edição e administração previstas pelas permissões do módulo |
| Gerente Sistêmico de Documento Eletrônico | gestão sistêmica de tipos, modelos, classificações e documentos |
| Gestão Nível de Acesso dos Processos Documentos Eletrônicos | alteração de nível de acesso e gestão correlata |
| Auditor / Auditor Sistêmico | consulta ampliada e acesso a registros conforme permissões |
| Procurador | consulta ampliada e operações processuais autorizadas |
| Chefe de Setor | atuação sobre documentos do setor e compartilhamentos autorizados |
| Servidor, Aluno, Aposentado, Prestador de Serviço e Usuário Externo | acesso conforme vínculo, compartilhamento, papel e permissões atribuídas |

> ⚠️ REVISAR: a matriz efetiva de grupos e permissões é carregada de `permissions.yaml` e pode ser complementada por dados da instalação.

## Estrutura interna

| Componente | Responsabilidade |
|---|---|
| `models.py` | modelos de documentos, catálogos, solicitações, assinaturas, compartilhamentos e auditoria |
| `views.py` | dashboards, CRUD, fluxos de revisão/assinatura, compartilhamento, anexação e consulta |
| `forms.py` | validações de negócio e formulários das operações |
| `admin.py` | listagens, filtros, ações em lote e controle de acesso no admin |
| `utils.py` | renderização, hash, armazenamento privado, notificações, integração e indexação |
| `generators.py` | identificadores sequenciais, siglas e identificadores de documentos pessoais |
| `assinar_documento.py` | assinatura por senha (HMAC) |
| `managers.py` / `tables.py` | consultas especializadas, filtros e tabelas de documentos |
| `signals.py` | transições derivadas de solicitações de revisão e assinatura |
| `tasks.py` / `beat.py` | impressão de PDF/PDF-A e limpeza agendada de revisões |
| `management/commands/` | inicialização, indexação, correção, validação e manutenção |

## Endpoints principais

| Área | Rotas representativas |
|---|---|
| Entrada | `/documento_eletronico/dashboard/`, `/documento_eletronico/meus_documentos/` |
| Documento textual | `/admin/documento_eletronico/documentotexto/` (criação/listagem), `/documento_eletronico/editar_documento/<id>/`, `/documento_eletronico/concluir_documento/<id>/`, `/documento_eletronico/cancelar_documento/<id>/` |
| Assinatura | `/documento_eletronico/assinar_documento/<documento_id>/`, `/documento_eletronico/assinar_documento_cert/<documento_id>/`, `/documento_eletronico/assinar_documento_lote/` |
| Revisão | `/documento_eletronico/solicitar_revisao/<documento_id>/`, `/documento_eletronico/revisar_documento/<documento_id>/` |
| Acesso | `/documento_eletronico/gerenciar_compartilhamento_documento/<documento_id>/`, `/documento_eletronico/alterar_nivel_acesso_documento_texto/<documento_id>/` |
| Digitalizados e anexos | `/admin/documento_eletronico/documentodigitalizado/` (CRUD), `/documento_eletronico/listar_documentos_anexar/<documento_id>/`, `/documento_eletronico/anexar_documento_a_documentotexto/<documentotexto_id>/<documento_id>/`, `/documento_eletronico/desanexar_documento/<documentotexto_id>/<documento_id>/` |
| Consulta | `/documento_eletronico/autenticar_documento/`, `/documento_eletronico/verificar_documento_externo/`, `/documento_eletronico/consulta_publica/` |

> ⚠️ REVISAR: os nomes acima são agrupamentos técnicos de rotas existentes em `urls.py`; a disponibilidade final depende de autenticação, permissões e configurações.

## Modelos de domínio

| Subdomínio | Modelos |
|---|---|
| Documentos e conteúdo | `DocumentoTexto`, `DocumentoDigitalizado`, `TipoConferencia`, `DocumentoTextoInteressado`, `DocumentoDigitalizadoInteressado`, `DocumentoTextoAnexoDocumentoTexto`, `DocumentoTextoAnexoDocumentoDigitalizado` |
| Catálogos e classificação | `TipoDocumento`, `TipoDocumentoTexto`, `TipoDocumentoTextoHistoricoConteudo`, `RestricaoAssinatura`, `TipoVinculoDocumento`, `VinculoDocumentoTexto`, `HipoteseLegal`, `ModeloDocumento`, `Classificacao` |
| Assinaturas e revisão | `SolicitacaoAssinatura`, `SolicitacaoRevisao`, `Assinatura`, `AssinaturaDocumentoTexto`, `AssinaturaDocumentoDigitalizado` |
| Acesso e auditoria | `CompartilhamentoDocumentoPessoa`, `CompartilhamentoDocumentoDigitalizadoPessoa`, `SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa`, `CompartilhamentoSetorPessoa`, `RegistroAcaoDocumentoTexto`, `RegistroAcaoDocumentoDigitalizado` |

As classes abstratas `Documento`, `Solicitacao` e `RegistroAcaoDocumento` concentram comportamento compartilhado. `DocumentoTextoPessoal`, `DocumentoDigitalizadoPessoal` e `DocumentoDigitalizadoAnexoSimples` são proxies, não tabelas adicionais.

## ERD

O modelo foi particionado por subdomínio: [índice do modelo de dados](modelo-de-dados/_indice.md).

## Regras de negócio chave

- O nível de acesso restringe leitura e edição; documentos `restritos` e `sigilosos` exigem `HipoteseLegal`, enquanto documentos públicos não mantêm hipótese legal.
- Documento textual passa por estados de rascunho, conclusão, revisão, assinatura, assinatura concluída, finalização e cancelamento, conforme transições FSM do modelo.
- Conteúdo textual torna-se imutável quando possui identificador definitivo ou assinatura; documentos assinados/finalizados não são editáveis.
- A assinatura pode ser solicitada a vínculos, com dependências condicionais; a assinatura efetiva altera o estado por sinais e pode disparar finalização.
- A numeração definitiva considera tipo, setor e ano; documentos pessoais usam o vínculo do proprietário no identificador.
- Anexos simples seguem as regras de acesso do documento pai e participam da geração do PDF.
- Ações de criação, visualização, impressão, edição, assinatura, compartilhamento, revisão, cancelamento e alteração de acesso podem ser auditadas.

## Jobs / Tasks

| Nome | Tipo | Comportamento |
|---|---|---|
| `imprimir_pdf` | task assíncrona | gera PDF do documento e disponibiliza arquivo temporário |
| `imprimir_pdfa` | task assíncrona | gera PDF, converte para PDF/A e disponibiliza o resultado |
| `delete_revisions_documento_eletronico` | beat/management command | executa limpeza agendada de revisões às 04:07 |
| Comandos em `management/commands/` | manutenção | inicializam, indexam, validam e corrigem dados do módulo |

> ⚠️ REVISAR: os contratos individuais dos comandos de manutenção não foram consolidados neste One Page; consultar seus arquivos antes de automatizar a execução.

## Dependências

- `comum`: pessoas, vínculos, configurações, notificações e serviços compartilhados;
- `rh`: servidores, cargos, funções e setores;
- `contenttypes`: relações genéricas e permissões por objeto;
- `djtools`: modelos base, FSM, segurança, PDF, tabelas e infraestrutura;
- `processo_eletronico`: processo, tramitação, juntada e permissões processuais, quando instalado;
- `catalogo_provedor_servico`: autenticação/serviços GovBR, quando instalado;
- `centralservicos`: integração opcional usada pela configuração do módulo.

## Configuração

| Chave/configuração | Efeito observado |
|---|---|
| `DOC_SECRET_KEY` | base secreta usada na assinatura por senha/HMAC |
| `documento_eletronico.registrar_acoes_documentos_publicos` | controla registro de ações em documentos públicos |
| `documento_eletronico.permite_busca_corpo_conteudo` | habilita busca pelo corpo do documento |
| `documento_eletronico.permite_assinatura_lote` | habilita assinatura em lote |
| `documento_eletronico.permite_finalizacao_lote` | habilita finalização em lote |
| `documento_eletronico.base_conhecimento_permissao_acesso_documento` | controla integração de permissão com base de conhecimento |
| `documento_eletronico.grupossistemicos_com_perm_leitura_de_modelosdoc` | grupos sistêmicos que podem ler modelos |
| `processo_eletronico.*` | hipóteses legais, limites de upload, exclusão de minutas e tramitação |
| `catalogo_provedor_servico.api_key_notifica_govbr` | chave do serviço de notificação GovBR |

> ⚠️ REVISAR: valores padrão, origem administrativa e sensibilidade de cada configuração devem ser confirmados na instalação alvo.

## Como testar

```bash
pytest -q documento_eletronico
python manage.py test_behave --behave_stop --noinput documento_eletronico
```

O projeto exige PostgreSQL para os testes Django; a configuração de teste usa `MIGRATE=False` e constrói o esquema a partir dos modelos. Os fluxos de navegador não fazem parte desta documentação técnica.

## Links

- [HLA](HLA.md)
- [Glossário](GLOSSARIO.md)
- [Modelo de dados](modelo-de-dados/_indice.md)
- [Fronteira](FRONTEIRA.md)
- [Fluxos](fluxos/)

Gerado/atualizado via subagent `documentador` em 2026-09-09.
