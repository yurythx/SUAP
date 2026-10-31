# Projetos de Ensino

> Gerencia o ciclo de vida de projetos de ensino do IFRN — da publicação do edital à
> conclusão do projeto — para servidores, alunos e avaliadores.

## Visão geral

O módulo `projetos_ensino` (área "Ensino") cobre todo o processo de fomento a projetos de
ensino: o gestor publica um **edital** (com calendário, critérios, recursos e ofertas por
campus); coordenadores **submetem e enviam** projetos; pré-avaliadores e avaliadores
**pré-selecionam, avaliam e selecionam**; após a divulgação, os projetos selecionados
entram em **execução** (atividades, gastos, frequência, fotos) e são **monitorados** até a
**conclusão**. Suporta dois tipos de edital — comum (`ENSINO`) e de fluxo contínuo
(`ENSINO_CONTINUO`) — e os fluxos pós-resultado de **recurso** e **cancelamento**.

## Responsabilidades

- Cadastrar e publicar editais de ensino, com calendário, critérios de seleção (`CriterioAvaliacao`), critérios pontuáveis (`Parametro`/`ParametroEdital`), recursos financeiros e ofertas por campus.
- Permitir submissão de projetos por coordenadores (servidores e, quando habilitado, alunos de graduação), com equipe, metas/atividades, memória de cálculo e desembolso.
- Conduzir a pré-seleção (por campus/coordenador de projetos) e a seleção (por avaliadores, com pontuação e classificação).
- Divulgar resultados parcial e final e tratar interposição de recursos.
- Acompanhar a execução: registro de execução de atividades, gastos, frequência de bolsistas, fotos, caracterização de beneficiários, lições aprendidas e avaliação dos alunos.
- Tratar conclusão, cancelamento, inativação e reabertura de projetos.
- Emitir declarações/certificados (participação, orientação, avaliador) e relatórios (equipes, e-mails, atraso, lições, beneficiários, estatísticas).

**Fora de escopo:** dados de pessoas/servidores (`rh`), alunos/cursos/disciplinas (`edu`),
naturezas de despesa (`financeiro`), vínculos e prestadores de serviço (`comum`). Projetos
de **pesquisa/extensão** são de outros apps; aqui só há o campo `relacao_pesquisa_ext`.

## Atores e papéis

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Gerente Sistêmico de Projetos de Ensino | grupo `Gerente Sistêmico de Projetos de Ensino` (`pode_gerenciar_edital`) | Gerencia editais, critérios, comissões, vê todos os projetos, altera fichas de avaliação, cancela pré-avaliação |
| Coordenador de Projetos de Ensino | grupo `Coordenador de Projetos de Ensino` (`pode_pre_avaliar_projeto`, `pode_monitorar_projeto`, `pode_avaliar_cancelamento_projeto`) | Pré-seleciona, monitora e avalia cancelamentos/recursos nos campi atribuídos (próprio + `CampusAdicional`) |
| Avaliador de Projetos de Ensino | grupo `Avaliador de Projetos de Ensino` (`pode_avaliar_projeto`) | Avalia (pontua) projetos indicados a si |
| Coordenador do projeto | _derivado_ — `Participacao.responsavel = True` | Submete/edita/envia o projeto, gerencia equipe, registra execução/gastos/conclusão; ⚠️ REVISAR: papel relacional, não é grupo |
| Monitor do projeto | _derivado_ — `Projeto.vinculo_monitor` | Valida atividades, gastos e a conclusão do projeto; ⚠️ REVISAR: papel relacional |
| Pré-avaliador | _derivado_ — `Projeto.vinculo_autor_pre_avaliacao` (perm `pode_pre_avaliar_projeto`/`pode_monitorar_projeto`) | Pré-aprova/pré-rejeita/devolve o projeto na pré-seleção; ⚠️ REVISAR: papel relacional + permissão |
| Monitor de Projetos de Ensino | grupo `Monitor de Projetos de Ensino` | Pré-avalia e monitora projetos de qualquer campus |
| Integrante da Comissão de Acompanhamento | grupo homônimo | Permissões equivalentes ao coordenador de projetos para acompanhamento |
| Aluno / Servidor participante | grupos `Aluno`/`Servidor` (`pode_interagir_com_projeto`) | Interage com projetos de que participa; aluno registra considerações sobre sua avaliação (`pode_registrar_consideracao_aluno`) |
| Visualizador de Projetos de Ensino | grupo homônimo (`pode_visualizar_*`) | Vê projetos/relatórios do seu campus |
| Diretor Acadêmico / Coordenador de Curso | grupos (app_manager `edu`) | Gerenciam editais/comissões/colaboradores (Diretor) ou visualizam projetos (Coord. Curso) |
| Avaliador / Colaborador externo | `comum.PrestadorServico` / `AvaliadorExterno` | Participam como colaborador voluntário ou avaliam projetos sem vínculo de servidor |

