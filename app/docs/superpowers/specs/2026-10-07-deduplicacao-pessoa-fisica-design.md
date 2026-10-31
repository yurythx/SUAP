# Deduplicação de PessoaFisica

**Data:** 2026-10-07
**Status:** desenho aprovado; MR 1 aberto (!19286); MR 2 implementado e em revisão final. Atualizado em 08/10/2026 com as decisões e correções da implementação (seção 6).
**Antecedentes:** `2026-05-25-pessoa-fisica-unificada-design.md` (branch `refactor/unif-pf-dedup-data`, MR !18214 fechado sem merge) e `2026-07-01-mover-campos-pessoa-para-vinculo-design.md` (MR !18460, mergeado).

## Objetivo

Uma pessoa civil = uma `PessoaFisica`, garantido pelo banco:

| Campo | Constraint final |
|---|---|
| `cpf` | nulo ou único |
| `passaporte` | nulo, ou único junto com o país: **(país de origem, passaporte)** |
| `pais_origem` | obrigatório quando não há CPF, exceto para documento sintético (CHECK) |
| `documento_identificador` | não nulo e único |

O SUAP roda em várias instituições, cada uma com seu banco. Nada no desenho pode depender dos dados do IFRN: nenhuma lista de valores-lixo, nenhum limiar calibrado numa base. Os números abaixo servem de caso de teste e de ordem de grandeza, não de regra.

## Estado atual (IFRN, 2026-10-07, leitura em prod)

- 555.876 PFs. Grupos de CPF duplicado: 104.631 (347.588 PFs). Com CPF válido: 104.752 grupos / 317.789 PFs. Em 80.963 grupos há mais de uma PF de aluno, porque cada matrícula cria uma PF.
- CPF lixo: 24.994 máscaras sem dígito (`-`, `   .   .   -`, `___.___.___-__`), todas de aluno; 1.840 de dígito repetido.
- Sem CPF e sem passaporte: 16.605 (16.584 alunos, 60 prestadores, 29 sem papel).
- `passaporte` nunca é NULL (`default=''`): 551.258 vazios. Duplicados: 816 grupos, com lixo de 1 caractere repetido até 63×. 2.983 `edu.Aluno` têm passaporte próprio.
- Sinal de CPF errado dentro do grupo: nascimento divergente em 840 grupos, nome divergente em 2.151, os dois em 91.
- No banco há 86 FKs para `pessoa_fisica` e 36 para `pessoa`, mas o ORM conhece só 13. As outras **109 são fantasmas**: campos migrados para `Vinculo` com `RemoveField` só de state (`SeparateDatabaseAndState`), mantidos como mecanismo de recuperação de falha. São 100 colunas em tabelas vivas e 5 tabelas `through` de M2M, cada uma com a migration que a tirou do state, mais 3 tabelas que nenhuma migration cria: `financeiro_empenho` (0 linhas), `temp_rh_resposta` e `temp_enquete_cnat_resposta`. Os conflitos de unicidade medidos antes (`saude_prontuario.pessoa_fisica_id`: 4.147 grupos; Lattes: 239) estão em colunas fantasmas: hoje `Prontuario` e `CurriculoVittaeLattes` são 1:1 com `Vinculo`.
- Entre as FKs vivas, nenhuma tem unicidade só na FK. Pseudo-singletons sem constraint no banco: `PessoaInfoComplementar` (o `UniqueConstraint(pessoa, api_origem)` está solto no `Meta`, fora de `constraints`, e nunca foi criado; 26.571 grupos teriam repetição) e `PessoaEndereco` (`Pessoa.pessoaendereco` = `.first()`; 9.050 grupos com mais de um endereço).
- `PessoaExterna`: 39.599, cada uma com PF própria e sem outro papel.
- Os papéis (`Servidor`, `PrestadorServico`, `Aluno`) referenciam PF por FK (`AbstractRelacionamento.pessoa_fisica`), não por herança multi-table.

## Decisões

| # | Decisão |
|---|---|
| 1 | PFs legadas sem documento válido recebem `documento_identificador` sintético (`SEMDOC-`, `SEMPAIS-`, `CONFLITO-` ou `INVALIDO-`, com o id e, quando houver, o documento original); PF nova exige CPF ou passaporte. |
| 2 | Entrega: comando operado por instituição + migration de constraint com trava. Nenhum merge roda no `migrate`. |
| 3 | Grupo suspeito: separar, nunca mesclar pessoas com nascimento divergente. |
| 4 | Referência com unicidade só na FK que colide: o grupo é separado. Único handler: `PessoaInfoComplementar` (mantém a consulta mais recente). |
| 5 | Pessoa que volta: política por fonte (SIAPE autoritativa, matrícula cautelosa, gov.br preenche). Edição do próprio cadastro é autoritativa, mas fora do SIAPE não troca o documento (08/10). |
| 6 | `PessoaExterna`: só neutralizada aqui; a revisão do model é spec próprio, depois do dedup. |
| 7 | Motor: planejar → aplicar em lote, set-based, com plano persistido. |
| 8 | Duas releases e três MRs: na Release 1, o MR 1 apaga as colunas fantasmas e o MR 2 traz o comando e fecha a entrada; na Release 2, o MR 3 traz as constraints. |
| 10 | Passaporte só identifica junto com o país emissor; sem CPF, o país é obrigatório (exceto documento sintético). Minicurso e PROITEC usam `PREENCHER` (decisões de 07/10/2026). |
| 9 | Colunas fantasmas de pessoa são apagadas por migration `RunSQL` (lista explícita, uma migration por app dono). A descoberta de referências fica no ORM, com trava de catálogo. |
| 11 | Documento inválido (CPF com DV errado ou dígito repetido; passaporte curto ou repetido) nunca casa com ninguém e não cria PF, em nenhuma entrada, inclusive importadores (08/10). |
| 12 | CPF de uma pessoa com passaporte+país que já pertence a outra PF com outro CPF: recusar (08/10). |

