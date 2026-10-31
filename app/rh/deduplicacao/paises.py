"""País de origem de pessoa física (comum.Pais) a partir do país do aluno (edu.Pais): pelo nome e, sem correspondência,
pela sigla ISO 3166-1 alfa-3.

edu.Pais e comum.Pais usam esquemas de código diferentes: nunca converter pelo código. Os nomes também divergem
("República Árabe Do Egito" no edu, "EGITO" no SIAPE); a sigla do edu é o alfa-3, o mesmo de ``comum.Pais.iso_alfa3``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rh.deduplicacao.documentos import normalizar_nome_pais

if TYPE_CHECKING:
    from comum.models import Pais


def ids_por_nome() -> dict[str, int]:
    from comum.models import Pais

    return {normalizar_nome_pais(nome): pk for pk, nome in Pais.objects.values_list('pk', 'nome')}


def ids_por_iso() -> dict[str, int]:
    """O comum.Pais de cada alfa-3; com mais de um (territórios, a Suíça 150 e 236), o de menor código do SIAPE, que é o do Estado."""
    from comum.models import Pais

    linhas = Pais.objects.exclude(iso_alfa3='').order_by('-codigo').values_list('pk', 'iso_alfa3')
    return {iso: pk for pk, iso in linhas}  # em ordem decrescente: fica o de menor código


def id_do_pais_do_aluno(nome: str | None, sigla: str | None, por_nome: dict[str, int], por_iso: dict[str, int]) -> int | None:
    return por_nome.get(normalizar_nome_pais(nome)) or por_iso.get((sigla or '').strip().upper())


def pais_do_aluno(pais: Any) -> Pais | None:
    """O comum.Pais do edu.Pais ``pais`` (pelo nome, senão pela sigla alfa-3)."""
    from comum.models import Pais

    pk = id_do_pais_do_aluno(pais.nome, pais.sigla, ids_por_nome(), ids_por_iso()) if pais else None
    return Pais.objects.get(pk=pk) if pk else None


def pais_por_nome(nome: str | None) -> Pais | None:
    """Só pelo nome: para quem não tem o edu.Pais (a planilha de intercâmbio traz o nome do país)."""
    from comum.models import Pais

    pk = ids_por_nome().get(normalizar_nome_pais(nome)) if nome else None
    return Pais.objects.get(pk=pk) if pk else None
