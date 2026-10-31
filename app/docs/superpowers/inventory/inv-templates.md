# Inventário de Templates — 8 campos Pessoa/PessoaFisica

Data: 2026-07-02  
Escopo: `*.html` excluindo `*/tests/` e `docs/superpowers/`

---

## 1. Tally

**Total de sites reais em templates: 299**  
(excluídos ≈43 grupos de ruído de email + 6 grupos de foto — ver seção Ruído)

### Por campo

| Campo | Total | SERVIDOR | ALUNO | PRESTADOR | USER | AMBIGUOUS |
|---|---|---|---|---|---|---|
| email | 113 | 38 | 6 | 0 | 8 | 61 |
| email_secundario | 20 | 5 | 5 | 1 | 1 | 8 |
| foto (raw .foto/.foto.url) | 17 | 3 | 13 | 0 | 0 | 1 |
| get_foto_75x100_url | 117 | 12 | 17 | 9 | 49 | 30 |
| get_foto_150x200_url | 14 | 12 | 2 | 0 | 0 | 2 (vinculo/eleicao) |
| raca | 12 | 2 | 8 | 0 | 0 | 2 |
| setores_adicionais | 4 | 4 | 0 | 0 | 0 | 0 |
| deficiencia | 1 | 1 | 0 | 0 | 0 | 0 |
| povo_indigena | 1 | 0 | 1 | 0 | 0 | 0 |
| sistema_origem | **0** | - | - | - | - | - |

**AMBIGUOUS total: 110 sites** (37% do total) — maior risco pós-RemoveField

### Por fonte-de-vínculo (todos os campos)

| Fonte | Sites |
|---|---|
| SERVIDOR | 59 |
| ALUNO | 46 |
| PRESTADOR | 25 |
| USER (via get_profile/user.get_profile) | 59 |
| AMBIGUOUS (vinculo.pessoa / pessoafisica genérico) | 110 |

### Ruído excluído (email)
`setor.email`, `candidato.email` (processo_seletivo), `pessoa_externa.email`, `visitante.email`,
`UsuarioExterno.email` (próprio do model), `notificacao.email`, `log.email`, `contato.email` (PJ),
`demanda.email`, `inscrito.solicitante.email` (Vinculo diretamente), `p.get_participante.email`,
`p.get_responsavel.email`, `dados.endereco_profissional.email` (cnpq), `vinculo_fornecedor.pessoa.email`
(fornecedor/almoxarifado — AMBIGUOUS entre PJ e PF; marcado separado), `email_institucional` /
`email_academico` / `email_google_classroom` (campos distintos, não ocorrem nesses templates).

### Ruído excluído (foto)
`patrimonio foto.foto.url` (modelo Foto de patrimônio), `eventos participante_logado.foto`
(Participante model), `rh solicitacao.foto` (SolicitacaoAlteracaoFoto), `pesquisa autor.foto`
(PessoaExterna), `rh carteira.foto`.

---

## 2. Top 3 apps com mais AMBIGUOUS

| Rank | App | AMBIGUOUS sites | Campos dominantes |
|---|---|---|---|
| 1 | **edu** | 24 | email via vinculo.pessoa/pessoafisica (polo, disciplina, professor, evento, pre_matricula_internacional) |
| 2 | **pesquisa** / **projetos** | 12 cada | email via vinculo_coordenador.pessoa / vinculo_pessoa.pessoa / relacionamento.pessoa_fisica |
| 4 | **erros** | 10 | get_foto_75x100_url via vinculo.pessoa.pessoafisica (todos os templates de comentários/notas) |
| 5 | **portaria** | 9 | email + get_foto_75x100_url via vinculo.pessoa / vinculo.pessoa.pessoafisica |

---

## 3. Tabela completa

> Legenda: campo abreviado — `foto*` = qualquer variante (foto, get_foto_75x100_url, get_foto_150x200_url)  
> Tipo READ = leitura no template; WRITE = widget de formulário editando o campo.  
> Confiança: alto = cadeia clara até PF; medio = model intermediário pode abstrair.

