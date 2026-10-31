import datetime
from collections import OrderedDict

import pandas as pd
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models.aggregates import Avg, Max, Min, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from comum.models import Ano, APIExterna
from djtools.templatetags.filters import format_
from djtools.utils import (
    XlsResponse,
    documento,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu import perms, tasks
from edu.forms import (
    AdicionarAlunosTurmaMinicursoForm,
    DefinirLocalAulaTurmaForm,
    EfetuarMatriculasTurmaForm,
    EfetuarMatriculaTurmaForm,
    EstatisticaTurmaForm,
    GerarDiarioForm,
    GerarTurmasForm,
    MapaTurmaForm,
    TransferirTurmaForm,
)
from edu.models import Aluno, MatriculaDiario, MatriculaPeriodo, Polo, RotuloModulo, Turma, Turno


@permission_required('edu.gerar_turmas')
@rtr()
def gerar_turmas(request):
    title = 'Gerar Turmas'
    form = GerarTurmasForm(request, data=request.GET or None, initial={'periodo_letivo': 1})
    if form.is_valid():
        form.processar(commit=True)
        ids = []
        for turma in form.turmas:
            ids.append(str(turma.id))
        ano = get_object_or_404(Ano, ano=datetime.datetime.now().year)
        return httprr('/admin/edu/turma/?id__in={}'.format(','.join(ids)), 'Turmas geradas com sucesso.')
    return locals()


@permission_required('edu.gerar_turmas')
@rtr()
def gerar_diarios(request, pk):
    title = 'Gerar diários'
    turma = get_object_or_404(Turma.locals, pk=pk)
    form = GerarDiarioForm(data=request.POST or None, turma=turma)
    if form.is_valid():
        form.processar()
        return httprr(turma.get_absolute_url(), 'Diários gerados com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.view_turma')
@rtr()
def adicionar_alunos_turma_minicurso(request, pk):
    manager = request.user.has_group_cached('Diretor Acadêmico') and Turma.objects or Turma.locals
    obj = get_object_or_404(manager, pk=pk)
    title = f'Turma {obj} - Adicionar alunos à turma de minicurso'
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.curso_campus)
    if pode_realizar_procedimentos:
        form = AdicionarAlunosTurmaMinicursoForm(obj, data=request.POST or None, request=request)
        if form.is_valid():
            erros = form.processar()
            if erros:
                return httprr(
                    f'/edu/turma/{obj.pk}/?tab=dados_alunos', mark_safe('Foram encontrados os seguintes erros:<br>' + '<br>'.join(erros)), 'error'
                )
            return httprr(f'/edu/turma/{obj.pk}/?tab=dados_alunos', 'Alunos adicionados com sucesso.')
    return locals()


