"""Leitura das planilhas de organograma e de pessoas da prefeitura.

Não grava nada. O comando ``importar_prefeitura`` usa estas funções e só então
cria setores e servidores.
"""

from __future__ import annotations

import csv
from pathlib import Path

SIGLA_RAIZ = 'PMR'
NOME_RAIZ = 'Prefeitura Municipal de Rondonópolis'
LIMITE_SIGLA = 15
LIMITE_NOME_SETOR = 100
LIMITE_LOGIN = 30

COLUNAS_UNIDADE = {
    'sigla': '2-siglaUnidade',
    'nome': '3-descricaoUnidade',
    'superior': '4-superiorNaHierarquia',
    'email': '5-emailUnidade',
    'orgao': '1-orgaoUnidade',
    'telefone': '14-telefoneUnidade',
}
COLUNAS_USUARIO = {
    'login': '2.sigla',
    'nome': '3.nome',
    'cpf': '5.cpf',
    'email': '6.emailInstitucional',
    'setor': '7.unidadePrimeiraPermissao',
    'perfil': '8.perfilPrimeiraPermissao',
}


def digitos(valor: str | None) -> str:
    return ''.join(caractere for caractere in (valor or '') if caractere.isdigit())


def formatar_cpf(valor: str | None) -> str:
    numeros = digitos(valor)
    if len(numeros) != 11:
        return (valor or '').strip()
    return f'{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}'


def cpf_valido(valor: str | None) -> bool:
    numeros = digitos(valor)
    if len(numeros) != 11 or len(set(numeros)) == 1:
        return False
    return _digito(numeros[:9]) == int(numeros[9]) and _digito(numeros[:10]) == int(numeros[10])


def _digito(base: str) -> int:
    soma = sum(int(base[indice]) * (len(base) + 1 - indice) for indice in range(len(base)))
    resto = (soma * 10) % 11
    return 0 if resto == 10 else resto


def ler_unidades(caminho: str) -> list[dict[str, str]]:
    return [_unidade(linha) for linha in _linhas(caminho)]


def ler_usuarios(caminho: str) -> list[dict[str, str]]:
    return [_usuario(linha) for linha in _linhas(caminho)]


def _linhas(caminho: str) -> list[dict[str, str]]:
    with Path(caminho).open(encoding='utf-8-sig', newline='') as arquivo:
        return list(csv.DictReader(arquivo))


def _unidade(linha: dict[str, str]) -> dict[str, str]:
    return {campo: (linha.get(coluna) or '').strip() for campo, coluna in COLUNAS_UNIDADE.items()}


def _usuario(linha: dict[str, str]) -> dict[str, str]:
    usuario = {campo: (linha.get(coluna) or '').strip() for campo, coluna in COLUNAS_USUARIO.items()}
    usuario['cpf'] = formatar_cpf(usuario['cpf'])
    return usuario


def validar(unidades: list[dict[str, str]], usuarios: list[dict[str, str]], sigla_raiz: str = SIGLA_RAIZ) -> list[str]:
    erros = _erros_de_unidade(unidades, sigla_raiz)
    erros.extend(_erros_de_usuario(usuarios, {item['sigla'] for item in unidades}))
    return erros


def _erros_de_unidade(unidades: list[dict[str, str]], sigla_raiz: str) -> list[str]:
    erros: list[str] = []
    siglas = [item['sigla'] for item in unidades]
    conhecidas = set(siglas)
    if sigla_raiz in conhecidas:
        erros.append(f'A sigla {sigla_raiz} é a raiz do órgão e não pode repetir uma unidade.')
    erros.extend(_duplicados('setor', siglas))
    for item in unidades:
        erros.extend(_limites_unidade(item, conhecidas))
        if _tem_ciclo(item['sigla'], {unidade['sigla']: unidade['superior'] for unidade in unidades}):
            erros.append(f'{item["sigla"]}: a hierarquia entra em ciclo.')
    return erros


def _limites_unidade(item: dict[str, str], conhecidas: set[str]) -> list[str]:
    erros: list[str] = []
    if not item['sigla'] or not item['nome']:
        erros.append('Unidade sem sigla ou sem nome.')
    if len(item['sigla']) > LIMITE_SIGLA:
        erros.append(f'{item["sigla"]}: sigla passa de {LIMITE_SIGLA} caracteres.')
    if len(item['nome']) > LIMITE_NOME_SETOR:
        erros.append(f'{item["sigla"]}: nome passa de {LIMITE_NOME_SETOR} caracteres.')
    if item['superior'] and item['superior'] not in conhecidas:
        erros.append(f'{item["sigla"]}: superior {item["superior"]} não está na planilha.')
    return erros


def _erros_de_usuario(usuarios: list[dict[str, str]], siglas: set[str]) -> list[str]:
    erros = _duplicados('login', [item['login'] for item in usuarios])
    erros.extend(_duplicados('CPF', [item['cpf'] for item in usuarios]))
    for item in usuarios:
        erros.extend(_limites_usuario(item, siglas))
    return erros


def _limites_usuario(item: dict[str, str], siglas: set[str]) -> list[str]:
    erros: list[str] = []
    if not item['login'] or not item['nome']:
        erros.append('Pessoa sem login ou sem nome.')
    if len(item['login']) > LIMITE_LOGIN:
        erros.append(f'{item["login"]}: login passa de {LIMITE_LOGIN} caracteres.')
    if not cpf_valido(item['cpf']):
        erros.append(f'{item["login"]}: CPF inválido.')
    if item['setor'] not in siglas:
        erros.append(f'{item["login"]}: setor {item["setor"]} não está na planilha.')
    if not item['perfil']:
        erros.append(f'{item["login"]}: sem perfil.')
    return erros


def _duplicados(rotulo: str, valores: list[str]) -> list[str]:
    vistos: set[str] = set()
    repetidos: set[str] = set()
    for valor in valores:
        if valor in vistos:
            repetidos.add(valor)
        vistos.add(valor)
    return [f'{rotulo} repetido: {valor}' for valor in sorted(repetidos)]


def _tem_ciclo(sigla: str, superiores: dict[str, str]) -> bool:
    visitados: set[str] = set()
    atual = sigla
    while atual:
        if atual in visitados:
            return True
        visitados.add(atual)
        atual = superiores.get(atual, '')
    return False


def ordenar_unidades(unidades: list[dict[str, str]]) -> list[dict[str, str]]:
    superiores = {item['sigla']: item['superior'] for item in unidades}

    def profundidade(sigla: str) -> int:
        pai = superiores.get(sigla, '')
        if not pai:
            return 1
        return profundidade(pai) + 1

    return sorted(unidades, key=lambda item: (profundidade(item['sigla']), item['sigla']))
