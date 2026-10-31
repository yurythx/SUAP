"""Resolução do aluno do SUAP a partir de uma linha do arquivo de matrículas da PNP.

A PNP não exporta um identificador do SUAP: a coluna ``matricula`` é dela própria e não
tem interseção com ``edu.Aluno.matricula``. O aluno é então derivado do CPF e, quando o
CPF sozinho não decide (a mesma pessoa costuma ter vários cursos), do curso e da unidade,
ambos comparados por similaridade porque a PNP e o SUAP nomeiam os cursos de formas
diferentes ("COSTUREIRO" contra "FIC+ em Costureiro(a) de Máquina Reta [PRONATEC]").
"""

import re
import unicodedata
from difflib import SequenceMatcher

from edu.models import Aluno, CursoCampus
from pnp.models import EstruturaPNP

LIMIAR_DE_SIMILARIDADE = 0.9


def normalizar(texto: str) -> str:
    """Normaliza um nome para comparação, ignorando acento, pontuação e caixa."""
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().upper()
    return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', texto).split())


def normalizar_curso(nome: str) -> str:
    """Normaliza o nome de um curso, removendo o programa entre colchetes e o prefixo FIC.

    O SUAP cadastra "FIC+ Agente Cultural [PRONATEC]" onde a PNP exporta "AGENTE CULTURAL";
    sem tirar esses adornos a similaridade cai abaixo do limiar em quase todo curso FIC.
    """
    texto = unicodedata.normalize('NFKD', str(nome or '')).encode('ascii', 'ignore').decode().upper()
    texto = re.sub(r'\[[^\]]*\]', ' ', texto)
    texto = re.sub(r'^\s*FIC\s*\+?\s*-?\s*(EM\s+)?', ' ', texto)
    return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', texto).split())


def so_digitos(valor: str) -> str:
    return re.sub(r'\D', '', str(valor or ''))


def get_cpf(valor: str) -> str:
    """Devolve o CPF só com dígitos, ou vazio se não for um CPF (a PNP usa -0000000000)."""
    digitos = so_digitos(valor)
    return digitos if len(digitos) == 11 and digitos != '0' * 11 else ''


def eh_nome_utilizavel(nome: str) -> bool:
    """Descarta os nomes que a PNP exporta como um registro inteiro colado com tabulações."""
    return '\t' not in str(nome or '')


def parecidos(alvo: str, opcoes: list[tuple[str, int]]) -> set[int]:
    """Devolve os ids cujo nome normalizado atinge o limiar de similaridade com o alvo."""
    if not alvo:
        return set()
    return {pk for nome, pk in opcoes if nome and SequenceMatcher(None, alvo, nome).ratio() >= LIMIAR_DE_SIMILARIDADE}


class IndiceDeAlunos:
    """Índices em memória usados na resolução, carregados uma vez por importação.

    Percorrer o arquivo consultando o banco linha a linha seria inviável: são centenas de
    milhares de linhas. As tabelas envolvidas cabem em memória, então são carregadas de uma
    vez; só a lista de alunos por curso é carregada sob demanda, por ser usada em poucas linhas.
    """

    def __init__(self) -> None:
        self.uo_por_estrutura = dict(EstruturaPNP.objects.filter(uo__isnull=False).values_list('codigo', 'uo_id'))
        self.estrutura_por_codigo = dict(EstruturaPNP.objects.values_list('codigo', 'id'))
        self.uo_do_curso = {}
        self.nomes_do_curso = {}
        self.cursos_da_uo = {}
        for pk, descricao, historico, uo_id in CursoCampus.objects.values_list('id', 'descricao', 'descricao_historico', 'diretoria__setor__uo_id'):
            nomes = {normalizar_curso(descricao), normalizar_curso(historico)} - {''}
            self.uo_do_curso[pk] = uo_id
            self.nomes_do_curso[pk] = nomes
            self.cursos_da_uo.setdefault(uo_id, []).extend((nome, pk) for nome in nomes)
        self.alunos_por_cpf = {}
        for pk, cpf, curso_id in Aluno.objects.values_list('id', 'pessoa_fisica__cpf', 'curso_campus_id'):
            chave = get_cpf(cpf)
            if chave:
                self.alunos_por_cpf.setdefault(chave, []).append((pk, curso_id))
        self.ja_vinculados = set(Aluno.objects.filter(matriculapnp__isnull=False).values_list('id', flat=True))
        self._alunos_do_curso = {}
        self._curso_da_unidade = {}

    def get_alunos_do_curso(self, curso_id: int) -> list[tuple[str, int]]:
        if curso_id not in self._alunos_do_curso:
            valores = Aluno.objects.filter(curso_campus_id=curso_id).values_list('pessoa_fisica__nome', 'id')
            self._alunos_do_curso[curso_id] = [(normalizar(nome), pk) for nome, pk in valores]
        return self._alunos_do_curso[curso_id]

    def get_curso_da_unidade(self, uo_id: int | None, curso: str) -> int | None:
        """Localiza o CursoCampus da unidade cujo nome casa com o informado pela PNP.

        Varrer o catálogo do campus por similaridade é caro, e o arquivo repete os mesmos
        pares unidade/curso milhares de vezes, então o resultado é memoizado.
        """
        if not uo_id:
            return None
        alvo = normalizar_curso(curso)
        if (uo_id, alvo) not in self._curso_da_unidade:
            catalogo = self.cursos_da_uo.get(uo_id, [])
            exatos = {pk for nome, pk in catalogo if nome == alvo}
            encontrados = exatos or parecidos(alvo, catalogo)
            self._curso_da_unidade[uo_id, alvo] = encontrados.pop() if len(encontrados) == 1 else None
        return self._curso_da_unidade[uo_id, alvo]


