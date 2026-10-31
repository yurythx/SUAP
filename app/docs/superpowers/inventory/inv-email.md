# Inventário: campo `email` (→ `Vinculo.email_pessoal`)

## 1. Tally

| Métrica | Valor |
|---|---|
| Hits brutos (`grep -rIn '\.email\b'`) | 322 |
| Sites REAIS (Pessoa/PessoaFisica.email) | 68 |
| READ | 67 |
| WRITE | 1 |
| Ruído descartado | 254 |

**Ruído principal:** `User.email`, `Setor.email`, `candidato.email` (Candidato próprio), `participante.email` (Participante próprio), `avaliador.email` (AvaliadorExterno/pesquisa/projetos — campo próprio), `Endereco.email` (cnpq), `coordenador.email` em estagios (User queryset), paths ORM como strings (`'pessoa_fisica.email'`), SQL raw, kwargs, PessoaJuridica.

**Split por fonte-de-vínculo:**
| Fonte | Sites |
|---|---|
| SERVIDOR | 28 |
| ALUNO | 17 |
| AMBIGUOUS (Pessoa/PF/self/Vinculo sem papel claro) | 16 |
| USER (via `get_profile()`) | 6 |
| PRESTADOR | 1 |

---

## 2. Tabela

| file:line | R/W | fonte-vínculo | contexto/expr | confiança |
|---|---|---|---|---|
| remanejamento/models.py:350 | R | SERVIDOR | `inscricao.servidor.pessoa_fisica.email` | alta |
| acompanhamentofuncional/models.py:164 | R | SERVIDOR | `servidor_cedido.pessoa_fisica.email` (guard) | alta |
| acompanhamentofuncional/models.py:167 | R | SERVIDOR | `chefe_imediato.pessoa_fisica.email` (guard) | alta |
| temp_rh2/admin.py:244 | R | SERVIDOR | `obj.servidor.pessoa_fisica.email` | alta |
| edu/educacenso.py:1040 | R | SERVIDOR | `servidor.pessoa_fisica.email` (guard) | alta |
| edu/educacenso.py:1041 | R | SERVIDOR | `servidor.pessoa_fisica.email.upper()` | alta |
| pgd/views.py:686 | R | SERVIDOR | `participante.servidor.pessoa_fisica.email` (guard) | alta |
| ldap_backend/models.py:491 | R | SERVIDOR | `obj.pessoa_fisica.email` (Servidor, in `_get_emails_notificacao_inativacao`) | alta |
| pesquisa/tasks.py:31 | R | SERVIDOR | `avaliador.pessoa_fisica.email` (avaliadores = Servidor.objects) | alta |
| rh/admin.py:872 | R | SERVIDOR | `obj.pessoa_fisica.email` (ServidorAdmin.get_info) | alta |
| rh/admin.py:969 | R | SERVIDOR | `servidor.pessoa_fisica.email` (export XLS) | alta |
| rh/admin.py:2648 | R | SERVIDOR | `obj.solicitante.pessoa_fisica.email` (obj.solicitante é Servidor) | alta |
| rh/models/carreira/servidor.py:675 | R | SERVIDOR | `self.pessoa_fisica.email` (Servidor.tem_acesso_servicos_microsoft) | alta |
| contratos/views.py:2290 | R | SERVIDOR | `fiscal.servidor.pessoa_fisica.email` | alta |
| contratos/views.py:2312 | R | SERVIDOR | `fiscal.servidor.pessoa_fisica.email` | alta |
| contratos/models.py:1919 | R | SERVIDOR | `fiscal.servidor.pessoa_fisica.email` (list comp em get_emails_notificar) | alta |
| projetos/models.py:2790 | R | SERVIDOR | `self.vinculo.relacionamento.pessoa_fisica.email` (branch eh_servidor) | alta |
| projetos_ensino/models.py:1874 | R | SERVIDOR | `self.vinculo.relacionamento.pessoa_fisica.email` (branch eh_servidor) | alta |
| projetos/views.py:6576 | R | SERVIDOR | `pessoa.relacionamento.pessoa_fisica.email` (Vinculo.exclude(aluno)) | alta |
| projetos/views.py:6577 | R | SERVIDOR | `avaliadores_internos.add(pessoa.relacionamento.pessoa_fisica.email)` | alta |
| pesquisa/admin.py:1804 | R | SERVIDOR | `obj.vinculo.pessoa.pessoafisica.email` (pessoafisica lookup) | alta |
| eleicao/models.py:592 | R | SERVIDOR | `subinstance.pessoa_fisica.email` (`isinstance(subinstance, Servidor)` branch) | alta |
| eleicao/models.py:702 | R | SERVIDOR | `subinstance.email` (Servidor via `__getattr__` → `pessoa_fisica.email`) | alta |
| rh/views.py:2006 | R | SERVIDOR | `s.email` (s=Servidor; via `__getattr__` → `pessoa_fisica.email`) | alta |
| microsoft/views.py:35 | R | SERVIDOR | `servidor.pessoa_fisica.email` (guard) | alta |
| microsoft/views.py:38 | R | SERVIDOR | `servidor.pessoa_fisica.email` (get_dreamspark_url) | alta |
| comum/models.py:807 | R | SERVIDOR | `self.relacionamento.pessoa_fisica.email` (Vinculo.get_email, branch `eh_servidor`) | alta |
| rh/admin.py:1915 | R | USER | `obj.vinculo.user.get_profile().email` (AvaliadorAdmin export) | alta |
| edu/admin/alunos.py:153 | R | ALUNO | `obj.pessoa_fisica.email` (obj=Aluno) | alta |
| edu/admin/estagio_docente.py:150 | R | ALUNO | `aluno.pessoa_fisica.email` (guard) | alta |
| edu/models/diplomas.py:956 | R | ALUNO | `aluno.pessoa_fisica.email` (guard) | alta |
| edu/models/diplomas.py:957 | R | ALUNO | `aluno.pessoa_fisica.email` | alta |
| edu/models/diplomas.py:1419 | R | ALUNO | `aluno.pessoa_fisica.email` (guard) | alta |
| edu/models/diplomas.py:1420 | R | ALUNO | `aluno.pessoa_fisica.email` | alta |
| edu/models/diarios.py:1020 | R | ALUNO | `aluno.pessoa_fisica.email` (guard em nota) | alta |
| estagios/models.py:263 | R | ALUNO | `self.aluno.pessoa_fisica.email` (guard) | alta |
| estagios/models.py:264 | R | ALUNO | `self.aluno.pessoa_fisica.email` | alta |
| estagios/models.py:1103 | R | ALUNO | `self.aprendiz.pessoa_fisica.email` (guard) | alta |
| estagios/models.py:1104 | R | ALUNO | `self.aprendiz.pessoa_fisica.email` | alta |
| estagios/models.py:4012 | R | ALUNO | `self.aluno.pessoa_fisica.email` (guard) | alta |
| estagios/models.py:4013 | R | ALUNO | `self.aluno.pessoa_fisica.email` | alta |
| microsoft/views.py:18 | R | ALUNO | `aluno.pessoa_fisica.email` (guard) | alta |
| microsoft/views.py:21 | R | ALUNO | `aluno.pessoa_fisica.email` (get_dreamspark_url) | alta |
| edu/views/eventos.py:324 | R | ALUNO | `participante_evento.participante.pessoa.pessoafisica.email` (guard) | alta |
| edu/views/eventos.py:339 | R | ALUNO | `pessoafisica.email.strip()` (to list) | alta |
| edu/models/comunicador.py:38 | R | ALUNO | `qs_alunos.values_list('pessoa_fisica__email', flat=True)` (ORM traversal) | alta |
| comum/services/icp_edu.py:34 | R | USER | `self.signer.email` (signer=user.get_profile()=PF) | alta |
| comum/services/icp_edu.py:37 | R | USER | `self.signer.email` (no payload dict) | alta |
| djtools/forms/__init__.py:49 | R | USER | `request.user.get_profile().email` (remetente initial) | alta |
| edu/models/comunicador.py:39 | R | USER | `self.remetente.get_profile().email` (User remetente) | alta |
| edu/models/comunicador.py:44 | R | USER | `coordenador.get_profile().email` (User coordenador) | alta |
| edu/models/comunicador.py:47 | R | USER | `diretor.get_profile().email` (User diretor) | alta |
| rh/models/pessoa/pessoa_fisica.py:601 | R | AMBIGUOUS | `self.email` (PF.emails property, self=PessoaFisica) | alta |
| rh/models/pessoa/pessoa_fisica.py:602 | R | AMBIGUOUS | `lista.append(self.email)` (PF.emails property) | alta |
| ponto/models.py:2730 | R | AMBIGUOUS | `pessoa.email` (pessoa=vinculo_pessoa.pessoa → Pessoa.email) | alta |
| comum/admin.py:559 | R | AMBIGUOUS | `obj.solicitante_vinculo.pessoa.email` (Pessoa.email) | média |
| projetos/admin.py:464 | R | AMBIGUOUS | `coordenador.pessoa.email` (Vinculo.pessoa → Pessoa.email) | alta |
| projetos/tasks.py:201 | R | AMBIGUOUS | `coordenador.pessoa.email` (Vinculo.pessoa → Pessoa.email) | alta |
| projetos_ensino/admin.py:234 | R | AMBIGUOUS | `coordenador.pessoa.email` (Vinculo.pessoa → Pessoa.email) | alta |
| projetos_ensino/tasks.py:75 | R | AMBIGUOUS | `coordenador.pessoa.email` (Vinculo.pessoa → Pessoa.email) | alta |
| pesquisa/views.py:7391 | R | AMBIGUOUS | `projeto.vinculo_coordenador.pessoa.email` (Pessoa.email) | alta |
| api/schemas/ensino.py:1075 | R | AMBIGUOUS | `obj.vinculo.pessoa.email` (Pessoa.email via Vinculo, resolve_email_institucional) | alta |
| patrimonio/admin.py:73 | R | AMBIGUOUS | `obj.vinculo.pessoa.email` (Pessoa.email) | alta |
| patrimonio/admin.py:91 | R | AMBIGUOUS | `obj.vinculo.pessoa.email` (Pessoa.email, XLS export) | alta |
| contratos/models.py:1920 | R | AMBIGUOUS | `vinculo_contratado.pessoa.email` (pode ser PJ ou PF) | média |
| contratos/views.py:1942 | R | AMBIGUOUS | `vinculo_contratado.pessoa.email` (guard; pode ser PJ) | média |
| contratos/views.py:1964 | R | AMBIGUOUS | `vinculo_contratado.pessoa.email` (guard; pode ser PJ) | média |
| projetos_ensino/forms.py:2430 | R | PRESTADOR | `avaliador.email = email` — avaliador.pessoa_fisica=PrestadorServico → WRITE na PF | W |
| edu/forms/mini_cursos.py:189 | W | AMBIGUOUS | `pessoa_fisica.email = participante['email']` (novo PF criado no momento) | alta |

