import datetime
import io
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from sentry_sdk import capture_exception

from comum.models import APIExterna, Configuracao
from djtools import layout
from djtools.templatetags.filters import format_, normalizar
from djtools.utils import (
    breadcrumbs,
    gerar_documento_impressao,
    group_required,
    httprr,
    permission_required,
    rtr,
    send_mail,
)
from edu.forms import (
    AdicionarParticipanteTurmaMinicursoForm,
    AutenticarCertificadoMinicursoForm,
    ClonarMinicursoForm,
    EditarParticipanteTurmaMinicursoForm,
    ImportarParticipantesTurmaMinicursoForm,
    MonitorMinicursoForm,
    ProfessorMinicursoForm,
    TurmaMinicursoForm,
    VincularParticipanteSemTurmaMinicursoForm,
)
from edu.models import (
    Aluno,
    AtividadePraticaProfissional,
    Minicurso,
    ModeloDocumento,
    MonitorMinicurso,
    ParticipanteTurmaMinicurso,
    ProfessorMinicurso,
    TurmaMinicurso,
)
from edu.models.historico import MatriculaPeriodo
from rh.models import Servidor


@rtr()
@permission_required('edu.view_minicurso')
def minicurso(request, pk):
    manager = Minicurso.objects if request.user.has_perm('comum.is_operador_de_censo') else Minicurso.locals
    obj = get_object_or_404(manager, pk=pk)
    pode_realizar_acoes = Minicurso.locals.filter(pk=pk).exists()
    pode_clonar_curso = request.user.has_group_cached('Administrador Acadêmico', ignore_groups_if_superuser=False)
    title = f'{obj}'
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def clonar_minicurso(request, pk):
    title = 'Clonar Minicurso'
    obj = get_object_or_404(Minicurso, pk=pk)
    form = ClonarMinicursoForm(data=request.POST or None)
    if form.is_valid():
        ids = obj.clonar(form.cleaned_data['diretorias'])
        param = ','.join([str(id) for id in ids])
        return httprr(f'/admin/edu/minicurso/?id__in={param}', 'Cursos clonados com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_minicurso')
def criar_turma_minicurso(request, pk):
    obj = get_object_or_404(Minicurso, pk=pk)
    title = f'Criar uma nova Turma para o Minicurso {obj}'

    form = TurmaMinicursoForm(obj, data=request.POST or None)

    if request.method == 'POST':
        form = TurmaMinicursoForm(obj, data=request.POST or None, files=request.FILES or None)
        if form.is_valid():
            form.processar()
            return httprr(f'/edu/minicurso/{obj.pk}', 'Turma para o Minicurso criada com sucesso.')
    else:
        form = TurmaMinicursoForm(obj)

    return locals()


@rtr()
@permission_required('edu.view_turmaminicurso')
def turma_minicurso(request: HttpRequest, pk: int) -> dict[str, object] | HttpResponse:
    obj = get_object_or_404(TurmaMinicurso.objects, pk=pk)
    pode_realizar_acoes = Minicurso.locals.filter(pk=obj.minicurso_id).exists()
    if 'moodle' in request.GET and obj.integracao_com_moodle and pode_realizar_acoes:
        moodle = APIExterna.MOODLE.get_service()
        if not settings.DEBUG and not APIExterna.MOODLE.ativo:
            return httprr('.', 'A integração com o Moodle não está ativa temporariamente, tente mais tarde.', 'error')
        try:
            acao = request.GET['moodle']
            if acao == 'sincronizar':
                url = moodle.sincronizar_turma_minicurso(obj)
                obj.url_moodle = url
                obj.save()
                return httprr('.', f'Dados enviados com sucesso. A URL de acesso para o ambiente virtual é: {url}')
            elif acao == 'importar_notas':
                contador = moodle.importar_notas_turma_minicurso(obj, request.user.username)
                return httprr(f'/edu/turma_minicurso/{obj.pk}/?tab=participantes', f'Total de {contador} registro(s) importado(s) com sucesso.')
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)
            return httprr('.', f'Erro ao se comunicar com o Moodle: {e}', tag='error')
    title = f'Turma: {obj}'
    hoje = datetime.date.today()
    participantes = obj.participanteturmaminicurso_set.all().order_by('aluno__pessoa_fisica__nome', 'pk')
    possui_aluno_desvinculado = Aluno.objects.filter(curso_campus_id=obj.minicurso_id, participanteturmaminicurso__isnull=True).exists()
    return locals()