## 0. Remoção das colunas fantasmas (Release 1, MR 1)

As colunas e tabelas fantasmas que apontam para `pessoa_fisica`/`pessoa` são apagadas antes do dedup. Elas existem para recuperação de falha das migrações para `Vinculo`, e o state do Django já não as conhece; por isso a remoção é `RunSQL`.

- **Uma migration por app dono da tabela**, para que instituição sem o app não dependa de migration que não tem.
- **Lista explícita**, tirada do diff catálogo × ORM e conferida contra o histórico de migrations: cada item precisa de uma migration que o removeu só do state. Nunca uma lista calculada em tempo de execução, que apagaria colunas de LPS ou de customizações de outra instituição.
- SQL: `SET LOCAL lock_timeout = '10s'`; `ALTER TABLE IF EXISTS <t> DROP COLUMN IF EXISTS <c>` (leva a FK e os índices junto) e `DROP TABLE IF EXISTS <t>` para as tabelas `through`. Precedente no repo: `edu/0151`.
- Irreversível (sem `reverse_sql`); a recuperação passa a ser o backup do runbook.
- Os comandos `processo_eletronico_dump_pessoafisica` e `dump_documento_pessoafisica` leem as fantasmas, mas **ficam**: as migrations `processo_eletronico/0032` e `documento_eletronico/0027` os chamam via `call_command`, e num banco novo rodam antes do drop, com as colunas presentes. Saem os métodos mortos `DocumentoTexto.obter_pessoas_podem_ler/editar` (`documento_eletronico/models.py`), que leem `pessoa_permitida_id`, campo que já não existe no model.
- Tabelas que não vieram de migration (no IFRN, `financeiro_empenho`, `temp_rh_resposta` e `temp_enquete_cnat_resposta`) não são tocadas pelo produto: a trava de catálogo do `planejar` (seção 2) as aponta e a instituição decide.

## 1. Regras de dados

As funções de normalização ficam num módulo só e são usadas tanto pela higiene quanto pela entrada de dados (seção 3).

### Higiene

Cada alteração grava uma linha em `rh.DeduplicacaoPessoa` com o valor original.

- **CPF:** remove os não dígitos. É válido se tiver 11 dígitos, não for dígito repetido e o DV conferir. Válido fica gravado com máscara `000.000.000-00` (formato de 93% da base; `get_cpf_anonimo` assume a máscara). Inválido vira `NULL`, ação `cpf_anulado`.
- **Passaporte:** `strip`, maiúsculas, sem espaços. Vira `NULL` se ficar vazio, tiver menos de 5 caracteres ou for um único caractere repetido (ação `passaporte_anulado`). Se o passaporte da PF for inválido ou vazio e o do `edu.Aluno` mais recente for válido, o do aluno é copiado para a PF (ação `passaporte_preenchido`, que sobrescreve; `valor_original` guarda o inválido).
- **País de origem:** só para quem não tem CPF válido, a higiene infere o país pelo aluno **mais recente** — se o país dele não converter, nada é inferido (ação `pais_preenchido`): aluno brasileiro vira Brasil; aluno estrangeiro tem o `edu.Pais` convertido para `comum.Pais` **pelo nome** (sem acento, maiúsculo). Nunca pelo código: os dois models usam esquemas diferentes, e as 62 coincidências de código em prod apontam para países trocados. No IFRN, das 49,4 mil PFs sem CPF válido e sem país, cerca de 30 mil são inferíveis; cerca de 19,5 mil (750 com passaporte) não são.
- **Passaporte só com país:** a chave é `<ISO 3166-1 alfa-3 do país>-<passaporte>` (ex.: `ARG-AB123456`), com o alfa-3 em `comum.Pais.iso_alfa3` (ver 6.1). Passaporte sem país não é documento: a PF recebe sintético e o número fica guardado.
- **`documento_identificador`:** CPF, senão passaporte/país, senão sintético (ação `sintetico`):

  | Caso | Formato | Exemplo |
  |---|---|---|
  | Sem documento (inclusive máscara-lixo sem dígito) | `SEMDOC-<id>` | `SEMDOC-482193` |
  | Passaporte válido sem país (emenda de 09/10) | `SEMPAIS-<id>-<passaporte>` | `SEMPAIS-549929-AAE771571` |
  | Separada por conflito (seção "Merge") | `CONFLITO-<id>-<documento original normalizado>` | `CONFLITO-482193-012.345.678-90` |
  | CPF anulado por inválido, com dígitos | `INVALIDO-<id>-<dígitos originais>` | `INVALIDO-482193-01234567891` |

  O id garante a unicidade, mesmo quando o mesmo documento conflita em várias PFs. O prefixo não numérico impede que o sintético seja tomado por documento real. O documento original na própria PF deixa a busca (`icontains`) achar a pessoa e mostra o conflito para quem for corrigir. Para caber o passaporte original com o país (até 50 + 5 caracteres), `documento_identificador` passa a `max_length=80` na Release 1 (aumentar varchar no Postgres só altera metadado).

