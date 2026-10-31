import calendar
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from djtools import layout
from djtools.utils import httprr, rtr
from edu.forms import RejeitarSolicitacaoUsuarioForm
from edu.models import Aluno
from etep import perms, tasks
from etep.forms import (
    AdicionarEncaminhamentosForm,
    DocumentoForm,
    InteressadosForm,
    NotificarInteressadosForm,
    DesvincularInteressadosForm,
    RegistroAcompanhamentoForm,
    RelatorioAcompanhamentoForm,
    SituacaoAcompanhamentoForm,
)
from etep.models import (
    Acompanhamento,
    Atividade,
    Documento,
    Encaminhamento,
    Interessado,
    RegistroAcompanhamento,
    RegistroAcompanhamentoInteressado,
    RegistroInteressado,
    SolicitacaoAcompanhamento,
)


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    usuario = request.user
    if usuario.has_group_cached('Interessado ETEP'):
        vinculo = usuario.get_vinculo()
        ciencias_pendentes = RegistroAcompanhamento.locals.ciencia_pendente(vinculo).count()
        if ciencias_pendentes:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(ciencias_pendentes, "ão,ões")} de Acompanhamento',
                    'subtitulo': 'aguardando sua ciência',
                    'qtd': ciencias_pendentes,
                    'url': '/etep/registros_ciencia_pendente/',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_group_cached(['Pedagogo', 'Membro ETEP'], ignore_groups_if_superuser=False):
        solicitacoes_pendentes = SolicitacaoAcompanhamento.locals.filter(data_avaliacao__isnull=True).count()
        if solicitacoes_pendentes:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(solicitacoes_pendentes, "ão,ões")} de Acompanhamento',
                    'subtitulo': 'a avaliar',
                    'qtd': solicitacoes_pendentes,
                    'url': '/admin/etep/solicitacaoacompanhamento/?tab=tab_pendentes',
                }
            )

    return pendencias


@layout.quadro('ETEP', icone='pencil-alt')
def index_quadros(quadro, request):
    if request.user.has_group_cached(['Pedagogo', 'Membro ETEP'], ignore_groups_if_superuser=False):
        solicitacoes_em_acompanhamento = SolicitacaoAcompanhamento.locals.em_acompanhamento().count()
        if solicitacoes_em_acompanhamento:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Solicitações',
                    subtitulo='Em acompanhamento',
                    qtd=solicitacoes_em_acompanhamento,
                    url='/admin/etep/solicitacaoacompanhamento/?tab=tab_em_acompanhamento',
                )
            )

        acompanhamentos_prioritarios = Acompanhamento.locals.prioritarios().count()
        if acompanhamentos_prioritarios:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Acompanhamentos',
                    subtitulo='Prioritários',
                    qtd=acompanhamentos_prioritarios,
                    url='/admin/etep/acompanhamento/?tab=tab_acompanhamento_prioritario',
                )
            )

        acompanhamentos_regulares = Acompanhamento.locals.em_acompanhamento().count()
        if acompanhamentos_regulares:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Acompanhamentos',
                    subtitulo='Regulares',
                    qtd=acompanhamentos_regulares,
                    url='/admin/etep/acompanhamento/?tab=tab_em_acompanhamento',
                )
            )

        hoje = datetime.now()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana = inicio_semana + timedelta(days=6)
        inicio_mes = hoje - timedelta(days=hoje.day - 1)
        dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
        fim_mes = datetime(hoje.year, hoje.month, dias_mes)

        setor = request.user.get_vinculo().setor
        if setor:
            qs_atividade = Atividade.locals.filter(usuario__vinculo__setor__uo=setor.uo).order_by('data_inicio_atividade')
            atividade_etep_hoje = qs_atividade.filter(data_inicio_atividade__date=hoje)
            for atividade in atividade_etep_hoje:
                quadro.add_item(
                    layout.ItemGrupo(grupo='Hoje', titulo=f'{atividade.data_inicio_atividade} - {atividade.titulo}', url=atividade.get_absolute_url())
                )

            atividade_etep_semana = qs_atividade.filter(data_inicio_atividade__gte=inicio_semana, data_inicio_atividade__lte=fim_semana)
            for atividade in atividade_etep_semana:
                quadro.add_item(
                    layout.ItemGrupo(
                        grupo='Esta Semana', titulo=f'{atividade.data_inicio_atividade} - {atividade.titulo}', url=atividade.get_absolute_url()
                    )
                )

            atividade_etep_mes = qs_atividade.filter(data_inicio_atividade__gte=inicio_mes, data_inicio_atividade__lte=fim_mes)
            for atividade in atividade_etep_mes:
                quadro.add_item(
                    layout.ItemGrupo(
                        grupo='Este Mês', titulo=f'{atividade.data_inicio_atividade} - {atividade.titulo}', url=atividade.get_absolute_url()
                    )
                )

    return quadro


