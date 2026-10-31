#!/usr/bin/env python
"""Valida a documentação de usuário de um módulo: data e cobertura de tela.

Contrato decidido em https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/17000:

- **alerta, nunca reprovação.** O job de CI é `allow_failure: true`; este script sai 0 mesmo
  com achados. O código de saída sinaliza erro de uso, não doc velha;
- a superfície é uma **nota automática no MR**, então o dono é o autor do MR — quem está ali
  com o módulo na cabeça, no único momento em que atualizar a doc é barato;
- reporta o **estado completo do módulo tocado**, não só o delta do MR: os ~90 módulos começam
  sem doc, e um gate diff-local nunca emitiria sinal para eles.

Dois sinais:

1. **validação de data** — a doc é mais velha que as telas do módulo?
2. **cobertura** — tela do `menu.yaml` que nenhuma tarefa documentada menciona.

O denominador é o `menu.yaml`, **nunca** o `urls.py`: `rotas_do_modulo`
(`bin/scripts/paridade_e2e.py:193`) é estruturalmente cego a `/admin/*`, que são 831 das 1.373
entradas de menu (61%) do que o usuário alcança. Do `paridade_e2e.py` se copia a **forma**
(script DB-free, dispensa declarada com motivo, roda no CI), não a fonte.

Uso::

    python bin/scripts/validar_doc.py eventos
    python bin/scripts/validar_doc.py eventos edu --markdown
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

import yaml

# Separador de caminho de menu como as docs o escrevem (`Ensino > Cursos > Componentes`, com o caractere U+203A).
SEPARADOR = ' › '  # noqa: RUF001 — caractere deliberado: é o que o documento gerado usa

# O que renderiza uma tela: se algum destes mudou depois da doc, ela está atrasada.
CODIGO_DE_TELA = ('views.py', 'urls.py', 'forms.py', 'admin.py', 'templates')


def _ultimo_commit(caminhos: list[str]) -> str:
    """Data ISO do último commit que tocou qualquer um dos caminhos; vazio se nenhum."""
    if not caminhos:
        return ''
    achado = subprocess.run(
        ['git', 'log', '-1', '--format=%cI', '--', *caminhos],
        capture_output=True,
        text=True,
        check=False,
    )
    return achado.stdout.strip()


def datas(modulo: str) -> tuple[str, str]:
    """``(data_da_doc, data_do_codigo_de_tela)``. Vazio quando o alvo não existe."""
    doc = Path(modulo, 'docs', 'usuario.md')
    alvos = [str(Path(modulo, parte)) for parte in CODIGO_DE_TELA if Path(modulo, parte).exists()]
    return (_ultimo_commit([str(doc)]) if doc.exists() else '', _ultimo_commit(alvos))


def telas_do_menu(modulo: str) -> dict[str, str]:
    """``Área::Submenu::Item -> url`` das entradas de ``<modulo>/menu.yaml`` que têm ``url``.

    A chave é o caminho **completo**, não o rótulo folha: é ele que desambigua ``Alunos`` de
    ``Ensino > Alunos e Professores > Alunos`` — ver ``cita``.
    """
    caminho = Path(modulo, 'menu.yaml')
    if not caminho.exists():
        return {}
    conteudo = yaml.safe_load(caminho.read_text(encoding='utf-8')) or {}
    return {chave: corpo['url'] for chave, corpo in conteudo.items() if isinstance(corpo, dict) and corpo.get('url')}


def dispensas(modulo: str) -> dict[str, str]:
    """``TELAS_DISPENSADAS`` do conftest de doc do módulo — tela sem tarefa, com motivo.

    Mesmo idioma de ``ROTAS_DISPENSADAS``/``CENARIOS_DISPENSADOS`` (``paridade_e2e.py``): lido
    por AST, sem importar Django.
    """
    conftest = Path(modulo, 'tests', 'doc', 'conftest.py')
    if not conftest.exists():
        return {}
    arvore = ast.parse(conftest.read_text(encoding='utf-8'), filename=str(conftest))
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Assign) and isinstance(no.value, ast.Dict)):
            continue
        if any(isinstance(alvo, ast.Name) and alvo.id == 'TELAS_DISPENSADAS' for alvo in no.targets):
            return {
                c.value: v.value
                for c, v in zip(no.value.keys, no.value.values, strict=True)
                if isinstance(c, ast.Constant) and isinstance(v, ast.Constant)
            }
    return {}


def _normalizar(texto: str) -> str:
    return re.sub(r'\s+', ' ', texto).strip().lower()


def _rotulo_solto(rotulo: str, texto: str) -> bool:
    return re.search(rf'(?<![^\W_]){re.escape(rotulo)}(?![^\W_])', texto, re.IGNORECASE) is not None


def cita(chave: str, tarefas: str, apoio: str) -> bool:
    """A doc menciona esta tela?

    Duas regras, por seção, e a diferença **não** é preciosismo:

    - no texto das **tarefas**, exige o **caminho completo** do menu (``Ensino > Cursos,
      Matrizes e Componentes > Componentes``), que é como as tarefas de fato escrevem;
    - na seção **Telas de apoio**, aceita o **rótulo solto**, porque ali listar o nome **é** a
      declaração de cobertura — foi o que a anatomia (#16997) fixou.

    A versão anterior aceitava rótulo solto no documento inteiro e media bem só em módulo
    pequeno com rótulos distintivos. Medido em 03/08/2026: no ``edu``, **143 de 188 telas
    (76%)** contavam como cobertas antes de qualquer dispensa, e uma frase genérica de duas
    linhas "cobria" quatro telas — porque rótulos como ``Alunos``, ``Turmas`` e ``Cursos``
    aparecem em qualquer frase deste domínio. No ``eventos`` (21 telas, rótulos como
    ``Espacialidades``) o defeito era invisível.
    """
    if _normalizar(chave.replace('::', SEPARADOR)) in _normalizar(tarefas):
        return True
    return bool(apoio) and _rotulo_solto(chave.rsplit('::', maxsplit=1)[-1], apoio)


def descobertas(modulo: str) -> list[tuple[str, str]]:
    """Telas do menu que nenhuma tarefa menciona e que não estão dispensadas."""
    doc = Path(modulo, 'docs', 'usuario.md')
    bruto = doc.read_text(encoding='utf-8') if doc.exists() else ''
    # A seção de apoio tem regra própria de casamento — ver `cita`.
    partes = bruto.split('## Telas de apoio')
    tarefas, apoio = partes[0], partes[1] if len(partes) > 1 else ''
    dispensadas = dispensas(modulo)
    return sorted(
        (chave, url)
        for chave, url in telas_do_menu(modulo).items()
        if chave not in dispensadas and chave.split('::')[-1] not in dispensadas and not cita(chave, tarefas, apoio)
    )


def relatar(modulo: str) -> list[str]:
    """Linhas em markdown com o estado da doc do módulo, ou vazio se não há o que dizer."""
    telas = telas_do_menu(modulo)
    if not telas:
        return []

    data_doc, data_codigo = datas(modulo)
    # `sem_doc` é sobre o ARQUIVO existir, não sobre haver commit: doc recém-criada ainda não
    # commitada tem data vazia, e reportá-la como inexistente seria mentira.
    sem_doc = not Path(modulo, 'docs', 'usuario.md').exists()
    atrasada = bool(data_doc and data_codigo and data_doc < data_codigo)
    faltando = descobertas(modulo)
    dispensadas = dispensas(modulo)

    if not (sem_doc or atrasada or faltando):
        return []

    linhas = [f'### `{modulo}`', '']
    if sem_doc:
        # Sem doc, listar as telas "descobertas" é redundante: a resposta já é "não existe doc".
        # O custo aceito em #17000 é o módulo ser sinalizado, não receber 20 linhas de óbvio.
        linhas += [f'- **Sem documentação de usuário.** O módulo expõe {len(telas)} telas no menu e não tem `{modulo}/docs/usuario.md`.', '']
        return linhas
    if atrasada:
        linhas.append(f'- **Doc mais velha que as telas.** Último commit na doc: `{data_doc[:10]}`; no código de tela: `{data_codigo[:10]}`.')
    if faltando:
        linhas.append(f'- **{len(faltando)} de {len(telas)} telas sem menção na doc** ({len(dispensadas)} dispensadas):')
        linhas += [f'  - `{url}` — {chave}' for chave, url in faltando[:15]]
        if len(faltando) > 15:
            linhas.append(f'  - …e mais {len(faltando) - 15}.')
    linhas.append('')
    return linhas


def _cabecalho() -> list[str]:
    return [
        '## 📄 Documentação de usuário',
        '',
        'Sinal automático, **não bloqueia o merge**. Tela sem tarefa pode ser dispensada com motivo',
        'em `TELAS_DISPENSADAS`, no `tests/doc/conftest.py` do módulo — a seção *Telas de apoio* da',
        'doc já cobre a maioria dos casos.',
        '',
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('modulos', nargs='+', help='módulos a inspecionar')
    parser.add_argument('--markdown', action='store_true', help='emite a nota pronta para o MR (vazio se não há achados)')
    argumentos = parser.parse_args()

    corpo: list[str] = []
    for modulo in argumentos.modulos:
        corpo += relatar(modulo)

    if not corpo:
        if not argumentos.markdown:
            sys.stdout.write('nada a reportar\n')
        return 0

    sys.stdout.write('\n'.join((_cabecalho() if argumentos.markdown else []) + corpo) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
