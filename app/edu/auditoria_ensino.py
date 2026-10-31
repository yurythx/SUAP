from __future__ import annotations

import csv
import datetime
import io
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import regex
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Count, Q
from sentry_sdk import capture_exception

from comum.models import UsuarioGrupo
from djtools.utils import mask_cpf, retira_acentos, send_notification
from edu.models import (
    Aluno,
    AuditoriaEnsino,
    Cidade,
    CursoCampus,
    Diretoria,
    Modalidade,
    RegistroAuditoriaEnsino,
    RegistroDiferenca,
    SituacaoMatricula,
)

if TYPE_CHECKING:
    from rh.models import UnidadeOrganizacional

ID_INTERCAMBIO = 4
ANO_CORTE_PRONATEC_SISTEC = 2025
RE_NOME_INVALIDO = regex.compile(r"[^\p{L} '\-]")

SITUACOES_MAP: dict[tuple[int, ...], list[str]] = {
    (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO): ['CONCLUÍDA'],
    (
        SituacaoMatricula.CANCELADO,
        SituacaoMatricula.JUBILADO,
        SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
        SituacaoMatricula.FALECIDO,
        SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
        SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
        SituacaoMatricula.EVASAO,
        SituacaoMatricula.NAO_CONCLUIDO,
    ): ['ABANDONO', 'DESLIGADO'],
    (
        SituacaoMatricula.MATRICULADO,
        SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
        SituacaoMatricula.INTERCAMBIO,
        SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
        SituacaoMatricula.TRANCADO,
    ): ['EM_CURSO'],
    (
        SituacaoMatricula.CONCLUDENTE,
        SituacaoMatricula.ESTAGIARIO_CONCLUDENTE,
        SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
        SituacaoMatricula.AGUARDANDO_ENADE,
        SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO,
    ): ['INTEGRALIZADA'],
    (SituacaoMatricula.TRANSFERIDO_EXTERNO,): ['TRANSF_EXT'],
    (SituacaoMatricula.TRANSFERIDO_INTERNO,): [],
}


def iterate_task(task: Any, iterable: Iterable[Any]) -> Iterable[Any]:
    if task and hasattr(task, 'iterate'):
        return task.iterate(iterable)
    return iterable


def _parse_data_inicio(data_str: str) -> datetime.date:
    coluna = data_str.split(' ', maxsplit=1)[0]
    if '/' in coluna:
        day, month, year = map(int, coluna.split('/'))
    else:
        year, month, day = map(int, coluna.split('-'))
    return datetime.date(year, month, day)


def _parse_cpf(cpf_raw: Any) -> str:
    cpf = str(cpf_raw or '').replace('.', '').replace('-', '').strip()
    return mask_cpf(cpf.zfill(11)) if cpf else ''


def _curso_tem_codigo_sistec(codigo_sistec_str: str | None, codigo_procurado: int) -> bool:
    if not codigo_sistec_str:
        return False
    alvo = str(codigo_procurado)
    return any(part.strip() == alvo for part in codigo_sistec_str.split(';'))


def _determinar_valor_comparacao(aluno: Aluno) -> list[str]:
    for situacoes, valores in SITUACOES_MAP.items():
        if aluno.situacao_id in situacoes:
            if aluno.situacao_id == SituacaoMatricula.TRANSFERIDO_INTERNO:
                qs = Aluno.objects.filter(
                    curso_campus__modalidade_id=aluno.curso_campus.modalidade_id,
                    ano_letivo__ano__gte=aluno.ano_letivo.ano,
                ).exclude(id=aluno.id, curso_campus__diretoria__setor__uo_id=aluno.curso_campus.diretoria.setor.uo_id)
                if aluno.pessoa_fisica.cpf:
                    qs = qs.filter(pessoa_fisica__cpf=aluno.pessoa_fisica.cpf)
                else:
                    qs = qs.filter(pessoa_fisica=aluno.pessoa_fisica)
                qs = qs.order_by('-ano_letivo__ano')
                return ['TRANSF_EXT'] if qs.exists() else ['TRANSF_INT']
            return valores
    return []


def _desconsiderar_minicursos_menor_20h(qs: Any) -> Any:
    """Exclui alunos de cursos FIC < 160h (Minicurso) com carga horária total < 20 horas."""
    return qs.exclude(curso_campus__ch_total__lt=CursoCampus.CARGA_HORARIA_BASE_MINICURSO, curso_campus__modalidade_id=Modalidade.FIC_MENOS)


def _obter_qs_alunos_sistec(auditoria_ensino: AuditoriaEnsino, apenas_sem_cpf: bool = False) -> Any:
    qs = (
        Aluno.objects.filter(
            curso_campus__diretoria__setor__uo=auditoria_ensino.campus,
            data_inicio_ciclo__gte=auditoria_ensino.data_inicio_auditoria,
        )
        .exclude(
            Q(participanteturmaminicurso__turma__gerar_matricula=False)
            | Q(aluno_especial=True)
            | Q(forma_ingresso_id=ID_INTERCAMBIO)
            | Q(curso_campus__codigo_sistec__isnull=True)
            | Q(curso_campus__codigo_sistec='')
        )
        .exclude(Q(candidato_vaga__isnull=False, candidato_vaga__vaga__isnull=True))
        .exclude(
            curso_campus__diretoria__tipo=Diretoria.TIPO_PRONATEC,
            ano_letivo__ano__lt=ANO_CORTE_PRONATEC_SISTEC,
        )
    )
    if auditoria_ensino.data_fim_auditoria:
        qs = qs.filter(data_inicio_ciclo__lte=auditoria_ensino.data_fim_auditoria)
    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)
    if apenas_sem_cpf:
        qs = qs.filter(Q(pessoa_fisica__cpf__isnull=True) | Q(pessoa_fisica__cpf=''))
    else:
        qs = qs.exclude(Q(pessoa_fisica__cpf__isnull=True) | Q(pessoa_fisica__cpf=''))
    return _desconsiderar_minicursos_menor_20h(qs)


