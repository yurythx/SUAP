# Modelo de dados — Projeto (PPC)

> ERD do subdomínio central: o PPC, seus conteúdos, comissão (elaboradores/colaboradores/
> revisores), documentos da tramitação, movimentações e certificação intermediária.
> Models herdam `LogModel`. Termos: ver [../GLOSSARIO.md](../GLOSSARIO.md).

```mermaid
erDiagram
    PROJETO_PEDAGOGICO_CURSO ||--o{ CONTEUDO_PPC : "conteudos"
    CONTEUDO_PPC ||--o{ COMENTARIO_CONTEUDO_PPC : "comentarios"
    PROJETO_PEDAGOGICO_CURSO ||--o{ DOCUMENTO_PPC : "documentos"
    PROJETO_PEDAGOGICO_CURSO ||--o{ ELABORADOR_PPC : "elaboradores"
    PROJETO_PEDAGOGICO_CURSO ||--o{ COLABORADOR_PPC : "colaboradores"
    PROJETO_PEDAGOGICO_CURSO ||--o{ REVISOR_PPC : "revisores"
    PROJETO_PEDAGOGICO_CURSO ||--o{ MOVIMENTACAO_PPC : "movimentacoes"
    PROJETO_PEDAGOGICO_CURSO ||--o{ ATUALIZACAO_COMISSAO_ELABORACAO : "atualizacoes"
    ATUALIZACAO_COMISSAO_ELABORACAO ||--o{ HISTORICO_ELABORADOR_PPC : "historico"
    PROJETO_PEDAGOGICO_CURSO ||--o{ CERTIFICACAO_PARCIAL : "certificacoes"
    CERTIFICACAO_PARCIAL ||--o{ PLANO_DISCIPLINA_CERTIFICACAO_PARCIAL : "planos"
    PROJETO_PEDAGOGICO_CURSO }o--|| MODELO_PPC : "modelo_ppc (externo)"
    PROJETO_PEDAGOGICO_CURSO }o--|| DIRETRIZ : "diretriz (externo)"
    PROJETO_PEDAGOGICO_CURSO }o--|| SOLICITACAO_PPC : "solicitacao (externo)"
    PROJETO_PEDAGOGICO_CURSO }o--o| PRO_REITORIA : "proreitoria (externo)"
    PROJETO_PEDAGOGICO_CURSO }o--o| CAMARA : "camara (externo)"
    CONTEUDO_PPC }o--|| CONTEUDO : "conteudo_modelo (externo)"
    PLANO_DISCIPLINA_CERTIFICACAO_PARCIAL }o--|| PLANO_DISCIPLINA : "plano_disciplina (externo)"
    PROJETO_PEDAGOGICO_CURSO {
        string nome_curso
        string situacao
        bool vigente
        int ch_curso
        int tipo_tramitacao
    }
    CONTEUDO_PPC {
        text texto
        string situacao
    }
    DOCUMENTO_PPC {
        string tipo_documento
        string situacao_ppc
        string situacao_documento
        string decisao
        int id_documento
    }
    ELABORADOR_PPC {
        string funcao
        string permissao
    }
```

## Entidades

| Entidade | Descrição | Relações-chave |
|---|---|---|
| `ProjetoPedagogicoCurso` | O PPC; máquina de estado central (elaboração→revisão→tramitação→aprovado/finalizado) | FK `ModeloPPC`, `Diretriz`, `SolicitacaoPPC`, `ProReitoria`, `Camara` |
| `ConteudoPPC` | Instância editável de um `Conteudo` do modelo, dentro do PPC | FK `ProjetoPedagogicoCurso`, `Conteudo`, `rh.Servidor` (revisor) |
| `ComentarioConteudoPPC` | Comentário de revisão sobre um conteúdo do PPC | FK `ConteudoPPC`, `rh.Servidor` |
| `DocumentoPPC` | Documento eletrônico emitido em cada etapa da tramitação (parecer/deliberação/resolução/despacho) | FK `ProjetoPedagogicoCurso`, `rh.Servidor` |
| `ElaboradorPPC` | Membro da comissão de elaboração (coordenador/membro; leitura/edição) | FK `ProjetoPedagogicoCurso`, `rh.Servidor` |
| `ColaboradorPPC` | Colaborador (acesso) do PPC | FK `ProjetoPedagogicoCurso`, `rh.Servidor` |
| `RevisorPPC` | Servidor revisor do PPC | FK `ProjetoPedagogicoCurso`, `rh.Servidor` |
| `AtualizacaoComissaoElaboracao` | Registro de atualização da comissão (vinculada a portaria) | FK `ProjetoPedagogicoCurso` |
| `HistoricoElaboradorPPC` | Histórico (cadastro/edição/exclusão) de elaboradores por atualização | FK `AtualizacaoComissaoElaboracao`, `rh.Servidor` |
| `MovimentacaoPPC` | Registro de cada transição de situação do PPC | FK `ProjetoPedagogicoCurso`, `comum.Vinculo` |
| `CertificacaoParcial` | Certificação intermediária do PPC (titulação, CH) | FK `ProjetoPedagogicoCurso`, `edu.Modalidade` |
| `PlanoDisciplinaCertificacaoParcial` | Vínculo de planos de disciplina à certificação intermediária | FK `CertificacaoParcial`, `PlanoDisciplina` |

## Entidades externas referenciadas

| Entidade | Módulo/área de origem |
|---|---|
| `ModeloPPC`, `Conteudo` | `ppc` (subdomínio Modelos) |
| `Diretriz` | `ppc` (subdomínio Diretriz) |
| `SolicitacaoPPC` | `ppc` (subdomínio Solicitação) |
| `ProReitoria`, `Camara` | `ppc` (subdomínio Configuração) |
| `PlanoDisciplina` | `ppc` (subdomínio Plano de Disciplina) |
| `Servidor` | `rh` |
| `Vinculo` | `comum` |
| `Modalidade` | `edu` |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
