import math
from datetime import date, datetime

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.db.models.expressions import Case, Value, When
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404

from avaliacao_cursos import tasks
from avaliacao_cursos.forms import (
    AdicionarQuestionarioForm,
    GrupoPerguntaForm,
    OpcaoRespostaPerguntaForm,
    OpcoesRespostaPerguntaForm,
    PerguntaForm,
    RelatorioForm,
    RespondentesForm,
    ResultadoForm,
)
from avaliacao_cursos.models import (
    Avaliacao,
    AvaliacaoComponenteCurricular,
    GrupoPergunta,
    JustificativaAvaliacaoComponenteCurricular,
    OpcaoRespostaPergunta,
    Pergunta,
    Questionario,
    Respondente,
    Resposta,
    Segmento,
)
from comum.models import Configuracao
from djtools import forms, layout
from djtools.crosstab.bidimensional import TabelaBidimensional
from djtools.html.graficos import BarChart, PieChart, StackedGroupedColumnChart
from djtools.utils import group_required, httprr, permission_required, rtr
from edu.models import ProfessorDiario
from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Modalidade, Nucleo
from edu.models.cursos import Componente, ComponenteCurricular, CursoCampus, Matriz
from edu.models.diretorias import Diretoria
from edu.utils import TabelaResumoAluno
from rh.models import Setor, UnidadeOrganizacional


@layout.inscricao()
def index_inscricoes(request):
    """Lista questionários de avaliação de cursos pendentes para o usuário logado.

    Considera apenas respondentes do vínculo atual cujos questionários estão
    no período de resposta e ainda não foram finalizados.

    Args:
        request: requisição HTTP usada para obter o vínculo do usuário.

    Returns:
        list[dict]: itens com ``url``, ``titulo`` e ``prazo`` para cada questionário pendente.
    """
    inscricoes = []
    qs = (
        Respondente.objects.filter(
            vinculo=request.user.get_vinculo(),
            questionario__data_inicio__lte=datetime.today(),
            questionario__data_termino__gte=datetime.today(),
            finalizado=False,
        )
        .select_related('questionario')
        .annotate(
            tem_resposta=Case(
                When(resposta__isnull=False, then=Value(True)),
                default=Value(False),
            ),
            tem_avaliacao_componente_curricular=Case(
                When(avaliacaocomponentecurricular__isnull=False, then=Value(True)),
                default=Value(False),
            ),
        )
    )
    for questionario in qs.order_by('id').distinct():
        titulo_prefix = (
            'Continue respondendo o' if questionario.tem_resposta or questionario.tem_avaliacao_componente_curricular else 'Você precisa responder o'
        )
        titulo = f'{titulo_prefix} <strong>Questionário de Avaliação de Cursos - {questionario.segmento}</strong>.'.format(
            titulo_prefix, questionario.segmento
        )
        inscricoes.append(
            {
                'url': f'/avaliacao_cursos/responder/{questionario.pk}/',
                'titulo': titulo,
                'prazo': questionario.questionario.data_termino,
            }
        )
    return inscricoes


@rtr()
@login_required
def resultado(request):
    title = 'Resultado'
    form = ResultadoForm(request.GET or None)
    if form.is_valid():
        respondentes = form.processar()
        qtd_respondentes = respondentes.count()
        qtd_finalizadas = respondentes.filter(finalizado=True).count()

    return locals()


@rtr()
@login_required
def avaliacao(request, pk):
    url = f'/avaliacao_cursos/questionario/{pk}/'
    obj = get_object_or_404(Avaliacao, pk=pk)
    title = str(obj)
    if request.GET.get('tab') == 'monitoramento':
        uos = UnidadeOrganizacional.objects.suap().all()
        segmentos = Segmento.objects.all()
        modalidades = Modalidade.objects.filter(pk__in=obj.questionario_set.values_list('modalidades', flat=True).distinct())
        estatisticas = {}
        estatisticas_discente = {}
        for uo in uos:
            estatistica = []
            estatistica_discente = []
            for segmento in segmentos:
                estatistica.append(obj.get_qtd_respondentes(uo, segmento))
                estatistica.append(obj.get_qtd_iniciado(uo, segmento))
                estatistica.append(obj.get_qtd_finalizados(uo, segmento))
            for modalidade in modalidades:
                estatistica_discente.append(obj.get_qtd_respondentes_discente(uo, modalidade))
                estatistica_discente.append(obj.get_qtd_iniciado_discente(uo, modalidade))
                estatistica_discente.append(obj.get_qtd_finalizados_discente(uo, modalidade))
            estatisticas[uo.sigla] = estatistica
            estatisticas_discente[uo.sigla] = estatistica_discente
    return locals()


@rtr()
@group_required('Avaliador de Cursos')
def adicionar_questionario(request, pk, questionario_pk=None):
    title = 'Adicionar Questionário'
    url = f'/avaliacao_cursos/questionario/{pk}/'
    obj = get_object_or_404(Avaliacao, pk=pk)
    questionario = questionario_pk and Questionario.objects.get(pk=questionario_pk) or Questionario()
    questionario.avaliacao = obj
    form = AdicionarQuestionarioForm(data=request.POST or None, instance=questionario)
    if form.is_valid():
        questionario = form.save(True)
        return httprr('..', 'Questionário salvo com sucesso.')

    return locals()