def _obter_codigos_sistec_minicursos_menor_20h(campus: UnidadeOrganizacional | None = None) -> set[int]:
    """Retorna os códigos SISTEC associados a cursos FIC < 160h (Minicurso) com carga horária < 20h."""
    codigos: set[int] = set()
    qs = CursoCampus.objects.filter(
        ch_total__lt=CursoCampus.CARGA_HORARIA_BASE_MINICURSO,
        ch_total__isnull=False,
        codigo_sistec__isnull=False,
    ).exclude(codigo_sistec='')
    if campus:
        qs = qs.filter(diretoria__setor__uo=campus)
    for cod_str in qs.values_list('codigo_sistec', flat=True):
        for part in cod_str.split(';'):
            part = part.strip()
            if part.isdigit():
                codigos.add(int(part))
    return codigos


def _obter_codigos_sistec_nivel(nivel_ensino_id: int | None) -> set[int] | None:
    if not nivel_ensino_id:
        return None
    codigos: set[int] = set()
    qs = (
        CursoCampus.objects.filter(modalidade__nivel_ensino_id=nivel_ensino_id, codigo_sistec__isnull=False)
        .exclude(codigo_sistec='')
        .values_list('codigo_sistec', flat=True)
    )
    for cod_str in qs:
        for part in cod_str.split(';'):
            part = part.strip()
            if part.isdigit():
                codigos.add(int(part))
    return codigos


def _selecionar_candidato_aluno(candidatos: list[Aluno], data_inicio: datetime.date) -> Aluno:
    if len(candidatos) == 1:
        return candidatos[0]
    mesmo_ciclo = [
        a
        for a in candidatos
        if a.data_inicio_ciclo and a.data_inicio_ciclo.year == data_inicio.year and a.data_inicio_ciclo.month == data_inicio.month
    ]
    if len(mesmo_ciclo) == 1:
        return mesmo_ciclo[0]
    mesmo_ano = [a for a in candidatos if a.ano_letivo and a.ano_letivo.ano == data_inicio.year]
    if len(mesmo_ano) == 1:
        return mesmo_ano[0]
    if len(mesmo_ano) == 0:
        raise Aluno.DoesNotExist
    raise Aluno.MultipleObjectsReturned


def _codigo_sistec_vazio(aluno: Any) -> bool:
    cod = getattr(aluno, 'codigo_sistec', None)
    if cod is None or not isinstance(cod, (str, int)):
        return True
    return not str(cod).strip()


def _buscar_candidatos_por_codigo_sistec(
    cod_sistec: str,
    codigo_sistec_curso: int,
    alunos_por_cod_sistec: dict[str, list[Aluno]] | None,
    alunos_por_cpf: dict[str, list[Aluno]] | None,
    cpf_aluno: str,
) -> list[Aluno]:
    if alunos_por_cod_sistec and cod_sistec in alunos_por_cod_sistec:
        candidatos = [a for a in alunos_por_cod_sistec[cod_sistec] if _curso_tem_codigo_sistec(a.curso_campus.codigo_sistec, codigo_sistec_curso)]
        if candidatos:
            return candidatos

    if alunos_por_cpf and cpf_aluno:
        candidatos = [
            a
            for a in alunos_por_cpf.get(cpf_aluno, [])
            if _curso_tem_codigo_sistec(a.curso_campus.codigo_sistec, codigo_sistec_curso)
            and str(getattr(a, 'codigo_sistec', '') or '').strip() == cod_sistec
        ]
        if candidatos and alunos_por_cod_sistec is not None:
            alunos_por_cod_sistec.setdefault(cod_sistec, []).extend(candidatos)
        return candidatos

    return []


def _localizar_por_codigo_sistec(
    cod_sistec: str,
    codigo_sistec_curso: int,
    data_inicio: datetime.date,
    alunos_por_cod_sistec: dict[str, list[Aluno]] | None = None,
    alunos_por_cpf: dict[str, list[Aluno]] | None = None,
    cpf_aluno: str = '',
) -> tuple[Aluno | None, list[Aluno], str | None]:
    if not cod_sistec:
        return None, [], None

    candidatos = _buscar_candidatos_por_codigo_sistec(cod_sistec, codigo_sistec_curso, alunos_por_cod_sistec, alunos_por_cpf, cpf_aluno)
    if not candidatos:
        return None, [], None

    try:
        aluno = _selecionar_candidato_aluno(candidatos, data_inicio)
        return aluno, candidatos, None
    except Aluno.DoesNotExist:
        return None, candidatos, 'NOT_FOUND'
    except Aluno.MultipleObjectsReturned:
        return None, candidatos, 'DUPLICATE'


def _localizar_candidatos_fallback(
    data: dict[str, Any],
    cpf_aluno: str,
    codigo_sistec_curso: int,
    alunos_por_cpf: dict[str, list[Aluno]],
    qs_final_alunos: Any,
) -> list[Aluno]:
    if cpf_aluno:
        return [
            a
            for a in alunos_por_cpf.get(cpf_aluno, [])
            if _curso_tem_codigo_sistec(a.curso_campus.codigo_sistec, codigo_sistec_curso) and _codigo_sistec_vazio(a)
        ]
    dt_nasc = _parse_data_inicio(data['DT_DATA_NASCIMENTO'])
    qs = qs_final_alunos.filter(pessoa_fisica__nome__iexact=data['NO_ALUNO'], pessoa_fisica__nascimento_data=dt_nasc).select_related(
        'situacao', 'pessoa_fisica', 'curso_campus__diretoria__setor__uo', 'ano_letivo'
    )
    return [a for a in qs if _curso_tem_codigo_sistec(a.curso_campus.codigo_sistec, codigo_sistec_curso) and _codigo_sistec_vazio(a)]


def _localizar_aluno_sistec(
    data: dict[str, Any],
    cpf_aluno: str,
    codigo_sistec_curso: int,
    data_inicio: datetime.date,
    alunos_por_cpf: dict[str, list[Aluno]],
    qs_final_alunos: Any,
    alunos_por_cod_sistec: dict[str, list[Aluno]] | None = None,
) -> tuple[Aluno | None, list[Aluno], str | None]:
    cod_sistec = str(data.get('CO_MATRICULA', '')).strip()
    aluno, candidatos, erro = _localizar_por_codigo_sistec(
        cod_sistec,
        codigo_sistec_curso,
        data_inicio,
        alunos_por_cod_sistec=alunos_por_cod_sistec,
        alunos_por_cpf=alunos_por_cpf,
        cpf_aluno=cpf_aluno,
    )
    if aluno or erro == 'DUPLICATE':
        return aluno, candidatos, erro

    candidatos = _localizar_candidatos_fallback(data, cpf_aluno, codigo_sistec_curso, alunos_por_cpf, qs_final_alunos)
    if not candidatos:
        return None, [], 'NOT_FOUND'

    try:
        aluno = _selecionar_candidato_aluno(candidatos, data_inicio)
        return aluno, candidatos, None
    except Aluno.DoesNotExist:
        return None, candidatos, 'NOT_FOUND'
    except Aluno.MultipleObjectsReturned:
        return None, candidatos, 'DUPLICATE'


