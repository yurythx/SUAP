"""Constantes compartilhadas pelos exemplos da API (desenvolvimento local)."""

# POST multipart com o PDF para assinatura no servidor.
API_SIGN_HASH_PATH_PREFIX = '/api/signer/pdf/sign/hash'
API_VERIFY_PDF_PATH = '/api/verifier/pdf/verify'

# False = assinar sem carimbo (upload sem campos de estampa; hash sem aparência de carimbo).
INCLUDE_STAMP = True

STAMP_BOX_WIDTH = 260
STAMP_BOX_HEIGHT = 70
STAMP_BOX_X_OFFSET = 11
STAMP_BOX_Y_OFFSET = -2
# STAMP_BACKGROUND_IMAGE: Path | None = Path("/Users/breno/Downloads/carimbo.png")

# URL exibida no carimbo como referência de verificação (deve ser acessível aos leitores do PDF).
STAMP_VERIFY_URL = 'https://verificador.rnp.br'
# Fuso horário da data/hora impressa no texto do carimbo.
STAMP_TIME_ZONE = 'America/Sao_Paulo'

# Margens internas do texto no carimbo (esquerda, superior, direita, inferior), em pontos PDF.
STAMP_TEXT_MARGINS = (14, 7, 0, 0)
STAMP_FONT_SIZE_PT = 3
STAMP_BORDER_WIDTH_PT = 0

# Posição padrão do widget de assinatura com carimbo em ``sign_hash_pdf`` quando ``stamp_pos`` é ``None``.
STAMP_HASH_PAGE = 0
STAMP_HASH_ALIGN_BY = 'left'
STAMP_HASH_ALIGN_X = 5
STAMP_HASH_ALIGN_Y = 5

HTTP_TIMEOUT_S = 60

# Prefixo dos widgets de assinatura em ``sign_hash_pdf`` (``Signature1``, ``Signature2``, …).
SIGN_HASH_FIELD_NAME_PREFIX = 'Signature'
