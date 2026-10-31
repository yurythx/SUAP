from datetime import datetime
from typing import TypedDict


class SharePointIds(TypedDict, total=False):
    """
    Agrupa diversos identificadores para um item armazenado no Sharepoint.

    Mais detalhes em: https://learn.microsoft.com/en-us/graph/api/resources/sharepointids?view=graph-rest-1.0.
    """

    listId: str
    listItemId: str
    listItemUniqueId: str
    siteId: str
    siteUrl: str
    tenantId: str
    webId: str


class SiteInfo(TypedDict, total=False):
    """
    Metadados de um site do Sharepoint.

    Alguns atributos complexos foram simplificados usando um dict comum.

    O recurso é detalhado em: https://learn.microsoft.com/en-us/graph/api/resources/site?view=graph-rest-1.0.
    """

    id: str
    createdDateTime: datetime
    description: str
    displayName: str
    eTag: str
    isPersonalSite: bool
    lastModifiedDateTime: datetime
    name: str
    root: dict
    sharepointIds: SharePointIds
    siteCollection: dict
    webUrl: str


class FileHashes(TypedDict, total=False):
    """
    Hashes do arquivo retornado pela API do MS Graph. Apenas um dos campos é preenchido no retorno.

    Mais detalhes em: https://learn.microsoft.com/en-us/graph/api/resources/hashes?view=graph-rest-1.0.
    """

    crc32Hash: str
    quickXorHash: str
    sha1Hash: str
    sha256Hash: str


class File(TypedDict):
    """
    Metadados de arquivos retornados pela API do MS Graph.

    Mais detalhes em: https://learn.microsoft.com/en-us/graph/api/resources/file?view=graph-rest-1.0.
    """

    hashes: FileHashes
    mimeType: str


class Folder(TypedDict):
    """
    Metadados de pastas retornadas pela API do MS Graph.

    Mais detalhes em: https://learn.microsoft.com/en-us/graph/api/resources/folder?view=graph-rest-1.0.

    O atributo `view` pode ser definido como TypedDict futuramente.
    Por enquanto, deixamos como dict porque as informações contidas nele são irrelevantes para o nosso uso.
    (https://learn.microsoft.com/en-us/graph/api/resources/folderview?view=graph-rest-1.0).
    """

    childCount: int
    view: dict


class ItemReference(TypedDict):
    """
    Referências necessárias para endereçar um item do drive.

    Mais detalhes em: https://learn.microsoft.com/en-us/graph/api/resources/itemreference?view=graph-rest-1.0.
    """

    id: str
    name: str
    path: str
    driveId: str
    driveType: str
    shareId: str
    sharepointIds: SharePointIds
    siteId: str


class DriveItem(TypedDict, total=False):
    """
    Item do drive retornado pela API do MS Graph.

    Esta representação é uma simplificação, contendo apenas os campos que nos interessam no momento.
    A definição completa pode ser encontrada em: https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0.
    """

    id: str
    name: str
    webUrl: str
    folder: Folder
    file: File
    size: int
    parentReference: ItemReference
