"""Checagem do gerador da camada de compatibilidade do Bootstrap 5 (``bin/scripts/gerar_bootstrap5_compat.py``), sem banco."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import gerar_bootstrap5_compat as g

CSS5 = (
    ':root{--bs-danger-rgb:220,53,69;--bs-x:1;--bs-border-color:#ddd;--bs-body-bg:#fff}'
    '.border{border:1px solid var(--bs-border-color)!important}'
    '.bg-body{background-color:var(--bs-body-bg)!important}'
    '@media (min-width:1200px){.container,.container-xl{max-width:1140px}.container-xl{width:1px;max-width:1px}}'
    '.text-center{text-align:center!important}'
    '.text-danger{--bs-text-opacity:1;color:rgba(var(--bs-danger-rgb),var(--bs-text-opacity))!important}'
    '.btn{padding:1px;color:red!important}'
    '.col-md-6{flex:0 0 auto;width:50%}.col-6{width:50%}'
    '.form-select{background:url("data:image/svg+xml;charset=utf8,a;b");display:block}'
    '@media (min-width:768px){.d-md-none{display:none!important}.card{padding:0}.col-md-3{width:25%}}'
    '@media (prefers-reduced-motion:reduce){.btn{transition:none}}'
)
CSS6 = '.col-6{width:1px}.text-center{text-align:center}.container{max-width:1px}:root{--bs-y:1;--bs-border-color:red;--bs-body-bg:#000}'


def test_mantem_utilitarios_grade_responsiva_e_form_select_e_so_isso() -> None:
    saida = g.gerar(CSS5, CSS6)

    for mantido in ('.text-center{', '.text-danger{', '.col-md-6{', '.form-select{', '@media (min-width:768px){.d-md-none{', '.col-md-3{'):
        assert mantido in saida, mantido
    for descartado in ('.btn{', '.col-6{', '.card{', 'prefers-reduced-motion'):
        assert descartado not in saida, descartado


def test_declara_so_as_variaveis_que_o_6_nao_tem_e_que_as_regras_leem() -> None:
    saida = g.gerar(CSS5, CSS6)

    assert '--bs-danger-rgb:220,53,69' in saida
    assert '--bs-x' not in saida


def test_variavel_que_o_6_tambem_declara_sai_com_prefixo_e_o_container_vem_so_com_a_largura() -> None:
    saida = g.gerar(CSS5, CSS6)

    # `--bs-body-bg` colide com o do 6: sai como `--bs5-` no :root do compat e a regra lê o prefixado.
    assert ':root{--bs5-body-bg:#fff;--bs-danger-rgb:220,53,69}' in saida
    assert '.bg-body{background-color:var(--bs5-body-bg)!important}' in saida
    # `--bs-border-color` o tema redefine (VARIAVEIS_DO_TEMA): não é declarado nem prefixado, a regra o lê vivo, como no 5.
    assert '--bs5-border-color' not in saida
    assert '.border{border:1px solid var(--bs-border-color)!important}' in saida
    assert '@media (min-width:1200px){.container,.container-xl{max-width:1140px}}' in saida
