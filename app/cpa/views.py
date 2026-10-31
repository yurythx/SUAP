import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.aggregates import Count
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from cpa.forms import (
    EmpresaForm,
    PaiAlunoForm,
    PerguntaForm,
    ResponderQuestionarioFormFactory,
    ResultadoAgrupadoForm,
    ResultadoForm,
    ResultadoPorCursoForm,
)
from cpa.models import Categoria, Pergunta, Questionario
from djtools.layout import inscricao
from djtools.utils import JsonResponse, group_required, httprr, rtr
from edu.models import Aluno, CursoCampus


@inscricao()
def index_inscricoes(request):
    inscricoes = []
    questionario_auto_avaliacao = Questionario.get_pendente(request.user)
    if questionario_auto_avaliacao and Questionario.questionario_pode_ser_respondido(request.user, questionario_auto_avaliacao):
        inscricoes.append(
            {
                'url': f'/cpa/responder_questionario/{questionario_auto_avaliacao.pk}',
                'titulo': f'{questionario_auto_avaliacao.titulo_alerta} ({questionario_auto_avaliacao.get_percentual_respondido(request.user)}%).',
                'prazo': questionario_auto_avaliacao.data_fim,
            }
        )

    return inscricoes


@rtr()
@group_required('cpa_gerente')
def adicionar_pergunta(request, questionario_id, categoria_id):
    title = 'Adicionar Pergunta'
    questionario = get_object_or_404(Questionario, pk=questionario_id)
    categoria = get_object_or_404(Categoria, pk=categoria_id)
    form = PerguntaForm(request.POST or None, questionario=questionario, categoria=categoria)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Pergunta adicionada com sucesso.')
    return locals()


@rtr()
@group_required('cpa_gerente')
def editar_pergunta(request, pk):
    title = 'Editar Pergunta'
    pergunta = get_object_or_404(Pergunta, pk=pk)
    form = PerguntaForm(request.POST or None, instance=pergunta)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Pergunta alterada com sucesso.')
    return locals()


@rtr()
def identificacao(request, tipo):
    title = 'Avaliação Institucional'
    if int(tipo) == Questionario.PAI_ALUNO:
        publico = 'Pai de Aluno'
        form = PaiAlunoForm(request.POST or None)
    elif int(tipo) == Questionario.EMPRESA:
        publico = 'Empresa'
        form = EmpresaForm(request.POST or None)
    else:
        raise PermissionDenied

    questionarios = Questionario.objects.filter(data_inicio__lte=datetime.datetime.today(), data_fim__gte=datetime.datetime.today(), publico=tipo)
    if form.is_valid():
        uo = (
            'uo' in form.cleaned_data
            and form.cleaned_data['uo']
            or Aluno.objects.get(matricula=form.cleaned_data['matricula']).curso_campus.diretoria.setor.uo_id
        )
        referencia = 'matricula' in form.cleaned_data and form.cleaned_data['matricula'] or form.cleaned_data['cnpj']
        return httprr(
            '/cpa/responder_questionario/{}/?identificador={}&uo={}&referencia={}'.format(
                questionarios[0].pk, form.cleaned_data['identificacao'], uo, referencia
            )
        )

    return locals()


@rtr()
@group_required('cpa_gerente')
def questionario(request, pk):
    title = 'Avaliação Institucional'
    questionario = get_object_or_404(Questionario, pk=pk)
    categorias = questionario.get_perguntas_agrupadas_por_categoria()
    return locals()


@rtr()
@group_required('cpa_gerente, cpa_visualizador, cpa_visualizador_sistemico')
def resultado(request):
    title = 'Resultado'
    ano = datetime.datetime.now().year
    form = ResultadoForm(data=request.GET or None, initial={'ano': ano})
    if form.is_valid():
        if 'xls' in request.GET:
            return form.processar_xls()

        [questionario, categorias, opcoes, grafico_empilhado] = form.processar()

    return locals()


