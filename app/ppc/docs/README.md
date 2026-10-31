# Projeto Pedagógico de Curso (PPC)

> Gerencia, no SUAP, todo o ciclo de elaboração, tramitação e aprovação de Projetos Pedagógicos de Curso e dos Planos de Disciplina, até a geração das matrizes curriculares no módulo `edu`.

## Visão geral

O módulo `ppc` (área "Ensino") apoia a construção institucional dos cursos: parte de uma
**solicitação** de criação/adequação de PPC, passa pela **elaboração** dos conteúdos e
da matriz por uma comissão de servidores, segue por uma **tramitação de aprovação** nos
órgãos colegiados (Pró-Reitoria, Câmara, CONSEPEX, CONSUP) e termina **materializando** o
PPC aprovado em uma `edu.Matriz` real, com componentes e cursos. Também centraliza o
catálogo de **Planos de Disciplina** elaborados pelas comissões (PTDEM) e as **Diretrizes**
que regem cargas horárias e estrutura de cada tipo de oferta.

## Responsabilidades

- Registrar e tramitar **solicitações de PPC** (criação/adequação), com emissão de ata do colegiado e portaria de elaboração.
- Manter **diretrizes** por ano/tipo de oferta/modalidade (limites de CH, períodos, núcleos, eixos, prática profissional).
- Manter **modelos de PPC** e **modelos de plano de disciplina** (seções/conteúdos reutilizáveis).
- Conduzir a **elaboração colaborativa** do PPC (conteúdos, comissão de elaboradores/revisores) e sua **tramitação/aprovação** nos conselhos.
- Gerir o ciclo de vida dos **planos de disciplina** (elaboração → revisão → aprovação) e seu vínculo às matrizes do PPC.
- **Gerar** a matriz curricular, os componentes e os cursos no módulo `edu` a partir do PPC aprovado.
- Processar a **bibliografia** consolidada do PPC e emitir minutas/PDFs.

**Fora de escopo:** o cadastro definitivo de cursos, matrizes, componentes e estrutura
acadêmica vive em `edu` — o `ppc` apenas os **gera/alimenta**. Pessoas e setores vêm de
`rh`; entidades de domínio acadêmico (Modalidade, Núcleo, NivelEnsino, etc.) vêm de `edu`.

## Atores e papéis

Derivado de `permissions.yaml`, dos decorators das views e de papéis relacionais nos models.

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| Administrador de PPC | grupo `Administrador de PPC` / `comum.is_administrador_de_ppc` | Configura diretrizes, modelos, câmaras, pró-reitorias, comissões; administra solicitações e PPCs |
| Administrador Acadêmico | grupo `Administrador Acadêmico` (`comum.is_administrador_academico`) | Cria/altera solicitações, finaliza PPC, edita identificação do PPC aprovado |
| Diretor Acadêmico / Diretor Geral / Reitor | grupos homônimos (`app_manager: edu`) | Criam/alteram solicitações de PPC; deletam indicações de elaborador |
| Servidor | grupo `Servidor` / `comum.is_servidor` | Acessa o painel; cria/edita planos de disciplina; visualiza PPCs/diretrizes |
| Administrador de tipo de oferta | _derivado_ — `AdministradorTipoOferta.servidores` (M2M) | Administra diretrizes/modelos do(s) tipo(s) de oferta atribuído(s) ⚠️ REVISAR: papel relacional, não é grupo |
| Elaborador / Coordenador do PPC | _derivado_ — `ElaboradorPPC.funcao`/`permissao` | Edita conteúdos e a matriz do PPC durante a elaboração |
| Revisor do PPC | _derivado_ — `RevisorPPC` | Assume/revisa/homologa conteúdos do PPC em revisão |
| Membro da comissão PTDEM | _derivado_ — `ComissaoPTDEM.servidores` (M2M) | Cria planos de disciplina |
| Revisor de plano de disciplina / Avaliador | _derivado_ — `RevisorPlanoDisciplina`, `PlanoDisciplina.avaliador` | Analisa, comenta e aprova planos de disciplina |

## Estrutura interna

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `ppc/models.py` | 41 models (`LogModel`); regras de negócio e máquinas de estado (fat models) |
| Views | `ppc/views.py` | Views funcionais (`@rtr`); painel e todas as transições de workflow |
| URLs | `ppc/urls.py` | Rotas sob `/ppc/` |
| API | `ppc/api.py` | _N/A — módulo não expõe django-ninja_ |
| Forms | `ppc/forms.py` | `ModelFormPlus`/`FormPlus` para diretrizes, PPC, planos, matrizes, solicitações |
| Admin | `ppc/admin.py` | `ModelAdminPlus` (Diretriz, ModeloPPC, SolicitacaoPPC, PPC, PlanoDisciplina, etc.) — abas de pendência |
| Tasks | `ppc/tasks.py`, `ppc/beat.py` | Geração assíncrona de minuta e de bibliografia; beat diário de sincronização |
| Commands | `ppc/management/commands/` | `ppc_sincronizar` (beat), `ppc_converte_html_bibliografias`, `ppc_migrar_justificativas`, `ppc_remover_formatacao` |
| Outros | `ppc/utils.py`, `ppc/templatetags/ppc_tags.py` | `processar_bibliografia`; filtros de template |