def _processar_linha_sistec(
    data: dict[str, Any],
    auditoria_ensino: AuditoriaEnsino,
    alunos_por_cpf: dict[str, list[Aluno]],
    qs_final_alunos: Any,
    alunos_atualizar_sistec: list[Aluno],
    ids_nao_ausentes: list[int],
    alunos_por_cod_sistec: dict[str, list[Aluno]] | None = None,
    apenas_sem_cpf: bool = False,
) -> RegistroAuditoriaEnsino | None:
    cpf_aluno = _parse_cpf(data.get('NU_CPF'))
    if apenas_sem_cpf and cpf_aluno:
        return None

    codigo_sistec_curso = int(data['CO_CURSO'])
    situacao_sistec = data['NO_STATUS_MATRICULA']
    ciclo = data['NO_CICLO_MATRICULA']
    nome_aluno = data['NO_ALUNO']
    cod_sistec = str(data.get('CO_MATRICULA', '')).strip()
    data_inicio = _parse_data_inicio(data['DT_DATA_INICIO'])

    if not (
        auditoria_ensino.data_inicio_auditoria < data_inicio
        and (auditoria_ensino.data_fim_auditoria is None or auditoria_ensino.data_fim_auditoria > data_inicio)
    ):
        return None

    try:
        aluno, candidatos, erro = _localizar_aluno_sistec(
            data,
            cpf_aluno,
            codigo_sistec_curso,
            data_inicio,
            alunos_por_cpf,
            qs_final_alunos,
            alunos_por_cod_sistec=alunos_por_cod_sistec,
        )
        if erro == 'NOT_FOUND':
            return RegistroAuditoriaEnsino(
                auditoria_ensino=auditoria_ensino,
                registro=f'-;{cpf_aluno};{nome_aluno};{situacao_sistec};-;NÃO ENCONTRADO;-;{ciclo}',
                divergente=True,
            )
        if erro == 'DUPLICATE':
            matriculas = '| '.join(a.matricula for a in candidatos)
            ids_nao_ausentes.extend(a.id for a in candidatos)
            return RegistroAuditoriaEnsino(
                auditoria_ensino=auditoria_ensino,
                registro=f'{matriculas};{cpf_aluno};{nome_aluno};{situacao_sistec};-;DUPLICADO;-;{ciclo}',
                divergente=True,
            )

        assert aluno is not None
        val_comp = _determinar_valor_comparacao(aluno)
        situacao_auditoria = 'CONVERGENTE' if situacao_sistec in val_comp else 'DIVERGENTE'
        divergente = situacao_auditoria != 'CONVERGENTE'

        if not aluno.codigo_sistec and cod_sistec:
            aluno.codigo_sistec = cod_sistec
            alunos_atualizar_sistec.append(aluno)
            if alunos_por_cod_sistec is not None:
                alunos_por_cod_sistec[cod_sistec].append(aluno)

        ids_nao_ausentes.append(aluno.id)
        return RegistroAuditoriaEnsino(
            auditoria_ensino=auditoria_ensino,
            registro=f'{aluno.matricula};{cpf_aluno};{nome_aluno};{situacao_sistec};{aluno.situacao.descricao};{situacao_auditoria};{aluno.curso_campus.descricao};{ciclo}',
            divergente=divergente,
        )
    except Exception:
        return RegistroAuditoriaEnsino(
            auditoria_ensino=auditoria_ensino,
            registro=f'-;{cpf_aluno};{nome_aluno};{situacao_sistec};-;ERRO_PROCESSAMENTO;-;{ciclo}',
            divergente=True,
        )


def _aluno_ausente_valido(aluno: Aluno, auditoria_ensino: AuditoriaEnsino) -> bool:
    if aluno.situacao_id == SituacaoMatricula.TRANSFERIDO_INTERNO:
        qs = Aluno.objects.exclude(id=aluno.id).filter(
            ano_letivo__ano__gte=aluno.ano_letivo.ano,
        )
        if aluno.pessoa_fisica.cpf:
            qs = qs.filter(pessoa_fisica__cpf=aluno.pessoa_fisica.cpf)
        else:
            qs = qs.filter(pessoa_fisica=aluno.pessoa_fisica)

        if (
            not qs.exclude(curso_campus__diretoria__setor__uo_id=aluno.curso_campus.diretoria.setor.uo_id).exists()
            or not qs.exclude(curso_campus__modalidade_id=aluno.curso_campus.modalidade_id).exists()
        ):
            return False

    mp = aluno.get_matriculas_periodo(orderbyDesc=False).first()
    if mp is None or mp.turma is None:
        return False
    dt_cal = mp.turma.calendario_academico.data_inicio
    if dt_cal < auditoria_ensino.data_inicio_auditoria:
        return False
    return not bool(auditoria_ensino.data_fim_auditoria and dt_cal > auditoria_ensino.data_fim_auditoria)


def _obter_chave_aluno_sistec(data: dict[str, Any], codigo_unidade: str, apenas_sem_cpf: bool) -> tuple[Any, ...]:
    cod_curso = str(int(data['CO_CURSO']))
    if not apenas_sem_cpf:
        cpf = _parse_cpf(data.get('NU_CPF'))
        return (cpf, cod_curso, codigo_unidade)
    nome = str(data.get('NO_ALUNO', '')).strip().upper()
    dt_nasc = _parse_data_inicio(data['DT_DATA_NASCIMENTO']) if data.get('DT_DATA_NASCIMENTO') else None
    return (nome, dt_nasc, cod_curso, codigo_unidade)


