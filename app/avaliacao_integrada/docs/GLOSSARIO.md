# Glossário — Avaliação Integrada

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| Avaliação Integrada | A autoavaliação institucional aplicada pela CPA: um instrumento comum a toda a instituição, respondido por vários públicos no mesmo período. Dá nome ao módulo | `apps.py` (`verbose_name`) |
| Instrumento | O catálogo de perguntas reutilizável, organizado em eixo → dimensão → macroprocesso → indicador. Não é uma entidade: é a árvore formada por esses quatro models | `models.py` (`Eixo`, `Dimensao`, `Macroprocesso`, `Indicador`) |
| Avaliação | A **aplicação** do instrumento num ano/período, para um público e um prazo. É o que tem data de início/término, textos de instrução e público-alvo | `models.py` (`Avaliacao`) |
| Eixo | Primeiro nível do instrumento; no questionário vira uma aba | `models.py` (`Eixo`) |
| Dimensão | Segundo nível, dentro de um eixo | `models.py` (`Dimensao`) |
| Macroprocesso | Terceiro nível, dentro de uma dimensão; agrupa os indicadores sob um título | `models.py` (`Macroprocesso`) |
| Indicador | A pergunta em si, com seu tipo de resposta e todos os filtros de aplicabilidade. O texto que o respondente lê é o **critério de análise** (`aspecto`), não a denominação (`nome`) | `models.py` (`Indicador`) |
| Critério de Análise | Rótulo do campo apresentado ao respondente e usado nos relatórios | `Indicador.aspecto` |
| Denominação do Indicador | Nome interno, usado nas listagens de gestão e — nos indicadores autocalculados — como **chave de comportamento** | `Indicador.nome` |
| Indicador autocalculado | Indicador cujo valor o sistema preenche a partir do cadastro da pessoa (cargo, curso, ano de ingresso…), deixando o campo somente-leitura. Só funciona para as 13 denominações reconhecidas | `Indicador.automatico`, `Indicador.INDICADORES_AUTOCALCULADOS` |
| Iterador | Configuração que faz um indicador se repetir para cada objeto do respondente (cada curso, modalidade, professor ou turma), em vez de valer uma vez para a instituição | `models.py` (`Iterador`); `views.montar_formulario` |
| Objeto (da resposta) | O alvo a que uma resposta se refere quando há iterador. `None` significa "a instituição" | `Resposta.objeto` (`GenericForeignKey`) |
| Escala Likert | Régua de resposta reutilizável (níveis com descrição, emoji e critério de padronização). É o tipo de resposta padrão dos indicadores | `models.py` (`EscalaLikert`, `NivelEscalaLikert`) |
| Segmento | O público a que a pessoa pertence na avaliação (Docente, Estudante, Pais, Empresa Prestadora…). Determina quais indicadores ela recebe e por qual porta entra. São 14, de PK fixa em código | `models.py` (`Segmento`) |
| Público interno | Segmentos de quem tem conta no SUAP: servidores (gestor, docente, técnico, ETEP, CPA central/campus) e estudantes | `Segmento.TIPO_PUBLICO_INTERNO`, `Segmento.SERVIDORES`, `Segmento.ALUNOS` |
| Sociedade civil (público externo) | Segmentos de quem responde sem conta: pais/responsáveis, alunos egressos, empresas e profissionais prestadores de serviço, supervisores de estágio, desligados e "demais" | `Segmento.TIPO_SOCIEDADE_CIVIL`, `Segmento.SOCIEDADE_CIVIL` |
| Público-alvo | O conjunto de pessoas aptas a responder uma avaliação, calculado a partir dos filtros dela | `Avaliacao.obter_publicoalvo` |
| Gerar / reprocessar público-alvo | Materializar o público-alvo em registros `Respondente`. "Com exclusão" apaga antes todas as respostas já dadas | `Avaliacao.gerar_respondentes`, `tasks.reprocessar_publico_alvo` |
| Respondente | A pessoa **dentro de uma avaliação e de um segmento** — não é a pessoa em si. A mesma pessoa pode ser dois respondentes (ex.: gestor que também responde como docente) | `models.py` (`Respondente`) |
| Finalizado / Enviar respostas | Ato irreversível de submeter o questionário; enquanto não ocorre, as respostas ficam salvas e editáveis | `Respondente.finalizado`, `Resposta.processar(finalizar=True)` |
| Percentual respondido | Proporção de indicadores aplicáveis com resposta válida. A variante "realmente respondido" ignora indicadores automáticos e opcionais | `Respondente.get_percentual_respondido`, `get_percentual_realmente_respondido` |
| Área de vinculação | Campo de atuação de um setor (Ensino, Pesquisa, Extensão, Atividades Estudantis…). É por ela que se decide quais perguntas um servidor técnico recebe; cadastro pertence ao `rh` | `rh.AreaVinculacao`; usada em `Avaliacao.areas_vinculacao`, `Indicador.areas_vinculacao`, `Respondente.possui_area_vinculacao` |
| Link de compartilhamento | URL pública tokenizada da avaliação externa, exibida na tela da avaliação e no rodapé "Serviços de Acesso Público" | `views.avaliacao` (`url_to_share`), `views.servicos_anonimos` |
| Token | String `base64(json)` que carrega `avaliacao_id` e, conforme o passo, `respondente_id` e os dados informados pelo usuário externo. Não é assinado | `Avaliacao.gerar_token`, `Avaliacao.obter_dados` |
| Quadro-resumo | Consolidação campus × segmento em quatro blocos: Finalizados, Respondido 100% mas não enviados, Parciais e Não Respondidos | `views.avaliacao_quadro_resumo_bloco`, `views.quadro_resumo_xlsx` |
| Universo × Respondentes | No detalhamento do indicador: quantas pessoas foram convidadas e quantas responderam | `views.exibir_relatorio_indicador` (`qtd_respondentes`, `qtd_respostas`) |
| Respostas efetivas | Subconjunto usado nas medidas-resumo: exclui os níveis com critério "Desconheço" e "Não se aplica" | `views.exibir_relatorio_indicador` (`get_respostas`) |
| Comissão CPA | Comissão Própria de Avaliação, central (uma na instituição) ou local (uma por campus), designada por portaria | `models.py` (`ComissaoCPA`) |
| Identificação (do respondente) | O dado que identifica um respondente externo, variável por segmento: matrícula do aluno (Pais), CPF (egresso, prestador), CNPJ (empresa) ou e-mail | `Respondente.identificacao` |
| Fique atento! | Quadro da tela inicial do SUAP onde o convite para responder aparece | `views.index_inscricoes` (`@layout.inscricao()`) |

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| AAI | Autoavaliação Institucional | Nome usado nos commands (`gerar_aai_2024`, `aai_restore_respostas`) e no namespace de cache (`aai:respondente_helper`) |
| CPA | Comissão Própria de Avaliação | `ComissaoCPA`, segmentos `CPA Central`/`CPA Campus`, grupos `cpa_central`/`cpa_campus` |
| CPA Central / CPA Local | Comissão da instituição / do campus | `ComissaoCPA.CPA_CENTRAL`, `ComissaoCPA.CPA_LOCAL`. Atenção: o segmento equivalente chama-se `CPA_CAMPUS` |
| ETEP | Equipe Técnico-Pedagógica | `Segmento.ETEP` — pedagogo, psicólogo e técnico em assuntos educacionais (cargos `701058`, `701060`, `701079`) lotados em setor de área "ensino" |
| PDI | Plano de Desenvolvimento Institucional | `TipoAvaliacao.AVALIACAO_PLANEJAMENTO_PDI` (PK 10), tipo padrão dos indicadores |
| UO | Unidade Organizacional (campus/reitoria) | `rh.UnidadeOrganizacional`; campo `uo` em `Respondente`, `ComissaoCPA` |
| PI / PE | Público Interno / Público Externo | `Segmento.TIPO_CHOICES` — o rótulo de `PE` é "Sociedade Civil (Público Externo)" |
| PJ / PF | Pessoa Jurídica / Pessoa Física | Chaves `pj_nome`/`pf_nome` em `Respondente.dados_usuario_externo` |
| XLSX | Formato de planilha Excel | Exportações (`tasks.relatorio_xlsx`, `tasks.exportar_crosstab_xlsx`) |

