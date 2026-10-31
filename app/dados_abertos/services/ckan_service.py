"""Serviços de sincronização com o CKAN.

Este módulo concentra as rotinas de alto nível para sincronização de
organizações, datasets e resources com uma instância CKAN remota,
utilizando o cliente definido em ``ckan_client``.

As docstrings utilizam o estilo Google para facilitar a geração
automática de documentação.
"""

from django.utils import timezone
from ..ckan_client import CKANClient, CKANError
from .metadados import CAMPOS_ESCALARES, payload_dataset
from django.core.exceptions import ValidationError
from django.db.models.fields.files import FieldFile
import logging

logger = logging.getLogger(__name__)


class DatasetNotFoundError(Exception):
    """Erro de dataset não encontrado no CKAN.

    Usado quando não é possível localizar o dataset remoto por ``id`` ou
    por ``name``. Tipicamente indica que o dataset foi removido ou que o
    ``name`` colide com um registro soft-deletado.

    Attributes:
        dataset_name: Nome do dataset utilizado na busca.
    """

    def __init__(self, dataset_name):
        super().__init__(f"Dataset '{dataset_name}' não encontrado no CKAN.")


class DatasetConflictError(Exception):
    """Erro de conflito ao sincronizar dataset.

    Em geral mapeia respostas HTTP 409 do CKAN, como tentativa de criar
    um dataset com ``name`` já existente.

    Attributes:
        dataset_name: Nome do dataset local.
        detail: Texto adicional para contexto do conflito.
    """

    def __init__(self, dataset_name, detail: str | None = None):
        msg = f"Conflito ao sincronizar o dataset '{dataset_name}' no CKAN."
        if detail:
            msg += f' Detalhe: {detail}'
        super().__init__(msg)


class DatasetSoftDeletedError(Exception):
    """Indica que o dataset remoto está em estado ``deleted`` (soft-delete).

    Nessa condição, o CKAN não permite reuso do mesmo ``name`` até que o
    dataset seja reativado (``state=active``) ou renomeado.
    """

    def __init__(self, dataset_name):
        super().__init__(f"Dataset '{dataset_name}' está soft-deleted no CKAN. Reative-o (state=active) ou renomeie o dataset local.")


class ImagemOrganizacaoError(Exception):
    """A imagem da organização não pôde ser lida localmente ou não foi aceita pelo CKAN."""


class ResourceNotFoundError(Exception):
    """Erro de resource não encontrado no CKAN."""

    def __init__(self, resource_name):
        super().__init__(f"Resource '{resource_name}' não encontrado no CKAN.")


class ResourceConflictError(Exception):
    """Erro de conflito ao sincronizar resource.

    Usado quando múltiplos resources remotos satisfazem os critérios de
    busca (ex.: mesmo ``name``) ou quando há conflito de atualização.
    """

    def __init__(self, resource_name, detail: str | None = None):
        msg = f"Conflito ao sincronizar o resource '{resource_name}' no CKAN."
        if detail:
            msg += f' Detalhe: {detail}'
        super().__init__(msg)


def _imagem_para_upload(org) -> FieldFile | None:
    """Retorna o arquivo de imagem da organização, ou ``None`` se não houver.

    O arquivo é entregue como ``FieldFile``, para que o cliente o leia pelo storage. Usar
    ``FieldFile.path`` aqui amarraria a sincronização ao sistema de arquivos: em produção a
    mídia fica num storage remoto (S3/MinIO), cujo ``path`` levanta ``NotImplementedError``
    — e nenhuma organização com imagem anexada conseguia ser sincronizada.

    Args:
        org: Instância de ``Organizacao``.

    Returns:
        FieldFile | None: Arquivo da imagem, quando há uma anexada.

    Raises:
        ImagemOrganizacaoError: Se há imagem anexada mas o arquivo não está no storage,
            ou se o storage não pôde ser consultado.
    """
    imagem = getattr(org, 'imagem', None)
    if not imagem:
        return None
    try:
        existe_no_storage = imagem.storage.exists(imagem.name)
    except Exception as e:
        raise ImagemOrganizacaoError(f"não foi possível ler a imagem de '{org.nome}': {e}") from e
    # Sem esta checagem quem falha é o `open()` dentro do cliente, com um erro que não
    # menciona imagem alguma e não ajuda quem lê a mensagem no admin.
    if not existe_no_storage:
        raise ImagemOrganizacaoError(f"a imagem de '{org.nome}' não está mais no storage: {imagem.name}")
    return imagem


