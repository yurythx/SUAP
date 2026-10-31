"""Fase ``aplicar`` do deduplicar_pessoas: grava a higiene e mescla os grupos do plano, em lotes.

Set-based: por lote, um ``UPDATE … FROM dedup_mapa`` por referência. Antes de apagar as perdedoras,
o Collector confirma que nada além da própria PF/Pessoa seria apagado.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import batched, groupby
from operator import itemgetter
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.backends.utils import CursorWrapper
from django.db.models import Case, Exists, OuterRef, Value, When
from django.db.models.deletion import Collector
from django.utils import timezone

from rh.deduplicacao.campos import campos_mesclaveis, resolver_campos
from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    digitos,
    documento_original,
    documento_sintetico,
    sintetico_atual,
    formatar_cpf,
    formatar_passaporte,
    passaporte_valido,
)
from rh.deduplicacao.entrada import chave_prioridade, nascimento_diverge
from rh.deduplicacao.orfas import apagar_planejadas, modelos_alheios
from rh.deduplicacao.plano import Pessoa as Membro
from rh.deduplicacao.plano import referencia_de_nascimento
from rh.deduplicacao.referencias import Referencia, ReferenciaGenerica, referencias, referencias_genericas
from rh.models import DeduplicacaoPessoa as D
from rh.models import Pessoa, PessoaFisica, PessoaInfoComplementar

ORDEM_HIGIENE = [D.CPF_ANULADO, D.PAIS_PREENCHIDO, D.PASSAPORTE_PREENCHIDO, D.PASSAPORTE_ANULADO, D.SEPARADA, D.SINTETICO]
BLOCO_DE_HIGIENE = 2000


class ReferenciaRemanescente(Exception):
    """O DELETE da perdedora apagaria algo além da própria PF/Pessoa."""


class PlanoDesatualizado(Exception):
    """O plano não vale mais para o grupo (PF apagada, documento ou nascimento mudou): falha só o grupo, não o comando."""

    def __init__(self, motivo: str) -> None:
        super().__init__(f'{motivo}; rode planejar de novo')


ERROS_DO_GRUPO = (DatabaseError, ReferenciaRemanescente, ValidationError, PlanoDesatualizado)


def aplicar(lote: int = 1000) -> dict[str, int]:
    higiene = _aplicar_higiene()
    # fora da transação da higiene (um DELETE só, transação própria): ela segura o select_for_update das PFs, e esta limpeza
    # ordena a tabela inteira; é cache reconsultável, e a falha aqui não desfaz a higiene auditada. Antes dos lotes: a repetição
    # que só nasce ao juntar perdedora e sobrevivente continua com a mescla.
    with connection.cursor() as cursor:
        _manter_info_complementar_recente(cursor, toda_a_tabela=True)
    refs, genericas = referencias(), referencias_genericas()
    mescladas = erros = 0
    for grupos in _fatias(_grupos_pendentes(), lote):
        try:
            with transaction.atomic():
                _mesclar(grupos, refs, genericas)
            mescladas += len(grupos)
        except ERROS_DO_GRUPO:
            ok, falhas = _mesclar_um_a_um(grupos, refs, genericas)
            mescladas, erros = mescladas + ok, erros + falhas
    apagadas = apagar_planejadas(refs, genericas)  # depois das mesclas: a perdedora some com elas, e a referência reapontada já conta
    with transaction.atomic(), connection.cursor() as cursor:
        contatos = _remover_contatos_repetidos(cursor)
    return {
        'higiene': higiene,
        'mescladas': mescladas,
        'erros': erros,
        'apagadas': apagadas,
        'busca': _atualizar_busca_do_passaporte(),
        'contatos': contatos,
    }


# Iguais quando estas expressões coincidem; fica a primeira pela ordem. Telefone: os dígitos do número, ramal e observação.
# Endereço: todos os campos (o que veio pelo formulário do SUAP fica). Contato diferente não é repetido: fica.
CONTATOS_REPETIDOS = {
    'comum_pessoatelefone': (
        "regexp_replace(coalesce(numero, ''), '\\D', '', 'g'), coalesce(ramal, ''), coalesce(observacao, '')",
        'id',
    ),
    'comum_pessoaendereco': (
        "municipio_id, upper(trim(coalesce(logradouro, ''))), upper(trim(coalesce(numero, ''))), upper(trim(coalesce(complemento, ''))), "
        "upper(trim(coalesce(bairro, ''))), regexp_replace(coalesce(cep, ''), '\\D', '', 'g')",
        'via_form_suap DESC, id',
    ),
}


def _remover_contatos_repetidos(cursor: CursorWrapper) -> int:
    """Apaga o telefone e o endereço repetidos de cada pessoa física; devolve quantos.

    A mescla reaponta os contatos de todas as cópias para a sobrevivente: cada cópia trazia os seus (um servidor do suap_dev
    ficou com 91 telefones, 88 do mesmo número). A tabela inteira, como a ``PessoaInfoComplementar``: pega também as já mescladas.
    """
    total = 0
    for tabela, (iguais, ordem) in CONTATOS_REPETIDOS.items():
        cursor.execute(
            f'DELETE FROM {tabela} t USING (SELECT id, row_number() OVER (PARTITION BY pessoa_id, {iguais} ORDER BY {ordem}) AS n '
            f'FROM {tabela} WHERE pessoa_id IN (SELECT pessoa_ptr_id FROM pessoa_fisica)) r WHERE t.id = r.id AND r.n > 1'
        )
        total += cursor.rowcount
    return total


def _atualizar_busca_do_passaporte() -> int:
    """Recalcula a busca de quem tem passaporte, que desde a 3.21.0 inclui ``ARG-AB123456``; antes, só o ``save()`` a recalculava.

    Depois das mesclas: os usernames já são os dos vínculos reapontados. Devolve quantas pessoas mudaram.
    """
    pessoas = list(PessoaFisica.objects.filter(passaporte__isnull=False).select_related('pais_origem'))
    usernames = _usernames([pessoa.pk for pessoa in pessoas])
    alteradas = []
    for pessoa in pessoas:
        busca = pessoa._cortar_busca(pessoa._get_search_fields_optimized_content_to_save(usernames[pessoa.pk]))
        if busca != pessoa.search_fields_optimized:
            pessoa.search_fields_optimized = busca
            alteradas.append(pessoa)
    PessoaFisica.objects.bulk_update(alteradas, ['search_fields_optimized'], batch_size=1000)
    return len(alteradas)


def _mesclar_um_a_um(grupos: dict[int, list[int]], refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> tuple[int, int]:
    ok = falhas = 0
    for sobrevivente, perdedoras in grupos.items():
        try:
            with transaction.atomic():
                _mesclar({sobrevivente: perdedoras}, refs, genericas)
            ok += 1
        except ERROS_DO_GRUPO as erro:
            # ERRO fica com aplicado_em NULL de propósito: a trava da Release 2 conta pendentes, e um novo planejar a descarta e refaz o plano.
            D.objects.create(pf_id=sobrevivente, sobrevivente_id=sobrevivente, acao=D.ERRO, motivo=_motivo(erro))
            falhas += 1
    return ok, falhas


def _motivo(erro: Exception) -> str:
    return str(erro)[:2000]  # só PlanoDesatualizado manda replanejar: a mensagem vem da própria exceção


def _aplicar_higiene() -> int:
    from comum.models import Pais

    isos = dict(Pais.objects.values_list('pk', 'iso_alfa3'))
    total = 0
    with transaction.atomic():
        # na ordem: a linha que falha deixa a PF como estava, e as seguintes dela (ex.: o sintético) também falham
        for acao in ORDEM_HIGIENE:
            pendentes = D.objects.filter(acao=acao, aplicado_em__isnull=True)
            for bloco in batched(pendentes.iterator(chunk_size=BLOCO_DE_HIGIENE), BLOCO_DE_HIGIENE, strict=False):
                total += _aplicar_bloco_de_higiene(acao, bloco, isos)
            pendentes.update(aplicado_em=timezone.now())  # a linha recusada virou ERRO e já não casa o filtro
        normalizar_documentos()
    return total


def _aplicar_bloco_de_higiene(acao: str, linhas: Sequence[D], isos: dict[int, str]) -> int:
    """Aplica as linhas cuja premissa do plano ainda vale; as outras viram ERRO pendente (o planejar as refaz).

    Uma leitura travada das PFs do bloco e uma gravação por bloco. As linhas são conferidas em ordem sobre os valores lidos,
    atualizados a cada linha aplicada: duas linhas da mesma PF (o planejar não as gera numa ação) veriam o mesmo que linha a linha.
    """
    pks = sorted({linha.pf_id for linha in linhas})
    travadas = PessoaFisica.objects.select_for_update().filter(pk__in=pks).order_by('pk').values('pk', 'cpf', 'passaporte', 'pais_origem_id')
    atuais = {atual.pop('pk'): atual for atual in travadas}
    recusadas, alteracoes = [], []
    for linha in linhas:
        atual = atuais.get(linha.pf_id)
        if atual is None or not PREMISSAS_DE_HIGIENE[acao](linha, atual, isos):
            recusadas.append(linha.pk)
            continue
        alteracao = _alteracao_de_higiene(linha)
        atual.update(alteracao)
        alteracoes.append((tuple(alteracao), [*alteracao.values(), linha.pf_id]))
    _atualizar_pessoas_fisicas(alteracoes)
    if acao in (D.CPF_ANULADO, D.SEPARADA):  # a busca do vínculo leva o CPF: quem o perdeu não pode mais ser achado por ele
        _atualizar_busca_dos_vinculos(sorted({linha.pf_id for linha in linhas if linha.pk not in recusadas}))
    if recusadas:
        D.objects.filter(pk__in=recusadas).update(acao=D.ERRO, motivo=f'plano desatualizado ({acao}); rode planejar de novo')
    return len(linhas) - len(recusadas)


def _atualizar_pessoas_fisicas(alteracoes: Iterable[tuple[tuple[str, ...], list[Any]]]) -> None:
    """``UPDATE pessoa_fisica`` por ``executemany``: cada item é (campos, [valores..., pk]); a ordem é mantida.

    Só campos da própria tabela de PessoaFisica (não da Pessoa): é o caso dos documentos e do país.
    """
    meta, q = PessoaFisica._meta, connection.ops.quote_name
    with connection.cursor() as cursor:
        for campos, itens in groupby(alteracoes, key=itemgetter(0)):
            atribuicoes = ', '.join(f'{q(meta.get_field(campo).column)} = %s' for campo in campos)
            cursor.executemany(f'UPDATE {q(meta.db_table)} SET {atribuicoes} WHERE {q(meta.pk.column)} = %s', [valores for _, valores in itens])


def _chave_atual(atual: dict[str, Any], isos: dict[int, str]) -> str | None:
    """A chave da PF como o planejar a calcula: CPF válido, senão passaporte válido + ISO do país."""
    if cpf_valido(atual['cpf']):
        return formatar_cpf(atual['cpf'])
    passaporte = atual['passaporte'] if passaporte_valido(atual['passaporte']) else None
    return chave_passaporte(passaporte, isos.get(atual['pais_origem_id']))


Premissa = Callable[[D, dict[str, Any], dict[int, str]], bool]
# o valor que o planejar viu: sem isso, um plano velho anula o CPF que alguém corrigiu depois
PREMISSAS_DE_HIGIENE: dict[str, Premissa] = {
    D.CPF_ANULADO: lambda linha, atual, _: formatar_cpf(atual['cpf']) == formatar_cpf(linha.valor_original),
    D.PASSAPORTE_ANULADO: lambda linha, atual, _: formatar_passaporte(atual['passaporte']) == linha.valor_original,
    D.PASSAPORTE_PREENCHIDO: lambda linha, atual, _: not passaporte_valido(atual['passaporte']),
    D.PAIS_PREENCHIDO: lambda linha, atual, _: atual['pais_origem_id'] is None and not cpf_valido(atual['cpf']),
    D.SEPARADA: lambda linha, atual, isos: _chave_atual(atual, isos) == linha.valor_original,
    D.SINTETICO: lambda linha, atual, isos: not digitos(atual['cpf']) and _chave_atual(atual, isos) is None,
}


def _alteracao_de_higiene(linha: D) -> dict[str, str | int | None]:
    if linha.acao == D.CPF_ANULADO:
        # junto, não só na normalização: na Release 2 a CHECK "sem CPF exige país" não é deferível
        return {'cpf': None, 'documento_identificador': documento_sintetico(linha.pf_id, cpf_invalido=linha.valor_original)}
    if linha.acao == D.PAIS_PREENCHIDO:
        return {'pais_origem_id': int(linha.documento)}
    if linha.acao == D.PASSAPORTE_ANULADO:
        return {'passaporte': None}
    if linha.acao == D.PASSAPORTE_PREENCHIDO:
        return {'passaporte': linha.documento}
    if linha.acao == D.SEPARADA:
        return {linha.campo: None, 'documento_identificador': linha.documento}
    return {'documento_identificador': linha.documento}


def normalizar_documentos(pks: list[int] | None = None) -> None:
    """Formata CPF/passaporte e recalcula documento_identificador (mesma regra do PessoaFisica.save); ``pks``: só essas PFs."""
    from comum.models import Pais

    isos = dict(Pais.objects.values_list('pk', 'iso_alfa3'))
    campos = ('cpf', 'passaporte', 'documento_identificador')
    alteradas = []
    linhas = PessoaFisica.objects.values_list('pk', 'cpf', 'passaporte', 'pais_origem_id', 'documento_identificador')
    if pks is not None:
        linhas = linhas.filter(pk__in=pks)
    for pk, cpf, passaporte, pais_id, documento in linhas.iterator(chunk_size=5000):
        novo_cpf, novo_passaporte = formatar_cpf(cpf), formatar_passaporte(passaporte)
        chave = novo_cpf or chave_passaporte(novo_passaporte, isos.get(pais_id))
        novo_documento = chave or sintetico_atual(pk, documento, novo_passaporte, pais_id is not None)
        if (novo_cpf, novo_passaporte, novo_documento) != (cpf, passaporte, documento):
            alteradas.append((campos, [novo_cpf, novo_passaporte, novo_documento, pk]))
    _atualizar_pessoas_fisicas(alteradas)  # sem o CASE do bulk_update, que pesava com centenas de milhares de linhas


def _grupos_pendentes() -> dict[int, list[int]]:
    grupos: dict[int, list[int]] = defaultdict(list)
    for pf_id, sobrevivente in D.objects.filter(acao=D.MESCLADA, aplicado_em__isnull=True).values_list('pf_id', 'sobrevivente_id'):
        grupos[sobrevivente].append(pf_id)
    return grupos


def _fatias(grupos: dict[int, list[int]], tamanho: int) -> Iterator[dict[int, list[int]]]:
    itens = list(grupos.items())
    for inicio in range(0, len(itens), tamanho):
        yield dict(itens[inicio : inicio + tamanho])


def _mesclar(grupos: dict[int, list[int]], refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> None:
    pares = [(perdedora, sobrevivente) for sobrevivente, perdedoras in grupos.items() for perdedora in perdedoras]
    _conferir_plano([*grupos, *(perdedora for perdedora, _ in pares)])
    _conferir_identidade(grupos)
    executar_mescla(grupos, refs, genericas)
    D.objects.filter(sobrevivente_id__in=list(grupos), acao__in=[D.MESCLADA, D.CAMPO_DESCARTADO], aplicado_em__isnull=True).update(
        aplicado_em=timezone.now()
    )


def executar_mescla(grupos: dict[int, list[int]], refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> None:
    """Reaponta as referências das perdedoras para o sobrevivente, preenche os campos vazios dele e apaga as perdedoras; sem auditoria."""
    pares = [(perdedora, sobrevivente) for sobrevivente, perdedoras in grupos.items() for perdedora in perdedoras]
    with connection.cursor() as cursor:
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')  # FKs deferidas falham aqui, não no COMMIT
        cursor.execute('DROP TABLE IF EXISTS pg_temp.dedup_mapa')
        cursor.execute('CREATE TEMP TABLE dedup_mapa (perdedora integer PRIMARY KEY, sobrevivente integer NOT NULL) ON COMMIT DROP')
        cursor.executemany('INSERT INTO dedup_mapa VALUES (%s, %s)', pares)
        cursor.execute('ANALYZE dedup_mapa')  # tabela temporária nunca passa pelo autovacuum; sem estatística, os joins com tabelas grandes degeneram
        _manter_info_complementar_recente(cursor)
        for ref in refs:
            _reapontar(cursor, ref)
        tipos = [ContentType.objects.get_for_model(PessoaFisica).pk, ContentType.objects.get_for_model(Pessoa).pk]
        for generica in genericas:
            _reapontar_generica(cursor, generica, tipos)
    _preencher_sobreviventes(grupos)
    _apagar_perdedoras([perdedora for perdedora, _ in pares])


def _conferir_plano(pks: list[int]) -> None:
    """Antes de qualquer SQL do lote: sem isso, a PF sumida vira KeyError no preenchimento ou erro de FK no reapontamento."""
    faltando = set(pks) - set(PessoaFisica.objects.filter(pk__in=pks).values_list('pk', flat=True))
    if faltando:
        raise PlanoDesatualizado(f'PF do plano não existe mais: {", ".join(map(str, sorted(faltando)))}')


def _conferir_identidade(grupos: dict[int, list[int]]) -> None:
    """Cada perdedora ainda tem o documento do sobrevivente e não tem nascimento divergente (a premissa do planejar).

    Lê com ``select_for_update`` em ordem de pk: ninguém troca o documento até o fim do lote, e dois lotes não se travam.
    """
    pks = sorted([*grupos, *(pk for perdedoras in grupos.values() for pk in perdedoras)])
    linhas = PessoaFisica.objects.com_prioridade().select_for_update(of=('self',)).filter(pk__in=pks).order_by('pk')
    membros = {pf.pk: (pf.documento_identificador, Membro(pf.pk, pf.cpf, pf.passaporte, pf.nascimento_data, chave_prioridade(pf))) for pf in linhas}
    for sobrevivente, perdedoras in grupos.items():
        documento, vencedora = membros[sobrevivente]
        referencia = referencia_de_nascimento([vencedora, *(membros[pk][1] for pk in perdedoras)], vencedora)
        for pk in perdedoras:
            if not _mesmo_documento(membros[pk][0], documento):
                raise PlanoDesatualizado(f'PF {pk}: documento mudou depois do planejar')
            if nascimento_diverge(referencia.nascimento, membros[pk][1].nascimento):
                raise PlanoDesatualizado(f'PF {pk}: nascimento mudou depois do planejar')


def _mesmo_documento(da_perdedora: str | None, do_sobrevivente: str | None) -> bool:
    """Igual, ou o mesmo documento original quando um dos dois é uma separada (CONFLITO-): as separadas unidas entre si, ou a
    que volta para a dona do documento, não têm o mesmo ``documento_identificador``."""
    if da_perdedora == do_sobrevivente:
        return True
    separada = any((documento or '').startswith('CONFLITO-') for documento in (da_perdedora, do_sobrevivente))
    return separada and documento_original(da_perdedora) == documento_original(do_sobrevivente)


def _manter_info_complementar_recente(cursor: CursorWrapper, toda_a_tabela: bool = False) -> None:
    """Uma linha por (pessoa, api_origem): a consulta mais recente (empate: maior pk). É cache reconsultável, sem auditoria.

    ``toda_a_tabela``: todas as pessoas (PF ou PJ), não só as do ``dedup_mapa`` do lote; a trava da Release 2 conta a tabela inteira.
    """
    meta, q = PessoaInfoComplementar._meta, connection.ops.quote_name
    tabela, pk = q(meta.db_table), q(meta.pk.column)
    pessoa, api, consulta = (q(meta.get_field(nome).column) for nome in ('pessoa', 'api_origem', 'data_hora_consulta'))
    dono, origem = f'i.{pessoa}', f'{tabela} i'
    if not toda_a_tabela:
        dono = f'COALESCE(m.sobrevivente, i.{pessoa})'
        origem += f' LEFT JOIN dedup_mapa m ON m.perdedora = i.{pessoa}'
        origem += f' WHERE i.{pessoa} IN (SELECT perdedora FROM dedup_mapa UNION SELECT sobrevivente FROM dedup_mapa)'
    cursor.execute(
        f"""DELETE FROM {tabela} x USING (
            SELECT i.{pk} AS id, ROW_NUMBER() OVER (PARTITION BY {dono}, i.{api} ORDER BY i.{consulta} DESC NULLS LAST, i.{pk} DESC) AS ordem
            FROM {origem}
        ) d WHERE x.{pk} = d.id AND d.ordem > 1"""
    )


def _reapontar(cursor: CursorWrapper, ref: Referencia) -> None:
    q = connection.ops.quote_name
    tabela, coluna, pk = q(ref.tabela), q(ref.coluna), q(ref.pk)
    for unicidade in ref.compostas:
        colunas = [f'r.{q(c)}' for c in unicidade if c != ref.coluna]
        outras = ', '.join(colunas)
        # o índice único trata NULL como distinto: linha com NULL nas outras colunas nunca colide e não pode ser apagada
        preenchidas = ' '.join(f'AND {c} IS NOT NULL' for c in colunas)
        cursor.execute(
            f"""DELETE FROM {tabela} x USING (
                SELECT r.{pk} AS id, ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(m.sobrevivente, r.{coluna}), {outras} ORDER BY (m.perdedora IS NULL) DESC, r.{pk}
                ) AS ordem
                FROM {tabela} r LEFT JOIN dedup_mapa m ON m.perdedora = r.{coluna}
                WHERE r.{coluna} IN (SELECT perdedora FROM dedup_mapa UNION SELECT sobrevivente FROM dedup_mapa) {preenchidas}
            ) d WHERE x.{pk} = d.id AND d.ordem > 1"""
        )
    cursor.execute(f'UPDATE {tabela} SET {coluna} = m.sobrevivente FROM dedup_mapa m WHERE {tabela}.{coluna} = m.perdedora')


def _reapontar_generica(cursor: CursorWrapper, ref: ReferenciaGenerica, tipos: list[int]) -> None:
    q = connection.ops.quote_name
    tabela, tipo, objeto = q(ref.tabela), q(ref.coluna_tipo), q(ref.coluna_id)
    cast = '::text' if ref.id_texto else ''
    cursor.execute(
        f'UPDATE {tabela} SET {objeto} = m.sobrevivente{cast} FROM dedup_mapa m '
        f'WHERE {tabela}.{tipo} = ANY(%s) AND {tabela}.{objeto} = m.perdedora{cast}',
        [tipos],
    )


# O que o PessoaFisica.save() deriva e a mescla pode mudar; os documentos não mudam (ver _preencher_sobrevivente).
CAMPOS_DERIVADOS = ('nome_registro', 'nome', 'nome_usual', 'search_fields_optimized')


def _preencher_sobreviventes(grupos: dict[int, list[int]]) -> None:
    """O efeito do ``PessoaFisica.save()`` em cada sobrevivente, com um número fixo de consultas por lote.

    ponytail: não chama ``reset_user_profiles()``: ele só limpa o cache em memória deste processo (``User.VINCULOS``/
    ``PESSOAS_FISICAS``), e quem guarda o cache velho são os servidores de aplicação e os workers, reiniciados depois do aplicar (runbook).
    """
    campos = campos_mesclaveis()
    pks = [*grupos, *(pk for perdedoras in grupos.values() for pk in perdedoras)]
    valores = {v['pk']: v for v in PessoaFisica.objects.filter(pk__in=pks).values('pk', *campos)}
    usernames = _usernames(list(grupos))
    alteradas, gravar = [], set()
    for pessoa in PessoaFisica.objects.filter(pk__in=list(grupos)).select_related('pais_origem'):  # o ISO entra na busca
        preenchimentos, _ = resolver_campos(valores[pessoa.pk], [valores[pk] for pk in grupos[pessoa.pk]])
        mudaram = _preencher_sobrevivente(pessoa, preenchimentos, usernames[pessoa.pk])
        if mudaram:
            alteradas.append(pessoa)
            gravar |= mudaram
    if alteradas:
        PessoaFisica.objects.bulk_update(alteradas, sorted(gravar))
    _recalcular_vinculos(list(grupos))
    _atualizar_busca_dos_vinculos(list(grupos))


def _atualizar_busca_dos_vinculos(pks: list[int]) -> None:
    """Recalcula a busca (``Vinculo.search``) dos vínculos das pessoas: o UPDATE em massa da PF não passa pelo ``save()`` do vínculo."""
    from comum.models import Vinculo

    campo = Vinculo._meta.get_field('search')
    vinculos = Vinculo.objects.filter(pessoa_id__in=pks).select_related('user', 'pessoa__pessoafisica', 'pessoa__pessoajuridica')
    for lote in batched(vinculos.iterator(chunk_size=1000), 1000, strict=False):
        alterados = []
        for vinculo in lote:
            busca = campo.pre_save(vinculo, add=False)
            if vinculo.search != busca:
                vinculo.search = busca
                alterados.append(vinculo)
        if alterados:
            Vinculo.objects.bulk_update(alterados, ['search'], batch_size=1000)


def _usernames(pks: list[int]) -> dict[int, list[str | None]]:
    """Os usernames dos vínculos de cada pessoa (os das perdedoras já reapontados), numa consulta só."""
    from comum.models import Vinculo

    usernames: dict[int, list[str | None]] = defaultdict(list)
    for pessoa_id, username in Vinculo._default_manager.filter(pessoa_id__in=pks).values_list('pessoa_id', 'user__username'):
        usernames[pessoa_id].append(username)
    return usernames


def _preencher_sobrevivente(pessoa: PessoaFisica, preenchimentos: dict[str, Any], usernames: list[str | None]) -> set[str]:
    """Aplica os preenchimentos e deriva nomes e busca como o ``save()``; devolve os campos que mudaram.

    Documentos: ``resolver_campos`` não preenche ``cpf``, ``passaporte`` (só auditado) nem ``documento_identificador``, e a
    higiene e a normalização já rodaram. O ``pais_origem`` preenchido não muda a chave: perdedora e sobrevivente têm o mesmo
    ``documento_identificador`` (``_conferir_identidade``), e o do passaporte já traz o país do sobrevivente.
    """
    antes = {campo: getattr(pessoa, campo) for campo in (*preenchimentos, *CAMPOS_DERIVADOS)}
    for campo, valor in preenchimentos.items():
        setattr(pessoa, campo, valor)
    pessoa._derivar_nomes()
    pessoa.search_fields_optimized = pessoa._cortar_busca(pessoa._get_search_fields_optimized_content_to_save(usernames))
    return {campo for campo, valor in antes.items() if getattr(pessoa, campo) != valor}


def _recalcular_vinculos(pks: list[int]) -> None:
    """``eh_servidor``/``eh_aluno``/``eh_prestador`` em SQL e ``eh_usuarioexterno`` pelo prestador, como no ``PessoaFisica.save()``."""
    from comum.models import PrestadorServico
    from rh.models import Servidor

    eh_aluno: Exists | bool = False
    if 'edu' in settings.INSTALLED_APPS:
        from edu.models import Aluno

        eh_aluno = Exists(Aluno._default_manager.filter(pessoa_fisica=OuterRef('pk')))
    PessoaFisica.objects.filter(pk__in=pks).update(
        eh_servidor=Exists(Servidor._default_manager.filter(pessoa_fisica=OuterRef('pk'))),
        eh_aluno=eh_aluno,
        eh_prestador=Exists(PrestadorServico.objects.filter(pessoa_fisica=OuterRef('pk'))),
        eh_usuarioexterno=Case(When(pk__in=_usuarios_externos(pks), then=Value(True)), default=Value(False)),
    )


def _usuarios_externos(pks: list[int]) -> list[int]:
    """As pessoas cujo prestador, o mesmo do ``.first()`` do ``save()``, não tem ocupação vigente."""
    from comum.models import PrestadorServico

    # select_related: o filtro do possui_ocupacao_ativa passa por AbstractFuncionario.__getattr__, que carregaria a PF de cada prestador
    prestadores = PrestadorServico.objects.filter(pessoa_fisica_id__in=pks).select_related('pessoa_fisica')
    primeiros: dict[int, Any] = {}
    for prestador in prestadores if prestadores.ordered else prestadores.order_by('pk'):
        primeiros.setdefault(prestador.pessoa_fisica_id, prestador)
    return [pk for pk, prestador in primeiros.items() if not prestador.possui_ocupacao_ativa()]


def _apagar_perdedoras(pks: list[int]) -> None:
    perdedoras = PessoaFisica.objects.filter(pk__in=pks)
    coletor = Collector(using=perdedoras.db)
    coletor.collect(perdedoras)
    alheios = modelos_alheios(coletor, {PessoaFisica, Pessoa})
    if alheios:
        raise ReferenciaRemanescente('O DELETE apagaria: ' + ', '.join(sorted(m._meta.label for m in alheios)))
    coletor.delete()  # o que a trava conferiu é o que se apaga, sem coletar de novo
