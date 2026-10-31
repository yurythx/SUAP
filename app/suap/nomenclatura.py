# ruff: noqa: F403
# -------------------------------
# Campus
# -------------------------------
campus = 'Campus'
campi = 'Campi'
do_campus = 'do campus'
dos_campi = 'dos campi'
o_campus = 'o campus'
os_campi = 'os campi'

# -------------------------------
# PGD 2
# -------------------------------
# PIT
# ---------
plano_individual_de_trabalho_pgd2 = 'Plano Individual de Trabalho'
plano_individual_de_trabalho_sigla_pgd2 = 'PIT'
plano_individual_de_trabalho_com_sigla_pgd2 = 'Plano Individual de Trabalho (PIT)'
#
planos_individuais_de_trabalho_pgd2 = 'Planos Individuais de Trabalho'
plano_individual_de_trabalho_sigla_plural_pgd2 = 'PITs'
# RIT
# ---------
relatorio_individual_de_trabalho_pgd2 = 'Relatório Individual de Trabalho'
relatorio_individual_de_trabalho_sigla_pgd2 = 'RIT'
relatorio_individual_de_trabalho_com_sigla_pgd2 = 'Relatório Individual de Trabalho (RIT)'
#
relatorios_individuais_de_trabalho_pgd2 = 'Relatórios Individuais de Trabalho'
relatorio_individual_de_trabalho_sigla_plural_pgd2 = 'RITs'

# PIT/RIT
# ---------
pit_rit_pgd2 = 'PIT/RIT'
pits_rits_pgd2 = 'PITs/RITs'


# Esse trecho de código tem por objetivo permitir que outros institutos customizem os termos definidos acima
try:
    from .nomenclatura_local import *  # type: ignore[import-untyped]
except ImportError:
    pass
