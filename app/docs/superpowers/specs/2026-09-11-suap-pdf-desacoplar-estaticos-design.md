# Desacoplar os estáticos do SUAP do serviço suap-pdf

Data: 11/09/2026

## Problema

O `suap-pdf` é um serviço independente, mas o `suap_deploy` monta nele o volume dos
estáticos do SUAP:

```yaml
pdfprinter:
  volumes:
    - static:/opt/suap-pdf/static:ro
```

O acoplamento existe por causa de um único ponto: o endpoint `wkhtml_to_pdf` recebe o
HTML já renderizado, mas **não recebe os arquivos que esse HTML referencia**. O
`wkhtml.make_absolute_paths` reescreve cada `"/static/..."` para
`file://$SUAP_PDF_STATIC_ROOT/...`, e é o volume que faz esses caminhos existirem.

Consequências: o `suap-pdf` não roda sozinho (o CI, que sobe o serviço sem volume, gera
PDFs sem estilo desde sempre); o deploy do `suap-pdf` precisa evitar `make down` porque ele
apaga o `suap_static`, repopulado só pelo web do SUAP; e os dois projetos precisam
compartilhar um sistema de arquivos.

Objetivo: o SUAP passa a enviar, via API, tudo que o HTML precisa, e o volume é removido.

## Escopo

No escopo: o endpoint `wkhtml_to_pdf` e seu único chamador no SUAP,
`render_pdf_from_template_with_wkhtmltopdf` ([djtools/utils/pdf.py:316](../../../djtools/utils/pdf.py)),
usado por `documento_eletronico`, `processo_eletronico`, `licenca_capacitacao` e
`boletim_servico`.

Fora do escopo:

- **`/media/`** — o pdfprinter já não resolve mídia hoje (o `make_absolute_paths` só trata
  `/static/`). O logo configurado da instituição sai de `default_storage.url()`
  ([comum/utils.py:306](../../../comum/utils.py)) e continua se comportando exatamente como
  hoje. Só o fallback (`/static/comum/img/logo.jpg`) é asset estático, e esse entra no
  escopo naturalmente.
- Os demais endpoints (`docx_to_pdf`, `html_to_pdf`, `xlsx_to_pdf`, `csv_to_pdf`,
  `pdf_to_pdfa`, `sign_pdf`, `verify_pdf`) — nenhum lida com estáticos.
- O ramo local de geração (`django-wkhtmltopdf`, quando `caminho_libreoffice` não é URL),
  que resolve por `STATIC_ROOT` no próprio processo do SUAP.

## Levantamento

Os estáticos que os templates de impressão referenciam:

| Ref | Origem | Observação |
|-----|--------|-----------|
| `/static/ckeditor/ckeditor/contents.css?t=FB9E` | corpo, **header e footer** | hardcoded |
| `url(./Calibri.ttf)` | dentro do `contents.css` | 352 KB, **relativa ao CSS** |
| `/static/djtools/css/pdf_assinaturas.css` | corpo | hardcoded |
| `{% static 'documento_eletronico/css/documento.css' %}` | corpo | sai com `?v=<md5>` |
| `{% static 'comum/img/brazao_colorido.jpg' %}`, `logo_instituicao_icone.jpg` | corpo | |
| `url('/static/comum/img/logo_if_portrait.png')` | CSS inline do `relatorio_pdf.html` | |

Três fatos que moldam o desenho:

1. **A `Calibri.ttf` é referenciada de dentro do CSS, por caminho relativo.** Funciona hoje
   só porque o `contents.css` permanece um arquivo em disco: o `make_absolute_paths` não o
   reescreve, e o navegador resolve `./Calibri.ttf` contra a localização `file://` do CSS.
   Qualquer desenho que embuta o CSS num `<style>` quebra a fonte em silêncio.
2. **Header e footer também precisam da fonte.** Ambos aplicam `body.cke_editable` e o
   rodapé do parecer renderiza conteúdo do usuário (`parecer_simples.rodape|safe`). Não dá
   pra simplesmente remover o `<link>` deles. E o wkhtmltopdf relê o HTML de header/footer
   **a cada página**.
3. **As refs aparecem em três formas** — `{% static %}` com `?v=<md5>` (do
   `CacheControlPipelineStorage`), hardcoded com `?t=FB9E` e hardcoded puro — e o corpo
   contém HTML autoral do usuário (ckeditor), que pode trazer refs próprias. A coleta tem
   que varrer o **HTML renderizado**, não uma lista fixa.

## Alternativas consideradas

**Inline como `data:` URI no SUAP** (só mexeria num repo, e o pdfprinter atual já
funcionaria): descartada porque a Calibri viraria ≈470 KB de base64 em corpo, header e
footer, e a geração é em lote — um processo com dezenas de documentos multiplicaria isso.

**pdfprinter busca os estáticos por HTTP no SUAP**: tira o volume mas troca por
acoplamento de rede em tempo de execução, e o `sanitize.py` já registra que o wkhtmltopdf
quebra com URLs https. Contraria o objetivo de "mandar tudo via API".

