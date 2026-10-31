# Desacoplar os estáticos do SUAP do suap-pdf — Plano de Implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** Fazer o SUAP enviar via API os arquivos estáticos que o HTML de impressão referencia, para que o volume `static:/opt/suap-pdf/static:ro` possa ser removido do serviço `pdfprinter`.

**Arquitetura:** O SUAP varre o HTML renderizado, resolve cada `/static/...` em disco (inclusive o que os CSS referenciam por caminho relativo, como a `Calibri.ttf`) e envia um mapa `{chave: sha256}`. O pdfprinter mantém um cache de blobs endereçado por conteúdo em `volume/assets/<sha256>` e monta, por request, um diretório temporário com um symlink por asset, que passa a ser a raiz dos `file://`. Hash que falte no cache é pedido com `409 {"missing": [...]}`, e o SUAP reenvia uma única vez com os conteúdos.

**Stack:** Python 3.14 + Django 5.2 (SUAP, pytest); Python 3.12 + FastAPI (suap-pdf, scripts de teste com `assert`); Docker Compose (suap_deploy).

**Spec:** [docs/superpowers/specs/2026-09-11-suap-pdf-desacoplar-estaticos-design.md](../specs/2026-09-11-suap-pdf-desacoplar-estaticos-design.md)

## Restrições globais

- **Três repositórios**, cada um com sua branch e seus commits:
  - SUAP: `/home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd` (worktree; branch `claude/suap-pdf-static-decoupling-e9d287`) — **não faça `cd` para o repositório principal**.
  - suap-pdf: `/home/hugo/workspace/suap-pdf` (branch base `main`).
  - suap_deploy: `/home/hugo/workspace/suap_deploy` (branch base `master`).
- **SUAP**: ruff com `line-length = 150` e aspas simples; identificadores, comentários e mensagens de commit em **pt-BR**; complexidade ciclomática das funções tocadas **≤ 10**; anotar tipos nas defs tocadas (parâmetros e retorno). O pre-commit roda no `git commit` e formata.
- **suap-pdf**: ruff com `line-length = 150` e `quote-style = "preserve"` (não troque aspas de código existente); nomes de código em **inglês**, seguindo o repo; toda mensagem de commit precisa do trailer **`Changelog: added`** (ou `changed`), senão o job de release é bloqueado.
- **Compatibilidade obrigatória durante todo o plano**: o campo `assets` é opcional e, na sua ausência, o pdfprinter continua usando `SUAP_PDF_STATIC_ROOT`. Não remova esse fallback antes da Tarefa 8.
- **Nada de `/media/`**: o pdfprinter não resolve mídia hoje e continua não resolvendo.

## Estrutura de arquivos

**suap-pdf**
- Criar `assets.py` — cache de blobs por sha256, validação de chave e materialização do diretório do request. Responsabilidade única, sem FastAPI, testável com stdlib.
- Criar `test_assets.py` — script de asserts para `assets.py` e `wkhtml.make_absolute_paths`, rodável fora da imagem.
- Modificar `wkhtml.py` — `make_absolute_paths` passa a aceitar a raiz.
- Modificar `main.py` — endpoint `wkhtml_to_pdf`: assets, 409, diretório único por request.
- Modificar `Dockerfile` — `ADD assets.py`.
- Modificar `test.py` e `README.md`.

**SUAP**
- Criar `djtools/utils/estaticos_pdf.py` — coleta e resolução dos estáticos. Fica fora de `djtools/utils/pdf.py` (1015 linhas) porque é a costura nova e é testável sem banco.
- Criar `djtools/tests/utils/test_utils_estaticos_pdf.py`.
- Modificar `djtools/utils/__init__.py`, `djtools/utils/pdf.py` e `djtools/tests/utils/test_utils_pdf.py`.

**suap_deploy**
- Modificar `docker-compose.yml` (remove o volume) e a documentação que o cita.

---

### Tarefa 1: Cache de blobs no suap-pdf (`assets.py`)

**Arquivos:**
- Criar: `/home/hugo/workspace/suap-pdf/assets.py`
- Criar: `/home/hugo/workspace/suap-pdf/test_assets.py`

**Interfaces:**
- Consome: nada.
- Produz: `AssetError(Exception)`; `BLOBS_DIRECTORY: str`; `missing(assets: dict[str, str]) -> list[str]`; `store(blobs: dict[str, str]) -> None`; `materialize(assets: dict[str, str], dest: str) -> None`. Em `assets`, a chave é o caminho relativo a `/static/` e o valor é o sha256; em `blobs`, a chave é o sha256 e o valor é o conteúdo em base64.

- [ ] **Passo 1: Escrever o teste que falha**

Crie `/home/hugo/workspace/suap-pdf/test_assets.py`:

```python
# Script de asserts (o repo não usa pytest). Roda fora da imagem: só stdlib.
import base64
import hashlib
import os
import shutil
import tempfile

import assets


def _b64(data):
    return base64.b64encode(data).decode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def com_cache_temporario(func):
    def wrapper():
        original = assets.BLOBS_DIRECTORY
        assets.BLOBS_DIRECTORY = tempfile.mkdtemp()
        try:
            func()
        finally:
            shutil.rmtree(assets.BLOBS_DIRECTORY, ignore_errors=True)
            assets.BLOBS_DIRECTORY = original
        print(f'ok {func.__name__}')

    return wrapper


@com_cache_temporario
def test_missing_lista_o_que_nao_esta_em_cache():
    conteudo = b'body { color: red; }'
    sha = _sha(conteudo)
    assert assets.missing({'a/x.css': sha}) == [sha]
    assets.store({sha: _b64(conteudo)})
    assert assets.missing({'a/x.css': sha}) == []


@com_cache_temporario
def test_store_rejeita_hash_que_nao_confere():
    try:
        assets.store({_sha(b'outra coisa'): _b64(b'conteudo')})
    except assets.AssetError:
        return
    raise AssertionError('esperava AssetError para hash que não confere')


@com_cache_temporario
def test_store_rejeita_base64_invalido():
    try:
        assets.store({'a' * 64: 'nao é base64!!'})
    except assets.AssetError:
        return
    raise AssertionError('esperava AssetError para base64 inválido')


@com_cache_temporario
def test_store_e_idempotente():
    conteudo = b'x'
    sha = _sha(conteudo)
    assets.store({sha: _b64(conteudo)})
    assets.store({sha: _b64(conteudo)})
    assert assets.missing({'x': sha}) == []


@com_cache_temporario
def test_materialize_cria_arquivo_legivel_em_subdiretorio():
    conteudo = b'@font-face { src: url(./Calibri.ttf); }'
    sha = _sha(conteudo)
    assets.store({sha: _b64(conteudo)})
    dest = tempfile.mkdtemp()
    assets.materialize({'ckeditor/ckeditor/contents.css': sha}, dest)
    caminho = os.path.join(dest, 'ckeditor/ckeditor/contents.css')
    with open(caminho, 'rb') as arquivo:
        assert arquivo.read() == conteudo
    shutil.rmtree(dest, ignore_errors=True)


@com_cache_temporario
def test_materialize_rejeita_chave_com_travessia():
    conteudo = b'x'
    sha = _sha(conteudo)
    assets.store({sha: _b64(conteudo)})
    dest = tempfile.mkdtemp()
    for chave in ('../fora.css', '/etc/passwd', 'a/../../fora.css'):
        try:
            assets.materialize({chave: sha}, dest)
        except assets.AssetError:
            continue
        raise AssertionError(f'esperava AssetError para a chave {chave}')
    shutil.rmtree(dest, ignore_errors=True)


@com_cache_temporario
def test_missing_rejeita_hash_malformado():
    try:
        assets.missing({'x.css': '../../etc/passwd'})
    except assets.AssetError:
        return
    raise AssertionError('esperava AssetError para sha256 malformado')


if __name__ == '__main__':
    test_missing_lista_o_que_nao_esta_em_cache()
    test_store_rejeita_hash_que_nao_confere()
    test_store_rejeita_base64_invalido()
    test_store_e_idempotente()
    test_materialize_cria_arquivo_legivel_em_subdiretorio()
    test_materialize_rejeita_chave_com_travessia()
    test_missing_rejeita_hash_malformado()
    print('todos os testes de assets passaram')
```

