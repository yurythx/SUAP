from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from datetime import datetime
from django.http import HttpResponseForbidden
from edu.models.internacionalizacao import PreMatriculaInternacional, InscricaoAlunoEstrangeiro, SolicitacaoCorrecaoInscricaoAlunoEstrangeiro
from djtools import layout
from edu import tasks

from djtools.utils import (
    rtr,
    permission_required,
    httprr,
)
from edu.forms import (
    RealizarConvocacaoInternacionalForm,
    InscricaoAlunoEstrangeiroForm,
    SolicitarCorrecaoInscricaoForm,
    EnviarCorrecaoInscricaoForm,
    AvalicaoInscricaoAlunoEstrangeiroForm,
    ProcessarPreMatriculaForm,
)


@layout.info()
def index_infos(request):
    """Indica ao aluno estrangeiro a próxima ação de pré-matrícula.

    Para usuários externos, exibe link de acompanhamento se já existe inscrição
    em andamento (situação solicitada ou aguardando correção); caso contrário,
    oferece o link de pré-matrícula se há convocação ativa em período de inscrição.

    Args:
        request: requisição HTTP usada para obter o vínculo do usuário.

    Returns:
        list[dict]: aviso com ``url``, ``titulo`` e ``icone`` quando aplicável;
        lista vazia para usuários não-externos ou sem ações pendentes.
    """
    infos = []
    vinculo = request.user.get_vinculo()
    if vinculo.eh_usuario_externo:
        situacoes_validas = [InscricaoAlunoEstrangeiro.SITUACAO_SOLICITADA, InscricaoAlunoEstrangeiro.SITUACAO_AGUARDANDO_CORRECAO]
        inscricao_em_andamento = (
            vinculo.inscricaoalunoestrangeiro_set.filter(situacao__in=situacoes_validas)
            .select_related('pre_matricula__matriz_curso__curso_campus')
            .order_by('id')
            .last()
        )
        if inscricao_em_andamento:
            infos.append(
                {
                    'url': inscricao_em_andamento.get_absolute_url(),
                    'titulo': f'Acompanhe sua pré-matrícula no curso {inscricao_em_andamento.pre_matricula.matriz_curso.curso_campus.descricao_historico}',
                    'icone': 'cog',
                }
            )
        else:
            convocacao = vinculo.planilhaconvocacao_set.select_related('pre_matricula__matriz_curso__curso_campus').order_by('id').last()
            if convocacao and convocacao.pre_matricula.is_em_periodo_inscricao():
                infos.append(
                    {
                        'url': '/edu/inscricao_internacional/',
                        'titulo': f'Realize sua pré-matrícula no curso {convocacao.pre_matricula.matriz_curso.curso_campus.descricao_historico}',
                        'icone': 'cog',
                    }
                )
    return infos


@rtr()
@permission_required('edu.change_prematriculainternacional')
def pre_matricula_internacional(request, pk):
    obj = get_object_or_404(PreMatriculaInternacional, pk=pk)
    inscritos = obj.inscricaoalunoestrangeiro_set.values_list('vinculo', flat=True)
    title = str(obj)
    return locals()