@permission_required('edu.view_turma')
@rtr()
def turma(request, pk):
    manager = request.user.has_group_cached('Diretor Acadêmico') and Turma.objects or Turma.locals
    obj = get_object_or_404(manager, pk=pk)
    title = f'Turma {obj}'

    qtd_alunos_ativos = obj.get_qtd_alunos_ativos()
    qtd_diarios = obj.diario_set.count()

    diarios_pendentes = obj.get_diarios_pendentes()
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.curso_campus)
    pode_gerar_diario = pode_realizar_procedimentos and obj.pode_gerar_diario()
    regime_modular = obj.matriz.is_regime_modular()

    if request.GET.get('tab') in ['dados_diarios', 'horarios'] or request.GET.get('tab') is None:
        diarios = obj.diario_set.order_by('componente_curricular__tipo_modulo', 'componente_curricular__componente__descricao', 'id')

    if request.GET.get('tab') == 'dados_alunos':
        alunos = obj.get_alunos_matriculados()
        alunos_diarios = obj.get_alunos_matriculados_diarios()

    if request.GET.get('tab') == 'horarios':
        semestre = request.GET.get('semestre') or '1'
        turnos = obj.get_horarios(semestre)
        diarios_por_sigla = diarios.filter(horarioauladiario__isnull=False).distinct()

    if request.GET.get('tab') == 'dados_modulos':
        modulos = []
        for modulo in (
            obj.diario_set.values_list('componente_curricular__tipo_modulo', flat=True).distinct().order_by('componente_curricular__tipo_modulo')
        ):
            nome = RotuloModulo.objects.filter(matriz_id=obj.matriz_id, tipo_modulo=modulo).only('descricao').first()
            pode_fechar = (
                MatriculaDiario.objects.filter(
                    situacao=MatriculaDiario.SITUACAO_CURSANDO,
                    matricula_periodo_id__in=obj.matriculaperiodo_set.values_list('id', flat=True),
                    diario__componente_curricular__tipo_modulo=modulo,
                )
                .values_list('matricula_periodo_id', flat=True)
                .exists()
            )
            pode_reabrir = (
                MatriculaDiario.objects.filter(
                    situacao__in=[
                        MatriculaDiario.SITUACAO_APROVADO,
                        MatriculaDiario.SITUACAO_REPROVADO,
                        MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
                    ],
                    matricula_periodo_id__in=obj.matriculaperiodo_set.values_list('id', flat=True),
                    diario__componente_curricular__tipo_modulo=modulo,
                )
                .values_list('matricula_periodo_id', flat=True)
                .exists()
            )
            modulos.append(
                {
                    'modulo': modulo,
                    'nome': nome or f'Módulo {modulo}',
                    'pode_fechar': pode_fechar,
                    'pode_reabrir': pode_reabrir,
                }
            )

    ids = request.GET.get('matriculas_periodo')
    url_redirect = f'/edu/turma/{pk}/?tab=dados_alunos'
    if ids:
        if not pode_realizar_procedimentos:
            return httprr(url_redirect, 'Você não tem permissão para realizar isso.', 'error')
        matriculas_periodo = MatriculaPeriodo.objects.filter(id__in=ids.split('_'), turma_id=pk)
        alunos_removidos = obj.remover_alunos(matriculas_periodo, request.user)

        if alunos_removidos:
            alunos_str = ', '.join([str(aluno) for aluno in alunos_removidos])
            return httprr(url_redirect, f'O(s) aluno(s) {alunos_str} foi(ram) removido(s) da turma com sucesso.')
        else:
            return httprr(url_redirect, 'Nenhum dos alunos selecionados pôde ser removido da turma.', 'error')

    if 'moodle' in request.GET and obj.tem_integracao_com_moodle():
        if not APIExterna.MOODLE.ativo:
            return httprr(url_redirect, 'A integração com o Moodle não está ativa temporariamente, tente mais tarde.', 'error')
        return tasks.sincronizar_turma_moodle(obj)

    if 'boletim' in request.GET:
        ids = '_'.join([str(pk) for pk in obj.matriculaperiodo_set.values_list('pk', flat=True)])
        return httprr(f'/edu/emitir_boletim_pdf/{ids}/')

    return locals()


@group_required('Administrador Acadêmico, Diretor Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Secretário Acadêmico')
@rtr('transferir_turma_ou_diario.html')
def transferir_turma(request, turma_origem, alunos):
    title = 'Transferência de Turma'
    turma_origem = get_object_or_404(Turma.locals, pk=turma_origem)

    if turma_origem.matriz.estrutura.tipo_avaliacao != turma_origem.matriz.estrutura.TIPO_AVALIACAO_SERIADO:
        httprr('..', 'Transferência de turma só é realizada para alunos do regime seriado.', 'error')
    matriculas_periodo = alunos.split('_')

    aluno_com_nota = False
    qs_diarios = turma_origem.diario_set.all()
    mp = MatriculaPeriodo.objects.filter(id__in=matriculas_periodo)
    matriculas = MatriculaDiario.objects.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO, diario__in=qs_diarios, matricula_periodo__in=mp)

    for matricula in matriculas:
        if matricula.tem_nota_lancada():
            aluno_com_nota = True
            break

    if aluno_com_nota:
        return httprr(
            f'/edu/turma/{turma_origem.pk}/?tab=dados_alunos', 'Só é possível realizar a transferência de alunos sem nota lançada.', 'error'
        )

    form = TransferirTurmaForm(turma_origem, data=request.POST or None)

    turma_destino = form.get_entered_data('turma_destino')
    falta_diario = False
    if turma_destino:
        diarios = turma_origem.transferir(matriculas_periodo, turma_destino, False)
        for diario in diarios:
            if not diario[1]:
                falta_diario = True
                break

    if falta_diario:
        return httprr(
            f'/edu/turma/{turma_origem.pk}/?tab=dados_alunos', 'A turma de destino não possui todos os diários da turma de origem.', 'error'
        )

    if form.is_valid():
        try:
            diarios = turma_origem.transferir(matriculas_periodo, turma_destino, True)
        except ValidationError as e:
            return httprr(f'/edu/turma/{turma_origem.pk}/?tab=dados_alunos', e.message, 'error')
        return httprr(f'/edu/turma/{turma_destino.pk}/', 'Transferência realizada com sucesso.')

    return locals()