@login_required
@rtr()
def acompanhamento(request, acompanhamento_pk):
    obj = get_object_or_404(Acompanhamento.locals, pk=acompanhamento_pk)
    title = str(obj)
    encaminhamentos = obj.acompanhamentoencaminhamento_set.all()
    if not perms.pode_ver_etep(request, obj):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    registros_acompanhamentos = RegistroAcompanhamento.locals.filter(acompanhamento=obj)
    registros = registros_acompanhamentos.filter(descricao__isnull=False)
    anexos = registros_acompanhamentos.exclude(anexo='')
    interessados = Interessado.locals.ativos().filter(acompanhamento=obj)
    registros_interessados = RegistroInteressado.objects.filter(interessado__acompanhamento=obj)
    usuario_interessado = interessados.filter(vinculo__user=request.user)
    solicitacoes = obj.solicitacaoacompanhamento_set.all()
    lista_acompanhamento = []
    setor = obj.aluno.curso_campus.diretoria.setor
    tem_permissao_realizar_procedimentos_etep = perms.tem_permissao_realizar_procedimentos_etep(request, setor)
    tem_permissao_completa = request.user.has_group_cached('etep Administrador') or request.user.is_superuser
    pode_apagar = True
    existe_encaminhamento = Encaminhamento.objects.exclude(
        id__in=obj.acompanhamentoencaminhamento_set.values_list('encaminhamento__id', flat=True)
    ).exists()
    percentual_faltas = 0
    if obj.aluno.get_ultima_matricula_periodo():
        percentual_faltas = 100 - obj.aluno.get_ultima_matricula_periodo().get_percentual_carga_horaria_frequentada()
    if 0 < percentual_faltas > 100:
        percentual_faltas = 0
    for registro in registros_acompanhamentos:
        if registro.situacao:
            pode_apagar = False
        registro_acompanhamento_interessado = RegistroAcompanhamentoInteressado.objects.filter(
            registro_acompanhamento=registro, interessado__in=usuario_interessado
        )
        lista_acompanhamento.append(
            {
                'tipo': 'acompanhamento',
                'ordem': '3',
                'data_hora': registro.data,
                'objeto': registro,
                'usuario': registro.usuario,
                'pode_apagar': pode_apagar,
                'ciencia_realizada': registro_acompanhamento_interessado,
            }
        )
        pode_apagar = False
    for solicitacao in solicitacoes:
        lista_acompanhamento.append(
            {
                'tipo': 'solicitacao',
                'ordem': '1',
                'data_hora': solicitacao.data_solicitacao,
                'objeto': solicitacao,
                'usuario': solicitacao.solicitante,
                'pode_apagar': False,
            }
        )
        if solicitacao.data_avaliacao:
            lista_acompanhamento.append(
                {
                    'tipo': 'solicitacao_atendida',
                    'ordem': '2',
                    'data_hora': solicitacao.data_avaliacao,
                    'objeto': solicitacao,
                    'usuario': solicitacao.avaliador,
                    'pode_apagar': False,
                }
            )

    for encaminhamento in encaminhamentos:
        lista_acompanhamento.append(
            {
                'tipo': 'encaminhamento',
                'ordem': '4',
                'data_hora': encaminhamento.data,
                'objeto': encaminhamento,
                'usuario': encaminhamento.usuario,
                'pode_apagar': True,
            }
        )

    # if tem_permissao_realizar_procedimentos_etep:
    #     for registro_interessado in registros_interessados:
    #         lista_acompanhamento.append(
    #             dict(tipo='interessados', ordem='5', data_hora=registro_interessado.data, objeto=registro_interessado,
    #                  usuario=registro_interessado.usuario, pode_apagar=False)
    #         )
    lista_acompanhamento.sort(key=lambda x: (x['data_hora'], x['ordem']), reverse=True)

    return locals()


@login_required
@rtr()
def adicionar_registro(request, acompanhamento_pk):
    title = 'Adicionar Registro'
    acompanhamento = get_object_or_404(Acompanhamento.locals, pk=acompanhamento_pk)
    if not perms.pode_ver_etep(request, acompanhamento):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = RegistroAcompanhamentoForm(acompanhamento, request.POST or None, request.FILES or None, request=request)
    if form.is_valid():
        form.save()
        form.processar()
        return httprr('..', 'Acompanhamento adicionado com sucesso.')
    return locals()