@rtr()
@login_required
def questionario(request, pk):
    title = 'Visualizar Questionário'
    url = f'/avaliacao_cursos/questionario/{pk}/'
    obj = get_object_or_404(Questionario, pk=pk)

    qtd_respondentes = obj.respondente_set.count()
    qtd_finalizados = obj.respondente_set.filter(finalizado=True).count()
    qtd_iniciado = Resposta.objects.filter(respondente__questionario=obj).values_list('respondente').order_by('respondente').distinct().count()

    if 'identificar_respondentes' in request.GET:
        obj.identificar_respondentes(excluir=False)
        return httprr(url, 'Respondentes identificados com sucesso.')

    if 'reprocessar_respondentes' in request.GET:
        obj.identificar_respondentes(excluir=True)
        return httprr(url, 'Respondentes reprocessados com sucesso.')

    if 'grupo_pergunta_id' in request.GET:
        pk_grupo_pergunta = request.GET.get('grupo_pergunta_id')
        grupo_pergunta = get_object_or_404(GrupoPergunta, pk=pk_grupo_pergunta)
        grupo_pergunta.delete()
        return httprr(url, 'Grupo excluído com sucesso.')

    if 'pergunta_id' in request.GET:
        pk_pergunta = request.GET.get('pergunta_id')
        pergunta = get_object_or_404(Pergunta, pk=pk_pergunta)
        pergunta.delete()
        return httprr(url, 'Pergunta excluída com sucesso.')

    if not obj.respondente_set.filter(segmento=Segmento.ALUNO).exists():
        tabela_resumo = TabelaBidimensional(
            'Quadro Resumo - Segmentos',
            qs=obj.respondente_set.all(),
            vertical_key='setor__uo',
            vertical_source=UnidadeOrganizacional,
            horizontal_key='segmento',
            horizontal_source=Segmento,
            vertical_header_name='Unidade Organizacional',
            vertical_include_null_value=True,
        )

    else:
        qs_alunos = Aluno.objects.filter(vinculos__in=obj.respondente_set.values_list('vinculo', flat=True))
        tabela_resumo = TabelaResumoAluno(qs_alunos)
    return locals()


@rtr()
@group_required('Avaliador de Cursos')
def adicionar_grupo_pergunta(request, questionario_pk, grupo_pergunta_pk=None):
    title = 'Adicionar Grupo de Pergunta'
    questionario = get_object_or_404(Questionario, pk=questionario_pk)

    instance = grupo_pergunta_pk and GrupoPergunta.objects.get(pk=grupo_pergunta_pk) or None
    form = GrupoPerguntaForm(data=request.POST or None, instance=instance)

    if form.is_valid():
        form.instance.questionario = questionario
        form.save()
        return httprr('..', 'Grupo adicionado com sucesso')
    return locals()


@rtr()
@group_required('Avaliador de Cursos')
def adicionar_pergunta(request, grupo_pergunta_pk, pergunta_pk=None):
    title = 'Adicionar Pergunta'
    grupo_pergunta = get_object_or_404(GrupoPergunta, pk=grupo_pergunta_pk)

    instance = pergunta_pk and Pergunta.objects.get(pk=pergunta_pk) or None
    form = PerguntaForm(data=request.POST or None, instance=instance)

    if form.is_valid():
        form.instance.grupo_pergunta = grupo_pergunta
        form.save()
        return httprr('..', 'Pergunta adicionada com sucesso')
    return locals()


@rtr()
@group_required('Avaliador de Cursos')
def adicionar_opcao_resposta(request, pergunta_pk, opcao_resposta_pk=None):
    title = 'Adicionar Opção de Resposta'
    pergunta = get_object_or_404(Pergunta, pk=pergunta_pk)

    instance = opcao_resposta_pk and OpcaoRespostaPergunta.objects.get(pk=opcao_resposta_pk) or None
    if opcao_resposta_pk:
        form = OpcaoRespostaPerguntaForm(data=request.POST or None, instance=instance)
        if form.is_valid():
            form.instance.pergunta = pergunta
            form.save()
            return httprr('..', 'Opção de Resposta adicionada com sucesso')
    else:
        form = OpcoesRespostaPerguntaForm(data=request.POST or None)
        if form.is_valid():
            form.save(pergunta)
            return httprr('..', 'Opção de Resposta adicionada com sucesso')
    return locals()


@rtr()
@login_required
def visualizar_respondentes(request, pk):
    title = 'Visualizar Respondentes'
    obj = get_object_or_404(Questionario, pk=pk)
    form = RespondentesForm(data=request.POST or None, questionario=obj)
    respondentes = obj.respondente_set.all().order_by('vinculo__pessoa__nome')

    if form.is_valid():
        respondentes = form.processar()

    return locals()


@rtr()
@permission_required('avaliacao_cursos.delete_questionario')
def reabrir(request, pk):
    obj = get_object_or_404(Respondente, pk=pk)
    obj.reabrir()
    return httprr('..', 'Questionário reaberto com sucesso.')