def _imagem_registrada_no_ckan(result: dict | None) -> bool:
    """Diz se o CKAN registrou alguma imagem para a organização.

    A prova é a presença de **qualquer** um dos dois campos. O ``group_dictize`` do
    CKAN 2.11.5 sempre deriva ``image_display_url`` de ``image_url``, mas depender só
    do derivado amarraria a detecção a um detalhe de serialização. Os dois vazios
    significam uma coisa só — nada foi registrado —, que é o caso de produção que
    motivou esta correção: ``image_url: ''`` e zero arquivos em
    ``storage/uploads/group/``.

    Args:
        result: Retorno de ``organization_create``/``organization_update``.

    Returns:
        bool: ``True`` se há imagem registrada no CKAN.
    """
    dados = result or {}
    return bool(dados.get('image_display_url') or dados.get('image_url'))


def _url_da_imagem_enviada(result: dict | None) -> str:
    """Extrai do retorno do CKAN a URL navegável da imagem recém-enviada.

    O CKAN devolve em ``image_url`` apenas o **nome do arquivo** gravado no storage;
    a URL completa vem em ``image_display_url``. Gravar o nome cru em
    ``Organizacao.url_imagem`` (um ``URLField``) faria a sincronização seguinte
    reenviá-lo como se fosse uma URL — então só passa daqui o que de fato é URL.

    Args:
        result: Retorno de ``organization_create``/``organization_update``.

    Returns:
        str: URL de exibição da imagem, ou vazio se o retorno não trouxer uma.
    """
    dados = result or {}
    for campo in ('image_display_url', 'image_url'):
        valor = dados.get(campo) or ''
        if valor.startswith(('http://', 'https://')):
            return valor
    return ''


def sync_organization_with_ckan(org_queryset, base_url: str, api_key: str) -> tuple[int, int, list[str]]:
    """Sincroniza as organizações selecionadas com o CKAN.

    Para cada organização do queryset, cria ou atualiza a entidade no
    CKAN. Quando houver imagem local, realiza upload multipart com o
    campo ``image_upload``; caso contrário, usa ``image_url``.

    Args:
        org_queryset: QuerySet de ``OrganizacaoCKAN`` a sincronizar.
        base_url: URL base do CKAN.
        api_key: Chave de API do CKAN.

    Returns:
        tuple[int, int, list[str]]: Quantidade de sucessos, de erros e
        lista de mensagens de erro detalhadas (se houver).
    """
    client = CKANClient(base_url=base_url, api_key=api_key)
    success_count = 0
    error_count = 0
    errors = []

    for org in org_queryset:
        try:
            # Prepara o payload para o CKAN
            data = {
                'name': org.nome,
                'title': org.titulo or org.nome,  # 'title' é obrigatório no CKAN
                'description': org.descricao or '',
                # image_url só será enviada quando não houver upload
                'state': org.estado or 'active',  # Default para 'active' se não definido
                'extras': [{'key': k, 'value': v} for k, v in (org.extras or {}).items()],
            }

            # Detecta a imagem anexada para upload. Uma falha aqui é erro, não ausência de
            # imagem: seguir sem o arquivo sincronizaria tudo menos aquilo que o usuário
            # anexou, e ainda relataria sucesso.
            imagem = _imagem_para_upload(org)

            # Se não houver upload, usa a URL local (se existir). Só vale o que de fato
            # é uma URL: registros que passaram pelo código antigo guardam em url_imagem
            # o nome de arquivo devolvido pelo CKAN, e reenviá-lo espalharia o estrago.
            if not imagem:
                url_local = org.url_imagem or ''
                data['image_url'] = url_local if url_local.startswith(('http://', 'https://')) else None

            logger.info(f"Sincronizando organização '{org.nome}' com payload: {data} upload={'sim' if imagem else 'não'}")

            # Cria/Atualiza
            result = None
            if org.id_remoto:
                result = client.organization_update({'id': org.id_remoto, **data}, imagem=imagem)
            else:
                result = client.organization_create(data, imagem=imagem)
                org.id_remoto = (result or {}).get('id', org.id_remoto)

            # Se houve upload, refletir a URL retornada no campo local url_imagem
            url_remota = _url_da_imagem_enviada(result) if imagem else ''
            if url_remota:
                org.url_imagem = url_remota

            # Grava antes de cobrar a imagem: numa primeira sincronização o CKAN já
            # criou a organização e devolveu o id, e perder esse id faria a próxima
            # tentativa criá-la de novo, colidindo com o nome que agora existe lá.
            if imagem and not _imagem_registrada_no_ckan(result):
                # Persiste o que o CKAN confirmou — sobretudo o id_remoto de uma
                # organização recém-criada, cuja perda faria a próxima tentativa criá-la
                # de novo — mas sem carimbar `sincronizado_em`: a sincronização não se
                # completou, e a listagem não pode dizer que sim depois que a mensagem
                # de erro sair da tela.
                org.save(update_fields=['id_remoto', 'url_imagem'])
                raise ImagemOrganizacaoError(
                    f"o CKAN aceitou a atualização de '{org.nome}' mas não registrou a imagem enviada; "
                    'confira o ckan.storage_path e os limites de upload do servidor'
                )

            org.sincronizado_em = timezone.now()
            org.save(update_fields=['id_remoto', 'sincronizado_em', 'url_imagem'])
            success_count += 1
        except ImagemOrganizacaoError as e:
            error_count += 1
            errors.append(str(e))
            logger.warning(f"Imagem não sincronizada para a organização '{org.nome}': {e}")
        except CKANError as e:
            error_count += 1
            errors.append(str(e))
            logger.warning(f"Erro ao sincronizar organização '{org.nome}': {e}")
        except Exception as e:
            error_count += 1
            errors.append(str(e))
            logger.exception(f"Erro inesperado ao sincronizar organização '{org.nome}': {e}")

    return success_count, error_count, errors


