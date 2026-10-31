"""Carimbo e widget de assinatura no fluxo PAdES por hash (preparação no cliente).

O serviço devolve apenas o pacote criptográfico (CMS); este módulo posiciona o retângulo da
assinatura na página e define texto, margens e imagem de fundo com PyHanko, para que o PDF
fechado fique visualmente consistente com a assinatura por upload quando os mesmos parâmetros
em ``constants`` / ``stamp`` são usados.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.layout import AxisAlignment, InnerScaling, Margins, SimpleBoxLayoutRule
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign.fields import MDPPerm, SigFieldSpec, append_signature_field
from pyhanko.sign.signers import cms_embedder
from pyhanko.stamp import TextStampStyle

from .constants import (
    SIGN_HASH_FIELD_NAME_PREFIX,
    # STAMP_BACKGROUND_IMAGE,
    STAMP_BORDER_WIDTH_PT,
    STAMP_BOX_HEIGHT,
    STAMP_BOX_WIDTH,
    STAMP_BOX_X_OFFSET,
    STAMP_BOX_Y_OFFSET,
    STAMP_FONT_SIZE_PT,
    STAMP_HASH_ALIGN_BY,
    STAMP_HASH_ALIGN_X,
    STAMP_HASH_ALIGN_Y,
    STAMP_HASH_PAGE,
    STAMP_TEXT_MARGINS,
)


def next_unused_signature_field_name(
    writer: IncrementalPdfFileWriter,
    *,
    name_prefix: str = SIGN_HASH_FIELD_NAME_PREFIX,
) -> str:
    """Gera um nome de campo AcroForm ainda não usado (por exemplo ``Signature1``, ``Signature2``)."""
    prev = writer.prev
    taken: set[str] = set()

    try:
        acro = prev.root['/AcroForm'].get_object()
        fields = acro.get('/Fields') or []
        for ref in fields:
            try:
                field = ref.get_object()
            except AttributeError, TypeError:
                continue
            if str(field.get('/FT', '')) != '/Sig':
                continue
            field_name = field.get('/T')
            if field_name is not None:
                taken.add(str(field_name))
    except AttributeError, KeyError, TypeError, ValueError:
        pass

    for sig in getattr(prev, 'embedded_signatures', ()):
        field_name = sig.sig_field.raw_get('/T')
        if field_name is not None:
            taken.add(str(field_name))

    index = 1
    while True:
        candidate = f'{name_prefix}{index}'
        if candidate not in taken:
            return candidate
        index += 1


def _modify_stamp_box_size(page_size: list[float], stamp_box_size: list[int]) -> None:
    """Reduz o tamanho da caixa do carimbo se ela não couber na página (com margem de segurança)."""
    width_limit = max(page_size[2] - 10, 0)
    if stamp_box_size[0] > width_limit:
        stamp_box_size[0] = int(min(width_limit, page_size[2])) if page_size[2] > 0 else 0

    height_limit = max(page_size[3] - 10, 0)
    if stamp_box_size[1] > height_limit:
        stamp_box_size[1] = int(min(height_limit, page_size[3])) if page_size[3] > 0 else 0


def _get_stamp_positions(
    page_size: list[float],
    stamp_align_by: str,
    stamp_align_x: float,
    stamp_align_y: float,
    stamp_box_size: list[int],
) -> tuple[float, float, float, float]:
    """Converte alinhamento e âncora em retângulo ``(x1, x2, y1, y2)`` em espaço da página."""
    stamp_x1_pos = stamp_align_x if stamp_align_by == 'left' else stamp_align_x + float(page_size[2] / 2)
    if stamp_x1_pos + stamp_box_size[0] > page_size[2]:
        stamp_x1_pos = page_size[2] - stamp_box_size[0]
    stamp_x1_pos = max(stamp_x1_pos, 0)

    stamp_x2_pos = min(stamp_x1_pos + stamp_box_size[0], page_size[2])

    stamp_y1_pos = stamp_align_y
    if stamp_y1_pos < 0:
        stamp_y1_pos = 0
    elif stamp_y1_pos > page_size[3]:
        stamp_y1_pos = page_size[3] - stamp_box_size[1]

    stamp_y2_pos = min(stamp_y1_pos + int(stamp_box_size[1]), page_size[3])

    return stamp_x1_pos, stamp_x2_pos, stamp_y1_pos, stamp_y2_pos


def compute_stamp_page_and_box(
    pdf_bytes: bytes,
    stamp_pos: dict[str, int] | None,
) -> tuple[int, tuple[int, int, int, int]]:
    """Índice da página (0-based) e retângulo do widget de assinatura em pontos PDF, compatível com ``SigFieldSpec.box`` do PyHanko."""
    try:
        reader = PdfFileReader(BytesIO(pdf_bytes), strict=False)
        page_count = int(reader.root['/Pages']['/Count'])
    except KeyError, TypeError, ValueError:
        return 0, (0, 0, 0, 0)

    if stamp_pos is None:
        page_idx = STAMP_HASH_PAGE
    else:
        page_idx = int(stamp_pos['page'])

    if page_idx < 0:
        page_idx += page_count
    page_idx = max(0, min(page_idx, page_count - 1))

    try:
        page_ref, _ = reader.find_page_for_modification(page_idx)
        page_obj = page_ref.get_object()
        page_size = [float(x) for x in page_obj['/MediaBox']]
    except KeyError, TypeError, ValueError:
        page_size = [0.0, 0.0, 612.0, 792.0]

    stamp_box_size = [STAMP_BOX_WIDTH, STAMP_BOX_HEIGHT]
    _modify_stamp_box_size(page_size, stamp_box_size)

    if stamp_pos is None:
        align_x, align_y = float(STAMP_HASH_ALIGN_X), float(STAMP_HASH_ALIGN_Y)
        align_by = STAMP_HASH_ALIGN_BY
    else:
        align_x = float(int(stamp_pos['x']) - STAMP_BOX_X_OFFSET)
        align_y = float(int(stamp_pos['y']) - STAMP_BOX_HEIGHT - STAMP_BOX_Y_OFFSET)
        align_by = 'left'

    x1, x2, y1, y2 = _get_stamp_positions(page_size, align_by, align_x, align_y, stamp_box_size)
    return page_idx, (int(x1), int(y1), int(x2), int(y2))


def build_hash_text_stamp_style(stamp_path: str) -> TextStampStyle:
    """Estilo de carimbo só texto (e imagem de fundo opcional), alinhado aos defaults em ``constants``."""
    margins = Margins(*STAMP_TEXT_MARGINS)
    inner_content = SimpleBoxLayoutRule(
        x_align=AxisAlignment.from_x_align('right'),
        y_align=AxisAlignment.from_y_align('mid'),
        margins=margins,
        inner_content_scaling=InnerScaling.STRETCH_TO_FIT,
    )
    text_box_rule = SimpleBoxLayoutRule(
        x_align=AxisAlignment.ALIGN_MID,
        y_align=AxisAlignment.ALIGN_MID,
        margins=margins,
        inner_content_scaling=InnerScaling.SHRINK_TO_FIT,
    )
    text_box_style = TextBoxStyle(font_size=STAMP_FONT_SIZE_PT, box_layout_rule=text_box_rule)
    background = PdfImage(stamp_path)

    return TextStampStyle(
        border_width=STAMP_BORDER_WIDTH_PT,
        background=background,
        stamp_text='',
        text_box_style=text_box_style,
        inner_content_layout=inner_content,
        background_opacity=1.0,
    )


def append_hash_signature_field_with_stamp(
    writer,
    *,
    pdf_bytes: bytes,
    field_name: str,
    stamp_pos: dict[str, int] | None,
) -> None:
    """Inclui no writer incremental o campo de assinatura visível e permissões de formulário (MDP)."""
    page_idx, box = compute_stamp_page_and_box(pdf_bytes, stamp_pos)
    append_signature_field(
        writer,
        SigFieldSpec(
            sig_field_name=field_name,
            on_page=page_idx,
            box=box,
            field_mdp_spec=None,
            doc_mdp_update_value=MDPPerm.FILL_FORMS,
        ),
    )


def sig_appearance_setup_for_hash(
    stamp_path: str,
    *,
    appearance_timestamp: datetime | None,
    signer_display_name: str | None,
    stamp_url: str,
):
    """Configuração de aparência da assinatura para o empacotador CMS do PyHanko (texto, horário, URL)."""
    style = build_hash_text_stamp_style(stamp_path)
    text_params = {'url': stamp_url} if stamp_url else None
    return cms_embedder.SigAppearanceSetup(
        style=style,
        name=signer_display_name,
        timestamp=appearance_timestamp,
        text_params=text_params,
    )
