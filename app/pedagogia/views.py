from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools import layout
from djtools.html.graficos import PieChart
from djtools.utils import XlsResponse, httprr, permission_required, rtr
from pedagogia.forms import AvaliacaoProcessualCursoForm, ResultadoAvaliacaoCursosForm
from pedagogia.models import AvaliacaoDisciplina, AvaliacaoProcessualCurso, ItemQuestionarioMatriz, QuestionarioMatriz


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()
        if QuestionarioMatriz.pode_responder(aluno):
            inscricoes.append({'url': '/pedagogia/avaliacao_processual_curso/', 'titulo': 'Responda ao questionário de Avaliação do Curso.'})

    return inscricoes


@rtr()
@permission_required('pedagogia.change_questionariomatriz')
def resultado_avaliacao_cursos(request):
    title = 'Resultado da Avaliação'
    form = ResultadoAvaliacaoCursosForm(request.POST or None)

    if 'exportar_tabela_resumo' in request.GET:
        lista_nucleos = request.session.get('lista_nucleos')

        if lista_nucleos:
            rows = [
                [
                    'Disciplina',
                    'Ótimo',
                    'Bom',
                    'Regular',
                    'Insuficiente',
                    'Desconheço',
                    'Ótimo',
                    'Bom',
                    'Regular',
                    'Insuficiente',
                    'Desconheço',
                    'Ótimo',
                    'Bom',
                    'Regular',
                    'Insuficiente',
                    'Desconheço',
                ]
            ]

            for nucleo in lista_nucleos:
                for i in nucleo['lista_disciplinas']:
                    row = [
                        i['disciplina'],
                        i['avaliacao_carga_horaria']['otimo'][0],
                        i['avaliacao_carga_horaria']['bom'][0],
                        i['avaliacao_carga_horaria']['regular'][0],
                        i['avaliacao_carga_horaria']['insuficiente'][0],
                        i['avaliacao_carga_horaria']['desconheco'][0],
                        i['avaliacao_sequencia_didatica']['otimo'][0],
                        i['avaliacao_sequencia_didatica']['bom'][0],
                        i['avaliacao_sequencia_didatica']['regular'][0],
                        i['avaliacao_sequencia_didatica']['insuficiente'][0],
                        i['avaliacao_sequencia_didatica']['desconheco'][0],
                        i['avaliacao_ementa_disciplina']['otimo'][0],
                        i['avaliacao_ementa_disciplina']['bom'][0],
                        i['avaliacao_ementa_disciplina']['regular'][0],
                        i['avaliacao_ementa_disciplina']['insuficiente'][0],
                        i['avaliacao_ementa_disciplina']['desconheco'][0],
                    ]
                    rows.append(row)

            return XlsResponse(rows)
        else:
            return httprr('..', 'Não foi possível criar a planilha. Por favor, tente novamente.', 'error')

    if 'exportar_respostas_insuficientes' in request.GET:
        lista_nucleos = request.session.get('lista_nucleos')

        if lista_nucleos:
            tipos = ['avaliacao_carga_horaria', 'avaliacao_sequencia_didatica', 'avaliacao_ementa_disciplina']
            rows = [['Núcleo', 'Disciplina', 'Tipo de Avaliação', 'Justificativa']]

            for nucleo in lista_nucleos:
                for i in nucleo['lista_disciplinas']:
                    for tipo in tipos:
                        justificativas = i[tipo]['justificativas_insuficientes']
                        for justificativa in justificativas:
                            row = [nucleo['nucleo'], i['disciplina'], tipo, justificativa]
                            rows.append(row)

            return XlsResponse(rows)
        else:
            return httprr('..', 'Não foi possível criar a planilha. Por favor, tente novamente.', 'error')

    if form.is_valid():
        uo = form.cleaned_data['uo']
        questionarios = form.cleaned_data['curso']
        if not questionarios:
            questionarios = QuestionarioMatriz.objects.filter(cursos__modalidade=form.cleaned_data['modalidade']).distinct()
        total_alunos_aptos = QuestionarioMatriz.get_total_alunos_aptos(questionarios, uo)
        total_questionarios_respondidos = QuestionarioMatriz.get_total_questionarios_repondidos(questionarios, uo)
        percentual_respondido = 0
        if total_alunos_aptos:
            percentual_respondido = int((float(total_questionarios_respondidos) / float(total_alunos_aptos)) * 100)

        disciplinas = []
        if questionarios.count() == 1:
            for questionario in questionarios:
                for item in questionario.itemquestionariomatriz_set.all().order_by('periodo'):
                    avch = item.get_grafico('avaliacao_carga_horaria', uo)
                    avsd = item.get_grafico('avaliacao_sequencia_didatica', uo)
                    aved = item.get_grafico('avaliacao_ementa_disciplina', uo)
                    disciplinas.append((item.disciplina, avch, avsd, aved))

        else:
            # TODO: LISTAR TODAS AS DISCIPLINAS DOS NUCLEOS ARTICULARDOR E ESTRUTURANTE DAS MATRIZES RELACIONADAS AOS QUESTIONARIOS SELECINADOS
            avaliacao_regime_credito = {}
            avaliacao_processual_curso = AvaliacaoProcessualCurso.objects.filter(questionario_matriz__in=questionarios).distinct()
            total = avaliacao_processual_curso.count()
            parcial = avaliacao_processual_curso.filter(avaliacao_regime_credito='Ótimo').count()
            avaliacao_regime_credito['otimo'] = (parcial, float(parcial) / float(total) * 100)
            parcial = avaliacao_processual_curso.filter(avaliacao_regime_credito='Bom').count()
            avaliacao_regime_credito['bom'] = (parcial, float(parcial) / float(total) * 100)
            parcial = avaliacao_processual_curso.filter(avaliacao_regime_credito='Regular').count()
            avaliacao_regime_credito['regular'] = (parcial, float(parcial) / float(total) * 100)
            parcial = avaliacao_processual_curso.filter(avaliacao_regime_credito='Insuficiente').count()
            avaliacao_regime_credito['insuficiente'] = (parcial, float(parcial) / float(total) * 100)
            parcial = avaliacao_processual_curso.filter(avaliacao_regime_credito='Desconheço').count()
            avaliacao_regime_credito['desconheco'] = (parcial, float(parcial) / float(total) * 100)

            lista_nucleos = (
                ItemQuestionarioMatriz.objects.filter(questionario_matriz__in=questionarios)
                .values_list('nucleo', flat=True)
                .distinct()
                .order_by('nucleo')
            )
            lista_nucleos = [{'nucleo': elem, 'lista_disciplinas': [], 'lista_disciplinas_grafico': []} for elem in lista_nucleos]
            for elem in lista_nucleos:
                lista_nucleo = (
                    ItemQuestionarioMatriz.objects.filter(questionario_matriz__in=questionarios)
                    .filter(nucleo__in=[elem['nucleo']])
                    .order_by('nucleo')
                    .order_by('disciplina')
                    .values_list('disciplina', flat=True)
                    .distinct()
                )
                for disciplina in lista_nucleo:
                    avaliacoes = AvaliacaoDisciplina.objects.filter(
                        item_questionario_matriz__questionario_matriz__in=questionarios, item_questionario_matriz__disciplina=disciplina
                    )
                    item = {}
                    item['disciplina'] = disciplina
                    item['avaliacao_carga_horaria'] = {}
                    item['avaliacao_sequencia_didatica'] = {}
                    item['avaliacao_ementa_disciplina'] = {}
                    item['avaliacao_regime_credito'] = {}
                    total = avaliacoes.count()

                    if total:
                        parcial = avaliacoes.filter(avaliacao_carga_horaria='Ótimo').count()
                        item['avaliacao_carga_horaria']['otimo'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_carga_horaria='Bom').count()
                        item['avaliacao_carga_horaria']['bom'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_carga_horaria='Regular').count()
                        item['avaliacao_carga_horaria']['regular'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_carga_horaria='Insuficiente').count()
                        item['avaliacao_carga_horaria']['insuficiente'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_carga_horaria='Desconheço').count()
                        item['avaliacao_carga_horaria']['desconheco'] = (parcial, float(parcial) / float(total) * 100)
                        item['avaliacao_carga_horaria']['justificativas_insuficientes'] = avaliacoes.filter(
                            avaliacao_carga_horaria='Insuficiente', avaliacao_carga_horaria_justificativa__isnull=False
                        ).values_list('avaliacao_carga_horaria_justificativa', flat=True)

                        grafico1 = PieChart(
                            'avaliacao_carga_horaria' + disciplina,
                            title=AvaliacaoDisciplina._meta.get_field('avaliacao_carga_horaria').verbose_name,
                            subtitle=AvaliacaoDisciplina._meta.get_field('avaliacao_carga_horaria').help_text,
                            minPointLength=0,
                            data=[
                                ['Ótimo', item['avaliacao_carga_horaria']['otimo'][0]],
                                ['Bom', item['avaliacao_carga_horaria']['bom'][0]],
                                ['Regular', item['avaliacao_carga_horaria']['regular'][0]],
                                ['Insuficiente', item['avaliacao_carga_horaria']['insuficiente'][0]],
                                ['Desconheço', item['avaliacao_carga_horaria']['desconheco'][0]],
                            ],
                        )
                        grafico1.id = 'avaliacao_carga_horaria' + disciplina
                        grafico1.pk = ','.join(
                            [
                                str(i)
                                for i in avaliacoes.filter(avaliacao_carga_horaria='Insuficiente')
                                .values_list('item_questionario_matriz__id', flat=True)
                                .distinct()
                            ]
                        )
                        grafico1.campo = 'avaliacao_carga_horaria'
                        grafico1.insuficiente = avaliacoes.filter(avaliacao_carga_horaria='Insuficiente').count()

                        parcial = avaliacoes.filter(avaliacao_sequencia_didatica='Ótimo').count()
                        item['avaliacao_sequencia_didatica']['otimo'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_sequencia_didatica='Bom').count()
                        item['avaliacao_sequencia_didatica']['bom'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_sequencia_didatica='Regular').count()
                        item['avaliacao_sequencia_didatica']['regular'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_sequencia_didatica='Insuficiente').count()
                        item['avaliacao_sequencia_didatica']['insuficiente'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_sequencia_didatica='Desconheço').count()
                        item['avaliacao_sequencia_didatica']['desconheco'] = (parcial, float(parcial) / float(total) * 100)
                        item['avaliacao_sequencia_didatica']['justificativas_insuficientes'] = avaliacoes.filter(
                            avaliacao_sequencia_didatica='Insuficiente', avaliacao_sequencia_didatica_justificativa__isnull=False
                        ).values_list('avaliacao_sequencia_didatica_justificativa', flat=True)

                        grafico2 = PieChart(
                            'avaliacao_sequencia_didatica' + disciplina,
                            title=AvaliacaoDisciplina._meta.get_field('avaliacao_sequencia_didatica').verbose_name,
                            subtitle=AvaliacaoDisciplina._meta.get_field('avaliacao_sequencia_didatica').help_text,
                            minPointLength=0,
                            data=[
                                ['Ótimo', item['avaliacao_sequencia_didatica']['otimo'][0]],
                                ['Bom', item['avaliacao_sequencia_didatica']['bom'][0]],
                                ['Regular', item['avaliacao_sequencia_didatica']['regular'][0]],
                                ['Insuficiente', item['avaliacao_sequencia_didatica']['insuficiente'][0]],
                                ['Desconheço', item['avaliacao_sequencia_didatica']['desconheco'][0]],
                            ],
                        )
                        grafico2.id = 'avaliacao_sequencia_didatica' + disciplina
                        grafico2.pk = ','.join(
                            [
                                str(i)
                                for i in avaliacoes.filter(avaliacao_sequencia_didatica='Insuficiente')
                                .values_list('item_questionario_matriz__id', flat=True)
                                .distinct()
                            ]
                        )
                        grafico2.campo = 'avaliacao_sequencia_didatica'
                        grafico2.insuficiente = avaliacoes.filter(avaliacao_sequencia_didatica='Insuficiente').count()

                        parcial = avaliacoes.filter(avaliacao_ementa_disciplina='Ótimo').count()
                        item['avaliacao_ementa_disciplina']['otimo'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_ementa_disciplina='Bom').count()
                        item['avaliacao_ementa_disciplina']['bom'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_ementa_disciplina='Regular').count()
                        item['avaliacao_ementa_disciplina']['regular'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_ementa_disciplina='Insuficiente').count()
                        item['avaliacao_ementa_disciplina']['insuficiente'] = (parcial, float(parcial) / float(total) * 100)
                        parcial = avaliacoes.filter(avaliacao_ementa_disciplina='Desconheço').count()
                        item['avaliacao_ementa_disciplina']['desconheco'] = (parcial, float(parcial) / float(total) * 100)
                        item['avaliacao_ementa_disciplina']['justificativas_insuficientes'] = avaliacoes.filter(
                            avaliacao_ementa_disciplina='Insuficiente', avaliacao_ementa_disciplina_justificativa__isnull=False
                        ).values_list('avaliacao_ementa_disciplina_justificativa', flat=True)

                        grafico3 = PieChart(
                            'avaliacao_ementa_disciplina' + disciplina,
                            title=AvaliacaoDisciplina._meta.get_field('avaliacao_ementa_disciplina').verbose_name,
                            subtitle=AvaliacaoDisciplina._meta.get_field('avaliacao_ementa_disciplina').help_text,
                            minPointLength=0,
                            data=[
                                ['Ótimo', item['avaliacao_ementa_disciplina']['otimo'][0]],
                                ['Bom', item['avaliacao_ementa_disciplina']['bom'][0]],
                                ['Regular', item['avaliacao_ementa_disciplina']['regular'][0]],
                                ['Insuficiente', item['avaliacao_ementa_disciplina']['insuficiente'][0]],
                                ['Desconheço', item['avaliacao_ementa_disciplina']['desconheco'][0]],
                            ],
                        )
                        grafico3.id = 'avaliacao_ementa_disciplina' + disciplina
                        grafico3.pk = ','.join(
                            [
                                str(i)
                                for i in avaliacoes.filter(avaliacao_ementa_disciplina='Insuficiente')
                                .values_list('item_questionario_matriz__id', flat=True)
                                .distinct()
                            ]
                        )
                        grafico3.campo = 'avaliacao_ementa_disciplina'
                        grafico3.insuficiente = avaliacoes.filter(avaliacao_ementa_disciplina='Insuficiente').count()

                        elem['lista_disciplinas_grafico'].append((disciplina, grafico1, grafico2, grafico3))
                    else:
                        item['avaliacao_carga_horaria']['otimo'] = (0, 0)
                        item['avaliacao_carga_horaria']['bom'] = (0, 0)
                        item['avaliacao_carga_horaria']['regular'] = (0, 0)
                        item['avaliacao_carga_horaria']['insuficiente'] = (0, 0)
                        item['avaliacao_carga_horaria']['desconheco'] = (0, 0)
                        item['avaliacao_carga_horaria']['justificativas_insuficientes'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['otimo'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['bom'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['regular'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['insuficiente'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['desconheco'] = (0, 0)
                        item['avaliacao_sequencia_didatica']['justificativas_insuficientes'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['otimo'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['bom'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['regular'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['insuficiente'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['desconheco'] = (0, 0)
                        item['avaliacao_ementa_disciplina']['justificativas_insuficientes'] = (0, 0)

                    elem['lista_disciplinas'].append(item)

            # Jogando os objetos da Matriz (Resumo) na Sessão para facilitar a exportação
            if lista_nucleos:
                request.session['lista_nucleos'] = lista_nucleos

        boxes_graficos = []
        graficos = []
        for campo in ['identificacao_5_bolsa_trabalho', 'identificacao_5_alimentacao', 'identificacao_5_transporte', 'identificacao_5_outroi']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Assistência Estudantil', graficos))

        graficos = []
        for campo in [
            'identificacao_7_bolsa_de_IC_ifrn',
            'identificacao_7_bolsa_de_IC_externa',
            'identificacao_7_bolsa_de_extensao_ifrn',
            'identificacao_7_bolsa_de_extensao_externa',
            'identificacao_7_pibid',
            'identificacao_7_pibic',
            'identificacao_7_pibit',
        ]:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Bolsas', graficos))

        graficos = []
        for campo in ['identificacao_8', 'identificacao_9']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Trabalho/Estágio', graficos))

        graficos = []
        for campo in [
            'parte_2_II_a_1',
            'parte_2_II_a_2',
            'parte_2_II_a_3',
            'parte_2_II_a_4',
            'parte_2_II_a_5',
            'parte_2_II_a_6',
            'parte_2_II_a_7',
            'parte_2_II_a_8',
        ]:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)

        boxes_graficos.append(('Parte II - Item a)', graficos))

        graficos = []
        for campo in [
            'parte_2_II_b_1',
            'parte_2_II_b_2',
            'parte_2_II_b_3',
            'parte_2_II_b_4',
            'parte_2_II_b_5',
            'parte_2_II_b_6',
            'parte_2_II_b_7',
            'parte_2_II_b_8i',
        ]:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item b)', graficos))

        graficos = []
        for campo in ['parte_2_II_c_1', 'parte_2_II_c_2', 'parte_2_II_c_3', 'parte_2_II_c_4', 'parte_2_II_c_5', 'parte_2_II_c_6']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item c)', graficos))

        graficos = []
        for campo in ['parte_2_II_d_1', 'parte_2_II_d_2', 'parte_2_II_d_3', 'parte_2_II_d_4']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item d)', graficos))

        graficos = []
        for campo in ['parte_2_II_e_1', 'parte_2_II_e_2', 'parte_2_II_e_3']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item e)', graficos))

        graficos = []
        for campo in ['parte_2_II_f_1', 'parte_2_II_f_2', 'parte_2_II_f_3', 'parte_2_II_f_4', 'parte_2_II_f_5', 'parte_2_II_f_6', 'parte_2_II_f_7']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item f)', graficos))

        graficos = []
        for campo in ['parte_2_II_g_1', 'parte_2_II_g_2', 'parte_2_II_g_3', 'parte_2_II_g_4']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item g)', graficos))

        graficos = []
        for campo in ['parte_2_II_h_1', 'parte_2_II_h_2', 'parte_2_II_h_3', 'parte_2_II_h_4', 'parte_2_II_h_5', 'parte_2_II_h_6']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item h)', graficos))

        graficos = []
        for campo in ['parte_2_II_i_1', 'parte_2_II_i_2', 'parte_2_II_i_3', 'parte_2_II_i_4', 'parte_2_II_i_5', 'parte_2_II_i_6', 'parte_2_II_i_7']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item i)', graficos))

        graficos = []
        for campo in ['parte_2_II_j_1', 'parte_2_II_j_2', 'parte_2_II_j_3', 'parte_2_II_j_4', 'parte_2_II_j_5', 'parte_2_II_j_6']:
            grafico = QuestionarioMatriz.get_grafico(questionarios, campo, uo)
            graficos.append(grafico)
        boxes_graficos.append(('Parte II - Item j)', graficos))
    return locals()


@rtr()
@permission_required('pedagogia.change_questionariomatriz')
def ver_respostas_insuficiente(request, pk, campo):
    objs = AvaliacaoDisciplina.objects.filter(item_questionario_matriz__pk__in=pk.split(','))
    d = {campo: 'Insuficiente'}
    justificativas = objs.filter(**d)
    return locals()


@rtr()
@permission_required('pedagogia.view_questionariomatriz')
def questionariomatriz(request, pk):
    obj = get_object_or_404(QuestionarioMatriz, pk=pk)
    title = f'Questionário de Matriz - {obj}'
    if 'replicar' in request.GET:
        obj.replicar()
        return httprr('/admin/pedagogia/questionariomatriz/', 'Questionário replicado com sucesso.')
    return locals()


@rtr()
@login_required()
def avaliacao_processual_curso(request):
    title = 'Avaliação Processual dos Cursos'
    aluno = request.user.get_relacionamento()

    if aluno.curso_campus.modalidade.pk == 2 or aluno.curso_campus.modalidade.pk == 3:
        regime = 'Regime de Crédito'
    else:
        regime = 'Regime Misto (Disciplinas semestrais e anuais)'

    qs = QuestionarioMatriz.objects.filter(cursos=aluno.curso_campus)
    if not qs.exists():
        return httprr('/', 'Não há questionário de matriz para esse curso.', 'error')
    questionario_matriz = qs[0]

    qs_avaliacao_processual = AvaliacaoProcessualCurso.objects.filter(aluno=aluno)
    instance = None
    if qs_avaliacao_processual:
        instance = qs_avaliacao_processual[0]

    form = AvaliacaoProcessualCursoForm(request.POST or None, instance=instance)

    if form.is_valid():
        form.processar()

        if request.GET.get('passo') == '1':
            return httprr('/pedagogia/avaliacao_processual_curso/', 'Questionário salvo com sucesso.')
        passo = 1
    else:
        if request.GET.get('passo') == '1':
            passo = 1
        else:
            passo = 2

    return locals()