@permission_required('edu.view_turma')
@documento()
@rtr()
def horarios_turma_pdf(request, pk):
    obj = get_object_or_404(Turma.locals, pk=pk)
    uo = obj.curso_campus.diretoria.setor.uo
    title = str(obj)
    diarios = obj.diario_set.order_by('componente_curricular__componente')
    semestre = request.GET.get('semestre') or '1'
    turnos = obj.get_horarios(semestre)
    diarios_por_sigla = diarios.filter(horarioauladiario__isnull=False).distinct().order_by('componente_curricular__componente__sigla')
    return locals()


@permission_required('edu.change_turma')
@rtr()
def adicionar_aluno_turma(request, pk, ingressante=False):
    turma = get_object_or_404(Turma.locals, pk=pk)
    title = 'Adicionar Aluno à Turma'
    turnos = Turno.objects.all()
    polos = Polo.objects.all().order_by('descricao')
    polo = None
    if 'matriculas_periodo' in request.POST:
        matriculas_periodo = MatriculaPeriodo.objects.filter(id__in=request.POST.getlist('matriculas_periodo'))
        turma.matricular_alunos(matriculas_periodo)
        return httprr(f'/edu/turma/{turma.pk}/?tab=dados_alunos', 'Aluno(s) matriculado(s) com sucesso.')
    for turno in turnos:
        if 'turno' in request.POST:
            if turno.pk == int(request.POST['turno']):
                turno.selecionado = True
                break
        else:
            if turno.pk == turma.turno.pk:
                turno.selecionado = True
                break

    matriculas_periodo = turma.get_alunos_apto_matricula(turno=turno, apenas_ingressantes=ingressante)

    if request.POST.get('polo'):
        pk = int(request.POST.get('polo', '0'))
    elif hasattr(turma.polo, 'pk'):
        pk = turma.polo.pk
    else:
        pk = 0

    if pk > 0:
        for polo in polos:
            if polo.pk == pk:
                polo.selecionado = True
                break
        matriculas_periodo = matriculas_periodo.filter(aluno__polo=polo)

    return locals()


