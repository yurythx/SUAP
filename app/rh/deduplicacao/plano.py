"""Fase ``planejar`` do deduplicar_pessoas: higiene, grupos e separações, sem escrever em PessoaFisica.

Resultado em rh.DeduplicacaoPessoa. Regras: spec 2026-10-07-deduplicacao-pessoa-fisica-design.md, seções 1 e 2.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.management import CommandError
from django.db import connection, transaction

from comum.models import Pais
from rh.deduplicacao.campos import SEM_VALOR_NA_AUDITORIA, campos_mesclaveis, resolver_campos
from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    documento_original,
    documento_sintetico,
    eh_sintetico,
    formatar_cpf,
    formatar_passaporte,
    passaporte_valido,
)
from rh.deduplicacao.entrada import nascimento_diverge
from rh.deduplicacao.paises import id_do_pais_do_aluno, ids_por_iso, ids_por_nome
from rh.deduplicacao.orfas import apagaveis, candidatas
from rh.deduplicacao.referencias import Referencia, constraints_desconhecidas, referencias, referencias_genericas
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaFisica


@dataclass
class Pessoa:
    pk: int
    cpf: str | None
    passaporte: str | None
    nascimento: date | None
    prioridade: tuple[bool, bool, bool, int]
    documento: str | None = None  # documento_identificador atual (sintético já gravado é preservado)
    pais_id: int | None = None
    iso_pais: str | None = None  # ISO 3166-1 alfa-3 do país; '' (sem alfa-3) não forma chave
    cpf_invalido: str | None = None
    passaporte_em_conflito: str | None = None
    sobrevivente: int | None = None
    separacao: tuple[str, str, str] | None = None  # (campo, documento original, motivo)

    @property
    def chave(self) -> str | None:
        return self.cpf or chave_passaporte(self.passaporte, self.iso_pais)


# atomic: as leituras com .iterator() usam cursor de servidor; fora de transação ele é WITH HOLD e, atrás do pgbouncer em
# modo transaction, o FETCH seguinte pode cair noutra conexão ("cursor ... does not exist"). Dentro da transação, não.
@transaction.atomic
def planejar() -> dict[str, int]:
    refs = referencias()
    desconhecidas = constraints_desconhecidas(refs)
    if desconhecidas:
        raise CommandError(_recomendacao_fks_desconhecidas(desconhecidas))
    acoes: list[D] = []
    pessoas = _carregar_pessoas()
    passaportes_de_aluno, paises_de_aluno = _passaportes_de_aluno(), _paises_de_aluno()
    isos = dict(Pais.objects.values_list('pk', 'iso_alfa3'))
    for pessoa in pessoas:
        _higienizar(pessoa, passaportes_de_aluno.get(pessoa.pk), acoes)
        _inferir_pais(pessoa, paises_de_aluno.get(pessoa.pk), isos, acoes)
    grupos = _mesclas(pessoas)
    _unir_separadas(pessoas, grupos)
    _separar_colisoes_um_para_um(grupos, refs)
    pessoas = _separar_orfas(pessoas, grupos, refs, acoes)
    _emitir_mesclas_e_separacoes(pessoas, acoes)
    _emitir_conflitos_de_campo(grupos, acoes)
    _resolver_passaportes_repetidos(pessoas, acoes)
    _emitir_sinteticos(pessoas, acoes)
    with transaction.atomic():
        D.objects.filter(aplicado_em__isnull=True).delete()
        D.objects.bulk_create(acoes, batch_size=5000)
    return dict(Counter(acao.acao for acao in acoes))


def _recomendacao_fks_desconhecidas(desconhecidas: list[tuple[str, str, str]]) -> str:
    """Mensagem do aborto com o que o DBA faz, já com os nomes desta instituição (runbook, "Problemas comuns")."""
    tabelas = sorted({tabela for tabela, _, _ in desconhecidas})
    banco = connection.settings_dict['NAME']
    return '\n'.join(
        [
            'FKs para pessoa que o ORM não conhece (remova ou trate antes de deduplicar): '
            + ', '.join(f'{tabela}.{coluna}' for tabela, coluna, _ in desconhecidas),
            'Nenhuma migration do SUAP cria estas tabelas, e as FKs impedem apagar as pessoas duplicadas. Para cada tabela, o DBA escolhe:',
            '  1. Se nenhum sistema usa a tabela: arquive e apague.',
            f'     pg_dump -Fc {" ".join(f"-t {tabela}" for tabela in tabelas)} -f tabelas-fora-de-migration.dump {banco}',
            *(f'     DROP TABLE {tabela};' for tabela in tabelas),
            '  2. Se ainda usa: mantenha a tabela e tire só a FK (as linhas que apontavam para uma duplicata ficam com um id que deixa de existir).',
            *(f'     ALTER TABLE {tabela} DROP CONSTRAINT {constraint};' for tabela, _, constraint in desconhecidas),
            'O dump pode ter dado pessoal: guarde com acesso restrito. Depois, rode o planejar de novo. Roteiro: docs/operacoes/deduplicar-pessoas.md.',
        ]
    )


def _carregar_pessoas() -> list[Pessoa]:
    # ponytail: toda a tabela em memória (~555 mil PFs no IFRN ≈ 150 MB); paginar por documento se uma instituição estourar
    linhas = PessoaFisica.objects.com_prioridade().values_list(
        'pk', 'cpf', 'passaporte', 'nascimento_data', 'servidor_ativo', 'aluno_ativo', 'prestador_ativo', 'documento_identificador', 'pais_origem_id'
    )
    return [
        Pessoa(pk, cpf, passaporte, nasc, (srv, alu, pre, pk), documento, pais)
        for pk, cpf, passaporte, nasc, srv, alu, pre, documento, pais in linhas.iterator(chunk_size=5000)
    ]


def _passaportes_de_aluno() -> dict[int, str]:
    if 'edu' not in settings.INSTALLED_APPS:
        return {}
    from edu.models import Aluno

    return dict(Aluno.objects.exclude(passaporte__isnull=True).exclude(passaporte='').order_by('pk').values_list('pessoa_fisica_id', 'passaporte'))


def _paises_de_aluno() -> dict[int, int]:
    """pf_id → comum.Pais pelo aluno mais recente: brasileiro → Brasil; estrangeiro → edu.Pais pelo nome, senão pela sigla alfa-3."""
    if 'edu' not in settings.INSTALLED_APPS:
        return {}
    from edu.models import Aluno

    por_nome, por_iso = ids_por_nome(), ids_por_iso()
    brasil = por_nome.get('BRASIL')
    paises: dict[int, int | None] = {}
    alunos = Aluno.objects.order_by('pk').values_list('pessoa_fisica_id', 'nacionalidade', 'pais_origem__nome', 'pais_origem__sigla')
    for pf_id, nacionalidade, nome_pais, sigla in alunos.iterator(chunk_size=5000):
        # o aluno mais recente decide, mesmo sem país mapeável: não se recorre a um aluno mais antigo
        estrangeiro = not (nacionalidade or '').upper().startswith('BRASIL')
        paises[pf_id] = id_do_pais_do_aluno(nome_pais, sigla, por_nome, por_iso) if estrangeiro else brasil
    return {pf_id: pais for pf_id, pais in paises.items() if pais}


def _inferir_pais(pessoa: Pessoa, pais_do_aluno: int | None, isos: dict[int, str], acoes: list[D]) -> None:
    """Sem CPF, o país é obrigatório (CHECK da Release 2): infere do aluno quando falta."""
    if pessoa.pais_id is None and not pessoa.cpf and pais_do_aluno:
        acoes.append(D(pf_id=pessoa.pk, acao=D.PAIS_PREENCHIDO, campo='pais_origem', documento=str(pais_do_aluno)))
        pessoa.pais_id = pais_do_aluno
    pessoa.iso_pais = isos.get(pessoa.pais_id)


def _higienizar(pessoa: Pessoa, passaporte_do_aluno: str | None, acoes: list[D]) -> None:
    if pessoa.cpf and not cpf_valido(pessoa.cpf):
        acoes.append(D(pf_id=pessoa.pk, acao=D.CPF_ANULADO, campo='cpf', valor_original=pessoa.cpf))
        pessoa.cpf_invalido, pessoa.cpf = pessoa.cpf, None
    else:
        pessoa.cpf = formatar_cpf(pessoa.cpf)
    passaporte = formatar_passaporte(pessoa.passaporte)
    # PF separada (CONFLITO-) não recebe o passaporte do aluno: a separação vale até alguém corrigir o documento, e copiá-lo de
    # volta recriaria o par e separaria de novo a cada rodada (o planejar nunca convergiria)
    separada = (pessoa.documento or '').startswith('CONFLITO-')
    if not separada and not passaporte_valido(passaporte) and passaporte_valido(passaporte_do_aluno):
        do_aluno = formatar_passaporte(passaporte_do_aluno)
        acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_PREENCHIDO, campo='passaporte', documento=do_aluno, valor_original=passaporte or ''))
        passaporte = do_aluno
    if passaporte and not passaporte_valido(passaporte):
        acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_ANULADO, campo='passaporte', valor_original=passaporte))
        passaporte = None
    pessoa.passaporte = passaporte


def _mesclas(pessoas: list[Pessoa]) -> dict[int, list[Pessoa]]:
    """Agrupa por documento e decide sobrevivente/separadas; devolve {sobrevivente: perdedoras mescladas}.

    A CONFLITO- já gravada volta para a dona do documento original quando o nascimento não diverge (ex.: alguém corrigiu o
    nascimento errado que causou a separação). Ela nunca é a vencedora: a vencedora fica com o documento.
    """
    por_chave: dict[str, list[Pessoa]] = defaultdict(list)
    separadas: dict[str, list[Pessoa]] = defaultdict(list)
    for pessoa in pessoas:
        if pessoa.chave:
            por_chave[pessoa.chave].append(pessoa)
        elif original := _original_da_separada(pessoa):
            separadas[original].append(pessoa)
    grupos: dict[int, list[Pessoa]] = {}
    for chave, grupo in por_chave.items():
        if len(grupo) + len(separadas.get(chave, [])) > 1:
            _decidir_grupo(grupo, separadas.get(chave, []), grupos)
    return grupos


def _decidir_grupo(grupo: list[Pessoa], separadas: list[Pessoa], grupos: dict[int, list[Pessoa]]) -> None:
    """Separa do ``grupo`` (as PFs com o documento) quem diverge no nascimento e junta o resto, e as ``separadas`` compatíveis, na vencedora."""
    referencia = _referencia_do_grupo(grupo)
    mantidas = [p for p in grupo if not nascimento_diverge(referencia.nascimento, p.nascimento)]
    vencedora = max(mantidas, key=lambda p: p.prioridade)
    for pessoa in grupo:
        if pessoa is not vencedora and nascimento_diverge(referencia.nascimento, pessoa.nascimento):
            _separar(pessoa, f'nascimento {pessoa.nascimento} ≠ {referencia.nascimento} da PF {referencia.pk}')
    juntas = [p for p in (*mantidas, *separadas) if p is not vencedora and not nascimento_diverge(referencia.nascimento, p.nascimento)]
    for pessoa in juntas:
        pessoa.sobrevivente = vencedora.pk
    if juntas:
        grupos.setdefault(vencedora.pk, []).extend(juntas)


def _referencia_do_grupo(grupo: list[Pessoa]) -> Pessoa:
    """A PF cujo nascimento fica com o documento: o do servidor ativo (vem do SIAPE), senão o da maioria do grupo.

    Empate no tamanho, ou ninguém com nascimento: a regra de prioridade (servidor ativo > aluno ativo > prestador ativo > maior id).
    """
    com_nascimento = [p for p in grupo if p.nascimento]
    if not com_nascimento:
        return max(grupo, key=lambda p: p.prioridade)
    servidores_ativos = [p for p in com_nascimento if p.prioridade[0]]
    if servidores_ativos:
        return max(servidores_ativos, key=lambda p: p.prioridade)
    tamanho = Counter(p.nascimento for p in com_nascimento)
    return max(com_nascimento, key=lambda p: (tamanho[p.nascimento], p.prioridade))


def _unir_separadas(pessoas: list[Pessoa], grupos: dict[int, list[Pessoa]]) -> None:
    """Separadas de um mesmo documento original e mesmo nascimento são uma pessoa só: viram uma CONFLITO-, não uma por PF.

    Entram as separadas por nascimento nesta rodada e as CONFLITO- já gravadas que não voltaram para a dona do documento;
    não as separadas por colisão 1:1, que ainda não aconteceram.
    """
    por_original: dict[tuple[str, date | None], list[Pessoa]] = defaultdict(list)
    for pessoa in pessoas:
        original = None if pessoa.sobrevivente else _original_da_separada(pessoa)
        if original:
            por_original[(original, pessoa.nascimento)].append(pessoa)
    for separadas in (g for g in por_original.values() if len(g) > 1):
        sobrevivente = max(separadas, key=lambda p: p.prioridade)
        for pessoa in separadas:
            if pessoa is not sobrevivente:
                pessoa.sobrevivente = sobrevivente.pk
                grupos.setdefault(sobrevivente.pk, []).append(pessoa)


def _original_da_separada(pessoa: Pessoa) -> str | None:
    if pessoa.separacao:
        return pessoa.separacao[1]
    if not pessoa.chave and (pessoa.documento or '').startswith('CONFLITO-'):
        return documento_original(pessoa.documento)
    return None


def referencia_de_nascimento(grupo: list[Pessoa], vencedora: Pessoa) -> Pessoa:
    """A vencedora, ou, se ela não tem nascimento, a mais prioritária do grupo que tem."""
    if vencedora.nascimento:
        return vencedora
    return max((p for p in grupo if p.nascimento), key=lambda p: p.prioridade, default=vencedora)


def _separar(pessoa: Pessoa, motivo: str) -> None:
    campo = 'cpf' if pessoa.cpf else 'passaporte'
    pessoa.separacao = (campo, pessoa.chave, motivo)
    pessoa.sobrevivente = None
    setattr(pessoa, campo, None)


def _separar_colisoes_um_para_um(grupos: dict[int, list[Pessoa]], refs: list[Referencia]) -> None:
    for ref in (r for r in refs if r.um_para_um):
        membros = [pk for sobrevivente, perdedoras in grupos.items() for pk in (sobrevivente, *(p.pk for p in perdedoras))]
        q = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT DISTINCT {q(ref.coluna)} FROM {q(ref.tabela)} WHERE {q(ref.coluna)} = ANY(%s)', [membros])
            com_linha = {pk for (pk,) in cursor.fetchall()}
        for sobrevivente, perdedoras in list(grupos.items()):
            if sum(pk in com_linha for pk in (sobrevivente, *(p.pk for p in perdedoras))) > 1:
                for pessoa in perdedoras:
                    if not pessoa.chave:
                        pessoa.sobrevivente = None  # já separada (CONFLITO-, ou nesta rodada): só sai do grupo, sem separar de novo
                    else:
                        _separar(pessoa, f'unicidade em {ref.tabela}.{ref.coluna}')
                del grupos[sobrevivente]


def _separar_orfas(pessoas: list[Pessoa], grupos: dict[int, list[Pessoa]], refs: list[Referencia], acoes: list[D]) -> list[Pessoa]:
    """Marca para apagar a PF sem relacionamento e devolve as demais; a higiene dela sai do plano.

    Grupo com alguém relacionado mescla: a perdedora some na mescla, e a sobrevivente recebe as referências. Grupo todo sem
    relacionamento é apagado inteiro, sem mesclar: senão a sobrevivente só apareceria como órfã no próximo planejar.
    """
    sem_relacionamento = set(apagaveis(candidatas(refs, referencias_genericas())))
    for sobrevivente, perdedoras in list(grupos.items()):
        if {sobrevivente, *(perdedora.pk for perdedora in perdedoras)} <= sem_relacionamento:
            for perdedora in perdedoras:
                perdedora.sobrevivente = None
            del grupos[sobrevivente]
    membros = {*grupos, *(perdedora.pk for perdedoras in grupos.values() for perdedora in perdedoras)}
    orfas = sem_relacionamento - membros
    acoes[:] = [acao for acao in acoes if acao.pf_id not in orfas]
    acoes.extend(D(pf_id=pessoa.pk, acao=D.APAGADA, documento=pessoa.documento or '') for pessoa in pessoas if pessoa.pk in orfas)
    return [pessoa for pessoa in pessoas if pessoa.pk not in orfas]


def _emitir_mesclas_e_separacoes(pessoas: list[Pessoa], acoes: list[D]) -> None:
    for pessoa in pessoas:
        if pessoa.sobrevivente:
            documento = pessoa.chave or _original_da_separada(pessoa)  # a separada unida já não tem chave
            acoes.append(D(pf_id=pessoa.pk, sobrevivente_id=pessoa.sobrevivente, acao=D.MESCLADA, documento=documento))
        elif pessoa.separacao:
            campo, original, motivo = pessoa.separacao
            sintetico = documento_sintetico(pessoa.pk, conflito=original)
            acoes.append(D(pf_id=pessoa.pk, acao=D.SEPARADA, campo=campo, valor_original=original, documento=sintetico, motivo=motivo))


def _emitir_conflitos_de_campo(grupos: dict[int, list[Pessoa]], acoes: list[D]) -> None:
    campos = campos_mesclaveis()
    itens = list(grupos.items())
    for inicio in range(0, len(itens), 2000):
        fatia = itens[inicio : inicio + 2000]
        pks = [pk for sobrevivente, perdedoras in fatia for pk in (sobrevivente, *(p.pk for p in perdedoras))]
        valores = {v['pk']: v for v in PessoaFisica.objects.filter(pk__in=pks).values('pk', *campos)}
        for sobrevivente, perdedoras in fatia:
            _, descartes = resolver_campos(valores[sobrevivente], [valores[p.pk] for p in perdedoras])
            acoes.extend(_campo_descartado(pk, sobrevivente, campo, valor) for pk, campo, valor in descartes)


def _campo_descartado(pk: int, sobrevivente: int, campo: str, valor: object) -> D:
    if campo in SEM_VALOR_NA_AUDITORIA:
        return D(pf_id=pk, sobrevivente_id=sobrevivente, acao=D.CAMPO_DESCARTADO, campo=campo, motivo='valor omitido (biometria/senha)')
    return D(pf_id=pk, sobrevivente_id=sobrevivente, acao=D.CAMPO_DESCARTADO, campo=campo, valor_original=str(valor))


def _par_do_passaporte(pessoa: Pessoa) -> str | tuple[int, str] | None:
    """A chave do passaporte; no país sem ISO, o par (país, passaporte) da trava ``passaporte_repetido`` e da UNIQUE da Release 2."""
    if not pessoa.passaporte or pessoa.pais_id is None:
        return None
    return chave_passaporte(pessoa.passaporte, pessoa.iso_pais) or (pessoa.pais_id, pessoa.passaporte)


def _resolver_passaportes_repetidos(pessoas: list[Pessoa], acoes: list[D]) -> None:
    """Unicidade por (país, passaporte) entre as pessoas que sobram; passaporte sem país não é documento.

    O país sem ISO não forma documento (nada mescla por ele), mas o par repetido nele também é anulado na de menor
    prioridade: senão a trava ``passaporte_repetido`` não sairia nunca, já que país extinto não ganha ISO.
    """
    por_passaporte: dict[str | tuple[int, str], list[Pessoa]] = defaultdict(list)
    for pessoa in pessoas:
        par = _par_do_passaporte(pessoa)
        if par and not pessoa.sobrevivente:
            por_passaporte[par].append(pessoa)
    for repetidas in (g for g in por_passaporte.values() if len(g) > 1):
        mantida = max(repetidas, key=lambda p: p.prioridade)
        for pessoa in repetidas:
            if pessoa is not mantida:
                acoes.append(D(pf_id=pessoa.pk, acao=D.PASSAPORTE_ANULADO, campo='passaporte', valor_original=pessoa.passaporte))
                pessoa.passaporte_em_conflito = chave_passaporte(pessoa.passaporte, pessoa.iso_pais)
                pessoa.passaporte = None


def _emitir_sinteticos(pessoas: list[Pessoa], acoes: list[D]) -> None:
    for pessoa in pessoas:
        if pessoa.chave or pessoa.sobrevivente or pessoa.separacao or eh_sintetico(pessoa.documento):
            continue  # sintético já gravado sobrevive a um novo planejar (SEMDOC-/SEMPAIS- o aplicar recalcula na normalização)
        passaporte_sem_pais = pessoa.passaporte if pessoa.pais_id is None else None
        documento = documento_sintetico(
            pessoa.pk, conflito=pessoa.passaporte_em_conflito, cpf_invalido=pessoa.cpf_invalido, passaporte_sem_pais=passaporte_sem_pais
        )
        acoes.append(D(pf_id=pessoa.pk, acao=D.SINTETICO, documento=documento))