@rtr()
@login_required()
def inscricao_aluno_estrangeiro(request, pk):
    obj = get_object_or_404(InscricaoAlunoEstrangeiro, pk=pk)
    is_usuario_convocado = obj.vinculo.user_id == request.user.pk
    if not request.user.has_perm('edu.change_prematriculainternacional') and not is_usuario_convocado:
        return HttpResponseForbidden()
    solicitacao_correcao_pendente = obj.get_solicitacoes_correcao_pendente().order_by('id').last()
    if request.user.is_superuser and 'cancelar_avaliacao' in request.GET:
        obj.cancelar_avaliacao()
        return httprr(obj.get_absolute_url(), 'Avaliação desfeita com sucesso.')
    title = str(obj)
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def solicitar_correcao_inscricao_aluno_estrangeiro(request, pk):
    title = 'Solicitar Correção'
    obj = get_object_or_404(InscricaoAlunoEstrangeiro, pk=pk)
    form = SolicitarCorrecaoInscricaoForm(data=request.POST or None, request=request)
    if form.is_valid():
        form.instance.inscricao = obj
        form.save()
        form.instance.enviar_email_solicitacao_correcao()
        return httprr('..', 'Solicitação de correção realizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def enviar_correcao_inscricao_aluno_estrangeiro(request, pk):
    title = 'Re-enviar Inscrição'
    obj = get_object_or_404(SolicitacaoCorrecaoInscricaoAlunoEstrangeiro, pk=pk)
    if obj.inscricao.vinculo.user_id != request.user.pk:
        return HttpResponseForbidden()
    form = EnviarCorrecaoInscricaoForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        form.instance.enviar_email_correcao()
        return httprr('..', 'Inscrição re-enviada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def deferir_inscricao_aluno_estrangeiro(request, pk):
    title = 'Indeferir Solicitação'
    obj = get_object_or_404(InscricaoAlunoEstrangeiro, pk=pk)
    form = AvalicaoInscricaoAlunoEstrangeiroForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.instance.data_avaliacao = datetime.now()
        form.instance.avaliador = request.user.get_vinculo()
        form.instance.situacao = InscricaoAlunoEstrangeiro.SITUACAO_DEFERIDA
        form.save()
        form.instance.enviar_email_avaliacao()
        return httprr('..', 'Deferimento realizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def indeferir_inscricao_aluno_estrangeiro(request, pk):
    title = 'Indeferir Solicitação'
    obj = get_object_or_404(InscricaoAlunoEstrangeiro, pk=pk)
    form = AvalicaoInscricaoAlunoEstrangeiroForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.instance.data_avaliacao = datetime.now()
        form.instance.avaliador = request.user.get_vinculo()
        form.instance.situacao = InscricaoAlunoEstrangeiro.SITUACAO_INDEFERIDA
        form.save()
        form.instance.enviar_email_avaliacao()
        return httprr('..', 'Indeferimento realizado com sucesso.')
    return locals()


@rtr()
@login_required
def inscricao_internacional(request):
    title = 'Realizar Inscrição'
    vinculo = request.user.get_vinculo()
    convocacao = vinculo.planilhaconvocacao_set.order_by('id').last()
    if convocacao is None or not convocacao.pre_matricula.is_em_periodo_inscricao():
        return HttpResponseForbidden()
    instance = vinculo.inscricaoalunoestrangeiro_set.filter(pre_matricula=convocacao.pre_matricula).order_by('id').last()
    form = InscricaoAlunoEstrangeiroForm(data=request.POST or None, files=request.FILES or None, instance=instance, request=request)
    if form.is_valid():
        form.instance.pre_matricula = convocacao.pre_matricula
        form.instance.vinculo = vinculo
        form.save()
        return httprr(form.instance.get_absolute_url(), 'Inscrição realizada com sucesso. Aguarde enquanto sua solicitação é avaliada.')
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def editar_inscricao_aluno_estrangeiro(request, pk):
    title = 'Editar Inscrição'
    obj = get_object_or_404(InscricaoAlunoEstrangeiro, pk=pk)
    form = InscricaoAlunoEstrangeiroForm(data=request.POST or None, files=request.FILES or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(form.instance.get_absolute_url(), 'Inscrição realizada com sucesso. Aguarde enquanto sua solicitação é avaliada.')
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def convocacao_prematricula_internacional(request, pk):
    obj = get_object_or_404(PreMatriculaInternacional, pk=pk)
    title = 'Convocar Selecionados'
    form = RealizarConvocacaoInternacionalForm(data=request.POST or None, files=request.FILES or None)
    form.fields['data_publicacao'].initial = datetime.now().date()
    if form.is_valid():
        try:
            form.instance.pre_matricula = obj
            form.save()
            vinculos = form.instance.processar()
            form.instance.enviar_emails(vinculos)
            return httprr(obj.get_absolute_url(), 'Convocação realizada com sucesso.', close_popup=True)
        except ValueError as e:
            return httprr(obj.get_absolute_url(), str(e), 'error', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_prematriculainternacional')
def processar_prematricula_internacional(request, pk):
    title = 'Gerar Matrículas'
    obj = get_object_or_404(PreMatriculaInternacional, pk=pk)
    form = ProcessarPreMatriculaForm(data=request.POST or None)
    if form.is_valid():
        return tasks.gerar_matriculas(obj, dict(form.cleaned_data))
    return locals()
