#!/usr/bin/env python3
"""Assina PDF via rota de hash e incorpora o PKCS7 no documento final."""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import requests
from asn1crypto import cms
from django.conf import settings
from django.core.cache import cache
from pypdf import PdfReader
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.fields import MDPPerm, SigFieldSpec, append_signature_field
from pyhanko.sign.general import SigningError
from pyhanko.sign.signers import SignatureObject, cms_embedder

from comum.models import APIExterna
from djtools.storages.utils import cache_file, get_overwrite_storage

from .constants import (
    API_SIGN_HASH_PATH_PREFIX,
    HTTP_TIMEOUT_S,
    INCLUDE_STAMP,
    STAMP_VERIFY_URL,
)
from .hash_pdf_stamp import (
    append_hash_signature_field_with_stamp,
    next_unused_signature_field_name,
    sig_appearance_setup_for_hash,
)
from .stamp import signature_img, stamp_signer_display_name


logger = logging.getLogger(__name__)


def count_signatures(pdf_path: str | Path) -> int:
    """Retorna a quantidade de assinaturas incorporadas no PDF, se possível."""
    try:
        with open(pdf_path, 'rb') as file_obj:
            reader = PdfFileReader(file_obj)
            return len(getattr(reader, 'embedded_signatures', ()))
    except OSError, TypeError, ValueError:
        return 0


def _http_post_sign_hash(url: str, bearer_token: str) -> tuple[bytes, int]:
    """Faz POST no endpoint de assinatura por hash e retorna corpo/status."""
    response = requests.post(
        url,
        headers={'Authorization': f'Bearer {bearer_token}'},
        timeout=HTTP_TIMEOUT_S,
    )
    if not response.ok:
        raise Exception(response.text)
    return response.content, response.status_code


def _pkcs7_pem_to_der(data: bytes) -> bytes:
    """Converte PKCS7 PEM para DER; se já vier DER, retorna sem alteração."""
    text = data.decode(errors='replace').strip()
    if 'BEGIN PKCS7' not in text:
        return data
    b64_lines = [line.strip() for line in text.splitlines() if not line.startswith('-----')]
    return base64.b64decode(''.join(b64_lines))


def _prepare_pdf_and_hash(
    pdf_bytes: bytes,
    digest_algorithm: str,
    bytes_reserved: int,
    *,
    stamp_pos: dict[str, int] | None,
    access_token: str,
    stamp_path: str,
):
    """Prepara o PDF para assinatura CMS e devolve digest, writer e metadados."""
    writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes), strict=False)
    field_name = next_unused_signature_field_name(writer)

    if INCLUDE_STAMP:
        append_hash_signature_field_with_stamp(
            writer,
            pdf_bytes=pdf_bytes,
            field_name=field_name,
            stamp_pos=stamp_pos,
        )
    else:
        append_signature_field(
            writer,
            SigFieldSpec(
                sig_field_name=field_name,
                on_page=0,
                box=(0, 0, 0, 0),
            ),
        )

    cms_writer = cms_embedder.PdfCMSEmbedder().write_cms(field_name=field_name, writer=writer)
    next(cms_writer)

    appearance_ts = datetime.now(UTC) + timedelta(seconds=3)
    sig_obj = SignatureObject(
        timestamp=appearance_ts,
        bytes_reserved=bytes_reserved,
    )

    if INCLUDE_STAMP:
        appearance = sig_appearance_setup_for_hash(
            stamp_path,
            appearance_timestamp=appearance_ts,
            signer_display_name=stamp_signer_display_name(access_token),
            stamp_url=STAMP_VERIFY_URL,
        )
        cms_writer.send(
            cms_embedder.SigObjSetup(
                sig_placeholder=sig_obj,
                mdp_setup=cms_embedder.SigMDPSetup(
                    md_algorithm=digest_algorithm,
                    docmdp_perms=MDPPerm.FILL_FORMS,
                ),
                appearance_setup=appearance,
            )
        )
    else:
        cms_writer.send(
            cms_embedder.SigObjSetup(
                sig_placeholder=sig_obj,
                mdp_setup=cms_embedder.SigMDPSetup(md_algorithm=digest_algorithm),
            )
        )

    prep_digest, output = cms_writer.send(cms_embedder.SigIOSetup(md_algorithm=digest_algorithm, in_place=True))
    return prep_digest, output, cms_writer, field_name


