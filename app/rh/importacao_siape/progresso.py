"""Instrumenta a execução de um layout sem alterar as funções `importar_*` do ImportadorSIAPE."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager


# Para que serve: as funções `importar_*` do `ImportadorSIAPE` só recebem uma lista e iteram sobre
# ela; para mostrar a barra de progresso e saber a linha de cada aviso sem reescrevê-las, a lista
# passada é esta, que conta o avanço enquanto é percorrida.
class ItensComProgresso(list):
    """Lista de itens que reporta quantos já foram percorridos, sem alterar quem itera sobre ela.

    Usada como a lista de itens passada às funções `importar_*` do `ImportadorSIAPE`: cada `for
    item in itens` avança `self.posicao` e, a cada `passo` itens (e ao esgotar a iteração), chama
    `ao_avancar` com a quantidade percorrida — sem exigir nenhuma mudança nessas funções. Só
    reporta quantidades maiores que a última reportada (uma segunda iteração não reporta de novo);
    acesso por índice, fatia ou `len` não conta como avanço.

    Args:
        itens: Itens da lista (as linhas do lote, já como dicionários).
        ao_avancar: Chamado com a quantidade de itens já percorridos, a cada `passo` itens.
        passo: A cada quantos itens reportar o avanço; por padrão, 1/50 do tamanho da lista
            (no mínimo 1), para não chamar `ao_avancar` a cada item.
    """

    def __init__(self, itens: Iterable[dict], ao_avancar: Callable[[int], None], passo: int | None = None) -> None:
        super().__init__(itens)
        self.posicao = 0
        self._ao_avancar = ao_avancar
        self._passo = passo or max(1, len(self) // 50)
        self._reportado = 0

    def __iter__(self) -> Iterator[dict]:
        """Itera pelos itens como uma lista normal, reportando o avanço a cada `passo` itens e ao final."""
        for indice, item in enumerate(super().__iter__(), start=1):
            self.posicao = indice
            if indice % self._passo == 0:
                self._reportar(indice)
            yield item
        self._reportar(len(self))

    def _reportar(self, quantidade: int) -> None:
        """Chama `ao_avancar` só se `quantidade` for maior que o último valor já reportado."""
        if quantidade > self._reportado:
            self._reportado = quantidade
            self._ao_avancar(quantidade)


# Para que serve: o `ImportadorSIAPE` relata problemas por linha só via logging; sem este handler
# esses avisos iriam para o log do servidor, fora do alcance do operador. Com ele, viram
# ocorrências por arquivo/linha na tela, sem mudar o importador.
class CapturaOcorrencias(logging.Handler):
    """Handler de logging que captura, só da própria thread, os avisos/erros emitidos durante a
    importação de um lote, para registrá-los como `ImportacaoSiapeOcorrencia`.

    Filtrar pela thread (`record.thread != self._thread`) é essencial: vários lotes rodam em
    threads diferentes do mesmo pool, cada um com seu próprio handler registrado no mesmo logger
    (`rh.importador`), e cada um só deve capturar os registros da sua própria execução.

    Args:
        registrar: Chamado com (nível em minúsculas, posição do item atual ou `None`, mensagem)
            para cada registro de nível WARNING ou acima emitido pela própria thread no logger
            instrumentado (ou em loggers filhos dele, por propagação).
        itens: `ItensComProgresso` em andamento, usado para saber a posição do item atual no
            momento do log; `None` quando a posição não é rastreada.
    """

    def __init__(self, registrar: Callable[[str, int | None, str], None], itens: ItensComProgresso | None = None) -> None:
        super().__init__(level=logging.WARNING)
        self._thread = threading.get_ident()
        self._registrar = registrar
        self._itens = itens

    def emit(self, record: logging.LogRecord) -> None:
        """Chama `registrar` para o registro, se ele vier da mesma thread que criou este handler."""
        if record.thread != self._thread:
            return
        try:
            linha = self._itens.posicao if self._itens is not None else None
            self._registrar(record.levelname.lower(), linha, record.getMessage())
        except Exception:
            self.handleError(record)


# Para que serve: garante que o handler de um lote é removido ao fim dele, mesmo com erro; sem isso,
# handlers de lotes já terminados se acumulariam no logger compartilhado ao longo da importação.
@contextmanager
def capturando_ocorrencias(
    registrar: Callable[[str, int | None, str], None], itens: ItensComProgresso | None = None, logger: str = 'rh.importador'
) -> Iterator[CapturaOcorrencias]:
    """Instala um `CapturaOcorrencias` no logger durante o bloco `with`, e o remove ao sair.

    Args:
        registrar: Repassado ao `CapturaOcorrencias` — chamado para cada ocorrência capturada.
        itens: `ItensComProgresso` em andamento, repassado ao `CapturaOcorrencias` para saber a
            posição do item atual; `None` quando não há posição a rastrear.
        logger: Nome do logger instrumentado (padrão: `rh.importador`).

    Não mexe no nível do logger: várias threads entram/saem daqui ao mesmo tempo (um lote cada)
    e salvar/restaurar o nível por aqui faria uma thread desfazer o `setLevel` de outra. Quem
    garante que o nível deixa passar WARNING é `execucao._garantir_nivel_de_log`, chamado uma
    única vez na thread principal antes do grafo começar.
    """
    alvo = logging.getLogger(logger)
    handler = CapturaOcorrencias(registrar, itens)
    alvo.addHandler(handler)
    try:
        yield handler
    finally:
        alvo.removeHandler(handler)
