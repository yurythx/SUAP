import html
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify

from auditoria.forms.beneficio import RelatorioQualitativoFilterForm
from auditoria.models.beneficio import DetalhamentoQualitativo
from auditoria.models.monitoramento import Monitoramento
from auditoria.tasks import estoque_beneficios_financeiros_to_xls
from comum.utils import get_setor
from djtools.utils import get_datetime_now, httprr, rtr, transaction
from django.utils.html import strip_tags
from documento_eletronico.forms import ListarDocumentosTextoForm
from documento_eletronico.models import DocumentoTexto


from ..forms import (
    BeneficioDocumentoDigitalizadoForm,
    BeneficioForm,
    CancelarBeneficioForm,
    FinalizarBeneficioForm,
    ParcelaFinanceiraForm,
    RelatorioFinanceiroFilterForm,
    RemoverDocumentoBeneficioForm,
)
from ..models import Beneficio, BeneficioDocumento, BeneficioStatus, DetalhamentoFinanceiro, HistoricoBeneficio, ParcelaFinanceira


def clean_html(value: str) -> str:
    if not value:
        return ''

    # Remove tags (<p>, <strong>, etc.)
    text = strip_tags(value)
    # Converte entidades HTML
    text = html.unescape(text)
    return text.strip()


@rtr('auditoria/templates/beneficios/beneficio.html')
@permission_required('comum.is_auditor')
def visualizar_beneficio(request, beneficio_id):
    beneficio: Beneficio = get_object_or_404(Beneficio, id=beneficio_id)
    title = f'Benefício #{beneficio.id}'
    quantidade_documentos_removidos = BeneficioDocumento.objects.removidos().count()
    if beneficio.status not in BeneficioStatus.SITUACOES_INATIVAS:
        steps = '<ul class="steps">'
        for situacao, opcoes in beneficio.get_fluxo():
            if situacao == beneficio.status:
                steps += f'<li><span class="step-{slugify(opcoes[1])} active">{opcoes[0]}</span></li>'
            else:
                steps += f'<li><span class="step-{slugify(opcoes[1])}">{opcoes[0]}</span></li>'
        steps += '</ul>'
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def beneficio_adicionar_parcela(request, beneficio_id):
    detalhamento: DetalhamentoFinanceiro = get_object_or_404(DetalhamentoFinanceiro, beneficio_id=beneficio_id)
    target_url = f'{detalhamento.beneficio.get_absolute_url()}?tab=detalhamento'
    title = f'Adicionar parcela ao benefício #{detalhamento.beneficio}'
    if not detalhamento.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = ParcelaFinanceiraForm(request.POST or None, detalhamento=detalhamento, request=request)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Parcela Registrada com Sucesso')
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def beneficio_editar_parcela(request, parcela_id):
    parcela: ParcelaFinanceira = get_object_or_404(ParcelaFinanceira, id=parcela_id)
    detalhamento: DetalhamentoFinanceiro = parcela.detalhamento
    beneficio: Beneficio = detalhamento.beneficio
    title = f'Editar parcela do benefício #{parcela}'
    target_url = f'{detalhamento.beneficio.get_absolute_url()}?tab=detalhamento'
    if not detalhamento.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = ParcelaFinanceiraForm(request.POST or None, instance=parcela, request=request)
    if form.is_valid():
        with transaction.atomic():
            form.save()
            vinculo = request.user.get_vinculo()
            HistoricoBeneficio.objects.create(
                beneficio=beneficio, descricao=f'{vinculo} modificou a parcela #{parcela.id} do benefício #{beneficio.id}'
            )
        return httprr(target_url, 'Parcela Registrada com Sucesso')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def beneficio_remover_parcela(request, parcela_id):
    parcela: ParcelaFinanceira = get_object_or_404(ParcelaFinanceira, id=parcela_id)
    detalhamento: DetalhamentoFinanceiro = parcela.detalhamento
    target_url = f'{detalhamento.beneficio.get_absolute_url()}?tab=detalhamento'
    if not detalhamento.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    beneficio: Beneficio = detalhamento.beneficio
    with transaction.atomic():
        parcela.delete()
        vinculo = request.user.get_vinculo()
        HistoricoBeneficio.objects.create(beneficio=beneficio, descricao=f'{vinculo} modificou a parcela #{parcela.pk} do benefício #{beneficio.pk}')
    return httprr(target_url, 'Parcela Excluída com Sucesso')