@rtr()
@login_required
def responder(request, pk):
    obj = get_object_or_404(Respondente, pk=pk)
    title = f'Responder Questionário de Avaliação de Cursos - {obj.segmento}'
    eh_previsualizacao = request.user.has_perm('avaliacao_cursos.change_avaliacao') and request.user.get_vinculo() != obj.vinculo
    if (date.today() > obj.questionario.data_termino) and not eh_previsualizacao:
        return httprr('/', 'O prazo para resposta da Avaliação foi expirado.', 'error')

    if not eh_previsualizacao:
        if request.user.get_vinculo() != obj.vinculo:
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if request.user.get_vinculo() == obj.vinculo and obj.finalizado:
        return httprr('/', 'A avaliação já foi respondida.', 'error')

    qtd_perguntas = 0
    qtd_respondida = 0
    modalidades = []
    for i, modalidade in enumerate(obj.questionario.modalidades.all()):
        if i > 0:
            if i == obj.questionario.modalidades.count() - 1:
                modalidades.append(f' e {modalidade.descricao}')
            else:
                modalidades.append(f', {modalidade.descricao}')
        else:
            modalidades.append(modalidade.descricao)
    modalidades_str = ''.join(modalidades)

    form = forms.Form(data=request.POST or None)
    ids_perguntas_obrigatorias = Pergunta.objects.filter(grupo_pergunta__questionario=obj.questionario, obrigatoria=True).values_list('pk', flat=True)
    ids_componentes_ministrados = ProfessorDiario.objects.filter(professor__vinculo__id=obj.vinculo.id).values_list(
        'diario__componente_curricular', flat=True
    )
    avaliacoes = AvaliacaoComponenteCurricular.objects.filter(respondente=obj).values_list(
        'carga_horaria', 'componente_curricular', 'sequencia_didatica', 'ementa_programa', 'regime_misto', 'justificativa'
    )
    respostas = {}
    for carga_horaria, componente_curricular_pk, sequencia_didatica, ementa_programa, regime_misto, justificativa in avaliacoes:
        respostas[componente_curricular_pk] = {
            'carga_horaria': carga_horaria,
            'sequencia_didatica': sequencia_didatica,
            'ementa_programa': ementa_programa,
            'regime_misto': regime_misto,
            'justificativa': justificativa,
        }
    matrizes = []
    justificativas = {
        (x, y): z for x, y, z in obj.justificativaavaliacaocomponentecurricular_set.values_list('componente_curricular', 'campo', 'justificativa')
    }
    for matriz in obj.get_matrizes():
        anual = matriz.matrizcurso_set.filter(curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL).exists()
        periodos = [1, 2, 3, 4]
        qs = matriz.componentecurricular_set.filter(periodo_letivo__in=periodos)
        colspan = matriz.qtd_periodos_letivos + 6
        nucleos = []
        attrs = ('carga_horaria', 'sequencia_didatica', 'ementa_programa')
        for nucleo in Nucleo.objects.filter(pk__in=qs.values_list('nucleo', flat=True).distinct()):
            componentes_curriculares = []
            for componente_curricular in (
                qs.filter(nucleo=nucleo)
                .exclude(tipo__in=(ComponenteCurricular.TIPO_SEMINARIO, ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL))
                .order_by('componente__descricao')
                .distinct()
            ):
                componente_curricular.justificativa_1 = justificativas.get((componente_curricular.pk, 1))
                componente_curricular.justificativa_2 = justificativas.get((componente_curricular.pk, 2))
                componente_curricular.justificativa_3 = justificativas.get((componente_curricular.pk, 3))
                for attr in attrs:
                    if not eh_previsualizacao:
                        initial = componente_curricular.pk in respostas and respostas[componente_curricular.pk][attr] or None
                    else:
                        initial = None
                    field_name = f'{componente_curricular.pk}:::{attr}'
                    if attr == 'justificativa':
                        form.fields[field_name] = forms.CharField(required=False, initial=initial)
                    else:
                        form.fields[field_name] = forms.ChoiceField(choices=Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES, required=False, initial=initial)

                    if obj.segmento_id == Segmento.PROFESSOR:
                        if componente_curricular.pk in ids_componentes_ministrados:
                            form.fields[field_name].widget.attrs['data-required'] = 1
                        else:
                            form.fields[field_name].widget.attrs['readonly'] = True
                            form.fields[field_name].widget.attrs['disabled'] = 'disabled'
                    else:
                        form.fields[field_name].widget.attrs['data-required'] = 1

                    setattr(componente_curricular, attr, field_name)
                componentes_curriculares.append(componente_curricular)
            nucleos.append((f'Núcleo {nucleo}', componentes_curriculares))

        componentes_curriculares = []
        for componente_curricular in qs.filter(tipo=ComponenteCurricular.TIPO_SEMINARIO).order_by('componente__descricao').distinct():
            for attr in attrs:
                if not eh_previsualizacao:
                    initial = componente_curricular.pk in respostas and respostas[componente_curricular.pk][attr] or None
                else:
                    initial = None
                field_name = f'{componente_curricular.pk}:::{attr}'
                if attr == 'justificativa':
                    form.fields[field_name] = forms.CharField(required=False, initial=initial)
                else:
                    form.fields[field_name] = forms.ChoiceField(choices=Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES, required=False, initial=initial)
                if obj.segmento_id == Segmento.PROFESSOR:
                    if componente_curricular.pk in ids_componentes_ministrados:
                        form.fields[field_name].widget.attrs['data-required'] = 1
                    else:
                        form.fields[field_name].widget.attrs['readonly'] = True
                        form.fields[field_name].widget.attrs['disabled'] = 'disabled'
                else:
                    form.fields[field_name].widget.attrs['data-required'] = 1

                setattr(componente_curricular, attr, field_name)
            componentes_curriculares.append(componente_curricular)
        nucleos.append(('Seminários', componentes_curriculares))

        componentes_curriculares = []
        for componente_curricular in qs.filter(tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL).order_by('componente__descricao').distinct():
            for attr in attrs:
                initial = componente_curricular.pk in respostas and respostas[componente_curricular.pk][attr] or None
                field_name = f'{componente_curricular.pk}:::{attr}'
                form.fields[field_name] = forms.ChoiceField(choices=Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES, required=False, initial=initial)
                setattr(componente_curricular, attr, field_name)
                if obj.segmento_id == Segmento.PROFESSOR:
                    if componente_curricular.pk in ids_componentes_ministrados:
                        form.fields[field_name].widget.attrs['data-required'] = 1
                    else:
                        form.fields[field_name].widget.attrs['readonly'] = True
                        form.fields[field_name].widget.attrs['disabled'] = 'disabled'
                else:
                    form.fields[field_name].widget.attrs['data-required'] = 1

            componentes_curriculares.append(componente_curricular)
        nucleos.append(('Prática Profissional', componentes_curriculares))

        matrizes.append((matriz.descricao, nucleos, anual))

    grupos_pergunta = []
    respostas_grupo_pergunta = {}
    for pergunta_pk, resposta, multipla_escolha in (
        Resposta.objects.filter(respondente=obj).values_list('pergunta__id', 'resposta', 'pergunta__multipla_escolha').distinct()
    ):
        if pergunta_pk in respostas_grupo_pergunta:
            if not isinstance(respostas_grupo_pergunta[pergunta_pk], list):
                respostas_grupo_pergunta[pergunta_pk] = [respostas_grupo_pergunta[pergunta_pk], resposta]
            else:
                respostas_grupo_pergunta[pergunta_pk].append(resposta)
        else:
            if multipla_escolha:
                respostas_grupo_pergunta[pergunta_pk] = [resposta]
            else:
                respostas_grupo_pergunta[pergunta_pk] = resposta
    for grupo_pergunta in obj.questionario.grupopergunta_set.all():
        grupo_pergunta.perguntas = []
        for pergunta in grupo_pergunta.pergunta_set.all():
            initial = respostas_grupo_pergunta.get(pergunta.pk)
            pergunta.form_field_name = str(pergunta.pk)
            field = pergunta.get_form_field(initial=initial)
            form.fields[pergunta.form_field_name] = field
            if pergunta.obrigatoria:
                field.widget.attrs['data-required'] = 1
            grupo_pergunta.perguntas.append(pergunta)
        grupos_pergunta.append(grupo_pergunta)

    for field_name in form.fields:
        field = form.fields[field_name]
        if 'readonly' not in field.widget.attrs or not field.widget.attrs['readonly']:
            if field.widget.attrs.get('data-required'):
                qtd_perguntas += 1
                if field.initial:
                    qtd_respondida += 1

    percentual = math.ceil(qtd_perguntas and (100.0 * qtd_respondida / qtd_perguntas) or 0)

    # Validando as perguntas obrigatórias ao salvar e finalizar
    if '_save_and_finalize' in request.POST:
        if percentual < 100:
            form.add_error(None, 'A avaliação só pode ser concluída quando 100% das perguntas obrigatórias forem respondidas.')

    if form.is_valid():
        finalizar = '_save_and_finalize' in request.POST

        novas_respostas = {}
        for field_name in form.cleaned_data:
            valor = form.cleaned_data.get(field_name)

            if ':::' in field_name:
                componente_curricular.pk, attr = field_name.split(':::')
                if componente_curricular.pk not in novas_respostas:
                    novas_respostas[componente_curricular.pk] = {'carga_horaria': None, 'sequencia_didatica': None, 'ementa_programa': None}
                novas_respostas[componente_curricular.pk][attr] = valor
            else:
                if type(valor) not in (list, tuple):
                    qs = Resposta.objects.filter(respondente=obj, pergunta=field_name)
                    if qs.exists():
                        qs.update(resposta=valor)
                    elif valor:
                        Resposta.objects.create(respondente=obj, pergunta_id=field_name, resposta=valor)
                else:
                    Resposta.objects.filter(respondente=obj, pergunta=field_name).delete()
                    for valor_opcao in valor:
                        Resposta.objects.create(respondente=obj, pergunta_id=field_name, resposta=valor_opcao)

        for componente_curricular_pk, resposta_data in novas_respostas.items():
            qs = AvaliacaoComponenteCurricular.objects.filter(respondente=obj, componente_curricular=componente_curricular_pk)
            if qs.exists():
                qs.update(**resposta_data)
            else:
                if resposta_data['sequencia_didatica'] or resposta_data['ementa_programa']:
                    resposta_data.update(respondente=obj, componente_curricular_id=componente_curricular_pk)
                    AvaliacaoComponenteCurricular.objects.create(**resposta_data)

        if finalizar:
            # Finalizando a avaliação
            obj.finalizado = finalizar
            obj.save()
            return httprr('/', 'Avaliação finalizada com sucesso.')
        else:
            return httprr('.', 'Avaliação parcialmente salva com sucesso.')
    return locals()