## Entidades ↔ termo de negócio

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `Segmento` | "Segmento Respondente" / "Perfil" | `verbose_name` é "Segmento Respondente"; o questionário externo o chama de "Tipo do Respondente" e a tela do respondente, de "Perfil" |
| `Indicador` | "Pergunta" / "Critério de Análise" | O respondente nunca vê a palavra "indicador": lê o `aspecto` |
| `Respondente` | "Pessoa convidada a responder" | Não é a pessoa: é o par pessoa × avaliação × segmento. Para o público externo não há `user` — a pessoa vive no JSON `dados_usuario_externo` |
| `Resposta` | "Resposta" | `verbose_name_plural` está grafado no singular ("Resposta") |
| `Iterador` | — (sem nome de negócio) | Conceito puramente técnico exposto no admin do indicador; o usuário percebe apenas que a pergunta se repete por curso/turma/professor |
| `ComissaoCPA.tipo = CPA_LOCAL` | "CPA Local" | O segmento correspondente chama-se `CPA_CAMPUS`; a tradução acontece em `Avaliacao._filtrar_respondentes_por_segmento` |
| `Avaliacao.token` | — | Campo legado, marcado em desuso desde 24/09/2024; o token atual é calculado, não armazenado |
| `EscalaLikert` / `NivelEscalaLikert` | "Escala Likert" / "níveis" | Cadastrados na mesma tela (inline) |
| `TipoAvaliacao` | "Tipo de Avaliação" / "Subsídio p/ Avaliações" | O mesmo model aparece com os dois rótulos: "Tipos" na avaliação, "Subsídio p/ Avaliações" no indicador |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-05._