## Endpoints principais

Todas as views são funcionais sob `/ppc/` (a maioria com `@rtr()`). Amostra dos pontos centrais:

| Método | Rota | View | Permissão |
|---|---|---|---|
| GET | `/ppc/painel/` | `painel` | `@permission_required('comum.is_servidor')` |
| GET/POST | `/ppc/diretriz/<pk>/` | `diretriz` | `@permission_required('ppc.view_diretriz')` |
| GET/POST | `/ppc/solicitacaoppc/<pk>/` | `solicitacaoppc` | `@permission_required('ppc.view_solicitacaoppc')` |
| POST | `/ppc/solicitacaoppc/<pk>/enviar/` | `enviar_solicitacaoppc` | `@permission_required('ppc.add_solicitacaoppc')` |
| POST | `/ppc/solicitacaoppc/<pk>/emitir_ata/` | `emitir_ata_solicitacaoppc` | `@permission_required('ppc.change_solicitacaoppc')` |
| POST | `/ppc/solicitacaoppc/<pk>/emitir_portaria/` | `emitir_portaria_solicitacaoppc` | `@permission_required('ppc.change_solicitacaoppc')` |
| GET/POST | `/ppc/projetopedagogicocurso/<pk>/` | `projetopedagogicocurso` | `@permission_required('ppc.view_projetopedagogicocurso')` |
| POST | `/ppc/projetopedagogicocurso/<pk>/informar_reitoria/` | `informar_reitoria_projetopedagogicocurso` | `@permission_required('ppc.change_projetopedagogicocurso')` |
| POST | `/ppc/projetopedagogicocurso/<pk>/emitir_documento/<documento>/` | `emitir_documento_projetopedagogicocurso` | `@permission_required('ppc.change_projetopedagogicocurso')` |
| POST | `/ppc/projetopedagogicocurso/<pk>/gerar_matriz/` | `gerar_matriz_projetopedagogicocurso` | `@permission_required('ppc.change_projetopedagogicocurso')` |
| POST | `/ppc/projetopedagogicocurso/<pk>/finalizar/` | `finalizar_projetopedagogicocurso` | `@permission_required('comum.is_administrador_academico')` |
| GET/POST | `/ppc/planodisciplina/<pk>/` | `planodisciplina` | `@permission_required('ppc.view_planodisciplina')` |
| POST | `/ppc/planodisciplina/<pk>/aprovar/` | `aprovar_planodisciplina` | `@permission_required('ppc.change_planodisciplina')` |
| GET | `/ppc/projetopedagogicocurso/<pk>/pdf/` | `ppc_pdf` | `@login_required` |

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| `Diretriz` | Regras curriculares por ano/tipo de oferta/modalidade (CH, períodos, núcleos) | FK `edu.Modalidade`, `edu.NaturezaParticipacao`, `comum.Ano`, `edu.EstruturaCurso` |
| `ModeloPPC` / `Secao` / `Conteudo` | Template de PPC (seções e conteúdos editáveis) | `Secao`→`ModeloPPC`; `Conteudo`→`Secao` |
| `SolicitacaoPPC` | Pedido de criação/adequação de PPC (com ata e portaria) | FK `rh.Servidor`, `edu.Modalidade`, `ppc.ProjetoPedagogicoCurso` (adequação) |
| `ProjetoPedagogicoCurso` | O PPC em si; máquina de estado central da tramitação | FK `ModeloPPC`, `Diretriz`, `SolicitacaoPPC`, `ProReitoria`, `Camara` |
| `ConteudoPPC` | Instância editável de cada `Conteudo` dentro de um PPC | FK `ProjetoPedagogicoCurso`, `Conteudo` |
| `MatrizPPC` | Matriz curricular do PPC; gera a `edu.Matriz` real | FK `ProjetoPedagogicoCurso`, `edu.Matriz`, `edu.Turno`; M2M `edu.CursoCampus` |
| `PlanoDisciplina` | Plano de disciplina (ementa/programa) com ciclo próprio de aprovação | FK `ModeloPlanoDisciplina`, `Diretriz`, `edu.Nucleo`, `edu.Componente` |
| `PlanoDisciplinaPPC` | Vínculo de um plano à matriz do PPC (período, tipo, CH) | FK `PlanoDisciplina`, `MatrizPPC` |
| `DocumentoPPC` | Documento eletrônico emitido em cada etapa da tramitação | FK `ProjetoPedagogicoCurso`, `rh.Servidor` |

