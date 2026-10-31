from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, IntegerField, Sum, When
from django.shortcuts import get_object_or_404

from auditoria.models.nucleo import NucleoAuditoria
from auditoria.papeis import get_auditores_ativos
from comum.utils import get_setor
from djtools.utils import get_datetime_now, httprr, permission_required, rtr
from documento_eletronico.forms import ListarDocumentosTextoForm
from documento_eletronico.models import DocumentoTexto

from ..forms import (
    EstoqueMonitoramentoFilterForm,
    EstoqueRecomendacaoFilterForm,
    RelatorioDigitalizadoEditForm,
    RelatorioDigitalizadoForm,
    RelatorioRainFilterForm,
    RemoverDocumentoRelatorioForm,
)
from ..models import Monitoramento, MonitoramentoStatus, Recomendacao, Relatorio, RelatorioDocumento
from ..tasks import estoque_monitoramentos_to_xls, estoque_recomendacoes_to_xls, relatorio_raint_to_xls
from ..utils import get_ch_prevista_auditores_ano


@rtr('auditoria/templates/relatorio/relatorio.html')
@login_required()
def visualizar_relatorio(request, relatorio_id):
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    title = f'Relatório {relatorio}'
    quantidade_documentos_removidos = RelatorioDocumento.objects.removidos().count()
    eh_auditor = request.user.has_perm('comum.is_auditor') and request.user.has_group_cached(['Auditor'])
    return locals()


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@permission_required('comum.is_auditor')
def listar_relatorios_anexar(request, relatorio_id):
    instance = get_object_or_404(Relatorio, pk=relatorio_id)
    title = f'Documentos que podem ser adicionados ao relatório {instance}'
    label_add_documento = 'Adicionar ao relatório'
    is_anexar_documento = True
    exibir_dados_gerais = False
    aviso = 'Somente documentos finalizados poderão ser adicionados a um relatório.'
    exibir_tab_documentos_interno = True
    view_action = 'auditoria:anexar_documento_relatorio'
    view_action_label = 'Adicionar ao Relatório'
    initial = {}
    setor = get_setor(request.user)
    if setor and setor.uo:
        initial = {'campus': setor.uo.pk, 'setor': setor.pk, 'ano': get_datetime_now().year}
    filters = request.GET.copy()
    page = filters.pop('page', 0)
    data = initial if not filters else request.GET
    form = ListarDocumentosTextoForm(data, request=request)
    documentos, documentos_compartilhados, params, order_str = form.processar()
    relatorios_ids = RelatorioDocumento.objects.filter(relatorio=instance, removido_em__isnull=True).values_list('id', flat=True)
    documentos.exclude(id__in=relatorios_ids)
    documentos = documentos.finalizados().order_by('-data_ultima_modificacao')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def anexar_documento_relatorio(request, relatorio_id, documento_id):
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    target_url = '..'
    if not relatorio.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    relatorio.adicionar_documento(documento, request.user)
    relatorio.save()
    return httprr(relatorio.get_absolute_url(), 'Operação realizada com sucesso')