def _try_get_dataset(client: CKANClient, key: str):
    """Tenta obter um dataset e retorna ``None`` quando não encontrado.

    Args:
        client: Instância de ``CKANClient``.
        key: ``id`` (UUID) ou ``name`` do dataset.

    Returns:
        dict | None: Dataset remoto, caso exista.
    """
    try:
        return client.package_show(key)
    except CKANError as e:
        if '404' in str(e) or 'Not found' in str(e):
            return None
        raise


def sync_dataset_with_ckan(dataset_queryset, base_url, api_key):
    """Sincroniza datasets (packages) com o CKAN.

    Ao atualizar, aplica diffs apenas nos campos alterados (os escalares de
    ``metadados.CAMPOS_ESCALARES``, tags e extras). Se não existir remotamente, tenta criar e
    lida com conflitos 409 (incluindo casos de soft-delete).

    Args:
        dataset_queryset: QuerySet de ``DatasetCKAN`` a sincronizar.
        base_url: URL base do CKAN.
        api_key: Chave de API do CKAN.

    Returns:
        tuple[int, int]: Quantidades de sucessos e erros.

    Raises:
        DatasetNotFoundError: Se dataset esperado não for encontrado.
        DatasetSoftDeletedError: Se o dataset remoto estiver soft-deleted.
        DatasetConflictError: Em conflitos de nome.
    """
    client = CKANClient(base_url=base_url, api_key=api_key)
    success = 0
    errors = 0

    for ds in dataset_queryset:
        try:
            remote = None
            if ds.id_remoto:
                remote = _try_get_dataset(client, ds.id_remoto)
                if not remote:
                    remote = _try_get_dataset(client, ds.nome)
                    if remote:
                        ds.id_remoto = remote.get('id')
                    else:
                        ds.estado = 'deleted'
                        ds.sincronizado_em = timezone.now()
                        ds.save(update_fields=['estado', 'sincronizado_em'])
                        raise DatasetNotFoundError(ds.nome)
            else:
                remote = _try_get_dataset(client, ds.nome)

            if remote:
                # Atualiza estado local conforme remoto
                remote_state = remote.get('state') or 'active'
                if remote_state == 'deleted':
                    ds.estado = 'deleted'
                    ds.sincronizado_em = timezone.now()
                    ds.save(update_fields=['estado', 'sincronizado_em'])
                    raise DatasetSoftDeletedError(ds.nome)
                else:
                    if ds.estado != 'active':
                        ds.estado = 'active'

            payload = payload_dataset(ds)
            logger.info(f'[sync-dataset] {ds.nome} payload={payload} remoto={"existe" if remote else "novo"} state_local={ds.estado}')

            if remote:
                diffs = {}
                for k in CAMPOS_ESCALARES:
                    if k in payload and (remote.get(k) or '') != (payload.get(k) or ''):
                        diffs[k] = payload[k]
                remote_tags = sorted([t['name'] for t in remote.get('tags', [])])
                local_tags = sorted([t['name'] for t in payload['tags']])
                if remote_tags != local_tags:
                    diffs['tags'] = payload['tags']
                # sem groups
                remote_extras = {e['key']: e['value'] for e in remote.get('extras', [])}
                local_extras = {e['key']: e['value'] for e in payload['extras']}
                if remote_extras != local_extras:
                    diffs['extras'] = payload['extras']

                if diffs:
                    diffs['id'] = remote['id']
                    logger.debug(f'[sync-dataset] diffs={diffs}')
                    client.package_update(diffs)

                ds.id_remoto = remote['id']
                ds.estado = 'active'  # remoto ativo
            else:
                try:
                    created = client.package_create(payload)
                    ds.id_remoto = created.get('id')
                    ds.estado = 'active'
                except CKANError as e:
                    if '409' in str(e) or 'Conflict' in str(e):
                        again = _try_get_dataset(client, ds.nome)
                        if again:
                            if again.get('state') == 'deleted':
                                ds.estado = 'deleted'
                                ds.sincronizado_em = timezone.now()
                                ds.save(update_fields=['estado', 'sincronizado_em'])
                                raise DatasetSoftDeletedError(ds.nome)
                            ds.id_remoto = again.get('id')
                            ds.estado = 'active'
                        else:
                            raise DatasetConflictError(ds.nome, 'Nome já utilizado.')
                    else:
                        raise

            ds.sincronizado_em = timezone.now()
            ds.save(update_fields=['id_remoto', 'estado', 'sincronizado_em'])
            success += 1

        except (DatasetNotFoundError, DatasetSoftDeletedError, DatasetConflictError) as ex:
            errors += 1
            logger.warning(f'[sync-dataset] {ds.nome} erro: {ex}')
            raise
        except CKANError as ex:
            errors += 1
            logger.warning(f'[sync-dataset] {ds.nome} CKANError: {ex}')
        except Exception as ex:
            errors += 1
            logger.exception(f'[sync-dataset] {ds.nome} erro inesperado: {ex}')

    return success, errors


