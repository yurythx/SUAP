"""Pessoas físicas sem relacionamento: o ``planejar`` as marca, e o ``aplicar`` as apaga.

Contam como relacionamento as referências do catálogo (``referencias``/``referencias_genericas``), menos os dependentes
da própria pessoa: sem vínculo, servidor, aluno, prestador ou objeto genérico apontando para ela, a PF é lixo, e o DELETE
leva os dependentes junto (CASCADE). O vínculo da própria pessoa externa, sem usuário, também é dependente. O Collector confere que nada além deles seria apagado ou anulado.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import batched

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.db.models import Model, ProtectedError, QuerySet, RestrictedError
from django.db.models.deletion import Collector
from django.utils import timezone

from rh.deduplicacao.referencias import Referencia, ReferenciaGenerica
from rh.models import DeduplicacaoPessoa as D
from comum.models import Vinculo
from rh.models import Pessoa, PessoaExterna, PessoaFisica

DEPENDENTES_DA_PESSOA = (
    'comum.PessoaEndereco',
    'comum.PessoaTelefone',
    'comum.ContatoEmergencia',
    'rh.PessoaInfoComplementar',
    'rh.PessoaExterna',
    'rh.Biometria',
    'rh.BiometriaSolicitacao',
)
BLOCO = 1000
MOTIVO_MANTIDA = 'não apagada: ganhou relacionamento ou já não existia depois do planejar'


def _dependentes() -> list[type[Model]]:
    return [apps.get_model(label) for label in DEPENDENTES_DA_PESSOA]


def candidatas(refs: list[Referencia], genericas: list[ReferenciaGenerica], entre: Sequence[int] | None = None) -> set[int]:
    """As PFs (ou as de ``entre``) que nenhuma referência viva aponta, fora os dependentes da própria pessoa.

    O vínculo da própria pessoa externa, sem usuário, também é dependente (o ``save()`` da externa o cria); objeto genérico
    apontando para ele ou para a externa conta como relacionamento.
    """
    q = connection.ops.quote_name
    pk = f'pf.{q(PessoaFisica._meta.pk.column)}'
    dependentes = {modelo._meta.db_table for modelo in _dependentes()}
    condicoes = [_sem_referencia(r, pk) for r in refs if r.tabela not in dependentes]
    for g in genericas:
        condicoes.append(
            f'NOT EXISTS (SELECT 1 FROM {q(g.tabela)} x WHERE x.{q(g.coluna_tipo)} = ANY(%(tipos)s) '
            f'AND x.{q(g.coluna_id)} = {pk}{"::text" if g.id_texto else ""})'
        )
        if g.tabela != Vinculo._meta.db_table:  # o relacionamento do próprio vínculo aponta para a externa: é a dependência
            condicoes += [_sem_generica_para(g, modelo, campo, pk) for modelo, campo in ((Vinculo, 'pessoa'), (PessoaExterna, 'pessoa_fisica'))]
    if entre is not None:
        condicoes.append(f'{pk} = ANY(%(entre)s)')
    parametros = {
        'tipos': [ContentType.objects.get_for_model(PessoaFisica).pk, ContentType.objects.get_for_model(Pessoa).pk],
        'tipo_externa': _tipo_externa(),
        'tipo_vinculo': ContentType.objects.get_for_model(Vinculo).pk,
        'tipo_pessoaexterna': _tipo_externa(),
        'entre': list(entre or []),
    }
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {pk} FROM {q(PessoaFisica._meta.db_table)} pf WHERE {" AND ".join(condicoes) or "TRUE"}', parametros)
        sem_referencia = {linha[0] for linha in cursor.fetchall()}
    return sem_referencia - _com_dependente_referenciado(sem_referencia)


SQL_FKS_PARA = """
    SELECT c.conrelid::regclass::text, a.attname::text, c.confrelid::regclass::text
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.confrelid = ANY(%s::regclass[])
"""


def _com_dependente_referenciado(pks: set[int]) -> set[int]:
    """As de ``pks`` cujo vínculo ou pessoa externa outra tabela referencia (FK do banco).

    O Collector as recusaria de qualquer jeito, mas uma a uma: o vínculo tem centenas de FKs, e o bloco com uma só delas
    caía na conferência individual (na suap_dev, 6 mil de 18 mil PFs só com a externa). Aqui é uma consulta por FK.
    """
    if not pks:
        return set()
    q = connection.ops.quote_name
    colunas_da_pf = {
        Vinculo._meta.db_table: Vinculo._meta.get_field('pessoa').column,
        PessoaExterna._meta.db_table: PessoaExterna._meta.get_field('pessoa_fisica').column,
    }
    proprias = {modelo._meta.db_table for modelo in (PessoaFisica, Pessoa, Vinculo, *_dependentes())}
    referenciadas: set[int] = set()
    with connection.cursor() as cursor:
        cursor.execute(SQL_FKS_PARA, [list(colunas_da_pf)])
        fks = [(tabela.strip('"'), coluna, alvo.strip('"')) for tabela, coluna, alvo in cursor.fetchall()]
        for tabela, coluna, alvo in fks:
            if tabela in proprias:
                continue
            cursor.execute(
                f'SELECT DISTINCT d.{q(colunas_da_pf[alvo])} FROM {q(tabela)} x JOIN {q(alvo)} d ON x.{q(coluna)} = d.id '
                f'WHERE d.{q(colunas_da_pf[alvo])} = ANY(%s)',
                [list(pks)],
            )
            referenciadas |= {linha[0] for linha in cursor.fetchall()}
    return referenciadas


def _sem_referencia(ref: Referencia, pk: str) -> str:
    q = connection.ops.quote_name
    condicao = f'NOT EXISTS (SELECT 1 FROM {q(ref.tabela)} x WHERE x.{q(ref.coluna)} = {pk}'
    if (ref.tabela, ref.coluna) == (Vinculo._meta.db_table, Vinculo._meta.get_field('pessoa').column):
        tipo, usuario = (q(Vinculo._meta.get_field(campo).column) for campo in ('tipo_relacionamento', 'user'))
        condicao += f' AND NOT (x.{tipo} = %(tipo_externa)s AND x.{usuario} IS NULL)'
    return condicao + ')'


def _sem_generica_para(g: ReferenciaGenerica, modelo: type[Model], campo: str, pk: str) -> str:
    """Nenhum objeto genérico ``g`` aponta para a linha de ``modelo`` (vínculo ou externa) da PF."""
    q = connection.ops.quote_name
    alvo = f'd.{q(modelo._meta.pk.column)}{"::text" if g.id_texto else ""}'
    return (
        f'NOT EXISTS (SELECT 1 FROM {q(g.tabela)} x JOIN {q(modelo._meta.db_table)} d ON x.{q(g.coluna_id)} = {alvo} '
        f'WHERE x.{q(g.coluna_tipo)} = %(tipo_{modelo._meta.model_name})s AND d.{q(modelo._meta.get_field(campo).column)} = {pk})'
    )


def _tipo_externa() -> int:
    return ContentType.objects.get_for_model(PessoaExterna).pk


def apagaveis(pks: Iterable[int]) -> list[int]:
    """As de ``pks`` cujo DELETE só leva os dependentes; o bloco que falha é conferido uma a uma."""
    ok: list[int] = []
    for bloco in batched(sorted(pks), BLOCO, strict=False):
        ok += bloco if _coletor_limpo(bloco) else [pk for pk in bloco if _coletor_limpo([pk])]
    return ok


def apagar_planejadas(refs: list[Referencia], genericas: list[ReferenciaGenerica]) -> int:
    """Apaga as PFs marcadas pelo ``planejar`` que continuam sem relacionamento; devolve quantas."""
    pendentes = D.objects.filter(acao=D.APAGADA, aplicado_em__isnull=True)
    total = 0
    for bloco in batched(sorted(pendentes.values_list('pf_id', flat=True)), BLOCO, strict=False):
        with transaction.atomic():
            # ordem de pk, como no _conferir_identidade; sem of=, trava também a linha de pessoa: o vínculo novo espera
            travadas = list(PessoaFisica.objects.select_for_update().filter(pk__in=bloco).order_by('pk').values_list('pk', flat=True))
            apagadas = _apagar(sorted(candidatas(refs, genericas, entre=travadas)))
            agora = timezone.now()
            pendentes.filter(pf_id__in=apagadas).update(aplicado_em=agora)
            pendentes.filter(pf_id__in=bloco).exclude(pf_id__in=apagadas).update(aplicado_em=agora, motivo=MOTIVO_MANTIDA)
        total += len(apagadas)
    return total


def _apagar(pks: list[int]) -> list[int]:
    coletor = _coletor_limpo(pks)
    if coletor:
        coletor.delete()
        return pks
    apagadas = []
    for pk in pks:
        if coletor := _coletor_limpo([pk]):
            coletor.delete()
            apagadas.append(pk)
    return apagadas


def _coletor_limpo(pks: Sequence[int]) -> Collector | None:
    """O Collector das PFs, se o DELETE só levar PF, Pessoa, os dependentes e o vínculo da própria externa sem usuário; senão None."""
    coletor = Collector(using=PessoaFisica.objects.db)
    try:
        coletor.collect(PessoaFisica.objects.filter(pk__in=pks))
    except ProtectedError, RestrictedError:
        return None
    tipo_externa = _tipo_externa()
    if any(vinculo.user_id or vinculo.tipo_relacionamento_id != tipo_externa for vinculo in coletor.data.get(Vinculo, ())):
        return None
    return None if modelos_alheios(coletor, {PessoaFisica, Pessoa, Vinculo, *_dependentes()}) else coletor


def modelos_alheios(coletor: Collector, proprios: set[type[Model]]) -> set[type[Model]]:
    """Models, além de ``proprios``, com linhas que o DELETE apagaria (data, fast_deletes) ou anularia (field_updates).

    ``field_updates`` é ``{(campo, valor): [querysets]}``; o SET_NULL é preguiçoso (``lazy_sub_objs``) e entra mesmo sem linha,
    por isso cada entrada é conferida no banco.
    """
    alheios = {modelo for modelo, objetos in coletor.data.items() if objetos and modelo not in proprios}
    alheios |= {qs.model for qs in coletor.fast_deletes if qs.model not in proprios and qs.exists()}
    alheios |= {campo.model for (campo, _valor), lotes in coletor.field_updates.items() if any(_tem_linhas(lote) for lote in lotes)}
    return alheios


def _tem_linhas(objetos: QuerySet | Iterable[Model]) -> bool:
    return objetos.exists() if isinstance(objetos, QuerySet) else bool(list(objetos))