### EMAIL

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| arquivo/templates/arquivos_upload.html:59 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| contratos/templates/pendencias.html:48 | email | SERVIDOR | fiscal.servidor.pessoa_fisica | READ | alto |
| contratos/templates/pendencias.html:92 | email | SERVIDOR | fiscal.servidor.pessoa_fisica | READ | alto |
| rsc/templates/abrir_processo_rsc.html:641 | email | SERVIDOR | processo.servidor.pessoa_fisica | READ | alto |
| rsc/templates/requerimento_pdf.html:97 | email | SERVIDOR | processo.servidor.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:107,109 | email | SERVIDOR | chefe.servidor.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:138,140,171,173 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:250,252,275,277 | email | PRESTADOR | prestador.pessoa_fisica | READ | alto |
| rh/templates/setor.html:73,75 | email | SERVIDOR | chefe.servidor.pessoa_fisica | READ | alto |
| rh/templates/setor.html:106,108,142,144 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/setor.html:199,201,224,226 | email | PRESTADOR | estagiario.pessoa_fisica | READ | alto |
| rh/templates/setor.html:251,253,276,278 | email | PRESTADOR | prestador.pessoa_fisica | READ | alto |
| rh/templates/servidor.html:110 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/aniversariantes.html:35 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/abrir_processo_afastamento_parcial.html:121 | email | SERVIDOR | processo.servidor.pessoa_fisica | READ | alto |
| rh/lps/demo_lps/templates/servidor.html:93 | email | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| professor_titular/templates/requerimento_pdf.html:73 | email | SERVIDOR | processo.servidor.pessoa_fisica | READ | alto |
| professor_titular/templates/abrir_processo_titular.html:871 | email | SERVIDOR | processo.servidor.pessoa_fisica | READ | alto |
| estagios/templates/gerar_relatorio_semestral_estagio.html:160 | email | PRESTADOR | estagiario.pessoa_fisica | READ | alto |
| estagios/templates/gerar_relatorio_modulo_aprendizagem.html:162 | email | PRESTADOR | aprendiz.pessoa_fisica | READ | alto |
| projetos/templates/relatorio_projeto.html:147 | email | SERVIDOR | projeto.get_responsavel.funcionario.pessoa_fisica | READ | alto |
| projetos_ensino/templates/relatorio_projeto.html:120 | email | SERVIDOR | projeto.get_responsavel.funcionario.pessoa_fisica | READ | alto |
| edu/templates/diretoria.html:247 | email | SERVIDOR | coordenador.servidor.pessoa_fisica | READ | alto |
| edu/templates/comprovante_matricula_pdf.html:103,104 | email | ALUNO | aluno.pessoa_fisica | READ | alto |
| edu/templates/turma_minicurso.html:196 | email | ALUNO | participante.aluno.pessoa_fisica | READ | alto |
| edu/templates/ver_alunos_turma_minicurso.html:19 | email | ALUNO | participante.aluno.pessoa_fisica | READ | alto |
| edu/templates/tabs/aluno_dados_pessoais.html:208 | email_secundario | ALUNO | obj.pessoa_fisica | READ | alto |
| catalogo_provedor_servico/templates/requerimento_pdf.html:109 | email | ALUNO | aluno.pessoa_fisica | READ | alto |
| rsc/templates/imprimir_documentos_pdf.html:192 | email | USER | avaliador.vinculo.user.get_profile | READ | alto |
| professor_titular/templates/imprimir_documentos_pdf.html:149 | email | USER | avaliador.vinculo.user.get_profile | READ | alto |
| edu/templates/diretoria.html:84,86 | email | USER | membro.usuario_grupo.user.get_profile | READ | alto |
| comum/templates/prestador_servico.html:81 | email | PRESTADOR | obj.pessoa_fisica | READ | alto |
| frota/templates/relatorio_motoristas_temporarios.html:40,41,78,79 | email | AMBIGUOUS | registro.vinculo_pessoa.pessoa | READ | alto |
| pesquisa/templates/listar_equipes_dos_projetos_detalhado_pesquisa.html:41,143 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| pesquisa/templates/relatorio_projeto.html:123 | email | AMBIGUOUS | projeto.vinculo_coordenador.relacionamento.pessoa_fisica | READ | alto |
| pesquisa/templates/relatorio_projeto.html:232,288 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| pesquisa/templates/imprimir_projeto.html:120 | email | AMBIGUOUS | projeto.vinculo_coordenador.relacionamento.pessoa_fisica | READ | alto |
| pesquisa/templates/imprimir_projeto.html:230,286 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| pesquisa/templates/lista_email_coordenadores.html:28 | email | AMBIGUOUS | projeto.vinculo_coordenador.pessoa | READ | alto |
| projetos/templates/listar_projetos_em_atraso.html:36 | email | AMBIGUOUS | p.vinculo_coordenador.pessoa | READ | alto |
| projetos/templates/relatorio_projeto.html:201,263,325 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| projetos/templates/listar_equipes_dos_projetos_detalhado.html:37,90,134,177 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| projetos/templates/imprimir_projeto.html:157 | email | AMBIGUOUS | projeto.vinculo_coordenador.relacionamento.pessoa_fisica | READ | alto |
| projetos/templates/imprimir_projeto.html:305,367 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| projetos/templates/lista_email_coordenadores.html:30 | email | AMBIGUOUS | projeto.vinculo_coordenador.pessoa | READ | alto |
| projetos_ensino/templates/relatorio_projeto.html:155 | email | AMBIGUOUS | p.vinculo_pessoa.pessoa | READ | alto |
| projetos_ensino/templates/imprimir_projeto.html:115 | email | AMBIGUOUS | projeto.vinculo_coordenador.relacionamento.pessoa_fisica | READ | alto |
| projetos_ensino/templates/lista_email_coordenadores.html:28 | email | AMBIGUOUS | projeto.vinculo_coordenador.pessoa | READ | alto |
| projetos_ensino/templates/listar_equipes_dos_projetos_detalhado.html:41,85,128 | email | AMBIGUOUS | p.pessoa | READ | alto |
| projetos_ensino/templates/relatorio_projeto.html:198 | email | AMBIGUOUS | p.pessoa | READ | alto |
| portaria/templates/registro_acesso_campus.html:49 | email | AMBIGUOUS | acesso.vinculo.pessoa | READ | alto |
| portaria/templates/listar_historico_acesso_geral.html:42 | email | AMBIGUOUS | acesso.vinculo.pessoa | READ | alto |
| portaria/templates/listar_pessoas.html:32,34 | email | AMBIGUOUS | vinculo.pessoa | READ | alto |
| edu/templates/polo.html:226,228,299,301 | email | AMBIGUOUS | coordenador/tutor.vinculo.pessoa | READ | alto |
| edu/templates/disciplina.html:50,52 | email | AMBIGUOUS | professor_diario.professor.vinculo.pessoa | READ | alto |
| edu/templates/professor.html:55,186,190 | email | AMBIGUOUS | obj.vinculo.pessoa | READ | alto |
| edu/templates/professor.html:336 | email | AMBIGUOUS | obj.vinculo.relacionamento.pessoa_fisica | READ | alto |
| edu/templates/evento.html:116,184,249 | email | AMBIGUOUS | participante_evento.participante.pessoa.pessoafisica | READ | alto |
| edu/templates/pre_matricula_internacional.html:70,119 | email | AMBIGUOUS | vinculo.pessoa.pessoafisica / inscricao.vinculo.pessoa.pessoafisica | READ | alto |
| patrimonio/templates/requisicao_inventario_uso_pessoal_listar.html:23 | email | AMBIGUOUS | requisicao.vinculo.pessoa | READ | alto |
| contratos/templates/contrato.html:372 | email | AMBIGUOUS | contrato.vinculo_contratado.pessoa | READ | alto |
| contratos/templates/contrato_publico.html:233 | email | AMBIGUOUS | contrato.vinculo_contratado.pessoa | READ | alto |
| almoxarifado/templates/entrada.html:66,100 | email | AMBIGUOUS | vinculo_fornecedor.pessoa | READ | medio |
| estagios/templates/gerar_justificativa_visita_estagio.html:21 | email | AMBIGUOUS | obj.pratica_profissional.orientador.vinculo.pessoa | READ | alto |
| estagios/templates/gerar_justificativa_visita_modulo_aprendizagem.html:20 | email | AMBIGUOUS | obj.aprendizagem.orientador.vinculo.pessoa | READ | alto |
| estagios/templates/gerar_relatorio_visita_estagio.html:20 | email | AMBIGUOUS | obj.pratica_profissional.orientador.vinculo.pessoa | READ | alto |
| estagios/templates/gerar_relatorio_visita_aprendizagem.html:20 | email | AMBIGUOUS | obj.aprendizagem.orientador.vinculo.pessoa | READ | alto |
| estagios/templates/gerar_termo_compromisso.html:53 | email | AMBIGUOUS | obj.orientador.vinculo.pessoa | READ | alto |
| eleicao/templates/votacao.html:39 | email | AMBIGUOUS | candidato.candidato_vinculo.relacionamento.pessoa_fisica | READ | alto |
| eleicao/templates/campanha.html:31 | email | AMBIGUOUS | candidato.candidato_vinculo.relacionamento.pessoa_fisica | READ | alto |