def _build_resource_payload(res):
    """Monta o payload de resource para a action API.

    Args:
        res: Instância local de ``ResourceCKAN``.

    Returns:
        dict: Payload compatível com ``resource_create/resource_patch``.
    """
    payload = {
        'name': res.nome,
        'description': getattr(res, 'descricao', '') or '',
        'format': getattr(res, 'formato', '') or '',
    }
    # Campos opcionais se existirem no model
    for attr in ('mimetype', 'url'):
        if hasattr(res, attr):
            val = getattr(res, attr) or None
            if val:
                # CKAN usa 'mimetype' e 'url'
                payload[attr] = val
    return payload


def _locate_remote_resource(
    client: CKANClient,
    dataset_key: str,
    local_name: str,
    *,
    local_format: str | None = None,
    is_link: bool | None = None,
    local_url: str | None = None,
):
    """Localiza um resource remoto dentro de um dataset.

    Critérios de refinamento aplicados em ordem:
    1. ``name`` (obrigatório);
    2. ``format`` (CSV/JSON), quando informado;
    3. Tipo (link vs upload), quando ``is_link`` for especificado;
    4. ``url`` (se ``is_link`` e ``local_url`` informado).

    Se após filtros persistirem múltiplos candidatos, gera
    ``ResourceConflictError`` para evitar ambiguidades.

    Args:
        client: Instância do cliente CKAN.
        dataset_key: ``id`` (UUID) ou ``name`` do dataset.
        local_name: Nome local do resource.
        local_format: Formato local (ex.: ``CSV`` ou ``JSON``).
        is_link: ``True`` para links, ``False`` para uploads, ``None`` para ignorar critério.
        local_url: URL local (aplicável quando ``is_link`` for ``True``).

    Returns:
        dict | None: Resource remoto correspondente, se encontrado.

    Raises:
        ResourceConflictError: Se houver mais de um candidato compatível.
    """
    try:
        resources = client.package_resources(dataset_key)
    except CKANError:
        return None

    candidates = [r for r in resources if r.get('name') == local_name]
    if not candidates:
        return None

    if local_format:
        lf = (local_format or '').lower()
        candidates = [r for r in candidates if (r.get('format') or '').lower() == lf]
        if not candidates:
            return None

    if is_link is not None:
        if is_link:
            candidates = [r for r in candidates if (r.get('url_type') or 'link') == 'link']
        else:
            candidates = [r for r in candidates if (r.get('url_type') or '') != 'link']
        if not candidates:
            return None

    if is_link and local_url:
        candidates = [r for r in candidates if (r.get('url') or None) == local_url]
        if not candidates:
            return None

    if len(candidates) > 1:
        raise ResourceConflictError(
            local_name,
            detail=f"Encontrado mais de um resource com mesmo nome no dataset '{dataset_key}'. Refine por formato/URL ou defina remote_id.",
        )

    return candidates[0]


