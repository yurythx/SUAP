import datetime

from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu.forms import MensagemComplementarForm, MensagemForm
from edu.models import Aluno, ConvocacaoENADE, Mensagem, RegistroLeitura


@permission_required('edu.add_mensagem')
@rtr()
def enviar_mensagem_complementar(request, pk):
    title = 'Enviar Mensagem Complementar'
    obj = get_object_or_404(Mensagem, pk=pk)
    if obj.remetente.pk != request.user.pk:
        return HttpResponseForbidden()
    form = MensagemComplementarForm(obj, data=request.POST or None, request=request, files=request.FILES or None)
    if form.is_valid():
        nova_mensagem = form.processar()
        link = f'<a href="/edu/mensagem/{nova_mensagem.pk}/">CLIQUE AQUI</a>'
        return httprr('..', mark_safe(f'Mensagens ({nova_mensagem.destinatarios.count()}) enviadas com sucesso. Para visualizá-la, {link}.'))
    return locals()


@permission_required('edu.add_mensagem')
@rtr()
def enviar_mensagem(request):
    title = 'Nova Mensagem'
    initial = {}
    post = request.POST.copy()
    url = '.'

    if 'diario' in request.GET:
        initial['diario'] = request.GET.get('diario')
        if 'origem' in request.GET:
            url = f'/edu/{request.GET.get("origem")}/{request.GET.get("diario")}/'
            if request.GET.get('origem') == 'meu_diario':
                url = f'{url}1/'

    if 'aluno' in request.GET:
        aluno = Aluno.objects.filter(matricula=request.GET.get('aluno')).only('id').first()
        if aluno:
            initial['aluno'] = aluno.id
            if 'origem' in request.GET:
                url = f'/edu/{request.GET.get("origem")}/{request.GET.get("aluno")}/'

    if 'enade' in request.GET:
        initial['enade'] = request.GET.get('enade')
        if 'curso_campus' in request.GET:
            initial['curso_campus'] = request.GET.get('curso_campus')
        elif 'modalidade' in request.GET:
            initial['curso_campus'] = list(
                ConvocacaoENADE.objects.filter(id=request.GET.get('enade'))
                .first()
                .cursos.filter(modalidade_id=request.GET.get('modalidade'))
                .values_list('id', flat=True)
            )
        if 'tipo_convocacao' in request.GET:
            initial['tipo_convocacao'] = request.GET.get('tipo_convocacao')
        if 'periodo' in request.GET:
            initial['periodo'] = request.GET.get('periodo')
        url = f'/edu/convocados_enade/{request.GET.get("enade")}/{request.GET.get("curso_campus")}/'

    form = MensagemForm(post or None, files=request.FILES or None, request=request, initial=initial)

    if form.is_valid():
        result = form.processar(request)
        if isinstance(result, int):
            if result:
                return httprr(url, f'{result} mensagens enviadas com sucesso.')
            else:
                return httprr(url, 'Não foi enviada a mensagem, pois não foi encontrada nenhuma pessoa nos campos do destinatário.', 'error')
        else:
            return result
    return locals()


@login_required()
@rtr()
def mensagem(request, pk):
    obj = get_object_or_404(Mensagem, pk=pk)
    title = obj.assunto
    is_remetente = obj.remetente_id == request.user.pk
    is_destinatario = obj.destinatarios.filter(id=request.user.pk).exists()
    is_administrador = request.user.has_group_cached('Administrador Acadêmico')

    if not is_remetente and not is_destinatario and not is_administrador:
        return httprr('/', 'Apenas o remetente e os destinatários podem visualizar a mensagem.', 'error')

    if is_destinatario and not obj.existe_registro_leitura(request.user):
        RegistroLeitura.objects.create(mensagem=obj, destinatario=request.user, data_leitura=datetime.datetime.today())

    if is_remetente or is_administrador:
        registros_leitura = RegistroLeitura.objects.filter(mensagem=obj)
        outros_destinatarios = obj.destinatarios.exclude(pk__in=registros_leitura.values_list('destinatario', flat=True))
    return locals()
