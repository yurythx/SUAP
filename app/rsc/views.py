import datetime
import io
import json
import os
import uuid
import zipfile
from decimal import Decimal
from itertools import chain

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.dispatch import Signal
from django.http import Http404, HttpRequest, HttpResponse
from django.http.response import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pypdf import PdfReader, PdfWriter

from comum.models import Configuracao
from comum.utils import get_setor, get_setor_cppd, get_sigla_reitoria, get_uo
from djtools import layout
from djtools.html.graficos import BarChart, ColumnChart, PieChart
from djtools.storages import AWSUploadBackend, LocalUploadBackend, is_remote_storage
from djtools.storages.utils import cache_file, copy_file
from djtools.templatetags.filters import format_datetime
from djtools.utils import JsonResponse, XlsResponse, documento, httprr, is_ajax, permission_required, render, rtr, strptime_or_default, upload_em_pdf
from documento_eletronico.models import Documento, TipoConferencia
from processo_eletronico.models import Processo as ProcessoEletronico
from processo_eletronico.models import TipoProcesso
from protocolo.models import Processo, Tramite
from rh.models import Avaliador, Setor
from rsc import dashboard as rsc_dashboard
from rsc import relatorio_situacao as rsc_relatorio_situacao
from rsc.forms import (
    AssinaturaRequerimentoForm,
    AtualizarProcessoRSCForm,
    AvaliadorForm,
    DashboardFiltroForm,
    DataConclusaoTitulacaoRSCForm,
    DataExercicioCarreiraForm,
    DocumentosExigidosForm,
    JustificativaDesistenciaForm,
    ProcessoPagamentoForm,
    ProcessoRSCAddForm,
    ProcessoRSCForm,
    RecusaAvaliacaoForm,
    RejeitarProcessoCPPDForm,
    RelatorioPagamentoForm,
    RelatorioSituacaoFiltroForm,
    ValidacaoCPPDForm,
)
from rsc.models import (
    PRIVATE_ROOT_DIR,
    Arquivo,
    ArquivosExigidos,
    Avaliacao,
    AvaliacaoItem,
    CloneArquivoErro,
    ConfiguracaoRSC,
    Criterio,
    Diretriz,
    ParametroPagamento,
    ProcessoAvaliador,
    ProcessoRSC,
    TipoRsc,
    ValidacaoCPPD,
)


