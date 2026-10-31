import json
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import reduce
from operator import or_
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.db.transaction import atomic
from django.forms import BaseInlineFormSet, inlineformset_factory, model_to_dict
from django.forms.formsets import formset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.template.loader import get_template
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.text import get_valid_filename
from django_tables2 import DateColumn, LinkColumn
from django_tables2.utils import Accessor

from comum.models import Ano, APIExterna, Arquivo, Configuracao, Notificador
from comum.utils import get_setor, get_uo
from contratos.forms import (
    AdicionaFiscalEmLoteForm,
    AdicionarEmpenhoForm,
    AgendaForm,
    AnexoContratoForm,
    AnexoMaoDeObraForm,
    ApostilamentoForm,
    ArrecadacaoReceitaForm,
    BuscarContratoComprasGovForm,
    ConsultaFiscalForm,
    ContaContratoForm,
    ContratoCancelarForm,
    ContratoConcluirForm,
    ContratoTiposDocumentosComprobatorioForm,
    CopiarMaoDeObra,
    CronogramaForm,
    DepositoContaContratoForm,
    DespachoFiscalForm,
    DespachoTermoAditivoForm,
    DocumentoEmpenhoContratoMedicaoForm,
    DocumentoEmpenhoContratoMedicaoInlineFormSet,
    EditarContaContratoForm,
    EditarMovimentacaoContaContratoForm,
    EditarPublicacaoContratoForm,
    EscolhaContaVinculadaRetencaoForm,
    ExportacaoForm,
    FiltroContratoEletricoForm,
    FiltroContratoForm,
    FiscalForm,
    GarantiaForm,
    IMRForm,
    IndicadoresForm,
    ItemContratoForm,
    MaoDeObraForm,
    MedicaoEletricaForm,
    MedicaoForm,
    MedicaoTipoDocumentoComprobatorioForm,
    OcorrenciaForm,
    OcorrenciaMaoDeObraForm,
    OcorrenciaMedicaoForm,
    ParcelaContratoFormSet,
    ParcelaForm,
    PenalidadeForm,
    PublicacaoAditivoForm,
    PublicacaoContratoForm,
    RegistrarFiscalizacaoForm,
    RelatorioConsumoEnergiaForm,
    RelatorioEmpenhosForm,
    RelatorioPendenciasForm,
    RelatorioTerceirizadosForm,
    SaqueContaContratoForm,
    SituacaoContratosForm,
    SolicitacaoPublicacaoPortariaFiscalForm,
    TermoAditivoForm,
    UploadArquivoContratoForm,
    UploadArquivoForm,
    VerbaSalarialMaoDeObraForm,
    servidor_campus,
)
from contratos.models import (
    CONTINUIDADE_CONTINUO,
    IMR,
    Aditivo,
    Agenda,
    AnexoAgenda,
    AnexoContrato,
    AnexoMaoDeObra,
    Apostilamento,
    ArrecadacaoReceita,
    BaseLegal,
    ContaContrato,
    ContaVinculadaCalculo,
    Contrato,
    ContratoTipoDocumentoComprobatorio,
    Cronograma,
    DocumentoEmpenhoContrato,
    DocumentoEmpenhoContratoMedicao,
    DocumentoTextoContrato,
    Fiscal,
    Garantia,
    ItemContrato,
    MaoDeObra,
    Medicao,
    MedicaoEletrica,
    MedicaoTipoDocumentoComprobatorio,
    MovimentacaoContaContrato,
    Ocorrencia,
    OcorrenciaMaoDeObra,
    Parcela,
    Penalidade,
    PreConfiguracaoAgenda,
    PublicacaoAditivo,
    PublicacaoContrato,
    TipoContrato,
    TipoDocumentoComprobatorio,
    TipoLicitacao,
    VerbaSalarialMaoDeObra,
)
from djtools import layout
from djtools.html.graficos import BarChart, LineChart
from djtools.tables import get_table
from djtools.templatetags.filters import format_money, in_group
from djtools.utils import (
    JsonResponse,
    XlsResponse,
    group_required,
    html_email_template,
    httprr,
    permission_required,
    proximo_mes,
    render,
    rtr,
    send_mail,
    somar_dias,
)
from documento_eletronico.forms import ListarDocumentosTextoForm
from documento_eletronico.models import (
    CompartilhamentoDocumentoPessoa,
    Documento,
    DocumentoTexto,
    HipoteseLegal,
    ModeloDocumento,
    NivelPermissao,
    TipoVinculoDocumento,
    VinculoDocumentoTexto,
)
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.utils import EstagioProcessamentoVariavel, get_variaveis, processar_template_ckeditor
from processo_eletronico.models import Processo
from rh.models import PessoaJuridica, Servidor, UnidadeOrganizacional
from suap import nomenclatura
from tesouro_gerencial.models import DocumentoBase

from . import tasks
from .utils import Notificar, add_log_entry, por_extenso, verificar_fiscal


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Consultas gerais', 'titulo': 'Contratos', 'icone': 'file-contract', 'url': '/contratos/listar_contratos/'}
    )

    return servicos_anonimos


@layout.quadro('Contratos', icone='file-alt')
def index_quadros(quadro, request):
    relacionamento = request.user.get_relacionamento()
    uo_id = relacionamento.setor.uo_id if relacionamento.setor else None
    dias_inicio_licitacao = Configuracao.get_valor_por_chave('contratos', 'dias_nova_licitacao') or 90
    if request.user.has_group_cached('Gerente de Contrato', ignore_groups_if_superuser=False):
        proximos_a_vencer = Contrato.objects.proximos_a_vencer().filter(campi=uo_id).count()
        if proximos_a_vencer:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(proximos_a_vencer)} no campus',
                    subtitulo=f'Com vencimento nos próximos {dias_inicio_licitacao} dias',
                    qtd=proximos_a_vencer,
                    url=f'/admin/contratos/contrato/?campi__id__exact={uo_id}&tab=tab_proximos_a_vencer',
                )
            )

        proximos_a_vencer_com_garantias = Contrato.objects.proximos_a_vencer_com_garantias().filter(campi=uo_id).count()
        if proximos_a_vencer_com_garantias:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(proximos_a_vencer_com_garantias)} no campus',
                    subtitulo=f'Com garantia e vencimento nos próximos {dias_inicio_licitacao} dias',
                    qtd=proximos_a_vencer_com_garantias,
                    url=f'/admin/contratos/contrato/?campi__id__exact={uo_id}&tab=tab_proximos_a_vencer_com_garantias',
                )
            )

        com_vigencia_expirada = Contrato.objects.com_vigencia_expirada().filter(campi=uo_id).count()
        if com_vigencia_expirada:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(com_vigencia_expirada)} no campus',
                    subtitulo='Com vigência expirada',
                    qtd=com_vigencia_expirada,
                    url=f'/admin/contratos/contrato/?campi__id__exact={uo_id}&tab=tab_com_vigencia_expirada',
                )
            )

        com_ocorrencias_expiradas = Contrato.objects.com_ocorrencias_expiradas().filter(campi=uo_id).count()
        if com_ocorrencias_expiradas:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(com_ocorrencias_expiradas)} no campus',
                    subtitulo='Com ocorrências expiradas',
                    qtd=com_ocorrencias_expiradas,
                    url=f'/admin/contratos/contrato/?campi__id__exact={uo_id}&tab=tab_com_ocorrencias_expiradas',
                )
            )

    if request.user.has_group_cached('Fiscal de Contrato', ignore_groups_if_superuser=False):
        ids_contrato_como_fiscal_ativo = (
            Fiscal.objects.filter(servidor=relacionamento, inativo=False).only('contrato').values_list('contrato', flat=True)
        )
        proximos_a_vencer = Contrato.objects.proximos_a_vencer().filter(id__in=ids_contrato_como_fiscal_ativo).count()
        if proximos_a_vencer:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(proximos_a_vencer)} que fiscalizo',
                    subtitulo=f'Com vencimento nos próximos {dias_inicio_licitacao} dias',
                    qtd=proximos_a_vencer,
                    url='/admin/contratos/contrato/?fiscal=somente_eu&tab=tab_proximos_a_vencer',
                )
            )

        proximos_a_vencer_com_garantias = Contrato.objects.proximos_a_vencer_com_garantias().filter(id__in=ids_contrato_como_fiscal_ativo).count()
        if proximos_a_vencer_com_garantias:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(proximos_a_vencer_com_garantias)} que fiscalizo',
                    subtitulo=f'Com garantia e vencimento nos próximos {dias_inicio_licitacao} dias',
                    qtd=proximos_a_vencer_com_garantias,
                    url='/admin/contratos/contrato/?fiscal=somente_eu&tab=tab_proximos_a_vencer_com_garantias',
                )
            )

        com_vigencia_expirada = Contrato.objects.com_vigencia_expirada().filter(id__in=ids_contrato_como_fiscal_ativo).count()
        if com_vigencia_expirada:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(com_vigencia_expirada)} que fiscalizo',
                    subtitulo='Com vigência expirada',
                    qtd=com_vigencia_expirada,
                    url='/admin/contratos/contrato/?fiscal=somente_eu&tab=tab_com_vigencia_expirada',
                )
            )

        com_ocorrencias_expiradas = Contrato.objects.com_ocorrencias_expiradas().filter(id__in=ids_contrato_como_fiscal_ativo).count()
        if com_ocorrencias_expiradas:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Contrato{pluralize(com_ocorrencias_expiradas)} que fiscalizo',
                    subtitulo='Com ocorrências expiradas',
                    qtd=com_ocorrencias_expiradas,
                    url='/admin/contratos/contrato/?fiscal=somente_eu&tab=tab_com_ocorrencias_expiradas',
                )
            )

    return quadro


@login_required
def redirect_contratos(request):
    uo = get_uo(request.user)
    url_base = '/admin/contratos/contrato/'
    return HttpResponseRedirect(url_base + f'?campi__id__exact={uo.id}' if uo else url_base)


@rtr()
@permission_required('contratos.pode_visualizar_contrato')
def aditivo(request, aditivo_id):
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    title = f'Termo Aditivo {aditivo.numero}'
    pode_atualizar_contrato = request.user.has_perm('contratos.change_contrato')
    pode_submeter_arquivo = request.user.has_perm('contratos.pode_submeter_arquivo')
    pode_visualizar_arquivo = request.user.has_perm('contratos.pode_visualizar_arquivo')
    pode_adicionar_publicacao = request.user.has_perm('contratos.pode_adicionar_publicacao')
    pode_excluir_publicacao = request.user.has_perm('contratos.pode_excluir_publicacao')
    pode_submeter_publicacao = request.user.has_perm('contratos.pode_submeter_publicacao')
    pode_visualizar_publicacao = request.user.has_perm('contratos.pode_visualizar_publicacao')
    pode_adicionar_fiscal = request.user.has_perm('contratos.pode_adicionar_fiscal')
    pode_excluir_fiscal = request.user.has_perm('contratos.pode_excluir_fiscal')

    return locals()


@rtr()
@login_required()
def alterar_situacao_fiscal(request, contrato_id, situacao):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    pode_adicionar_fiscal = request.user.has_perm('contratos.pode_adicionar_fiscal')
    pode_excluir_fiscal = request.user.has_perm('contratos.pode_excluir_fiscal')
    if request.method == 'POST' and (pode_adicionar_fiscal or pode_excluir_fiscal) and 'fiscal_ids' in request.POST:
        fiscal_ids = request.POST.getlist('fiscal_ids')
        if situacao == 1:
            Fiscal.objects.filter(contrato=contrato, id__in=fiscal_ids).update(inativo=False)
            return httprr(f'/contratos/contrato/{contrato.id}/?tab=fiscais', 'Fiscais ativados com sucesso.')
        elif situacao == 0:
            Fiscal.objects.filter(contrato=contrato, id__in=fiscal_ids).update(inativo=True)
            return httprr(f'/contratos/contrato/{contrato.id}/?tab=fiscais', 'Fiscais deativados com sucesso.')