def _aluno_em_sistec(aluno: Aluno, alunos_sistec_set: set[tuple[Any, ...]], apenas_sem_cpf: bool) -> bool:
    cod_uo = aluno.curso_campus.diretoria.setor.uo.codigo_sistec or ''
    codigos = aluno.curso_campus.codigo_sistec.split(';') if aluno.curso_campus.codigo_sistec else []
    for cod in codigos:
        cod_limpo = cod.strip()
        if not apenas_sem_cpf:
            if (aluno.pessoa_fisica.cpf, cod_limpo, cod_uo) in alunos_sistec_set:
                return True
        else:
            nome = aluno.pessoa_fisica.nome.strip().upper()
            dt_nasc = aluno.pessoa_fisica.nascimento_data
            if (nome, dt_nasc, cod_limpo, cod_uo) in alunos_sistec_set:
                return True
    return False


def _processar_alunos_ausentes_sistec(
    auditoria_ensino: AuditoriaEnsino,
    qs_final_alunos: Any,
    ids_nao_ausentes: list[int],
    alunos_sistec_set: set[tuple[Any, ...]],
    task: Any,
    apenas_sem_cpf: bool = False,
) -> list[RegistroAuditoriaEnsino]:
    qs_ausentes = (
        qs_final_alunos.exclude(id__in=ids_nao_ausentes)
        .select_related('pessoa_fisica', 'situacao', 'curso_campus__diretoria__setor__uo', 'ano_letivo')
        .distinct()
    )
    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs_ausentes):
        if not _aluno_ausente_valido(aluno, auditoria_ensino):
            continue
        if not _aluno_em_sistec(aluno, alunos_sistec_set, apenas_sem_cpf):
            cpf_aluno = aluno.pessoa_fisica.cpf or ''
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno.matricula};{cpf_aluno};{aluno.pessoa_fisica.nome};-;{aluno.situacao!s};AUSENTE;{aluno.curso_campus.descricao};-',
                    divergente=True,
                )
            )
    return registros


def _inicializar_task_sistec(task: Any, qs_final_alunos: Any, total_linhas: int, rsheet: list[Any]) -> None:
    from djtools.models import Task

    if task and hasattr(task, 'pk') and task.pk:
        Task.objects.filter(pk=task.pk).update(total=total_linhas)
    if task and hasattr(task, 'count'):
        task.count(qs_final_alunos, rsheet)


def _carregar_alunos_por_cpf(qs_final_alunos: Any, cpfs: set[str]) -> dict[str, list[Aluno]]:
    alunos_por_cpf: dict[str, list[Aluno]] = defaultdict(list)
    qs_carga = (
        qs_final_alunos.filter(pessoa_fisica__cpf__in=cpfs)
        .select_related('situacao', 'pessoa_fisica', 'curso_campus__diretoria__setor__uo', 'ano_letivo')
        .distinct()
    )
    for aluno in qs_carga:
        alunos_por_cpf[aluno.pessoa_fisica.cpf].append(aluno)
    return alunos_por_cpf


def _carregar_alunos_por_codigo_sistec(qs_final_alunos: Any, codigos: set[str]) -> dict[str, list[Aluno]]:
    alunos_por_cod: dict[str, list[Aluno]] = defaultdict(list)
    if not codigos:
        return alunos_por_cod
    codigos_busca = set(codigos)
    for c in list(codigos):
        codigos_busca.add(f'{c} ')
        codigos_busca.add(f' {c}')
    qs_carga = (
        qs_final_alunos.filter(codigo_sistec__in=codigos_busca)
        .select_related('situacao', 'pessoa_fisica', 'curso_campus__diretoria__setor__uo', 'ano_letivo')
        .distinct()
    )
    for aluno in qs_carga:
        if aluno.codigo_sistec:
            alunos_por_cod[str(aluno.codigo_sistec).strip()].append(aluno)
    return alunos_por_cod


def _indexar_alunos_cpf_em_cod_sistec(
    alunos_por_cpf: dict[str, list[Aluno]],
    alunos_por_cod_sistec: dict[str, list[Aluno]],
) -> None:
    for lista_alunos in alunos_por_cpf.values():
        for aluno in lista_alunos:
            if aluno.codigo_sistec:
                cod = str(aluno.codigo_sistec).strip()
                if aluno not in alunos_por_cod_sistec[cod]:
                    alunos_por_cod_sistec[cod].append(aluno)


def _iterar_linhas_planilha_sistec(
    rsheet: list[dict[str, Any]],
    auditoria_ensino: AuditoriaEnsino,
    codigos_nivel: set[int] | None,
    codigo_unidade: str,
    alunos_por_cpf: dict[str, list[Aluno]],
    qs_final_alunos: Any,
    task: Any,
    codigos_desconsiderados: set[int] | None = None,
    alunos_por_cod_sistec: dict[str, list[Aluno]] | None = None,
    apenas_sem_cpf: bool = False,
) -> tuple[list[RegistroAuditoriaEnsino], set[tuple[Any, ...]], list[Aluno], list[int]]:
    registros: list[RegistroAuditoriaEnsino] = []
    alunos_sistec_set: set[tuple[Any, ...]] = set()
    alunos_atualizar: list[Aluno] = []
    ids_nao_ausentes: list[int] = []

    for data in iterate_task(task, rsheet):
        cod_curso = int(data['CO_CURSO'])
        if codigos_desconsiderados and cod_curso in codigos_desconsiderados:
            continue
        if codigos_nivel is not None and cod_curso not in codigos_nivel:
            continue
        if apenas_sem_cpf and _parse_cpf(data.get('NU_CPF')):
            continue

        alunos_sistec_set.add(_obter_chave_aluno_sistec(data, codigo_unidade, apenas_sem_cpf))
        reg = _processar_linha_sistec(
            data,
            auditoria_ensino,
            alunos_por_cpf,
            qs_final_alunos,
            alunos_atualizar,
            ids_nao_ausentes,
            alunos_por_cod_sistec=alunos_por_cod_sistec,
            apenas_sem_cpf=apenas_sem_cpf,
        )
        if reg:
            registros.append(reg)

    return registros, alunos_sistec_set, alunos_atualizar, ids_nao_ausentes


