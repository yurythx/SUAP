# Inventário de call-sites: setores_adicionais, sistema_origem, povo_indigena, deficiencia, raca

## Tally

- **Total de sites reais**: 36
- **READ**: 29 | **WRITE**: 7
- **Por fonte-de-vínculo**:
  - SERVIDOR: 11
  - ALUNO: 18
  - USER (via vinculo.pessoa): 1
  - AMBIGUOUS: 6
- **Hits brutos excluídos como RUÍDO**: ≈30
  (strings/dicts em `enquete/tasks.py`, `rh/tasks.py`, `ae/views.py`, `djtools/choices/__init__.py`, `edu/validators.py`, `edu/forms/relatorios.py`; SQL strings em `gestao/models.py`; objetos não-PF em `saude/admin.py` [Caracterizacao], `financeiro/importador.py` [NotaCredito/NotaSistema], `processo_seletivo/` [Candidato.aprovado_deficiencia]; features BDD em `edu/features/steps/given.py` e `catalogo_provedor_servico/features/steps/given.py`; self.raca em `edu/models/internacionalizacao.py` [InscricaoAlunoEstrangeiro, não PF])

**Nota sobre setores_adicionais e sistema_origem**: ambos são campos de `Pessoa` (não `PessoaFisica`); PessoaFisica herda de Pessoa via MTI. Servidor acessa via `__getattribute__` proxy → `self.pessoa_fisica`. A migração para Vinculo afeta também esses campos em Pessoa.

**Nota sobre deficiencia**: nenhum hit real `.deficiencia` em PessoaFisica encontrado (os hits em `processo_seletivo/` são `Candidato.aprovado_deficiencia`, campo diferente).

---

## Tabela de sites reais

