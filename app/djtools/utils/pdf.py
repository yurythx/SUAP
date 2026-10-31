from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import traceback
import zipfile
from datetime import datetime, timedelta
from functools import WRAPPER_ASSIGNMENTS, wraps
from io import BytesIO
from typing import IO, TYPE_CHECKING

import magic
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from django.forms import ValidationError
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.template.defaultfilters import filesizeformat
from django.template.loader import get_template
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from pypdf import PdfWriter
from requests.exceptions import HTTPError
from sentry_sdk import capture_exception

from djtools import relatorios

from . import requests
from .breadcrumbs import breadcrumbs_previous_url
from .estaticos_pdf import Asset, coletar_assets
from .response import render_to_string
from .test import running_tests

if TYPE_CHECKING:
    # `from . import requests` acima sombreia o nome `requests`: dentro deste
    # módulo ele é o wrapper do djtools, não a biblioteca — só dá pra referenciar
    # `Response` via import isolado para tipagem.
    from requests import Response

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = [mimetypes.guess_extension(ext).upper() for ext in getattr(settings, 'CONTENT_TYPES', ['application/pdf'])]


def merge_pdf_files_qpdf(paths_files):
    """
    Função para merge de arquivos PDF
    """

    outfile = tempfile.NamedTemporaryFile(suffix='.pdf', dir=settings.TEMP_DIR, delete=False)
    outfile.close()
    qpdf = getattr(settings, 'QPDF_CMD', None)
    try:
        command = [qpdf, '--empty', '--decrypt', '--linearize', '--pages', *paths_files, '--', outfile.name]
        subprocess.run(command, check=False)
        return outfile.name
    except OSError:
        raise Exception(f'Error executing {qpdf}.')
    except SystemExit:
        raise Exception(f'Error while running QPDF subprocess. Traceback: \n {traceback.format_exc()}')
    except Exception:
        raise Exception(f'Error while running QPDF subprocess. Traceback: \n {traceback.format_exc()}')


def merge_pdf_files(paths_files):
    output_file = merge_pdf_files_qpdf(paths_files)

    with open(output_file, 'rb') as outfile:
        output_pdf = outfile.read()
    os.remove(output_file)
    return output_pdf


def decrypt_pdf_content(content_pdf):
    qpdf = getattr(settings, 'QPDF_CMD', None)
    if not isinstance(content_pdf, UploadedFile):
        return content_pdf
    metadata = {
        'field_name': getattr(content_pdf, 'field_name', '__empty__'),
        'name': content_pdf.name,
        'content_type': content_pdf.content_type,
        'size': content_pdf.size,
        'charset': content_pdf.charset,
    }
    infile = tempfile.NamedTemporaryFile(suffix='.pdf', dir=settings.TEMP_DIR, delete=False)
    content_pdf.file.seek(0)
    infile.write(content_pdf.read())
    infile.close()
    outfile = tempfile.NamedTemporaryFile(suffix='.pdf', dir=settings.TEMP_DIR, delete=False)
    cmd = [qpdf, '--decrypt', infile.name, outfile.name]
    try:
        retorno = subprocess.run(cmd, capture_output=True, check=False)
        if retorno.returncode not in [0, 3]:  # 0 = sucesso, 3 = warnings (como PDF encriptado mas com permissões de escrita)
            raise Exception(retorno.stdout.decode() + '\n' + retorno.stderr.decode())
        out = BytesIO()
        out.write(outfile.read())
        upload = InMemoryUploadedFile(
            file=out,
            field_name=metadata['field_name'],
            name=metadata['name'],
            content_type=metadata['content_type'],
            size=metadata['size'],
            charset=metadata['charset'],
        )
        upload.file.seek(0)
        outfile.close()
        os.remove(infile.name)
        os.remove(outfile.name)
        return upload
    except OSError:
        raise Exception(f'Error executing qpdf ({qpdf}). Is it in your PATH?')
    except SystemExit:
        raise Exception(f'Error while running qpdf subprocess. Traceback: \n {traceback.format_exc()}')
    except Exception:
        raise Exception(f'Error while running qpdf subprocess. Traceback: \n {traceback.format_exc()}')


def check_can_edit_pdf(content_pdf):
    blank_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False, mode='wb')
    content_pdf.file.seek(0)
    tmp_pdf.write(content_pdf.read())
    content_pdf.file.seek(0)
    tmp_pdf.close()
    try:
        pdf_writer = PdfWriter()
        pdf_writer.add_blank_page(10, 10)
        pdf_writer.write(blank_pdf)
        blank_pdf.close()
        merge_pdf_files([tmp_pdf.name, blank_pdf.name])
        os.remove(blank_pdf.name)
        os.remove(tmp_pdf.name)
        return True
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        blank_pdf.close()
        os.remove(blank_pdf.name)
        os.remove(tmp_pdf.name)
        return False


