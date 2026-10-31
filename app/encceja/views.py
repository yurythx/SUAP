import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from sentry_sdk import capture_exception

from comum.models import RegistroEmissaoDocumento
from djtools import layout
from djtools.utils import httprr, permission_required, rtr
from edu.models import SolicitacaoCertificadoENEM
from encceja.forms import AtualizarConfiguracaoSolicitacaoForm, CancelamentoSolicitacaoForm, FiltroQuantitativoForm, ImportarForm
from encceja.models import Solicitacao


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/encceja/quantitativo/', 'icone': 'certificate', 'titulo': 'Certificação ENCCEJA / ENEM'}
    )

    return servicos_anonimos


@permission_required('encceja.add_solicitacao')
@rtr()
def solicitacao(request, pk):
    obj = get_object_or_404(Solicitacao.objects, pk=pk)
    parcial = not obj.pode_certificar_integralmente()
    modelo_sem_timbre = (parcial and obj.configuracao.modelo_certificacao_parcial) or (not parcial and obj.configuracao.modelo_certificacao_completa)
    modelo_com_timbre = (parcial and obj.configuracao.modelo_certificacao_parcial_com_timbre) or (
        not parcial and obj.configuracao.modelo_certificacao_completa_com_timbre
    )
    motivo_certificacao_negada = obj.get_motivo_certificacao_negada()
    title = str(obj)
    if 'imprimir' in request.GET:
        try:
            com_timbre = 'timbre' in request.GET
            return obj.imprimir_certificacao(request.user, com_timbre=com_timbre)
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)
            return httprr(
                f'/encceja/solicitacao/{pk}/',
                'Ocorreu um erro ao gerar o certificado. Verifique se o modelo de certificado está cadastrado corretamente e tente novamente.',
                'error',
            )
    return locals()


@permission_required('encceja.add_solicitacao')
@rtr()
def cancelar_solicitacao(request, pk):
    obj = Solicitacao.objects.get(pk=pk)
    title = str(obj)
    form = CancelamentoSolicitacaoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.instance.cancelada = True
        form.instance.data_cancelamento = datetime.date.today()
        form.instance.responsavel_cancelamento = request.user
        form.save()
        RegistroEmissaoDocumento.objects.filter(tipo='ENCCEJA', modelo_pk=obj.pk).update(cancelado=True)
        return httprr('..', 'Cancelamento realizado com sucesso.')
    return locals()


@permission_required('encceja.add_solicitacao')
@rtr()
def descancelar_solicitacao(request, pk):
    obj = Solicitacao.objects.get(pk=pk)
    title = str(obj)
    form = CancelamentoSolicitacaoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.instance.cancelada = False
        form.instance.data_cancelamento = None
        form.instance.responsavel_cancelamento = None
        form.save()
        if obj.data_emissao:
            registro = RegistroEmissaoDocumento.objects.filter(tipo='ENCCEJA', modelo_pk=obj.pk).order_by('-data_emissao').first()
            if registro is None:
                return httprr(
                    '..', 'A solicitação foi descancelada, mas o registro de emissão do certificado não foi localizado.', 'error', close_popup=True
                )
            else:
                registro.cancelado = False
                registro.save()
        return httprr('..', 'Descancelamento realizado com sucesso.', close_popup=True)
    return locals()


@permission_required('encceja.add_solicitacao')
@rtr()
def atualizar_configuracao_solicitacao_encceja(request, pk):
    obj = Solicitacao.objects.get(pk=pk)
    title = str(obj)
    form = AtualizarConfiguracaoSolicitacaoForm(data=request.POST or None)
    if form.is_valid():
        RegistroEmissaoDocumento.objects.filter(tipo='ENCCEJA', modelo_pk=obj.pk).update(
            cancelado=True,
        )
        obj.data_emissao = None
        obj.save()
        return httprr('..', 'Atualização da configuracao da solicitacao realizada com sucesso.')
    return locals()


@permission_required('encceja.add_configuracao')
@rtr()
def importar_resultado(request):
    title = 'Importar Resultado'
    form = ImportarForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('/admin/encceja/solicitacao/', e.message, 'error')
        return httprr('/admin/encceja/solicitacao/', 'Importação realizada com sucesso.')
    return locals()


@rtr()
def quantitativo(request):
    title = 'Ensino Médio - Quantitativo de Certificados e Declarações Emitidos'
    category = 'Relatórios'
    icon = 'certificate'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = FiltroQuantitativoForm(data=request.GET or None)
    primeira_solicitacao = SolicitacaoCertificadoENEM.objects.order_by('data_solicitacao').first()
    if primeira_solicitacao:
        primeira_solicitacao = primeira_solicitacao.data_solicitacao
    else:
        primeira_solicitacao = Solicitacao.objects.order_by('data_emissao').first()
        if primeira_solicitacao:
            primeira_solicitacao = primeira_solicitacao.data_emissao
    if form.is_valid():
        registros = form.processar()
    else:
        registros = form.get_registros()
    return locals()
