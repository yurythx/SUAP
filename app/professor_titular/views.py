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
from django.db.models import Q, Sum
from django.dispatch import Signal
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import lower
from django.views.decorators.csrf import csrf_exempt
from pypdf import PdfReader, PdfWriter
from sentry_sdk import capture_exception

from comum.models import Configuracao
from comum.utils import get_setor, get_setor_cppd, get_sigla_reitoria, get_uo
from djtools.forms import ValidationError
from djtools.storages import AWSUploadBackend, LocalUploadBackend, is_remote_storage
from djtools.storages.utils import cache_file, copy_file
from djtools.templatetags.filters import format_datetime, format_money
from djtools.utils import JsonResponse, documento, httprr, is_ajax, permission_required, rtr, strptime_or_default, upload_em_pdf
from documento_eletronico.models import Documento, TipoConferencia, TipoDocumento
from processo_eletronico.models import Processo as ProcessoEletronico
from processo_eletronico.models import TipoProcesso
from professor_titular.forms import (
    AssinaturaRequerimentoForm,
    AvaliadorForm,
    DataConcessaoTitulacaoDoutorForm,
    DataGraduacaoIngressoEBTTForm,
    DeclaracaoDIGPEForm,
    JustificativaDesistenciaForm,
    ProcessoPagamentoForm,
    ProcessoTitularForm,
    RecusaAvaliacaoForm,
    RejeitarProcessoCPPDForm,
    RelatorioPagamentoForm,
    TermoAvaliacaoDesempenhoForm,
    ValidacaoCPPDForm,
)
from professor_titular.models import (
    PRIVATE_ROOT_DIR,
    Arquivo,
    ArquivosExigidos,
    Avaliacao,
    AvaliacaoItem,
    CategoriaMemorialDescritivo,
    CloneArquivoErro,
    ConfiguracaoTitular,
    Criterio,
    Grupo,
    PontuacaoMinima,
    ProcessoAvaliador,
    ProcessoTitular,
    ValidacaoCPPD,
)
from protocolo.models import Processo, Tramite
from rh import utils
from rh.models import Avaliador
from rsc.models import ParametroPagamento


@login_required()
def criar_processo_titular(request):
    servidor_logado = request.user.get_relacionamento()
    if request.user.eh_servidor and not servidor_logado.eh_docente:
        raise PermissionDenied('Você não é docente para criar um processo de professor titular.')
    processo = ProcessoTitular()
    processo.servidor = servidor_logado
    processo.status = ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD
    processo.ano = datetime.date.today().year
    processo.save()
    return redirect(f'/professor_titular/abrir_processo_titular/{processo.id}/')


