import datetime
import io

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from sentry_sdk import capture_exception

from comum.models import Configuracao
from djtools import forms, layout
from djtools.utils import (
    check_pdf,
    getattr_coalesce,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu import tasks
from edu.forms import (
    CancelarRegistroEmissaoDiplomaForm,
    EmitirCertificacaoParcialForm,
    EmitirDiplomaAlunoForm,
    EmitirDiplomaLoteForm,
    EmitirSegundaViaDiplomaForm,
    ImportarAutenticacaoSistecForm,
    ImprimirDiplomaForm,
    ImprimirRegistroDiplomaAlunoForm,
    IniciarSessaoAssinaturaEletronicaForm,
    IniciarSessaoAssinaturaEletronicaViaApiForm,
    IniciarSessaoAssinaturaSenhaForm,
    PublicaoDOURegistroEmissaoDiplomaForm,
    RegistroEmissaoDiplomaPublicForm,
    RevogarDiplomaForm,
)
from edu.models import (
    AssinaturaAtaEletronica,
    AssinaturaDigital,
    AssinaturaEletronica,
    HistoricoEscolarParcial,
    Modalidade,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
    SolicitacaoAssinaturaEletronica,
)
from djtools.signals import minhas_acoes
from .pdfs import gerar_autenticacao_diploma_pdf


@minhas_acoes.registrar_acao()
def minhas_acoes(request, data, datahora_inicio, datahora_fim):
    qs = RegistroEmissaoDiploma.objects.filter(emissor=request.user)

    if datahora_inicio:
        qs = qs.filter(data_expedicao__gte=datahora_inicio)
    if datahora_fim:
        qs = qs.filter(data_expedicao__lte=datahora_fim)
    for registro in qs.order_by('data_expedicao'):
        data.append(
            (
                'Ensino',
                'Emissão de Diploma',
                f'{registro} - {registro.aluno}',
                f'em {registro.data_expedicao.strftime("%d/%m/%Y")}',
                f'/edu/registroemissaodiploma/{registro.id}/',
            )
        )


@rtr()
@permission_required('edu.emitir_diploma')
def emitir_segunda_via_diploma(request, pk):
    title = 'Emitir Novo Registro de Diploma'
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    initial = {'autenticacao_sistec': obj.autenticacao_sistec}
    form = EmitirSegundaViaDiplomaForm(data=request.POST or None, request=request, initial=initial)
    form.fields['autenticacao_sistec'].widget = forms.HiddenInput()

    if form.is_valid():
        try:
            registro_emissao_dimploma = form.processar(obj)
            return httprr(
                f'/admin/edu/registroemissaodiploma/?id__in={registro_emissao_dimploma.pk}',
                f'{registro_emissao_dimploma.via}ª Via de diploma emitida com sucesso.',
            )
        except Exception as e:
            return httprr('/edu/emitir_diploma/', str(e), 'error')

    return locals()


@rtr()
@permission_required('edu.view_registroemissaodiploma')
def informar_dados_publicao_dou(request, pk):
    title = 'Informar Dados da Publicação no DOU'
    instance = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    form = PublicaoDOURegistroEmissaoDiplomaForm(data=request.POST or None, instance=instance)
    if form.is_valid():
        form.save()
        return httprr('..', 'Dados registrados com sucesso.')
    return locals()


@rtr()
@permission_required('edu.emitir_diploma')
def emitir_certificacao_parcial(request):
    title = 'Emitir certificação parcial'
    form = EmitirCertificacaoParcialForm(data=request.POST or None)
    if form.is_valid():
        try:
            id = form.processar()
            url = f'/admin/edu/registroemissaodiploma/?id__in={id}'
            return httprr(url, 'Registro de emissão de certificação parcial criado com sucesso.')
        except ValidationError as e:
            return httprr('/edu/emitir_certificacao_parcial/', e.message, 'error')
        except Exception as e:
            capture_exception(e)
    return locals()


@rtr()
@permission_required('edu.emitir_diploma')
def emitir_diploma(request):
    initial = {'aluno': request.GET.get('aluno')}
    form = EmitirDiplomaAlunoForm(data=request.POST or None, request=request, initial=initial)
    if form.is_valid():
        try:
            ids = form.processar()
            url = f'/admin/edu/registroemissaodiploma/?id__in={ids[0]}'
            return httprr(url, 'Registro de emissão de diploma cadastrado com sucesso.')
        except ValidationError as e:
            return httprr('/edu/emitir_diploma/', e.message, 'error')
        except Exception as e:
            capture_exception(e)
            return httprr('/edu/emitir_diploma/', str(e), 'error')

    aluno = form.cleaned_data.get('aluno')
    title = 'Emitir Diploma {}'.format(aluno and f' - {aluno}' or '')
    if aluno:
        if aluno.situacao_id in [SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO]:
            registros = aluno.get_registros_emissao_diploma(tipo=RegistroEmissaoDiploma.TIPO_CONCLUSAO_CURSO).order_by('via')
        elif aluno.integralizou_ensino_medio:
            registros = aluno.get_registros_emissao_diploma(tipo=RegistroEmissaoDiploma.TIPO_CONCLUSAO_ENSINO_MEDIO).order_by('via')
        else:
            registros = aluno.get_registros_emissao_diploma().order_by('via')

        if not aluno.requer_autenticacao_sistec_para_emissao_diploma:
            form.fields['autenticacao_sistec'].widget = forms.HiddenInput()

    return locals()


@rtr()
@permission_required('edu.emitir_diploma')
def emitir_diplomas(request):
    title = 'Emitir Diploma em Lote'
    form = EmitirDiplomaLoteForm(data=request.POST or None, request=request)
    if form.is_valid():
        try:
            ids = form.processar()
        except Exception as e:
            return httprr('/edu/emitir_diplomas/', str(e), 'error')
        return httprr(
            '/admin/edu/registroemissaodiploma/?id__in={}'.format(','.join(ids)), 'Registros de emissão de diploma cadastrados com sucesso.'
        )
    return locals()


@rtr()
def registroemissaodiploma_public(request):
    title = 'Registro de Diplomas'
    category = 'Ensino'
    icon = 'certificate'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = RegistroEmissaoDiplomaPublicForm(data=request.GET or None)
    registros = RegistroEmissaoDiploma.objects.none()
    if form.is_valid():
        registros = form.processar()
    return locals()


@rtr()
def diploma_digital(request, pk, codigo):
    title = f'Diploma Digital - {codigo}'
    category = 'Ensino'
    icon = 'certificate'
    try:
        obj = RegistroEmissaoDiploma.objects.get(pk=pk)
        if codigo != obj.get_assinatura_digital().get_codigo_validacao_xml_diploma():
            return httprr('/', 'Código inválido.', 'error')
    except RegistroEmissaoDiploma.DoesNotExist:
        return httprr('/', 'Este registro de emissão de diploma não existe.', 'error')
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    return locals()


@rtr()
@permission_required('edu.change_registroemissaodiploma')
def registroemissaodiploma(request, pk):
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    tipo_emissao = obj.is_certificacao_parcial() and 'certificação parcial' or 'diploma'
    title = f'Emissão de {tipo_emissao} - {obj.via}ª via'
    is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    is_diploma_digital = obj.is_digital()
    assinatura_digital = obj.get_assinatura_digital() if is_diploma_digital else None
    possui_inconsistencia_assinaturadigital = obj.assinaturadigital_set.count() > 1 if is_diploma_digital else False
    pode_forcar_sincronizacao = (
        request.user.is_superuser and assinatura_digital and not possui_inconsistencia_assinaturadigital and not obj.is_finalizado()
    )

    if 'registrar' in request.GET:
        obj.registrar()
        return httprr(f'/edu/registroemissaodiploma/{obj.pk}/', 'Diploma registrado com sucesso. As assinaturas do registro podem ser realizadas.')
    if 'excluir' in request.GET and not obj.data_registro:
        obj.delete()
        return httprr('..', 'Registro excluído com sucesso.')
    if 'sincronizar_assinatura' in request.GET and pode_forcar_sincronizacao:
        from edu.diploma_digital.rap import AssinadorDigital

        assinador = AssinadorDigital()
        assinador.sincronizar(assinatura_digital)
        return httprr(f'/edu/registroemissaodiploma/{obj.pk}/?tab=dados_assinatura_digital', 'Sincronização realizada com sucesso.')
    if 'restart_processing' in request.GET and is_administrador:
        from edu.diploma_digital.rap import AssinadorDigital

        assinador = AssinadorDigital()
        url = f'/edu/registroemissaodiploma/{obj.pk}/?tab=dados_assinatura_digital'
        resposta = assinador.reprocessar_documento(request.GET['restart_processing'])
        if resposta.get('documentId') == request.GET['restart_processing']:
            return httprr(url, 'Processamento reiniciado com sucesso')
        return httprr(url, resposta.get('error', {}).get('message', 'Ocorreu um erro ao se comunicar com o RAP.'), 'error')
    if 'restart_signatures' in request.GET and is_administrador:
        from edu.diploma_digital.rap import AssinadorDigital

        assinador = AssinadorDigital()
        url = f'/edu/registroemissaodiploma/{obj.pk}/?tab=dados_assinatura_digital'
        resposta = assinador.reprocessar_documento(request.GET['restart_signatures'], command='restart-signatures')
        if resposta.get('documentId') == request.GET['restart_signatures']:
            return httprr(url, 'Assinaturas reiniciadas com sucesso')
        return httprr(url, resposta.get('error', {}).get('message', 'Ocorreu um erro ao se comunicar com o RAP.'), 'error')
    if 'reprocessar_documento' in request.GET and request.user.is_superuser and obj.is_assinado_digitalmente():
        obj.get_assinatura_digital().reprocessar_documento_com_erro()
        return httprr(f'/edu/registroemissaodiploma/{obj.pk}/?tab=dados_assinatura_digital', 'Documento reprocessado com sucesso.')
    if 'enviar' in request.GET and (obj.is_eletronico() or obj.is_digital()):
        obj.enviar_por_email()
        return httprr('..', 'Diploma/Histórico enviados com sucesso.')

    uo = obj.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    return locals()


@rtr()
@permission_required('edu.change_registroemissaodiploma')
def cancelar_registroemissaodiploma(request, pk):
    title = 'Cancelar Registro de Emissão de Diploma'
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    form = CancelarRegistroEmissaoDiplomaForm(request.POST or None, instance=obj)
    if form.is_valid():
        try:
            form.processar()
            return httprr('..', 'Registro de emissão de diploma cancelado com sucesso.')
        except ValidationError as e:
            form.errors['__all__'] = [e.message]
    return locals()


@rtr()
@permission_required('edu.emitir_diploma')
def imprimir_diploma(request, pks):
    erros = []
    title = 'Gerar Diploma'
    objs = []
    if '_' in pks:
        objs = RegistroEmissaoDiploma.objects.filter(id__in=pks.split('_'))
        if objs.values_list('aluno__curso_campus__id', flat=True).distinct().count() > 1:
            erros.append('Não é possível gerar diploma/certificado para alunos de cursos diferentes.')

        if objs.values_list('tipo', flat=True).distinct().count() > 1:
            erros.append('Não é possível gerar diploma/certificado para tipos de registros diferentes.')

        if objs.values_list('aluno__situacao', flat=True).distinct().count() > 1:
            erros.append('Não é possível gerar diploma/certificado para alunos com situações diferentes.')

    else:
        objs = [get_object_or_404(RegistroEmissaoDiploma, pk=pks)]

    obj = objs[0]

    if obj.tipo == RegistroEmissaoDiploma.TIPO_CERTIFICACAO_PARCIAL:
        modalidade_id = obj.configuracao_certificacao_parcial.modalidade_certificacao_id
    else:
        modalidade_id = obj.aluno.curso_campus.modalidade_id
        # Alunos do integrado que ainda não concluíram só podem obter certificados do ensino médio
        if modalidade_id == Modalidade.INTEGRADO:
            if obj.aluno.situacao_id != SituacaoMatricula.CONCLUIDO:
                modalidade_id = Modalidade.ENSINO_MEDIO

    if not obj.data_registro:
        erros.append('É necessário realizar o registro do diploma.')

    if not obj.aluno.curso_campus.diretoria.diretor_geral:
        erros.append(f'É necessário definir o Diretor Geral do campus no cadastro da diretoria {obj.aluno.curso_campus.diretoria}.')

    if not obj.aluno.curso_campus.diretoria.diretor_academico:
        erros.append(f'É necessário definir o Diretor Acadêmico no cadastro da diretoria {obj.aluno.curso_campus.diretoria}.')

    if not obj.aluno.curso_campus.is_fic():
        if not obj.aluno.curso_campus.coordenador:
            erros.append(
                f'É necessário definir o Coordenador do curso "{obj.aluno.curso_campus.descricao}" no cadastro da diretoria {obj.aluno.curso_campus.diretoria}.'
            )

    if obj.aluno.curso_campus.modalidade_id in [
        Modalidade.LICENCIATURA,
        Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
        Modalidade.TECNOLOGIA,
        Modalidade.ENGENHARIA,
        Modalidade.ESPECIALIZACAO,
    ]:
        if obj.aluno.polo and not obj.aluno.polo.codigo_censup:
            erros.append(f'Código e-MEC do Polo "{obj.aluno.polo}" é obrigatório.')
        elif not obj.aluno.curso_campus.codigo_emec:
            erros.append('Código e-MEC do curso é obrigatório.')

    if erros:
        return httprr('..', ' '.join(erros), 'error')

    aluno_sica = bool('sica' in settings.INSTALLED_APPS and obj.aluno.historico_set.exists())
    form = ImprimirDiplomaForm(
        data=request.POST or None, request=request, diretoria=obj.aluno.curso_campus.diretoria, modalidade=modalidade_id, aluno_sica=aluno_sica
    )

    solicita_assinatura_diploma_cra = Configuracao.get_valor_por_chave('edu', 'solicita_assinatura_diploma_cra')
    solicita_assinatura_diploma_da = Configuracao.get_valor_por_chave('edu', 'solicita_assinatura_diploma_da')
    if obj.is_eletronico():
        if solicita_assinatura_diploma_cra:
            form.fields['coordenador_registro_academico'].required = True
        if solicita_assinatura_diploma_da and modalidade_id == Modalidade.FIC:
            form.fields['diretor_academico'].required = True

    if form.is_valid():
        reitor_exercicio = form.cleaned_data['reitor']
        reitor = form.reitor or reitor_exercicio
        reitor_protempore = form.cleaned_data['reitor_protempore']
        diretor_geral = form.cleaned_data['diretor_geral']
        diretor_geral_protempore = form.cleaned_data['diretor_geral_protempore']
        diretor_academico = form.cleaned_data['diretor_academico']
        diretor_ensino = form.cleaned_data['diretor_ensino']
        coordenador_registro_academico = form.cleaned_data['coordenador_registro_academico']
        modelo_documento = form.cleaned_data['modelo_documento']

        plural_diplomas = pluralize(len(objs))
        mensagem = f'Diploma{plural_diplomas} gerado{plural_diplomas} com sucesso.'
        is_assinatura_fisica = True
        if obj.is_eletronico() or obj.is_digital():
            mensagem = f'{mensagem} O envio será realizado por e-mail e disponibilizado no SUAP para o{plural_diplomas} aluno{plural_diplomas} após conclusão das assinaturas.'
            is_assinatura_fisica = False

        for obj in objs:
            if not is_assinatura_fisica:
                if obj.is_eletronico():  # certificados ICP EDU
                    if AssinaturaEletronica.objects.filter(registro_emissao_diploma=obj).exists():
                        messages.error(request, f'Registro {obj.pk} já possui assinatura digital realizada.')
                        continue
                    vinculos = []
                    if (
                        modalidade_id != Modalidade.FIC
                        and not obj.aluno.is_integralizado_fase_escolar()
                        and not obj.aluno.is_integralizado_cursando()
                    ):
                        vinculos.append(reitor_exercicio.get_vinculo())
                    vinculos.append(diretor_geral)
                    if solicita_assinatura_diploma_cra:
                        vinculos.append(coordenador_registro_academico.servidor.get_vinculo())
                    if solicita_assinatura_diploma_da and modalidade_id == Modalidade.FIC:
                        vinculos.append(diretor_academico)
                    assinatura_eletronica = AssinaturaEletronica.objects.create(
                        registro_emissao_diploma=obj,
                        reitor=reitor_exercicio,
                        reitor_protempore=reitor_protempore,
                        diretor_geral=diretor_geral,
                        diretor_geral_protempore=diretor_geral_protempore,
                        diretor_academico=diretor_academico,
                        diretor_ensino=diretor_ensino,
                        coordenador_registro_academico=coordenador_registro_academico,
                        modelo_documento=form.cleaned_data['modelo_documento'],
                    )
                    for vinculo in vinculos:
                        SolicitacaoAssinaturaEletronica.objects.create(assinatura_eletronica=assinatura_eletronica, vinculo=vinculo)
                    obj.situacao = RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DIPLOMA
                    obj.save()
                else:  # certificados ICP Brasil
                    if AssinaturaDigital.objects.filter(registro_emissao_diploma=obj).exists():
                        messages.error(request, f'Registro {obj.pk} já possui assinatura digital realizada.')
                        continue
                    registro_emissao_documento_diploma = gerar_autenticacao_diploma_pdf(request, pk=obj.pk)
                    AssinaturaDigital.objects.create(
                        registro_emissao_diploma=obj,
                        reitor=reitor_exercicio,
                        reitor_protempore=reitor_protempore,
                        diretor_geral=diretor_geral,
                        diretor_geral_protempore=diretor_geral_protempore,
                        diretor_academico=diretor_academico,
                        diretor_ensino=diretor_ensino,
                        coordenador_registro_academico=coordenador_registro_academico,
                        modelo_documento=form.cleaned_data['modelo_documento'],
                        registro_emissao_documento_diploma=registro_emissao_documento_diploma,
                    )
                    obj.situacao = RegistroEmissaoDiploma.AGUARDANDO_SINCRONIZACAO
                    obj.save()
            else:
                obj.situacao = RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_FISICA
                obj.save()

        if is_assinatura_fisica:
            return tasks.imprimir_diplomas_lote(
                request,
                objs,
                modelo_documento,
                reitor,
                reitor_exercicio,
                diretor_geral,
                diretor_academico,
                diretor_ensino,
                coordenador_registro_academico,
                reitor_protempore,
                diretor_geral_protempore,
            )
        else:
            return httprr('..', mensagem)
    return locals()


@rtr()
@login_required()
@permission_required('edu.efetuar_matricula')
def imprimir_registro_diploma_aluno(request):
    title = 'Selecione o Aluno'
    form = ImprimirRegistroDiplomaAlunoForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@group_required('Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor')
@rtr()
def iniciar_sessao_assinatura_eletronica(request):
    title = 'Iniciar Sessão de Assinatura Eletrônica'
    utilizar_api_icpedu = Configuracao.get_valor_por_chave('edu', 'utilizar_api_icpedu')
    if utilizar_api_icpedu:
        form = IniciarSessaoAssinaturaEletronicaViaApiForm(data=request.POST or None, request=request)
    else:
        form = IniciarSessaoAssinaturaEletronicaForm(data=request.POST or None, request=request)
    if form.is_valid():
        return httprr('/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario', 'Sessão de assinatura eletrônica iniciada com sucesso.')
    return locals()


@group_required('Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor')
def finalizar_sessao_assinatura_eletronica(request):
    if 'sessao_assinatura_eletronica' in request.session:
        del request.session['sessao_assinatura_eletronica']
        request.session.save()
    return httprr('/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario', 'Sessão de assinatura eletrônica finalizada com sucesso.')


@group_required('Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor')
@rtr()
def revogar_assinatura_eletronica(request, pk):
    title = 'Revogar Assinaturas Eletrônicas'
    form = RevogarDiplomaForm(data=request.POST or None, request=request)
    if form.is_valid():
        for assinatura_eletronica in AssinaturaEletronica.objects.filter(pk__in=pk.split('_')):
            assinatura_eletronica.revogar(form.cleaned_data['motivo'])
        return httprr('..', 'Assinaturas revogadas com sucesso.')
    return locals()


@group_required('Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor')
def assinar_diplomas_eletronicos(request, pk):
    qs = AssinaturaEletronica.objects.filter(pk__in=pk.split('_'), registro_emissao_diploma__cancelado=False)
    # recuperando antecipadamente a sessão de assinaturas para evitar que a sessão seja removida no meio
    # da geração em lote de diplomas, o que poderia ocasionar erro.
    id_certificado, senha_certificado = request.session.get('sessao_assinatura_eletronica', (None, None))
    if not id_certificado or not senha_certificado:
        return httprr('..', 'Sessão de assinatura expirada. Por favor inicie a sessão de assinaturas novamente.')
    erros_registros = []
    erros_historicos = []
    erros_diplomas = []
    pdf_invalido = False
    for assinatura in qs:
        if getattr_coalesce(assinatura, 'registro_emissao_documento_diploma.documento.name'):
            with assinatura.registro_emissao_documento_diploma.documento.open('rb') as f:
                content = f.read()
            if not check_pdf(io.BytesIO(content)):
                erros_registros.append(str(assinatura.registro_emissao_diploma.aluno))
                pdf_invalido = True

        if assinatura.registro_emissao_diploma.emite_historico() and getattr_coalesce(
            assinatura, 'registro_emissao_documento_historico.documento.name'
        ):
            with assinatura.registro_emissao_documento_historico.documento.open('rb') as f:
                content = f.read()
            if not check_pdf(io.BytesIO(content)):
                erros_historicos.append(str(assinatura.registro_emissao_diploma.aluno))
                pdf_invalido = True

        if getattr_coalesce(assinatura, 'diploma.name'):
            with assinatura.diploma.open('rb') as f:
                content = f.read()
            if not check_pdf(io.BytesIO(content)):
                erros_diplomas.append(str(assinatura.registro_emissao_diploma.aluno))
                pdf_invalido = True
    if pdf_invalido:
        if erros_registros:
            messages.error(request, f'Registro de Emissão de Diploma dos alunos {erros_registros} corrompidos.')
        if erros_historicos:
            messages.error(request, f'Histórico de Emissão de Diploma dos alunos {erros_historicos} corrompidos.')
        if erros_diplomas:
            messages.error(request, f'Diploma dos alunos {erros_diplomas} corrompidos.')
        return httprr('/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario', 'Erro ao tentar assinar o diploma.', 'error')
    return tasks.assinar_diplomas_eletronicos(request, qs, id_certificado, senha_certificado)


@login_required()
@rtr()
def assinar_ata_eletronica(request, pk):
    title = 'Assinar Ata Eletrônica'
    assinatura = get_object_or_404(AssinaturaAtaEletronica, pk=pk)
    if assinatura.vinculo.user != request.user:
        return HttpResponseForbidden()
    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        assinatura.assinar()
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@permission_required('edu.view_registroemissaodiploma')
def baixar_xml_documentacao_academica(request, pk, token=None):
    obj = get_object_or_404(AssinaturaDigital, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        arquivo = obj.baixar_xml_documentacao_academica()
        response = HttpResponse(arquivo, content_type='application/force-download')
        response['Content-Disposition'] = f'attachment; filename=documentacao_academica_{pk}.xml'
        return response
    except Exception as e:
        return httprr('..', str(e), 'error')


def baixar_xml_historico_escolar_parcial(request, pk, token):
    obj = get_object_or_404(HistoricoEscolarParcial, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        arquivo = obj.baixar_xml()
        response = HttpResponse(arquivo, content_type='application/force-download')
        response['Content-Disposition'] = f'attachment; filename=historico_escolar_parcial_{pk}.xml'
        return response
    except Exception as e:
        return httprr('..', str(e), 'error')


def baixar_xml_historico_escolar(request, pk, token=None):
    obj = get_object_or_404(AssinaturaDigital, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        arquivo = obj.baixar_xml_historico_escolar()
        response = HttpResponse(arquivo, content_type='application/force-download')
        response['Content-Disposition'] = f'attachment; filename=historico_escolar_{pk}.xml'
        return response
    except Exception as e:
        return httprr('..', str(e), 'error')


def baixar_xml_dados_diploma(request, pk, token=None):
    obj = get_object_or_404(AssinaturaDigital, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        arquivo = obj.baixar_xml_dados_diploma()
        response = HttpResponse(arquivo, content_type='application/force-download')
        response['Content-Disposition'] = f'attachment; filename=diploma_{pk}.xml'
        return response
    except Exception as e:
        return httprr('..', str(e), 'error')


@rtr()
def diplomas_digitais(request):
    title = 'Diplomas Digitais'
    return locals()


@rtr()
@login_required()
def consultar_status_assinaturas(request, pk):
    title = 'Situação das Assinaturas'
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    if obj.is_eletronico():
        assinatura = obj.get_assinatura_eletronica()
        if assinatura:
            return consultar_status_assinaturas_eletronicas(request, assinatura.pk)
    elif obj.aluno.curso_campus.assinatura_digital:
        assinatura = obj.get_assinatura_digital()
        if assinatura:
            return consultar_status_assinaturas_digitais(request, assinatura.pk)
    return locals()


@rtr()
@login_required()
def consultar_status_assinaturas_digitais(request, pk):
    title = 'Situação das Assinaturas'
    obj = get_object_or_404(AssinaturaDigital, pk=pk)
    try:
        dados = obj.consultar_status_assinaturas()
        return locals()
    except Exception as e:
        return httprr('..', str(e), 'error')


@rtr()
@login_required()
def consultar_status_assinaturas_eletronicas(request, pk):
    title = 'Situação das Assinaturas'
    obj = get_object_or_404(AssinaturaEletronica, pk=pk)
    solicitacoes_assinatura = obj.solicitacaoassinaturaeletronica_set.all()
    return locals()


@rtr()
@permission_required('edu.view_codigoautenticadorsistec')
def importar_autenticacao_sistec(request):
    title = 'Importar Autenticação SISTEC'
    form = ImportarAutenticacaoSistecForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        try:
            c = form.processar()
            return httprr('..', f'Importação de {c} código(s) realizada com sucesso')
        except Exception as e:
            if settings.DEBUG:
                raise e
        return httprr('..', 'Formato do formato inválido.', 'error')
    return locals()
