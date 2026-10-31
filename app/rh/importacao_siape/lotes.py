"""Divisão de um layout em lotes que podem rodar em paralelo entre si."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from rh.importacao_siape.layouts import Particao
from rh.utils import extrai_matricula

TAMANHO_LOTE_PADRAO = 5000
# piso do tamanho efetivo quando o layout é dividido para ocupar todos os workers: evita lotes
# pequenos demais, em que o custo fixo de cada lote (caches do importador) pesaria mais que o ganho
TAMANHO_MINIMO_LOTE = 1000


# Para que serve: guardar só os índices (e não as linhas) mantém a divisão barata e deixa todos os
# lotes de um arquivo lendo a mesma lista de itens; o número vira o "Lote N" visto na tela.
@dataclass(frozen=True)
class Lote:
    """Um lote de um arquivo: seu número (1-based) e os índices das linhas que ele contém.

    Attributes:
        numero: Número do lote dentro do arquivo, de 1 a N.
        indices: Índices 0-based das linhas do arquivo que pertencem a este lote, em ordem crescente.
    """

    numero: int  # 1..N
    indices: tuple[int, ...]  # índices 0-based das linhas no arquivo, em ordem crescente


def _chave_matricula(item: dict, campo: str) -> str:
    """Matrícula extraída de `campo` no item, ou string vazia se o campo faltar ou for inválido."""
    try:
        return extrai_matricula(item[campo])
    except ValueError, TypeError, IndexError:
        return ''


# Para que serve: traduz a declaração de `layouts._PARTICOES` numa função aplicável linha a linha;
# resolve de antemão o que é caro (o mapa matrícula -> CPF vem pronto de fora) para não consultar o
# banco a cada item.
def chave_de_particao(particao: Particao, cpf_por_matricula: Mapping[str, str] | None = None) -> Callable[[dict], str]:
    """Monta, a partir de uma `Particao`, a função que extrai a chave de partição de um item.

    Args:
        particao: Descreve como obter a chave (tipo + campo de origem).
        cpf_por_matricula: Matrícula -> CPF, necessário só para `particao.tipo == 'cpf_da_matricula'`;
            uma matrícula sem CPF correspondente cai numa chave própria (`'matricula:<matrícula>'`),
            em vez de se misturar com outra matrícula sem CPF.

    Returns:
        Uma função que recebe um item (linha do arquivo, já como dicionário) e devolve a chave de
        partição dele como string.
    """
    cpf_por_matricula = cpf_por_matricula or {}
    if particao.tipo == 'campo':
        return lambda item: item[particao.campo].strip()
    if particao.tipo == 'matricula':
        return lambda item: _chave_matricula(item, particao.campo)

    def _chave_cpf(item: dict) -> str:
        """Chave de partição por CPF do servidor dono da matrícula extraída do campo do item."""
        matricula = _chave_matricula(item, particao.campo)
        return cpf_por_matricula.get(matricula, f'matricula:{matricula}')

    return _chave_cpf


def _agrupar_indices_por_chave(itens: Sequence[dict], chave: Callable[[dict], str]) -> dict[str, list[int]]:
    """Agrupa os índices dos itens pela chave de partição deles, na ordem em que aparecem."""
    indices_por_chave: dict[str, list[int]] = {}
    for indice, item in enumerate(itens):
        indices_por_chave.setdefault(chave(item), []).append(indice)
    return indices_por_chave


def _tamanho_efetivo(linhas: int, tamanho: int, minimo_de_lotes: int, tamanho_minimo: int) -> int:
    """Primeiro decide quantos lotes, depois reparte as linhas por igual (sem sobra minúscula no fim)."""
    quantidade = max(-(-linhas // tamanho), min(minimo_de_lotes, linhas // max(1, tamanho_minimo)))
    return -(-linhas // max(1, quantidade))


# Para que serve: um layout grande (ex.: servidor1, históricos) numa thread só deixaria os outros
# workers ociosos e a importação lenta. Dividir sem separar linhas da mesma chave é o que permite
# paralelizar sem duplicar ou sobrescrever registros.
def dividir_em_lotes(
    itens: Sequence[dict],
    chave: Callable[[dict], str] | None,
    tamanho: int = TAMANHO_LOTE_PADRAO,
    minimo_de_lotes: int = 1,
    tamanho_minimo: int = TAMANHO_MINIMO_LOTE,
) -> list[Lote]:
    """Divide os itens em lotes; uma chave de partição nunca fica em dois lotes.

    Sem `chave` (layout sem partição) ou com até `tamanho` linhas, devolve um único lote com tudo.
    Acima disso, o lote efetivo encolhe até caberem `minimo_de_lotes` lotes (o número de workers),
    sem ficar menor que `tamanho_minimo`: um layout de ~9 mil linhas sozinho na sua camada
    (servidor1..4) ocupa todos os workers. O tamanho efetivo é uma meta, não um teto: as linhas de
    uma chave entram inteiras, então um lote pode passar dele (e sair menos lotes que o previsto).
    """
    if chave is None or len(itens) <= tamanho:
        return [Lote(1, tuple(range(len(itens))))]
    tamanho = _tamanho_efetivo(len(itens), tamanho, minimo_de_lotes, tamanho_minimo)

    indices_por_chave = _agrupar_indices_por_chave(itens, chave)
    lotes: list[Lote] = []
    indices_do_lote: list[int] = []
    for indices in indices_por_chave.values():
        indices_do_lote.extend(indices)
        if len(indices_do_lote) >= tamanho:
            lotes.append(Lote(len(lotes) + 1, tuple(sorted(indices_do_lote))))
            indices_do_lote = []
    if indices_do_lote:
        lotes.append(Lote(len(lotes) + 1, tuple(sorted(indices_do_lote))))
    return lotes
