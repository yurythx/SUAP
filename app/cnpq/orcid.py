from xml.dom import minidom

ORCID_ATRIBUTOS_LATTES = ('ORCID', 'ORCID-ID', 'ID-ORCID', 'IDENTIFICADOR-ORCID')
ORCID_URL_MAX_LENGTH = 200


def formatar_orcid(orcid: str) -> str:
    orcid = orcid.strip()
    if not orcid:
        return ''
    if not orcid.startswith(('http://', 'https://')):
        orcid = f'https://orcid.org/{orcid}'
    return orcid if len(orcid) <= ORCID_URL_MAX_LENGTH else ''


def get_orcid_documento(documento: object) -> str:
    for dados_gerais in documento.getElementsByTagName('DADOS-GERAIS'):
        for atributo in ORCID_ATRIBUTOS_LATTES:
            orcid = formatar_orcid(dados_gerais.getAttribute(atributo))
            if orcid:
                return orcid
    return ''


def get_orcid_lattes(curriculo_str: bytes | str) -> str:
    documento = minidom.parseString(curriculo_str)
    return get_orcid_documento(documento)
