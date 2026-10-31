# Glossário — Projeto Pedagógico de Curso (PPC)

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| PPC (Projeto Pedagógico de Curso) | Documento que estrutura um curso (identidade, CH, conteúdos e matriz); núcleo do módulo | `models.py` (`ProjetoPedagogicoCurso`) |
| Solicitação de PPC | Pedido formal de criação ou adequação de um PPC, que tramita até a portaria de elaboração | `models.py` (`SolicitacaoPPC`) |
| Diretriz | Conjunto de regras curriculares (CH, períodos, núcleos, eixos, prática) por ano/tipo de oferta/modalidade | `models.py` (`Diretriz`) |
| Tipo de oferta | Categoria do curso (mapeada para `edu.Modalidade`); chave de configuração de diretrizes/modelos | `models.py` (FKs `tipo_oferta`) |
| Modelo de PPC | Template de seções e conteúdos que instancia os `ConteudoPPC` de cada PPC | `models.py` (`ModeloPPC`, `Secao`, `Conteudo`) |
| Conteúdo | Texto de uma seção do PPC; editável ou fixo, com ciclo edição→revisão→homologação | `models.py` (`ConteudoPPC`) |
| Matriz do PPC | Planejamento da matriz curricular dentro do PPC; gera a `edu.Matriz` real | `models.py` (`MatrizPPC`) |
| Geração de matriz | Materialização do PPC aprovado em matriz/componentes/cursos no `edu` | `models.py` (`MatrizPPC.gerar_matriz`) |
| Plano de disciplina | Documento de uma disciplina (ementa, programa, bibliografia), com aprovação própria | `models.py` (`PlanoDisciplina`) |
| Plano de disciplina do PPC | Vínculo de um plano à matriz do PPC, com período, tipo e CH específicos | `models.py` (`PlanoDisciplinaPPC`) |
| Comissão de elaboração | Conjunto de elaboradores (1 coordenador + membros) responsável por construir o PPC | `models.py` (`ElaboradorPPC`) |
| Comissão PTDEM | Comissão responsável por elaborar planos de disciplina, vinculada a núcleos | `models.py` (`ComissaoPTDEM`) |
| Prática profissional | Modalidade de atividade prática exigida/optativa por núcleo (ex.: estágio) | `models.py` (`ModalidadePraticaProfissional*`) |
| Certificação intermediária (parcial) | Certificado emitido antes da conclusão do curso, com CH e planos próprios | `models.py` (`CertificacaoParcial`) |
| Tramitação | Sequência de análises do PPC pelos órgãos colegiados até a aprovação | `models.py` (`DocumentoPPC.atualizar_situacao`) |
| Ad referendum | Decisão tomada por instância individual, a referendar posteriormente pelo colegiado | `models.py` (campo `ad_referendum`) |
| Bibliografia consolidada | Agregação deduplicada das bibliografias dos planos de disciplina do PPC | `utils.py` (`processar_bibliografia`) |

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| PPC | Projeto Pedagógico de Curso | Todo o módulo |
| PTDEM | (comissão de planos de disciplina) | `ComissaoPTDEM` — elaboração de planos ⚠️ REVISAR: significado por extenso não consta no código |
| CONSEPEX | Conselho de Ensino, Pesquisa e Extensão (expansão padrão, não consta no código) | Etapa de tramitação (`ANALISE_CONSEPEX`) |
| CONSUP | Conselho Superior (expansão padrão, não consta no código) | Etapa de tramitação (`ANALISE_CONSUP`) |
| CH | Carga Horária | Campos `ch_*` em diretrizes, PPC e matriz |
| EAD | Educação a Distância | Percentuais/versões EAD em diretriz e planos |
| TCC | Trabalho de Conclusão de Curso | Tipo de componente/CH |
| ATPA | Atividade Teórico-Prática de Aprofundamento | Campos `ch_atpa` |
| AC | Atividade Complementar | Campos `ch_ac` |
| CENSUP / EDUCACENSO / e-MEC / SISTEC | Cadastros oficiais de cursos (MEC/INEP) | Códigos no `ProjetoPedagogicoCurso` |
| ENADE | Exame Nacional de Desempenho dos Estudantes | Flag `exige_enade` da diretriz |
| ETEP | (representação na indicação de elaboradores) | `IndicacaoElaboradorPPC.REPRESENTACAO_ETEP` ⚠️ REVISAR |

## Entidades ↔ termo de negócio

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `ProjetoPedagogicoCurso` | PPC | Nome técnico longo; usuário diz "PPC" |
| `SolicitacaoPPC` | Solicitação de PPC | — |
| `MatrizPPC` | Matriz do PPC | Distinta de `edu.Matriz` (que é a matriz efetiva gerada) |
| `ConteudoPPC` | Conteúdo do PPC | Instância de `Conteudo` (do modelo) dentro do PPC |
| `ElaboradorPPC` | Membro da comissão de elaboração | `funcao` = Coordenador/Membro |
| `ComissaoPTDEM` | Comissão de planos de disciplina | Sigla legada PTDEM |
| `AdministradorTipoOferta` | Administrador de tipo de oferta | Papel relacional (M2M com servidores) |
| `DocumentoPPC` | Documento da tramitação | Parecer/Deliberação/Resolução/Despacho |
| `Camara` / `ProReitoria` | Câmara / Pró-Reitoria | Órgãos de análise da tramitação |

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