@rtr()
@login_required
def estatistica_avaliacao(request, pk):
    avaliacao = Avaliacao.objects.get(pk=pk)
    title = f'Relatório - {avaliacao}'
    form = RelatorioForm(avaliacao, data=request.POST or None)
    if form.is_valid():
        uos = form.cleaned_data.get('uos')
        segmento = form.cleaned_data.get('segmento')
        matriz = form.cleaned_data.get('matriz')
        modalidades = form.cleaned_data.get('modalidades')
        qs = Questionario.objects.filter(avaliacao=avaliacao, segmentos=segmento)
        if qs.exists():
            obj = qs[0]
            lista = ['?_=']
            lista.append(f'segmento={segmento.pk}')
            lista.append('uos={}'.format('-'.join([str(uo.pk) for uo in uos])))
            lista.append('modalidades={}'.format('-'.join([str(modalidade.pk) for modalidade in modalidades])))
            lista.append('matriz={}'.format(matriz and matriz.pk or ''))
            params = '&'.join(lista)

    return locals()


@rtr()
@login_required
def estatistica_avaliacao_componentes(request, pk):
    avaliacao = Avaliacao.objects.get(pk=pk)
    title = f'Relatório - {avaliacao}'
    form = RelatorioForm(avaliacao, data=request.POST or None)
    form.fields['segmento'].queryset = Segmento.objects.filter(pk__in=(Segmento.ALUNO, Segmento.PROFESSOR))
    if form.is_valid():
        uos = form.cleaned_data.get('uos')
        segmento = form.cleaned_data.get('segmento')
        matriz = form.cleaned_data.get('matriz')
        modalidades = form.cleaned_data.get('modalidades')
        qs = AvaliacaoComponenteCurricular.objects.filter(respondente__questionario__avaliacao=avaliacao)
        if modalidades:
            qs = qs.filter(componente_curricular__matriz__matrizcurso__curso_campus__modalidade__in=modalidades)
        if matriz:
            qs = qs.filter(componente_curricular__matriz=matriz)
        if uos:
            qs = qs.filter(componente_curricular__matriz__matrizcurso__curso_campus__diretoria__setor__uo__in=uos)
        if segmento:
            qs = qs.filter(respondente__segmento=segmento)
        componentes = Componente.objects.filter(
            pk__in=qs.order_by('componente_curricular__componente').values_list('componente_curricular__componente', flat=True).distinct()
        )
    return locals()