Limiares abertos a ajuste: passaporte com menos de 5 caracteres; "nascimento divergente" = datas diferentes, ambas preenchidas.

### Merge

- **Grupo:** PFs com o mesmo `documento_identificador`, calculado depois da higiene. Sintético nunca agrupa.
- **Sobrevivente:** servidor ativo > aluno ativo > prestador ativo > maior `id`. "Ativo" usa os métodos de cada papel.
- **Suspeita:** a referência do grupo é o nascimento do sobrevivente ou, se ele não tiver, o do membro de maior prioridade que tenha. A PF com `nascimento_data` diferente da referência (ambas preenchidas) não é mesclada. Perde o CPF (ou o passaporte, se era ele o documento), recebe o sintético `CONFLITO-<id>-<documento original>` e é registrada com o valor original (ação `separada`). As demais PFs do grupo são mescladas.
- **Conflito de campo:** vale o valor não nulo do sobrevivente. Se o sobrevivente tem nulo, o campo é preenchido pela perdedora de maior `id`. Cada valor descartado é registrado (ação `campo_descartado`). Biometria (`template`) e `senha_ponto` também preenchem o vazio, mas a divergência é registrada **sem o valor** (`motivo='valor omitido (biometria/senha)'`). Campos derivados ou de identidade não se mesclam (`cpf`, `documento_identificador`, `nome`, `nome_usual`, `uuid`, `eh_*`, `search_fields_optimized`); o passaporte da perdedora só é auditado.
- **Passaporte residual:** se, depois do merge, duas PFs com CPFs diferentes têm o mesmo par passaporte+país, a de menor prioridade fica com passaporte `NULL` (ação `passaporte_anulado`).
- **Unicidade nas referências:**
  - Unicidade composta (par de M2M ou `unique_together`): apaga a linha da perdedora que repetiria o par do sobrevivente — só quando as outras colunas do índice são todas não nulas (o Postgres trata `NULL` como distinto). Só índices únicos **totais** sobre colunas-chave contam: índice parcial, de expressão e colunas `INCLUDE` são ignorados de propósito; uma colisão real neles falha no UPDATE e o grupo vira `erro`, sem apagar nada.
  - Unicidade só na FK (1:1): se mais de uma PF do grupo tem linha, o grupo inteiro vira `separada`. Hoje nenhuma FK viva cai aqui; a regra existe para outras instituições e para models futuros.
  - `PessoaInfoComplementar` (handler): por `(pessoa, api_origem)`, fica a linha de `data_hora_consulta` mais recente e as outras são apagadas (é cache de API do governo, reconsultável).
- **Endereço:** `Pessoa.pessoaendereco` passa a devolver o endereço mais recente (`order_by('-pk')`). Os endereços das perdedoras são reapontados, não apagados.

## 2. Motor: `manage.py deduplicar_pessoas`

### Tabela `rh.DeduplicacaoPessoa`

Plano, auditoria e mapa de id antigo → novo, numa tabela só.

Campos: `pf_id`, `sobrevivente_id` (nulo quando não há merge), `documento`, `acao` (`cpf_anulado`, `passaporte_anulado`, `passaporte_preenchido`, `pais_preenchido`, `sintetico`, `mesclada`, `separada`, `campo_descartado`, `divergencia_entrada`, `erro`), `campo`, `valor_original`, `motivo`, `criado_em`, `aplicado_em`.

Linhas gravadas pela entrada de dados (seção 3, `divergencia_entrada`) já nascem com `aplicado_em` preenchido: são auditoria, não plano. Linhas `erro` ficam com `aplicado_em` nulo de propósito: a trava da Release 2 as conta, e um novo `planejar` as descarta e refaz o plano.

### Subcomandos

1. **`planejar`:** apaga o plano não aplicado e recalcula a partir dos dados atuais. Não escreve em PF. Pode rodar quantas vezes quiser; um sintético já gravado (`CONFLITO-`/`INVALIDO-`) sobrevive a um novo plano.
2. **`relatorio --csv <path>`:** totais por ação e as linhas detalhadas. O CSV contém CPF: o comando avisa que é dado pessoal, recusa caminhos dentro de `MEDIA_ROOT` e grava com permissão 0600.
3. **`aplicar [--lote 1000]`:** primeiro a higiene (numa transação só, na ordem fixa `cpf_anulado`, `pais_preenchido`, `passaporte_preenchido`, `passaporte_anulado`, `separada`, `sintetico`, seguida da normalização de documentos), depois os merges em lotes de N grupos, um `transaction.atomic()` por lote. `--lote` aceita só inteiro ≥ 1. O comando não abre transação externa.

