"""Executa um grafo de dependências: em série (workers <= 1) ou num pool de threads.

`executar_etapas` é a base: cada nó pronto é expandido em etapas de unidades (uma unidade é
uma função sem argumentos). `executar_grafo` é o caso particular de uma única unidade por nó.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from functools import partial

Unidade = Callable[[], None]


# Para que serve: quem chama o agendador precisa decidir a situação final da importação e montar
# o `Log` (o que rodou, o que falhou, o que ficou de fora e por quê) sem reconsultar o banco.
@dataclass
class Resultado:
    """Desfecho agregado da execução do grafo, por nome de nó.

    Attributes:
        concluidos: Nomes que terminaram sem erro, na ordem em que concluíram.
        falhos: Nome do nó -> exceção que o fez falhar.
        pulados: Nome do nó -> motivo pelo qual ele não chegou a rodar.
    """

    concluidos: list[str] = field(default_factory=list)
    falhos: dict[str, BaseException] = field(default_factory=dict)
    pulados: dict[str, str] = field(default_factory=dict)


def _nada(nome: str, motivo: str) -> None:
    """Callback padrão de `ao_pular`: não faz nada."""
    return None


def _nada_final(nome: str, erro: BaseException | None) -> None:
    """Callback padrão de `ao_finalizar`: não faz nada."""
    return None


@dataclass
class _EstadoNo:
    """Estado de um nó durante a execução paralela do grafo.

    Attributes:
        etapas: Etapas do nó ainda não submetidas ao pool, na ordem em que devem rodar.
        pendentes_na_etapa: Quantas unidades da etapa atual ainda não terminaram.
        erro: Primeira exceção ocorrida numa unidade deste nó, se houver.
    """

    etapas: list[list[Unidade]]
    pendentes_na_etapa: int = 0
    erro: BaseException | None = None


@dataclass
class _ContextoParalelo:
    """Estado compartilhado pelas funções auxiliares da execução paralela do grafo.

    Attributes:
        pendentes: Nome do nó -> dependências dele ainda não concluídas.
        pool: Pool de threads onde as unidades são submetidas.
        ao_finalizar: Chamado com (nome, erro) quando um nó termina.
        ao_pular: Chamado com (nome, motivo) quando um nó é pulado.
        resultado: Resultado agregado, atualizado conforme os nós terminam.
        estados: Nome do nó -> `_EstadoNo`, para os nós ainda em execução.
        em_execucao: Future submetida ao pool -> nome do nó dono dela.
    """

    pendentes: dict[str, set[str]]
    pool: ThreadPoolExecutor
    ao_finalizar: Callable[[str, BaseException | None], None]
    ao_pular: Callable[[str, str], None]
    resultado: Resultado
    estados: dict[str, _EstadoNo] = field(default_factory=dict)
    em_execucao: dict[Future, str] = field(default_factory=dict)


# Para que serve: os layouts do SIAPE têm precedência (tabelas antes do servidor, servidor antes dos
# históricos) e alguns são grandes demais para uma thread só. Este motor roda o que já pode rodar
# em paralelo, respeita a ordem e isola falhas: pula só quem depende do que falhou.
def executar_etapas(
    dependencias: Mapping[str, Collection[str]],
    expandir: Callable[[str], Sequence[Sequence[Unidade]]],
    workers: int,
    ao_pular: Callable[[str, str], None] = _nada,
    ao_finalizar: Callable[[str, BaseException | None], None] = _nada_final,
) -> Resultado:
    """Executa um grafo de dependências em que cada nó pronto é expandido em etapas de unidades.

    Um nó fica pronto quando todas as suas dependências concluíram. As etapas de um mesmo nó rodam
    em sequência; as unidades de uma mesma etapa rodam em paralelo entre si (quando `workers > 1`).
    Se uma etapa tem unidade com erro, as etapas seguintes do nó não rodam. `expandir`,
    `ao_pular` e `ao_finalizar` são sempre chamados na thread que chamou esta função; só as
    unidades vão para o pool.

    Args:
        dependencias: Nome do nó -> nomes dos nós dos quais ele depende.
        expandir: Dado o nome de um nó pronto, devolve suas etapas (sequências de unidades).
        workers: Tamanho do pool de threads; `workers <= 1` executa tudo em série, na thread atual.
        ao_pular: Chamado com (nome, motivo) quando um nó é pulado por dependência não concluída.
        ao_finalizar: Chamado com (nome, erro) quando um nó termina (`erro` é `None` em sucesso).

    Returns:
        O `Resultado` agregado da execução (concluídos, falhos, pulados).

    Raises:
        ValueError: se sobrarem nós pendentes sem nenhum pronto (ciclo ou dependência inexistente).
    """
    pendentes = {nome: set(deps) for nome, deps in dependencias.items()}
    resultado = Resultado()
    if workers <= 1:
        _em_serie_etapas(pendentes, expandir, ao_finalizar, ao_pular, resultado)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='importacao_siape') as pool:
            try:
                _em_paralelo_etapas(pendentes, expandir, ao_pular, ao_finalizar, resultado, pool)
            except BaseException:
                # um `ao_pular`/`ao_finalizar` que estoura na thread principal (fora dos `except
                # Exception` de `_finalizar_no`) sairia deste bloco sem cancelar nada: o `__exit__`
                # do pool esperaria as unidades AINDA NA FILA rodarem até o fim antes de propagar.
                pool.shutdown(wait=True, cancel_futures=True)
                raise
    return resultado


# Para que serve: atalho para quando cada nó é uma tarefa só, sem lotes. Hoje só os testes do
# agendador o usam; a importação usa `executar_etapas` direto.
def executar_grafo(
    dependencias: Mapping[str, Collection[str]],
    executar: Callable[[str], None],
    workers: int,
    ao_pular: Callable[[str, str], None] = _nada,
) -> Resultado:
    """Caso particular de `executar_etapas` com uma única unidade por nó (sem etapas internas).

    Args:
        dependencias: Nome do nó -> nomes dos nós dos quais ele depende.
        executar: Chamado com o nome de cada nó pronto.
        workers: Tamanho do pool de threads; `workers <= 1` executa tudo em série.
        ao_pular: Chamado com (nome, motivo) quando um nó é pulado por dependência não concluída.

    Returns:
        O `Resultado` agregado da execução (concluídos, falhos, pulados).
    """
    return executar_etapas(dependencias, lambda nome: [[partial(executar, nome)]], workers, ao_pular)


def _prontos(pendentes: dict[str, set[str]]) -> list[str]:
    """Remove de `pendentes` e devolve os nós sem nenhuma dependência pendente."""
    prontos = [nome for nome, deps in pendentes.items() if not deps]
    for nome in prontos:
        del pendentes[nome]
    return prontos


def _erro_de_ciclo(pendentes: dict[str, set[str]]) -> ValueError:
    """Monta o erro para quando sobram nós pendentes sem nenhum pronto (ciclo ou dependência inexistente)."""
    return ValueError('Ciclo ou dependência inexistente no grafo: ' + ', '.join(sorted(pendentes)))


def _finalizar_no(
    nome: str,
    erro: BaseException | None,
    ao_finalizar: Callable[[str, BaseException | None], None],
    pendentes: dict[str, set[str]],
    ao_pular: Callable[[str, str], None],
    resultado: Resultado,
) -> None:
    """Chama `ao_finalizar` para o nó e registra o desfecho dele em `resultado`.

    Uma exceção levantada por `ao_finalizar` vira o erro do nó quando ele ainda não tinha falhado
    (senão o erro original das unidades prevalece).
    """
    try:
        ao_finalizar(nome, erro)
    except Exception as erro_finalizar:
        if erro is None:
            erro = erro_finalizar
    _registrar(nome, erro, pendentes, ao_pular, resultado)


def _registrar(
    nome: str,
    erro: BaseException | None,
    pendentes: dict[str, set[str]],
    ao_pular: Callable[[str, str], None],
    resultado: Resultado,
) -> None:
    """Marca o nó como concluído (liberando-o das dependências dos demais nós) ou como falho,
    pulando em cascata quem dependia dele.
    """
    if erro is None:
        resultado.concluidos.append(nome)
        for deps in pendentes.values():
            deps.discard(nome)
        return
    resultado.falhos[nome] = erro
    _pular_dependentes(nome, pendentes, ao_pular, resultado)


def _pular_dependentes(nome: str, pendentes: dict[str, set[str]], ao_pular: Callable[[str, str], None], resultado: Resultado) -> None:
    """Pula recursivamente todo nó ainda pendente que dependia (direta ou indiretamente) de `nome`.

    Args:
        nome: Nó que falhou (ou já foi pulado), cujos dependentes devem ser pulados também.
        pendentes: Nome do nó -> dependências ainda não concluídas; nós pulados são removidos daqui.
        ao_pular: Chamado com (nome do dependente, motivo) para cada nó pulado.
        resultado: Resultado agregado, onde o motivo de cada pulo é registrado.
    """
    for dependente in [n for n, deps in pendentes.items() if nome in deps]:
        if dependente not in pendentes:
            continue
        del pendentes[dependente]
        motivo = f'Dependência {nome} não foi concluída.'
        resultado.pulados[dependente] = motivo
        ao_pular(dependente, motivo)
        _pular_dependentes(dependente, pendentes, ao_pular, resultado)


# --- série -----------------------------------------------------------------


def _em_serie_etapas(
    pendentes: dict[str, set[str]],
    expandir: Callable[[str], Sequence[Sequence[Unidade]]],
    ao_finalizar: Callable[[str, BaseException | None], None],
    ao_pular: Callable[[str, str], None],
    resultado: Resultado,
) -> None:
    """Executa o grafo inteiro na thread atual: a cada volta, roda todos os nós prontos, em ordem.

    Raises:
        ValueError: se sobrarem nós pendentes sem nenhum pronto (ciclo ou dependência inexistente).
    """
    while pendentes:
        prontos = _prontos(pendentes)
        if not prontos:
            raise _erro_de_ciclo(pendentes)
        for nome in prontos:
            erro = _executar_no_serial(nome, expandir)
            _finalizar_no(nome, erro, ao_finalizar, pendentes, ao_pular, resultado)


def _executar_no_serial(nome: str, expandir: Callable[[str], Sequence[Sequence[Unidade]]]) -> BaseException | None:
    """Expande e roda todas as etapas de um nó, em sequência; devolve o primeiro erro, se houver."""
    try:
        etapas = expandir(nome)
    except Exception as erro:
        return erro
    for etapa in etapas:
        erro = _executar_etapa_serial(etapa)
        if erro is not None:
            return erro
    return None


def _executar_etapa_serial(etapa: Sequence[Unidade]) -> BaseException | None:
    """Roda todas as unidades da etapa, mesmo se uma falhar, e devolve o primeiro erro, se houver."""
    primeiro_erro: BaseException | None = None
    for unidade in etapa:
        try:
            unidade()
        except Exception as erro:
            if primeiro_erro is None:
                primeiro_erro = erro
    return primeiro_erro


# --- paralelo ----------------------------------------------------------------


def _em_paralelo_etapas(
    pendentes: dict[str, set[str]],
    expandir: Callable[[str], Sequence[Sequence[Unidade]]],
    ao_pular: Callable[[str, str], None],
    ao_finalizar: Callable[[str, BaseException | None], None],
    resultado: Resultado,
    pool: ThreadPoolExecutor,
) -> None:
    """Executa o grafo no pool: inicia os nós prontos, espera a primeira unidade concluir e repete,
    até não sobrar nó pendente nem unidade em execução.

    Raises:
        ValueError: se sobrarem nós pendentes sem nenhum pronto (ciclo ou dependência inexistente).
    """
    ctx = _ContextoParalelo(pendentes, pool, ao_finalizar, ao_pular, resultado)
    while ctx.pendentes or ctx.em_execucao:
        _iniciar_prontos(ctx, expandir)
        if not ctx.em_execucao:
            if ctx.pendentes:
                raise _erro_de_ciclo(ctx.pendentes)
            continue
        feitos, _ = wait(ctx.em_execucao, return_when=FIRST_COMPLETED)
        _processar_completos(feitos, ctx)


def _iniciar_prontos(ctx: _ContextoParalelo, expandir: Callable[[str], Sequence[Sequence[Unidade]]]) -> None:
    """Inicia todo nó que estiver pronto, inclusive os que ficam prontos por causa de um nó sem
    etapas finalizado nesta mesma passada (ver comentário abaixo).
    """
    # Um nó sem etapas termina aqui mesmo (síncrono), o que pode liberar novos dependentes:
    # laço até não sobrar nenhum pronto, para não deixá-los esperando um future de outro nó.
    while prontos := _prontos(ctx.pendentes):
        for nome in prontos:
            estado = _iniciar_no_paralelo(nome, expandir, ctx.pool, ctx.em_execucao)
            if estado.pendentes_na_etapa == 0:
                _finalizar_no(nome, estado.erro, ctx.ao_finalizar, ctx.pendentes, ctx.ao_pular, ctx.resultado)
            else:
                ctx.estados[nome] = estado


def _iniciar_no_paralelo(
    nome: str,
    expandir: Callable[[str], Sequence[Sequence[Unidade]]],
    pool: ThreadPoolExecutor,
    em_execucao: dict[Future, str],
) -> _EstadoNo:
    """Expande as etapas do nó e submete a primeira ao pool; devolve o estado inicial do nó.

    Uma falha ao expandir vira o erro do nó, sem etapas para submeter.
    """
    try:
        etapas = [list(etapa) for etapa in expandir(nome)]
    except Exception as erro:
        return _EstadoNo(etapas=[], erro=erro)
    estado = _EstadoNo(etapas=etapas)
    _submeter_proxima_etapa(nome, estado, pool, em_execucao)
    return estado


def _proxima_etapa(estado: _EstadoNo) -> list[Unidade] | None:
    """Descarta etapas vazias e devolve a próxima etapa não vazia do nó, ou `None` se acabaram."""
    while estado.etapas:
        etapa = estado.etapas.pop(0)
        if etapa:
            return etapa
    return None


def _submeter_proxima_etapa(nome: str, estado: _EstadoNo, pool: ThreadPoolExecutor, em_execucao: dict[Future, str]) -> None:
    """Submete ao pool as unidades da próxima etapa do nó, ou marca o nó sem pendências se já acabaram."""
    proxima = _proxima_etapa(estado)
    if proxima is None:
        estado.pendentes_na_etapa = 0
        return
    estado.pendentes_na_etapa = len(proxima)
    for unidade in proxima:
        em_execucao[pool.submit(unidade)] = nome


def _processar_completos(feitos: Collection[Future], ctx: _ContextoParalelo) -> None:
    """Contabiliza cada future concluída e avança (ou finaliza) o nó dela quando a etapa termina."""
    for futuro in feitos:
        nome = ctx.em_execucao.pop(futuro)
        estado = ctx.estados[nome]
        _registrar_conclusao_de_unidade(estado, futuro.exception())
        if estado.pendentes_na_etapa == 0:
            _avancar_ou_finalizar(nome, estado, ctx)


def _registrar_conclusao_de_unidade(estado: _EstadoNo, erro_unidade: BaseException | None) -> None:
    """Guarda o erro da unidade no estado do nó (o primeiro, se mais de uma falhar) e decrementa
    a contagem de unidades ainda pendentes na etapa atual.
    """
    if erro_unidade is not None and estado.erro is None:
        estado.erro = erro_unidade
    estado.pendentes_na_etapa -= 1


def _avancar_ou_finalizar(nome: str, estado: _EstadoNo, ctx: _ContextoParalelo) -> None:
    """Submete a próxima etapa do nó se ele não falhou; finaliza o nó quando não sobrar etapa."""
    if estado.erro is None:
        _submeter_proxima_etapa(nome, estado, ctx.pool, ctx.em_execucao)
    if estado.pendentes_na_etapa == 0:
        del ctx.estados[nome]
        _finalizar_no(nome, estado.erro, ctx.ao_finalizar, ctx.pendentes, ctx.ao_pular, ctx.resultado)
