"""Checagem da tradução permissão → frase "Quem pode" (``bin/scripts/papeis.py``), sem banco.

Afirma os quatro ramos que #17003 decidiu — zero grupos, um, até o teto, e acima dele — mais
a precedência de ``groups_required``, que dispensa inversão.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import papeis

INDICE = {
    ('eventos', 'view_evento'): ['Servidor', 'Aluno'],
    ('almoxarifado', 'add_material'): ['Coordenador de Almoxarifado'],
    ('edu', 'view_aluno'): [f'Grupo {n}' for n in range(36)],
    ('edu', 'change_turma'): ['A', 'B', 'C', 'D', 'E'],
    ('edu', 'view_diario'): ['A', 'B', 'C', 'D', 'E', 'F'],
}


def test_sem_grupo_nenhum_diz_a_verdade() -> None:
    frase = papeis.quem_pode(['comum.is_servidor'], None, INDICE)
    assert 'nenhum perfil padrão do SUAP concede' in frase, frase
    assert '`comum.is_servidor`' in frase, frase


def test_um_grupo_nomeia() -> None:
    assert papeis.quem_pode(['almoxarifado.add_material'], None, INDICE) == 'Coordenador de Almoxarifado'


def test_ate_o_teto_nomeia_todos_em_ordem() -> None:
    assert papeis.quem_pode(['eventos.view_evento'], None, INDICE) == 'Aluno, Servidor'
    assert papeis.quem_pode(['edu.change_turma'], None, INDICE) == 'A, B, C, D, E'


def test_acima_do_teto_vira_frase_generica() -> None:
    # 36 grupos: nomear todos seria uma linha que o leitor pula.
    assert papeis.quem_pode(['edu.view_aluno'], None, INDICE) == 'qualquer perfil com permissão de consultar aluno'
    # 6 já passa do teto de 5.
    assert papeis.quem_pode(['edu.view_diario'], None, INDICE) == 'qualquer perfil com permissão de consultar diario'


def test_codename_fora_do_padrao_cai_na_permissao_crua() -> None:
    indice = {('comum', 'pode_tudo'): [f'G{n}' for n in range(10)]}
    assert papeis.quem_pode(['comum.pode_tudo'], None, indice) == 'qualquer perfil com a permissão `comum.pode_tudo`'


def test_groups_required_tem_precedencia_e_dispensa_inversao() -> None:
    # Não consulta o índice: o menu.yaml já nomeou o perfil.
    assert papeis.quem_pode(['edu.view_aluno'], ['Servidor', 'Aluno'], INDICE) == 'Aluno, Servidor'


def test_permissoes_multiplas_nao_repetem_a_mesma_frase() -> None:
    frase = papeis.quem_pode(['edu.change_turma', 'edu.change_turma'], None, INDICE)
    assert frase == 'A, B, C, D, E', frase


if __name__ == '__main__':
    for nome, caso in sorted(globals().items()):
        if nome.startswith('test_'):
            caso()
            sys.stdout.write(f'ok {nome}\n')