## Estrutura interna

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `projetos_ensino/models.py` | 44 models; `Projeto` concentra a máquina de estados (`get_status`/`get_periodo` + métodos `pode_*`); `Edital` tem o calendário e managers por período |
| Views | `projetos_ensino/views.py` | ≈150 views funcionais (`@rtr`); workflow, relatórios, declarações/PDFs, widget de dashboard, tab de servidor |
| URLs | `projetos_ensino/urls.py` | Rotas sob `/projetos_ensino/` |
| API | `projetos_ensino/api.py` | _N/A — não há api.py (Django clássico)_ |
| Forms | `projetos_ensino/forms.py` | `ModelFormPlus`/`FormPlus` de submissão, avaliação, recurso, relatórios |
| Admin | `projetos_ensino/admin.py` | `ModelAdminPlus` de Projeto, Edital, Comissões, cadastros (Critérios, Beneficiário, Colaborador/Avaliador Externo, CampusAdicional) |
| Tasks | `projetos_ensino/tasks.py` | 5 tasks de exportação XLS (`@task` de `djtools.assincrono`) |
| Commands | `projetos_ensino/management/commands/` | _N/A_ |
| Outros | `menu.yaml`, `permissions.yaml`, `features/` (BDD), `tests/` (pytest) | Navegação, grupos/permissões, testes de fluxo |

## Endpoints principais

(filtrados pelo `menu.yaml`; rota completa sob `/projetos_ensino/`)

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| GET | `/editais_abertos/` | `editais_abertos` (Adicionar projeto) | `pode_interagir_com_projeto` |
| GET | `/meus_projetos/` | `meus_projetos` | `pode_interagir_com_projeto` |
| GET | `/editais/` | `editais` | `pode_interagir_com_projeto` |
| GET | `/pre_avaliacao/` | `pre_avaliacao` (Pré-avaliar) | `pode_pre_avaliar_projeto` |
| GET | `/avaliacao/` | `avaliacao` (Avaliar) | `pode_avaliar_projeto` |
| GET | `/indicar_pre_avaliador/` | `indicar_pre_avaliador` | `pode_avaliar_cancelamento_projeto` |
| GET | `/editais_para_avaliacao/` | `editais_para_avaliacao` (Indicar Avaliador) | `add_comissaoedital` |
| GET | `/gerenciar_monitores/` | `gerenciar_monitores` | `pode_avaliar_cancelamento_projeto` |
| GET | `/projetos_em_execucao/` | `projetos_em_execucao` (Monitoramento) | `pode_monitorar_projeto` |
| GET | `/solicitacoes_de_cancelamento/` | `solicitacoes_de_cancelamento` | `pode_avaliar_cancelamento_projeto` |
| GET | `/solicitacoes_de_recurso/` | `solicitacoes_de_recurso` (Interposição de recursos) | `pode_avaliar_cancelamento_projeto` |
| GET | `/resultado_edital/<periodo>/` | `resultado_edital` (Resultado Final/Parcial) | `pode_interagir_com_projeto` |
| GET | `/relatorio_licoes_aprendidas/`, `/listar_equipes_dos_projetos/`, `/estatisticas/`, ... | relatórios | `pode_visualizar_relatorios_projetos_ensino` |
| GET | `/emitir_declaracao_avaliador/` | `emitir_declaracao_avaliador` | `pode_avaliar_projeto` |

> ⚠️ REVISAR: `GET /divulgar_resultado_edital/<edital_id>/<periodo>/` **não tem**
> `@permission_required` (só `@rtr()`) — diferente do sibling `resultado_edital`. Ver HLA §7.

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `Edital` | Edital de ensino: calendário, tipo, forma de seleção, critérios, recursos, ofertas | FK `cadastrado_por`; managers por período |
| `Projeto` | Projeto submetido; máquina de estados (submissão → pré-seleção → seleção → execução → conclusão) | FK `edital`, `uo`, `setor`, `eixo_tematico` |
| `Participacao` | Membro da equipe (coordenador/servidor/aluno/colaborador) | FK `projeto`, `vinculo_pessoa`, `orientador` |
| `Avaliacao` / `ItemAvaliacao` | Avaliação pontuada por critério; recalcula a pontuação do projeto | FK `projeto`, `vinculo`, `criterio_avaliacao` |
| `Meta` / `Etapa` | Metas e atividades planejadas | FK `projeto`/`meta`, `responsavel` |
| `ItemMemoriaCalculo` / `Desembolso` / `RegistroGasto` | Orçamento planejado e gastos realizados | FK `projeto`/`item`/`despesa` |
| `RecursoProjeto` / `ProjetoCancelado` | Interposição de recurso e cancelamento | OneToOne/FK `projeto` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/) (44 models em 8 subdomínios).