def _localizar_recurso_remoto(client: CKANClient, res, dataset_key: str, is_link: bool):
    """Localiza o resource remoto: primeiro por ``id_remoto``, depois por nome dentro do dataset.

    Quando encontra pelo nome, grava o ``id_remoto`` no recurso local.

    Args:
        client: Instância do cliente CKAN.
        res: Recurso local.
        dataset_key: ``id`` ou ``name`` do dataset no CKAN.
        is_link: Se o recurso é um link (sem arquivo local).

    Returns:
        dict | None: Resource remoto, se existir.
    """
    if res.id_remoto:
        try:
            return client.resource_show(res.id_remoto)
        except CKANError:
            pass

    lookup = _locate_remote_resource(
        client,
        dataset_key,
        res.nome,
        local_format=res.formato,
        is_link=is_link,
        local_url=res.url if is_link else None,
    )
    if lookup:
        res.id_remoto = lookup.get('id')
    return lookup


def _criar_recurso_remoto(client: CKANClient, res, payload: dict, is_link: bool) -> str | None:
    """Cria o resource no CKAN, como link ou com upload do arquivo local.

    Args:
        client: Instância do cliente CKAN.
        res: Recurso local.
        payload: Payload já montado para a action API.
        is_link: Se o recurso é um link (sem arquivo local).

    Returns:
        str | None: ``id`` do resource criado no CKAN.

    Raises:
        ValidationError: Se o recurso não tem nem arquivo nem URL.
    """
    if is_link or not getattr(res, 'arquivo', None):
        if not is_link and not getattr(res, 'url', None):
            raise ValidationError('Resource sem url ou arquivo.')
        return client.resource_create(payload).get('id')
    return client.resource_create(payload, file_field='upload', arquivo=res.arquivo).get('id')


def _calcular_diffs_recurso(remote: dict, payload: dict, is_link: bool) -> dict:
    """Campos cujo valor remoto difere do local.

    Args:
        remote: Resource como está no CKAN.
        payload: Payload montado a partir do recurso local.
        is_link: Se o recurso é um link (a URL só é comparada nesse caso).

    Returns:
        dict: Somente os campos a serem enviados no patch.
    """
    diffs = {}
    for campo in ('name', 'description', 'format'):
        if remote.get(campo, '') != payload.get(campo, ''):
            diffs[campo] = payload.get(campo, '')
    if 'mimetype' in payload and remote.get('mimetype') != payload.get('mimetype'):
        diffs['mimetype'] = payload.get('mimetype')
    if is_link and remote.get('url') != payload.get('url'):
        diffs['url'] = payload.get('url')
    return diffs


def recurso_alterado_apos_sync(res) -> bool:
    """Indica se o recurso foi alterado depois da última sincronização.

    É o sinal de que o arquivo local foi substituído: sem ele, trocar apenas o conteúdo (sem mexer
    em nome, descrição ou formato) não produziria diffs e o dado novo nunca subiria ao CKAN.

    Mede a **linha inteira** (``data_atualizacao`` é ``auto_now``), não o arquivo isoladamente:
    editar só a descrição também marca alterado. Distinguir um caso do outro exigiria guardar um
    marcador próprio do arquivo (hash ou instante do último upload).

    Args:
        res: Recurso local.

    Returns:
        bool: ``True`` quando nunca sincronizou ou quando mudou após a última sincronização.
    """
    if not res.sincronizado_em:
        return True
    return bool(res.data_atualizacao and res.data_atualizacao > res.sincronizado_em)


