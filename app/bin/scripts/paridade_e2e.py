#!/usr/bin/env python
"""Gate de paridade cenário→teste entre as ``.feature`` do behave e os e2e do pytest.

Contrato decidido em https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/16970:

- cada teste declara os cenários que cobre com ``@pytest.mark.cenario('<arquivo>.feature', 'Nome', ...)``;
- a unidade é o cenário **ativo** (comentado não conta); ``Esquema do Cenário`` vale 1;
- cenário sem teste pode ser dispensado em ``CENARIOS_DISPENSADOS`` no ``conftest.py`` do módulo,
  sempre com motivo textual;
- **100% = zero órfãos**. Com ``--junitxml``, um teste vermelho derruba TODOS os cenários que declara.

Os marcadores são lidos por AST — sem importar Django, sem subir banco.

Uso::

    python bin/scripts/paridade_e2e.py eventos
    python bin/scripts/paridade_e2e.py eventos --junitxml artifacts/e2e.xml
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

RE_CENARIO = re.compile(r'^\s*(?:Cenário|Cenario|Scenario|Esquema do Cenário|Scenario Outline)\s*:\s*(.+?)\s*$')

Chave = tuple[str, str]


def cenarios_ativos(modulo: str) -> dict[Chave, int]:
    """Mapeia ``(arquivo, nome) -> ocorrências`` para os cenários não comentados do módulo.

    A chave deduplica homônimos dentro do mesmo arquivo (97 casos no repo, quase todos
    boilerplate tipo "Sai do sistema"): repetição colapsa numa unidade e o relatório avisa.
    """
    encontrados: dict[Chave, int] = defaultdict(int)
    for arquivo in sorted(Path(modulo, 'features').rglob('*.feature')):
        for linha in arquivo.read_text(encoding='utf-8', errors='replace').splitlines():
            if linha.lstrip().startswith('#'):
                continue
            casou = RE_CENARIO.match(linha)
            if casou:
                encontrados[(str(arquivo), casou.group(1))] += 1
    return dict(encontrados)


def _literais(no: ast.expr) -> list[str]:
    return [arg.value for arg in getattr(no, 'args', []) if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]


def _marcador_cenario(decorador: ast.expr) -> list[str] | None:
    """Extrai os literais de ``@pytest.mark.cenario(...)``; ``None`` se for outro decorador."""
    if not isinstance(decorador, ast.Call):
        return None
    alvo = decorador.func
    if isinstance(alvo, ast.Attribute) and alvo.attr == 'cenario':
        return _literais(decorador)
    return None


def marcadores(modulo: str) -> dict[Chave, list[str]]:
    """Mapeia ``(arquivo, nome) -> [nodeid-prefixo, ...]`` lendo os testes por AST."""
    declarados: dict[Chave, list[str]] = defaultdict(list)
    for arquivo in sorted(Path(modulo, 'tests', 'e2e').glob('test_*.py')):
        arvore = ast.parse(arquivo.read_text(encoding='utf-8'), filename=str(arquivo))
        for no in arvore.body:
            if not isinstance(no, ast.FunctionDef):
                continue
            for decorador in no.decorator_list:
                args = _marcador_cenario(decorador)
                if args and len(args) >= 2:
                    for nome in args[1:]:
                        declarados[(args[0], nome)].append(f'{arquivo}::{no.name}')
    return dict(declarados)


def _dict_do_conftest(modulo: str, nome: str) -> ast.Dict | None:
    """Devolve o literal de dicionário atribuído a ``nome`` no conftest do módulo.

    Aceita as duas formas de atribuição: ``X = {...}`` (``ast.Assign``) e
    ``X: dict[str, str] = {...}`` (``ast.AnnAssign``), para o conftest poder anotar o dicionário
    sem que o gate deixe de enxergá-lo.
    """
    conftest = Path(modulo, 'tests', 'e2e', 'conftest.py')
    if not conftest.exists():
        return None
    arvore = ast.parse(conftest.read_text(encoding='utf-8'), filename=str(conftest))
    for no in arvore.body:
        alvos = getattr(no, 'targets', []) or [getattr(no, 'target', None)]
        if any(isinstance(alvo, ast.Name) and alvo.id == nome for alvo in alvos) and isinstance(no.value, ast.Dict):
            return no.value
    return None


def dispensas(modulo: str) -> dict[Chave, str]:
    """Lê ``CENARIOS_DISPENSADOS = {('arquivo', 'Cenário'): 'motivo'}`` do conftest do módulo."""
    literal = _dict_do_conftest(modulo, 'CENARIOS_DISPENSADOS')
    return _dict_de_dispensas(literal) if literal else {}


def _dict_de_dispensas(literal: ast.Dict) -> dict[Chave, str]:
    resultado: dict[Chave, str] = {}
    for chave, valor in zip(literal.keys, literal.values, strict=True):
        if not (isinstance(chave, ast.Tuple) and isinstance(valor, ast.Constant)):
            continue
        partes = [elemento.value for elemento in chave.elts if isinstance(elemento, ast.Constant)]
        if len(partes) == 2:
            resultado[(partes[0], partes[1])] = valor.value
    return resultado


def _prefixo_do_caso(caso: ET.Element) -> str:
    """``arquivo.py::funcao`` de um ``<testcase>``, na mesma forma que ``marcadores()`` produz.

    O atributo ``file`` é OPCIONAL no junit e o pytest deste projeto não o emite — o relatório
    traz só ``classname``/``name``/``time``. Sem o fallback todo prefixo saía como
    ``::funcao``, não casava com nada e o gate reportava ``vermelhos: 0`` com a suíte vermelha:
    medido no edu com 3 testes falhando e 3 cenários declarados sobre eles.
    """
    funcao = caso.get('name', '').split('[')[0]
    arquivo = caso.get('file')
    if not arquivo:
        # `classname` é o módulo pontuado (`edu.tests.e2e.test_07_renovacao`). Num teste dentro
        # de classe viria com a classe no fim e o caminho sairia errado — mas `marcadores()` só
        # lê funções de módulo, então esse caso não tem cenário declarado para derrubar.
        arquivo = caso.get('classname', '').replace('.', '/') + '.py'
    return f'{arquivo}::{funcao}'


def vermelhos(caminho_junit: str) -> set[str]:
    """Prefixos ``arquivo::funcao`` que falharam ou deram erro no relatório junit do pytest."""
    raiz = ET.parse(caminho_junit).getroot()
    return {_prefixo_do_caso(caso) for caso in raiz.iter('testcase') if caso.find('failure') is not None or caso.find('error') is not None}


def _emitir(linhas: list[str]) -> None:
    """Escreve o relatório. `sys.stdout.write` e não `print` — o hook `prints` do pre-commit veta o segundo."""
    sys.stdout.write('\n'.join(linhas) + '\n')
    sys.stdout.flush()


def relatar(modulo: str, caminho_junit: str | None) -> int:
    ativos = cenarios_ativos(modulo)
    if not ativos:
        # Sem `.feature` não há o que medir, e "0 de 0 órfãos, exit 0" é um verde vazio —
        # indistinguível de paridade fechada para quem só lê o código de saída. O módulo
        # está no Modo 2 do contrato (a unidade de cobertura é a rota), então o gate manda
        # usar `--rotas` em vez de aprovar por ausência.
        _emitir(
            [
                f'{modulo}: nenhum cenário ativo — módulo sem `features/`.',
                '  use `--rotas`: neste modo a unidade de cobertura é a rota, não o cenário.',
            ]
        )
        return 1

    declarados = marcadores(modulo)
    dispensados = dispensas(modulo)
    falhos = vermelhos(caminho_junit) if caminho_junit else set()

    cobertos, orfaos, com_teste_vermelho = [], [], []
    for chave in sorted(ativos):
        testes = declarados.get(chave, [])
        if not testes:
            (orfaos if chave not in dispensados else cobertos).append(chave)
        elif caminho_junit and any(teste in falhos for teste in testes):
            com_teste_vermelho.append(chave)
        else:
            cobertos.append(chave)

    linhas = [
        f'{modulo}: {len(ativos)} cenários ativos',
        f'  cobertos:    {len(cobertos) - len(dispensados)}',
        f'  dispensados: {len(dispensados)}',
        f'  vermelhos:   {len(com_teste_vermelho)}' + ('' if caminho_junit else '  (sem --junitxml: verde NÃO verificado)'),
        f'  órfãos:      {len(orfaos)}',
    ]
    linhas += [f'    ÓRFÃO  {arquivo} :: {nome}' for arquivo, nome in orfaos]
    linhas += [f'    VERMELHO  {arquivo} :: {nome}' for arquivo, nome in com_teste_vermelho]
    linhas += [
        f'    aviso: nome repetido {vezes}x no arquivo (conta como 1): {chave[0]} :: {chave[1]}'
        for chave, vezes in sorted(ativos.items())
        if vezes > 1
    ]
    _emitir(linhas)

    return 1 if orfaos or com_teste_vermelho else 0


RE_PARAMETRO = re.compile(r'<[^>]+>')


def rotas_do_modulo(modulo: str) -> dict[str, re.Pattern[str]]:
    """Mapeia ``rota declarada -> regex`` a partir de ``<modulo>/urls.py``.

    O SUAP monta cada app em ``/<app>/`` por descoberta automática (``suap/urls.py``), então a
    rota comparável é ``/<modulo>/<padrão>``. Parâmetros (``<int:pk>``) viram ``[^/]+``.
    """
    urls = Path(modulo, 'urls.py')
    if not urls.exists():
        return {}
    arvore = ast.parse(urls.read_text(encoding='utf-8'), filename=str(urls))
    declaradas = {}
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ('path', 're_path')):
            continue
        padroes = _literais(no)
        if padroes:
            rota = f'/{modulo}/{padroes[0]}'
            declaradas[rota] = re.compile('^' + RE_PARAMETRO.sub('[^/]+', re.escape(rota).replace('\\<', '<').replace('\\>', '>')) + '$')
    return declaradas


def urls_nos_testes(modulo: str) -> set[str]:
    """Toda string literal iniciada por ``/`` nos arquivos de teste do módulo.

    Só ``test_*.py``: varrer o ``conftest.py`` faria a chave de ``ROTAS_DISPENSADAS`` contar
    como rota visitada, e toda dispensa viraria cobertura fantasma.
    """
    visitadas = set()
    for arquivo in sorted(Path(modulo, 'tests', 'e2e').glob('test_*.py')):
        arvore = ast.parse(arquivo.read_text(encoding='utf-8'), filename=str(arquivo))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value.startswith('/'):
                visitadas.add(no.value)
    return visitadas


def relatar_rotas(modulo: str) -> int:
    """Gate do modo 2 (módulo sem `.feature`): cobertura de rota, com dispensa por motivo."""
    declaradas = rotas_do_modulo(modulo)
    visitadas = urls_nos_testes(modulo)
    literal = _dict_do_conftest(modulo, 'ROTAS_DISPENSADAS')
    dispensadas = (
        {chave.value: valor.value for chave, valor in zip(literal.keys, literal.values, strict=True) if isinstance(chave, ast.Constant)}
        if literal
        else {}
    )

    descobertas = []
    for rota, padrao in sorted(declaradas.items()):
        if rota in dispensadas or any(padrao.match(visitada) for visitada in visitadas):
            continue
        descobertas.append(rota)

    linhas = [
        f'{modulo}: {len(declaradas)} rotas em urls.py',
        f'  cobertas:    {len(declaradas) - len(descobertas) - len(dispensadas)}',
        f'  dispensadas: {len(dispensadas)}',
        f'  descobertas: {len(descobertas)}',
    ]
    linhas += [f'    SEM TESTE  {rota}' for rota in descobertas]
    _emitir(linhas)
    return 1 if descobertas else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('modulo', help='diretório do app (ex.: eventos)')
    parser.add_argument('--junitxml', help='relatório junit do pytest; sem ele só o mapeamento é validado')
    parser.add_argument('--rotas', action='store_true', help='modo 2: cobre rotas de urls.py em vez de cenários (módulo sem .feature)')
    argumentos = parser.parse_args()
    if argumentos.rotas:
        return relatar_rotas(argumentos.modulo)
    if not Path(argumentos.modulo, 'features').is_dir():
        sys.stderr.write(f'{argumentos.modulo}: sem diretório features/ — use --rotas (não há cenário a comparar)\n')
        return 0
    return relatar(argumentos.modulo, argumentos.junitxml)


if __name__ == '__main__':
    raise SystemExit(main())
