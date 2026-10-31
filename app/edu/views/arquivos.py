import datetime
import hashlib

from django.db.models import Q
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse

from djtools.utils import (
    httprr,
    limitar_tamanho_nome_arquivo,
    permission_required,
    rtr,
)
from edu import tasks
from edu.forms import AvaliarArquivoUnicoForm, EditarAlunoArquivoForm, RenovarValidadeArquivoUnicoForm, UploadAlunoArquivoUnicoForm
from edu.models import Aluno, AlunoArquivo


@rtr()
@permission_required('edu.add_alunoarquivo')
def upload_arquivo_unico(request, pk):
    title = 'Upload de Arquivo'
    aluno = get_object_or_404(Aluno, pk=pk)
    form = UploadAlunoArquivoUnicoForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        tipo = form.cleaned_data['tipo']

        # TODO: Rever este cadastro de Aluno Arquivo, pois da forma como está, caso o operador adicione dois arquivos iguais,
        # dois arquivoUnico serão criados no banco e no disco, ao invés de apenas um ArquivoUnico e dois AlunoArquivo referenciando
        # esse ArquivoUnico. O método AlunoArquivo.update_or_create_from_file_bytes cuida disso. Na época que Breno foi implementar
        # o cadastro manual de arquivos, eu cheguei a comentar com ele sobre esse método, mas talvez ele não tenha entendido bem a
        # a ideia.
        arquivo_unico = form.save()
        arquivo_unico.tipo_conteudo = arquivo_unico.conteudo.file.content_type
        arquivo_unico.tamanho_em_bytes = arquivo_unico.conteudo.file.size
        arquivo_unico.charset = None
        arquivo_unico.nome_original_primeiro_upload = limitar_tamanho_nome_arquivo(arquivo_unico.conteudo.file.name, 100)
        arquivo_unico.data_hora_primeiro_upload = datetime.datetime.now()
        arquivo_unico.data_hora_criacao_registro = datetime.datetime.now()
        arquivo_unico.hash_sha512 = hashlib.sha512(arquivo_unico.conteudo.file.read())
        hash_sha512_link_id_str = '[{}],[{}]'.format(
            arquivo_unico.data_hora_criacao_registro.strftime('%d%m%Y__%H:%M:%S.%f'), arquivo_unico.hash_sha512
        )
        hash_sha512_link_id_bytes = (hash_sha512_link_id_str).encode('utf-8')
        arquivo_unico.hash_sha512_link_id = hashlib.sha512(hash_sha512_link_id_bytes).hexdigest()
        arquivo_unico.save()

        arquivo_aluno = AlunoArquivo()
        arquivo_aluno.tipo_origem_cadastro = AlunoArquivo.TIPO_ORIGEM_CADASTRO_MANUAL
        arquivo_aluno.tipo = tipo
        arquivo_aluno.aluno = aluno
        arquivo_aluno.arquivo_unico = arquivo_unico
        arquivo_aluno.nome_original = arquivo_unico.conteudo.file.name
        arquivo_aluno.nome_exibicao = arquivo_aluno.tipo.nome
        arquivo_aluno.descricao = arquivo_aluno.tipo.nome
        arquivo_aluno.validado = None
        arquivo_aluno.data_hora_upload = datetime.datetime.now()
        arquivo_aluno.data_hora_criacao_registro = datetime.datetime.now()
        arquivo_aluno.save()
        return httprr('..', 'Arquivo cadastrado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_alunoarquivo')
def download_pasta_documental(request, pk):
    hoje = datetime.datetime.now().date()
    documentos = AlunoArquivo.objects.filter(aluno_id=pk, validado=True, data_expiracao__gte=hoje)
    return tasks.download_pasta_documental(documentos)


@rtr()
@permission_required('edu.add_alunoarquivo')
def editar_tipo_alunoarquivo(request, pk):
    title = 'Editar Tipo de Arquivo'
    instance = get_object_or_404(AlunoArquivo, pk=pk)
    form = EditarAlunoArquivoForm(data=request.POST or None, files=request.FILES or None, instance=instance)
    if form.is_valid():
        instance.tipo = form.cleaned_data['tipo']
        instance.save()
        url_ret = '{}?tab=pasta_documental'.format(reverse('aluno', kwargs={'matricula': instance.aluno.matricula}))
        return httprr(url_ret, 'Tipo de arquivo alterado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_alunoarquivo')
def avaliar_arquivo_unico(request, pk):
    title = 'Avaliar Documento'
    arquivo_aluno = get_object_or_404(AlunoArquivo, pk=pk)
    if not arquivo_aluno.can_validate(request.user):
        return HttpResponseForbidden()
    form = AvaliarArquivoUnicoForm(data=request.POST or None, instance=arquivo_aluno)
    if form.is_valid():
        form.save()
        arquivo_aluno.validar(request.user)
        return httprr('..', 'Avaliação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_alunoarquivo')
def renovar_validade_arquivo_unico(request, pk):
    title = 'Renovar Validade do Documento'
    arquivo_aluno = get_object_or_404(AlunoArquivo, pk=pk)
    form = RenovarValidadeArquivoUnicoForm(data=request.POST or None, instance=arquivo_aluno)
    if form.is_valid():
        form.processar(request.user)
        return httprr('..', 'Renovação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_alunoarquivo')
def avaliacao_documentos(request, pk):
    title = 'Avaliação de documentos'
    qs = AlunoArquivo.objects.filter(validado__isnull=True, aluno__curso_campus__diretoria_id=pk)
    if 'coordenador' in request.GET and request.user.groups.filter(name='Coordenador de Curso').exists():
        qs = qs.filter(Q(aluno__curso_campus__coordenador__user=request.user) | Q(aluno__curso_campus__coordenador_2__user=request.user))
    return locals()