@rtr()
@login_required
def xls_avaliacao(request, pk, pk_grupo=None):
    respostas = Resposta.objects.filter(pergunta__grupo_pergunta__questionario__avaliacao_id=pk)

    if pk_grupo:
        respostas = respostas.filter(pergunta__grupo_pergunta=pk_grupo)

    if '_' in request.GET:
        segmento_id = int(request.GET.get('segmento'))
        respostas = respostas.filter(respondente__segmento=segmento_id)

        uos = request.GET.get('uos', False)
        uo_ids = uos and uos.split('-') or []
        if uo_ids:
            respostas = respostas.filter(respondente__setor__uo__in=uo_ids)

        matriz = request.GET.get('matriz', False)
        matriz_id = matriz and int(matriz) or False

        modalidades = request.GET.get('modalidades', False)
        modalidade_ids = modalidades and [int(x) for x in modalidades.split('-')] or []

        if segmento_id == Segmento.ALUNO:
            if modalidade_ids:
                ids_alunos = Aluno.objects.filter(curso_campus__modalidade__in=modalidade_ids).values_list('id', flat=True)
                respostas = respostas.filter(
                    respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                )
            if matriz_id:
                ids_alunos = Aluno.objects.filter(curso_campus__matrizcurso__matriz=matriz_id).values_list('id', flat=True)
                respostas = respostas.filter(
                    respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                )
        else:
            if modalidade_ids:
                respondente_pks = (
                    respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__modalidade__in=modalidade_ids)
                    .order_by('respondente')
                    .values_list('respondente')
                    .distinct()
                )
                respostas = respostas.filter(respondente__in=respondente_pks)
            if matriz_id:
                respondente_pks = (
                    respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__matrizcurso__matriz=matriz_id)
                    .order_by('respondente')
                    .values_list('respondente')
                    .distinct()
                )
                respostas = respostas.filter(respondente__in=respondente_pks)

    else:
        setor_id = request.GET.get('setor', False)
        if setor_id:
            respostas = respostas.filter(respondente__setor=setor_id)
        segmento_id = request.GET.get('segmento', False)
        if segmento_id:
            respostas = respostas.filter(respondente__segmento=segmento_id)

    return tasks.xls_avaliacao(respostas, segmento_id, matriz_id)


@rtr()
@login_required
def estatistica_resposta(request, pk):
    title = 'Estatísticas de Respostas'
    pergunta = Pergunta.objects.get(pk=pk)
    respostas = pergunta.resposta_set.all()
    mostrar_filtros = True

    series = []

    subtitle = []
    uo_ids = None
    modalidade_ids = None
    matriz_id = None
    setor_id = None

    if '_' in request.GET:
        segmento_id = int(request.GET.get('segmento'))
        uo_ids = request.GET.get('uos') and request.GET.get('uos').split('-') or None
        modalidade_ids = request.GET.get('modalidades') and [int(x) for x in request.GET.get('modalidades').split('-')] or []
        matriz_id = request.GET.get('matriz') and int(request.GET.get('matriz')) or None
        respostas = respostas.filter(respondente__segmento=segmento_id)

        if uo_ids:
            respostas = respostas.filter(respondente__setor__uo__in=uo_ids)
        if segmento_id == Segmento.ALUNO:
            if modalidade_ids:
                ids_alunos = Aluno.objects.filter(curso_campus__modalidade__in=modalidade_ids).values_list('id', flat=True)
                respostas = respostas.filter(
                    respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                )
            if matriz_id:
                ids_alunos = Aluno.objects.filter(curso_campus__matrizcurso__matriz=matriz_id).values_list('id', flat=True)
                respostas = respostas.filter(
                    respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                )
        else:
            if modalidade_ids:
                respondente_pks = (
                    respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__modalidade__in=modalidade_ids)
                    .order_by('respondente')
                    .values_list('respondente')
                    .distinct()
                )
                respostas = respostas.filter(respondente__in=respondente_pks)
            if matriz_id:
                respondente_pks = (
                    respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__matrizcurso__matriz=matriz_id)
                    .order_by('respondente')
                    .values_list('respondente')
                    .distinct()
                )
                respostas = respostas.filter(respondente__in=respondente_pks)

        if uo_ids or modalidade_ids or matriz_id:
            mostrar_filtros = False

    else:
        setor_id = request.GET.get('setor', '')
        if setor_id:
            respostas = respostas.filter(respondente__setor=setor_id)
        segmento_id = request.GET.get('segmento', '')
        if segmento_id:
            segmento = Segmento.objects.get(pk=segmento_id)
            respostas = respostas.filter(respondente__segmento=segmento_id)

    for resposta in respostas.values_list('resposta', flat=True).order_by('resposta').distinct():
        series.append((resposta, respostas.filter(resposta=resposta).order_by('respondente').values_list('respondente').distinct().count()))

    total_respondentes = respostas.order_by('respondente').values_list('respondente').distinct().count()

    if pergunta.tipo_resposta != Pergunta.RESPOSTA_SUBJETIVA:
        if modalidade_ids:
            subtitle.append(', '.join([modalidade.descricao for modalidade in Modalidade.objects.filter(pk__in=modalidade_ids)]))
        if segmento_id:
            segmento = Segmento.objects.get(pk=segmento_id)
            subtitle.append(segmento.descricao)
        if matriz_id:
            matriz = Matriz.objects.get(pk=matriz_id)
            subtitle.append(matriz.descricao)
        if setor_id:
            setor = Setor.objects.suap_ativos().get(pk=setor_id)
            subtitle.append(setor.sigla)
        if uo_ids:
            subtitle.append(', '.join([uo.sigla for uo in UnidadeOrganizacional.objects.suap().filter(pk__in=uo_ids)]))

        subtitle = ' - '.join(subtitle)

        if pergunta.multipla_escolha:
            plotOptions = {'column': {'dataLabels': {'enabled': 'true', 'color': 'white'}}}
            grafico = BarChart(
                'grafico',
                title=str(pergunta),
                subtitle=subtitle,
                minPointLength=0,
                data=series,
                plotOptions=plotOptions,
                tooltip={'valueSuffix': f' de {total_respondentes}'},
            )
            grafico.plotOptions['series']['dataLabels']['enabled'] = 'true'
            grafico.plotOptions['series']['dataLabels']['padding'] = '0'
            grafico.plotOptions['series']['dataLabels']['format'] = '{y}'
            grafico.plotOptions['column']['dataLabels']['padding'] = '0'
        else:
            dataLabels_format = '<b>{point.name}</b>: {point.percentage:.0f} %'
            grafico = PieChart('grafico', title=str(pergunta), subtitle=subtitle, minPointLength=0, data=series, dataLabels_format=dataLabels_format)
        if 'setor' in request.GET:
            return HttpResponse(str(grafico))
    else:
        respostas = respostas.order_by('respondente__setor')

    if mostrar_filtros:
        setores = (
            Setor.objects.suap_ativos()
            .filter(pk__in=list(respostas.order_by('respondente__setor').values_list('respondente__setor', flat=True)))
            .distinct()
        )
        segmentos = pergunta.grupo_pergunta.questionario.segmentos.all()

    return locals()


