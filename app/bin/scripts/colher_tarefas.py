#!/usr/bin/env python
"""Colhe o inventário de tarefas escrito nas ``.feature`` do behave, antes que a deleção o leve.

Decidido em https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/17002 (roteiro em .../16995):

- **fluxo é tarefa fim-a-fim**, e os títulos ``Funcionalidade:``/``Cenário:`` são o único
  inventário fim-a-fim escrito por humano no repo;
- o protocolo de deleção (.../16975) apaga ``<modulo>/features/`` inteiro, um MR por módulo,
  e **já começou** — por isso o script lê também as ``.feature`` **já apagadas**, recuperando
  cada uma do commit anterior à sua deleção.

Guarda título, prosa, a tag ``@do_document`` e os caminhos de menu citados. **Não** guarda os
passos Gherkin: são script de teste, e quem quiser recuperá-los usa ``git revert`` no MR de
deleção — esta colheita é cópia de conveniência, não substituta do histórico.

Uso::

    python bin/scripts/colher_tarefas.py                     # escreve o YAML padrão
    python bin/scripts/colher_tarefas.py --saida /tmp/x.yaml
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

SAIDA_PADRAO = Path('docs/agents/inventario-tarefas.yaml')
# Primeiro commit da migração e2e (`643104607e`). Antes disso, toda deleção de `.feature` é
# refactor antigo, não o protocolo de remoção do behave — ver `features_conhecidas`.
INICIO_DA_MIGRACAO_E2E = '2026-07-27'

RE_FUNCIONALIDADE = re.compile(r'^\s*(?:Funcionalidade|Feature)\s*:\s*(.+?)\s*$')
RE_CENARIO = re.compile(r'^\s*(?:Cenário|Cenario|Scenario|Esquema do Cenário|Scenario Outline)\s*:\s*(.+?)\s*$')
RE_MENU = re.compile(r'acesso o menu\s*"([^"]+)"')
# Palavras que abrem um passo Gherkin: encerram o bloco de prosa de uma Funcionalidade/Cenário.
RE_PASSO = re.compile(r'^(?:Dado|Dada|Dados|Dadas|Quando|Então|Entao|E|Mas|Given|When|Then|And|But|Exemplos|Examples)\b')


def _rev_de_delecao(caminho: str) -> str | None:
    """Commit **anterior** à deleção de ``caminho``, ou ``None`` se o arquivo ainda existe."""
    if Path(caminho).exists():
        return None
    saida = subprocess.run(
        ['git', 'log', '-1', '--diff-filter=D', '--format=%H', '--', caminho],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return f'{saida}^' if saida else None


def features_conhecidas() -> dict[str, str | None]:
    """Toda ``.feature`` que existe **ou já existiu**, mapeada para a rev em que se pode lê-la.

    Valor ``None`` = está na árvore de trabalho. Caso contrário, é a rev anterior à deleção.
    """
    conhecidas: dict[str, str | None] = {str(p): None for p in sorted(Path().glob('*/features/**/*.feature'))}
    # Do histórico, recuperar SÓ o que o protocolo de deleção (.../16975) levou — ou seja,
    # deleções a partir do início da migração e2e. Dos 44 commits que já apagaram `.feature`,
    # 43 são refactor de 2020-2025 e descrevem um SUAP que não existe mais: ressuscitá-los
    # seria ruído, não inventário. Deleções futuras do protocolo entram sozinhas.
    saida = subprocess.run(
        ['git', 'log', f'--since={INICIO_DA_MIGRACAO_E2E}', '--diff-filter=D', '--name-only', '--format=', '--', '*/features/*.feature'],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for linha in saida.splitlines():
        caminho = linha.strip()
        if not caminho.endswith('.feature') or caminho in conhecidas:
            continue
        rev = _rev_de_delecao(caminho)
        if rev is not None:
            conhecidas[caminho] = rev
    return dict(sorted(conhecidas.items()))


def ler(caminho: str, rev: str | None) -> str | None:
    """Conteúdo do arquivo na árvore de trabalho (``rev is None``) ou na rev indicada."""
    if rev is None:
        return Path(caminho).read_text(encoding='utf-8', errors='replace')
    resultado = subprocess.run(['git', 'show', f'{rev}:{caminho}'], capture_output=True, text=True, check=False)
    return resultado.stdout if resultado.returncode == 0 else None


def _prosa(linhas: list[str], inicio: int) -> tuple[str, int]:
    """Bloco de descrição a partir de ``inicio``: linhas que não são passo, tabela, tag ou comentário."""
    partes = []
    i = inicio
    while i < len(linhas):
        texto = linhas[i].strip()
        if not texto:
            i += 1
            continue
        if texto[0] in '|@#' or RE_PASSO.match(texto) or RE_CENARIO.match(texto) or RE_FUNCIONALIDADE.match(texto):
            break
        partes.append(texto)
        i += 1
    return ' '.join(partes), i


def _telas_do_cenario(linhas: list[str], inicio: int) -> list[str]:
    """Caminhos de menu (``Área::Submenu::Item``) citados até o próximo cenário."""
    telas = []
    for linha in linhas[inicio:]:
        if RE_CENARIO.match(linha) or RE_FUNCIONALIDADE.match(linha):
            break
        telas += [t for t in RE_MENU.findall(linha) if t not in telas]
    return telas


def colher(texto: str, caminho: str) -> list[dict]:
    """Funcionalidades do arquivo, cada uma com seus cenários (título, prosa, tag e telas)."""
    linhas = texto.split('\n')
    funcionalidades: list[dict] = []
    i = 0
    while i < len(linhas):
        casa_func = RE_FUNCIONALIDADE.match(linhas[i])
        if casa_func:
            descricao, i = _prosa(linhas, i + 1)
            funcionalidades.append({'nome': casa_func.group(1), 'arquivo': caminho, 'descricao': descricao, 'cenarios': []})
            continue
        casa_cen = RE_CENARIO.match(linhas[i])
        if not casa_cen:
            i += 1
            continue
        if not funcionalidades:
            funcionalidades.append({'nome': '(sem Funcionalidade)', 'arquivo': caminho, 'descricao': '', 'cenarios': []})
        anteriores = [linha.strip() for linha in linhas[max(0, i - 3) : i]]
        descricao, proximo = _prosa(linhas, i + 1)
        funcionalidades[-1]['cenarios'].append(
            {
                'nome': casa_cen.group(1),
                'documentavel': any(linha.startswith('@') and 'do_document' in linha for linha in anteriores),
                'descricao': descricao,
                'telas': _telas_do_cenario(linhas, i + 1),
            }
        )
        i = proximo if proximo > i else i + 1
    return funcionalidades


def montar(conhecidas: dict[str, str | None]) -> dict:
    """Agrupa as funcionalidades por módulo, registrando de onde cada arquivo veio."""
    modulos: dict[str, dict] = {}
    for caminho, rev in conhecidas.items():
        texto = ler(caminho, rev)
        if texto is None:
            continue
        modulo = caminho.split('/')[0]
        entrada = modulos.setdefault(modulo, {'origem': {}, 'funcionalidades': []})
        entrada['origem'][caminho] = 'árvore de trabalho' if rev is None else f'apagada, recuperada de {rev}'
        entrada['funcionalidades'] += colher(texto, caminho)
    return {modulo: modulos[modulo] for modulo in sorted(modulos)}


def _resumo(modulos: dict) -> dict:
    cenarios = [c for m in modulos.values() for f in m['funcionalidades'] for c in f['cenarios']]
    recuperados = sum(1 for m in modulos.values() for o in m['origem'].values() if o.startswith('apagada'))
    return {
        'modulos': len(modulos),
        'arquivos': sum(len(m['origem']) for m in modulos.values()),
        'arquivos_recuperados_do_historico': recuperados,
        'funcionalidades': sum(len(m['funcionalidades']) for m in modulos.values()),
        'cenarios': len(cenarios),
        'cenarios_documentaveis': sum(1 for c in cenarios if c['documentavel']),
        'cenarios_com_prosa': sum(1 for c in cenarios if c['descricao']),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--saida', default=str(SAIDA_PADRAO), help=f'arquivo YAML de saída (padrão: {SAIDA_PADRAO})')
    argumentos = parser.parse_args()

    modulos = montar(features_conhecidas())
    resumo = _resumo(modulos)
    documento = {
        'aviso': (
            'Gerado por bin/scripts/colher_tarefas.py. Cópia de conveniência dos títulos, prosa, tag @do_document e '
            'caminhos de menu das .feature do behave — os passos Gherkin NÃO estão aqui; para recuperá-los, '
            'use git revert no MR de deleção do módulo.'
        ),
        'resumo': resumo,
        'modulos': modulos,
    }
    Path(argumentos.saida).write_text(yaml.safe_dump(documento, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8')
    sys.stdout.write(f'{argumentos.saida}: ' + ', '.join(f'{chave}={valor}' for chave, valor in resumo.items()) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