@rtr()
@permission_required('edu.view_turmaminicurso')
def vincular_participantes_sem_turma_minicurso(request, pk):
    obj = get_object_or_404(TurmaMinicurso.objects, pk=pk)
    if not Minicurso.locals.filter(pk=obj.minicurso_id).exists():
        return httprr(f'/edu/turma_minicurso/{pk}/', 'Você não tem permissão para executar este procedimento.', 'error')
    title = f'Vincular participantes à turma {obj}'
    form = VincularParticipanteSemTurmaMinicursoForm(data=request.POST or None, minicurso_id=obj.minicurso_id, turma_minicurso_id=pk)
    if request.POST and form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr(f'/edu/turma_minicurso/{pk}/', str(e), 'error')
        return httprr(f'/edu/turma_minicurso/{pk}/', 'Participante vinculado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_minicurso')
def editar_participante_turma_minicurso(request, pk):
    obj = get_object_or_404(ParticipanteTurmaMinicurso, pk=pk)
    if Servidor.objects.filter(pessoa_fisica_id=obj.aluno.pessoa_fisica_id).exists():
        return httprr('..', 'Não é possível editar os dados de participante Servidor.', 'error')
    title = f'Atualizar participante {obj.aluno.pessoa_fisica.cpf}'
    form = EditarParticipanteTurmaMinicursoForm(data=request.POST or None, instance=obj.aluno.pessoa_fisica)
    if request.POST and form.is_valid():
        form.processar()
        return httprr('..', 'Participante atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_minicurso')
def editar_professor_minicurso(request, turma_minicurso_pk, professor_minicurso_pk=None):
    turma_minicurso = get_object_or_404(TurmaMinicurso, pk=turma_minicurso_pk)
    title = f'Adicionar Professor a turma: {turma_minicurso}'
    professor_minicurso = None
    if professor_minicurso_pk:
        professor_minicurso = get_object_or_404(ProfessorMinicurso, pk=professor_minicurso_pk)
        title = 'Editar Professor'
    form = ProfessorMinicursoForm(
        data=request.POST or None,
        instance=professor_minicurso_pk and professor_minicurso or ProfessorMinicurso(turma_minicurso=turma_minicurso),
        request=request,
    )
    if request.POST and form.is_valid():
        form.save()
        return httprr('..', 'Professor atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_minicurso')
def editar_monitor_minicurso(request, turma_minicurso_pk, monitor_minicurso_pk=None):
    turma_minicurso = get_object_or_404(TurmaMinicurso, pk=turma_minicurso_pk)
    title = f'Adicionar Monitor a turma: {turma_minicurso}'
    monitor_minicurso = None
    if monitor_minicurso_pk:
        monitor_minicurso = get_object_or_404(MonitorMinicurso, pk=monitor_minicurso_pk)
        title = 'Editar Monitor'
    form = MonitorMinicursoForm(
        data=request.POST or None,
        instance=monitor_minicurso_pk and monitor_minicurso or MonitorMinicurso(turma_minicurso=turma_minicurso),
        request=request,
    )
    if request.POST and form.is_valid():
        form.save()
        return httprr('..', 'Monitor atualizado com sucesso.')
    return locals()