**Enviar todo o conteúdo em todo request, sem cache**: é o desenho escolhido menos a camada
de hash. Mais simples, mas reenvia ≈470 KB por PDF para sempre.

## Desenho

O SUAP envia um mapa de assets **endereçado por conteúdo**; o pdfprinter mantém um cache
de blobs por hash e materializa um diretório por request.

### Contrato — `POST /api/v1/wkhtml_to_pdf`

Campos atuais (`template`, `header_template`, `footer_template`, `options`) inalterados.
Dois novos, opcionais:

```json
{
  "assets": {
    "ckeditor/ckeditor/contents.css": "<sha256>",
    "ckeditor/ckeditor/Calibri.ttf": "<sha256>"
  },
  "blobs": { "<sha256>": "<base64>" }
}
```

- **Chave de `assets`**: caminho relativo a `/static/`, sem query string nem fragmento, sem
  `/` inicial e sem `..`.
- **Com `assets`**: a raiz dos estáticos do request é um tmpdir montado com esses arquivos.
- **Sem `assets`**: fallback para `SUAP_PDF_STATIC_ROOT`, como hoje — é o que mantém a
  compatibilidade durante o rollout.
- **Hash ausente do cache e não presente em `blobs`** → `409 {"missing": ["<sha256>", ...]}`,
  respondido antes de qualquer conversão.
- **Chave inválida, base64 inválido, ou hash que não confere com o conteúdo recebido** →
  `400 {"message": ...}`. Hoje o wrapper `endpoint` transforma qualquer exceção em 500;
  `HTTPException` passa direto, então esses casos usam `HTTPException`.
- Sem limite de tamanho de payload, coerente com os outros endpoints que já recebem base64
  no corpo. A defesa é o token mais a validação de caminho.

### Lado SUAP

Módulo novo **`djtools/utils/estaticos_pdf.py`**, exportado pelo `djtools/utils/__init__.py`
como os demais. Separado do `pdf.py` (1015 linhas) porque é a costura nova e é testável sem
banco.

```python
class Asset(NamedTuple):
    sha256: str
    base64: str

def coletar_assets(*htmls: str) -> dict[str, Asset]: ...
```

Algoritmo:

1. Varre os HTMLs renderizados atrás de `/static/<caminho>` dentro de aspas ou de `url(...)`.
   A chave descarta query e fragmento.
2. Resolve cada chave em disco por `django.contrib.staticfiles.finders.find(rel)`, que acha
   nos `static/` dos apps sem depender de `collectstatic` e funciona igual em dev e nos
   containers web e celery; se não achar, tenta `STATIC_ROOT/rel`. Não achou nos dois: fica
   de fora, com `logger.warning`. É o mesmo resultado visual de hoje (ref quebrada), sem
   derrubar a impressão.
3. Para cada `.css` coletado, varre `url(...)` e `@import` no conteúdo. Ref absoluta
   `/static/...` vira chave igual; ref relativa resolve contra o diretório da chave do
   próprio CSS; `data:`, `http:` e `https:` são ignoradas. Recursivo, com conjunto de
   visitados para não ciclar. É o que traz a `Calibri.ttf`.
4. `lru_cache` por `(caminho, mtime)` guarda `(sha256, base64)`, evitando reler e
   recodificar os mesmos arquivos a cada impressão.

Ponto de integração, no ramo HTTP de `render_pdf_from_template_with_wkhtmltopdf`: monta
`assets` com os hashes dos três HTMLs renderizados e envia. Em `409`, reenvia o mesmo
request **uma única vez**, agora com `blobs` só dos hashes listados em `missing`. Um segundo
409 vira exceção — um pdfprinter com disco cheio não pode virar laço.

O ramo local, os 4 apps chamadores e todos os templates ficam intactos.

Junto vai o conserto de um bug latente na mesma função,
[djtools/utils/pdf.py:319](../../../djtools/utils/pdf.py): `if not cmd_options: cmd_options =
{... for ... in cmd_options.items()}` levanta `AttributeError` se alguém chamar sem
`cmd_options`. Hoje todos os chamadores passam o argumento, então nunca disparou.

### Lado pdfprinter (`suap-pdf`)

Nomes em inglês, acompanhando o código existente do repo.

- **`wkhtml.py`**: `make_absolute_paths(content, root=None)` ganha o parâmetro; sem ele, cai
  no `SUAP_PDF_STATIC_ROOT`. A lógica de reescrita não muda — `"/static/x.css?v=1"` vira
  `file://<raiz>/x.css?v=1`, com a query preservada, que é o que já acontece hoje em
  produção.