### EMAIL_SECUNDARIO

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| rh/templates/servidor.html:106 | email_secundario | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/lps/demo_lps/templates/servidor.html:89 | email_secundario | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/importar_servidor.html:46 | email_secundario | SERVIDOR | dados (import) | READ | alto |
| comum/templates/prestador_servico.html:85 | email_secundario | PRESTADOR | obj.pessoa_fisica | READ | alto |
| edu/templates/comprovante_matricula_pdf.html:106 | email_secundario | ALUNO | aluno.pessoa_fisica | READ | alto |
| edu/templates/turma_minicurso.html:196 | email_secundario | ALUNO | participante.aluno.pessoa_fisica | READ | alto |
| edu/templates/ver_alunos_turma_minicurso.html:19 | email_secundario | ALUNO | participante.aluno.pessoa_fisica | READ | alto |
| edu/templates/tabs/aluno_dados_pessoais.html:208 | email_secundario | ALUNO | obj.pessoa_fisica | READ | alto |
| edu/templates/inscricao_aluno_estrangeiro.html:192 | email_secundario | ALUNO | obj | READ | alto |
| edu/templates/professor.html:336 | email_secundario | AMBIGUOUS | obj.vinculo.relacionamento.pessoa_fisica | READ | alto |
| edu/templates/evento.html:116,184,249 | email_secundario | AMBIGUOUS | participante_evento.participante.pessoa.pessoafisica | READ | alto |
| pesquisa/templates/visualizar_assessor.html:40 | email_secundario | AMBIGUOUS | assessor.vinculo.pessoa.pessoafisica | READ | alto |
| frota/templates/relatorio_motoristas_temporarios.html:42,80 | email_secundario | AMBIGUOUS | registro.vinculo_pessoa.pessoa | READ | alto |
| comum/templates/usuarios_externos_pendentes_validacao.html:37 | email_secundario | USER | usuarioexterno | READ | medio |
| comum/templates/tela_pensionista.html:124 | email_secundario | AMBIGUOUS | pensionista.usuario_externo | READ | medio |
| comum/templates/usuario_externo.html:20 | email_secundario | AMBIGUOUS | obj (UsuarioExterno) | READ | medio |

