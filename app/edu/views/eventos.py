import datetime
import io
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from comum.models import Configuracao, RegistroEmissaoDocumento
from djtools.templatetags.filters import format_, normalizar
from djtools.utils import (
    XlsResponse,
    documento,
    gerar_documento_impressao,
    httprr,
    permission_required,
    rtr,
    send_mail,
)
from edu import tasks
from edu.forms import (
    AdicionarAlunosColacaoGrauForm,
    AdicionarParticipanteEventoForm,
    AlterarVinculoParticipanteEventoForm,
    DeferirColacaoGrauForm,
    EditarParticipanteEventoForm,
    ImportarParticipantesEventoForm,
    ModeloCertificadoEventoForm,
)
from edu.models import (
    Aluno,
    ColacaoGrau,
    CursoCampus,
    Evento,
    Modalidade,
    ParticipacaoColacaoGrau,
    ParticipanteEvento,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
)


@permission_required('edu.add_colacaograu')
@rtr()
def adicionar_alunos_colacao_grau(request, pk):
    title = 'Adicionar Aluno a Colação de Grau'
    colacao_grau = get_object_or_404(ColacaoGrau.objects, pk=pk)
    is_administrador = request.user.has_group_cached('Administrador Acadêmico') or request.user.has_group_cached('Organizador de Formatura')
    hoje = datetime.datetime.now().date()
    if not is_administrador:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = AdicionarAlunosColacaoGrauForm(request, colacao_grau=colacao_grau, data=request.GET or None)
    if form.is_valid():
        alunos = form.cleaned_data.get('alunos')
        return tasks.adicionar_aluno_colacao_grau(alunos.values_list('id', flat=True), pk)
    return locals()


@permission_required('edu.view_colacaograu')
@rtr()
def colacao_grau(request, pk):
    obj = get_object_or_404(ColacaoGrau.objects, pk=pk)
    title = str(obj)
    participacoes = obj.participacaocolacaograu_set.all()
    hoje = datetime.datetime.now().date()
    tem_aluno_com_diploma = RegistroEmissaoDiploma.objects.filter(aluno__participacaocolacaograu__colacao_grau_id=pk).exists()
    pode_deferir = request.user.has_perm('edu.add_colacaograu') and not obj.deferida
    is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    pode_cancelar_deferimento = is_administrador and obj.deferida and not tem_aluno_com_diploma
    cursos = CursoCampus.objects.filter(id__in=obj.participacaocolacaograu_set.values_list('aluno__curso_campus__id'))
    if 'curso_campus' in request.POST and request.POST['curso_campus'] != '0':
        participacoes = participacoes.filter(aluno__curso_campus__id=request.POST['curso_campus'])

    for curso in cursos:
        if 'curso_campus' in request.POST:
            if curso.pk == int(request.POST['curso_campus']):
                curso.selecionado = True
                break

    if 'xls' in request.GET:
        count = 0
        rows = [['#', 'Matrícula', 'Nome', 'Curso', 'I.R.A.']]

        for participacao in participacoes:
            count += 1
            row = [
                count,
                format_(participacao.aluno.matricula),
                format_(participacao.aluno.get_nome_social_composto()),
                format_(participacao.aluno.curso_campus),
                format_(participacao.aluno.get_ira()),
            ]
            rows.append(row)
        return XlsResponse(rows)

    if 'cancelar_deferimento' in request.GET and pode_cancelar_deferimento:
        obj.cancelar_deferimento()
        return httprr('.', 'Deferimento cancelado com sucesso.')

    if 'participacao_colacao_grau' in request.POST and pode_deferir:
        participacoes = ParticipacaoColacaoGrau.objects.filter(id__in=request.POST.getlist('participacao_colacao_grau'))
        for p in participacoes:
            p.aluno.situacao_id = SituacaoMatricula.MATRICULADO
            p.aluno.save()
            p.delete()
        return httprr('.', 'Aluno removido com sucesso.')

    qs_alunos_aptos = (
        Aluno.objects.filter(curso_campus__diretoria=obj.diretoria)
        .filter(
            matriz__isnull=False,
            situacao_id__in=[SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL],
            pendencia_colacao_grau=True,
        )
        .exclude(pendencia_tcc=True)
        .exclude(pendencia_ch_atividade_complementar=True)
        .exclude(pendencia_ch_tcc=True, pendencia_ch_pratica_profissional=True)
        .exclude(pendencia_ch_seminario=True)
        .exclude(pendencia_ch_eletiva=True)
        .exclude(pendencia_ch_optativa=True)
        .exclude(pendencia_ch_obrigatoria=True)
        .exclude(pendencia_pratica_profissional=True)
        .exclude(curso_campus__modalidade=Modalidade.FIC)
    )

    # tratamento de pendência do ENADE considerando a data da colação de grau.
    alunos_aptos = [aluno for aluno in qs_alunos_aptos if not aluno.pendencia_enade or aluno.cumpriu_enade(data_colacao_grau=obj.data_colacao)]

    return locals()