def _aplicar_campo_arquivo(arquivo, campo, valor):
    """Aplica um campo do arquivo (qtd/data/nota/descricao). Vazio ou inválido => ignora.

    Retorna True se o valor foi aplicado, False caso contrário (mantendo o valor anterior).
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return False
    try:
        if campo == 'qtd':
            arquivo.qtd_itens = int(valor)
        elif campo == 'data':  # formato 'aaaa-mm-dd'
            ano, mes, dia = (int(parte) for parte in valor.split('-'))
            arquivo.data_referencia = datetime.date(ano, mes, dia)
        elif campo == 'nota':
            arquivo.nota_pretendida = float(valor)
        elif campo == 'descricao':
            arquivo.descricao = valor
        else:
            return False
    except ValueError:
        # valor sempre é string não-vazia aqui (guarda acima); só ValueError é alcançável.
        return False
    return True


@layout.info()
def index_infos(request):
    infos = []

    if request.user.has_group_cached('Avaliador Externo'):
        if Avaliador.objects.filter(vinculo=request.user.get_vinculo()).exists():
            infos.append({'url': '/rh/atualizar_dados_avaliador/', 'titulo': '<strong>Avaliador:</strong> mantenha sempre seus dados atualizados.'})

    return infos


@rtr()
@login_required()
def criar_processo_rsc(request):
    title = 'Adicionar Processo'

    sub_instance = request.user.get_relacionamento()
    if not sub_instance.eh_docente:
        raise PermissionDenied('Você não tem permissão para acessar esta página.')

    form = ProcessoRSCAddForm(request.POST or None)
    if form.is_valid():
        processo = ProcessoRSC()
        processo.servidor = request.user.get_relacionamento()
        processo.status = ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD
        processo.tipo_rsc = form.cleaned_data['rsc_pretendida']
        processo.save()
        return redirect(f'/rsc/abrir_processo_rsc/{processo.id}/')

    return locals()


@rtr()
@login_required()
def imprimir_processo(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    return locals()


@login_required()
def visualizar_arquivo_pdf(request, arquivo_id):
    try:
        arquivo = Arquivo.objects.get(encrypted_pk=arquivo_id)
        soh_cppd_dono_avaliador(request, arquivo.processo)
        pdf_data = mark_safe(default_storage.url(arquivo.diretorio))
        return render('viewer.html', locals())
    except Exception:
        return httprr('..', 'O arquivo não existe ou foi removido.', 'error')


@login_required()
def visualizar_arquivo_exigido_pdf(request, arquivo_id):
    try:
        arquivo = ArquivosExigidos.objects.get(encrypted_pk=arquivo_id)
        soh_cppd_dono_avaliador(request, arquivo.processo)
        pdf_data = mark_safe(default_storage.url(arquivo.diretorio))
        return render('viewer.html', locals())
    except Exception:
        return httprr('..', 'O arquivo não existe ou foi removido.', 'error')


@csrf_exempt
@login_required()
def excluir_arquivo_pdf(request, arquivo_id):
    try:
        arquivo = Arquivo.objects.get(encrypted_pk=arquivo_id)
        soh_dono(request, arquivo.processo)
        default_storage.delete(arquivo.diretorio)

        # excluindo registro do banco
        arquivo.delete()

        retorno = JsonResponse({'ok': True, 'msg': ''})
        data_referencia_retroativa = arquivo.processo.get_data_referencia_retroativa()
        if data_referencia_retroativa:
            retorno['data_referencia_retroatividade'] = format_datetime(data_referencia_retroativa)
        else:
            retorno['data_referencia_retroatividade'] = '-'

        return retorno
    except Exception:
        return JsonResponse({'ok': False, 'msg': ''})


@csrf_exempt
@login_required()
def excluir_arquivo_exigido_pdf(request, arquivo_id):
    try:
        arquivo = ArquivosExigidos.objects.get(encrypted_pk=arquivo_id)
        soh_dono(request, arquivo.processo)
        default_storage.delete(arquivo.diretorio)

        # excluindo registro do banco
        arquivo.delete()

        retorno = JsonResponse({'ok': True, 'msg': ''})
        data_referencia_retroativa = arquivo.processo.get_data_referencia_retroativa()
        if data_referencia_retroativa:
            retorno['data_referencia_retroatividade'] = format_datetime(data_referencia_retroativa)
        else:
            retorno['data_referencia_retroatividade'] = '-'

        return retorno
    except Exception:
        return JsonResponse({'ok': False, 'msg': ''})


@login_required()
def excluir_processo_rsc(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_dono(request, processo)
    if processo.status != ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD:
        return httprr('/admin/rsc/processorsc/', 'Processo só pode ser excluido se estiver na situação: Aguardando Envio para CPPD', tag='error')
    # removendo arquivo físico
    arquivos = processo.arquivo_set.all()
    for arquivo in arquivos:
        default_storage.delete(arquivo.diretorio)

    processo.delete()

    return httprr('/admin/rsc/processorsc/', 'Processo excluído com sucesso.')


@csrf_exempt
@rtr()
@login_required()
@transaction.atomic
def clonar_processo_rsc(request, processo_id):
    sub_instance = request.user.get_relacionamento()
    processo_rsc = get_object_or_404(ProcessoRSC, pk=processo_id)
    # apenas pode clonar o processo o próprio avaliado (docente) ou um membro da CPPD quando o avaliador falecer no decorrer do processo
    if not sub_instance.eh_docente and (not eh_membro_cppd(request) and processo_rsc.interessado_falecido()):
        raise PermissionDenied('Você não tem permissão para acessar esta página.')

    novo_processo = ProcessoRSC()
    novo_processo.clonado = True
    novo_processo.servidor = processo_rsc.servidor
    novo_processo.status = ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD
    # verificando se o interessado é falecido
    if processo_rsc.interessado_falecido():
        novo_processo.status = ProcessoRSC.STATUS_AGUARDANDO_NOVA_VALIDACAO

    novo_processo.tipo_rsc = processo_rsc.tipo_rsc
    #   Salvando Processo novo
    novo_processo.save()
    #   Recuperando informações do processo antigo
    #   Datas documentos preliminares
    novo_processo.data_concessao_ultima_rt = processo_rsc.data_concessao_ultima_rt
    novo_processo.data_conclusao_titulacao_rsc_pretendido = processo_rsc.data_conclusao_titulacao_rsc_pretendido
    novo_processo.data_exercio_carreira = processo_rsc.data_exercio_carreira
    #   Documentos Preliminares
    for arquivo_exigido in processo_rsc.arquivosexigidos_set.all():
        arquivo_novo = ArquivosExigidos()
        arquivo_novo.processo = novo_processo
        arquivo_novo.nome = arquivo_exigido.nome
        filename = str(uuid.uuid4()) + (os.path.splitext(arquivo_novo.nome)[1] or '')
        diretorio = os.path.join(get_upload_directory(novo_processo.servidor), filename)
        arquivo_novo.diretorio = diretorio
        arquivo_novo.tipo = arquivo_exigido.tipo
        arquivo_novo.tamanho = arquivo_exigido.tamanho
        try:
            arquivo_novo.save()
            copy_file(arquivo_exigido.diretorio, arquivo_novo.diretorio)
        except FileNotFoundError:
            CloneArquivoErro.objects.get_or_create(
                tipo_arquivo=CloneArquivoErro.ARQUIVO_EXIGIDO,
                tipo_documento_exigido=arquivo_novo.get_tipo_display(),
                nome_arquivo=arquivo_exigido.nome,
                processo_rsc=novo_processo,
            )

    #   Documentos Diretrizes e Criterios
    for arquivo in processo_rsc.arquivo_set.all():
        arquivo_diretriz = Arquivo()
        arquivo_diretriz.processo = novo_processo
        arquivo_diretriz.criterio = arquivo.criterio
        arquivo_diretriz.qtd_itens = arquivo.qtd_itens
        arquivo_diretriz.nota_pretendida = arquivo.nota_pretendida
        arquivo_diretriz.data_referencia = arquivo.data_referencia

        arquivo_diretriz.nome = arquivo.nome
        filename = str(uuid.uuid4()) + (os.path.splitext(arquivo_diretriz.nome)[1] or '')
        diretorio = os.path.join(get_upload_directory(novo_processo.servidor), filename)
        arquivo_diretriz.diretorio = diretorio
        arquivo_diretriz.tamanho = arquivo.tamanho
        arquivo_diretriz.descricao = arquivo.descricao
        try:
            arquivo_diretriz.save()
            copy_file(arquivo.diretorio, arquivo_diretriz.diretorio)
        except FileNotFoundError:
            CloneArquivoErro.objects.get_or_create(
                tipo_arquivo=CloneArquivoErro.ARQUIVO,
                criterio=arquivo_diretriz.criterio,
                nome_arquivo=arquivo_diretriz.nome,
                processo_rsc=novo_processo,
            )

    novo_processo.pontuacao_pretendida = processo_rsc.pontuacao_pretendida
    novo_processo.pontuacao_pretendida_rsc1 = processo_rsc.pontuacao_pretendida_rsc1
    novo_processo.pontuacao_pretendida_rsc2 = processo_rsc.pontuacao_pretendida_rsc2
    novo_processo.pontuacao_pretendida_rsc3 = processo_rsc.pontuacao_pretendida_rsc3
    #   Introdução e Conclusão Memorial descritivo
    novo_processo.introducao_relatorio_descritivo = processo_rsc.introducao_relatorio_descritivo
    novo_processo.conclusao_relatorio_descritivo = processo_rsc.conclusao_relatorio_descritivo
    novo_processo.itinerario_formacao = processo_rsc.itinerario_formacao
    novo_processo.atuacao_docente = processo_rsc.atuacao_docente
    novo_processo.producao_cademica = processo_rsc.producao_cademica
    novo_processo.prestacao_servicos = processo_rsc.prestacao_servicos
    novo_processo.atividade_adm = processo_rsc.atividade_adm
    novo_processo.titulos_homenagens = processo_rsc.titulos_homenagens
    novo_processo.save()

    return httprr(f'/rsc/abrir_processo_rsc/{novo_processo.pk}/', 'Processo RSC clonado com sucesso.')


@csrf_exempt
@rtr()
@login_required()
def clonar_processo_rsc_mantendo_mesmo_processo_eletronico(request, processo_id):
    processo_rsc = get_object_or_404(ProcessoRSC, pk=processo_id)
    # apenas pode clonar o super usuário
    if not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão para acessar esta página.')
    if processo_rsc.status not in [ProcessoRSC.STATUS_REJEITADO, ProcessoRSC.STATUS_REPROVADO]:
        return httprr(
            '/admin/rsc/processorsc/',
            message='A solicitação de RSC não está nos status: Reprovado ou Rejeitado para permitir clonar.',
            tag='alert',
        )

    novo_processo = ProcessoRSC()
    novo_processo.servidor = processo_rsc.servidor
    novo_processo.status = ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD

    novo_processo.tipo_rsc = processo_rsc.tipo_rsc
    novo_processo.processo_eletronico = processo_rsc.processo_eletronico
    novo_processo.protocolo = processo_rsc.protocolo
    #   Salvando Processo novo
    novo_processo.save()
    #   Recuperando informações do processo antigo
    #   Datas documentos preliminares
    novo_processo.data_concessao_ultima_rt = processo_rsc.data_concessao_ultima_rt
    novo_processo.data_conclusao_titulacao_rsc_pretendido = processo_rsc.data_conclusao_titulacao_rsc_pretendido
    novo_processo.data_exercio_carreira = processo_rsc.data_exercio_carreira
    #   Documentos Preliminares
    for arquivo_exigido in processo_rsc.arquivosexigidos_set.all():
        arquivo_novo = ArquivosExigidos()
        arquivo_novo.processo = novo_processo
        arquivo_novo.nome = arquivo_exigido.nome
        filename = str(uuid.uuid4()) + (os.path.splitext(arquivo_novo.nome)[1] or '')
        diretorio = os.path.join(get_upload_directory(novo_processo.servidor), filename)
        arquivo_novo.diretorio = diretorio
        arquivo_novo.tipo = arquivo_exigido.tipo
        arquivo_novo.tamanho = arquivo_exigido.tamanho
        arquivo_novo.save()
        copy_file(arquivo_exigido.diretorio, arquivo_novo.diretorio)

    #   Documentos Diretrizes e Criterios
    for arquivo in processo_rsc.arquivo_set.all():
        arquivo_diretriz = Arquivo()
        arquivo_diretriz.processo = novo_processo
        arquivo_diretriz.criterio = arquivo.criterio
        arquivo_diretriz.qtd_itens = arquivo.qtd_itens
        arquivo_diretriz.nota_pretendida = arquivo.nota_pretendida
        arquivo_diretriz.data_referencia = arquivo.data_referencia

        arquivo_diretriz.nome = arquivo.nome
        filename = str(uuid.uuid4()) + (os.path.splitext(arquivo_diretriz.nome)[1] or '')
        diretorio = os.path.join(get_upload_directory(novo_processo.servidor), filename)
        arquivo_diretriz.diretorio = diretorio
        arquivo_diretriz.tamanho = arquivo.tamanho
        arquivo_diretriz.descricao = arquivo.descricao
        arquivo_diretriz.save()
        copy_file(arquivo.diretorio, arquivo_diretriz.diretorio)

    novo_processo.pontuacao_pretendida = processo_rsc.pontuacao_pretendida
    novo_processo.pontuacao_pretendida_rsc1 = processo_rsc.pontuacao_pretendida_rsc1
    novo_processo.pontuacao_pretendida_rsc2 = processo_rsc.pontuacao_pretendida_rsc2
    novo_processo.pontuacao_pretendida_rsc3 = processo_rsc.pontuacao_pretendida_rsc3
    #   Introdução e Conclusão Memorial descritivo
    novo_processo.introducao_relatorio_descritivo = processo_rsc.introducao_relatorio_descritivo
    novo_processo.conclusao_relatorio_descritivo = processo_rsc.conclusao_relatorio_descritivo
    novo_processo.itinerario_formacao = processo_rsc.itinerario_formacao
    novo_processo.atuacao_docente = processo_rsc.atuacao_docente
    novo_processo.producao_cademica = processo_rsc.producao_cademica
    novo_processo.prestacao_servicos = processo_rsc.prestacao_servicos
    novo_processo.atividade_adm = processo_rsc.atividade_adm
    novo_processo.titulos_homenagens = processo_rsc.titulos_homenagens
    novo_processo.save()

    return httprr(f'/rsc/abrir_processo_rsc/{novo_processo.pk}/', 'Processo RSC clonado com sucesso.')


@csrf_exempt
@rtr()
@login_required()
def abrir_processo_rsc(request, processo_id):
    processo = (
        ProcessoRSC.objects.filter(pk=processo_id)
        .select_related('servidor', 'tipo_rsc', 'servidor__cargo_emprego')
        .prefetch_related('arquivo_set')
        .first()
    )
    if not processo:
        raise Http404('Não foi encontrado processo de professor titular com o referida id')
    eh_dono_processo = eh_dono(request, processo)
    soh_cppd_e_dono(request, processo)
    title = processo.tipo_rsc

    data_conclusao_titulacao_rsc_form = DataConclusaoTitulacaoRSCForm(request=request, processo=processo)
    data_exercicio_carreira_form = DataExercicioCarreiraForm(request=request, processo=processo)
    documentos_exigidos_form = DocumentosExigidosForm(request=request, processo=processo)

    """
    buscando a última validação cppd
    """
    ultima_validacao = processo.ultima_validacao_processo()

    mostrar_resumo_problemas = (
        ultima_validacao
        and ultima_validacao.motivo_rejeicao
        and ultima_validacao.titulacao_status
        and ultima_validacao.inicio_exercicio_status
        and ultima_validacao.ultima_concessao_rt_status
        and ultima_validacao.formulario_pontuacao_status
        and ultima_validacao.relatorio_descritivo_status
    )

    tipos_rsc = TipoRsc.objects.all()

    processo_form = ProcessoRSCForm(
        data={
            'introducao_relatorio_descritivo': processo.introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_ultima_rt': processo.data_concessao_ultima_rt,
            'data_exercio_carreira': processo.data_exercio_carreira,
            'data_conclusao_titulacao_rsc_pretendido': processo.data_conclusao_titulacao_rsc_pretendido,
        },
        processo=processo,
    )

    arquivos_documentos_exigidos = ArquivosExigidos.objects.filter(processo=processo)
    for arquivo in arquivos_documentos_exigidos:
        if arquivo.tipo == ArquivosExigidos.TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO:
            processo_form.arquivo_conclusao_titulacao_rsc_pretendido = arquivo
        elif arquivo.tipo == ArquivosExigidos.INICIO_EXERCIO_CARREIRA:
            processo_form.arquivo_exercio_carreira = arquivo
        elif arquivo.tipo == ArquivosExigidos.CONCESSAO_ULTIMA_RT:
            processo_form.arquivo_concessao_ultima_rt = arquivo

    diretrizes = Diretriz.objects.all().prefetch_related('diretriz_set', 'criterio_set')

    pontuacao_requerida = 0
    data_referencia_retroatividade = None
    for tipo_rsc in tipos_rsc:
        dir_list = []
        for diretriz in tipo_rsc.diretriz_set.all():
            valor = 0
            criterio_list = []
            for criterio in diretriz.criterio_set.all():
                valor_criterio = 0
                arquivos = processo.arquivo_set.filter(criterio=criterio)
                for arquivo in arquivos:
                    valor += arquivo.nota_pretendida

                    valor_criterio += arquivo.nota_pretendida

                # somando pontos por critério
                criterio.arquivos = arquivos
                criterio.total_ponto = valor_criterio
                criterio_list.append(criterio)

            diretriz.criterios = criterio_list

            if valor > diretriz.teto:
                valor = diretriz.teto

            # somando pontos das RSCs
            pontuacao_requerida += valor

            # somando pontos das diretrizes
            diretriz.total_ponto = valor
            dir_list.append(diretriz)
        tipo_rsc.diretrizes = dir_list

        # verificando se pode ser mostrada a avaliação
        if processo.pode_mostrar_avaliacao():
            qs_avaliacoes = Avaliacao.objects.filter(processo=processo, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA])
            avaliacoes = []
            for avaliacao in qs_avaliacoes:
                ava = avaliacao
                ava.itens = (
                    avaliacao.avaliacaoitem_set.all().order_by('arquivo__criterio__diretriz__tipo_rsc', '-arquivo__criterio__numero').distinct()
                )
                ava.avaliador = avaliacao.avaliador
                if avaliacao.status == Avaliacao.INDEFERIDA:
                    ava.status = f'<strong>{avaliacao.get_status_display()}:</strong> {avaliacao.motivo_indeferimento}'
                else:
                    ava.status = f'<strong>{avaliacao.get_status_display()}</strong>'
                avaliacoes.append(ava)

    config = ConfiguracaoRSC.objects.first()
    if not config:
        raise Http404('Não foi encontrada configuração para o processo de RSC.')

    return locals()


def _atualizar_textos_processo(processo, request):
    # atualiza introducao e conclusao do processo
    processo.introducao_relatorio_descritivo = request.POST['introducao_relatorio_descritivo']
    processo.conclusao_relatorio_descritivo = request.POST['conclusao_relatorio_descritivo']
    processo.itinerario_formacao = request.POST['itinerario_formacao_txt']
    processo.atuacao_docente = request.POST['atuacao_docente_txt']
    processo.producao_cademica = request.POST['producao_cademica_txt']
    processo.prestacao_servicos = request.POST['prestacao_servicos_txt']
    processo.atividade_adm = request.POST['atividade_adm_txt']
    processo.titulos_homenagens = request.POST['titulos_homenagens_txt']


def _atualizar_campos_editaveis_processo(processo, request):
    if request.POST.get('data_concessao_ultima_rt'):
        processo.data_concessao_ultima_rt = strptime_or_default(request.POST.get('data_concessao_ultima_rt'), '%Y-%m-%d').date()
    if request.POST.get('data_exercio_carreira'):
        processo.data_exercio_carreira = strptime_or_default(request.POST.get('data_exercio_carreira'), '%Y-%m-%d').date()
    if request.POST.get('data_conclusao_titulacao_rsc_pretendido'):
        processo.data_conclusao_titulacao_rsc_pretendido = strptime_or_default(
            request.POST.get('data_conclusao_titulacao_rsc_pretendido'), '%Y-%m-%d'
        ).date()

    rsc1 = (request.POST.get('rsc1') or '').strip()
    rsc2 = (request.POST.get('rsc2') or '').strip()
    rsc3 = (request.POST.get('rsc3') or '').strip()
    if rsc1:
        processo.pontuacao_pretendida_rsc1 = Decimal(rsc1.replace(',', '.'))
    if rsc2:
        processo.pontuacao_pretendida_rsc2 = Decimal(rsc2.replace(',', '.'))
    if rsc3:
        processo.pontuacao_pretendida_rsc3 = Decimal(rsc3.replace(',', '.'))

    processo.pontuacao_pretendida = processo.pontuacao_pretendida_rsc1 + processo.pontuacao_pretendida_rsc2 + processo.pontuacao_pretendida_rsc3


def _salvar_arquivos_processo(request):
    # Agrupa as chaves 'Arquivo_<pk>_<campo>' por arquivo para evitar N+1 queries.
    campos_por_arquivo = {}
    for key in request.POST:
        key_partes = key.split('_')  # 'Arquivo_<pk>_<campo>'
        if len(key_partes) == 3 and key_partes[0] == 'Arquivo':
            campos_por_arquivo.setdefault(key_partes[1], {})[key_partes[2]] = request.POST[key]

    if not campos_por_arquivo:
        return

    for arquivo in Arquivo.objects.filter(pk__in=campos_por_arquivo.keys()):
        alterado = False
        for campo, valor in campos_por_arquivo[str(arquivo.pk)].items():
            if _aplicar_campo_arquivo(arquivo, campo, valor):
                alterado = True
        if alterado:
            arquivo.save()


def _enviar_processo_cppd(processo):
    processo.status = ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD
    validacaoCPPD = processo.ultima_validacao_processo()
    if validacaoCPPD:
        processo.status = ProcessoRSC.STATUS_AGUARDANDO_NOVA_VALIDACAO
        validacaoCPPD.ajustado = True
        validacaoCPPD.save()

    processo.save()
    return httprr('/admin/rsc/processorsc/', 'Processo enviado para CPPD, imprima os documentos.')


@csrf_exempt
@login_required()
def salvar_processo_rsc(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_dono(request, processo)
    try:
        """
        verifica status do processo
        """
        if not processo.avaliado_pode_editar() and not processo.avaliado_pode_ajustar():
            raise Exception('Você não pode alterar um processo que já foi enviado à CPPD.')

        if request.method == 'POST' and is_ajax(request):
            _atualizar_textos_processo(processo, request)

            if processo.avaliado_pode_editar():
                _atualizar_campos_editaveis_processo(processo, request)

            processo.save()

            _salvar_arquivos_processo(request)

            # trata envio a cppd
            if 'enviar_processo' in request.POST:
                return _enviar_processo_cppd(processo)

        retorno = {'ok': True, 'msg': ''}
        data_referencia_retroativa = processo.get_data_referencia_retroativa()
        if data_referencia_retroativa:
            retorno['data_referencia_retroatividade'] = format_datetime(data_referencia_retroativa)
        else:
            retorno['data_referencia_retroatividade'] = '-'

        return JsonResponse(retorno)
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
def atualizar_processo_eletronico_rsc(request):
    if not (eh_presidente_cppd(request) or request.user.is_superuser):
        raise PermissionDenied

    title = 'Atualizar processo RSC'
    form = AtualizarProcessoRSCForm(request.POST or None)
    if form.is_valid():
        if form.processar():
            return httprr('/admin/rsc/processorsc/', 'Processo de RSC atualizado com sucesso')

    return locals()


def _cadastrar_processo(processo, request, servidor_docente_do_processo_rsc, setor_processo):
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        processo_tramite = {
            'tipo_processo': TipoProcesso.objects.get(id=517),
            'assunto': 'Reconhecimento de Saberes e Competências - RSC',
            'setor_destino': get_setor_cppd(),
        }

        processo.processo_eletronico = ProcessoEletronico.cadastrar_processo(
            user=request.user,
            processo_tramite=processo_tramite,
            papel=request.user.get_relacionamento().papeis_ativos.first(),
            documentos_texto=[],
            documentos_digitalizados=[],
            interessados=servidor_docente_do_processo_rsc,
            setor_processo=setor_processo,
        )
    else:
        # Cria protocolo físico
        protocolo = Processo()
        protocolo.assunto = 'Requerimento RSC'
        protocolo.pessoa_interessada = processo.servidor
        protocolo.tipo = Processo.TIPO_REQUERIMENTO
        protocolo.save()

        tramite = Tramite()
        tramite.processo = protocolo
        tramite.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
        tramite.orgao_interno_encaminhamento = setor_processo or get_setor()
        tramite.orgao_interno_recebimento = get_setor_cppd()
        tramite.pessoa_encaminhamento = request.user.get_profile()
        tramite.data_encaminhamento = datetime.datetime.now()
        tramite.ordem = 1
        tramite.save()

        processo.protocolo = protocolo
        processo.finalizar_processo()


@csrf_exempt
@login_required()
@require_POST
def salvar_arquivo_rsc(request, arquivo_id):
    try:
        arquivo = Arquivo.objects.get(encrypted_pk=arquivo_id)
        soh_dono(request, arquivo.processo)
        if not arquivo.processo.avaliado_pode_editar() and not arquivo.processo.avaliado_pode_ajustar():
            raise Exception('Você não pode alterar um processo que já foi enviado à CPPD.')

        qtd = request.POST.get(f'Arquivo_{arquivo.id}_qtd', '').strip()
        data = request.POST.get(f'Arquivo_{arquivo.id}_data', '').strip()
        descricao = request.POST.get(f'Arquivo_{arquivo.id}_descricao', '').strip()
        if not qtd or not data or not descricao:
            raise Exception('Preencha Quantidade, Data de Referência e Descrição deste arquivo antes de salvá-lo.')

        if not _aplicar_campo_arquivo(arquivo, 'qtd', qtd):
            raise Exception('Quantidade inválida para este arquivo.')
        if not _aplicar_campo_arquivo(arquivo, 'data', data):
            raise Exception('Data de Referência inválida para este arquivo.')
        if not _aplicar_campo_arquivo(arquivo, 'descricao', descricao):
            raise Exception('Descrição inválida para este arquivo.')
        arquivo.nota_pretendida = arquivo.qtd_itens * arquivo.criterio.fator * arquivo.criterio.diretriz.peso
        arquivo.save()

        retorno = {'ok': True, 'msg': '', 'pontuacao_arquivo': str(arquivo.nota_pretendida)}
        data_referencia_retroativa = arquivo.processo.get_data_referencia_retroativa()
        retorno['data_referencia_retroatividade'] = format_datetime(data_referencia_retroativa) if data_referencia_retroativa else '-'
        return JsonResponse(retorno)
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0] if e.args else 'Erro ao salvar o arquivo.'})


@rtr()
def enviar_processo_rsc(request, processo_id):
    title = 'Assinatura do requerimento para confirmar o envio'
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)

    # verificar os arquivos do processo em busca de arquivos com datas ou quantidade de itens nulos
    problema_arquivo = Arquivo.objects.filter(processo=processo).filter(Q(data_referencia__isnull=True) | Q(qtd_itens__isnull=True)).exists()
    if problema_arquivo:
        return httprr(
            request.META.get('HTTP_REFERER'),
            'Existe(m) arquivo(s) faltando o preenchimento da data ou quantidade de itens. Identifique de forma mais fácil o problema no Quandro de Resumo.',
            'error',
        )

    soh_dono(request, processo)

    form = AssinaturaRequerimentoForm(
        request.POST or None,
        request=request,
        conteudo=processo.conteudo_a_ser_assinado_do_requerimento,
        chave=processo.chave_a_ser_utilizada_na_assinatura_do_requerimento,
    )

    if form.is_valid() and form.assinatura_is_valida() and (processo.avaliado_pode_editar() or processo.avaliado_pode_ajustar()):
        try:
            servidor = request.user.get_relacionamento()
            setor_servidor = servidor.setor
            if servidor.eh_aposentado:
                if servidor.setor_lotacao:
                    setor_servidor = servidor.setor_lotacao.uo.equivalente.setor
                else:
                    setor_servidor = Setor.objects.suap_ativos().get(sigla=get_sigla_reitoria())

            msg_erro_campos_nao_preenchidos = (
                'Existem campos que não foram preenchidos corretamente. Verifique na aba Quadro de Quadro de Resumo quais as informações incorretas.'
            )
            msg_erro_nao_associado_setor = 'Você não está associado a nenhum Setor. Por favor contactar a gestão de pessoas do seu campus.'

            if not setor_servidor:
                form.add_error(None, msg_erro_nao_associado_setor)

            if request.method == 'POST':
                if processo.avaliado_pode_editar() and not processo.protocolo:
                    if not setor_servidor:
                        return JsonResponse({'ok': False, 'msg': msg_erro_nao_associado_setor})

                    ########################################################################
                    # Verificando se todos os arquivos estão com as informações necessárias
                    ########################################################################
                    if Arquivo.objects.filter(Q(data_referencia__isnull=True) | Q(qtd_itens__isnull=True), processo=processo).exists():
                        return JsonResponse({'ok': False, 'msg': msg_erro_campos_nao_preenchidos})

                ########################################################################
                # Verificando se todos os arquivos estão com as informações necessárias
                ########################################################################
                if Arquivo.objects.filter(Q(data_referencia__isnull=True) | Q(qtd_itens__isnull=True), processo=processo).exists():
                    form.add_error(None, msg_erro_campos_nao_preenchidos)

                processo.assinatura_requerimento = form.assinatura
                ######################
                # Abertura do processo
                ######################
                servidor_docente_do_processo_rsc = [processo.servidor.get_vinculo()]
                _cadastrar_processo(processo, request, servidor_docente_do_processo_rsc, setor_servidor)

                processo.status = ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD
                ######################################################
                # processo.ano_envio_cppd = datetime.date.today().year
                ######################################################
                validacaoCPPD = processo.ultima_validacao_processo()

                if validacaoCPPD:
                    processo.status = ProcessoRSC.STATUS_AGUARDANDO_NOVA_VALIDACAO
                    validacaoCPPD.ajustado = True
                    validacaoCPPD.save()
                processo.save()
                return httprr('/admin/rsc/processorsc/', 'Processo RSC enviado para CPPD', close_popup=True)
        except Exception as ex:
            form.add_error(None, f'Erro ao enviar para CPPD, tente novamente. ERROR: {ex}')
    return locals()


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
@transaction.atomic
def validar_processorsc(request, processo_id):
    soh_cppd(request)
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    title = f'Validação do Processo {processo}'

    if not processo.pode_ser_validado():
        raise PermissionDenied('Você não tem permissão para acessar esta página!')

    arquivos = processo.arquivo_set.exclude(descricao='').order_by('data_referencia').distinct()
    arquivos_producoes_academicas = arquivos.filter(criterio__categoria_memorial_descritivo__pk=1)
    arquivos_descricoes_atividades_administracao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=2)
    arquivos_prestacoes_de_servicos = arquivos.filter(criterio__categoria_memorial_descritivo__pk=3)
    arquivos_titulos_e_homenagens = arquivos.filter(criterio__categoria_memorial_descritivo__pk=4)
    arquivos_atauacao_docente = arquivos.filter(criterio__categoria_memorial_descritivo__pk=5)
    arquivos_itinerario_de_formacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=6)

    btn_aceitar = ValidacaoCPPD.ACAO_CHOICES[ValidacaoCPPD.ACAO_ACEITAR][1]
    btn_devolver = ValidacaoCPPD.ACAO_CHOICES[ValidacaoCPPD.ACAO_DEVOLVER][1]
    btn_rejeitar = ValidacaoCPPD.ACAO_CHOICES[ValidacaoCPPD.ACAO_REJEITAR][1]

    choice_validacao_arquivo = ValidacaoCPPD.TIPO_VALIDACAO_CHOICE

    validacoes_processo = ValidacaoCPPD.objects.filter(processo=processo).order_by('-data')

    form = ValidacaoCPPDForm(request.POST or None, processo=processo, request=request)

    if request.method == 'POST' and is_ajax(request):
        try:
            msg = 'Validação concluída com sucesso!'
            acao = request.POST.get('acao')
            ok = True

            """
            ajustando variável ação
            """
            if acao == 'aceitar':
                acao_valor = ValidacaoCPPD.ACAO_ACEITAR
            if acao == 'devolver':
                acao_valor = ValidacaoCPPD.ACAO_REJEITAR
            if acao == 'rejeitar':
                acao_valor = ValidacaoCPPD.ACAO_REJEITAR

            """
            gerando objeto ValidacaoCPPD
            """
            validacaoCPPD = ValidacaoCPPD()
            validacaoCPPD.acao = acao_valor
            validacaoCPPD.processo = processo
            validacaoCPPD.validador = request.user.get_relacionamento()

            if acao != 'rejeitar':
                """
                verificando titulação
                """
                titulacao_status = request.POST.get('titulacao_status')
                if titulacao_status == '0':
                    raise Exception('O título que habilita ao RSC pretendido (mestrado, especialização ou graduação) não está validado!')

                inicio_exercicio_status = request.POST.get('inicio_exercicio_status')
                if inicio_exercicio_status == '0':
                    raise Exception('O exercício na carreira de EBTT não está validado!')

                if processo.tipo_rsc.nome != 'RSC-I':
                    ultima_concessao_rt_status = request.POST.get('ultima_concessao_rt_status')
                    if ultima_concessao_rt_status == '0':
                        raise Exception('A concessão da última RT não está validada.')

                formulario_pontuacao_status = request.POST.get('formulario_pontuacao_status')
                if formulario_pontuacao_status == '0' and acao == 'aceitar':
                    raise Exception('O aceite NÃO foi possível pois o fomulário de pontuação não foi confirmado!')

                relatorio_descritivo = request.POST.get('relatorio_descritivo')
                if not relatorio_descritivo:
                    raise Exception('Você precisa avaliar o relatório descritivo!')

                relatorio_descritivo_status = request.POST.get('relatorio_descritivo_status')
                if relatorio_descritivo_status == '0' and acao == 'aceitar':
                    raise Exception('O aceite NÃO foi possível pois o relatório descritivo não foi confirmado!')

                """
                validando data de conclusão
                """
                titulacao = request.POST.get('processo_titulacao')
                data_titulacao_validada = request.POST.get('data_conclusao_titulacao_rsc_pretendido_validada')
                if int(titulacao) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_titulacao_validada == '':
                    raise Exception('A data de conclusão validada deve ser preenchida.')
                if not data_titulacao_validada:
                    data_titulacao_validada = processo.data_conclusao_titulacao_rsc_pretendido
                else:
                    data_titulacao_validada = strptime_or_default(data_titulacao_validada, '%Y-%m-%d').date()

                """
                validando data do início de exercício
                """
                inicio_exercicio = request.POST.get('processo_exercicio_ebtt')
                data_inicio_exercicio_validada = request.POST.get('data_exercio_carreira_validada')
                if int(inicio_exercicio) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_inicio_exercicio_validada == '':
                    raise Exception('A data do início de exercício deve ser preenchida.')
                if not data_inicio_exercicio_validada:
                    data_inicio_exercicio_validada = processo.data_exercio_carreira
                else:
                    data_inicio_exercicio_validada = strptime_or_default(data_inicio_exercicio_validada, '%Y-%m-%d').date()

                """
                validando data de concessão da última RT
                """
                if processo.tipo_rsc.nome != 'RSC-I':
                    ultima_rt = request.POST.get('processo_ultima_rt')
                    data_ultima_rt_validada = request.POST.get('data_concessao_ultima_rt_validada')
                    if int(ultima_rt) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_ultima_rt_validada == '':
                        raise Exception('A data dos efeitos da concessão da última RT validada deve ser preenchida.')
                    if not data_ultima_rt_validada:
                        data_ultima_rt_validada = processo.data_concessao_ultima_rt
                    else:
                        data_ultima_rt_validada = strptime_or_default(data_ultima_rt_validada, '%Y-%m-%d').date()

                """
                completando objeto validacaoCPPD
                """
                validacaoCPPD.data_conclusao_titulacao_rsc_pretendido_validada = data_titulacao_validada
                validacaoCPPD.titulacao_status = titulacao_status
                validacaoCPPD.data_exercio_carreira_validada = data_inicio_exercicio_validada
                validacaoCPPD.inicio_exercicio_status = inicio_exercicio_status

                if processo.tipo_rsc.nome != 'RSC-I':
                    validacaoCPPD.data_concessao_ultima_rt_validada = data_ultima_rt_validada
                    validacaoCPPD.ultima_concessao_rt_status = ultima_concessao_rt_status

                validacaoCPPD.formulario_pontuacao_status = formulario_pontuacao_status
                validacaoCPPD.relatorio_descritivo_status = relatorio_descritivo_status

                """
                devolvendo o processo para
                """
                if acao == 'devolver':
                    processo.status = ProcessoRSC.STATUS_AGUARDANDO_AJUSTES_USUARIO
                    motivo_rejeicao = request.POST.get('motivo_rejeicao')
                    if not motivo_rejeicao or motivo_rejeicao == '':
                        raise Exception('O motivo da devolução deve ser preenchido.')
                    else:
                        validacaoCPPD.motivo_rejeicao = motivo_rejeicao
                        ok = True
                    msg = 'Processo devolvido para ajustes do usuário.'

                """
                aceitando o processo
                """
                if acao == 'aceitar':
                    motivo_rejeicao = request.POST.get('motivo_rejeicao')
                    processo.status = ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES
                    validacaoCPPD.processo = processo
                    validacaoCPPD.motivo_rejeicao = motivo_rejeicao
                    msg = 'Processo aceito.'
                    ok = True

            else:
                motivo_rejeicao = request.POST.get('motivo_rejeicao')
                if not motivo_rejeicao or motivo_rejeicao == '':
                    raise Exception('O motivo da rejeição deve ser preenchido.')
                else:
                    validacaoCPPD.motivo_rejeicao = motivo_rejeicao
                    processo.status = ProcessoRSC.STATUS_REJEITADO
                msg = 'Processo rejeitado com sucesso!'

            processo.save()

            validacaoCPPD.save()

        except Exception as e:
            ok = False
            msg = e.args[0]
        return JsonResponse({'msg': msg, 'url': '/admin/rsc/processorsc/', 'ok': ok})

    return locals()


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def rejeitar_processo_cppd(request, processo_id):
    soh_cppd(request)
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    title = 'Rejeitar Processo'

    form = RejeitarProcessoCPPDForm(request.POST or None, request=request, processo=processo)
    if request.POST and form.is_valid():
        try:
            form.processar()
            return httprr('..', 'Processo rejeitado com sucesso.')
        except Exception as e:
            return httprr('.', e.args[0], 'error')

    return locals()


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def selecionar_avaliadores(request, processo_id):
    soh_cppd(request)
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    title = f'Selecionar avaliadores {processo}'

    form = AvaliadorForm(request.POST or None, processo=processo)
    if request.POST and form.is_valid():
        try:
            form.processar(request.user.get_vinculo())
            return httprr('..', 'Avaliadores selecionados com sucesso.')
        except Exception as e:
            msg = e.args[0]
            if isinstance(msg, list):
                msg = '<br />'.join(msg)
            return httprr('.', msg, 'error')

    return locals()


@rtr()
@login_required()
def acompanhar_avaliacao(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)

    soh_cppd_e_dono(request, processo)

    title = f'Acompanhamento do Processo {processo}'
    ultima_validacao = processo.ultima_validacao_processo()

    eh_membro_do_cppd = eh_presidente_cppd(request) or eh_membro_cppd(request)

    data_exercio_carreira = processo.data_exercio_carreira
    if ultima_validacao and ultima_validacao.data_exercio_carreira_validada != data_exercio_carreira:
        data_exercio_carreira = '{} (Validada pela CPPD: {})'.format(
            data_exercio_carreira and data_exercio_carreira.strftime('%Y-%m-%d'),
            ultima_validacao.data_exercio_carreira_validada and ultima_validacao.data_exercio_carreira_validada.strftime('%d/%m/%Y'),
        )

    data_conclusao_titulacao_rsc_pretendido = processo.data_conclusao_titulacao_rsc_pretendido
    if ultima_validacao and ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada != data_conclusao_titulacao_rsc_pretendido:
        data_conclusao_titulacao_rsc_pretendido = '{} (Validada pela CPPD: {})'.format(
            data_conclusao_titulacao_rsc_pretendido and data_conclusao_titulacao_rsc_pretendido.strftime('%Y-%m-%d'),
            ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada
            and ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada.strftime('%Y-%m-%d'),
        )

    data_concessao_ultima_rt = processo.data_concessao_ultima_rt
    if ultima_validacao and ultima_validacao.data_concessao_ultima_rt_validada != data_concessao_ultima_rt:
        data_concessao_ultima_rt = '{} (Validada pela CPPD: {})'.format(
            data_concessao_ultima_rt and data_concessao_ultima_rt.strftime('%Y-%m-%d'),
            ultima_validacao.data_concessao_ultima_rt_validada and ultima_validacao.data_concessao_ultima_rt_validada.strftime('%Y-%m-%d'),
        )

    data_referencia_validada = processo.get_data_referencia_final()
    data_referencia_documentos = processo.get_data_referencia_retroativa(True, True)

    avaliadores_selecionados = []
    eh_dono_processo = eh_dono(request, processo)
    eh_dono_processo_ou_presidente_cppd = eh_dono(request, processo) or eh_presidente_cppd(request)
    is_superuser = request.user.is_superuser

    estado_processo = ProcessoRSC.STATUS_CHOICES[processo.estado_atual_processo()][1]
    estado_processo_class_css = 'alert'
    if processo.estado_atual_processo() == 0:
        estado_processo_class_css = 'success'
    elif processo.estado_atual_processo() == 1:
        estado_processo_class_css = 'error'

    """
    verificando avaliadores internos
    """
    processo_avaliadores = ProcessoAvaliador.objects.filter(processo=processo)
    avaliadores_internos_reserva = []
    avaliadores_internos_excluidos = []
    avaliadores_externos_reserva = []
    avaliadores_externos_excluidos = []
    for processo_avaliador in processo_avaliadores:
        avaliacao = Avaliacao.objects.filter(processo=processo_avaliador.processo, avaliador=processo_avaliador.avaliador)
        if avaliacao.exists():
            avaliacao = avaliacao[0]
            if avaliacao.status == Avaliacao.INDEFERIDA:
                avaliacao_status = f'<strong>{avaliacao.get_status_display()}:</strong> {avaliacao.motivo_indeferimento}'
            else:
                avaliacao_status = f'<strong>{avaliacao.get_status_display()}</strong>'
        else:
            avaliacao_status = None

        data_referencia_validada_avaliador = processo.get_data_referencia_retroativa(True, False, processo_avaliador.avaliador)
        pontuacao_validada = processo._calculo_pontos(
            [Avaliacao.EM_AVALIACAO, Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], True, processo_avaliador.avaliador
        )

        if processo_avaliador.avaliador.eh_interno():
            """
            avaliador interno principal
            """
            if processo_avaliador.avaliador_principal():
                avaliador_interno_selecionado = processo_avaliador.avaliador
                if eh_dono_processo and not processo.pode_mostrar_avaliacao():
                    avaliador_interno_selecionado.nome = 'Avaliador Interno'
                else:
                    avaliador_interno_selecionado.nome = processo_avaliador.avaliador.eh_interno()
                avaliador_interno_selecionado.pontuacao_validada = pontuacao_validada
                avaliador_interno_selecionado.data_referencia_validada = data_referencia_validada_avaliador
                avaliador_interno_selecionado.situacao = processo_avaliador.situacao_avaliador()
                avaliador_interno_selecionado.data_limite = processo_avaliador.data_limite_display()
                avaliador_interno_selecionado.avaliacao_status = avaliacao_status
                avaliador_interno_selecionado.responsavel_cadastro = processo_avaliador.responsavel_cadastro

                avaliadores_selecionados.append(avaliador_interno_selecionado)
            """
            avaliadores internos reservas
            """
            if processo_avaliador.avaliador_reserva():
                avaliador_interno_reserva = processo_avaliador.avaliador.eh_interno()
                avaliadores_internos_reserva.append(avaliador_interno_reserva)
            """
            avaliadores internos excluídos do processo
            """
            if processo_avaliador.avaliador_excluido_processo():
                avaliador_interno_excluido = processo_avaliador.avaliador
                if eh_dono_processo and not processo.pode_mostrar_avaliacao():
                    avaliador_interno_excluido.nome = 'Avaliador Interno'
                else:
                    avaliador_interno_excluido.nome = processo_avaliador.avaliador.eh_interno()
                if processo_avaliador.tipo_recusa:
                    avaliador_interno_status = f'Recusado pelo avaliador. Tipo recusa: {processo_avaliador.get_tipo_recusa_display()}. Motivo da recusa: {processo_avaliador.motivo_recusa}.'
                elif processo_avaliador.avaliacao_correspondente() and processo_avaliador.avaliacao_correspondente().tipo_desistencia:
                    aval = processo_avaliador.avaliacao_correspondente()
                    avaliador_interno_status = f'Desistência do avaliador. Tipo desistência: {aval.get_tipo_desistencia_display()}. Motivo desistência: {aval.motivo_desistencia}.'
                else:
                    avaliador_interno_status = processo_avaliador.get_status_display()
                avaliador_interno_excluido.status = avaliador_interno_status
                avaliadores_internos_excluidos.append(avaliador_interno_excluido)

        else:
            """
            avaliador externo principal
            """
            if processo_avaliador.avaliador_principal():
                avaliador_externo_selecionado = processo_avaliador.avaliador
                if eh_dono_processo and not processo.pode_mostrar_avaliacao():
                    avaliador_externo_selecionado.nome = 'Avaliador Externo'
                else:
                    avaliador_externo_selecionado.nome = processo_avaliador.avaliador.eh_externo()
                avaliador_externo_selecionado.pontuacao_validada = pontuacao_validada
                avaliador_externo_selecionado.data_referencia_validada = data_referencia_validada_avaliador
                avaliador_externo_selecionado.situacao = processo_avaliador.situacao_avaliador()
                avaliador_externo_selecionado.data_limite = processo_avaliador.data_limite_display()
                avaliador_externo_selecionado.avaliacao_status = avaliacao_status
                avaliador_externo_selecionado.responsavel_cadastro = processo_avaliador.responsavel_cadastro
                avaliadores_selecionados.append(avaliador_externo_selecionado)
            """
            avaliadores externos reservar
            """
            if processo_avaliador.avaliador_reserva():
                avaliador_externo_reserva = processo_avaliador.avaliador.eh_externo()
                avaliadores_externos_reserva.append(avaliador_externo_reserva)
            """
            avaliadores externos excluídos do processo
            """
            if processo_avaliador.avaliador_excluido_processo():
                avaliador_externo_excluido = processo_avaliador.avaliador
                if eh_dono_processo and not processo.pode_mostrar_avaliacao():
                    avaliador_externo_excluido.nome = 'Avaliador Externo'
                else:
                    avaliador_externo_excluido.nome = processo_avaliador.avaliador.eh_externo()
                if processo_avaliador.tipo_recusa:
                    avaliador_externo_status = f'Recusado pelo avaliador. Tipo recusa: {processo_avaliador.get_tipo_recusa_display()}. Motivo da recusa: {processo_avaliador.motivo_recusa}.'
                elif processo_avaliador.avaliacao_correspondente() and processo_avaliador.avaliacao_correspondente().tipo_desistencia:
                    aval = processo_avaliador.avaliacao_correspondente()
                    avaliador_externo_status = f'Desistência do avaliador. Tipo desistência: {aval.get_tipo_desistencia_display()}. Motivo desistência: {aval.motivo_desistencia}.'
                else:
                    avaliador_externo_status = processo_avaliador.get_status_display()
                avaliador_externo_excluido.status = avaliador_externo_status
                avaliadores_externos_excluidos.append(avaliador_externo_excluido)

    return locals()


@rtr()
@login_required()
def processo_avaliacao(request):
    title = 'Processos para Avaliação'
    vinculo = request.user.get_vinculo()

    """
    processos aguardando aceite
    """
    processos_avaliacao = ProcessoAvaliador.objects.filter(
        status=ProcessoAvaliador.AGUARDANDO_ACEITE,
        avaliador__vinculo=vinculo,
        processo__status__in=[ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO],
    )

    """
    processos em avaliação
    """
    processos_em_avaliacao = ProcessoAvaliador.objects.filter(
        status=ProcessoAvaliador.EM_AVALIACAO, avaliador__vinculo=vinculo, processo__status=ProcessoRSC.STATUS_EM_AVALIACAO
    )

    """
    avaliações concluídas
    """
    avaliacoes_concluidas = ProcessoAvaliador.objects.filter(status=ProcessoAvaliador.AVALIACAO_FINALIZADA, avaliador__vinculo=vinculo)

    return locals()


@login_required()
@permission_required('rsc.pode_validar_processorsc')
def revisar_datas_limite(request):
    from django.core.management import call_command

    call_command('checa_datas_processos_rsc')
    return httprr('..', 'Avaliadores atualizados.')


@login_required()
@permission_required('rsc.view_processoavaliador')
def reenviar_email_avaliador(request, processo_avaliador_id):
    processo_avaliador = get_object_or_404(ProcessoAvaliador, pk=processo_avaliador_id)
    if not processo_avaliador.pode_reenviar_email():
        return httprr('/admin/rsc/processoavaliador/', 'Não é possível reenviar e-mail para esta situação.', tag='error')
    email_destino = processo_avaliador.reenviar_email()
    return httprr('/admin/rsc/processoavaliador/', f'E-mail reenviado com sucesso para {email_destino}.')


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc,rsc.pode_ver_relatorio_rsc')
def dashboard(request):
    title = 'Painel RSC'
    form = DashboardFiltroForm(request.GET or None)
    ano = datetime.date.today().year
    tipo_rsc = None
    if form.is_valid():
        ano = int(form.cleaned_data.get('ano') or ano)
        tipo_rsc = form.cleaned_data.get('tipo_rsc')
    qs = rsc_dashboard.base_queryset(tipo_rsc.id if tipo_rsc else None)

    indicadores = rsc_dashboard.indicadores(qs)

    grafico_situacao = ColumnChart('grafico_situacao', title='Processos por situação', data=rsc_dashboard.dados_por_situacao(qs))
    grafico_tipo = PieChart('grafico_tipo', title='Processos por tipo de RSC', data=rsc_dashboard.dados_por_tipo_rsc(qs))
    grafico_unidade = BarChart('grafico_unidade', title='Processos por unidade', data=rsc_dashboard.dados_por_unidade(qs))
    grafico_resultado = PieChart('grafico_resultado', title='Resultado dos processos finalizados', data=rsc_dashboard.dados_resultado(qs))
    grafico_finalizados = ColumnChart(
        'grafico_finalizados', title=f'Finalizados por mês ({ano})', data=rsc_dashboard.dados_finalizados_por_mes(qs, ano)
    )

    lista_acao_cppd = rsc_dashboard.processos_acao_cppd(qs)
    lista_prazo_critico = rsc_dashboard.avaliadores_prazo_critico()
    lista_sem_reserva = rsc_dashboard.processos_sem_reserva(qs)
    lista_avaliadores_incompletos = rsc_dashboard.processos_avaliadores_incompletos(qs)

    return locals()


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc,rsc.pode_ver_relatorio_rsc')
def relatorio_situacao(request):
    """Situação dos processos que entraram no ano, com o andamento da banca dos que estão em análise.

    Com ``?xls=1`` devolve a mesma informação em planilha, uma aba por situação.
    """
    title = 'Situação dos processos'
    form = RelatorioSituacaoFiltroForm(request.GET or None)
    ano = datetime.date.today().year
    tipo_rsc = None
    if form.is_valid():
        ano = int(form.cleaned_data.get('ano') or ano)
        tipo_rsc = form.cleaned_data.get('tipo_rsc')

    grupos = rsc_relatorio_situacao.montar_relatorio(ano, tipo_rsc.id if tipo_rsc else None)
    if request.GET.get('xls') == '1':
        return XlsResponse(rsc_relatorio_situacao.linhas_xls(grupos), name=f'rsc_situacao_processos_{ano}')

    parametros_xls = request.GET.copy()
    parametros_xls['xls'] = '1'
    url_xls = f'?{parametros_xls.urlencode()}'
    return locals()


@rtr()
@login_required()
def aceitar_rejeitar_processo(request, processo_id):
    processo_avaliador = get_object_or_404(ProcessoAvaliador, pk=processo_id)
    request.user.get_relacionamento()

    if not eh_avaliador_do_processo(request, processo_avaliador.processo_id):
        raise PermissionDenied('Você não é avaliador deste processo.')

    if processo_avaliador.processo.status not in [ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO]:
        raise PermissionDenied('Processo não pode ser aceito ou rejeitado')

    if request.GET.get('acao') == 'rejeitar':
        msg = 'Avaliação rejeitada com sucesso.'
        processo_avaliador.rejeitar()
    else:
        msg = 'Avaliação aceita com sucesso.'
        processo_avaliador.aceitar()

    if request.method == 'POST' and is_ajax(request):
        return JsonResponse({'ok': True, 'msg': msg})
    else:
        return httprr('/rsc/processo_avaliacao/', msg)


@rtr()
@login_required()
def avaliar_processo(request, processo_id, avaliador_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    avaliador = get_object_or_404(Avaliador, pk=avaliador_id)

    if not ProcessoAvaliador.objects.filter(processo__id=processo_id, avaliador__id=avaliador_id).exists():
        raise PermissionDenied('Você não é avaliador deste processo.')

    title = f'Avaliar Processo {processo}'
    eh_dono_processo = eh_dono(request, processo)

    data_referencia = processo.get_data_referencia_retroativa()
    data_referencia_validada = processo.get_data_referencia_retroativa(True, False, avaliador)
    data_referencia_arquivos = processo.get_data_referencia_retroativa(False, True)
    pontuacao_validada_com_corte = processo._calculo_pontos([Avaliacao.EM_AVALIACAO, Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], True, avaliador)

    # verificando se existe avaliação criada para o avaliador passado
    avaliacao = Avaliacao.objects.filter(processo=processo, avaliador=avaliador)
    if not avaliacao.exists():
        processo.criar_avaliacao(avaliador)
        avaliacao = Avaliacao.objects.filter(processo=processo, avaliador=avaliador)

    avaliacao = avaliacao[0]
    if not (processo.status == ProcessoRSC.STATUS_EM_AVALIACAO or avaliacao.status in [Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]):
        raise PermissionDenied('Processo não pode ser avaliado.')

    if avaliacao.status == Avaliacao.EM_AVALIACAO:
        if pontuacao_validada_com_corte < 25:
            avaliacao_status = 'No momento a avaliação não está atingindo a pontuação mínima necessária no RSC pretendido.'
        elif pontuacao_validada_com_corte > 25 and pontuacao_validada_com_corte < 50:
            avaliacao_status = 'No momento a avaliação não está atingindo a pontuação mínima necessária na soma do RSC-I, RSC-II e RSC-III.'
        elif pontuacao_validada_com_corte >= 50:
            avaliacao_status = 'No momento a avaliação está deferindo o pedido de RSC.'
    else:
        avaliacao_status = avaliacao.get_status_display()

    arquivos_rsc1 = avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-I').order_by('arquivo__criterio__numero')
    arquivos_rsc2 = avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-II').order_by('arquivo__criterio__numero')
    arquivos_rsc3 = avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-III').order_by('arquivo__criterio__numero')

    config = ConfiguracaoRSC.objects.first()
    if not config:
        raise Http404('Não foi encontrada configuração para o processo de RSC.')

    return locals()


@rtr()
@login_required()
def avaliar_item(request, avaliacao_item_id):
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=avaliacao_item_id)

    if not eh_avaliador_da_avaliacao(request, avaliacao_item.avaliacao_id):
        raise PermissionDenied('Você não é avaliador deste processo.')

    title = f'{avaliacao_item.arquivo.criterio.diretriz.nome} - {avaliacao_item.arquivo.criterio.diretriz.descricao}'
    criterio = f'{avaliacao_item.arquivo.criterio.numero} - {avaliacao_item.arquivo.criterio.nome}'

    return locals()


@rtr()
@login_required()
def salvar_avaliacao(request, avaliacao_item_id):
    try:
        justificar = False
        # selecionando o item da avaliação
        item_avaliacao = AvaliacaoItem.objects.get(id=avaliacao_item_id)

        if not eh_avaliador_da_avaliacao(request, item_avaliacao.avaliacao_id):
            raise Exception('Você não é avaliador deste processo.')

        data_referencia = request.POST.get(f'data_referencia_validada_{avaliacao_item_id}')
        if data_referencia:
            data_tmp = strptime_or_default(data_referencia, '%d/%m/%Y')
            item_avaliacao.data_referencia = None
            if data_tmp:
                item_avaliacao.data_referencia = data_tmp.date()
            else:
                raise Exception(f'A data {data_referencia} não é uma data válida.')

        qtd_itens_validado = request.POST.get(f'qtd_itens_validado_{avaliacao_item_id}')
        if int(qtd_itens_validado) > item_avaliacao.arquivo.criterio.teto:
            msg_erro = f'A quantidade do item ({qtd_itens_validado}) é maior que o teto do critério ({item_avaliacao.arquivo.criterio.teto}). Por favor, corrija e tente finalizar novamente.'
            raise Exception(msg_erro)
        if qtd_itens_validado and int(qtd_itens_validado) < 0:
            raise Exception('Não é permitido quantidade de items negativo. Por favor, corrija e tente finalizar novamente.')
        else:
            if qtd_itens_validado:
                item_avaliacao.qtd_itens_validado = qtd_itens_validado
            else:
                item_avaliacao.qtd_itens_validado = None

        """
        verificando se a data de referência ou quantidade de item foram alterados
        """
        justificativa = request.POST.get(f'justificativa_avaliacao_{avaliacao_item_id}')
        if item_avaliacao.houve_alteracao_avaliacao() and not justificativa:
            justificar = True
            raise Exception(
                'Sua avaliação alterou a data de referência requerida ou a quantidade de pontos. É necessário justificar suas modificações.'
            )

        if justificativa:
            item_avaliacao.justificativa = justificativa

        item_avaliacao.save()

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0], 'justificar': justificar})


@rtr()
@login_required()
@permission_required('rsc.pode_avaliar_processorsc')
def finalizar_avaliacao(request, avaliacao_id):
    try:
        avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)

        if not eh_avaliador_da_avaliacao(request, avaliacao.id):
            raise Exception('Você não é avaliador desta avaliação.')

        if not (avaliacao.status == Avaliacao.EM_AVALIACAO):
            raise Exception('Não é permitido finalizar uma avaliação que não esteja na situação "EM AVALIAÇÃO".')

        avaliacao.finalizar_avaliacao()

        return JsonResponse({'ok': True, 'msg': 'Avaliação finalizada com sucesso.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def finalizar_processo(request, processo_id):
    try:
        soh_cppd(request)
        processo = get_object_or_404(ProcessoRSC, pk=processo_id)

        if 'processo_eletronico' in settings.INSTALLED_APPS:
            if not processo.protocolo:
                arquivo = gerar_processo_completo(request, processo_id)
                arq = open(f'/tmp/processo_rsc_completo_{processo_id}.pdf', 'wb+')
                arq.write(arquivo.content)

                arquivo_memorial_descritivo = relatorio_descritivo_pdf(request, processo_id)
                arq_memorial_descritivo = open(f'/tmp/relatorio_descritivo_{processo_id}.pdf', 'wb+')
                arq_memorial_descritivo.write(arquivo_memorial_descritivo.content)

                arquivo_formulario_pontuacao = formulario_pontuacao_pdf(request, processo_id)
                arq_formulario_pontuacao = open(f'/tmp/formulario_pontuacao_{processo_id}.pdf', 'wb+')
                arq_formulario_pontuacao.write(arquivo_formulario_pontuacao.content)

                from documento_eletronico.models import TipoDocumento

                documentos_digitalizados = [
                    {
                        'tipo': TipoDocumento.objects.get(id=5),
                        'tipo_conferencia': TipoConferencia.objects.first(),
                        'assunto': 'Formulário de pontuação requerida',
                        'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
                        'arquivo': arq_formulario_pontuacao,
                    },
                    {
                        'tipo': TipoDocumento.objects.get(id=5),
                        'tipo_conferencia': TipoConferencia.objects.first(),
                        'assunto': 'Relatório descritivo',
                        'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
                        'arquivo': arq_memorial_descritivo,
                    },
                    {
                        'tipo': TipoDocumento.objects.get(id=5),
                        'tipo_conferencia': TipoConferencia.objects.first(),
                        'assunto': 'Listagem de documentos comprobatórios',
                        'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
                        'arquivo': arq,
                    },
                ]

                ProcessoEletronico.adicionar_documentos_processo(
                    processo=processo.processo_eletronico,
                    user=request.user,
                    papel=request.user.get_relacionamento().papeis_ativos.first(),
                    documentos_texto=[],
                    documentos_digitalizados=documentos_digitalizados,
                )
        else:
            if not processo.protocolo:
                # Cria protocolo
                protocolo = Processo()
                protocolo.assunto = 'Requerimento RSC'
                protocolo.set_interessado(processo.servidor)
                protocolo.tipo = Processo.TIPO_REQUERIMENTO
                protocolo.save()

                tramite = Tramite()
                tramite.processo = protocolo
                tramite.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
                tramite.orgao_interno_encaminhamento = get_setor()
                tramite.orgao_interno_recebimento = get_setor_cppd()
                tramite.pessoa_encaminhamento = request.user.get_profile()
                tramite.data_encaminhamento = datetime.datetime.now()
                tramite.ordem = 1
                tramite.save()

                processo.protocolo = protocolo

        processo.finalizar_processo()

        if processo.status == ProcessoRSC.STATUS_ANALISADO:
            return httprr('/admin/rsc/processorsc/?tab=tab_processos_analisados_aposentados', 'Processo incluído como analisado.')

        else:
            return httprr('/admin/rsc/processorsc/?tab=tab_processos_finalizados', 'Processo finalizado com sucesso.')
    except Exception as e:
        return httprr('/admin/rsc/processorsc/', f'Erro ao finalizar processo: {e}', 'error')


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def deferir_processo_aposentado(request, processo_id):
    try:
        soh_cppd(request)
        processo = get_object_or_404(ProcessoRSC, pk=processo_id)
        processo.deferir_processo_aposentado()

        return httprr('/admin/rsc/processorsc/?tab=tab_processos_finalizados_aposentados', 'Processo deferido com sucesso.')
    except Exception as e:
        return httprr('/admin/rsc/processorsc/', f'Erro ao deferir processo: {e.args[0]}', 'error')


@rtr()
@login_required()
def ciencia_resultado(request, processo_id):
    try:
        processo = get_object_or_404(ProcessoRSC, pk=processo_id)
        soh_presidentecppd_e_dono(request, processo)

        opcao_ciencia_deferimento = request.POST.get('ciencia_deferimento')
        opcao_ciencia_data_retroatividade = request.POST.get('ciencia_data_retroatividade')
        if opcao_ciencia_deferimento and opcao_ciencia_data_retroatividade:
            processo.dar_ciencia_resultado(opcao_ciencia_deferimento, opcao_ciencia_data_retroatividade)
        else:
            raise Exception('Preencha corretamente as opções de ciência da avaliação.')

        return JsonResponse({'ok': True, 'msg': 'Ciência registrada com sucesso.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
@login_required()
def desistir_avaliacao(request, avaliacao_id):
    if not eh_avaliador_da_avaliacao(request, avaliacao_id):
        if is_ajax(request):
            return Exception('Você não é avaliador desta avaliação.')
        else:
            raise PermissionDenied('Você não é avaliador desta avaliação.')

    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    title = 'Justificar Desistência'
    form = JustificativaDesistenciaForm(request.POST or None, avaliacao=avaliacao)
    if request.method == 'POST' and is_ajax(request):
        try:
            if not request.POST.get('justificativa'):
                raise Exception('O campo justificativa é de preenchimento obrigatório.')

            avaliacao.desistir_avaliacao(request.POST)
            return JsonResponse({'ok': True, 'msg': 'Desistência registrada com sucesso.'})
        except Exception as e:
            return JsonResponse({'ok': False, 'msg': e.args[0]})

    return locals()


@rtr()
@login_required()
def recusar_avaliacao(request, processo_avaliacao_id):
    processo_avaliacao = get_object_or_404(ProcessoAvaliador, pk=processo_avaliacao_id)

    if not eh_avaliador_do_processo(request, processo_avaliacao.processo_id):
        raise PermissionDenied('Você não é avaliador deste processo.')

    title = 'Motivo da Recusa'
    form = RecusaAvaliacaoForm(request.POST or None, processo_avaliador=processo_avaliacao)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Processo recusado com sucesso.')
    return locals()


@rtr()
@login_required()
def termo_aceite(request, processo_avaliacao_id):
    processo_avaliacao = get_object_or_404(ProcessoAvaliador, pk=processo_avaliacao_id)
    title = 'Termo de Confidencialidade e Sigilo'

    return locals()


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def processos_sem_avaliador_reserva(request):
    title = 'Processos Sem Avaliador Reserva'

    soh_cppd(request)

    qs_processos = ProcessoRSC.objects.filter(status__in=[ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO]).order_by(
        'servidor__pessoa_fisica__nome'
    )
    processos = []
    for proc in qs_processos:
        if (proc.qtd_avaliadores_internos_reserva() <= 0 and proc.qtd_avaliadores_internos_ativos() <= 0) or (
            proc.qtd_avaliadores_externos_reserva() <= 0 and proc.qtd_avaliadores_externos_ativos() < 2
        ):
            processos.append(proc)

    return locals()


def create_on_upload(request, processo, diretorio, nome_do_arquivo, criterio, tamanho_arquivo):
    soh_dono(request, processo)
    novo_arquivo = Arquivo()
    novo_arquivo.nome = nome_do_arquivo
    novo_arquivo.diretorio = diretorio
    novo_arquivo.criterio = criterio
    novo_arquivo.processo = processo
    novo_arquivo.tamanho = tamanho_arquivo
    novo_arquivo.save()
    return novo_arquivo


def create_on_upload_documentos_exigidos(request, processo, diretorio, nome_do_arquivo, tamanho_arquivo, tipo):
    soh_dono(request, processo)
    # Tem que refatorar para não deixar salvar vários arquivos de um mesmo tipo para o mesmo processo. o arquivo deve ser sempre atualizado
    novo_arquivo = ArquivosExigidos()
    novo_arquivo.nome = nome_do_arquivo
    novo_arquivo.diretorio = diretorio
    novo_arquivo.processo = processo
    novo_arquivo.tamanho = tamanho_arquivo

    if tipo == 'TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO':
        novo_arquivo.tipo = ArquivosExigidos.TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO
    elif tipo == 'INICIO_EXERCIO_CARREIRA':
        novo_arquivo.tipo = ArquivosExigidos.INICIO_EXERCIO_CARREIRA
    else:
        novo_arquivo.tipo = ArquivosExigidos.CONCESSAO_ULTIMA_RT

    novo_arquivo.save()

    return novo_arquivo


def get_upload_directory(instance):
    object_id = instance.id
    path = f'{PRIVATE_ROOT_DIR}/{object_id}'
    return path


class FileUploader:
    def __init__(self, backend=None, **kwargs):
        if is_remote_storage():
            self.get_backend = lambda: AWSUploadBackend(**kwargs)
        else:
            self.get_backend = lambda: LocalUploadBackend(**kwargs)

    def __call__(self, request, *args, **kwargs):
        return self._upload(request, *args, **kwargs)

    def _upload(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.method == 'POST':
            if 'processo' in request.GET:
                processo_id = request.GET['processo']
                processo = get_object_or_404(ProcessoRSC, pk=processo_id)
            else:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            if not pode_anexar(request, processo):
                raise PermissionDenied

            if 'criterio' in request.GET:
                criterio_id = request.GET['criterio']
                criterio = get_object_or_404(Criterio, pk=criterio_id)
            else:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')

            content_type = str(request.META.get('CONTENT_TYPE', ''))
            content_length = int(request.META.get('CONTENT_LENGTH', 0))
            if content_type == '' or content_length == 0:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            resolvido = upload_em_pdf(request)
            if resolvido is None:
                return HttpResponse(json.dumps({'success': False}), content_type='application/json')
            upload, is_raw, filename = resolvido

            # Here, we have the filename and file size
            backend = self.get_backend()

            # creating the destination upload directory
            upload_to = get_upload_directory(processo.servidor)
            # configuring the
            new_filename = backend.setup(upload_to, filename)
            # save the file
            success = backend.upload(upload, content_length, is_raw, *args, **kwargs)
            # callback
            uploaded_path = backend.upload_complete(*args, **kwargs) if success else None

            if success:
                arquivo = create_on_upload(request, processo, uploaded_path, filename, criterio, content_length)
                ret_json = {
                    'success': success,
                    'filename': new_filename,
                    'arquivo_pk': arquivo.id,
                    'arquivo_pk_crypto': arquivo.encrypted_pk,
                    'tamanho': content_length,
                    'field_qtd': ProcessoRSCForm.factory_field_render_qtd_itens(arquivo),
                    'field_data': ProcessoRSCForm.factory_field_render_data_referencia(arquivo),
                    'field_nota': ProcessoRSCForm.factory_field_render_nota_pretendida(arquivo),
                    'field_descricao': ProcessoRSCForm.factory_field_render_descricao(arquivo),
                }
            else:
                ret_json = {
                    'success': success,
                    'filename': new_filename,
                    'arquivo_pk': '',
                    'arquivo_pk_crypto': '',
                    'tamanho': content_length,
                    'field_qtd': '',
                    'field_data': '',
                    'field_nota': '',
                    'field_descricao': '',
                }

            return HttpResponse(json.dumps(ret_json, cls=DjangoJSONEncoder), content_type='text/html; charset=utf-8')
        else:
            response = HttpResponseNotAllowed(['POST'])
            response.write('ERROR: Only POST allowed')
            return response


class FileUploaderDocumentosExigidos:
    def __init__(self, backend=None, **kwargs):
        if is_remote_storage():
            self.get_backend = lambda: AWSUploadBackend(**kwargs)
        else:
            self.get_backend = lambda: LocalUploadBackend(**kwargs)

    def __call__(self, request, *args, **kwargs):
        return self._upload(request, *args, **kwargs)

    def _upload(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.method == 'POST':
            if 'processo' in request.GET:
                processo_id = request.GET['processo']
                processo = get_object_or_404(ProcessoRSC, pk=processo_id)
            else:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            if not pode_anexar(request, processo):
                raise PermissionDenied

            if 'tipo' in request.GET:
                tipo = request.GET['tipo']
            else:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')

            content_type = str(request.META.get('CONTENT_TYPE', ''))
            content_length = int(request.META.get('CONTENT_LENGTH', 0))
            if content_type == '' or content_length == 0:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            resolvido = upload_em_pdf(request)
            if resolvido is None:
                return HttpResponse(json.dumps({'success': False}), content_type='application/json')
            upload, is_raw, filename = resolvido

            # Here, we have the filename and file size
            backend = self.get_backend()

            # creating the destination upload directory
            upload_to = get_upload_directory(processo.servidor)
            # configuring the
            new_filename = backend.setup(upload_to, filename)
            # save the file
            success = backend.upload(upload, content_length, is_raw, *args, **kwargs)
            # callback
            uploaded_path = backend.upload_complete(*args, **kwargs) if success else None

            if success:
                arquivo = create_on_upload_documentos_exigidos(request, processo, uploaded_path, filename, content_length, tipo)
                ret_json = {
                    'success': success,
                    'filename': new_filename,
                    'arquivo_pk': arquivo.id,
                    'arquivo_pk_crypto': arquivo.encrypted_pk,
                    'tamanho': content_length,
                }
            else:
                ret_json = {
                    'success': success,
                    'filename': new_filename,
                    'arquivo_pk': '',
                    'arquivo_pk_crypto': '',
                    'tamanho': content_length,
                }

            return HttpResponse(json.dumps(ret_json, cls=DjangoJSONEncoder), content_type='text/html; charset=utf-8')
        else:
            response = HttpResponseNotAllowed(['POST'])
            response.write('ERROR: Only POST allowed')
            return response


file_uploaded = Signal()  # providing_args=['backend', 'request']
rsc_upload = login_required()(FileUploader())
rsc_upload_documentos_exigidos = login_required()(FileUploaderDocumentosExigidos())


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def requerimento_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    if processo.status == ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def formulario_pontuacao_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    if processo.status == ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    arquivos_rsc1 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-I').select_related('criterio', 'criterio__diretriz')
    arquivos_rsc2 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-II').select_related('criterio', 'criterio__diretriz')
    arquivos_rsc3 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-III').select_related('criterio', 'criterio__diretriz')

    return locals()


@rtr()
@login_required()
def quadro_resumo_pontuacao_requerida(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    arquivos_rsc1 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-I').select_related('criterio', 'criterio__diretriz')
    arquivos_rsc2 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-II').select_related('criterio', 'criterio__diretriz')
    arquivos_rsc3 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-III').select_related('criterio', 'criterio__diretriz')
    return locals()


@rtr()
@login_required()
def quadro_resumo_avaliacao(request, avaliacao_id):
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    resumo = _resumo_avaliacoes(avaliacao)
    avaliacoes = resumo['avaliacoes']
    ponto_global_diretriz = resumo['ponto_global_diretriz']
    ponto_teto_diretriz = resumo['ponto_teto_diretriz']

    return locals()


def _resumo_avaliacoes(avaliacao):
    itens_rsc1 = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-I')
        .order_by('arquivo__criterio__diretriz__tipo_rsc', 'arquivo__criterio__numero')
        .distinct()
    )
    soma_pontuacao_validada_rsc1 = 0
    ponto_global_diretriz = {}
    ponto_teto_diretriz = {}
    tmp_dict_teto = {}
    for item in itens_rsc1:
        if item.pontuacao_validada():
            if item.arquivo.criterio.diretriz_id in ponto_global_diretriz:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()

            if item.arquivo.criterio.diretriz_id in tmp_dict_teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()
            if tmp_dict_teto[item.arquivo.criterio.diretriz_id] > item.arquivo.criterio.diretriz.teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = Decimal(f'{round(item.arquivo.criterio.diretriz.teto, 2):.2f}')

            soma_pontuacao_validada_rsc1 += item.pontuacao_validada()

    ponto_teto_diretriz = tmp_dict_teto
    soma_pontuacao_teto_rsc1 = sum(tmp_dict_teto.values())

    itens_rsc2 = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-II')
        .order_by('arquivo__criterio__diretriz__tipo_rsc', 'arquivo__criterio__numero')
        .distinct()
    )
    soma_pontuacao_validada_rsc2 = 0
    tmp_dict_teto = {}
    for item in itens_rsc2:
        if item.pontuacao_validada():
            if item.arquivo.criterio.diretriz_id in ponto_global_diretriz:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()

            if item.arquivo.criterio.diretriz_id in tmp_dict_teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()
            if tmp_dict_teto[item.arquivo.criterio.diretriz_id] > item.arquivo.criterio.diretriz.teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = Decimal(f'{round(item.arquivo.criterio.diretriz.teto, 2):.2f}')

            soma_pontuacao_validada_rsc2 += item.pontuacao_validada()

    soma_pontuacao_teto_rsc2 = sum(tmp_dict_teto.values())
    ponto_teto_diretriz.update(tmp_dict_teto)

    itens_rsc3 = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__diretriz__tipo_rsc__nome='RSC-III')
        .order_by('arquivo__criterio__diretriz__tipo_rsc', 'arquivo__criterio__numero')
        .distinct()
    )
    soma_pontuacao_validada_rsc3 = 0
    tmp_dict_teto = {}
    for item in itens_rsc3:
        if item.pontuacao_validada():
            if item.arquivo.criterio.diretriz_id in ponto_global_diretriz:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                ponto_global_diretriz[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()

            if item.arquivo.criterio.diretriz_id in tmp_dict_teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
            else:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()
            if tmp_dict_teto[item.arquivo.criterio.diretriz_id] > item.arquivo.criterio.diretriz.teto:
                tmp_dict_teto[item.arquivo.criterio.diretriz_id] = Decimal(f'{round(item.arquivo.criterio.diretriz.teto, 2):.2f}')

            soma_pontuacao_validada_rsc3 += item.pontuacao_validada()

    soma_pontuacao_teto_rsc3 = sum(tmp_dict_teto.values())
    ponto_teto_diretriz.update(tmp_dict_teto)

    avaliacao.itens = list(chain(itens_rsc1, itens_rsc2, itens_rsc3))
    avaliacao.subtotal_rsc1 = soma_pontuacao_validada_rsc1
    avaliacao.subtotal_teto_rsc1 = soma_pontuacao_teto_rsc1
    avaliacao.subtotal_rsc2 = soma_pontuacao_validada_rsc2
    avaliacao.subtotal_teto_rsc2 = soma_pontuacao_teto_rsc2
    avaliacao.subtotal_rsc3 = soma_pontuacao_validada_rsc3
    avaliacao.subtotal_teto_rsc3 = soma_pontuacao_teto_rsc3
    avaliacoes = [avaliacao]

    return {'avaliacoes': avaliacoes, 'ponto_global_diretriz': ponto_global_diretriz, 'ponto_teto_diretriz': ponto_teto_diretriz}


@rtr()
@login_required()
def documentos_preliminares(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    eh_dono_processo = eh_dono(request, processo)
    soh_cppd_dono_avaliador(request, processo)

    data_conclusao_titulacao_rsc_form = DataConclusaoTitulacaoRSCForm(request=request, processo=processo)
    data_exercicio_carreira_form = DataExercicioCarreiraForm(request=request, processo=processo)
    documentos_exigidos_form = DocumentosExigidosForm(request=request, processo=processo)

    processo_form = ProcessoRSCForm(
        data={
            'introducao_relatorio_descritivo': processo.introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_ultima_rt': processo.data_concessao_ultima_rt,
            'data_exercio_carreira': processo.data_exercio_carreira,
            'data_conclusao_titulacao_rsc_pretendido': processo.data_conclusao_titulacao_rsc_pretendido,
        },
        processo=processo,
    )

    arquivos_documentos_exigidos = ArquivosExigidos.objects.filter(processo=processo)
    for arquivo in arquivos_documentos_exigidos:
        if arquivo.tipo == ArquivosExigidos.TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO:
            processo_form.arquivo_conclusao_titulacao_rsc_pretendido = arquivo
        elif arquivo.tipo == ArquivosExigidos.INICIO_EXERCIO_CARREIRA:
            processo_form.arquivo_exercio_carreira = arquivo
        elif arquivo.tipo == ArquivosExigidos.CONCESSAO_ULTIMA_RT:
            processo_form.arquivo_concessao_ultima_rt = arquivo

    return locals()


@rtr()
@login_required()
def relatorio_descritivo(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_avaliador(request, processo)

    arquivos = processo.arquivo_set.exclude(descricao='').order_by('data_referencia').distinct()
    arquivos_producoes_academicas = arquivos.filter(criterio__categoria_memorial_descritivo__pk=1)
    arquivos_descricoes_atividades_administracao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=2)
    arquivos_prestacoes_de_servicos = arquivos.filter(criterio__categoria_memorial_descritivo__pk=3)
    arquivos_titulos_e_homenagens = arquivos.filter(criterio__categoria_memorial_descritivo__pk=4)
    arquivos_atauacao_docente = arquivos.filter(criterio__categoria_memorial_descritivo__pk=5)
    arquivos_itinerario_de_formacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=6)

    introducao_relatorio_descritivo = processo.introducao_relatorio_descritivo
    conclusao_relatorio_descritivo = processo.conclusao_relatorio_descritivo

    processo_form = ProcessoRSCForm(
        data={
            'introducao_relatorio_descritivo': introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_ultima_rt': processo.data_concessao_ultima_rt,
            'data_exercio_carreira': processo.data_exercio_carreira,
            'data_conclusao_titulacao_rsc_pretendido': processo.data_conclusao_titulacao_rsc_pretendido,
        }
    )

    return locals()


@documento(enumerar_paginas=True)
@rtr()
@login_required()
def relatorio_descritivo_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    if processo.status == ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    uo = get_uo(request.user)

    arquivos = processo.arquivo_set.exclude(descricao='').order_by('data_referencia').distinct()

    arquivos_producoes_academicas = arquivos.filter(criterio__categoria_memorial_descritivo__pk=1)
    arquivos_descricoes_atividades_administracao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=2)
    arquivos_prestacoes_de_servicos = arquivos.filter(criterio__categoria_memorial_descritivo__pk=3)
    arquivos_titulos_e_homenagens = arquivos.filter(criterio__categoria_memorial_descritivo__pk=4)
    arquivos_atauacao_docente = arquivos.filter(criterio__categoria_memorial_descritivo__pk=5)
    arquivos_itinerario_de_formacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=6)

    hoje = datetime.date.today()

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def documentos_anexados_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    if processo.status == ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    arquivos_rsc1 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-I')
    arquivos_rsc2 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-II')
    arquivos_rsc3 = processo.arquivo_set.filter(criterio__diretriz__tipo_rsc__nome='RSC-III')
    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def imprimir_documentos_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    ultima_validacao = processo.ultima_validacao_processo()

    if processo.servidor.setor_exercicio and processo.servidor.setor_exercicio.uo:
        campus = None
        if processo.estado_atual_processo() == 1:
            campus = 'COGPE'
        setor_encaminhamento = '{}/{}'.format(campus or 'DG', processo.servidor.setor_exercicio.uo.sigla)
        if processo.servidor.setor_exercicio.uo.sigla == get_sigla_reitoria():
            setor_encaminhamento = '{}/{}'.format(campus or 'GABIN', processo.servidor.setor_exercicio.uo.sigla)
    else:
        setor_encaminhamento = '{}/{}'.format('COGPE', 'RE')

    TITULACAO_REFERENTE_CHOICES = {'RSC-I': 'Especialiação', 'RSC-II': 'Mestrado', 'RSC-III': 'Doutorado'}
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

    hoje = datetime.date.today()
    data_extenso = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")} ({Configuracao.get_valor_por_chave("comum", "instituicao_estado")}), {hoje.day} de {meses.get(hoje.month)} de {hoje.year}.'

    """
    DEFERIMENTO OU INDEFERIMENTO
    """
    estado_atual_processo = 'Indeferido'
    status_processo_despacho = 'INDEFERIMENTO'
    texto_encaminhamento_despacho_cppd = 'para arquivamento.'
    texto_encaminhamento_despacho_reitor = 'para arquivamento.'

    if processo.estado_atual_processo() == 0:
        estado_atual_processo = 'Deferido'
        status_processo_despacho = 'DEFERIMENTO'
        texto_encaminhamento_despacho_cppd = 'para emissão de portaria de retribuição de titulação e demais encaminhamentos.'
        texto_encaminhamento_despacho_reitor = 'para emissão de Portaria e demais encaminhamentos.'

    # data de retroatividade do processo VALIDADA
    data_retroatividade = processo.get_data_referencia_final()
    # data de referência apenas dos arquivos VALIDADOS
    data_referencia_arquivos = processo.get_data_referencia_retroativa(True, True)
    # data de referência apenas dos arquivos VALIDADOS
    data_consolidada_documentos = processo.get_data_referencia_retroativa(True, True)

    data_exercio_carreira = processo.data_exercio_carreira
    if ultima_validacao and ultima_validacao.data_exercio_carreira_validada != data_exercio_carreira:
        data_exercio_carreira = '{} <br />(Validada pela CPPD: {})'.format(
            data_exercio_carreira.strftime('%Y-%m-%d'),
            ultima_validacao.data_exercio_carreira_validada.strftime('%Y-%m-%d'),
        )

    data_conclusao_titulacao_rsc_pretendido = processo.data_conclusao_titulacao_rsc_pretendido
    if ultima_validacao and ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada != data_conclusao_titulacao_rsc_pretendido:
        data_conclusao_titulacao_rsc_pretendido = '{} <br />(Validada pela CPPD: {})'.format(
            data_conclusao_titulacao_rsc_pretendido.strftime('%Y-%m-%d'),
            ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada.strftime('%Y-%m-%d'),
        )

    data_concessao_ultima_rt = processo.data_concessao_ultima_rt
    if (
        ultima_validacao
        and ultima_validacao.data_concessao_ultima_rt_validada
        and ultima_validacao.data_concessao_ultima_rt_validada != data_concessao_ultima_rt
    ):
        data_concessao_ultima_rt = '{} <br />(Validada pela CPPD: {})'.format(
            data_concessao_ultima_rt.strftime('%Y-%m-%d'),
            ultima_validacao.data_concessao_ultima_rt_validada.strftime('%Y-%m-%d'),
        )

    avaliacoes = Avaliacao.objects.filter(processo=processo, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).order_by(
        'avaliador__vinculo__pessoa__nome'
    )
    titulacao_referente = TITULACAO_REFERENTE_CHOICES[processo.tipo_rsc.nome]

    # texto do despacho que vai para o reitor
    texto_final_despacho_reitor = f'Com base nos pareceres emitidos pelos avaliadores e nas datas de referência supra citadas, o processo para <strong>{processo.tipo_rsc.nome}</strong> '
    texto_final_despacho_reitor += (
        f'foi <strong>{estado_atual_processo.upper()}</strong>, com respaldo no parágrafo único do art. 11 da Resolução nº 15/2014-CONSUP/IFRN'
    )
    if processo.estado_atual_processo() == 0:  # se o processo for deferido
        texto_final_despacho_reitor += (
            ', com efeitos a partir de <strong>{}</strong>, para concessão de Retribuição por Titulação referente a <strong>{}</strong>'.format(
                data_retroatividade.strftime('%Y-%m-%d'),
                titulacao_referente.upper(),
            )
        )
    texto_final_despacho_reitor += '.'

    # texto do despacho de homologação do reitor
    texto_despacho_homologacao = f'HOMOLOGO o presente resultado final de <strong>{status_processo_despacho}</strong> de Reconhecimento de Saberes e Competências, constante do presente processo'
    if processo.estado_atual_processo() == 0:  # se o processo for deferido
        texto_despacho_homologacao += (
            ', para concessão de Retribuição por Titulação referente a <strong>{}</strong>, com efeitos a partir de <strong>{}</strong>'.format(
                titulacao_referente.upper(),
                data_retroatividade.strftime('%Y-%m-%d'),
            )
        )
    texto_despacho_homologacao += '.'

    # selecionando avaliadores e dados do resumo da avaliação
    avaliadores_resumo = []
    processo_avaliadores = ProcessoAvaliador.objects.filter(processo=processo, status=ProcessoAvaliador.AVALIACAO_FINALIZADA).order_by(
        'avaliador__vinculo__pessoa__nome'
    )
    for processo_avaliador in processo_avaliadores:
        avaliacao = Avaliacao.objects.filter(processo=processo_avaliador.processo, avaliador=processo_avaliador.avaliador)

        avaliacao_status = None
        if avaliacao.exists():
            avaliacao = avaliacao[0]
            avaliacao_status = avaliacao.get_status_display()

            resumo = _resumo_avaliacoes(avaliacao)
            avaliacao_quadro_resumo = resumo['avaliacoes']
            ponto_global_diretriz = resumo['ponto_global_diretriz']
            ponto_teto_diretriz = resumo['ponto_teto_diretriz']

        data_referencia_validada = None
        if avaliacao.status == Avaliacao.DEFERIDA:
            data_referencia_validada = processo.get_data_referencia_retroativa(True, False, processo_avaliador.avaliador)

        pontuacao_validada = processo._calculo_pontos(
            [Avaliacao.EM_AVALIACAO, Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], True, processo_avaliador.avaliador
        )

        if processo_avaliador.avaliador_principal():
            avaliador = processo_avaliador.avaliador
            avaliador.nome = processo_avaliador.avaliador.vinculo.relacionamento.pessoa_fisica.nome
            if avaliador.eh_interno():
                avaliador.matricula = processo_avaliador.avaliador.vinculo.relacionamento.matricula
            else:
                avaliador.matricula = processo_avaliador.avaliador.matricula_siape
            avaliador.pontuacao_validada = pontuacao_validada
            avaliador.data_referencia_validada = data_referencia_validada
            avaliador.data_referencia_arquivos = data_referencia_arquivos
            avaliador.avaliacao_status = avaliacao_status

            avaliador.avaliacao_quadro_resumo = avaliacao_quadro_resumo
            avaliador.ponto_global_diretriz = ponto_global_diretriz
            avaliador.ponto_teto_diretriz = ponto_teto_diretriz

            avaliadores_resumo.append(avaliador)

    return locals()


@rtr()
@login_required()
def processos_pagamento_avaliador_interno(request):
    title = 'Processos para Pagamento de Avaliadores Internos'
    form = ProcessoPagamentoForm(request.GET or None)

    qs_parametro = ParametroPagamento.objects.all()

    if qs_parametro.exists():
        parametro = qs_parametro[0]
        qs_avaliacoes = Avaliacao.objects.filter(
            avaliador__in=Avaliador.internos.all(),
            status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
            processo__status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO],
        )

        if form.is_valid():
            avaliador = form.cleaned_data['avaliador']
            interessado = form.cleaned_data['interessado']
            avaliadores_pagamento_avaliacao = form.cleaned_data['avaliadores_pagamento_avaliacao']

            if avaliador:
                qs_avaliacoes = qs_avaliacoes.filter(avaliador__vinculo__pessoa__nome__icontains=avaliador)
            if interessado:
                qs_avaliacoes = qs_avaliacoes.filter(processo__servidor__pessoafisica_ptr__nome__unaccent__icontains=interessado)
            if avaliadores_pagamento_avaliacao:
                if avaliadores_pagamento_avaliacao == ProcessoPagamentoForm.AVALIACOES_PAGAS:
                    qs_avaliacoes = qs_avaliacoes.filter(avaliacao_paga=True)
                elif avaliadores_pagamento_avaliacao == ProcessoPagamentoForm.AVALIACOES_NAO_PAGAS:
                    qs_avaliacoes = qs_avaliacoes.filter(avaliacao_paga=False)

        qs_avaliacoes = qs_avaliacoes.order_by('avaliador__vinculo__pessoa__nome').distinct('avaliador__vinculo__pessoa__nome')

        avaliacoes = []
        for avaliacao in qs_avaliacoes:
            obj_avaliacao = avaliacao
            obj_avaliacao.qtd_avaliacoes_pagas = avaliacao.avaliador.qtd_avaliacoes_pagas(avaliacao)
            obj_avaliacao.qtd_avaliacoes_nao_pagas = avaliacao.avaliador.qtd_avaliacoes_nao_pagas(avaliacao)

            obj_avaliacao.valor_pago = obj_avaliacao.qtd_avaliacoes_pagas * parametro.valor_por_avaliacao
            obj_avaliacao.valor_a_pagar = obj_avaliacao.qtd_avaliacoes_nao_pagas * parametro.valor_por_avaliacao
            obj_avaliacao.total_horas = (obj_avaliacao.qtd_avaliacoes_pagas + obj_avaliacao.qtd_avaliacoes_nao_pagas) * parametro.hora_por_avaliacao
            avaliacoes.append(obj_avaliacao)

    return locals()


@rtr()
@login_required()
def processos_pagamento_avaliador_externo(request):
    title = 'Processos para Pagamento de Avaliadores Externos'
    form = ProcessoPagamentoForm(request.GET or None)

    qs_parametro = ParametroPagamento.objects.all()

    if qs_parametro.exists():
        parametro = qs_parametro[0]
        qs_avaliacoes = Avaliacao.objects.filter(
            avaliador__in=Avaliador.externos.all(),
            status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
            processo__status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO],
        )

        if form.is_valid():
            avaliador = form.cleaned_data['avaliador']
            interessado = form.cleaned_data['interessado']
            avaliadores_pagamento_avaliacao = form.cleaned_data['avaliadores_pagamento_avaliacao']

            if avaliador:
                qs_avaliacoes = qs_avaliacoes.filter(avaliador__vinculo__pessoa__nome__icontains=avaliador)
            if interessado:
                qs_avaliacoes = qs_avaliacoes.filter(processo__servidor__pessoafisica_ptr__nome__unaccent__icontains=interessado)
            if avaliadores_pagamento_avaliacao:
                if avaliadores_pagamento_avaliacao == ProcessoPagamentoForm.AVALIACOES_PAGAS:
                    qs_avaliacoes = qs_avaliacoes.filter(avaliacao_paga=True)
                elif avaliadores_pagamento_avaliacao == ProcessoPagamentoForm.AVALIACOES_NAO_PAGAS:
                    qs_avaliacoes = qs_avaliacoes.filter(avaliacao_paga=False)

        qs_avaliacoes = qs_avaliacoes.order_by('avaliador__vinculo__pessoa__nome').distinct('avaliador__vinculo__pessoa__nome')

        avaliacoes = []
        inss = 0.11
        iss = 0.05
        for avaliacao in qs_avaliacoes:
            obj_avaliacao = avaliacao

            obj_avaliacao.qtd_avaliacoes_pagas = avaliacao.avaliador.qtd_avaliacoes_pagas(avaliacao)
            obj_avaliacao.qtd_avaliacoes_nao_pagas = avaliacao.avaliador.qtd_avaliacoes_nao_pagas(avaliacao)

            # valores pagos
            obj_avaliacao.valor_bruto_pago = obj_avaliacao.qtd_avaliacoes_pagas * parametro.valor_por_avaliacao
            obj_avaliacao.desconto_inss_pago = obj_avaliacao.valor_bruto_pago * inss
            obj_avaliacao.desconto_iss_pago = obj_avaliacao.valor_bruto_pago * iss
            obj_avaliacao.valor_liquido_pago = obj_avaliacao.valor_bruto_pago - (obj_avaliacao.desconto_inss_pago + obj_avaliacao.desconto_iss_pago)

            # valores a pagar
            obj_avaliacao.valor_bruto_a_pagar = obj_avaliacao.qtd_avaliacoes_nao_pagas * parametro.valor_por_avaliacao
            obj_avaliacao.desconto_inss_a_pagar = obj_avaliacao.valor_bruto_a_pagar * inss
            obj_avaliacao.desconto_iss_a_pagar = obj_avaliacao.valor_bruto_a_pagar * iss
            obj_avaliacao.valor_liquido_a_pagar = obj_avaliacao.valor_bruto_a_pagar - (
                obj_avaliacao.desconto_inss_a_pagar + obj_avaliacao.desconto_iss_a_pagar
            )

            # total de horas
            obj_avaliacao.total_horas = (obj_avaliacao.qtd_avaliacoes_pagas + obj_avaliacao.qtd_avaliacoes_nao_pagas) * parametro.hora_por_avaliacao

            avaliacoes.append(obj_avaliacao)

    return locals()


@rtr()
@login_required()
def popup_avaliacao_pagamento_avaliador(request, avaliador_id):
    avaliador = get_object_or_404(Avaliador, pk=avaliador_id)
    title = f'Avaliações para Pagamento do Avaliador {avaliador.vinculo.user.get_profile().nome}'

    if request.POST:
        opcoes = request.POST.getlist('avaliacoes_options')
        Avaliacao.objects.filter(avaliador=avaliador).update(avaliacao_paga=False)
        Avaliacao.objects.filter(avaliador=avaliador, id__in=opcoes).update(avaliacao_paga=True)
        for id in opcoes:
            avaliacao = Avaliacao.objects.filter(id=id)
            if avaliacao.exists():
                avaliacao = avaliacao[0]
                if avaliacao.data_pagamento is None:
                    avaliacao.data_pagamento = datetime.datetime.now()
                    avaliacao.save()

        return httprr('..', 'Avaliações marcadas como paga com sucesso.')

    avaliacoes = Avaliacao.objects.filter(avaliador=avaliador, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).order_by(
        'processo__servidor__pessoa_fisica__nome'
    )

    return locals()


@rtr()
@login_required()
def download_arquivos(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    try:
        filenames = []
        dict_refer_file = {}
        # adicionando na lista os arquivos exigidos (documentos preliminares)
        for arquivo_exigido in processo.arquivosexigidos_set.all():
            related_name = arquivo_exigido.diretorio
            path_file = cache_file(related_name)
            filenames.append(path_file)

            _fdir, fname = os.path.split(path_file)
            dict_refer_file[fname] = arquivo_exigido.nome

        # adicionando na lista os arquivos utilizados para pontuar
        for arquivo in processo.arquivo_set.all():
            related_name = arquivo_exigido.diretorio
            path_file = cache_file(related_name)
            filenames.append(path_file)

            _fdir, fname = os.path.split(path_file)
            dict_refer_file[fname] = arquivo.nome

        # adicona ao nome o processo
        if processo.processo_eletronico:
            tipo_protocolo = processo.processo_eletronico.numero_protocolo_fisico
        elif processo.protocolo:
            tipo_protocolo = processo.protocolo.numero_processo
        else:
            tipo_protocolo = processo.id

        zip_subdir = f'arquivos_processo_{tipo_protocolo}'
        zip_filename = f'{zip_subdir}.zip'

        s = io.BytesIO()
        zf = zipfile.ZipFile(s, 'w')

        for fpath in filenames:
            _fdir, fname = os.path.split(fpath)
            zip_path = os.path.join(zip_subdir, fname)
            zf.write(fpath, zip_path)
        zf.close()

        resp = HttpResponse(s.getvalue())
        resp['Content-Disposition'] = f'attachment; filename={zip_filename}'
        resp['Content-Type'] = 'application/pdf'

        return resp
    except OSError as ex:
        msg = f'Ocorrreu um erro ao carregar o arquivo {dict_refer_file[fname]}'
        if ex.args[0] == 2:
            msg = f'O arquivo {dict_refer_file[fname]} não foi encontrado.'
        return httprr(request.META.get('HTTP_REFERER'), msg, 'error')


@rtr()
@login_required()
def gerar_processo_completo(request, processo_id):
    processo = get_object_or_404(ProcessoRSC, pk=processo_id)
    soh_cppd_dono_e_rh(request, processo)
    try:
        merger = PdfWriter()

        # adicionando na lista os arquivos exigidos (documentos preliminares)
        for arquivo_exigido in processo.arquivosexigidos_set.all():
            pdf = PdfReader(default_storage.open(arquivo_exigido.diretorio))
            merger.append(pdf)

        # adicionando na lista os arquivos utilizados para pontuar
        for arquivo in processo.arquivo_set.all():
            pdf = PdfReader(default_storage.open(arquivo.diretorio))
            merger.append(pdf)

        s = io.BytesIO()
        merger.write(s)

        nome_arquivo = f'processo_completo_{processo.id}.pdf'

        resp = HttpResponse(s.getvalue())
        resp['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        resp['Content-Type'] = 'application/pdf'

        return resp
    except Exception as ex:
        if settings.DEBUG:
            raise ex
        return httprr('..', ex, 'error')


@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def relatorio_pagamento(request):
    title = 'Relatório de Pagamento'

    soh_cppd(request)

    form = RelatorioPagamentoForm(request.GET or None)

    if form.is_valid():
        parametros = ParametroPagamento.objects.all()
        if parametros.exists():
            parametro = parametros[0]

            # parametros
            valor_por_avaliacao = parametro.valor_por_avaliacao
            hora_por_avaliacao = parametro.hora_por_avaliacao
            inss = 0.11
            iss = 0.05

            # verificando os filtros de data de inicio e data final
            data_inicio = form.cleaned_data.get('data_inicio')
            data_final = form.cleaned_data.get('data_final')

            # verificando se é para mostrar apenas as avaliações pagas
            avaliacoes_pagas = form.cleaned_data.get('avaliacao_paga')

            pode_reverter_pagamento = False
            if avaliacoes_pagas and request.user.is_superuser:
                pode_reverter_pagamento = True

            """
            Lista de processos
            """
            processos_ids = (
                ProcessoRSC.objects.filter(
                    status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO, ProcessoRSC.STATUS_REJEITADO],
                    avaliacao__status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
                    avaliacao__avaliacao_paga=avaliacoes_pagas,
                )
                .distinct('id')
                .values_list('id', flat=True)
            )

            processos = ProcessoRSC.objects.filter(id__in=processos_ids).order_by('servidor__pessoa_fisica__nome')

            if data_inicio and data_final:
                processos = processos.filter(data_finalizacao_processo__range=(data_inicio, data_final))

            total_processos = processos.count()

            avaliacoes = []
            processos_id = []
            total_processos_por_instituicao = {}
            for processo in processos:
                if processo.id in total_processos_por_instituicao:
                    total_processos_por_instituicao[processo.id] += 1
                else:
                    total_processos_por_instituicao[processo.id] = 1

                processos_id.append(processo.id)
                qs_avaliacoes = processo.avaliacao_set.filter(status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], avaliacao_paga=avaliacoes_pagas)
                for avaliacao in qs_avaliacoes.order_by('avaliador__vinculo__pessoa__nome'):
                    if avaliacao not in avaliacoes:
                        avaliacoes.append(avaliacao)

            avaliadores_internos = []
            avaliadores_externos = []
            total_avaliacoes_internos = 0
            total_avaliacoes_externos = 0
            total_avaliacoes_por_instituicao = {}
            for avaliacao in avaliacoes:
                avaliador = avaliacao.avaliador

                if avaliador not in avaliadores_internos and avaliador not in avaliadores_externos:
                    qs_avaliacoes_avaliador = (
                        Avaliacao.objects.filter(
                            processo__id__in=processos_id,
                            processo__status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO, ProcessoRSC.STATUS_REJEITADO],
                            status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
                            avaliacao_paga=avaliacoes_pagas,
                            avaliador=avaliador,
                        )
                        .order_by('processo__servidor__pessoa_fisica__nome')
                        .distinct('processo__servidor__pessoa_fisica__nome')
                    )

                    avaliador.avaliacoes = qs_avaliacoes_avaliador
                    avaliador.qtde_avaliacoes = avaliador.avaliacoes.count()
                    avaliador.qtde_horas = avaliador.qtde_avaliacoes * hora_por_avaliacao
                    avaliador.valor_a_pagar = avaliador.qtde_avaliacoes * valor_por_avaliacao

                    if avaliador.instituicao_origem:
                        if avaliador.instituicao_origem_id in total_avaliacoes_por_instituicao:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id] += avaliador.qtde_avaliacoes
                        else:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id] = avaliador.qtde_avaliacoes

                    if avaliador.eh_interno():
                        total_avaliacoes_internos += avaliador.qtde_avaliacoes
                        avaliadores_internos.append(avaliador)

                    if avaliador.eh_externo():
                        total_avaliacoes_externos += avaliador.qtde_avaliacoes
                        avaliador.desconto_inss_a_pagar = avaliador.valor_a_pagar * inss
                        avaliador.desconto_iss_a_pagar = avaliador.valor_a_pagar * iss
                        avaliador.valor_liquido_a_pagar = avaliador.valor_a_pagar - (avaliador.desconto_inss_a_pagar + avaliador.desconto_iss_a_pagar)
                        avaliadores_externos.append(avaliador)

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
@permission_required('rsc.pode_validar_processorsc')
def relatorio_pagamento_pdf(request):
    avaliacoes_id = request.POST.getlist('avaliacoes')
    relatorio = request.GET.get('relatorio')

    soh_cppd(request)

    avaliacoes = Avaliacao.objects.filter(
        id__in=avaliacoes_id,
        processo__status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO, ProcessoRSC.STATUS_REJEITADO],
        status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
    )

    # marca as avaliações como pagas
    if request.GET.get('pagar'):
        avaliacoes.update(avaliacao_paga=True)
        return httprr(request.META.get('HTTP_REFERER'), 'Avaliações marcadas como pagas com sucesso.')

    # ação que reverte pagamento (apenas superusers)
    if request.user.is_superuser and request.GET.get('reverter_pagamento'):
        avaliacoes.update(avaliacao_paga=False)
        return httprr(request.META.get('HTTP_REFERER'), 'Reversão de pagamento realizado com sucesso.')

    parametros = ParametroPagamento.objects.all()
    if parametros.exists():
        parametro = parametros[0]

        # parametros
        valor_por_avaliacao = parametro.valor_por_avaliacao
        hora_por_avaliacao = parametro.hora_por_avaliacao
        inss = 0.11
        iss = 0.05

        # verificando a querystring para pegar os filtros aplicados na consulta
        try:
            querystring = request.META.get('HTTP_REFERER').split('?')[1]
            campos_filtro = querystring.split('&')
            avaliacao_paga = False
            for campo in campos_filtro:
                if 'data_inicio' in campo:
                    data_inicio = campo.split('=')[1]
                if 'data_final' in campo:
                    data_final = campo.split('=')[1]
                if 'avaliacao_paga' in campo:
                    avaliacao_paga = campo.split('=')[1]
        except Exception:
            return httprr('/rsc/relatorio_pagamento/', 'Erro ao tentar gerar o relatório de pagamento. Preencha alguns filtros.', 'error')

        if avaliacao_paga == 'on':
            avaliacao_paga = True
        else:
            avaliacao_paga = False

        processos = []
        processos_id = []
        for avaliacao in avaliacoes.order_by('processo__servidor__pessoa_fisica__nome'):
            if avaliacao.processo not in processos and relatorio == 'processo':
                processos.append(avaliacao.processo)
            if avaliacao.processo_id not in processos_id:
                processos_id.append(avaliacao.processo_id)

        total_processos = len(processos_id)

        if relatorio != 'processo':
            avaliadores_internos = []
            avaliadores_externos = []

            if relatorio == 'externo_instituicao_origem':
                avaliacoes = avaliacoes.order_by('avaliador__instituicao_origem__nome', 'avaliador__vinculo__pessoa__nome')
            elif relatorio == 'externo' or relatorio == 'interno':
                avaliacoes = avaliacoes.order_by('avaliador__vinculo__pessoa__nome')

            total_avaliacoes_internos = 0
            valor_total_internos = 0
            total_avaliacoes_externos = 0
            valor_total_externos = 0
            total_avaliacoes_por_instituicao = {}
            for avaliacao in avaliacoes:
                avaliador = avaliacao.avaliador

                if avaliador in avaliadores_internos or avaliador in avaliadores_externos:
                    continue

                qs_avaliacoes_avaliador = Avaliacao.objects.filter(
                    processo__id__in=processos_id,
                    status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA],
                    processo__status__in=[ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO, ProcessoRSC.STATUS_REJEITADO],
                    avaliacao_paga=avaliacao_paga,
                    avaliador=avaliador,
                ).order_by('processo__servidor__pessoa_fisica__nome')
                avaliador.avaliacoes = list(qs_avaliacoes_avaliador)
                avaliador.qtde_avaliacoes = len(avaliador.avaliacoes)
                avaliador.qtde_horas = avaliador.qtde_avaliacoes * hora_por_avaliacao
                avaliador.valor_a_pagar = avaliador.qtde_avaliacoes * valor_por_avaliacao

                if avaliacao.avaliador.eh_interno() and relatorio == 'interno':
                    total_avaliacoes_internos += avaliador.qtde_avaliacoes
                    avaliadores_internos.append(avaliador)
                    valor_total_internos += avaliador.valor_a_pagar

                if avaliacao.avaliador.eh_externo() and (relatorio == 'externo' or relatorio == 'externo_instituicao_origem'):
                    total_avaliacoes_externos += avaliador.qtde_avaliacoes

                    avaliador.desconto_inss_a_pagar = round(avaliador.valor_a_pagar * inss, 2)
                    avaliador.desconto_iss_a_pagar = round(avaliador.valor_a_pagar * iss, 2)
                    avaliador.valor_liquido_a_pagar = avaliador.valor_a_pagar - (avaliador.desconto_inss_a_pagar + avaliador.desconto_iss_a_pagar)
                    avaliadores_externos.append(avaliador)

                    if avaliador.instituicao_origem:
                        if avaliador.instituicao_origem_id in total_avaliacoes_por_instituicao:
                            for ava in avaliador.avaliacoes:
                                if ava.processo_id not in total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id][0]:
                                    total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id][0].append(ava.processo_id)
                                    total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id][1] += 1  # qtde. processos
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id][2] += avaliador.qtde_avaliacoes  # qtde. avaliações
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id][3] += avaliador.valor_a_pagar  # valor total a pagar
                        else:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem_id] = [
                                [avaliacao.processo_id],
                                1,
                                avaliador.qtde_avaliacoes,
                                avaliador.valor_a_pagar,
                            ]

                    valor_total_externos += avaliador.valor_liquido_a_pagar

            total_avaliacoes = total_avaliacoes_internos + total_avaliacoes_externos

        return locals()


def eh_dono(request, processo):
    retorno = False
    if request.user.is_authenticated and request.user.get_vinculo() == processo.servidor.get_vinculo():
        retorno = True
    return retorno


def pode_anexar(request: HttpRequest, processo: ProcessoRSC) -> bool:
    """Como a tela do processo, que só mostra os uploaders ao dono com o processo editável."""
    return eh_dono(request, processo) and processo.avaliado_pode_editar()


def soh_dono(request, processo):
    if not eh_dono(request, processo):
        raise PermissionDenied


def soh_cppd(request):
    if not eh_membro_cppd(request):
        raise PermissionDenied


def eh_avaliador(request, processo):
    return request.user.has_perm('rsc.pode_avaliar_processorsc')


def eh_membro_cppd(request):
    return request.user.has_perm('rsc.pode_validar_processorsc')


def eh_presidente_cppd(request):
    return request.user.has_perm('rsc.delete_processoavaliador')


def eh_rh(request):
    return request.user.has_perm('rsc.pode_ver_relatorio_rsc')


def soh_cppd_dono_avaliador(request, processo):
    if not request.user.has_perm('rsc.pode_validar_processorsc') and not eh_dono(request, processo) and not eh_avaliador(request, processo):
        raise PermissionDenied


def soh_presidentecppd_e_dono(request, processo):
    if not eh_presidente_cppd(request) and not eh_dono(request, processo):
        raise PermissionDenied


def soh_cppd_e_dono(request, processo):
    if not request.user.has_perm('rsc.pode_validar_processorsc') and soh_dono(request, processo):
        raise PermissionDenied


def soh_cppd_dono_e_rh(request, processo):
    if not eh_membro_cppd(request) and not eh_dono(request, processo) and not eh_rh(request):
        raise PermissionDenied


def eh_avaliador_do_processo(request, processo_id):
    vinculo = request.user.get_vinculo()
    return ProcessoAvaliador.objects.filter(avaliador__vinculo=vinculo, processo__id=processo_id).exists()


def eh_avaliador_da_avaliacao(request, avaliacao_id):
    vinculo = request.user.get_vinculo()
    return Avaliacao.objects.filter(avaliador__vinculo=vinculo, id=avaliacao_id).exists()


@rtr()
@login_required()
def gerar_processo_eletronico(request, processo_id):
    if eh_presidente_cppd(request) or request.user.is_superuser:
        processo = get_object_or_404(ProcessoRSC, pk=processo_id)

        docente_enviou_processo = processo.status != ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD
        processo_eletronico_gerado = processo.processo_eletronico
        pode_gerar_pe = True
        if not docente_enviou_processo:
            pode_gerar_pe = False

        if processo_eletronico_gerado:
            pode_gerar_pe = False

        if not pode_gerar_pe:
            raise PermissionDenied('Você não tem permissão para acessar esta página.')

        setor_servidor = processo.servidor.setor
        if processo.servidor.eh_aposentado:
            if processo.servidor.setor_lotacao:
                setor_servidor = processo.servidor.setor_lotacao.uo.equivalente.setor
            else:
                setor_servidor = get_setor_cppd()

        processo_tramite = {
            'tipo_processo': TipoProcesso.objects.get(id=517),
            'assunto': 'Reconhecimento de Saberes e Competências - RSC',
            'setor_destino': get_setor_cppd(),
        }

        from processo_eletronico.models import Processo as ProcessoEletronico

        processo.processo_eletronico = ProcessoEletronico.cadastrar_processo(
            user=processo.servidor.get_user(),
            processo_tramite=processo_tramite,
            papel=processo.servidor.papeis_ativos.first(),
            documentos_texto=[],
            documentos_digitalizados=[],
            interessados=[processo.servidor.get_vinculo()],
            setor_processo=setor_servidor,
        )
        processo.save()

        return httprr('/admin/rsc/processorsc/', 'Processo Eletrônico gerado com sucesso.')
    else:
        raise PermissionDenied('Você não tem permissão para acessar esta página.')
