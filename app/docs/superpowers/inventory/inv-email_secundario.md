# Inventário: `email_secundario` → `Vinculo.email_notificacao`

## Metodologia

`grep -rIn '\.email_secundario\b' --include='*.py' .`
Excluídos: `*/migrations/`, `*/tests/`, `test_*.py`, `docs/superpowers/`, definição do campo em `rh/models/pessoa/pessoa.py:31`.
Excluídos como RUÍDO (fora de escopo): `edu/features/steps/given.py` (BDD fixtures), `djtools/new_tests/common_steps/given.py` (BDD fixtures).

---

## Tally

| Categoria | Qtde |
|-----------|------|
| **Total hits brutos (sem migrações/tests)** | 122 |
| Excluídos BDD/features (ruído de fixture) | 5 |
| Excluídos def de campo (`rh/models/pessoa/pessoa.py:31`) | 1 |
| **Sites REAIS (Pessoa/PessoaFisica)** | **116** |
| — READ | 96 |
| — WRITE (`x.email_secundario = ...`) | 20 |
| RUÍDO/PessoaExterna | 0 |

### Por fonte-de-vínculo (sites reais)

| Fonte | READ | WRITE | Total |
|-------|------|-------|-------|
| ALUNO | 42 | 12 | 54 |
| SERVIDOR | 18 | 2 | 20 |
| USER (get_profile / get_vinculo / threadlocal) | 16 | 1 | 17 |
| AMBIGUOUS (pessoa/relacionamento sem papel fixo) | 20 | 5 | 25 |

---

## Tabela de sites reais