| file:line | campo | r/w | fonte-vínculo | contexto/expr | conf |
|-----------|-------|-----|---------------|---------------|------|
| `protocolo/views.py:39` | setores_adicionais | READ | USER | `vinculo.pessoa.setores_adicionais.all()` — `vinculo = request.user.get_vinculo()` | high |
| `rh/forms.py:954` | setores_adicionais | READ | SERVIDOR | `self.instance.setores_adicionais.all()` — ServidorForm (model=Servidor), via proxy __getattribute__ → pessoa_fisica | high |
| `rh/models/carreira/servidor.py:217` | setores_adicionais | WRITE | SERVIDOR | `pessoa_fisica.setores_adicionais.set(setores_adicionais)` — em `Servidor.importar_siape()` | high |
| `saude/views.py:505` | setores_adicionais | READ | SERVIDOR | `servidor.pessoa_fisica.setores_adicionais.all()` | high |
| `comum/utils.py:203` | setores_adicionais | READ | AMBIGUOUS | `profile.setores_adicionais.values_list('id', flat=True)` — `profile = user.get_profile()` (Servidor/Aluno/Prestador via __getattribute__) | high |
| `edu/educacenso.py:775` | povo_indigena | READ | SERVIDOR | `servidor.pessoa_fisica.povo_indigena` | high |
| `edu/educacenso.py:778` | povo_indigena | READ | SERVIDOR | `servidor.pessoa_fisica.povo_indigena.codigo_educacenso` | high |
| `edu/educacenso.py:1092` | povo_indigena | READ | ALUNO | `aluno.pessoa_fisica.povo_indigena` | high |
| `edu/educacenso.py:1095` | povo_indigena | READ | ALUNO | `aluno.pessoa_fisica.povo_indigena.codigo_educacenso` | high |
| `edu/forms/alunos.py:246` | povo_indigena | WRITE | ALUNO | `self.instance.pessoa_fisica.povo_indigena = ...` — AlunoForm (model=Aluno) | high |
| `edu/forms/matriculas.py:949` | povo_indigena | WRITE | ALUNO | `pessoa_fisica.povo_indigena = ...` — EfetuarMatriculaForm.processar(), `pessoa_fisica = PessoaFisica()` nova | high |
| `edu/models/internacionalizacao.py:498` | povo_indigena | WRITE | ALUNO | `pessoa_fisica.povo_indigena = self.povo_indigena` — InscricaoAlunoEstrangeiro.gerar_matricula(), copia campo para nova PF | med |
| `rh/models/pessoa/pessoa_fisica.py:309` | povo_indigena | READ | AMBIGUOUS | `if self.raca and self.raca.is_indigena() and not self.povo_indigena` — método clean() em PessoaFisica (self) | high |
| `processo_seletivo/tasks.py:424` | raca | WRITE | ALUNO | `aluno.pessoa_fisica.raca = dados['raca']` | high |
| `ae/tasks.py:1722` | raca | READ | ALUNO | `if pessoa_fisica.raca:` — `pessoa_fisica = aluno.pessoa_fisica` | high |
| `ae/tasks.py:1723` | raca | READ | ALUNO | `pessoa_fisica.raca.descricao == 'Branca'` | high |
| `ae/tasks.py:1725` | raca | READ | ALUNO | `pessoa_fisica.raca.descricao == 'Preta'` | high |
| `ae/tasks.py:1727` | raca | READ | ALUNO | `pessoa_fisica.raca.descricao == 'Parda'` | high |
| `ae/tasks.py:1729` | raca | READ | ALUNO | `pessoa_fisica.raca.descricao == 'Amarela'` | high |
| `ae/tasks.py:1731` | raca | READ | ALUNO | `pessoa_fisica.raca.descricao == 'Indígena'` | high |
| `edu/educacenso.py:774` | raca | READ | SERVIDOR | `servidor.pessoa_fisica.raca_id and servidor.pessoa_fisica.raca.is_indigena()` | high |
| `edu/educacenso.py:806` | raca | READ | SERVIDOR | `servidor.pessoa_fisica.raca.codigo_censup if servidor.pessoa_fisica.raca_id else 1` | high |
| `edu/educacenso.py:1091` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca_id and aluno.pessoa_fisica.raca.is_indigena()` | high |
| `edu/educacenso.py:1136` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca_id and aluno.pessoa_fisica.raca.codigo_censup or 1` | high |
| `edu/censup.py:189` | raca | READ | SERVIDOR | `servidor.pessoa_fisica.raca_id and servidor.pessoa_fisica.raca.codigo_censup or 1` | high |
| `edu/censup.py:577` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca.codigo_censup or ''` | high |
| `edu/censup.py:580` | raca | READ | ALUNO | `aluno.caracterizacao.raca_id and aluno.caracterizacao.raca.codigo_censup or ''` — fallback via Caracterizacao (RUÍDO desta linha; linha 577 é PF) | med |
| `edu/views/matriculas.py:102` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca` — em dict de dados JSON | high |
| `edu/management/commands/edu_importar_csv.py:230` | raca | WRITE | ALUNO | `pf.raca = Raca.objects.filter(...).first()` — `pf` = PessoaFisica direta (management command) | high |
| `edu/management/commands/edu_atualizar_dados_pessoas_alunos_proitec.py:18` | raca | WRITE | ALUNO | `aluno.pessoa_fisica.raca = dados['raca']` | high |
| `edu/forms/alunos.py:245` | raca | WRITE | ALUNO | `self.instance.pessoa_fisica.raca = ...` — AlunoForm save() | high |
| `edu/forms/matriculas.py:948` | raca | WRITE | ALUNO | `pessoa_fisica.raca = ...` — EfetuarMatriculaForm.processar() para nova PF | high |
| `edu/models/napne.py:89` | raca | READ | ALUNO | `pf.raca` — `pf = self.aluno.pessoa_fisica` em get_detalhes_aluno() | high |
| `edu/forms/professores.py:508` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca and aluno.pessoa_fisica.raca.descricao != 'Não declarado'` | high |
| `edu/forms/professores.py:510` | raca | READ | ALUNO | `aluno.pessoa_fisica.raca.descricao` | high |
| `rh/forms.py:949` | raca | READ | SERVIDOR | `self.instance.pessoa_fisica.raca` — ServidorForm.__init__() | high |
| `rh/models/pessoa/pessoa_fisica.py:309` | raca | READ | AMBIGUOUS | `if self.raca and self.raca.is_indigena()` — clean() em PessoaFisica (self) | high |
| `edu/models/internacionalizacao.py:497` | raca | WRITE | ALUNO | `pessoa_fisica.raca = self.raca` — InscricaoAlunoEstrangeiro.gerar_matricula(), self.raca é campo da inscrição | med |
| `edu/educacenso.py:1092` (povo)+ `edu/educacenso.py:1095` | povo_indigena | READ | ALUNO | agrupados acima | — |
