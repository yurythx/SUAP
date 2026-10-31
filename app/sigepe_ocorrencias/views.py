from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from djtools.utils import rtr, permission_required
from django.http import FileResponse

from sigepe_ocorrencias.models import PacoteOcorrenciaSigepe, RegistroAcaoSigepeOcorrencia, OcorrenciaSigepe
from sigepe_ocorrencias.forms import UploadArquivoRetornoForm
from djtools.utils import httprr

from sigepe_ocorrencias import tasks


@rtr()
@permission_required('sigepe_ocorrencias.view_pacoteocorrenciasigepe')
def visualizar_pacote(request, pacote_id):
    pacote = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)
    title = str(pacote)

    pode_gerar_novo_arquivo_envio = pacote.pode_gerar_novo_arquivo_envio()
    pode_solicitar_atualizacao_arquivo_envio = pacote.pode_solicitar_atualizacao_arquivo_envio()
    pode_zerar = pacote.pode_zerar()

    registros_acoes = RegistroAcaoSigepeOcorrencia.objects.filter(pacote_ocorrencia=pacote).order_by('-data')

    return locals()


@permission_required('sigepe_ocorrencias.add_pacoteocorrenciasigepe')
def download_arquivo_pacote_envio(request, pacote_id):
    obj = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)

    if not obj.arquivo_envio_arquivo:
        raise PermissionDenied

    nome_download = obj.arquivo_envio_nome
    response = FileResponse(obj.arquivo_envio_arquivo.open('rb'), as_attachment=True, filename=nome_download)

    return response


@rtr()
@permission_required('sigepe_ocorrencias.add_pacoteocorrenciasigepe')
def upload_arquivo_pacote_envio(request, pacote_id):
    pacote = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)
    title = f'{pacote} - Atualizar arquivo de envio'

    if request.method == 'POST':
        form = UploadArquivoRetornoForm(request.POST, request.FILES, instance=pacote)
        if form.is_valid():
            form.save()

            pacote.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO
            pacote.save()

            tasks.gerar_ocorrencias_atualizacao(pacote_ocorrencia=pacote, user=request.user)

            return httprr(f'/sigepe_ocorrencias/visualizar_pacote/{pacote_id}/', 'Upload realizado com sucesso.')
    else:
        form = UploadArquivoRetornoForm(instance=pacote)

    return locals()


@rtr()
@permission_required('sigepe_ocorrencias.add_pacoteocorrenciasigepe')
def gerar_arquivo_envio(request, pacote_id):
    pacote = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)

    pacote.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_GERAR_ARQUIVO_ENVIO
    pacote.save()

    tasks.gerar_ocorrencias(pacote_ocorrencia=pacote, user=request.user)

    return httprr(f'/sigepe_ocorrencias/visualizar_pacote/{pacote_id}/', 'Arquivo sendo gerado.')


@rtr()
@permission_required('sigepe_ocorrencias.add_pacoteocorrenciasigepe')
def zerar_pacote(request, pacote_id):
    pacote = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)

    pacote.situacao = PacoteOcorrenciaSigepe.CADASTRADO
    pacote.arquivo_envio_nome = None
    pacote.arquivo_envio_arquivo = None
    pacote.arquivo_retorno_arquivo = None
    pacote.save()

    OcorrenciaSigepe.objects.filter(pacote_ocorrencia=pacote).delete()

    RegistroAcaoSigepeOcorrencia.registrar_acao(
        pacote_ocorrencia=pacote,
        observacao='Pacote de ocorrências foi reiniciado. A partir de agora novos arquivos podem ser gerados do zero',
        user=request.user,
    )

    return httprr(f'/sigepe_ocorrencias/visualizar_pacote/{pacote_id}/', 'Arquivo sendo gerado.')


@rtr()
@permission_required('sigepe_ocorrencias.add_pacoteocorrenciasigepe')
def excluir_pacote(request, pacote_id):
    pacote = get_object_or_404(PacoteOcorrenciaSigepe, pk=pacote_id)
    pacote.delete()
    return httprr('/admin/sigepe_ocorrencias/pacoteocorrenciasigepe/', 'Pacote removido.')
