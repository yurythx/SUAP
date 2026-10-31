from urllib.error import URLError

from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404

from djtools.utils import httprr
from edu.models import Aluno
from microsoft.utils import get_dreamspark_url
from rh.models import Servidor


def redirecionar_aluno(request, servico):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    url = None
    if servico == 'office365':
        url = 'http://outlook.office365.com'
    elif servico == 'dreamspark':
        if not aluno.tem_acesso_servicos_microsoft() or not aluno.email_academico:
            return httprr('/', 'Você não tem permissão para acessar este serviço.', 'error')
        try:
            url = get_dreamspark_url(aluno.email_academico, aluno.pessoa_fisica.nome)
        except URLError:
            return httprr('/', 'Não foi possível conectar-se ao serviço. Tente novamente mais tarde.', 'error')

    if url:
        return HttpResponseRedirect(url)
    else:
        return httprr('/', 'Você não tem permissão para acessar este serviço.', 'error')


def redirecionar_servidor(request, servico):
    servidor = get_object_or_404(Servidor, matricula=request.user.username)
    url = None
    if servico == 'dreamspark':
        if not servidor.tem_acesso_servicos_microsoft() or not servidor.email_institucional:
            return httprr('/', 'Você não tem permissão para acessar este serviço.', 'error')
        try:
            url = get_dreamspark_url(servidor.email_institucional, servidor.pessoa_fisica.nome)
        except URLError:
            return httprr('/', 'Não foi possível conectar-se ao serviço. Tente novamente mais tarde.', 'error')
    if url:
        return HttpResponseRedirect(url)
    else:
        return httprr('/', 'Você não tem permissão para acessar este serviço.', 'error')