def _precisa_reenviar_arquivo(res, remote: dict, diffs: dict, force_file: bool) -> bool:
    """Decide se o conteúdo do arquivo local deve subir de novo ao CKAN.

    Args:
        res: Recurso local.
        remote: Resource como está no CKAN.
        diffs: Campos de metadado alterados.
        force_file: Se ``True``, força o reenvio.

    Returns:
        bool: ``True`` quando o arquivo deve ser reenviado.
    """
    if not getattr(res, 'arquivo', None):
        return False
    return bool(force_file or diffs or remote.get('url_type') == 'link' or recurso_alterado_apos_sync(res))


def _atualizar_recurso_remoto(client: CKANClient, res, remote: dict, payload: dict, is_link: bool, force_file: bool) -> str | None:
    """Aplica no CKAN os metadados alterados e, quando necessário, reenvia o arquivo.

    Args:
        client: Instância do cliente CKAN.
        res: Recurso local.
        remote: Resource como está no CKAN.
        payload: Payload montado a partir do recurso local.
        is_link: Se o recurso é um link (sem arquivo local).
        force_file: Se ``True``, força o reenvio do arquivo.

    Returns:
        str: ``id`` do resource no CKAN.
    """
    diffs = _calcular_diffs_recurso(remote, payload, is_link)
    reenviar_arquivo = False

    if not is_link:
        reenviar_arquivo = _precisa_reenviar_arquivo(res, remote, diffs, force_file)
        virou_link = not getattr(res, 'arquivo', None) and remote.get('url_type') != 'link'
        if virou_link and getattr(res, 'url', None):
            diffs['url'] = res.url

    if not (diffs or reenviar_arquivo):
        return res.id_remoto

    update_payload = {'id': res.id_remoto, **diffs}
    if reenviar_arquivo:
        atualizado = client.resource_update(update_payload, file_field='upload', arquivo=res.arquivo)
    else:
        atualizado = client.resource_update(update_payload)
    return atualizado.get('id', res.id_remoto)


def _registrar_sincronizacao(res, id_remoto: str | None) -> None:
    """Grava no recurso local o ``id`` remoto e o instante da sincronização."""
    res.id_remoto = id_remoto
    res.sincronizado_em = timezone.now()
    res.save(update_fields=['id_remoto', 'sincronizado_em'])


def _sincronizar_recurso(client: CKANClient, res, force_file: bool) -> None:
    """Cria ou atualiza um resource no CKAN e registra a sincronização no recurso local."""
    dataset_key = res.dataset.id_remoto or res.dataset.nome
    # tipo do recurso (link vs upload) precisa ser definido antes de localizar por nome
    is_link = bool(getattr(res, 'url', None)) and not getattr(res, 'arquivo', None)

    remote = _localizar_recurso_remoto(client, res, dataset_key, is_link)

    payload = _build_resource_payload(res)
    payload['package_id'] = dataset_key
    logger.info(f'[sync-resource] {res.nome} exists={bool(remote)} link={is_link} payload={payload}')

    if remote:
        id_remoto = _atualizar_recurso_remoto(client, res, remote, payload, is_link, force_file)
    else:
        id_remoto = _criar_recurso_remoto(client, res, payload, is_link)

    _registrar_sincronizacao(res, id_remoto)


def sync_resource_with_ckan(resource_queryset, base_url, api_key, *, force_file: bool = False):
    """Sincroniza recursos individuais com o CKAN.

    Regras principais:
    - Se ``id_remoto`` existe e ``resource_show`` falha, tenta localizar por
      nome dentro do dataset.
    - Se não localizar, cria um novo resource.
    - Para links (sem arquivo local) usa ``resource_create/update`` sem upload.
    - Para arquivos, usa ``resource_create/update`` com upload (campo
      ``upload``).
    - Nunca remove resources remotamente.

    Args:
        resource_queryset: QuerySet de ``ResourceCKAN`` a sincronizar.
        base_url: URL base do CKAN.
        api_key: Chave de API do CKAN.
        force_file: Se ``True``, força reenvio do arquivo mesmo sem diffs.

    Returns:
        tuple[int, int]: Quantidade de sucessos e de erros.
    """
    client = CKANClient(base_url=base_url, api_key=api_key)
    success = 0
    errors = 0

    for res in resource_queryset:
        try:
            _sincronizar_recurso(client, res, force_file)
            success += 1
        except (ResourceNotFoundError, ResourceConflictError, ValidationError) as ex:
            errors += 1
            logger.warning(f'[sync-resource] {res.nome} erro: {ex}')
        except CKANError as ex:
            errors += 1
            logger.warning(f'[sync-resource] {res.nome} CKANError: {ex}')
        except Exception as ex:
            errors += 1
            logger.exception(f'[sync-resource] {res.nome} erro inesperado: {ex}')

    return success, errors