---

## 3. Arquivos com mais sites AMBIGUOUS

1. **projetos/** (admin.py + tasks.py + models.py + views.py) — 4 sites, todos via `coordenador.pessoa.email` / `vinculo_coordenador.pessoa.email` / `vinculo.relacionamento.pessoa_fisica.email`
2. **projetos_ensino/** (admin.py + tasks.py + models.py) — 3 sites, mesmos padrões espelhados de projetos
3. **contratos/** (models.py + views.py) — 3 sites via `vinculo_contratado.pessoa.email` (papel indefinido — pode ser PJ)

---

## Notas para reescrita

- **`Pessoa.email`** (acessado via `vinculo.pessoa.email`, `vinculo_coordenador.pessoa.email`, etc.) e **`PessoaFisica.email`** são o **mesmo campo** — `PessoaFisica` herda de `Pessoa` via `pessoa_ptr`.
- **`AbstractFuncionario.__getattr__`** delega atributos não encontrados para `pessoa_fisica`; `servidor.email` e `s.email` sobre Servidor acessam `pessoa_fisica.email` implicitamente.
- **`edu/models/comunicador.py:38`** usa ORM traversal `values_list('pessoa_fisica__email', flat=True)` — precisará de `values_list('pessoa_fisica__vinculo_set__email_pessoal', flat=True)` ou equivalente após migração.
- **`contratos/models.py` + views lines 1942/1964** — verificar se `vinculo_contratado` pode ser PessoaJuridica; se sim, esses sites podem ser fora do escopo da migração.
- **WRITE único real em PF:** `edu/forms/mini_cursos.py:189` — PessoaFisica nova sendo construída.
