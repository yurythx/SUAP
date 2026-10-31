import datetime
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404

from comum.models import UsuarioGrupo
from edu.models import Log
from djtools.storages import get_temp_storage
from djtools.utils import (
    group_required,
    httprr,
    permission_required,
    rtr,
    send_notification,
)
from edu import tasks
from edu.forms import (
    ExecucaoPlanoLaboratorioForm,
    AlterarRespostaJustificativaCensupForm,
    AtualizarCodigoEducacensoForm,
    AuditoriaCensoForm,
    ClonarRegistroEducacensoForm,
    ImportarEducacensoEtapa2Form,
    IniciarAberturaExtemporaneaForm,
    PreencherRelatorioAlunosNaoExistentesNoSistecForm,
    PreencherRelatorioCensupForm,
    PreencherRelatorioSistecForm,
    AtualizarSistecAlunoForm,
    QuestaoEducacensoForm,
    RelatorioCensupForm,
    RelatorioEducacensoEtapa2Form,
    RelatorioEducacensoForm,
    RelatorioIsFForm,
    RelatorioSTTUForm,
    RespostaEducacensoFormFactory,
    RespostaJustificativaCensupForm,
    RespostaQuestaoEducacensoFormFactory,
    SolicitarAberturaExtemporaneaForm,
    SolicitarAberturaExtemporaneaAdministradorForm,
)
from edu.models import (
    AberturaExtemporanea,
    AlteracaoRespostaJustificativaCensup,
    Aluno,
    Diario,
    Diretoria,
    ExecucaoPlanoLaboratorio,
    JustificativaCensup,
    Laboratorio,
    NivelEnsino,
    RespostaEducacenso,
    RespostaJustificativaCensup,
)
from edu.models.censos import QuestaoEducacenso, RegistroEducacenso
from rh.models import UnidadeOrganizacional


@rtr()
@group_required('Administrador Acadêmico')
def relatorio_educacenso_alunos_sem_codigo(request):
    return tasks.exportar_alunos_sem_codigo_educacenso(datetime.date.today().year)