- [ ] **Passo 2: Rodar o teste e conferir que falha**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py
```

Esperado: `ModuleNotFoundError: No module named 'assets'`.

- [ ] **Passo 3: Escrever a implementação mínima**

Crie `/home/hugo/workspace/suap-pdf/assets.py`:

```python
import base64
import binascii
import hashlib
import os
import posixpath
import re
import tempfile

# Blobs endereçados por conteúdo. Ficam em volume/ (no suap_deploy, montado em
# /opt/suap-pdf/volume), ao lado de volume/certs/ usado pelo signer.
BLOBS_DIRECTORY = os.path.join('volume', 'assets')

SHA256 = re.compile(r'^[0-9a-f]{64}$')


class AssetError(Exception):
    """Erro de cliente ao enviar assets: chave, hash ou base64 inválidos."""


def missing(assets):
    """Devolve, ordenados, os hashes de `assets` que ainda não estão em cache."""
    pendentes = {_checked_sha(sha) for sha in assets.values()}
    return sorted(sha for sha in pendentes if not os.path.isfile(_blob_path(sha)))


def store(blobs):
    """Grava cada blob recebido em base64, conferindo o hash informado."""
    os.makedirs(BLOBS_DIRECTORY, exist_ok=True)
    for sha, content in blobs.items():
        _checked_sha(sha)
        try:
            data = base64.b64decode(content, validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise AssetError(f'Blob {sha} não é base64 válido.')
        if hashlib.sha256(data).hexdigest() != sha:
            raise AssetError(f'Blob {sha} não confere com o conteúdo enviado.')
        _write_atomic(_blob_path(sha), data)


def materialize(assets, dest):
    """Monta `dest` com um symlink por asset, apontando para o blob em cache."""
    for key, sha in assets.items():
        path = _safe_join(dest, key)
        blob = os.path.abspath(_blob_path(_checked_sha(sha)))
        if not os.path.isfile(blob):
            raise AssetError(f'Blob {sha} não está em cache.')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.lexists(path):
            os.symlink(blob, path)


def _blob_path(sha):
    return os.path.join(BLOBS_DIRECTORY, sha)


def _checked_sha(sha):
    if not isinstance(sha, str) or not SHA256.match(sha):
        raise AssetError(f'Hash inválido: {sha!r}. Esperado sha256 em hexadecimal minúsculo.')
    return sha


def _safe_join(dest, key):
    if not isinstance(key, str) or not key or key.startswith('/') or '\\' in key:
        raise AssetError(f'Chave de asset inválida: {key!r}.')
    relativo = posixpath.normpath(key)
    if relativo.startswith('..') or relativo == '.':
        raise AssetError(f'Chave de asset inválida: {key!r}.')
    path = os.path.realpath(os.path.join(dest, relativo))
    if os.path.commonpath([path, os.path.realpath(dest)]) != os.path.realpath(dest):
        raise AssetError(f'Chave de asset escapa do diretório do request: {key!r}.')
    return path


def _write_atomic(path, data):
    # Dois requests simultâneos podem trazer o mesmo blob: escreve num temporário
    # no mesmo diretório e troca de nome, que é atômico no mesmo sistema de arquivos.
    handle, temporario = tempfile.mkstemp(dir=BLOBS_DIRECTORY)
    try:
        with os.fdopen(handle, 'wb') as arquivo:
            arquivo.write(data)
        os.replace(temporario, path)
    except BaseException:
        os.unlink(temporario)
        raise
```

- [ ] **Passo 4: Rodar o teste e conferir que passa**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py
```

Esperado: sete linhas `ok test_...` e `todos os testes de assets passaram`.

- [ ] **Passo 5: Rodar o lint**

```bash
cd /home/hugo/workspace/suap-pdf && ruff format --check assets.py test_assets.py && ruff check assets.py test_assets.py
```

Esperado: `2 files already formatted` e `All checks passed!`. Se o format reclamar, rode `ruff format assets.py test_assets.py`.

- [ ] **Passo 6: Commitar**

```bash
cd /home/hugo/workspace/suap-pdf && git checkout -b feat/assets-via-api && git add assets.py test_assets.py && git commit -m "feat: cache de assets endereçado por conteúdo

Guarda os estáticos enviados pelo SUAP em volume/assets/<sha256> e monta,
por request, um diretório com um symlink por asset.

Changelog: added"
```

---

### Tarefa 2: `make_absolute_paths` aceita a raiz

**Arquivos:**
- Modificar: `/home/hugo/workspace/suap-pdf/wkhtml.py:82-107`
- Modificar: `/home/hugo/workspace/suap-pdf/test_assets.py`

**Interfaces:**
- Consome: nada da Tarefa 1.
- Produz: `wkhtml.make_absolute_paths(content: str, root: str | None = None) -> str`. Com `root=None`, mantém o comportamento atual (`SUAP_PDF_STATIC_ROOT`, default `/opt/suap-pdf/static`).

- [ ] **Passo 1: Escrever o teste que falha**

Acrescente ao final de `test_assets.py`, **antes** do bloco `if __name__ == '__main__':`:

```python
def test_make_absolute_paths_usa_a_raiz_informada():
    import wkhtml

    html = '<link href="/static/a/x.css?v=1"><img src="/static/b.png">'
    resultado = wkhtml.make_absolute_paths(html, '/tmp/req123/static')
    assert 'file:///tmp/req123/static/a/x.css?v=1' in resultado, resultado
    assert 'file:///tmp/req123/static/b.png' in resultado, resultado
    print('ok test_make_absolute_paths_usa_a_raiz_informada')


def test_make_absolute_paths_sem_raiz_usa_a_variavel_de_ambiente():
    import wkhtml

    os.environ['SUAP_PDF_STATIC_ROOT'] = '/opt/suap-pdf/static'
    resultado = wkhtml.make_absolute_paths('<img src="/static/b.png">')
    assert 'file:///opt/suap-pdf/static/b.png' in resultado, resultado
    print('ok test_make_absolute_paths_sem_raiz_usa_a_variavel_de_ambiente')
```

E acrescente as duas chamadas no bloco `if __name__ == '__main__':`, logo antes do `print` final:

```python
    test_make_absolute_paths_usa_a_raiz_informada()
    test_make_absolute_paths_sem_raiz_usa_a_variavel_de_ambiente()
```

- [ ] **Passo 2: Rodar o teste e conferir que falha**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py
```

Esperado: `TypeError: make_absolute_paths() takes 1 positional argument but 2 were given`.

- [ ] **Passo 3: Escrever a implementação mínima**

Em `wkhtml.py`, troque a assinatura e o dicionário de `overrides`:

```python
def make_absolute_paths(content, root=None):
    """Convert all MEDIA files into a file://URL paths in order to
    correctly get it displayed in PDFs."""
    overrides = [
        {
            'root': root or os.environ.get('SUAP_PDF_STATIC_ROOT', '/opt/suap-pdf/static'),
            'url': '/static/',
        }
    ]
```

O resto do corpo da função não muda.

- [ ] **Passo 4: Rodar o teste e conferir que passa**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py
```

Esperado: nove linhas `ok test_...` e `todos os testes de assets passaram`.

- [ ] **Passo 5: Commitar**

```bash
cd /home/hugo/workspace/suap-pdf && ruff format --check wkhtml.py test_assets.py && ruff check wkhtml.py test_assets.py && git add wkhtml.py test_assets.py && git commit -m "feat: make_absolute_paths aceita a raiz dos estáticos

Sem o parâmetro, mantém o SUAP_PDF_STATIC_ROOT de hoje.

Changelog: changed"
```

---

### Tarefa 3: Endpoint `wkhtml_to_pdf` com assets, 409 e diretório único

**Arquivos:**
- Modificar: `/home/hugo/workspace/suap-pdf/main.py:162-190`
- Modificar: `/home/hugo/workspace/suap-pdf/Dockerfile:15-23`
- Modificar: `/home/hugo/workspace/suap-pdf/test.py`
- Modificar: `/home/hugo/workspace/suap-pdf/README.md`

**Interfaces:**
- Consome: `assets.AssetError`, `assets.missing`, `assets.store`, `assets.materialize` (Tarefa 1); `wkhtml.make_absolute_paths(content, root)` (Tarefa 2).
- Produz: o contrato HTTP que a Tarefa 5 usa — `POST /api/v1/wkhtml_to_pdf` aceitando `assets: {chave: sha256}` e `blobs: {sha256: base64}`, respondendo `409 {"missing": [sha256, ...]}` e `400 {"message": "..."}`.

- [ ] **Passo 1: Escrever os testes que falham**

Acrescente a `test.py`, depois de `test_html_to_pdf`:

```python
def test_wkhtml_to_pdf_com_assets():
    os.makedirs('output', exist_ok=True)
    css = b'body { color: #333; }'
    sha = hashlib.sha256(css).hexdigest()
    template = '<html><head><link rel="stylesheet" href="/static/x/estilo.css"></head><body><p>Olá</p></body></html>'
    url = f'{BASE_URL}/api/v1/wkhtml_to_pdf'

    # 1) sem os blobs, o serviço pede o que falta
    data = {'template': template, 'options': {}, 'assets': {'x/estilo.css': sha}}
    loginput(url, data)
    response = client.post(url, json=data, headers=headers)
    logoutput(response)
    assert response.status_code == 409, response.status_code
    assert response.json()['missing'] == [sha], response.json()

    # 2) com os blobs, gera o PDF e popula o cache
    data['blobs'] = {sha: base64.b64encode(css).decode()}
    response = client.post(url, json=data, headers=headers)
    assert response.status_code == 200, response.content[:200]
    with open(os.path.join('output', 'wkhtml-assets.pdf'), 'w+b') as file:
        file.write(response.content)

    # 3) o request seguinte acerta o cache, sem reenviar conteúdo
    del data['blobs']
    response = client.post(url, json=data, headers=headers)
    assert response.status_code == 200, response.content[:200]


def test_wkhtml_to_pdf_rejeita_chave_com_travessia():
    css = b'body { color: #333; }'
    sha = hashlib.sha256(css).hexdigest()
    url = f'{BASE_URL}/api/v1/wkhtml_to_pdf'
    data = {
        'template': '<p>x</p>',
        'options': {},
        'assets': {'../fora.css': sha},
        'blobs': {sha: base64.b64encode(css).decode()},
    }
    loginput(url, data)
    response = client.post(url, json=data, headers=headers)
    logoutput(response)
    assert response.status_code == 400, response.status_code
    assert 'message' in response.json(), response.json()


def test_wkhtml_to_pdf_rejeita_blob_que_nao_confere():
    url = f'{BASE_URL}/api/v1/wkhtml_to_pdf'
    sha = hashlib.sha256(b'conteudo esperado').hexdigest()
    data = {
        'template': '<p>x</p>',
        'options': {},
        'assets': {'x/estilo.css': sha},
        'blobs': {sha: base64.b64encode(b'outro conteudo').decode()},
    }
    loginput(url, data)
    response = client.post(url, json=data, headers=headers)
    logoutput(response)
    assert response.status_code == 400, response.status_code


def test_wkhtml_to_pdf_sem_assets_usa_o_fallback():
    # Compatibilidade: SUAP ainda não atualizado não manda `assets`, e o serviço
    # precisa seguir gerando o PDF pelo SUAP_PDF_STATIC_ROOT.
    os.makedirs('output', exist_ok=True)
    url = f'{BASE_URL}/api/v1/wkhtml_to_pdf'
    data = {'template': '<html><body><p>Sem assets</p></body></html>', 'options': {}}
    loginput(url, data)
    response = client.post(url, json=data, headers=headers)
    logoutput(response)
    assert response.status_code == 200, response.content[:200]
    assert response.content[:4] == b'%PDF', response.content[:200]
    with open(os.path.join('output', 'wkhtml-sem-assets.pdf'), 'w+b') as file:
        file.write(response.content)
```

No topo de `test.py`, acrescente `import hashlib` depois de `import base64`. E no bloco `if __name__ == '__main__':`, acrescente as quatro chamadas logo depois de `test_html_to_pdf()`:

```python
    test_wkhtml_to_pdf_com_assets()
    test_wkhtml_to_pdf_rejeita_chave_com_travessia()
    test_wkhtml_to_pdf_rejeita_blob_que_nao_confere()
    test_wkhtml_to_pdf_sem_assets_usa_o_fallback()
```

Atenção ao rodar: o cache de assets fica em `volume/`, que é bind-mounted do host. Uma
segunda rodada do `test.py` sem limpar `volume/` faz a asserção de `409` falhar, porque o
blob já está em cache (conteúdo igual ⇒ mesmo sha256). Limpe `output/` e `volume/` antes de
cada execução.

- [ ] **Passo 2: Rodar os testes e conferir que falham**

Precisa do wkhtmltopdf, então roda dentro da imagem. `SUAP_PDF_STATIC_ROOT` vai para um diretório vazio de propósito: é o que prova que o PDF sai sem depender de volume.

```bash
cd /home/hugo/workspace/suap-pdf && echo dev > pdf-version.txt && docker build -t suap-pdf . && docker run --rm -v "$PWD":/opt/suap-pdf -w /opt/suap-pdf -e SUAP_PDF_SENTRY_URL= -e SUAP_PDF_STATIC_ROOT=/vazio suap-pdf python test.py
```

Esperado: falha em `test_wkhtml_to_pdf_com_assets`, com `assert response.status_code == 409` recebendo 200 (o endpoint ainda ignora `assets`).

- [ ] **Passo 3: Escrever a implementação**

Em `main.py`, acrescente aos imports do topo (depois de `import tempfile`):

```python
import shutil
```

e, junto dos imports de módulos locais (depois de `import utils`):

```python
import assets as assets_store
```

Substitua o endpoint inteiro (`main.py:162-190`) por:

```python
def _write_html(workdir, name, content, root):
    path = os.path.join(workdir, name)
    with open(path, 'w') as file:
        file.write(wkhtml.make_absolute_paths(content, root))
    return path


def _prepare_assets(workdir, body):
    """Devolve a raiz dos estáticos do request, ou None para usar o fallback."""
    asset_hashes = body.get('assets') or {}
    if not asset_hashes:
        return None, None
    assets_store.store(body.get('blobs') or {})
    pending = assets_store.missing(asset_hashes)
    if pending:
        return None, Response(json.dumps(dict(missing=pending)), status_code=409, headers={'content-type': 'application/json'})
    root = os.path.join(workdir, 'static')
    assets_store.materialize(asset_hashes, root)
    return root, None


@app.post("/api/v1/wkhtml_to_pdf")
@endpoint(True)
async def wkhtml_to_pdf(request: Request):
    body = await request.json()
    template = body.get('template')
    header_template = body.get('header_template')
    footer_template = body.get('footer_template')
    options = body.get('options')

    # Um diretório por request abriga os assets e os HTMLs de corpo, cabeçalho e
    # rodapé: o rmtree no finally não deixa nenhum deles para trás em /tmp.
    workdir = tempfile.mkdtemp()
    try:
        try:
            root, conflict = _prepare_assets(workdir, body)
        except assets_store.AssetError as e:
            return Response(json.dumps(dict(message=str(e))), status_code=400, headers={'content-type': 'application/json'})
        if conflict is not None:
            return conflict

        path = _write_html(workdir, 'template.html', template, root)
        if header_template:
            options['header_html'] = _write_html(workdir, 'header.html', header_template, root)
        if footer_template:
            options['footer_html'] = _write_html(workdir, 'footer.html', footer_template, root)

        pdf = wkhtml.convert_to_pdf(path, options)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return Response(
        pdf,
        headers={'Content-Disposition': 'inline; filename="arquivo.pdf"'},
        media_type='application/pdf',
    )
```

Em `Dockerfile`, acrescente logo depois da linha `ADD utils.py utils.py`:

```dockerfile
ADD assets.py assets.py
```

- [ ] **Passo 4: Rodar os testes e conferir que passam**

```bash
cd /home/hugo/workspace/suap-pdf && docker build -t suap-pdf . && docker run --rm -v "$PWD":/opt/suap-pdf -w /opt/suap-pdf -e SUAP_PDF_SENTRY_URL= -e SUAP_PDF_STATIC_ROOT=/vazio suap-pdf python test.py
```

Esperado: o script chega ao fim sem `AssertionError`, e `output/wkhtml-assets.pdf` existe. Confirme que o PDF saiu com o CSS aplicado apesar do `SUAP_PDF_STATIC_ROOT=/vazio`.

Os arquivos de `output/` e `volume/` são criados como root; limpe com:

```bash
cd /home/hugo/workspace/suap-pdf && docker run --rm -v "$PWD":/opt/suap-pdf -w /opt/suap-pdf suap-pdf rm -rf output volume __pycache__
```

- [ ] **Passo 5: Atualizar o README**

Em `/home/hugo/workspace/suap-pdf/README.md`:

1. Na tabela de configuração (linha 54), substitua a linha do `SUAP_PDF_STATIC_ROOT` por:

```markdown
| `SUAP_PDF_STATIC_ROOT` | `/opt/suap-pdf/static` | **Fallback legado.** Raiz dos estáticos no `wkhtml_to_pdf` quando a requisição **não** traz `assets`: referências `"/static/..."` no HTML viram `file://<raiz>/...`. O SUAP atual envia os estáticos pela própria API (campo `assets`), e essa variável só existe para compatibilidade com versões anteriores. |
```

2. Na lista de observações dos endpoints, logo depois do item de `wkhtml_to_pdf` (linha 88-90), acrescente:

```markdown
- **`wkhtml_to_pdf`, estáticos**: `assets` mapeia cada caminho relativo a `/static/` (sem query
  string, sem `/` inicial e sem `..`) para o **sha256** do conteúdo. Os blobs ficam em cache em
  `volume/assets/<sha256>`; se algum faltar, a resposta é `409 {"missing": [sha256, ...]}` e o
  cliente reenvia o mesmo request acrescentando `blobs: {"<sha256>": "<base64>"}`. Chave inválida,
  base64 inválido ou hash que não confere respondem `400`. Sem `assets`, vale o fallback
  `SUAP_PDF_STATIC_ROOT`.
```

3. Na seção de deploy, substitua o parágrafo das linhas 168-171 (que explica por que não se usa `make down`) por:

```markdown
Não usa `make down`/`make up` do `suap_deploy` de propósito: o `up -d` recria só o que mudou de
imagem e preserva o volume `volume/` (certificados salvos e cache de assets), enquanto o
`make down` apaga volumes do SUAP sem necessidade para este serviço.
```

- [ ] **Passo 6: Commitar**

```bash
cd /home/hugo/workspace/suap-pdf && ruff format --check main.py test.py && ruff check main.py test.py assets.py && git add main.py Dockerfile test.py README.md && git commit -m "feat: wkhtml_to_pdf recebe os estáticos pela API

O SUAP passa a enviar assets: {caminho: sha256} e, quando pedido via 409,
blobs: {sha256: base64}. Sem assets, mantém o fallback SUAP_PDF_STATIC_ROOT.
O diretório do request passa a abrigar também os HTMLs de cabeçalho e rodapé,
que antes ficavam para trás em /tmp.

Changelog: added"
```

---

### Tarefa 4: Coleta dos estáticos no SUAP (`estaticos_pdf.py`)

Daqui em diante, trabalhe em `/home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd`, na branch `claude/suap-pdf-static-decoupling-e9d287`.

**Arquivos:**
- Criar: `djtools/utils/estaticos_pdf.py`
- Criar: `djtools/tests/utils/test_utils_estaticos_pdf.py`
- Modificar: `djtools/utils/__init__.py:8` (a lista de imports é alfabética; `estaticos_pdf` entra entre `email` e `files`)

**Interfaces:**
- Consome: nada das tarefas anteriores (só o formato de `assets` do contrato da Tarefa 3).
- Produz: `Asset(NamedTuple)` com os campos `sha256: str` e `base64: str`; `coletar_assets(*htmls: str) -> dict[str, Asset]`, cuja chave é o caminho relativo a `/static/`, sem query string.

- [ ] **Passo 1: Escrever os testes que falham**

Crie `djtools/tests/utils/test_utils_estaticos_pdf.py`:

```python
from __future__ import annotations

import base64
import hashlib

import pytest
from django.contrib.staticfiles import finders
from django.test import override_settings

from djtools.utils.estaticos_pdf import coletar_assets


@pytest.fixture
def raiz_estatica(tmp_path, settings):
    """Um STATICFILES_DIRS temporário, para os testes não dependerem dos apps."""
    (tmp_path / 'css').mkdir()
    (tmp_path / 'img').mkdir()
    (tmp_path / 'css' / 'estilo.css').write_bytes(b'@font-face { src: url(./fonte.ttf); }')
    (tmp_path / 'css' / 'fonte.ttf').write_bytes(b'fonte binaria')
    (tmp_path / 'img' / 'logo.png').write_bytes(b'png')
    (tmp_path / 'img' / 'copia.png').write_bytes(b'png')
    settings.STATICFILES_DIRS = [str(tmp_path)]
    # finders.get_finder é lru_cache e o FileSystemFinder lê STATICFILES_DIRS no
    # __init__: sem limpar o cache, o segundo teste em diante olharia o diretório
    # do teste anterior. Verificado empiricamente — não remova.
    finders.get_finder.cache_clear()
    yield tmp_path
    finders.get_finder.cache_clear()


class TestColetarAssets:
    def test_coleta_link_img_e_url_css_inline(self, raiz_estatica):
        html = """
            <link rel="stylesheet" href="/static/css/estilo.css?v=abc123">
            <img src="/static/img/logo.png">
            <style>body { background: url('/static/img/logo.png'); }</style>
        """
        assets = coletar_assets(html)
        assert set(assets) == {'css/estilo.css', 'css/fonte.ttf', 'img/logo.png'}

    def test_chave_descarta_query_e_fragmento(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png?t=FB9E#x">')
        assert list(assets) == ['img/logo.png']

    def test_ref_relativa_dentro_do_css_resolve_contra_o_css(self, raiz_estatica):
        assets = coletar_assets('<link href="/static/css/estilo.css">')
        assert 'css/fonte.ttf' in assets
        conteudo = base64.b64decode(assets['css/fonte.ttf'].base64)
        assert conteudo == b'fonte binaria'

    def test_sha256_e_base64_conferem_com_o_arquivo(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png">')
        asset = assets['img/logo.png']
        assert asset.sha256 == hashlib.sha256(b'png').hexdigest()
        assert base64.b64decode(asset.base64) == b'png'

    def test_mesmo_conteudo_em_dois_caminhos_gera_o_mesmo_hash(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png"><img src="/static/img/copia.png">')
        assert assets['img/logo.png'].sha256 == assets['img/copia.png'].sha256

    def test_ignora_refs_externas_data_e_media(self, raiz_estatica):
        html = """
            <img src="https://exemplo.edu.br/x.png">
            <img src="data:image/png;base64,AAAA">
            <img src="/media/upload/foto.png">
        """
        assert coletar_assets(html) == {}

    def test_arquivo_inexistente_nao_levanta_e_fica_de_fora(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/nao-existe.png">')
        assert assets == {}

    def test_varre_todos_os_htmls_sem_duplicar(self, raiz_estatica):
        corpo = '<img src="/static/img/logo.png">'
        cabecalho = '<link href="/static/css/estilo.css">'
        rodape = '<link href="/static/css/estilo.css">'
        assets = coletar_assets(corpo, cabecalho, rodape)
        assert set(assets) == {'img/logo.png', 'css/estilo.css', 'css/fonte.ttf'}

    def test_aceita_html_vazio_ou_none(self, raiz_estatica):
        assert coletar_assets('', None) == {}

    def test_chave_nunca_escapa_da_raiz(self, raiz_estatica):
        assert coletar_assets('<img src="/static/../../etc/passwd">') == {}

    @override_settings(STATIC_ROOT='/tmp/static-root-inexistente')
    def test_sem_o_arquivo_em_lugar_nenhum_retorna_vazio(self):
        assert coletar_assets('<img src="/static/qualquer/coisa.png">') == {}

    def test_resolve_pelo_static_root_quando_o_finder_nao_acha(self, tmp_path, settings):
        # Pós-collectstatic: o arquivo só existe no STATIC_ROOT, fora dos static/ dos apps.
        (tmp_path / 'coletado.png').write_bytes(b'png coletado')
        settings.STATICFILES_DIRS = []
        settings.STATIC_ROOT = str(tmp_path)
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<img src="/static/coletado.png">')
            assert set(assets) == {'coletado.png'}
            assert base64.b64decode(assets['coletado.png'].base64) == b'png coletado'
        finally:
            finders.get_finder.cache_clear()


class TestCicloEntreCss:
    def test_import_circular_nao_entra_em_laco(self, tmp_path, settings):
        (tmp_path / 'a.css').write_bytes(b'@import "b.css";')
        (tmp_path / 'b.css').write_bytes(b'@import "a.css";')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/a.css">')
            assert set(assets) == {'a.css', 'b.css'}
        finally:
            finders.get_finder.cache_clear()

    def test_import_com_url_resolve_o_alvo(self, tmp_path, settings):
        # `@import url("x.css")` existe no repo (djtools/static/.../jquery.ui.base.css).
        (tmp_path / 'base.css').write_bytes(b'@import url("core.css");\n@import url(outro.css);')
        (tmp_path / 'core.css').write_bytes(b'p { color: red; }')
        (tmp_path / 'outro.css').write_bytes(b'p { color: blue; }')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/base.css">')
            assert set(assets) == {'base.css', 'core.css', 'outro.css'}
        finally:
            finders.get_finder.cache_clear()

    def test_ref_absoluta_dentro_do_css_vira_a_mesma_chave_do_html(self, tmp_path, settings):
        # `url(/static/...)` dentro de CSS existe no repo (djtools/static/djtools/css/anonima.css).
        (tmp_path / 'sub').mkdir()
        (tmp_path / 'sub' / 'tema.css').write_bytes(b'body { background-image: url(/static/sub/logo.svg); }')
        (tmp_path / 'sub' / 'logo.svg').write_bytes(b'<svg/>')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/sub/tema.css">')
            assert set(assets) == {'sub/tema.css', 'sub/logo.svg'}
        finally:
            finders.get_finder.cache_clear()

    def test_import_url_externo_e_ignorado(self, tmp_path, settings):
        (tmp_path / 'x.css').write_bytes(b"@import url('https://fonts.googleapis.com/css2?family=Open+Sans');")
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assert set(coletar_assets('<link href="/static/x.css">')) == {'x.css'}
        finally:
            finders.get_finder.cache_clear()
```

- [ ] **Passo 2: Rodar os testes e conferir que falham**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest djtools/tests/utils/test_utils_estaticos_pdf.py -q
```

Esperado: `ModuleNotFoundError: No module named 'djtools.utils.estaticos_pdf'`.

- [ ] **Passo 3: Escrever a implementação**

Crie `djtools/utils/estaticos_pdf.py`:

```python
from __future__ import annotations

import base64
import hashlib
import logging
import os
import posixpath
import re
from functools import lru_cache
from typing import NamedTuple

from django.conf import settings
from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)

# Refs a /static/ dentro de aspas (href, src) ou de url(...) em CSS inline.
REF_ESTATICO = re.compile(r"""["'(]\s*/static/([^"')\s>]+)""")
# Refs dentro de um arquivo CSS: url(...) e @import, inclusive a forma
# `@import url(...)` — sem o `(?:url\()?` o grupo captura o literal "url(" em vez
# do alvo, e a ref aninhada some em silêncio.
REF_CSS = re.compile(r"""(?:url\(|@import\s+(?:url\()?)\s*["']?([^"')\s;]+)""")
EXTERNAS = ('data:', 'http:', 'https:', '//')


class Asset(NamedTuple):
    """Conteúdo de um arquivo estático, pronto para ir na API do suap-pdf."""

    sha256: str
    base64: str


def coletar_assets(*htmls: str | None) -> dict[str, Asset]:
    """Mapeia os `/static/` referenciados nos HTMLs para o conteúdo do arquivo.

    A varredura é feita no HTML já renderizado, então cobre tanto as referências
    dos templates quanto as que vierem no conteúdo escrito pelo usuário. Cada CSS
    coletado é varrido também, para trazer o que ele referencia (fontes, imagens).

    Args:
        htmls: os HTMLs de corpo, cabeçalho e rodapé.

    Returns:
        Dicionário do caminho relativo a `/static/` (sem query) para o `Asset`.
    """
    assets: dict[str, Asset] = {}
    for html in htmls:
        for ref in REF_ESTATICO.findall(html or ''):
            _coletar(_chave(ref), assets)
    return assets


def _chave(ref: str) -> str:
    return posixpath.normpath(ref.split('?')[0].split('#')[0].lstrip('/'))


def _coletar(chave: str, assets: dict[str, Asset]) -> None:
    if chave in assets or chave.startswith('..') or chave in ('.', '/'):
        return
    caminho = _resolver(chave)
    if not caminho:
        logger.warning('Estático não encontrado para a impressão em PDF: %s', chave)
        return
    assets[chave] = _ler(caminho, os.path.getmtime(caminho))
    if chave.endswith('.css'):
        _coletar_refs_do_css(chave, caminho, assets)


def _coletar_refs_do_css(chave: str, caminho: str, assets: dict[str, Asset]) -> None:
    with open(caminho, encoding='utf-8', errors='ignore') as arquivo:
        css = arquivo.read()
    diretorio = posixpath.dirname(chave)
    for ref in REF_CSS.findall(css):
        ref = ref.strip('\'"')
        if not ref or ref.startswith(EXTERNAS):
            continue
        if ref.startswith('/static/'):
            # Sem o removeprefix a chave sairia como 'static/x.png': o _chave só tira
            # as barras iniciais, não o segmento 'static/', e o arquivo não resolveria.
            _coletar(_chave(ref.removeprefix('/static/')), assets)
        elif not ref.startswith('/'):
            _coletar(_chave(posixpath.join(diretorio, ref)), assets)


def _resolver(chave: str) -> str | None:
    # finders.find acha nos static/ dos apps sem depender do collectstatic, o que
    # faz o mesmo código valer em dev e nos containers web e celery.
    caminho = finders.find(chave)
    if caminho:
        return caminho if isinstance(caminho, str) else caminho[0]
    caminho = os.path.join(settings.STATIC_ROOT, chave)
    return caminho if os.path.isfile(caminho) else None


@lru_cache(maxsize=256)
def _ler(caminho: str, mtime: float) -> Asset:
    # mtime entra na chave do cache só para invalidar quando o arquivo muda.
    with open(caminho, 'rb') as arquivo:
        conteudo = arquivo.read()
    return Asset(hashlib.sha256(conteudo).hexdigest(), base64.b64encode(conteudo).decode())
```

Em `djtools/utils/__init__.py`, acrescente a linha na posição alfabética, entre `email` e `files`:

```python
from djtools.utils.estaticos_pdf import *
```

- [ ] **Passo 4: Rodar os testes e conferir que passam**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest djtools/tests/utils/test_utils_estaticos_pdf.py -q
```

Esperado: `Total: 16  Passed: 16  Failed: 0`.

- [ ] **Passo 5: Commitar**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && git add djtools/utils/estaticos_pdf.py djtools/utils/__init__.py djtools/tests/utils/test_utils_estaticos_pdf.py && git commit -m "[djtools] Coleta os estáticos referenciados pelo HTML de impressão

Varre o HTML renderizado atrás de /static/, resolve cada arquivo em disco e
devolve sha256 + base64. Varre também os CSS coletados, o que traz as fontes
e imagens referenciadas por caminho relativo dentro deles."
```

---

### Tarefa 5: Enviar os assets e tratar o 409

**Arquivos:**
- Modificar: `djtools/utils/pdf.py:316-347`
- Modificar: `djtools/tests/utils/test_utils_pdf.py`

**Interfaces:**
- Consome: `coletar_assets` e `Asset` (Tarefa 4); o contrato HTTP da Tarefa 3.
- Produz: nenhuma interface nova — `render_pdf_from_template_with_wkhtmltopdf` mantém a assinatura atual.

- [ ] **Passo 1: Escrever os testes que falham**

Acrescente ao final de `djtools/tests/utils/test_utils_pdf.py`:

```python
class TestRenderPdfComWkhtmltopdf:
    """O ramo HTTP de render_pdf_from_template_with_wkhtmltopdf."""

    def _configuracao(self, _app, chave, _enviroment_variable_name=None):
        # A assinatura real é get_valor_por_chave(cls, app, chave, ...) — o app vem antes
        # da chave (comum/models.py:1568). Inverter a ordem dá KeyError: 'comum'.
        return {'caminho_libreoffice': 'http://pdfprinter:8000', 'token_libreoffice': 'segredo'}[chave]

    def _resposta(self, status_code, content=b'%PDF-1.4', json_data=None):
        resposta = MagicMock(status_code=status_code, content=content, text='')
        resposta.json.return_value = json_data or {}
        return resposta

    def _chamar(self, mock_post, assets):
        from djtools.utils.pdf import render_pdf_from_template_with_wkhtmltopdf

        with (
            patch('comum.models.Configuracao.get_valor_por_chave', side_effect=self._configuracao),
            patch('djtools.utils.pdf.render_to_string', return_value='<html></html>'),
            patch('djtools.utils.pdf.coletar_assets', return_value=assets),
            patch('djtools.utils.pdf.requests.post', mock_post),
        ):
            return render_pdf_from_template_with_wkhtmltopdf('x.html', cmd_options={'orientation': 'portrait'})

    def test_payload_leva_apenas_os_hashes(self):
        from djtools.utils.estaticos_pdf import Asset

        mock_post = MagicMock(return_value=self._resposta(200))
        assert self._chamar(mock_post, {'css/x.css': Asset('abc', 'Y29udGV1ZG8=')}) == b'%PDF-1.4'
        enviado = mock_post.call_args.kwargs['json']
        assert enviado['assets'] == {'css/x.css': 'abc'}
        assert 'blobs' not in enviado

    def test_409_reenvia_uma_vez_com_os_blobs_faltantes(self):
        from djtools.utils.estaticos_pdf import Asset

        assets = {'css/x.css': Asset('abc', 'AAA='), 'img/y.png': Asset('def', 'BBB=')}
        mock_post = MagicMock(side_effect=[self._resposta(409, json_data={'missing': ['abc']}), self._resposta(200)])
        assert self._chamar(mock_post, assets) == b'%PDF-1.4'
        assert mock_post.call_count == 2
        segundo = mock_post.call_args_list[1].kwargs['json']
        assert segundo['blobs'] == {'abc': 'AAA='}
        assert segundo['assets'] == {'css/x.css': 'abc', 'img/y.png': 'def'}

    def test_segundo_409_levanta_excecao(self):
        from djtools.utils.estaticos_pdf import Asset

        mock_post = MagicMock(return_value=self._resposta(409, json_data={'missing': ['abc']}))
        with pytest.raises(Exception, match='servidor de impressão'):
            self._chamar(mock_post, {'css/x.css': Asset('abc', 'AAA=')})
        assert mock_post.call_count == 2

    def test_sem_cmd_options_nao_levanta(self):
        from djtools.utils.pdf import render_pdf_from_template_with_wkhtmltopdf

        mock_post = MagicMock(return_value=self._resposta(200))
        with (
            patch('comum.models.Configuracao.get_valor_por_chave', side_effect=self._configuracao),
            patch('djtools.utils.pdf.render_to_string', return_value='<html></html>'),
            patch('djtools.utils.pdf.coletar_assets', return_value={}),
            patch('djtools.utils.pdf.requests.post', mock_post),
        ):
            assert render_pdf_from_template_with_wkhtmltopdf('x.html') == b'%PDF-1.4'
        assert mock_post.call_args.kwargs['json']['options'] == {}
```

- [ ] **Passo 2: Rodar os testes e conferir que falham**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest djtools/tests/utils/test_utils_pdf.py -q
```

Esperado: falhas em `TestRenderPdfComWkhtmltopdf` — `AttributeError: <module 'djtools.utils.pdf'> does not have the attribute 'coletar_assets'`.

- [ ] **Passo 3: Escrever a implementação**

Em `djtools/utils/pdf.py`, acrescente o import junto dos outros imports locais (depois de `from .breadcrumbs import breadcrumbs_previous_url`):

```python
from .estaticos_pdf import coletar_assets
```

Substitua o começo da função (`djtools/utils/pdf.py:316-347`) por:

```python
def _postar_wkhtml(url: str, data: dict, headers: dict, assets: dict) -> object:
    """Posta no suap-pdf e, se ele pedir os blobs que faltam (409), reenvia uma vez."""
    response = requests.post(url, json=data, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    if response.status_code == 409:
        faltantes = set(response.json().get('missing', []))
        data = dict(data, blobs={asset.sha256: asset.base64 for asset in assets.values() if asset.sha256 in faltantes})
        response = requests.post(url, json=data, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    return response


def render_pdf_from_template_with_wkhtmltopdf(template, header_template=None, footer_template=None, context=None, cmd_options=None):
    if not context:
        context = {}
    cmd_options = {key: str(val is None and '-' or val) for key, val in cmd_options.items()} if cmd_options else {}
    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')
        headers = {'Authorization': f'Token {token_libreoffice}'}
        rendered_template = render_to_string(template, context)
        if header_template:
            rendered_header = render_to_string(header_template, context)
        else:
            rendered_header = ''
        if footer_template:
            rendered_footer = render_to_string(footer_template, context)
        else:
            rendered_footer = ''
        # Os estáticos vão junto do HTML: o suap-pdf não compartilha mais o volume
        # de estáticos do SUAP. Só os hashes são enviados; o conteúdo, se ele pedir.
        assets = coletar_assets(rendered_template, rendered_header, rendered_footer)
        data = {
            'template': rendered_template,
            'header_template': rendered_header,
            'footer_template': rendered_footer,
            'options': cmd_options,
            'assets': {chave: asset.sha256 for chave, asset in assets.items()},
        }
        response = _postar_wkhtml(f'{caminho_libreoffice}/api/v1/wkhtml_to_pdf', data, headers, assets)
        if response.status_code != 200:
            raise Exception(
                f'Erro ao tentar obter resposta do servidor de impressão de PDFs, por favor tente novamente em alguns minutos. Detalhe: {response.text}'
            )
        return response.content
```

O resto da função (ramo `running_tests()` e ramo local com `django-wkhtmltopdf`) não muda.

Note a correção do bug da linha 319-320: antes era `if not cmd_options: cmd_options = {... for ... in cmd_options.items()}`, que levantaria `AttributeError` se alguém chamasse sem `cmd_options`.

- [ ] **Passo 4: Rodar os testes e conferir que passam**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest djtools/tests/utils/ -q
```

Esperado: `Failed: 0  Errors: 0`, com os 27 testes de `test_utils_pdf.py` e os 16 de `test_utils_estaticos_pdf.py`.

- [ ] **Passo 5: Rodar os testes dos apps que usam a função**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && DJANGO_SETTINGS_MODULE=suap.settings_test DATABASE_PORT=5433 uv run pytest documento_eletronico processo_eletronico -q --reuse-db
```

Esperado: mesmo resultado de antes da mudança. Se o Postgres na 5433 não estiver de pé, suba o efêmero documentado no `AGENTS.md`:

```bash
docker run --rm -d --name suap-test-db -p 5433:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements
```

- [ ] **Passo 6: Commitar**

```bash
cd /home/hugo/workspace/suap/.claude/worktrees/agitated-sutherland-b890bd && git add djtools/utils/pdf.py djtools/tests/utils/test_utils_pdf.py && git commit -m "[djtools] Envia os estáticos ao suap-pdf pela API

O payload do wkhtml_to_pdf passa a levar assets: {caminho: sha256} e, quando o
serviço responde 409 pedindo o que falta, reenvia uma única vez com os blobs.
Corrige de passagem o tratamento de cmd_options ausente, que levantava
AttributeError."
```

---

### Tarefa 6: Verificação fim a fim sem o volume

Esta tarefa não altera código: é o portão que autoriza a Tarefa 7. **Toda conferência aqui roda com o volume de estáticos fora** — qualquer PDF gerado com o `suap_static` ainda montado em `/opt/suap-pdf/static` passaria pelo motivo errado.

**Arquivos:** nenhum.

**Interfaces:**
- Consome: tudo das Tarefas 1 a 5.
- Produz: a evidência que libera a remoção do volume.

- [ ] **Passo 1: Subir o pdfprinter novo sem estáticos**

No ambiente de homologação, com a imagem construída na Tarefa 3:

```bash
docker run --rm -d --name pdfprinter-teste -p 9000:8000 -e SUAP_PDF_ACCESS_TOKEN=<token-da-configuracao> -e SUAP_PDF_SENTRY_URL= -e SUAP_PDF_STATIC_ROOT=/vazio suap-pdf
```

Nenhum `-v` com estáticos. Aponte o SUAP para ele em `/comum/configuracao` (chave `caminho_libreoffice` = `http://localhost:9000`, `token_libreoffice` igual ao token acima).

- [ ] **Passo 2: Gerar os PDFs dos quatro casos**

Pelo sistema, gere e guarde cada PDF:

1. `documento_eletronico` — impressão de um documento assinado (o caso mais rico: fonte Calibri, `contents.css`, `documento.css`, `pdf_assinaturas.css`, brasão, logo, selo e QR code).
2. `processo_eletronico` — impressão de um processo com **mais de uma página**, que exercita cabeçalho e rodapé por página.
3. `licenca_capacitacao` — impressão do pedido do servidor, cujo logo vem de MEDIA.
4. `boletim_servico` — geração de um boletim, que é o caminho em lote.

- [ ] **Passo 3: Comparar com o comportamento anterior**

Para cada um dos quatro, compare com o PDF gerado antes da mudança (mesma origem de dados): fonte, brasão, logo, tabelas e o bloco de assinaturas têm que sair idênticos. Qualquer elemento sem estilo indica asset não coletado.

- [ ] **Passo 4: Conferir os avisos de estático não resolvido**

```bash
grep -E "Estático (não encontrado|ilegível) para a impressão em PDF" <log-do-suap>
```

São **duas** mensagens distintas, e as duas importam: `não encontrado` é a referência que não
resolveu em disco; `ilegível` é o arquivo que existe mas não pôde ser lido (permissão, por
exemplo). Grepar só a primeira deixaria a segunda passar em silêncio.

Esperado: nenhuma linha. Se aparecer alguma, decida caso a caso — pode ser uma referência já quebrada hoje (que o volume também não servia) ou um caminho que a coleta não resolveu. Referência já quebrada se registra e segue; caminho não resolvido volta para a Tarefa 4.

- [ ] **Passo 5: Medir o efeito do cache**

```bash
docker logs pdfprinter-teste 2>&1 | tail -30
```

E, no SUAP, cronometre duas impressões seguidas do mesmo documento. Esperado: a primeira envia os blobs (o `409` aparece uma vez por arquivo por container) e a segunda não envia nenhum. Registre os dois tempos e os dois tamanhos de payload — é o que prova o cache.

- [ ] **Passo 6: Registrar o resultado**

Anote no MR do SUAP: os quatro casos conferidos, o diff visual (ou a ausência dele), os avisos encontrados e os números do cache.

---

### Tarefa 7: Remover o volume no suap_deploy

Só execute depois que a Tarefa 6 estiver verde em homologação.

**Arquivos:**
- Modificar: `/home/hugo/workspace/suap_deploy/docker-compose.yml:109-112`

**Interfaces:**
- Consome: a evidência da Tarefa 6.
- Produz: o `pdfprinter` sem dependência do volume `suap_static`.

- [ ] **Passo 1: Remover a linha do volume**

Em `/home/hugo/workspace/suap_deploy/docker-compose.yml`, no serviço `pdfprinter`, apague **apenas** a linha do volume de estáticos:

```yaml
    volumes:
      - "${SUAP_PDF_VOLUME_PATH:-./deploy/pdf}:/opt/suap-pdf/volume"
      - "${SUAP_PDF_VOLUME_PATH:-./deploy/pdf}/tmp:/tmp"
```

O volume `static` continua montado em `web`, `nginx` e `celery` — não toque nesses. O volume nomeado `static` no fim do arquivo também permanece.

- [ ] **Passo 2: Conferir que o compose continua válido**

```bash
cd /home/hugo/workspace/suap_deploy && docker compose config --quiet && echo "compose ok" && grep -n "suap-pdf/static" docker-compose.yml; echo "saída vazia acima = volume removido"
```

Esperado: `compose ok` e nenhuma linha de `grep`.

- [ ] **Passo 3: Subir e gerar um PDF**

```bash
cd /home/hugo/workspace/suap_deploy && docker compose up -d pdfprinter && docker compose ps pdfprinter
```

Gere uma impressão de `documento_eletronico` e confirme que sai estilizada.

- [ ] **Passo 4: Documentar**

Em `/home/hugo/workspace/suap_deploy/docs/FAQ.md`, na seção dos profiles (linha 195 em diante), acrescente ao final da resposta sobre `pdfprinter`:

```markdown
Desde a versão do `suap-pdf` que recebe os estáticos pela API, um nó só com o profile
`pdfprinter` não precisa mais do volume `suap_static` — o SUAP envia no próprio request tudo
que o HTML referencia. Antes disso, um nó sem o `web` tinha o volume vazio e gerava PDFs sem
estilo.
```

- [ ] **Passo 5: Commitar**

```bash
cd /home/hugo/workspace/suap_deploy && git checkout -b feat/pdfprinter-sem-volume-static && git add docker-compose.yml docs/FAQ.md && git commit -m "feat(pdfprinter): remove o volume de estáticos do SUAP

O suap-pdf passou a receber os estáticos pela API, no próprio request do
wkhtml_to_pdf. Um nó só com o profile pdfprinter não depende mais do
suap_static, que nele ficava vazio."
```

---

### Tarefa 8: Remover o fallback no suap-pdf

Só execute depois que a Tarefa 7 estiver em produção e estável — enquanto o fallback existir, um SUAP antigo continua funcionando.

**Arquivos:**
- Modificar: `/home/hugo/workspace/suap-pdf/wkhtml.py`
- Modificar: `/home/hugo/workspace/suap-pdf/main.py`
- Modificar: `/home/hugo/workspace/suap-pdf/test_assets.py`
- Modificar: `/home/hugo/workspace/suap-pdf/README.md`

**Interfaces:**
- Consome: o contrato da Tarefa 3, agora obrigatório.
- Produz: `make_absolute_paths(content: str, root: str) -> str`, com `root` obrigatório.

- [ ] **Passo 1: Ajustar o teste para o novo contrato**

Em `test_assets.py`, apague `test_make_absolute_paths_sem_raiz_usa_a_variavel_de_ambiente` e a sua chamada no `if __name__ == '__main__':`. Acrescente:

```python
def test_wkhtml_exige_a_raiz():
    import wkhtml

    try:
        wkhtml.make_absolute_paths('<img src="/static/b.png">')
    except TypeError:
        print('ok test_wkhtml_exige_a_raiz')
        return
    raise AssertionError('esperava TypeError sem a raiz')
```

E a chamada correspondente no bloco `if __name__ == '__main__':`.

- [ ] **Passo 2: Rodar e conferir que falha**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py
```

Esperado: `AssertionError: esperava TypeError sem a raiz`.

- [ ] **Passo 3: Remover o fallback**

Em `wkhtml.py`:

```python
def make_absolute_paths(content, root):
    """Convert all MEDIA files into a file://URL paths in order to
    correctly get it displayed in PDFs."""
    overrides = [{'root': root, 'url': '/static/'}]
```

Em `main.py`, dentro de `_prepare_assets`, troque o early return por um erro explícito:

```python
    # Chaveie pela PRESENÇA do campo, não por ele estar vazio: o SUAP atual sempre
    # manda `assets`, ainda que `{}` (quando o HTML não referencia estático nenhum, ou
    # quando nada resolveu). Testar `if not asset_hashes` transformaria esse caso em 400
    # duro em vez de deixá-lo degradar — e isso depois que a Tarefa 7 já removeu o volume,
    # ou seja, fora da janela de rollback.
    if 'assets' not in body:
        raise assets_store.AssetError('A requisição precisa trazer o campo assets com os estáticos do HTML.')
    asset_hashes = body.get('assets') or {}
```

- [ ] **Passo 4: Rodar e conferir que passa**

```bash
cd /home/hugo/workspace/suap-pdf && python3 test_assets.py && docker build -t suap-pdf . && docker run --rm -v "$PWD":/opt/suap-pdf -w /opt/suap-pdf -e SUAP_PDF_SENTRY_URL= suap-pdf python test.py
```

Esperado: os dois scripts terminam sem `AssertionError`.

- [ ] **Passo 5: Limpar o README**

Em `README.md`, apague a linha inteira do `SUAP_PDF_STATIC_ROOT` da tabela de configuração e, na observação do `wkhtml_to_pdf` acrescentada na Tarefa 3, apague a frase final `Sem 'assets', vale o fallback 'SUAP_PDF_STATIC_ROOT'.`, trocando-a por: `O campo 'assets' é obrigatório.`

- [ ] **Passo 6: Commitar**

```bash
cd /home/hugo/workspace/suap-pdf && ruff format --check wkhtml.py main.py test_assets.py && ruff check wkhtml.py main.py test_assets.py && git add wkhtml.py main.py test_assets.py README.md && git commit -m "feat!: remove o fallback SUAP_PDF_STATIC_ROOT

Os estáticos agora chegam sempre pela API. A variável e o volume que ela
apontava deixaram de existir no suap_deploy.

Changelog: removed"
```

---

## Ordem de deploy

A ordem importa e é a da spec. Enquanto o volume existir, qualquer combinação de versões funciona: um pdfprinter antigo ignora os campos novos e usa o volume, e um SUAP antigo não manda `assets` e cai no fallback.

1. Tarefas 1-3 → release e deploy do `suap-pdf` (nada muda de comportamento).
2. Tarefas 4-5 → MR e deploy do SUAP em homologação.
3. Tarefa 6 → verificação com o volume fora.
4. Tarefa 7 → remoção do volume no `suap_deploy`.
5. Tarefa 8 → release seguinte do `suap-pdf`, já sem o fallback.

**Rollback:** reverter o deploy do SUAP faz voltar ao fallback pelo volume, e é por isso que a Tarefa 7 só acontece depois da 6.
