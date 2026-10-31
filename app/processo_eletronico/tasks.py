from __future__ import annotations

import os
import tempfile
import zipfile
from datetime import datetime
from typing import TYPE_CHECKING

import magic
import sentry_sdk
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction
from django.utils.safestring import mark_safe

from djtools.assincrono import task
from djtools.models import Task
from djtools.storages import cache_file, download_temporary_file, get_temp_storage
from djtools.utils import (
    convert_docx_to_pdf,
    converter_csv_para_pdf,
    converter_imagem_para_pdf,
    converter_planilha_para_pdf,
    full_check_file,
    merge_pdf_files,
)
from documento_eletronico.models import DocumentoDigitalizado, TipoDocumento
from processo_eletronico.models import Tramite
from processo_eletronico.utils import gerar_partes_processo_pdf

if TYPE_CHECKING:
    from comum.models import User
    from rh.models.carreira.papel import Papel


@task('Gerar Processo PDF')
def gerar_processo_pdf(user, processo, leitura_para_barramento, eh_consulta_publica=False, task=None):
    """
    Método que retorna o PDF completo do processo.

    :param user: usuário que está querendo ver os PDFs que compõem o processo.
    :param processo: o processo em si
    :param leitura_para_barramento: identifica se o PDFs exibido tem como objetivo a tramitação para barramento. Se for,
     então alguma regras vão ser aplicadas para saber se o PDF deverá conter o conteúdo do documento ou apenas alguns
     dados básicos.
    """
    paths_files = []

    def add_file_temp_dir(content, nome_arquivo):
        base_filename = f'{nome_arquivo}.pdf'
        filename = os.path.join(settings.TEMP_DIR, base_filename.replace(' ', '_'))
        arquivo = open(filename, 'wb+')
        arquivo.write(content)
        arquivo.close()
        paths_files.append(arquivo.name)

    def remove_files_temp_dir(paths_files):
        for path_file in paths_files:
            os.remove(path_file)

    try:
        partes_processo_pdf = gerar_partes_processo_pdf(processo, user, leitura_para_barramento, eh_consulta_publica=eh_consulta_publica, task=task)
        ordem = 0
        agora = datetime.now()
        for parte_processo in task.iterate(partes_processo_pdf):
            ordem += 1
            add_file_temp_dir(parte_processo['pdf'], f'{ordem}_{processo.id}_{agora}')

        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
        tmp.write(merge_pdf_files(paths_files))
        tmp.close()
        task.update_progress(90)
        remove_files_temp_dir(paths_files)
        task.finalize('Processo Gerado com sucesso.', '..', file_path=tmp.name)
    except Exception:
        task.update_progress(0)
        task.finalize('Erro ao tentar gerar o PDF deste processo, por favor tente novamente.', '..', error=True)


@task('Gerar Zip do Processo')
def gerar_zip_processo(user, processo, leitura_para_barramento, eh_consulta_publica=False, task=None):
    """
    Método que retorna o ZIP com os PDFs do processo.

    :param user: usuário que está querendo ver os PDFs que compõem o processo.
    :param processo: o processo em si
    :param leitura_para_barramento: identifica se o PDFs exibido tem como objetivo a tramitação para barramento. Se for,
     então alguma regras vão ser aplicadas para saber se o PDF deverá conter o conteúdo do documento ou apenas alguns
     dados básicos.
    """
    paths_files = []

    def add_file_temp_dir(content, nome_arquivo):
        base_filename = f'{nome_arquivo}.pdf'
        filename = os.path.join(settings.TEMP_DIR, base_filename.replace(' ', '_'))
        arquivo = open(filename, 'wb+')
        arquivo.write(content)
        arquivo.close()
        paths_files.append(arquivo.name)

    def remove_files_temp_dir(paths_files):
        for path_file in paths_files:
            os.remove(path_file)

    partes_processo_pdf = gerar_partes_processo_pdf(processo, user, leitura_para_barramento, eh_consulta_publica, task=task)
    ordem = 0
    agora = datetime.now()
    task.count(partes_processo_pdf)
    for parte_processo in partes_processo_pdf:
        ordem += 1
        add_file_temp_dir(parte_processo['pdf'], f'{ordem}_{processo.id}_{agora}')

    path_zip = os.path.join(settings.TEMP_DIR, str(processo.id) + '.zip')
    zip_file = zipfile.ZipFile(path_zip, 'w')

    for path in paths_files:
        zip_file.write(os.path.relpath(path), os.path.basename(path), compress_type=zipfile.ZIP_DEFLATED)

    zip_file.close()
    task.update_progress(99)
    remove_files_temp_dir(paths_files)
    task.finalize('Processo Gerado com sucesso.', '..', file_path=zip_file.filename)


def _verificar_integridade_pdf_gerado(file_obj: File, caminho: str) -> str:
    try:
        caminho_cache = cache_file(caminho)
        if not caminho_cache:
            raise FileNotFoundError(f'Não foi possível obter em cache o arquivo gerado a partir de "{caminho}".')
        arquivo = InMemoryUploadedFile(
            file=file_obj,
            field_name=None,
            name=caminho_cache,
            content_type='application/pdf',
            size=os.path.getsize(caminho_cache),
            charset=None,
        )
        full_check_file(arquivo, check_content_types=False)
    except ValidationError as e:
        return mark_safe(' '.join(e.messages))
    except Exception as e:
        # Erro inesperado (ex.: dependência de sistema ausente, storage remoto indisponível) —
        # não expor o texto técnico ao usuário final; registrar para investigação e devolver uma
        # mensagem genérica. Precisa estar dentro do try: se escapar, aborta o transaction.atomic()
        # do chamador e derruba até os anexos já anexados com sucesso.
        with sentry_sdk.new_scope() as scope:
            scope.set_extra('caminho_arquivo', caminho)
            sentry_sdk.capture_exception(e)
        return 'Não foi possível verificar a integridade do arquivo. Tente novamente mais tarde ou entre em contato com o suporte.'
    return ''


