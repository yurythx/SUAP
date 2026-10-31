"""Carimbo na assinatura para o fluxo de assinatura com upload de PDF.

Monta os campos de formulário e a imagem opcional de fundo enviados junto do arquivo na
requisição de assinatura. A aparência final no PDF é definida pelo serviço de assinatura
com base nas configurações definidas.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import qrcode
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from .constants import STAMP_TIME_ZONE, STAMP_VERIFY_URL


def _load_font(font_path: str, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega a fonte solicitada com fallback seguro para a fonte padrão do Pillow."""
    try:
        return ImageFont.truetype(font_path, font_size)
    except OSError, ValueError:
        return ImageFont.load_default()


def _jwt_payload_unverified(access_token: str) -> dict[str, Any] | None:
    """Lê o payload do Bearer token, sem validar assinatura, para montar os dados do carimbo."""
    try:
        parts = access_token.split('.')
        if len(parts) != 3:
            return None
        payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode('ascii'))
        return json.loads(payload_bytes)
    except TypeError, ValueError, json.JSONDecodeError:
        return None


def stamp_signer_display_name(access_token: str) -> str:
    """Nome do signatário para metadados ou aparência da assinatura no cliente."""
    payload = _jwt_payload_unverified(access_token) or {}
    signer_name = payload.get('rnp_name') or payload.get('name') or ''
    return str(signer_name).strip()


def _compose_stamp_message(*, signer_name: str, sign_time: datetime, verify_url: str) -> str:
    """Monta o texto exibido no carimbo com nome, data/hora e URL de validação."""
    verify_line = f'\nVerifique em {verify_url}' if verify_url else ''
    return f'Assinado digitalmente por\n{signer_name}\nData: {sign_time.strftime("%d/%m/%Y %H:%M:%S")}{verify_line}'


def hash_stamp_display_message(access_token: str) -> str:
    """Mensagem de texto do carimbo no fluxo assinar-por-hash (deve combinar com ``stamp_form_fields``)."""
    signer_name = stamp_signer_display_name(access_token)
    sign_time = datetime.now(ZoneInfo(STAMP_TIME_ZONE))
    return _compose_stamp_message(signer_name=signer_name, sign_time=sign_time, verify_url=STAMP_VERIFY_URL)


def signature_img(
    validation_url,
    signer,
    document_type=None,
    authentication_code=None,
    bgcolor='#EEEEEE',
    title=None,
):
    """Gera a representação visual da assinatura digital no padrão dos documentos eletrônicos do SUAP."""
    width, height = 1200, 240
    current_time = datetime.now()
    image = Image.new('RGBA', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([(3, 3), (width - 3, height - 3)], fill=bgcolor, outline=bgcolor)

    font_path = os.path.join(settings.BASE_DIR, 'comum', 'static/comum/font/MicrosoftSansSerif.ttf')
    bold_font_path = os.path.join(settings.BASE_DIR, 'comum', 'static/comum/font/MicrosoftSansSerifBold.ttf')
    font = _load_font(font_path, 25)
    bold = _load_font(bold_font_path, 25)

    cursor_y = 20
    stamp_title = f'Assinado em {{}} como {str(title).upper()}' if title else 'Documento assinado eletronicamente em {} por'
    draw.text((50, cursor_y), stamp_title.format(current_time.strftime('%d/%m/%Y as %H:%M')), (0, 0, 0), font=font)
    cursor_y += 30
    draw.text((80, cursor_y), f'• {str(signer).upper()}', (0, 0, 0), font=bold)

    draw.line([(50, 95), (width - 300, 95)], fill='#CCCCCC', width=3)
    draw.text((50, cursor_y + 120), 'Para comprovar sua autenticidade, faça a leitura do QRCode ou acesse', (0, 0, 0), font=font)
    draw.text((50, cursor_y + 140), validation_url, (0, 0, 0), font=font)

    if document_type:
        cursor_y += 50
        draw.text((50, cursor_y), 'Tipo de Documento:', (0, 0, 0), font=bold)
        draw.text((400, cursor_y), document_type, (0, 0, 0), font=font)
    if authentication_code:
        cursor_y += 30
        draw.text((50, cursor_y), 'Código de Autenticação:', (0, 0, 0), font=bold)
        draw.text((400, cursor_y), authentication_code, (0, 0, 0), font=font)

    qr_img = create_qrcode_image(validation_url, bgcolor=bgcolor)
    image.paste(qr_img.get_image(), (width - 250, 5, width - 30, 225))

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    try:
        image.save(temp_file.name)
        return temp_file.name
    finally:
        temp_file.close()


def create_qrcode_image(url, bgcolor='#EEEEEE'):
    """Cria uma imagem contendo o QRCode da URL passada como parâmetro."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='#000000', back_color=bgcolor)
        qr_img.thumbnail((220, 220), Image.Resampling.LANCZOS)
        return qr_img
    except TypeError, ValueError:
        return Image.new('RGBA', (220, 220), (255, 255, 255, 0))