@permission_required('edu.view_turma')
@rtr()
def mapa_turma(request, pk):
    turma = get_object_or_404(Turma.locals, pk=pk)

    title = f'Mapa da Turma - {turma}'
    form = MapaTurmaForm(turma.diario_set.all().order_by('componente_curricular__componente__sigla'), request.POST or None)
    diarios = None
    if form.is_valid():
        diarios = form.cleaned_data['diarios']

        quantidade = 1
        for diario in diarios:
            if len(diario.get_lista_etapas()) > quantidade:
                quantidade = len(diario.get_lista_etapas())
        etapas = OrderedDict()
        for etapa in range(1, quantidade + 1):
            etapas[f'etapa_{etapa}'] = f'Etapa {etapa}'
        etapas['etapa_final'] = 'Etapa final'
        etapas['todas'] = 'Todas as etapas'

        matriculas_periodo = turma.get_alunos_relacionados()
        matriculas_diario = (
            MatriculaDiario.locals.filter(diario__in=diarios)
            .order_by(
                'matricula_periodo__aluno__pessoa_fisica__nome',
                'matricula_periodo__aluno__pk',
                'diario__componente_curricular__componente__sigla',
                'diario',
            )
            .annotate(total_faltas=Sum('falta__quantidade'))
            .select_related(
                'matricula_periodo__situacao',
                'matricula_periodo__turma__matriz__estrutura',
                'matricula_periodo__aluno__matriz__estrutura',
                'diario__componente_curricular__componente',
                'diario__estrutura_curso',
            )
        )

        tabela_mapa = []
        count = 0
        situacoes_diario = [md.get_situacao_diario_resumida() for md in matriculas_diario]
        for matricula_periodo in matriculas_periodo:
            aluno_diarios = []
            for diario in diarios:
                if (
                    count < matriculas_diario.count()
                    and matriculas_diario[count].diario.pk == diario.pk
                    and matriculas_diario[count].matricula_periodo.pk == matricula_periodo.pk
                ):
                    matriculas_diario[count].numero_faltas_primeira_etapa = matriculas_diario[count].get_numero_faltas_primeira_etapa()
                    matriculas_diario[count].numero_faltas_segunda_etapa = matriculas_diario[count].get_numero_faltas_segunda_etapa()

                    # Dict base
                    dados = {
                        'md': matriculas_diario[count],
                        'rotulo': situacoes_diario[count]['rotulo'],
                        'percentualfrequencia': matriculas_diario[count].get_percentual_carga_horaria_frequentada(),
                        'percentualfrequencia1': matriculas_diario[count].get_percentual_carga_horaria_frequentada(1),
                        'percentualfrequencia2': matriculas_diario[count].get_percentual_carga_horaria_frequentada(2),
                        'faltas': matriculas_diario[count].total_faltas,
                        'faltas_etapa1': matriculas_diario[count].numero_faltas_primeira_etapa,
                        'faltas_etapa2': matriculas_diario[count].numero_faltas_segunda_etapa,
                    }

                    if len(etapas) > 3:
                        matriculas_diario[count].numero_faltas_terceira_etapa = matriculas_diario[count].get_numero_faltas_terceira_etapa()
                        matriculas_diario[count].numero_faltas_quarta_etapa = matriculas_diario[count].get_numero_faltas_quarta_etapa()
                        dados.update(
                            {
                                'percentualfrequencia3': matriculas_diario[count].get_percentual_carga_horaria_frequentada(3),
                                'percentualfrequencia4': matriculas_diario[count].get_percentual_carga_horaria_frequentada(4),
                                'faltas_etapa3': matriculas_diario[count].numero_faltas_terceira_etapa,
                                'faltas_etapa4': matriculas_diario[count].numero_faltas_quarta_etapa,
                            }
                        )

                    aluno_diarios.append(dados)
                    count += 1
                else:
                    aluno_diarios.append({'md': None})
            tabela_mapa.append([matricula_periodo, aluno_diarios])

    if request.POST.get('xls'):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=mapa_turma.xlsx'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            # Prepare data for each sheet
            sheets_data = {'Etapa 1': [], 'Etapa 2': [], 'Etapa 3': [], 'Etapa 4': [], 'Etapa Final': []}

            # Headers
            headers = ['Aluno']
            for diario in diarios:
                headers.extend([diario.componente_curricular.componente.sigla, '', ''])

            subheaders = ['']
            for diario in diarios:
                subheaders.extend(
                    [f'{diario.get_carga_horaria_cumprida()}H de {diario.componente_curricular.componente.get_ch_hora_aula()}H', '', '']
                )

            subsubheaders = ['']
            for _ in diarios:
                subsubheaders.extend(['N', 'F', 'Sit.'])

            for data in sheets_data.values():
                data.append(headers)
                data.append(subheaders)
                data.append(subsubheaders)

            # Data rows
            for item in tabela_mapa:
                aluno_nome = item[0].aluno.get_nome_social_composto()

                row_etapa1 = [aluno_nome]
                row_etapa2 = [aluno_nome]
                row_etapa3 = [aluno_nome]
                row_etapa4 = [aluno_nome]
                row_final = [aluno_nome]

                # Etapa 1
                for value in item[1]:
                    if value.get('md'):
                        row_etapa1.extend(
                            [value.get('md').get_nota_boletim(1, True) or '-', value.get('faltas_etapa1') or '-', value.get('rotulo') or '-']
                        )
                    else:
                        row_etapa1.extend(['-', '-', '-'])
                if not turma.matriz.estrutura.is_lancamento_conceito():
                    row_etapa1.append(format_(item[0].get_media_na_primeira_etapa()))

                # Etapa 2
                for value in item[1]:
                    if value.get('md'):
                        row_etapa2.extend(
                            [value.get('md').get_nota_boletim(2, True) or '-', value.get('faltas_etapa2') or '-', value.get('rotulo') or '-']
                        )
                    else:
                        row_etapa2.extend(['-', '-', '-'])
                if not turma.matriz.estrutura.is_lancamento_conceito():
                    row_etapa2.append(format_(item[0].get_media_na_segunda_etapa()))

                # Etapa 3
                for value in item[1]:
                    if value.get('md'):
                        row_etapa3.extend(
                            [value.get('md').get_nota_boletim(3, True) or '-', value.get('faltas_etapa3') or '-', value.get('rotulo') or '-']
                        )
                    else:
                        row_etapa3.extend(['-', '-', '-'])
                if not turma.matriz.estrutura.is_lancamento_conceito():
                    row_etapa3.append(format_(item[0].get_media_na_terceira_etapa()))

                # Etapa 4
                for value in item[1]:
                    if value.get('md'):
                        row_etapa4.extend(
                            [value.get('md').get_nota_boletim(4, True) or '-', value.get('faltas_etapa4') or '-', value.get('rotulo') or '-']
                        )
                    else:
                        row_etapa4.extend(['-', '-', '-'])
                if not turma.matriz.estrutura.is_lancamento_conceito():
                    row_etapa4.append(format_(item[0].get_media_na_quarta_etapa()))

                # Etapa Final
                for value in item[1]:
                    if value.get('md'):
                        row_final.extend([value.get('md').get_nota_boletim(5, True) or '-', '-', value.get('rotulo') or '-'])
                    else:
                        row_final.extend(['-', '-', '-'])
                if not turma.matriz.estrutura.is_lancamento_conceito():
                    row_final.append(format_(item[0].get_media_na_etapa_final()))

                sheets_data['Etapa 1'].append(row_etapa1)
                sheets_data['Etapa 2'].append(row_etapa2)
                sheets_data['Etapa 3'].append(row_etapa3)
                sheets_data['Etapa 4'].append(row_etapa4)
                sheets_data['Etapa Final'].append(row_final)

            # Write to Excel
            for sheet_name, data in sheets_data.items():
                df = pd.DataFrame(data)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

                # Merging cells logic would be complex here, simplifying for now
                # Ideally we should use openpyxl to merge cells for headers
                worksheet = writer.sheets[sheet_name]

                # Merge headers
                col_idx = 2
                for _ in diarios:
                    worksheet.merge_cells(start_row=1, start_column=col_idx, end_row=1, end_column=col_idx + 2)
                    worksheet.merge_cells(start_row=2, start_column=col_idx, end_row=2, end_column=col_idx + 2)
                    col_idx += 3

                if not turma.matriz.estrutura.is_lancamento_conceito():
                    # Add 'Média' header if needed, assuming it's the last column
                    last_col = col_idx
                    worksheet.merge_cells(start_row=1, start_column=last_col, end_row=3, end_column=last_col)
                    worksheet.cell(row=1, column=last_col, value='Média')

        return response

    return locals()