def _copiar_anexo_como_documento_digitalizado(
    caminho_arquivo: str,
    nome_arquivo: str,
    descricao: str,
    tipo_documento: TipoDocumento,
    nivel_acesso: int,
    temporario: bool,
    url_publica: str,
    usuario: User,
    papel: Papel,
) -> DocumentoDigitalizado | str:
    if temporario:
        caminho_arquivo_cached = download_temporary_file(caminho_arquivo)
        storage = get_temp_storage()
    else:
        caminho_arquivo_cached = cache_file(caminho_arquivo)
        storage = default_storage
    content_type = magic.Magic(mime=True).from_file(caminho_arquivo_cached)
    extensao = os.path.splitext(caminho_arquivo_cached)[1].lower()
    caminho_pdf = caminho_arquivo_cached

    # doc, docx
    if content_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        caminho_pdf = convert_docx_to_pdf(settings.TEMP_DIR, caminho_arquivo_cached)
    # xls, xlsx
    elif content_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        caminho_pdf = converter_planilha_para_pdf(caminho_arquivo_cached)
    # csv
    elif content_type == 'text/csv':
        caminho_pdf = converter_csv_para_pdf(caminho_arquivo_cached, descricao)
    # jpg, jpeg, png
    elif content_type in ['image/jpeg', 'image/png']:
        dados_imagem = {
            'caminho_arquivo': caminho_arquivo,
            'descricao': descricao,
            'storage': storage,
            'content_type': content_type,
            'url_publica': url_publica,
            'exibir_url': True,
        }
        caminho_pdf = converter_imagem_para_pdf(dados_imagem)
    # pdf
    elif content_type == 'application/pdf':
        pass
    else:
        # aborta execução, retornando o mimetype para notificar o usuário
        return content_type

    with open(caminho_pdf, 'rb') as f:
        file_content = f.read()

    nome_arquivo = nome_arquivo.replace(extensao, '.pdf')
    return DocumentoDigitalizado.criar(
        file_content=file_content,
        file_name=nome_arquivo,
        tipo_documento=tipo_documento,
        nivel_acesso=nivel_acesso,
        assunto=descricao,
        user=usuario,
        papel=papel,
    )


@task('Criar Processo com Trâmite')
def criar_arquivos_e_primeiro_tramite_de_processo(
    processo,
    anexos,
    usuario,
    papel,
    setor_criacao,
    corpo_despacho,
    setor_destino,
    url_redirecionamento,
    notify=False,
    on_finish=None,
    on_finish_extra_params=None,
    task=None,
):
    if task:
        Task.objects.filter(pk=task.pk).update(notify=notify)

    with transaction.atomic():
        anexos = anexos or []
        arquivos_com_erro = {}
        task.count(anexos)
        for anexo in task.iterate(anexos):
            try:
                doc = _copiar_anexo_como_documento_digitalizado(
                    caminho_arquivo=anexo['path'],
                    nome_arquivo=anexo['name'],
                    descricao=anexo['descricao'],
                    tipo_documento=anexo['tipo_documento'],
                    nivel_acesso=anexo['nivel_acesso'],
                    temporario=anexo['temporario'],
                    url_publica=anexo['url_publica'],
                    usuario=usuario,
                    papel=papel,
                )
            except Exception as e:
                # Idem: um erro inesperado aqui (ex.: storage remoto indisponível) não pode
                # abortar o transaction.atomic() e derrubar os anexos já processados com sucesso.
                with sentry_sdk.new_scope() as scope:
                    scope.set_extra('anexo', anexo['descricao'])
                    sentry_sdk.capture_exception(e)
                arquivos_com_erro[anexo['descricao']] = (
                    'Não foi possível processar este arquivo. Tente novamente mais tarde ou entre em contato com o suporte.'
                )
                continue

            if isinstance(doc, str):
                arquivos_com_erro[anexo['descricao']] = mark_safe(
                    f'O tipo do conteúdo do arquivo ({doc}) é inválido e impediu a conversão automatizada para PDF. '
                    f'Utilize uma ferramenta de <a href="https://www.adobe.com/br/acrobat/online/convert-pdf.html">conversão para PDF</a> '
                    f'para converter o arquivo manualmente'
                )
            else:
                erro_integridade = _verificar_integridade_pdf_gerado(doc.arquivo, doc.arquivo.name)
                if erro_integridade:
                    arquivos_com_erro[anexo['descricao']] = erro_integridade
                else:
                    processo.adicionar_documento_digitalizado(doc, usuario=usuario)

        primeiro_tramite = Tramite()
        primeiro_tramite.processo = processo
        primeiro_tramite.tramitar_processo(
            remetente_setor=setor_criacao,
            remetente_vinculo=usuario.get_vinculo(),
            despacho_corpo=corpo_despacho,
            destinatario_vinculo=None,
            destinatario_setor=setor_destino,
            assinar_tramite=True,
            papel=papel,
        )
        numero_processo_criado = processo.numero_protocolo
        url_processo = processo.get_absolute_url()

        if url_redirecionamento:
            parametros_url = f'numero_processo_criado={numero_processo_criado}&url_processo={processo.get_absolute_url()}'
            if '?' in url_redirecionamento:
                url_redirecionamento += f'&{parametros_url}'
            else:
                url_redirecionamento += f'?{parametros_url}'

        if on_finish:
            on_finish(numero_processo_criado, url_processo, arquivos_com_erro, on_finish_extra_params)

        task.finalize('Processo gerado e tramitado com sucesso.', url_redirecionamento or '..')