def check_pdf(content, ignore_warnings=True):
    """
    Verifica a validade de um arquivo PDF (File/ContentFile do Django) usando qpdf --check.

    Args:
        content (django.core.files.File): Objeto de arquivo Django (File ou ContentFile).
        ignore_warnings (bool): Se True, qpdf --warning-exit-0 é usado para ignorar warnings.

    Returns:
        bool: True se o qpdf retornar 0 (válido), False caso contrário.
    """
    qpdf_cmd = getattr(settings, 'QPDF_CMD', 'qpdf')

    if not qpdf_cmd:
        logger.error('QPDF_CMD não está configurado nas settings.')
        return False

    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, mode='wb', suffix='.pdf') as temp_file_obj:
            content.seek(0)
            temp_file_obj.write(content.read())
            filepath = temp_file_obj.name
            temp_file = filepath

    except Exception as e:
        logger.warning(f'Erro ao manipular o arquivo temporário: {e}', exc_info=True)
        if settings.DEBUG:
            raise
        capture_exception(e)
        return False

    parameters = ['--check']
    retornos = [0]
    if ignore_warnings:
        retornos.append(3)  # 3 é o código de retorno para warnings

    cmd = [qpdf_cmd, *parameters, filepath]

    try:
        retorno = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=30,
        )

        is_valid = retorno.returncode in retornos

        if not is_valid:
            logger.warning(
                f'qpdf falhou (código {retorno.returncode}) para o arquivo: {filepath}. Stderr: {retorno.stderr.decode()}. Stdout: {retorno.stdout.decode()}'
            )
        else:
            logger.info(
                f'qpdf check passed for {filepath} with return code {retorno.returncode}. Stderr: {retorno.stderr.decode()}. Stdout: {retorno.stdout.decode()}'
            )

        return is_valid
    except Exception as e:
        logger.warning(f'Erro na execução do subprocesso qpdf: {e}', exc_info=True)
        if settings.DEBUG:
            raise e
        capture_exception(e)
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                logger.warning(f'Falha ao remover arquivo temporário {temp_file}: {e}', exc_info=True)


def _check_content_type_allowed(content_type, raise_validation_error):
    allowed_types = getattr(settings, 'CONTENT_TYPES', ['application/pdf'])
    if content_type not in allowed_types:
        if raise_validation_error:
            raise ValidationError(f'Tipo de arquivo não permitido. Arquivos permitidos são dos seguintes tipos: {", ".join(ALLOWED_EXTENSIONS)}')
        return None
    return content_type == 'application/pdf'


def _validate_pdf_integrity(content, can_decrypt_content, can_edit_required, raise_validation_error):
    is_valid = check_pdf(content)
    if not is_valid:
        if raise_validation_error:
            raise ValidationError(
                mark_safe(
                    'Arquivo protegido com senha, encriptado, corrompido ou mal formado. Utilize uma ferramenta de <a href="https://www.ilovepdf.com/pt/reparar-pdf" target="_blank">reparação de PDFs</a> ou uma ferramenta de <a href="https://www.ilovepdf.com/pt/desbloquear_pdf" target="_blank">remoção de senha de PDFs</a>'
                )
            )
        return False

    if can_decrypt_content:
        try:
            content = decrypt_pdf_content(content)
        except Exception:
            if raise_validation_error:
                raise ValidationError(
                    mark_safe(
                        'Arquivo protegido com senha ou encriptado. Utilize uma ferramenta de <a href="https://www.ilovepdf.com/pt/reparar-pdf" target="_blank">reparação de PDFs</a> ou uma ferramenta de <a href="https://www.ilovepdf.com/pt/desbloquear_pdf" target="_blank">remoção de senha de PDFs</a>'
                    )
                )
            return False

    if can_edit_required:
        can_edit = check_can_edit_pdf(content)
        if not can_edit:
            if raise_validation_error:
                raise ValidationError(
                    mark_safe(
                        'Arquivo encriptado protegido contra escrita. Utilize uma ferramenta de <a href="https://www.ilovepdf.com/pt/reparar-pdf" target="_blank">reparação de PDFs</a> ou uma ferramenta de <a href="https://www.ilovepdf.com/pt/desbloquear_pdf" target="_blank">remoção de senha de PDFs</a>'
                    )
                )
            return False

    return True


def full_check_file(
    content,
    can_decrypt_content=True,
    check_required=True,
    check_content_types=True,
    can_edit_required=True,
    max_file_size=None,
    raise_validation_error=True,
):
    """
    Realiza uma verificação completa de um arquivo PDF, incluindo validade e permissão de edição.

    Args:
        content (django.core.files.File): Objeto de arquivo Django (File ou ContentFile).
        can_decrypt_content (bool): Se True, verifica se o conteúdo do PDF pode ser descriptografado.
        check_empty (bool): Se True, verifica se o conteúdo do PDF não é None.
        check_content_types (bool): Se True, verifica os tipos de conteúdo do PDF.
        can_edit_required (bool): Se True, verifica se o PDF pode ser editado.
        max_file_size (int): Tamanho máximo permitido do arquivo em bytes. Se None, não há limite.
        raise_validation_error (bool): Se True, levanta uma exceção em caso de falha na validação.
    """
    if check_required:
        if content is None:
            if raise_validation_error:
                raise ValidationError('Este campo é obrigatório.')
            return False
    elif not content:
        return True

    if max_file_size is not None and getattr(content, 'size', 0) > max_file_size:
        if raise_validation_error:
            raise ValidationError(
                f'O tamanho máximo para um arquivo é de {filesizeformat(max_file_size)} bytes. '
                f'O arquivo atual possui {filesizeformat(content.size)} bytes.'
            )
        return False

    is_pdf = True
    if check_content_types:
        content_type = magic.Magic(mime=True).from_buffer(content.read(2048))
        content.seek(0)
        result = _check_content_type_allowed(content_type, raise_validation_error)
        if result is None:
            return False
        is_pdf = result

    if not is_pdf:
        return True

    return _validate_pdf_integrity(content, can_decrypt_content, can_edit_required, raise_validation_error)


