from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edu.models import AuditoriaEnsino

import csv
import datetime
import io
import operator
import os
import re
import tempfile
import unicodedata
import zipfile
from collections import OrderedDict, defaultdict
from time import sleep

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.utils import IntegrityError
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from sentry_sdk import capture_exception

from comum.models import APIExterna, Configuracao
from djtools.assincrono import task
from djtools.models import Task
from djtools.storages import get_temp_storage
from djtools.templatetags.filters import cpf_sem_caracteres, format_
from djtools.utils import (
    CsvResponse,
    XlsResponse,
    gerar_documento_impressao,
    mask_cpf,
    render_to_string,
    running_tests,
    send_mail,
    similaridade,
    to_ascii,
)
from edu import censup, educacenso, pedemeia2, q_academico
from edu.migracao import (
    ImportadorAlunos,
    ImportadorComponentes,
    ImportadorCursos,
    ImportadorEquivalencia,
    ImportadorHistoricoAluno,
    ImportadorInicializarPeriodoLetivo,
    ImportadorMatrizes,
    ImportadorProcedimentoMatricula,
)
from edu.models import (
    Aluno,
    Aula,
    ComponenteCurricular,
    CursoCampus,
    Diario,
    EstruturaCurso,
    Falta,
    MatriculaDiario,
    MatriculaPeriodo,
    Modalidade,
    NivelEnsino,
    PedidoMatriculaDiario,
    PossivelConcluinte,
    PossivelIntegralizado,
    Professor,
    RegistroConvocacaoENADE,
    Requerimento,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
)
from edu.models.eventos import ParticipacaoColacaoGrau


@task('Sincronizar Turma com Moodle')
def sincronizar_turma_moodle(turma, task=None):
    moodle = APIExterna.MOODLE.get_service()
    for diario in task.iterate(turma.diario_set.filter(integracao_com_moodle=True)):
        try:
            url = moodle.sincronizar(diario)
        except Exception as e:
            capture_exception(e)
            task.finalize(f'Ocorreu um erro ao se comunicar com o Moodle. {e}', error=True)
            return
        diario.url_moodle = url
        diario.save()
    task.finalize('Turma sincronizada com sucesso.')


@task('Fechar Período')
def fechar_periodo(forcar_fechamento, matriculas_periodo, diarios, querystring, modulo=None, task=None):
    task.count(matriculas_periodo, diarios)
    for matricula_periodo in task.iterate(matriculas_periodo):
        matricula_periodo.fechar_periodo_letivo(forcar_fechamento, modulo)

    for diario in task.iterate(diarios):
        diario.fechar()
    msg = 'Módulo' if modulo else 'Período'
    task.finalize(f'{msg} fechado com sucesso.', f'/edu/fechar_periodo_letivo/?{querystring}&finalize=1')


@task('Abrir Período')
def abrir_periodo(diarios, matriculas_periodo, querystring, modulo=None, task=None):
    task.count(diarios, matriculas_periodo)

    for diario in task.iterate(diarios):
        diario.abrir()

    for matricula_periodo in task.iterate(matriculas_periodo):
        matricula_periodo.abrir_periodo_letivo(modulo)

    msg = 'Módulo' if modulo else 'Período'
    task.finalize(f'{msg} aberto com sucesso.', f'/edu/abrir_periodo_letivo/?{querystring}&finalize=1')


@task('Migrar Alunos')
def migrar_alunos(matriculas, matriz_id, ano_letivo, periodo_letivo, task=None):
    dao = running_tests() and q_academico.MockDAO() or q_academico.DAO()
    dao.importar_historico_resumo(matriculas, matriz_id, ano_letivo, periodo_letivo, task=task, validacao=False)


@task('Suspender Diários em Lote')
@transaction.atomic()
def suspender_diarios_lote(diarios, inicio, justificativa, motivo, task=None):
    qtd_sucesso = 0
    for obj in task.iterate(diarios):
        try:
            obj.suspender(inicio, justificativa, motivo)
            qtd_sucesso += 1
        except Exception as e:
            task.finalize('Erro ao Suspender Diários em Lote.', error=True)
            capture_exception(e)
            return
    task.finalize(f'{qtd_sucesso} Suspensões de Diários cadastradas com sucesso.')


@task('Encerrar Suspensão de Diários em Lote')
@transaction.atomic()
def encerrar_suspensao_diarios_lote(diarios, fim, task=None):
    qtd_encerrados = 0
    for obj in task.iterate(diarios):
        try:
            if obj.possui_suspensao_aberta():
                qtd_encerrados += 1
            obj.encerrar_suspensao(fim)
        except Exception as e:
            task.finalize('Erro ao encerrar suspensão de Diários em Lote.', error=True)
            capture_exception(e)
            return
    task.finalize(f'{qtd_encerrados}  suspensões de Diários encerradas com sucesso.')


@task('Exportar Dados Aluno e Caracterização')
def exportar_dados_aluno_caracterizacao(ano_ingresso, periodo_ingresso, sigla_campus, task=None):
    def get_alunos(ano, periodo, campus, qtd_campos_caracterizacao, qtd_periodos_vazio, task):
        result = []
        qs_alunos = Aluno.objects.filter(curso_campus__diretoria__setor__uo__sigla=campus, ano_letivo__ano=ano, periodo_letivo=periodo).exclude(
            curso_campus__modalidade_id__in=[Modalidade.FIC, Modalidade.FIC_MENOS]
        )

        for aluno in task.iterate(qs_alunos):
            dados_aluno = []
            modalidade = aluno.curso_campus.modalidade
            dados_aluno.append(aluno.matricula)
            dados_aluno.append(aluno.forma_ingresso and aluno.forma_ingresso.descricao or '-')
            dados_aluno.append(aluno.curso_campus.codigo)
            dados_aluno.append(aluno.curso_campus.descricao)
            dados_aluno.append(modalidade or '-')
            dados_aluno.append(modalidade and modalidade.nivel_ensino or '-')
            dados_aluno.append(aluno.matriz.natureza_participacao)
            dados_aluno.append(aluno.curso_campus.diretoria.setor.sigla)
            dados_aluno.append(aluno.curso_campus.diretoria.setor.uo.sigla)
            dados_aluno.append(aluno.situacao)
            if aluno.situacao.id in SituacaoMatricula.SITUACOES_INATIVAS_PARA_EXCLUSAO_TURMA:
                dados_aluno.append(aluno.get_ultima_matricula_periodo().ano_letivo.ano)
            else:
                dados_aluno.append('-')
            dados_aluno.append(aluno.turno)
            dados_aluno.append(aluno.ano_letivo and aluno.ano_letivo.ano or '-')
            dados_aluno.append(aluno.ano_let_prev_conclusao)
            dados_aluno.append(aluno.ano_conclusao)
            dados_aluno.append(aluno.cidade)
            dados_aluno.append(aluno.get_tipo_zona_residencial_display())
            dados_aluno.append(aluno.convenio)
            dados_aluno.append(aluno.pessoa_fisica and aluno.pessoa_fisica.nascimento_data or '-')
            dados_aluno.append(aluno.pessoa_fisica and aluno.pessoa_fisica.sexo or '-')
            dados_aluno.append(format_(aluno.get_nee()))
            dados_aluno.append(aluno.get_participacoes_abertas())

            caracterizacao = apps.get_model('ae.Caracterizacao').objects.filter(aluno_id=aluno.id).first()
            if caracterizacao:
                for field in caracterizacao._meta.get_fields():
                    if hasattr(field, 'attname'):
                        attname = field.attname

                        if attname != 'id' and attname != 'aluno_id':
                            if field.is_relation and field.many_to_one:
                                related_obj = getattr(caracterizacao, field.name)
                                valor_display = getattr(related_obj, 'descricao', str(related_obj)) if related_obj else '-'
                            else:
                                valor_display = getattr(caracterizacao, attname)

                            dados_aluno.append(format_(valor_display, False))
            else:
                for _i in range(qtd_campos_caracterizacao):
                    dados_aluno.append('-')

            for _i in range(qtd_periodos_vazio):
                dados_aluno.append('-')
                dados_aluno.append('-')
                dados_aluno.append('-')
                dados_aluno.append('-')

            ano_corrente = datetime.datetime.now().year
            qs_mp = MatriculaPeriodo.objects.filter(aluno_id=aluno.id, ano_letivo__ano__lte=ano_corrente).order_by(
                'ano_letivo__ano', 'periodo_letivo'
            )
            if periodo == 1:
                qs_mp = qs_mp.filter(ano_letivo__ano__gte=ano)
            else:
                qs_mp = qs_mp.filter(ano_letivo__ano__gt=ano) | qs_mp.filter(ano_letivo__ano=ano, periodo_letivo=2)

            for mp in qs_mp:
                if mp.ano_letivo.ano == ano and mp.periodo_letivo == 1 and periodo == 2:
                    continue

                dados_aluno.append(format_(mp.get_ira()))
                dados_aluno.append(f'{format_(mp.get_percentual_carga_horaria_frequentada())}%')
                dados_aluno.append(mp.situacao)
                dados_aluno.append(mp.get_participacoes())

                if aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                    dados_aluno.append('-')
                    dados_aluno.append('-')
                    dados_aluno.append('-')
                    dados_aluno.append('-')

            result.append(dados_aluno)
        return result

    ano_corrente = datetime.datetime.now().year
    key = 0
    PERIODOS = {}
    for ano in range(2015, ano_corrente + 1):
        PERIODOS[key] = f'{ano}.1'
        PERIODOS[key + 1] = f'{ano}.2'
        key += 2
    qtd_periodos_vazio = 0

    dados = []
    cabecalho = [
        'Matrícula',
        'Forma de Ingresso',
        'Código do Curso',
        'Curso',
        'Modalidade',
        'Nível de Ensino',
        'Natureza de Participação',
        'Diretoria',
        'Campus',
        'Situação',
        'Ano Cancelamento/Evasão/Trancamento',
        'Turno',
        'Ano Letivo de Ingresso',
        'Ano Prev. de Conclusão',
        'Ano Letivo de Conclusão',
        'Município de Residência',
        'Zona Residencial',
        'Convênio',
        'Data de Nascimento',
        'Sexo',
        'Necessidades Educacionais Específicas',
        'Participações em Programas Atual',
    ]
    caracterizacao = apps.get_model('ae.Caracterizacao').objects.first()
    qtd_campos_caracterizacao = 0
    for field in caracterizacao._meta.get_fields():
        if hasattr(field, 'verbose_name'):
            if field.attname != 'id' and field.attname != 'aluno_id':
                qtd_campos_caracterizacao += 1
                cabecalho.append(field.verbose_name)
    for key, value in PERIODOS.items():
        cabecalho.append(f'IRA {value}')
        cabecalho.append(f'Frequência {value}')
        cabecalho.append(f'Situação no Período {value}')
        cabecalho.append(f'Participações em Programas no Período {value}')
        if value == f'{ano_ingresso}.{periodo_ingresso}':
            qtd_periodos_vazio = key
    dados.append(cabecalho)
    dados.extend(get_alunos(ano_ingresso, periodo_ingresso, sigla_campus, qtd_campos_caracterizacao, qtd_periodos_vazio, task))
    CsvResponse(dados, processo=task, delimiter=';')


@task('Atualizar Lista de Convocação - ENADE')
def atualizar_lista_convocacao_enade(convocacao_enade, cursos, periodos=None, task=None):
    hoje = datetime.date.today()

    is_avaliacao_teorica = convocacao_enade.is_avaliacao_teorica()
    if is_avaliacao_teorica:
        processa_ingressante = convocacao_enade.data_inscricao_ingressantes and convocacao_enade.data_inscricao_ingressantes >= hoje
        processa_concluinte = convocacao_enade.data_inscricao and convocacao_enade.data_inscricao >= hoje

        if not processa_ingressante and not processa_concluinte:
            return task.finalize(
                'O período de processamento das inscrições de ingressantes e concluintes foi finalizado.',
                f'/edu/convocacao_enade/{convocacao_enade.pk}/',
            )

    situacoes = list(convocacao_enade.situacoes_convocadas.all().values_list('id', flat=True))
    alunos = (
        Aluno.com_matriz.filter(
            matriculaperiodo__ano_letivo_id=convocacao_enade.ano_letivo_id,
            situacao_id__in=situacoes,
            curso_campus_id__in=cursos,
        )
        .exclude(curso_campus__processamento_enade=False)
        .distinct()
    )

    if is_avaliacao_teorica:
        for curso in cursos:
            qs_remocao = RegistroConvocacaoENADE.objects.filter(
                convocacao_enade_id=convocacao_enade.id, aluno__curso_campus_id=curso, situacao__isnull=True
            ).exclude(aluno__situacao_id__in=situacoes)
            if processa_ingressante:
                qs_remocao.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE).delete()
            if processa_concluinte:
                qs_remocao.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE).delete()

        modalidades = {}
        for mce in convocacao_enade.modalidadeconvocacaoenade_set.all():
            modalidades[mce.modalidade_id] = {
                'percentual_minimo_ingressantes': mce.percentual_minimo_ingressantes,
                'percentual_maximo_ingressantes': mce.percentual_maximo_ingressantes,
                'percentual_minimo_concluintes': mce.percentual_minimo_concluintes,
                'percentual_maximo_concluintes': mce.percentual_maximo_concluintes,
            }

        for aluno in task.iterate(alunos):
            percentual_ch_componentes_cumprido = aluno.get_percentual_carga_horaria_cumprida()
            qs_registro = RegistroConvocacaoENADE.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade)
            percentual_minimo_ingressantes = modalidades[aluno.curso_campus.modalidade_id]['percentual_minimo_ingressantes']
            percentual_maximo_ingressantes = modalidades[aluno.curso_campus.modalidade_id]['percentual_maximo_ingressantes']
            percentual_minimo_concluintes = modalidades[aluno.curso_campus.modalidade_id]['percentual_minimo_concluintes']
            percentual_maximo_concluintes = modalidades[aluno.curso_campus.modalidade_id]['percentual_maximo_concluintes']

            if qs_registro.exists():
                obj = qs_registro[0]
                if processa_ingressante:
                    if aluno.ano_letivo_id == convocacao_enade.ano_letivo_id and (
                        percentual_minimo_ingressantes <= percentual_ch_componentes_cumprido <= percentual_maximo_ingressantes
                    ):
                        obj.percentual_ch_cumprida = percentual_ch_componentes_cumprido
                        obj.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE
                        obj.save()
                        continue
                    if obj.tipo_convocacao == RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE:
                        obj.delete()
                        continue
                if processa_concluinte:
                    if percentual_minimo_concluintes <= percentual_ch_componentes_cumprido <= percentual_maximo_concluintes:
                        obj.percentual_ch_cumprida = percentual_ch_componentes_cumprido
                        obj.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
                        obj.save()
                        continue
                    if (
                        obj.tipo_convocacao == RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
                        and not obj.possivel_concluinte
                        and not obj.possivel_integralizado
                    ):
                        obj.delete()
                        continue
            else:
                if processa_ingressante:
                    if aluno.ano_letivo_id == convocacao_enade.ano_letivo_id and (
                        percentual_minimo_ingressantes <= percentual_ch_componentes_cumprido <= percentual_maximo_ingressantes
                    ):
                        RegistroConvocacaoENADE.objects.create(
                            aluno=aluno,
                            convocacao_enade=convocacao_enade,
                            percentual_ch_cumprida=percentual_ch_componentes_cumprido,
                            tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE,
                        )
                        continue
                if processa_concluinte:
                    if percentual_minimo_concluintes <= percentual_ch_componentes_cumprido <= percentual_maximo_concluintes:
                        RegistroConvocacaoENADE.objects.create(
                            aluno=aluno,
                            convocacao_enade=convocacao_enade,
                            percentual_ch_cumprida=percentual_ch_componentes_cumprido,
                            tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE,
                        )
                        continue
                    if convocacao_enade.is_possivel_integralizado(aluno):
                        dados = {
                            'percentual_ch_prevista': aluno.get_percentual_carga_horaria_cumprida(previsao=True),
                            'ch_periodo': aluno.get_ch_componentes_matriz_cursando(),
                            'ch_cumprida': aluno.get_ch_cumprida(),
                        }
                        PossivelIntegralizado.objects.update_or_create(aluno=aluno, convocacao_enade=convocacao_enade, defaults=dados)
                    elif PossivelIntegralizado.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade).exists():
                        PossivelIntegralizado.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade).delete()

                    existe_concluinte = PossivelConcluinte.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade).exists()
                    if convocacao_enade.is_possivel_concluinte(aluno):
                        if not existe_concluinte:
                            PossivelConcluinte.objects.create(aluno=aluno, convocacao_enade=convocacao_enade)
                    elif existe_concluinte:
                        PossivelConcluinte.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade).delete()

    else:
        alunos_convocados_outras_edicoes = (
            RegistroConvocacaoENADE.objects.convocacoes_avaliacao_pratica()
            .exclude(convocacao_enade_id=convocacao_enade.id)
            .values_list('aluno_id', flat=True)
        )
        alunos = alunos.exclude(id__in=alunos_convocados_outras_edicoes)
        for aluno in task.iterate(alunos):
            convocado = False
            qs_estagio = aluno.get_estagios_docentes().only('id')
            if periodos:
                qs_periodos = convocacao_enade.periodoconvocacaoregencia_set.filter(pk__in=periodos.values('pk'))
            else:
                qs_periodos = convocacao_enade.periodoconvocacaoregencia_set.all()
            for periodo in qs_periodos:
                if convocado:
                    continue
                qs_estagio = qs_estagio.filter(
                    matricula_diario__diario__calendario_academico__data_inicio__lte=periodo.data_fim,
                    matricula_diario__diario__calendario_academico__data_fim__gte=periodo.data_inicio,
                )
                estagio = (
                    qs_estagio.filter(
                        matricula_diario__diario__componente_curricular__tipo_estagio_docente__in=[
                            ComponenteCurricular.ESTAGIO_DOCENTE_3,
                            ComponenteCurricular.ESTAGIO_DOCENTE_4,
                        ]
                    )
                    .order_by('matricula_diario__diario__componente_curricular__tipo_estagio_docente')
                    .first()
                )

                if estagio:
                    convocacao = RegistroConvocacaoENADE.objects.filter(aluno=aluno, convocacao_enade=convocacao_enade).first()
                    if convocacao:
                        if convocacao.situacao != RegistroConvocacaoENADE.SITUACAO_PRESENTE:
                            convocacao.percentual_ch_cumprida = aluno.get_percentual_carga_horaria_cumprida()
                            convocacao.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
                            convocacao.periodo_convocacao_regencia_id = periodo.id
                            convocacao.estagio_docente_id = estagio.id
                            convocacao.save()
                    else:
                        RegistroConvocacaoENADE.objects.create(
                            aluno=aluno,
                            convocacao_enade=convocacao_enade,
                            percentual_ch_cumprida=aluno.get_percentual_carga_horaria_cumprida(),
                            tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP,
                            periodo_convocacao_regencia=periodo,
                            estagio_docente_id=estagio.id,
                        )
                    convocado = True

    task.finalize('Lista de convocados atualizada com sucesso.', f'/edu/convocacao_enade/{convocacao_enade.pk}/')


@task('Dispensar não convocados - ENADE')
def dispensar_nao_convocados_enade(convocacao_enade, task=None):
    alunos = Aluno.com_matriz.filter(
        ano_letivo_id=convocacao_enade.ano_letivo_id,
        curso_campus__in=convocacao_enade.get_pk_cursos_nao_convocados(),
        curso_campus__justificativa_dispensa_ingressante_id__isnull=False,
    )
    for aluno in task.iterate(alunos):
        qs = RegistroConvocacaoENADE.objects.filter(aluno=aluno, convocacao_enade_id=convocacao_enade.pk)
        if qs.exists():
            registro = qs[0]
        else:
            registro = RegistroConvocacaoENADE()
            registro.aluno = aluno
            registro.convocacao_enade = convocacao_enade
            registro.percentual_ch_cumprida = aluno.get_percentual_carga_horaria_cumprida()

        registro.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE
        registro.situacao = RegistroConvocacaoENADE.SITUACAO_DISPENSADO
        registro.justificativa_dispensa_id = aluno.curso_campus.justificativa_dispensa_ingressante_id
        registro.save()
    task.finalize('Ingressantes dispensados com sucesso.', f'/edu/convocacao_enade/{convocacao_enade.pk}/')


