import logging
from functools import partial

from django.conf import settings
from django.template.defaultfilters import pluralize
from acervo_academico.models import RotinaImportacao, ItemRotina, LogRotina
from djtools.assincrono import task
from djtools.utils import get_datetime_now
from microsoft.schemas import DriveItem
from microsoft.services import SharepointService
from rh.models import UnidadeOrganizacional


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


def criar_ou_atualizar_itemrotina(rotina: RotinaImportacao, sigla_campus: str, drive_item: DriveItem) -> tuple[ItemRotina, bool]:
    logger.info(f'Criando/atualizando item de rotina para o arquivo {drive_item["name"]} ({drive_item["id"]}).')
    item_rotina = None
    criado = False
    if 'file' in drive_item:
        item_rotina = ItemRotina.objects.filter(rotina=rotina, id_arquivo=drive_item['id']).first()
        if item_rotina is None:
            item_rotina = ItemRotina(rotina=rotina, id_arquivo=drive_item['id'])
            criado = True
        item_rotina.campus = UnidadeOrganizacional.objects.suap().campi().get(sigla=sigla_campus)
        item_rotina.nome_arquivo = drive_item['name']
        item_rotina.content_type_arquivo = drive_item['file']['mimeType']
        item_rotina.tamanho_arquivo = drive_item['size']
        item_rotina.url_arquivo = drive_item['webUrl']
        item_rotina.save()

    return item_rotina, criado


def processar_arquivo_do_drive(
    rotina: RotinaImportacao, sigla_campus: str, drive_item: DriveItem, apenas_simular=False, reprocessar_bem_sucedidos=False
):
    item_rotina, _ = criar_ou_atualizar_itemrotina(rotina, sigla_campus, drive_item)
    logger.debug(f'Processando arquivo {drive_item["name"]} ({drive_item["id"]}).')
    if item_rotina is not None and item_rotina.processado is False or reprocessar_bem_sucedidos:
        item_rotina.processar(apenas_simular=apenas_simular)


def item_esta_pronto_para_processamento(item: DriveItem):
    return 'OK' in item['name']


@task('Baixar dados da rotina de importação')
def baixar_metadados_da_rotina_de_importacao(rotina: RotinaImportacao, task=None):
    if rotina.em_processamento():
        task.finalize('Tarefa abortada porque rotina já está em processamento.', url=rotina.get_absolute_url(), error=True)
        return

    logger.info(f'Baixando metadados da {rotina}.')
    try:
        logger.info(f'Baixando metadados dos arquivos associados à {rotina}.')

        LogRotina.registrar_info(rotina, '-' * 100)
        LogRotina.registrar_info(rotina, 'Baixando metadados dos arquivos associados à rotina.')

        rotina.status = RotinaImportacao.EM_PROCESSAMENTO
        rotina.nome_do_projeto = rotina.consultar_nome_do_projeto()
        rotina.save()

        sp_service = SharepointService.get_instance(rotina.dominio_site, rotina.caminho_projeto, rotina.diretorio_raiz)
        diretorios_prontos = sp_service.buscar_diretorios_no_drive(func_filtro=item_esta_pronto_para_processamento)

        siglas_campi = UnidadeOrganizacional.objects.suap().campi().values_list('sigla', flat=True)
        for diretorio in task.iterate(diretorios_prontos):
            caminho = f'{diretorio["parentReference"]["path"]}/{diretorio["name"]}'
            sigla_campus = None
            for sigla in siglas_campi:
                if f'/{sigla}/' in caminho:
                    sigla_campus = sigla
                    break
            if sigla_campus is None:
                LogRotina.registrar_erro(rotina, f'Não foi possível identificar o campus do diretorio: {caminho.removeprefix("/drive/root:")}.')
                continue

            sp_service.processar_arquivos_do_diretorio(
                id_diretorio_pai=diretorio['id'],
                func_processar=partial(criar_ou_atualizar_itemrotina, rotina, sigla_campus),
            )

        rotina.status = RotinaImportacao.CRIADA
        rotina.save()
        LogRotina.registrar_erro(rotina, 'Metadados baixados com sucesso.')

    except Exception as e:
        detalhes_excecao = type(e).__name__ + ': ' + str(e)
        logger.error(f'Ocorreu um erro ao baixar os metadados da {rotina}: {detalhes_excecao}.')
        LogRotina.registrar_erro(rotina, f'{detalhes_excecao}')
        rotina.status = RotinaImportacao.FALHOU
        rotina.save()
        task.finalize(f'Ocorreu um erro ao processar a tarefa: {detalhes_excecao}', url=rotina.get_absolute_url(), error=True)

    task.finalize('Tarefa concluída com sucesso.', url=rotina.get_absolute_url())


