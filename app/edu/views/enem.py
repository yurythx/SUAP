import datetime
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from comum.models import Configuracao, Vinculo
from comum.utils import get_sigla_reitoria
from djtools import layout
from djtools.templatetags.filters import normalizar
from djtools.utils import (
    documento,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import (
    AtenderComRessalvaSolicitacaoCertificadoENEMForm,
    CancelarRegistroEmissaoCertificadoENEMForm,
    ConsultarAndamentoSolicitacaoCertificadoENEMForm,
    EditarDadosPessoaisSolicitacaoCertificadoENEM,
    EditarRegistroAlunoINEPForm,
    EscolherReitorDiretorGeralForm,
    PesquisarRegistroAlunoINEPForm,
    RejeitarSolicitacaoCertificadoENEMForm,
    ReplicarSolicitacaoCertificadoENEMForm,
    SolicitarCertificadoENEMForm,
)
from edu.models import ConfiguracaoCertificadoENEM, Diretoria, RegistroAlunoINEP, RegistroEmissaoCertificadoENEM, SolicitacaoCertificadoENEM
from rh.models import Servidor, UnidadeOrganizacional


@rtr()
@login_required()
def configuracao_certificacao_enem(request, pk):
    obj = get_object_or_404(ConfiguracaoCertificadoENEM, pk=pk)
    pedidos_certificado = obj.registroalunoinep_set.all().order_by('nome')
    form = PesquisarRegistroAlunoINEPForm(obj, data=request.GET or None)

    if form.is_valid():
        pedidos_certificado = form.processar(obj)

    title = 'Configuração para Certificação ENEM'
    return locals()


@rtr()
@login_required()
def editar_registro_inep(request, pk):
    obj = get_object_or_404(RegistroAlunoINEP, pk=pk)
    form = EditarRegistroAlunoINEPForm(instance=obj, data=request.POST or None)

    if form.is_valid():
        form.save()
        return httprr('..', 'Registro atualizado com sucesso.')

    title = 'Editar Registro de Aluno no INEP'
    return locals()


@rtr()
@login_required()
def solicitacao_certificado_enem(request, pk):
    obj = get_object_or_404(SolicitacaoCertificadoENEM, pk=pk)
    mime_types_imagem = ('image/jpeg', 'image/pjpeg', 'image/png')
    title = 'Solicitação de Certificado ENEM'

    is_avaliada = obj.avaliada
    is_anterior_2014 = obj.configuracao_certificado_enem.ano.ano <= 2013

    return locals()


@login_required
@documento(enumerar_paginas=False)
@rtr()
def comprovante_solicitacao_certificado_enem_pdf(request: HttpRequest, codigo_geracao_solicitacao: str) -> dict[str, Any] | HttpResponse:
    obj = get_object_or_404(SolicitacaoCertificadoENEM, codigo_geracao_solicitacao=codigo_geracao_solicitacao)
    uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    title = 'Comprovante de Solicitação de Certificado ENEM'
    hoje = datetime.datetime.now()
    url_suap = settings.SITE_URL
    data_maxima_atendimento = obj.data_solicitacao + relativedelta(months=1)
    if obj.configuracao_certificado_enem.ano.ano <= 2013:
        return httprr('..', 'Não é possível imprimir o comprovante para solicitações de anos anteriores a 2014.', 'error')

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@rtr()
def solicitar_certificado_enem(request):
    title = 'Solicitar Certificado ENEM'
    category = 'Ensino'
    icon = 'certificate'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = SolicitarCertificadoENEMForm(request.POST or None, files=request.FILES or None)
    if form.is_valid():
        obj = form.processar()
        return httprr(
            f'/edu/comprovante_solicitacao_certificado_enem/{obj.codigo_geracao_solicitacao}',
            'A sua Solicitação foi realizada com sucesso e será analisada e o resultado será enviado para o seu email.',
        )

    return locals()


@rtr()
def consultar_andamento_certificado_enem(request):
    title = 'Consultar Andamento de Solicitação de Certificado ENEM'
    form = ConsultarAndamentoSolicitacaoCertificadoENEMForm(request.POST or None)
    if form.is_valid():
        obj = form.processar()
        if obj:
            is_avaliada = obj.avaliada
            is_anterior_2014 = obj.configuracao_certificado_enem.ano.ano > 2013
        else:
            is_avaliada = False
            is_anterior_2014 = False

    return locals()


@rtr()
def editar_dados_pessoais_solicitacao_enem(request, codigo_geracao_solicitacao):
    title = 'Editar meus Dados Pessoais - Solicitação de Certificado ENEM'
    solicitacao_enem = get_object_or_404(SolicitacaoCertificadoENEM, codigo_geracao_solicitacao=codigo_geracao_solicitacao)
    obj = solicitacao_enem.get_registro_aluno_inep()
    form = EditarDadosPessoaisSolicitacaoCertificadoENEM(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr(
            f'/edu/comprovante_solicitacao_certificado_enem/{solicitacao_enem.codigo_geracao_solicitacao}',
            'A sua Solicitação foi atualizada com sucesso.',
        )

    return locals()


@rtr()
@permission_required('edu.change_solicitacaocertificadoenem')
@login_required()
def atender_solicitacao_certificado_enem(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCertificadoENEM, pk=pk)
    try:
        solicitacao.atender(request.user)
        registro_emissao = solicitacao.get_registro_emissao_certificado_enem()
    except ValidationError as error:
        return httprr(f'/edu/solicitacao_certificado_enem/{solicitacao.pk}/', str(error), 'error')
    return httprr(f'/edu/registroemissaocertificadoenem/{registro_emissao.pk}/', 'Registro de emissão de Certificado ENEM cadastrado com sucesso.')


@rtr()
@permission_required('edu.change_solicitacaocertificadoenem')
@login_required()
def atender_com_ressalva_solicitacao_certificado_enem(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCertificadoENEM, pk=pk)
    form = AtenderComRessalvaSolicitacaoCertificadoENEMForm(data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            try:
                solicitacao.atender(request.user, request.POST['razao_ressalva'])
                return httprr(f'/edu/solicitacao_certificado_enem/{solicitacao.pk}/', 'Solicitação atendida com sucesso.')
            except ValidationError as error:
                return httprr(f'/edu/solicitacao_certificado_enem/{solicitacao.pk}/', str(error), 'error')
    return locals()


@rtr()
@permission_required('edu.change_solicitacaocertificadoenem')
def rejeitar_solicitacao_certificado_enem(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCertificadoENEM, pk=pk)
    form = RejeitarSolicitacaoCertificadoENEMForm(data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            try:
                solicitacao.rejeitar(request.user, request.POST['razao_indeferimento'])
                return httprr(f'/edu/solicitacao_certificado_enem/{solicitacao.pk}/', 'Solicitação rejeitada com sucesso.')
            except ValidationError as error:
                return httprr(f'/edu/solicitacao_certificado_enem/{solicitacao.pk}/', str(error), 'error')
    return locals()


@rtr()
@permission_required('edu.change_solicitacaocertificadoenem')
def replicar_solicitacao_certificado_enem(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCertificadoENEM, pk=pk)
    form = ReplicarSolicitacaoCertificadoENEMForm(data=request.POST or None, instance=solicitacao, request=request)
    if form.is_valid():
        try:
            replicada = form.save()
        except ValidationError as error:
            return httprr(
                f'/edu/solicitacao_certificado_enem/{pk}/', f'Ocorreu um erro ao replicar a solicitação de Certificado ENEM: {error.message}', 'error'
            )
        return httprr(f'/edu/solicitacao_certificado_enem/{replicada.pk}/', 'Solicitação replicada com sucesso.')
    return locals()


@rtr()
@login_required()
def registroemissaocertificadoenem(request, pk):
    title = 'Registro de Emissão de Certificado ENEM'
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    if 'email' in request.GET:
        obj.solicitacao.enviar_email(obj.solicitacao.avaliador)
        return httprr(f'/edu/registroemissaocertificadoenem/{pk}/', f'E-mail enviado para {obj.solicitacao.email}')
    hoje = datetime.datetime.now()
    return locals()


@rtr()
@permission_required('edu.change_registroemissaocertificadoenem')
@login_required()
def cancelar_registroemissaocertificadoenem(request, pk):
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    form = CancelarRegistroEmissaoCertificadoENEMForm(data=request.POST or None, instance=obj)
    if request.method == 'POST':
        if form.is_valid():
            obj.cancelar(request.user, request.POST['razao_cancelamento'])
            return httprr('..', 'Registro de emissão de Certificado ENEM cancelado com sucesso.')
    return locals()


@documento(enumerar_paginas=False)
@rtr('registroemissaocertificadoenem_pdf.html')
@login_required()
def registroemissaocertificadoenem_pdf(request: HttpRequest, pk: int) -> dict[str, Any]:
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    hoje = datetime.datetime.now()
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@documento('Certificado ENEM', modelo='edu.registroemissaocertificadoenem', exibe_emissor=True)
@rtr('imprimir_certificado_enem_pdf.html')
@login_required()
def imprimir_certificado_enem_pdf(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    hoje = datetime.datetime.now()

    # Verificando se o candidato é menor de idade.
    configuracao_enem = obj.solicitacao.configuracao_certificado_enem
    data_nascimento_candidato = obj.solicitacao.get_registro_aluno_inep().data_nascimento
    diferenca_em_anos = relativedelta(configuracao_enem.data_primeira_prova, data_nascimento_candidato).years
    is_menor_idade = diferenca_em_anos < 18

    if obj.solicitacao.configuracao_certificado_enem.ano.ano <= 2013:
        return httprr('..', 'Não é possível imprimir o certificado para solicitações de anos anteriores a 2014.', 'error')

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()

    return locals()


@rtr()
@login_required()
def escolher_reitor_diretor_geral(request, pk):
    title = 'Escolher Reitor e Diretor Geral para o Certificado ENEM'
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    uo = obj.solicitacao.uo

    diretoria = Diretoria.objects.filter(setor__uo=uo)
    if diretoria:
        diretoria = diretoria[0]
    else:
        return httprr('..', 'Diretoria inexistente', 'error')

    reitoria = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    initial = {
        'reitor': reitoria.get_diretor_geral(True) and reitoria.get_diretor_geral(True)[0].pk or None,
        'diretor_geral': diretoria.diretor_geral_id,
    }

    form = EscolherReitorDiretorGeralForm(diretoria.get_diretores_gerais(), data=request.POST or None, initial=initial)

    if form.is_valid():
        reitor = form.cleaned_data.get('reitor').pk
        diretor_geral = form.cleaned_data.get('diretor_geral').pk

        reitor_em_exercicio = form.initial['reitor'] != form.cleaned_data.get('reitor').pk
        diretor_geral_em_exercicio = form.initial['diretor_geral'] != form.cleaned_data.get('diretor_geral').pk

        return httprr(
            f'/edu/imprimir_certificado_enem_antes_2014_pdf/{pk}/?reitor={reitor}&reitor_em_exercicio={reitor_em_exercicio}&diretor_geral={diretor_geral}&diretor_geral_em_exercicio={diretor_geral_em_exercicio}'
        )
    return locals()


@documento(enumerar_paginas=False)
@rtr('imprimir_certificado_enem_antes_2014_pdf.html')
@login_required()
def imprimir_certificado_enem_antes_2014_pdf(request, pk):
    hoje = datetime.datetime.now()

    if not request.GET.get('reitor') or not request.GET.get('diretor_geral'):
        return httprr('..', 'Você precisa definir o Reitor e o Diretor Geral.', 'error')

    reitor = Servidor.objects.get(pk=request.GET.get('reitor'))
    diretor_geral = Vinculo.objects.get(pk=request.GET.get('diretor_geral')).relacionamento

    reitor_em_exercicio = request.GET.get('reitor_em_exercicio')
    diretor_geral_em_exercicio = request.GET.get('diretor_geral_em_exercicio')

    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    uo = obj.solicitacao.uo
    reitoria = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())

    cargo_diretor = 'Diretor{}-Geral {} - {}'.format(
        diretor_geral.sexo == 'F' and 'a' or '', diretor_geral_em_exercicio == 'True' and 'em Exercício' or '', normalizar(uo.nome)
    )
    cargo_reitor = 'Reitor{} {}'.format(reitor.sexo == 'F' and 'a' or '', reitor_em_exercicio == 'True' and 'em Exercício' or '')

    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

    return locals()


@documento('Certificado ENEM', modelo='edu.registroemissaocertificadoenem', exibe_emissor=True)
@rtr('imprimir_certificado_enem_pdf.html')
def gerar_certificado_enem_pdf(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, pk=pk)
    if obj.cancelado:
        return httprr(
            '/edu/solicitar_certificado_enem/',
            f'O certificado não pode ser gerado porque foi cancelado pelo servidor {obj.responsavel_cancelamento} pelo seguinte motivo: "{obj.razao_cancelamento}"',
            'error',
        )

    uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    hoje = datetime.datetime.now()
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


def gerar_certificado_enem(request, codigo_geracao_certificado):
    obj = get_object_or_404(RegistroEmissaoCertificadoENEM, codigo_geracao_certificado=codigo_geracao_certificado)
    return gerar_certificado_enem_pdf(request, pk=obj.pk)