def _postar_wkhtml(url: str, data: dict[str, object], headers: dict[str, str], assets: dict[str, Asset]) -> Response:
    """Posta no suap-pdf e, se ele pedir os blobs que faltam (409), reenvia uma vez."""
    response = requests.post(url, json=data, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    if response.status_code == 409:
        faltantes = set(response.json().get('missing', []))
        data = dict(data, blobs={asset.sha256: asset.base64 for asset in assets.values() if asset.sha256 in faltantes})
        response = requests.post(url, json=data, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    return response


def render_pdf_from_template_with_wkhtmltopdf(
    template: str,
    header_template: str | None = None,
    footer_template: str | None = None,
    context: dict | None = None,
    cmd_options: dict | None = None,
) -> bytes:
    if not context:
        context = {}
    cmd_options = {key: str(val is None and '-' or val) for key, val in cmd_options.items()} if cmd_options else {}
    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')
        headers = {'Authorization': f'Token {token_libreoffice}'}
        rendered_template = render_to_string(template, context)
        if header_template:
            rendered_header = render_to_string(header_template, context)
        else:
            rendered_header = ''
        if footer_template:
            rendered_footer = render_to_string(footer_template, context)
        else:
            rendered_footer = ''
        # Os estáticos vão junto do HTML: o suap-pdf não compartilha mais o volume
        # de estáticos do SUAP. Só os hashes são enviados; o conteúdo, se ele pedir.
        assets = coletar_assets(rendered_template, rendered_header, rendered_footer)
        data = {
            'template': rendered_template,
            'header_template': rendered_header,
            'footer_template': rendered_footer,
            'options': cmd_options,
            'assets': {chave: asset.sha256 for chave, asset in assets.items()},
        }
        response = _postar_wkhtml(f'{caminho_libreoffice}/api/v1/wkhtml_to_pdf', data, headers, assets)
        if response.status_code != 200:
            # HTTPError (e não Exception) para os chamadores tratarem queda do serviço como RequestException, igual a timeout/conexão.
            raise HTTPError(
                f'Erro ao tentar obter resposta do servidor de impressão de PDFs, por favor tente novamente em alguns minutos. Detalhe: {response.text}',
                response=response,
            )
        return response.content

    if running_tests():
        return render_to_string(template, context).encode('utf-8')

    from wkhtmltopdf import render_pdf_from_template

    template = get_template(template)
    return render_pdf_from_template(
        template,
        header_template=header_template,
        footer_template=footer_template,
        context=context,
        cmd_options=cmd_options,
    )


def documento(
    tipo_para_verificacao=None,
    landscape=False,
    validade=None,
    enumerar_paginas=True,
    pdf_response=True,
    modelo=None,
    forcar_recriacao=False,
    exibe_emissor=False,
):
    """
    Decorator utilizado para que possibilite a conversão da função/view no padrão **PDF**.

    Args:
        tipo_para_verificacao ():
        landscape ():
        validade ():
        enumerar_paginas ():
        pdf_response ():
        modelo ():
        forcar_recriacao ():
        exibe_emissor: exibe a matrícula do usuário que emitiu o documento.

    Returns:
        Função decorada.
    """

    def receive_function(function):
        @wraps(function, assigned=WRAPPER_ASSIGNMENTS)
        def receive_function_args(request, *args, **kwargs):
            response = function(request, *args, **kwargs)
            if response is None:
                return HttpResponse('<h2>Falha ao gerar o documento: nenhuma resposta foi recebida.</h2>', content_type='text/html', status=500)

            pk = None
            chave_extra = None
            if tipo_para_verificacao:
                pk = kwargs.get('pk')
                if not pk:
                    response.headers['location'] = ('Location', breadcrumbs_previous_url(request))
                    return response

                if tipo_para_verificacao == 'Certificado de Conclusão de Módulo':
                    chave_extra = kwargs.get('modulo')
                if tipo_para_verificacao == 'Histórico Final':
                    chave_extra = kwargs.get('via')
            if response.headers['content-type'] == 'application/pdf':
                return response

            if isinstance(response, HttpResponseRedirect):
                if response.headers['location'] == request.path:
                    response.headers['location'] = breadcrumbs_previous_url(request)
                return response

            if isinstance(response, HttpResponseForbidden):
                return response

            if 'html' in request.GET or running_tests():
                return response

            RegistroEmissaoDocumento = apps.get_model('comum', 'RegistroEmissaoDocumento')
            html = response.content.decode('utf-8')

            string_paginacao = ''
            if not enumerar_paginas:
                html = html.replace('@bottom-right', '')

            data_emissao = datetime.now()
            if validade and tipo_para_verificacao == 'Declaração de Nada Consta':
                data_validade = data_emissao + timedelta(validade)
                msg_validade = ''
            elif validade and tipo_para_verificacao not in ('Pesquisa', 'Extensão'):
                data_validade = data_emissao + timedelta(validade)
                msg_validade = '<strong>Válido até</strong>: {}<br>'.format(data_validade.strftime('%d/%m/%Y'))
            else:
                data_validade = None
                msg_validade = ''

            codigo_verificador = hashlib.sha1(f'{request.user.pk}{data_emissao}{settings.SECRET_KEY}'.encode()).hexdigest()
            url_suap = settings.SITE_URL
            msg = ''
            dir_name = f'comum/registroemissaodocumento/documento/{data_emissao.year}/{str(data_emissao.month).zfill(2)}'
            file_name = f'{dir_name}/{codigo_verificador}.pdf'
            if tipo_para_verificacao:
                data_emissao_str = data_emissao.strftime('%d/%m/%Y')
                if tipo_para_verificacao == 'Certificado ENEM':
                    msg = f"""
                        <br/><br/>
                        <table>
                            <tr>
                                <td></td>
                                <td style="width: 300px; border:1px solid #ccc; font-size:18px; text-align: center; margin:0; padding: 10px 0; line-height:130%;">
                                    Código para autenticação: <br/>
                                    <strong>{codigo_verificador[0:6]}</strong>
                                </td>
                                <td></td>
                            </tr>
                        </table>
                        <br/>
                        <div style="text-align:center; font-size:14px;">
                            Documento emitido pelo SUAP. Para comprovar sua autenticidade, acesse
                            <strong><a href="{url_suap}/comum/autenticar_documento/">{url_suap}/comum/autenticar_documento/</a>.</strong> <br/>
                            <strong>Tipo de Documento:</strong> {tipo_para_verificacao} <br/>
                            <strong>Data da Emissão:</strong> {data_emissao_str}
                        </div>
                    """
                else:
                    if request.GET.get('dados_assinatura'):
                        assinaturas_html = []
                        dados_assinatura = json.loads(request.GET.get('dados_assinatura'))
                        for dado_assinatura in dados_assinatura:
                            papel = dado_assinatura.get('papel', '')
                            if papel:
                                papel = f'{papel}, '
                            assinaturas_html.append(
                                f'<li><strong>{dado_assinatura["nome"]}</strong> ({dado_assinatura["matricula"]}), {papel}em <strong>{dado_assinatura["data"]}</strong> com chave <strong>{dado_assinatura["chave"]}</strong>.</li>'
                            )
                        url_simples = RegistroEmissaoDocumento.url_autenticacao(tipo_para_verificacao, data_emissao, codigo_verificador)
                        url_completa = RegistroEmissaoDocumento.url_autenticacao(
                            tipo_para_verificacao, data_emissao, codigo_verificador, completa=True
                        )
                        qrcode = RegistroEmissaoDocumento.qrcode(url_completa)
                        msg = """
                        <div class="assinaturas">
                            <div>
                                <h3>Documento assinado eletronicamente por:</h3>
                                <ul>
                                    {}
                                </ul>
                            </div>
                            <div class="qrcode">
                                <img width="20px" src="data:image/png;base64,{}" alt="QR code do documento" />
                                Documento emitido pelo SUAP. Para comprovar sua autenticidade, faça a leitura do QrCode ao lado ou acesse
                                {} e informe os dados a seguir.<br/>
                                <strong>Tipo de Documento:</strong> {} <br/>
                                <strong>Data da Emissão:</strong> {} <br/>
                                <strong>Código de Autenticação:</strong> {}
                            </div>
                        </div>
                        """.format(''.join(assinaturas_html), qrcode, url_simples, tipo_para_verificacao, data_emissao_str, codigo_verificador[0:6])
                    else:
                        valido_ate = ''
                        if msg_validade:
                            valido_ate = f' - {msg_validade}'
                        emissor = ''
                        if exibe_emissor:
                            usuario = request.user and request.user.username or 'SUAP'
                            emissor = f' - <strong>Emissor</strong>: {usuario}'
                        url_autenticacao = f'{url_suap}/comum/autenticar_documento/'
                        msg = f'<footer><div align="center" style="text-align:center; font-size:8pt;">{string_paginacao}<br>Para comprovar a autenticidade desse documento, acesse <strong><a href="{url_autenticacao}">{url_autenticacao}</a></strong><br><strong>Código verificador</strong>: {codigo_verificador[0:6]} - <strong>Tipo</strong>: {tipo_para_verificacao} - <strong>Emissão em</strong>: {data_emissao_str}{emissor}{valido_ate}</div></footer>'
                if tipo_para_verificacao == 'Extensão':
                    diretorio = 'projetos/certificados/'
                    file_name = os.path.join(diretorio, f'{codigo_verificador}.pdf')
                elif tipo_para_verificacao == 'Pesquisa':
                    diretorio = 'pesquisa/declaracoes/'
                    file_name = os.path.join(diretorio, f'{codigo_verificador}.pdf')
            content = io.BytesIO()
            html = html.replace('</body>', f'{msg}</body>')

            if landscape is True:
                html = html.replace('a4 portrait', 'a4 landscape')
                html = html.replace('logo_if_portrait', 'logo_if_landscape')

            from weasyprint import HTML

            try:
                HTML(string=html, base_url=settings.SITE_URL).write_pdf(content)
            except Exception as error:
                if settings.DEBUG:
                    raise error
                capture_exception(error)
                html_error = """<p>Ocorreu um erro ao gerar o PDF.</p>
                    <p>Evite <b>copiar</b> e <b>colar</b> texto com formatação do <b>Microsoft Word</b> ou inserir imagens com dimensões maiores que as do PDF.</p>
                    <p>Atenção: Revise os campos preenchidos para gerar o documento e se não for possível gerar o arquivo corretamente, na tela anterior à geração deste PDF, reporte o erro do sistema.</p>
                """
                HTML(string=html_error, base_url=settings.SITE_URL).write_pdf(content)
            content.seek(0)

            if tipo_para_verificacao:
                tipo_objeto = modelo and ContentType.objects.get_for_model(apps.get_model(modelo)) or None
                qs_registro = RegistroEmissaoDocumento.objects.filter(
                    tipo=tipo_para_verificacao, tipo_objeto=tipo_objeto, modelo_pk=pk, cancelado=False, chave_extra=chave_extra
                )
                if not qs_registro or validade or settings.DEBUG or forcar_recriacao:
                    registro = RegistroEmissaoDocumento()
                    registro.tipo = tipo_para_verificacao
                    registro.data_emissao = data_emissao
                    registro.codigo_verificador = codigo_verificador
                    registro.data_validade = data_validade
                    registro.modelo_pk = pk
                    registro.tipo_objeto = tipo_objeto
                    registro.chave_extra = chave_extra
                    file_obj = default_storage.save(file_name, content)
                    content.seek(0)
                    registro.documento = file_obj
                    registro.save()
                else:
                    registro = qs_registro[0]
                return pdf_response and registro.as_pdf_response() or registro
            else:
                return HttpResponse(content, content_type='application/pdf')

        return receive_function_args

    return receive_function


def libreoffice_new_line(tokens, align_center='', font_size=17):
    if len(tokens) > 1:
        if align_center:
            align_center = '<w:jc w:val="center"/>'
        out = ['</w:t></w:r></w:p>']
        for token in tokens:
            out.append(f'<w:p><w:pPr><w:spacing w:after="0"/>{align_center}</w:pPr><w:r><w:rPr><w:sz w:val="{font_size}"/></w:rPr><w:t>{token}')
            out.append('</w:t></w:r></w:p>')
        del out[-1]
        return ''.join(out)
    elif len(tokens) == 1:
        return tokens[0]
    return ''


def _converter_no_servico(url: str, headers: dict[str, str], **corpo: object) -> str:
    """Posta no serviço de conversão (``caminho_libreoffice``) e grava o PDF devolvido num temporário.

    Raises:
        HTTPError: se o serviço responder status diferente de 200 (queda/lentidão já chegam como ``RequestException``).
    """
    response = requests.post(url, headers=headers, timeout=settings.REQUESTS_TIMEOUT, **corpo)
    if response.status_code != 200:
        raise HTTPError(
            'Erro ao tentar obter resposta do servidor de impressão de PDFs, por favor tente novamente em alguns minutos.', response=response
        )
    with tempfile.NamedTemporaryFile(mode='w+b', suffix='.pdf', delete=False) as pdf_file:
        pdf_file.write(response.content)
    return pdf_file.name


def convert_docx_to_pdf(folder: str, source: str, timeout: int | None = None, pdfa: bool = False) -> str:
    extensao = os.path.splitext(source)[1]

    content_type = magic.Magic(mime=True).from_file(source)
    if content_type not in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        raise ValueError(f'Tipo de conteúdo inválido: "{content_type}".')

    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')

    if running_tests():
        return source

    # ===================== SERVIÇO VIA CONTAINER =====================
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')
        headers = {'Authorization': f'Token {token_libreoffice}'}

        with open(source, 'r+b') as doc:
            template = base64.b64encode(doc.read()).decode()
        data = {'template': template, 'qrcode': None, 'pdfa': pdfa, 'values': {}}
        return _converter_no_servico(f'{caminho_libreoffice}/api/v1/docx_to_pdf', headers, json=data)
    # ==================================================================

    my_env = os.environ.copy()
    my_env['HOME'] = settings.TEMP_DIR

    if caminho_libreoffice:
        if settings.DEBUG and not os.path.exists(caminho_libreoffice):
            return source

        converto_to = 'pdf:writer_pdf_Export:SelectPdfVersion=1' if pdfa else 'pdf'
        args = [caminho_libreoffice, '--safe-mode', '--headless', '--convert-to', converto_to, '--outdir', folder, source]

        retorno = subprocess.run(args, env=my_env, capture_output=True, check=False)
        # Warniing conhecido: 'libpng warning: iCCP: known incorrect sRGB profile'
        warning_patterns = [
            r'warning:',  # Captura qualquer linha que contenha "warning:"
        ]

        stderr_content = retorno.stderr.decode() if retorno.stderr else ''
        is_only_warnings = False

        if stderr_content.strip():
            # Remove linhas em branco e verifica se todas as linhas restantes são warnings conhecidos
            stderr_lines = [line.strip() for line in stderr_content.split('\n') if line.strip()]
            if stderr_lines:
                is_only_warnings = all(any(re.search(pattern, line, re.IGNORECASE) for pattern in warning_patterns) for line in stderr_lines)

        # Considera erro apenas se returncode != 0 ou se stderr contém mensagens que não são warnings conhecidos
        if retorno.returncode != 0 or (stderr_content.strip() and not is_only_warnings):
            capture_exception(Exception(retorno.stdout.decode() + '\n' + stderr_content))
            if settings.DEBUG:
                logger.debug(f'Erro na conversão DOCX->PDF: {retorno.stdout.decode()}\n{stderr_content}')
            raise Exception(
                'Ocorreu um erro na conversão do documento. Por favor tente novamente em alguns minutos. Se o problema persistir reporte erro.'
            )
        else:
            return source.replace(extensao, '.pdf')
    else:
        capture_exception(Exception('Configure o caminho do libre office na view /comum/configuracao'))
        raise Exception('Ocorreu um erro na configuração do SUAP. Por favor, entre em contato com o setor de desenvolvimento do SUAP.')


def _gerar_documento_impressao_no_servico(
    caminho_libreoffice: str, dicionario: dict, modelo_documento_path: str | IO[bytes], pdfa: bool | None, imagem_path: str | None
) -> str:
    from comum.models import Configuracao

    token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')
    headers = {'Authorization': f'Token {token_libreoffice}'}
    template = base64.b64encode(
        open(modelo_documento_path, 'r+b').read() if isinstance(modelo_documento_path, str) else modelo_documento_path.read()
    ).decode()
    qrcode = base64.b64encode(open(imagem_path, 'rb').read()).decode() if imagem_path else None
    data = {
        'template': template,
        'qrcode': qrcode,
        'pdfa': pdfa,
        'values': {key: str(val is None and '-' or val) for key, val in dicionario.items()},
    }
    return _converter_no_servico(f'{caminho_libreoffice}/api/v1/docx_to_pdf', headers, json=data)


def _midias_placeholder(template_docx: zipfile.ZipFile, tempdir: str) -> list[str]:
    """Caminhos (``word/media/...``) das imagens do modelo que são o placeholder a ser trocado pela imagem informada."""
    media_relative_paths = []
    template_docx.extractall(tempdir, members=[name for name in template_docx.namelist() if 'word/media' in name])
    for dirpath, _, media_names in os.walk(os.path.join(tempdir, 'word/media')):
        for media_name in media_names:
            media_path = os.path.join(dirpath, media_name)
            size = os.stat(media_path).st_size
            if size == os.stat(os.path.join(settings.BASE_DIR, 'comum/static/comum/img/placeholder.png')).st_size:
                media_relative_paths.append(os.path.join('word/media', media_name))
    return media_relative_paths


def gerar_documento_impressao(
    dicionario: dict, modelo_documento_path: str | IO[bytes], pdfa: bool | None = False, imagem_path: str | None = None
) -> str:
    """
    :param dicionario: dados que serão substitutos pelas marcações do docx
    :param modelo_documento_path: caminho do arquivo docx contendo as marcações que serão substituidas
    :param pdfa: informar None caso deseje que o próprio docx seja retorna.
        informar True caso deseje que o docx seja convertido para PDF-A
        informar False caso deseje que o docx seja conertido para PDF
    :return: caminho do arquivo resultante do processamento
    """

    # ===================== SERVIÇO VIA CONTAINER =====================
    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        return _gerar_documento_impressao_no_servico(caminho_libreoffice, dicionario, modelo_documento_path, pdfa, imagem_path)
    # ==================================================================

    template_docx = zipfile.ZipFile(modelo_documento_path)
    new_docx = zipfile.ZipFile(os.path.join(settings.TEMP_DIR, f'temp{get_random_string(12)}.docx'), 'a')
    tempdir = tempfile.mkdtemp()
    tmp_xml_file = open(template_docx.extract('word/document.xml', tempdir))
    tempXmlStr = tmp_xml_file.read()
    tmp_xml_file.close()
    os.unlink(tmp_xml_file.name)

    for key in list(dicionario.keys()):
        value = str(dicionario.get(key)).replace('&', '&amp;')
        tempXmlStr = tempXmlStr.replace(key, value)

    tmp_xml_file = tempfile.NamedTemporaryFile(mode='w+', dir=settings.TEMP_DIR, delete=False)
    tmp_xml_file.write(tempXmlStr)
    tmp_xml_file.close()

    media_relative_paths = _midias_placeholder(template_docx, tempdir)

    for arquivo in template_docx.filelist:
        if arquivo.filename != 'word/document.xml' and arquivo.filename not in media_relative_paths:
            new_docx.writestr(arquivo.filename, template_docx.read(arquivo))

    new_docx.write(tmp_xml_file.name, 'word/document.xml')
    if media_relative_paths and imagem_path:
        for media_relative_path in media_relative_paths:
            new_docx.write(imagem_path, media_relative_path)

    template_docx.close()
    new_docx.close()
    os.unlink(tmp_xml_file.name)
    shutil.rmtree(tempdir)
    if pdfa is not None:
        pdf_file_path = convert_docx_to_pdf(settings.TEMP_DIR, new_docx.filename, pdfa=pdfa)
        if pdf_file_path != new_docx.filename:
            os.unlink(new_docx.filename)
        return pdf_file_path
    else:
        # Caso não seja informado, deverá retornar o caminho para o arquivo DOCX processado.
        return new_docx.filename


def convert_pdf_to_pdfa(source: str, version: int = 2, compatibility_level: float = 1.4) -> str:
    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')

    if running_tests():
        return source

    # ===================== SERVIÇO VIA CONTAINER =====================
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')
        headers = {'Authorization': f'Token {token_libreoffice}'}

        with open(source, 'r+b') as doc:
            template = base64.b64encode(doc.read()).decode()
        data = {'template': template, 'version': version, 'compatibility_level': compatibility_level}
        response = requests.post(
            f'{caminho_libreoffice}/api/v1/pdf_to_pdfa',
            json=data,
            headers=headers,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if response.status_code != 200:
            # HTTPError (e não Exception genérica) deixa quem chama tratar a indisponibilidade do conversor como infra.
            raise HTTPError(
                'Erro ao tentar obter resposta do servidor de impressão de PDFs, por favor tente novamente em alguns minutos.', response=response
            )

        # O temporário só nasce com a resposta 200: criado antes do POST, sobrava vazio a cada falha do conversor (#17601).
        with tempfile.NamedTemporaryFile('wb', delete=False, suffix='.pdf') as pdf_file:
            pdf_file.write(response.content)
        return pdf_file.name

    pdfa_file_path = tempfile.NamedTemporaryFile('wb', delete=False, suffix='.pdf').name
    command = f'{settings.GHOSTSCRIPT_CMD} -q -dPDFA={version} -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -dNOOUTERSAVE -dPDFACompatibilityPolicy=1 -dCompatibilityLevel={compatibility_level} -sOutputFile={pdfa_file_path} {source}'
    os.system(command)
    return pdfa_file_path


def converter_planilha_para_pdf(caminho_arquivo: str, timeout: int | None = None, pdfa: bool = False) -> str:
    extensao = os.path.splitext(caminho_arquivo)[1]

    content_type = magic.Magic(mime=True).from_file(caminho_arquivo)
    if content_type not in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        raise ValueError(f'Tipo de conteúdo inválido: "{content_type}".')

    if running_tests():
        return caminho_arquivo

    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')

    # ===================== SERVIÇO VIA CONTAINER =====================
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')

        headers = {'Authorization': f'Token {token_libreoffice}'}
        url = f'{caminho_libreoffice}/api/v1/xlsx_to_pdf'
        data = open(caminho_arquivo, 'rb').read()
        return _converter_no_servico(url, headers, data=data)
    # ==================================================================

    if caminho_libreoffice:
        diretorio = os.path.dirname(caminho_arquivo)
        my_env = os.environ.copy()
        my_env['HOME'] = settings.TEMP_DIR

        if settings.DEBUG and not os.path.exists(caminho_libreoffice):
            return caminho_arquivo

        converto_to = 'pdf:writer_pdf_Export:SelectPdfVersion=1' if pdfa else 'pdf'
        args = [caminho_libreoffice, '--safe-mode', '--headless', '--convert-to', converto_to, '--outdir', diretorio, caminho_arquivo]

        retorno = subprocess.run(args, env=my_env, capture_output=True, check=False)
        if retorno.returncode != 0:
            dados_erro = f'{retorno.stdout.decode()}\n{retorno.stderr.decode()}\nCódigo de retorno: {retorno.returncode}'
            capture_exception(Exception(dados_erro))
            if settings.DEBUG:
                logger.debug(f'Erro na conversão PDF->PDF/A: {dados_erro}')
            raise Exception(
                'Ocorreu um erro na conversão do documento. Por favor tente novamente em alguns minutos. Se o problema persistir reporte erro.'
            )
        else:
            return caminho_arquivo.replace(extensao, '.pdf')
    else:
        capture_exception(Exception('Configure o caminho do libre office na view /comum/configuracao'))
        raise Exception('Ocorreu um erro na configuração do SUAP. Por favor, entre em contato com o setor de desenvolvimento do SUAP.')


def _papel_para_largura(largura_mm: int) -> str:
    """Menor papel do reportlab (``-`` = paisagem) em que cabe a largura estimada da página."""
    for limite_mm, papel in ((210, 'A4'), (297, '-A4'), (420, '-A3'), (594, '-A2'), (841, '-A1'), (1189, '-A0')):
        if largura_mm <= limite_mm:
            return papel
    return '-B0'  # o maior tamanho de papel suportado pelo reportlab


def converter_csv_para_pdf(caminho_do_arquivo: str, descricao: str | None = None) -> str:
    """
    Gera um PDF a partir de um arquivo CSV.

    :param caminho_do_arquivo:
        O caminho absoluto do arquivo CSV.
    :type caminho_do_arquivo: :class:`str`
    :param descricao:
        A descrição dos dados.
    :type caminho_do_arquivo: :class:`str`

    :returns: o caminho do arquivo pdf gerado
    :rtype: :class:`str`
    """
    content_type = magic.Magic(mime=True).from_file(caminho_do_arquivo)
    if content_type != 'text/csv':
        raise ValueError(f'Tipo de conteúdo inválido: "{content_type}".')

    if running_tests():
        return caminho_do_arquivo

    from comum.models import Configuracao

    caminho_libreoffice = Configuracao.get_valor_por_chave('comum', 'caminho_libreoffice')

    # ===================== SERVIÇO VIA CONTAINER =====================
    if caminho_libreoffice and caminho_libreoffice.startswith('http'):
        token_libreoffice = Configuracao.get_valor_por_chave('comum', 'token_libreoffice')

        headers = {'Authorization': f'Token {token_libreoffice}'}
        url = f'{caminho_libreoffice}/api/v1/csv_to_pdf'
        data = open(f'{caminho_do_arquivo}', 'rb').read()
        return _converter_no_servico(url, headers, data=data)
    # ==================================================================

    primeira_linha_como_cabecalho = True
    dados_coletados = []
    tamanho_da_maior_linha = 0
    with open(caminho_do_arquivo) as arquivo_csv:
        inicio_arquivo = arquivo_csv.read(1024)
        dialect = csv.Sniffer().sniff(inicio_arquivo)

        arquivo_csv.seek(0)
        reader = csv.reader(arquivo_csv, dialect=dialect)
        for linha in reader:
            dados_coletados.append(linha)
            tamanho_da_maior_linha = max(len(linha), tamanho_da_maior_linha)
    tamanho_da_maior_linha += 1  # será adicionada uma coluna extra com o número da linha

    largura_da_coluna = 25  # milímetros
    # converte bool para inteiro, para se adequar à assinatura do método pdf.table()
    primeira_linha_como_cabecalho = primeira_linha_como_cabecalho and 1 or 0

    col_widths = [largura_da_coluna] * (tamanho_da_maior_linha - 1)
    largura_estimada_da_pagina_mm = 10 + largura_da_coluna * tamanho_da_maior_linha + 10

    paper = _papel_para_largura(largura_estimada_da_pagina_mm)

    subtitulo = f'Convertido do formato CSV pelo SUAP em {datetime.now().strftime("%d/%m/%Y, às %H:%M:%S")}.'

    titulo = relatorios.para(descricao, style='title')
    subtitulo = relatorios.para(subtitulo, style='Italic', alignment='center')
    tabela = relatorios.table(dados_coletados, w=col_widths, head=primeira_linha_como_cabecalho, count=1)

    conteudo_pdf = relatorios.PdfReport([titulo, subtitulo, relatorios.space(10), tabela], paper=paper).generate()

    pdf_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.pdf', delete=False)
    pdf_file.write(conteudo_pdf)
    pdf_file.close()
    return pdf_file.name


def generate_pdf_template_object(template_object, file_object, context, base_url=None):
    """
    Inner function to pass template objects directly instead of passing a filename
    """
    from weasyprint import HTML

    HTML(string=template_object.render(context), base_url=base_url or settings.SITE_URL).write_pdf(file_object)
    return file_object


def generate_pdf(template_name, file_object=None, context=None, base_url=None):
    file_object = file_object or io.BytesIO()
    context = context or {}
    tmpl = get_template(template_name)
    generate_pdf_template_object(tmpl, file_object, context, base_url=base_url)
    return file_object


def converter_imagem_para_pdf(imagem: dict) -> str:
    """
    Gera um PDF a partir de uma imagem.
    O PDF gerado exibirá a imagem conforme definido no template `imagem_pdf.html`.

    :param imagem:
        Um dicionário com os dados da imagem, no formato `{ "caminho": str, "descricao": str, "exibir_url": bool }`.
        `caminho` deve ser o caminho absoluto. `exibir_url` definirá como a imagem será legendada: se `True`,
        exibe a url; caso contário, exibe o nome do arquivo.
    :type imagem: :class:`dict`

    :returns: o caminho para o pdf gerado
    :rtype: :class:`str`
    """

    caminho = imagem['caminho_arquivo']  # gera KeyError se chave não existir
    storage = imagem['storage']
    content_type = imagem['content_type']

    if content_type.split('/')[0] != 'image':
        raise ValueError(f'Tipo de conteúdo inválido: {content_type}. Tipo esperado: "image/*".')

    # garante que valores existirão no template
    imagem['descricao'] = imagem.get('descricao') or ''
    imagem['exibir_url'] = imagem.get('exibir_url') or False

    # Computando outros dados da imagem
    nome_arquivo = os.path.basename(caminho)
    url_arquivo = storage.url(caminho)
    imagem['nome_arquivo'] = nome_arquivo
    imagem['url_arquivo'] = url_arquivo

    from comum.models import Configuracao

    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

    conteudo_pdf = generate_pdf(template_name='imagem_pdf.html', context={'imagem': imagem, 'nome_instituicao': instituicao}).getvalue()

    pdf_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.pdf', delete=False)
    pdf_file.write(conteudo_pdf)
    pdf_file.close()
    return pdf_file.name