@rtr()
@login_required
def estatistica_grupo_resposta(request, pk):
    title = 'Estatísticas de Respostas'
    grupo_pergunta = GrupoPergunta.objects.get(pk=pk)
    series = []
    groups = []
    respostas = Resposta.objects.none()
    mostrar_filtros = True
    groups = [x for x, y in Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES[1:]]

    subtitle = []
    uo_ids = None
    modalidade_ids = None
    matriz_id = None
    setor_id = None
    segmento_id = None

    for pergunta in grupo_pergunta.pergunta_set.filter(tipo_resposta=Pergunta.RESPOSTA_ESCALA_PADRAO).all():
        series.append([pergunta.enunciado])
        respostas = pergunta.resposta_set.exclude(resposta='')

        if '_' in request.GET:
            segmento_id = int(request.GET.get('segmento'))
            uo_ids = request.GET.get('uos') and request.GET.get('uos').split('-') or None
            modalidade_ids = request.GET.get('modalidades').split('-')
            matriz_id = request.GET.get('matriz') and int(request.GET.get('matriz')) or None

            if uo_ids:
                respostas = respostas.filter(respondente__setor__uo__in=uo_ids)
            if segmento_id == Segmento.ALUNO:
                if modalidade_ids:
                    ids_alunos = Aluno.objects.filter(curso_campus__modalidade__in=modalidade_ids).values_list('id', flat=True)
                    respostas = respostas.filter(
                        respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                    )
                if matriz_id:
                    ids_alunos = Aluno.objects.filter(curso_campus__matrizcurso__matriz=matriz_id).values_list('id', flat=True)
                    respostas = respostas.filter(
                        respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos
                    )
            else:
                if modalidade_ids:
                    respondente_pks = (
                        respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__modalidade__in=modalidade_ids)
                        .order_by('respondente')
                        .values_list('respondente')
                        .distinct()
                    )
                    respostas = respostas.filter(respondente__in=respondente_pks)
                if matriz_id:
                    respondente_pks = (
                        respostas.filter(respondente__vinculo__professor__professordiario__diario__turma__curso_campus__matrizcurso__matriz=matriz_id)
                        .order_by('respondente')
                        .values_list('respondente')
                        .distinct()
                    )
                    respostas = respostas.filter(respondente__in=respondente_pks)

            if uo_ids or modalidade_ids or matriz_id:
                mostrar_filtros = False
        else:
            setor_id = request.GET.get('setor', '')
            if setor_id:
                respostas = respostas.filter(respondente__setor=setor_id)
            segmento_id = request.GET.get('segmento', '')
            if segmento_id:
                respostas = respostas.filter(respondente__segmento=segmento_id)

        for resposta in groups:
            series[-1].append(respostas.filter(resposta=resposta).count())

    if modalidade_ids:
        subtitle.append(', '.join([modalidade.descricao for modalidade in Modalidade.objects.filter(pk__in=modalidade_ids)]))
    if segmento_id:
        segmento = Segmento.objects.get(pk=segmento_id)
        subtitle.append(segmento.descricao)
    if matriz_id:
        matriz = Matriz.objects.get(pk=matriz_id)
        subtitle.append(matriz.descricao)
    if setor_id:
        setor = Setor.objects.suap_ativos().get(pk=setor_id)
        subtitle.append(setor.sigla)
    if uo_ids:
        subtitle.append(', '.join([uo.sigla for uo in UnidadeOrganizacional.objects.suap().filter(pk__in=uo_ids)]))

    subtitle = ' - '.join(subtitle)

    plotOptions = {'column': {'dataLabels': {'enabled': 'true', 'color': 'white'}}}
    grafico = StackedGroupedColumnChart(
        'grafico', title=grupo_pergunta.descricao, subtitle=subtitle, data=series, groups=groups, plotOptions=plotOptions
    )
    grafico.plotOptions['series']['dataLabels']['enabled'] = 'true'
    grafico.plotOptions['series']['dataLabels']['padding'] = '0'
    grafico.plotOptions['series']['dataLabels']['format'] = '{percentage:.0f}%'
    grafico.plotOptions['column']['dataLabels']['padding'] = '0'

    if 'setor' in request.GET:
        return HttpResponse(str(grafico))
    if mostrar_filtros:
        setores = (
            Setor.objects.suap_ativos()
            .filter(pk__in=list(respostas.order_by('respondente__setor').values_list('respondente__setor', flat=True)))
            .distinct()
        )
        segmentos = grupo_pergunta.questionario.segmentos.all()

    return locals()