@permission_required('edu.add_colacaograu')
@rtr()
def deferir_colacao_grau(request, pk):
    title = 'Deferir Colação de Grau'
    obj = get_object_or_404(ColacaoGrau.objects, pk=pk)
    form = DeferirColacaoGrauForm(obj, data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Colação de grau deferida com sucesso.')
    return locals()


@permission_required('edu.view_colacaograu')
@documento()
@rtr()
def imprimir_lista_colacao_grau_pdf(request, pk):
    obj = get_object_or_404(ColacaoGrau.objects, pk=pk)
    is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    participacoes = obj.participacaocolacaograu_set.all()
    hoje = datetime.datetime.now().date()
    uo = obj.diretoria.setor.uo

    return locals()


@rtr()
@permission_required('edu.add_evento')
def evento(request, pk):
    obj = get_object_or_404(Evento, pk=pk)
    title = 'Palestra/Evento'
    if 'cpfs' in request.POST:
        for participante_evento_id in request.POST.getlist('cpfs'):
            ParticipanteEvento.objects.filter(id=participante_evento_id).delete()
    return locals()


@rtr()
@permission_required('edu.add_evento')
def adicionar_modelo_certificado_evento(request, pk, tipo):
    obj = get_object_or_404(Evento, pk=pk)
    title = f'Modelo do Certificado de {tipo}'
    form = ModeloCertificadoEventoForm(obj, tipo=tipo, files=request.FILES or None, data=request.POST or None)
    if request.POST and form.is_valid():
        form.processar()
        return httprr('..', 'Modelo de certificado adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_evento')
def adicionar_participante_evento(request, pk, tipo):
    obj = get_object_or_404(Evento, pk=pk)
    title = f'Adicionar {tipo} à Palestra/Evento'
    form = AdicionarParticipanteEventoForm(obj, tipo=tipo, data=request.POST or None)
    if request.POST and form.is_valid():
        form.processar()
        return httprr('..', f'{tipo} adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_evento')
def editar_participante_evento(request, pk):
    obj = get_object_or_404(ParticipanteEvento, pk=pk)
    title = 'Atualizar Participante de Palestra/Evento'
    if obj.participante.eh_aluno() or obj.participante.eh_prestador() or obj.participante.eh_servidor():
        return httprr('..', 'Não é possível editar este participante.', 'error')
    form = EditarParticipanteEventoForm(data=request.POST or None, instance=obj.participante.relacionamento)
    if request.POST and form.is_valid():
        form.save()
        return httprr('..', 'Participante atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_evento')
def alterar_vinculo_participante_evento(request, pk):
    obj = get_object_or_404(ParticipanteEvento, pk=pk)
    title = 'Alterar Vínculo do Participante de Palestra/Evento'
    form = AlterarVinculoParticipanteEventoForm(data=request.POST or None, instance=obj)
    if request.POST and form.is_valid():
        form.save()
        return httprr('..', 'Participante atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_evento')
def importar_participantes_evento(request, pk, tipo):
    obj = get_object_or_404(Evento, pk=pk)
    title = f'Importar {tipo}s para Palestra/Evento'

    if request.method == 'POST':
        form = ImportarParticipantesEventoForm(obj, data=request.POST or None, files=request.FILES or None, tipo=tipo)
        if form.is_valid():
            form.processar()
            return httprr(f'/edu/evento/{pk}/', f'{tipo}s adicionados com sucesso.')
    else:
        form = ImportarParticipantesEventoForm(obj, tipo=tipo)
    return locals()


@login_required()
def imprimir_certificado_participacao_evento(request, pk):
    participanteEvento = get_object_or_404(ParticipanteEvento, pk=pk)
    if request.user.has_perm('edu.add_evento') or participanteEvento.participante.pessoa.pessoafisica.cpf == request.user.get_profile().cpf:
        try:
            return imprimir_certificado(request, pk)
        except Exception as e:
            return httprr('..', str(e), 'error')
    return httprr('..', 'Você não tem permissão para realizar isso.', 'error')


def imprimir_certificado_participacao_evento_email(request, token):
    obj = get_object_or_404(ParticipanteEvento, token=token)
    try:
        return imprimir_certificado(request, obj.pk, True)
    except Exception as e:
        return httprr('/accounts/login/', str(e), 'error')


def imprimir_certificado(request, pk, is_anonimo=False):
    obj = get_object_or_404(ParticipanteEvento, pk=pk)
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

    qs_registro = RegistroEmissaoDocumento.objects.filter(tipo='Certificado de Participação em Evento', modelo_pk=pk)
    if qs_registro.exists():
        codigo = qs_registro[0].codigo_verificador
        hoje = qs_registro[0].data_emissao
    else:
        codigo = obj.token
        hoje = datetime.date.today()

    codigo_verificador = (
        'Documento emitido pelo SUAP. Para comprovar sua autenticidade, '
        'acesse {}/comum/autenticar_documento/ - '
        'Código de autenticação: {} - Tipo de Documento: Certificado de Participação em Evento - '
        'Data da emissão: {} '.format(settings.SITE_URL, codigo[0:7], hoje.strftime('%d/%m/%Y'))
    )

    if obj.tipo_participacao == ParticipanteEvento.PALESTRANTE:
        modelo_documento = obj.evento.modelo_certificado_palestrante
    elif obj.tipo_participacao == ParticipanteEvento.CONVIDADO:
        modelo_documento = obj.evento.modelo_certificado_convidado
    else:
        modelo_documento = obj.evento.modelo_certificado_participacao

    if modelo_documento.name == '':
        return httprr(f'/edu/evento/{obj.evento.pk}/', 'Modelo do certificado não cadastrado.', 'error')

    dicionario = {
        '#PARTICIPANTE#': normalizar(obj.participante.pessoa.pessoafisica.nome),
        '#CPF#': obj.participante.pessoa.pessoafisica.cpf,
        '#CAMPUS#': normalizar(obj.evento.uo.nome),
        '#CIDADE#': normalizar(obj.evento.uo.municipio.nome),
        '#UF#': obj.evento.uo.municipio.uf,
        '#DATA#': f'{hoje.day} de {meses[hoje.month - 1]} de {hoje.year}',
        '#CODIGOVERIFICADOR#': codigo_verificador,
    }
    if qs_registro.exists():
        registro = qs_registro[0]
    else:
        caminho_arquivo = gerar_documento_impressao(dicionario, io.BytesIO(modelo_documento.read()))
        if not caminho_arquivo:
            url = '..'
            if is_anonimo:
                url = '/'
            return httprr(url, 'Documento não encontrado.', 'error')
        nome_arquivo = caminho_arquivo.split('/')[-1]

        registro = RegistroEmissaoDocumento()
        registro.tipo = 'Certificado de Participação em Evento'
        registro.codigo_verificador = codigo
        registro.data_emissao = hoje
        registro.documento.save(nome_arquivo, ContentFile(open(caminho_arquivo, 'rb').read()))
        registro.data_validade = None
        registro.modelo_pk = pk
        registro.save()
        os.unlink(caminho_arquivo)

    content_type = registro.documento.name.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
    response = HttpResponse(registro.documento.read(), content_type=content_type)
    extensao = content_type == 'application/pdf' and 'pdf' or 'docx'
    response['Content-Disposition'] = f'attachment; filename=Certificado.{extensao}'
    return response


@permission_required('edu.add_evento')
def enviar_certificado_participacao_evento(request, evento_pk, pks):
    obj = get_object_or_404(Evento, pk=evento_pk)
    participantes_evento = ParticipanteEvento.objects.filter(pk__in=pks.split('_'))

    emails_nao_enviados = []
    for participante_evento in participantes_evento:
        if participante_evento.participante.email_notificacao:
            subject = f'CERTIFICADO DE PARTICIPAÇÃO - {obj.titulo}'
            body = """
                Caro(a) {},

                Para gerar o seu certificado de participação no "{}" clique no link abaixo:

                {}edu/imprimir_certificado_participacao_evento/{}/
            """.format(
                participante_evento.participante.pessoa.pessoafisica.nome,
                participante_evento.evento.titulo,
                Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica'),
                participante_evento.token,
            )
            to = {
                participante_evento.participante.email_pessoal.strip(),
                participante_evento.participante.email_notificacao.strip(),
            }
            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=False)
            except Exception:
                emails_nao_enviados.append(to)
    if emails_nao_enviados:
        return httprr(
            f'/edu/evento/{evento_pk}/',
            f'Os seguintes e-mails para os seguintes destinatários não puderam ser enviados: {emails_nao_enviados}',
            'error',
        )
    return httprr(f'/edu/evento/{evento_pk}/', 'Emails enviados com sucesso.')