def sync_dataset_resources_with_ckan(dataset_queryset, base_url, api_key, *, force_file: bool = False):
    """Sincroniza todos os resources de cada dataset selecionado.

    Args:
        dataset_queryset: QuerySet de ``DatasetCKAN``.
        base_url: URL base do CKAN.
        api_key: Chave de API do CKAN.
        force_file: Se ``True``, força reenvio de arquivos.

    Returns:
        tuple[int, int]: Total de sucessos e total de erros.
    """
    total_success = 0
    total_errors = 0
    for ds in dataset_queryset:
        # Garantir que dataset está remoto (tem remote_id ou existe)
        # Se não estiver sincronizado, ignore ou sincronize primeiro
        if not ds.id_remoto:
            logger.warning(f"[sync-dataset-resources] Dataset '{ds.nome}' sem id_remoto. Sincronize o dataset antes.")
            continue
        resources = getattr(ds, 'resources', None) or getattr(ds, 'recursos', None)
        if resources is None:
            logger.warning(f"[sync-dataset-resources] Dataset '{ds.nome}' sem relação de resources esperada.")
            continue
        success, errors = sync_resource_with_ckan(resources.all(), base_url, api_key, force_file=force_file)
        total_success += success
        total_errors += errors
    return total_success, total_errors


def toggle_dataset_state_with_ckan(dataset_queryset, base_url, api_key, target_state: str):
    """Altera o estado de datasets no CKAN (``active``/``deleted``).

    Atualiza somente o campo ``state`` no CKAN e reflete o estado
    localmente, sem modificar resources.

    Args:
        dataset_queryset: QuerySet de ``DatasetCKAN`` a atualizar.
        base_url: URL base do CKAN.
        api_key: Chave de API do CKAN.
        target_state: Estado alvo (``active`` ou ``deleted``).

    Returns:
        tuple[int, int]: Quantidade de sucessos e de erros.
    """
    assert target_state in ('active', 'deleted')
    client = CKANClient(base_url=base_url, api_key=api_key)
    success = 0
    errors = 0
    for ds in dataset_queryset:
        try:
            # Garantir existência remota
            remote = None
            if ds.id_remoto:
                remote = _try_get_dataset(client, ds.id_remoto)
            if not remote:
                remote = _try_get_dataset(client, ds.nome)
                if remote:
                    ds.id_remoto = remote.get('id')
                else:
                    # Sem dataset remoto não dá pra alterar state
                    raise DatasetNotFoundError(ds.nome)

            if remote.get('state') == target_state:
                # Já está no estado desejado
                if ds.estado != target_state:
                    ds.estado = target_state
                    ds.sincronizado_em = timezone.now()
                    ds.save(update_fields=['estado', 'sincronizado_em', 'id_remoto'])
                success += 1
                continue

            # Atualiza somente state
            client.package_update({'id': remote['id'], 'state': target_state})
            ds.estado = target_state
            ds.sincronizado_em = timezone.now()
            ds.save(update_fields=['estado', 'sincronizado_em', 'id_remoto'])
            success += 1
        except (DatasetNotFoundError, DatasetSoftDeletedError) as ex:
            errors += 1
            logger.warning(f'[toggle-dataset-state] {ds.nome} erro: {ex}')
        except CKANError as ex:
            errors += 1
            logger.warning(f'[toggle-dataset-state] {ds.nome} CKANError: {ex}')
        except Exception as ex:
            errors += 1
            logger.exception(f'[toggle-dataset-state] {ds.nome} erro inesperado: {ex}')
    return success, errors
