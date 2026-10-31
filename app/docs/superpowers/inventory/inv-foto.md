# Inventário PessoaFisica.foto — campo `foto`

## 1. Tally

| Categoria | Qtd |
|-----------|-----|
| Hits brutos `.foto` (.py, sem migrations/tests) | 100 |
| RUÍDO (outro modelo com foto próprio) | 18 |
| **Sites reais PessoaFisica.foto** | **82** |
| — via get_foto_*_url (call-sites do dado) | 55 |
| — acesso direto .foto | 27 |

### Split READ/WRITE (sites reais)

| Tipo | Qtd |
|------|-----|
| READ | 70 |
| WRITE (`.foto.save(…)` ou `.foto = …`) | 12 |

### Por fonte-de-vínculo

| Fonte | Qtd |
|-------|-----|
| SERVIDOR | 30 |
| ALUNO | 31 |
| USER (profile/get_profile()) | 10 |
| AMBIGUOUS (vinculo.relacionamento.pessoa_fisica ou sem papel claro) | 11 |

### Sites "via get_foto_*_url"

55 call-sites que não acessam `.foto` diretamente mas delegam a um método que lê `self.foto` (get_foto_75x100_url, get_foto_150x200_url, get_foto_url_publica, get_foto_75x100_url_publica, get_foto_150x200_url_publica, get_foto_path).

---

## 2. Tabela de sites reais

### PessoaFisica — métodos que leem self.foto (defs internas)

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| rh/models/pessoa/pessoa_fisica.py:442-484 | READ | AMBIGUOUS | get_foto_url_publica / get_foto_75x100_url / get_foto_150x200_url / get_foto_url — lêem self.foto (e aluno.foto como fallback) | ALTA |
| rh/models/pessoa/pessoa_fisica.py:449 | READ | AMBIGUOUS | self.foto.get_url_publica(tamanho) dentro de get_foto_url_publica | ALTA |
| rh/models/pessoa/pessoa_fisica.py:450 | READ | AMBIGUOUS | path_img = self.foto.get_url_publica(tamanho) | ALTA |
| rh/models/pessoa/pessoa_fisica.py:465 | READ | AMBIGUOUS | path_img = aluno.foto.url_75x100 (fallback via aluno) | ALTA |
| rh/models/pessoa/pessoa_fisica.py:467-468 | READ | AMBIGUOUS | if self.foto: path_img = self.foto.url_75x100 | ALTA |
| rh/models/pessoa/pessoa_fisica.py:476-480 | READ | AMBIGUOUS | aluno/self.foto.url_150x200 | ALTA |
| rh/models/pessoa/pessoa_fisica.py:484 | READ | AMBIGUOUS | self.foto and self.foto.url | ALTA |

### Aluno.foto (edu — modelo próprio, mesmo fluxo de migração)

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| edu/models/alunos.py:4852 | WRITE | ALUNO | self.foto = None | ALTA |
| edu/models/alunos.py:6517-6534 | READ | ALUNO | get_foto_75x100_url / get_foto_150x200_url / get_foto_path — lêem self.foto | ALTA |
| edu/models/alunos.py:6640 | READ | ALUNO | 'foto': self.foto and self.foto.url | ALTA |
| edu/q_academico_fotos.py:63 | READ | ALUNO | if not aluno.foto.name | ALTA |
| edu/q_academico_fotos.py:65 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| edu/q_academico_fotos.py:69-70 | WRITE | ALUNO | default_storage.delete(aluno.foto.name); aluno.foto = '' | ALTA |
| edu/tasks.py:3964 | READ | ALUNO | if not aluno.foto | ALTA |
| edu/forms/alunos.py:704 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| edu/forms/alunos.py:705 | WRITE | ALUNO | aluno.pessoa_fisica.foto.save(...) — dupla gravação aluno E pf | ALTA |
| edu/forms/alunos.py:1067 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| edu/forms/matriculas.py:1073 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| edu/forms/matriculas.py:1075 | WRITE | ALUNO | aluno.foto.save(..., arquivo_foto.read()) | ALTA |
| edu/forms/internacionalizacao.py:215 | WRITE | ALUNO | self.instance.foto.save(...) — InscricaoAlunoEstrangeiro (modelo separado, RUÍDO) | RUÍDO |
| edu/forms/internacionalizacao.py:217 | WRITE | ALUNO | self.instance.foto.save(...) — idem | RUÍDO |
| edu/models/internacionalizacao.py:584 | WRITE | ALUNO | aluno.foto.save(...) (copia de InscricaoAlunoEstrangeiro) | ALTA |
| edu/management/commands/edu_zip_fotos_alunos.py:23 | READ | ALUNO | if not aluno.pessoa_fisica.foto | ALTA |
| edu/management/commands/edu_zip_fotos_alunos.py:28 | READ | ALUNO | aluno.pessoa_fisica.foto.name.replace(...) | ALTA |
| catalogo_provedor_servico/providers/impl/default/base.py:426 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| catalogo_provedor_servico/providers/impl/default/matricula_superior.py:360 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| catalogo_provedor_servico/providers/impl/default/matricula_pos_graduacao.py:376 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| catalogo_provedor_servico/providers/impl/default/matricula_ead.py:308 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| catalogo_provedor_servico/providers/impl/default/matricula_fic.py:314 | WRITE | ALUNO | aluno.foto.save(...) | ALTA |
| api/endpoints/ensino.py:1305-1306 | READ | ALUNO | if aluno.foto: / aluno.foto.open('rb') | ALTA |