ERD completo: ver [modelo-de-dados/](modelo-de-dados/).

## Regras de negócio chave

- **Três máquinas de estado encadeadas** (`models.py`): `SolicitacaoPPC.atualizar_situacao`, `ProjetoPedagogicoCurso` (elaboração↔revisão em `atualizar_situacao` e tramitação dos conselhos em `DocumentoPPC.atualizar_situacao`) e `PlanoDisciplina`.
- **Geração da matriz** (`MatrizPPC.gerar_matriz`): materializa o PPC aprovado em `edu.Matriz`, `edu.Componente`/`ComponenteCurricular`, e opcionalmente `edu.CursoCampus` — escrita central no módulo `edu`.
- **Validação de cargas horárias** distribuída nos `clean()` de `Diretriz`/`NucleoDiretriz`/`PeriodoDiretriz`/`ModalidadePraticaProfissional*` (somatórios não podem exceder os tetos da diretriz).
- **Bibliografia consolidada** (`utils.processar_bibliografia`): agrega as seções "Bibliografia Básica/Complementar" dos planos de disciplina do PPC, deduplicando obras.
- **Sobrescrita de conteúdos** ao ativar um `ModeloPPC` com `permite_sobrescrever_ppc` (`ModeloPPC.ativar` / `sobrescrever_conteudos_ppc`).
- Unicidade de diretriz/modelo ativo por (ano,) tipo de oferta e modalidade; só um coordenador por comissão (`ElaboradorPPC.clean`).

## Jobs / Tasks Celery

| Task / Job | Decorator / mecanismo | Dispara | Idempotência |
|---|---|---|---|
| `gerar_minuta_ppc` | `@task` (`djtools.assincrono`) | View (geração de minuta sob demanda) | Gera PDF temporário; reexecutável |
| `gerar_bibliografia` | `@task` (`djtools.assincrono`) | View `gerar_bibliografia_projetopedagogicocurso` | Sim — recalcula e sobrescreve `bibliografia_html` |
| `ppc_sincronizar` | beat (`ppc/beat.py`, crontab 03:37) → command | Diário | Sim — chama `atualizar_situacao()` para solicitações/PPCs pendentes de documento finalizado |

## Dependências

- **Módulos internos:** `comum`, `edu`, `rh` (ver `module_dependencies.json`).
- **Integrações:** `documento_eletronico` (`DocumentoTexto` — atas, portarias, pareceres, deliberações, resoluções, despachos), `processo_eletronico` (`Processo` — convênio), `ckeditor` (forms), `comum.Configuracao` (config por banco). As integrações de documento/processo são **condicionais** (`'<app>' in settings.INSTALLED_APPS`).

## Configuração

Configuração própria via `comum.Configuracao` (app `ppc`), lida com `Configuracao.get_valor_por_chave('ppc', ...)`:

| Origem | Chave | Uso |
|---|---|---|
| `comum.Configuracao` (`ppc`) | `setor_secretaria_conselhos` | Setor da secretaria dos conselhos (tramitação) |
| `comum.Configuracao` (`ppc`) | `setor_revisao_plano_disciplina` | Setor padrão de revisão de planos de disciplina |
| `comum.Configuracao` (`ppc`) | `permite_vincular_portaria_solicitacao` | Habilita vincular portaria diretamente na solicitação |
| `comum.Configuracao` (`ppc`) | `permite_gerar_curso_sem_pafc` | Permite gerar curso sem PAFC vinculado |
| `comum.Configuracao` (`ppc`) | `permite_gerar_curso_matriz` | Habilita geração de curso a partir da matriz |
| `comum.Configuracao` (`ppc`) | `permite_revisao_planodisciplina_em_elaboracao` | Permite revisar plano ainda em elaboração |
| `comum.Configuracao` (`ppc`) | `nome_modelo_ata` / `nome_modelo_portaria` / `nome_modelo_parecer_revisao` / `nome_modelo_parecer_camara` / `nome_modelo_deliberacao` / `nome_modelo_resolucao` / `nome_modelo_despacho` | Nomes dos modelos de documento eletrônico por etapa |
| `comum.Configuracao` (`comum`) | `instituicao_sigla` | Sigla da instituição usada nos PDFs |

## Como testar

```bash
pytest ppc/tests/
```

> ⚠️ REVISAR: o módulo não possui diretório `ppc/tests/` no momento da geração desta documentação.

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: [modelo-de-dados/](modelo-de-dados/)
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)

---
_Gerado/atualizado via subagent `documentador` em 2026-06-04._