@login_required
@rtr()
def alterar_registro(request, registro_pk):
    title = 'Alterar Registro'
    registro = get_object_or_404(RegistroAcompanhamento.objects, pk=registro_pk)
    if not perms.pode_editar_registro(request, registro):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = RegistroAcompanhamentoForm(registro.acompanhamento, request.POST or None, request.FILES or None, instance=registro, request=request)
    if form.is_valid():
        form.save()
        form.processar()
        return httprr('..', 'Acompanhamento alterado com sucesso.')

    return locals()


@login_required
@rtr()
def excluir_registro(request, registro_pk):
    obj = get_object_or_404(RegistroAcompanhamento.locals, pk=registro_pk)
    if not perms.pode_editar_registro(request, obj):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    if 'confirmar' in request.GET:
        obj.delete()
        return httprr('..', 'Registro excluído com sucesso.')
    return locals()


@login_required
@rtr()
def registros_ciencia_pendente(request):
    title = 'Registros de Acompanhamento ETEP com Ciência Pendente'
    vinculo = request.user.get_vinculo()
    registros_sem_ciencia = RegistroAcompanhamento.locals.ciencia_pendente(vinculo)
    return locals()


@login_required
@rtr()
def alterar_encaminhamentos(request, registro_pk):
    title = 'Alterar Encaminhamentos'
    registro = get_object_or_404(RegistroAcompanhamento.objects, pk=registro_pk)
    setor = registro.acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = RegistroAcompanhamentoForm(registro.acompanhamento, request.POST or None, request.FILES or None, instance=registro, request=request)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Acompanhamento alterado com sucesso.')

    return locals()


@login_required
@rtr()
def alterar_situacao_acompanhamento(request, acompanhamento_pk):
    title = 'Alterar Situação'
    acompanhamento = get_object_or_404(Acompanhamento.locals, pk=acompanhamento_pk)
    setor = acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = SituacaoAcompanhamentoForm(acompanhamento, request.POST or None, request.FILES or None)
    if form.is_valid():
        obj = form.save()
        return httprr('..', 'Situação alterada com sucesso.')

    return locals()


@login_required
@rtr()
def alterar_interessados(request, acompanhamento_pk):
    title = 'Registrar Interessados'
    acompanhamento = get_object_or_404(Acompanhamento.locals, pk=acompanhamento_pk)
    setor = acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = InteressadosForm(acompanhamento, request.POST or None, request=request)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Interessados registrados com sucesso.', close_popup=True)

    return locals()


@login_required
@rtr()
def inativar_interessado(request, interessado_pk):
    interessado = get_object_or_404(Interessado.locals, pk=interessado_pk)
    setor = interessado.acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    interessado.inativar()
    return httprr(f'/etep/acompanhamento/{interessado.acompanhamento.id}/?tab=interessados', 'Interessado inativado com sucesso.')


@login_required
@rtr()
def reativar_interessado(request, interessado_pk):
    interessado = get_object_or_404(Interessado.locals, pk=interessado_pk)
    setor = interessado.acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    interessado.ativar()
    return httprr(interessado.acompanhamento.get_absolute_url(), 'Interessado reativado com sucesso.')