@rtr()
@login_required
def responder_questionario(request, pk):
    questionario = get_object_or_404(Questionario, pk=pk)
    title = questionario.descricao

    if not Questionario.questionario_pode_ser_respondido(request.user, questionario):
        raise PermissionDenied('Você já respondeu este questionário.')

    if questionario != Questionario.get_pendente(request.user):
        raise PermissionDenied

    Form = ResponderQuestionarioFormFactory(request, questionario.get_opcoes(), questionario.get_perguntas_agrupadas_por_categoria())
    form = Form(request.POST or None)
    if form.is_valid():
        form.save()
        messages.info(request, 'Respostas salvas com sucesso.')
        return httprr('/')

    return locals()


@rtr()
@group_required('cpa_gerente, cpa_visualizador, cpa_visualizador_sistemico')
def respostas_subjetivas(request, pergunta_id):
    pergunta = get_object_or_404(Pergunta, pk=pergunta_id)
    form = ResultadoForm(data=request.GET or None)
    if form.is_valid():
        respostas = form.obter_respostas_subjetivas(pergunta)

    return locals()


@rtr()
@group_required('cpa_gerente, cpa_visualizador, cpa_visualizador_sistemico')
def resultado_agrupados(request):
    title = 'Resultado Agrupado'
    ano = datetime.datetime.now().year
    form = ResultadoAgrupadoForm(data=request.GET or None, initial={'ano': ano})
    if form.is_valid():
        if 'xls' in request.GET:
            return form.processar_xls()

        resultado = form.processar()
        if isinstance(resultado, HttpResponseBase):
            return resultado
        [questionarios, questionario_agrupado, opcoes, publicos, nome_questionario_agrupado] = resultado

    return locals()


@rtr()
@group_required('cpa_gerente, cpa_visualizador, cpa_visualizador_sistemico')
def resultado_por_curso(request):
    title = 'Resultado Por Curso'
    ano = datetime.datetime.now().year
    form = ResultadoPorCursoForm(data=request.GET or None, initial={'ano': ano})
    if form.is_valid():
        graficos = form.processar()

    return locals()


@login_required
@csrf_exempt
def get_cursos(request):
    data = request.POST or request.GET
    id = data.get('filter_pks') or 0
    label = data.get('label')
    curso_ids = []
    descricoes = []
    qs = CursoCampus.objects.filter(diretoria__setor__uo_id=id)
    qs = qs.values(label).annotate(count=Count(label))
    cursos = CursoCampus.objects.filter(diretoria__setor__uo_id=id).filter(descricao_historico__in=qs.values_list(label, flat=True))
    for curso in cursos:
        if curso.descricao_historico not in descricoes:
            descricoes.append(curso.descricao_historico)
            curso_ids.append(curso.id)

    qs = CursoCampus.objects.filter(id__in=curso_ids).order_by(label)
    return JsonResponse(list(qs.values('id', label)))


@rtr()
@group_required('cpa_gerente')
def clonar_questionario(request, questionario_id):
    questionario = get_object_or_404(Questionario, pk=questionario_id)
    perguntas = list(questionario.pergunta_set.all())
    questionarioopcao_set = list(questionario.questionarioopcao_set.all())
    questionariocategoria_set = list(questionario.questionariocategoria_set.all())
    questionario.id = None
    questionario.save()
    for pergunta in perguntas:
        pergunta.id = None
        pergunta.questionario = questionario
        pergunta.save()

    for questionarioopcao in questionarioopcao_set:
        questionarioopcao.id = None
        questionarioopcao.questionario = questionario
        questionarioopcao.save()

    for questionariocategoria in questionariocategoria_set:
        questionariocategoria.id = None
        questionariocategoria.questionario = questionario
        questionariocategoria.save()

    return httprr(f'/admin/cpa/questionario/{questionario.pk:d}/', 'Relatório clonado com sucesso.')