def _gerar_sistec(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    codigo_unidade = auditoria_ensino.campus.codigo_sistec or ''
    planilha = auditoria_ensino.fonte_dados.open('rb')
    planilha_encoded = io.TextIOWrapper(planilha, encoding='iso-8859-1')
    reader = csv.DictReader(planilha_encoded, delimiter=';')
    cabecalho = {str(c).strip() for c in (reader.fieldnames or [])}
    rsheet = [{str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None} for row in reader]
    planilha_encoded.flush()

    fluxo_com_cpf = 'CO_ALUNO_IDENTIFICADO' in cabecalho and 'NU_CPF' in cabecalho
    apenas_sem_cpf = not fluxo_com_cpf

    qs_final_alunos = _obter_qs_alunos_sistec(auditoria_ensino, apenas_sem_cpf=apenas_sem_cpf)
    _inicializar_task_sistec(task, qs_final_alunos, len(rsheet), rsheet)
    codigos_nivel = _obter_codigos_sistec_nivel(auditoria_ensino.nivel_ensino_id)
    codigos_desconsiderados = _obter_codigos_sistec_minicursos_menor_20h(auditoria_ensino.campus)

    codigos_sistec = {str(row.get('CO_MATRICULA', '')).strip() for row in rsheet if row.get('CO_MATRICULA')}
    codigos_sistec.discard('')
    alunos_por_cod_sistec = _carregar_alunos_por_codigo_sistec(qs_final_alunos, codigos_sistec)

    if fluxo_com_cpf:
        cpfs = {_parse_cpf(row.get('NU_CPF')) for row in rsheet if row.get('NU_CPF')}
        cpfs.discard('')
        alunos_por_cpf = _carregar_alunos_por_cpf(qs_final_alunos, cpfs)
        _indexar_alunos_cpf_em_cod_sistec(alunos_por_cpf, alunos_por_cod_sistec)
    else:
        alunos_por_cpf = {}

    registros, alunos_sistec_set, alunos_atualizar, ids_nao_ausentes = _iterar_linhas_planilha_sistec(
        rsheet,
        auditoria_ensino,
        codigos_nivel,
        codigo_unidade,
        alunos_por_cpf,
        qs_final_alunos,
        task,
        codigos_desconsiderados=codigos_desconsiderados,
        alunos_por_cod_sistec=alunos_por_cod_sistec,
        apenas_sem_cpf=apenas_sem_cpf,
    )

    if alunos_atualizar:
        Aluno.objects.bulk_update(alunos_atualizar, ['codigo_sistec'])

    ausentes = _processar_alunos_ausentes_sistec(
        auditoria_ensino,
        qs_final_alunos,
        ids_nao_ausentes,
        alunos_sistec_set,
        task,
        apenas_sem_cpf=apenas_sem_cpf,
    )
    registros.extend(ausentes)

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _obter_qs_alunos_situacao_matricula(auditoria_ensino: AuditoriaEnsino) -> Any:
    qs = (
        Aluno.objects.filter(curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus.id)
        .exclude(curso_campus__codigo_sistec__isnull=True)
        .exclude(curso_campus__codigo_sistec='')
        .exclude(
            situacao_id__in=[
                SituacaoMatricula.MATRICULADO,
                SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                SituacaoMatricula.TRANCADO,
                SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
            ]
        )
    )
    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)
    qs = qs.filter(
        Q(matriz__estrutura__proitec=True, situacao_id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO])
        | Q(matriz__estrutura__proitec=False)
    )
    return _desconsiderar_minicursos_menor_20h(qs)


def _gerar_situacao_matricula(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    data_referencia = auditoria_ensino.data_auditoria - relativedelta(months=1)
    qs_alunos = _obter_qs_alunos_situacao_matricula(auditoria_ensino)
    subquery_ids = qs_alunos.values_list('id', flat=True)

    diffs_qs = (
        RegistroDiferenca.objects.filter(
            log__nome_modelo='Aluno',
            campo='Situação',
            log__dt__year=data_referencia.year,
            log__dt__month=data_referencia.month,
            log__ref__in=subquery_ids,
        )
        .select_related('log')
        .order_by('log__ref', 'log__dt')
    )

    diffs_por_aluno: dict[int, list[RegistroDiferenca]] = defaultdict(list)
    for diff in diffs_qs:
        diffs_por_aluno[diff.log.ref].append(diff)

    divergencias: dict[int, tuple[str, str, Any]] = {}
    for aluno_id, diffs in diffs_por_aluno.items():
        situacao_anterior = diffs[0].valor_anterior
        situacao_atual = diffs[-1].valor_atual
        if situacao_anterior != situacao_atual:
            divergencias[aluno_id] = (situacao_anterior, situacao_atual, diffs[-1].log.dt)

    if not divergencias:
        return

    alunos = qs_alunos.filter(id__in=divergencias.keys()).select_related('pessoa_fisica', 'curso_campus').in_bulk()

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno_id in iterate_task(task, divergencias.keys()):
        aluno = alunos.get(aluno_id)
        if not aluno:
            continue
        ant, atu, dt_log = divergencias[aluno_id]
        cpf_aluno = aluno.pessoa_fisica.cpf or ''
        registros.append(
            RegistroAuditoriaEnsino(
                auditoria_ensino=auditoria_ensino,
                registro=f'{aluno.matricula};{cpf_aluno};{aluno.pessoa_fisica.nome};{ant};{atu};{dt_log};{aluno.curso_campus.descricao}',
                divergente=True,
            )
        )
    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _comparar_dados_rf(aluno: Aluno, dados_rf: dict[str, Any]) -> tuple[bool, str, str, str, str, str, str]:
    tem_divergencia = False
    nome_suap = nome_rf = nascimento_suap = nascimento_rf = mae_suap = mae_rf = '-'

    if retira_acentos(aluno.pessoa_fisica.nome_registro.upper()) != retira_acentos(dados_rf['Nome'].upper()):
        nome_suap = aluno.pessoa_fisica.nome_registro
        nome_rf = dados_rf['Nome']
        tem_divergencia = True

    nascimento_aluno_suap = re.sub(r'\D', '', str(aluno.pessoa_fisica.nascimento_data))
    nascimento_aluno_rf = re.sub(r'\D', '', str(dados_rf['DataNascimento']))
    if nascimento_aluno_suap != nascimento_aluno_rf:
        nascimento_suap = f'{nascimento_aluno_suap[6:8]}/{nascimento_aluno_suap[4:6]}/{nascimento_aluno_suap[0:4]}'
        nascimento_rf = f'{nascimento_aluno_rf[6:8]}/{nascimento_aluno_rf[4:6]}/{nascimento_aluno_rf[0:4]}'
        tem_divergencia = True

    nome_mae = aluno.nome_mae or ''
    if retira_acentos(nome_mae.upper()) != retira_acentos(dados_rf['NomeMae'].upper()):
        mae_suap = nome_mae
        mae_rf = dados_rf['NomeMae']
        tem_divergencia = True

    return tem_divergencia, nome_suap, nome_rf, nascimento_suap, nascimento_rf, mae_suap, mae_rf


def _validar_operador_rf() -> bool:
    from demandas.models import AreaAtuacaoDemanda

    area_ensino = AreaAtuacaoDemanda.objects.filter(area__nome='Ensino').first()
    if not area_ensino or not hasattr(area_ensino, 'demandante_responsavel'):
        return False
    vinculo = area_ensino.demandante_responsavel.get_vinculo()
    cpf_operador = getattr(vinculo.pessoa.pessoafisica, 'cpf', None)
    return cpf_operador is not None


def _obter_qs_alunos_rf(auditoria_ensino: AuditoriaEnsino) -> Any:
    alunos = (
        Aluno.objects.filter(curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus_id, matriz__estrutura__proitec=False)
        .exclude(curso_campus__codigo_sistec__isnull=True)
        .exclude(curso_campus__codigo_sistec='')
        .exclude(nacionalidade='Estrangeira')
        .select_related('pessoa_fisica', 'curso_campus')
    )
    if auditoria_ensino.nivel_ensino_id:
        alunos = alunos.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)
    alunos = alunos.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False))
    return _desconsiderar_minicursos_menor_20h(alunos)