@rtr()
@login_required()
def upload_documento_beneficio(request, beneficio_id):
    beneficio: Beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    title = f'Upload de Documento externo à {Beneficio}'
    target_url = f'{beneficio.get_absolute_url()}?tab=documentos'
    if not beneficio.pode_adicionar_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = BeneficioDocumentoDigitalizadoForm(request.POST or None, request.FILES or None, request=request)
    if form.is_valid():
        with transaction.atomic():
            documento = form.save()
            beneficio.adicionar_documento(documento, request.user)
            vinculo = request.user.get_vinculo()
            HistoricoBeneficio.objects.create(
                beneficio=beneficio, descricao=f'{vinculo} colocou o documento #{documento.pk} no benefício #{beneficio.pk}'
            )
            return httprr(target_url, 'Documento anexado com sucesso.')
    return locals()


@rtr()
@login_required()
def monitorar_beneficio(request, beneficio_id):
    beneficio: Beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    target_url = beneficio.get_absolute_url()
    if not beneficio.pode_inicar_monitoramento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    with transaction.atomic():
        beneficio.monitorar()
        beneficio.save()
        HistoricoBeneficio.objects.create(
            beneficio=beneficio, descricao=f'{request.user.get_vinculo()} iniciou o monitoramento do benefício #{beneficio.id}'
        )

    return httprr(target_url, message='Monitoramento iniciado.')


def anexar_documento_beneficio(request, beneficio_id, documento_id):
    beneficio: Beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    documento: DocumentoTexto = get_object_or_404(DocumentoTexto, pk=documento_id)
    target_url = f'{beneficio.get_absolute_url()}?tab=documentos'
    if not beneficio.pode_adicionar_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    with transaction.atomic():
        beneficio.adicionar_documento(documento, request.user)
        vinculo = request.user.get_vinculo()
        HistoricoBeneficio.objects.create(
            beneficio=beneficio, descricao=f'{vinculo} colocou o documento #{documento.pk} no benefício #{beneficio.pk}'
        )
    return httprr(target_url, 'Operação realizada com sucesso.')


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@login_required()
def listar_beneficio_anexar(request, beneficio_id):
    instance = get_object_or_404(Beneficio, pk=beneficio_id)
    title = f'Documentos que podem ser adicionados ao benefício {instance}'
    label_add_documento = 'Adicionar ao benefício'
    is_anexar_documento = True
    exibir_dados_gerais = False
    aviso = 'Somente documentos finalizados poderão ser adicionados ao benefício.'
    exibir_tab_documentos_interno = True
    view_action = 'auditoria:anexar_documento_beneficio'
    view_action_label = 'Adicionar ao Benefício'
    initial = {}
    setor = get_setor(request.user)
    if setor and setor.uo:
        initial = {'campus': setor.uo.pk, 'setor': setor.pk, 'ano': get_datetime_now().year}
    filters = request.GET.copy()
    page = filters.pop('page', 0)
    data = initial if not filters else request.GET
    form = ListarDocumentosTextoForm(data, request=request)
    documentos, documentos_compartilhados, params, order_str = form.processar()
    content_type = ContentType.objects.get_for_model(DocumentoTexto)
    ids = BeneficioDocumento.objects.filter(beneficio=instance, content_type=content_type, removido_em__isnull=True).values_list(
        'object_id', flat=True
    )
    documentos = documentos.finalizados().exclude(id__in=ids).order_by('-data_ultima_modificacao')
    return locals()