### FOTO / GET_FOTO_* (seleção — SERVIDOR e AMBIGUOUS principais)

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| arquivo/templates/arquivos_upload.html:47 | foto.url_150x200 | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| arquivo/templates/arquivos_servidor.html:7 | foto.url_150x200 | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/servidor.html:89 | get_foto_150x200_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/servidores_sem_cargo.html:29 | get_foto_75x100_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/servidores_sem_setor_suap.html:35 | get_foto_75x100_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:91,123,154 | get_foto_75x100_url | SERVIDOR | chefe/servidor.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:191,214 | get_foto_75x100_url | PRESTADOR | estagiario | READ | alto |
| rh/templates/setor_detalhes.html:243,266 | get_foto_75x100_url | PRESTADOR | prestador.pessoa_fisica | READ | alto |
| rh/templates/setor_detalhes.html:294 | get_foto_75x100_url | ALUNO | bolsista.participacao.aluno.pessoa_fisica | READ | alto |
| rh/templates/setor.html:57,91,125 | get_foto_75x100_url | SERVIDOR | chefe/servidor.pessoa_fisica | READ | alto |
| rh/templates/setor.html:192,215 | get_foto_75x100_url | PRESTADOR | estagiario.pessoa_fisica | READ | alto |
| rh/templates/setor.html:244,267 | get_foto_75x100_url | PRESTADOR | prestador.pessoa_fisica | READ | alto |
| rh/templates/setor.html:295 | get_foto_75x100_url | ALUNO | bolsista.participacao.aluno.pessoa_fisica | READ | alto |
| rh/lps/demo_lps/templates/servidor.html:63 | get_foto_150x200_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| contratos/templates/includes/mao-de-obra-card.html:3 | get_foto_75x100_url | PRESTADOR | maodeobra.prestador_servico.pessoa_fisica | READ | alto |
| ponto/templates/includes/funcionario_dados_gerais.html:2 | get_foto_150x200_url | SERVIDOR | relatorio.funcionario.pessoa_fisica | READ | alto |
| pgd/templates/listar_pendencias_setor_servidor.html:23 | get_foto_150x200_url | SERVIDOR | servidor.servidor.pessoa_fisica | READ | alto |
| pgd2/templates/includes/dados_servidor2.html:4 | get_foto_150x200_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| comum/templates/autenticar_documento.html:38 | get_foto_150x200_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| comum/templates/ver_solicitacao_documento.html:40 | get_foto_150x200_url | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| progressoes/templates/abrir_avaliacao.html:79,100 | get_foto_75x100_url | SERVIDOR | avaliado/avaliador.pessoa_fisica | READ | alto |
| professor_titular/templates/abrir_processo_titular.html:858 | get_foto_75x100_url | SERVIDOR | processo.servidor | READ | alto |
| edu/templates/aluno.html:271 | get_foto_150x200_url | ALUNO | obj (aluno) | READ | alto |
| edu/templates/carometros_alunos_pdf.html:24 | get_foto_75x100_url | ALUNO | aluno | READ | alto |
| edu/templates/comprovante_matricula_pdf.html:47,48 | foto | ALUNO | aluno.foto | READ | alto |
| edu/templates/comprovante_matricula.html:14,15 | foto | ALUNO | aluno.foto | READ | alto |
| edu/templates/registroemissaodiploma_pdf.html:44,45 | foto | ALUNO | obj.aluno.foto | READ | alto |
| edu/templates/disciplina.html:104 | foto | ALUNO | matricula_diario.matricula_periodo.aluno.foto | READ | alto |
| edu/templates/emitir_boletim_pdf.html:17 | get_foto_150x200_url | ALUNO | matricula_periodo.aluno | READ | alto |
| edu/templates/includes/notas_form.html:266 | get_foto_75x100_url | ALUNO | matriculadiario.matricula_periodo.aluno | READ | alto |
| edu/templates/includes/notas_conceito_form.html:244 | get_foto_75x100_url | ALUNO | matriculadiario.matricula_periodo.aluno | READ | alto |
| edu/templates/includes/chamada_form.html:99 | get_foto_75x100_url | ALUNO | matricula_diario.matricula_periodo.aluno | READ | alto |
| ae/templates/comprovante_inscricao.html:5 | foto | ALUNO | inscricao.aluno.foto | READ | alto |
| ae/templates/gerenciar_participacao.html:26 | get_foto_75x100_url | ALUNO | inscrito.aluno.pessoa_fisica | READ | alto |
| ae/templates/programa.html:54,195 | get_foto_75x100_url | ALUNO | inscrito.aluno.pessoa_fisica | READ | alto |
| ae/templates/participacoes_bolsas_include.html:8 | get_foto_75x100_url | ALUNO | participacao.aluno.pessoa_fisica | READ | alto |
| auxilioemergencial/templates/comprovante_inscricao.html:10 | foto | ALUNO | inscricao.aluno.foto | READ | alto |
| etep/templates/acompanhamento.html:32 | get_foto_150x200_url | ALUNO | obj.aluno | READ | alto |
| edu/templates/napne/visualizar_acolhimento.html:32 | get_foto_75x100_url | ALUNO | acolhimento.aluno.get_profile | READ | alto |
| edu/templates/diario_aba_atividades_extensao.html:14 | get_foto_75x100_url | ALUNO | md.matricula_periodo.aluno | READ | alto |
| edu/templates/relatorio_impressao_pdf.html:94 | get_foto_75x100_url | ALUNO | aluno | READ | alto |
| edu/templates/inscricao_aluno_estrangeiro.html:40 | get_foto_150x200_url | ALUNO | obj (aluno estrangeiro) | READ | alto |
| edu/templates/diretoria.html:237 | get_foto_75x100_url | SERVIDOR | coordenador.servidor.pessoa_fisica | READ | alto |
| edu/templates/professor.html:34 | get_foto_150x200_url | AMBIGUOUS | obj (Professor view) | READ | alto |
| edu/templates/disciplinas.html:36 | get_foto_75x100_url | AMBIGUOUS | professor.professor (Professor obj) | READ | alto |
| edu/templates/polo.html:291 | get_foto_75x100_url | AMBIGUOUS | tutor.vinculo.pessoa | READ | alto |
| compras/templates/gerenciar_comentarios_etapa.html:23 | get_foto_75x100_url | AMBIGUOUS | comentario.vinculo.pessoa.pessoafisica | READ | alto |
| documento_eletronico/templates/visualizar_documento.html:587 | get_foto_75x100_url | AMBIGUOUS | interessado.pessoa.pessoafisica | READ | alto |
| saude/templates/includes/dados_paciente.html:3 | get_foto_75x100_url | AMBIGUOUS | atendimento.prontuario.vinculo.pessoa | READ | alto |
| saude/templates/prontuarios.html:30,61 | get_foto_75x100_url | AMBIGUOUS | pessoa (var direta) | READ | alto |
| saude/templates/prontuario.html:63 | get_foto_75x100_url | AMBIGUOUS | prontuario.vinculo.pessoa | READ | alto |
| processo_eletronico/templates/processo_eletronico/processo.html:594 | get_foto_75x100_url | AMBIGUOUS | comentario.vinculo.pessoa.pessoafisica | READ | alto |
| processo_eletronico/templates/.../processos_sem_tramitacao.html:47 | get_foto_75x100_url | AMBIGUOUS | interessado.pessoa.pessoafisica | READ | alto |
| processo_eletronico/templates/.../distribuicao_interna_processos_setor.html:130,263,392 | get_foto_75x100_url | AMBIGUOUS | interessado.pessoa.pessoafisica | READ | alto |
| portaria/templates/registro_acesso_campus.html:39 | get_foto_75x100_url | AMBIGUOUS | acesso.vinculo.pessoa.pessoafisica | READ | alto |
| portaria/templates/listar_historico_acesso_geral.html:35 | get_foto_75x100_url | AMBIGUOUS | acesso.vinculo.pessoa.pessoafisica | READ | alto |
| portaria/templates/listar_pessoas.html:26 | get_foto_75x100_url | AMBIGUOUS | vinculo.pessoa | READ | alto |
| ppc/templates/planodisciplina.html:218,253 | get_foto_75x100_url | AMBIGUOUS | comentario.vinculo.pessoa.pessoafisica | READ | alto |
| erros/templates/erro.html:185,215,235,255 | get_foto_75x100_url | AMBIGUOUS | informante/interessado/atendente.pessoa.pessoafisica | READ | alto |
| erros/templates/abas/notasinternas.html:31,44 | get_foto_75x100_url | AMBIGUOUS | nota.vinculo.pessoa.pessoafisica | READ | alto |
| erros/templates/abas/comentarios.html:64,91,107 | get_foto_75x100_url | AMBIGUOUS | comentario.vinculo.pessoa.pessoafisica | READ | alto |
| erros/templates/includes/erro.html:61 | get_foto_75x100_url | AMBIGUOUS | erro.informante.pessoa.pessoafisica | READ | alto |
| ae/templates/relatorio_erro_participacoes.html:12 | get_foto_75x100_url | AMBIGUOUS | pessoa_fisica (var direta) | READ | alto |
| eleicao/templates/votacao.html:28 | foto | AMBIGUOUS | candidato.candidato_vinculo.relacionamento.foto | READ | alto |
| eleicao/templates/campanha.html:19 | foto | AMBIGUOUS | candidato.candidato_vinculo.relacionamento.foto | READ | alto |
| portaria/templates/alterar_pessoa_externa.html:46 | foto | AMBIGUOUS | form.foto (PessoaExterna) | WRITE | alto |
| portaria/templates/cadastrar_pessoa_externa.html:45 | foto | AMBIGUOUS | form.foto (PessoaExterna) | WRITE | alto |
| comum/templates/selecionar_vinculo.html:14 | foto | AMBIGUOUS | vinculo.foto (Vinculo model) | READ | alto |
| comum/templates/minha_conta.html:99 | get_foto_150x200_url | USER | usuario.get_relacionamento.pessoa_fisica | READ | alto |
| (demandas, centralservicos, edu forum, chaves, catalogo_provedor...) | get_foto_75x100_url | USER | *.get_profile | READ | alto |