### Professor.foto (edu — modelo próprio, mesmo fluxo)

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| edu/models/professores.py:361-396 | READ | SERVIDOR | get_foto_75x100_url / get_foto_150x200_url — lêem self.foto e self.vinculo.relacionamento.pessoa_fisica.foto | ALTA |
| edu/forms/professores.py:54 | WRITE | SERVIDOR | professor.foto.save(...) | ALTA |

### Servidor via pessoa_fisica.foto

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| rh/models/carreira/servidor.py:377-379 | READ | SERVIDOR | if self.pessoa_fisica.foto and default_storage.exists; self.pessoa_fisica.foto.open('rb') | ALTA |
| rh/models/carreira/servidor.py:621 | READ | SERVIDOR | all([..., self.pessoa_fisica.foto]) — validação cracha | ALTA |
| rh/models/carreira/servidor.py:649 | READ | SERVIDOR | self.pessoa_fisica.foto em lista de campos obrigatórios | ALTA |
| rh/models/seguranca/foto.py:70 | READ | SERVIDOR | servidor_solicitante.foto.read() — SolicitacaoAlteracaoFoto.validar(); servidor é Servidor, foto não existe diretamente → provavelmente bug latente ou acessa via pessoa_fisica | MÉDIA |
| rh/models/seguranca/foto.py:75 | WRITE | SERVIDOR | servidor_solicitante.foto.save(...) — idem | MÉDIA |
| rh/tasks.py:38 | READ | SERVIDOR | s.pessoa_fisica.foto.name.replace(...) | ALTA |
| rh/tasks.py:211 | READ | SERVIDOR | servidor.pessoa_fisica.foto and servidor.pessoa_fisica.foto.url_75x100 | ALTA |
| rh/pdf.py:206 | READ | SERVIDOR | servidor.pessoa_fisica.foto.name.replace(...) | ALTA |
| comum/management/commands/zip_fotos_funcionarios.py:25 | READ | SERVIDOR | if not s.pessoa_fisica.foto | ALTA |
| comum/management/commands/zip_fotos_funcionarios.py:28 | READ | SERVIDOR | s.pessoa_fisica.foto.name.replace(...) | ALTA |
| comum/management/commands/zip_fotos_funcionarios.py:35 | READ | SERVIDOR | if not s.pessoa_fisica.foto | ALTA |
| comum/management/commands/zip_fotos_funcionarios.py:38 | READ | SERVIDOR | s.pessoa_fisica.foto.name.replace(...) | ALTA |
| comum/management/commands/zip_fotos_funcionarios.py:44 | READ | SERVIDOR | s.pessoa_fisica.foto.name.replace(...) | ALTA |
| ldap_backend/utils.py:93-94 | READ | SERVIDOR | if pf.foto: / pf.foto.name.replace(...) — pf é PessoaFisica | ALTA |

### Via get_profile / user — fonte USER

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| centralservicos/views.py:2057 | READ | USER | usuario.get_profile().foto — get_profile() retorna PessoaFisica | ALTA |
| djtools/views.py:463 | READ | USER | profile.get_foto_75x100_url() — via get_foto_*_url | ALTA |
| djtools/views.py:519 | READ | USER | profile.get_foto_75x100_url() | ALTA |
| djtools/templatetags/tags/utils.py:731 | READ | USER | profile.get_foto_75x100_url() | ALTA |
| djtools/templatetags/filters/utils.py:397 | READ | USER | user.get_profile().get_foto_75x100_url() | ALTA |
| djtools/middleware/govbr.py:265 | READ | USER | if … not pessoa_fisica.foto | ALTA |
| djtools/middleware/govbr.py:269 | WRITE | USER | pessoa_fisica.foto.save(...) — upload via gov.br | ALTA |
| comum/forms.py:2393 | WRITE | USER | self.pessoa_fisica.foto.save(...) — AlterarFotoForm | ALTA |
| comum/webservice.py:154 | READ | USER | pf.get_foto_url_publica() | ALTA |

