"""Estado compartilhado entre testes de uma mesma tarefa (encadeamento da submissão).

Os testes de doc rodam em ordem alfabética num único processo (o job ``gerar-doc`` roda
``pytest -m doc`` com ``-n 1``); o teste que cria o projeto pela tela guarda aqui o id para o
teste seguinte da mesma tarefa. Isso acopla a ordem dos arquivos no diretório (``test_02b``
depende de ``test_02a``; ``test_finalizar_projeto``/``test_validar_conclusao`` dependem de
``test_registrar_conclusao``) — quando o teste precisa rodar isolado ou em ordem alterada, esse
encadeamento quebra. O acesso aqui NUNCA levanta ``KeyError`` cru: ``pega`` devolve a chave ou
falha com a mensagem que diz qual teste precisa ter rodado antes, o que também deixa a falha
legível sob ``--reruns 2`` (uma retentativa que não repõe a chave acusa o encadeamento, não um
``KeyError`` sem contexto).
"""

from __future__ import annotations

CAMPOS: dict[str, object] = {}


def pega(chave: str, dependencia: str) -> object:
    """Lê uma chave de ``CAMPOS``, falhando com mensagem clara se ela ainda não existir.

    ``dependencia`` nomeia o teste que produz a chave — a falha então diz "*o teste X deve ter
    rodado antes*" em vez de um ``KeyError`` sem contexto.
    """
    if chave not in CAMPOS:
        raise AssertionError(
            f'"{chave}" não está no estado compartilhado; o teste {dependencia!r} deve ter rodado antes (a suíte depende da ordem alfabética dos arquivos de teste).'
        )
    return CAMPOS[chave]


def novo() -> None:
    """Zera o estado compartilhado — chamado antes de cada teste que o vai popular."""
    CAMPOS.clear()