def _processar_aluno_rf(aluno: Aluno, auditoria_ensino: AuditoriaEnsino) -> RegistroAuditoriaEnsino | None:
    cpf = aluno.pessoa_fisica.cpf
    tem_divergencia = False
    nome_suap = nome_rf = nascimento_suap = nascimento_rf = mae_suap = mae_rf = '-'

    if cpf is None:
        tem_divergencia = True
        cpf = 'CPF não informado'
    else:
        try:
            dados_rf = aluno.get_dados_receita_federal()
        except Exception as e:
            if str(e) == 'CPF Inválido.':
                return RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno.matricula};CPF Inválido ({cpf});-;-;-;-;-;-;{aluno.curso_campus.descricao}',
                    divergente=True,
                )
            capture_exception(e)
            return None
        if dados_rf:
            tem_divergencia, nome_suap, nome_rf, nascimento_suap, nascimento_rf, mae_suap, mae_rf = _comparar_dados_rf(aluno, dados_rf)

    if tem_divergencia:
        return RegistroAuditoriaEnsino(
            auditoria_ensino=auditoria_ensino,
            registro=f'{aluno.matricula};{cpf};{nome_suap};{nome_rf};{nascimento_suap};{nascimento_rf};{mae_suap};{mae_rf};{aluno.curso_campus.descricao}',
            divergente=True,
        )
    return None


def _gerar_receita_federal(auditoria_ensino: AuditoriaEnsino, task: Any) -> bool:
    if not _validar_operador_rf():
        return False

    alunos = _obter_qs_alunos_rf(auditoria_ensino)
    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, alunos):
        reg = _processar_aluno_rf(aluno, auditoria_ensino)
        if reg:
            registros.append(reg)

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)
    return True


def _gerar_matricula_modalidade(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    qs = (
        Aluno.objects.filter(
            situacao__ativo=True,
            matriz_id__isnull=False,
            curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus.id,
        )
        .exclude(curso_campus__modalidade_id__in=[Modalidade.FIC, Modalidade.FIC_MENOS])
        .exclude(curso_campus__codigo_sistec__isnull=True)
        .exclude(curso_campus__codigo_sistec='')
    )
    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)
    qs = _desconsiderar_minicursos_menor_20h(qs)

    duplicados = qs.values('curso_campus__modalidade', 'pessoa_fisica__cpf').annotate(count=Count('curso_campus__modalidade')).filter(count__gt=1)

    registros: list[RegistroAuditoriaEnsino] = []
    for item in iterate_task(task, duplicados):
        alunos = Aluno.objects.filter(
            situacao__ativo=True,
            pessoa_fisica__cpf=item['pessoa_fisica__cpf'],
            curso_campus__modalidade_id=item['curso_campus__modalidade'],
        )
        if auditoria_ensino.nivel_ensino_id:
            alunos = alunos.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)
        alunos = _desconsiderar_minicursos_menor_20h(alunos)

        campos = alunos.values(
            'matricula',
            'pessoa_fisica__cpf',
            'pessoa_fisica__nome_registro',
            'curso_campus__modalidade__descricao',
            'situacao__descricao',
            'curso_campus__descricao',
        )
        for al in campos:
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{al["matricula"]};{al["pessoa_fisica__cpf"]};{al["pessoa_fisica__nome_registro"]};{al["curso_campus__modalidade__descricao"]};{al["situacao__descricao"]};{al["curso_campus__descricao"]}',
                    divergente=True,
                )
            )

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _gerar_nome_aluno(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    qs = Aluno.objects.filter(situacao__ativo=True, curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus.id).exclude(
        curso_campus__diretoria__tipo=Diretoria.TIPO_PRONATEC
    )
    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)

    qs = qs.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False))
    qs = (
        _desconsiderar_minicursos_menor_20h(qs)
        .values(
            'pessoa_fisica__nome_registro',
            'pessoa_fisica__cpf',
            'matricula',
            'curso_campus__diretoria__setor__sigla',
            'curso_campus__descricao',
        )
        .distinct()
    )

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs):
        nome = aluno['pessoa_fisica__nome_registro']
        if nome and bool(RE_NOME_INVALIDO.search(nome)):
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno["matricula"]};{aluno["pessoa_fisica__cpf"]};{nome};{auditoria_ensino.campus};{aluno["curso_campus__diretoria__setor__sigla"]};{aluno["curso_campus__descricao"]}',
                    divergente=True,
                )
            )

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _gerar_nome_pais(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    qs = Aluno.objects.filter(situacao__ativo=True, curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus.id).exclude(
        curso_campus__diretoria__tipo=Diretoria.TIPO_PRONATEC
    )
    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)

    qs = qs.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False))
    qs = (
        _desconsiderar_minicursos_menor_20h(qs)
        .values(
            'nome_pai',
            'nome_mae',
            'pessoa_fisica__cpf',
            'matricula',
            'curso_campus__diretoria__setor__sigla',
            'curso_campus__descricao',
        )
        .distinct()
    )

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs):
        nome_pai = aluno['nome_pai']
        if nome_pai and bool(RE_NOME_INVALIDO.search(nome_pai)):
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno["matricula"]};{aluno["pessoa_fisica__cpf"]};Pai;{nome_pai};{auditoria_ensino.campus};{aluno["curso_campus__diretoria__setor__sigla"]};{aluno["curso_campus__descricao"]}',
                    divergente=True,
                )
            )
        nome_mae = aluno['nome_mae']
        if nome_mae and bool(RE_NOME_INVALIDO.search(nome_mae)):
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno["matricula"]};{aluno["pessoa_fisica__cpf"]};Mãe;{nome_mae};{auditoria_ensino.campus};{aluno["curso_campus__diretoria__setor__sigla"]};{aluno["curso_campus__descricao"]}',
                    divergente=True,
                )
            )

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _gerar_nome_servidor(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    from rh.models import Servidor

    qs = (
        Servidor.objects.ativos()
        .filter(setor__uo_id=auditoria_ensino.campus.id)
        .values('pessoa_fisica__nome_registro', 'pessoa_fisica__cpf', 'matricula')
    )
    registros: list[RegistroAuditoriaEnsino] = []
    for servidor in iterate_task(task, qs):
        nome = servidor['pessoa_fisica__nome_registro']
        if nome and bool(RE_NOME_INVALIDO.search(nome)):
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{servidor["matricula"]};{servidor["pessoa_fisica__cpf"]};{nome};{auditoria_ensino.campus}',
                    divergente=True,
                )
            )

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _gerar_cidade_alunos(auditoria_ensino: AuditoriaEnsino, task: Any) -> list[RegistroAuditoriaEnsino]:
    qs = (
        Aluno.objects.filter(
            situacao__ativo=True,
            curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus_id,
            nacionalidade='Brasileira',
            naturalidade__nome__isnull=False,
        )
        .filter(Q(naturalidade__codigo__isnull=True) | Q(naturalidade__codigo=''))
        .exclude(curso_campus__codigo_sistec__isnull=True)
        .exclude(curso_campus__codigo_sistec='')
    )
    qs = qs.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False))
    qs = (
        _desconsiderar_minicursos_menor_20h(qs)
        .values(
            'pessoa_fisica__nome_registro',
            'pessoa_fisica__cpf',
            'matricula',
            'naturalidade__nome',
            'curso_campus__descricao',
        )
        .distinct()
    )

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs):
        nome_cidade = aluno['naturalidade__nome']
        registros.append(
            RegistroAuditoriaEnsino(
                auditoria_ensino=auditoria_ensino,
                registro=f'{aluno["matricula"]};{aluno["pessoa_fisica__cpf"]};{auditoria_ensino.campus};Aluno;{nome_cidade};{aluno["curso_campus__descricao"]}',
                divergente=True,
            )
        )
    return registros