@login_required
@rtr()
def adicionar_encaminhamentos(request, acompanhamento_pk):
    title = 'Adicionar Encaminhamento'
    acompanhamento = get_object_or_404(Acompanhamento.objects, pk=acompanhamento_pk)
    setor = acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = AdicionarEncaminhamentosForm(acompanhamento, request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr(f'/etep/acompanhamento/{acompanhamento.id}/?tab=encaminhamentos', 'Encaminhamentos adicionados com sucesso.', close_popup=True)
    return locals()


@login_required
@rtr()
def notificar_acompanhamento(request, registro_pk):
    title = 'Notificar Interessados'
    registro = get_object_or_404(RegistroAcompanhamento.objects, pk=registro_pk)
    setor = registro.acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = NotificarInteressadosForm(registro, request.POST or None, request=request)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Interessados notificados com sucesso.')
    return locals()


@login_required
@rtr()
def desvincular_acompanhamento(request, registro_pk):
    title = 'Desvincular Interessados'
    registro = get_object_or_404(RegistroAcompanhamento.objects, pk=registro_pk)
    setor = registro.acompanhamento.aluno.curso_campus.diretoria.setor
    if not perms.tem_permissao_realizar_procedimentos_etep(request, setor):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = DesvincularInteressadosForm(registro, request.POST or None, request=request)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Interessados desvinculados com sucesso.')
    return locals()


@login_required
@rtr()
def dar_ciencia_acompanhamento(request, registro_acompanhamento_interessado_pk):
    registro_acompanhamento_interessado = get_object_or_404(RegistroAcompanhamentoInteressado.objects, pk=registro_acompanhamento_interessado_pk)
    if request.user != registro_acompanhamento_interessado.interessado.vinculo.user:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    if not registro_acompanhamento_interessado.data_ciencia:
        registro_acompanhamento_interessado.data_ciencia = datetime.now()
        registro_acompanhamento_interessado.save()
        return httprr(request.META.get('HTTP_REFERER'), 'Ciência tomada com sucesso.')
    else:
        return httprr(request.META.get('HTTP_REFERER'), 'Ciência já tomada anteriormente.', 'error')


@login_required
@rtr()
def solicitacao_acompanhamento(request, solicitacao_pk):
    obj = get_object_or_404(SolicitacaoAcompanhamento.locals, pk=solicitacao_pk)

    title = f'Solicitação de Acompanhamento {solicitacao_pk}'

    pode_ver_etep = request.user.has_group_cached('Servidor')
    setor = obj.aluno.curso_campus.diretoria.setor
    tem_permissao_realizar_procedimentos_etep = perms.tem_permissao_realizar_procedimentos_etep(request, setor)
    acompanhamento = Acompanhamento.objects.filter(aluno=obj.aluno)
    if not pode_ver_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    acompanhamento_title = '-'
    if obj.acompanhamento:
        acompanhamento_title = f'Acompanhamento #{obj.acompanhamento.id}'

    aluno = Aluno.objects.filter(vinculos__user=obj.solicitante)
    if aluno:
        aluno = aluno[0]
    atender = request.GET.get('atender', False)
    if atender:
        obj.atender(request.user)
        obj = SolicitacaoAcompanhamento.locals.get(pk=solicitacao_pk)
        url = obj.acompanhamento.get_absolute_url()
        return httprr(url, 'Solicitação deferida com sucesso.')
    return locals()


@login_required
@rtr()
def rejeitar_solicitacao(request, solicitacao_pk):
    title = 'Rejeitar Solicitação'
    solicitacao = get_object_or_404(SolicitacaoAcompanhamento.locals, pk=solicitacao_pk)
    form = RejeitarSolicitacaoUsuarioForm(data=request.POST or None)
    setor = solicitacao.aluno.curso_campus.diretoria.setor
    tem_permissao_realizar_procedimentos_etep = perms.tem_permissao_realizar_procedimentos_etep(request, setor)
    if not request.user.has_perm('etep.change_solicitacaoacompanhamento') and not tem_permissao_realizar_procedimentos_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if request.method == 'POST':
        if form.is_valid():
            solicitacao.rejeitar(request.user, request.POST['razao_indeferimento'])
            return httprr('..', 'Solicitações indeferidas com sucesso.')

    return locals()


@login_required
@rtr()
def atividade(request, atividade_pk):
    obj = get_object_or_404(Atividade.locals, pk=atividade_pk)
    title = f'Atividade #{obj.pk}'
    tem_permissao_alterar_documentos_etep = perms.tem_permissao_alterar_documentos_etep(request, obj)
    tem_permissao_ver_documentos_etep = perms.tem_permissao_ver_documentos_etep(request)
    if not tem_permissao_ver_documentos_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    return locals()


@login_required
@rtr()
def adicionar_documento(request, atividade_pk):
    atividade = get_object_or_404(Atividade.locals, pk=atividade_pk)
    form = DocumentoForm(atividade=atividade, data=request.POST or None, files=request.FILES or None)
    tem_permissao_alterar_documentos_etep = perms.tem_permissao_alterar_documentos_etep(request, atividade)
    tem_permissao_ver_documentos_etep = perms.tem_permissao_ver_documentos_etep(request)
    if not tem_permissao_alterar_documentos_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    if form.is_valid():
        form.save()
        return httprr('..', 'Documento adicionado com sucesso.')
    return locals()


@login_required
@rtr()
def alterar_documento(request, documento_pk):
    documento = get_object_or_404(Documento.locals, pk=documento_pk)
    form = DocumentoForm(atividade=documento.atividade, instance=documento, data=request.POST or None, files=request.FILES or None)
    tem_permissao_alterar_documentos_etep = perms.tem_permissao_alterar_documentos_etep(request, documento.atividade)
    tem_permissao_ver_documentos_etep = perms.tem_permissao_ver_documentos_etep(request)
    if not tem_permissao_alterar_documentos_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    if form.is_valid():
        form.save()
        return httprr('..', 'Documento alterado com sucesso.')
    return locals()


@login_required
@rtr()
def relatorio_acompanhamento(request):
    title = 'Relatório de Acompanhamentos'
    form = RelatorioAcompanhamentoForm(data=request.GET or None)
    if form.is_valid():
        qs = form.processar()
        if 'xls' in request.GET:
            return tasks.exportar_relatorio_acompanhamento(qs)
    return locals()