@rtr()
@login_required
def resultado_avaliacao_matriz(request, pk, matriz_pk):
    title = 'Estatísticas de Respostas'
    avaliacao = Avaliacao.objects.get(pk=pk)

    id_questionario_professor = None

    qs = avaliacao.questionario_set.all()
    qs_questionario_aluno = qs.filter(segmentos=Segmento.ALUNO).values_list('pk', flat=True)
    id_questionario_aluno = qs_questionario_aluno.exists() and qs_questionario_aluno[0] or None
    qs_questionario_professor = qs.filter(segmentos=Segmento.PROFESSOR).values_list('pk', flat=True)
    id_questionario_professor = qs_questionario_professor.exists() and qs_questionario_professor[0] or None

    matriz = Matriz.objects.get(pk=matriz_pk)
    matrizes = []
    anual = matriz.matrizcurso_set.filter(curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL).exists()
    periodos = list(range(1, matriz.qtd_periodos_letivos + 1))
    colspan = matriz.qtd_periodos_letivos + 6
    nucleos = []
    attrs = ('carga_horaria', 'sequencia_didatica', 'ementa_programa', 'regime_misto', 'justificativa')
    for nucleo in Nucleo.objects.filter(pk__in=matriz.componentecurricular_set.values_list('nucleo', flat=True).distinct()):
        componentes_curriculares = list(
            matriz.componentecurricular_set.filter(nucleo=nucleo)
            .exclude(tipo__in=(ComponenteCurricular.TIPO_SEMINARIO, ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL))
            .order_by('componente__descricao')
            .distinct()
        )
        nucleos.append((f'Núcleo {nucleo}', componentes_curriculares))

    componentes_curriculares = []
    for componente_curricular in (
        matriz.componentecurricular_set.filter(tipo=ComponenteCurricular.TIPO_SEMINARIO).order_by('componente__descricao').distinct()
    ):
        componentes_curriculares.append(componente_curricular)
    nucleos.append(('Seminários', componentes_curriculares))

    componentes_curriculares = []
    for componente_curricular in (
        matriz.componentecurricular_set.filter(tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL).order_by('componente__descricao').distinct()
    ):
        componentes_curriculares.append(componente_curricular)
    nucleos.append(('Prática Profissional', componentes_curriculares))

    matrizes.append((matriz, nucleos, anual))
    return locals()


@rtr()
@login_required
def estatistica_resposta_componente_curricular(request, pk, componente_curricular_pk, segmento_pk):
    componente_curricular = ComponenteCurricular.objects.get(pk=componente_curricular_pk)
    return estatistica_resposta_componente(request, pk, componente_curricular.matriz_id, componente_curricular.componente_id, segmento_pk)


@rtr()
@login_required
def estatistica_resposta_componente(request, pk, matriz_pk, componente_pk, segmento_pk):
    title = 'Estatísticas de Respostas'
    subtitle = []
    respostas = AvaliacaoComponenteCurricular.objects.filter(respondente__questionario__avaliacao=pk, respondente__segmento=segmento_pk)
    if matriz_pk and int(matriz_pk):
        componente_curricular = ComponenteCurricular.objects.get(matriz=matriz_pk, componente=componente_pk)
        respostas = respostas.filter(componente_curricular=componente_curricular)
    else:
        componente_curricular = Componente.objects.get(pk=componente_pk)
        respostas = respostas.filter(componente_curricular__componente=componente_pk)
    setor = request.GET.get('setor', '')
    if setor:
        setor = Setor.objects.suap_ativos().get(pk=setor)
        respostas = respostas.filter(respondente__setor=setor)
        subtitle.append(setor.sigla)
    segmento_id = request.GET.get('segmento', segmento_pk)
    if segmento_id:
        segmento = Segmento.objects.get(pk=segmento_id)
        respostas = respostas.filter(respondente__segmento=segmento)
        subtitle.append(segmento.descricao)
    series = []
    groups = []
    subtitle = ' - '.join(subtitle)
    for choice in Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES[1:]:
        groups.append(choice[0])
    series.append(['Carga Horária'])
    for valor in groups:
        series[-1].append(respostas.exclude(carga_horaria='').filter(carga_horaria=valor).count())
    series.append(['Sequência-Didática'])
    for valor in groups:
        series[-1].append(respostas.exclude(sequencia_didatica='').filter(sequencia_didatica=valor).count())
    series.append(['Ementa'])
    for valor in groups:
        series[-1].append(respostas.exclude(ementa_programa='').filter(ementa_programa=valor).count())
    series.append(['Regime Misto'])
    for valor in groups:
        series[-1].append(respostas.exclude(regime_misto='').filter(regime_misto=valor).count())

    dataLabels_format = '<b>{point.name}</b>: {point.percentage:.1f} %'
    plotOptions = {'column': {'dataLabels': {'enabled': 'true', 'color': 'white'}}}
    grafico = StackedGroupedColumnChart(
        'grafico', title=str(componente_curricular), subtitle=subtitle, data=series, groups=groups, plotOptions=plotOptions
    )

    grafico.plotOptions['series']['dataLabels']['enabled'] = 'true'
    grafico.plotOptions['series']['dataLabels']['padding'] = '0'
    grafico.plotOptions['series']['dataLabels']['format'] = '{percentage:.0f}%'
    grafico.plotOptions['column']['dataLabels']['padding'] = '0'

    setores = Setor.objects.suap_ativos().filter(
        pk__in=respostas.order_by('respondente__setor').values_list('respondente__setor', flat=True).distinct()
    )
    respostas = respostas.filter(justificativa__isnull=False).exclude(justificativa='').order_by('respondente__setor')
    series2 = []
    for serie in series:
        serie2 = [serie[0]]
        total = sum(serie[1:])
        for i in range(1, len(groups) + 1):
            percentual = 0 if total == 0 else round(100 * serie[i] / total)
            serie2.append(percentual)
        series2.append(serie2)
    return locals()