def _gerar_cidade_servidores(auditoria_ensino: AuditoriaEnsino, task: Any) -> list[RegistroAuditoriaEnsino]:
    from rh.models import Servidor

    qs_servidor = list(
        Servidor.objects.ativos()
        .filter(setor__uo_id=auditoria_ensino.campus.id)
        .values('pessoa_fisica__cpf', 'matricula', 'pessoa_fisica__nascimento_municipio__nome')
    )

    nomes_cidades = {s['pessoa_fisica__nascimento_municipio__nome'] for s in qs_servidor if s['pessoa_fisica__nascimento_municipio__nome']}

    cidades_qs = Cidade.objects.filter(nome__in=nomes_cidades, pais__sigla='BRA')
    cidades_por_nome: dict[str, Cidade] = {}
    for c in cidades_qs:
        if c.nome not in cidades_por_nome:
            cidades_por_nome[c.nome] = c

    registros: list[RegistroAuditoriaEnsino] = []
    for servidor in iterate_task(task, qs_servidor):
        nome_cidade = servidor['pessoa_fisica__nascimento_municipio__nome']
        if not nome_cidade:
            continue
        cidade = cidades_por_nome.get(nome_cidade)
        if cidade and not cidade.codigo:
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{servidor["matricula"]};{servidor["pessoa_fisica__cpf"]};{auditoria_ensino.campus};Servidor;{nome_cidade};-',
                    divergente=True,
                )
            )
    return registros


def _gerar_cidade(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    registros = _gerar_cidade_alunos(auditoria_ensino, task)
    registros.extend(_gerar_cidade_servidores(auditoria_ensino, task))
    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _gerar_aluno_sem_sistec(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    ano_inicio = datetime.date.today().year - 5
    qs_alunos = (
        Aluno.objects.filter(
            codigo_sistec__isnull=True,
            curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus_id,
            ano_letivo__ano__gte=ano_inicio,
        )
        .exclude(participanteturmaminicurso__turma__gerar_matricula=False)
        .exclude(aluno_especial=True)
        .exclude(forma_ingresso_id=ID_INTERCAMBIO)
        .exclude(curso_campus__codigo_sistec__isnull=True)
        .exclude(curso_campus__codigo_sistec='')
        .exclude(
            candidato_vaga__vaga__isnull=True,
            situacao__in=[
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            ],
        )
        .select_related('pessoa_fisica', 'situacao', 'curso_campus')
        .only('matricula', 'pessoa_fisica__cpf', 'pessoa_fisica__nome', 'situacao__descricao', 'curso_campus__descricao')
        .distinct()
    )

    if auditoria_ensino.nivel_ensino_id:
        qs_alunos = qs_alunos.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)

    qs_alunos = _desconsiderar_minicursos_menor_20h(qs_alunos)

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs_alunos):
        cpf_aluno = aluno.pessoa_fisica.cpf or ''
        registros.append(
            RegistroAuditoriaEnsino(
                auditoria_ensino=auditoria_ensino,
                registro=f'{aluno.matricula};{cpf_aluno};{aluno.pessoa_fisica.nome};{aluno.situacao.descricao};{aluno.curso_campus.descricao}',
                divergente=True,
            )
        )
    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _aluno_esta_retido(
    aluno: Aluno,
    limite_fic_menos: datetime.date,
    limite_demais: datetime.date,
) -> bool:
    """Verifica se o aluno atende aos critérios de retenção para auditoria."""
    data_prevista = aluno.data_prevista_termino_ciclo
    if not data_prevista:
        return True
    if aluno.eh_aluno_minicurso():
        return aluno.situacao_id == SituacaoMatricula.MATRICULADO and data_prevista <= limite_fic_menos
    return data_prevista <= limite_demais