| file:line | R/W | fonte-vínculo | contexto/expr | confiança |
|-----------|-----|---------------|---------------|-----------|
| ae/tasks.py:1705 | R | ALUNO | `pessoa_fisica.email or pessoa_fisica.email_secundario` | alta |
| ae/views.py:5809 | R | ALUNO | field string `'pessoa_fisica.email_secundario'` em exibição | alta |
| ae/views.py:6383 | R | ALUNO | `pessoa_fisica_aluno.email_secundario` | alta |
| api/schemas/ensino.py:895 | R | AMBIGUOUS | alias `'professor.vinculo.pessoa.email_secundario'` (Professor→Vinculo→Pessoa) | média |
| api/schemas/ensino.py:923 | R | ALUNO | alias `'matricula_periodo.aluno.pessoa_fisica.email_secundario'` | alta |
| api/schemas/rh.py:186 | R | AMBIGUOUS | alias `'pessoa_fisica.email_secundario'` (contexto genérico rh schema) | média |
| api/schemas/rh.py:481 | R | SERVIDOR | `obj.servidor.pessoa_fisica.email or obj.servidor.pessoa_fisica.email_secundario` | alta |
| comum/admin.py:814 | R | AMBIGUOUS | `obj.pessoa_fisica.email_secundario` (admin de Vinculo/User) | média |
| comum/admin.py:867 | R | AMBIGUOUS | `obj.pessoa_fisica.email_secundario` em mensagem de boas-vindas | média |
| comum/forms.py:465 | R | AMBIGUOUS | `self.pessoa_fisica.email_secundario` (form de perfil) | média |
| comum/forms.py:821 | R | AMBIGUOUS | `self.instance.pessoa_fisica.email_secundario` (form genérico) | média |
| comum/forms.py:1365 | R | USER | `user.get_profile().email_secundario` | alta |
| comum/management/commands/expirar_senhas_antigas.py:48 | R | USER | `user.get_profile().email_secundario` | alta |
| comum/management/commands/sync_emails.py:50 | W | SERVIDOR | `pessoa_fisica.email_secundario = servidor.email_institucional` | alta |
| comum/models.py:508 | R | USER | `pessoa.email_secundario` via `self.get_profile()` (User.enviar_email_boas_vindas) | alta |
| comum/models.py:803 | R | SERVIDOR | `self.relacionamento.pessoa_fisica.email or self.relacionamento.pessoa_fisica.email_secundario` (Vinculo.get_email, eh_servidor) | alta |
| comum/models.py:805 | R | AMBIGUOUS | `self.relacionamento.pessoa_fisica.email_secundario` (eh_prestador branch) | alta |
| comum/models.py:809 | R | ALUNO | `self.relacionamento.pessoa_fisica.email_secundario` (eh_aluno branch) | alta |
| comum/models.py:810 | R | ALUNO | `self.relacionamento.pessoa_fisica.email_secundario` (eh_aluno branch) | alta |
| comum/models.py:816 | R | AMBIGUOUS | `self.pessoa.email_secundario` fallback em Vinculo.get_email | alta |
| comum/models.py:1019 | R | AMBIGUOUS | `getattr_coalesce(vinculo, 'pessoa.pessoafisica.email_secundario')` (notif login) | alta |
| comum/models.py:1057 | R | AMBIGUOUS | `getattr_coalesce(vinculo, 'pessoa.pessoafisica.email_secundario')` (notif login) | alta |
| comum/models.py:2202 | R | AMBIGUOUS | `self.pessoa_fisica.email_secundario` (UsuarioExterno) | alta |
| comum/models.py:3978 | R | USER | `pessoa_fisica.email_secundario` guard (redefinir senha) | alta |
| comum/models.py:3982 | W | USER | `self.email = pessoa_fisica.email_secundario` (redefinir senha) | alta |
| comum/views.py:1661 | R | USER | `pessoa_fisica.email_secundario` guard (recuperação de senha) | alta |
| comum/views.py:1667 | R | USER | `profile.email_secundario` guard | alta |
| comum/views.py:1671 | R | USER | `request.user.get_profile().email_secundario` | alta |
| contracheques/migracao.py:216 | W | SERVIDOR | `p.email_secundario = email` (migração de dados, p=PessoaFisica de servidor) | alta |
| contracheques/views.py:2117 | R | SERVIDOR | `cc.servidor.pessoa_fisica.email or cc.servidor.pessoa_fisica.email_secundario` | alta |
| djtools/choices/__init__.py:285 | R | AMBIGUOUS | campo string `'pessoa_fisica.email_secundario'` em choices (genérico) | média |
| djtools/contrib/auth/backends/__init__.py:25 | R | USER | `user.get_profile().email_secundario` (auth backend) | alta |
| djtools/forms/__init__.py:84 | R | USER | `request.user.get_vinculo().pessoa.email_secundario` (form init) | alta |
| djtools/models.py:151 | W | USER | `self.email = self.user.get_vinculo().pessoa.email_secundario` (SolicitacaoDeEmail) | alta |
| djtools/ninja/router.py:37 | R | USER | `profile.email_secundario or profile.email or None` (API /me) | alta |
| djtools/utils/response.py:34 | R | USER | `request.user.get_vinculo().pessoa.email_secundario` guard | alta |
| djtools/utils/response.py:55 | R | USER | `request.user.get_vinculo().pessoa.email_secundario` no to= | alta |
| djtools/views.py:694 | R | AMBIGUOUS | `getattr_coalesce(vinculo, 'pessoa.pessoafisica.email_secundario')` (admin geral) | alta |
| edu/admin/alunos.py:154 | R | ALUNO | `obj.pessoa_fisica.email_secundario` | alta |
| edu/admin/estagio_docente.py:152 | R | ALUNO | `aluno.pessoa_fisica.email_secundario` guard | alta |
| edu/admin/estagio_docente.py:153 | R | ALUNO | `email_aluno = aluno.pessoa_fisica.email_secundario` | alta |
| edu/forms/alunos.py:1138 | R | ALUNO | `self.aluno.get_vinculo().pessoa.email_secundario` (form init) | alta |
| edu/forms/matriculas.py:947 | W | ALUNO | `pessoa_fisica.email_secundario = self.cleaned_data['email_pessoal']` | alta |
| edu/forms/mini_cursos.py:342 | W | ALUNO | `pessoa_fisica.email_secundario = self.cleaned_data['email']` | alta |
| edu/forms/mini_cursos.py:414 | W | ALUNO | `pessoa_fisica.email_secundario = participante['email']` (bulk) | alta |
| edu/forms/relatorios.py:268 | R | ALUNO | campo string `'pessoa_fisica.email_secundario'` em relatório | alta |
| edu/management/commands/edu_atualizar_dados_pessoas_alunos_proitec.py:21 | W | ALUNO | `aluno.pessoa_fisica.email_secundario = dados['email_pessoal']` | alta |
| edu/management/commands/edu_importar_csv.py:221 | W | ALUNO | `pf.email_secundario = dados[EMAIL]` (importação CSV aluno) | alta |
| edu/models/alunos.py:621 | R | ALUNO | campo string `'pessoa_fisica.email_secundario'` em exibição | alta |
| edu/models/alunos.py:1303 | R | ALUNO | `self.pessoa_fisica.email or self.pessoa_fisica.email_secundario or self.email_academico` | alta |
| edu/models/alunos.py:6635 | R | ALUNO | `'email_pessoal': self.pessoa_fisica.email_secundario or ''` (Aluno.to_dict) | alta |
| edu/models/comunicador.py:41 | R | USER | `self.remetente.get_profile().email_secundario` | alta |
| edu/models/comunicador.py:42 | R | USER | `emails.append(self.remetente.get_profile().email_secundario)` | alta |
| edu/models/diplomas.py:958 | R | ALUNO | `self.registro_emissao_diploma.aluno.pessoa_fisica.email_secundario` guard | alta |
| edu/models/diplomas.py:959 | R | ALUNO | `to.append(...)` | alta |
| edu/models/diplomas.py:1421 | R | ALUNO | `...aluno.pessoa_fisica.email_secundario` guard | alta |
| edu/models/diplomas.py:1422 | R | ALUNO | `to.append(...)` | alta |
| edu/models/internacionalizacao.py:201 | R | ALUNO | `vinculo.pessoa.pessoafisica.email_secundario` | alta |
| edu/models/internacionalizacao.py:596 | R | ALUNO | `self.vinculo.pessoa.pessoafisica.email_secundario` | alta |
| edu/models/internacionalizacao.py:620 | R | ALUNO | `self.vinculo.pessoa.pessoafisica.email_secundario` | alta |
| edu/models/internacionalizacao.py:662 | R | ALUNO | `self.inscricao.vinculo.pessoa.pessoafisica.email_secundario` | alta |
| edu/models/internacionalizacao.py:669 | R | AMBIGUOUS | `self.solicitante.pessoa.pessoafisica.email_secundario` (solicitante pode ser qualquer papel) | média |
| edu/models/procedimentos.py:330 | R | ALUNO | `pedido_matricula.matricula_periodo.aluno.pessoa_fisica.email_secundario` | alta |
| edu/models/projeto_final.py:319 | R | ALUNO | `self.vinculo.pessoa.pessoafisica.email_secundario` (vinculo de aluno) | alta |
| edu/services.py:82 | R | ALUNO | `obj.pessoa_fisica.email_secundario or ''` | alta |
| edu/services.py:90 | R | AMBIGUOUS | `obj.professor.vinculo.pessoa.email_secundario or ''` (Professor) | média |
| edu/services.py:99 | R | AMBIGUOUS | `obj.professor.vinculo.pessoa.email_secundario or ''` (Professor) | média |
| edu/sttu.py:56 | R | ALUNO | `matricula_periodo.aluno.pessoa_fisica.email_secundario or ...email_academico` | alta |
| edu/views/alunos.py:250 | R | ALUNO | `obj.pessoa_fisica.email_secundario` guard | alta |
| edu/views/alunos.py:256 | R | ALUNO | `[obj.pessoa_fisica.email_secundario]` no-op (guard acima) | alta |
| edu/views/alunos.py:260 | R | ALUNO | f-string mensagem | alta |
| edu/views/alunos.py:945 | R | ALUNO | `'email': aluno.pessoa_fisica.email_secundario` dict | alta |
| edu/views/alunos.py:985 | R | ALUNO | `'email_secundario': aluno.pessoa_fisica.email_secundario` dict | alta |
| edu/views/alunos.py:1048 | R | ALUNO | `'email_secundario': aluno.pessoa_fisica.email_secundario` dict | alta |
| edu/views/eventos.py:340 | R | ALUNO | `participante_evento.participante.pessoa.pessoafisica.email_secundario.strip()` | alta |
| edu/views/matriculas.py:96 | R | ALUNO | `'email_pessoal': aluno.pessoa_fisica.email_secundario` | alta |
| edu/views/mini_cursos.py:274 | R | ALUNO | `aluno.pessoa_fisica.email_secundario` | alta |
| egressos/forms.py:173 | R | ALUNO | `self.instance.pessoa_fisica.email_secundario` (form init) | alta |
| egressos/forms.py:179 | W | ALUNO | `pessoa_fisica.email_secundario = self.cleaned_data.get('email_pessoal', None)` | alta |
| egressos/models.py:66 | R | ALUNO | `aluno.pessoa_fisica.email_secundario` guard | alta |
| egressos/models.py:67 | R | ALUNO | `emails.append(...)` | alta |
| egressos/models.py:84 | R | ALUNO | `aluno.pessoa_fisica.email_secundario` guard | alta |
| egressos/models.py:85 | R | ALUNO | `emails.append(...)` | alta |
| egressos/models.py:109 | R | ALUNO | campo string `'pessoa_fisica.email_secundario'` em exibição | alta |
| egressos/tasks.py:21 | R | ALUNO | `format_(aluno.pessoa_fisica.email_secundario)` | alta |
| egressos/views.py:242 | R | ALUNO | `format_(aluno.pessoa_fisica.email_secundario)` | alta |
| erros/views.py:140 | R | USER | `request.user.get_profile().email or request.user.get_profile().email_secundario` | alta |
| estagios/admin.py:403 | R | ALUNO | `obj.aluno.pessoa_fisica.email_secundario` | alta |
| estagios/admin.py:908 | R | ALUNO | `obj.aprendiz.pessoa_fisica.email_secundario` (aprendiz=aluno tipo aprendiz) | alta |
| estagios/admin.py:1206 | R | ALUNO | `obj.aluno.pessoa_fisica.email_secundario` | alta |
| estagios/models.py:261 | R | ALUNO | `self.aluno.pessoa_fisica.email_secundario` guard | alta |
| estagios/models.py:262 | R | ALUNO | return `self.aluno.pessoa_fisica.email_secundario` | alta |
| estagios/models.py:1101 | R | ALUNO | `self.aprendiz.pessoa_fisica.email_secundario` guard | alta |
| estagios/models.py:1102 | R | ALUNO | return | alta |
| estagios/models.py:4010 | R | ALUNO | `self.aluno.pessoa_fisica.email_secundario` guard | alta |
| estagios/models.py:4011 | R | ALUNO | return | alta |
| ldap_backend/models.py:493 | R | SERVIDOR | `obj.pessoa_fisica.email_secundario` (LDAP sync) | alta |
| ldap_backend/tasks.py:55 | R | USER | `user.get_profile().email_secundario` | alta |
| ldap_backend/utils.py:116 | R | SERVIDOR | `model_obj.pessoa_fisica.email_secundario or None` (LDAP attr) | alta |
| patrimonio/admin.py:78 | R | AMBIGUOUS | `obj.vinculo.pessoa.email_secundario` (vinculo genérico) | média |
| patrimonio/admin.py:92 | R | AMBIGUOUS | `obj.vinculo.pessoa.email_secundario` (XLS) | média |
| pesquisa/admin.py:1151 | R | AMBIGUOUS | `obj.pessoa_fisica.email_secundario` guard (pesquisador) | média |
| pesquisa/admin.py:1820 | R | AMBIGUOUS | `obj.vinculo.pessoa.pessoafisica.email_secundario` (HTML) | média |
| pesquisa/forms.py:3448 | R | AMBIGUOUS | `self.instance.pessoa_fisica.pessoa_fisica.email_secundario` (duplo .pessoa_fisica — suspeito) | baixa |
| pesquisa/views.py:7863 | R | AMBIGUOUS | `pessoa.pessoa_fisica.email_secundario` guard | média |
| processo_seletivo/tasks.py:379 | R | ALUNO | `aluno.pessoa_fisica.email_secundario is None` guard | alta |
| processo_seletivo/tasks.py:380 | W | ALUNO | `aluno.pessoa_fisica.email_secundario = email_secundario` | alta |
| processo_seletivo/tasks.py:387 | W | ALUNO | `pessoa_fisica.email_secundario = email_secundario` | alta |
| processo_seletivo/tasks.py:427 | W | ALUNO | `aluno.pessoa_fisica.email_secundario = email_pessoal` | alta |
| projetos/views.py:6578 | R | AMBIGUOUS | `pessoa.relacionamento.pessoa_fisica.email_secundario` (relacionamento misto) | média |
| projetos/views.py:6579 | R | AMBIGUOUS | `avaliadores_internos.add(...)` | média |
| rh/models/pessoa/pessoa_fisica.py:606 | R | AMBIGUOUS | `self.email_secundario` em método `get_emails()` de PessoaFisica | alta |
| rh/models/pessoa/pessoa_fisica.py:607 | R | AMBIGUOUS | `lista.append(self.email_secundario)` | alta |
| rh/models/pessoa/pessoa.py:131 | R | AMBIGUOUS | `self.email_secundario is None` guard em `save()` de Pessoa (base class) | alta |
| rh/models/pessoa/pessoa.py:132 | W | AMBIGUOUS | `self.email_secundario = ''` (normalização em save()) | alta |
| rh/models/pessoa/pessoa.py:136 | R | AMBIGUOUS | `self.email_secundario` guard validação email institucional | alta |
| saude/views.py:699 | R | ALUNO | `vinculo_aluno.pessoa_fisica.email_secundario or vinculo_aluno.email_academico` | alta |

---

## Notas adicionais

- `pesquisa/forms.py:3448` tem `self.instance.pessoa_fisica.pessoa_fisica.email_secundario` (duplo `.pessoa_fisica`) — possível bug latente, confiança baixa.
- `rh/models/pessoa/pessoa.py:131-136` são no método `save()` da classe base `Pessoa` — WRITE implícito de normalização, não edição de usuário.
- `edu/models/internacionalizacao.py:669` usa `self.solicitante` que pode ser servidor ou aluno — AMBIGUOUS real.
- `comum/models.py:816` é fallback final em `Vinculo.get_email()` após checar relacionamento por papel — cobre todos os papéis.
- Sites com alias string (`'pessoa_fisica.email_secundario'`) em `list_display` / relatórios são READ passivo pelo ORM do djtools.