### Um lote do `aplicar`

1. Roda o handler de `PessoaInfoComplementar`.
2. **Descobre as referências** pelo registro de apps, em tempo de execução, o que só pega os apps instalados naquela instituição:
   - `ForeignKey` / `OneToOneField` para `PessoaFisica` e para `Pessoa`;
   - tabelas `through` de `ManyToManyField`;
   - `GenericForeignKey` cujo `content_type` é PF ou Pessoa, exceto de apps de histórico (`reversion`): histórico fica com o id antigo.
3. Para cada referência com unicidade composta, apaga as linhas da perdedora que colidiriam. Depois faz um `UPDATE … SET fk = sobrevivente` a partir do plano.
4. `Vinculo.pessoa` passa a ser o sobrevivente; `Vinculo.secret` guarda o id antigo.
5. Grava os valores resolvidos no sobrevivente e recalcula `eh_*` e `search_fields_optimized`.
6. **Trava antes do DELETE:** roda o `Collector` do Django sobre as perdedoras. Se ele fosse apagar ou anular algo além das linhas de `PessoaFisica`/`Pessoa` delas (só conta model com linhas de fato; `SET_NULL` vazio não conta), o lote faz rollback e é refeito grupo a grupo; o grupo que falhar vira `erro` com o motivo e o comando segue.
7. Apaga as perdedoras e marca `aplicado_em`.

**Plano desatualizado:** o `aplicar` reconfere a premissa de cada linha antes de gravar. A higiene só vale se o valor atual ainda é o que o `planejar` viu; a mescla só vale se as PFs ainda existem, têm o mesmo `documento_identificador` do sobrevivente e nenhuma diverge do nascimento de referência. Se não, a linha/grupo vira `erro` com "rode planejar de novo".

A detecção de 1:1 acontece no `planejar`: uma referência cuja unicidade é **só** a FK, com linha em mais de uma PF do grupo, já põe o grupo no plano como `separada`.

**Trava de catálogo:** antes de planejar, o comando lista as FKs de `pg_constraint` que apontam para `pessoa_fisica`/`pessoa` e compara com as referências do ORM. Havendo alguma desconhecida, aborta listando `tabela.coluna` e orientando a instituição a removê-la ou tratá-la. Sem isso, o DELETE da perdedora falharia no commit por violação de FK.

### Propriedades

- **Retomável e idempotente:** grupo aplicado não é reaplicado; uma falha retoma de onde parou.
- **Concorrência:** a janela de manutenção é **obrigatória** para o `aplicar` (a higiene é uma transação sobre a tabela inteira e bloqueia todo `save()` de PF, inclusive o login gov.br); rode `planejar` de novo dentro da janela, logo antes. O comando conecta direto no Postgres, não pelo pgbouncer (`planejar`/`relatorio` usam cursor de servidor). Referência nova criada a uma perdedora durante o lote cai na trava do passo 6; correção feita entre `planejar` e `aplicar` cai na reconferência do plano.
- **Fora:** histórico (`class History`) e logs continuam com ids antigos (o mapa está em `DeduplicacaoPessoa`); não há redirect de URL de id antigo.

## 3. Entrada de dados (Release 1)

### `PessoaFisica.objects.obter_ou_criar(dados, politica) -> (pf, criada)`

Único caminho para criar PF. CPF, passaporte e país (`pais_origem`, instância de `comum.Pais`, ou `pais_origem_id`) vêm dentro de `dados`. Normaliza os documentos com as funções da seção 1 e:

- **busca primeiro só pelo CPF**; sem CPF que case, pelo par passaporte+país **apenas entre PFs sem CPF** (o estrangeiro que depois ganhou CPF é reusado e recebe o CPF);
- **recusa** (`DocumentoDeOutraPessoa`) se o par passaporte+país já pertence a uma PF com outro CPF;
- **nunca casa nem cria** com CPF inválido, ou com passaporte inválido sem CPF válido (`ValidationError`);
- serializa por documento com advisory lock (das duas chaves, em ordem fixa), liberado ao fim de cada chamada para não acumular em transação longa de importador.

Encontrou: aplica a política. Não encontrou: cria. `aplicar_politica(pf, dados, politica)` aplica a mesma regra nos ramos de **atualização** (SIAPE, prestador, importadores), e `verificar_documento(...)` é a checagem sem escrita para o `clean()` de formulário.