def _gerar_alunos_retidos(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    hoje = datetime.date.today()
    limite_fic_menos = hoje - datetime.timedelta(days=1)
    limite_demais = hoje - relativedelta(years=1)

    situacoes_candidatas = SituacaoMatricula.SITUACOES_CURSANDO

    qs = (
        Aluno.objects.filter(
            curso_campus__diretoria__setor__uo_id=auditoria_ensino.campus_id,
            situacao_id__in=situacoes_candidatas,
        )
        .exclude(curso_campus__diretoria__tipo=Diretoria.TIPO_PRONATEC, ano_letivo__ano__lt=ANO_CORTE_PRONATEC_SISTEC)
        .select_related('pessoa_fisica', 'situacao', 'curso_campus', 'matriz')
    )

    if auditoria_ensino.nivel_ensino_id:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino_id=auditoria_ensino.nivel_ensino_id)

    qs = _desconsiderar_minicursos_menor_20h(qs).distinct()

    alunos_para_atualizar: list[Aluno] = []
    for aluno in qs.filter(data_prevista_termino_ciclo__isnull=True):
        dt_prevista = aluno.calcular_data_prevista_termino_ciclo()
        if dt_prevista:
            aluno.data_prevista_termino_ciclo = dt_prevista
            alunos_para_atualizar.append(aluno)
    if alunos_para_atualizar:
        Aluno.objects.bulk_update(alunos_para_atualizar, ['data_prevista_termino_ciclo'], batch_size=1000)

    registros: list[RegistroAuditoriaEnsino] = []
    for aluno in iterate_task(task, qs):
        if _aluno_esta_retido(aluno, limite_fic_menos, limite_demais):
            dt_prevista = aluno.data_prevista_termino_ciclo.strftime('%d/%m/%Y') if aluno.data_prevista_termino_ciclo else 'NÃO INFORMADO'
            cpf_aluno = aluno.pessoa_fisica.cpf or ''
            registros.append(
                RegistroAuditoriaEnsino(
                    auditoria_ensino=auditoria_ensino,
                    registro=f'{aluno.matricula};{cpf_aluno};{aluno.pessoa_fisica.nome};{aluno.situacao.descricao};{aluno.curso_campus.descricao};{dt_prevista}',
                    divergente=True,
                )
            )

    if registros:
        RegistroAuditoriaEnsino.objects.bulk_create(registros, batch_size=1000)


def _obter_destinatarios_notificacao(auditoria_ensino: AuditoriaEnsino) -> list[Any]:
    if auditoria_ensino.is_auditoria_administrador():
        qs = UsuarioGrupo.objects.filter(group__name='Administrador Acadêmico').select_related('user').distinct()
        return [ug.user.get_vinculo() for ug in qs]

    setores = Diretoria.objects.filter(setor__uo_id=auditoria_ensino.campus.pk).values_list('setor_id', flat=True)
    qs = UsuarioGrupo.objects.filter(group__name='Secretário Acadêmico', setores__id__in=setores).select_related('user').distinct()
    return [ug.user.get_vinculo() for ug in qs]


def _enviar_notificacao_divergencia(auditoria_ensino: AuditoriaEnsino) -> None:
    usuarios = _obter_destinatarios_notificacao(auditoria_ensino)
    titulo = '[SUAP] Auditoria de Ensino Gerada'
    texto = (
        f'<h2>Auditoria - {auditoria_ensino.get_tipo_auditoria_display()}</h2>'
        '<p>Existe uma auditoria aguardando sua avaliação.</p>'
        f'<p>Acesse {settings.SITE_URL}/admin/edu/auditoriaensino/?tab=tab_gerada para listar todas as auditorias pendentes.</p>'
    )
    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, usuarios, fail_silently=True)


def _finalizar_auditoria(auditoria_ensino: AuditoriaEnsino, task: Any) -> None:
    auditoria_ensino.geracao_finalizada = True
    auditoria_ensino.save()

    if auditoria_ensino.registroauditoriaensino_set.filter(divergente=True).exists():
        if auditoria_ensino.tipo_auditoria != AuditoriaEnsino.TIPO_SISTEC:
            _enviar_notificacao_divergencia(auditoria_ensino)
    else:
        agora = datetime.datetime.now()
        auditoria_ensino.data_ciencia_atendente = agora
        auditoria_ensino.data_resolucao_auditoria = agora
        auditoria_ensino.save()

    if task and hasattr(task, 'finalize'):
        task.finalize('Auditoria gerada com sucesso.', auditoria_ensino.get_absolute_url())


HANDLERS = {
    AuditoriaEnsino.TIPO_SISTEC: _gerar_sistec,
    AuditoriaEnsino.TIPO_SITUACAO_MATRICULA: _gerar_situacao_matricula,
    AuditoriaEnsino.TIPO_MATRICULA_MODALIDADE: _gerar_matricula_modalidade,
    AuditoriaEnsino.TIPO_NOME_ALUNO: _gerar_nome_aluno,
    AuditoriaEnsino.TIPO_NOME_PAIS: _gerar_nome_pais,
    AuditoriaEnsino.TIPO_NOME_SERVIDOR: _gerar_nome_servidor,
    AuditoriaEnsino.TIPO_CIDADE: _gerar_cidade,
    AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC: _gerar_aluno_sem_sistec,
    AuditoriaEnsino.TIPO_ALUNOS_RETIDOS: _gerar_alunos_retidos,
}


class AuditoriaEnsinoService:
    @classmethod
    def notificar_campus(cls, auditoria_ensino: AuditoriaEnsino) -> None:
        _enviar_notificacao_divergencia(auditoria_ensino)

    @classmethod
    def processar(cls, auditoria_ensino: AuditoriaEnsino, task: Any = None) -> None:
        tipo = auditoria_ensino.tipo_auditoria
        if tipo == AuditoriaEnsino.TIPO_RECEITA_FEDERAL:
            if not _gerar_receita_federal(auditoria_ensino, task):
                return
        else:
            handler = HANDLERS.get(tipo)
            if handler:
                handler(auditoria_ensino, task)

        _finalizar_auditoria(auditoria_ensino, task)
