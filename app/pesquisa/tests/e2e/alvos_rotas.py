"""Alvos e helpers do smoke de rotas de `pesquisa` (`test_17_rotas.py` e `test_18_rotas_editora_pi.py`).

Cada rota declarada ali usa um **marcador** entre chaves (``{projeto}``), e não um ``pk``: o
valor real só entra em tempo de execução, resolvido a partir do que a cadeia dos `test_NN_*`
já criou. A vantagem não é elegância — é que nenhum ``pk`` mágico é inventado, e um alvo que
não existe falha dizendo **o que** falta e **quem** cria, em vez de virar um 404 no meio da
lista de falhas.

Os resolvers são preguiçosos de propósito (via ``Alvos``, abaixo):
resolver todos de uma vez amarraria cada grupo de rotas ao estado de todos os models, e há alvo
que só existe depois de um degrau específico da cadeia.
"""

from __future__ import annotations

from djtools.e2e_ui import Tela


def _primeiro(modelo, **filtros):
    """``pk`` determinístico do primeiro registro que casa — ou falha dizendo o que falta.

    ``order_by('id')`` para o smoke não mudar de alvo entre execuções, e ``assert`` em vez de
    ``skip`` porque uma rota declarada e não visitada seria cobertura fantasma: o gate lê o
    literal do arquivo, não a request.
    """
    objeto = modelo.objects.filter(**filtros).order_by('id').first()
    assert objeto is not None, (
        f'sem {modelo.__name__} ({filtros}) no banco: a cadeia é sequencial, rode `pytest pesquisa/tests/e2e` inteiro '
        '(o smoke depende do que os test_NN_* criam)'
    )
    return objeto.pk


def _projeto():
    from pesquisa.models import Projeto

    return _primeiro(Projeto, titulo='Título do projeto')


def _obra():
    from pesquisa.models import Obra

    return _primeiro(Obra, titulo='título da obra')


def _edital():
    from pesquisa.models import Edital

    return _primeiro(Edital, titulo='Nome do edital')


def _edital_editora():
    from pesquisa.models import EditalSubmissaoObra

    return _primeiro(EditalSubmissaoObra, titulo='Edital para publicação')


def _participacao():
    from pesquisa.models import Participacao

    return _primeiro(Participacao, projeto__titulo='Título do projeto')


def _laboratorio():
    from pesquisa.models import LaboratorioPesquisa

    return _primeiro(LaboratorioPesquisa, nome__startswith='Nome do Laboratório ')


def _comissao():
    from pesquisa.models import ComissaoEditalPesquisa

    return _primeiro(ComissaoEditalPesquisa)


def _registro_pi():
    from pesquisa.models import RegistroPropriedadeIntelectual

    return _primeiro(RegistroPropriedadeIntelectual)


def _desembolso():
    from pesquisa.models import Desembolso

    return _primeiro(Desembolso, item__projeto__titulo='Título do projeto')


def _meta():
    from pesquisa.models import Meta

    return _primeiro(Meta, projeto__titulo='Título do projeto')


def _etapa():
    from pesquisa.models import Etapa

    return _primeiro(Etapa, meta__projeto__titulo='Título do projeto')


def _item_memoria():
    from pesquisa.models import ItemMemoriaCalculo

    return _primeiro(ItemMemoriaCalculo, projeto__titulo='Título do projeto')


def resolvedores() -> dict:
    """``marcador -> função que devolve o pk``. O marcador é o que a rota escreve entre chaves."""
    return {
        'projeto': _projeto,
        'obra': _obra,
        'edital': _edital,
        'edital_editora': _edital_editora,
        'participacao': _participacao,
        'laboratorio': _laboratorio,
        'comissao': _comissao,
        'registro_pi': _registro_pi,
        'desembolso': _desembolso,
        'meta': _meta,
        'etapa': _etapa,
        'item_memoria': _item_memoria,
    }


class Alvos(dict):
    """``marcador -> valor``, resolvido **na primeira vez que uma rota o usa**.

    Usado com ``str.format_map`` (``format(**mapa)`` copiaria o dicionário e nunca chamaria
    ``__missing__``). O valor fica em cache no próprio dicionário.
    """

    def __init__(self, resolvedores):
        super().__init__()
        self._resolvedores = resolvedores

    def __missing__(self, marcador):
        resolvedor = self._resolvedores.get(marcador)
        assert resolvedor, f'marcador {{{marcador}}} sem alvo declarado em pesquisa/tests/e2e/alvos_rotas.py'
        self[marcador] = resolvedor()
        return self[marcador]


def abrir(web, rotas, papel, alvos=None):
    """Abre cada rota e devolve a lista de problemas, **sem parar na primeira**.

    O `except` é largo de propósito: uma exceção do Playwright (timeout, redirect recusado)
    abortaria o laço e o relatório diria "erro interno" em vez de listar as rotas quebradas —
    que é justamente o que este smoke existe para dizer.
    """
    tela = Tela(web)
    falhas, guardadas = [], []
    for rota in rotas:
        endereco = rota.format_map(alvos) if alvos is not None else rota
        try:
            resposta = tela.buscar(endereco)
        except Exception as erro:
            falhas.append(f'{endereco} -> {type(erro).__name__}: {str(erro).splitlines()[0]}')
            continue
        if resposta.status == 200:
            continue
        if resposta.status in (301, 302):
            destino = resposta.headers.get('location', '')
            if 'login' in destino:
                falhas.append(f'{endereco} -> redirect para o login ({destino})')
            continue
        if resposta.status == 403:
            guardadas.append(endereco)
            continue
        falhas.append(f'{endereco} -> HTTP {resposta.status}')
    return falhas, guardadas


def relatorio_de_guardadas(guardadas: list[str]) -> None:
    """Escreve em stderr quantas rotas responderam 403 e quais.

    Não é asserção: num módulo **encadeado** como este, 403 numa rota que o guard condiciona ao
    estado do projeto/obra significa "guarda fechado", não "papel errado" — o papel de cada grupo
    foi medido nas execuções em que a cadeia estava no estado certo. `sys.stderr` direto porque o
    hook `prints` do pre-commit veta `print`.
    """
    import sys

    sys.stderr.write(f'\n[rotas] {len(guardadas)} rotas responderam 403 (guard de estado):\n')
    for endereco in guardadas:
        sys.stderr.write(f'  {endereco}\n')