@rtr()
@login_required()
def contrato(request, contrato_id):
    contrato = get_object_or_404(
        Contrato.objects.select_related(
            'tipo',
            'subtipo',
            'base_legal',
            'processo',
            'empenho',
            'campus_gerenciador',
            'vinculo_contratado__pessoa',
        ).prefetch_related(
            'campi',
            'setores_gerenciadores',
            Prefetch('documentos_texto', queryset=DocumentoTextoContrato.objects.select_related('documento')),
            Prefetch('fiscais', queryset=Fiscal.objects.select_related('tipo', 'servidor__pessoa_fisica', 'campus')),
            Prefetch('maosdeobra', queryset=MaoDeObra.objects.select_related('prestador_servico__pessoa_fisica')),
        ),
        pk=contrato_id,
    )
    is_visualizador_sistemico = (
        request.user.is_superuser or request.user.has_group_cached('Auditor') or request.user.has_group_cached('Supervisor de Contratos')
    )
    restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
    vinculo = request.user.get_vinculo()
    if restringir_por_unidade and not is_visualizador_sistemico:
        if not vinculo or not vinculo.setor or contrato.campus_gerenciador_id != vinculo.setor.uo_id:
            return HttpResponseForbidden()

    mesmo_campus = not restringir_por_unidade or (vinculo and vinculo.setor and contrato.campus_gerenciador_id == vinculo.setor.uo_id)
    pode_gerenciar = contrato.pode_gerenciar(request.user)
    pode_atualizar_contrato = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.change_contrato')
    pode_submeter_arquivo = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_submeter_arquivo')
    pode_visualizar_arquivo = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_visualizar_arquivo')
    pode_efetuar_medicao = (mesmo_campus or pode_gerenciar) and contrato.pode_efetuar_medicao(request)
    pode_gerar_cronograma = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_gerar_cronograma')
    pode_visualizar_cronograma = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_visualizar_cronograma')
    pode_adicionar_publicacao = (
        (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_adicionar_publicacao') and not contrato.cancelado
    )
    pode_excluir_publicacao = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_excluir_publicacao')
    pode_submeter_publicacao = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_submeter_publicacao')
    pode_visualizar_publicacao = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_visualizar_publicacao')
    pode_adicionar_anexo = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_adicionar_anexo')
    pode_visualizar_anexo = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_visualizar_anexo')
    pode_adicionar_fiscal = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_adicionar_fiscal')
    pode_excluir_fiscal = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_excluir_fiscal')
    pode_aditivar_contrato = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_aditivar_contrato')
    pode_cancelar_contrato = (mesmo_campus or pode_gerenciar) and request.user.has_perm('contratos.pode_cancelar_contrato')
    is_operador = (mesmo_campus or pode_gerenciar) and request.user.has_group_cached(['Operador de Contrato', 'Gerente de Contrato'])

    title = str(contrato.numero)
    data_vencimento = contrato.data_vencimento
    vence_nos_proximos_90_dias = False
    hoje = datetime.now().date()
    if data_vencimento and data_vencimento > hoje and (data_vencimento < (hoje + timedelta(days=90))):
        vence_nos_proximos_90_dias = True
    campus_filtro = None
    aditivos = contrato.get_aditivos()
    apostilamentos = contrato.get_apostilamentos()
    garantias = contrato.garantias.all()
    penalidades = contrato.penalidades.all()
    itens_contrato = ItemContrato.objects.filter(contrato=contrato)
    maosdeobra = contrato.maosdeobra.all()
    ocorrencias = contrato.ocorrencias.all().order_by('data')
    arrecadacaoreceita = contrato.arrecadacao_receitas.all()
    anexos = contrato.anexos.all().order_by('data')
    uos = contrato.campi.all()
    uo_selecionada = int(request.GET.get('uo_selecionada') or 0)
    documentostexto_do_contrato = contrato.documentos_texto.exclude(documento__status__in=[DocumentoStatus.STATUS_CANCELADO])
    agendas = contrato.agendas.all()
    # evita exceção quando usuário logado não é um servidor
    fiscal = None
    eh_gestor_contrato = None
    if request.user.eh_servidor:
        fiscal = contrato.get_fiscal(request.user.get_relacionamento())
        eh_gestor_contrato = contrato.eh_gestor_contrato(request.user.get_relacionamento())
    pode_gerenciar_todas_medicoes = pode_efetuar_medicao and fiscal.tipo.pode_gerenciar_todas_medicoes_contrato
    pode_gerenciar_recebimento_definitivo = contrato.pode_gerenciar_recebimento_definitivo(request)

    pode_gerenciar_empenho = contrato.pode_gerenciar_empenho(request)
    pode_gerenciar_conta = contrato.pode_gerenciar_conta(request)
    pode_gerenciar_ocorrencia = contrato.pode_gerenciar_ocorrencia(request)
    pode_gerenciar_penalidade = contrato.pode_gerenciar_penalidade(request)
    pode_gerenciar_mao_de_obra = contrato.pode_gerenciar_mao_de_obra(request)
    pode_gerenciar_agenda_fiscalizacao = contrato.pode_gerenciar_agenda_fiscalizacao(request)

    if pode_excluir_fiscal and 'excluir_fiscal' in request.GET:
        fiscal = Fiscal.objects.get(pk=request.GET['excluir_fiscal'])
        fiscal.inativo = True
        fiscal.data_exclusao = datetime.today()
        fiscal.save()
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Fiscal removido com sucesso.')

    if pode_excluir_publicacao and 'excluir_publicacao' in request.GET:
        publicacao = PublicacaoContrato.objects.filter(pk=request.GET['excluir_publicacao']).first()
        if publicacao:
            publicacao.delete()
            return httprr(f'/contratos/contrato/{contrato.id}/', 'Publicação removida com sucesso.')
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Ocorrência não encontrada. Portanto, não pode excluí-la.', tag='error')

    if 'excluir_ocorrencia' in request.GET:
        if not pode_gerenciar_ocorrencia:
            return httprr(
                f'/contratos/contrato/{contrato.id}/?tab=ocorrencias',
                'Você não cadastrou essa ocorrência. Portanto, não pode excluí-la.',
                tag='error',
            )

        ocorrencia = Ocorrencia.objects.get(pk=request.GET['excluir_ocorrencia'])
        if ocorrencia.fiscal != fiscal:
            return httprr(
                f'/contratos/contrato/{contrato.id}/?tab=ocorrencias',
                'Você não cadastrou essa ocorrência. Portanto, não pode excluí-la.',
                tag='error',
            )
        ocorrencia.delete()
        return httprr(f'/contratos/contrato/{contrato.id}/?tab=ocorrencias', 'Ocorrência removida com sucesso.')

    if fiscal or request.user.has_group_cached('Gerente de Contrato') or request.user.has_group_cached('Coordenador de Contrato Sistêmico'):
        if 'excluir_anexo' in request.GET:
            anexo = AnexoContrato.objects.get(pk=request.GET['excluir_anexo'])
            anexo.delete()
            return httprr(f'/contratos/contrato/{contrato.id}/?tab=documentos_relacionados', 'Anexo removido com sucesso.')

    # Todo: verificar se será utilizada apenas remoção lógica e caso seja delete() adicionar a checagem de permission requerid ou grupo Gerente de Contrato
    if 'remover_vinculo_documento' in request.GET:
        if request.user.has_group_cached('Gerente de Contrato'):
            documento_contrato = DocumentoTextoContrato.objects.get(pk=request.GET['remover_vinculo_documento'])
            documento_contrato.delete()
            return httprr(
                f'/contratos/contrato/{contrato.id}/', f'Vínculo com documento {documento_contrato.documento.identificador} removido com sucesso.'
            )
        else:
            raise PermissionDenied

    fiscais = contrato.fiscais.all()
    empenhos = contrato.get_empenhos()

    cronograma = contrato.get_cronograma()
    parcelas = Parcela.objects.none()
    if cronograma:
        medicoes_queryset = Medicao.objects.select_related(
            'fiscal__servidor__pessoa_fisica',
            'campus',
            'processo',
            'despacho_documentotexto',
            'termo_definitivo_documentotexto',
            'imr',
        ).prefetch_related(
            Prefetch('movimentacoes_conta', queryset=MovimentacaoContaContrato.objects.select_related('conta')),
            Prefetch(
                'documentos_empenho_medicao',
                queryset=DocumentoEmpenhoContratoMedicao.objects.select_related('documento_empenho_contrato__empenho'),
            ),
        )
        parcelas = (
            cronograma.parcelas.all()
            .order_by('data_prevista_inicio')
            .prefetch_related(Prefetch('medicoes', queryset=medicoes_queryset))
            .annotate(valor_executado=Sum('medicoes__valor_executado'))
        )

    if uo_selecionada:
        empenhos = empenhos.filter(empenho__emitente_ug__uo=uo_selecionada)
        fiscais = fiscais.filter(campus=uo_selecionada)
        ocorrencias = ocorrencias.filter(campus=uo_selecionada)
        maosdeobra = maosdeobra.filter(campus=uo_selecionada)
        anexos = anexos.filter(campus=uo_selecionada)
        parcelas = parcelas.filter(medicoes__campus=uo_selecionada)
        campus_filtro = uo_selecionada

    maosdeobra_ativas = maosdeobra.filter(desligamento__isnull=True)
    maosdeobra_inativas = maosdeobra.filter(desligamento__isnull=False)

    documentos_relacionados = anexos.count() + documentostexto_do_contrato.count()
    termo = Aditivo()
    termo.valor = contrato.valor
    termo.qtd_parcelas = contrato.qtd_parcelas
    termo.data_inicio = contrato.data_inicio
    termo.data_fim = contrato.data_fim

    aditivo_form = TermoAditivoForm(instance=termo, data_inicio_contrato=contrato.data_inicio)
    tipo_contrato_eletrico = contrato.subtipo and contrato.subtipo_id == int(
        Configuracao.get_valor_por_chave('contratos', 'tipo_contrato_energia_eletrica') or 0
    )
    if tipo_contrato_eletrico:
        form_contrato_eletrico = FiltroContratoEletricoForm(request.POST or None, contrato=contrato)
        if form_contrato_eletrico.is_valid():
            medicoes_eletricas = MedicaoEletrica.objects.filter(medicao__parcela__cronograma__contrato=contrato)
            ano = form_contrato_eletrico.cleaned_data.get('ano')
            mes = form_contrato_eletrico.cleaned_data.get('mes')
            if ano != 'todos':
                medicoes_eletricas = medicoes_eletricas.filter(ano_referencia=int(ano))
            if mes:
                medicoes_eletricas = medicoes_eletricas.filter(mes_referencia=mes)

            medicoes_ = OrderedDict()
            for medicao in medicoes_eletricas.order_by('ano_referencia', 'mes_referencia'):
                mes_ano = f'{medicao.mes_referencia}/{medicao.ano_referencia}'
                consumo_ponta = consumo_fora_ponta = 0
                if medicoes_.get(mes_ano):
                    if medicao.consumo_ponta:
                        consumo_ponta = float(medicao.consumo_ponta)
                    medicoes_[mes_ano]['consumo_ponta'] += consumo_ponta
                    if medicao.consumo_fora_ponta:
                        consumo_fora_ponta = float(medicao.consumo_fora_ponta)
                    medicoes_[mes_ano]['consumo_fora_ponta'] += consumo_fora_ponta
                    medicoes_[mes_ano]['total'] += consumo_ponta + consumo_fora_ponta
                else:
                    medicoes_[mes_ano] = {}
                    if medicao.consumo_ponta:
                        consumo_ponta = float(medicao.consumo_ponta)
                    medicoes_[mes_ano]['consumo_ponta'] = consumo_ponta
                    if medicao.consumo_fora_ponta:
                        consumo_fora_ponta = float(medicao.consumo_fora_ponta)
                    medicoes_[mes_ano]['consumo_fora_ponta'] = consumo_fora_ponta
                    medicoes_[mes_ano]['total'] = consumo_ponta + consumo_fora_ponta

            series = [
                [key, float(dicionario['consumo_ponta']), float(dicionario['consumo_fora_ponta']), float(dicionario['total'])]
                for key, dicionario in list(medicoes_.items())
            ]
            grafico = LineChart(
                'grafico',
                title='Gastos Elétricos',
                data=series,
                groups=['Consumo de Ponta', 'Consumo Fora Ponta', 'Consumo Total'],
                yAxis_title_text='kWh',
                plotOptions_line_dataLabels_enable=True,
                plotOptions_line_enableMouseTracking=True,
            )
    return locals()


@rtr()
@permission_required('contratos.pode_cancelar_contrato')
def cancelar_contrato(request, contrato_id):
    title = 'Cancelar contrato'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = ContratoCancelarForm(request.POST or None)
    if form.is_valid():
        motivo_cancelamento = form.cleaned_data['motivo_cancelamento']
        contrato.motivo_cancelamento = motivo_cancelamento
        contrato.cancelado = True
        contrato.dh_cancelamento = datetime.now()
        contrato.usuario_cancelamento = request.user
        contrato.save()
        return httprr('..', 'Contrato cancelado.')

    return locals()


@rtr()
@permission_required('contratos.can_delete')
@atomic
def excluir(request, contrato_id):
    pass


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def exportar_maodeobra(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    rows = [
        [
            'Prestador de Serviço',
            'Data de Nascimento',
            'Categoria',
            'Função',
            'Escolaridade',
            'Jornada de Trabalho',
            'Hora Início da Jornada',
            'Hora Fim da Jornada',
            'Hora Início do Intervalo',
            'Hora Fim do Intervalo',
            'Salário Bruto',
            'Início da Vigência',
            'Custo Mensal',
            'Data de Desligamento',
        ]
    ]
    for maodeobra in contrato.maosdeobra.all():
        row = [
            maodeobra.prestador_servico,
            maodeobra.data_nascimento,
            maodeobra.categoria,
            maodeobra.funcao,
            maodeobra.escolaridade,
            maodeobra.jornada_trabalho,
            maodeobra.hora_inicio_jornada.strftime('%H:%M') if maodeobra.hora_inicio_jornada else '-',
            maodeobra.hora_fim_jornada.strftime('%H:%M') if maodeobra.hora_fim_jornada else '-',
            maodeobra.hora_inicio_intervalo.strftime('%H:%M') if maodeobra.hora_inicio_intervalo else '-',
            maodeobra.hora_fim_intervalo.strftime('%H:%M') if maodeobra.hora_fim_intervalo else '-',
            maodeobra.salario_bruto,
            maodeobra.inicio_vigencia,
            maodeobra.custo_mensal,
            maodeobra.desligamento,
        ]
        rows.append(row)
        ocorrencias = maodeobra.ocorrencias.all()
        if ocorrencias:
            row = ['', '']
            row.append('Tipo')
            row.append('Descrição')
            row.append('Data Início')
            row.append('Data Fim')
            rows.append(row)

            count = 0
            for obj in ocorrencias:
                row = ['']
                count += 1
                row.append(f'Ocorrência {count}')
                row.append(f'{obj.tipo}')
                row.append(f'{obj.descricao}')
                row.append(f'{obj.data_inicio.strftime("%d/%m/%Y")}')
                row.append(f'{obj.data_fim.strftime("%d/%m/%Y") if obj.data_fim else "-"}')
                rows.append(row)

        verbas_salariais = maodeobra.verbas_salariais.all()
        if verbas_salariais:
            row = ['', '']
            row.append('Tipo')
            row.append('Valor')
            row.append('Data Início')
            row.append('Data Fim')
            rows.append(row)

            count = 0
            for obj in verbas_salariais:
                row = ['']
                count += 1
                row.append(f'Verba Salarial {count}')
                row.append(f'{obj.tipo}')
                row.append(f'{obj.valor}')
                row.append(f'{obj.data_inicio.strftime("%d/%m/%Y")}')
                row.append(f'{obj.data_fim.strftime("%d/%m/%Y") if obj.data_fim else "-"}')
                rows.append(row)

    return XlsResponse(rows)


@rtr()
@login_required
def excluir_maodeobra(request, maodeobra_id):
    maodeobra = get_object_or_404(MaoDeObra, pk=maodeobra_id)
    if not maodeobra.contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    contrato_id = maodeobra.contrato.id
    maodeobra.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Mão de obra excluída com sucesso.')


@rtr()
@login_required
def editar_maodeobra(request, maodeobra_id):
    title = 'Editar Mão de obra'
    maodeobra = get_object_or_404(MaoDeObra, pk=maodeobra_id)
    if not maodeobra.contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    dados_anteriores = model_to_dict(maodeobra)
    form = MaoDeObraForm(request.POST or None, instance=maodeobra)
    if form.is_valid():
        form.save()
        dados_atuais = model_to_dict(maodeobra)
        # Comparando os dados e obtendo os valores alterados
        valores_alterados = {
            campo: f'De {dados_anteriores[campo]} para {dados_atuais[campo]}'
            for campo, valor in dados_anteriores.items()
            if valor != dados_atuais[campo]
        }

        add_log_entry(request, maodeobra, valores_alterados)
        return httprr('..', 'Mão de obra editada com sucesso.')
    return locals()


@rtr()
@login_required
def adicionar_maodeobra(request, contrato_id):
    title = 'Adicionar Mão de obra'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    maodeobra = MaoDeObra()
    maodeobra.contrato = contrato
    form = MaoDeObraForm(request.POST or None, instance=maodeobra, contrato=contrato)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr('..', 'Mão de obra adicionada com sucesso.')
    return locals()


@rtr()
@login_required
def adicionar_anexomaodeobra(request, maodeobra_id):
    title = 'Adicionar Anexo à Mão de Obra'
    maodeobra = get_object_or_404(MaoDeObra, pk=maodeobra_id)
    if not maodeobra.contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    form = AnexoMaoDeObraForm(request.POST or None, request.FILES or None, maodeobra=maodeobra)
    if form.is_valid():
        form.save()
        return httprr('..', 'Anexo adicionado com sucesso à mão de obra.')
    return locals()


@rtr()
@login_required
def remover_anexomaodeobra(request, anexomaodeobra_id):
    anexo = get_object_or_404(AnexoMaoDeObra, pk=anexomaodeobra_id)
    contrato = anexo.maodeobra.contrato
    if not contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    anexo.delete()
    return httprr(f'/contratos/contrato/{contrato.id}/?tab=maodeobra', 'Anexo removido com sucesso.')


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def excluir_apostilamento(request, apostilamento_id):
    apostilamento = get_object_or_404(Apostilamento, pk=apostilamento_id)
    contrato_id = apostilamento.contrato.id
    apostilamento.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Apostilamento excluído com sucesso.')


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def editar_apostilamento(request, apostilamento_id):
    title = 'Editar Apostilamento'
    apostilamento = get_object_or_404(Apostilamento, pk=apostilamento_id)
    form = ApostilamentoForm(
        request.POST or None, request.FILES or None, instance=apostilamento, data_inicio_contrato=apostilamento.contrato.data_inicio
    )
    if form.is_valid():
        form.save()
        return httprr(f'/contratos/contrato/{apostilamento.contrato.id}/', 'Apostilamento editado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def adicionar_apostilamento(request, contrato_id):
    title = 'Adicionar Apostilamento'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    apostilamento = Apostilamento()
    apostilamento.valor = contrato.valor
    apostilamento.data_inicio = contrato.data_inicio
    apostilamento.data_fim = contrato.data_fim
    form = ApostilamentoForm(request.POST or None, request.FILES or None, instance=apostilamento, data_inicio_contrato=contrato.data_inicio)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        url = f'/contratos/contrato/{contrato_id}/'
        msg = 'Apostilamento adicionado com sucesso.'
        if form.instance.tipo == Apostilamento.REPACTUACAO:
            msg = f'{msg} Atualize as remunerações de funcionários vinculados ao contrato'
            url = f'{url}?tab=maodeobra#'
            if contrato.mao_obra_exclusiva:
                Notificar.apostilamento_em_contrato_mao_de_obra(contrato)
        return httprr(url, msg)
    return locals()


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def excluir_garantia(request, garantia_id):
    garantia = get_object_or_404(Garantia, pk=garantia_id)
    contrato_id = garantia.contrato.id
    garantia.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Garantia excluída com sucesso.')


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def editar_garantia(request, garantia_id):
    title = 'Editar Garantia'
    garantia = get_object_or_404(Garantia, pk=garantia_id)
    form = GarantiaForm(request.POST or None, request.FILES or None, instance=garantia)
    if form.is_valid():
        form.save()
        return httprr(f'/contratos/contrato/{garantia.contrato.id}/', 'Garantia editada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def adicionar_garantia(request, contrato_id):
    title = 'Adicionar Garantia'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    garantia = Garantia()
    garantia.contrato = contrato
    form = GarantiaForm(request.POST or None, request.FILES or None, instance=garantia)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr('..', 'Garantia adicionada com sucesso.')
    return locals()


@rtr()
@login_required
def adicionar_penalidade(request, contrato_id):
    title = 'Adicionar Penalidade'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_penalidade(request):
        raise PermissionDenied
    penalidade = Penalidade()
    penalidade.contrato = contrato
    form = PenalidadeForm(request.POST or None, request.FILES or None, instance=penalidade)
    if form.is_valid():
        form.instance.contrato = contrato
        form.instance.atualizado_por = request.user.get_vinculo()
        form.save()
        return httprr('..', 'Penalidade adicionada com sucesso.')
    return locals()


@rtr()
@login_required
def editar_penalidade(request, penalidade_id):
    title = 'Editar Penalidade'
    penalidade = get_object_or_404(Penalidade, pk=penalidade_id)
    if not penalidade.contrato.pode_gerenciar_penalidade(request):
        raise PermissionDenied
    form = PenalidadeForm(request.POST or None, request.FILES or None, instance=penalidade)
    if form.is_valid():
        form.instance.atualizado_por = request.user.get_vinculo()
        form.save()
        return httprr(f'/contratos/contrato/{penalidade.contrato.id}/?tab=penalidades', 'Penalidade editada com sucesso.')
    return locals()


@rtr()
@login_required
def excluir_penalidade(request, penalidade_id):
    penalidade = get_object_or_404(Penalidade, pk=penalidade_id)
    if not penalidade.contrato.pode_gerenciar_penalidade(request):
        raise PermissionDenied
    contrato_id = penalidade.contrato.id
    penalidade.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/?tab=penalidades', 'Penalidade removida com sucesso.')


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def adicionar_aditivo(request, contrato_id):
    title = 'Adicionar Aditivo'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    termo = Aditivo()
    termo.valor = contrato.valor
    termo.qtd_parcelas = contrato.qtd_parcelas
    termo.data_inicio = contrato.data_inicio
    termo.data_fim = contrato.data_fim
    form = TermoAditivoForm(request.POST or None, request.FILES or None, instance=termo, data_inicio_contrato=contrato.data_inicio)
    if form.is_valid():
        termo = form.save(commit=False)
        contrato.adicionar_termo_aditivo(termo)
        arquivo_up = request.FILES['arquivo_aditivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        if termo.arquivo:
            termo.arquivo.delete()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        termo.arquivo = arquivo
        termo.save()
        arquivo.store(request.user, content)
        return httprr('..', 'Termo aditivo adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_aditivar_contrato')
def excluir_aditivo(request, aditivo_id):
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    contrato_id = aditivo.contrato.id
    aditivo.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Termo aditivo excluído com sucesso.')


@rtr()
@permission_required('contratos.pode_adicionar_fiscal')
def adicionar_fiscal(request, contrato_id):
    title = 'Adicionar Fiscal'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = AdicionaFiscalEmLoteForm(request.POST or None)
    formset = servidor_campus(request.POST or None)
    if form.is_valid() and formset.is_valid():
        for fiscal in formset.forms:
            if fiscal.instance and hasattr(fiscal.instance, 'servidor') and hasattr(fiscal.instance, 'campus'):
                form.instance.id = None
                form.instance.contrato = contrato
                form.instance.servidor = fiscal.instance.servidor
                form.instance.campus = fiscal.instance.campus
                obj = form.save()
                contrato.adicionar_fiscal(obj)
        return httprr('..', 'Fiscal adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_fiscal')
def editar_fiscal(request, fiscal_id):
    title = 'Editar Fiscal'
    instance = get_object_or_404(Fiscal, pk=fiscal_id)
    form = FiscalForm(request.POST or None, instance=instance)
    if form.is_valid():
        fiscal = form.save()
        return httprr(f'/contratos/contrato/{fiscal.contrato.id}/', 'Fiscal editado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_fiscal')
def adicionar_fiscal_aditivo(request, aditivo_id):
    title = 'Adicionar Fiscal'
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    form = FiscalForm(request.POST or None)
    if form.is_valid():
        fiscal = form.save(commit=False)
        fiscal.termo_aditivo = aditivo
        aditivo.contrato.adicionar_fiscal(fiscal)
    return locals()


@rtr()
@login_required
def adicionar_conta(request, contrato_id):
    title = 'Adicionar Conta'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_conta(request):
        raise PermissionDenied
    servidor = request.user.get_relacionamento()
    fiscal = contrato.get_fiscal(servidor=servidor)
    form = ContaContratoForm(request.POST or None, contrato=contrato, fiscal=fiscal, servidor=servidor)
    if form.is_valid():
        form.save()
        return httprr('..', 'Conta adicionada com sucesso.')
    return locals()


@rtr()
@login_required
def editar_conta(request, conta_id):
    title = 'Editar Conta'
    conta = get_object_or_404(ContaContrato, pk=conta_id)
    if not conta.contrato.pode_gerenciar_conta(request):
        raise PermissionDenied
    servidor = request.user.get_relacionamento()
    fiscal = conta.contrato.get_fiscal(servidor=servidor)
    form = EditarContaContratoForm(request.POST or None, instance=conta, fiscal=fiscal, servidor=servidor)
    if form.is_valid():
        form.save()
        return httprr('..', 'Conta atualizada com sucesso.')
    return locals()


@rtr()
@login_required
def deposito_conta(request, medicao_id):
    title = 'Depósito em Conta'
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    contrato = medicao.parcela.cronograma.contrato
    percentuais = ContaVinculadaCalculo.obter_percentuais_para_contrato(contrato)
    perc_13 = percentuais['perc_13']
    perc_ferias = percentuais['perc_ferias']
    perc_fgts = percentuais['perc_fgts']
    perc_sub = percentuais['perc_submodulo']
    perc_13_display = ContaVinculadaCalculo.formatar_percentual_display(perc_13)
    perc_ferias_display = ContaVinculadaCalculo.formatar_percentual_display(perc_ferias)
    perc_fgts_display = ContaVinculadaCalculo.formatar_percentual_display(perc_fgts)
    perc_sub_display = ContaVinculadaCalculo.formatar_percentual_display(perc_sub)
    if not contrato.pode_gerenciar_conta(request):
        raise PermissionDenied
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    form = DepositoContaContratoForm(request.POST or None, contrato=contrato, medicao=medicao, fiscal=fiscal)
    if form.is_valid():
        form.save()
        return httprr('..', 'Depósito adicionado com sucesso.')
    return locals()


@rtr()
@login_required
def saque_conta(request, conta_id):
    title = 'Saque em Conta'
    conta = get_object_or_404(ContaContrato, pk=conta_id)
    if not conta.contrato.pode_gerenciar_conta(request):
        raise PermissionDenied
    servidor = request.user.get_relacionamento()
    fiscal = conta.contrato.get_fiscal(servidor=servidor)
    form = SaqueContaContratoForm(request.POST or None, conta=conta, fiscal=fiscal, servidor=servidor, deposito=False)
    if form.is_valid():
        form.save()
        return httprr('..', 'Saque adicionado com sucesso.')
    return locals()


@rtr()
@login_required
def editar_movimentacao(request, movimentacao_id):
    title = 'Editar Movimentação'
    movimentacao = get_object_or_404(MovimentacaoContaContrato, pk=movimentacao_id)
    if not movimentacao.conta.contrato.pode_gerenciar_conta(request):
        raise PermissionDenied
    fiscal = movimentacao.conta.contrato.get_fiscal(servidor=request.user.get_relacionamento())
    form = EditarMovimentacaoContaContratoForm(request.POST or None, instance=movimentacao, fiscal=fiscal)
    if form.is_valid():
        form.save()
        return httprr('..', 'Movimentação atualizada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_publicacao')
def adicionar_publicacao(request, contrato_id):
    title = 'Adicionar Publicação'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = PublicacaoContratoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo_up = request.FILES['arquivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        publicacao = PublicacaoContrato()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        publicacao.contrato = contrato
        publicacao.data = form.cleaned_data['data']
        publicacao.numero = form.cleaned_data['numero']
        publicacao.descricao = form.cleaned_data['descricao']
        publicacao.tipo = form.cleaned_data['tipo']
        publicacao.arquivo = arquivo
        publicacao.save()
        arquivo.store(request.user, content)
        contrato.adicionar_publicacao(publicacao)
        return httprr('..', 'Publicação adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_publicacao')
def editar_publicacao(request, publicacao_id):
    title = 'Editar Publicação'
    instance = get_object_or_404(PublicacaoContrato, pk=publicacao_id)
    initial = {
        'contrato': instance.contrato,
        'data': instance.data,
        'numero': instance.numero,
        'descricao': instance.descricao,
        'tipo': instance.tipo.id,
    }
    form = EditarPublicacaoContratoForm(request.POST or None, request.FILES or None, initial=initial)
    if form.is_valid():
        publicacao = instance
        pessoa = request.user.get_profile()
        publicacao.data = form.cleaned_data['data']
        instance.numero = form.cleaned_data['numero']
        instance.descricao = form.cleaned_data['descricao']
        instance.tipo = form.cleaned_data['tipo']
        publicacao.save()
        return httprr(f'/contratos/contrato/{publicacao.contrato.id}/', 'Publicação editada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_publicacao')
def adicionar_publicacao_aditivo(request, aditivo_id):
    title = 'Adicionar Publicação'
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    form = PublicacaoAditivoForm(request.POST or None)
    if form.is_valid():
        publicacao = form.save(commit=False)
        aditivo.adicionar_publicacao(publicacao)
        PublicacaoContrato.objects.get_or_create(
            tipo=publicacao.tipo, contrato=aditivo.contrato, numero=publicacao.numero, data=publicacao.data, descricao=publicacao.descricao
        )
        return httprr(f'/contratos/aditivo/{aditivo.id}/', 'Publicação adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_publicacao')
def editar_publicacao_aditivo(request, publicacao_id):
    title = 'Editar Publicação de Aditivo'
    instance = get_object_or_404(PublicacaoAditivo, pk=publicacao_id)
    form = PublicacaoAditivoForm(request.POST or None, instance=instance)
    if form.is_valid():
        publicacao = form.save()
        return httprr(f'/contratos/aditivo/{instance.aditivo.id}/', 'Publicação editada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_excluir_publicacao')
def excluir_publicacao_aditivo(request, publicacao_id):
    instance = get_object_or_404(PublicacaoAditivo, pk=publicacao_id)
    contrato_id = instance.aditivo.contrato.id
    instance.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Publicação excluída com sucesso.')


@rtr()
@permission_required('contratos.pode_adicionar_anexo')
def adicionar_anexo(request, contrato_id):
    title = 'Adicionar Anexo'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    anexo = AnexoContrato()
    anexo.contrato = contrato
    form = AnexoContratoForm(request.POST or None, request.FILES or None, instance=anexo, contrato=contrato)
    if form.is_valid():
        arquivo_up = request.FILES['anexo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        anexo.arquivo = arquivo
        anexo.save()
        arquivo.store(request.user, content)
        contrato.adicionar_anexo(anexo)
        return httprr('..', 'Anexo adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_adicionar_anexo')
def editar_anexo(request, anexo_id):
    title = 'Editar Anexo'
    anexo = get_object_or_404(AnexoContrato, pk=anexo_id)
    form = AnexoContratoForm(request.POST or None, request.FILES or None, instance=anexo, user=request.user)
    if form.is_valid():
        anexo = form.save(commit=False)
        arquivo_up = request.FILES.get('anexo')
        if arquivo_up:
            nome = arquivo_up.name
            pessoa = request.user.get_vinculo()
            if anexo.arquivo:
                anexo.arquivo.delete()
            arquivo = Arquivo()
            arquivo.save(nome, pessoa)
            anexo.arquivo = arquivo
        anexo.save()
        if arquivo_up:
            arquivo_up.seek(0)
            content = arquivo_up.read()
            arquivo.store(request.user, content)
        return httprr(f'/contratos/contrato/{anexo.contrato.id}/?tab=5', 'Anexo atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_gerar_cronograma')
def definir_cronograma(request, contrato_id):
    title = 'Cronograma'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = CronogramaForm(request.POST or None)
    if form.is_valid():
        cronograma = form.save(commit=False)
        contrato.set_cronograma(cronograma)
        return httprr('..', 'Número de cronograma definido com sucesso. As parcelas necessitam ser geradas.')
    return locals()


@rtr()
@permission_required('contratos.pode_gerar_cronograma')
def atualizar_parcela(request, parcela_id, contrato_id):
    title = 'Atualizar Parcela'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    parcela = get_object_or_404(Parcela, pk=parcela_id)
    form = ParcelaForm(request.POST or None, instance=parcela)
    form.set_contrato(contrato)
    if form.is_valid():
        temp = form.save(commit=False)
        parcela.data_prevista_inicio = temp.data_prevista_inicio
        parcela.data_prevista_fim = temp.data_prevista_fim
        if form.cleaned_data.get('valor_previsto'):
            parcela.valor_previsto = temp.valor_previsto
        parcela.save()
        return httprr('..', 'Parcela atualizada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_gerar_cronograma')
def adicionar_parcela(request, contrato_id):
    title = 'Adicionar Parcela'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if contrato.get_cronograma() is None:
        return httprr('..', 'Contrato não possui número de cronograma definido.')
    parcela = Parcela()
    parcela.data_prevista_inicio = contrato.data_inicio
    parcela.data_prevista_fim = somar_dias(contrato.data_inicio, 30)
    parcela.valor_previsto = contrato.get_saldo_atual()
    form = ParcelaForm(request.POST or None, instance=parcela, contrato=contrato)
    form.set_contrato(contrato)
    if form.is_valid():
        parcela = form.save(commit=False)
        contrato.get_cronograma().adicionar_parcela(parcela)
        return httprr('..', 'Parcela adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_gerar_cronograma')
def gerar_parcelas(request, contrato_id):
    title = 'Gerenciar Parcelas'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if contrato.get_cronograma() is None:
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Contrato não possui número de cronograma definido.')

    initial = []
    data = contrato.data_inicio
    data_inicial = data
    qtd_parcelas = request.GET.get('parcelas', contrato.qtd_parcelas) or 0

    if 'data' in request.GET:
        try:
            data = datetime.strptime(request.GET['data'], '%d/%m/%Y')
        except Exception:
            data = contrato.data_inicio
    for _i in range(1, int(qtd_parcelas) + 1):
        vencimento = proximo_mes(data)
        initial.append(
            {
                'data_prevista_inicio': data,
                'data_prevista_fim': somar_dias(vencimento, -1),
                'valor_previsto': contrato.get_saldo_atual() / int(qtd_parcelas),
            }
        )
        data = vencimento

    formset = ParcelaContratoFormSet(request.POST or None, initial=initial)
    for form in formset.forms:
        form.set_contrato(contrato)
    if formset.is_valid():
        for form in formset.forms:
            parcela = form.save(commit=False)
            contrato.get_cronograma().adicionar_parcela(parcela)
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Parcelas geradas com sucesso.')
    return locals()


@rtr()
@group_required('Gerente de Contrato')
def configurar_medicao(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    title = f'Configurar Medição - {contrato.numero}'
    tipos_documentos_do_contrato = ContratoTipoDocumentoComprobatorio.objects.filter(contrato__id=contrato.pk).order_by('id')
    form = ContratoTiposDocumentosComprobatorioForm(request.POST or None, contrato=contrato)
    if form.is_valid():
        form.save()
        return httprr(f'/contratos/configurar_medicao/{contrato.id}/', 'Tipo de documento comprobatório adicionado ao contrato.')

    return locals()


@group_required('Gerente de Contrato')
def excluir_tipo_documento_contrato(request, contrato_id, tipo_documento_contrato_id):
    tipo_documento_contrato = get_object_or_404(ContratoTipoDocumentoComprobatorio, pk=tipo_documento_contrato_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if MedicaoTipoDocumentoComprobatorio.objects.filter(
        medicao__parcela__cronograma__contrato=contrato, tipo_documento_comprobatorio=tipo_documento_contrato.tipo_documento_comprobatorio
    ).exists():
        return httprr(
            f'/contratos/configurar_medicao/{contrato.id}/',
            'Você não pode excluir este tipo de documento pois já está vinculado a uma medição.',
            tag='warning',
        )
    tipo_documento_contrato.delete()
    return httprr(f'/contratos/configurar_medicao/{contrato.id}/', 'Tipo de documento comprobatório excluído para este contrato.')


@permission_required('contratos.pode_gerar_cronograma')
def excluir_parcela(request, parcela_id, contrato_id):
    parcela = get_object_or_404(Parcela, pk=parcela_id)
    if parcela.medicoes.all().exists():
        return httprr(f'/contratos/contrato/{contrato_id}/?tab=cronograma#parcela_{parcela_id}', 'Você não pode excluir uma parcela com medição.')
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    parcela.delete()
    return httprr(f'/contratos/contrato/{contrato.id}/', 'Parcela excluída com sucesso.')


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
def sem_medicao(request, parcela_id, contrato_id):
    parcela = get_object_or_404(Parcela, pk=parcela_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not (contrato.eh_fiscal(request.user.get_relacionamento()) or parcela.cronograma.contrato == contrato):
        raise ValidationError('Você não é fiscal desse contrato.')
    if parcela.sem_medicao:
        parcela.sem_medicao = False
    else:
        parcela.sem_medicao = True
    parcela.save()
    return httprr(f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{parcela_id}', 'Parcela sem medição informada com sucesso.')


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def informar_imr(request, parcela_id, contrato_id):
    title = 'Instrumento de Medição de Resultado'
    parcela = get_object_or_404(Parcela, pk=parcela_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    form = IMRForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.instance.parcela = parcela
        form.instance.fiscal = fiscal
        form.save()
        return httprr('..', 'Instrumento de medição de resultado registrado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def editar_imr(request, imr_id, contrato_id):
    title = 'Instrumento de Medição de Resultado'
    imr = get_object_or_404(IMR, pk=imr_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    form = IMRForm(request.POST or None, request.FILES or None, instance=imr)
    if form.is_valid():
        form.save()
        return httprr('..', 'Instrumento de medição de resultado atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def excluir_imr(request, imr_id, contrato_id):
    imr = get_object_or_404(IMR, pk=imr_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    if not fiscal.tipo.pode_gerenciar_todas_medicoes_contrato:
        return httprr(f'/contratos/contrato/{contrato_id}/?tab=cronograma', 'Você não tem permissão para excluir esse IMR.')
    imr.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/?tab=cronograma', 'IMR excluído com sucesso.')


def _get_form_class_medicao(contrato: Contrato) -> tuple[type[MedicaoForm], str]:
    """Form da medição e o tipo do contrato: ``MedicaoEletricaForm``/``'eletrico'`` para energia elétrica."""
    tipo_contrato_eletrico = Configuracao.get_valor_por_chave('contratos', 'tipo_contrato_energia_eletrica')
    if tipo_contrato_eletrico and contrato.subtipo and contrato.subtipo_id == int(tipo_contrato_eletrico):
        return MedicaoEletricaForm, 'eletrico'
    return MedicaoForm, ''


def _get_formset_empenhos_medicao(request: HttpRequest, contrato: Contrato) -> BaseInlineFormSet | None:
    """Formset dos empenhos que pagam a medição; ``None`` quando o contrato permite medir sem empenho."""
    if contrato.permite_medicao_sem_empenho:
        return None
    FormFormset = DocumentoEmpenhoContratoMedicaoForm
    FormFormset.contrato = contrato
    empenho_medicao = inlineformset_factory(
        Medicao,
        DocumentoEmpenhoContratoMedicao,
        fields=['documento_empenho_contrato', 'valor'],
        can_delete=False,
        extra=0,
        form=FormFormset,
        formset=DocumentoEmpenhoContratoMedicaoInlineFormSet,
        min_num=1,
    )
    return empenho_medicao(request.POST or None)


def _salvar_medicao_com_arquivo(request: HttpRequest, medicao: Medicao) -> None:
    """Grava a medição com o arquivo enviado em ``arquivo_medicao``."""
    arquivo_medicao_up = request.FILES['arquivo_medicao']
    arquivo_medicao_up.seek(0)
    content_medicao = arquivo_medicao_up.read()
    if medicao.arquivo:
        medicao.arquivo.delete()
    arquivo_medicao = Arquivo()
    arquivo_medicao.save(arquivo_medicao_up.name, request.user.get_vinculo())
    medicao.arquivo = arquivo_medicao
    medicao.save()
    arquivo_medicao.store(request.user, content_medicao)


def _vincular_empenhos_medicao(formset: BaseInlineFormSet | None, medicao: Medicao) -> None:
    """Vincula à medição os empenhos do formset (já validado)."""
    if formset is None:
        return
    for form_empenho_medicao in formset.forms:
        if form_empenho_medicao.cleaned_data:
            documento_empenho_contrato_medicao = form_empenho_medicao.instance
            documento_empenho_contrato_medicao.medicao = medicao
            documento_empenho_contrato_medicao.save()
            medicao.documentos_empenho_medicao.add(documento_empenho_contrato_medicao)


def _registrar_documentos_comprobatorios(contrato: Contrato, medicao: Medicao, cleaned_data: dict) -> None:
    """Registra a conferência do fiscal para cada documento comprobatório exigido pelo contrato."""
    for field_conf in ContratoTipoDocumentoComprobatorio.objects.filter(contrato__pk=contrato.id):
        name_field_esperado = f'field_name_{field_conf.tipo_documento_comprobatorio.id}'
        if name_field_esperado in cleaned_data:
            MedicaoTipoDocumentoComprobatorio.objects.get_or_create(
                medicao=medicao,
                tipo_documento_comprobatorio=TipoDocumentoComprobatorio.objects.get(pk=field_conf.tipo_documento_comprobatorio.id),
                confirmacao_fiscal=cleaned_data.get(name_field_esperado) or MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA,
            )


def _registrar_medicao_eletrica(medicao: Medicao, cleaned_data: dict) -> None:
    """Grava os dados de consumo da medição de energia elétrica e registra a ocorrência de multa, se houver."""
    campos = (
        'ano_referencia',
        'mes_referencia',
        'consumo_ponta',
        'consumo_fora_ponta',
        'demanda_contratada',
        'demanda_medida',
        'valor_multa_excedente',
    )
    MedicaoEletrica.objects.update_or_create(medicao=medicao, defaults={campo: cleaned_data.get(campo) for campo in campos})

    if medicao.medicaoeletrica.deve_solicitar_valor_multa():
        medicao.ocorrencia = f"""Ocorreu ultrapassagem do contrato de demanda de potência/Total ultrapassado = {medicao.medicaoeletrica.demanda_ultrapassada} kW,
                Multa por ultrapassagem = R$ {cleaned_data.get('valor_multa_excedente')}. O fiscal do contrato deverá avaliar se
                há necessidade de ajustar a demanda de potência contratada."""
        medicao.save()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
@atomic()
def efetuar_medicao(request: HttpRequest, parcela_id: int, contrato_id: int, imr_id: int | None = None) -> HttpResponse | dict:
    """Registra a medição da parcela; com o formset de empenhos inválido nada é gravado e a tela volta com os erros."""
    title = 'Efetuar Medição'
    parcela = get_object_or_404(Parcela, pk=parcela_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    imr = get_object_or_404(IMR, pk=imr_id) if imr_id else None
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    FormClass, tipo_contrato = _get_form_class_medicao(contrato)

    form = FormClass(request.POST or None, request.FILES or None, parcela=parcela, request=request, imr=imr)
    formset = _get_formset_empenhos_medicao(request, contrato)
    form_valido = form.is_valid()
    formset_valido = formset is None or formset.is_valid()
    if form_valido and formset_valido:
        medicao = form.save(commit=False)
        medicao.fiscal = fiscal
        medicao.data_medicao = date.today()
        medicao.parcela = parcela
        _salvar_medicao_com_arquivo(request, medicao)
        _vincular_empenhos_medicao(formset, medicao)
        _registrar_documentos_comprobatorios(contrato, medicao, form.cleaned_data)
        if tipo_contrato == 'eletrico':
            _registrar_medicao_eletrica(medicao, form.cleaned_data)
        return httprr('..', anchor=f'parcela_{parcela_id}', message='Medição realizada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
@atomic()
def atualizar_medicao(request, medicao_id, contrato_id):
    title = 'Atualizar Medição'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    # é o mesmo fiscal que fez a medição?
    pode_gerenciar_todas_medicoes = fiscal.tipo.pode_gerenciar_todas_medicoes_contrato
    if fiscal.servidor != medicao.fiscal.servidor and not pode_gerenciar_todas_medicoes:
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}'.format(contrato.id),
            'Somente o fiscal que registrou a medição tem permissão para alterá-la.',
        )

    tipo_contrato = ''
    tipo_contrato_eletrico = Configuracao.get_valor_por_chave('contratos', 'tipo_contrato_energia_eletrica')
    if tipo_contrato_eletrico and contrato.subtipo and contrato.subtipo.pk == int(tipo_contrato_eletrico):
        FormClass = MedicaoEletricaForm
        tipo_contrato = 'eletrico'
    else:
        FormClass = MedicaoForm

    form = FormClass(request.POST or None, request.FILES or None, parcela=medicao.parcela, instance=medicao, request=request)
    FormFormset = DocumentoEmpenhoContratoMedicaoForm
    FormFormset.contrato = contrato
    empenho_medicao = inlineformset_factory(
        Medicao,
        DocumentoEmpenhoContratoMedicao,
        fields=['documento_empenho_contrato', 'valor'],
        extra=0,
        form=FormFormset,
        formset=DocumentoEmpenhoContratoMedicaoInlineFormSet,
        min_num=1,
    )
    formset = empenho_medicao(request.POST or None, instance=medicao)
    if form.is_valid() and formset.is_valid():
        medicao = form.save(commit=False)
        medicao.fiscal = fiscal
        medicao.data_medicao = date.today()

        arquivo_up = request.FILES.get('arquivo_medicao')
        arquivo = None
        arquivo_antigo = None
        if arquivo_up:
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()

            if medicao.arquivo:
                arquivo_antigo = medicao.arquivo

            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            medicao.arquivo = arquivo

        medicao.save()
        for form_empenho_medicao in formset.forms:
            if form_empenho_medicao.cleaned_data:
                documentos_empenho_contrato_medicao = form_empenho_medicao.instance
                if form_empenho_medicao.cleaned_data.get('DELETE'):
                    if documentos_empenho_contrato_medicao.pk is not None:
                        documentos_empenho_contrato_medicao.delete()
                else:
                    documentos_empenho_contrato_medicao.medicao = medicao
                    documentos_empenho_contrato_medicao.save()
                    medicao.documentos_empenho_medicao.add(documentos_empenho_contrato_medicao)

        if arquivo_up and arquivo:
            arquivo_up.seek(0)
            content = arquivo_up.read()
            arquivo.store(request.user, content)

        # Remomovendo o antigo arquivo. É importante que essa operaçao seja feito por último,
        # após a medição ter sido salva e apontar pra outro arquivo, para evitar que a medição
        # seja removida (pelo relaciomamento "CASCADE") e cadastrada novamente com o mesmo id.
        if arquivo_antigo:
            arquivo_antigo.delete()

        if ContratoTipoDocumentoComprobatorio.objects.filter(contrato__pk=contrato.id).exists():
            for field_conf in ContratoTipoDocumentoComprobatorio.objects.filter(contrato__pk=contrato.id):
                name_field_esperado = f'field_name_{field_conf.tipo_documento_comprobatorio.id}'
                id_tipo_doc = 0
                if name_field_esperado in form.cleaned_data:
                    id_tipo_doc = field_conf.tipo_documento_comprobatorio.id
                else:
                    return httprr(
                        f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}',
                        'Por favor, selecione um tipo de documento comprobatório.',
                        'error',
                    )
                medicao_tipo_doc = MedicaoTipoDocumentoComprobatorio.objects.filter(
                    medicao__id=medicao.id, tipo_documento_comprobatorio__id=TipoDocumentoComprobatorio.objects.get(pk=id_tipo_doc).id
                ).first()
                if medicao_tipo_doc:
                    medicao_tipo_doc.confirmacao_fiscal = (
                        form.cleaned_data.get(name_field_esperado) or MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA
                    )
                    medicao_tipo_doc.save()
                else:
                    # Se o tipo foi adicionado ao contrato após a criação da medição,
                    # criamos o registro na própria atualização para permitir salvar
                    medicao_tipo_doc = MedicaoTipoDocumentoComprobatorio.objects.create(
                        medicao=medicao,
                        tipo_documento_comprobatorio=TipoDocumentoComprobatorio.objects.get(pk=id_tipo_doc),
                        confirmacao_fiscal=(form.cleaned_data.get(name_field_esperado) or MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA),
                    )
        if tipo_contrato == 'eletrico':
            kwargs = {
                'ano_referencia': form.cleaned_data.get('ano_referencia'),
                'mes_referencia': form.cleaned_data.get('mes_referencia'),
                'consumo_ponta': form.cleaned_data.get('consumo_ponta'),
                'consumo_fora_ponta': form.cleaned_data.get('consumo_fora_ponta'),
                'demanda_contratada': form.cleaned_data.get('demanda_contratada'),
                'demanda_medida': form.cleaned_data.get('demanda_medida'),
                'valor_multa_excedente': form.cleaned_data.get('valor_multa_excedente'),
            }
            MedicaoEletrica.objects.update_or_create(medicao=medicao, defaults=kwargs)

            if medicao.medicaoeletrica.deve_solicitar_valor_multa():
                medicao.ocorrencia = f"""Ocorreu ultrapassagem do contrato de demanda de potência/Total ultrapassado = {medicao.medicaoeletrica.demanda_ultrapassada} kW,
                Multa por ultrapassagem = R$ {form.cleaned_data.get('valor_multa_excedente')}. O fiscal do contrato deverá avaliar se
                há necessidade de ajustar a demanda de potência contratada."""
                medicao.save()
        return httprr(f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}', 'Medição atualizada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
def historico_medicao(request, medicao_id):
    title = 'Histórico da Medição'
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    historico = json.loads(medicao.historico_medicao)
    calculos_conta_vinculada = medicao.get_calculos_conta_vinculada()
    return locals()


@permission_required('contratos.pode_efetuar_medicao')
def exportar_calculo_conta_vinculada_xls(request, calculo_id):
    calculo = get_object_or_404(
        ContaVinculadaCalculo.objects.select_related('contrato', 'medicao', 'usuario').prefetch_related('itens__maodeobra'), pk=calculo_id
    )
    contrato = calculo.contrato or (calculo.medicao.parcela.cronograma.contrato if calculo.medicao else None)
    if not contrato:
        raise PermissionDenied

    eh_gestor = request.user.eh_servidor and contrato.eh_gestor_contrato(request.user.get_relacionamento())
    if not request.user.has_group_cached('Gerente de Contrato') and not eh_gestor and not contrato.pode_gerenciar_conta(request):
        raise PermissionDenied

    rows = [
        ['Cálculo', calculo.id],
        ['Contrato', str(calculo.contrato or '-')],
        ['Medição', str(calculo.medicao or '-')],
        ['Data', calculo.data_criacao.strftime('%d/%m/%Y %H:%M') if calculo.data_criacao else '-'],
        ['Usuário', str(calculo.usuario_display)],
        ['Total', str(calculo.valor_total or '')],
        ['Justificativa', str(calculo.justificativa_display)],
        ['Percentuais', calculo.percentuais_utilizados_display or '-'],
        ['Fonte', ContaVinculadaCalculo.FONTE_PERCENTUAIS],
        [],
        ['Trabalhador', 'Base de cálculo', '13º', 'Férias + 1/3', 'FGTS', 'Submódulo 4.1', 'Total', 'Tipo', 'Justificativa'],
    ]

    for item in calculo.itens.all():
        rows.append(
            [
                str(item.maodeobra or '-'),
                str(item.salario or ''),
                str(item.valor_13 or ''),
                str(item.valor_ferias or ''),
                str(item.valor_fgts or ''),
                str(item.valor_submodulo or ''),
                str(item.total_item or ''),
                str(item.get_tipo_display()),
                str(item.justificativa or ''),
            ]
        )
    return XlsResponse(rows)


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def conferencia_documentos(request, medicao_id, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    title = f'Conferência de Documentos: {medicao}'
    medicoes = medicao.documentos_comprobatorios.all()
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def adicionar_ocorrencia_medicao(request, medicao_id, contrato_id):
    title = 'Informar Ocorrência na Medição'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    eh_servidor = request.user.eh_servidor
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    # é o mesmo fiscal que fez a medição?
    pode_gerenciar_todas_medicoes = fiscal.tipo.pode_gerenciar_todas_medicoes_contrato
    if fiscal.servidor != medicao.fiscal.servidor and not pode_gerenciar_todas_medicoes:
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}'.format(contrato.id),
            'Somente o fiscal que registrou a medição tem permissão para alterar ou informar ocorrência.',
        )
    form = OcorrenciaMedicaoForm(request.POST or None, instance=medicao)
    if form.is_valid():
        medicao = form.save()
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}',
            'Ocorrência/Providência da Medição atualizada com sucesso.',
        )
    return locals()


@rtr()
@permission_required('contratos.pode_efetuar_medicao')
@verificar_fiscal()
def excluir_medicao(request, medicao_id, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    fiscal = contrato.get_fiscal(servidor=request.user.get_relacionamento())
    pode_gerenciar_todas_medicoes = fiscal.tipo.pode_gerenciar_todas_medicoes_contrato
    if fiscal.servidor != medicao.fiscal.servidor and not pode_gerenciar_todas_medicoes:
        return httprr(f'/contratos/contrato/{contrato.id}/?tab=cronograma', 'Você não tem permissão para excluir essa medição')
    with transaction.atomic():
        qtd_estornos = medicao.registrar_estorno_conta_vinculada_por_exclusao(fiscal=fiscal, servidor=request.user.get_relacionamento())
        medicao.delete()
    if qtd_estornos:
        msg = 'Medição excluída com sucesso e a conta vinculada foi ajustada com estorno automático.'
    else:
        msg = 'Medição excluída com sucesso'
    return httprr(f'/contratos/contrato/{contrato.id}/?tab=cronograma#parcela_{medicao.parcela.id}', msg)


# TODO: A chamada para esta função foi removida na demanda 850, tendo em vista que o despacho agora é gerado como documento nato-digital
@rtr()
def despacho_medicao(request, medicao_id, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    parcela = medicao.parcela
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    dia = medicao.data_medicao.day
    mes = meses[medicao.data_medicao.month - 1]
    ano = medicao.data_medicao.year

    key = medicao.fiscal.servidor.setor.uo.setor.sigla
    mapa = {}
    for campus in UnidadeOrganizacional.objects.suap().all():
        mapa[campus.setor.sigla] = {'endereco': campus.endereco, 'cidade': campus.municipio}
    endereco = mapa[key]['endereco']
    cidade = mapa[key]['cidade']
    return locals()


@group_required('Fiscal de Contrato')
@verificar_fiscal()
def gerar_despacho_documentotexto(request, medicao_id, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    # Instanciar modelo de documento texto
    modelo = None
    try:
        modelo = ModeloDocumento.objects.get(nome='Relatório Circustanciado de Recebimento Provisório')
    except Exception:
        messages.error(request, 'Não existe o modelo de documento texto com nome de "Relatório Circustanciado de Recebimento Provisório".')
        return httprr(f'/contratos/contrato/{contrato_id}/')

    user = request.user

    docs_medicao = medicao.documentos_comprobatorios.select_related('tipo_documento_comprobatorio')
    tabela_documentos_comprobatorios = Medicao.montar_tabela_documentos_comprobatorios(
        docs_medicao=docs_medicao,
        titulo_coluna_status='Recebido?',
        status_getter=lambda doc: f'<p style="text-align:center">{doc.confirmacao_fiscal_display}</p>',
        mensagem_vazia='Nenhum checklist de fiscalização foi cadastrado para esta medição.',
    )

    assunto = 'Relatório de Recebimento Provisório - contrato {} - medição de {} até {}'.format(
        contrato.numero, medicao.data_inicio.strftime('%d/%m/%Y'), medicao.data_fim.strftime('%d/%m/%Y')
    )
    setor_dono = get_setor(user)

    # Tags do modelo
    variaveis = {}
    variaveis['cidade_campus_fiscal'] = medicao.campus.municipio if medicao.campus else contrato.campi.first().municipio
    variaveis['numero_processo_medicao_ou_contrato'] = medicao.processo or contrato.processo
    variaveis['contrato_numero'] = contrato.numero
    variaveis['contrato_objeto'] = contrato.objeto
    variaveis['medicao_numero_nota_fiscal'] = medicao.numero_documento
    variaveis['medicao_data_inicial'] = medicao.data_inicio.strftime('%d/%m/%Y')
    variaveis['medicao_data_final'] = medicao.data_fim.strftime('%d/%m/%Y')
    variaveis['nome_contratada'] = contrato.vinculo_contratado.pessoa.nome
    variaveis['cnpj_contratada'] = contrato.vinculo_contratado.pessoa.get_cpf_ou_cnpj()
    variaveis['campus_pluralize'] = nomenclatura.do_campus if medicao.campus or contrato.campi.all().count() == 1 else {nomenclatura.dos_campi}
    variaveis['contrato_sigla_campi'] = medicao.campus or contrato.get_uos_as_string()
    variaveis['artigo_base_legal'] = (
        contrato.base_legal.conformidade_base_legal
        if contrato.base_legal and contrato.base_legal.conformidade_base_legal
        else 'Art. 73 da Lei nº 8.666/93'
    )
    variaveis['medicao_parcela_cronograma'] = medicao.parcela.cronograma.numero
    variaveis['instituicao_sigla'] = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    variaveis['medicao_valor'] = format_money(medicao.valor_executado)
    variaveis['medicao_valor_por_extenso'] = por_extenso(medicao.valor_executado)
    variaveis['contrato_nome_fiscal'] = medicao.fiscal.servidor.pessoa_fisica.nome
    variaveis['contrato_matricula_fiscal'] = medicao.fiscal.servidor.matricula
    variaveis['tabela_documentos_comprobatorios'] = tabela_documentos_comprobatorios
    variaveis['ocorrencias'] = medicao.ocorrencia
    variaveis['providencias'] = medicao.providencia
    total_empenho = 0
    empenhos = []
    for documento_empenho_contrato_medicao in medicao.documentos_empenho_medicao.all():
        empenho = documento_empenho_contrato_medicao.documento_empenho_contrato.empenho
        valor = documento_empenho_contrato_medicao.valor
        total_empenho += valor
        empenhos.append(f'(Unidade Gestora {nomenclatura.campus} {empenho.emitente_ug.uo}) Empenho {empenho.numero}: R$ {format_money(valor)}<br />')
    variaveis['empenhos'] = ''.join(empenhos)
    variaveis['total_empenhos'] = f'TOTAL: R$ {format_money(total_empenho)}'

    if contrato.permite_medicao_sem_empenho:
        variaveis['empenhos'] = 'Não se aplica, pois contrato possui arrecadação de receita.'

    # Se documento ja existe e é rascunho ou concluido cria novamente
    # Se o documento está assinado ou finalizado já mostra documento e exibe uma mensagem que para gerar um novo deve cancelar o antigo
    # Se o documento está cancelado no momento de criar o novo deve adicionar o vinculo do antigo como retifica e depois adicionar a referencia para o novo

    variaveis_correntes = get_variaveis(
        documento_identificador=None,
        estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
        usuario=user,
        setor_dono=setor_dono,
    )

    def gerar_documento():
        hipotese_legal = HipoteseLegal.objects.filter(pk=6).first()
        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user,
            setor_dono=setor_dono,
            modelo=modelo,
            assunto=assunto,
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
            hipotese_legal=hipotese_legal,
            variaveis=variaveis,
        )
        # Vincula o documento digital criado a medição do contrato
        medicao.despacho_documentotexto = documento_novo
        medicao.save()
        return documento_novo

    tag = 'success'
    if not medicao.despacho_documentotexto:
        documento_novo = gerar_documento()
        msg = 'Relatório gerado com sucesso!'
    elif medicao.despacho_documentotexto.estah_em_rascunho or medicao.despacho_documentotexto.estah_concluido:
        documento_novo = medicao.despacho_documentotexto
        variaveis_correntes.update(variaveis)
        documento_novo.corpo = processar_template_ckeditor(texto=modelo.corpo_padrao, variaveis=variaveis_correntes)
        if medicao.despacho_documentotexto.estah_concluido:
            documento_novo.editar_documento()
        documento_novo.save()
        msg = 'Relatório atualizado com sucesso!'
    elif medicao.despacho_documentotexto.estah_aguardando_assinatura:
        documento_novo = medicao.despacho_documentotexto
        msg = f'Este documento está na situação {documento_novo.get_status()} que não permite edição. Para gerar um novo despacho deve-se excluir solicitação da assinatura do documento: {documento_novo.identificador}'
        tag = 'warning'
    elif medicao.despacho_documentotexto.estah_assinado or medicao.despacho_documentotexto.estah_finalizado:
        documento_novo = medicao.despacho_documentotexto
        msg = f'Este documento está na situação {documento_novo.get_status()} que não permite edição. Para gerar um novo despacho favor cancelar este documento: {documento_novo.identificador}'
        tag = 'warning'
    elif medicao.despacho_documentotexto.estah_cancelado:
        documento_antigo = medicao.despacho_documentotexto
        documento_novo = gerar_documento()
        # tipo vinculo - retificação
        tipo_vinculo = TipoVinculoDocumento.objects.get(descricao='Retificação')
        # Vincula documentos
        vinculo_documentos = VinculoDocumentoTexto()
        vinculo_documentos.tipo_vinculo_documento = tipo_vinculo
        vinculo_documentos.documento_texto_base = documento_novo
        vinculo_documentos.documento_texto_alvo = documento_antigo
        vinculo_documentos.usuario_criacao = user
        vinculo_documentos.save()
        # Atualiza referencia da objeto de Medicao
        medicao.despacho_documentotexto = documento_novo
        medicao.save()
        msg = 'Relatório substituído com sucesso!'
    if documento_novo and msg:
        CompartilhamentoDocumentoPessoa.objects.get_or_create(
            vinculo_permitido=user.get_vinculo(), documento=documento_novo, nivel_permissao=NivelPermissao.EDITAR
        )
    return httprr(documento_novo.get_absolute_url(), msg, tag=tag)


@rtr()
@permission_required('contratos.pode_submeter_arquivo')
def upload_contrato(request, contrato_id):
    title = 'Upload de Arquivo'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = UploadArquivoContratoForm(request.POST or None, request.FILES or None, instance=contrato)
    if form.is_valid():
        arquivo_up = request.FILES.get('arquivo_contrato')
        if arquivo_up:
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            if contrato.arquivo:
                contrato.arquivo.delete()
            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            form.instance.arquivo = arquivo
            form.save()
            arquivo.store(request.user, content)
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Arquivo do contrato atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_submeter_arquivo')
def upload_aditivo(request, aditivo_id):
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    form = UploadArquivoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo_up = request.FILES['arquivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        if aditivo.arquivo:
            aditivo.arquivo.delete()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        aditivo.arquivo = arquivo
        aditivo.save()
        arquivo.store(request.user, content)
        return httprr(f'/contratos/aditivo/{aditivo.id}/', 'Termo aditivo enviado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_submeter_arquivo')
def upload_publicacao(request, pub_id, contrato_id):
    title = 'Upload de publicação'
    publicacao = get_object_or_404(PublicacaoContrato, pk=pub_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = UploadArquivoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo_up = request.FILES['arquivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        if publicacao.arquivo:
            publicacao.arquivo.delete()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        publicacao.arquivo = arquivo
        publicacao.save()
        arquivo.store(request.user, content)
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Publicação enviada com sucesso.')
    return locals()


@permission_required('contratos.pode_submeter_medicao')
def notificar_ocorrencia(request, ocorrencia_id):
    ocorrencia = get_object_or_404(Ocorrencia, pk=ocorrencia_id)
    if not ocorrencia.contrato.pode_gerenciar_ocorrencia(request):
        return PermissionDenied
    """ Enviando email, notificando a empresa sobre a ocorrência """
    if not ocorrencia.contrato.vinculo_contratado.email_notificacao:
        return httprr(ocorrencia.contrato.get_absolute_url(), 'O e-mail da contratada não foi informado. Por favor, verifique.', tag='error')

    titulo = '[SUAP] Contratos: Notificação de Ocorrência'
    attachments = []
    if ocorrencia.arquivo:
        content = ocorrencia.arquivo.load(request.user)
        attachments = [(ocorrencia.arquivo.nome, content, 'application/pdf')]
    send_mail(titulo, ocorrencia.get_texto_notificacao(), settings.DEFAULT_FROM_EMAIL, ocorrencia.get_emails_notificar(), attachments=attachments)

    ocorrencia.notificacao_enviada = True
    ocorrencia.save()

    return httprr(ocorrencia.contrato.get_absolute_url(), 'Notificação enviada com sucesso.')


@permission_required('contratos.pode_submeter_medicao')
def pre_visualizar_notificacao_ocorrencia(request, ocorrencia_id):
    ocorrencia = get_object_or_404(Ocorrencia, pk=ocorrencia_id)
    if not ocorrencia.contrato.pode_gerenciar_ocorrencia(request):
        return PermissionDenied
    """ Enviando email, notificando a empresa sobre a ocorrência """
    if not ocorrencia.contrato.vinculo_contratado.email_notificacao:
        return httprr(ocorrencia.contrato.get_absolute_url(), 'O e-mail da contratada não foi informado. Por favor, verifique.', tag='error')

    html = html_email_template(ocorrencia.get_texto_notificacao())
    return HttpResponse(html)


def __upload_arquivo_ocorrencia(request, tipo, ocorrencia_id):
    """Método privado, pois está sendo usado apenas internamente
    Responsável por realizar um upload de arquivo na ocorrencia.
    O upload pode ser da ocorrencia ou da resposta
    :param tipo = ['ocorrencia', 'resposta']
    """
    ocorrencia = get_object_or_404(Ocorrencia, pk=ocorrencia_id)
    if not ocorrencia.contrato.pode_gerenciar_ocorrencia(request):
        return PermissionDenied
    tipo_label = 'Ocorrência' if tipo == 'ocorrencia' else 'Resposta'
    title = f'Upload de Arquivo de {tipo_label}'
    form = UploadArquivoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        if tipo == 'ocorrencia':
            arquivo_up = request.FILES['arquivo']
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            if ocorrencia.arquivo:
                ocorrencia.arquivo.delete()
            ocorrencia.arquivo = arquivo
            ocorrencia.save()
            arquivo.store(request.user, content)
        else:
            ocorrencia.anexo_resposta = request.FILES['arquivo']
            ocorrencia.save()
        return httprr(f'/contratos/contrato/{ocorrencia.contrato.id}/', f'Arquivo de {tipo_label} enviado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_submeter_medicao')
def upload_ocorrencia(request, ocorrencia_id):
    return __upload_arquivo_ocorrencia(request, 'ocorrencia', ocorrencia_id)


@rtr()
@permission_required('contratos.pode_submeter_medicao')
def upload_ocorrencia_resposta(request, ocorrencia_id):
    return __upload_arquivo_ocorrencia(request, 'resposta', ocorrencia_id)


@rtr()
@permission_required('contratos.pode_submeter_arquivo')
def upload_publicacao_aditivo(request, pub_id, aditivo_id):
    publicacao = get_object_or_404(PublicacaoAditivo, pk=pub_id)
    aditivo = get_object_or_404(Aditivo, pk=aditivo_id)
    form = UploadArquivoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo_up = request.FILES['arquivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        if publicacao.arquivo:
            publicacao.arquivo.delete()
        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        publicacao.arquivo = arquivo
        publicacao.save()
        arquivo.store(request.user, content)
        publicacao_contrato = PublicacaoContrato.objects.filter(
            tipo=publicacao.tipo, contrato=aditivo.contrato, numero=publicacao.numero, data=publicacao.data, descricao=publicacao.descricao
        ).first()
        if publicacao_contrato:
            publicacao_contrato.arquivo = arquivo
            publicacao_contrato.save()
        return httprr(f'/contratos/aditivo/{aditivo.id}/', 'Publicação enviada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_submeter_medicao')
@verificar_fiscal()
def upload_medicao(request, medicao_id, contrato_id):
    # TODO: verificar se somente quem fez a medição pode submeter
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    title = f'Enviar Arquivo - Número do Documento: {medicao.numero_documento} (Contrato: {contrato})'
    form = UploadArquivoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo_up = request.FILES['arquivo']
        arquivo_up.seek(0)
        content = arquivo_up.read()
        nome = arquivo_up.name
        vinculo = request.user.get_vinculo()
        if medicao.arquivo:
            medicao.arquivo.delete()

        arquivo = Arquivo()
        arquivo.save(nome, vinculo)
        medicao.arquivo = arquivo
        medicao.save()
        arquivo.store(request.user, content)
        return httprr(f'/contratos/contrato/{contrato.id}/', 'Anexo enviado com sucesso.')
    return locals()


def visualizar_arquivo_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    arquivo = contrato.arquivo_contrato
    try:
        response = HttpResponse(arquivo.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'filename=contrato.pdf'
        arquivo.close()
        return response
    except Exception:
        return HttpResponse('O arquivo solicitado foi adulterado ou não existe.')


def visualizar_arquivo(request, arquivo_id):
    arquivo = get_object_or_404(Arquivo, pk=arquivo_id)
    content = arquivo.load(request.user)
    if content is not None:
        response = HttpResponse(content, content_type=arquivo.get_content_type(content))
        response['Content-Disposition'] = f'inline; filename={get_valid_filename(arquivo.nome)}'
        return response
    else:
        return HttpResponse('O arquivo solicitado foi adulterado ou não existe.')


@rtr()
@permission_required('contratos.pode_visualizar_contrato')
def buscar_contrato_export_to_xls(request, contratos):
    return tasks.buscar_contrato_export_to_xls(contratos)


@rtr('contratos.html')
def contratos_a_serem_aditivados(request):
    cabecalho = 'Contratos a serem Aditivados'
    contratos = Contrato.objects.a_serem_aditivados()
    return locals()


@rtr('contratos.html')
def contratos_a_serem_licitados(request):
    cabecalho = 'Contratos a serem Licitados'
    contratos = Contrato.objects.a_serem_licitados()
    return locals()


@rtr()
def solicitacao_fiscal(request, contrato_id):
    title = 'Geração de Ofício para Solicitação de Fiscal'
    campus = get_uo(request.user).nome
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    hoje = datetime.today()
    dia = hoje.day
    mes = meses[hoje.month - 1]
    ano = hoje.year

    template = get_template('contratos/templates/memorando_solicitacao_fiscal.html')
    html = template.render({'title': title, 'campus': campus, 'contrato': contrato, 'meses': meses, 'hoje': hoje, 'dia': dia, 'mes': mes, 'ano': ano})

    try:
        modelo = ModeloDocumento.objects.get(nome='Ofício de Solicitação de Fiscal')
    except Exception:
        messages.error(request, 'Não existe o modelo de documento texto com nome de "Ofício de Solicitação de Fiscal".')

    user = request.user
    assunto = f'Ofício para Solicitação de Fiscal do Contrato {contrato.numero}'
    setor_dono = get_setor(user)

    documento_novo = DocumentoTexto.adicionar_documento_texto(
        usuario=user, setor_dono=setor_dono, assunto=assunto, modelo=modelo, nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, corpo=html
    )
    # Cria vínculo entre o documento e o contrato
    documento_contrato = DocumentoTextoContrato()
    documento_contrato.documento = documento_novo
    documento_contrato.contrato = contrato
    documento_contrato.save()
    msg = 'Ofício gerado com sucesso!'
    return httprr(documento_novo.get_absolute_url(), msg, 'success')


@rtr()
def gerar_despacho_termo_aditivo(request, termo_id):
    title = 'Geração de Despacho para Termo Aditivo'
    termo = get_object_or_404(Aditivo, pk=termo_id)
    form = DespachoTermoAditivoForm(request.POST or None)
    if form.is_valid():
        memorando = form.cleaned_data['numero_memorando']
        despacho = form.cleaned_data['numero_despacho']
        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        hoje = datetime.today()
        dia = hoje.day
        mes = meses[hoje.month - 1]
        ano = hoje.year
        dia_contrato = termo.contrato.data_inicio.day
        mes_contrato = meses[termo.contrato.data_inicio.month - 1]
        ano_contrato = termo.contrato.data_inicio.year
        return render('despacho_termo_aditivo.html', locals())
    return locals()


@rtr()
def gerar_despacho_fiscal(request, contrato_id):
    title = 'Geração de Despacho para Fiscal'
    campus = get_uo(request.user).nome
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = DespachoFiscalForm(request.POST)
    if form.is_valid():
        servidor = form.cleaned_data['servidor']
        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        hoje = datetime.today()
        dia = hoje.day
        mes = meses[hoje.month - 1]
        ano = hoje.year

        template = get_template('contratos/templates/despacho_fiscal.html')
        html = template.render(
            {
                'title': title,
                'campus': campus,
                'contrato': contrato,
                'servidor': servidor,
                'meses': meses,
                'hoje': hoje,
                'dia': dia,
                'mes': mes,
                'ano': ano,
            }
        )

        try:
            modelo = ModeloDocumento.objects.get(nome='Despacho Simples')
        except Exception:
            messages.error(request, 'Não existe o modelo de documento texto com nome de "Despacho Simples".')

        user = request.user
        assunto = f'Despacho para emissão de Portaria do Fiscal {servidor.pessoa_fisica.nome} do Contrato {contrato.numero}'
        setor_dono = get_setor(user)

        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user, setor_dono=setor_dono, assunto=assunto, modelo=modelo, nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, corpo=html
        )
        # Cria vínculo entre o documento e o contrato
        documento_contrato = DocumentoTextoContrato()
        documento_contrato.documento = documento_novo
        documento_contrato.contrato = contrato
        documento_contrato.save()
        return httprr(documento_novo.get_absolute_url(), 'Despacho gerado com sucesso!')
    return locals()


@rtr()
def solicitacao_publicacao_portaria_fiscal(request, contrato_id):
    title = 'Geração de Ofício para Solicitação de Publicação de Portaria'
    campus = get_uo(request.user).nome
    form = SolicitacaoPublicacaoPortariaFiscalForm(request.POST or None)
    if form.is_valid():
        servidor = form.cleaned_data['servidor']
        contrato = get_object_or_404(Contrato, pk=contrato_id)
        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        hoje = datetime.today()
        dia = hoje.day
        mes = meses[hoje.month - 1]
        ano = hoje.year
        if contrato.processo:
            dia_processo = contrato.processo.data_cadastro.day
            mes_processo = meses[contrato.processo.data_cadastro.month - 1]
            ano_processo = contrato.processo.data_cadastro.year

        template = get_template('contratos/templates/memorando_portaria_fiscal.html')
        html = template.render(
            {
                'title': title,
                'campus': campus,
                'contrato': contrato,
                'servidor': servidor,
                'meses': meses,
                'hoje': hoje,
                'dia': dia,
                'mes': mes,
                'ano': ano,
            }
        )

        try:
            modelo = ModeloDocumento.objects.get(nome='Ofício de Solicitação de Publicação de Portaria')
        except Exception:
            messages.error(request, 'Não existe o modelo de documento texto com nome de "Ofício de Solicitação de Publicação de Portaria".')

        user = request.user
        assunto = f' Ofício para Solicitação de Portaria - Fiscal {servidor.pessoa_fisica.nome} - Contrato {contrato.numero}'
        setor_dono = get_setor(user)

        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user, setor_dono=setor_dono, assunto=assunto, modelo=modelo, nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, corpo=html
        )
        # Cria vínculo entre o documento e o contrato
        documento_contrato = DocumentoTextoContrato()
        documento_contrato.documento = documento_novo
        documento_contrato.contrato = contrato
        documento_contrato.save()
        return httprr(documento_novo.get_absolute_url(), 'Ofício gerado com sucesso!')
    return locals()


@rtr()
def pendencias(request):
    notificador = Notificador()
    title = 'Pendências'
    count = 0

    if request.method == 'POST' and 'contrato_ids' in request.POST:
        for id in request.POST.getlist('contrato_ids'):
            contrato = Contrato.objects.get(pk=id)
            for fiscal in contrato.get_fiscais_atuais():
                titulo_dict = {'numero_contrato': contrato.numero}
                mensagem_dict = {
                    'numero_contrato': contrato.numero,
                    'data_vencimento': contrato.data_vencimento.strftime('%d/%m/%Y'),
                    'campus': fiscal.campus.setor.nome,
                }
                count = count + notificador.notificar(1, None, fiscal.servidor.email_institucional, titulo_dict, mensagem_dict)
        return httprr('/contratos/pendencias/', f'{count:d} notificações de vencimento de contrato enviadas com sucesso.')

    if request.method == 'POST' and 'parcela_ids' in request.POST:
        for id in request.POST.getlist('parcela_ids'):
            parcela = Parcela.objects.get(pk=id)
            contrato = parcela.cronograma.contrato

            for fiscal in contrato.get_fiscais_atuais():
                data_prevista_fim = parcela.data_prevista_fim.strftime('%d/%m/%Y')
                data_prevista_inicio = parcela.data_prevista_inicio.strftime('%d/%m/%Y')
                titulo_dict = {
                    'numero_contrato': contrato.numero,
                    'data_prevista_fim': data_prevista_fim,
                    'data_prevista_inicio': data_prevista_inicio,
                }
                mensagem_dict = {
                    'numero_contrato': contrato.numero,
                    'data_prevista_fim': data_prevista_fim,
                    'data_prevista_inicio': data_prevista_inicio,
                    'campus': fiscal.campus.setor.nome,
                }
                count = count + notificador.notificar(2, None, fiscal.servidor.email_institucional, titulo_dict, mensagem_dict)
        return httprr('/contratos/pendencias/', f'{count:d} notificações de medição de parcela atrasada enviadas com sucesso.')

    form = RelatorioPendenciasForm(request.POST or None)
    if form.is_valid():
        uo = form.cleaned_data.get('campus')
        contratos = Contrato.objects.a_serem_aditivados().filter(campi=uo)
        total_contratos = len(contratos)
        parcelas = Parcela.get_parcelas_nao_medidas(uo=uo)

    return locals()


@rtr()
@login_required
def registrar_ocorrencia(request, contrato_id):
    title = 'Registro de Ocorrência'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_ocorrencia(request):
        raise PermissionDenied
    servidor = request.user.get_relacionamento()
    fiscal = contrato.get_fiscal(servidor=servidor)
    form = OcorrenciaForm(request.POST or None, contrato=contrato)
    if form.is_valid():
        form.instance.contrato = contrato
        form.instance.fiscal = fiscal
        form.instance.servidor = servidor
        form.save()
        return httprr('..', 'Ocorrência registrada com sucesso.')
    return locals()


@rtr()
@login_required
def editar_ocorrencia(request, ocorrencia_id):
    title = 'Editar Ocorrência'
    ocorrencia = get_object_or_404(Ocorrencia, pk=ocorrencia_id)
    if not ocorrencia.contrato.pode_gerenciar_ocorrencia(request):
        raise PermissionDenied
    servidor = request.user.get_relacionamento()
    fiscal = ocorrencia.contrato.get_fiscal(servidor=servidor)
    form = OcorrenciaForm(request.POST or None, instance=ocorrencia)
    if form.is_valid():
        form.instance.fiscal = fiscal
        form.instance.servidor = servidor
        form.save()
        return httprr('..', 'Ocorrência editada com sucesso.')
    return locals()


@rtr()
def rol_responsabilidade_fiscais(request):
    title = 'Responsabilidades dos Fiscais'
    return locals()


@rtr()
@group_required('Servidor')
def visualizar_fiscais(request):
    uo = None
    title = 'Fiscais de Contrato'
    fiscais = []
    is_visualizador_sistemico = (
        request.user.is_superuser or request.user.has_group_cached('Auditor') or request.user.has_group_cached('Supervisor de Contratos')
    )
    restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
    if restringir_por_unidade and not is_visualizador_sistemico:
        uo = request.user.get_vinculo().setor.uo
    hoje = datetime.today()
    data = request.GET or None
    if uo and not data:
        data = {'campus': uo.pk}
    form = ConsultaFiscalForm(data)
    if uo:
        form.fields['campus'].queryset = form.fields['campus'].queryset.filter(pk=uo.pk)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        matricula = form.cleaned_data.get('matricula')
        tipo_fiscal = form.cleaned_data.get('tipo_fiscal')
        categoria_servidor = form.cleaned_data.get('categoria_servidor')
        tipo_contrato = form.cleaned_data.get('tipo_contrato')
        subtipo_contrato = form.cleaned_data.get('subtipo_contrato')
        tem_contrato_ativo = form.cleaned_data.get('tem_contrato_ativo')
        exportar_para_xls = form.cleaned_data.get('exportar_para_xls')

        qs = Servidor.objects.filter(fiscal__isnull=False)
        if uo:
            qs = qs.filter(setor__uo=uo)
        elif campus:
            qs = qs.filter(setor__uo=campus)
        if matricula:
            qs = qs.filter(matricula=matricula)
        if tipo_fiscal:
            qs = qs.filter(fiscal__tipo=tipo_fiscal)
        if categoria_servidor and categoria_servidor == form.DOCENTE:
            qs = qs.filter(eh_docente=True)
        elif categoria_servidor and categoria_servidor == form.TECNICO_ADMINISTRATIVO:
            qs = qs.filter(eh_tecnico_administrativo=True)
        if tipo_contrato:
            qs = qs.filter(fiscal__contrato__tipo=tipo_contrato)
        if subtipo_contrato:
            qs = qs.filter(fiscal__contrato__subtipo=subtipo_contrato)
        if tem_contrato_ativo and tem_contrato_ativo == 'sim':
            qs = qs.filter(
                id__in=Fiscal.objects.filter(inativo=False, contrato__cancelado=False, contrato__concluido=False)
                .exclude(data_vigencia__lt=hoje)
                .values_list('servidor', flat=True)
            )
        elif tem_contrato_ativo and tem_contrato_ativo == 'nao':
            qs = qs.exclude(
                id__in=Fiscal.objects.filter(inativo=False, contrato__cancelado=False, contrato__concluido=False)
                .exclude(data_vigencia__lt=hoje)
                .values_list('servidor', flat=True)
            )
        qs = qs.distinct()

        try:
            page = int(request.GET.get('page', '1')) - 1
        except Exception:
            page = 0

        if not exportar_para_xls:
            qs_paginado = qs[page * 50 : page * 50 + 50]
        else:
            qs_paginado = qs

        for item in qs_paginado:
            categoria = 'Docente' if item.eh_docente else 'Técnico Administrativo'
            vezes_que_foi_fiscal = Fiscal.objects.filter(servidor=item)
            tipo = list(vezes_que_foi_fiscal.values_list('tipo__descricao', flat=True).order_by('tipo__descricao').distinct())
            contrato_ativo = vezes_que_foi_fiscal.filter(inativo=False, contrato__cancelado=False, contrato__concluido=False).exclude(
                data_vigencia__lt=hoje
            )
            contratos = list(contrato_ativo.values_list('contrato__pk', flat=True).order_by('contrato__pk').distinct())
            fiscais.append(
                {
                    'servidor_id': item.pk,
                    'nome': item.nome,
                    'matricula': item.matricula,
                    'campus': item.campus,
                    'email': item.email_pessoal,
                    'tipo': tipo,
                    'categoria': categoria,
                    'contrato_ativo': contrato_ativo.exists(),
                    'quantidade': vezes_que_foi_fiscal.values('contrato').distinct().count(),
                }
            )

        if exportar_para_xls:
            return tasks.exportar_fiscais_para_xls(fiscais)
    return locals()


@rtr()
@group_required('Servidor')
def visualizar_contratos_por_fiscal(request, matricula):
    try:
        fiscal = Fiscal.objects.filter(servidor__matricula=matricula)
        servidor = Servidor.objects.get(matricula=matricula)
    except Exception:
        messages.error(request, 'Nenhum fiscal encontrado com o parâmetro informado.')
    title = f'Contratos do Fiscal - {servidor.pessoa_fisica.nome}'
    contratos = Contrato.objects.filter(fiscais__in=fiscal).distinct()
    return locals()


@rtr()
def situacao_contratos(request):
    title = 'Situação dos Contratos'
    form = SituacaoContratosForm(request.POST or None)
    if form.is_valid():
        uo = form.cleaned_data['campus']
        eh_continuado = form.cleaned_data['eh_continuado']
        eh_concluido = form.cleaned_data['eh_concluido']
        data_inicio = form.cleaned_data['data_inicio']
        data_fim = form.cleaned_data['data_fim']
        contratos = Contrato.objects.all().order_by('data_inicio')
        relatorio = []
        if data_inicio and data_fim:
            # TODO: para data fim deverá ser considerado TODOS os aditivos
            contratos = contratos.filter(data_inicio__gt=data_inicio, data_fim__lt=data_fim)

            # selecionou campus?
            if uo:
                contratos = contratos.filter(campi=uo.pk)

            # continuado?
            if eh_continuado:
                contratos = contratos.filter(continuidade=CONTINUIDADE_CONTINUO)

            # concluídos?
            if eh_concluido:
                contratos = contratos.filter(concluido=True)

            # itera contratos e adiciona propriedades em uma lista
            for contrato in contratos:
                contratada = contrato.vinculo_contratado
                cpf_cnpj = contrato.vinculo_contratado.pessoa.get_cpf_ou_cnpj()
                objeto = contrato.objeto
                numero_contrato = contrato.numero
                valor_contrato = contrato.valor
                vigencia_inicio = contrato.data_inicio
                vigencia_fim = contrato.data_fim
                continuidade = contrato.continuidade
                concluido = contrato.concluido

                # lista último termo aditivo de prazo
                qs_ultimo_ta_prazo = contrato.aditivos.all().filter(de_prazo=True)
                ultimo_ta_prazo = None
                if qs_ultimo_ta_prazo:
                    ultimo_ta_prazo = qs_ultimo_ta_prazo.order_by('-data_fim')[0]

                # valor global do contrato (valor inicial + aditivos -> os aditivos serão somados no ultimo_ta_valor)
                valor_global = valor_contrato

                # lista último termo aditivo de valor
                qs_ultimo_ta_valor = contrato.aditivos.all().filter(de_valor=True)
                ultimo_ta_valor = None
                if qs_ultimo_ta_valor:
                    ultimo_ta_valor = qs_ultimo_ta_valor.order_by('-id')[0]

                    # soma os aditivos de valor e joga resultado em valor_global (valor + aditivos)
                    for soma_ta_valor in qs_ultimo_ta_valor:
                        if soma_ta_valor.valor:  # tratando valor None em contratos antigos
                            valor_global = valor_global + soma_ta_valor.valor

                # lista empenhos referente ao contrato
                empenho = contrato.empenho

                # fiscais
                fiscais_nomes = ''
                for fiscais in contrato.fiscais.all():
                    fiscais_nomes = fiscais_nomes + fiscais.servidor.pessoa_fisica.nome + ' / '

                # adiciona a lista
                relatorio.append(
                    {
                        'id': contrato.id,
                        'contratada': contratada,
                        'cpf_cnpj': cpf_cnpj,
                        'objeto': objeto,
                        'numero_contrato': numero_contrato,
                        'valor_contrato': valor_contrato,
                        'vigencia_inicio': vigencia_inicio,
                        'vigencia_fim': vigencia_fim,
                        'ultimo_ta_prazo': ultimo_ta_prazo,
                        'ultimo_ta_valor': ultimo_ta_valor,
                        'valor_global': valor_global,
                        'empenho': empenho,
                        'fiscais_nomes': fiscais_nomes,
                        'continuidade': continuidade,
                        'concluido': concluido,
                    }
                )

            return render('relatorio_situacao_contratos.html', locals())

    return locals()


@rtr()
@login_required()
def relatorio_pendencias_dados(request):
    title = 'Relatório de Pendências'
    form = RelatorioPendenciasForm(request.POST or None)
    contratos_pendentes = {}
    if form.is_valid():
        contratos_pendentes = Contrato.get_pendencias(form.cleaned_data['campus'])
        return render('relatorio_pendencias.html', locals())

    return locals()


@rtr()
@login_required()
@group_required('Fiscal de Contrato, Gerente de Contrato, Auditor')
def relatorio_consumo_energia(request):
    title = f'Relatório de Consumo de Energia Elétrica por {nomenclatura.campus}'
    eh_fiscal = in_group(request.user, 'Fiscal de Contrato')
    eh_gerente = in_group(request.user, 'Gerente de Contrato')
    eh_auditor = in_group(request.user, 'Auditor')
    form = RelatorioConsumoEnergiaForm(request.POST or None, request=request)
    if form.is_valid():
        ano_object = form.cleaned_data['ano']
        medicoes = MedicaoEletrica.objects.filter(ano_referencia=ano_object.ano)
        mes = form.cleaned_data['mes'] if form.cleaned_data.get('mes', False) != '0' else False
        if mes:
            medicoes = medicoes.filter(mes_referencia=mes)
        if form.cleaned_data.get('campus', False):
            medicoes = medicoes.filter(Q(medicao__campus_id=form.cleaned_data['campus'].pk) | Q(medicao__campus_id__isnull=True))
        if medicoes:
            return tasks.relatorio_consumo_energia_xls(medicoes)
        else:
            messages.add_message(request, messages.WARNING, 'Não existem medições de consumo de energia elétrica para o período solicitado.')
    return locals()


@rtr()
@login_required()
@group_required('Fiscal de Contrato, Gerente de Contrato, Auditor')
def relatorio_terceirizados(request):
    title = 'Relatório de Terceirizados '
    eh_gerente = in_group(request.user, 'Gerente de Contrato')
    eh_auditor = in_group(request.user, 'Auditor')
    form = RelatorioTerceirizadosForm(request.POST or None, request=request)
    if form.is_valid():
        contrato = form.cleaned_data['contrato']
        campus = form.cleaned_data['campus']
        situacao_terceirizado = form.cleaned_data.get('situacao_terceirizado')
        situacao_contrato = form.cleaned_data.get('situacao_contrato')
        mascarar_cpfs = form.cleaned_data.get('mascarar_cpfs')
        terceirizados = MaoDeObra.objects.all()
        if campus:
            terceirizados = terceirizados.filter(campus_id=campus)
        if contrato:
            terceirizados = terceirizados.filter(contrato=contrato)

        if situacao_terceirizado:
            if situacao_terceirizado == RelatorioTerceirizadosForm.ATIVO:
                terceirizados = terceirizados.filter(desligamento=None)
            else:
                terceirizados = terceirizados.exclude(desligamento=None)
        if situacao_contrato:
            if situacao_contrato == RelatorioTerceirizadosForm.ATIVO:
                terceirizados = terceirizados.filter(contrato__concluido=False, contrato__cancelado=False)
            elif situacao_contrato == RelatorioTerceirizadosForm.CONCLUIDO:
                terceirizados = terceirizados.filter(contrato__concluido=True)
            else:
                terceirizados = terceirizados.filter(contrato__cancelado=True)

        if terceirizados:
            return tasks.relatorio_terceirizados_xls(terceirizados, mascarar_cpfs)
        else:
            messages.add_message(request, messages.WARNING, 'Não existem terceirizados vinculados aos contratos para o filtro informado.')
    return locals()


@rtr('relatorio_empenhos.html')
@login_required()
@group_required('Fiscal de Contrato, Gerente de Contrato, Auditor')
def relatorio_empenhos(request):
    title = 'Relatório de Empenhos '
    eh_gerente = in_group(request.user, 'Gerente de Contrato')
    eh_auditor = in_group(request.user, 'Auditor')
    contratos_com_empenho = None
    form = RelatorioEmpenhosForm(request.GET or None, request=request)
    if form.is_valid():
        contrato = form.cleaned_data['contrato']
        campus = form.cleaned_data['campus']
        empenho = form.cleaned_data['empenho']
        empresa_cnpj = form.cleaned_data['empresa_cnpj']
        contratos_com_empenho = DocumentoEmpenhoContrato.objects.filter(empenho__tipo=DocumentoBase.TIPO_NE)
        if campus:
            contratos_com_empenho = DocumentoEmpenhoContrato.objects.filter(contrato__campus_gerenciador_id=campus)
            contratos_com_empenho = contratos_com_empenho.filter(contrato__campi__in=[campus])
        if contrato:
            contratos_com_empenho = contratos_com_empenho.filter(contrato__pk=contrato.pk)
        if empenho:
            contratos_com_empenho = contratos_com_empenho.filter(empenho=empenho)
        if empresa_cnpj:
            contratos_com_empenho = contratos_com_empenho.filter(empenho__favorecido_codigo__contains=empresa_cnpj)

        if contratos_com_empenho:
            if request.GET.get('xls'):
                return tasks.relatorio_empenhos_xls(contratos_com_empenho)
        else:
            messages.add_message(request, messages.WARNING, 'Não existem empenhos vinculados aos contratos para os filtros informados.')

    return locals()


@rtr()
def contrato_publico(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    data_vencimento = contrato.data_vencimento
    vence_nos_proximos_90_dias = False
    hoje = datetime.now().date()
    if data_vencimento and data_vencimento > hoje and (data_vencimento < (hoje + timedelta(days=90))):
        vence_nos_proximos_90_dias = True

    aditivos = contrato.get_aditivos()
    apostilamentos = contrato.get_apostilamentos()
    garantias = contrato.garantias.all()
    maosdeobra = contrato.maosdeobra.select_related('prestador_servico__pessoa_fisica').all()
    ocorrencias = contrato.ocorrencias.all().order_by('data')
    title = f'Contrato {contrato.numero}'
    return locals()


@rtr()
def listar_contratos(request):
    title = 'Consulta pública de Contratos'
    category = 'Consultas'
    icon = 'file-contract'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = FiltroContratoForm(request.POST or None)
    contratos = Contrato.objects.all().order_by('-data_vencimento')
    if form.is_valid():
        busca = form.cleaned_data.get('busca')
        if busca:
            or_queries = [Q(**{f'{field_name}__icontains': busca}) for field_name in Contrato.SEARCH_FIELDS]
            contratos = contratos.filter(reduce(or_, or_queries))

        contratada = form.cleaned_data.get('contratada')
        if contratada:
            contratos = contratos.filter(vinculo_contratado=contratada)

        tipo_contrato = form.cleaned_data.get('tipo_contrato')
        if tipo_contrato:
            contratos = contratos.filter(tipo=tipo_contrato)

        subtipo_contrato = form.cleaned_data.get('subtipo_contrato')
        if subtipo_contrato:
            contratos = contratos.filter(subtipo=subtipo_contrato)

        continuidade = form.cleaned_data.get('continuidade')
        if subtipo_contrato:
            contratos = contratos.filter(continuidade=continuidade)

        natureza = form.cleaned_data.get('natureza')
        if natureza:
            contratos = contratos.filter(natureza=natureza)

        base_legal = form.cleaned_data.get('base_legal')
        if base_legal:
            contratos = contratos.filter(base_legal=base_legal)

        mao_obra_exclusiva = form.cleaned_data.get('possui_dedicacao_exclusiva_mao_de_obra')
        if mao_obra_exclusiva:
            mao_obra_exclusiva = mao_obra_exclusiva == 'True'
            contratos = contratos.filter(mao_obra_exclusiva=mao_obra_exclusiva)

        tipo_licitacao = form.cleaned_data.get('tipo_licitacao')
        if tipo_licitacao:
            contratos = contratos.filter(tipo_licitacao=tipo_licitacao)

        concluido = form.cleaned_data.get('concluido')
        if concluido:
            contratos = contratos.filter(concluido=concluido)

        cancelado = form.cleaned_data.get('cancelado')
        if cancelado:
            contratos = contratos.filter(concluido=cancelado)

        campi = form.cleaned_data.get('campi')
        if campi:
            contratos = contratos.filter(campi=campi).distinct()

        periodo_data_inicio = form.cleaned_data.get('periodo_data_inicio')
        if [_f for _f in periodo_data_inicio if _f]:
            contratos = contratos.filter(data_inicio__range=periodo_data_inicio)

        periodo_data_vencimento = form.cleaned_data.get('periodo_data_vencimento')
        if [_f for _f in periodo_data_vencimento if _f]:
            contratos = contratos.filter(data_vencimento__range=periodo_data_vencimento)

    custom_fields = {
        'numero': LinkColumn('contrato_publico', kwargs={'contrato_id': Accessor('pk')}, verbose_name='Número do Contrato'),
        'data_inicio': DateColumn(format='d/m/Y'),
        'data_vencimento': DateColumn(format='d/m/Y'),
    }
    fields = (
        'numero',
        'processo',
        'pregao',
        'tipo_licitacao',
        'campi',
        'vinculo_contratado',
        'concluido',
        'cancelado',
        'data_inicio',
        'data_vencimento',
    )
    sequence = ['numero', 'processo', 'pregao', 'tipo_licitacao', 'data_inicio', 'data_vencimento']
    table = get_table(queryset=contratos, fields=fields, custom_fields=custom_fields, per_page_field=20, sequence=sequence, to_export=False)
    return locals()


@rtr()
def exportacao(request):
    def p(valor):
        if type(valor) is bool:
            return valor and 'Sim' or 'Não'
        return valor and valor or ''

    uo = None
    is_visualizador_sistemico = (
        request.user.is_superuser or request.user.has_group_cached('Auditor') or request.user.has_group_cached('Supervisor de Contratos')
    )
    restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
    if restringir_por_unidade and not is_visualizador_sistemico:
        uo = request.user.get_vinculo().setor.uo
    title = 'Exportação de dados de contrato'
    form = ExportacaoForm(request.POST or None)
    if uo:
        form.fields['campi'].queryset = form.fields['campi'].queryset.filter(pk=uo.pk)
    if form.is_valid():
        tipo = form.cleaned_data.get('tipo', None)
        data_inicio_periodo = form.cleaned_data.get('data_inicio_periodo', None)
        campi = form.cleaned_data.get('campi', None)
        status = form.cleaned_data.get('status', None)
        quadros = form.cleaned_data.get('quadros', [])

        quadro_publicacao = ExportacaoForm.QUADRO_PUBLICACAO in quadros
        quadro_cronograma = ExportacaoForm.QUADRO_CRONOGRAMA in quadros
        quadro_empenhos = ExportacaoForm.QUADRO_EMPENHOS in quadros
        quadro_terceirizados = ExportacaoForm.QUADRO_TERCEIRIZADOS in quadros

        contratos = Contrato.objects.filter(campi__in=form.cleaned_data['campi'])

        if tipo is not None:
            contratos = contratos.filter(tipo=tipo)

        if status is not None:
            if status == ExportacaoForm.STATUS_CONCLUIDO:
                contratos = contratos.filter(concluido=True)
            elif status == ExportacaoForm.STATUS_CANCELADOS:
                contratos = contratos.filter(cancelado=True)
            elif status == ExportacaoForm.STATUS_ANDAMENTO:
                contratos = contratos.exclude(Q(concluido=True) | Q(cancelado=True))

        if data_inicio_periodo is not None and data_inicio_periodo[0] != '':
            contratos = contratos.filter(data_inicio__range=data_inicio_periodo)

        publicacoes = PublicacaoAditivo.objects.filter(aditivo__contrato__in=contratos)
        cronogramas = Cronograma.objects.filter(contrato__in=contratos)
        parcelas = Parcela.objects.filter(cronograma__in=cronogramas)
        if (publicacoes.count() + contratos.count() + cronogramas.count() + parcelas.count()) > 50000:
            return httprr('/contratos/exportacao', 'A exportação só pode emitir até 50.000 registros, por favor refine sua pesquisa.', 'error')

        return tasks.exportar_contratos_xls(contratos, quadro_publicacao, quadro_cronograma, quadro_empenhos, quadro_terceirizados)

    return locals()


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@group_required('Gerente de Contrato')
def listar_documentos_adicionar_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if 'documento_eletronico' not in settings.INSTALLED_APPS:
        raise Exception('A aplicação Documento Eletrônico não está instalada, no entanto, não será possível vincular documentos')

    if not request.user.has_perm('contratos.pode_adicionar_anexo'):
        return httprr(
            reverse_lazy('contrato', current_app='contratos', kwargs={'contrato_id': contrato.id}),
            'Você não tem permissão para vincular documentos ao contrato.',
        )

    # Usado no template para mostrar conteudo especifico do contrato
    is_contrato = True

    title = f'Documentos que podem ser vinculados ao contrato {contrato.numero}'
    setor = get_setor(request.user)
    initial = {'campus': setor.uo_id, 'setor': setor.pk, 'ano': datetime.today().year}
    form = ListarDocumentosTextoForm(request.GET or initial, request=request)
    documentos, documentos_compartilhados, params, order_str = form.processar()

    # Exclusao e ordenacao dos documentos que podem ser adcionados
    documentos_ja_vinculados_ids = DocumentoTextoContrato.objects.filter(contrato=contrato).values_list('documento__id', flat=True)
    documentos_finalizados_ids = DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO).values_list('id', flat=True)
    documentos = documentos.exclude(id__in=documentos_ja_vinculados_ids).filter(id__in=documentos_finalizados_ids)
    documentos = documentos.order_by(
        '-data_criacao', 'identificador_tipo_documento_sigla', 'identificador_numero', 'identificador_ano', 'identificador_setor_sigla'
    )
    return locals()


@rtr()
@group_required('Gerente de Contrato')
def vincular_documento_contrato(request, contrato_id, documento_id):
    # View para adicionar um documento a um contrato
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    if not request.user.has_perm('contratos.pode_adicionar_anexo'):
        return httprr(
            reverse_lazy('contrato', current_app='contratos', kwargs={'contrato_id': contrato.id}),
            'Você não tem permissão para vincular documentos ao contrato.',
        )

    if documento.nivel_acesso == Documento.NIVEL_ACESSO_SIGILOSO:
        raise PermissionDenied

    if not documento.estah_finalizado:
        raise PermissionDenied

    documento_contrato = DocumentoTextoContrato()
    documento_contrato.documento = documento
    documento_contrato.contrato = contrato
    documento_contrato.save()
    return httprr(
        reverse_lazy('contrato', current_app='contratos', kwargs={'contrato_id': contrato.id}), 'Documento vinculado com sucesso ao contrato.'
    )


@rtr()
@group_required('Gerente de Contrato, Operador de Contrato')
def adicionar_arrecadacao_receita(request, contrato_id):
    title = 'Adicionar Valor Concessão'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    arrecadacao = ArrecadacaoReceita()
    arrecadacao.contrato = contrato
    form = ArrecadacaoReceitaForm(request.POST or None, instance=arrecadacao)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr('..', 'Garantia adicionada com sucesso.')
    return locals()


@rtr()
@group_required('Gerente de Contrato, Operador de Contrato')
def editar_arrecadacao(request, arrecadacao_id):
    title = 'Editar Valor de Concessão'
    arrecadacao = get_object_or_404(ArrecadacaoReceita, pk=arrecadacao_id)
    form = ArrecadacaoReceitaForm(request.POST or None, instance=arrecadacao)
    if form.is_valid():
        form.save()
        return httprr(f'/contratos/contrato/{arrecadacao.contrato.id}/', 'Valor de Concessão editado com sucesso.')
    return locals()


@rtr()
@group_required('Gerente de Contrato, Operador de Contrato')
def excluir_arrecadacao(request, arrecadacao_id):
    arrecadacao = get_object_or_404(ArrecadacaoReceita, pk=arrecadacao_id)
    contrato_id = arrecadacao.contrato.id
    arrecadacao.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/', 'Valor da Concessão excluído com sucesso.')


@rtr()
@group_required('Fiscal de Contrato, Gerente de Contrato')
def receber_definitivamente_medicao(request, medicao_id):
    title = 'Receber Definitivamente'
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    contrato = medicao.parcela.cronograma.contrato
    contas_ativas = list(contrato.contas.filter(ativa=True).order_by('descricao', 'id'))
    conta_ativa_unica = contas_ativas[0] if len(contas_ativas) == 1 else None
    conta_retencao_form = None
    if len(contas_ativas) > 1:
        conta_retencao_form = EscolhaContaVinculadaRetencaoForm(
            request.POST or None, contas=contrato.contas.filter(ativa=True).order_by('descricao', 'id')
        )

    if not contrato.pode_gerenciar_recebimento_definitivo(request):
        raise PermissionDenied('Você não pode gerenciar o recebimento definitivo deste contrato.')

    if not medicao.recebimento_provisorio_emitido():
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma',
            'O recebimento definitivo só pode ser realizado após a emissão do relatório de recebimento provisório.',
            tag='warning',
        )

    if not medicao.termo_definitivo_permite_atualizacao():
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma',
            'O recebimento definitivo não pode mais ser atualizado porque o termo definitivo já foi encaminhado para assinatura, assinado ou finalizado.',
            tag='warning',
        )

    usa_fluxo_recebimento_definitivo_com_documentos = medicao.usa_fluxo_recebimento_definitivo_com_documentos()
    percentuais = ContaVinculadaCalculo.obter_percentuais_para_contrato(contrato)
    perc_13 = percentuais['perc_13']
    perc_ferias = percentuais['perc_ferias']
    perc_fgts = percentuais['perc_fgts']
    perc_sub = percentuais['perc_submodulo']
    perc_13_display = ContaVinculadaCalculo.formatar_percentual_display(perc_13)
    perc_ferias_display = ContaVinculadaCalculo.formatar_percentual_display(perc_ferias)
    perc_fgts_display = ContaVinculadaCalculo.formatar_percentual_display(perc_fgts)
    perc_sub_display = ContaVinculadaCalculo.formatar_percentual_display(perc_sub)

    def _normalize_initial_override(item):
        if not isinstance(item, dict):
            return None
        return {
            'salario': item.get('salario'),
            'valor_13': item.get('valor_13'),
            'valor_ferias': item.get('valor_ferias'),
            'valor_fgts': item.get('valor_fgts'),
            'valor_submodulo': item.get('valor_submodulo'),
            'tipo': item.get('tipo') or 'automatico',
            'modo': item.get('modo') or item.get('tipo') or 'automatico',
            'justificativa': item.get('justificativa') or '',
        }

    def _build_initial_cv_state():
        if request.method == 'POST':
            overrides_raw = request.POST.get('overrides')
            maos_raw = request.POST.get('maos')
            try:
                overrides_post = json.loads(overrides_raw) if overrides_raw else {}
            except Exception:
                overrides_post = {}
            if overrides_raw or maos_raw is not None:
                return {
                    'selected': [item for item in (maos_raw or '').split(',') if item],
                    'overrides': {
                        str(key): normalized
                        for key, value in (overrides_post or {}).items()
                        if (normalized := _normalize_initial_override(value)) is not None
                    },
                }

        calculo = medicao.get_ultimo_calculo_conta_vinculada()
        if calculo and calculo.dados_json:
            itens = calculo.dados_json.get('itens') or []
            return {
                'selected': [str(item.get('maodeobra_id')) for item in itens if item.get('maodeobra_id')],
                'overrides': {
                    str(item.get('maodeobra_id')): normalized
                    for item in itens
                    if item.get('maodeobra_id') and (normalized := _normalize_initial_override(item)) is not None
                },
            }
        return None

    initial_cv_state = _build_initial_cv_state()

    MedicaoDocumentoComprobatorioSet = formset_factory(MedicaoTipoDocumentoComprobatorioForm, extra=0)
    initial = []
    if usa_fluxo_recebimento_definitivo_com_documentos and medicao.documentos_comprobatorios.exists():
        documentos_para_avaliacao = medicao.documentos_comprobatorios.all()
        qtd_documentos = documentos_para_avaliacao.count()
        if not qtd_documentos:
            return httprr(
                f'/contratos/contrato/{contrato.id}/?tab=cronograma',
                f'Existem documentos pendentes de confirmação pelo Fiscal: {medicao.fiscal.servidor.pessoa_fisica.nome}.',
                tag='warning',
            )

        initial = []
        for reg in documentos_para_avaliacao:
            initial.append(
                {
                    'medicao': reg.medicao,
                    'tipo_documento_comprobatorio': reg.tipo_documento_comprobatorio,
                    'confirmacao_fiscal': reg.confirmacao_fiscal,
                    'recebido_gerente': reg.recebido_gerente,
                    'parecer_gerente': reg.parecer_gerente,
                }
            )

        MedicaoDocumentoComprobatorioSet = formset_factory(MedicaoTipoDocumentoComprobatorioForm, extra=qtd_documentos)
    elif usa_fluxo_recebimento_definitivo_com_documentos:
        return httprr('..', 'Medição ainda não possui nenhum documento comprobatório.', 'error')

    formset = MedicaoDocumentoComprobatorioSet(request.POST or None, request.FILES or None)
    for subform, data in zip(formset.forms, initial, strict=False):
        subform.initial = data
        subform.fields['tipo_documento_comprobatorio'].disabled = True
        subform.fields['confirmacao_fiscal'].disabled = True
        subform.fields['tipo_documento_comprobatorio'].widget.attrs['disabled'] = True
        subform.fields['confirmacao_fiscal'].widget.attrs['disabled'] = True
        subform.fields['recebido_gerente'].widget.attrs['required'] = True
        # Add consistent styling to form fields
        try:
            subform.fields['tipo_documento_comprobatorio'].widget.attrs.update({'class': 'form-control form-control-sm'})
        except Exception:
            pass
        try:
            subform.fields['confirmacao_fiscal'].widget.attrs.update({'class': 'form-select form-select-sm'})
        except Exception:
            pass
        try:
            subform.fields['recebido_gerente'].widget.attrs.update({'class': 'form-select form-select-sm'})
        except Exception:
            pass
        try:
            subform.fields['parecer_gerente'].widget.attrs.update({'class': 'form-control'})
        except Exception:
            pass

    if formset.is_valid():
        if not usa_fluxo_recebimento_definitivo_com_documentos:
            return httprr(f'/contratos/contrato/{contrato.id}/', 'Recebimento Definitivo realizado com sucesso.')

        overrides_raw = request.POST.get('overrides')
        overrides = None
        if overrides_raw:
            try:
                overrides = json.loads(overrides_raw)
            except Exception:
                overrides = None

        validation_errors = []
        if overrides and isinstance(overrides, dict):
            for k, v in overrides.items():
                if not isinstance(v, dict):
                    continue
                changed_keys = [x for x in v if x not in ('justificativa', 'tipo', 'modo')]
                if changed_keys:
                    justificativa = v.get('justificativa')
                    if not justificativa or not str(justificativa).strip():
                        validation_errors.append(f'Justificativa obrigatória para trabalhador {k}.')
        if validation_errors:
            for err in validation_errors:
                messages.error(request, err)
            return locals()

        tem_pendencias = False
        maos_raw = request.POST.get('maos')
        maos_list = None
        if maos_raw is not None:
            try:
                maos_list = [int(x) for x in maos_raw.split(',') if x.strip()]
            except Exception:
                maos_list = None
        sem_recolhimento = maos_list is not None and len(maos_list) == 0

        for form in formset.forms:
            if form.cleaned_data.get('recebido_gerente') and form.cleaned_data['recebido_gerente'] == MedicaoTipoDocumentoComprobatorio.PENDENTE:
                tem_pendencias = True
            form.save(commit=False)
            if 'tipo_documento_comprobatorio' in form.cleaned_data and form.cleaned_data.get('tipo_documento_comprobatorio'):
                instance = medicao.documentos_comprobatorios.get(tipo_documento_comprobatorio=form.cleaned_data['tipo_documento_comprobatorio'])
                instance.confirmacao_fiscal = form.cleaned_data['confirmacao_fiscal']
                instance.tipo_documento_comprobatorio = form.cleaned_data['tipo_documento_comprobatorio']
                instance.recebido_gerente = form.cleaned_data['recebido_gerente']
                instance.parecer_gerente = form.cleaned_data['parecer_gerente']
                instance.avaliador_gerente = request.user
                instance.data_avaliacao = datetime.now()
                instance.save()
        if tem_pendencias:
            justificativa_persistencia = (
                'Mês sem recolhimento de conta vinculada (todos os trabalhadores desmarcados).'
                if sem_recolhimento
                else 'Rascunho salvo ao atualizar recebimento definitivo com pendências.'
            )
            medicao.calcular_conta_vinculada(
                maosdeobra_ids=maos_list,
                usuario=request.user,
                tipo='automatico',
                persist=True,
                justificativa=justificativa_persistencia,
                per_item_overrides=overrides,
            )
            medicao.remover_lancamento_conta_vinculada_recebimento_definitivo()
            Notificar.informar_pendencias_na_medicao_ao_fiscal(medicao)
            return httprr(
                f'/contratos/contrato/{contrato.id}/',
                'Recebimento Definitivo atualizado. Foi enviada uma notificação para o Fiscal com as pendências informadas.',
            )
        else:
            # Ao receber definitivamente, calcula e persiste automaticamente a conta vinculada
            try:
                conta_destino = None
                if not sem_recolhimento:
                    conta_destino_id = request.POST.get('conta_vinculada_id')
                    if conta_ativa_unica:
                        conta_destino = conta_ativa_unica
                    elif contas_ativas and conta_retencao_form and conta_retencao_form.is_valid():
                        conta_destino = conta_retencao_form.cleaned_data['conta_vinculada_id']
                    elif contas_ativas:
                        try:
                            conta_destino = next(conta for conta in contas_ativas if str(conta.id) == str(conta_destino_id))
                        except StopIteration:
                            messages.error(request, 'Selecione a conta vinculada que recebera a retencao desta medicao.')
                            return locals()

                resultado = medicao.calcular_conta_vinculada(
                    maosdeobra_ids=maos_list,
                    usuario=request.user,
                    tipo='automatico',
                    persist=True,
                    justificativa='Persistido ao receber definitivamente',
                    per_item_overrides=overrides,
                )
                valor_total = Decimal(str(resultado.get('totais', {}).get('valor_total') or '0')).quantize(Decimal('0.01'))

                if conta_destino and not sem_recolhimento:
                    servidor = request.user.get_relacionamento() if getattr(request.user, 'eh_servidor', False) else None
                    fiscal = contrato.get_fiscal(servidor=servidor) if servidor else None
                    medicao.movimentacoes_conta.filter(deposito=True).exclude(conta=conta_destino).delete()
                    MovimentacaoContaContrato.objects.update_or_create(
                        conta=conta_destino,
                        medicao=medicao,
                        deposito=True,
                        defaults={
                            'valor': str(valor_total),
                            'data': date.today(),
                            'fiscal': fiscal,
                            'servidor': servidor,
                        },
                    )
                    msg = (
                        f'Recebimento Definitivo realizado com sucesso. Cálculo da conta vinculada persistido '
                        f'e lançado na conta {conta_destino.descricao} (R$ {valor_total}).'
                    )
                elif contas_ativas and sem_recolhimento:
                    medicao.remover_lancamento_conta_vinculada_recebimento_definitivo()
                    msg = 'Recebimento Definitivo realizado com sucesso. Mês marcado sem recolhimento de conta vinculada.'
                else:
                    msg = (
                        f'Recebimento Definitivo realizado com sucesso. Cálculo da conta vinculada persistido (R$ {valor_total}), '
                        'mas o contrato não possui conta ativa para lançamento.'
                    )
            except Exception:
                msg = 'Recebimento Definitivo realizado com sucesso. Erro ao tentar persistir cálculo da conta vinculada.'
            return httprr(f'/contratos/contrato/{contrato.id}/', msg)
    return locals()


@group_required('Fiscal de Contrato, Gerente de Contrato')
def gerar_termo_definitivo_documentotexto(request, medicao_id, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    if not contrato.pode_gerenciar_recebimento_definitivo(request):
        raise PermissionDenied('Você não pode gerenciar o recebimento definitivo deste contrato.')
    if not medicao.pode_gerar_termo_definitivo():
        return httprr(
            f'/contratos/contrato/{contrato.id}/?tab=cronograma',
            'O termo definitivo só pode ser gerado após o recebimento definitivo concluído pelo gestor e enquanto o documento continuar editável.',
            tag='warning',
        )

    # Instanciar modelo de documento texto
    modelo = None
    try:
        modelo = ModeloDocumento.objects.get(nome='Termo Circunstanciado de Recebimento Definitivo')
    except Exception:
        messages.error(request, 'Não existe o modelo de documento texto com nome de "Termo Circunstanciado de Recebimento Definitivo".')

    user = request.user
    assunto = 'Termo referente ao contrato nº {} - medição de {} até {}'.format(
        contrato.numero, medicao.data_inicio.strftime('%d/%m/%Y'), medicao.data_fim.strftime('%d/%m/%Y')
    )
    setor_dono = get_setor(user)

    # def get_lista_documentos_display():
    docs_medicao = medicao.documentos_comprobatorios.select_related('tipo_documento_comprobatorio')
    tabela_documentos_comprobatorios = Medicao.montar_tabela_documentos_comprobatorios(
        docs_medicao=docs_medicao,
        titulo_coluna_status='REVISADO?',
        status_getter=lambda doc: doc.get_recebido_gerente_display() if doc.recebido_gerente else doc.confirmacao_fiscal_display,
        mensagem_vazia='Nenhum checklist de fiscalização foi cadastrado para esta medição.',
    )
    # Tags do modelo

    variaveis = {}
    variaveis['cidade_campus_fiscal'] = medicao.campus.municipio if medicao.campus else contrato.campi.first().municipio
    variaveis['numero_processo_medicao_ou_contrato'] = medicao.processo or contrato.processo
    variaveis['contrato_numero'] = contrato.numero
    variaveis['contrato_objeto'] = contrato.objeto
    variaveis['medicao_numero_nota_fiscal'] = medicao.numero_documento
    variaveis['medicao_data_inicial'] = medicao.data_inicio.strftime('%d/%m/%Y')
    variaveis['medicao_data_final'] = medicao.data_fim.strftime('%d/%m/%Y')
    variaveis['nome_contratada'] = contrato.vinculo_contratado.pessoa.nome
    variaveis['cnpj_contratada'] = contrato.vinculo_contratado.pessoa.get_cpf_ou_cnpj()
    variaveis['campus_pluralize'] = nomenclatura.do_campus if medicao.campus or contrato.campi.all().count() == 1 else nomenclatura.dos_campi
    variaveis['contrato_sigla_campi'] = medicao.campus or contrato.get_uos_as_string()
    variaveis['artigo_base_legal'] = (
        contrato.base_legal.conformidade_base_legal
        if contrato.base_legal and contrato.base_legal.conformidade_base_legal
        else 'Art. 73 da Lei nº 8.666/93'
    )
    variaveis['medicao_parcela_cronograma'] = medicao.parcela.cronograma.numero
    variaveis['instituicao_sigla'] = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    variaveis['medicao_valor'] = format_money(medicao.valor_executado)
    variaveis['medicao_valor_por_extenso'] = por_extenso(medicao.valor_executado)
    variaveis['medicao_parcela_valor_previsto'] = format_money(medicao.parcela.valor_previsto)
    variaveis['contrato_nome_fiscal'] = medicao.fiscal.servidor.pessoa_fisica.nome
    variaveis['contrato_matricula_fiscal'] = medicao.fiscal.servidor.matricula
    variaveis['tabela_documentos_comprobatorios'] = tabela_documentos_comprobatorios

    variaveis_correntes = get_variaveis(
        documento_identificador=None,
        estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
        usuario=user,
        setor_dono=setor_dono,
    )

    def gerar_documento():
        hipotese_legal = HipoteseLegal.objects.filter(pk=6).first()
        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user,
            setor_dono=setor_dono,
            modelo=modelo,
            assunto=assunto,
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
            hipotese_legal=hipotese_legal,
            variaveis=variaveis,
        )
        medicao.atualizar_tabela_conta_vinculada_termo_definitivo_documento(documento_novo)
        documento_novo.save(update_fields=['corpo'])
        # Vincula o documento digital criado a medição do contrato
        medicao.termo_definitivo_documentotexto = documento_novo
        medicao.save()
        return documento_novo

    documento_novo = None
    msg = ''

    if not medicao.termo_definitivo_documentotexto:
        documento_novo = gerar_documento()
        msg = 'Termo Circunstanciado de Recebimento Definitivo gerado com sucesso.'
    elif medicao.termo_definitivo_documentotexto.estah_em_rascunho or medicao.termo_definitivo_documentotexto.estah_concluido:
        documento_novo = medicao.termo_definitivo_documentotexto
        variaveis_correntes.update(variaveis)
        documento_novo.corpo = processar_template_ckeditor(texto=modelo.corpo_padrao, variaveis=variaveis_correntes)
        medicao.atualizar_tabela_conta_vinculada_termo_definitivo_documento(documento_novo)
        if medicao.termo_definitivo_documentotexto.estah_concluido:
            documento_novo.editar_documento()
        documento_novo.save()
        msg = 'Termo Circunstanciado de Recebimento Definitivo atualizado com sucesso.'
    elif medicao.termo_definitivo_documentotexto.estah_assinado or medicao.termo_definitivo_documentotexto.estah_finalizado:
        documento_novo = medicao.termo_definitivo_documentotexto
        msg = f'Este documento está na situação {documento_novo.get_status()} que não permite edição. Para gerar um novo despacho favor cancelar este documento: {documento_novo.identificador}'
    elif medicao.termo_definitivo_documentotexto.estah_cancelado:
        documento_antigo = medicao.termo_definitivo_documentotexto
        documento_novo = gerar_documento()
        # tipo vinculo - retificação
        tipo_vinculo = TipoVinculoDocumento.objects.get(descricao='Retificação')
        # Vincula documentos
        vinculo_documentos = VinculoDocumentoTexto()
        vinculo_documentos.tipo_vinculo_documento = tipo_vinculo
        vinculo_documentos.documento_texto_base = documento_novo
        vinculo_documentos.documento_texto_alvo = documento_antigo
        vinculo_documentos.usuario_criacao = user
        vinculo_documentos.save()
        # Atualiza referencia da objeto de Medicao
        medicao.termo_definitivo_documentotexto = documento_novo
        medicao.save()
        msg = 'Termo Circunstanciado de Recebimento Definitivo substituído com sucesso.'

    if documento_novo and msg:
        CompartilhamentoDocumentoPessoa.objects.get_or_create(
            vinculo_permitido=user.get_vinculo(), documento=documento_novo, nivel_permissao=NivelPermissao.EDITAR
        )
        return httprr(documento_novo.get_absolute_url(), msg)
    else:
        return httprr('..', 'Erro ao tentar gerar termo definitivo.', 'error')


@group_required('Fiscal de Contrato, Gerente de Contrato')
def calcular_conta_vinculada_ajax(request, medicao_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'msg': 'Requisição inválida. Use POST.'}, status=405)
    medicao = get_object_or_404(Medicao, pk=medicao_id)
    contrato = medicao.parcela.cronograma.contrato
    if not contrato.pode_gerenciar_recebimento_definitivo(request):
        return JsonResponse({'status': 'error', 'msg': 'Permissão negada.'}, status=403)

    maos = request.POST.get('maos')
    maos_list = None
    if maos is not None:
        try:
            maos_list = [int(x) for x in maos.split(',') if x.strip()]
        except Exception:
            maos_list = None

    persist = request.POST.get('persist') in ['1', 'true', 'True']
    tipo = request.POST.get('tipo') or 'automatico'
    justificativa = request.POST.get('justificativa')
    valor_manual = request.POST.get('valor_manual')
    overrides_raw = request.POST.get('overrides')
    overrides = None
    if overrides_raw:
        try:
            overrides = json.loads(overrides_raw)
        except Exception:
            overrides = None

    resultado = medicao.calcular_conta_vinculada(
        maosdeobra_ids=maos_list,
        usuario=request.user,
        tipo=tipo,
        persist=persist,
        justificativa=justificativa,
        manual_valor=valor_manual,
        per_item_overrides=overrides,
    )
    return JsonResponse({'status': 'ok', 'resultado': resultado})


@rtr()
@login_required()
def relatorio_valores_executados(request, contrato_id):
    title = f'Demonstrativo de Valores Executados por {nomenclatura.campus}'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    cronograma = contrato.get_cronograma()
    lista_valores_executados = []
    infos_sem_campus = {}
    total_contrato = Decimal('0')
    if cronograma:
        pks_uos_contrato = Contrato.objects.filter(pk=contrato.id).values_list('campi', flat=True)
        for uo in UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato):
            infos = {}
            total = Decimal('0')
            for parcela in cronograma.parcelas.all():
                for medicao in parcela.medicoes.filter(campus=uo):
                    total += medicao.valor_executado
            total_contrato += total

            infos['uo'] = uo.sigla
            infos['total_executado'] = f'{total:.2f}'
            lista_valores_executados.append(infos)
    total_sem_campus_definido = contrato.get_valor_executado() - total_contrato
    infos_sem_campus['uo'] = 'Sem campus definido'
    infos_sem_campus['total_executado'] = f'{total_sem_campus_definido:.2f}'
    lista_valores_executados.append(infos_sem_campus)
    return locals()


@rtr()
@login_required
def adicionar_documento_empenho_contrato(request, contrato_id):
    title = 'Adicionar Empenho'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_empenho(request):
        raise PermissionDenied
    instance = DocumentoEmpenhoContrato(contrato=contrato)
    form = AdicionarEmpenhoForm(request.POST or None, instance=instance)
    if form.is_valid():
        form.save()
        return httprr('..', 'Empenho adicionado com sucesso.')
    return locals()


@rtr()
@login_required
def excluir_documento_empenho_contrato(request, documento_empenho_contrato_id):
    documento_empenho_contrato = get_object_or_404(DocumentoEmpenhoContrato, pk=documento_empenho_contrato_id)
    if not documento_empenho_contrato.contrato.pode_gerenciar_empenho(request):
        raise PermissionDenied
    contrato_id = documento_empenho_contrato.contrato_id
    documento_empenho_contrato.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/?tab=empenhos', 'Empenho removido com sucesso.')


@rtr()
@login_required
def editar_documento_empenho_contrato(request, documento_empenho_contrato_id):
    title = 'Editar Empenho'
    documento_empenho_contrato = get_object_or_404(DocumentoEmpenhoContrato, pk=documento_empenho_contrato_id)
    if not documento_empenho_contrato.contrato.pode_gerenciar_empenho(request):
        raise PermissionDenied
    form = AdicionarEmpenhoForm(request.POST or None, instance=documento_empenho_contrato)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ocorrência editada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.pode_encerrar_contrato')
def concluir_contrato(request, contrato_id):
    title = 'Encerrar/Rescindir Contrato'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    form = ContratoConcluirForm(request.POST or None)
    if form.is_valid():
        motivo_conclusao = form.cleaned_data['motivo_conclusao']
        data_conclusao = form.cleaned_data['data_conclusao']
        contrato.motivo_conclusao = motivo_conclusao
        contrato.concluido = True
        contrato.data_conclusao = data_conclusao
        contrato.save()
        return httprr('..', 'Contrato Concluído.')
    return locals()


@rtr()
@permission_required('contratos.pode_encerrar_contrato')
def desfazer_conclusao_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    contrato.concluido = False
    contrato.data_conclusao = None
    contrato.motivo_conclusao = None
    contrato.save()
    return httprr('..', 'Operação realizada com sucesso.')


@rtr()
@login_required
def adicionar_agenda(request, contrato_id):
    title = 'Adicionar Agenda'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_agenda_fiscalizacao(request):
        raise PermissionDenied
    form = AgendaForm(request.POST or None, contrato=contrato)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr('..', 'Agenda adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.add_contrato')
def importar_novo_contrato_comprasgov(request):
    title = 'Importar Contrato do ComprasGov'
    try:
        form = BuscarContratoComprasGovForm(request.GET or None)
        if form.is_valid():
            dict_info_contrato = form.buscar()
            if dict_info_contrato:
                codigo_unidade = dict_info_contrato.get('unidade_codigo')
                if not UnidadeOrganizacional.objects.filter(codigo_ug=codigo_unidade).exists():
                    return httprr('.', f'Não existe Unidade Organizacional com o código {codigo_unidade} retornado para este contrato.', 'error')

                initial = {
                    'id_comprasgov': dict_info_contrato.get('id'),
                    'numero': dict_info_contrato.get('numero'),
                    'objeto': dict_info_contrato.get('objeto'),
                    'data_inicio': dict_info_contrato.get('vigencia_inicio'),
                    'data_fim': dict_info_contrato.get('vigencia_fim'),
                    'qtd_parcelas': dict_info_contrato.get('num_parcelas'),
                    'valor_previsto_parcela': dict_info_contrato.get('valor_parcela'),
                    'valor': dict_info_contrato.get('valor_global'),
                    'pregao': dict_info_contrato.get('licitacao_numero'),
                    'natureza': dict_info_contrato.get('receita_despesa'),
                }

                # Mapeamento de campi atendidos e campus gerenciador
                qs_campi = UnidadeOrganizacional.objects.suap().filter(codigo_ug=dict_info_contrato.get('unidade_compra'))
                if qs_campi.exists():
                    initial['campi'] = qs_campi.last().id
                    initial['campus_gerenciador'] = qs_campi.last().id

                # Mapeamento de processo
                qs_processo = Processo.objects.filter(numero_protocolo_fisico=dict_info_contrato['processo'].replace('/', '.'))
                if qs_processo.exists():
                    initial['processo'] = qs_processo.last().get_processo_fisico_relacionado().id

                # Mapeamento de Base Legal
                if dict_info_contrato.get('fundamento_legal'):
                    qs_base_legal = BaseLegal.objects.filter(titulo__icontains=dict_info_contrato.get('fundamento_legal'))
                    if qs_base_legal.exists():
                        initial['base_legal'] = qs_base_legal.last().id

                # Mapeamento de Tipo de Contrato
                qs_tipo = TipoContrato.objects.filter(descricao__icontains=dict_info_contrato.get('categoria'))
                if qs_tipo.exists():
                    initial['tipo'] = qs_tipo.last().id

                # Mapeamento de Tipo de Licitação
                qs_modalidade = TipoLicitacao.objects.filter(descricao__icontains=dict_info_contrato.get('modalidade'))
                if qs_modalidade.exists():
                    initial['tipo_licitacao'] = qs_modalidade.first().id

                # Mapeamento de fornecedor
                cnpj_fornecedor = dict_info_contrato['fonecedor_cnpj_cpf_idgener']
                qs_fornecedor = PessoaJuridica.objects.filter(cnpj=cnpj_fornecedor)
                fornecedor = (
                    qs_fornecedor.first()
                    if qs_fornecedor.exists()
                    else PessoaJuridica.adicionar_pessoajuridica_importar_api_cnpj(cnpj=cnpj_fornecedor)
                )
                if fornecedor:
                    initial['vinculo_contratado'] = fornecedor.get_vinculo().id

                messages.success(request, 'Altere as informações necessárias e clique em Salvar para adicionar o contrato no SUAP.')
                url = reverse('admin:contratos_contrato_add')
                url_com_parametros = f'{url}?{urlencode(initial)}'
                return HttpResponseRedirect(url_com_parametros)
            else:
                messages.warning(request, 'Não foi possível localizar o contrato no ComprasGov')
    except Exception as e:
        if settings.DEBUG:
            raise e
        messages.error(request, str(e))
        return httprr('.', str(e), 'error')
    return locals()


@rtr()
@login_required
def editar_agenda(request, agenda_id):
    title = 'Editar Agenda'
    agenda = get_object_or_404(Agenda, pk=agenda_id)
    if not agenda.contrato.pode_gerenciar_agenda_fiscalizacao(request):
        raise PermissionDenied
    form = AgendaForm(request.POST or None, instance=agenda)
    if form.is_valid():
        form.save()
        return httprr('..', 'Agenda alterada com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.change_contrato')
def importar_itens_contrato_comprasgov(request, contrato_id):
    try:
        contrato = get_object_or_404(Contrato, pk=contrato_id)

        eh_coordenador_sistemico = request.user.has_group_cached('Coordenador de Contrato Sistêmico', ignore_groups_if_superuser=False)
        if (
            not contrato.eh_fiscal(request.user.get_relacionamento()) or not contrato.eh_gestor_contrato(request.user.get_relacionamento())
        ) and not eh_coordenador_sistemico:
            raise PermissionDenied

        if not contrato.id_comprasgov:
            return httprr(
                f'/contratos/contrato/{contrato_id}/?tab=itens',
                mark_safe(
                    '<a target="_blank" href="/admin/processo_eletronico/grupointeressadosprocesso/">Clique Aqui e veja como localizar o identificador no https://contratos.comprasnet.gov.br/</a>'
                ),
                tag='warning',
            )

        api_externa = APIExterna.CONTRATOSGOVBR
        if not api_externa.ativo:
            return httprr(
                f'/contratos/contrato/{contrato_id}/?tab=itens',
                'A integração com o ComprasGov está desativada. Por favor, entre em contato com o suporte técnico.',
                tag='error',
            )
        api_service = api_externa.get_service()
        itens_contrato_api = api_service.obter_itens_contrato_comprasgov(contrato.id_comprasgov)
        qtd_itens_add = 0
        for item in itens_contrato_api:
            novo_item = ItemContrato()
            novo_item.contrato = contrato
            novo_item.grupo = item.get('grupo_id')
            novo_item.descricao = item.get('descricao_complementar')
            novo_item.quantidade = item.get('quantidade')
            novo_item.valor_unitario = Decimal(item.get('valorunitario').replace('.', '').replace(',', '.'))
            novo_item.valor_total = Decimal(item.get('valortotal').replace('.', '').replace(',', '.'))
            novo_item.numero_item = item.get('numero_item_compra')
            if item.get('tipo_id') == 'Material':
                novo_item.tipo = ItemContrato.MATERIAL
            elif item.get('tipo_id') == 'Serviço':
                novo_item.tipo = ItemContrato.SERVICO
            novo_item.id_comprasgov = item.get('id')

            if not ItemContrato.objects.filter(contrato=contrato, id_comprasgov=novo_item.id_comprasgov).exists():
                novo_item.save()
                qtd_itens_add += 1

        if qtd_itens_add >= 1:
            messages.success(request, f'{qtd_itens_add} itens do contrato adicionados com sucesso.')
        else:
            messages.info(request, 'Nenhum item importado do ComprasGov.')

        if not itens_contrato_api:
            messages.warning(request, 'Não foi possível localizar os itens do contrato no ComprasGov')
    except Exception as e:
        messages.error(request, str(e))
        return httprr('..', str(e), 'error')

    return httprr(f'/contratos/contrato/{contrato_id}/?tab=itens')


@rtr()
@permission_required('contratos.change_contrato')
def adicionar_item(request, contrato_id):
    title = 'Adicionar Item'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    eh_coordenador_sistemico = request.user.has_group_cached('Coordenador de Contrato Sistêmico', ignore_groups_if_superuser=False)
    if (
        not contrato.eh_fiscal(request.user.get_relacionamento()) or not contrato.eh_gestor_contrato(request.user.get_relacionamento())
    ) and not eh_coordenador_sistemico:
        raise PermissionDenied
    item = ItemContrato()
    item.contrato = contrato
    form = ItemContratoForm(request.POST or None, request.FILES or None, instance=item)
    if form.is_valid():
        form.instance.contrato = contrato
        form.instance.atualizado_por = request.user.get_vinculo()
        form.save()
        return httprr('..', 'Item adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.change_contrato')
def editar_item(request, item_id):
    title = 'Editar Item'
    item = get_object_or_404(ItemContrato, pk=item_id)
    contrato = item.contrato
    eh_coordenador_sistemico = request.user.has_group_cached('Coordenador de Contrato Sistêmico', ignore_groups_if_superuser=False)
    if (
        not contrato.eh_fiscal(request.user.get_relacionamento()) or not contrato.eh_gestor_contrato(request.user.get_relacionamento())
    ) and not eh_coordenador_sistemico:
        raise PermissionDenied
    form = ItemContratoForm(request.POST or None, request.FILES or None, instance=item)
    if form.is_valid():
        form.instance.atualizado_por = request.user.get_vinculo()
        form.save()
        return httprr(f'/contratos/contrato/{item.contrato.id}/?tab=itens', 'Item editado com sucesso.')
    return locals()


@rtr()
@permission_required('contratos.change_contrato')
def excluir_item(request, item_id):
    item = get_object_or_404(ItemContrato, pk=item_id)
    contrato = item.contrato
    eh_coordenador_sistemico = request.user.has_group_cached('Coordenador de Contrato Sistêmico', ignore_groups_if_superuser=False)
    if (
        not contrato.eh_fiscal(request.user.get_relacionamento()) or not contrato.eh_gestor_contrato(request.user.get_relacionamento())
    ) and not eh_coordenador_sistemico:
        raise PermissionDenied
    contrato_id = item.contrato.id
    item.delete()
    return httprr(f'/contratos/contrato/{contrato_id}/?tab=itens', 'Item removido com sucesso.')


@rtr()
@login_required
def adicionar_agenda_pre_configurada(request, contrato_id):
    title = 'Adicionar Agenda Pré-Configurada'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_agenda_fiscalizacao(request):
        raise PermissionDenied
    itens = PreConfiguracaoAgenda.objects.all()
    if request.method == 'POST' and 'pre_configuracao_ids' in request.POST:
        ids = request.POST.getlist('pre_configuracao_ids')
        queryset = PreConfiguracaoAgenda.objects.filter(pk__in=ids)
        for pre_configuracao in queryset:
            agenda = Agenda()
            agenda.contrato = contrato
            agenda.pre_configuracao = pre_configuracao
            agenda.descricao = pre_configuracao.acao
            agenda.data_prevista = contrato.data_inicio + timedelta(days=pre_configuracao.prazo)
            agenda.save()
        return httprr('..', 'Agenda Pré-Configurada registrada com sucesso.')
    return locals()


@rtr()
@login_required
def registrar_fiscalizacao(request, agenda_id):
    title = 'Registrar Fiscalização'
    agenda = get_object_or_404(Agenda, pk=agenda_id)
    if not agenda.contrato.pode_gerenciar_agenda_fiscalizacao(request):
        raise PermissionDenied
    form = RegistrarFiscalizacaoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        agenda.data_execucao = form.cleaned_data['data_execucao']
        agenda.save()
        for anexo in request.FILES.getlist('anexos'):
            anexo_agenda = AnexoAgenda()
            anexo_agenda.agenda = agenda
            anexo_agenda.arquivo = anexo
            anexo_agenda.save()
        return httprr('..', 'Fiscalização registrada com sucesso.')
    return locals()


@rtr('ocorrencias_maodeobra.html')
@login_required
def adicionar_ocorrenciamaodeobra(request, maodeobra_id):
    title = 'Adicionar Ocorrência à Mão de Obra'
    maodeobra = get_object_or_404(MaoDeObra, pk=maodeobra_id)
    pode_gerenciar_mao_de_obra = maodeobra.contrato.pode_gerenciar_mao_de_obra(request)
    if not pode_gerenciar_mao_de_obra:
        raise PermissionDenied
    form = OcorrenciaMaoDeObraForm(request.POST or None, request.FILES or None, maodeobra=maodeobra)
    if form.is_valid():
        form.save()
        return httprr('.', 'Ocorrência adicionada com sucesso à mão de obra.')
    return locals()


@rtr('ocorrencias_maodeobra.html')
@login_required
def editar_ocorrenciamaodeobra(request, ocorrencia_maodeobra_id):
    title = 'Editar Ocorrência à Mão de Obra'
    ocorrenciar_maodeobra = OcorrenciaMaoDeObra.objects.get(pk=ocorrencia_maodeobra_id)
    maodeobra = ocorrenciar_maodeobra.maodeobra
    if not maodeobra.contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    form = OcorrenciaMaoDeObraForm(request.POST or None, request.FILES or None, instance=ocorrenciar_maodeobra, maodeobra=maodeobra)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ocorrência atualizada com sucesso.')
    return locals()


@rtr('verbasalarial_maodeobra.html')
@login_required
def adicionar_verbasalarial(request, maodeobra_id):
    title = 'Adicionar Verba Salarial à Mão de Obra'
    maodeobra = get_object_or_404(MaoDeObra, pk=maodeobra_id)
    pode_gerenciar_mao_de_obra = maodeobra.contrato.pode_gerenciar_mao_de_obra(request)
    if not pode_gerenciar_mao_de_obra:
        raise PermissionDenied
    form = VerbaSalarialMaoDeObraForm(request.POST or None, request.FILES or None, maodeobra=maodeobra)
    if form.is_valid():
        form.save()
        return httprr('.', 'Verba Salarial adicionada com sucesso à mão de obra.')
    return locals()


@rtr('verbasalarial_maodeobra.html')
@login_required
def editar_verbasalarial(request, verbasalarial_id):
    title = 'Editar Verba Salarial à Mão de Obra'
    instance = VerbaSalarialMaoDeObra.objects.get(pk=verbasalarial_id)
    maodeobra = instance.maodeobra
    if not maodeobra.contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    form = VerbaSalarialMaoDeObraForm(request.POST or None, request.FILES or None, instance=instance, maodeobra=maodeobra)
    if form.is_valid():
        form.save()
        return httprr('..', 'Verba Salarial atualizada com sucesso.')
    return locals()


@rtr()
@login_required()
def indicadores(request):
    uo = None
    title = 'Indicadores para Contratos'
    is_visualizador_sistemico = (
        request.user.is_superuser or request.user.has_group_cached('Auditor') or request.user.has_group_cached('Supervisor de Contratos')
    )
    restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
    if restringir_por_unidade and not is_visualizador_sistemico:
        uo = request.user.get_vinculo().setor.uo
    hoje = datetime.now().date()
    ano_atual = Ano.objects.get(ano=hoje.year)
    initial = {'ano': ano_atual.id}
    data = request.GET or None
    if uo and not data:
        initial['campus'] = uo.id
        data = {'ano': ano_atual.id, 'campus': uo.id}
    form = IndicadoresForm(data, initial=initial)
    if uo:
        form.fields['campus'].queryset = form.fields['campus'].queryset.filter(pk=uo.pk)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')

        dados = Medicao.objects.all()
        if uo:
            dados = dados.filter(campus=uo)
        elif campus:
            dados = dados.filter(campus=campus)

        dados_despesas_anuais = dados.filter(data_medicao__year=ano.ano)
        dados_crescimento_despesas = dados.filter(data_medicao__year__gt=ano.ano - 5, data_medicao__year__lte=ano.ano)

        def get_grafico_despesas_anuais(grafico_id, dados, subtipo=False):
            dados = (
                dados.values_list('parcela__cronograma__contrato__tipo__descricao')
                .annotate(soma=Sum('valor_executado'))
                .values_list('parcela__cronograma__contrato__tipo__descricao', 'soma')
            )
            if subtipo:
                dados = (
                    dados.values_list('parcela__cronograma__contrato__subtipo__descricao')
                    .annotate(soma=Sum('valor_executado'))
                    .values_list('parcela__cronograma__contrato__subtipo__descricao', 'soma')
                )

            dados_despesas_anuais = []
            for tipo, valor in dados:
                dados_despesas_anuais.append((tipo, float(valor)))

            subtitle = 'Gráfico em barra com os valores dos gastos anuais dos contratos pelo tipo de contrato.'
            if subtipo:
                subtitle = 'Gráfico em barra com os valores dos gastos anuais dos contratos pelo subtipo de contrato.'
            grafico = BarChart(
                grafico_id,
                title='Despesas anuais',
                subtitle=subtitle,
                minPointLength=0,
                tooltip={'pointFormat': '<strong>R$ {point.y:,.2f}</strong>'},
                data=dados_despesas_anuais,
            )
            grafico.id = grafico_id
            return grafico

        def get_grafico_crescimento_despesas(grafico_id, dados):
            dados = (
                dados.values_list('data_medicao__year')
                .annotate(soma=Sum('valor_executado'))
                .values_list('data_medicao__year', 'soma')
                .order_by('data_medicao__year')
            )
            dados_crescimento_despesas = []
            for tipo, valor in dados:
                dados_crescimento_despesas.append((tipo, float(valor)))

            grafico = LineChart(
                grafico_id,
                title='Crescimento das despesas',
                subtitle='Gráfico em linha demonstrando o crescimento dos últimos 5 anos das despesas com contratos',
                data=dados_crescimento_despesas,
                groups=['Despesas'],
                yAxis_title_text='R$',
                tooltip={'pointFormat': '<strong>R$ {point.y:,.2f}</strong>'},
                plotOptions_line_dataLabels_enable=True,
                plotOptions_line_enableMouseTracking=True,
            )
            grafico.id = grafico_id
            return grafico

        # Contratos gerais: Deve considerar todos os contratos.

        # Despesas anuais: Gráfico em barra com os valores dos gastos anuais dos contratos pelo tipo de contrato.
        grafico_contratos_gerais_despesas_anuais = get_grafico_despesas_anuais('grafico_contratos_gerais_despesas_anuais', dados_despesas_anuais)

        # Crescimento das despesas: Gráfico em linha demonstrando o crescimento dos últimos 5 anos das despesas com contratos (deve considerar o ano final, como o Ano do filtro; isto é, caso o filtro esteja marcado como 2015, o gráfico deve exibir as linhas 2011, 2012, 2013, 2014 e 2015).
        grafico_contratos_gerais_crescimento_despesas = get_grafico_crescimento_despesas(
            'grafico_contratos_gerais_crescimento_despesas', dados_crescimento_despesas
        )

        # Contratos com mão de obra terceirizada: Deve considerar somente os contratos com a opção "Possui dedicação exclusiva de mão de obra" marcada como "Sim".

        # Despesas anuais: Gráfico em barra com os valores dos gastos anuais dos contratos pelo tipo de contrato.
        grafico_contratos_mao_obra_despesas_anuais = get_grafico_despesas_anuais(
            'grafico_contratos_mao_obra_despesas_anuais',
            dados_despesas_anuais.filter(parcela__cronograma__contrato__mao_obra_exclusiva=True),
            subtipo=True,
        )

        # Crescimento das despesas: Gráfico em linha demonstrando o crescimento dos últimos 5 anos das despesas com contratos (deve considerar o ano final, como o Ano do filtro; isto é, caso o filtro esteja marcado como 2015, o gráfico deve exibir as linhas 2011, 2012, 2013, 2014 e 2015).
        grafico_contratos_mao_obra_crescimento_despesas = get_grafico_crescimento_despesas(
            'grafico_contratos_mao_obra_crescimento_despesas',
            dados_crescimento_despesas.filter(parcela__cronograma__contrato__mao_obra_exclusiva=True),
        )

        # Contratos continuados: Deve considerar somente os contratos com a opção "Continuidade" marcada como "Sim".

        # Despesas anuais: Gráfico em barra com os valores dos gastos anuais dos contratos pelo tipo de contrato.
        grafico_contratos_continuados_despesas_anuais = get_grafico_despesas_anuais(
            'grafico_contratos_continuados_despesas_anuais',
            dados_despesas_anuais.filter(parcela__cronograma__contrato__continuidade=CONTINUIDADE_CONTINUO),
            subtipo=True,
        )
    return locals()


@rtr()
@login_required
def copiar_maodeobra(request, contrato_id):
    title = 'Copiar Mão de Obra'
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    if not contrato.pode_gerenciar_mao_de_obra(request):
        raise PermissionDenied
    form = CopiarMaoDeObra(request.POST or None, contrato=contrato)
    if form.is_valid():
        form.save()
        return httprr(f'/contratos/contrato/{contrato_id}/?tab=itens', 'Mão de obra copiada com sucesso.')
    return locals()