@task('Exportar Alunos - XLS')
def exportar_listagem_alunos_xls(
    request, alunos, campos_exibicao, cabecalhos, filtros=(), ano_letivo=None, periodo_letivo=None, is_matricula_periodo=False, task=None
):
    count = 0
    rows = [['#', 'Matrícula', 'Nome']]
    if is_matricula_periodo:
        rows[0].append('Ano Letivo de Referência')
    for campo in campos_exibicao:
        for label in cabecalhos:
            if label[0] == campo:
                rows[0].append(format_(label[1], html=False))
    task.count(alunos, alunos)
    for obj in task.iterate(alunos):
        aluno = obj.aluno if is_matricula_periodo else obj
        if ano_letivo and periodo_letivo:
            aluno.ano_letivo_referencia = ano_letivo
            aluno.periodo_letivo_referencia = periodo_letivo
        count += 1
        row = [
            count,
            format_(aluno.getattr('matricula', request, justification='txt'), html=False),
            format_(aluno.getattr('get_nome_social_composto', request), html=False),
        ]
        if is_matricula_periodo:
            row.append(obj.ano_letivo.ano)
        for campo in campos_exibicao:
            row.append(format_(aluno.getattr(campo, request), html=False))
        rows.append(row)
    rows_filtros = [['FILTROS']]
    for filtro in filtros:
        rows_filtros.append([filtro.get('chave'), filtro.get('valor')])
    if len(rows) >= 65536:
        CsvResponse(rows, processo=task)
    else:
        XlsResponse({'Registros': rows, 'Filtros': rows_filtros} if filtros else rows, processo=task)


@task('Exportar relatório de coordenação de cursos')
def exportar_relatorio_coordenacao_curso(request, cursos_id, task=None):
    rows = [
        [
            '#',
            'Código',
            'Curso',
            'Ativo',
            'Diretoria',
            'Modalidade',
            'Coordenador',
            'Email do coordenador',
            'Coordenador substituto',
            'Email do coordenador substituto',
        ]
    ]

    count = 0
    for curso in task.iterate(CursoCampus.objects.filter(id__in=cursos_id.split('_'))):
        count += 1
        coordenador_nome = f'{curso.coordenador.nome_usual}' if curso.coordenador else '-'
        coordenador_email = curso.coordenador.email_notificacao if curso.coordenador else '-'
        coordenador_2_nome = f'{curso.coordenador_2.nome_usual}' if curso.coordenador_2 else '-'
        coordenador_2_email = curso.coordenador_2.email_notificacao if curso.coordenador_2 else '-'

        row = [
            count,
            format_(curso.codigo),
            format_(curso.descricao_historico),
            format_('Sim' if curso.ativo else 'Não'),
            format_(curso.diretoria),
            format_(curso.modalidade),
            format_(coordenador_nome),
            format_(coordenador_email),
            format_(coordenador_2_nome),
            format_(coordenador_2_email),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Auditoria Censos')
def exportar_auditoria_censos(tipo, uo, curso, nivel_ensino, modalidade, situacao, cpf_operador, task=None):
    rows = []
    qs = Aluno.objects.all()
    if uo:
        qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
    if curso:
        qs = qs.filter(curso_campus=curso)
    if nivel_ensino:
        qs = qs.filter(curso_campus__modalidade__nivel_ensino__in=nivel_ensino)
    if modalidade:
        qs = qs.filter(curso_campus__modalidade__in=modalidade)
    if situacao:
        qs = qs.filter(situacao__in=situacao)

    if tipo == 1:  # Dados Divergentes com a Receita Federal
        rows.append(['Auditoria', 'CPF', 'Matrícula', 'Nome SUAP', 'Nome RF', 'Nascimento SUAP', 'Nascimento RF', 'Mãe SUAP', 'Mãe RF'])
        for aluno in task.iterate(qs):
            try:
                dados_rf = aluno.get_dados_receita_federal()
                row = [
                    'Dados Divergentes com a Receita Federal',
                    format_(aluno.pessoa_fisica.cpf),
                    format_(aluno.matricula),
                ]
                if aluno.pessoa_fisica.nome_registro != dados_rf['Nome']:
                    row.append(aluno.pessoa_fisica.nome_registro)
                    row.append(dados_rf['Nome'])
                else:
                    row.append('-')
                    row.append('-')
                nascimento_suap = re.sub(r'\D', '', str(aluno.pessoa_fisica.nascimento_data))
                nascimento_rf = re.sub(r'\D', '', str(dados_rf['DataNascimento']))
                if nascimento_suap != nascimento_rf:
                    row.append(f'{nascimento_suap[6:8]}/{nascimento_suap[4:6]}/{nascimento_suap[0:4]}')
                    row.append(f'{nascimento_rf[6:8]}/{nascimento_rf[4:6]}/{nascimento_rf[0:4]}')
                else:
                    row.append('-')
                    row.append('-')
                if aluno.nome_mae != dados_rf['NomeMae']:
                    row.append(aluno.nome_mae)
                    row.append(dados_rf['NomeMae'])
                else:
                    row.append('-')
                    row.append('-')
                rows.append(row)
            except Exception:
                continue

    elif tipo == 2:  # Matrículas na mesma Modalidade
        rows.append(['Auditoria', 'CPF', 'Matrícula', 'Nome', 'Modalidade', 'Situação', 'Curso'])
        qs = qs.values('curso_campus__modalidade', 'pessoa_fisica__cpf').annotate(count=Count('curso_campus__modalidade'))
        for q in task.iterate(qs):
            if q['count'] > 1:
                alunos = Aluno.objects.filter(
                    situacao__in=situacao, pessoa_fisica__cpf=q['pessoa_fisica__cpf'], curso_campus__modalidade_id=q['curso_campus__modalidade']
                ).values(
                    'matricula',
                    'pessoa_fisica__cpf',
                    'pessoa_fisica__nome_registro',
                    'curso_campus__modalidade__descricao',
                    'situacao__descricao',
                    'curso_campus__descricao',
                )
                for aluno in alunos:
                    row = [
                        'Matrículas na mesma Modalidade',
                        format_(aluno['pessoa_fisica__cpf']),
                        format_(aluno['matricula']),
                        format_(aluno['pessoa_fisica__nome_registro']),
                        format_(aluno['curso_campus__modalidade__descricao']),
                        format_(aluno['situacao__descricao']),
                        format_(aluno['curso_campus__descricao']),
                    ]
                    rows.append(row)
    else:  # Nome com Pontuação/Caracter Especial
        rows.append(['Auditoria', 'CPF', 'Matrícula', 'Nome', 'Campus', 'Diretoria', 'Curso'])
        for aluno in task.iterate(qs):
            nome = aluno.pessoa_fisica.nome_registro
            if re.search(r'\W', nome.replace(' ', '')):
                row = [
                    'Nome com Pontuação/Caracter Especial',
                    format_(aluno.pessoa_fisica.cpf),
                    format_(aluno.matricula),
                    format_(nome),
                    format_(aluno.curso_campus.diretoria.setor.uo),
                    format_(aluno.curso_campus.diretoria),
                    format_(aluno.curso_campus),
                ]
                rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Processar questão EDUCACENSO')
@transaction.atomic()
def processar_questao_educacenso(questao, criar_respostas, task=None):
    from edu.models import RegistroEducacenso, RespostaEducacenso
    from rh.models import UnidadeOrganizacional

    total = 3
    i = 1
    if criar_respostas:
        total += UnidadeOrganizacional.objects.campi().all().count()
    task.start_progress(total=total)
    task.update_progress(i)
    if criar_respostas:
        for uo in UnidadeOrganizacional.objects.campi().all():
            RespostaEducacenso.objects.get_or_create(questao_id=questao.id, campus_id=uo.id)
            i += 1
            task.update_progress(i)
    task.update_progress(i + 1)
    RegistroEducacenso.atualizar_numero_campo(questao)
    task.update_progress(i + 2)
    task.finalize('Processamento realizado com sucesso', f'/edu/registroeducacenso/{questao.registro_id}/')


@task('Clonar registro EDUCACENSO')
def clonar_registro_educacenso(registro, ano_censo, copiar_respostas, task=None):
    import copy

    from edu.models import RespostaEducacenso
    from rh.models import UnidadeOrganizacional

    task.count(registro.questaoeducacenso_set.all())

    questionario = copy.copy(registro)
    questionario.id = None
    questionario.numero_registro = f'{registro.numero_registro} [CLONADO]'
    questionario.ano_censo = ano_censo
    questionario.privado = True
    questionario.save()

    for questao in task.iterate(registro.questaoeducacenso_set.all()):
        questao_copy = copy.copy(questao)
        questao_copy.id = None
        questao_copy.registro = questionario
        questao_copy.save()

        if copiar_respostas:
            for resposta in questao.respostaeducacenso_set.all():
                resposta_copy = copy.copy(resposta)
                resposta_copy.situacao = RespostaEducacenso.SITUACAO_AGUARDANDO
                resposta_copy.id = None
                resposta_copy.questao = questao_copy
                resposta_copy.save()
        else:
            for uo in UnidadeOrganizacional.objects.campi().all():
                RespostaEducacenso.objects.get_or_create(questao_id=questao_copy.id, campus_id=uo.id)

    task.finalize('Processamento realizado com sucesso', f'/edu/registroeducacenso/{questionario.id}/')


@task('Atualizar Código do Aluno - EDUCACENSO')
def atualizar_codigo_educacenso(registros, task=None):
    def _similaridade(a, b):
        tamanho = min(len(a), len(b))
        a = a[:tamanho]
        b = b[:tamanho]
        return similaridade(a, b)

    lista = []
    for line in task.iterate(registros):
        if isinstance(line, bytes):
            try:
                line = line.decode('utf-8')
            except UnicodeDecodeError:
                line = line.decode('latin-1', errors='replace')
        line = line.strip()
        if '|' not in line:
            if line:
                lista.append(f'Formato inválido: {line}')
            continue
        tokens = line.split('|')
        matricula = tokens[0].strip()
        cpf = mask_cpf(tokens[1].strip())
        codigo_educacenso = tokens[-1].strip()

        qs_aluno = (
            Aluno.objects.filter(matricula=matricula)
            .select_related('pessoa_fisica')
            .only('nome_mae', 'pessoa_fisica__nome_mae', 'nome_pai', 'pessoa_fisica__nome_pai', 'pessoa_fisica__nome')
        )

        if qs_aluno.filter(pessoa_fisica__cpf=cpf).exists():
            qs_aluno.update(codigo_educacenso=codigo_educacenso)
        else:
            if len(tokens) < 7:
                lista.append(f'Formato inválido: {line}')
                continue
            nome_mae = tokens[5].strip()
            nome_pai = tokens[6].strip()
            try:
                nascimento_data = datetime.datetime.strptime(tokens[4], '%d/%m/%Y')
            except ValueError:
                lista.append(f'{matricula}||{nome_mae}|{codigo_educacenso}||||||')
                continue

            aluno = qs_aluno.filter(pessoa_fisica__nascimento_data=nascimento_data).first()
            if aluno:
                nome_mae1 = (
                    to_ascii(aluno.nome_mae or aluno.pessoa_fisica.nome_mae or '').upper().replace('.', '').replace("'", '').replace('-', '').strip()
                )
                nome_pai1 = (
                    to_ascii(aluno.nome_pai or aluno.pessoa_fisica.nome_pai or '').upper().replace('.', '').replace("'", '').replace('-', '').strip()
                )
                if nome_mae == nome_mae1:
                    qs_aluno.update(codigo_educacenso=codigo_educacenso)
                else:
                    similaridade_nome_mae = _similaridade(nome_mae, nome_mae1)
                    similaridade_nome_pai = nome_pai and nome_pai1 and _similaridade(nome_pai, nome_pai1) or 0
                    if similaridade_nome_mae > 0.8 or (similaridade_nome_mae > 0.5 and similaridade_nome_pai > 0.7):
                        qs_aluno.update(codigo_educacenso=codigo_educacenso)
                    else:
                        lista.append(
                            f'{matricula}|{aluno.pessoa_fisica.nome}|{nome_mae}|{codigo_educacenso}|{nome_mae}|{nome_mae1}|{similaridade_nome_mae}|{nome_pai}|{nome_pai1}|{similaridade_nome_pai}'
                        )
            else:
                lista.append(f'{matricula}||{nome_mae}|{codigo_educacenso}||||||')
    if lista:
        output = tempfile.NamedTemporaryFile(mode='w', dir=os.path.join(settings.TEMP_DIR), delete=False, suffix='.txt')
        output.write('\r\n'.join(lista))
        output.close()
        task.finalize(
            'Processamento realizado parcialmente. Gerado arquivo de registros não encontrados ou formatação inválida.',
            '/edu/atualizar_codigo_educacenso/',
            file_path=output.name,
        )
    else:
        task.finalize('Processamento realizado com sucesso', '/edu/atualizar_codigo_educacenso/')


@task('Exportar Dados - CENSUP')
def exportar_dados_censup(tipo, ano, uos, amostra, cpfs, ignorar_cpfs, ignorar_data_conclusao, task=None):
    censup.Exportador(
        tipo, ano, uos=uos, amostra=amostra, cpfs=cpfs, ignorar_cpfs=ignorar_cpfs, ignorar_data_conclusao=ignorar_data_conclusao, task=task
    )


@task('Exportar Dados - EDUCACENSO (Primeira Etapa)')
def exportar_dados_educacenso(ano, uo, validar_alunos, ignorar_erros, ignorar_matriculas, filtrar_matriculas, inferir_turma, partiu_if, task=None):
    educacenso.Exportador(ano, uo, validar_alunos, ignorar_erros, ignorar_matriculas, filtrar_matriculas, inferir_turma, partiu_if, task=task)


@task('Exportar Dados - EDUCACENSO (Segunda Etapa)')
def exportar_dados_educacenso2(ano, uo, ignorar_erros, task=None):
    educacenso.ExportadorEtapa2(ano, uo, ignorar_erros, task=task)


@task('Importar Dados - EDUCACENSO (Segunda Etapa)')
def importar_dados_educacenso2(ano_letivo, conteudo, task=None):
    matriculas_periodo = {}
    lines = conteudo.split('\n')
    for line in task.iterate(lines):
        line = line.strip()
        if line.startswith('30|'):
            line30 = line.split('|')
            codigo_educacenso = line30[3]
            matricula = line30[2]
            nis = line30[38]
            qs = Aluno.objects.filter(matricula=matricula)
            if qs.exists():
                qs.update(codigo_educacenso=codigo_educacenso, nis=nis)
                matricula_periodo = MatriculaPeriodo.objects.filter(aluno__matricula=matricula, ano_letivo=ano_letivo, periodo_letivo=1).first()
                matriculas_periodo[codigo_educacenso] = matricula_periodo
            else:
                cpf = line30[4]
                if cpf.strip():
                    cpf = mask_cpf(cpf)
                codigo_educacenso_campus = line30[1]
                qs_matricula_periodo = MatriculaPeriodo.objects.filter(
                    aluno__pessoa_fisica__cpf=cpf,
                    aluno__curso_campus__diretoria__setor__uo__codigo_inep=codigo_educacenso_campus,
                    aluno__curso_campus__modalidade__in=(
                        Modalidade.INTEGRADO,
                        Modalidade.INTEGRADO_EJA,
                        Modalidade.FIC_INTEGRADO_EJA,
                        Modalidade.SUBSEQUENTE,
                        Modalidade.CONCOMITANTE,
                        Modalidade.PROEJA_FIC_FUNDAMENTAL,
                    ),
                    ano_letivo=ano_letivo,
                    periodo_letivo=1,
                )
                if qs_matricula_periodo.count() == 1:
                    matricula_periodo = qs_matricula_periodo.first()
                    Aluno.objects.filter(pk=matricula_periodo.aluno_id).update(codigo_educacenso=codigo_educacenso, nis=nis)
                    matriculas_periodo[codigo_educacenso] = matricula_periodo
                else:
                    continue
        if line.startswith('60|'):
            line60 = line.split('|')
            codigo_educacenso = line60[3]
            codigo_educacenso_periodo = line60[6]
            codigo_educacenso_turma = line60[5]
            matricula_periodo = matriculas_periodo.get(codigo_educacenso)
            if matricula_periodo:
                matricula_periodo.codigo_educacenso = codigo_educacenso_periodo
                matricula_periodo.save()
                if matricula_periodo.turma_id:  # and not matricula_periodo.turma.codigo_educacenso
                    matricula_periodo.turma.codigo_educacenso = codigo_educacenso_turma
                    matricula_periodo.turma.save()
    task.finalize('Arquivo processado com sucesso.', '..')


@task('Exportar Alunos sem Código - EDUCACENSO')
def exportar_alunos_sem_codigo_educacenso(ano, task=None):
    educacenso.ExportadorAlunosSemCodigo(ano, task=task)


@task('Processar Pedidos de Matrícula')
def processar_pedidos_matricula(self, task=None):
    # Pedidos de matrícula do seriado (turma selecionada)
    pedidos_matricula_por_ira = (
        self.pedidomatricula_set.filter(pedidomatriculadiario__isnull=False, turma__isnull=False)
        .distinct()
        .order_by('-matricula_periodo__aluno__ira')
    )
    # Pedidos de matrícula do crédito e dependencia do seriado (diario selecionado)
    diarios_pedidos_pendentes = Diario.objects.filter(
        pedidomatriculadiario__pedido_matricula__configuracao_pedido_matricula=self, pedidomatriculadiario__data_processamento__isnull=True
    ).distinct()
    # Pedidos sem seleção de turma ou seriado
    pedidos_matricula_vinculo = self.pedidomatricula_set.exclude(matricula_periodo__matriculadiario__isnull=False)

    task.count(pedidos_matricula_por_ira, diarios_pedidos_pendentes, pedidos_matricula_vinculo)

    def do():
        try:
            sid = transaction.savepoint()
            # APENAS SERIADO INICIO
            # percorrendo os pedidos que possuem turma e pedidos de diários ordenados pelo ira e inserindo na turma e nos diários dela os alunos que não mudaram de turma
            pedidos_mudanca_turma = []
            for pedido_matricula in task.iterate(pedidos_matricula_por_ira):
                ultima_turma_cursada = pedido_matricula.matricula_periodo.aluno.get_ultima_turma_cursada()
                turma_solicitada = pedido_matricula.turma
                pedidos_matricula_diario_turma = pedido_matricula.pedidomatriculadiario_set.filter(diario__turma=turma_solicitada)
                matricular = False
                if ultima_turma_cursada:
                    if pedido_matricula.matricula_periodo.aluno.situacao_id not in [
                        SituacaoMatricula.MATRICULADO,
                        SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                        SituacaoMatricula.TRANCADO,
                        SituacaoMatricula.INTERCAMBIO,
                        SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                    ]:
                        pedidos_matricula_diario_turma.update(
                            deferido=False, motivo=PedidoMatriculaDiario.MOTIVO_MATRICULA_INATIVA, data_processamento=datetime.date.today()
                        )

                    elif ultima_turma_cursada.sequencial == turma_solicitada.sequencial:
                        # mesma_turma
                        matricular = True
                    else:
                        # mudanca_turma
                        pedidos_mudanca_turma.append(pedido_matricula)
                else:
                    # alunos integralizados do Q-Acadêmico sem turma na última matrícula período
                    if pedido_matricula.matricula_periodo.situacao_id not in [
                        SituacaoMatriculaPeriodo.MATRICULADO,
                        SituacaoMatriculaPeriodo.EM_ABERTO,
                        SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                    ]:
                        pedidos_matricula_diario_turma.update(
                            deferido=False, motivo=PedidoMatriculaDiario.MOTIVO_MATRICULA_INATIVA, data_processamento=datetime.date.today()
                        )
                    elif turma_solicitada.get_alunos_matriculados().count() < turma_solicitada.quantidade_vagas:
                        matricular = True
                    else:
                        # indeferindo devido ao ira
                        pedidos_matricula_diario_turma.update(
                            deferido=False, motivo=PedidoMatriculaDiario.MOTIVO_IRA, data_processamento=datetime.date.today()
                        )

                if matricular:
                    # matriculando na turma
                    pedido_matricula.matricular_na_turma()

                    # matriculando nos diários da turma acima
                    for pedido_matricula_diario in pedidos_matricula_diario_turma:
                        pedido_matricula_diario.matricular_no_diario(PedidoMatriculaDiario.MOTIVO_PERIODIZADO)

            # verificando se os alunos que solicitaram mudança de turma terão direito a vaga
            for pedido_matricula in pedidos_mudanca_turma:
                turma_solicitada = pedido_matricula.turma
                pedidos_matricula_diario_turma_solicitada = pedido_matricula.pedidomatriculadiario_set.filter(diario__turma=turma_solicitada)

                if pedido_matricula.matricula_periodo.situacao_id not in [
                    SituacaoMatriculaPeriodo.MATRICULADO,
                    SituacaoMatriculaPeriodo.EM_ABERTO,
                    SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                ]:
                    pedidos_matricula_diario_turma_solicitada.update(
                        deferido=False, motivo=PedidoMatriculaDiario.MOTIVO_MATRICULA_INATIVA, data_processamento=datetime.date.today()
                    )
                elif turma_solicitada.get_alunos_matriculados().count() < turma_solicitada.quantidade_vagas:
                    # matriculando na turma
                    pedido_matricula.matricular_na_turma()

                    # matriculando nos diários
                    for pedido_matricula_diario in pedidos_matricula_diario_turma_solicitada:
                        pedido_matricula_diario.matricular_no_diario(PedidoMatriculaDiario.MOTIVO_IRA)
                else:
                    # indeferindo mudança de turma
                    pedidos_matricula_diario_turma_solicitada.update(
                        deferido=False, motivo=PedidoMatriculaDiario.MOTIVO_IRA, data_processamento=datetime.date.today()
                    )
            # APENAS SERIADO FIM

            # CRÉDITO E DEPÊNDENCIAS DO SERIADO INICIO
            # Indeferindo requerimentos que não foram analisados no prazo.
            if datetime.date.today() > self.data_fim:
                ids_requerimentos_quebra_requisito = list(
                    self.pedidomatricula_set.values_list('requerimentos_matricula_quebra_de_requisito__pk', flat=True)
                )
                ids_requerimentos_aumento_ch = list(self.pedidomatricula_set.values_list('requerimentos_matricula_com_aumento_ch__pk', flat=True))
                requerimentos_pendentes = Requerimento.objects.filter(
                    tipo__in=[Requerimento.MATRICULA_QUEBRA_REQUISITO, Requerimento.MATRICULA_QUEBRA_CH_MAX],
                    deferido__isnull=True,
                    pk__in=set(ids_requerimentos_quebra_requisito + ids_requerimentos_aumento_ch),
                )

                for requerimento in requerimentos_pendentes:
                    requerimento.observacao = 'Pedido indeferido devido à ausência de análise antes do processamento da renovação de matrícula.'
                    requerimento.indeferir()

            # obtendo os diarios com pedido pendentes
            for diario in task.iterate(diarios_pedidos_pendentes):
                # obtendo os pedidos pendentes deste diario e adicionando o atributo prioridade_periodo
                pedidos_pendentes = diario.pedidomatriculadiario_set.filter(
                    pedido_matricula__configuracao_pedido_matricula=self, data_processamento__isnull=True
                )
                pedidos_prioridade_periodo = []
                for pedido in pedidos_pendentes:
                    # tratando prioridade para optativos
                    prioridade_periodo = 1
                    if not pedido.diario.componente_curricular.optativo:
                        prioridade_periodo = abs(
                            pedido.pedido_matricula.matricula_periodo.aluno.periodo_atual - pedido.diario.componente_curricular.periodo_letivo
                        )

                    pedido.prioridade_periodo = prioridade_periodo
                    pedido.ira = pedido.pedido_matricula.matricula_periodo.aluno.ira
                    pedidos_prioridade_periodo.append(pedido)

                # ordenando a lista pedidos_prioridade por prioridade_periodo, -ira
                pedidos_prioridade_periodo = sorted(pedidos_prioridade_periodo, key=operator.attrgetter('prioridade_periodo'))
                pedidos_prioridade_periodo = sorted(pedidos_prioridade_periodo, key=operator.attrgetter('ira'), reverse=True)

                # percorrendo lista ordenada para deferimento e indeferimento
                for pedido_matricula_diario in pedidos_prioridade_periodo:
                    # aluno do pedido esta no mesmo periodo do componente curricular
                    motivo = PedidoMatriculaDiario.MOTIVO_PERIODO_IRA
                    if pedido_matricula_diario.prioridade_periodo == 0:
                        motivo = PedidoMatriculaDiario.MOTIVO_PERIODIZADO

                    if pedido_matricula_diario.pedido_matricula.matricula_periodo.situacao_id not in [
                        SituacaoMatriculaPeriodo.MATRICULADO,
                        SituacaoMatriculaPeriodo.EM_ABERTO,
                        SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                    ]:
                        pedido_matricula_diario.indeferir(PedidoMatriculaDiario.MOTIVO_MATRICULA_INATIVA)
                    elif pedido_matricula_diario.diario.matriculadiario_set.all().count() < pedido_matricula_diario.diario.quantidade_vagas:
                        # matriculando no diário
                        pedido_matricula_diario.matricular_no_diario(motivo)
                    else:
                        # indeferindo
                        pedido_matricula_diario.indeferir(motivo)

            # CRÉDITO E DEPÊNDENCIAS DO SERIADO FIM

            # alunos que realizaram pedidos de matrícula e que não houve deferimento em nenhum diário
            pedidos_matricula_vinculo = self.pedidomatricula_set.exclude(matricula_periodo__matriculadiario__isnull=False)
            for pedido_matricula_vinculo in task.iterate(pedidos_matricula_vinculo):
                if pedido_matricula_vinculo.matricula_periodo.situacao_id in [
                    SituacaoMatriculaPeriodo.MATRICULADO,
                    SituacaoMatriculaPeriodo.EM_ABERTO,
                    SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                ]:
                    try:
                        deve_impedir_matricula_vinculo = pedido_matricula_vinculo.matricula_periodo.aluno.deve_impedir_matricula_vinculo()
                        if deve_impedir_matricula_vinculo:
                            pedido_matricula_vinculo.motivo_impedimento_matricula_vinculo = deve_impedir_matricula_vinculo
                            pedido_matricula_vinculo.save()
                        else:
                            pedido_matricula_vinculo.matricula_periodo.matricula_vinculo()
                    except IntegrityError as e:
                        capture_exception(e)
                    except ValidationError as e:
                        capture_exception(e)

            ids_matriculas_diarios_cancelados = self.pedidomatricula_set.filter(
                matriculas_diario_canceladas__situacao=MatriculaDiario.SITUACAO_CURSANDO
            ).values_list('matriculas_diario_canceladas', flat=True)
            for matricula_diario in MatriculaDiario.objects.filter(id__in=ids_matriculas_diarios_cancelados):
                try:
                    matricula_diario.cancelar()
                except ValidationError as e:
                    capture_exception(e)

            transaction.savepoint_commit(sid)
            task.finalize('Pedidos de matrícula processados com sucesso.', f'/edu/configuracao_pedido_matricula/{self.pk}/?tab=monitoramento')
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e

    do()


@task('Auditoria SISTEC -> SUAP')
def exportar_sistec_suap(planilha_path, campus, task=None):
    """Exporta dados de alunos do SUAP para auditoria no SISTEC.

    Args:
        planilha_path: caminho do arquivo de planilha SISTEC.
        campus: objeto do campus para filtrar os dados.
        task: objeto de task assíncrona para controle de progresso.
    """
    import pandas as pd

    storage = get_temp_storage()
    retry = 0
    while not storage.exists(planilha_path) and retry < 60:
        sleep(2)
        retry += 1
    with open(planilha_path, 'wb') as local:
        local.write(storage.open(planilha_path).read())
    rows = list(csv.DictReader(open(planilha_path, encoding='iso-8859-1'), delimiter=';'))

    output_data = []

    for data in task.iterate(rows):
        row_data = data.copy()

        try:
            coluna_busca = data['NO_STATUS_MATRICULA']
            coluna_cpf_aluno = data['NU_CPF']
            coluna_codigo_curso = int(data['CO_CURSO'])
            coluna_data_inicio = data['DT_DATA_INICIO']

            campo = coluna_busca
            codigo_curso = int(coluna_codigo_curso)
            codigo_unidade = campus.codigo_sistec

            # tratando data caso venha no formato dd/mm/yyyy ou yyyy-mm-dd
            if '/' in coluna_data_inicio:
                day, month, year = list(map(int, coluna_data_inicio.split(' ')[0].split('/')))
            else:
                year, month, day = list(map(int, coluna_data_inicio.split(' ')[0].split('-')))

            data_inicio = datetime.datetime(year, month, day)

            # Tratando o CPF - Se CPF vier mascarado retira a máscara e aplica novamente
            cpf_aluno = str(coluna_cpf_aluno).replace('.', '').replace('-', '')
            cpf_aluno = str(int(cpf_aluno))
            cpf_aluno = cpf_aluno.rjust(11, '0')
            cpf_aluno = mask_cpf(cpf_aluno)

            row_data['SITUACAO_NO_SISTEC'] = coluna_busca

            qs_aluno = Aluno.objects.filter(pessoa_fisica__cpf=cpf_aluno, curso_campus__diretoria__setor__uo__codigo_sistec=codigo_unidade)
            qs_aluno = (
                qs_aluno.filter(curso_campus__codigo_sistec=codigo_curso)
                or qs_aluno.filter(curso_campus__codigo_sistec__contains=f';{codigo_curso};')
                or qs_aluno.filter(curso_campus__codigo_sistec__startswith=f'{codigo_curso};')
                or qs_aluno.filter(curso_campus__codigo_sistec__endswith=f';{codigo_curso}')
            )
            if qs_aluno.count() == 1:
                aluno = qs_aluno[0]
            else:
                aluno = qs_aluno.get(ano_letivo__ano=data_inicio.year)

            row_data['SITUACAO_NO_SUAP'] = str(aluno.situacao).upper()

            # Calculando o valor do campo de comparação
            valor_campo_comparacao = ''
            if aluno.situacao.pk in [SituacaoMatricula.EVASAO, SituacaoMatricula.NAO_CONCLUIDO]:
                valor_campo_comparacao = ['ABANDONO', 'DESLIGADO']
            elif aluno.situacao.pk in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]:
                valor_campo_comparacao = ['CONCLUÍDA']
            elif aluno.situacao.pk in [
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.JUBILADO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                SituacaoMatricula.FALECIDO,
                SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            ]:
                valor_campo_comparacao = ['ABANDONO', 'DESLIGADO']
            elif aluno.situacao.pk in [
                SituacaoMatricula.MATRICULADO,
                SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                SituacaoMatricula.INTERCAMBIO,
                SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                SituacaoMatricula.TRANCADO,
            ]:
                valor_campo_comparacao = ['EM_CURSO']
            elif aluno.situacao.pk in [
                SituacaoMatricula.CONCLUDENTE,
                SituacaoMatricula.ESTAGIARIO_CONCLUDENTE,
                SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
                SituacaoMatricula.AGUARDANDO_ENADE,
                SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO,
            ]:
                valor_campo_comparacao = ['INTEGRALIZADA']
            elif aluno.situacao.pk == SituacaoMatricula.TRANSFERIDO_EXTERNO:
                valor_campo_comparacao = ['TRANSF_EXT']
            elif aluno.situacao.pk == SituacaoMatricula.TRANSFERIDO_INTERNO:
                qs = (
                    Aluno.objects.filter(
                        pessoa_fisica__cpf=aluno.pessoa_fisica.cpf,
                        curso_campus__modalidade=aluno.curso_campus.modalidade,
                        ano_letivo__gte=aluno.ano_letivo,
                    )
                    .exclude(pk=aluno.pk)
                    .exclude(curso_campus__diretoria__setor__uo=aluno.curso_campus.diretoria.setor.uo)
                    .order_by('-ano_letivo__ano')
                )
                if qs.exists():
                    valor_campo_comparacao = ['TRANSF_EXT']
                else:
                    valor_campo_comparacao = ['TRANSF_INT']
            elif campo == 'REPROVADO':
                valor_campo_comparacao = ['MATRICULADO']

            if campo in valor_campo_comparacao:
                row_data['COMPARACAO'] = 'CONVERGENTE'
            else:
                row_data['COMPARACAO'] = 'DIVERGENTE'

            # Adicionando a Diretoria do aluno
            row_data['DIRETORIA'] = str(aluno.curso_campus.diretoria)

        except Aluno.DoesNotExist:
            row_data['SITUACAO_NO_SUAP'] = 'NÃO LOCALIZADO'
            row_data['COMPARACAO'] = 'NÃO LOCALIZADO'
            row_data['DIRETORIA'] = 'NÃO LOCALIZADO'
        except Aluno.MultipleObjectsReturned:
            aluno = qs_aluno.first()
            row_data['SITUACAO_NO_SUAP'] = 'VERIFICAR'
            row_data['COMPARACAO'] = 'VERIFICAR'
            row_data['DIRETORIA'] = str(aluno.curso_campus.diretoria)
        except Exception:
            pass

        output_data.append(row_data)

    df = pd.DataFrame(output_data)

    response = tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False)
    df.to_excel(response.name, index=False, sheet_name='Alunos')
    response.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)