@rtr()
@login_required()
def imprimir_processo(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    return locals()


@login_required()
def visualizar_arquivo_pdf(request, arquivo_id):
    arquivo = Arquivo.objects.filter(encrypted_pk=arquivo_id).first()
    if arquivo:
        soh_cppd_dono_avaliador(request, arquivo.processo)
        try:
            response = FileResponse(default_storage.open(arquivo.diretorio, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(arquivo.nome)}"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except FileNotFoundError:
            return httprr('..', 'Arquivo não encontrado.', 'error')
    else:
        return httprr('..', 'Arquivo não encontrado.', 'error')


@login_required()
def visualizar_arquivo_exigido_pdf(request, arquivo_id):
    arquivo = ArquivosExigidos.objects.filter(encrypted_pk=arquivo_id).first()
    if arquivo:
        soh_cppd_dono_avaliador(request, arquivo.processo)
        try:
            response = FileResponse(default_storage.open(arquivo.diretorio, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(arquivo.nome)}"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except FileNotFoundError:
            return httprr('..', 'Arquivo não encontrado.', 'error')
    else:
        return httprr('..', 'Arquivo não encontrado.', 'error')


@csrf_exempt
@login_required()
def excluir_arquivo_pdf(request, arquivo_id):
    try:
        arquivo = Arquivo.objects.filter(encrypted_pk=arquivo_id).first()
        if arquivo:
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
        else:
            return JsonResponse({'ok': False, 'msg': 'Arquivo não encontrado.'})
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
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
    except Exception as ex:
        return JsonResponse({'ok': False, 'msg': str(ex)})


@login_required()
def excluir_processo_titular(request, processo_id):
    processo = ProcessoTitular.objects.get(pk=processo_id)
    soh_dono(request, processo)

    if not processo.avaliado_pode_editar():
        return httprr('..', tag='error', message='O processo não pode ser excluído na situação atual.')

    # removendo arquivo físico
    arquivos = processo.arquivo_set.all()
    for arquivo in arquivos:
        default_storage.delete(arquivo.diretorio)

    processo.delete()

    return httprr('/admin/professor_titular/processotitular/', 'Processo excluído com sucesso.')


@rtr()
@login_required()
def documentos_preliminares(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)

    data_concessao_titulacao_doutor_form = DataConcessaoTitulacaoDoutorForm(request=request, processo=processo)
    data_graduacao_ingresso_ebtt_form = DataGraduacaoIngressoEBTTForm(request=request, processo=processo)
    termo_avaliacao_desempenho_form = TermoAvaliacaoDesempenhoForm(request=request, processo=processo)
    declaracao_DIGPE_form = DeclaracaoDIGPEForm(request=request, processo=processo)

    ultima_validacao = processo.ultima_validacao_processo()

    processo_form = ProcessoTitularForm(
        data={
            'introducao_relatorio_descritivo': processo.introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_titulacao_doutor': processo.data_concessao_titulacao_doutor,
            'data_progressaoD404': processo.data_progressaoD404,
            'data_avaliacao_desempenho': processo.data_avaliacao_desempenho,
            'data_graduacao_EBTT': processo.data_graduacao_EBTT,
        },
        processo=processo,
    )

    arquivos_documentos_exigidos = ArquivosExigidos.objects.filter(processo=processo)
    for arquivo in arquivos_documentos_exigidos:
        if arquivo.tipo == ArquivosExigidos.TITULO_DOUTOR:
            processo_form.arquivo_conclusao_titulacao_titular_pretendido = arquivo
        elif arquivo.tipo == ArquivosExigidos.TERMO_AVALIACAO_DESEMPENHO:
            processo_form.arquivo_termo_avaliacao_desempenho = arquivo
        elif arquivo.tipo == ArquivosExigidos.DECLARACAO_DIGPE:
            processo_form.arquivo_declarao_DIGPE = arquivo
        elif arquivo.tipo == ArquivosExigidos.DIPLOMA_GRADUACAO_EBTT:
            processo_form.arquivo_graduacao_ingresso_ebtt = arquivo

    return locals()


def _recalcular_ponto(processo):
    grupos = Grupo.objects.all()
    pontuacao_requerida = 0
    ano = datetime.date.today().year
    if processo.protocolo or processo.processo_eletronico:
        ano = processo.get_ano_protocolo

    for grupo in grupos:
        soma_indicadores_grupo = 0
        soma_arquivos_indicadores = 0

        teto_grupo = grupo.get_teto(ano)
        indicadores = []
        for indicador in grupo.indicador_set.all():
            valor = 0
            criterio_list = []
            for criterio in indicador.criterio_set.all():
                valor_criterio = 0
                arquivos = processo.arquivo_set.filter(criterio=criterio)
                for arquivo in arquivos:
                    valor += arquivo.nota_pretendida
                    soma_arquivos_indicadores += arquivo.nota_pretendida

                    valor_criterio += arquivo.nota_pretendida

                # somando pontos por critério
                criterio.total_ponto = valor_criterio
                criterio_list.append(criterio)

            indicador.criterios = criterio_list

            # somando pontos das RSCs
            pontuacao_requerida += valor

            # somando pontos das diretrizes
            indicador.total_ponto = valor
            soma_indicadores_grupo = soma_arquivos_indicadores

            indicadores.append(indicador)
        grupo.indicadores = indicadores

        if soma_indicadores_grupo > teto_grupo:
            soma_indicadores_grupo = teto_grupo

        if grupo.nome == 'A':
            processo.pontuacao_pretendida_grupo_A = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'B':
            processo.pontuacao_pretendida_grupo_B = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'C':
            processo.pontuacao_pretendida_grupo_C = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'D':
            processo.pontuacao_pretendida_grupo_D = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'E':
            processo.pontuacao_pretendida_grupo_E = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'F':
            processo.pontuacao_pretendida_grupo_F = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'G':
            processo.pontuacao_pretendida_grupo_G = soma_indicadores_grupo
            processo.save()
        elif grupo.nome == 'H':
            processo.pontuacao_pretendida_grupo_H = soma_indicadores_grupo

        processo.pontuacao_pretendida = (
            (processo.pontuacao_pretendida_grupo_A or 0)
            + (processo.pontuacao_pretendida_grupo_B or 0)
            + (processo.pontuacao_pretendida_grupo_C or 0)
            + (processo.pontuacao_pretendida_grupo_D or 0)
            + (processo.pontuacao_pretendida_grupo_E or 0)
            + (processo.pontuacao_pretendida_grupo_F or 0)
            + (processo.pontuacao_pretendida_grupo_G or 0)
            + (processo.pontuacao_pretendida_grupo_H or 0)
        )
        processo.save()


@csrf_exempt
@rtr()
@login_required()
def recalcular_pontuacao(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)

    _recalcular_ponto(processo)

    return httprr('..', 'Pontuação recalculada com sucesso.')


@csrf_exempt
@rtr()
@login_required()
def abrir_processo_titular(request, processo_id):
    processo = (
        ProcessoTitular.objects.filter(pk=processo_id).select_related('servidor', 'servidor__cargo_emprego').prefetch_related('arquivo_set').first()
    )
    if not processo:
        raise Http404('Não foi encontrado processo de professor titular com o referida id')
    soh_cppd_e_dono(request, processo)
    eh_dono_processo = eh_dono(request, processo)
    pode_salvar = eh_dono_processo and processo.status in [
        ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD,
        ProcessoTitular.STATUS_AGUARDANDO_AJUSTES_USUARIO,
    ]
    title = 'Processo Titular'

    data_concessao_titulacao_doutor_form = DataConcessaoTitulacaoDoutorForm(request=request, processo=processo)
    data_graduacao_ingresso_ebtt_form = DataGraduacaoIngressoEBTTForm(request=request, processo=processo)
    termo_avaliacao_desempenho_form = TermoAvaliacaoDesempenhoForm(request=request, processo=processo)
    declaracao_DIGPE_form = DeclaracaoDIGPEForm(request=request, processo=processo)
    """
    buscando a última validação cppd
    """
    ultima_validacao = processo.ultima_validacao_processo()

    grupos = Grupo.objects.all()

    processo_form = ProcessoTitularForm(
        data={
            'introducao_relatorio_descritivo': processo.introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_titulacao_doutor': processo.data_concessao_titulacao_doutor,
            'data_progressaoD404': processo.data_progressaoD404,
            'data_avaliacao_desempenho': processo.data_avaliacao_desempenho,
            'data_graduacao_EBTT': processo.data_graduacao_EBTT,
        },
        processo=processo,
    )

    arquivos_documentos_exigidos = ArquivosExigidos.objects.filter(processo=processo)
    for arquivo in arquivos_documentos_exigidos:
        if arquivo.tipo == ArquivosExigidos.TITULO_DOUTOR:
            processo_form.arquivo_conclusao_titulacao_titular_pretendido = arquivo
        elif arquivo.tipo == ArquivosExigidos.TERMO_AVALIACAO_DESEMPENHO:
            processo_form.arquivo_termo_avaliacao_desempenho = arquivo
        elif arquivo.tipo == ArquivosExigidos.DECLARACAO_DIGPE:
            processo_form.arquivo_declarao_DIGPE = arquivo
        elif arquivo.tipo == ArquivosExigidos.DIPLOMA_GRADUACAO_EBTT:
            processo_form.arquivo_graduacao_ingresso_ebtt = arquivo

    pontuacao_requerida = 0
    data_referencia_retroatividade = None
    ano = processo.get_ano_protocolo if processo.protocolo or processo.processo_eletronico else datetime.date.today().year

    grupos_list = []
    for grupo in grupos.prefetch_related('indicador_set', 'indicador_set__criterio_set', 'indicador_set__criterio_set__arquivo_set'):
        #
        grupo_tem_pontos = False
        total_pontos_grupo = 0
        teto_grupo = grupo.get_teto(ano)
        #
        soma_indicadores_grupo = 0
        soma_arquivos_indicadores = 0
        indicadores = []
        for indicador in grupo.indicador_set.all():
            valor = 0
            criterio_list = []
            for criterio in indicador.criterio_set.all():
                valor_criterio = 0
                arquivos = processo.arquivo_set.filter(criterio=criterio)
                for arquivo in arquivos:
                    np = arquivo.nota_pretendida or 0
                    if np > 0:
                        grupo_tem_pontos = True
                    valor += np
                    soma_arquivos_indicadores += np
                    valor_criterio += np
                    # if data_referencia_retroatividade == None or  arquivo.data_referencia == None or arquivo.data_referencia < data_referencia_retroatividade and arquivo.nota_pretendida > 0:
                    #    data_referencia_retroatividade = arquivo.data_referencia

                # somando pontos por critério
                criterio.total_ponto = valor_criterio
                criterio_list.append(criterio)

            indicador.criterios = criterio_list

            # somando pontos das RSCs
            pontuacao_requerida += valor

            # somando pontos das diretrizes
            indicador.total_ponto = valor
            soma_indicadores_grupo = soma_arquivos_indicadores

            indicadores.append(indicador)
        grupo.indicadores = indicadores
        grupo.tem_pontos = grupo_tem_pontos
        grupos_list.append(grupo)

    pontuacoes = PontuacaoMinima.objects.filter(ano=ano)
    pontuacoes_requeridas = []
    if pontuacoes.exists():
        pontuacao_minima_exigida = pontuacoes[0].pontuacao_exigida
        qtd_minima_grupos = pontuacoes[0].qtd_minima_grupos

        for po in pontuacoes:
            grupo = po.grupo.nome
            pontos = po.pontuacao_exigida * (po.grupo.percentual / 100)
            pontos = f'{pontos:.2f}'
            grupo_pontos = f'Grupo {grupo} tem como pontuação máxima {pontos} pontos'
            pontuacoes_requeridas.append(grupo_pontos)

    relacionamento = request.user.get_relacionamento()

    #
    # selecionando configurações
    config = ConfiguracaoTitular.objects.first()
    if not config:
        raise Http404('Não existe configuração para o processo de professor titular.')
    return locals()


@csrf_exempt
@login_required()
def salvar_processo_titular(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_dono(request, processo)
    try:
        """
        verifica status do processo
        """
        if not processo.avaliado_pode_editar() and not processo.avaliado_pode_ajustar():
            raise Exception('Você não pode alterar um processo que já foi enviado à CPPD.')

        if request.method == 'POST' and is_ajax(request):
            # atualiza introducao e conclusao do processo
            processo.introducao_relatorio_descritivo = request.POST['introducao_relatorio_descritivo']
            processo.conclusao_relatorio_descritivo = request.POST['conclusao_relatorio_descritivo']
            processo.atividade_ensino_orientacao = request.POST['atividade_ensino_orientacao_txt']
            processo.atividade_pesquisa_dev_tec_inovacao = request.POST['atividade_pesquisa_dev_tec_inovacao_txt']
            processo.atividade_extensao = request.POST['atividade_extensao_txt']
            processo.participacao_processo_avaliacao = request.POST['atividade_processo_avaliacao_txt']
            processo.revista_cientifica = request.POST['participacao_revista_cientifica_txt']
            processo.membro_comissao_carater_pedagogico = request.POST['participacao_membro_comissao_carater_pedagogico_txt']
            processo.membro_comissao_elaboracao_ou_revisao_projeto_pedagogico = request.POST[
                'participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico_txt'
            ]
            processo.organizacao_eventos = request.POST['arquivos_participacao_organizacao_eventos_txt']
            processo.membro_comissao_carater_nao_pedagogico = request.POST['arquivos_participacao_membro_comissao_carater_nao_pedagogico_txt']
            processo.exercicio_cargo_direcao_coordenacao = request.POST['arquivos_exercicio_cargo_direcao_coordenacao_txt']
            processo.atividade_aperfeicoamento = request.POST['arquivos_atividade_aperfeicoamento_txt']
            processo.atividade_representacao = request.POST['arquivos_atividade_representacao_txt']

            if processo.avaliado_pode_editar():
                if request.POST.get('data_concessao_titulacao_doutor'):
                    processo.data_concessao_titulacao_doutor = strptime_or_default(
                        request.POST.get('data_concessao_titulacao_doutor').strip(), '%Y-%m-%d'
                    ).date()
                if request.POST.get('data_progressaoD404'):
                    processo.data_progressaoD404 = strptime_or_default(request.POST.get('data_progressaoD404').strip(), '%Y-%m-%d').date()
                if request.POST.get('data_avaliacao_desempenho'):
                    processo.data_avaliacao_desempenho = strptime_or_default(request.POST.get('data_avaliacao_desempenho'), '%Y-%m-%d').date()
                if request.POST.get('data_graduacao_EBTT'):
                    processo.data_graduacao_EBTT = strptime_or_default(request.POST.get('data_graduacao_EBTT').strip(), '%Y-%m-%d').date()
                if request.POST.get('rsc1').strip():
                    processo.pontuacao_pretendida_grupo_A = Decimal(request.POST.get('rsc1').strip().replace(',', '.'))
                if request.POST.get('rsc2').strip():
                    processo.pontuacao_pretendida_grupo_B = Decimal(request.POST.get('rsc2').strip().replace(',', '.'))
                if request.POST.get('rsc3').strip():
                    processo.pontuacao_pretendida_grupo_C = Decimal(request.POST.get('rsc3').strip().replace(',', '.'))
                if request.POST.get('rsc4').strip():
                    processo.pontuacao_pretendida_grupo_D = Decimal(request.POST.get('rsc4').strip().replace(',', '.'))
                if request.POST.get('rsc5').strip():
                    processo.pontuacao_pretendida_grupo_E = Decimal(request.POST.get('rsc5').strip().replace(',', '.'))
                if request.POST.get('rsc6').strip():
                    processo.pontuacao_pretendida_grupo_F = Decimal(request.POST.get('rsc6').strip().replace(',', '.'))
                if request.POST.get('rsc7').strip():
                    processo.pontuacao_pretendida_grupo_G = Decimal(request.POST.get('rsc7').strip().replace(',', '.'))
                if request.POST.get('rsc8').strip():
                    processo.pontuacao_pretendida_grupo_H = Decimal(request.POST.get('rsc8').strip().replace(',', '.'))

                processo.pontuacao_pretendida = (
                    processo.pontuacao_pretendida_grupo_A
                    + processo.pontuacao_pretendida_grupo_B
                    + processo.pontuacao_pretendida_grupo_C
                    + processo.pontuacao_pretendida_grupo_D
                    + processo.pontuacao_pretendida_grupo_E
                    + processo.pontuacao_pretendida_grupo_F
                    + processo.pontuacao_pretendida_grupo_G
                    + processo.pontuacao_pretendida_grupo_H
                )

            processo.save()

            # procura os arquivos do processo e salva as informacoes
            for key in list(request.POST.keys()):
                key_partes = key.split('_')  # chaves procuradas: 'Arquivo_idArquivo_campo' e 'Criterio_criterio.pk_descricao
                if len(key_partes) == 3:
                    if key_partes[0] == 'Arquivo':
                        pk_arquivo = key_partes[1]
                        arquivo = Arquivo.objects.get(pk=pk_arquivo)

                        campo = key_partes[2]
                        if campo == 'qtd':
                            arquivo.qtd_itens = int(request.POST[key])

                        elif campo == 'data':  # 'dd/mm/aaaa'
                            data_partes = request.POST[key].split('-')

                            dia = int(data_partes[2])
                            mes = int(data_partes[1])
                            ano = int(data_partes[0])
                            if datetime.date.today() < datetime.date(ano, mes, dia):
                                msg = f'A data de referência não pode ser maior do que a data atual. Problema encontrado no critério {arquivo.criterio} do grupo {arquivo.criterio.indicador.grupo.nome}.'
                                msg_retorno = {'ok': False, 'msg': msg}
                                return JsonResponse(msg_retorno)

                            arquivo.data_referencia = datetime.date(ano, mes, dia)

                        elif campo == 'nota':
                            arquivo.nota_pretendida = float(request.POST[key])

                        elif campo == 'descricao':
                            if request.POST[key] == '':
                                msg = (
                                    f'A descrição de critério {arquivo.criterio} do grupo {arquivo.criterio.indicador.grupo.nome} não foi preenchida.'
                                )
                                msg_retorno = {'ok': False, 'msg': msg}
                                return JsonResponse(msg_retorno)
                            else:
                                arquivo.descricao = request.POST[key]

                        arquivo.save()
            # messages.info(request, 'Processo salvo com sucesso.')

        retorno = {'ok': True, 'msg': ''}
        data_referencia_retroativa = processo.get_data_referencia_retroativa()
        if data_referencia_retroativa:
            retorno['data_referencia_retroatividade'] = format_datetime(data_referencia_retroativa)
        else:
            retorno['data_referencia_retroatividade'] = '-'

        return JsonResponse(retorno)
    except Exception as e:
        if settings.DEBUG:
            raise e
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
def enviar_processo_titular(request, processo_id):
    title = 'Assinatura do requerimento para confirmar o envio'
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)

    # verificar os arquivos do processo em busca de arquivos com datas ou quantidade de itens nulos
    problema_arquivo = Arquivo.objects.filter(processo=processo).filter(Q(data_referencia__isnull=True) | Q(qtd_itens__isnull=True)).exists()
    if problema_arquivo:
        return httprr(
            request.META.get('HTTP_REFERER'),
            'Existe(m) arquivo(s) faltando o preenchimento da data ou quantidade de itens. Identifique de forma mais fácil o problema no Quandro de Resumo.',
            'error',
        )

    form = AssinaturaRequerimentoForm(
        request.POST or None,
        request=request,
        conteudo=processo.conteudo_a_ser_assinado_do_requerimento,
        chave=processo.chave_a_ser_utilizada_na_assinatura_do_requerimento,
    )
    if form.is_valid() and form.assinatura_is_valida():
        try:
            processo.assinatura_requerimento = form.assinatura
            processo.status = ProcessoTitular.STATUS_AGUARDANDO_VALIDACAO_CPPD
            processo.ano_envio_cppd = datetime.date.today().year
            validacaoCPPD = processo.ultima_validacao_processo()

            if validacaoCPPD:
                processo.status = ProcessoTitular.STATUS_AGUARDANDO_NOVA_VALIDACAO
                validacaoCPPD.ajustado = True
                validacaoCPPD.save()
            processo.save()
            return httprr('/admin/professor_titular/processotitular/', 'Processo titular enviado para CPPD', close_popup=True)
        except Exception:
            form.add_error(None, 'Erro ao enviar para CPPD, tente novamente.')
    return locals()


@rtr()
@permission_required('professor_titular.pode_validar_processotitular')
@transaction.atomic
def validar_processo_titular(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    title = f'Validação do Processo {processo}'

    if processo.status not in [ProcessoTitular.STATUS_AGUARDANDO_VALIDACAO_CPPD, ProcessoTitular.STATUS_AGUARDANDO_NOVA_VALIDACAO]:
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
                verificando status
                """
                titulacao_status = request.POST.get('titulacao_status')
                if titulacao_status == '0':
                    raise Exception('O título que habilita a classe titular (Doutorado) não está validado.')

                graduacao_ebtt_status = request.POST.get('graduacao_ebtt_status')
                if graduacao_ebtt_status == '0':
                    raise Exception('A graduação no ingresso no cargo EBTT não está validada.')

                progressao_status = request.POST.get('progressao_status')
                if progressao_status == '0':
                    raise Exception('A Progressão para D404 não está validada.')

                avaliacao_desempenho_status = request.POST.get('avaliacao_desempenho_status')
                if avaliacao_desempenho_status == '0':
                    raise Exception('A Avaliação de Desempenho não está validada.')

                formulario_pontuacao_status = request.POST.get('formulario_pontuacao_status')
                if formulario_pontuacao_status == '0' and acao == 'aceitar':
                    raise Exception('O aceite NÃO foi possível pois o fomulário de pontuação não foi confirmado.')

                relatorio_descritivo = request.POST.get('relatorio_descritivo')
                if not relatorio_descritivo:
                    raise Exception('Você precisa avaliar o relatório descritivo.')

                relatorio_descritivo_status = request.POST.get('relatorio_descritivo_status')
                if relatorio_descritivo_status == '0' and acao == 'aceitar':
                    raise Exception('O aceite NÃO foi possível pois o relatório descritivo não foi confirmado.')

                """
                validando data de conclusão Titulo Doutor
                """
                titulacao = request.POST.get('titulacao')
                data_conclusao_titulacao_validada = request.POST.get('data_conclusao_titulacao_validada')
                if int(titulacao) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_conclusao_titulacao_validada == '':
                    raise Exception('A data de conclusão validada deve ser preenchida.')
                if not data_conclusao_titulacao_validada:
                    if not processo.data_concessao_titulacao_doutor:
                        raise Exception('O processo está sem a data da titulação de doutor.')
                    data_conclusao_titulacao_validada = processo.data_concessao_titulacao_doutor
                else:
                    data_conclusao_titulacao_validada = strptime_or_default(request.POST.get('data_conclusao_titulacao_validada'), '%Y-%m-%d')

                """
                validando data graduação do início de exercício EBTT
                """
                inicio_exercicio = request.POST.get('graduacao_ebtt')
                data_graduacao_ebtt_validada = request.POST.get('data_graduacao_ebtt_validada')
                if int(inicio_exercicio) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_graduacao_ebtt_validada == '':
                    raise Exception('A data da graduação para ingresso no cargo de professor de EBTT deve ser preenchida.')
                if not data_graduacao_ebtt_validada:
                    if not processo.data_graduacao_EBTT:
                        raise Exception('O processo está sem data de graduação no ingresso na carreira EBTT.')
                    data_graduacao_ebtt_validada = processo.data_graduacao_EBTT
                else:
                    data_graduacao_ebtt_validada = strptime_or_default(request.POST.get('data_graduacao_ebtt_validada'), '%Y-%m-%d')

                """
                validando data de Progressão para D404
                """
                progressao = request.POST.get('progressao')
                data_progressao_validada = request.POST.get('data_progressao_validada')
                if int(progressao) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_progressao_validada == '':
                    raise Exception('A data da progressão para D404 validada deve ser preenchida.')
                if not data_progressao_validada:
                    if not processo.data_progressaoD404:
                        raise Exception('O processo está sem a data de progressão para D404.')
                    data_progressao_validada = processo.data_progressaoD404
                else:
                    data_progressao_validada = strptime_or_default(request.POST.get('data_progressao_validada'), '%d/%m/%Y')

                """
                validando data de avaliação de desempenho
                """
                avaliacao_desempenho = request.POST.get('avaliacao_desempenho')
                data_avaliacao_desempenho_validada = request.POST.get('data_avaliacao_desempenho_validada')
                if int(avaliacao_desempenho) == ValidacaoCPPD.TIPO_VALIDACAO_DATA_ERRADA and data_avaliacao_desempenho_validada == '':
                    raise Exception('A data do termo de avaliação de desempenho validada deve ser preenchida.')
                if not data_avaliacao_desempenho_validada:
                    if not processo.data_avaliacao_desempenho:
                        raise Exception('O processo está sem a data de avaliação de desempenho')
                    data_avaliacao_desempenho_validada = processo.data_avaliacao_desempenho
                else:
                    data_avaliacao_desempenho_validada = strptime_or_default(request.POST.get('data_avaliacao_desempenho_validada'), '%Y-%m-%d')

                """
                completando objeto validacaoCPPD
                """
                validacaoCPPD.data_conclusao_titulacao_validada = data_conclusao_titulacao_validada
                validacaoCPPD.titulacao_status = titulacao_status

                validacaoCPPD.data_graduacao_ebtt_validada = data_graduacao_ebtt_validada
                validacaoCPPD.graduacao_ebtt_status = graduacao_ebtt_status

                validacaoCPPD.data_progressao_validada = data_progressao_validada
                validacaoCPPD.progressao_status = progressao_status

                validacaoCPPD.data_avaliacao_desempenho_validada = data_avaliacao_desempenho_validada
                validacaoCPPD.avaliacao_desempenho_status = avaliacao_desempenho_status

                validacaoCPPD.formulario_pontuacao_status = formulario_pontuacao_status
                validacaoCPPD.relatorio_descritivo_status = relatorio_descritivo_status

                """
                rejeitando o processo
                """
                if acao == 'devolver':
                    processo.status = ProcessoTitular.STATUS_AGUARDANDO_AJUSTES_USUARIO
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
                    processo.status = ProcessoTitular.STATUS_AGUARDANDO_AVALIADORES
                    validacaoCPPD.processo = processo
                    msg = 'Processo aceito.'
                    ok = True

            else:
                motivo_rejeicao = request.POST.get('motivo_rejeicao')
                if not motivo_rejeicao or motivo_rejeicao == '':
                    raise Exception('O motivo da rejeição deve ser preenchido.')
                else:
                    validacaoCPPD.motivo_rejeicao = motivo_rejeicao
                    processo.status = ProcessoTitular.STATUS_REJEITADO
                msg = 'Processo rejeitado com sucesso!'

            processo.save()

            validacaoCPPD.save()

        except Exception as e:
            ok = False
            msg = e.args[0]
        return JsonResponse({'msg': msg, 'url': '/admin/professor_titular/processotitular/', 'ok': ok})

    return locals()


@login_required()
def create_on_upload(request, processo, diretorio, nome_do_arquivo, criterio, tamanho_arquivo):
    soh_dono(request, processo)
    novo_arquivo = Arquivo()
    novo_arquivo.nome = utils.gerar_nome_unico(nome_do_arquivo)
    novo_arquivo.diretorio = diretorio
    novo_arquivo.criterio = criterio
    novo_arquivo.processo = processo
    novo_arquivo.tamanho = tamanho_arquivo
    novo_arquivo.save()
    return novo_arquivo


@login_required()
def create_on_upload_documentos_exigidos(request, processo, diretorio, nome_do_arquivo, tamanho_arquivo, tipo):
    soh_dono(request, processo)
    # Tem que refatorar para não deixar salvar vários arquivos de um mesmo tipo para o mesmo processo. o arquivo deve ser sempre atualizado
    novo_arquivo = ArquivosExigidos()
    novo_arquivo.nome = nome_do_arquivo
    novo_arquivo.diretorio = diretorio
    novo_arquivo.processo = processo
    novo_arquivo.tamanho = tamanho_arquivo
    if tipo == 'TITULO_DOUTOR':
        novo_arquivo.tipo = ArquivosExigidos.TITULO_DOUTOR
    elif tipo == 'TERMO_AVALIACAO_DESEMPENHO':
        novo_arquivo.tipo = ArquivosExigidos.TERMO_AVALIACAO_DESEMPENHO
    elif tipo == 'DECLARACAO_DIGPE':
        novo_arquivo.tipo = ArquivosExigidos.DECLARACAO_DIGPE
    elif tipo == 'DIPLOMA_GRADUACAO_EBTT':
        novo_arquivo.tipo = ArquivosExigidos.DIPLOMA_GRADUACAO_EBTT
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
                processo = get_object_or_404(ProcessoTitular, pk=processo_id)
            else:
                return JsonResponse({'success': False, 'status': 400})
            if not pode_anexar(request, processo):
                raise PermissionDenied

            if 'criterio' in request.GET:
                criterio_id = request.GET['criterio']
                criterio = get_object_or_404(Criterio, pk=criterio_id)
            else:
                return JsonResponse({'success': False, 'status': 400})

            content_type = str(request.META.get('CONTENT_TYPE', ''))
            content_length = int(request.META.get('CONTENT_LENGTH', 0))
            if content_type == '' or content_length == 0:
                return JsonResponse({'success': False, 'status': 400})
            resolvido = upload_em_pdf(request)
            if resolvido is None:
                return JsonResponse({'success': False})
            upload, is_raw, filename = resolvido

            # Limita o nome enviado pelo usuário para não estourar os campos
            # varchar(255) de Arquivo (nome/diretorio) nem o limite de path do
            # filesystem/storage. gerar_nome_unico ainda soma ~9 chars ao nome.
            filename = utils.truncar_nome_arquivo(filename)

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
                if not hasattr(arquivo, 'id'):
                    return JsonResponse({'success': False, 'status': 400})

                ret_json = {
                    'success': success,
                    'filename': new_filename,
                    'arquivo_pk': arquivo.id,
                    'arquivo_pk_crypto': arquivo.encrypted_pk,
                    'tamanho': content_length,
                    'field_qtd': ProcessoTitularForm.factory_field_render_qtd_itens(arquivo),
                    'field_data': ProcessoTitularForm.factory_field_render_data_referencia(arquivo),
                    'field_nota': ProcessoTitularForm.factory_field_render_nota_pretendida(arquivo),
                    'field_descricao': ProcessoTitularForm.factory_field_render_descricao(arquivo),
                }

                return JsonResponse(ret_json)
            else:
                return JsonResponse({'success': False, 'status': 400})

            # let Ajax Upload know whether we saved it or not

            # form_arquivo = CriterioArquivoForm()

            # field_data_referencia_name = "Arquivo_{}_data".format(arquivo.id)
            # field_data_referencia =  form_arquivo.fields['data_referencia'].widget.render(field_data_referencia_name,'', {'id': 'data_{}'.format(arquivo.id)})

            # field_qtd_itens_name = "Arquivo_{}_qtd".format(arquivo.id)
            # field_qtd_itens_onkeyup = "calcula_nota_pretendida(this, {}, {}, {}, {}, {});".format(arquivo.criterio.fator, arquivo.id, arquivo.criterio.teto,
            #                                                                                  arquivo.criterio.diretriz.id, arquivo.criterio.diretriz.tipo_titular.id)
            # field_qtd_itens = form_arquivo.fields['qtd_itens'].widget.render(field_qtd_itens_name,'', {'id': 'qtd_{}'.format(arquivo.id),
            #                                                                                            'OnKeyUp': field_qtd_itens_onkeyup})

            # field_nota_pretendida_name = "Arquivo_{}_nota".format(arquivo.id)
            # field_nota_pretendida =  form_arquivo.fields['nota_pretendida'].widget.render(field_nota_pretendida_name,'', {'id': 'nota_{}'.format(arquivo.id),
            #                                                                                                               'type': 'hidden' })
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
                processo = get_object_or_404(ProcessoTitular, pk=processo_id)
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
            else:
                arquivo = None

            ret_json = {
                'success': success,
                'filename': new_filename,
                'arquivo_pk': arquivo and arquivo.id or 0,
                'arquivo_pk_crypto': arquivo and arquivo.encrypted_pk or 0,
                'tamanho': content_length,
            }

            return HttpResponse(json.dumps(ret_json, cls=DjangoJSONEncoder), content_type='text/html; charset=utf-8')
        else:
            response = HttpResponseNotAllowed(['POST'])
            response.write('ERROR: Only POST allowed')
            return response


file_uploaded = Signal()  # providing_args=['backend', 'request']
professor_titular_upload = login_required()(FileUploader())
professor_titular_upload_documentos_exigidos = login_required()(FileUploaderDocumentosExigidos())


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def requerimento_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    if processo.status == ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def formulario_pontuacao_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)

    if not processo.get_data_referencia_retroativa():
        raise Exception('Não existe data de referencia para este processo.')
    ano_data_retroatividade = processo.get_data_referencia_retroativa().year
    pontuacoes = PontuacaoMinima.objects.filter(ano=ano_data_retroatividade)

    arquivos_grupo_A = processo.arquivo_set.filter(criterio__indicador__grupo__nome='A')
    subtotal_global_A = 0
    pontuacao_a = pontuacoes.filter(grupo__nome='A')[0]
    for arquivo_grupo_A in arquivos_grupo_A:
        subtotal_global_A += arquivo_grupo_A.nota_pretendida
    teto_a = pontuacao_a.pontuacao_exigida * pontuacao_a.grupo.percentual / 100
    subtotal_com_teto_A = min(subtotal_global_A, teto_a)

    arquivos_grupo_B = processo.arquivo_set.filter(criterio__indicador__grupo__nome='B')
    subtotal_global_B = 0
    pontuacao_b = pontuacoes.filter(grupo__nome='B')[0]
    for arquivo_grupo_B in arquivos_grupo_B:
        subtotal_global_B += arquivo_grupo_B.nota_pretendida
    teto_b = pontuacao_b.pontuacao_exigida * pontuacao_b.grupo.percentual / 100
    subtotal_com_teto_B = min(subtotal_global_B, teto_b)

    arquivos_grupo_C = processo.arquivo_set.filter(criterio__indicador__grupo__nome='C')
    subtotal_global_C = 0
    pontuacao_c = pontuacoes.filter(grupo__nome='C')[0]
    for arquivo_grupo_C in arquivos_grupo_C:
        subtotal_global_C += arquivo_grupo_C.nota_pretendida
    teto_c = pontuacao_c.pontuacao_exigida * pontuacao_c.grupo.percentual / 100
    subtotal_com_teto_C = min(subtotal_global_C, teto_c)

    arquivos_grupo_D = processo.arquivo_set.filter(criterio__indicador__grupo__nome='D')
    subtotal_global_D = 0
    pontuacao_d = pontuacoes.filter(grupo__nome='D')[0]
    for arquivo_grupo_D in arquivos_grupo_D:
        subtotal_global_D += arquivo_grupo_D.nota_pretendida
    teto_d = pontuacao_d.pontuacao_exigida * pontuacao_d.grupo.percentual / 100
    subtotal_com_teto_D = min(subtotal_global_D, teto_d)

    arquivos_grupo_E = processo.arquivo_set.filter(criterio__indicador__grupo__nome='E')
    subtotal_global_E = 0
    pontuacao_e = pontuacoes.filter(grupo__nome='E')[0]
    for arquivo_grupo_E in arquivos_grupo_E:
        subtotal_global_E += arquivo_grupo_E.nota_pretendida
    teto_e = pontuacao_e.pontuacao_exigida * pontuacao_e.grupo.percentual / 100
    subtotal_com_teto_E = min(subtotal_global_E, teto_e)

    arquivos_grupo_F = processo.arquivo_set.filter(criterio__indicador__grupo__nome='F')
    subtotal_global_F = 0
    pontuacao_f = pontuacoes.filter(grupo__nome='F')[0]
    for arquivo_grupo_F in arquivos_grupo_F:
        subtotal_global_F += arquivo_grupo_F.nota_pretendida
    teto_f = pontuacao_f.pontuacao_exigida * pontuacao_f.grupo.percentual / 100
    subtotal_com_teto_F = min(subtotal_global_F, teto_f)

    arquivos_grupo_G = processo.arquivo_set.filter(criterio__indicador__grupo__nome='G')
    subtotal_global_G = 0
    pontuacao_g = pontuacoes.filter(grupo__nome='G')[0]
    for arquivo_grupo_G in arquivos_grupo_G:
        subtotal_global_G += arquivo_grupo_G.nota_pretendida
    teto_g = pontuacao_g.pontuacao_exigida * pontuacao_g.grupo.percentual / 100
    subtotal_com_teto_G = min(subtotal_global_G, teto_g)

    arquivos_grupo_H = processo.arquivo_set.filter(criterio__indicador__grupo__nome='H')
    subtotal_global_H = 0
    pontuacao_h = pontuacoes.filter(grupo__nome='H')[0]
    for arquivo_grupo_H in arquivos_grupo_H:
        subtotal_global_H += arquivo_grupo_H.nota_pretendida
    teto_h = pontuacao_h.pontuacao_exigida * pontuacao_h.grupo.percentual / 100
    subtotal_com_teto_H = min(subtotal_global_H, teto_h)

    return locals()


@rtr()
@login_required()
def quadro_resumo_pontuacao_requerida(request, processo_id):
    processo = ProcessoTitular.objects.filter(pk=processo_id).prefetch_related('arquivo_set').first()
    if not processo:
        raise Http404('Não foi encontrado processo de professor titular com a referida pk')
    soh_cppd_e_dono(request, processo)
    arquivos_grupo_A = processo.arquivo_set.filter(criterio__indicador__grupo__nome='A').order_by(
        'criterio__num_artigo', 'criterio__inciso', 'criterio__alinea'
    )
    arquivos_grupo_B = processo.arquivo_set.filter(criterio__indicador__grupo__nome='B').select_related('criterio')
    arquivos_grupo_C = processo.arquivo_set.filter(criterio__indicador__grupo__nome='C').select_related('criterio')
    arquivos_grupo_D = processo.arquivo_set.filter(criterio__indicador__grupo__nome='D').select_related('criterio')
    arquivos_grupo_E = processo.arquivo_set.filter(criterio__indicador__grupo__nome='E').select_related('criterio')
    arquivos_grupo_F = processo.arquivo_set.filter(criterio__indicador__grupo__nome='F').select_related('criterio')
    arquivos_grupo_G = processo.arquivo_set.filter(criterio__indicador__grupo__nome='G').select_related('criterio')
    arquivos_grupo_H = processo.arquivo_set.filter(criterio__indicador__grupo__nome='H').select_related('criterio')

    soma_A = arquivos_grupo_A.aggregate(total=Sum('nota_pretendida'))['total']
    soma_B = arquivos_grupo_B.aggregate(total=Sum('nota_pretendida'))['total']
    soma_C = arquivos_grupo_C.aggregate(total=Sum('nota_pretendida'))['total']
    soma_D = arquivos_grupo_D.aggregate(total=Sum('nota_pretendida'))['total']
    soma_E = arquivos_grupo_E.aggregate(total=Sum('nota_pretendida'))['total']
    soma_F = arquivos_grupo_F.aggregate(total=Sum('nota_pretendida'))['total']
    soma_G = arquivos_grupo_G.aggregate(total=Sum('nota_pretendida'))['total']
    soma_H = arquivos_grupo_H.aggregate(total=Sum('nota_pretendida'))['total']

    return locals()


def _resumo_avaliacoes(avaliacao):
    itens_grupoA = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='A')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_A = 0
    soma_pontuacao_validada_grupo_a_corte = 0
    teto_grupo_A = 0
    ano_tipo_protocolo = avaliacao.processo.get_ano_protocolo

    for item in itens_grupoA:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_A += item.pontuacao_validada()

    if itens_grupoA:
        teto_grupo_A = itens_grupoA[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_A >= teto_grupo_A:
            soma_pontuacao_validada_grupo_a_corte = teto_grupo_A
        else:
            soma_pontuacao_validada_grupo_a_corte = soma_pontuacao_validada_grupo_A

    itens_grupoB = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='B')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )

    soma_pontuacao_validada_grupo_B = 0
    soma_pontuacao_validada_grupo_b_corte = 0
    teto_grupo_B = 0

    for item in itens_grupoB:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_B += item.pontuacao_validada()

    if itens_grupoB:
        teto_grupo_B = itens_grupoB[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_B >= teto_grupo_B:
            soma_pontuacao_validada_grupo_b_corte = teto_grupo_B
        else:
            soma_pontuacao_validada_grupo_b_corte = soma_pontuacao_validada_grupo_B

    itens_grupoC = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='C')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_C = 0
    soma_pontuacao_validada_grupo_c_corte = 0
    teto_grupo_C = 0

    for item in itens_grupoC:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_C += item.pontuacao_validada()
    if itens_grupoC:
        teto_grupo_C = itens_grupoC[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_C >= teto_grupo_C:
            soma_pontuacao_validada_grupo_c_corte = teto_grupo_C
        else:
            soma_pontuacao_validada_grupo_c_corte = soma_pontuacao_validada_grupo_C

    itens_grupoD = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='D')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_D = 0
    soma_pontuacao_validada_grupo_d_corte = 0
    teto_grupo_D = 0

    for item in itens_grupoD:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_D += item.pontuacao_validada()
    if itens_grupoD:
        teto_grupo_D = itens_grupoD[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_D >= teto_grupo_D:
            soma_pontuacao_validada_grupo_d_corte = teto_grupo_D
        else:
            soma_pontuacao_validada_grupo_d_corte = soma_pontuacao_validada_grupo_D

    itens_grupoE = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='E')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_E = 0
    soma_pontuacao_validada_grupo_e_corte = 0
    teto_grupo_E = 0

    for item in itens_grupoE:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_E += item.pontuacao_validada()
    if itens_grupoE:
        teto_grupo_E = itens_grupoE[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_E >= teto_grupo_E:
            soma_pontuacao_validada_grupo_e_corte = teto_grupo_E
        else:
            soma_pontuacao_validada_grupo_e_corte = soma_pontuacao_validada_grupo_E

    itens_grupoF = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='F')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_F = 0
    soma_pontuacao_validada_grupo_f_corte = 0
    teto_grupo_F = 0

    for item in itens_grupoF:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_F += item.pontuacao_validada()
    if itens_grupoF:
        teto_grupo_F = itens_grupoF[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_F >= teto_grupo_F:
            soma_pontuacao_validada_grupo_f_corte = teto_grupo_F
        else:
            soma_pontuacao_validada_grupo_f_corte = soma_pontuacao_validada_grupo_F

    itens_grupoG = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='G')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_G = 0
    soma_pontuacao_validada_grupo_g_corte = 0
    teto_grupo_G = 0

    for item in itens_grupoG:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_G += item.pontuacao_validada()
    if itens_grupoG:
        teto_grupo_G = itens_grupoG[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_G >= teto_grupo_G:
            soma_pontuacao_validada_grupo_g_corte = teto_grupo_G
        else:
            soma_pontuacao_validada_grupo_g_corte = soma_pontuacao_validada_grupo_G

    itens_grupoH = (
        avaliacao.avaliacaoitem_set.filter(arquivo__criterio__indicador__grupo__nome='H')
        .order_by('arquivo__criterio__indicador__grupo__nome', 'arquivo__criterio__artigo')
        .distinct()
    )
    soma_pontuacao_validada_grupo_H = 0
    soma_pontuacao_validada_grupo_h_corte = 0
    teto_grupo_H = 0

    for item in itens_grupoH:
        if item.pontuacao_validada():
            soma_pontuacao_validada_grupo_H += item.pontuacao_validada()
    if itens_grupoH:
        teto_grupo_H = itens_grupoH[0].arquivo.criterio.indicador.grupo.get_teto(ano_tipo_protocolo)
        if soma_pontuacao_validada_grupo_H >= teto_grupo_H:
            soma_pontuacao_validada_grupo_h_corte = teto_grupo_H
        else:
            soma_pontuacao_validada_grupo_h_corte = soma_pontuacao_validada_grupo_H

    avaliacao.itens = list(chain(itens_grupoA, itens_grupoB, itens_grupoC, itens_grupoD, itens_grupoE, itens_grupoF, itens_grupoG, itens_grupoH))

    avaliacao.subtotal_grupo_a = soma_pontuacao_validada_grupo_A
    avaliacao.subtotal_grupo_b = soma_pontuacao_validada_grupo_B
    avaliacao.subtotal_grupo_c = soma_pontuacao_validada_grupo_C
    avaliacao.subtotal_grupo_d = soma_pontuacao_validada_grupo_D
    avaliacao.subtotal_grupo_e = soma_pontuacao_validada_grupo_E
    avaliacao.subtotal_grupo_f = soma_pontuacao_validada_grupo_F
    avaliacao.subtotal_grupo_g = soma_pontuacao_validada_grupo_G
    avaliacao.subtotal_grupo_h = soma_pontuacao_validada_grupo_H

    avaliacao.subtotal_grupo_a_corte = soma_pontuacao_validada_grupo_a_corte
    avaliacao.subtotal_grupo_b_corte = soma_pontuacao_validada_grupo_b_corte
    avaliacao.subtotal_grupo_c_corte = soma_pontuacao_validada_grupo_c_corte
    avaliacao.subtotal_grupo_d_corte = soma_pontuacao_validada_grupo_d_corte
    avaliacao.subtotal_grupo_e_corte = soma_pontuacao_validada_grupo_e_corte
    avaliacao.subtotal_grupo_f_corte = soma_pontuacao_validada_grupo_f_corte
    avaliacao.subtotal_grupo_g_corte = soma_pontuacao_validada_grupo_g_corte
    avaliacao.subtotal_grupo_h_corte = soma_pontuacao_validada_grupo_h_corte

    avaliacoes = [avaliacao]

    return {'avaliacoes': avaliacoes}


@rtr()
@login_required()
def relatorio_descritivo(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_dono_avaliador(request, processo)

    # arquivos do processo com descricao
    arquivos = processo.arquivo_set.exclude(descricao='').distinct().select_related('criterio')

    # arquivos e criterios por categoria
    def arquivos_criterios_por_categoria(arquivos, categoria):
        arquivos = arquivos.filter(criterio__categoria_memorial_descritivo__indice=categoria)
        criterios = []
        for arquivo in arquivos:
            if arquivo.criterio not in criterios:
                criterios.append(arquivo.criterio)
        return [arquivos, criterios]

    arquivos_atividade_ensino_orientacao, criterios_atividade_ensino_orientacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_ENSINO_PESQUISA_ORIENTACAO
    )
    arquivos_atividade_pesquisa_dev_tec_inovacao, criterios_atividade_pesquisa_dev_tec_inovacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_PESQUISA_DEV_TEC_INOVACAO
    )
    arquivos_atividade_extensao, criterios_atividade_extensao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_EXTENSAO
    )
    arquivos_participacao_processo_avaliacao, criterios_participacao_processo_avaliacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_PROCESSO_AVALIACAO
    )
    arquivos_participacao_revista_cientifica, criterios_participacao_revista_cientifica = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_REVISTA_CIENTIFICA
    )
    (
        arquivos_participacao_membro_comissao_carater_pedagogico,
        criterios_participacao_membro_comissao_carater_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_CARATER_PEDAGOGICO)
    (
        arquivos_participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico,
        criterios_participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_ELABORACAO_OU_REVISAO_PROJETO_PEDAGOGICO)
    arquivos_participacao_organizacao_eventos, criterios_participacao_organizacao_eventos = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_ORGANIZACAO_EVENTOS
    )
    (
        arquivos_participacao_membro_comissao_carater_nao_pedagogico,
        criterios_participacao_membro_comissao_carater_nao_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_CARATER_NAO_PEDAGOGICO)
    arquivos_exercicio_cargo_direcao_coordenacao, criterios_exercicio_cargo_direcao_coordenacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.EXERCICIO_CARGO_DIRECAO_COORDENACAO
    )
    arquivos_atividade_aperfeicoamento, criterios_atividade_aperfeicoamento = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_APERFEICOAMENTO
    )
    arquivos_atividade_representacao, criterios_atividade_representacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_REPRESENTACAO
    )

    introducao_relatorio_descritivo = processo.introducao_relatorio_descritivo
    conclusao_relatorio_descritivo = processo.conclusao_relatorio_descritivo

    processo_form = ProcessoTitularForm(
        processo=processo,
        data={
            'introducao_relatorio_descritivo': processo.introducao_relatorio_descritivo,
            'conclusao_relatorio_descritivo': processo.conclusao_relatorio_descritivo,
            'data_concessao_titulacao_doutor': processo.data_concessao_titulacao_doutor,
            'data_progressaoD404': processo.data_progressaoD404,
            'data_avaliacao_desempenho': processo.data_avaliacao_desempenho,
            'data_graduacao_EBTT': processo.data_graduacao_EBTT,
        },
    )

    return locals()


@documento(enumerar_paginas=True)
@rtr()
@login_required()
def relatorio_descritivo_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    # if processo.status == ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD:
    #     raise PermissionDenied

    uo = get_uo(request.user)

    arquivos = processo.arquivo_set.exclude(descricao='').order_by('data_referencia').distinct().select_related('criterio')

    def arquivos_criterios_por_categoria(arquivos, categoria):
        arquivos = arquivos.filter(criterio__categoria_memorial_descritivo__indice=categoria)
        criterios = []
        for arquivo in arquivos:
            if arquivo.criterio not in criterios:
                criterios.append(arquivo.criterio)
        return [arquivos, criterios]

    arquivos_atividade_ensino_orientacao, criterios_atividade_ensino_orientacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_ENSINO_PESQUISA_ORIENTACAO
    )
    arquivos_atividade_pesquisa_dev_tec_inovacao, criterios_atividade_pesquisa_dev_tec_inovacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_PESQUISA_DEV_TEC_INOVACAO
    )
    arquivos_atividade_extensao, criterios_atividade_extensao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_EXTENSAO
    )
    arquivos_participacao_processo_avaliacao, criterios_participacao_processo_avaliacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_PROCESSO_AVALIACAO
    )
    arquivos_participacao_revista_cientifica, criterios_participacao_revista_cientifica = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_REVISTA_CIENTIFICA
    )
    (
        arquivos_participacao_membro_comissao_carater_pedagogico,
        criterios_participacao_membro_comissao_carater_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_CARATER_PEDAGOGICO)
    (
        arquivos_participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico,
        criterios_participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_ELABORACAO_OU_REVISAO_PROJETO_PEDAGOGICO)
    arquivos_participacao_organizacao_eventos, criterios_participacao_organizacao_eventos = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_ORGANIZACAO_EVENTOS
    )
    (
        arquivos_participacao_membro_comissao_carater_nao_pedagogico,
        criterios_participacao_membro_comissao_carater_nao_pedagogico,
    ) = arquivos_criterios_por_categoria(arquivos, CategoriaMemorialDescritivo.PARTICIPACAO_MEMBRO_COMISSAO_CARATER_NAO_PEDAGOGICO)
    arquivos_exercicio_cargo_direcao_coordenacao, criterios_exercicio_cargo_direcao_coordenacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.EXERCICIO_CARGO_DIRECAO_COORDENACAO
    )
    arquivos_atividade_aperfeicoamento, criterios_atividade_aperfeicoamento = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_APERFEICOAMENTO
    )
    arquivos_atividade_representacao, criterios_atividade_representacao = arquivos_criterios_por_categoria(
        arquivos, CategoriaMemorialDescritivo.ATIVIDADE_REPRESENTACAO
    )

    arquivos_atividade_ensino_orientacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=1)
    arquivos_atividade_pesquisa_dev_tec_inovacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=2)
    arquivos_atividade_extensao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=3)
    arquivos_participacao_processo_avaliacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=4)
    arquivos_participacao_revista_cientifica = arquivos.filter(criterio__categoria_memorial_descritivo__pk=5)
    arquivos_participacao_membro_comissao_carater_pedagogico = arquivos.filter(criterio__categoria_memorial_descritivo__pk=6)
    arquivos_participacao_membro_comissao_elaboracao_ou_revisao_projeto_pedagogico = arquivos.filter(criterio__categoria_memorial_descritivo__pk=7)
    arquivos_participacao_organizacao_eventos = arquivos.filter(criterio__categoria_memorial_descritivo__pk=8)
    arquivos_participacao_membro_comissao_carater_nao_pedagogico = arquivos.filter(criterio__categoria_memorial_descritivo__pk=9)
    arquivos_exercicio_cargo_direcao_coordenacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=10)
    arquivos_atividade_aperfeicoamento = arquivos.filter(criterio__categoria_memorial_descritivo__pk=11)
    arquivos_atividade_representacao = arquivos.filter(criterio__categoria_memorial_descritivo__pk=12)

    hoje = datetime.date.today()

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def documentos_anexados_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    if processo.status == ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD:
        raise PermissionDenied

    arquivos_grupo_A = processo.arquivo_set.filter(criterio__indicador__grupo__nome='A')
    arquivos_grupo_B = processo.arquivo_set.filter(criterio__indicador__grupo__nome='B')
    arquivos_grupo_C = processo.arquivo_set.filter(criterio__indicador__grupo__nome='C')
    arquivos_grupo_D = processo.arquivo_set.filter(criterio__indicador__grupo__nome='D')
    arquivos_grupo_E = processo.arquivo_set.filter(criterio__indicador__grupo__nome='E')
    arquivos_grupo_F = processo.arquivo_set.filter(criterio__indicador__grupo__nome='F')
    arquivos_grupo_G = processo.arquivo_set.filter(criterio__indicador__grupo__nome='G')
    arquivos_grupo_H = processo.arquivo_set.filter(criterio__indicador__grupo__nome='H')
    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def encaminhamento_banca_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    soh_cppd_e_dono(request, processo)

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
    data_extenso = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")} ({Configuracao.get_valor_por_chave("comum", "instituicao_estado")}), {hoje.day} de {lower(meses.get(hoje.month))} de {hoje.year}.'

    # selecionando avaliadores
    avaliadores_resumo = []
    processo_avaliadores = ProcessoAvaliador.objects.filter(processo=processo, status=ProcessoAvaliador.AVALIACAO_FINALIZADA).order_by(
        'avaliador__vinculo__pessoa__nome'
    )
    for processo_avaliador in processo_avaliadores:
        if processo_avaliador.avaliador_principal():
            avaliador = processo_avaliador.avaliador
            avaliador.nome = processo_avaliador.avaliador.vinculo.pessoa.nome
            if avaliador.eh_interno():
                avaliador.matricula = processo_avaliador.avaliador.eh_interno().matricula
            else:
                avaliador.matricula = processo_avaliador.avaliador.matricula_siape

            avaliadores_resumo.append(avaliador)

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
def imprimir_documentos_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    soh_cppd_e_dono(request, processo)
    ultima_validacao = processo.ultima_validacao_processo()
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    soma = 0
    soma_qtd_itens = 0
    soma_media_final_validada = 0

    setor_encaminhamento = f'DG/{processo.servidor.setor_exercicio.uo.sigla}'
    sigla_reitoria = get_sigla_reitoria()
    if processo.servidor.setor_exercicio.uo.sigla == sigla_reitoria:
        setor_encaminhamento = f'GABIN/{processo.servidor.setor_exercicio.uo.sigla}'

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
    data_extenso = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")} ({Configuracao.get_valor_por_chave("comum", "instituicao_estado")}), {hoje.day} de {lower(meses.get(hoje.month))} de {hoje.year}.'

    """
    DEFERIMENTO OU INDEFERIMENTO
    """
    estado_atual_processo = 'Indeferido'
    status_processo_despacho = 'INDEFERIMENTO'
    texto_encaminhamento_despacho_cppd = '.'
    texto_encaminhamento_despacho_reitor = 'para arquivamento.'

    if processo.estado_atual_processo() == 0:
        estado_atual_processo = 'Deferido'
        status_processo_despacho = 'DEFERIMENTO'
        texto_encaminhamento_despacho_cppd = (
            ' para emissão de portaria de concessão de promoção do docente à classe Titular da Carreira de Magisterio do EBTT.'
        )
        texto_encaminhamento_despacho_reitor = 'para emissão de Portaria e demais encaminhamentos.'

    data_progressaoD404 = processo.data_progressaoD404
    if ultima_validacao and ultima_validacao.data_progressao_validada and ultima_validacao.data_progressao_validada != data_progressaoD404:
        if data_progressaoD404:
            data_progressaoD404 = data_progressaoD404.strftime('%d/%m/%Y')
        else:
            data_progressaoD404 = '-'

        data_progressaoD404 = '{} <br />(Validada pela CPPD: {})'.format(
            data_progressaoD404, ultima_validacao.data_progressao_validada.strftime('%d/%m/%Y')
        )

    data_titulacao = processo.data_concessao_titulacao_doutor
    if (
        ultima_validacao
        and ultima_validacao.data_conclusao_titulacao_validada
        and ultima_validacao.data_conclusao_titulacao_validada != data_titulacao
    ):
        if data_titulacao:
            data_titulacao = data_titulacao.strftime('%d/%m/%Y')
        else:
            data_titulacao = '-'

        data_titulacao = '{} <br />(Validada pela CPPD: {})'.format(
            data_titulacao, ultima_validacao.data_conclusao_titulacao_validada.strftime('%d/%m/%Y')
        )

    data_avaliacao_desempenho = processo.data_avaliacao_desempenho
    if (
        ultima_validacao
        and ultima_validacao.data_avaliacao_desempenho_validada
        and ultima_validacao.data_avaliacao_desempenho_validada != data_avaliacao_desempenho
    ):
        if data_avaliacao_desempenho:
            data_avaliacao_desempenho = data_avaliacao_desempenho.strftime('%d/%m/%Y')
        else:
            data_avaliacao_desempenho = '-'

        data_avaliacao_desempenho = '{} <br />(Validada pela CPPD: {})'.format(
            data_avaliacao_desempenho, ultima_validacao.data_avaliacao_desempenho_validada.strftime('%d/%m/%Y')
        )

    avaliacoes = Avaliacao.objects.filter(processo=processo, status=Avaliacao.FINALIZADA).order_by('avaliador__vinculo__pessoa__nome')

    # texto do despacho que vai para o reitor
    texto_final_despacho_reitor = f'Com base nos pareceres emitidos pelos avaliadores, a pontuação final do memorial descritivo foi de <strong>{format_money(processo.pontuacao_media_final())}</strong> e o resultado final do processo foi de <strong>{status_processo_despacho}</strong>'
    if processo.estado_atual_processo() == 0:  # se o processo for deferido
        texto_final_despacho_reitor += ', com efeitos a partir da publicação da portaria'
    texto_final_despacho_reitor += '.'

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

        pontuacao_validada = processo.get_pontuacao_avaliacao(avaliacao)
        if processo_avaliador.avaliador_principal():
            avaliador = processo_avaliador.avaliador
            avaliador.nome = avaliador.vinculo.relacionamento.pessoa_fisica.nome
            if avaliador.eh_interno():
                avaliador.matricula = avaliador.eh_interno().matricula
            else:
                avaliador.matricula = avaliador.matricula_siape

            avaliador.pontuacao_validada = pontuacao_validada
            avaliador.avaliacao_status = avaliacao_status
            avaliador.avaliacao_quadro_resumo = avaliacao_quadro_resumo
            avaliadores_resumo.append(avaliador)

    return locals()


@csrf_exempt
@rtr()
@login_required()
@transaction.atomic
def clonar_processo_titular(request, processo_id):
    sub_instance = request.user.get_relacionamento()
    if not sub_instance.eh_docente:
        raise PermissionDenied('Você não tem permissão para acessar esta página.')

    processo_titular = get_object_or_404(ProcessoTitular, pk=processo_id)
    novo_processo = ProcessoTitular()
    novo_processo.clonado = True
    novo_processo.servidor = processo_titular.servidor
    novo_processo.status = ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD
    #   Não se pode usar o ano do processo anterior porque teria que ter um critério para avaliar se o ano realmente pode ser
    #   o do processo anterior
    novo_processo.ano = datetime.date.today().year
    #   Salvando Processo novo
    novo_processo.save()
    #   Recuperando informações do processo antigo
    #   Datas documentos preliminares
    novo_processo.data_concessao_titulacao_doutor = processo_titular.data_concessao_titulacao_doutor
    novo_processo.data_progressaoD404 = processo_titular.data_progressaoD404
    novo_processo.data_avaliacao_desempenho = processo_titular.data_avaliacao_desempenho
    novo_processo.data_graduacao_EBTT = processo_titular.data_graduacao_EBTT

    #   Documentos Preliminares
    for arquivo_exigido in processo_titular.arquivosexigidos_set.all():
        arquivo_novo = ArquivosExigidos()
        arquivo_novo.processo = novo_processo
        arquivo_novo.nome = arquivo_exigido.nome
        filename = str(uuid.uuid4()) + (os.path.splitext(arquivo_novo.nome)[1] or '')
        diretorio = os.path.join(get_upload_directory(novo_processo.servidor), filename)
        arquivo_novo.diretorio = diretorio
        arquivo_novo.tipo = arquivo_exigido.tipo
        arquivo_novo.tamanho = arquivo_exigido.tamanho
        try:
            copy_file(arquivo_exigido.diretorio, arquivo_novo.diretorio)
            arquivo_novo.save()
        except FileNotFoundError:
            CloneArquivoErro.objects.get_or_create(
                tipo_arquivo=CloneArquivoErro.ARQUIVO_EXIGIDO,
                tipo_documento_exigido=arquivo_novo.get_tipo_display(),
                nome_arquivo=arquivo_exigido.nome,
                processo_titular=novo_processo,
            )

    # Documentos Diretrizes e Criterios
    for arquivo in processo_titular.arquivo_set.all():
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
            copy_file(arquivo.diretorio, arquivo_diretriz.diretorio)
            arquivo_diretriz.save()
        except FileNotFoundError:
            CloneArquivoErro.objects.get_or_create(
                tipo_arquivo=CloneArquivoErro.ARQUIVO,
                indicador=arquivo_diretriz.criterio.indicador,
                criterio=arquivo_diretriz.criterio,
                nome_arquivo=arquivo_diretriz.nome,
                processo_titular=novo_processo,
            )

    novo_processo.pontuacao_pretendida = processo_titular.pontuacao_pretendida
    novo_processo.pontuacao_pretendida_grupo_A = processo_titular.pontuacao_pretendida_grupo_A
    novo_processo.pontuacao_pretendida_grupo_B = processo_titular.pontuacao_pretendida_grupo_B
    novo_processo.pontuacao_pretendida_grupo_C = processo_titular.pontuacao_pretendida_grupo_C
    novo_processo.pontuacao_pretendida_grupo_D = processo_titular.pontuacao_pretendida_grupo_D
    novo_processo.pontuacao_pretendida_grupo_E = processo_titular.pontuacao_pretendida_grupo_E
    novo_processo.pontuacao_pretendida_grupo_F = processo_titular.pontuacao_pretendida_grupo_F
    novo_processo.pontuacao_pretendida_grupo_G = processo_titular.pontuacao_pretendida_grupo_G
    novo_processo.pontuacao_pretendida_grupo_H = processo_titular.pontuacao_pretendida_grupo_H

    #   Introdução e Conclusão Memorial descritivo
    novo_processo.introducao_relatorio_descritivo = processo_titular.introducao_relatorio_descritivo
    novo_processo.conclusao_relatorio_descritivo = processo_titular.conclusao_relatorio_descritivo
    novo_processo.itinerario_formacao = processo_titular.itinerario_formacao

    novo_processo.itinerario_formacao_aperfeicoamento_titulacao = processo_titular.itinerario_formacao_aperfeicoamento_titulacao
    novo_processo.atividade_ensino_orientacao = processo_titular.atividade_ensino_orientacao
    novo_processo.atividade_pesquisa_dev_tec_inovacao = processo_titular.atividade_pesquisa_dev_tec_inovacao
    novo_processo.atividade_extensao = processo_titular.atividade_extensao
    novo_processo.participacao_processo_avaliacao = processo_titular.participacao_processo_avaliacao
    novo_processo.revista_cientifica = processo_titular.revista_cientifica
    novo_processo.membro_comissao_carater_pedagogico = processo_titular.membro_comissao_carater_pedagogico
    novo_processo.membro_comissao_elaboracao_ou_revisao_projeto_pedagogico = processo_titular.membro_comissao_elaboracao_ou_revisao_projeto_pedagogico
    novo_processo.organizacao_eventos = processo_titular.organizacao_eventos
    novo_processo.membro_comissao_carater_nao_pedagogico = processo_titular.membro_comissao_carater_nao_pedagogico
    novo_processo.exercicio_cargo_direcao_coordenacao = processo_titular.exercicio_cargo_direcao_coordenacao
    novo_processo.atividade_aperfeicoamento = processo_titular.atividade_aperfeicoamento
    novo_processo.atividade_representacao = processo_titular.atividade_representacao

    #   Isso aqui é do RSC????
    novo_processo.atuacao_docente = processo_titular.atuacao_docente
    novo_processo.producao_cademica = processo_titular.producao_cademica
    novo_processo.prestacao_servicos = processo_titular.prestacao_servicos
    novo_processo.atividade_adm = processo_titular.atividade_adm
    novo_processo.titulos_homenagens = processo_titular.titulos_homenagens

    novo_processo.save()

    _recalcular_ponto(novo_processo)

    return httprr(f'/professor_titular/abrir_processo_titular/{novo_processo.pk}/', 'Processo titular clonado com sucesso.')


@rtr()
@login_required()
@permission_required('professor_titular.pode_validar_processotitular')
def selecionar_avaliadores(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    title = f'Selecionar avaliadores {processo}'

    form = AvaliadorForm(request.POST or None, processo=processo)
    if request.POST and form.is_valid():
        try:
            form.processar(request.user.get_vinculo())
        except ValidationError as e:
            return httprr('.', f'Erro ao selecionar avaliadores: {e}', tag='error', close_popup=False, close_popup_and_force_reload=False)
        return httprr('..', 'Avaliadores selecionados com sucesso.')

    return locals()


def _avaliacoes_por_avaliador(processo):
    """Indexa as avaliações do processo por avaliador, de forma determinística.

    O unique_together de `Avaliacao` garante uma avaliação por avaliador. O `order_by` com
    `setdefault` mantém a escolha estável mesmo diante de dados legados: antes, o dicionário
    era montado sobre uma queryset sem ordenação e ficava com a última linha que o banco
    devolvesse, o que fazia a tela alternar entre a avaliação real e uma duplicata vazia.

    Args:
        processo: processo cujas avaliações serão indexadas.
    Returns:
        Mapa de `avaliador_id` para a respectiva `Avaliacao`.
    """
    avaliacoes = {}
    for avaliacao in Avaliacao.objects.filter(processo=processo).select_related('avaliador').order_by('id'):
        avaliacoes.setdefault(avaliacao.avaliador_id, avaliacao)
    return avaliacoes


@rtr()
@login_required()
def acompanhar_avaliacao(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    title = f'Acompanhamento do {processo}'

    pontuacao_media_final = processo.pontuacao_media_final()
    avaliadores_selecionados = []
    eh_dono_processo = eh_dono(request, processo)

    # Evita chamadas repetidas ao método de estado
    estado_atual = processo.estado_atual_processo(pontuacao_media_final=pontuacao_media_final)
    estado_processo = ProcessoTitular.STATUS_CHOICES[estado_atual][1]
    estado_processo_class_css = 'alert'
    if estado_atual == 0:
        estado_processo_class_css = 'success'
    elif estado_atual == 1:
        estado_processo_class_css = 'danger'

    """
    verificando avaliadores internos
    """
    # Reduz N+1: carrega relacionamentos necessários de uma vez
    processo_avaliadores = ProcessoAvaliador.objects.filter(processo=processo).select_related('avaliador', 'vinculo_responsavel_cadastro')

    avaliacoes_by_avaliador = _avaliacoes_por_avaliador(processo)
    avaliadores_internos_reserva = []
    avaliadores_internos_excluidos = []
    avaliadores_externos_reserva = []
    avaliadores_externos_excluidos = []
    for processo_avaliador in processo_avaliadores:
        avaliacao = avaliacoes_by_avaliador.get(processo_avaliador.avaliador_id)
        avaliacao_status = f'<strong>{avaliacao.get_status_display()}</strong>' if avaliacao else None

        # Calcula pontuação validada considerando a avaliação específica (quando houver)
        pontuacao_validada = processo.get_pontuacao_avaliacao(avaliacao)

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
                avaliador_interno_selecionado.situacao = processo_avaliador.situacao_avaliador()
                avaliador_interno_selecionado.data_limite = processo_avaliador.data_limite_display()
                avaliador_interno_selecionado.avaliacao_status = avaliacao_status
                avaliador_interno_selecionado.vinculo_responsavel_cadastro = processo_avaliador.vinculo_responsavel_cadastro
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
                avaliador_externo_selecionado.situacao = processo_avaliador.situacao_avaliador()
                avaliador_externo_selecionado.data_limite = processo_avaliador.data_limite_display()
                avaliador_externo_selecionado.avaliacao_status = avaliacao_status
                avaliador_externo_selecionado.vinculo_responsavel_cadastro = processo_avaliador.vinculo_responsavel_cadastro
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
        processo__status__in=[ProcessoTitular.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoTitular.STATUS_EM_AVALIACAO],
    )

    """
    processos em avaliação
    """
    processos_em_avaliacao = ProcessoAvaliador.objects.filter(
        status=ProcessoAvaliador.EM_AVALIACAO, avaliador__vinculo=vinculo, processo__status=ProcessoTitular.STATUS_EM_AVALIACAO
    )

    """
    avaliações concluídas
    """
    avaliacoes_concluidas = ProcessoAvaliador.objects.filter(status=ProcessoAvaliador.AVALIACAO_FINALIZADA, avaliador__vinculo=vinculo)

    return locals()


@rtr()
@login_required()
def recusar_avaliacao(request, processo_avaliacao_id):
    processo_avaliacao = get_object_or_404(ProcessoAvaliador, pk=processo_avaliacao_id)
    title = 'Motivo da Recusa'
    form = RecusaAvaliacaoForm(request.POST or None, processo_avaliador=processo_avaliacao)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Processo recusado com sucesso.')
    return locals()


@rtr()
@login_required()
@permission_required('professor_titular.pode_validar_processotitular')
def rejeitar_processo_cppd(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
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
def termo_aceite(request, processo_avaliacao_id):
    processo_avaliacao = get_object_or_404(ProcessoAvaliador, pk=processo_avaliacao_id)
    title = 'Termo de Confidencialidade e Sigilo'

    return locals()


@rtr()
@login_required()
def aceitar_rejeitar_processo(request, processo_id):
    processo_avaliador = get_object_or_404(ProcessoAvaliador, pk=processo_id)
    if processo_avaliador.processo.status not in [ProcessoTitular.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoTitular.STATUS_EM_AVALIACAO]:
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
        return httprr('/professor_titular/processo_avaliacao/', msg)


@rtr()
@login_required()
def avaliar_processo(request, processo_id, avaliador_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    avaliador = get_object_or_404(Avaliador, pk=avaliador_id)

    processo_avaliador = ProcessoAvaliador.objects.filter(
        avaliador=avaliador, processo=processo, status__in=[ProcessoAvaliador.EM_AVALIACAO, ProcessoAvaliador.AVALIACAO_FINALIZADA]
    )

    # verificando permissões de acesso
    soh_cppd_dono_avaliador(request, processo)

    title = f'Avaliar Processo {processo}'

    # Recupera (ou cria) a avaliação do avaliador. O consultar-para-depois-criar anterior
    # abria uma janela de corrida: dois cliques simultâneos criavam duas avaliações.
    avaliacao = processo.criar_avaliacao(avaliador)
    pontuacao_validada_com_corte = processo.get_pontuacao_avaliacao(avaliacao)

    if not (processo.status == ProcessoTitular.STATUS_EM_AVALIACAO or avaliacao.status == Avaliacao.FINALIZADA):
        raise PermissionDenied('Processo não pode ser avaliado.')

    """
    Selecionando os arquivos para a avaliação
    """
    arquivos = (
        avaliacao.avaliacaoitem_set.all()
        .order_by(
            'arquivo__criterio__indicador__grupo__nome',
            'arquivo__criterio__indicador',
            'arquivo__criterio__artigo',
            'arquivo__criterio__inciso',
            'arquivo__criterio__alinea',
        )
        .distinct()
    )

    #
    # selecionando configurações
    config = ConfiguracaoTitular.objects.first()
    if not config:
        raise Http404('Não existe configuração para o processo de professor titular.')

    return locals()


@rtr()
@login_required()
@permission_required('professor_titular.pode_avaliar_processotitular')
def avaliar_item(request, avaliacao_item_id, item_anterior_id=None):
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=avaliacao_item_id)
    title = f'{avaliacao_item.arquivo.criterio.indicador.nome} - {avaliacao_item.arquivo.criterio.indicador.descricao}'
    criterio = avaliacao_item.arquivo.criterio

    url_avaliacao_item = (
        f'/professor_titular/avaliar_processo/{avaliacao_item.avaliacao.processo.id}/{avaliacao_item.avaliacao.avaliador.id}/?tab=avaliacao'
    )
    processo = avaliacao_item.avaliacao.processo

    bc = [
        ['Início', '/'],
        ['Processos para Avaliação', '/professor_titular/processo_avaliacao/'],
        [
            f'Avaliar Processo Processo Titular - {processo.servidor.pessoa_fisica.nome} ({processo.servidor.matricula})',
            url_avaliacao_item,
        ],
    ]
    request.session['bc'] = bc

    return locals()


@rtr()
@login_required()
def salvar_avaliacao(request, avaliacao_item_id):
    processamento_item = salvar_item_avaliacao(request, avaliacao_item_id)
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=avaliacao_item_id)
    processo = avaliacao_item.avaliacao.processo
    avaliador = avaliacao_item.avaliacao.avaliador
    if is_ajax(request):
        return JsonResponse(
            {'ok': processamento_item.get('ok'), 'msg': processamento_item.get('msg'), 'justificar': processamento_item.get('justificar')}
        )
    else:
        url = f'/professor_titular/avaliar_processo/{processo.id}/{avaliador.id}/?tab=avaliacao'
        return httprr(url, processamento_item.get('msg'))


@rtr()
@login_required()
def salvar_avancar_proximo(request, avaliacao_item_id):
    processamento_item = salvar_item_avaliacao(request, avaliacao_item_id)
    url = avancar_proximo_item(avaliacao_item_id)
    return httprr(url, processamento_item.get('msg'))


@rtr()
@login_required()
def pular_item(request, avaliacao_item_id):
    url = avancar_proximo_item(avaliacao_item_id)
    return httprr(url)


def avancar_proximo_item(avaliacao_item_id):
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=avaliacao_item_id)

    itens = (
        avaliacao_item.avaliacao.avaliacaoitem_set.all()
        .order_by(
            'arquivo__criterio__indicador__grupo__nome',
            'arquivo__criterio__indicador',
            'arquivo__criterio__artigo',
            'arquivo__criterio__inciso',
            'arquivo__criterio__alinea',
        )
        .distinct()
    )

    itens_nao_avaliados = itens.filter(data_referencia__isnull=True).exclude(qtd_itens_validado=0)

    if itens_nao_avaliados.exists():
        # assume que o próximo item será o primeiro item não avaliado
        proximo_item = itens_nao_avaliados[0]
        passou_item = False
        # verificando se existe mais de um item não avaliado, caso negativo, iremos redirecionar para o único existente
        if itens_nao_avaliados.count() > 1:
            # aqui precisamos percorrer todos os itens, inclusive os já avaliados
            for item in itens:
                # ao percorrer os item, iremos verificar se ja passamos pelo avaliado e se estamos em um item não
                # avaliado (o próximo a ser avaliado)
                if passou_item and item.justificativa is None and item.data_referencia is None:
                    proximo_item = item
                    break
                # setando uma flag para sabermos se já passamos pelo item avaliado
                if item.id == avaliacao_item.id:
                    passou_item = True
        url = f'/professor_titular/avaliar_item/{proximo_item.id}/'
    else:
        processo = avaliacao_item.avaliacao.processo
        avaliador = avaliacao_item.avaliacao.avaliador
        url = f'/professor_titular/avaliar_processo/{processo.id}/{avaliador.id}/?tab=avaliacao'

    return url


def salvar_item_avaliacao(request, avaliacao_item_id):
    try:
        justificar = False

        # selecionando o item da avaliação
        item_avaliacao = AvaliacaoItem.objects.get(id=avaliacao_item_id)

        data_referencia = request.POST.get(f'data_referencia_validada_{avaliacao_item_id}')
        try:
            if data_referencia:
                item_avaliacao.data_referencia = strptime_or_default(data_referencia, '%d/%m/%Y').date()
            else:
                item_avaliacao.data_referencia = None
        except AttributeError:
            item_avaliacao.data_referencia = None

        qtd_itens_validado = request.POST.get(f'qtd_itens_validado_{avaliacao_item_id}')
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
        justificativa = justificativa.strip()
        if item_avaliacao.houve_alteracao_avaliacao() and not justificativa:
            justificar = True
            raise Exception('Sua avaliação alterou a data de referência ou a quantidade de pontos. É necessário justificar suas modificações.')

        if justificativa:
            item_avaliacao.justificativa = justificativa
        else:
            item_avaliacao.justificativa = None

        item_avaliacao.save()
        msg = 'Item da avaliação salvo com sucesso.'
        return {'ok': True, 'msg': msg, 'justificar': justificar}
    except Exception as e:
        return {'ok': False, 'msg': e.args[0], 'justificar': justificar}


@rtr()
@login_required()
def quadro_resumo_avaliacao(request, avaliacao_id):
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    arquivos = (
        avaliacao.avaliacaoitem_set.all()
        .order_by(
            'arquivo__criterio__indicador__grupo__nome',
            'arquivo__criterio__indicador',
            'arquivo__criterio__artigo',
            'arquivo__criterio__inciso',
            'arquivo__criterio__alinea',
        )
        .distinct()
    )

    return locals()


@rtr()
@login_required()
def finalizar_avaliacao(request, avaliacao_id):
    try:
        avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
        if not (avaliacao.status == Avaliacao.EM_AVALIACAO):
            raise Exception('Não é permitido finalizar uma avaliação que não esteja na situação "EM AVALIAÇÃO".')

        avaliacao.finalizar_avaliacao_titular()

        return JsonResponse({'ok': True, 'msg': 'Avaliação finalizada com sucesso.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
@login_required()
def ciencia_resultado(request, processo_id):
    try:
        processo = get_object_or_404(ProcessoTitular, pk=processo_id)
        if processo.status in [ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO]:
            raise Exception('O processo já foi finalizado. A ciencia não pode ser atualizada.')
        opcao_ciencia_deferimento = request.POST.get('ciencia_deferimento')
        if opcao_ciencia_deferimento:
            processo.dar_ciencia_resultado(opcao_ciencia_deferimento)
        else:
            raise Exception('Preencha corretamente as opções de ciência da avaliação.')

        return JsonResponse({'ok': True, 'msg': 'Ciência registrada com sucesso.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
@login_required()
def finalizar_avaliacao_titular(request, avaliacao_id):
    try:
        avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
        if not (avaliacao.status == Avaliacao.EM_AVALIACAO):
            raise Exception('Não é permitido finalizar uma avaliação que não esteja na situação "EM AVALIAÇÃO".')

        avaliacao.finalizar_avaliacao_titular()

        return JsonResponse({'ok': True, 'msg': 'Avaliação finalizada com sucesso.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'msg': e.args[0]})


@rtr()
@login_required()
@transaction.atomic()
def finalizar_processo(request, processo_id):
    try:
        processo = get_object_or_404(ProcessoTitular, pk=processo_id)

        if 'processo_eletronico' in settings.INSTALLED_APPS:
            arquivo = gerar_processo_completo(request, processo_id)
            arq = open(f'/tmp/processo_titular_completo_{processo_id}.pdf', 'wb+')
            arq.write(arquivo.content)

            arquivo_memorial_descritivo = relatorio_descritivo_pdf(request, processo_id)
            arq_memorial_descritivo = open(f'/tmp/memorial_descritivo_{processo_id}.pdf', 'wb+')
            arq_memorial_descritivo.write(arquivo_memorial_descritivo.content)

            arquivo_formulario_pontuacao = formulario_pontuacao_pdf(request, processo_id)
            arq_formulario_pontuacao = open(f'/tmp/formulario_pontuacao_{processo_id}.pdf', 'wb+')
            arq_formulario_pontuacao.write(arquivo_formulario_pontuacao.content)

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
                    'assunto': 'Memorial descritivo para promoção à classe titular',
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

            processo_tramite = {
                'tipo_processo': TipoProcesso.objects.get(id=517),
                'assunto': 'Promoção Professor Classe Titular',
                'setor_destino': get_setor_cppd(),
            }

            processo.processo_eletronico = ProcessoEletronico.cadastrar_processo(
                user=processo.servidor.get_user(),
                processo_tramite=processo_tramite,
                papel=request.user.get_relacionamento().papeis_ativos.first(),
                documentos_texto=[],
                documentos_digitalizados=documentos_digitalizados,
            )
        else:
            # Cria protocolo
            protocolo = Processo()
            protocolo.assunto = 'Requerimento Professor Titular'
            protocolo.set_interessado(processo.servidor)
            protocolo.tipo = Processo.TIPO_REQUERIMENTO
            protocolo.save()

            tramite = Tramite()
            tramite.processo = protocolo
            tramite.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
            tramite.orgao_interno_encaminhamento = get_setor()
            tramite.orgao_interno_recebimento = get_setor_cppd()
            tramite.vinculo_encaminhamento = request.user.get_vinculo()
            tramite.data_encaminhamento = datetime.datetime.now()
            tramite.ordem = 1
            tramite.save()

            processo.protocolo = protocolo

        processo.finalizar_processo()

        return httprr('/admin/professor_titular/processotitular/?tab=tab_processos_finalizados', 'Processo finalizado com sucesso.')
    except Exception as e:
        return httprr('/admin/professor_titular/processotitular/', f'Erro ao finalizar processo: {e}', 'error')


@rtr()
@login_required()
def desistir_avaliacao(request, avaliacao_id):
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
def download_arquivos(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    try:
        filenames = []
        dict_refer_file = {}
        # adicionando na lista os arquivos exigidos (documentos preliminares)
        for arquivo_exigido in processo.arquivosexigidos_set.all():
            relative_name = arquivo_exigido.diretorio
            path_file = cache_file(relative_name)
            if not path_file:
                continue
            filenames.append(path_file)

            _fdir, fname = os.path.split(path_file)
            dict_refer_file[fname] = arquivo_exigido.nome

        # adicionando na lista os arquivos utilizados para pontuar
        for arquivo in processo.arquivo_set.all():
            relative_name = arquivo.diretorio
            path_file = cache_file(relative_name)
            if not path_file:
                continue
            filenames.append(path_file)

            _fdir, fname = os.path.split(path_file)
            dict_refer_file[fname] = arquivo.nome

        # adicona ao nome o processo
        if processo.processo_eletronico:
            tipo_protocolo = processo.processo_eletronico
        elif processo.protocolo:
            tipo_protocolo = processo.protocolo.numero_processo
        else:
            tipo_protocolo = processo.pk

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

        return resp
    except OSError as ex:
        msg = f'Ocorrreu um erro ao carregar o arquivo {dict_refer_file[fname]}'
        if ex.args[0] == 2:
            msg = f'O arquivo {dict_refer_file[fname]} não foi encontrado.'
        return httprr(request.META.get('HTTP_REFERER'), msg, 'error')


@rtr()
@login_required()
def gerar_processo_completo(request, processo_id):
    processo = get_object_or_404(ProcessoTitular, pk=processo_id)
    try:
        merger = PdfWriter()

        # adicionando na lista os arquivos exigidos (documentos preliminares)
        for arquivo_exigido in processo.arquivosexigidos_set.all():
            pdf = PdfReader(default_storage.open(arquivo_exigido.diretorio))
            merger.append(pdf)

        # adicionando na lista os arquivos utilizados para pontuar
        for arquivo in processo.arquivo_set.all():
            pdf = PdfReader(default_storage.open(arquivo.diretorio), strict=False)
            merger.append(pdf)

        s = io.BytesIO()
        merger.write(s)

        nome_arquivo = f'processo_completo_{processo.id}.pdf'

        resp = HttpResponse(s.getvalue())
        resp['Content-Disposition'] = f'attachment; filename={nome_arquivo}'

        return resp
    except Exception as ex:
        if settings.DEBUG:
            raise ex
        return httprr('..', ex, 'error')


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
            status__in=[Avaliacao.FINALIZADA],
            processo__status__in=[ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO],
        )

        if form.is_valid():
            avaliador = form.cleaned_data['avaliador']
            interessado = form.cleaned_data['interessado']
            avaliadores_pagamento_avaliacao = form.cleaned_data['avaliadores_pagamento_avaliacao']

            if avaliador:
                qs_avaliacoes = qs_avaliacoes.filter(avaliador__vinculo__pessoa__nome__icontains=avaliador)
            if interessado:
                qs_avaliacoes = qs_avaliacoes.filter(processo__servidor__pessoa_fisica__nome__icontains=interessado)
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
            status__in=[Avaliacao.FINALIZADA],
            processo__status__in=[ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO],
        )

        if form.is_valid():
            avaliador = form.cleaned_data['avaliador']
            interessado = form.cleaned_data['interessado']
            avaliadores_pagamento_avaliacao = form.cleaned_data['avaliadores_pagamento_avaliacao']

            if avaliador:
                qs_avaliacoes = qs_avaliacoes.filter(avaliador__vinculo__pessoa__nome__icontains=avaliador)
            if interessado:
                qs_avaliacoes = qs_avaliacoes.filter(processo__servidor__pessoa_fisica__nome__icontains=interessado)
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
    title = f'Avaliações para Pagamento do Avaliador {avaliador.vinculo.pessoa.nome}'

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

    avaliacoes = Avaliacao.objects.filter(avaliador=avaliador, status__in=[Avaliacao.FINALIZADA]).order_by('processo__servidor__pessoa_fisica__nome')

    return locals()


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

            """
            Lista de processos
            """
            processos = (
                ProcessoTitular.objects.filter(
                    status__in=[ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO, ProcessoTitular.STATUS_REJEITADO],
                    avaliacao__status=Avaliacao.FINALIZADA,
                    avaliacao__avaliacao_paga=avaliacoes_pagas,
                )
                .order_by('servidor__pessoa_fisica__nome')
                .distinct('servidor__pessoa_fisica__nome')
            )
            if data_inicio and data_final:
                processos = processos.filter(data_finalizacao_processo__range=(data_inicio, data_final))

            total_processos = processos.count()

            avaliacoes = []
            processos_id = []
            for processo in processos:
                processos_id.append(processo.id)
                qs_avaliacoes = processo.avaliacao_set.filter(status=Avaliacao.FINALIZADA, avaliacao_paga=avaliacoes_pagas)
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
                            processo__status__in=[
                                ProcessoTitular.STATUS_APROVADO,
                                ProcessoTitular.STATUS_REPROVADO,
                                ProcessoTitular.STATUS_REJEITADO,
                            ],
                            status=Avaliacao.FINALIZADA,
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
                        if avaliador.instituicao_origem.id in total_avaliacoes_por_instituicao:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id] += avaliador.qtde_avaliacoes
                        else:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id] = avaliador.qtde_avaliacoes

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
        processo__status__in=[ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO, ProcessoTitular.STATUS_REJEITADO],
        status=Avaliacao.FINALIZADA,
    )

    if request.GET.get('pagar'):
        avaliacoes.update(avaliacao_paga=True)
        return httprr(request.META.get('HTTP_REFERER'), 'Avaliações marcadas como pagas com sucesso.')

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
            return httprr(
                '/professor_titular/relatorio_pagamento/', 'Erro ao tentar gerar o relatório de pagamento. Preencha alguns filtros.', 'error'
            )

        if avaliacao_paga == 'on':
            avaliacao_paga = True
        else:
            avaliacao_paga = False

        processos = []
        processos_id = []
        for avaliacao in avaliacoes.order_by('processo__servidor__pessoa_fisica__nome').distinct('processo__servidor__pessoa_fisica__nome'):
            if avaliacao.processo not in processos:
                processos_id.append(avaliacao.processo.id)
                if relatorio == 'processo':
                    processos.append(avaliacao.processo)

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
                    status=Avaliacao.FINALIZADA,
                    processo__status__in=[
                        ProcessoTitular.STATUS_APROVADO,
                        ProcessoTitular.STATUS_REPROVADO,
                        ProcessoTitular.STATUS_REJEITADO,
                    ],
                    avaliacao_paga=avaliacao_paga,
                    avaliador=avaliador,
                ).order_by('processo__servidor__pessoa_fisica__nome')

                avaliador.avaliacoes = list(qs_avaliacoes_avaliador)
                avaliador.qtde_avaliacoes = len(avaliador.avaliacoes)
                avaliador.qtde_horas = avaliador.qtde_avaliacoes * hora_por_avaliacao
                avaliador.valor_a_pagar = avaliador.qtde_avaliacoes * valor_por_avaliacao

                if avaliador.eh_interno() and relatorio == 'interno':
                    total_avaliacoes_internos += avaliador.qtde_avaliacoes
                    avaliadores_internos.append(avaliador)
                    valor_total_internos += avaliador.valor_a_pagar

                if avaliador.eh_externo() and (relatorio == 'externo' or relatorio == 'externo_instituicao_origem'):
                    total_avaliacoes_externos += avaliador.qtde_avaliacoes

                    avaliador.desconto_inss_a_pagar = avaliador.valor_a_pagar * inss
                    avaliador.desconto_iss_a_pagar = avaliador.valor_a_pagar * iss
                    avaliador.valor_liquido_a_pagar = avaliador.valor_a_pagar - (avaliador.desconto_inss_a_pagar + avaliador.desconto_iss_a_pagar)
                    avaliadores_externos.append(avaliador)

                    if avaliador.instituicao_origem:
                        if avaliador.instituicao_origem.id in total_avaliacoes_por_instituicao:
                            for ava in avaliador.avaliacoes:
                                if ava.processo.id not in total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id][0]:
                                    total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id][0].append(ava.processo.id)
                                    total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id][1] += 1  # qtde. processos
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id][2] += avaliador.qtde_avaliacoes  # qtde. avaliações
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id][3] += avaliador.valor_a_pagar  # valor total a pagar
                        else:
                            total_avaliacoes_por_instituicao[avaliador.instituicao_origem.id] = [
                                [avaliacao.processo.id],
                                1,
                                avaliador.qtde_avaliacoes,
                                avaliador.valor_a_pagar,
                            ]

                    valor_total_externos += avaliador.valor_liquido_a_pagar

            total_avaliacoes = total_avaliacoes_internos + total_avaliacoes_externos

        return locals()


@login_required()
def salvar_arquivo_individual(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'msg': 'Requisição inválida. Use POST.'}, status=405)

    try:
        # 1. Validação do processo e permissão
        processo_id = request.POST.get('processo_id')
        if not processo_id:
            raise ValidationError('ID do processo não fornecido.')

        processo = get_object_or_404(ProcessoTitular, pk=processo_id)
        if not eh_dono(request, processo):
            return JsonResponse({'status': 'error', 'msg': 'Permissão negada.'}, status=403)

        # 2. Validação do arquivo
        arquivo_id = request.POST.get('arquivo_id')
        if not arquivo_id:
            # A lógica atual é apenas para atualização, então um ID é necessário.
            raise ValidationError('ID do arquivo não fornecido.')

        arquivo = Arquivo.objects.get(encrypted_pk=arquivo_id)

        # 3. Validação dos campos
        quantidade_str = request.POST.get('quantidade')
        data_str = request.POST.get('data')
        nota_str = request.POST.get('nota')
        descricao = request.POST.get('descricao', '').strip()

        # Validação da quantidade
        try:
            quantidade = int(quantidade_str)
            if quantidade < 0:
                raise ValidationError('A quantidade não pode ser negativa.')
        except ValueError, TypeError:
            raise ValidationError('A quantidade deve ser um número inteiro válido.')

        # Validação da data
        if not data_str or not data_str.strip():
            raise ValidationError('A data é obrigatória.')

        # Validação da nota
        try:
            # Substitui vírgula por ponto para aceitar formato brasileiro
            nota = float(nota_str.replace(',', '.'))
            if nota < 0:
                raise ValidationError('A nota não pode ser negativa.')
        except ValueError, TypeError, AttributeError:
            raise ValidationError('A nota deve ser um número válido.')

        # 4. Atualização do objeto
        arquivo.qtd_itens = quantidade
        arquivo.data_referencia = data_str
        arquivo.descricao = descricao
        arquivo.nota_pretendida = nota
        arquivo.save()

        return JsonResponse({'status': 'ok', 'msg': 'Item atualizado com sucesso.'})

    except (ValidationError, ProcessoTitular.DoesNotExist, Arquivo.DoesNotExist) as e:
        msg = e.message if hasattr(e, 'message') else str(e)
        return JsonResponse({'status': 'error', 'msg': msg}, status=400)
    except Exception as e:
        # Captura outras exceções inesperadas
        return JsonResponse({'status': 'error', 'msg': f'Ocorreu um erro inesperado: {e!s}'}, status=500)


def eh_avaliador(request):
    return request.user.has_perm('professor_titular.pode_avaliar_processotitular')


def eh_dono(request, processo):
    retorno = False
    if request.user.is_authenticated and request.user.get_vinculo() == processo.servidor.get_vinculo():
        retorno = True
    return retorno


def eh_membro_cppd(request):
    return request.user.has_perm('professor_titular.pode_validar_processotitular')


def soh_cppd(request):
    if not eh_membro_cppd(request):
        raise PermissionDenied


def pode_anexar(request: HttpRequest, processo: ProcessoTitular) -> bool:
    """Como a tela do processo, que só mostra os uploaders ao dono com o processo editável."""
    return eh_dono(request, processo) and processo.avaliado_pode_editar()


def soh_dono(request, processo):
    if not eh_dono(request, processo):
        raise PermissionDenied


def soh_cppd_dono_avaliador(request, processo):
    if not eh_membro_cppd(request) and not eh_dono(request, processo) and not eh_avaliador(request):
        raise PermissionDenied


def soh_cppd_e_dono(request, processo):
    if not eh_membro_cppd(request) and soh_dono(request, processo):
        raise PermissionDenied