@rtr()
@login_required()
def concluir_beneficio(request, beneficio_id):
    beneficio: Beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    target_url = beneficio.get_absolute_url()
    if not beneficio.pode_concluir(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    with transaction.atomic():
        beneficio.concluir(request.user)
        beneficio.save()
        HistoricoBeneficio.objects.create(beneficio=beneficio, descricao=f'{request.user.get_vinculo()} concluiu o benefício #{beneficio.id}')
    return httprr(target_url, 'Tarefa concluída com sucesso')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def cancelar_beneficio(request, beneficio_id):
    beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    target_url = beneficio.get_absolute_url()
    title = f'Cancelar {beneficio}'
    if not beneficio.pode_cancelar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = CancelarBeneficioForm(request.POST or None, request=request, instance=beneficio)
    if form.is_valid():
        with transaction.atomic():
            form.save()
            HistoricoBeneficio.objects.create(beneficio=beneficio, descricao=f'{request.user.get_vinculo()} cancelou o benefício #{beneficio.id}')
        #
        return httprr(target_url, 'Benefício cancelada com sucesso.', close_popup=True)
    #
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def finalizar_beneficio(request, beneficio_id):
    beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    target_url = beneficio.get_absolute_url()
    title = f'Finalizar {beneficio}'
    if not beneficio.pode_finalizar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = FinalizarBeneficioForm(request.POST or None, request=request, instance=beneficio)
    if form.is_valid():
        with transaction.atomic():
            form.save()
            HistoricoBeneficio.objects.create(beneficio=beneficio, descricao=f'{request.user.get_vinculo()} finalizou o benefício #{beneficio.id}')
        #
        return httprr(target_url, 'Benefício finalizado com sucesso.')
    #
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def reiniciar_monitoramento_beneficio(request, beneficio_id):
    beneficio = get_object_or_404(Beneficio, pk=beneficio_id)
    target_url = beneficio.get_absolute_url()
    if not beneficio.pode_reinicar_monitoramento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    with transaction.atomic():
        beneficio.reinicar_monitoramento()
        beneficio.save()
        HistoricoBeneficio.objects.create(
            beneficio=beneficio, descricao=f'{request.user.get_vinculo()} reiniciou o monitoramento do benefício #{beneficio.id}'
        )
    return httprr(target_url, message='Monitoramento reiniciado.')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def vincular_beneficio_ao_monitoramento(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    form = BeneficioForm(request.POST or None, request=request, content_object=monitoramento)
    if form.is_valid():
        instance = form.save()
        return httprr(instance.get_absolute_url(), message='Benefício vinculado com sucesso.')
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def remover_documento_beneficio(request, beneficio_documento_id):
    """
    Remove um documento do benefício.
    """
    beneficio_documento: BeneficioDocumento = get_object_or_404(BeneficioDocumento, pk=beneficio_documento_id)
    beneficio: Beneficio = beneficio_documento.beneficio
    title = f'Remover Documento do Benefício {beneficio}'
    target_url = f'{beneficio.get_absolute_url()}?tab=documentos'
    if not beneficio.pode_remover_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = RemoverDocumentoBeneficioForm(request.POST or None, instance=beneficio_documento, request=request)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Documento removido com sucesso.')
    return locals()


@rtr('auditoria/templates/beneficios/relatorio_qualitativo.html')
@permission_required('comum.is_auditor')
def relatorio_beneficios_qualitativos_view(request):
    """
    View para gerar o relatório de benefícios qualitativos.
    """
    title = 'Relatório Gerencial de Benefícios Qualitativos'
    form = RelatorioQualitativoFilterForm(request.GET or None)
    beneficios = DetalhamentoQualitativo.objects.all()
    if form.is_valid():
        beneficios = form.filter(beneficios)
    if 'xls' in request.GET:
        estoque = [
            {
                'identificador': beneficio_qualitativo.id,
                'ano': beneficio_qualitativo.beneficio.ano,
                'classe': beneficio_qualitativo.beneficio.classe.descricao,
                'origem do beneficio': str(beneficio_qualitativo.beneficio.content_object),
                'unidade afetada': beneficio_qualitativo.unidade_afetada.nome,
                'alcance_estrategico': beneficio_qualitativo.alcance_estrategico.descricao,
                'descricao': str(clean_html(beneficio_qualitativo.beneficio.descricao)),
            }
            for beneficio_qualitativo in beneficios
        ]
        return estoque_beneficios_financeiros_to_xls(estoque)
    beneficios = beneficios.order_by('beneficio__ano')
    return locals()


@rtr('auditoria/templates/beneficios/relatorio_financeiro.html')
@permission_required('comum.is_auditor')
def relatorio_beneficios_financeiros_view(request):
    """
    View para gerar o relatório de benefícios financeiros.
    """
    title = 'Relatório Gerencial de Benefícios Financeiros'
    form = RelatorioFinanceiroFilterForm(request.GET or None)
    beneficios = DetalhamentoFinanceiro.objects.all()
    if form.is_valid():
        beneficios = form.filter(beneficios)
    if 'xls' in request.GET:
        estoque = [
            {
                'identificador': beneficio_financeiro.id,
                'ano': beneficio_financeiro.beneficio.ano,
                'classe': beneficio_financeiro.beneficio.classe.descricao,
                'natureza': beneficio_financeiro.get_natureza_display(),
                'valor efetivo': beneficio_financeiro.total_efetivo(),
                'descricao': str(clean_html(beneficio_financeiro.beneficio.descricao)),
            }
            for beneficio_financeiro in beneficios
        ]
        return estoque_beneficios_financeiros_to_xls(estoque)
    beneficios = beneficios.order_by('beneficio__ano')
    return locals()