@rtr()
def autenticar_certificado_minicurso(request):
    title = 'Autenticação de Certificados de Minicurso'
    category = 'Ensino'
    icon = 'certificate'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = AutenticarCertificadoMinicursoForm(data=request.GET or None)
    if form.is_valid():
        obj, turma = form.processar()
        if not obj:
            return httprr('..', 'Aluno não encontrado.', 'error')
        turma_minicurso = obj.participanteturmaminicurso_set.first().turma
        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

        if request.GET.get('com_timbre') == '1':
            modelo_documento = ModeloDocumento.objects.get(descricao='Certificado MINICURSO [Papel Timbrado]', ativo=True).template
        else:
            modelo_documento = ModeloDocumento.objects.get(descricao='Certificado MINICURSO', ativo=True).template
        inicio = turma_minicurso.data_inicio
        inicio = f'{str(inicio.day).zfill(2)}/{str(inicio.month).zfill(2)}/{inicio.year}'
        fim = turma_minicurso.data_fim
        fim = f'{str(fim.day).zfill(2)}/{str(fim.month).zfill(2)}/{fim.year}'
        data = datetime.date.today()
        url_suap = settings.SITE_URL

        dicionario = {
            '#PARTICIPANTE#': normalizar(obj.pessoa_fisica.nome),
            '#CURSO#': turma_minicurso.minicurso.descricao_historico,
            '#INICIO#': inicio,
            '#FIM#': fim,
            '#DATA#': data.strftime('%d/%m/%Y'),
            '#CHTOTAL#': turma_minicurso.minicurso.ch_total,
            '#CPF#': obj.pessoa_fisica.cpf,
            '#NOMECAMPUS#': normalizar(turma_minicurso.minicurso.diretoria.setor.uo.nome),
            '#CIDADE#': normalizar(turma_minicurso.minicurso.diretoria.setor.uo.municipio.nome),
            '#UF#': turma_minicurso.minicurso.diretoria.setor.uo.municipio.uf,
            '#CODIGOVERIFICADOR#': f'Documento emitido pelo SUAP.\nPara comprovar sua autenticidade, entre com os dados:\nCPF: {obj.pessoa_fisica.cpf} \nData da conclusão: {fim}\nCódigo da turma: {str(turma.pk).zfill(5)}\nNa página {url_suap}/edu/autenticar_certificado_minicurso/  ',
        }
        try:
            caminho_arquivo = gerar_documento_impressao(dicionario, io.BytesIO(modelo_documento.read()))
        except Exception as e:
            return httprr('.', str(e), 'error')
        if not caminho_arquivo:
            return httprr('.', 'Documento não encontrado.', 'error')
        nome_arquivo = caminho_arquivo.split('/')[-1]
        arquivo = open(caminho_arquivo, 'rb')

        content_type = caminho_arquivo.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
        response = HttpResponse(arquivo.read(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        arquivo.close()
        os.unlink(caminho_arquivo)

        return response
    return locals()


@permission_required('edu.change_turmaminicurso')
def enviar_certificado_participacao_minicurso(request, turma_minicurso_pk, pks):
    obj = get_object_or_404(TurmaMinicurso, pk=turma_minicurso_pk)
    if obj.data_fim >= datetime.date.today():
        return httprr('..', 'Essa turma de minicurso não se encontra concluída.', 'error')
    participacoes = ParticipanteTurmaMinicurso.objects.filter(pk__in=pks.split('_'))

    for participacao in participacoes:
        aluno = participacao.aluno
        subject = f'CERTIFICADO DE PARTICIPAÇÃO - {obj.minicurso.descricao}'
        body = """
            Caro(a) {},

            Para gerar o seu certificado de participação no curso "{}" clique no link abaixo:

            {}edu/autenticar_certificado_minicurso/?cpf={}&data_conclusao={}&codigo_turma={}
        """.format(
            aluno.get_nome(),
            obj.minicurso,
            Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica'),
            aluno.pessoa_fisica.cpf,
            format_(obj.data_fim),
            turma_minicurso_pk,
        )
        from_email = settings.DEFAULT_FROM_EMAIL
        to = [aluno.email_notificacao]
        send_mail(subject, body, from_email, to)
    return httprr(request.META.get('HTTP_REFERER'), 'Email(s) enviado(s) com sucesso.')


@rtr()
@permission_required('edu.change_turmaminicurso')
def associar_atividadepraticaprofissional_participanteturmaminicurso(request, pk, aluno_id):
    participante = get_object_or_404(ParticipanteTurmaMinicurso.objects.select_related('turma__minicurso'), pk=pk)
    mp = (
        MatriculaPeriodo.objects.filter(
            aluno_id=aluno_id, ano_letivo_id=participante.turma.ano_letivo_id, periodo_letivo=participante.turma.periodo_letivo
        )
        .select_related('aluno')
        .only('id', 'aluno_id')
        .first()
    )
    url = breadcrumbs.breadcrumbs_current_url(request)
    if mp is None:
        return httprr(url, 'O ano/período letivo da turma não corresponde a um ano/período letivo de matrícula do aluno.', 'error')
    if not participante.turma.minicurso.tipo_curso_autoinstrucional:
        return httprr(url, 'O tipo de curso autoinstrucional não foi informado.', 'error')
    if not AtividadePraticaProfissional.pode_registrar(mp.aluno, int(participante.turma.minicurso.tipo_curso_autoinstrucional)):
        return httprr(url, 'O curso não permite o registro desta atividade de prática profissional.', 'error')

    AtividadePraticaProfissional.registrar_inicio_e_conclusao(
        int(participante.turma.minicurso.tipo_curso_autoinstrucional),
        participante.id,
        type(participante),
        mp.id,
        participante.turma.minicurso.ch_total,
        f'/edu/turma_minicurso/{participante.turma_id}/',
        f'Matrícula em {participante.turma.minicurso.descricao}',
        participante.nota,
    )

    return httprr(url, 'Atividade de prática profissional associada com sucesso.')


@rtr()
@permission_required('edu.change_turmaminicurso')
def adicionar_participante_turma_minicurso(request, pk):
    obj = get_object_or_404(TurmaMinicurso, pk=pk)
    title = 'Adicionar participante'
    form = AdicionarParticipanteTurmaMinicursoForm(obj, data=request.POST or None)
    if request.POST and form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('..', str(e), 'error')
        return httprr('..', 'Participante adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_turmaminicurso')
def aprovar_aluno_turma_minicurso(request, pks):
    pks = pks.split('_')
    alunos = ParticipanteTurmaMinicurso.objects.filter(pk__in=pks)
    if alunos:
        turma_minicurso = alunos[0].turma
        if turma_minicurso.data_fim > datetime.date.today():
            return httprr(
                turma_minicurso.get_absolute_url('tab=participantes'),
                f'Só será possível aprovar alunos desta turma a partir do dia {format_(turma_minicurso.data_fim)}, dia de fim desta turma.',
                'error',
            )
        turma_minicurso.aprovar(alunos)
        return httprr(turma_minicurso.get_absolute_url('tab=participantes'), 'Alunos aprovados com sucesso.')
    return httprr('..', 'Nenhum aluno selecionado.', 'error')


@rtr()
@permission_required('edu.change_turmaminicurso')
def reprovar_aluno_turma_minicurso(request, pks):
    pks = pks.split('_')
    alunos = ParticipanteTurmaMinicurso.objects.filter(pk__in=pks)
    if alunos:
        turma_minicurso = alunos[0].turma
        if turma_minicurso.data_fim > datetime.date.today():
            return httprr(
                turma_minicurso.get_absolute_url('tab=participantes'),
                f'Só será possível reprovar alunos desta turma a partir do dia {format_(turma_minicurso.data_fim)}, dia de fim desta turma.',
                'error',
            )
        turma_minicurso.reprovar(alunos)
        return httprr(turma_minicurso.get_absolute_url('tab=participantes'), 'Alunos reprovados com sucesso.')
    return httprr('..', 'Nenhum aluno selecionado.', 'error')


@rtr()
@permission_required('edu.change_turmaminicurso')
def importar_participantes_turma_minicurso(request, pk):
    obj = get_object_or_404(TurmaMinicurso, pk=pk)
    title = f'Importar participantes para turma do minicurso {obj.minicurso}'

    if request.method == 'POST':
        form = ImportarParticipantesTurmaMinicursoForm(obj, data=request.POST or None, files=request.FILES or None)
        if form.is_valid():
            try:
                form.processar()
                return httprr(f'/edu/turma_minicurso/{pk}/', 'Participantes adicionados com sucesso.', close_popup=True)
            except ValidationError as e:
                return httprr(f'/edu/turma_minicurso/{pk}/', str(e), 'error', close_popup=True)
    else:
        form = ImportarParticipantesTurmaMinicursoForm(obj)
    return locals()


@rtr()
@group_required('Professor')
def ver_alunos_turma_minicurso(request, pk):
    obj = get_object_or_404(TurmaMinicurso, pk=pk)
    title = f'Alunos Participantes da Turma {obj}'
    return locals()