### via get_foto_*_url call-sites externos (não definições)

#### ALUNO

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| edu/admin/alunos.py:87 | READ | ALUNO | obj.get_foto_75x100_url() | ALTA |
| edu/models/alunos.py:4221 | READ | ALUNO | self.get_foto_75x100_url() | ALTA |
| api/endpoints/ensino.py:1305 | READ | ALUNO | if aluno.foto (direto) | ALTA |
| api/schemas/ensino.py:434 | READ | ALUNO | aluno.get_foto_75x100_url_publica() | ALTA |
| api/schemas/ensino.py:464 | READ | ALUNO | aluno.get_foto_75x100_url_publica() | ALTA |
| api/schemas/ensino.py:689 | READ | ALUNO | aluno.get_foto_75x100_url_publica() | ALTA |
| api/schemas/ensino.py:712 | READ | ALUNO | aluno.get_foto_75x100_url_publica() | ALTA |
| api/schemas/ensino.py:1063 | READ | ALUNO | obj.get_foto_75x100_url() | ALTA |
| api/schemas/ensino.py:1069 | READ | ALUNO | obj.get_foto_75x100_url_publica() | ALTA |
| ae/forms.py:1350 | READ | ALUNO | obj.get_foto_75x100_url() | ALTA |
| projetos_ensino/forms.py:468 | READ | ALUNO | obj.foto.url (Aluno direto) | ALTA |

#### SERVIDOR / PROFESSOR

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| edu/admin/professores.py:132 | READ | SERVIDOR | obj.get_foto_75x100_url() (Professor) | ALTA |
| rh/admin.py:931 | READ | SERVIDOR | obj.pessoa_fisica.get_foto_75x100_url() | ALTA |
| rh/views.py:1885 | READ | SERVIDOR | servidor.pessoa_fisica.get_foto_150x200_url() | ALTA |
| rh/views.py:3198 | READ | SERVIDOR | setor.chefes.all().first().get_foto_75x100_url() | ALTA |
| rh/pdf.py:67 | READ | SERVIDOR | servidor.get_foto_path() | ALTA |
| rh/models/carreira/servidor.py:670 | READ | SERVIDOR | self.pessoa_fisica.get_foto_75x100_url() | ALTA |
| rh/models/seguranca/foto.py:117 | READ | SERVIDOR | self.solicitante.pessoa_fisica.get_foto_150x200_url() | ALTA |
| contracheques/views.py:2125 | READ | SERVIDOR | cc.servidor.pessoa_fisica.get_foto_75x100_url() | ALTA |
| api/endpoints/rh.py:114-117 | READ | SERVIDOR/ALUNO | pessoa_fisica.get_foto_75x100_url_publica() / relacionamento.get_foto_75x100_url_publica() | ALTA |
| api/endpoints/rh.py:543 | READ | SERVIDOR | servidor.pessoa_fisica.get_foto_150x200_url_publica() | ALTA |
| api/schemas/rh.py:107 | READ | SERVIDOR | obj.pessoa_fisica.get_foto_75x100_url_publica() | ALTA |
| api/schemas/rh.py:204 | READ | SERVIDOR | obj.pessoa_fisica.get_foto_150x200_url_publica() | ALTA |
| api/schemas/institucional.py:86 | READ | SERVIDOR | obj.get_foto_75x100_url_publica() | ALTA |
| api/schemas/institucional.py:141 | READ | USER | obj.get_profile().get_foto_75x100_url_publica() | ALTA |
| api/schemas/institucional.py:145 | READ | USER | obj.get_profile().get_foto_150x200_url_publica() | ALTA |
| api/schemas/ensino.py:434 | READ | SERVIDOR | professordiario.professor.get_foto_75x100_url_publica() | ALTA |

#### AMBIGUOUS (vinculo.relacionamento.pessoa_fisica / sem papel claro)