@rtr()
@group_required('Administrador Acadêmico')
def preencher_relatorio_censup(request):
    title = 'Preencher Relatório CENSUP'
    form = PreencherRelatorioCensupForm(request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        try:
            file_contents = form.cleaned_data['planilha'].file.read()
            tipo_relatorio = int(form.cleaned_data['tipo_relatorio'])
            tipo_busca = int(form.cleaned_data['tipo_busca'])
            coluna_busca = form.cleaned_data.get('coluna_busca') - 1
            coluna_salva = form.cleaned_data.get('coluna_salva') - 1
            return tasks.exportar_relatorio_censup_xls(file_contents, tipo_relatorio, coluna_busca, tipo_busca, coluna_salva)
        except Exception as e:
            if settings.DEBUG:
                raise e
            return httprr('.', 'Erro ao tentar ler arquivo.', 'error')
    return locals()


@rtr()
@permission_required('edu.change_registroeducacenso')
def atualizar_codigo_educacenso(request):
    title = 'Atualizar Código Educacenso'
    form = AtualizarCodigoEducacensoForm(request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def auditoria_censos(request):
    title = 'Auditoria Censos'
    form = AuditoriaCensoForm(data=request.POST or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('edu.view_log')
def preencher_relatorio_sistec(request):
    title = 'Auditoria SISTEC -> SUAP'
    form = PreencherRelatorioSistecForm(request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        try:
            planilha = form.cleaned_data['planilha']
            campus = form.cleaned_data['campus']
            storage = get_temp_storage()
            planilha_path = storage.open(planilha.name, 'w+b')
            planilha_path.write(planilha.file.read())
            planilha_path.close()
            return tasks.exportar_sistec_suap(planilha_path=planilha_path.name, campus=campus)
        except Exception as e:
            return httprr('.', str(e), 'error')
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def atualizar_codigo_sistec(request):
    title = 'Atualizar dados SISTEC de aluno'
    form = AtualizarSistecAlunoForm(request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        try:
            planilha = form.cleaned_data['planilha']
            sobrescrever = form.cleaned_data['sobrescrever']
            atualizar = form.cleaned_data['atualizar']
            atualizar_data_fim = form.cleaned_data.get('atualizar_data_fim', False)
            storage = get_temp_storage()
            planilha_path = storage.open(planilha.name, 'w+b')
            content = planilha.file.read()
            planilha_path.write(content)
            planilha_path.close()
            return tasks.atualizar_sistec_aluno(
                planilha_path=planilha_path.name,
                sobrescrever_codigo=sobrescrever,
                atualizar_data_inicio=atualizar,
                atualizar_data_fim=atualizar_data_fim,
            )
        except Exception as e:
            return httprr('.', str(e), 'error')
    return locals()


@rtr()
@permission_required('edu.view_log')
def preencher_relatorio_alunos_nao_existentes_sistec(request):
    title = 'Auditoria SUAP -> SISTEC'
    form = PreencherRelatorioAlunosNaoExistentesNoSistecForm(request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        try:
            planilha = form.cleaned_data['planilha']
            campus_selecionado = form.cleaned_data.get('campus')
            anos_selecionados = form.cleaned_data.get('ano_letivo')
            convenios_selecionados = form.cleaned_data.get('excluir_convenio')
            storage = get_temp_storage()
            planilha_path = storage.open(planilha.name, 'w+b')
            planilha_path.write(planilha.file.read())
            planilha_path.close()
            return tasks.exportar_relatorio_alunos_nao_existentes_sistec_xls(
                planilha_path.name, campus_selecionado, anos_selecionados, convenios_selecionados
            )
        except Exception:
            return httprr('.', 'Erro ao tentar ler arquivo.', 'error')
    return locals()


@rtr()
@group_required('Administrador Acadêmico, Secretário Acadêmico')
def relatorio_isf(request):
    title = 'Relatório Idiomas sem Fronteiras'
    form = RelatorioIsFForm(data=request.POST or None)
    if form.is_valid():
        ano_letivo, periodo_letivo = form.processar()
        qs_aluno = Aluno.objects.filter(curso_campus__modalidade__nivel_ensino__in=[NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO]).filter(
            matriculaperiodo__ano_letivo=ano_letivo, matriculaperiodo__periodo_letivo=periodo_letivo
        )
        return tasks.exportar_relatorio_isf_xls(qs_aluno)

    return locals()


@rtr()
@group_required('Administrador Acadêmico, Secretário Acadêmico, Auxiliar de Secretaria Acadêmica')
def relatorio_sttu(request):
    title = 'Relatório STTU'
    form = RelatorioSTTUForm(data=request.POST or None, request=request)
    if form.is_valid():
        qs = form.processar()
        return tasks.exportar_para_sttu(qs)

    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def relatorio_censup(request):
    title = 'Relatório CENSUP'
    form = RelatorioCensupForm(data=request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def relatorio_educacenso(request):
    title = 'Relatório Educacenso'
    form = RelatorioEducacensoForm(data=request.POST or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def relatorio_educacenso_etapa_2(request):
    title = 'Relatório Educacenso Etapa 2'
    form = RelatorioEducacensoEtapa2Form(data=request.POST or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('edu.change_registroeducacenso')
def importar_educacenso_etapa_2(request):
    title = 'Importação Educacenso Etapa 2'
    form = ImportarEducacensoEtapa2Form(data=request.POST or None, request=request, files=request.POST and request.FILES or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('edu.view_registroeducacenso')
def registroeducacenso(request, pk):
    obj = get_object_or_404(RegistroEducacenso, pk=pk)
    title = str(obj)
    questoes = obj.questaoeducacenso_set.all()
    qtd_questoes = obj.questaoeducacenso_set.count()
    campi = UnidadeOrganizacional.objects.campi().values('sigla', 'nome')
    campus_selecionado = campi.filter(sigla=request.GET.get('campus')).first()
    if not campus_selecionado:
        campus_selecionado = campi.first()
    respostas = obj.get_respostas_por_campus(sigla_campus=campus_selecionado['sigla'])
    return locals()


@rtr()
@permission_required('edu.add_registroeducacenso')
def clonar_registroeducacenso(request):
    title = 'Clonar Questionário'
    form = ClonarRegistroEducacensoForm(data=request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('edu.add_questaoeducacenso')
def adicionar_questaoeducacenso(request, pk_registroeducacenso, pk_clone=None):
    title = 'Adicionar Campo ao Questionário Educacenso'
    if pk_clone:
        clone = get_object_or_404(QuestaoEducacenso, pk=pk_clone)

    form = QuestaoEducacensoForm(data=request.POST or None, registro=pk_registroeducacenso, clone=pk_clone and clone or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('edu.change_questaoeducacenso')
def responder_questionarioeducacenso(request, pk_registroeducacenso):
    obj = get_object_or_404(RegistroEducacenso, pk=pk_registroeducacenso)
    title = f'Responder Questionário Educacenso (Campus {request.user.get_vinculo().setor.uo.sigla})'
    if obj.privado or (not obj.privado and obj.data_limite and obj.data_limite < datetime.datetime.today().date()):
        if not obj.privado:
            obj.fechar()
        return httprr(
            f'{obj.get_absolute_url()}',
            f'Questionário não está mais disponível para respostas, a data limite foi até {obj.data_limite.strftime("%d/%m/%Y")}',
            'error',
        )
    # Atualiza a situação de todas as questões para edição
    obj.get_questoes_para_resposta(request.user.get_vinculo().setor.uo.id).update(situacao=RespostaEducacenso.SITUACAO_EDICAO)
    Form = RespostaEducacensoFormFactory(request, pk_registroeducacenso, request.user.get_vinculo().setor.uo.id)
    if request.method == 'POST':
        form = Form(data=request.POST)
        if form.is_valid():
            if 'salvar_concluir' in request.POST:
                form.save(concluir=True)
            else:
                form.save()
            return httprr(f'{obj.get_absolute_url()}', 'Ação realizada com sucesso.')
    else:
        form = Form()
    return locals()


@rtr()
@permission_required('edu.add_questaoeducacenso')
def responder_questionarioeducacenso_campus(request, pk_registroeducacenso, campus):
    obj = get_object_or_404(RegistroEducacenso, pk=pk_registroeducacenso)
    uo = UnidadeOrganizacional.objects.campi().get(sigla=campus)
    title = f'Responder Questionário Educacenso ({campus})'
    Form = RespostaEducacensoFormFactory(request, pk_registroeducacenso, uo.id)
    if request.method == 'POST':
        form = Form(data=request.POST)
        if form.is_valid():
            form.save()
            return httprr(f'{obj.get_absolute_url()}', 'Ação realizada com sucesso.')
    else:
        form = Form()
    return locals()


@rtr()
@permission_required('edu.change_respostaeducacenso')
def editar_resposta_questionarioeducacenso(request, pk_resposta):
    obj = get_object_or_404(RespostaEducacenso, pk=pk_resposta)
    title = f'Editar Resposta - {obj.questao} (Campus {obj.campus})'
    Form = RespostaQuestaoEducacensoFormFactory(request, pk_questao=obj.questao.pk, pk_campus=obj.campus.pk)
    if request.method == 'POST':
        form = Form(data=request.POST)
        if form.is_valid():
            form.save()
            return httprr('..', 'Ação realizada com sucesso.')
    else:
        form = Form()
    return locals()


@rtr()
@permission_required('edu.add_questaoeducacenso')
def publicar_questaoeducacenso(request, pk_registroeducacenso, publicar):
    obj = get_object_or_404(RegistroEducacenso, pk=pk_registroeducacenso)
    if not obj.data_limite:
        return httprr(f'{obj.get_absolute_url()}', 'É necessário definir a data limite para respostas do Registro Educacenso', tag='warning')
    if int(publicar):
        obj.publicar()
        qs_usuario_grupo = UsuarioGrupo.objects.filter(group__name='Secretário Acadêmico').select_related('user').distinct()
        secretarios = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
        titulo = '[SUAP] Questionário Educacenso foi publicado para respostas dos Campi'
        texto = (
            '<h2>Questionário Educacenso foi publicado para respostas dos Campi</h2>'
            f'<p>O questionário ficará aberto para respostas até {obj.data_limite.strftime("%d/%m/%Y")}.</p>'
            f'<p>Acesse {settings.SITE_URL}/admin/edu/registroeducacenso/ para visualizar todos os questionários.</p>'
        )

        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, secretarios, fail_silently=True)
    else:
        obj.fechar()
    return httprr(f'{obj.get_absolute_url()}', 'Ação realizada com sucesso.')


@rtr()
@permission_required('edu.add_questaoeducacenso')
def responder_questaoeducacenso(request, pk):
    obj = get_object_or_404(QuestaoEducacenso, pk=pk)
    title = f'Responder para Todos os Campi - {obj}'
    Form = RespostaQuestaoEducacensoFormFactory(request, pk)
    if request.method == 'POST':
        form = Form(data=request.POST)
        if form.is_valid():
            form.save()
            return httprr(f'{obj.registro.get_absolute_url()}', 'Ação realizada com sucesso.')
    else:
        form = Form()
    return locals()


@rtr('logs.html')
@permission_required('edu.view_respostaeducacenso')
def log_resposta_educacenso(request, pk):
    title = 'Alterações na Resposta Educacenso'
    logs = Log.objects.filter(ref=pk, modelo='RespostaEducacenso').order_by('-pk')
    return locals()


@rtr()
@permission_required('edu.add_aberturaextemporanea')
def solicitar_abertura_extemporanea(request):
    title = 'Solicitar abertura extemporânea'
    form = SolicitarAberturaExtemporaneaForm(data=request.POST or None, request=request)
    if form.is_valid():
        form.processar(request.user)
        return httprr('/admin/edu/aberturaextemporanea/', 'Abertura extemporânea solicitada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_aberturaextemporanea')
def solicitar_abertura_extemporanea_administrador(request):
    title = 'Solicitar abertura extemporânea para múltiplos campi'
    form = SolicitarAberturaExtemporaneaAdministradorForm(data=request.POST or None, request=request)
    if form.is_valid():
        form.processar(request.user)
        return httprr('/admin/edu/aberturaextemporanea/', 'Abertura extemporânea solicitada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_aberturaextemporanea')
def abertura_extemporanea(request, pk):
    title = f'Abertura Extemporânea {pk}'
    obj = AberturaExtemporanea.objects.filter(pk=pk).first()
    return locals()


@rtr()
@permission_required('edu.change_aberturaextemporanea')
def iniciar_abertura_extemporanea(request, pk):
    title = 'Iniciar Abertura Extemporânea'
    obj = AberturaExtemporanea.objects.filter(pk=pk).first()
    form = IniciarAberturaExtemporaneaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.processar(request.user)
        return httprr('/admin/edu/aberturaextemporanea/', 'Abertura extemporânea solicitada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.view_justificativacensup')
def justificativacensup(request, pk):
    obj = JustificativaCensup.objects.get(pk=pk)
    title = obj
    total = obj.respostajustificativacensup_set.count()
    total_respondido = obj.respostajustificativacensup_set.filter(resposta__isnull=False).count()
    percentual_respondido = round(total_respondido * 100.0 / float(total), 2)
    diretorias = Diretoria.objects.filter(
        id__in=obj.respostajustificativacensup_set.values_list('aluno__curso_campus__diretoria_id', flat=True).distinct()
    )
    for diretoria in diretorias:
        diretoria.justificativas = obj.respostajustificativacensup_set.filter(aluno__curso_campus__diretoria_id=diretoria.pk).count()
        diretoria.respondidas = obj.respostajustificativacensup_set.filter(
            aluno__curso_campus__diretoria_id=diretoria.pk, resposta__isnull=False
        ).count()
        diretoria.percentual_respondido = round(diretoria.respondidas * 100.0 / float(diretoria.justificativas), 2)
    return locals()


@rtr()
@permission_required('edu.change_respostajustificativacensup')
def respostajustificativacensup(request, pk):
    title = 'Resposta de Justificativa CENSUP'
    obj = RespostaJustificativaCensup.objects.get(pk=pk)
    form = RespostaJustificativaCensupForm(data=request.POST or None, request=request, instance=obj)
    pode_solicitar_alteracao_resposta = obj.pode_solicitar_alteracao_resposta(request.user)
    pode_avaliar_solicitacao = obj.pode_avaliar_solicitacao(request.user)
    solicitacoes_alteracao = obj.alteracaorespostajustificativacensup_set.filter(deferido__isnull=True)
    tem_alteracao_solicitada = solicitacoes_alteracao.exists()
    if form.is_valid():
        form.processar(request.user)
        return httprr('..', 'Resposta salva com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_respostajustificativacensup')
def solicitar_alteracao_resposta(request, pk):
    title = 'Solicitação de Alteração de Resposta de Justificativa CENSUP'
    resposta_justificativa_censup = RespostaJustificativaCensup.objects.get(pk=pk)
    form = AlterarRespostaJustificativaCensupForm(
        data=request.POST or None, request=request, resposta_justificativa_censup=resposta_justificativa_censup
    )
    if form.is_valid():
        form.processar(request.user)
        return httprr(resposta_justificativa_censup.get_absolute_url(), 'Solicitação realizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.delete_respostajustificativacensup')
def avaliar_solicitacao_alteracao_resposta(request, pk, deferido):
    obj = AlteracaoRespostaJustificativaCensup.objects.get(pk=pk)
    obj.deferido = deferido
    obj.avaliar()
    return httprr(
        obj.resposta_justificativa_censup.get_absolute_url(),
        'Solicitação avaliada com sucesso.',
    )


@permission_required('edu.view_laboratorio')
@rtr()
def laboratorio(request, pk):
    obj = get_object_or_404(Laboratorio, pk=pk)
    title = obj.nome
    planos = obj.execucaoplanolaboratorio_set.order_by('-ano__ano')
    diarios = (
        Diario.objects.filter(Q(local_laboratorio=obj.sala_id) | Q(local_aula_id=obj.sala_id) | Q(locais_aula_secundarios=obj.sala_id))
        .order_by('-ano_letivo__ano', '-periodo_letivo')
        .distinct()
    )
    return locals()


@permission_required('edu.change_laboratorio')
@rtr()
def adicionar_execucaoplano(request, pk):
    title = 'Adicionar execução de planos'
    form = ExecucaoPlanoLaboratorioForm(data=request.POST or None, files=request.FILES or None, request=request, laboratorio_id=pk)
    if form.is_valid():
        form.save()
        return httprr('.', 'Operação realizada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.change_laboratorio')
@rtr()
def editar_execucaoplano(request, pk):
    obj = get_object_or_404(ExecucaoPlanoLaboratorio, pk=pk)
    title = f'Editar execução de planos {obj.ano.ano}'
    form = ExecucaoPlanoLaboratorioForm(data=request.POST or None, files=request.FILES or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('.', 'Operação realizada com sucesso.', close_popup=True)
    return locals()