### RACA

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| edu/templates/comprovante_matricula_pdf.html:113 | raca | ALUNO | aluno.pessoa_fisica | READ | alto |
| edu/templates/comprovante_matricula.html:86 | raca | ALUNO | aluno.pessoa_fisica | READ | alto |
| edu/templates/tabs/aluno_dados_pessoais.html:40 | raca | ALUNO | obj.pessoa_fisica | READ | alto |
| edu/templates/inscricao_aluno_estrangeiro.html:76 | raca | ALUNO | obj | READ | alto |
| rh/templates/tab_dados_gerais.html:53 | raca | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/templates/importar_servidor.html:145 | raca | SERVIDOR | dados.pessoa_fisica | READ | alto |
| saude/templates/includes/dados_extras_paciente.html:50 | raca | AMBIGUOUS | atendimento.prontuario.vinculo.pessoa.pessoafisica | READ | alto |
| edu/templates/importar_aluno_csv_v2.html:52 | raca | AMBIGUOUS | label (string ref, não acessor real) | READ | alto |
| auxilioemergencial/templates/comprovante_inscricao.html:68 | raca | ALUNO | inscricao.aluno.caracterizacao.raca | READ | medio |
| ae/templates/comprovante_inscricao.html:107 | raca | ALUNO | inscricao.aluno.caracterizacao.raca | READ | medio |
| edu/templates/tabs/aluno_caracterizacao.html:22,23 | raca | ALUNO | obj.caracterizacao.raca / historico | READ | medio |

### POVO_INDIGENA

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| edu/templates/inscricao_aluno_estrangeiro.html:80 | povo_indigena | ALUNO | obj | READ | alto |

### DEFICIENCIA

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| rh/templates/importar_servidor.html:161 | deficiencia | SERVIDOR | dados.pessoa_fisica | READ | alto |

### SETORES_ADICIONAIS

| file:line | campo | fonte-vínculo | var-base | modo | confiança |
|---|---|---|---|---|---|
| rh/templates/tab_dados_gerais.html:201,205 | setores_adicionais | SERVIDOR | servidor.pessoa_fisica | READ | alto |
| rh/lps/demo_lps/templates/servidor.html:266,270 | setores_adicionais | SERVIDOR | servidor.pessoa_fisica | READ | alto |

### SISTEMA_ORIGEM
Nenhum hit em templates.