| Política | Comportamento |
|---|---|
| `AUTORITATIVA` | Sobrescreve todo campo cujo valor de entrada não é nulo. Nascimento divergente não bloqueia, mas é registrado em `DeduplicacaoPessoa` (ação `divergencia_entrada`). |
| `CAUTELOSA` | Nascimento divergente (ambos preenchidos) levanta `DocumentoDeOutraPessoa(ValidationError)`. Senão, sobrescreve com os valores de entrada não vazios, sem apagar. |
| `PREENCHER` | Só preenche campo vazio. |

| Ponto de criação / atualização | Política |
|---|---|
| `Servidor.update_or_create` (SIAPE) | `AUTORITATIVA` nos dois ramos; pode trocar o documento |
| Criação por documento: matrícula, `q_academico`, CSV v1/v2, intercâmbio, `PrestadorServico` (pessoa nova), `PessoaExterna` nova | `CAUTELOSA` (`PessoaExterna` usa `PREENCHER` + `verificar_documento`: a cópia da externa nunca sobrescreve) |
| Próprio cadastro (aluno/prestador já existente atualizado pela própria fonte; PessoaExterna exclusiva) | `AUTORITATIVA`, mas **fora do SIAPE não troca `cpf`/`passaporte`/`pais_origem`** de PF que já tem documento válido |
| gov.br (criação), credores SIAFI, dependentes SIAPE, minicurso, PROITEC (fontes sem data de nascimento) | `PREENCHER` |

- O login gov.br continua atualizando `nome_registro` da PF existente (`comum/models.py:2121`), como hoje.
- Formulários chamam `verificar_documento`/`recusar_documento_de_outra_pessoa` no `clean()` (só na criação), para o erro sair no campo e não virar 500; o `obter_ou_criar` roda no `save()`/`processar`. Na matrícula, a recusa por CPF sai em `clean_data_nascimento` e a por passaporte em `clean_pais_origem`.
- Formulários que aceitam passaporte (prestador, colaborador externo de pesquisa/projetos/projetos de ensino, professor externo) pedem o país (`comum.Pais`), obrigatório para estrangeiro sem CPF; a matrícula e a planilha de intercâmbio convertem o país do `edu.Pais` pelo nome.
- `PessoaFisicaForm.clean_cpf` (admin) recusa CPF de outra PF, só quando o CPF foi alterado.
- Contato (endereço/telefone): PF criada grava; próprio cadastro sobrescreve sem gravar vazio; PF obtida de outra pessoa pelo documento só ganha contato se não tiver.
- Código que supunha 1 PF = 1 aluno passa a pegar o aluno/vínculo do usuário logado ou do papel.
- `edu/forms/matriculas.py:657/689` instanciam `PessoaFisica()` só para validar e não são pontos de criação.

### `PessoaFisica.save()`

- Normaliza CPF e passaporte (`''` → `NULL`).
- `documento_identificador` = CPF, senão `<ISO alfa-3>-<passaporte>` (país sem alfa-3 não forma documento), senão o sintético: `CONFLITO-`/`INVALIDO-` guardam a história e ficam; `SEMDOC-`/`SEMPAIS-` acompanham o passaporte atual. Quando alguém corrige a PF informando um CPF ou passaporte+país, o sintético é substituído pelo documento.
- PF nova sem CPF válido e sem passaporte válido + país levanta `ValidationError`. Só formata: anular documento de PF existente é decisão auditada da higiene.
- Sai o ramo `aluno_com_passaporte`, e o `Aluno.save()` também deixa de copiar o passaporte para a PF: a cópia desfaria o `passaporte_anulado` da higiene. O legado é coberto pela ação `passaporte_preenchido`; o estrangeiro novo traz o passaporte nos `dados`.
- Saem `PessoaFisica.clonar()`, o comando `duplicar_pessoas_por_vinculo` e as clonagens por `pk = None` (minicurso, transferência de curso, intercâmbio): o aluno novo reusa a PF.

### `PessoaExterna.save()`

Deixa de fazer `PessoaFisica.objects.filter(...).update(**instance)`, que depois do merge sobrescreveria os dados de um servidor com a cópia antiga da externa. Na criação: `verificar_documento` + `obter_ou_criar(PREENCHER)`. Na edição, a cópia da externa só chega à PF quando a PF é **exclusiva** dela (nenhum outro vínculo); PF compartilhada nunca é tocada. As colunas duplicadas ficam no banco até o spec de revisão do model.

### `passaporte` nullable e `documento_identificador` maior

Já na Release 1: `AlterField(documento_identificador, max_length=80)` e `AlterField(passaporte, null=True, blank=True)` sem `default=''`, e varredura de `passaporte=''`, `.exclude(passaporte='')`, `.filter(passaporte='')`, `== ''` e `getattr(..., 'passaporte', ...)` no ORM, em Python e nos templates.

## 4. Constraints (Release 2)

Schema final:

```python
cpf = models.CharField(max_length=20, null=True, unique=True, verbose_name='CPF', blank=False)
passaporte = models.CharFieldPlus(max_length=50, null=True, blank=True, verbose_name='Nº do Passaporte')
documento_identificador = models.CharFieldPlus(max_length=80, null=False, blank=False, unique=True)

class Meta:
    constraints = [
        models.UniqueConstraint(fields=['pais_origem', 'passaporte'], name='pessoa_fisica_pais_passaporte_unico'),
        models.CheckConstraint(
            condition=Q(cpf__isnull=False) | Q(pais_origem__isnull=False) | Q(documento_identificador__regex=r'^(SEMDOC|SEMPAIS|CONFLITO|INVALIDO)-'),
            name='pessoa_fisica_sem_cpf_exige_pais',
        ),
    ]
```

Com CPF e sem país, o par (`NULL`, passaporte) não é restrito (o Postgres trata `NULL` como distinto): a unicidade dessa pessoa é o CPF.

`db_index=True` sai de `cpf` e de `documento_identificador`, porque o índice único o substitui.

`PessoaInfoComplementar.Meta` ganha `constraints = [UniqueConstraint(fields=['pessoa', 'api_origem'], name='unique_info_api_govbr')]`, que hoje está solto e nunca foi criado.

Migration:

1. **`RunPython` de pré-verificação** (só leitura). Conta duplicados por `cpf`, `(pais_origem, passaporte)`, `documento_identificador` e `(pessoa, api_origem)` de `PessoaInfoComplementar`, PFs sem CPF e sem país com documento não sintético, `documento_identificador` nulo ou vazio, e linhas de `DeduplicacaoPessoa` não aplicadas ou em `erro`. Se alguma contagem for maior que zero, levanta um erro com os números e o roteiro (`deduplicar_pessoas planejar` → `relatorio` → `aplicar`, depois repetir o `migrate`). Num banco vazio, passa.
2. **`AlterField`** dos três campos. Uma duplicata que nasça entre a verificação e o `ALTER` faz a migration atômica falhar com `IntegrityError`, sem estado parcial.

Depois da mescla sobram cerca de 341 mil PFs no IFRN; o `migrate` da 4.0.0 (3 índices únicos, NOT NULL e a CHECK) levou ≈1,5 min no ensaio, com `lock_timeout` de 10 s e a aplicação parada.

## 5. Testes, ensaio e rollout

### Testes

| Arquivo | Cobre |
|---|---|
| `rh/tests/models/test_documento_pessoa.py` (DB-free) | normalização de CPF (DV, dígito repetido, máscaras-lixo) e de passaporte; cálculo de `documento_identificador` |
| `rh/tests/tasks/test_deduplicar_pessoas.py` | `planejar`: mesclada, separada por nascimento, 1:1 colidindo → separada, os três formatos de sintético (`SEMDOC`, `CONFLITO` com o documento original, `INVALIDO` com os dígitos), trava de catálogo (FK desconhecida → aborta) e nenhuma escrita em PF. `aplicar`: FK para PF, FK para `Pessoa`, M2M com colisão, GFK, `Vinculo.secret`, handler de `PessoaInfoComplementar`, endereço mais recente, trava do `Collector` (referência criada depois do `planejar` → rollback + `erro`), retomada, idempotência |
| `rh/tests/fluxos/test_fluxo_obter_ou_criar_pessoa.py` | matrícula com CPF existente reusa a PF; nascimento divergente → erro no campo CPF; SIAPE sobrescreve sem anular; gov.br preenche e atualiza `nome_registro`; `PessoaExterna.save()` não sobrescreve servidor |
| `rh/tests/tasks/test_preverificacao_constraints.py` | a função de pré-verificação da Release 2, chamada direto (a suíte roda `--no-migrations`) |
| varredura | falha se aparecer `PessoaFisica.objects.create(` ou `PessoaFisica()` salvo fora de `obter_ou_criar`, das factories e das migrations |

A `PessoaFisicaFactory` já gera CPF válido e único. Testes que montam duplicatas legadas usam a fixture `sem_unicidade_pessoa` (conftest raiz), que derruba as unicidades e a CHECK dentro da transação do teste, valendo antes e depois da Release 2.

### Ensaio, antes de cada release

1. Cópia de prod do IFRN (`suap_dev`): `migrate` (MR 1 + MR 2), remoção manual de `financeiro_empenho` e `temp_*`, `planejar` → `relatorio` → `aplicar`, medindo o tempo e conferindo as contagens com a seção "Estado atual".
2. Dump de `gerar_banco_mock`: uma base que não é a do IFRN.

### Runbook (`docs/operacoes/deduplicar-pessoas.md`)

1. Backup (inclui as colunas fantasmas, que a Release 1 apaga).
2. Atualizar para a Release 1. Se o `planejar` apontar FK desconhecida (tabela criada à mão, LPS), removê-la ou tratá-la antes de seguir.
3. `deduplicar_pessoas planejar`.
4. Revisar o `relatorio` (CSV com dado pessoal; LGPD).
5. `deduplicar_pessoas aplicar` em janela.
6. Conferir que não há linha pendente nem `erro`.
7. Atualizar para a Release 2.

O release note da Release 2 avisa que o `migrate` trava enquanto o passo 5 não for concluído.

### Entregas