def _parse_data_planilha_sistec(data_str: str | None) -> datetime.date | None:
    if not data_str:
        return None
    data_limpa = str(data_str).strip().split(' ')[0]
    if not data_limpa:
        return None
    try:
        if '/' in data_limpa:
            day, month, year = map(int, data_limpa.split('/'))
        elif '-' in data_limpa:
            year, month, day = map(int, data_limpa.split('-'))
        else:
            return None
        return datetime.date(year, month, day)
    except ValueError, IndexError:
        return None


def _curso_tem_codigo_sistec(campo_codigo_sistec: str | None, codigo_procurado: int) -> bool:
    if not campo_codigo_sistec:
        return False
    return str(codigo_procurado) in {p.strip() for p in campo_codigo_sistec.split(';') if p.strip()}


def _carregar_codigos_sistec_cursos() -> set[int]:
    codigos: set[int] = set()
    valores = CursoCampus.objects.exclude(codigo_sistec__isnull=True).exclude(codigo_sistec='').values_list('codigo_sistec', flat=True)
    for cod_str in valores:
        for parte in str(cod_str).split(';'):
            parte = parte.strip()
            if parte.isdigit():
                codigos.add(int(parte))
    return codigos


def _extrair_identificadores_planilha(
    rows: list[dict[str, Any]],
) -> tuple[set[str], set[str], set[datetime.date], set[tuple[str, datetime.date]]]:
    matriculas: set[str] = set()
    cpfs: set[str] = set()
    nomes_nasc_datas: set[datetime.date] = set()
    nomes_nasc_pares: set[tuple[str, datetime.date]] = set()

    for r in rows:
        mat = r.get('MATRICULA')
        if mat:
            matriculas.add(str(mat).strip())
        cpf = r.get('NU_CPF')
        cpf_limpo = str(cpf).replace('.', '').replace('-', '').strip() if cpf else ''
        if cpf_limpo:
            cpfs.add(mask_cpf(cpf_limpo.zfill(11)))
        else:
            nome = str(r.get('NO_ALUNO', '')).strip().lower()
            dt_nasc = _parse_data_planilha_sistec(r.get('DT_DATA_NASCIMENTO'))
            if nome and dt_nasc:
                nomes_nasc_datas.add(dt_nasc)
                nomes_nasc_pares.add((nome, dt_nasc))

    return matriculas, cpfs, nomes_nasc_datas, nomes_nasc_pares


def _precarregar_alunos_sistec(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Aluno], dict[str, list[Aluno]], dict[tuple[str, datetime.date], list[Aluno]]]:
    matriculas, cpfs, nomes_nasc_datas, nomes_nasc_pares = _extrair_identificadores_planilha(rows)

    alunos_por_matricula: dict[str, Aluno] = {}
    if matriculas:
        for a in Aluno.objects.filter(matricula__in=matriculas).select_related('curso_campus', 'pessoa_fisica', 'ano_letivo', 'situacao'):
            alunos_por_matricula[a.matricula] = a

    alunos_por_cpf: dict[str, list[Aluno]] = defaultdict(list)
    if cpfs:
        for a in Aluno.objects.filter(pessoa_fisica__cpf__in=cpfs).select_related('curso_campus', 'pessoa_fisica', 'ano_letivo', 'situacao'):
            alunos_por_cpf[a.pessoa_fisica.cpf].append(a)

    alunos_por_nome_nasc: dict[tuple[str, datetime.date], list[Aluno]] = defaultdict(list)
    if nomes_nasc_datas:
        for a in Aluno.objects.filter(pessoa_fisica__nascimento_data__in=nomes_nasc_datas).select_related(
            'curso_campus', 'pessoa_fisica', 'ano_letivo', 'situacao'
        ):
            if a.pessoa_fisica and a.pessoa_fisica.nome:
                par = (a.pessoa_fisica.nome.strip().lower(), a.pessoa_fisica.nascimento_data)
                if par in nomes_nasc_pares:
                    alunos_por_nome_nasc[par].append(a)

    return alunos_por_matricula, alunos_por_cpf, alunos_por_nome_nasc


def _atualizar_data_prevista_termino_aluno(
    aluno: Aluno,
    data_fim: datetime.date | None,
    atualizar_data_fim: bool,
    alunos_modificados: dict[int, Aluno],
) -> None:
    if atualizar_data_fim or aluno.data_prevista_termino_ciclo is None:
        data_fim_alvo = data_fim or aluno.calcular_data_prevista_termino_ciclo()
        if data_fim_alvo is not None:
            aluno.data_prevista_termino_ciclo = data_fim_alvo
            alunos_modificados[aluno.id] = aluno