## Regras de negócio chave

- **Máquina de estados** do projeto: `Projeto.get_periodo()` + `Projeto.get_status()` (`models.py`) derivam o estado a partir do calendário do `Edital` e dos flags `pre_aprovado`/`aprovado`/`inativado`/conclusão. Há ramos distintos para `ENSINO` e `ENSINO_CONTINUO`.
- **Classificação/seleção:** `Edital.classifica_projetos_extensao()` ordena por pontuação e desempate e marca `aprovado` até o ponto de corte (`Projeto.atingiu_ponto_de_corte()` = metade da pontuação máxima), respeitando `qtd_selecionados` por campus ou geral.
- **Pontuação:** `Avaliacao.save()`/`delete()` recalculam `Projeto.pontuacao` como **média** das avaliações (projeto com 1 só avaliação fica com 0).
- **Permissão de submissão:** `Edital.pode_submeter_projeto()` — servidor sempre; aluno só se `aluno_pode_submeter` e curso de graduação.
- **Conclusão:** `Projeto.pode_finalizar_conclusao()` exige zerar todas as pendências (execução, gastos, anexos, fotos, caracterização, lições, avaliação de aluno).
- **Campi do coordenador:** `CampusAdicional.get_campi_user()` define o escopo de campi do "Coordenador de Projetos de Ensino".
- **Contratos:** widget de dashboard (`@layout.quadro`) e aba no perfil do servidor (`@receiver(rh_servidor_view_tab)`). Ver [FRONTEIRA.md](FRONTEIRA.md).
- > ⚠️ REVISAR: `Projeto.pode_mostrar_dados_selecao()` referencia `Edital.EXTENSAO`, constante inexistente — bug latente (ver HLA §7).

## Jobs / Tasks Celery

| Task | Decorator | Dispara | Idempotência |
|---|---|---|---|
| `relatorio_licoes_aprendidas_to_xls` | `@task` (djtools.assincrono) | Botão "Exportar" no relatório de lições | Sim — só lê e gera XLS |
| `listar_equipes_dos_projetos_to_xls` | `@task` | Exportar relatório de equipes | Sim |
| `listar_projetos_em_atraso_export_to_xls` | `@task` | Exportar projetos em atraso | Sim |
| `listar_avaliadores_de_projetos_export_to_xls` | `@task` | Exportar avaliadores | Sim |
| `relatorio_caracterizacao_beneficiarios_to_xls` | `@task` | Exportar caracterização de beneficiários | Sim — ⚠️ REVISAR: monta o XLS mas **não faz `return`** (ver HLA §7) |

Todas são de **exportação/relatório** (somente leitura → XLS), sem efeito colateral no domínio.

## Dependências

- **Módulos internos:** `comum`, `rh`, `edu`, `financeiro` (confirmado em `module_dependencies.json`).
- **Integrações:** `comum.Configuracao` (chave `nome_proen`), `comum.Vinculo`/`PrestadorServico`/`Ano`/`Setor`/`User`; `djtools` (ModelPlus, forms, `layout`, `relatorios`, `assincrono`, PDF/XLS); armazenamento via `PrivateFileField` (MinIO/storage padrão); `rh.views.rh_servidor_view_tab` (signal).

## Configuração

| Origem | Chave | Uso |
|---|---|---|
| `comum.Configuracao` (app `projetos_ensino`) | `nome_proen` | Nome da Pró-Reitoria de Ensino em cabeçalhos de declarações/resultados (default "Pró-Reitoria de Ensino") |
| `comum.Configuracao` (app `comum`) | `instituicao` | Nome da instituição em documentos emitidos |

## Como testar

```bash
pytest projetos_ensino/tests/
```

Os testes (`tests/test_fluxo_projetos_ensino.py` + `tests/conftest.py`) exercem o pipeline
completo (edital → projeto → enviar → pré-seleção → avaliação → execução → conclusão) pelos
endpoints reais, verificando a mudança de estado do projeto.

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-06-19._