- **MR 1 (Release 1):** migrations `RunSQL` de remoção das fantasmas + remoção dos 2 métodos mortos que as liam.
- **MR 2 (Release 1):** `DeduplicacaoPessoa`, normalização, comando, handler de `PessoaInfoComplementar`, `pessoaendereco` mais recente, `obter_ou_criar` + pontos de criação e atualização, formulários com país, `save()`, `PessoaExterna.save()`, fim das clonagens, `passaporte` nullable, código 1 PF = 1 aluno, runbook.
- **MR 3 (Release 2):** constraints de `PessoaFisica` + `UniqueConstraint(pessoa, api_origem)` de `PessoaInfoComplementar` posto em `Meta.constraints` + pré-verificação.

Cada MR com sua issue.

## Fora do escopo

- Recalcular `eh_*` por signal de `Vinculo`.
- Revisão ou extinção de `PessoaExterna` e remoção das colunas duplicadas.
- **Lacuna conhecida:** depois da Release 2 não há ferramenta para juntar uma PF separada por engano (`CONFLITO-`) com a dona do CPF; antes dela, o runbook orienta refazer a deduplicação.
- **Limitação conhecida:** a matrícula do prestador estrangeiro sem CPF é só o número do passaporte; o mesmo número em dois países não pode ser prestador ao mesmo tempo.

## 6. Mudanças em relação ao desenho aprovado (07–08/10/2026)

| Mudança | Origem |
|---|---|
| Sem handlers de prontuário e Lattes (os dois são 1:1 com `Vinculo`); só `PessoaInfoComplementar` | conferência do código no planejamento |
| Colunas fantasmas apagadas no MR 1; descoberta pelo ORM com trava de catálogo | conferência do banco no planejamento |
| Passaporte + país como chave; país obrigatório sem CPF (CHECK) | decisão do usuário, 07/10 |
| Minicurso e PROITEC em `PREENCHER` | decisão do usuário, 07/10 |
| Próprio cadastro `AUTORITATIVA`; PessoaExterna só propaga se exclusiva; `clean_cpf` só se o CPF mudou; contato não sobrescreve terceiro | decisões (a)–(d) confirmadas pelo usuário, 08/10 |
| Fora do SIAPE, o próprio cadastro não troca o documento | decisão do usuário, 08/10 |
| Recusar par passaporte+país de outra PF; recusar documento inválido em toda entrada | decisões do usuário, 08/10 |
| Busca da entrada por CPF primeiro; `aplicar` reconfere o plano | revisão final (C1, C2) |
| Nascimento de referência do grupo; biometria/senha sem valor na auditoria | revisão da fase `planejar` |
| Unicidade só de índices totais; `NULL` distinto; `SET_NULL` vazio não é alheio; histórico do `reversion` não é reapontado | revisões das fases de referências e `aplicar` |
| Fim das clonagens de PF (`clonar`, `duplicar_pessoas_por_vinculo`, `pk = None`) | conferência do código; usuário aprovou apagar, 07/10 |
| Par passaporte+país de qualquer outra PF (inclusive sem CPF) é recusado; externa exclusiva recusa a troca de CPF no formulário (legada divergente segue salvável) | decisões do usuário, 08/10 (re-revisão) |
| Lock de documento por sessão, chave a chave, liberado a cada `obter_ou_criar` | re-revisão (vazamento do lock) |
| `search_fields_optimized` cortado no tamanho da coluna (`ModelPlus.save`) | ensaio: sobrevivente de 39 PFs estourava `varchar(400)` |
| `aplicar` em lote (sobreviventes sem `save()`, higiene e normalização por `executemany`) + índice de `rh_pessoaexterna.pessoa_fisica_id` (rh/0109, ausente em produção); constraints da Release 2 passam para rh/0110 | medição do ensaio: 53 → 11 min no IFRN |
| Reiniciar aplicação e Celery depois do `aplicar` (cache de vínculo/pessoa por processo) | revisão da otimização |
| Chave do passaporte com ISO 3166-1 alfa-3 em vez do código SIAPE; campo `comum.Pais.iso_alfa3` | decisão do usuário, 08/10 (ver 6.1) |
| Chave `ARG-AB123456` (passaporte só com letras e dígitos, até 26) e login do estrangeiro sem CPF novo; legado mantém o login só com o número; unicidade nos formulários pelo par | decisões do usuário, 09/10 (ver 6.2) |
| Nascimento divergente: fica com o documento o do servidor ativo (SIAPE), senão o da maioria do grupo (empate: prioridade); separadas de mesmo documento original e nascimento viram uma `CONFLITO-` só, inclusive as já gravadas; a `CONFLITO-` volta para a dona do documento original quando o nascimento passa a ser o mesmo (a dona fica com o documento); prestador cuja PF perdeu o CPF mantém o login | decisões do usuário, 09/10 (caso das matrículas 1962594/2962594 na suap_dev: 5 PFs de 17/09 separadas por um prestador ativo de 19/09; 67 de 894 grupos mudariam de dono) |
| PF sem relacionamento (sem vínculo, servidor, aluno, prestador ou GFK; endereço, telefone, contato de emergência, info complementar, pessoa externa, biometria e o vínculo da própria externa sem usuário não contam) é apagada: o `planejar` marca `apagada`, o `aplicar` apaga depois das mesclas; grupo todo sem relacionamento é apagado em vez de mesclado; o Collector confere nas duas fases que o DELETE só leva esses dependentes, e quem ganhou relacionamento entre as fases fica | decisão do usuário, 09–10/10 (suap_dev: 5.867 de 340 mil, 4.908 `SEMDOC-`, 938 com CPF, nenhuma com contato) |
- Redirect de URL de id antigo.