| file:line | read/write | fonte-vínculo | contexto/expr | confiança |
|-----------|-----------|---------------|---------------|-----------|
| pesquisa/admin.py:1780 | READ | AMBIGUOUS | obj.vinculo.pessoa.pessoafisica.get_foto_75x100_url() | MÉDIA |
| pesquisa/forms.py:794 | READ | AMBIGUOUS | obj.get_foto_75x100_url() — obj pode ser Servidor ou Aluno | MÉDIA |
| pesquisa/forms.py:993 | READ | AMBIGUOUS | obj.pessoa_fisica.get_foto_75x100_url() — obj pode ser Servidor/PrestadorServico | MÉDIA |
| pesquisa/forms.py:5131 | READ | AMBIGUOUS | relacionamento.get_foto_75x100_url() | MÉDIA |
| pesquisa/forms.py:5167 | READ | AMBIGUOUS | relacionamento.pessoa_fisica.get_foto_75x100_url() | MÉDIA |
| eleicao/models.py:564 | READ | AMBIGUOUS | vinculo.relacionamento.pessoa_fisica.get_foto_75x100_url() | ALTA |
| eleicao/models.py:680 | READ | AMBIGUOUS | pessoa_fisica.get_foto_75x100_url() — get_foto_eleitor | ALTA |
| comum/admin.py:487 | READ | AMBIGUOUS | solicitacao.solicitante_vinculo.pessoa.pessoafisica.foto | ALTA |
| comum/admin.py:576 | READ | AMBIGUOUS | obj.solicitante_vinculo.pessoa.pessoafisica.get_foto_75x100_url() | ALTA |
| comum/admin.py:790 | READ | AMBIGUOUS | obj.pessoa_fisica.get_foto_75x100_url() | ALTA |
| comum/forms.py:1067 | READ | AMBIGUOUS | solicitante_vinculo.pessoa.pessoafisica.foto is None | ALTA |
| comum/models.py:906 | READ | AMBIGUOUS | vinculo.pessoa.pessoa_fisica.get_foto_75x100_url() | ALTA |
| comum/models.py:2088 | READ | AMBIGUOUS | self.pessoa_fisica.get_foto_75x100_url() | ALTA |
| comum/views.py:3502 | READ | AMBIGUOUS | vinculo.relacionamento.pessoa_fisica.get_foto_150x200_url | ALTA |
| projetos/forms.py:833 | READ | AMBIGUOUS | obj.get_foto_75x100_url() — pode ser Servidor/Aluno/PrestadorServico | MÉDIA |
| projetos/forms.py:953 | READ | AMBIGUOUS | obj.pessoa_fisica.get_foto_75x100_url() | MÉDIA |
| projetos_ensino/forms.py:587 | READ | AMBIGUOUS | obj.pessoa_fisica.get_foto_75x100_url() | MÉDIA |
| chaves/forms.py:70 | READ | AMBIGUOUS | self.get_foto_75x100_url() — objeto com pessoa_fisica | MÉDIA |
| etep/admin.py:61 | READ | ALUNO | obj.aluno.get_foto_75x100_url() | ALTA |
| etep/admin.py:197 | READ | USER | obj.solicitante.get_profile().get_foto_75x100_url() | ALTA |
| demandas/views.py:1114 | READ | USER | atualizador.usuario.get_profile().get_foto_75x100_url | ALTA |
| rh/admin.py:1999 | READ | SERVIDOR | obj.vinculo.user.get_profile().get_foto_75x100_url() | ALTA |
| portaria/forms.py:64 | READ | AMBIGUOUS | self.instance.vinculo.pessoa.pessoafisica.get_foto_150x200_url() | ALTA |
| portaria/forms.py:105 | READ | AMBIGUOUS | self.instance.pessoa_externa.get_foto_150x200_url() — PessoaExterna tem foto própria, ver portaria/models.py | ALTA |
| portaria/views.py:108 | READ | AMBIGUOUS | pessoa_externa.get_foto_150x200_url() — PessoaExterna.foto | RUÍDO |

---

## 3. RUÍDO excluído

| file:line | motivo |
|-----------|--------|
| patrimonio/models.py:978 | FotoInventario.foto (próprio campo) |
| patrimonio/views.py:655 | nova_foto.foto — modelo patrimônio |
| patrimonio/views.py:878 | fotoinventario.foto.read() — modelo patrimônio |
| portaria/models.py:86-87,92-93 | PessoaExterna.foto (campo próprio linha 56) |
| eventos/models.py:3008 | Participante.foto (campo próprio linha 2645) |
| rh/admin.py:2783 | SolicitacaoAlteracaoFoto.foto (campo próprio linha 20) |
| edu/models/internacionalizacao.py:489 | InscricaoAlunoEstrangeiro.foto (campo próprio linha 223) |
| edu/forms/internacionalizacao.py:215,217 | self.instance = InscricaoAlunoEstrangeiro |
| portaria/views.py:108 | PessoaExterna.foto própria |
| rh/models/pessoa/abstract.py:48-49 | comentário, não código |
| rh/models/pessoa/abstract.py:46 | comentário |
| rh/models/pessoa/pessoa_fisica.py:(field def) | definição do campo, não call-site |
| portaria/views.py:89 | linha comentada |