@rtr()
@permission_required('comum.is_auditor')
def upload_documento_ao_relatorio(request, relatorio_id):
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    title = f'Upload de Documento Externo à {relatorio}'
    target_url = '..'
    #
    form = RelatorioDigitalizadoForm(request.POST or None, request.FILES or None, request=request)
    if form.is_valid():
        with transaction.atomic():
            documento = form.save()
            relatorio.adicionar_documento(documento, request.user)
            relatorio.save()
            return httprr(target_url, 'Documento anexado com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def remover_documento_relatorio(request, relatorio_documento_id):
    relatorio_documento = get_object_or_404(RelatorioDocumento, pk=relatorio_documento_id)
    title = f'Remover Documento do relatório {relatorio_documento.relatorio}'
    target_url = '..'
    if not relatorio_documento.pode_remover_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = RemoverDocumentoRelatorioForm(request.POST or None, instance=relatorio_documento, request=request)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Documento removido com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def editar_relatorio_documento(request, relatorio_documento_id):
    relatorio_documento = get_object_or_404(RelatorioDocumento, pk=relatorio_documento_id)
    title = f'Editar Documento {relatorio_documento.documento}'
    target_url = relatorio_documento.get_absolute_url()
    if not relatorio_documento.pode_editar_informacoes(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = RelatorioDigitalizadoEditForm(request.POST or None, instance=relatorio_documento.documento, request=request)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Documento editado com sucesso.')
    return locals()


@rtr('auditoria/templates/relatorios/relatorio_raint.html')
@permission_required('comum.is_auditor')
def relatorios_raint(request):
    title = 'Resultados do monitoramento das recomendações de auditoria'
    relatorios = Relatorio.objects.all().order_by('ano')
    form = RelatorioRainFilterForm(request.GET or None)
    if form.is_valid():
        relatorios = form.filter_queryset(relatorios)
    relatorios = relatorios.annotate(
        total_monitoramentos=Count('recomendacoes__monitoramentos'),
        registradas=Count(Case(When(recomendacoes__monitoramentos__status=MonitoramentoStatus.REGISTRADO, then=1), output_field=IntegerField())),
        em_monitoramento=Count(
            Case(When(recomendacoes__monitoramentos__status=MonitoramentoStatus.EM_MONITORAMENTO, then=1), output_field=IntegerField())
        ),
        atendidas=Count(Case(When(recomendacoes__monitoramentos__status=MonitoramentoStatus.CONCLUIDO, then=1), output_field=IntegerField())),
        nao_atendidas=Count(Case(When(recomendacoes__monitoramentos__status=MonitoramentoStatus.FINALIZADO, then=1), output_field=IntegerField())),
        canceladas=Count(Case(When(recomendacoes__monitoramentos__status=MonitoramentoStatus.CANCELADO, then=1), output_field=IntegerField())),
        percentual_atendidas=ExpressionWrapper(
            Case(When(total_monitoramentos__gt=0, then=F('atendidas') * 100.0 / F('total_monitoramentos')), default=0.0, output_field=FloatField()),
            output_field=FloatField(),
        ),
    )
    totais = relatorios.aggregate(
        total_registradas=Sum('registradas'),
        total_em_monitoramento=Sum('em_monitoramento'),
        total_atendidas=Sum('atendidas'),
        total_nao_atendidas=Sum('nao_atendidas'),
        total_canceladas=Sum('canceladas'),
        total=Sum('total_monitoramentos'),
    )
    # Calculando percentual de atendimento geral (evitando divisão por zero)
    totais['percentual_atendidas'] = (totais['total_atendidas'] * 100.0 / totais['total']) if totais['total'] else 0

    if 'xls' in request.GET:
        data = [
            {
                'ano': relatorio.ano,
                'acao': relatorio.acao,
                'em_monitoramento': relatorio.em_monitoramento,
                'registradas': relatorio.registradas,
                'atendidas': relatorio.atendidas,
                'nao_atendidas': relatorio.nao_atendidas,
                'canceladas': relatorio.canceladas,
                'percentual_atendidas': relatorio.percentual_atendidas,
                'total': relatorio.total_monitoramentos,
            }
            for relatorio in relatorios
        ]
        return relatorio_raint_to_xls(data, totais)

    return locals()


@rtr('auditoria/templates/relatorios/estoque_monitoramentos.html')
def estoque_monitoramentos(request):
    title = 'Estoque de Monitoramentos'
    monitoramentos = Monitoramento.objects.all().order_by('recomendacao__relatorio__ano', 'id')
    form = EstoqueMonitoramentoFilterForm(request.GET or None)
    if form.is_valid():
        monitoramentos = form.filter_queryset(monitoramentos)
    if 'xls' in request.GET:
        estoque = [
            {
                'identificador': monitoramento.id,
                'ano_relatorio': monitoramento.recomendacao.relatorio.ano,
                'acao': monitoramento.recomendacao.relatorio.acao,
                'campus': monitoramento.unidade,
                'situacao': monitoramento.get_status_display(),
                'ano_atendimento': monitoramento.ano_atendimento(),
                'recomendacao': monitoramento.recomendacao.descricao,
            }
            for monitoramento in monitoramentos
        ]
        return estoque_monitoramentos_to_xls(estoque)

    return locals()


@rtr('auditoria/templates/relatorios/estoque_recomendacoes.html')
def estoque_recomendacoes(request):
    title = 'Estoque de Recomendações'
    recomendacoes = Recomendacao.objects.all().order_by('-ano', 'id')
    form = EstoqueRecomendacaoFilterForm(request.GET or None)
    if form.is_valid():
        recomendacoes = form.filter_queryset(recomendacoes)
    if 'xls' in request.GET:
        estoque = [
            {
                'identificador': recomendacao.identificador,
                'ano_relatorio': recomendacao.relatorio.ano,
                'acao': recomendacao.relatorio.acao,
                #'campi': monitoramento.unidade,
                'situacao': recomendacao.get_status_display(),
                #'ano_atendimento': recomendacao.ano_atendimento(),
                'recomendacao': recomendacao.descricao,
            }
            for recomendacao in recomendacoes
        ]
        return estoque_recomendacoes_to_xls(estoque)

    return locals()


@rtr('auditoria/templates/relatorios/horas_por_auditor.html')
@permission_required('comum.is_auditor')
def relatorio_carga_horaria(request):
    ano = get_datetime_now().year
    auditores = get_auditores_ativos().filter(user__is_superuser=False)
    carga_horaria_por_auditor = get_ch_prevista_auditores_ano(auditores, ano)
    # Calcular total por mês
    # Mapear os meses para português
    meses = {
        1: 'Janeiro',
        2: 'Fevereiro',
        3: 'Março',
        4: 'Abril',
        5: 'Maio',
        6: 'Junho',
        7: 'Julho',
        8: 'Agosto',
        9: 'Setembro',
        10: 'Outubro',
        11: 'Novembro',
        12: 'Dezembro',
    }
    carga_horaria_por_auditor_formatado = {
        auditor: {meses[mes]: horas for mes, horas in horas_meses.items()} for auditor, horas_meses in carga_horaria_por_auditor.items()
    }
    # Calcular total por auditor
    totais_por_auditor = {auditor: sum(horas.values()) for auditor, horas in carga_horaria_por_auditor_formatado.items()}
    # Calcular total por mês (indexado pelos nomes dos meses)
    totais_por_auditor_mes = dict.fromkeys(meses.values(), 0)
    for horas in carga_horaria_por_auditor_formatado.values():
        for mes, carga in horas.items():
            totais_por_auditor_mes[mes] += carga
    # Calcular total geral
    total_geral = sum(totais_por_auditor_mes.values())

    # Calcula a carga horaria por núcleo
    carga_horaria_por_nucleo = {}
    nucleos = NucleoAuditoria.objects.prefetch_related('membros').all()
    for nucleo in nucleos:
        auditores_nucleo = list(nucleo.membros.all())
        carga_horaria_por_nucleo[nucleo.nome] = {
            mes: sum(carga_horaria_por_auditor_formatado.get(auditor.user, {}).get(mes, 0) for auditor in auditores_nucleo) for mes in meses.values()
        }
    totais_por_nucleo = {nucleo: sum(horas.values()) for nucleo, horas in carga_horaria_por_nucleo.items()}
    total_geral_nucleo = sum(totais_por_nucleo.values())
    totais_por_nucleo_mes = dict.fromkeys(meses.values(), 0)
    for horas in carga_horaria_por_nucleo.values():
        for mes, carga in horas.items():
            totais_por_nucleo_mes[mes] += carga
    meses = list(meses.values())
    return locals()
