# Glossário — Projetos de Ensino

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| Edital | Chamada que abre a submissão de projetos, com calendário (inscrição, pré-seleção, seleção, recurso, divulgação), critérios, recursos e ofertas. Pode ser **comum** (`ENSINO`) ou de **fluxo contínuo** (`ENSINO_CONTINUO`). | `models.py` (`Edital`) |
| Projeto | Proposta submetida a um edital; percorre os estados Em edição → Enviado → Pré-selecionado → Selecionado → Em execução → Concluído (ou Não selecionado/Inativado/Cancelado). | `models.py` (`Projeto`) |
| Pré-seleção | Triagem feita por pré-avaliador/coordenador de projetos do campus, marcando `pre_aprovado`, dentro do limite `qtd_aprovados` da oferta. | `Projeto.pre_aprovado`, `pre_selecionar` view |
| Seleção (avaliação) | Pontuação por critério feita pelos avaliadores indicados; gera `pontuacao` (média) e `classificacao`; quem passa do ponto de corte fica `aprovado`. | `Avaliacao`, `Edital.classifica_projetos_extensao` |
| Ponto de corte | Metade da soma das pontuações máximas dos critérios do edital; abaixo dela o projeto não é selecionado. | `Projeto.atingiu_ponto_de_corte` |
| Envio do projeto | Conclusão do planejamento (`data_conclusao_planejamento`) que torna o projeto elegível à pré-seleção; registra `ProjetoHistoricoDeEnvio`. | `concluir_planejamento` view |
| Recurso (interposição) | Apelação do coordenador contra o resultado da seleção, avaliada por servidor (aceito/não aceito + parecer). | `models.py` (`RecursoProjeto`) |
| Investimento (recurso financeiro) | Valor disponível no edital por despesa/origem (PROEX, DIGAE, CAMPUS), usado no plano de aplicação. | `models.py` (`Recurso`) |
| Memória de cálculo | Item planejado de gasto (despesa, quantidade, valor unitário). | `models.py` (`ItemMemoriaCalculo`) |
| Desembolso | Parcela mensal planejada de um item de memória de cálculo (mês 1..12 do projeto). | `models.py` (`Desembolso`) |
| Meta / Atividade | Meta agrupa atividades; a "Atividade" é o model `Etapa` (a UI a chama de Atividade). | `models.py` (`Meta`, `Etapa`) |
| Critério (pontuável) | Parâmetro reusável que vira pontuação configurável por edital (a UI o chama de "Critério"). | `models.py` (`Parametro`, `ParametroEdital`) |
| Critério de avaliação (seleção) | Critério qualitativo com pontuação máxima e ordem de desempate, avaliado na seleção. | `models.py` (`CriterioAvaliacao`) |
| Monitor | Servidor (`vinculo_monitor`) responsável por validar atividades/gastos/conclusão durante a execução. | `Projeto.vinculo_monitor` |
| Pré-avaliador | Quem pré-aprova/pré-rejeita o projeto na pré-seleção (registrado em `vinculo_autor_pre_avaliacao`). | `Projeto.vinculo_autor_pre_avaliacao` |
| Coordenador do projeto | Participante com `responsavel=True`; submete e gerencia o projeto. | `Participacao.responsavel` |
| Colaborador externo | Voluntário sem vínculo de servidor/aluno, participa via `comum.PrestadorServico`. | `models.py` (`ColaboradorExterno`) |
| Campus adicional | Campi extras que um "Coordenador de Projetos de Ensino" pode operar além do próprio. | `models.py` (`CampusAdicional`) |
| Lição aprendida | Aprendizado registrado na conclusão (quando o edital exige). | `models.py` (`LicaoAprendida`) |
| Caracterização de beneficiário | Quantidade prevista/atendida de beneficiários do público-alvo por tipo. | `models.py` (`CaracterizacaoBeneficiario`) |
| Inativação / Cancelamento | Inativação = encerramento administrativo (`inativado`); Cancelamento = solicitação do coordenador, com substituto opcional (`proximo_projeto`). | `Projeto.inativado`, `ProjetoCancelado` |

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| PROEN | Pró-Reitoria de Ensino | Cabeçalho de declarações/resultados (config `nome_proen`) |
| PROEX | Pró-Reitoria de Extensão | Valor literal de `Recurso.origem` no plano de aplicação |
| DIGAE | (Diretoria de Gestão de Atividades Estudantis) | Valor literal de `Recurso.origem`; ⚠️ REVISAR: significado inferido, não consta no código |
| UO | Unidade Organizacional (Campus) | FK `Projeto.uo`, `OfertaProjeto.uo` (de `rh`) |
| CH | Carga Horária | `Projeto.ch_total`, `Participacao.carga_horaria` |

## Entidades ↔ termo de negócio

> Mapeia o nome técnico do modelo para o conceito de negócio (quando divergem).

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `Parametro` | "Critério" | `verbose_name = 'Critério'` — não confundir com `CriterioAvaliacao` |
| `Etapa` | "Atividade" | `verbose_name = 'Atividade'`; agrupada sob uma `Meta` |
| `OfertaProjeto` | "Oferta de Projeto" / "Plano de Oferta por Campus" | `verbose_name = 'Oferta de Projeto'` |
| `Recurso` | "Investimento" | `verbose_name = 'Investimento'` — recurso **financeiro** do edital |
| `RecursoProjeto` | "Recurso" | `verbose_name = 'Recurso'` — **interposição/apelação** contra o resultado; conceito distinto de `Recurso` |
| `ComissaoEdital` | "Comissão de Avaliação" | `verbose_name = 'Comissão de Avaliação'` |
| `classifica_projetos_extensao` (método) | Classificação de projetos de **ensino** | Nome legado herdado de extensão; opera sobre projetos de ensino |
| `pontua_projetos_extensao` (método) | Cálculo de pontuação (ensino) | Nome legado "extensao" |

> ⚠️ REVISAR: vários identificadores (`extensao`, `Edital.EXTENSAO`) são resquícios de
> código copiado de módulos de extensão/pesquisa; aqui o domínio é **ensino**.

---
_Gerado/atualizado via subagent `documentador` em 2026-06-19._
