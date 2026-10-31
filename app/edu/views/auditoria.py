from django.apps import apps
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404

from djtools.history import log_view_object
from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu import utils
from edu.forms import (
    EditarAtendenteAuditoriaEnsinoForm,
    InformarCorrecaoAlunoSemSISTECForm,
    InformarCorrecaoNomeAlunoForm,
    InformarCorrecaoNomePaisForm,
    InformarCorrecaoReceitaFederalForm,
    InformarFonteDadosAuditoriaEnsinoForm,
    InformarSituacaoRegistroAuditoriaForm,
    RealizarAuditoriaForm,
    ResolverAuditoriaEnsinoForm,
    SolicitarAuditoriaEnsinoForm,
)
from edu.models import (
    Aluno,
    AuditoriaEnsino,
    CursoCampus,
    Diario,
    Diretoria,
    Encontro,
    Log,
    MaterialAula,
    RegistroAuditoriaEnsino,
    RegistroDiferenca,
    Modalidade,
)


@rtr()
@permission_required('edu.view_log')
def log(request, pk):
    title = f'Visualização do Log #{pk}'
    obj = get_object_or_404(Log, pk=pk)
    tipo = str(Log.TIPO_CHOICES[obj.tipo - 1][1])
    diff = RegistroDiferenca.objects.filter(log=obj)
    cls = apps.get_model(obj.app, obj.modelo)
    instancia = None
    qs = cls.objects.filter(pk=obj.ref)
    if qs.exists():
        instancia = qs[0]
        metadata = utils.metadata(instancia)
    return locals()


@permission_required('edu.view_log')
@rtr('logs.html')
def realizar_auditoria(request):
    title = 'Auditoria'
    form = RealizarAuditoriaForm(data=request.GET or None)
    pode_exportar_log = True

    if form.is_valid():
        logs = form.processar()

        if 'exportar' in request.GET:
            import pandas as pd

            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename=relatorio_de_logs.xlsx'

            data = []
            for log in logs:
                row = {}
                row['Id de Log'] = log.pk
                row['Data'] = f'{log.dt.day}/{log.dt.month}/{log.dt.year}'
                row['Usuário'] = log.user and f'{log.user.get_full_name()} ({log.user.username})' or '-'
                row['Diário'] = log.ref_diario or '-'
                aluno = Aluno.objects.filter(pk=log.ref_aluno).first() if log.ref_aluno else None
                row['Aluno'] = aluno and aluno.matricula or '-'
                row['Tipo'] = (
                    log.tipo == Log.CADASTRO and 'Cadastro' or log.tipo == Log.EDICAO and 'Edição' or log.tipo == Log.EXCLUSAO and 'Exclusão'
                )
                row['Modelo Alterado'] = log.nome_modelo
                row['Id. Modelo'] = log.ref
                obj = apps.get_model(log.app, log.modelo).objects.filter(pk=log.ref).first()
                row['Desc. Modelo'] = str(obj) if obj else ''

                if log.tipo in [Log.EDICAO, Log.EXCLUSAO]:
                    qs_diffs = RegistroDiferenca.objects.filter(log=log)
                    diffs = []
                    for diff in qs_diffs:
                        diffs.append('{}: {} para {}'.format(diff.campo, diff.valor_anterior, diff.valor_atual or '-'))
                    row['Dados Alterados'] = ', '.join(diffs)
                else:
                    row['Dados Alterados'] = '-'

                data.append(row)

            df = pd.DataFrame(data)
            df.to_excel(response, index=False)
            return response

    return locals()


@permission_required('edu.view_log')
@rtr('logs.html')
def log_diario(request, pk):
    qs_log = Log.objects.filter(ref_diario=pk) | Log.objects.filter(ref=pk, modelo='Diario')
    logs = qs_log.distinct().order_by('-id')
    title = f'Log do diário {pk}'
    return locals()


@permission_required('edu.view_log')
@rtr('logs.html')
def log_diario_especial(request, pk):
    encontros = Encontro.objects.filter(diario_especial_id=pk).values_list('pk', flat=True)
    qs_log = Log.objects.filter(ref=pk, modelo='DiarioEspecial') | Log.objects.filter(ref__in=encontros, modelo='Encontro')
    logs = qs_log.distinct().order_by('-id')
    title = f'Log do diário {pk}'
    return locals()


