"""Conflito de campo entre a PF sobrevivente e as perdedoras (puro, usado no planejar e no aplicar)."""

from __future__ import annotations

from typing import Any

# Derivados, identidade ou recalculados pelo save(): não se mesclam.
IGNORADOS = {
    'id',
    'pessoa_ptr_id',
    'cpf',
    'documento_identificador',
    'nome',
    'nome_usual',
    'eh_servidor',
    'eh_aluno',
    'eh_prestador',
    'eh_usuarioexterno',
    'search_fields_optimized',
    'uuid',
}
# Só auditados: o passaporte do sobrevivente não é trocado pelo da perdedora.
SO_AUDITORIA = {'passaporte'}
# Biometria e senha: mesclam-se, mas o descarte é auditado sem o valor (valor ``None`` no descarte).
SEM_VALOR_NA_AUDITORIA = {'template', 'senha_ponto'}
# Acompanham outro campo: vêm da mesma PF que deu o valor dele (a marca de origem da digital acompanha a digital).
# O False de um booleano não é vazio: sem isso, a digital da perdedora viria com a marca da sobrevivente.
ACOMPANHANTES = {'template_importado_terminal': 'template'}


def _normalizar(valor: Any) -> Any:
    """BinaryField chega como memoryview (psycopg2) ou bytes (psycopg3): compara-se pelo conteúdo."""
    return bytes(valor) if isinstance(valor, memoryview) else valor


def _vazio(valor: Any) -> bool:
    return valor is None or valor == '' or valor == b''


def _descarte(pk: int, campo: str, valor: Any) -> tuple[int, str, Any]:
    return pk, campo, None if campo in SEM_VALOR_NA_AUDITORIA else valor


def _resolver_campo(campo: str, atual: Any, ordenadas: list[dict], preenchimentos: dict[str, Any], descartes: list) -> dict | None:
    """Preenche o campo vazio com a primeira perdedora que tem valor e descarta os outros valores; devolve a perdedora que preencheu."""
    atual, origem = _normalizar(atual), None
    for perdedora in ordenadas:
        valor = _normalizar(perdedora[campo])
        if _vazio(valor) or valor == atual:
            continue
        if _vazio(atual) and campo not in SO_AUDITORIA:
            preenchimentos[campo] = atual = valor
            origem = perdedora
        else:
            descartes.append(_descarte(perdedora['pk'], campo, valor))
    return origem


def campos_mesclaveis() -> list[str]:
    from rh.models import PessoaFisica

    return [campo.attname for campo in PessoaFisica._meta.concrete_fields if campo.attname not in IGNORADOS]


def resolver_campos(vencedor: dict, perdedoras: list[dict]) -> tuple[dict[str, Any], list[tuple[int, str, Any]]]:
    """Preenche os vazios do vencedor com a perdedora de maior id; devolve o que foi descartado.

    O descarte de um campo de ``SEM_VALOR_NA_AUDITORIA`` vem com valor ``None``: quem audita não vê a biometria/senha.
    Um campo de ``ACOMPANHANTES`` vem da PF que deu o valor do campo que ele acompanha.
    """
    preenchimentos: dict[str, Any] = {}
    descartes: list[tuple[int, str, Any]] = []
    ordenadas = sorted(perdedoras, key=lambda p: p['pk'], reverse=True)
    origens: dict[str, dict] = {}
    for campo, atual in vencedor.items():
        if campo != 'pk' and campo not in ACOMPANHANTES:
            origem = _resolver_campo(campo, atual, ordenadas, preenchimentos, descartes)
            if origem is not None:
                origens[campo] = origem
    for campo, principal in ACOMPANHANTES.items():
        if campo not in vencedor:
            continue
        if principal in origens:
            preenchimentos[campo] = origens[principal][campo]
        else:
            _resolver_campo(campo, vencedor[campo], ordenadas, preenchimentos, descartes)
    descartes.sort(key=lambda d: (d[0], d[1]))
    return preenchimentos, descartes