### 6.1 Passaporte com ISO 3166-1 alfa-3 (emenda de 08/10/2026)

**Motivo:** legibilidade e interoperabilidade. O documento do estrangeiro passa a ser reconhecível fora do SUAP: `ARG-AB123456` em vez de `AB123456/011` (formato de 6.2).

- **Dado.** O campo `comum.Pais.iso_alfa3` é `CharField(3, blank=True)`, **sem** unicidade, porque o SIAPE lista a Suíça duas vezes (150 e 236) e as duas linhas viram `CHE`. A tabela curada código SIAPE → alfa-3 fica no command `preencher_iso_paises`; os códigos SIAPE são iguais em todas as instituições. Países extintos (ALEMANHA ORIENTAL, URSS, IUGOSLÁVIA…) ficam sem alfa-3.
  - **Preenchimento.** A migration `comum/0121` chama o command, que preenche só os campos vazios e nunca sobrescreve uma correção feita no admin. Na instalação do zero, o `carga_inicial` carrega `comum/fixtures/paises.json` (com o alfa-3) se a tabela estiver vazia. Os dois importadores do SIAPE preenchem o campo ao **criar** um país e não mexem nele ao atualizar.
  - **Admin.** O campo é editável no admin de País.
- **Chave.** `chave_passaporte(passaporte, iso_alfa3)` dá `<ISO3>-<passaporte formatado>`. Todos os pontos que montavam a chave com `Pais.codigo` passam a usar `Pais.iso_alfa3`.
- **País sem alfa-3 não forma documento**, a mesma regra do passaporte sem país:
  - **PF legada:** recebe sintético na higiene.
  - **PF nova sem CPF:** é recusada com "País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países."
- **Efeitos.**
  - O mesmo passaporte registrado com os dois códigos da Suíça agora agrupa no `planejar` e é barrado pela unicidade do `documento_identificador` na 4.0.0. A UNIQUE `(pais_origem, passaporte)` continua igual, mais frouxa que o documento.
  - Nada disso está em produção, então não há documento antigo para converter: a normalização do `aplicar` e o `save()` recalculam a chave.
- **Onde entra.** No MR 2 (3.21.0). O MR 3 não muda.
- **Dados medidos no suap_dev.**
  - **Estrangeiros:** 921 PFs estrangeiras com passaporte, em 34 países.
  - **`comum.Pais.codigo_educacenso`:** é o ISO numérico, mas só está preenchido em 182 de 282 países e tem erros (EGITO e EL SALVADOR com 222; DINAMARCA e DOMINICA com 212). Não serve de fonte.
  - **`edu.Pais.sigla`:** já é alfa-3. Ajuda a curar a tabela.

### 6.2 Chave como login do estrangeiro sem CPF (emenda de 09/10/2026)

**Motivo:** a chave vira o login (`userPrincipalName` no AD) do estrangeiro sem CPF. O login só com o número fazia a unicidade valer só pelo número: o mesmo passaporte de dois países não convivia, e o formulário recusava a segunda pessoa.

- **Formato.** `<ISO3>-<passaporte>`, ex.: `ARG-AB123456`. O passaporte guarda só letras e dígitos ASCII, em maiúsculas (`ab-123.456` → `AB123456`); a pontuação sai antes das maiúsculas. Válido: 5 a 26 caracteres, com dígito e não de um caractere repetido; o máximo é o que cabe nos 30 caracteres da matrícula depois de `ARG-`.
- **Login.** `PrestadorServico.matricula_do_passaporte(passaporte, pais)` é a fonte única: o login do prestador que já tem o par passaporte+país ou, no cadastro novo, a chave. O prestador existente nunca troca de login no `save()` (o legado segue só com o número; quem ganha CPF passa ao CPF). O prestador legado **sem país** com o mesmo número é a mesma pessoa até prova em contrário: a edição que lhe dá o país reusa o cadastro (antes criava outro, achado na suap_dev em 09/10), e o cadastro novo com o mesmo número é recusado pelo usuário que já existe.
- **Unicidade pelo par.** Os formulários de prestador, colaborador (pesquisa, projetos, projetos_ensino) e professor externo comparam o par passaporte+país, nunca só o número. Saem `filtro_passaporte_ja_usado` e `matricula_de_outro_pais`. A seleção de vínculo do login por passaporte e a API `meus-vinculos` também usam o par.
- **Onde entra.** No MR 2 (3.21.0). Nenhuma instituição tem a chave antiga gravada; na `suap_dev`, o próximo `planejar`/`aplicar` a normaliza.
