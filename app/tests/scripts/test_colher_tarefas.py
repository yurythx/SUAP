"""Checagem do colhedor de tarefas (``bin/scripts/colher_tarefas.py``), sem banco e sem git.

Afirma o que decide se o inventário presta: prosa separada dos passos Gherkin, ``@do_document``
lido como curadoria humana, caminhos de menu preservados, e cenário comentado fora da contagem.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import colher_tarefas

FEATURE = """# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Matricular Aluno
    Prosa da funcionalidade, em duas
    linhas coladas.

  Cenário: Configuração inicial
    Dado os cadastros da funcionalidade 001
    Quando acesso a página "/"

  @do_document
  Cenário: Pré-Cadastro: Forma de Ingresso
    São definidas as formas de ingresso. Ação executada pelo perfil Administrador Acadêmico.

    Quando acesso o menu "Ensino::Cadastros Gerais::Formas de Ingresso"
    E preencho o formulário com os dados
      | Campo | Tipo  | Valor |
      | Nome  | Texto | X     |

#  Cenário: Comentado

  Esquema do Cenário: Variantes
    Quando acesso o menu "Ensino::Outro"
    Exemplos:
      | a |
      | 1 |
"""


def _funcionalidade() -> dict:
    colhidas = colher_tarefas.colher(FEATURE, 'edu/features/004.x.feature')
    assert len(colhidas) == 1, colhidas
    return colhidas[0]


def test_funcionalidade_guarda_nome_e_prosa() -> None:
    func = _funcionalidade()
    assert func['nome'] == 'Matricular Aluno'
    assert func['descricao'] == 'Prosa da funcionalidade, em duas linhas coladas.'
    assert func['arquivo'] == 'edu/features/004.x.feature'


def test_cenario_comentado_fica_de_fora() -> None:
    nomes = [c['nome'] for c in _funcionalidade()['cenarios']]
    assert nomes == ['Configuração inicial', 'Pré-Cadastro: Forma de Ingresso', 'Variantes'], nomes


def test_prosa_do_cenario_nao_engole_passos_nem_tabela() -> None:
    cenario = _funcionalidade()['cenarios'][1]
    assert cenario['descricao'] == 'São definidas as formas de ingresso. Ação executada pelo perfil Administrador Acadêmico.'
    # Cenário cuja primeira linha já é um passo não inventa prosa.
    assert _funcionalidade()['cenarios'][0]['descricao'] == ''


def test_do_document_e_lido_como_curadoria() -> None:
    cenarios = _funcionalidade()['cenarios']
    assert [c['documentavel'] for c in cenarios] == [False, True, False]


def test_caminhos_de_menu_ficam_no_cenario_certo() -> None:
    cenarios = _funcionalidade()['cenarios']
    assert cenarios[1]['telas'] == ['Ensino::Cadastros Gerais::Formas de Ingresso']
    assert cenarios[2]['telas'] == ['Ensino::Outro']
    assert cenarios[0]['telas'] == []


if __name__ == '__main__':
    for nome, caso in sorted(globals().items()):
        if nome.startswith('test_'):
            caso()
            sys.stdout.write(f'ok {nome}\n')