def sign_hash_pdf(
    pdf_path: str,
    output_pdf: Path,
    access_token: str,
    api_base_url: str,
    stamp_pos: dict[str, int] | None = None,
    stamp_path: str | None = None,
) -> None:
    """Executa o fluxo assinar-por-hash e grava o PDF final assinado."""
    input_pdf = Path(pdf_path).expanduser().resolve()
    output_pdf = output_pdf.expanduser().resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    digest_algorithm = 'sha256'
    pdf_bytes = input_pdf.read_bytes()
    bytes_reserved = 16384

    for _ in range(2):
        prep_digest, output, cms_writer, field_name = _prepare_pdf_and_hash(
            pdf_bytes,
            digest_algorithm,
            bytes_reserved,
            stamp_pos=stamp_pos,
            access_token=access_token,
            stamp_path=stamp_path,
        )
        digest_hex = prep_digest.document_digest.hex()
        url = f'{api_base_url.rstrip("/")}{API_SIGN_HASH_PATH_PREFIX}/{digest_algorithm}/{digest_hex}'

        logger.info('URL: %s', url)
        logger.info('Input PDF: %s', input_pdf)
        logger.info('Campo de assinatura: %s', field_name)
        logger.info('Digest algorithm: %s', digest_algorithm)
        logger.info('Digest: %s', digest_hex)
        logger.info(f'Access Token: {access_token}')

        pem_signature, status = _http_post_sign_hash(url, access_token)
        cms_der = _pkcs7_pem_to_der(pem_signature)

        try:
            cms_writer.send(cms_der)
            output_pdf.write_bytes(output.getbuffer())
            logger.info('Status: %s', status)
            logger.info('Output PDF: %s', output_pdf)
            return
        except SigningError as exc:
            if status != 200:
                raise
            matched = re.search(r'allocated \d+ bytes, but contents required (\d+) bytes', str(exc))
            if not matched:
                raise
            bytes_reserved = int(matched.group(1))
            logger.info('Reajustando bytes reservados para assinatura: %s', bytes_reserved)

    raise RuntimeError('Não foi possível incorporar a assinatura CMS no PDF.')


def get_position(disposition: str, file_path: str | Path) -> tuple[int, int]:
    """Retorna a posição PAdES para o tipo de orientação do documento."""
    positions = {
        'portrait': ((55, 109), (307, 109), (0, 0)),
        'landscape': ((275, 133), (527, 133), (0, 0)),
    }
    return positions[disposition][count_signatures(file_path)]


def assinar_arquivo_pdf(
    file_path,
    signer,
    tipo_documento,
    x,
    y,
    page,
    bgcolor,
    titulo,
    codigo_autenticacao,
    disposition='portrait',
):
    """Assina um arquivo PDF no serviço ICPEDU e substitui o arquivo original quando necessário."""
    if file_path.startswith('/'):
        local_file_path = file_path
    else:
        local_file_path = cache_file(file_path)

    if x is None and y is None:
        x, y = get_position(disposition, local_file_path)
        if page == -1:
            y = 2

    api_externa = APIExterna.ICPEDU
    service = api_externa.get_service()
    signer_emails = getattr(signer, 'emails', None) or []
    if not signer_emails:
        raise ValueError('Signer sem e-mail cadastrado para assinatura digital.')
    service.set_signer(signer, signer_emails.split(' - ')[0])

    key = f'token_{signer.nome}_{signer.id}'
    token = cache.get(key, None)
    if token is None:
        token = service.get_token()
        cache.set(key, token, timeout=30)

    stamp_path = signature_img(
        validation_url=f'{settings.SITE_URL}/comum/validar_assinatura/',
        signer=signer.nome,
        document_type=tipo_documento,
        authentication_code=codigo_autenticacao,
        bgcolor=bgcolor,
        title=titulo,
    )

    try:
        sign_hash_pdf(
            local_file_path,
            Path(local_file_path),
            token,
            service.api_externa.url_base,
            stamp_pos={'x': x, 'y': y, 'page': page},
            stamp_path=stamp_path,
        )
    finally:
        if os.path.exists(stamp_path):
            os.unlink(stamp_path)

    storage = get_overwrite_storage()
    if local_file_path != file_path:
        with open(local_file_path, 'rb') as source_file:
            storage.save(file_path, source_file)
        if os.path.exists(local_file_path):
            os.unlink(local_file_path)


def verify(pdf_path):
    """Lista signatários reconhecidos em um PDF assinado."""
    reader = PdfReader(pdf_path)
    fields = reader.get_fields() or {}
    signers = []

    for field_data in fields.values():
        if field_data.get('/FT') == '/Sig' and '/V' in field_data:
            sig_dict = field_data['/V']
            if '/Contents' not in sig_dict:
                continue

            contents = sig_dict['/Contents']
            try:
                raw_bytes = bytes.fromhex(contents.rstrip('\x00')) if isinstance(contents, str) else bytes(contents).rstrip(b'\x00')
                content_info = cms.ContentInfo.load(raw_bytes)
                signed_data = content_info['content']
                certificates = signed_data['certificates']
                for cert in certificates:
                    cert_obj = cert.chosen
                    subject = cert_obj.subject.native
                    common_name = subject.get('common_name')
                    if common_name:
                        serial_number = subject.get('serial_number')
                        if serial_number:
                            signers.append({'cn': f'{common_name}:{serial_number}'})
            except TypeError, ValueError, KeyError:
                continue

    return signers
