#!/usr/bin/env python
"""Gera ``djtools/static/djtools/css/bootstrap5-compat.min.css``: os utilitários do Bootstrap 5 sobre o Bootstrap 6.

Por quê. Os templates do SUAP foram escritos para o Bootstrap 5 (``text-center``, ``text-end``, ``mt-4``, ``gap-5``, ``col-md-6``,
``d-lg-block``, ``form-select``, ``text-bg-*``, ``mw-100``...). No Bootstrap 6 o utilitário fica em ``@layer utilities`` e sem
``!important``, então perde para qualquer regra de elemento do tema (``table thead th { text-align: left }``); a escala de espaçamento
mudou (``gap-5`` de 3rem para 1rem); o responsivo virou ``md:col-6``; e ``form-select``, ``text-bg-*`` e ``mw-100`` deixaram de existir.
Migrar ~4.000 usos em 241 templates seria a pior troca; em vez disso o arquivo gerado devolve o comportamento do 5.

Origem. O CSS do Bootstrap 5.3.5 que o SUAP usava até o commit ``78a0f2e90eb358fab9ddc5c6695dd681b2ed668d``, que está na master
(``git show 78a0f2e90eb358fab9ddc5c6695dd681b2ed668d:djtools/static/djtools/css/bootstrap.min.css``). Dele ficam, e nada mais:

1. as regras de utilitário: toda declaração (fora as variáveis ``--bs-*``) é ``!important``, inclusive dentro de ``@media``;
2. o que o Bootstrap 6 não tem e o SUAP usa: grade responsiva (``col-md-*``, ``offset-lg-*``, ``row-cols-sm-*``, ``g-md-*``),
   ``form-select``, ``form-check*``, ``btn-primary|success|secondary|outline-secondary``, ``table-info|light`` e a tabela base
   (``.table`` e ``-sm|-bordered|-borderless|-striped|-hover|-active``, que o 6 também define, de outro jeito);
3. o ``max-width`` do ``.container`` por breakpoint (o 5 vai a 1140px em xl, o 6 a 1200px);
4. as variáveis ``--bs-*`` (``--bs-primary-rgb``, ``--bs-text-opacity``...) que essas regras leem, num ``:root`` no começo do arquivo. As que
   o Bootstrap 6 também declara, com outro valor (``--bs-border-color``, ``--bs-box-shadow``...), saem com o prefixo ``--bs5-`` e as regras
   passam a ler esse nome: os utilitários ficam com o valor do 5 e os componentes do 6 não mudam. A exceção é ``--bs-border-color``, que o
   tema do SUAP redefine em ``:root``: as regras o leem vivo (``VARIAVEIS_DO_TEMA``), como o 5 fazia, e a borda sai com a cor do tema.

A saída depende também do ``bootstrap.min.css`` do Bootstrap 6 do repositório (``CSS_DO_6``): dele vêm as classes que o 6 já define (e que o
compat, portanto, não repete) e os nomes de ``--bs-*`` que colidem (``--bs5-``). Trocou o ``bootstrap.min.css``? Regere o compat, e suba o
``?v=`` dos dois ``@import`` em ``default/pre.scss`` (o nginx serve ``/static`` com ``expires 30d``).

O arquivo é importado por ``default/pre.scss`` logo depois do ``bootstrap.min.css`` do 6. Fora de ``@layer``, vence o 6 como o ``!important``
do 5 vencia.

Como regerar::

    python bin/scripts/gerar_bootstrap5_compat.py            # usa o commit acima e grava o arquivo
    python bin/scripts/gerar_bootstrap5_compat.py --origem /caminho/bootstrap-5.3.5.min.css
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CSS_DO_6 = RAIZ / 'djtools/static/djtools/css/bootstrap.min.css'
SAIDA = RAIZ / 'djtools/static/djtools/css/bootstrap5-compat.min.css'
COMMIT_DO_5 = '78a0f2e90eb358fab9ddc5c6695dd681b2ed668d'  # na master; o mesmo CSS do 5.3.5 que estava no 68310cb3f8 (local, fora da master)
CAMINHO_NO_COMMIT = 'djtools/static/djtools/css/bootstrap.min.css'

BREAKPOINTS = 'sm|md|lg|xl|xxl'
# O que o Bootstrap 6 não tem (ou tem com outro nome) e o SUAP ainda usa além dos utilitários: grade responsiva, form-select, form-check*
# e as variantes de botão e de tabela dos templates (``btn btn-primary``, ``<table class="table-info">``, ``<thead class="table-light">``...).
FAMILIAS_EXTRAS = re.compile(
    rf'^\.(?:(?:col|offset|row-cols|g|gx|gy)-(?:{BREAKPOINTS})-|form-select|form-check\b|btn-(?:primary|success|secondary|outline-secondary)\b'
    r'|table-(?:info|light)\b)'
)
# A tabela base do 5 e as variantes que os templates usam. O 6 também define estes nomes, mas com outro mecanismo (outras variáveis, em
# camada): para o ``<table class="table">`` sair como no 5 as regras do 5 entram mesmo assim, e vencem as do 6 por estarem fora de camada.
FAMILIAS_FORCADAS = re.compile(r'^\.table(?![\w-])|^\.table-(?:sm|bordered|borderless|striped|hover|active)(?![\w-])')
# Variáveis que o próprio tema do SUAP redefine em ``:root`` (``--bs-border-color: var(--grey-200)``): o 5 as lia como estão, então as regras
# do compat leem a variável viva, sem declará-la nem prefixá-la.
VARIAVEIS_DO_TEMA = frozenset({'--bs-border-color'})
CLASSE = re.compile(r'\.((?:\\.|[\w-])+)')
VARIAVEL = re.compile(r'var\((--bs-[\w-]+)')
DECLARACAO_DE_VARIAVEL = re.compile(r'(--bs-[\w-]+)\s*:')
SO_CONTAINER = re.compile(r'^\.container(?:-(?:sm|md|lg|xl|xxl))?$')


def blocos(css: str) -> Iterator[tuple[str, str]]:
    """Separa o nível de topo em ``(preâmbulo, corpo)``; ``corpo`` é ``''`` nas declarações ``@charset``/``;``."""
    inicio = profundidade = 0
    preambulo = ''
    aspas = ''
    for i, c in enumerate(css):
        if aspas:
            aspas = '' if c == aspas else aspas
        elif c in '"\'':
            aspas = c
        elif c == '{':
            if profundidade == 0:
                preambulo, inicio = css[inicio:i].strip(), i + 1
            profundidade += 1
        elif c == '}':
            profundidade -= 1
            if profundidade == 0:
                yield preambulo, css[inicio:i]
                inicio = i + 1
        elif c == ';' and profundidade == 0:
            inicio = i + 1


def declaracoes(corpo: str) -> list[tuple[str, str]]:
    """Divide o corpo de uma regra em ``(propriedade, valor)``, respeitando ``;`` dentro de aspas e parênteses."""
    itens: list[str] = []
    atual = ''
    nivel = 0
    aspas = ''
    for c in corpo:
        if aspas:
            aspas = '' if c == aspas else aspas
        elif c in '"\'':
            aspas = c
        elif c == '(':
            nivel += 1
        elif c == ')':
            nivel -= 1
        if c == ';' and not aspas and nivel == 0:
            itens.append(atual)
            atual = ''
        else:
            atual += c
    itens.append(atual)
    pares = (item.partition(':') for item in itens if item.strip())
    return [(prop.strip(), valor.strip()) for prop, _, valor in pares]


def eh_utilitario(corpo: str) -> bool:
    """Toda declaração que não é variável é ``!important`` (e há pelo menos uma): o ``!important`` do 5 é o que o 6 perdeu."""
    decls = [(p, v) for p, v in declaracoes(corpo) if not p.startswith('--')]
    return bool(decls) and all(v.endswith('!important') for _, v in decls)


def classes_do_6(css_do_6: str) -> set[str]:
    return {c.replace('\\', '') for c in CLASSE.findall(css_do_6)}


def eh_extra(seletor: str, classes6: set[str]) -> bool:
    """Grade responsiva / ``form-select`` que o 6 não define."""
    if FAMILIAS_FORCADAS.match(seletor):
        return True
    if not FAMILIAS_EXTRAS.match(seletor):
        return False
    primeira = CLASSE.match(seletor.split(',', maxsplit=1)[0])
    return bool(primeira) and primeira.group(1).replace('\\', '') not in classes6


def eh_largura_do_container(seletor: str, corpo: str) -> bool:
    """``.container, .container-lg {max-width: 960px}`` do 5: o 6 tem outras larguras (1200px em xl, 1440px em xxl)."""
    return all(SO_CONTAINER.match(s) for s in seletor.split(',')) and [p for p, _ in declaracoes(corpo)] == ['max-width']


def vale(seletor: str, corpo: str, classes6: set[str]) -> bool:
    return eh_utilitario(corpo) or eh_extra(seletor, classes6) or eh_largura_do_container(seletor, corpo)


def selecionar(css5: str, classes6: set[str]) -> list[str]:
    """Regras mantidas, na ordem do Bootstrap 5 (``@media`` com só as regras que valem)."""
    saida: list[str] = []
    for preambulo, corpo in blocos(css5):
        if preambulo.startswith('@media'):
            dentro = [f'{s}{{{c}}}' for s, c in blocos(corpo) if vale(s, c, classes6)]
            if dentro:
                saida.append(f'{preambulo}{{{"".join(dentro)}}}')
        elif not preambulo.startswith('@') and vale(preambulo, corpo, classes6):
            saida.append(f'{preambulo}{{{corpo}}}')
    return saida


def variaveis_do_5(css5: str) -> dict[str, str]:
    """Variáveis ``--bs-*`` do ``:root`` do Bootstrap 5."""
    for preambulo, corpo in blocos(css5):
        if preambulo.startswith(':root'):
            return {p: v for p, v in declaracoes(corpo) if p.startswith('--bs-')}
    return {}


def declara(css: str, nome: str) -> bool:
    return re.search(rf'(?<![\w-]){re.escape(nome)}\s*:', css) is not None


def variaveis_lidas(regras: list[str], do_5: dict[str, str]) -> dict[str, str]:
    """Variáveis que as regras leem sem declarar e o ``:root`` do 5 declarava (com as que o valor delas lê, transitivamente)."""
    texto = ''.join(regras)
    locais = set(DECLARACAO_DE_VARIAVEL.findall(texto))
    pendentes = set(VARIAVEL.findall(texto)) - locais
    lidas: dict[str, str] = {}
    while pendentes:
        nome = pendentes.pop()
        if nome in lidas or nome not in do_5 or nome in VARIAVEIS_DO_TEMA:
            continue
        lidas[nome] = do_5[nome]
        pendentes |= set(VARIAVEL.findall(do_5[nome]))
    return lidas


def prefixar(texto: str, nomes: set[str]) -> str:
    """``var(--bs-x`` vira ``var(--bs5-x`` para os nomes dados; e ``--bs-x:`` (declaração) também."""
    texto = VARIAVEL.sub(lambda m: f'var(--bs5-{m.group(1)[5:]}' if m.group(1) in nomes else m.group(0), texto)
    return DECLARACAO_DE_VARIAVEL.sub(lambda m: f'--bs5-{m.group(1)[5:]}:' if m.group(1) in nomes else m.group(0), texto)


def aplicar_variaveis(regras: list[str], css5: str, css6: str) -> tuple[str, list[str]]:
    """``(:root, regras)``: o ``:root`` com as variáveis do 5 que as regras leem, e as regras já lendo o nome certo.

    Variável que o 6 não declara fica com o nome do 5; a que o 6 também declara ganha o prefixo ``--bs5-``.
    """
    lidas = variaveis_lidas(regras, variaveis_do_5(css5))
    colidem = {n for n in lidas if declara(css6, n)}
    corpo = ';'.join(prefixar(f'{n}:{lidas[n]}', colidem) for n in sorted(lidas))
    raiz = f':root{{{corpo}}}' if corpo else ''
    return raiz, [prefixar(r, colidem) for r in regras]


def gerar(css5: str, css6: str) -> str:
    """O conteúdo completo do arquivo de compatibilidade."""
    css5 = re.sub(r'/\*.*?\*/', '', css5, flags=re.DOTALL)
    regras = selecionar(css5, classes_do_6(css6))
    cabecalho = (
        f'/*! Utilitarios do Bootstrap 5.3.5 sobre o Bootstrap 6. Gerado por bin/scripts/gerar_bootstrap5_compat.py a partir do commit '
        f'{COMMIT_DO_5[:12]}; nao editar. */'
    )
    raiz, regras = aplicar_variaveis(regras, css5, css6)
    return cabecalho + raiz + ''.join(regras) + '\n'


def ler_css5(origem: Path | None) -> str:
    if origem:
        return origem.read_text(encoding='utf-8')
    return subprocess.run(
        ['git', 'show', f'{COMMIT_DO_5}:{CAMINHO_NO_COMMIT}'], cwd=RAIZ, check=True, capture_output=True, text=True, encoding='utf-8'
    ).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--origem', type=Path, help=f'CSS do Bootstrap 5.3.5 (padrão: o do commit {COMMIT_DO_5})')
    parser.add_argument('--saida', type=Path, default=SAIDA)
    args = parser.parse_args()
    css = gerar(ler_css5(args.origem), CSS_DO_6.read_text(encoding='utf-8'))
    args.saida.write_text(css, encoding='utf-8')
    destino = args.saida.relative_to(RAIZ) if args.saida.is_relative_to(RAIZ) else args.saida
    sys.stdout.write(f'{destino}: {len(css.encode())} bytes, {css.count("{")} blocos\n')
    sys.stdout.write(f'?v= do @import em default/pre.scss: {hashlib.md5(css.encode()).hexdigest()[:10]}\n')


if __name__ == '__main__':
    main()
