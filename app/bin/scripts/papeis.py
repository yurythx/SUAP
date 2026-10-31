#!/usr/bin/env python
"""Traduz exigência de acesso do ``menu.yaml`` para a frase "Quem pode" da doc de usuário.

Contrato decidido em https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/17003:

- a fonte é **sempre** a inversão ``permissions_required`` → grupo, via ``*/permissions.yaml``
  (a prosa das ``.feature`` nomeia o papel em 41% dos cenários, mas é de até 2020 e criaria
  duas vozes no site);
- **0 grupos** (53 das 839 permissões exigidas): diz que nenhum perfil padrão concede, em vez
  de inventar;
- **1 a 5 grupos** (757 das 839, 90%): nomeia todos;
- **6 ou mais** (82): frase genérica derivada da própria permissão — ``edu.view_aluno``
  pertence a 36 grupos, e uma linha com 36 nomes é uma linha que o leitor pula.

Limite conhecido: o ``menu.yaml`` diz quem pode **abrir a tela**, não quem **executa a
tarefa**. Quase sempre coincidem; quando não, a frase erra para o lado mais amplo.

Utilitário compartilhado — o subagente ``documentador-usuario`` o usa para a linha de cada
tarefa, e o gerador do site para a página transversal de perfis. Sem Django, sem banco.

Uso::

    python bin/scripts/papeis.py edu.view_aluno eventos.view_evento
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

TETO_DE_NOMES = 5

VERBOS = {
    'view': 'consultar',
    'add': 'cadastrar',
    'change': 'editar',
    'delete': 'remover',
}

Chave = tuple[str, str]


def _permissoes_do_grupo(corpo: dict) -> list[Chave]:
    """Pares ``(app, codename)`` que um grupo do ``permissions.yaml`` concede."""
    pares = []
    for app, modelos in corpo.items():
        if app == 'description' or not isinstance(modelos, dict):
            continue
        for perms in (modelos or {}).values():
            pares += [(app, p) for p in (perms or [])]
    return pares


def indice() -> tuple[dict[Chave, list[str]], dict[str, str]]:
    """Devolve ``((app, codename) -> grupos)`` e ``(grupo -> description)``.

    Lê todos os ``*/permissions.yaml`` — 331 grupos, dos quais só 70 dos que a regra chega a
    nomear têm ``description`` escrita.
    """
    por_permissao: dict[Chave, list[str]] = {}
    descricoes: dict[str, str] = {}
    for arquivo in sorted(Path().glob('*/permissions.yaml')):
        conteudo = yaml.safe_load(arquivo.read_text(encoding='utf-8')) or {}
        for grupo, corpo in conteudo.items():
            if not isinstance(corpo, dict):
                continue
            descricoes.setdefault(grupo, (corpo.get('description') or '').strip())
            for chave in _permissoes_do_grupo(corpo):
                grupos = por_permissao.setdefault(chave, [])
                if grupo not in grupos:
                    grupos.append(grupo)
    return por_permissao, descricoes


def grupos_de(permissao: str, por_permissao: dict[Chave, list[str]]) -> list[str]:
    """Grupos que concedem ``<app>.<codename>``, em ordem alfabética."""
    app, _, codename = permissao.partition('.')
    return sorted(por_permissao.get((app, codename), []))


def _frase_generica(permissao: str) -> str:
    """Descrição derivada da própria permissão, para quando os grupos são muitos."""
    _, _, codename = permissao.partition('.')
    acao, _, modelo = codename.partition('_')
    verbo = VERBOS.get(acao)
    if not verbo or not modelo:
        return f'qualquer perfil com a permissão `{permissao}`'
    return f'qualquer perfil com permissão de {verbo} {modelo}'


def quem_pode(permissoes: list[str], grupos_declarados: list[str] | None = None, por_permissao: dict[Chave, list[str]] | None = None) -> str:
    """Frase "Quem pode" de uma tarefa.

    ``grupos_declarados`` são os ``groups_required`` do ``menu.yaml``, quando existirem: já
    nomeiam o perfil e dispensam inversão. Só 213 das 1.373 entradas os trazem.
    """
    if grupos_declarados:
        return ', '.join(sorted(grupos_declarados))
    if por_permissao is None:
        por_permissao, _ = indice()

    partes = []
    for permissao in permissoes:
        grupos = grupos_de(permissao, por_permissao)
        if not grupos:
            partes.append(f'exige a permissão `{permissao}`, que nenhum perfil padrão do SUAP concede — o acesso é atribuído individualmente')
        elif len(grupos) <= TETO_DE_NOMES:
            partes.append(', '.join(grupos))
        else:
            partes.append(_frase_generica(permissao))
    return '; '.join(dict.fromkeys(partes))


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(f'uso: {sys.argv[0]} <app.codename> [<app.codename> ...]\n')
        return 2
    por_permissao, descricoes = indice()
    for permissao in sys.argv[1:]:
        grupos = grupos_de(permissao, por_permissao)
        sys.stdout.write(f'{permissao}  ({len(grupos)} grupos)\n  {quem_pode([permissao], None, por_permissao)}\n')
        for grupo in grupos[:TETO_DE_NOMES]:
            if descricoes.get(grupo):
                sys.stdout.write(f'    - {grupo}: {descricoes[grupo][:100]}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