def _atualizar_aluno_por_matricula(
    matricula: str,
    codigo_aluno: int,
    data_inicio: datetime.date,
    atualizar_data_inicio: bool,
    sobrescrever_codigo: bool,
    data: dict[str, Any],
    alunos_por_matricula: dict[str, Aluno],
    alunos_modificados: dict[int, Aluno],
    data_fim: datetime.date | None = None,
    atualizar_data_fim: bool = False,
    alunos_atribuidos: set[int] | None = None,
) -> None:
    aluno = alunos_por_matricula.get(matricula)
    if not aluno:
        data.update(MATRICULA=matricula, RESULTADO='ALUNO NÃO ENCONTRADO', DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    if alunos_atribuidos is not None:
        alunos_atribuidos.add(aluno.id)

    if atualizar_data_inicio:
        aluno.data_inicio_ciclo = data_inicio
        alunos_modificados[aluno.id] = aluno
    elif aluno.data_inicio_ciclo is None:
        aluno.data_inicio_ciclo = aluno.calcular_data_inicio_ciclo()
        if aluno.data_inicio_ciclo is not None:
            alunos_modificados[aluno.id] = aluno

    _atualizar_data_prevista_termino_aluno(aluno, data_fim, atualizar_data_fim, alunos_modificados)

    data_inicio_suap = aluno.data_inicio_ciclo.strftime('%d/%m/%Y 00:00') if aluno.data_inicio_ciclo else '-'
    data_fim_suap = aluno.data_prevista_termino_ciclo.strftime('%d/%m/%Y 00:00') if aluno.data_prevista_termino_ciclo else '-'
    if aluno.codigo_sistec:
        resultado = 'LOCALIZADO'
        if sobrescrever_codigo:
            resultado = 'ATUALIZADO'
            aluno.codigo_sistec = str(codigo_aluno)
            alunos_modificados[aluno.id] = aluno
    else:
        resultado = 'INFORMADO'
        aluno.codigo_sistec = str(codigo_aluno)
        alunos_modificados[aluno.id] = aluno
    data.update(MATRICULA=matricula, RESULTADO=resultado, DT_INICIO_SUAP=data_inicio_suap, DT_FIM_SUAP=data_fim_suap)


def _buscar_candidatos_atualizar_sistec(
    data: dict[str, Any],
    alunos_por_cpf: dict[str, list[Aluno]],
    alunos_por_nome_nasc: dict[tuple[str, datetime.date], list[Aluno]],
) -> tuple[list[Aluno] | None, str]:
    cpf = data.get('NU_CPF')
    cpf_aluno = str(cpf).replace('.', '').replace('-', '').strip() if cpf else ''
    if cpf_aluno:
        cpf_mascarado = mask_cpf(cpf_aluno.zfill(11))
        candidatos = alunos_por_cpf.get(cpf_mascarado)
        if not candidatos:
            return None, 'ALUNO COM CPF NÃO ENCONTRADO'
        return candidatos, ''

    nome = str(data.get('NO_ALUNO', '')).strip().lower()
    data_nasc = _parse_data_planilha_sistec(data.get('DT_DATA_NASCIMENTO'))
    if nome and data_nasc:
        candidatos = alunos_por_nome_nasc.get((nome, data_nasc))
        if not candidatos:
            return None, 'ALUNO SEM CPF NÃO ENCONTRADO'
        return candidatos, ''

    return None, 'DADOS INSUFICIENTES'


def _aplicar_codigo_sistec_mes(
    alunos_mes: list[Aluno],
    codigo_aluno: int,
    sobrescrever_codigo: bool,
    data: dict[str, Any],
    alunos_modificados: dict[int, Aluno],
    data_fim: datetime.date | None = None,
    atualizar_data_fim: bool = False,
) -> None:
    for a in alunos_mes:
        _atualizar_data_prevista_termino_aluno(a, data_fim, atualizar_data_fim, alunos_modificados)

    tem_codigo = any(bool(a.codigo_sistec) for a in alunos_mes)
    if tem_codigo:
        resultado = 'LOCALIZADO'
        if sobrescrever_codigo:
            resultado = 'ATUALIZADO'
            for a in alunos_mes:
                a.codigo_sistec = str(codigo_aluno)
                alunos_modificados[a.id] = a
    else:
        resultado = 'INFORMADO'
        for a in alunos_mes:
            a.codigo_sistec = str(codigo_aluno)
            alunos_modificados[a.id] = a

    matriculas = [a.matricula for a in alunos_mes]
    dt_suap = alunos_mes[0].data_inicio_ciclo.strftime('%d/%m/%Y 00:00') if alunos_mes[0].data_inicio_ciclo else '-'
    dt_fim_suap = alunos_mes[0].data_prevista_termino_ciclo.strftime('%d/%m/%Y 00:00') if alunos_mes[0].data_prevista_termino_ciclo else '-'
    data.update(
        MATRICULA=matriculas[0] if len(matriculas) == 1 else ', '.join(matriculas),
        RESULTADO=resultado,
        DT_INICIO_SUAP=dt_suap,
        DT_FIM_SUAP=dt_fim_suap,
    )


def _normalizar_status_sistec(texto: str | None) -> str:
    if not texto:
        return ''
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII').upper().strip()


def _situacao_compativel_sistec(aluno: Aluno, status_sistec: str | None) -> bool:
    if not status_sistec or not aluno.situacao_id:
        return False
    status = _normalizar_status_sistec(status_sistec)
    sit = aluno.situacao_id
    if status in ('EM_CURSO', 'MATRICULADO'):
        return sit in (
            SituacaoMatricula.MATRICULADO,
            SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatricula.INTERCAMBIO,
            SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
            SituacaoMatricula.TRANCADO,
        )
    if status in ('TRANSF_EXT', 'TRANSFERIDO_EXTERNO'):
        return sit == SituacaoMatricula.TRANSFERIDO_EXTERNO
    if status in ('TRANSF_INT', 'TRANSFERIDO_INTERNO'):
        return sit == SituacaoMatricula.TRANSFERIDO_INTERNO
    if status in ('CONCLUIDA', 'CONCLUIDO', 'FORMADO'):
        return sit in (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO)
    if status in ('ABANDONO', 'DESLIGADO', 'CANCELADO', 'JUBILADO', 'EVASAO'):
        return sit in (
            SituacaoMatricula.EVASAO,
            SituacaoMatricula.NAO_CONCLUIDO,
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.JUBILADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.FALECIDO,
            SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
        )
    if status in ('INTEGRALIZADA', 'INTEGRALIZADO'):
        return sit in (
            SituacaoMatricula.CONCLUDENTE,
            SituacaoMatricula.ESTAGIARIO_CONCLUDENTE,
            SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
            SituacaoMatricula.AGUARDANDO_ENADE,
            SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO,
        )
    return False


def _obter_data_referencia_aluno(aluno: Aluno) -> datetime.date | None:
    if aluno.data_inicio_ciclo:
        return aluno.data_inicio_ciclo
    dt = aluno.calcular_data_inicio_ciclo()
    if dt:
        return dt
    if aluno.ano_letivo_id and aluno.ano_letivo:
        mes = 1 if (getattr(aluno, 'periodo_letivo', 1) or 1) == 1 else 7
        return datetime.date(aluno.ano_letivo.ano, mes, 1)
    return None


def _filtrar_por_menor_distancia(candidatos: list[Aluno], data_inicio: datetime.date) -> list[Aluno]:
    def dist(aluno: Aluno) -> int:
        dt = _obter_data_referencia_aluno(aluno)
        return abs((dt - data_inicio).days) if dt else 999999

    menor = min(dist(a) for a in candidatos)
    return [a for a in candidatos if dist(a) == menor]


def _desempatar_por_ano_letivo(candidatos: list[Aluno], ano: int) -> list[Aluno]:
    iguais = [a for a in candidatos if a.ano_letivo and a.ano_letivo.ano == ano]
    return iguais or candidatos


def _desempatar_por_status(candidatos: list[Aluno], status_sistec: str | None) -> list[Aluno]:
    if not status_sistec:
        return candidatos
    compativeis = [a for a in candidatos if _situacao_compativel_sistec(a, status_sistec)]
    return compativeis or candidatos


def _garantir_datas_ciclo_calculadas(aluno: Aluno, alunos_modificados: dict[int, Aluno]) -> None:
    if aluno.data_inicio_ciclo is None:
        aluno.data_inicio_ciclo = aluno.calcular_data_inicio_ciclo()
        if aluno.data_inicio_ciclo is not None:
            alunos_modificados[aluno.id] = aluno
    if aluno.data_prevista_termino_ciclo is None:
        dt_prev = aluno.calcular_data_prevista_termino_ciclo()
        if dt_prev is not None:
            aluno.data_prevista_termino_ciclo = dt_prev
            alunos_modificados[aluno.id] = aluno


def _selecionar_melhor_candidato_curso(
    candidatos_curso: list[Aluno],
    data_inicio: datetime.date,
    status_sistec: str | None = None,
    alunos_atribuidos: set[int] | None = None,
) -> tuple[Aluno | None, bool]:
    if len(candidatos_curso) == 1:
        return candidatos_curso[0], False

    livres = [a for a in candidatos_curso if a.id not in (alunos_atribuidos or set())]
    pool = livres or candidatos_curso
    if len(pool) == 1:
        return pool[0], False

    pool = _desempatar_por_ano_letivo(pool, data_inicio.year)
    if len(pool) == 1:
        return pool[0], False

    pool = _filtrar_por_menor_distancia(pool, data_inicio)
    if len(pool) == 1:
        return pool[0], False

    pool = _desempatar_por_status(pool, status_sistec)
    if len(pool) == 1:
        return pool[0], False

    return None, True


def _tentar_meses_vizinhos_ou_curso(
    candidatos: list[Aluno],
    data_inicio: datetime.date,
    codigo_aluno: int,
    sobrescrever_codigo: bool,
    data: dict[str, Any],
    alunos_modificados: dict[int, Aluno],
    data_fim: datetime.date | None = None,
    atualizar_data_fim: bool = False,
) -> None:
    ano_ant = data_inicio.year - 1 if data_inicio.month == 1 else data_inicio.year
    mes_ant = 12 if data_inicio.month == 1 else data_inicio.month - 1
    mes_anterior = [a for a in candidatos if a.data_inicio_ciclo and a.data_inicio_ciclo.year == ano_ant and a.data_inicio_ciclo.month == mes_ant]
    if mes_anterior:
        _aplicar_codigo_sistec_mes(
            mes_anterior[:1], codigo_aluno, sobrescrever_codigo, data, alunos_modificados, data_fim=data_fim, atualizar_data_fim=atualizar_data_fim
        )
        data['RESULTADO'] += ' (MÊS ANTERIOR)'
        return

    ano_pos = data_inicio.year + 1 if data_inicio.month == 12 else data_inicio.year
    mes_pos = 1 if data_inicio.month == 12 else data_inicio.month + 1
    mes_posterior = [a for a in candidatos if a.data_inicio_ciclo and a.data_inicio_ciclo.year == ano_pos and a.data_inicio_ciclo.month == mes_pos]
    if mes_posterior:
        _aplicar_codigo_sistec_mes(
            mes_posterior[:1], codigo_aluno, sobrescrever_codigo, data, alunos_modificados, data_fim=data_fim, atualizar_data_fim=atualizar_data_fim
        )
        data['RESULTADO'] += ' (MÊS POSTERIOR)'
        return

    if candidatos:
        _aplicar_codigo_sistec_mes(
            candidatos[:1], codigo_aluno, sobrescrever_codigo, data, alunos_modificados, data_fim=data_fim, atualizar_data_fim=atualizar_data_fim
        )
        data['RESULTADO'] += ' (MATRÍCULA NO CURSO)'
    else:
        data.update(MATRICULA='', RESULTADO='NÃO ENCONTRADO', DT_INICIO_SUAP='', DT_FIM_SUAP='')


def _atualizar_aluno_por_curso_ciclo(
    candidatos: list[Aluno],
    codigo_curso: int,
    data_inicio: datetime.date,
    atualizar_data_inicio: bool,
    codigo_aluno: int,
    sobrescrever_codigo: bool,
    data: dict[str, Any],
    alunos_modificados: dict[int, Aluno],
    data_fim: datetime.date | None = None,
    atualizar_data_fim: bool = False,
    alunos_atribuidos: set[int] | None = None,
) -> None:
    candidatos_curso = [a for a in candidatos if _curso_tem_codigo_sistec(a.curso_campus.codigo_sistec, codigo_curso)]
    if not candidatos_curso:
        data.update(MATRICULA='', RESULTADO='ALUNO DO CURSO NÃO ENCONTRADO', DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    for a in candidatos_curso:
        _garantir_datas_ciclo_calculadas(a, alunos_modificados)

    status_sistec = data.get('NO_STATUS_MATRICULA')
    aluno_escolhido, eh_ambiguo = _selecionar_melhor_candidato_curso(
        candidatos_curso, data_inicio, status_sistec=status_sistec, alunos_atribuidos=alunos_atribuidos
    )
    if eh_ambiguo or aluno_escolhido is None:
        data.update(
            MATRICULA='',
            RESULTADO='AMBIGUIDADE: MÚLTIPLAS MATRÍCULAS NO MESMO CURSO',
            DT_INICIO_SUAP='',
            DT_FIM_SUAP='',
        )
        return

    if alunos_atribuidos is not None:
        alunos_atribuidos.add(aluno_escolhido.id)

    if atualizar_data_inicio:
        aluno_escolhido.data_inicio_ciclo = data_inicio
        alunos_modificados[aluno_escolhido.id] = aluno_escolhido
        _aplicar_codigo_sistec_mes(
            [aluno_escolhido], codigo_aluno, sobrescrever_codigo, data, alunos_modificados, data_fim=data_fim, atualizar_data_fim=atualizar_data_fim
        )
    else:
        if (
            aluno_escolhido.data_inicio_ciclo
            and aluno_escolhido.data_inicio_ciclo.year == data_inicio.year
            and aluno_escolhido.data_inicio_ciclo.month == data_inicio.month
        ):
            _aplicar_codigo_sistec_mes(
                [aluno_escolhido],
                codigo_aluno,
                sobrescrever_codigo,
                data,
                alunos_modificados,
                data_fim=data_fim,
                atualizar_data_fim=atualizar_data_fim,
            )
        else:
            _tentar_meses_vizinhos_ou_curso(
                [aluno_escolhido],
                data_inicio,
                codigo_aluno,
                sobrescrever_codigo,
                data,
                alunos_modificados,
                data_fim=data_fim,
                atualizar_data_fim=atualizar_data_fim,
            )


def _processar_linha_atualizacao_sistec(
    data: dict[str, Any],
    sobrescrever_codigo: bool,
    atualizar_data_inicio: bool,
    codigos_cursos_validos: set[int],
    alunos_por_matricula: dict[str, Aluno],
    alunos_por_cpf: dict[str, list[Aluno]],
    alunos_por_nome_nasc: dict[tuple[str, datetime.date], list[Aluno]],
    alunos_modificados: dict[int, Aluno],
    atualizar_data_fim: bool = False,
    alunos_atribuidos: set[int] | None = None,
) -> None:
    data_fim_str = data.get('DT_DATA_FIM_PREVISTO') or data.get('DT_FIM_PREVISTO')
    data.setdefault('DT_DATA_FIM_PREVISTO', data_fim_str or '')
    data_fim = _parse_data_planilha_sistec(data_fim_str)

    co_matricula = data.get('CO_MATRICULA')
    if co_matricula is None or not str(co_matricula).strip().isdigit():
        data.update(RESULTADO='CO_MATRICULA INVÁLIDO', DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    codigo_aluno = int(co_matricula)
    matricula = data.get('MATRICULA')
    data_inicio = _parse_data_planilha_sistec(data.get('DT_DATA_INICIO'))
    if not data_inicio:
        data.update(RESULTADO='DATA INÍCIO INVÁLIDA', DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    if matricula and codigo_aluno:
        _atualizar_aluno_por_matricula(
            str(matricula).strip(),
            codigo_aluno,
            data_inicio,
            atualizar_data_inicio,
            sobrescrever_codigo,
            data,
            alunos_por_matricula,
            alunos_modificados,
            data_fim=data_fim,
            atualizar_data_fim=atualizar_data_fim,
            alunos_atribuidos=alunos_atribuidos,
        )
        return

    codigo_curso = int(data['CO_CURSO'])
    if codigo_curso not in codigos_cursos_validos:
        data.update(MATRICULA='', RESULTADO='CURSO NÃO LOCALIZADO NO SUAP', DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    candidatos, erro = _buscar_candidatos_atualizar_sistec(data, alunos_por_cpf, alunos_por_nome_nasc)
    if not candidatos:
        data.update(MATRICULA='', RESULTADO=erro, DT_INICIO_SUAP='', DT_FIM_SUAP='')
        return

    _atualizar_aluno_por_curso_ciclo(
        candidatos,
        codigo_curso,
        data_inicio,
        atualizar_data_inicio,
        codigo_aluno,
        sobrescrever_codigo,
        data,
        alunos_modificados,
        data_fim=data_fim,
        atualizar_data_fim=atualizar_data_fim,
        alunos_atribuidos=alunos_atribuidos,
    )


@task('Atualizar SISTEC Aluno')
def atualizar_sistec_aluno(
    planilha_path,
    sobrescrever_codigo,
    atualizar_data_inicio,
    atualizar_data_fim=False,
    task=None,
):
    storage = get_temp_storage()
    retry = 0
    while not storage.exists(planilha_path) and retry < 60:
        sleep(2)
        retry += 1
    content = storage.open(planilha_path).read()
    with open(planilha_path, 'wb') as local:
        local.write(content)
    rows = list(csv.DictReader(open(planilha_path, encoding='iso-8859-1'), delimiter=';'))
    registros = []
    colunas = [
        'MATRICULA',
        'NU_CPF',
        'CO_MATRICULA',
        'CO_CURSO',
        'DT_DATA_INICIO',
        'DT_INICIO_SUAP',
        'DT_DATA_FIM_PREVISTO',
        'DT_FIM_SUAP',
        'NO_CICLO_MATRICULA',
        'RESULTADO',
    ]
    registros.append(';'.join(colunas))

    codigos_cursos_validos = _carregar_codigos_sistec_cursos()
    alunos_por_matricula, alunos_por_cpf, alunos_por_nome_nasc = _precarregar_alunos_sistec(rows)
    alunos_modificados: dict[int, Aluno] = {}
    alunos_atribuidos: set[int] = set()

    for data in task.iterate(rows) if task else rows:
        _processar_linha_atualizacao_sistec(
            data,
            sobrescrever_codigo,
            atualizar_data_inicio,
            codigos_cursos_validos,
            alunos_por_matricula,
            alunos_por_cpf,
            alunos_por_nome_nasc,
            alunos_modificados,
            atualizar_data_fim=atualizar_data_fim,
            alunos_atribuidos=alunos_atribuidos,
        )
        registros.append(';'.join([str(data.get(coluna, '')) for coluna in colunas]))

    if alunos_modificados:
        with transaction.atomic():
            Aluno.objects.bulk_update(
                list(alunos_modificados.values()),
                ['codigo_sistec', 'data_inicio_ciclo', 'data_prevista_termino_ciclo'],
                batch_size=1000,
            )

    file_path = os.path.join(settings.TEMP_DIR, 'log_atualizacao_sistec.csv')
    s = '\r\n'.join(registros)
    with open(file_path, 'w') as f:
        f.write(s)
    if task:
        task.finalize('Dados atualizados conforme arquivo de log.', '/edu/atualizar_codigo_sistec/', file_path=file_path)


@task('Gerar Auditoria do Ensino')
def gerar_auditoria_ensino(auditoria_ensino: AuditoriaEnsino, task: Task | None = None) -> None:
    from edu.auditoria_ensino import AuditoriaEnsinoService

    AuditoriaEnsinoService.processar(auditoria_ensino, task=task)


@task('Exportar Auditoria do Ensino')
def exportar_auditoria_ensino(auditoria_ensino, task=None):
    linhas = []
    linhas.append(auditoria_ensino.get_header(to_xls=True))
    registros = auditoria_ensino.get_registros_auditoria()
    for item in task.iterate(registros):
        linhas.append(item.get_itens(to_xls=True))
    return XlsResponse(linhas, processo=task)


@task('Remover Registros de Auditoria do Ensino')
def remover_registros_auditoria_ensino(auditoria_ensino, task=None):
    qs = auditoria_ensino.registroauditoriaensino_set.all()
    qs._raw_delete(using=qs.db)
    if task:
        task.finalize('Auditoria desfeita com sucesso.', auditoria_ensino.get_absolute_url())


@task('Emitir Boletins em PDF')
def emitir_boletins_pdf(request, matriculas_periodo, task=None):
    from edu import views

    pdf = views.emitir_boletins_aluno_pdf(request, matriculas_periodo, task)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf.content)
    tmp.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Gerar Carômetros de Alunos')
def carometros_alunos_pdf(request, alunos, filtros, task=None):
    from edu import views

    task.start_progress(total=3)
    task.update_progress(1)
    pdf = views.carometros_alunos_pdf(request, alunos, filtros)
    task.update_progress(2)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf.content)
    tmp.close()
    task.update_progress(3)
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Exportar Relatório EDUCACENSO para XLS')
def relatorio_educacenso_xls(alunos, ano_letivo, periodo_letivo, task=None):
    rows = [
        [
            '#',
            'Matrícula',
            'Nome',
            'CPF',
            'Diretoria',
            'Turma',
            'Situação da Matrícula',
            'Situação no Período',
            'Rendimento',
            'Movimento',
            'Concluinte',
        ]
    ]

    count = 0
    for aluno in task.iterate(alunos):
        qs = MatriculaPeriodo.objects.filter(aluno=aluno).order_by('-ano_letivo__ano', '-periodo_letivo')
        if periodo_letivo not in [None, '', '0', 0]:
            qs = qs.filter(periodo_letivo=periodo_letivo)
        if ano_letivo:
            qs = qs.filter(ano_letivo=ano_letivo)
        if qs:
            aluno.matricula_periodo = qs[0]
        count += 1
        if aluno.matricula_periodo.get_concluinte() is not None:
            if aluno.matricula_periodo.get_concluinte():
                concluinte = 'Sim'
            else:
                concluinte = 'Não'
        else:
            concluinte = '-'

        row = [
            count,
            format_(aluno.matricula),
            format_(aluno.get_nome_social_composto()),
            format_(aluno.pessoa_fisica.cpf),
            format_(aluno.curso_campus.diretoria),
            format_(aluno.matricula_periodo.get_codigo_turma()),
            format_(aluno.situacao),
            format_(aluno.matricula_periodo.situacao),
            format_(aluno.matricula_periodo.get_rendimento()),
            format_(aluno.matricula_periodo.get_movimento()),
            concluinte,
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório CENSUP para XLS')
def relatorio_censup_xls(alunos, ano_letivo, periodo_letivo, task=None):
    rows = [
        [
            '#',
            'Matrícula',
            'Nome',
            'CPF',
            'Curso',
            'Situação da Matrícula',
            'Situação no Período',
            'Situação Vínculo Curso',
            'Turno',
            'Reserva de Vagas',
            'Apoio Social',
            'Atividade Extracurricular',
            'C.H. Curso',
            'C.H. Cumprida',
        ]
    ]
    count = 0
    for aluno in task.iterate(alunos):
        count += 1
        ano = None
        qs = MatriculaPeriodo.objects.filter(aluno=aluno).order_by('-ano_letivo__ano', '-periodo_letivo')
        if periodo_letivo not in [None, '', '0', 0]:
            qs = qs.filter(periodo_letivo=periodo_letivo)
        if ano_letivo:
            ano = ano_letivo.ano
            qs = qs.filter(ano_letivo=ano_letivo)
        if qs:
            aluno.matricula_periodo = qs[0]
        row = [
            count,
            format_(aluno.matricula),
            format_(aluno.get_nome_social_composto()),
            format_(aluno.pessoa_fisica.cpf),
            format_(aluno.curso_campus),
            format_(aluno.situacao),
            format_(aluno.matricula_periodo.situacao),
            format_(aluno.matricula_periodo.get_situacao_censup()),
            format_(aluno.turno),
            (aluno.tem_cota() or 'Não'),
            (aluno.tem_apoio_social() and format_(aluno.tem_apoio_social()) or 'Não'),
            (aluno.tem_atividade_extracurricular() and format_(aluno.tem_atividade_extracurricular()) or 'Não'),
            format_(aluno.matriz and aluno.matriz.get_carga_horaria_total_prevista() or '-'),
            format_(aluno.matriz and aluno.get_ch_componentes_cumpridos(apenas_curriculares=True, ano=ano, incluir_atividades=True) or '-'),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Aluno por Disciplina Pendente para XLS')
def relatorio_pordisciplinapendente_xls(alunos, task=None):
    rows = [['#', 'Matrícula', 'Nome', 'Sigla', 'Período', 'Descrição', 'Tipo']]
    count = 0
    for aluno in task.iterate(alunos):
        for componente_pendente in aluno.get_componentes_obrigatorios_pendentes(True):
            count += 1
            row = [
                count,
                format_(aluno.matricula),
                format_(aluno.get_nome_social_composto()),
                format_(componente_pendente.componente.sigla),
                format_(componente_pendente.periodo_letivo),
                format_(componente_pendente.componente.descricao_historico),
                format_(componente_pendente.get_tipo_display()),
            ]
            rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Aluno por Disciplina Cursando para XLS')
def relatorio_pordisciplinacursando_xls(alunos, task=None):
    rows = [['#', 'Matrícula', 'Nome', 'Sigla', 'Período', 'Descrição', 'Tipo', 'Diario', 'Situação']]
    count = 0
    for aluno in task.iterate(alunos):
        for md in aluno.get_matriculas_diario_cursando():
            count += 1
            row = [
                count,
                format_(aluno.matricula),
                format_(aluno.get_nome_social_composto()),
                format_(md.diario.componente_curricular.componente.sigla),
                format_(md.diario.componente_curricular.periodo_letivo),
                format_(md.diario.componente_curricular.componente.descricao_historico),
                format_(md.diario.componente_curricular.get_tipo_display()),
                format_(md.diario.id),
                format_(md.get_situacao_diario()['rotulo']),
            ]
            rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Aluno por TCC para XLS')
def relatorio_tcc_xls(alunos, task=None):
    rows = [['#', 'Matrícula', 'Aluno', 'Nível de ensino', 'Tipo', 'Título', 'Banca', 'Data prevista', 'Data de defesa', 'Nota', 'Situação']]
    i = 0
    for aluno in task.iterate(alunos):
        i += 1
        for projeto_final in aluno.get_projetos_finais():
            rows.append(
                [
                    i,
                    aluno.matricula,
                    aluno.pessoa_fisica.nome,
                    aluno.curso_campus.modalidade.nivel_ensino.descricao,
                    projeto_final.tipo,
                    projeto_final.titulo,
                    ', '.join(
                        [
                            'Presidente:',
                            str(projeto_final.presidente),
                            'Examinador:',
                            str(projeto_final.examinador_interno),
                            'Examinador:',
                            str(projeto_final.examinador_externo),
                        ]
                    ),
                    format_(projeto_final.data_defesa),
                    format_(projeto_final.resultado_data),
                    format_(projeto_final.nota),
                    projeto_final.get_situacao_display(),
                ]
            )
    return XlsResponse(rows, processo=task)


@task('Exportar Listagem de Professores para XLS')
def exportar_listagem_professores_xls(request, professores, campos_exibicao, choices, ano_letivo, periodo_letivo, task=None):
    rows = [['#', 'Matrícula', 'Nome']]
    for campo in campos_exibicao:
        for label in choices:
            if label[0] == campo:
                rows[0].append(format_(label[1]))

    count = 0
    for professor in task.iterate(professores):
        professor.ano_letivo_informado = ano_letivo
        professor.periodo_letivo_informado = periodo_letivo
        count += 1
        row = [count, format_(professor.get_matricula()), format_(professor.vinculo.pessoa.nome)]
        for campo in campos_exibicao:
            row.append(format_(professor.getattr(campo, request), False))
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Dependência para XLS')
def exportar_relatorio_dependencia_xls(matriculas_diarios, task=None):
    rows = [
        ['#', 'Matrícula', 'Nome', 'Turno', 'Turma Subsequente', 'Diário', 'Componente', 'Situação', 'Diário de Dependência no Período Subsequente']
    ]

    count = 0
    for matricula_diario in task.iterate(matriculas_diarios):
        count += 1
        diario = hasattr(matricula_diario, 'diario') and matricula_diario.diario.pk or matricula_diario.codigo_diario_pauta
        matricula_periodo_subsequente = matricula_diario.matricula_periodo.get_matricula_periodo_subsequente()
        componente = (
            hasattr(matricula_diario, 'diario')
            and matricula_diario.diario.componente_curricular.componente.descricao_historico
            or matricula_diario.equivalencia_componente.componente.descricao_historico
        )
        row = [
            count,
            format_(matricula_diario.matricula_periodo.aluno.matricula),
            format_(matricula_diario.matricula_periodo.aluno.get_nome_social_composto()),
            format_(matricula_diario.matricula_periodo.aluno.turno),
            format_(matricula_periodo_subsequente.turma if matricula_periodo_subsequente else None),
            format_(diario),
            format_(componente),
            format_(matricula_diario.matricula_periodo.situacao.descricao),
            format_(matricula_diario.get_diario_dependencia()),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Diários para XLS')
def exportar_relatorio_diario_xls(diarios, campos_exibicao, choices, task=None):
    rows = [
        [
            '#',
            'Diário',
            ' Sigla do Componente',
            'Descrição do Componente',
            'Nível de Ensino',
            'Professores',
            'Carga Horária Prevista dos Professores',
            'Posse Etapa 1',
            'Posse Etapa 2',
            'Posse Etapa 3',
            'Posse Etapa 4',
            'Posse Etapa Final',
        ]
    ]
    for campo in campos_exibicao:
        for label in choices:
            if label[0] == campo:
                if label[0] == 'turma.curso_campus':
                    rows[0].append('Código do Curso')
                    rows[0].append('Descrição do Curso')
                else:
                    rows[0].append(format_(label[1]))
    count = 0
    for diario in task.iterate(diarios):
        posse_etapa_2 = '-'
        posse_etapa_3 = '-'
        posse_etapa_4 = '-'
        if diario.componente_curricular.qtd_avaliacoes > 1:
            posse_etapa_2 = diario.get_posse_etapa_2_display()
        if diario.componente_curricular.qtd_avaliacoes > 2:
            posse_etapa_3 = diario.get_posse_etapa_3_display()
        if diario.componente_curricular.qtd_avaliacoes > 3:
            posse_etapa_4 = diario.get_posse_etapa_4_display()
        count += 1
        row = [
            count,
            format_(diario.id),
            format_(diario.componente_curricular.componente.sigla),
            format_(diario.componente_curricular.componente.descricao),
            format_(diario.componente_curricular.componente.nivel_ensino),
            ', '.join([str(x) for x in diario.get_professores_display()]),
            diario.get_resumo_ch_prevista(),
            format_(diario.get_posse_etapa_1_display()),
            format_(posse_etapa_2),
            format_(posse_etapa_3),
            format_(posse_etapa_4),
            format_(diario.get_posse_etapa_5_display()),
        ]
        for campo in campos_exibicao:
            if campo == 'turma.curso_campus':
                row.append(format_(diario.turma.curso_campus.codigo))
                row.append(format_(diario.turma.curso_campus.descricao))
            else:
                row.append(format_(diario.getattr(campo)))
        rows.append(row)
    if len(rows) >= 65536:
        return CsvResponse(rows, processo=task)
    else:
        return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Diários para PDF')
def relatorio_diario_pdf(request, diarios, task=None):
    import zipfile

    from edu import views

    etapa = request.GET.get('etapa') or 1
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_file.close()
    f = zipfile.ZipFile(temp_file.name, 'w')
    for diario in task.iterate(diarios):
        arquivo = views.diario_pdf(request, diario.pk, etapa)
        f.writestr(f'diario_{diario.pk}.pdf', arquivo.content)
    f.close()
    task.finalize('Arquivo gerado com sucesso.', '..', file_path=f.filename)


@task('Baixar Pasta Documental')
def download_pasta_documental(documentos, task=None):
    import zipfile

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_file.close()
    f = zipfile.ZipFile(temp_file.name, 'w')
    for documento in task.iterate(documentos):
        extensao = documento.nome_original.split('.')[-1]
        f.writestr(f'{documento.nome_exibicao}.{extensao}', documento.arquivo_unico.conteudo.file.read())
    f.close()
    task.finalize('Arquivo gerado com sucesso.', '..', file_path=f.filename)


@task('Exportar Relatório de Diários com Alunos Pendentes')
def relatorio_diario_alunos_pendentes(request, diarios, filtros, exibir_botao_executar, agrupamento, campos_exibicao, task=None):
    from edu.forms import RelatorioDiarioForm

    qs = diarios.filter(estrutura_curso__tipo_avaliacao__in=[EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR])
    componentes_curriculares = qs.values_list('componente_curricular')
    alunos_componente_curricular_reprovados = (
        Aluno.objects.filter(
            matriculaperiodo__matriculadiario__diario__componente_curricular_id__in=componentes_curriculares,
            matriculaperiodo__matriculadiario__situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
        )
        .distinct()
        .values_list('id', 'matriculaperiodo__matriculadiario__diario__componente_curricular')
    )

    matriculas_diario_dependentes = set()
    for aluno, componente_curricular in task.iterate(alunos_componente_curricular_reprovados):
        matriculas_diario = MatriculaDiario.objects.filter(
            diario__componente_curricular_id=componente_curricular,
            matricula_periodo__aluno_id=aluno,
            situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL],
        )
        for matricula_diario in matriculas_diario:
            matriculas_diario_dependentes.add(matricula_diario)

    qs = qs.filter(matriculadiario__in=matriculas_diario_dependentes).distinct()
    filtros.append({'chave': 'Aluno Pendente', 'valor': format_(True)})
    form = RelatorioDiarioForm(data=request.GET or None, initial={'etapa': 1})
    query_string = request.META.get('QUERY_STRING', '').encode('utf-8').hex()
    ctx = {
        'exibir_botao_executar': exibir_botao_executar,
        'diarios': qs,
        'form': form,
        'filtros': filtros,
        'agrupamento': agrupamento,
        'campos_exibicao': campos_exibicao,
        'query_string': query_string,
    }
    response = render_to_string('relatorio_diario.html', ctx, request)
    f = tempfile.NamedTemporaryFile(suffix='.html', mode='w+', delete=False)
    f.write(response)
    f.close()
    task.finalize('Arquivo gerado com sucesso.', '..', file_path=f.name)


@task('Exportar Alunos Evadidos para XLS')
def exportar_evasao_em_lote_xls(alunos, task=None):
    count = 0
    rows = [
        [
            '#',
            'Matrícula',
            'Nome',
            'Situação do Aluno',
            'Situação da Matricula Período',
            'Percentual de C.H. Cumprida',
            'Curso',
            'Diretoria',
            'Campus',
        ]
    ]
    for aluno in task.iterate(alunos):
        count += 1
        row = [
            count,
            format_(aluno.matricula),
            format_(aluno.get_nome_social_composto()),
            format_(aluno.situacao),
            format_(aluno.get_ultima_matricula_periodo().situacao),
            format_(aluno.get_percentual_carga_horaria_cumprida()),
            format_(aluno.curso_campus.descricao),
            format_(aluno.curso_campus.diretoria),
            format_(aluno.curso_campus.diretoria.setor.uo),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Processar indicadores do ensino')
def processar_indicadores(request, task=None):
    from comum.models import Ano, UnidadeOrganizacional
    from edu.forms import IndicadoresForm

    form = IndicadoresForm(request.GET or None, request=request)
    form.full_clean()
    ano_inicio = form.cleaned_data.get('ano_inicio').ano
    ano_fim = form.cleaned_data.get('ano_fim', Ano.objects.latest('ano')).ano
    modalidade_selecionada = form.request.GET.get('modalidade_selecionada', None)
    modalidades = form.cleaned_data.get('modalidades', None)
    uo_selecionada = form.request.GET.get('uo_selecionada', None)
    uos = form.cleaned_data['uos']
    curso_selecionado = form.request.GET.get('curso_selecionado', None)
    deficiencias = form.cleaned_data.get('deficiencias')
    outras_nees = form.cleaned_data.get('outras_nees')
    cursos = None
    anos = list(range(ano_inicio, ano_fim + 1))
    if uo_selecionada:
        uo_selecionada = int(uo_selecionada)
        cursos = CursoCampus.objects.filter(diretoria__setor__uo_id=uo_selecionada, modalidade_id__in=modalidades)
        if curso_selecionado:
            curso_selecionado = int(curso_selecionado)
        else:
            curso_selecionado = 0
    else:
        uo_selecionada = 0
        curso_selecionado = 0

    variaveis = IndicadoresForm.processar_variaveis(
        ano_inicio,
        ano_fim,
        modalidades,
        uos,
        uo_id=uo_selecionada,
        curso_id=curso_selecionado,
        deficiencias=deficiencias,
        outras_nees=outras_nees,
    )

    indicadores = IndicadoresForm.gerar_indicadores(anos, variaveis)

    modalidades_pks = modalidades.values_list('pk', flat=True)
    deficiencias_pks = deficiencias.values_list('pk', flat=True)
    outras_nees_pks = outras_nees.values_list('pk', flat=True)
    uos_links = uos
    if uo_selecionada:
        uos_links = [UnidadeOrganizacional.objects.suap().get(pk=uo_selecionada)]
    uos_links = '_'.join([str(uo.pk) for uo in uos_links])

    ctx = {
        'uos': uos,
        'anos': anos,
        'uo_selecionada': uo_selecionada,
        'indicadores': OrderedDict(sorted(indicadores.items(), key=lambda t: t[0])),
        'modalidade_selecionada': modalidade_selecionada,
        'modalidades': modalidades,
        'modalidades_pks': modalidades_pks,
        'curso_selecionado': curso_selecionado,
        'cursos': cursos,
        'deficiencias': deficiencias,
        'deficiencias_pks': deficiencias_pks,
        'outras_nees': outras_nees,
        'outras_nees_pks': outras_nees_pks,
        'uos_links': uos_links,
        'form': form,
        'indicadores_colunas': form.INDICADORES,
        'parametros': request.META.get('QUERY_STRING', ''),
        'title': 'Indicadores de Ensino',
        'pode_exportar_xls': request.user.has_group_cached('Administrador Acadêmico') or uo_selecionada,
    }

    response = render_to_string('indicadores.html', ctx, request)
    f = tempfile.NamedTemporaryFile(suffix='.html', mode='w+', delete=False)
    f.write(response)
    f.close()
    return task.finalize('Relatório Gerado com Sucesso', '..', file_path=f.name)


@task('Exportar Indicadores para XLS')
def exportar_indicadores_xls(request, task=None):
    from comum.models import Ano
    from edu.forms import IndicadoresForm

    form = IndicadoresForm(request.GET or None, request=request)
    form.full_clean()

    ano_inicio = form.cleaned_data.get('ano_inicio').ano
    ano_fim = form.cleaned_data.get('ano_fim', Ano.objects.latest('ano')).ano
    anos = list(range(ano_inicio, ano_fim + 1))

    deficiencias = form.cleaned_data.get('deficiencias')
    outras_nees = form.cleaned_data.get('outras_nees')

    uo_selecionada = form.request.GET.get('uo_selecionada', None)
    if uo_selecionada:
        uos = [uo_selecionada]

    else:
        uos = form.cleaned_data['uos']

    modalidades = form.cleaned_data.get('modalidades', None)
    cursos = CursoCampus.objects.filter(diretoria__setor__uo_id__in=uos, modalidade_id__in=modalidades.values_list('pk', flat=True))

    rows = [
        [
            '#',
            'CURSO',
            'CURSO_NOME',
            'ANO',
            'MATRICULAS ATENDIDAS',
            'CONCLUIDOS',
            'RETIDOS',
            'MATRÍCULAS FINALIZADAS EVADIDAS',
            'REPROVADOS',
            'MATRICULAS CONTINUADAS REGULARES',
            'MATRÍCULAS CONTINUADAS RETIDAS',
            'CONCLUÍDOS NO PRAZO',
            'PREVISTO',
            'MATRÍCULAS FINALIZADAS',
            'CONCLUINTES',
            'INGRESSOS',
            '01 - Taxa de Retenção',
            '02 - Taxa de Conclusão',
            '03 - Taxa de Evasão',
            '04 - Taxa de Reprovações',
            '05 - Taxa de Matrícula Ativa Regular',
            '06 - Taxa de Matrícula Ativa Retida',
            '07 - Índice de Efetividade Acadêmica',
            '08 - Taxa de Saída com Êxito',
            '09 - Taxa de Permanência e Êxito',
            '10 - Índice de Eficácia',
        ]
    ]
    contador = 0
    for curso in task.iterate(cursos):
        variaveis = IndicadoresForm.processar_variaveis(
            anos[0],
            anos[-1],
            modalidades,
            uos,
            curso_id=curso,
            deficiencias=deficiencias,
            outras_nees=outras_nees,
        )
        indicadores = IndicadoresForm.gerar_indicadores(anos, variaveis)
        for ano in anos:
            contador += 1
            row = [
                contador,
                curso.codigo,
                curso.descricao_historico,
                ano,
                variaveis['ATENDIDOS'][ano].count(),
                variaveis['CONCLUIDOS'][ano].count(),
                variaveis['RETIDOS'][ano].count(),
                variaveis['EVADIDOS'][ano].count(),
                variaveis['REPROVADOS'][ano].count(),
                variaveis['CONTINUADOS_REGULARES'][ano].count(),
                variaveis['CONTINUADOS_RETIDOS'][ano].count(),
                variaveis['CONCLUIDOS_PRAZO'][ano].count(),
                variaveis['PREVISTOS'][ano].count(),
                variaveis['FINALIZADOS'][ano].count(),
                variaveis['CONCLUINTES'][ano].count(),
                variaveis['INGRESSOS'][ano].count(),
                format_(indicadores['01_TAXA_RETENCAO'][ano]),
                format_(indicadores['02_TAXA_CONCLUSAO'][ano]),
                format_(indicadores['03_TAXA_EVASAO'][ano]),
                format_(indicadores['04_TAXA_REPROVACOES'][ano]),
                format_(indicadores['05_TAXA_ATIVOS_REGULARES'][ano]),
                format_(indicadores['06_TAXA_ATIVOS_RETIDOS'][ano]),
                format_(indicadores['07_TAXA_EFETIVIDADE'][ano]),
                format_(indicadores['08_TAXA_SAIDA_EXITO'][ano]),
                format_(indicadores['09_TAXA_PERMANENCIA_EXITO'][ano]),
                format_(indicadores['10_INDICE_EFICACIA'][ano]),
            ]
            rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório do CENSUP para XLS')
def exportar_relatorio_censup_xls(file_contents, tipo_relatorio, coluna_busca, tipo_busca, coluna_salva, task=None):
    """Exporta relatório do CENSUP para arquivo XLS.

    Args:
        file_contents: conteúdo binário do arquivo de entrada.
        tipo_relatorio: tipo de relatório a ser gerado.
        coluna_busca: índice da coluna de busca.
        tipo_busca: tipo de busca a ser realizada.
        coluna_salva: índice da coluna a ser salva.
        task: objeto de task assíncrona para controle de progresso.

    Returns:
        str: mensagem de finalização com caminho do arquivo gerado.
    """
    import pandas as pd

    from edu.forms import PreencherRelatorioCensupForm

    df = pd.read_excel(io.BytesIO(file_contents), header=None)

    coluna_busca = int(coluna_busca)
    coluna_salva = int(coluna_salva)
    max_col = max(coluna_busca, coluna_salva)
    if len(df.columns) <= max_col:
        for i in range(len(df.columns), max_col + 1):
            df[i] = ''

    for index in task.iterate(range(len(df))):
        try:
            val = df.iloc[index, coluna_busca]
            if pd.isna(val) or val == '':
                continue

            if isinstance(val, float):
                campo = str(val).removesuffix('.0')
            else:
                campo = str(val)

            qs = None
            result_str = ''

            if tipo_relatorio == PreencherRelatorioCensupForm.CAMPUS_CURSO:
                qs = (
                    CursoCampus.objects.filter(codigo_censup=campo)
                    .select_related('diretoria', 'diretoria__setor')
                    .values_list('diretoria__setor__sigla', flat=True)
                )
                result_str = format_(qs)
            else:
                cpf = None
                if tipo_busca == PreencherRelatorioCensupForm.BUSCA_CPF:
                    if len(campo.strip()) < 11:
                        campo = campo.strip().zfill(11)
                    cpf = f'{campo[0:3]}.{campo[3:6]}.{campo[6:9]}-{campo[9:11]}'

                if tipo_relatorio == PreencherRelatorioCensupForm.CAMPUS_PROFESSOR:
                    qs = Professor.objects.select_related('vinculo__pessoa', 'vinculo__setor').values_list('vinculo__setor__sigla', flat=True)
                    if tipo_busca == PreencherRelatorioCensupForm.BUSCA_CPF:
                        qs = qs.filter(vinculo__pessoa__pessoafisica__cpf=cpf)
                    else:
                        qs = qs.filter(vinculo__user__username=campo)
                    result_str = format_(qs)
                else:
                    qs = Aluno.objects.filter(curso_campus__modalidade__nivel_ensino__pk__in=[NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO])
                    if tipo_busca == PreencherRelatorioCensupForm.BUSCA_CPF:
                        qs = qs.filter(pessoa_fisica__cpf=cpf)
                    else:
                        qs = qs.filter(matricula=campo)

                    if tipo_relatorio == PreencherRelatorioCensupForm.CAMPUS_ALUNO:
                        qs = qs.select_related('curso_campus', 'curso_campus__diretoria__setor').values_list(
                            'curso_campus__diretoria__setor__sigla', flat=True
                        )
                        result_str = format_(qs)
                    else:  # CURSO_ALUNO
                        result = qs.select_related('curso_campus').values('curso_campus__codigo_censup', 'curso_campus__descricao_historico')
                        obj = result.first()
                        if obj:
                            result_str = f'{obj["curso_campus__codigo_censup"]} - {obj["curso_campus__descricao_historico"]}'
                        else:
                            result_str = ''

            if len(result_str) < 10000:
                df.iloc[index, coluna_salva] = result_str
        except Exception as e:
            df.iloc[index, coluna_salva] = str(e)

    response = tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False)
    df.to_excel(response.name, index=False, header=False)
    response.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)


@task('Exportar Auditoria SUAP -> SISTEC para XLS')
def exportar_relatorio_alunos_nao_existentes_sistec_xls(planilha_path, campus_selecionado, anos_selecionados, convenios_selecionados, task=None):
    """Exporta relatório de alunos existentes no SUAP mas não encontrados no SISTEC.

    Args:
        planilha_path: caminho do arquivo de planilha SISTEC.
        campus_selecionado: objeto do campus filtrado.
        anos_selecionados: anos letivos para filtrar.
        convenios_selecionados: convênios para filtrar.
        task: objeto de task assíncrona para controle de progresso.
    """
    import pandas as pd

    storage = get_temp_storage()
    retry = 0
    while not storage.exists(planilha_path) and retry < 60:
        sleep(2)
        retry += 1
    with open(planilha_path, 'wb') as local:
        local.write(storage.open(planilha_path).read())
    rows = list(csv.DictReader(open(planilha_path, encoding='iso-8859-1'), delimiter=';'))

    # Processando os alunos da planilha do SISTEC
    lista_alunos_sistec = []
    codigo_unidade = campus_selecionado.codigo_sistec

    for row in rows:
        try:
            codigo_curso = row['CO_CURSO']

            # Tratando o CPF - Se CPF vier mascarado retira a máscara e aplica novamente
            cpf_aluno = str(row['NU_CPF']).replace('.', '').replace('-', '')
            cpf_aluno = str(int(cpf_aluno))
            cpf_aluno = cpf_aluno.rjust(11, '0')
            cpf_aluno = mask_cpf(cpf_aluno)

            lista_alunos_sistec.append({'cpf': cpf_aluno, 'codigo_curso': codigo_curso, 'codigo_unidade': codigo_unidade})
        except Exception:
            pass

    # Realizando o cruzamento dos alunos do SUAP com os da planilha do SISTEC
    qs_alunos = Aluno.objects.exclude(participanteturmaminicurso__turma__gerar_matricula=False).exclude(
        situacao__in=[
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            SituacaoMatricula.TRANSFERIDO_INTERNO,
            SituacaoMatricula.TRANSFERIDO_EXTERNO,
        ]
    )

    if convenios_selecionados:
        qs_alunos = qs_alunos.exclude(convenio__in=convenios_selecionados)

    qs_alunos = qs_alunos.filter(curso_campus__diretoria__setor__uo=campus_selecionado, ano_letivo__in=anos_selecionados)

    output_data = []
    for aluno in task.iterate(qs_alunos):
        encontrado = False
        for codigo_sistec in aluno.curso_campus.codigo_sistec.split(';'):
            dict_aluno = {
                'cpf': aluno.pessoa_fisica.cpf,
                'codigo_curso': codigo_sistec,
                'codigo_unidade': aluno.curso_campus.diretoria.setor.uo.codigo_sistec,
            }
            encontrado = encontrado or (dict_aluno in lista_alunos_sistec)
        if not encontrado:
            output_data.append(
                {
                    'CPF': aluno.pessoa_fisica.cpf,
                    'NOME': aluno.pessoa_fisica.nome,
                    'FORMA_INGRESSO': str(aluno.forma_ingresso),
                    'DIRETORIA': str(aluno.curso_campus.diretoria),
                    'CURSO': str(aluno.curso_campus),
                    'CURSO_CODIGO_SISTEC': str(aluno.curso_campus.codigo_sistec),
                    'SITUACAO_MATRICULA': str(aluno.situacao),
                    'ANO_INGRESSO': aluno.ano_letivo.ano,
                    'PERIODO_INGRESSO': aluno.periodo_letivo,
                }
            )

    df = pd.DataFrame(output_data)
    response = tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False)
    df.to_excel(response.name, index=False, sheet_name='Alunos')
    response.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)


@task('Exportar Relatório de Idiomas sem Fronteira para XLS')
def exportar_relatorio_isf_xls(qs_aluno, task=None):
    rows = [
        [
            'CODIGO_EMEC',
            'CODIGO_CURSO',
            'CURSO_NOME',
            'CURSO_TIPO',
            'CPF',
            'CSF',
            'INTEGRALIDADE',
            'MEDIA',
            'EMAIL',
            'TURNO',
            'BOLSISTAS JOVENS TALENTOS',
        ]
    ]

    for aluno in task.iterate(qs_aluno):
        # Informar o código somente para os cursos de graduação.
        curso_codigo = 0
        if aluno.curso_campus.modalidade.nivel_ensino.id == NivelEnsino.GRADUACAO:
            curso_codigo = aluno.curso_campus.codigo

        # O texto deve conter até 100 caracteres.
        curso_nome = aluno.curso_campus.descricao_historico[:100]

        # Utilize o valor 1 quando for curso de graduação.
        # Utilize o valor 2 quando for programa de pós-graduação lato sensu.
        # Utilize o valor 3 quando for programa de pós-graduação stricto sensu mestrado.
        # Utilize o valor 4 quando for programa de pós-graduação stricto sensu doutorado.
        curso_tipo = 0
        modalidade = aluno.curso_campus.modalidade
        if modalidade.nivel_ensino.id == NivelEnsino.GRADUACAO:
            curso_tipo = 1
        elif modalidade.id == Modalidade.ESPECIALIZACAO:
            curso_tipo = 2
        elif modalidade.id == Modalidade.MESTRADO:
            curso_tipo = 3
        elif modalidade.id == Modalidade.DOUTORADO:
            curso_tipo = 4

        # Informar somente os números no campo cpf.
        try:
            cpf_limpo = re.sub(r'\D', '', aluno.pessoa_fisica.cpf)
        except Exception:
            cpf_limpo = ''

        # Utilize o valor 1 quando o aluno for da área prioritária do CsF.
        # Utilize o valor 0 quando o aluno NÃO for da área prioritária do CsF.
        csf = aluno.curso_campus.ciencia_sem_fronteira and 1 or 0

        # Informar a proporção cursada pelo aluno para conclusão do curso ou programa. O campo aceitará valores fracionários, com utilização de ponto (.) como separador e até duas casas decimais (Exemplo: 60.50).
        # Os cursos de graduação e os programas de pós-graduação que não tenham como identificar o valor, a posição deve ser preenchida com 0.00.
        # Os valores deverão ser maiores ou iguais a 0.00 e menores que 100.00, portanto até 99.99.
        integralidade = aluno.get_percentual_carga_horaria_cumprida()
        if integralidade >= 100:
            integralidade = 99.99
        integralidade = format(integralidade, '.2f')

        # Informar a média do aluno no curso ou programa. O campo aceitará valores fracionários, com utilização de ponto (.) como separador e até duas casas decimais (Exemplo: 8.00).
        # Os cursos de graduação e os programas de pós-graduação que não tenham como identificar o valor, a posição deve ser preenchida com 0.00.
        # Os valores deverão ser maiores ou iguais a 0.00 e menores ou iguais a 100.00.
        media = aluno.get_ira()
        if media is None:
            media = 0
        media = format(media, '.2f')

        # Caso a instituição não tenha o e-mail de contato, o valor deve ser preenchido com email_nao_informado.
        # Deverá ser informado apenas um e-mail por aluno.
        email = aluno.email_pessoal or aluno.email_academico or 'email_nao_informado'

        # Utilize o valor 1 quando para o turno Matutino.
        # Utilize o valor 2 quando para o turno Vespertino.
        # Utilize o valor 3 quando para o turno Noturno.
        # Utilize o valor 4 quando para o turno Integral.
        turno = 0
        if aluno.turno:
            if aluno.turno.id == Turno.MATUTINO:
                turno = 1
            elif aluno.turno.id == Turno.VESPERTINO:
                turno = 2
            elif aluno.turno.id == Turno.NOTURNO:
                turno = 3
            elif aluno.turno.id == Turno.DIURNO:
                turno = 4

        row = [aluno.curso_campus.codigo_emec, curso_codigo, curso_nome, curso_tipo, cpf_limpo, csf, integralidade, media, email, turno, 0]
        rows.append(row)

    return XlsResponse(rows, processo=task)


@task('Exportar Dados para STTU')
def exportar_para_sttu(qs, task=None):
    from edu.sttu import Exportador

    Exportador(qs, task)


@task('Calcular Frequência Pé-de-Meia')
def calcular_frequencia_pedemeia(ano_letivo, periodo_letivo, mes, modalidades=(), atualizar_existente=True, task=None):
    pedemeia2.calcular_frequencia_suap(ano_letivo, periodo_letivo, mes, modalidades, atualizar_existente, task)


@task('Assinar Diplomas')
def assinar_diplomas_eletronicos(request, qs, id_certificado, senha_certificado, task=None):
    try:
        for assinatura_eletronica in task.iterate(qs):
            assinatura_eletronica.assinar(request, id_certificado, senha_certificado)
        return task.finalize('Assinatura realizada com sucesso.', '/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario')
    except Exception as e:
        capture_exception(e)
        if settings.DEBUG:
            raise e
        return task.finalize(
            'Diploma ainda não foi carregado. Por favor tente novamente.', '/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario', True
        )


@task('Alterar Matriz em Lote')
@transaction.atomic()
def alterar_matriz_lote(alunos_selecionados, matriz_id, motivo, vinculo, task=None):
    for aluno in task.iterate(alunos_selecionados):
        ch_cumprida_anterior = aluno.get_ch_cumprida()
        matriz_anterior = aluno.matriz

        aluno.matriz_id = matriz_id
        aluno.save()
        aluno.atualizar_situacao('Alteração de Matriz')
        aluno.identificar_registros_equivalencia(gerar=True)

        ch_cumprida_nova_matriz = aluno.get_ch_cumprida()
        if ch_cumprida_anterior != ch_cumprida_nova_matriz:
            from edu.models import ProcedimentoReducaoCH

            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = aluno.get_ultima_matricula_periodo()
            pr.tipo_procedimento = ProcedimentoReducaoCH.MUDANCA_MATRIZ
            pr.motivo = motivo
            pr.informacao_complementar = f'Alteração da matriz <strong>{matriz_anterior}</strong> para <strong>{aluno.matriz}</strong>.'
            pr.vinculo = vinculo
            pr.ch_nova = ch_cumprida_nova_matriz
            pr.ch_anterior = ch_cumprida_anterior
            pr.save()

    return task.finalize('Alteração realizada com sucesso.', '/edu/alterar_matriz_lote/')


@task('Adicionar alunos à Colação de Grau')
@transaction.atomic()
def adicionar_aluno_colacao_grau(alunos_id, colacao_grau_id, task=None):
    qs = ParticipacaoColacaoGrau.objects.filter(aluno_id__in=alunos_id, colacao_grau_id=colacao_grau_id)
    dict_participacao = {participacao.aluno_id: participacao for participacao in qs}
    for aluno_id in task.iterate(alunos_id):
        participacao_colacao_grau = dict_participacao.get(aluno_id)
        if participacao_colacao_grau is None:
            participacao_colacao_grau = ParticipacaoColacaoGrau()
            participacao_colacao_grau.aluno_id = aluno_id
            participacao_colacao_grau.colacao_grau_id = colacao_grau_id
        participacao_colacao_grau.save()

    return task.finalize('Alunos adicionados à colação de grau com sucesso.', f'/edu/colacao_grau/{colacao_grau_id}/')


@task('Evadir Alunos em Lote')
def evadir_alunos_lote(alunos_selecionados, task=None):
    qtd_nao_evadidos = 0
    for aluno in task.iterate(alunos_selecionados):
        try:
            aluno.get_ultima_matricula_periodo().evadir('Evasão em Lote')
        except ValidationError:
            qtd_nao_evadidos += 1
    if qtd_nao_evadidos:
        mensagem = f'Não foi possível evadir {qtd_nao_evadidos} aluno(s). Verifique os períodos anteriores.'
    else:
        mensagem = 'Evasão em lote realizada com sucesso.'
    return task.finalize(mensagem, '/edu/evasao_em_lote/')


@task('Imprimir Diplomas em Lote')
def imprimir_diplomas_lote(
    request,
    objs,
    modelo_documento,
    reitor_principal,
    reitor,
    diretor_geral,
    diretor_academico,
    diretor_ensino,
    coordenador_registro_academico,
    reitor_protempore,
    diretor_geral_protempore,
    task=None,
):
    from edu.views import gerar_autenticacao_diploma_pdf

    arquivos = []
    task.start_progress(len(objs) + 1)
    for _i, obj in enumerate(task.iterate(objs)):
        registro = gerar_autenticacao_diploma_pdf(request, pk=obj.pk)
        dicionario = obj.gerar_diploma(
            reitor_principal,
            reitor,
            diretor_geral,
            diretor_academico or diretor_ensino,
            coordenador_registro_academico,
            registro,
            reitor_protempore,
            diretor_geral_protempore,
        )
        caminho_arquivo = gerar_documento_impressao(dicionario, io.BytesIO(modelo_documento.template.read()))
        if not caminho_arquivo:
            task.finalize('Documento não encontrado.', error=True)
        nome_arquivo = caminho_arquivo.split('/')[-1]
        extensao = nome_arquivo.split('.')[-1]
        arquivos.append([caminho_arquivo, f'{obj.aluno.matricula}.{extensao}'])

    if len(arquivos) == 1:
        filename = arquivos[0][0]
    else:
        temp_file = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        temp_file.close()
        arquivo_zip = zipfile.ZipFile(temp_file.name, 'w')
        for arquivo, nome in arquivos:
            arquivo_zip.write(arquivo, nome)
            os.unlink(arquivo)
        arquivo_zip.close()
        filename = arquivo_zip.filename
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=filename)


def get_matriculas_periodos_relatorio_faltas(request, task, double_count=True):
    from edu.forms import RelatorioFaltasForm

    ctx = {'title': 'Relatório de Faltas', 'matriculas_periodos': [], 'lista1': []}
    form = RelatorioFaltasForm(request.GET or None, request=request)
    if form.is_valid():
        turma = form.cleaned_data['turma']
        diario = form.cleaned_data['diario']
        aluno = form.cleaned_data['aluno']
        beneficio = form.cleaned_data['beneficio']
        programa = form.cleaned_data['programa']
        uo = form.cleaned_data['uo']
        diretoria = form.cleaned_data['diretoria']
        curso_campus = form.cleaned_data['curso_campus']
        ano_letivo = form.cleaned_data['ano_letivo']
        periodo_letivo = form.cleaned_data['periodo_letivo']
        situacao_periodo = form.cleaned_data['situacao_periodo']
        intervalo_inicio = form.cleaned_data['intervalo_inicio']
        intervalo_fim = form.cleaned_data['intervalo_fim']
        situacoes_inativas = form.cleaned_data['situacoes_inativas']

        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

        qs_aulas = Aula.objects.all()
        qs_matriculas_periodo = MatriculaPeriodo.objects.all()

        if aluno:
            qs_aulas = qs_aulas.filter(professor_diario__diario__matriculadiario__matricula_periodo__aluno_id=aluno.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno_id=aluno.id)

        if programa and 'ae' in settings.INSTALLED_APPS:
            Participacao = apps.get_model('ae', 'Participacao')
            participacoes = Participacao.abertas.filter(programa__in=programa)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno__in=participacoes.values_list('aluno', flat=True))

        if beneficio:
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno__caracterizacao__beneficiario_programa_social=beneficio)

        if diario:
            qs_aulas = qs_aulas.filter(professor_diario__diario_id=diario.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(matriculadiario__diario_id=diario.id)

        if turma:
            qs_aulas = qs_aulas.filter(professor_diario__diario__turma_id=turma.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(turma_id=turma.id)

        if curso_campus:
            qs_aulas = qs_aulas.filter(professor_diario__diario__turma__curso_campus_id=curso_campus.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno__curso_campus_id=curso_campus.id)

        if uo:
            qs_aulas = qs_aulas.filter(professor_diario__diario__turma__curso_campus__diretoria__setor__uo_id=uo.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno__curso_campus__diretoria__setor__uo_id=uo.id)

        if diretoria:
            qs_aulas = qs_aulas.filter(professor_diario__diario__turma__curso_campus__diretoria_id=diretoria.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(aluno__curso_campus__diretoria_id=diretoria.id)

        if ano_letivo:
            qs_aulas = qs_aulas.filter(professor_diario__diario__matriculadiario__matricula_periodo__ano_letivo_id=ano_letivo.id)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(ano_letivo_id=ano_letivo.id)

        if periodo_letivo != '' and int(periodo_letivo):
            qs_aulas = qs_aulas.filter(professor_diario__diario__matriculadiario__matricula_periodo__periodo_letivo=periodo_letivo)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(periodo_letivo=periodo_letivo)

        if situacao_periodo:
            qs_aulas = qs_aulas.filter(professor_diario__diario__matriculadiario__matricula_periodo__situacao__in=situacao_periodo)
            qs_matriculas_periodo = qs_matriculas_periodo.filter(situacao__in=situacao_periodo)

        if intervalo_inicio:
            qs_aulas = qs_aulas.filter(data__gte=intervalo_inicio)

        if intervalo_fim:
            qs_aulas = qs_aulas.filter(data__lte=intervalo_fim)

        if qs_aulas.exists():
            data_primeira_aula = qs_aulas.order_by('data')[0].data
            data_ultima_aula = qs_aulas.latest('data').data
            data_primeira_aula = data_primeira_aula.replace(day=1)
            data_ultima_aula = data_ultima_aula.replace(day=1)
            qtd_meses = relativedelta(data_ultima_aula, data_primeira_aula).months + 1

            lista1 = [
                [
                    (data_primeira_aula + relativedelta(months=n)).year,
                    (data_primeira_aula + relativedelta(months=n)).month,
                    meses[(data_primeira_aula + relativedelta(months=n)).month - 1],
                ]
                for n in range(qtd_meses)
            ]

            matriculas_periodos = []
            if task:
                if double_count:
                    task.count(qs_matriculas_periodo, qs_matriculas_periodo)
                qs = task.iterate(qs_matriculas_periodo)
            else:
                qs = qs_matriculas_periodo
            for matricula_periodo in qs:
                qs_aulas_mp = Aula.objects.filter(professor_diario__diario__matriculadiario__matricula_periodo__aluno_id=matricula_periodo.aluno.id)
                qs_faltas = Falta.objects.filter(matricula_diario__matricula_periodo_id=matricula_periodo.id)

                if intervalo_inicio:
                    qs_aulas_mp = qs_aulas_mp.filter(data__gte=intervalo_inicio)
                    qs_faltas = qs_faltas.filter(aula__data__gte=intervalo_inicio)

                if intervalo_fim:
                    qs_aulas_mp = qs_aulas_mp.filter(data__lte=intervalo_fim)
                    qs_faltas = qs_faltas.filter(aula__data__lte=intervalo_fim)

                if diario:
                    qs_aulas_mp = qs_aulas_mp.filter(professor_diario__diario_id=diario.id)
                    qs_faltas = qs_faltas.filter(matricula_diario__diario_id=diario.id)

                aulas_faltas_abonos = []
                aulas_total = 0
                faltas_total = 0
                abonos_total = 0
                for ano, mes, _descricao in lista1:
                    aula, pks = matricula_periodo.get_qtd_aulas(qs_aulas_mp, mes, ano, situacoes_inativas) or 0
                    falta = aula and matricula_periodo.get_qtd_faltas(pks, qs_faltas) or 0
                    abono = falta and matricula_periodo.get_qtd_faltas(pks, qs_faltas, True) or 0
                    aulas_faltas_abonos.append({'aula': aula, 'falta': falta, 'abono': abono})
                    aulas_total += aula
                    faltas_total += falta
                    abonos_total += abono

                matricula_periodo.aulas_faltas_abonos = aulas_faltas_abonos
                matricula_periodo.aulas_total = aulas_total
                matricula_periodo.faltas_total = faltas_total
                matricula_periodo.abonos_total = abonos_total
                percentual_faltas = 0
                percentual_presenca = 0
                if matricula_periodo.aulas_total:
                    percentual_faltas = (matricula_periodo.faltas_total - matricula_periodo.abonos_total) * 100 / matricula_periodo.aulas_total
                    percentual_presenca = 100 - percentual_faltas

                matricula_periodo.percentual_faltas = '{number:.{digits}f}%'.format(number=percentual_faltas, digits=2)
                matricula_periodo.percentual_presenca = '{number:.{digits}f}%'.format(number=percentual_presenca, digits=2)
                matriculas_periodos.append(matricula_periodo)

            matriculas_periodos = sorted(matriculas_periodos, key=lambda x: x.percentual_presenca, reverse=True)

            ctx['matriculas_periodos'] = matriculas_periodos
            ctx['lista1'] = lista1

        ctx.update(
            {
                'aluno': aluno,
                'form': form,
                'turma': turma,
                'diario': diario,
                'uo': uo,
                'curso_campus': curso_campus,
                'diretoria': diretoria,
                'qs_aulas': qs_aulas,
            }
        )
    return ctx


@task('Listar Faltas de Alunos')
def relatorio_faltas(request, task=None):
    from edu.forms import RelatorioFaltasForm

    ctx = get_matriculas_periodos_relatorio_faltas(request, task, double_count=False)
    ctx['form'] = RelatorioFaltasForm(request.GET or None, request=request)
    response = render_to_string('relatorio_faltas.html', ctx, request)
    f = tempfile.NamedTemporaryFile(suffix='.html', mode='w+', delete=False)
    f.write(response)
    f.close()
    return task.finalize('Relatório Gerado com Sucesso', '..', file_path=f.name)


@task('Exportar Faltas de Alunos para XLS')
def relatorio_faltas_exportar(request, task=None):
    """Exporta relatório de faltas de alunos para arquivo XLS.

    Args:
        request: objeto da requisição HTTP com os parâmetros de filtro.
        campus: objeto do campus para filtrar os dados.
        task: objeto de task assíncrona para controle de progresso.

    Returns:
        str: mensagem de finalização com caminho do arquivo gerado.
    """
    import pandas as pd

    ctx = get_matriculas_periodos_relatorio_faltas(request, task)
    matriculas_periodos = ctx['matriculas_periodos']
    aluno = ctx['aluno']
    lista1 = ctx['lista1']
    lista = []
    matriculas_periodos_ids = request.POST.getlist('select_aluno')
    if matriculas_periodos_ids:
        ids = list(map(int, matriculas_periodos_ids))
        for matricula_periodo in matriculas_periodos:
            if matricula_periodo.id in ids:
                lista.append(matricula_periodo)
        matriculas_periodos = lista
    output = tempfile.NamedTemporaryFile(mode='wb', dir=os.path.join(settings.TEMP_DIR), delete=False, suffix='.xlsx')
    output.close()

    # Prepare columns for MultiIndex
    columns = []
    columns.append(('Matrícula', ''))
    columns.append(('Aluno', ''))
    if aluno:
        columns.append(('Período Letivo', ''))

    for ano, _mes, descricao in lista1:
        header = f'{descricao}/{ano}'
        columns.append((header, 'Aulas'))
        columns.append((header, 'Faltas'))
        columns.append((header, 'Abonos'))

    columns.append(('Total de Aulas', ''))
    columns.append(('Total de Faltas', ''))
    columns.append(('Percentual de Presença', ''))
    columns.append(('Percentual de Faltas', ''))
    columns.append(('Total de Justificativas', ''))
    columns.append(('Email do Aluno', ''))
    columns.append(('Telefone do Aluno', ''))
    columns.append(('Email do Responsável', ''))
    columns.append(('Telefone do Responsável', ''))

    data = []
    for matricula_periodo in matriculas_periodos:
        row = []
        row.append(matricula_periodo.aluno.matricula)
        row.append(matricula_periodo.aluno.pessoa_fisica.nome)
        if aluno:
            row.append(f'{matricula_periodo.ano_letivo.ano}/{matricula_periodo.periodo_letivo}')

        for n in matricula_periodo.aulas_faltas_abonos:
            row.append(n['aula'])
            row.append(n['falta'])
            row.append(n['abono'])

        row.append(matricula_periodo.aulas_total)
        row.append(matricula_periodo.faltas_total)
        row.append(matricula_periodo.percentual_presenca)
        row.append(matricula_periodo.percentual_faltas)
        row.append(matricula_periodo.abonos_total)

        email_aluno = matricula_periodo.aluno.email_academico or matricula_periodo.aluno.email_pessoal or '-'
        row.append(email_aluno)
        row.append(matricula_periodo.aluno.get_telefones() or '-')
        row.append(matricula_periodo.aluno.email_responsavel or '-')
        row.append('-')  # Telefone do responsavel

        data.append(row)

    mi = pd.MultiIndex.from_tuples(columns)
    df = pd.DataFrame(data, columns=mi)

    df.to_excel(output.name)

    return task.finalize('Notificações enviadas com sucesso', '..', file_path=output.name)


@task('Notificar Faltas de Alunos')
def relatorio_faltas_notificar(request, task=None):
    ctx = get_matriculas_periodos_relatorio_faltas(request, task)
    matriculas_periodos = ctx['matriculas_periodos']
    for matricula_periodo in task.iterate(matriculas_periodos):
        faltas_nao_justificadas = matricula_periodo.faltas_total - matricula_periodo.abonos_total
        if matricula_periodo.aluno.email_responsavel and faltas_nao_justificadas > 0:
            titulo = '[SUAP] Alerta de Frequência de Aluno'
            texto = (
                '<h1>Ensino</h1>'
                '<h2>Alerta de Frequência de Aluno</h2>'
                f'<p>O aluno {matricula_periodo.aluno.pessoa_fisica.nome} ({matricula_periodo.aluno.matricula}) tem {faltas_nao_justificadas:d} falta(s) não justificadas.</p>'
            )
            email_destino = [matricula_periodo.aluno.email_responsavel]
            send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, email_destino)
    return task.finalize('Notificações enviadas com sucesso', '..')


### INÍCIO MIGRAÇÃO DE DADOS V2 ###


@task('Migração de dados - Matrizes')
def importar_matrizes_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorMatrizes(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Componentes')
def importar_componentes_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorComponentes(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Cursos')
def importar_cursos_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorCursos(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Alunos')
def importar_alunos_csv_v2(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorAlunos(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Historicos')
def importar_historico_aluno_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorHistoricoAluno(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Procedimentos de matrícula')
def importar_procedimento_matricula_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorProcedimentoMatricula(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Equivalências')
def importar_equivalencia_csv(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorEquivalencia(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


@task('Migração de dados - Inicializar período letivo')
def inicializar_periodo_letivo(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=None):
    ImportadorInicializarPeriodoLetivo(arquivo_csv, apenas_validar, ignorar_obrigatorios, task=task).run()


### FIM MIGRAÇÃO DE DADOS V2 ###


@task('Gerando Cenário de Oferta')
def cenario_oferta(obj, task=None):
    context = {}
    task.count(obj.get_professores(), obj.get_grupos_atuacao(), ['1'])
    context['professores'] = []
    for professor in task.iterate(obj.get_professores()):
        prof = {
            'matricula': professor.get_matricula(),
            'nome': professor.get_nome(),
            'get_ch_semanal_professor': obj.get_ch_semanal_professor(professor.id),
            'pga_cont': professor.participacaogrupoatuacao_set.count(),
            'pgas': [],
        }
        for participacao in professor.participacaogrupoatuacao_set.all():
            pga = {'grupo_atuacao': participacao.grupo_atuacao, 'percentual': participacao.percentual, 'periodos': []}
            for periodo in obj.get_periodos():
                dados = f'{participacao.id}/{periodo}'
                pga['periodos'].append(obj.get_ch_disponivel_professor(dados))
            prof['pgas'].append(pga)
        context['professores'].append(prof)
    context['grupos_atuacao'] = []
    for grupo_atuacao in task.iterate(obj.get_grupos_atuacao()):
        grupo = {'nome': str(grupo_atuacao), 'periodos': []}
        for periodo in obj.get_periodos():
            dados = f'{grupo_atuacao.id}/{periodo}'
            periodos = {
                'get_docente_disponivel_grupo_atuacao_periodo': obj.get_docente_disponivel_grupo_atuacao_periodo(dados),
                'get_docente_necessario_grupo_atuacao_periodo': obj.get_docente_necessario_grupo_atuacao_periodo(dados),
                'get_docente_saldo_grupo_atuacao_periodo': obj.get_docente_saldo_grupo_atuacao_periodo(dados),
                'get_ch_disponivel_grupo_atuacao_periodo': obj.get_ch_disponivel_grupo_atuacao_periodo(dados),
                'get_ch_necessaria_grupo_atuacao_periodo': obj.get_ch_necessaria_grupo_atuacao_periodo(dados),
                'get_ch_saldo_grupo_atuacao_periodo': obj.get_ch_saldo_grupo_atuacao_periodo(dados),
            }
            grupo['periodos'].append(periodos)

        context['grupos_atuacao'].append(grupo)
    cache.set(f'edu_cenariooferta_{obj.id}', context)
    task.finalize('Variáveis reprocessadas com sucesso.', obj.get_absolute_url())


@task('Gerando crachás de alunos')
def imprime_cracha(request, alunos, task=None):
    if not Configuracao.get_valor_por_chave('edu', 'caminho_arquivo_cracha'):
        task.finalize('Erro ao tentar recuperar o caminho do arquivo do crachá.', error=True)
    imagemfundo = os.path.join(os.getcwd(), settings.BASE_DIR, Configuracao.get_valor_por_chave('edu', 'caminho_arquivo_cracha'))
    altura = 85 * mm
    largura = 54 * mm
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='wb', delete=False)
    tmp.close()
    c = Canvas(tmp.name, pagesize=(largura, altura))
    for aluno in task.iterate(alunos):
        if not aluno.foto:
            continue
        sangue = ''
        if aluno.pessoa_fisica.grupo_sanguineo and aluno.pessoa_fisica.fator_rh:
            grupo = aluno.getattr('pessoa_fisica.grupo_sanguineo', request, justification='')
            fator = aluno.getattr('pessoa_fisica.fator_rh', request, justification='')
            sangue = f'{grupo}{fator}'
        c.drawInlineImage(imagemfundo, 0.2 * mm, 0.2 * mm, largura - 0.2 * mm, altura - 0.2 * mm, preserveAspectRatio=True)
        c.setFillColorRGB(1, 1, 1)
        font_size = 10
        left = 3.7
        if sangue == 'AB+' or sangue == 'AB-':
            font_size = 7
            left = 3.4
        imagemfoto = aluno.getattr('get_foto_path', request, justification='')
        c.setFont('Helvetica-Bold', font_size)
        c.drawString(left * mm, 3 * mm, sangue)
        c.drawInlineImage(imagemfoto, 13.3 * mm, 25.0 * mm, 27.4 * mm, 36.5 * mm)
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica-Bold', 10)
        if aluno.pessoa_fisica.nome_usual:
            nome = aluno.getattr('pessoa_fisica.nome_usual', request, justification='').upper()
        else:
            nome = aluno.getattr('get_nome', request, justification='').upper()
            tokens = nome.split(' ')
            nome = f'{tokens[0]} {tokens[-1]}'

        matricula = aluno.getattr('matricula', request, justification='')
        c.drawCentredString(largura / 2, 20 * mm, nome)
        c.drawCentredString(largura / 2, 16 * mm, str(matricula))
        c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(largura / 2, 12 * mm, 'ALUNO')
        c.rotate(90)
        c.showPage()
    c.save()
    task.finalize('Processamento realizado com sucesso.', file_path=tmp.name)


@task('Download arquivo de estudantes com inscrição de ingressante do curso no Enade')
def download_estudantes_ingressantes_avaliacao_teorica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso, task=None):
    # Extrai o nome do arquivo com extensão
    nome_arquivo_zip = os.path.basename(file_path)
    # Remove a extensão e retorna o nome do arquivo
    nome_arquivo_zip = os.path.splitext(nome_arquivo_zip)[0]
    nome_arquivo_zip = f'/tmp/{nome_arquivo_zip}.zip'
    arquivo_zip = zipfile.ZipFile(nome_arquivo_zip, mode='w')
    task.total = lista_convocados.count()
    task.partial = 1
    Task.objects.filter(pk=task.pk).update(partial=task.partial, total=task.total)
    mensagens_erro = []
    with open(file_path, 'w') as arquivo:
        writer = csv.writer(arquivo, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                'CO_PROJETO',
                'TP_ORIGEM',
                'CO_IES',
                'CO_CURSO',
                'NU_CPF',
                'NU_ANO_FIM_ENSINO_MEDIO',
                'CO_TURNO_GRADUACAO',
                'NU_PERCENTUAL_INTEGRALIZACAO',
                'NU_ANO_INICIO_GRADUACAO',
                'NU_SEMESTRE_INICIO_GRADUACAO',
            ]
        )

        for convocacao in task.iterate(lista_convocados):
            integralizacao = convocacao.percentual_ch_cumprida or 0
            integralizacao = round(integralizacao, 1)

            ano_fim_ensino_medio = convocacao.aluno.ano_conclusao_estudo_anterior.ano if convocacao.aluno.ano_conclusao_estudo_anterior else ''
            turno_graduacao = convocacao.aluno.turno.codigo_enade if convocacao.aluno.turno else ''
            ano_inicio_graduacao = convocacao.aluno.ano_letivo.ano if convocacao.aluno.ano_letivo else ''

            # Verificando campos nulos e adicionando mensagens de erro
            if not ano_fim_ensino_medio:
                mensagens_erro.append(f'Ano de conclusão do ensino médio faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not turno_graduacao:
                mensagens_erro.append(f'Turno de graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not ano_inicio_graduacao:
                mensagens_erro.append(f'Ano de início da graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')

            row = [
                codigo_projeto,
                'E',  # Valor fixo, OK
                codigo_IES,
                codigo_curso,
                cpf_sem_caracteres(convocacao.aluno.pessoa_fisica.cpf),
                ano_fim_ensino_medio,  # 'NU_ANO_FIM_ENSINO_MEDIO',
                turno_graduacao,  # 'CO_TURNO_GRADUACAO',
                integralizacao,  # 'NU_PERCENTUAL_INTEGRALIZACAO'
                ano_inicio_graduacao,  # 'NU_ANO_INICIO_GRADUACAO',
                convocacao.aluno.periodo_letivo,  # 'NU_SEMESTRE_INICIO_GRADUACAO'
            ]
            writer.writerow(row)

    arquivo_zip.write(file_path, os.path.basename(file_path))

    if mensagens_erro:
        error_file_name = f'erros_{os.path.basename(file_path)}'
        error_file_path = os.path.join(os.path.dirname(file_path), error_file_name)
        # Escreve as mensagens de erro no arquivo de erros
        with open(error_file_path, 'w') as output:
            output.write('\r\n'.join(mensagens_erro))
        arquivo_zip.write(error_file_path, os.path.basename(error_file_path))

    arquivo_zip.close()
    task.finalize('Arquivos gerados com sucesso.', file_path=arquivo_zip.filename)


@task('Download arquivo de estudantes com inscrição de concluintes do curso no Enade')
def download_estudantes_concluintes_avaliacao_teorica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso, task=None):
    # Extrai o nome do arquivo com extensão
    nome_arquivo_zip = os.path.basename(file_path)
    # Remove a extensão e retorna o nome do arquivo
    nome_arquivo_zip = os.path.splitext(nome_arquivo_zip)[0]
    nome_arquivo_zip = f'/tmp/{nome_arquivo_zip}.zip'
    arquivo_zip = zipfile.ZipFile(nome_arquivo_zip, mode='w')
    task.total = lista_convocados.count()
    task.partial = 1
    Task.objects.filter(pk=task.pk).update(partial=task.partial, total=task.total)
    mensagens_erro = []
    with open(file_path, 'w') as arquivo:
        writer = csv.writer(arquivo, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                'CO_PROJETO',
                'TP_ORIGEM',
                'CO_IES',
                'CO_CURSO',
                'NU_CPF',
                'NU_ANO_FIM_ENSINO_MEDIO',
                'CO_TURNO_GRADUACAO',
                'NU_PERCENTUAL_INTEGRALIZACAO',
                'NU_ANO_FORMATURA',
                'NU_SEMESTRE_FORMATURA',
                'NU_ANO_INICIO_GRADUACAO',
                'IN_MUNICIPIO_POLO_EXTERIOR',
                'CO_MUNICIPIO_POLO',
            ]
        )

        for convocacao in task.iterate(lista_convocados):
            integralizacao = convocacao.percentual_ch_cumprida or 0
            integralizacao = round(integralizacao, 1)

            ano_fim_ensino_medio = convocacao.aluno.ano_conclusao_estudo_anterior.ano if convocacao.aluno.ano_conclusao_estudo_anterior else ''
            turno_graduacao = convocacao.aluno.turno.codigo_enade if convocacao.aluno.turno else ''
            ano_formatura, semestre_formatura = convocacao.get_ano_semestre_conclusao_curso()
            ano_inicio_graduacao = convocacao.aluno.ano_letivo.ano if convocacao.aluno.ano_letivo else ''
            polo = convocacao.aluno.polo.cidade.codigo if convocacao.aluno.polo and convocacao.aluno.polo.cidade else ''

            # Verificando campos nulos e adicionando mensagens de erro
            if not ano_fim_ensino_medio:
                mensagens_erro.append(f'Ano de conclusão do ensino médio faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not turno_graduacao:
                mensagens_erro.append(f'Turno de graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not ano_inicio_graduacao:
                mensagens_erro.append(f'Ano de início da graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')

            row = [
                codigo_projeto,
                'E',  # Valor fixo
                codigo_IES,
                codigo_curso,
                cpf_sem_caracteres(convocacao.aluno.pessoa_fisica.cpf) or '',  # 'NU_CPF',
                ano_fim_ensino_medio,  # 'NU_ANO_FIM_ENSINO_MEDIO'
                turno_graduacao,  # 'CO_TURNO_GRADUACAO'
                integralizacao,  # 'NU_PERCENTUAL_INTEGRALIZACAO'
                ano_formatura,  # 'NU_ANO_FORMATURA'
                semestre_formatura,  # 'NU_SEMESTRE_FORMATURA'
                ano_inicio_graduacao,  # 'NU_ANO_INICIO_GRADUACAO'
                '0',  # 'IN_MUNICIPIO_POLO_EXTERIOR' -> fixo
                polo,  # 'CO_MUNICIPIO_POLO'
            ]

            writer.writerow(row)

    arquivo_zip.write(file_path, os.path.basename(file_path))

    if mensagens_erro:
        error_file_name = f'erros_{os.path.basename(file_path)}'
        error_file_path = os.path.join(os.path.dirname(file_path), error_file_name)
        # Escreve as mensagens de erro no arquivo de erros
        with open(error_file_path, 'w') as output:
            output.write('\r\n'.join(mensagens_erro))
        arquivo_zip.write(error_file_path, os.path.basename(error_file_path))

    arquivo_zip.close()
    task.finalize('Arquivos gerados com sucesso.', file_path=arquivo_zip.filename)


@task('Download arquivo de orientadores de estágio do(s) estudante(s) habilitado(s) para avaliação da prática')
def download_professores_orientadores_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso, task=None):
    # Extrai o nome do arquivo com extensão
    nome_arquivo_zip = os.path.basename(file_path)
    # Remove a extensão e retorna o nome do arquivo
    nome_arquivo_zip = os.path.splitext(nome_arquivo_zip)[0]
    nome_arquivo_zip = f'/tmp/{nome_arquivo_zip}.zip'
    arquivo_zip = zipfile.ZipFile(nome_arquivo_zip, mode='w')
    task.total = lista_convocados.count()
    task.partial = 1
    Task.objects.filter(pk=task.pk).update(partial=task.partial, total=task.total)
    mensagens_erro = []
    with open(file_path, 'w') as arquivo:
        writer = csv.writer(arquivo, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                'CO_PROJETO',
                'TP_PERIODO',
                'TP_ORIGEM',
                'CO_IES',
                'CO_CURSO',
                'NU_CPF_ORIENTADOR',
            ]
        )

        linhas_unicas = set()
        for convocacao in task.iterate(lista_convocados):
            integralizacao = convocacao.percentual_ch_cumprida or 0
            integralizacao = round(integralizacao, 1)
            cpf_professor = (
                cpf_sem_caracteres(convocacao.estagio_docente.professor_orientador.vinculo.pessoa.pessoafisica.cpf)
                if convocacao.estagio_docente.professor_orientador and convocacao.estagio_docente.professor_orientador.vinculo
                else ''
            )

            periodo_convocacao = ''
            if convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month <= 6:
                periodo_convocacao = 1
            elif convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month > 6:
                periodo_convocacao = 2

            # Verificando campos nulos e adicionando mensagens de erro
            if not periodo_convocacao:
                mensagens_erro.append(f'Período da avaliação da prática faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not cpf_professor:
                mensagens_erro.append(f'CPF do professor faltante para o professor orientador do aluno {convocacao.aluno.pessoa_fisica.nome}')

            row = [
                codigo_projeto,
                periodo_convocacao,  # 'TP_PERIODO'
                'E',  # Valor fixo, OK
                codigo_IES,
                codigo_curso,
                cpf_professor,
            ]
            row_tuple = tuple(row)
            if row_tuple in linhas_unicas:
                continue  # Pula a linha se já tiver sido adicionada
            linhas_unicas.add(row_tuple)  # Adiciona a linha como tupla para garantir unicidade
            writer.writerow(row)

    arquivo_zip.write(file_path, os.path.basename(file_path))

    if mensagens_erro:
        error_file_name = f'erros_{os.path.basename(file_path)}'
        error_file_path = os.path.join(os.path.dirname(file_path), error_file_name)
        # Escreve as mensagens de erro no arquivo de erros
        with open(error_file_path, 'w') as output:
            output.write('\r\n'.join(mensagens_erro))
        arquivo_zip.write(error_file_path, os.path.basename(error_file_path))

    arquivo_zip.close()
    task.finalize('Arquivos gerados com sucesso.', file_path=arquivo_zip.filename)


@task('Download arquivo de supervisores de estágio do(s) estudante(s) habilitado(s) para avaliação da prática')
def download_professores_supervisores_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso, task=None):
    # Extrai o nome do arquivo com extensão
    nome_arquivo_zip = os.path.basename(file_path)
    # Remove a extensão e retorna o nome do arquivo
    nome_arquivo_zip = os.path.splitext(nome_arquivo_zip)[0]
    nome_arquivo_zip = f'/tmp/{nome_arquivo_zip}.zip'
    arquivo_zip = zipfile.ZipFile(nome_arquivo_zip, mode='w')
    task.total = lista_convocados.count()
    task.partial = 1
    Task.objects.filter(pk=task.pk).update(partial=task.partial, total=task.total)
    mensagens_erro = []
    with open(file_path, 'w') as arquivo:
        writer = csv.writer(arquivo, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                'CO_PROJETO',
                'TP_PERIODO',
                'TP_ORIGEM',
                'CO_IES',
                'CO_CURSO',
                'NU_CPF_SUPERVISOR',
                'CO_ENTIDADE',
            ]
        )

        linhas_unicas = set()
        for convocacao in task.iterate(lista_convocados):
            integralizacao = convocacao.percentual_ch_cumprida or 0
            integralizacao = round(integralizacao, 1)

            cpf_professor = (
                cpf_sem_caracteres(convocacao.estagio_docente.cpf_professor_colaborador)
                if convocacao.estagio_docente.cpf_professor_colaborador
                else ''
            )
            periodo_convocacao = ''
            if convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month <= 6:
                periodo_convocacao = 1
            elif convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month > 6:
                periodo_convocacao = 2
            escola = (
                convocacao.estagio_docente.local.codigo_inep
                if convocacao.estagio_docente and convocacao.estagio_docente.local and convocacao.estagio_docente.local
                else ''
            )

            # Verificando campos nulos e adicionando mensagens de erro
            if not periodo_convocacao:
                mensagens_erro.append(f'Período da avaliação da prática faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not cpf_professor:
                mensagens_erro.append(f'CPF do professor faltante para o professor supervisor do aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not escola:
                mensagens_erro.append(
                    f'Código da escola da educação básica (local onde o estudante está realizando o estágio obrigatório) faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}'
                )

            row = [
                codigo_projeto,
                periodo_convocacao,  # 'TP_PERIODO'
                'E',  # Valor fixo, OK
                codigo_IES,
                codigo_curso,
                cpf_professor,
                escola,  # 'CO_ENTIDADE'
            ]
            row_tuple = tuple(row)
            if row_tuple in linhas_unicas:
                continue  # Pula a linha se já tiver sido adicionada
            linhas_unicas.add(row_tuple)  # Adiciona a linha como tupla para garantir unicidade
            writer.writerow(row)

    arquivo_zip.write(file_path, os.path.basename(file_path))

    if mensagens_erro:
        error_file_name = f'erros_{os.path.basename(file_path)}'
        error_file_path = os.path.join(os.path.dirname(file_path), error_file_name)
        # Escreve as mensagens de erro no arquivo de erros
        with open(error_file_path, 'w') as output:
            output.write('\r\n'.join(mensagens_erro))
        arquivo_zip.write(error_file_path, os.path.basename(error_file_path))

    arquivo_zip.close()
    task.finalize('Arquivos gerados com sucesso.', file_path=arquivo_zip.filename)


@task('Download arquivo de estudante(s) habilitado(s) para avaliação da prática')
def download_estudantes_habilitados_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso, task=None):
    # Extrai o nome do arquivo com extensão
    nome_arquivo_zip = os.path.basename(file_path)
    # Remove a extensão e retorna o nome do arquivo
    nome_arquivo_zip = os.path.splitext(nome_arquivo_zip)[0]
    nome_arquivo_zip = f'/tmp/{nome_arquivo_zip}.zip'
    arquivo_zip = zipfile.ZipFile(nome_arquivo_zip, mode='w')
    task.total = lista_convocados.count()
    task.partial = 1
    Task.objects.filter(pk=task.pk).update(partial=task.partial, total=task.total)
    mensagens_erro = []
    with open(file_path, 'w') as arquivo:
        writer = csv.writer(arquivo, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                'CO_PROJETO',
                'TP_PERIODO',
                'TP_ORIGEM',
                'CO_IES',
                'CO_CURSO',
                'NU_CPF_ESTUDANTE',
                'NU_ANO_FIM_ENSINO_MEDIO',
                'CO_TURNO_GRADUACAO',
                'NU_PERCENTUAL_INTEGRALIZACAO',
                'NU_ANO_INICIO_GRADUACAO',
                'IN_MUNICIPIO_POLO_EXTERIOR',
                'CO_MUNICIPIO_POLO',
                'NU_CPF_ORIENTADOR',
                'NU_CPF_SUPERVISOR',
                'CO_ENTIDADE',
            ]
        )

        for convocacao in task.iterate(lista_convocados):
            integralizacao = convocacao.percentual_ch_cumprida or 0
            integralizacao = round(integralizacao, 1)

            periodo_convocacao = ''
            if convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month <= 6:
                periodo_convocacao = 1
            elif convocacao.periodo_convocacao_regencia and convocacao.periodo_convocacao_regencia.data_fim.month > 6:
                periodo_convocacao = 2
            ano_fim_ensino_medio = convocacao.aluno.ano_conclusao_estudo_anterior.ano if convocacao.aluno.ano_conclusao_estudo_anterior else ''
            turno_graduacao = convocacao.aluno.turno.codigo_enade if convocacao.aluno.turno else ''
            ano_inicio_graduacao = convocacao.aluno.ano_letivo.ano if convocacao.aluno.ano_letivo else ''
            cpf_professor_orientador = (
                cpf_sem_caracteres(convocacao.estagio_docente.professor_orientador.vinculo.pessoa.pessoafisica.cpf)
                if convocacao.estagio_docente.professor_orientador and convocacao.estagio_docente.professor_orientador.vinculo
                else ''
            )
            cpf_professor_coordenador = (
                cpf_sem_caracteres(convocacao.estagio_docente.cpf_professor_colaborador)
                if convocacao.estagio_docente.cpf_professor_colaborador
                else ''
            )
            polo = convocacao.aluno.polo.cidade.codigo if convocacao.aluno.polo and convocacao.aluno.polo.cidade else ''
            escola = (
                convocacao.estagio_docente.local.codigo_inep
                if convocacao.estagio_docente and convocacao.estagio_docente.local and convocacao.estagio_docente.local
                else ''
            )

            # Verificando campos nulos e adicionando mensagens de erro
            if not periodo_convocacao:
                mensagens_erro.append(f'Período da avaliação da prática faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not ano_fim_ensino_medio:
                mensagens_erro.append(f'Ano de conclusão do ensino médio faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not turno_graduacao:
                mensagens_erro.append(f'Turno de graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not ano_inicio_graduacao:
                mensagens_erro.append(f'Ano de início da graduação faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not cpf_professor_orientador:
                mensagens_erro.append(f'CPF do professor orientador faltante para o professor do aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not cpf_professor_coordenador:
                mensagens_erro.append(f'CPF do professor coordenador faltante para o professor do aluno {convocacao.aluno.pessoa_fisica.nome}')
            if not escola:
                mensagens_erro.append(
                    f'Código da escola da educação básica (local onde o estudante está realizando o estágio obrigatório) faltante para o aluno {convocacao.aluno.pessoa_fisica.nome}'
                )

            row = [
                codigo_projeto,
                periodo_convocacao,  #  'TP_PERIODO'
                'E',  # Valor fixo, OK
                codigo_IES,
                codigo_curso,
                cpf_sem_caracteres(convocacao.aluno.pessoa_fisica.cpf),
                ano_fim_ensino_medio,  # 'NU_ANO_FIM_ENSINO_MEDIO',
                turno_graduacao,  # 'CO_TURNO_GRADUACAO',
                integralizacao,  # 'NU_PERCENTUAL_INTEGRALIZACAO'
                ano_inicio_graduacao,  # 'NU_ANO_INICIO_GRADUACAO',
                '0',  # 'IN_MUNICIPIO_POLO_EXTERIOR' -> 0 = Cursos presenciais e EaD com polo no Brasil
                polo,  # 'CO_MUNICIPIO_POLO' aluno.polo.cidade.codigo
                cpf_professor_orientador,
                cpf_professor_coordenador,
                escola,  # 'CO_ENTIDADE'
            ]
            writer.writerow(row)

    arquivo_zip.write(file_path, os.path.basename(file_path))

    if mensagens_erro:
        error_file_name = f'erros_{os.path.basename(file_path)}'
        error_file_path = os.path.join(os.path.dirname(file_path), error_file_name)
        # Escreve as mensagens de erro no arquivo de erros
        with open(error_file_path, 'w') as output:
            output.write('\r\n'.join(mensagens_erro))
        arquivo_zip.write(error_file_path, os.path.basename(error_file_path))

    arquivo_zip.close()
    task.finalize('Arquivos gerados com sucesso.', file_path=arquivo_zip.filename)


@task('Imprimir relatório de alunos')
def relatorio_pdf(request, alunos, filtros, formatacao, campos_exibicao, task=None):
    from edu import views

    pdf = views.relatorio_pdf(request, alunos, filtros, formatacao, campos_exibicao, task)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf.content)
    tmp.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Exportar Relatório de Aluno para Programa Pé-de-meia em CSV')
def relatorio_pe_de_meia_csv(is_administrador, alunos, task=None):
    rows = [
        [
            'ESTUDANTE_CPF',
            'ESTUDANTE_NU_NIS',
            'ESTUDANTE_NOME',
            'ESTUDANTE_NOME_SOCIAL',
            'ESTUDANTE_DT_NASCIMENTO',
            'ESTUDANTE_MAE_NOME',
            'CO_ENTIDADE',
            'NO_ENTIDADE',
            'CO_MATRICULA_REDE',
            'DATA_INICIO_PERIODO_LETIVO',
            'DATA_INICIO_MATRICULA',
            'NU_ANO_MATRICULA',
            'ESTUDANTE_ETAPA_DE_ENSINO',
            'TURMA_FORMA_ORGANIZACAO',
            'TURMA_ORGANIZACAO_QUANTIDADE_TOTAL',
            'ESTUDANTE_ANO_PERIODO',
            'ESTUDANTE_E_MAIL',
            'ESTUDANTE_INTEGRAL',
            'ESTUDANTE_NU_RG',
            'ESTUDANTE_ORGAO_EMISSOR_RG',
            'ESTUDANTE_NU_CNH',
            'ESTUDANTE_NU_CERTIDAO_NASCIMENTO',
            'RESPONSAVEL_NU_CPF',
            'RESPONSAVEL_NU_NIS',
            'ESTUDANTE_DS_LOGRADOURO_RES',
            'ESTUDANTE_BAIRRO_RES',
            'ESTUDANTE_NU_ENDERECO_RES',
            'ESTUDANTE_CEP_RES',
            'ESTUDANTE_CO_MUNICIPIO_RES',
            'ESTUDANTE_CO_UF_RES',
            'ESTUDANTE_RACA_COR',
            'ESTUDANTE_DEFICIENCIA_BAIXA_VISAO',
            'ESTUDANTE_DEFICIENCIA_CEGUEIRA',
            'ESTUDANTE_DEFICIENCIA_AUDITIVA',
            'ESTUDANTE_DEFICIENCIA_FISICA',
            'ESTUDANTE_DEFICIENCIA_INTELECTUAL',
            'ESTUDANTE_DEFICIENCIA_SURDEZ',
            'ESTUDANTE_DEFICIENCIA_SURDOCEGUEIRA',
            'ESTUDANTE_DEFICIENCIA_MULTIPLA',
            'ESTUDANTE_TRANSTORNO_ESPECTRO_AUTISTA',
            'ESTUDANTE_ALTAS_HABILIDADES_SUPERDOTACAO',
            'ESTUDANTE_GENERO',
            'ESTUDANTE_PPL',
        ]
    ]
    i = 0
    for aluno in task.iterate(alunos):
        i += 1
        campus = aluno.curso_campus.diretoria and aluno.curso_campus.diretoria.setor and aluno.curso_campus.diretoria.setor.uo
        etapa = ''
        if aluno.curso_campus.modalidade_id == Modalidade.INTEGRADO:
            if aluno.periodo_atual == 1:
                etapa = 30
            elif aluno.periodo_atual == 2:
                etapa = 31
            elif aluno.periodo_atual == 3:
                etapa = 32
            elif aluno.periodo_atual == 4:
                etapa = 33
        elif aluno.curso_campus.modalidade.descricao == 'Concomitante':
            etapa = 39
        elif aluno.curso_campus.modalidade.descricao == 'FIC Integrado EJA':
            etapa = 67
        if not etapa or not aluno.pessoa_fisica.cpf:
            continue

        matriculas_periodo = aluno.get_matriculas_periodo()
        primeira_matricula_periodo = matriculas_periodo.last()
        ultima_matricula_periodo = matriculas_periodo.first()

        data_matricula = (
            primeira_matricula_periodo.turma.calendario_academico.data_inicio
            if primeira_matricula_periodo
            and primeira_matricula_periodo.turma
            and primeira_matricula_periodo.turma.calendario_academico
            and primeira_matricula_periodo.turma.calendario_academico.data_inicio
            else None
        )

        rows.append(
            [
                ''.join(filter(str.isdigit, aluno.pessoa_fisica.cpf)),  # CPF
                '',  # NIS
                aluno.pessoa_fisica.nome_registro,  # nome
                aluno.pessoa_fisica.nome_social if is_administrador else 'Sem permissão',  # nome_social
                aluno.pessoa_fisica.nascimento_data and aluno.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y') or '',  # data nascimento DD/MM/AAAA
                aluno.nome_mae or aluno.pessoa_fisica.nome_mae,  # nome mãe
                campus and campus.codigo_inep or '',  # Código INEP da unidade de ensino
                campus and campus.nome or '',  # nome da unidade de ensino
                aluno.matricula,  # matrícula
                ultima_matricula_periodo
                and ultima_matricula_periodo.turma
                and ultima_matricula_periodo.turma.calendario_academico
                and ultima_matricula_periodo.turma.calendario_academico.data_inicio
                and ultima_matricula_periodo.turma.calendario_academico.data_inicio.strftime('%d/%m/%Y')
                or '',  # data início período letivo
                data_matricula.strftime('%d/%m/%Y') if data_matricula else '',  # data início matrícula
                data_matricula.year if data_matricula else '',  # ano matrícula
                etapa,  # etapa de ensino
                aluno.curso_campus.periodicidade,  # turma forma organização
                aluno.matriz and aluno.matriz.qtd_periodos_letivos or '',  # turma organização quantidade total
                '',  # EJA ano período
                aluno.email_pessoal or aluno.email_academico or '',  # email
                '',  # integral
                aluno.pessoa_fisica.rg,  # RG
                aluno.pessoa_fisica.rg_orgao,  # RG órgão
                aluno.pessoa_fisica.cnh_carteira,  # CNH
                '',  # Certidão nascimento
                '',  # responsável CPF
                '',  # responsável NIS
                (aluno.logradouro or aluno.pessoa_fisica.endereco or '').replace(',', ' '),  # endereço
                (aluno.bairro or aluno.pessoa_fisica.endereco_bairro or '').replace(',', ' '),  # bairro
                (aluno.numero or aluno.pessoa_fisica.endereco_numero or '').replace(',', ' '),  # número endereço
                ''.join(filter(str.isdigit, (aluno.cep or aluno.pessoa_fisica.endereco_cep))),  # cep
                '',  # código ibge do municipio
                '',  # código ibge do UF
                '',  # Raça/Cor
                '',  # deficiência baixa visão
                '',  # deficiência cegueira
                '',  # deficiência auditiva
                '',  # deficiência física
                '',  # deficiência intelectual
                '',  # deficiência surdez
                '',  # deficiência surdocegueira
                '',  # deficiência multipla
                '',  # transtorno espectro autista
                '',  # altas habilidades superdotação
                '',  # genero
                '',  # PPL
            ]
        )
    return CsvResponse(rows, processo=task, value_for_none='')


@task('Exportar Relatório para Conselho de Classe em CSV')
def relatorio_conselho_classe_csv(alunos, ano_letivo=None, periodo_letivo=None, task=None):
    rows = [['Código Turma', 'Descrição Turma', 'Aluno', 'Matrícula', 'Situação Aluno', 'Diário', 'Situação Diário', 'MD', 'MFD', 'Frequência']]

    qs_matriculas_periodo = MatriculaPeriodo.objects.none()
    qs_matriculas_periodo = MatriculaPeriodo.objects.filter(aluno__in=alunos, ano_letivo__ano=ano_letivo.ano, periodo_letivo=periodo_letivo)

    matriculas_diario = MatriculaDiario.objects.filter(matricula_periodo__in=qs_matriculas_periodo)

    for matricula_diario in task.iterate(matriculas_diario):
        rows.append(
            [
                matricula_diario.diario.turma.codigo,
                matricula_diario.diario.turma.descricao,
                matricula_diario.matricula_periodo.aluno.pessoa_fisica.nome,
                matricula_diario.matricula_periodo.aluno.matricula,
                matricula_diario.matricula_periodo.aluno.situacao,
                matricula_diario.diario,
                matricula_diario.get_situacao_nota()['rotulo'],
                matricula_diario.get_media_disciplina(),
                matricula_diario.get_media_final_disciplina(),
                f'{matricula_diario.get_percentual_carga_horaria_frequentada():.2f}',
            ]
        )
    return CsvResponse(rows, processo=task, value_for_none='')


@task('Gerar Matrículas')
def gerar_matriculas(pre_matricula, dados, task=None):
    turno = dados['turno']
    polo = dados['polo']
    forma_ingresso = dados['forma_ingresso']
    convenio_internacional = dados['convenio_internacional']
    possui_convenio = dados['possui_convenio']
    convenio = dados['convenio']
    numero_pasta = dados['numero_pasta']
    observacao_matricula = dados['observacao_matricula']
    for inscricao in task.iterate(pre_matricula.get_inscricoes_deferidas()):
        with transaction.atomic():
            inscricao.gerar_matricula(
                turno, polo, forma_ingresso, convenio_internacional, possui_convenio, convenio, numero_pasta, observacao_matricula
            )
    task.finalize('Matrículas geradas com sucesso.', f'/edu/pre_matricula_internacional/{pre_matricula.id}/?tab=pre_matricula')


@task('Relatório de Disciplinas EAD - XLS')
def relatorio_disciplinas_ead(ano_letivo, qs, task=None):
    count = 0
    rows = [['#', 'Disciplina', 'Matriz', 'Curso', 'CH Total', '% Máximo EAD', 'Qtd. de Aulas EAD', 'Professores']]
    for cc in task.iterate(qs):
        count += 1
        row = [
            count,
            str(cc.componente),
            str(cc.matriz),
            ', '.join(cc.get_cursos(ano_letivo).values_list('codigo', flat=True)),
            cc.get_carga_horaria_total(),
            f'{cc.percentual_maximo_ead}%',
            cc.qtd_aulas_ead,
            ', '.join([professor.get_matricula() for professor in cc.get_professores(ano_letivo)]),
        ]
        rows.append(row)
    XlsResponse(rows, processo=task)
