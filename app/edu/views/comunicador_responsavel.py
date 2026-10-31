import datetime
from django.core import signing
from djtools.utils.response import EmptyImageResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu.forms import MensagemResponsavelForm, ResponderMensagemForm
from edu.models import MensagemResponsavel, RegistroLeituraResponsavel


@permission_required('edu.add_mensagem')
@rtr()
def enviar_mensagem_responsavel(request):
    title = 'Nova mensagem: Responsáveis de alunos'
    post = request.POST.copy()
    url = '.'

    form = MensagemResponsavelForm(post or None, files=request.FILES or None, request=request)

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
def responder_mensagem_responsavel(request, pk):
    title = 'Responder Mensagem'
    obj = get_object_or_404(RegistroLeituraResponsavel, pk=pk)
    form = ResponderMensagemForm(data=request.POST or None)
    if form.is_valid():
        obj.responder(form.cleaned_data['resposta'], request.user)
        return httprr('..', 'Resposta enviada com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def mensagemresponsavel(request, pk):
    obj = get_object_or_404(MensagemResponsavel, pk=pk)
    title = obj.assunto
    is_remetente = obj.remetente_id == request.user.pk
    is_destinatario = obj.destinatarios.filter(matricula=request.user.username).exists()
    is_administrador = request.user.has_group_cached('Membro ETEP', 'Diretor Acadêmico', 'Coordenador de Curso')

    if not is_remetente and not is_destinatario and not is_administrador:
        return httprr('/', 'Apenas o remetente e os destinatários podem visualizar a mensagem.', 'error')

    if is_destinatario and not obj.existe_registro_leitura(request.user):
        RegistroLeituraResponsavel.objects.create(mensagem=obj, destinatario=request.user, data_leitura=datetime.datetime.today())

    if is_remetente or is_administrador:
        registros_leitura = RegistroLeituraResponsavel.objects.filter(mensagem=obj)
        outros_destinatarios = obj.destinatarios.exclude(pk__in=registros_leitura.values_list('destinatario', flat=True))
    return locals()


def registro_leitra_mensagem_responsavel(request, pk):
    token = request.GET.get('token')
    try:
        email_responsavel = signing.loads(token)
    except TypeError, signing.BadSignature:
        return EmptyImageResponse()
    obj = get_object_or_404(MensagemResponsavel, pk=pk)
    for aluno in obj.destinatarios.filter(email_responsavel=email_responsavel):
        obj.registrar_leitura(aluno, 'E-mail', datetime.datetime.now())
    return EmptyImageResponse()