@permission_required('edu.change_turma')
@rtr()
def definir_local_aula_turma(request, turma_pk):
    title = 'Definir Local de Aula dos Diários'
    turma = get_object_or_404(Turma.locals, pk=turma_pk)
    form = DefinirLocalAulaTurmaForm(turma, data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Local de aula dos diários definido com sucesso.')
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def efetuar_matricula_turma(request: HttpRequest, aluno_id: int) -> HttpResponse | dict[str, Any]:
    aluno = get_object_or_404(
        Aluno.objects.select_related('pessoa_fisica', 'curso_campus', 'matriz', 'turno', 'situacao', 'ano_letivo'),
        pk=aluno_id,
    )
    title = f'Matrícula em Turma - {aluno.pessoa_fisica.nome_usual} ({aluno.matricula})'

    matricula_periodo = (
        MatriculaPeriodo.objects.filter(aluno=aluno, ano_letivo=aluno.ano_letivo, periodo_letivo=aluno.periodo_letivo)
        .select_related('turma', 'situacao')
        .first()
        or aluno.get_ultima_matricula_periodo()
    )
    turma_atual = matricula_periodo.turma if matricula_periodo else None

    initial = {}
    if turma_atual:
        initial['turma'] = turma_atual.pk

    form = EfetuarMatriculaTurmaForm(aluno, data=request.POST or None, initial=initial)
    if form.is_valid():
        form.processar(aluno)
        return httprr(
            '/edu/efetuar_matricula/',
            mark_safe(
                f'Matrícula realizada com sucesso. (<a target="_blank" href="/edu/comprovante_matricula_pdf/{aluno.pk}/">Imprimir Comprovante</a>).'
            ),
        )
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def efetuar_matriculas_turma(request, turma_id):
    title = 'Matrículas em Turma'
    turma = get_object_or_404(Turma, pk=turma_id)
    form = EfetuarMatriculasTurmaForm(turma, data=request.POST or None)
    if form.is_valid():
        alunos = form.processar(turma)
        return httprr(f'/edu/turma/{turma_id}/', 'Matrículas realizadas com sucesso.')
    return locals()


@rtr()
@login_required()
def turma_estatistica(request, turma_pk):
    turma = get_object_or_404(Turma, pk=turma_pk)
    title = f'Estatística da Turma {turma.codigo}'
    if turma.matriz.estrutura.is_lancamento_conceito():
        media = turma.matriz.estrutura.get_nota_minima_aprovacao_conceito()
        media_final = media
    else:
        media = turma.matriz.estrutura.media_aprovacao_sem_prova_final
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        media_final = turma.pertence_ao_plano_retomada and 50 or turma.matriz.estrutura.media_aprovacao_avaliacao_final
    etapa_acima = {1: [], 2: [], 3: [], 4: [], 5: []}
    etapa_abaixo = {1: [], 2: [], 3: [], 4: [], 5: []}
    etapa_media_acima = {1: [], 2: [], 3: [], 4: [], 5: []}
    etapa_media_abaixo = {1: [], 2: [], 3: [], 4: [], 5: []}

    media_turma = {1: [], 2: [], 3: [], 4: [], 5: []}

    form = EstatisticaTurmaForm(data=request.POST or None)
    form.fields['diarios'].queryset = turma.diario_set.all()
    if form.is_valid():
        etapas = form.cleaned_data['etapas']
        diarios = form.cleaned_data['diarios']
        abreviar = form.cleaned_data['abreviar']
        for diario in diarios:
            matriculas_diarios = diario.matriculadiario_set.all()
            diario.total_alunos = matriculas_diarios.count()
            diario.media = OrderedDict()

            if not diario.is_semestral_segundo_semestre():
                diario.media['N1'] = []
                diario.media['N2'] = []
            if diario.is_semestral_segundo_semestre() or not diario.is_semestral_em_calendario_anual():
                diario.media['N3'] = []
                diario.media['N4'] = []
            diario.media['NAF'] = []

            if diario.is_semestral_segundo_semestre():
                # acima da média
                diario.media['N3'].append(matriculas_diarios.filter(nota_1__gte=media).count())
                diario.media['N4'].append(matriculas_diarios.filter(nota_2__gte=media).count())

                # abaixo da média
                diario.media['N3'].append(matriculas_diarios.filter(nota_1__lt=media).count())
                diario.media['N4'].append(matriculas_diarios.filter(nota_2__lt=media).count())
            else:
                # acima da média
                diario.media['N1'].append(matriculas_diarios.filter(nota_1__gte=media).count())
                diario.media['N2'].append(matriculas_diarios.filter(nota_2__gte=media).count())
                if not diario.is_semestral_em_calendario_anual():
                    diario.media['N3'].append(matriculas_diarios.filter(nota_3__gte=media).count())
                    diario.media['N4'].append(matriculas_diarios.filter(nota_4__gte=media).count())

                # abaixo da média
                diario.media['N1'].append(matriculas_diarios.filter(nota_1__lt=media).count())
                diario.media['N2'].append(matriculas_diarios.filter(nota_2__lt=media).count())
                if not diario.is_semestral_em_calendario_anual():
                    diario.media['N3'].append(matriculas_diarios.filter(nota_3__lt=media).count())
                    diario.media['N4'].append(matriculas_diarios.filter(nota_4__lt=media).count())

            diario.media['NAF'].append(matriculas_diarios.filter(nota_final__gte=media_final).count())
            diario.media['NAF'].append(matriculas_diarios.filter(nota_final__lt=media_final).count())

            if diario.is_semestral_segundo_semestre():
                notas_1 = {'media': None, 'minima': None, 'maxima': None}
                notas_2 = {'media': None, 'minima': None, 'maxima': None}
                notas_3 = matriculas_diarios.filter(nota_1__isnull=False).aggregate(media=Avg('nota_1'), minima=Min('nota_1'), maxima=Max('nota_1'))
                notas_4 = matriculas_diarios.filter(nota_2__isnull=False).aggregate(media=Avg('nota_2'), minima=Min('nota_2'), maxima=Max('nota_2'))
            else:
                notas_1 = matriculas_diarios.filter(nota_1__isnull=False).aggregate(media=Avg('nota_1'), minima=Min('nota_1'), maxima=Max('nota_1'))
                notas_2 = matriculas_diarios.filter(nota_2__isnull=False).aggregate(media=Avg('nota_2'), minima=Min('nota_2'), maxima=Max('nota_2'))
                if not diario.is_semestral_em_calendario_anual():
                    notas_3 = matriculas_diarios.filter(nota_3__isnull=False).aggregate(
                        media=Avg('nota_3'), minima=Min('nota_3'), maxima=Max('nota_3')
                    )
                    notas_4 = matriculas_diarios.filter(nota_4__isnull=False).aggregate(
                        media=Avg('nota_4'), minima=Min('nota_4'), maxima=Max('nota_4')
                    )
                else:
                    notas_3 = {'media': None, 'minima': None, 'maxima': None}
                    notas_4 = {'media': None, 'minima': None, 'maxima': None}
            notas_final = matriculas_diarios.filter(nota_final__isnull=False).aggregate(
                media=Avg('nota_final'), minima=Min('nota_final'), maxima=Max('nota_final')
            )

            # notas
            if not diario.is_semestral_segundo_semestre():
                diario.media['N1'].append(notas_1)
                diario.media['N2'].append(notas_2)
            if diario.is_semestral_segundo_semestre() or not diario.is_semestral_em_calendario_anual():
                diario.media['N3'].append(notas_3)
                diario.media['N4'].append(notas_4)
            diario.media['NAF'].append(notas_final)

            # arredondando
            for notas in (notas_1, notas_2, notas_3, notas_4):
                if notas['media']:
                    notas['media'] = round(notas['media'])
            if notas_final['media']:
                notas_final['media'] = round(notas_final['media'])

            # dados do gráfico de alunos acima e abaixo
            for i in range(4):
                if 'N' + str(i + 1) in diario.media:
                    etapa_acima[i + 1].append(diario.media['N' + str(i + 1)][0])
                    etapa_abaixo[i + 1].append(diario.media['N' + str(i + 1)][1])
                else:
                    etapa_acima[i + 1].append(0)
                    etapa_abaixo[i + 1].append(0)
            etapa_acima[5].append(diario.media['NAF'][0])
            etapa_abaixo[5].append(diario.media['NAF'][1])

            # dados do gráfico de média
            etapa_media_acima[1].append(notas_1['media'] or 0)
            etapa_media_abaixo[1].append(notas_1['media'] and 100 - notas_1['media'] or 0)
            etapa_media_acima[2].append(notas_2['media'] or 0)
            etapa_media_abaixo[2].append(notas_2['media'] and 100 - notas_2['media'] or 0)
            etapa_media_acima[3].append(notas_3['media'] or 0)
            etapa_media_abaixo[3].append(notas_3['media'] and 100 - notas_3['media'] or 0)
            etapa_media_acima[4].append(notas_4['media'] or 0)
            etapa_media_abaixo[4].append(notas_4['media'] and 100 - notas_4['media'] or 0)
            etapa_media_acima[5].append(notas_final['media'] or 0)
            etapa_media_abaixo[5].append(notas_final['media'] and 100 - notas_final['media'] or 0)

            temp = []
            temp.append(notas_1['media'] or 0)
            if not diario.is_semestral_segundo_semestre():
                temp.append(matriculas_diarios.filter(nota_1__gte=notas_1['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_1__lt=notas_1['media'] or 0).count())
            else:
                temp.append(0)
                temp.append(0)
            media_turma[1].append(temp)

            temp = []
            temp.append(notas_2['media'] or 0)
            if not diario.is_semestral_segundo_semestre():
                temp.append(matriculas_diarios.filter(nota_2__gte=notas_2['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_2__lt=notas_2['media'] or 0).count())
            else:
                temp.append(0)
                temp.append(0)
            media_turma[2].append(temp)

            temp = []
            temp.append(notas_3['media'] or 0)
            if diario.is_semestral_segundo_semestre():
                temp.append(matriculas_diarios.filter(nota_1__gte=notas_3['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_1__lt=notas_3['media'] or 0).count())
            else:
                temp.append(matriculas_diarios.filter(nota_3__gte=notas_3['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_3__lt=notas_3['media'] or 0).count())
            media_turma[3].append(temp)

            temp = []
            temp.append(notas_4['media'] or 0)
            if diario.is_semestral_segundo_semestre():
                temp.append(matriculas_diarios.filter(nota_2__gte=notas_4['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_2__lt=notas_4['media'] or 0).count())
            else:
                temp.append(matriculas_diarios.filter(nota_4__gte=notas_4['media'] or 0).count())
                temp.append(matriculas_diarios.filter(nota_4__lt=notas_4['media'] or 0).count())
            media_turma[4].append(temp)

            temp = []
            temp.append(notas_final['media'] or 0)
            temp.append(matriculas_diarios.filter(nota_final__gte=notas_final['media'] or 0).count())
            temp.append(matriculas_diarios.filter(nota_final__lt=notas_final['media'] or 0).count())
            media_turma[5].append(temp)

        for dicionario in (etapa_acima, etapa_abaixo, etapa_media_acima, etapa_media_abaixo, media_turma):
            chaves = list(dicionario.keys())
            for chave in chaves:
                if str(chave) not in etapas:
                    dicionario.pop(chave, None)
        if 'to_xls' in request.GET:
            rows = [
                ['#', 'Código', 'Componente', 'Etapa', 'Qtd. Alunos', 'Acima da Média', 'Abaixo da Média', 'Nota Mínima', 'Nota Média', 'Nota Máxima']
            ]
            count = 0
            for diario in diarios:
                if hasattr(diario, 'media'):
                    etapa = 1
                    for key in diario.media:
                        if etapa <= diario.componente_curricular.qtd_avaliacoes or key == 'NAF':
                            count += 1
                            row = [
                                count,
                                format_(diario.pk),
                                format_(f'{diario.componente_curricular.componente}{diario.get_descricao_dinamica()}'),
                                format_(key),
                                format_(diario.matriculadiario_set.count()),
                                format_(diario.media[key][0]),
                                format_(diario.media[key][1]),
                                format_(diario.media[key][2]['minima']),
                                format_(diario.media[key][2]['media']),
                                format_(diario.media[key][2]['maxima']),
                            ]
                            rows.append(row)
                            etapa += 1
            return XlsResponse(rows)

    return locals()