- **`assets.py` (novo)**:
  - blobs em `volume/assets/<sha256>`, escritos por arquivo temporário + `os.replace`, para
    que dois requests simultâneos com o mesmo blob não se atropelem;
  - `missing(assets)` devolve os hashes que faltam;
  - `materialize(assets, dest)` cria `dest/<chave>` como **symlink** para o blob — sem
    cópia, e as refs relativas dentro do CSS continuam resolvendo;
  - validação por chave: rejeita chave absoluta, normaliza com `posixpath.normpath`, rejeita
    `..` e confere que o `realpath` final não escapa de `dest`;
  - sem expurgo do cache (são poucos MB, e container novo reaquece sozinho).
- **`main.py`, endpoint `wkhtml_to_pdf`**: um `mkdtemp()` por request hospeda os assets e
  também os HTMLs de corpo, header e footer, com `shutil.rmtree` num `finally`. Isso de
  quebra estanca um vazamento atual: hoje só o HTML do corpo é apagado
  (`utils.remove_temp_file`), e os de header e footer ficam para trás em `/tmp` — que no
  `suap_deploy` é um bind mount em disco.

## Testes

**SUAP** — `djtools/tests/utils/test_utils_estaticos_pdf.py`, sem banco:

- chave sem query, para as três formas de ref (`?v=`, `?t=`, sem query);
- `url(./Calibri.ttf)` dentro do CSS resolvida relativa ao diretório do CSS;
- `@import` recursivo e ciclo entre CSS não entram em laço;
- refs `http:`, `data:` e `/media/` ignoradas;
- arquivo inexistente não levanta exceção e não aparece no mapa;
- chave nunca começa com `/` nem contém `..`;
- mesmo conteúdo em dois caminhos gera o mesmo `sha256`.

Em `djtools/tests/utils/test_utils_pdf.py`, com `requests.post` mockado: o payload leva
`assets` só com hashes; um `409` provoca exatamente um reenvio, com `blobs` restrito aos
hashes de `missing`; um segundo `409` levanta exceção.

**suap-pdf** — casos no `test.py` (script, seguindo o idioma dele), todos com
`SUAP_PDF_STATIC_ROOT` apontando para um diretório vazio, para provar que o PDF sai
estilizado sem volume nenhum:

- request com `assets` e `blobs` gera o PDF e popula o cache;
- request seguinte só com `assets` acerta o cache;
- `assets` com hash desconhecido e sem `blobs` devolve `409` com o hash em `missing`;
- chave com `../` devolve `400`;
- `blobs` cujo conteúdo não bate com o hash devolve `400`.

## Rollout

Enquanto o volume existir, qualquer combinação de versões funciona: um pdfprinter antigo
ignora os campos novos e usa o volume, um SUAP antigo não manda `assets` e cai no fallback.

1. **suap-pdf**: release com `assets`/`blobs`/409, mantendo o fallback
   `SUAP_PDF_STATIC_ROOT`. Deploy. Nada muda de comportamento.
2. **suap**: MR com a coleta e o envio. Deploy em homologação.
3. **Verificação com o volume desmontado** (ou `SUAP_PDF_STATIC_ROOT` apontando para um
   diretório vazio).
4. **suap_deploy**: remove `static:/opt/suap-pdf/static:ro` do serviço `pdfprinter` no
   `docker-compose.yml` e as menções em README/FAQ/docs — inclusive a ressalva de deploy do
   `suap-pdf` que hoje explica por que não se usa `make down` (apagava o `suap_static`).
5. **suap-pdf**: release seguinte remove o fallback e o `SUAP_PDF_STATIC_ROOT` do código e
   do README.

**Rollback**: reverter o deploy do SUAP faz voltar ao fallback pelo volume. É por isso que o
passo 4 só acontece depois do 3.

## Verificação

Toda verificação roda **com o volume desmontado**. Qualquer conferência feita com o
`suap_static` ainda montado em `/opt/suap-pdf/static` passa pelo motivo errado.

Casos, comparando cada PDF com o gerado antes da mudança:

- `documento_eletronico` — o mais rico: fonte, dois CSS, logo, selo e qrcode;
- um processo multipágina do `processo_eletronico` — exercita header e footer por página;
- `licenca_capacitacao` — logo vindo de MEDIA, que deve continuar exatamente como hoje;
- um lote do `boletim_servico`.

Medir tamanho e tempo do primeiro request (miss, ≈470 KB) contra os seguintes (hit, algumas
centenas de bytes): é o que prova o cache. Ler os `logger.warning` de asset não resolvido —
podem revelar refs já quebradas hoje.

Nenhum teste atual pega asset faltando: o `bin/ci/docker-compose.yaml` sobe o pdfprinter sem
volume algum, ou seja, o CI vem gerando PDF sem estilo esse tempo todo — e passa a sair
estilizado depois desta mudança. O mesmo vale para o desenvolvimento local: o
`docker/docker-compose.dev.yml` também não monta estático no pdfprinter. Ou seja, o volume
do `suap_deploy` é a única instalação onde os PDFs saem estilizados hoje, e depois desta
mudança os três ambientes passam a se comportar igual.