def filtrar_por_unidade(candidatos: list[tuple[int, int]], uo_id: int | None, indice: IndiceDeAlunos) -> list[tuple[int, int]]:
    """Restringe os candidatos aos que estudam na unidade informada, se algum estudar."""
    if not uo_id:
        return candidatos
    da_unidade = [c for c in candidatos if indice.uo_do_curso.get(c[1]) == uo_id]
    return da_unidade or candidatos


def filtrar_por_curso(candidatos: list[tuple[int, int]], curso: str, indice: IndiceDeAlunos) -> list[tuple[int, int]]:
    """Restringe os candidatos aos que cursam o curso informado, comparado por similaridade."""
    alvo = normalizar_curso(curso)
    exatos = [c for c in candidatos if alvo in indice.nomes_do_curso.get(c[1], ())]
    if exatos:
        return exatos
    return [
        c
        for c in candidatos
        if any(SequenceMatcher(None, alvo, nome).ratio() >= LIMIAR_DE_SIMILARIDADE for nome in indice.nomes_do_curso.get(c[1], ()))
    ]


def resolver_por_cpf(cpf: str, curso: str, uo_id: int | None, indice: IndiceDeAlunos) -> int | None:
    """Resolve o aluno pelo CPF, desempatando por unidade e curso quando há mais de um."""
    candidatos = indice.alunos_por_cpf.get(cpf, [])
    if len(candidatos) == 1:
        return candidatos[0][0]
    if not candidatos:
        return None
    candidatos = filtrar_por_unidade(candidatos, uo_id, indice)
    if len(candidatos) > 1:
        candidatos = filtrar_por_curso(candidatos, curso, indice)
    return candidatos[0][0] if len(candidatos) == 1 else None


def resolver_por_nome(nome: str, curso: str, uo_id: int | None, indice: IndiceDeAlunos) -> int | None:
    """Resolve o aluno pelo nome dentro do curso da unidade, usado quando o CPF não decide."""
    if not eh_nome_utilizavel(nome):
        return None
    curso_id = indice.get_curso_da_unidade(uo_id, curso)
    if not curso_id:
        return None
    encontrados = parecidos(normalizar(nome), indice.get_alunos_do_curso(curso_id))
    return encontrados.pop() if len(encontrados) == 1 else None


def resolver_aluno(linha: dict, indice: IndiceDeAlunos) -> int | None:
    """Resolve o id do aluno de uma linha da PNP, ou ``None`` quando não é possível decidir.

    O nome só é usado quando o CPF não chega a candidato algum. Se o CPF chegou a candidatos
    mas o curso não desempatou, buscar pelo nome não ajudaria — os candidatos são a mesma
    pessoa, e o nome casaria com todos.
    """
    uo_id = indice.uo_por_estrutura.get(linha['codigo_estrutura'])
    cpf = get_cpf(linha['cpf'])
    candidatos = indice.alunos_por_cpf.get(cpf, []) if cpf else []
    if candidatos:
        aluno_id = resolver_por_cpf(cpf, linha['curso'], uo_id, indice)
    else:
        aluno_id = resolver_por_nome(linha['nome'], linha['curso'], uo_id, indice)
    return aluno_id if aluno_id not in indice.ja_vinculados else None