@task('Processar rotina de importação do Acervo Acadêmico')
def processar_rotina_de_importacao(rotina: RotinaImportacao, qs_campi, reprocessar_bem_sucedidos=False, task=None):
    if rotina.em_processamento():
        task.finalize('Tarefa abortada porque a rotina já está em processamento.', url=rotina.get_absolute_url(), error=True)
        return

    try:
        qs_todos_os_campi = UnidadeOrganizacional.objects.suap().campi()
        siglas_de_todos_os_campi = qs_todos_os_campi.values_list('sigla', flat=True)
        siglas_dos_campi_selecionados = qs_campi.values_list('sigla', flat=True)

        if qs_campi.count() == qs_todos_os_campi.count():
            campi_str = 'todos os campi'
        else:
            qtd_campi = qs_campi.count()
            campi_str = f'{pluralize(qtd_campi, "o campus,os campi")} {", ".join(siglas_dos_campi_selecionados)}'

        logger.info(f'Iniciando processamento da rotina de importação #{rotina.pk}.')
        LogRotina.registrar_info(rotina, '-' * 100)
        LogRotina.registrar_info(rotina, f'Iniciando processamento da rotina para {campi_str}.')

        rotina.status = RotinaImportacao.EM_PROCESSAMENTO
        rotina.nome_do_projeto = rotina.consultar_nome_do_projeto()
        rotina.save()

        qs_itens = (rotina.itens if reprocessar_bem_sucedidos else rotina.itens.exclude(status=ItemRotina.PROCESSADO)).filter(
            campus__in=qs_campi.values_list('id', flat=True)
        )
        qs_itens.update(status=ItemRotina.NA_FILA, detalhes_execucao='')

        sp_service = SharepointService.get_instance(rotina.dominio_site, rotina.caminho_projeto, rotina.diretorio_raiz)
        diretorios_prontos = sp_service.buscar_diretorios_no_drive(func_filtro=item_esta_pronto_para_processamento)

        logger.debug(f'Diretórios prontos: {[diretorio["parentReference"]["path"] for diretorio in diretorios_prontos]}')

        for diretorio in task.iterate(diretorios_prontos):
            logger.debug(f'Processando {diretorio}')
            caminho = f'{diretorio["parentReference"]["path"]}/{diretorio["name"]}'
            logger.debug(f'Processando diretório {caminho}.')
            sigla_campus = None
            for sigla in siglas_de_todos_os_campi:
                if f'/{sigla}/' in caminho:
                    sigla_campus = sigla
                    break
            if sigla_campus is None:
                LogRotina.registrar_erro(rotina, f'Não foi possível identificar o campus do diretorio: {caminho.removeprefix("/drive/root:")}.')
                continue

            if sigla_campus in siglas_dos_campi_selecionados:
                sp_service.processar_arquivos_do_diretorio(
                    id_diretorio_pai=diretorio['id'],
                    func_processar=partial(
                        processar_arquivo_do_drive,
                        rotina,
                        sigla_campus,
                        apenas_simular=settings.DEBUG,
                        reprocessar_bem_sucedidos=reprocessar_bem_sucedidos,
                    ),
                )

        rotina.status = RotinaImportacao.FINALIZADA
        rotina.ultima_execucao = get_datetime_now()
        rotina.save()
        LogRotina.registrar_info(rotina, 'Processamento finalizado.')
        task.finalize('Tarefa concluída com sucesso.', url=rotina.get_absolute_url())

    except Exception as e:
        detalhes_excecao = type(e).__name__ + ': ' + str(e)
        logger.error(f'Ocorreu um erro na importação: {detalhes_excecao}.')
        LogRotina.registrar_erro(rotina, f'{detalhes_excecao}')
        rotina.status = RotinaImportacao.FALHOU
        rotina.ultima_execucao = get_datetime_now()
        rotina.save()
        task.finalize(f'Ocorreu um erro ao processar a tarefa: {detalhes_excecao}', url=rotina.get_absolute_url(), error=True)


@task('Processar item de rotina de importação')
def processar_item_rotina(item_rotina, task=None):
    task.start_progress()

    item_rotina.processar()

    task.finalize('Processamento concluído. Acesse o item para mais detalhes.', url=item_rotina.get_absolute_url())