@permission_required('edu.view_log')
@rtr('logs.html')
def log_aluno(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    qs_log = Log.objects.filter(ref_aluno=pk) | Log.objects.filter(ref=pk, modelo='Aluno')
    qs_log = qs_log.distinct()
    logs = []
    for log in qs_log:
        logs.append({'pk': log.pk, 'user': log.user, 'dt': log.dt, 'descricao': log.descricao})
    for matricula_periodo in obj.matriculaperiodo_set.all():
        for hsmp in matricula_periodo.historicosituacaomatriculaperiodo_set.all():
            descricao = f'A matrícula período {matricula_periodo.ano_letivo.ano}.{matricula_periodo.periodo_letivo} foi atualizada para a situação "{hsmp.situacao!s}"'
            logs.append({'pk': None, 'user': hsmp.usuario, 'dt': hsmp.data, 'descricao': descricao})

    logs.sort(key=lambda x: x['dt'], reverse=True)
    title = str(obj)
    return locals()


@rtr()
@permission_required('edu.view_materialaula')
def registrar_acesso_aluno_material_aula(request, pk_diario, pk_materialaula):
    aluno = get_object_or_404(Aluno, vinculos__user=request.user)
    materialaula = get_object_or_404(MaterialAula, pk=pk_materialaula)
    diario = get_object_or_404(Diario, pk=pk_diario)
    descricao = f'O usuário visualizou o {materialaula._meta.verbose_name} #{materialaula.pk}'
    if settings.USE_HISTORY:
        log_view_object(materialaula)
    if settings.USE_EDU_LOG:
        log = Log()
        log.set_up(aluno.get_vinculo().user, Log.VISUALIZACAO, materialaula, descricao)
        log.ref_aluno = aluno.pk
        log.ref_diario = diario.pk
        log.save()
    return HttpResponseRedirect(materialaula.get_absolute_url())


@rtr()
@permission_required('edu.add_materialaula')
def log_acesso_material_aula(request, pk_diario, pk_materialaula):
    materialaula = get_object_or_404(MaterialAula, pk=pk_materialaula)
    title = f'{materialaula}'
    logs = Log.objects.filter(ref=pk_materialaula, modelo='MaterialAula', tipo=Log.VISUALIZACAO, ref_diario=pk_diario)
    return locals()


@rtr('logs.html')
@permission_required('edu.view_alunoarquivo')
def log_pasta_documental(request, pk):
    title = 'Alterações na Pasta Documental'
    logs = Log.objects.filter(ref_aluno=pk, modelo='AlunoArquivo').order_by('-pk')
    return locals()


@rtr('logs.html')
@permission_required('edu.view_convocacaoenade')
def log_situacao_enade(request, pk):
    title = 'Registro de Convocação ENADE'
    logs = Log.objects.filter(ref=pk, modelo='RegistroConvocacaoENADE')
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def solicitar_auditoria(request):
    title = 'Solicitar Auditoria'
    form = SolicitarAuditoriaEnsinoForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        result = form.processar()
        if result:
            return result
        return httprr('/admin/edu/auditoriaensino/', 'Auditoria solicitada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_auditoriaensino')
def resolver_auditoria(request, pk):
    title = 'Resolver Auditoria'
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    form = ResolverAuditoriaEnsinoForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.processar()
        return httprr(obj.get_absolute_url(), 'Auditoria resolvida com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def editar_atendente_auditoria(request, pk):
    title = 'Editar Atendente da Auditoria'
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    form = EditarAtendenteAuditoriaEnsinoForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.processar()
        return httprr(obj.get_absolute_url(), 'Atendente atualizado com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def auditoria(request, pk, acao):
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    if acao == 'gerar' and obj.pode_gerar(request.user):
        return obj.gerar(request.user)
    elif acao == 'desfazer' and obj.pode_desfazer(request.user):
        return obj.desfazer_auditoria_gerada(request.user)
    elif acao == 'atender' and obj.pode_atender(request.user):
        obj.atender(request.user)
        return httprr(obj.get_absolute_url(), 'Atendimento iniciado com sucesso.')
    elif acao == 'exportar' and obj.pode_exportar(request.user):
        return obj.exportar(request.user)
    elif acao == 'notificar_campus' and obj.pode_notificar_campus(request.user):
        obj.notificar_campus(request.user)
        return httprr(obj.get_absolute_url(), 'Notificação enviada com sucesso para o campus.')
    return httprr(obj.get_absolute_url(), f'Não foi possível {acao} esta auditoria.', 'error')


@rtr()
@permission_required('comum.is_administrador_academico')
def informar_fonte_dados_auditoria(request, pk):
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    title = 'Informar Fonte de Dados'
    form = InformarFonteDadosAuditoriaEnsinoForm(data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr(obj.get_absolute_url(), 'Auditoria salva com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.view_auditoriaensino')
def auditoria_ensino(request, pk):
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    title = f'Auditoria {obj.id} - {obj.get_tipo_auditoria_display()}'
    pendencia = obj.get_pendencia()

    pode_resolver = obj.pode_resolver(request.user)
    is_auditoria_sistec = obj.tipo_auditoria == AuditoriaEnsino.TIPO_SISTEC

    convergentes = [{'obj': registro, 'itens': registro.get_itens()} for registro in obj.get_registros_auditoria(divergente=False)]

    ignorados = [{'obj': registro, 'itens': registro.get_itens(), 'ignorado': True} for registro in obj.get_ignorados_auditorias_anteriores()]
    itens_ignorados = [registro['itens'] for registro in ignorados]

    registros_divergentes = [{'obj': registro, 'itens': registro.get_itens()} for registro in obj.get_registros_auditoria()]

    divergentes_nao_ignorados = []
    ignorados_auditoria_atual = []

    # divergentes_nao_ignorados = [linha for linha in registros_divergentes if linha['itens'] not in itens_ignorados]
    for linha in registros_divergentes:
        if linha['itens'] in itens_ignorados:
            ignorados_auditoria_atual.append(linha)
        else:
            divergentes_nao_ignorados.append(linha)

    if is_auditoria_sistec:
        divergentes = sorted(divergentes_nao_ignorados, key=lambda x: x['itens'][5])
    elif obj.tipo_auditoria == AuditoriaEnsino.TIPO_SITUACAO_MATRICULA:
        divergentes = sorted(divergentes_nao_ignorados, key=lambda x: x['itens'][4])
    else:
        divergentes = divergentes_nao_ignorados

    qtd_cursos_sem_sistec = 0
    qtd_fic_sem_sistec = 0
    if is_auditoria_sistec and request.user.has_perm('comum.is_administrador_academico'):
        qtd_cursos_sem_sistec = (
            CursoCampus.locals.filter(codigo_sistec='', ativo=True, diretoria__setor__uo_id=obj.campus_id)
            .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
            .exclude(modalidade_id=Modalidade.FIC_MENOS)
            .exclude(aluno__isnull=True)
            .count()
        )
        qtd_fic_sem_sistec = (
            CursoCampus.locals.filter(
                ch_total__gte=CursoCampus.CARGA_HORARIA_BASE_MINICURSO, codigo_sistec='', ativo=True, diretoria__setor__uo_id=obj.campus_id
            )
            .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
            .exclude(aluno__isnull=True)
            .count()
        )

    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def informar_correcao_registro_auditoria(request: HttpRequest, pk: int) -> HttpResponse | dict[str, object]:
    obj = get_object_or_404(RegistroAuditoriaEnsino, pk=pk)
    title = obj.get_resumo()
    matricula = obj.get_matricula()
    if not Aluno.objects.filter(matricula=matricula).exists():
        return httprr(
            obj.auditoria_ensino.get_absolute_url(),
            f'Não há aluno com a matrícula {matricula} no SUAP. Ignore o registro para concluir a auditoria.',
            'error',
            close_popup=True,
        )
    form = None
    if obj.auditoria_ensino.tipo_auditoria == AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC:
        form = InformarCorrecaoAlunoSemSISTECForm(data=request.POST or None, request=request, registro=obj)
    elif obj.auditoria_ensino.tipo_auditoria == AuditoriaEnsino.TIPO_RECEITA_FEDERAL:
        form = InformarCorrecaoReceitaFederalForm(data=request.POST or None, request=request, registro=obj)
    elif obj.auditoria_ensino.tipo_auditoria == AuditoriaEnsino.TIPO_NOME_PAIS:
        form = InformarCorrecaoNomePaisForm(data=request.POST or None, request=request, registro=obj)
    elif obj.auditoria_ensino.tipo_auditoria == AuditoriaEnsino.TIPO_NOME_ALUNO:
        form = InformarCorrecaoNomeAlunoForm(data=request.POST or None, request=request, registro=obj)

    if form and form.is_valid():
        form.processar(request.user)
        return httprr(obj.auditoria_ensino.get_absolute_url(), 'Situação atualizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def atualizar_situacao_registros_auditoria(request, pk):
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    if not obj.pode_resolver(request.user):
        return httprr(obj.get_absolute_url(), 'Você não tem permissão para isso.', 'error')
    if obj.tipo_auditoria == AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC:
        atualizados = obj.atualizar_situacao_registros(request.user)
        return httprr(obj.get_absolute_url(), f'{atualizados} registros atualizados com sucesso.')
    else:
        return httprr(obj.get_absolute_url(), 'Nenhuma ação realizada.', 'info')


@rtr()
@permission_required('edu.change_auditoriaensino')
def ignorar_registro_auditoria(request, pk):
    obj = get_object_or_404(RegistroAuditoriaEnsino, pk=pk)
    if obj.auditoria_ensino.pode_resolver(request.user):
        obj.situacao = RegistroAuditoriaEnsino.SITUACAO_IGNORADO
        obj.registrar_situacao(request.user)
        return httprr(obj.auditoria_ensino.get_absolute_url(), 'Situação atualizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def informar_situacao_registro_auditoria(request, pk):
    obj = get_object_or_404(RegistroAuditoriaEnsino, pk=pk)
    title = f'Registro de Auditoria {pk}'
    form = InformarSituacaoRegistroAuditoriaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.processar(request.user)
        return httprr(obj.auditoria_ensino.get_absolute_url(), 'Situação atualizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_auditoriaensino')
def informar_situacao_registro_auditoria_lote(request, pk, situacao, pks):
    obj = get_object_or_404(AuditoriaEnsino, pk=pk)
    if obj.pode_resolver(request.user):
        obj.registroauditoriaensino_set.filter(id__in=pks.split(',')).update(situacao=situacao)
        return httprr(obj.get_absolute_url(), 'Situação atualizada com sucesso.')
    else:
        return httprr(obj.get_absolute_url(), 'Você não tem permissão para isso.', 'error')