@rtr()
@login_required
def respostas_subjetivas_xls(request, pk):
    questionario = Questionario.objects.get(pk=pk)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=RespostasSubjetivas.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        for sigla in [instituicao, *list(UnidadeOrganizacional.objects.suap().all().values_list('sigla', flat=True))]:
            qs_diretorias = Diretoria.objects.filter(setor__uo__sigla=sigla)
            if qs_diretorias.count() > 1:
                for diretoria in qs_diretorias:
                    data_dict = {}
                    for i, grupo_pergunta in enumerate(questionario.grupopergunta_set.all()):
                        qs_perguntas = grupo_pergunta.pergunta_set.filter(tipo_resposta=Pergunta.RESPOSTA_SUBJETIVA)
                        for pergunta in qs_perguntas:
                            header = (f'Grupo {i + 1}', grupo_pergunta.descricao, pergunta.enunciado)
                            answers = [r.resposta for r in pergunta.resposta_set.filter(respondente__setor=diretoria.setor)]
                            data_dict[header] = answers
                        if not qs_perguntas:
                            header = (f'Grupo {i + 1}', '', '')
                            data_dict[header] = []

                    if data_dict:
                        df = pd.DataFrame({k: pd.Series(v) for k, v in data_dict.items()})
                        if not df.empty:
                            df.columns = pd.MultiIndex.from_tuples(df.columns)
                            sheet_name = diretoria.setor.sigla.replace('/', '-')[:31]
                            df.to_excel(writer, sheet_name=sheet_name)
            else:
                data_dict = {}
                for i, grupo_pergunta in enumerate(questionario.grupopergunta_set.all()):
                    qs_perguntas = grupo_pergunta.pergunta_set.filter(tipo_resposta=Pergunta.RESPOSTA_SUBJETIVA)
                    for pergunta in qs_perguntas:
                        header = (f'Grupo {i + 1}', grupo_pergunta.descricao, pergunta.enunciado)
                        qs = pergunta.resposta_set.all()
                        if sigla != instituicao:
                            qs = qs.filter(respondente__setor__uo__sigla=sigla)
                        answers = [r.resposta for r in qs]
                        data_dict[header] = answers
                    if not qs_perguntas:
                        header = (f'Grupo {i + 1}', '', '')
                        data_dict[header] = []

                if data_dict:
                    df = pd.DataFrame({k: pd.Series(v) for k, v in data_dict.items()})
                    if not df.empty:
                        df.columns = pd.MultiIndex.from_tuples(df.columns)
                        sheet_name = sigla[:31]
                        df.to_excel(writer, sheet_name=sheet_name)

    return response


@rtr()
@login_required
def respostas_subjetivas_componentes_xls(request, pk, matriz_id=None):
    questionario = Questionario.objects.get(pk=pk)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=RespostasSubjetivas.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        #    AvaliacaoComponenteCurricular
        qs = (
            JustificativaAvaliacaoComponenteCurricular.objects.filter(respondente__questionario=questionario)
            .exclude(justificativa='')
            .exclude(justificativa__isnull=True)
        )  # aprovada=True,
        if matriz_id:
            qs = qs.filter(componente_curricular__matriz=matriz_id)
        componentes = Componente.objects.filter(
            id__in=qs.order_by('componente_curricular__componente').values_list('componente_curricular__componente', flat=True).distinct()
        )
        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        for sigla in [instituicao, *list(UnidadeOrganizacional.objects.suap().all().values_list('sigla', flat=True))]:
            qs_diretorias = Diretoria.objects.filter(setor__uo__sigla=sigla)
            if qs_diretorias.count() > 1:
                for diretoria in qs_diretorias:
                    rows = []
                    pks_componentes = (
                        componentes.filter(componentecurricular__matriz__matrizcurso__curso_campus__diretoria__setor=diretoria.setor)
                        .order_by('pk')
                        .values_list('pk', flat=True)
                        .distinct()
                    )
                    tmp_componentes = componentes.filter(pk__in=pks_componentes)

                    for componente in tmp_componentes.order_by('descricao'):
                        qs_avaliacao_componente = qs.filter(componente_curricular__componente=componente)
                        if qs_avaliacao_componente.exists():
                            rows.append([str(componente)])
                            for justificativa in qs_avaliacao_componente.order_by('justificativa').values_list('justificativa', flat=True).distinct():
                                rows.append([justificativa])

                    if rows:
                        df = pd.DataFrame(rows)
                        sheet_name = diretoria.setor.sigla.replace('/', '-')[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
            else:
                rows = []
                for componente in componentes.order_by('descricao'):
                    qs_avaliacao_componente = qs.filter(componente_curricular__componente=componente)
                    if sigla != instituicao:
                        qs_avaliacao_componente = qs_avaliacao_componente.filter(respondente__setor__uo__sigla=sigla)

                    if qs_avaliacao_componente.exists():
                        rows.append([str(componente)])
                        for justificativa in qs_avaliacao_componente.order_by('justificativa').values_list('justificativa', flat=True).distinct():
                            rows.append([justificativa])

                if rows:
                    df = pd.DataFrame(rows)
                    sheet_name = sigla[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

    return response


@login_required
def justificar_avaliacao_componente_ajax(request, respondente, campo, componente_curricular):
    qs = JustificativaAvaliacaoComponenteCurricular.objects.filter(
        respondente_id=respondente, campo=int(campo), componente_curricular_id=componente_curricular
    )
    if qs.exists():
        obj = qs.first()
    else:
        obj = JustificativaAvaliacaoComponenteCurricular(respondente_id=respondente, campo=int(campo), componente_curricular_id=componente_curricular)
    obj.justificativa = request.GET['justificativa']
    if obj.justificativa:
        obj.save()
    else:
        if obj.pk:
            obj.delete()
    return HttpResponse('Justificativa salva com sucesso.')
